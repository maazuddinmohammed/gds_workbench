"""Prepare both layers’ Bindings against current registered metadata."""

import hashlib
import json
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any, LiteralString, cast

from gds_etl_workbench.application.change_sets.model import load_model_physical_scope
from gds_etl_workbench.application.change_sets.model_validation import (
    PhysicalModelCatalog,
    ValidatedModelChangeSet,
    validate_future_graph,
)
from gds_etl_workbench.application.model_read import ModelReadContext
from gds_etl_workbench.application.model_snapshot import (
    ModelReviewSnapshot,
    read_model_review_snapshot,
)
from gds_etl_workbench.domain.errors import InvalidRequestError
from gds_etl_workbench.domain.modeling_records import normalize_model_key_value
from gds_etl_workbench.domain.snapshots.metadata import normalize_natural_key_value
from gds_etl_workbench.domain.snapshots.model import ModelChangeSetDataset
from gds_etl_workbench.infrastructure.postgres import ReadTransaction

from .contracts import (
    ApplyModelBindingRequest,
    BindingAssignment,
    BindingAttribute,
    GeneratedBindingMatch,
    GeneratedBindingsPreview,
    GenerateModelBindingsRequest,
    ModelBindingPreview,
    PreviewModelBindingRequest,
    RegisteredTarget,
)
from .queries import BINDING_ENTITIES_SQL, TARGETS_FROM

_TARGET_SQL: LiteralString = """
SELECT object.object_id, object.object_schema, object.object_name,
       placement.tenant_code, system.system_code, connection.connection_code
  FROM core.object AS object
  JOIN core.connection AS connection ON connection.connection_id = object.connection_id
  JOIN core.tenant AS owner ON owner.gds_connection_id = connection.connection_id
  JOIN core.tenant AS placement ON placement.tenant_id = connection.tenant_id
  JOIN core.system AS system ON system.system_id = connection.system_id
  JOIN reference.zone AS zone ON zone.zone_id = object.zone_id
 WHERE object.object_id = %s AND owner.tenant_id = %s AND object.source_tenant_id = %s
   AND object.is_active AND owner.is_active AND placement.is_active AND system.is_active
   AND connection.is_active AND connection.is_global_data_store
   AND zone.is_active AND lower(btrim(zone.zone_code)) = %s
"""
_TARGET_ATTRIBUTES_SQL: LiteralString = """
SELECT attribute_id, attribute_name, attribute_data_type, attribute_nullability,
       is_natural_key, is_surrogate_key, is_meta_data, is_masking_required
  FROM core.attribute WHERE object_id = %s AND is_active
 ORDER BY attribute_ordinal_position, attribute_id LIMIT 5001
"""
_MASKED_SQL: LiteralString = """
SELECT DISTINCT mapping.logical_attribute_id
  FROM workflow.logical_attribute_source_mapping AS mapping
  JOIN core.attribute AS attribute ON attribute.attribute_id = mapping.source_attribute_id
 WHERE mapping.model_id = %s AND mapping.logical_attribute_source_mapping_status = 'active'
   AND attribute.is_masking_required
"""


@dataclass(frozen=True)
class PreparedModelBinding:
    preview: ModelBindingPreview
    validation: ValidatedModelChangeSet


async def load_model_binding(
    transaction: ReadTransaction,
    model: ModelReadContext,
    command: PreviewModelBindingRequest | ApplyModelBindingRequest,
) -> PreparedModelBinding:
    target = await transaction.fetch_one(
        _TARGET_SQL,
        (
            command.object_id,
            model.tenant_id,
            model.tenant_id,
            "silver" if command.layer == "logical" else "gold",
        ),
    )
    if target is None:
        raise InvalidRequestError(
            "Choose an active target owned by this Tenant on its GDS Connection and selected layer."
        )
    attributes = await transaction.fetch_all(_TARGET_ATTRIBUTES_SQL, (command.object_id,))
    if not attributes or len(attributes) > 5000:
        raise InvalidRequestError("The target must contain between 1 and 5,000 active Attributes.")
    masked_sql = (
        _MASKED_SQL if command.layer == "logical" else _MASKED_SQL.replace("logical", "dimensional")
    )
    masked = await transaction.fetch_all(masked_sql, (model.model_id,))
    return prepare_model_binding(
        model=model,
        review=await read_model_review_snapshot(transaction, model),
        physical_scope=await load_model_physical_scope(transaction, model),
        command=command,
        target=target,
        target_attributes=attributes,
        masked_attribute_ids={row[f"{command.layer}_attribute_id"] for row in masked},
    )


def prepare_model_binding(
    *,
    model: ModelReadContext,
    review: ModelReviewSnapshot,
    physical_scope: PhysicalModelCatalog,
    command: PreviewModelBindingRequest | ApplyModelBindingRequest,
    target: Mapping[str, Any],
    target_attributes: Sequence[Mapping[str, Any]],
    masked_attribute_ids: set[int],
) -> PreparedModelBinding:
    layer = command.layer
    entity = review.records_by_id.get(f"{layer}_entity", {}).get(command.entity_id)
    if entity is None or getattr(entity, f"{layer}_entity_status") != "active":
        raise InvalidRequestError("Choose an active Entity in this Model and layer.")
    entity_name: str = getattr(entity, f"{layer}_entity_name")
    logical: dict[int, dict[str, Any]] = {}
    for key, source_record in review.records_by_id.get(f"{layer}_attribute", {}).items():
        values = source_record.model_dump()
        if (
            normalize_model_key_value(values[f"{layer}_entity_name"])
            != normalize_model_key_value(entity_name)
            or values[f"{layer}_attribute_status"] != "active"
        ):
            continue
        attribute = {
            field.removeprefix(f"{layer}_attribute_"): value for field, value in values.items()
        }
        if layer == "dimensional":
            attribute["is_natural_key"] = attribute["key_role"] == "business"
            attribute["is_surrogate_key"] = attribute["key_role"] == "surrogate"
        logical[key] = attribute
    if not logical or len(logical) > 5000:
        raise InvalidRequestError("The Entity must contain between 1 and 5,000 active Attributes.")
    target_by_id = {row["attribute_id"]: row for row in target_attributes}
    same_entity = {"modeled_entity_type": f"{layer}_entity", "modeled_entity_name": entity_name}
    original_objects = {
        tuple(normalize_model_key_value(getattr(record, f)) for f in same_entity): record
        for record in review.snapshot.model_binding.objects
    }
    original_attributes = {
        normalize_model_key_value(record.modeled_attribute_name): record
        for record in review.snapshot.model_binding.attributes
        if record.modeled_entity_type == f"{layer}_entity"
        and normalize_model_key_value(record.modeled_entity_name)
        == normalize_model_key_value(entity_name)
    }
    object_record: dict[str, object] = {
        **same_entity,
        **{
            key: target[key]
            for key in (
                "tenant_code",
                "system_code",
                "connection_code",
                "object_schema",
                "object_name",
            )
        },
        "model_object_binding_status": "active",
        "model_object_binding_is_locked": False,
    }
    issues: list[str] = []
    old_object = original_objects.get(
        tuple(normalize_model_key_value(value) for value in same_entity.values())
    )
    if old_object:
        object_record["model_object_binding_is_locked"] = old_object.model_object_binding_is_locked
        if old_object.model_object_binding_status == "active" and any(
            normalize_natural_key_value(field, getattr(old_object, field))
            != normalize_natural_key_value(field, value)
            for field, value in object_record.items()
        ):
            issues.append(
                "This Entity already has an active Object Binding. "
                "Review its existing Binding before changing targets."
            )
    suggested: dict[int, int] = {}
    if command.assignments is None:
        targets_by_name: dict[object, list[int]] = {}
        for row in target_attributes:
            key = str(row["attribute_name"]).strip().lower()
            targets_by_name.setdefault(key, []).append(row["attribute_id"])
        for logical_id, attribute in logical.items():
            existing = original_attributes.get(normalize_model_key_value(attribute["name"]))
            name = existing.attribute_name if existing else attribute["name"]
            matches = targets_by_name.get(str(name).strip().lower(), [])
            if len(matches) == 1:
                suggested[logical_id] = matches[0]
    else:
        suggested = {item.modeled_attribute_id: item.attribute_id for item in command.assignments}
        if not set(suggested).issubset(logical) or not set(suggested.values()).issubset(
            target_by_id
        ):
            raise InvalidRequestError(
                "An Attribute assignment is outside the selected Entity or Object."
            )
    if (
        set(suggested) != set(logical)
        or set(suggested.values()) != set(target_by_id)
        or len(set(suggested.values())) != len(suggested)
    ):
        issues.append(
            "Assign every active modeled and target Attribute exactly once, "
            "including keys and audit columns."
        )
    records: list[dict[str, object]] = []
    assignments: list[BindingAssignment] = []
    for logical_id, attribute in sorted(
        logical.items(), key=lambda item: (item[1]["ordinal_position"], item[0])
    ):
        physical = target_by_id.get(suggested.get(logical_id))
        assignments.append(
            BindingAssignment(
                binding_id=next(
                    (
                        key
                        for key, record in review.records_by_id.get(
                            "model_attribute_binding", {}
                        ).items()
                        if record
                        == original_attributes.get(normalize_model_key_value(attribute["name"]))
                    ),
                    None,
                ),
                is_locked=bool(
                    original_attributes.get(normalize_model_key_value(attribute["name"]))
                    and original_attributes[
                        normalize_model_key_value(attribute["name"])
                    ].model_attribute_binding_is_locked
                ),
                modeled_attribute_id=logical_id,
                modeled_attribute_name=attribute["name"],
                modeled_data_type=attribute["data_type"],
                attribute_id=physical["attribute_id"] if physical else None,
            )
        )
        if physical is None:
            continue
        record: dict[str, object] = {
            **same_entity,
            "modeled_attribute_name": attribute["name"],
            "attribute_name": physical["attribute_name"],
            "model_attribute_binding_status": "active",
            "model_attribute_binding_is_locked": False,
        }
        old = original_attributes.get(normalize_model_key_value(attribute["name"]))
        if old:
            record["model_attribute_binding_is_locked"] = old.model_attribute_binding_is_locked
            if old.model_attribute_binding_status == "active" and normalize_natural_key_value(
                "attribute_name", old.attribute_name
            ) != normalize_natural_key_value("attribute_name", physical["attribute_name"]):
                issues.append(
                    f"{attribute['name']}: review the existing Attribute Binding "
                    "before changing it."
                )
        records.append(record)
        logical_type = re.sub(r"\s*([(),])\s*", r"\1", attribute["data_type"].strip().upper())
        target_type = re.sub(
            r"\s*([(),])\s*", r"\1", str(physical["attribute_data_type"]).strip().upper()
        )
        if logical_type != target_type:
            issues.append(f"{attribute['name']}: Modeled and registered storage types differ.")
        for source, field, label in (
            (attribute["is_nullable"], "attribute_nullability", "nullability"),
            (attribute["is_natural_key"], "is_natural_key", "natural key"),
            (attribute["is_surrogate_key"], "is_surrogate_key", "surrogate key"),
            (attribute["is_audit_column"], "is_meta_data", "audit column"),
        ):
            if source != physical[field]:
                issues.append(
                    f"{attribute['name']}: registered {label} differs from the modeled design."
                )
        if logical_id in masked_attribute_ids and not physical["is_masking_required"]:
            issues.append(
                f"{attribute['name']}: the registered target must preserve source masking."
            )
    documents: dict[ModelChangeSetDataset, list[dict[str, object]]] = {
        "model_object_binding": [object_record],
        "model_attribute_binding": records,
    }
    validation = validate_future_graph(
        snapshot=review.snapshot, staged_documents=documents, physical_scope=physical_scope
    )
    issues.extend(f"{issue.dataset}: {issue.message}" for issue in validation.issues)
    originals = {
        "model_object_binding": review.snapshot.model_binding.objects,
        "model_attribute_binding": review.snapshot.model_binding.attributes,
    }
    action_count = sum(
        record not in originals[dataset]
        for dataset, values in validation.records.items()
        for record in values
    )
    plan_digest = hashlib.sha256(
        json.dumps(
            {
                "model_revision": model.model_revision,
                "snapshot": review.snapshot.model_dump(mode="json"),
                "target": dict(target),
                "target_attributes": list(target_attributes),
                "assignments": [item.model_dump() for item in assignments],
                "issues": issues,
            },
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
        ).encode()
    ).hexdigest()
    return PreparedModelBinding(
        preview=ModelBindingPreview(
            model_id=model.model_id,
            model_revision=model.model_revision,
            entity_name=entity_name,
            binding_id=next(
                (
                    key
                    for key, record in review.records_by_id.get("model_object_binding", {}).items()
                    if record == old_object
                ),
                None,
            ),
            is_locked=bool(old_object and old_object.model_object_binding_is_locked),
            target=RegisteredTarget.model_validate(
                {field: target[field] for field in RegisteredTarget.model_fields}
            ),
            target_attributes=tuple(
                BindingAttribute(
                    attribute_id=row["attribute_id"],
                    attribute_name=row["attribute_name"],
                    data_type=row["attribute_data_type"],
                )
                for row in target_attributes
            ),
            assignments=tuple(assignments),
            can_apply=not issues and validation.valid,
            action_count=action_count,
            issues=tuple(issues[:100])
            + (
                (f"{len(issues) - 100} additional issues; correct the design and preview again.",)
                if len(issues) > 100
                else ()
            ),
            plan_digest=plan_digest,
        ),
        validation=validation,
    )


@dataclass(frozen=True)
class PreparedGeneratedBindings:
    preview: GeneratedBindingsPreview
    validation: ValidatedModelChangeSet


async def load_generated_bindings(
    transaction: ReadTransaction, model: ModelReadContext, command: GenerateModelBindingsRequest
) -> PreparedGeneratedBindings:
    """Build one reviewed Change Set from unambiguous name matches; preserve existing bindings."""
    entities = await transaction.fetch_all(BINDING_ENTITIES_SQL[command.layer], (model.model_id, 0))
    if not entities or len(entities) > 200:
        raise InvalidRequestError("Generate supports between 1 and 200 active Entities.")
    targets = await transaction.fetch_all(
        "SELECT object.object_id, object.object_name "
        + TARGETS_FROM
        + " AND lower(btrim(zone.zone_code)) = %s AND object.object_schema = %s "
        "ORDER BY object.object_id LIMIT 5001",
        (
            model.tenant_id,
            model.tenant_id,
            "silver" if command.layer == "logical" else "gold",
            command.object_schema,
        ),
    )
    if len(targets) > 5000:
        raise InvalidRequestError("Select a schema with at most 5,000 registered Objects.")
    review = await read_model_review_snapshot(transaction, model)
    physical_scope = await load_model_physical_scope(transaction, model)
    masked_sql = (
        _MASKED_SQL if command.layer == "logical" else _MASKED_SQL.replace("logical", "dimensional")
    )
    masked = {
        row[f"{command.layer}_attribute_id"]
        for row in await transaction.fetch_all(masked_sql, (model.model_id,))
    }
    by_name: dict[str, list[Mapping[str, Any]]] = {}
    for target in targets:
        by_name.setdefault(target["object_name"].strip().lower(), []).append(target)
    documents: dict[ModelChangeSetDataset, list[dict[str, object]]] = {
        "model_object_binding": [],
        "model_attribute_binding": [],
    }
    matches: list[GeneratedBindingMatch] = []
    digests: list[str] = []
    action_count = 0
    for entity in entities:
        base = {"entity_id": entity["entity_id"], "entity_name": entity["entity_name"]}
        if entity["binding_id"] is not None:
            matches.append(
                GeneratedBindingMatch(
                    **base,
                    object_id=entity["object_id"],
                    object_name=entity["object_name"],
                    status="locked" if entity["is_locked"] else "existing",
                )
            )
            continue
        candidates = by_name.get(entity["entity_name"].strip().lower(), [])
        if len(candidates) != 1:
            matches.append(
                GeneratedBindingMatch(**base, status="ambiguous" if candidates else "unmatched")
            )
            continue
        candidate = candidates[0]
        selection = PreviewModelBindingRequest(
            layer=command.layer,
            expected_model_revision=command.expected_model_revision,
            entity_id=entity["entity_id"],
            object_id=candidate["object_id"],
        )
        target = await transaction.fetch_one(
            _TARGET_SQL,
            (
                selection.object_id,
                model.tenant_id,
                model.tenant_id,
                "silver" if command.layer == "logical" else "gold",
            ),
        )
        attributes = await transaction.fetch_all(_TARGET_ATTRIBUTES_SQL, (selection.object_id,))
        if target is None or not attributes or len(attributes) > 5000:
            matches.append(
                GeneratedBindingMatch(
                    **base,
                    object_id=selection.object_id,
                    object_name=candidate["object_name"],
                    status="incompatible",
                    issues=("Target must contain 1–5,000 active Attributes.",),
                )
            )
            continue
        prepared = prepare_model_binding(
            model=model,
            review=review,
            physical_scope=physical_scope,
            command=selection,
            target=target,
            target_attributes=attributes,
            masked_attribute_ids=masked,
        )
        digests.append(prepared.preview.plan_digest)
        matches.append(
            GeneratedBindingMatch(
                **base,
                object_id=selection.object_id,
                object_name=candidate["object_name"],
                status="matched" if prepared.preview.can_apply else "incompatible",
                issues=prepared.preview.issues,
            )
        )
        if prepared.preview.can_apply:
            for dataset, records in prepared.validation.records.items():
                documents.setdefault(cast(ModelChangeSetDataset, dataset), []).extend(
                    record.model_dump(mode="json") for record in records
                )
            action_count += prepared.preview.action_count
        if sum(map(len, documents.values())) > 50_000:
            raise InvalidRequestError("Generated Bindings exceed the 50,000 record limit.")
    validation = validate_future_graph(
        snapshot=review.snapshot, staged_documents=documents, physical_scope=physical_scope
    )
    issues = tuple(f"{issue.dataset}: {issue.message}" for issue in validation.issues)
    digest = hashlib.sha256(
        json.dumps(
            {
                "request": command.model_dump(exclude={"expected_plan_digest"}),
                "model_revision": model.model_revision,
                "matches": [match.model_dump() for match in matches],
                "digests": digests,
                "candidate": validation.candidate_digest,
                "issues": issues,
            },
            sort_keys=True,
            ensure_ascii=False,
            separators=(",", ":"),
        ).encode()
    ).hexdigest()
    return PreparedGeneratedBindings(
        preview=GeneratedBindingsPreview(
            model_id=model.model_id,
            model_revision=model.model_revision,
            object_schema=command.object_schema,
            matches=tuple(matches),
            can_apply=validation.valid and action_count > 0,
            action_count=action_count,
            plan_digest=digest,
            issues=issues[:100],
        ),
        validation=validation,
    )
