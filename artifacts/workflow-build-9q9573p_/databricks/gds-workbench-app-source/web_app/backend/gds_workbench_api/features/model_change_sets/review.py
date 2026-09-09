"""Human lifecycle plans over existing owned records; never generate authored content."""

import hashlib
import json
from collections import defaultdict, deque
from dataclasses import asdict, dataclass, field
from typing import Literal, cast

from gds_etl_workbench.application.change_sets.model_validation import (
    PhysicalModelCatalog,
    ValidatedModelChangeSet,
    validate_future_graph,
)
from gds_etl_workbench.application.model_snapshot import ModelReviewSnapshot
from gds_etl_workbench.domain.errors import WorkbenchError
from gds_etl_workbench.domain.modeling_records import ModelingRecord, normalize_model_key_value
from gds_etl_workbench.domain.snapshots.model import DATASETS_BY_NAME, ModelChangeSetDataset

type ModelReviewDataset = Literal[
    "conceptual_object",
    "conceptual_relationship",
    "logical_submodel",
    "logical_entity",
    "logical_attribute",
    "logical_relationship",
    "dimensional_submodel",
    "dimensional_entity",
    "dimensional_attribute",
    "dimensional_relationship",
    "model_object_binding",
    "model_attribute_binding",
    "mapping_dependency",
    "mapping_object",
    "mapping_attribute",
    "generated_code",
    "generated_code_source_system",
    "validation_group",
    "validation_check",
]
type RecordReviewAction = Literal["lock", "unlock", "deactivate", "reactivate"]
type RecordIdentity = tuple[ModelReviewDataset, int]

# Dataset-specific lifecycle columns and snapshot collections. Table names remain
# a separate fixed SQL allowlist in the repository.
REVIEW_FIELDS: dict[ModelReviewDataset, tuple[str, str, str]] = {
    "conceptual_object": ("conceptual_object_is_locked", "conceptual_object_status", "objects"),
    "conceptual_relationship": (
        "conceptual_relationship_is_locked",
        "conceptual_relationship_status",
        "relationships",
    ),
    **{
        cast(ModelReviewDataset, f"{layer}_{kind}"): (
            f"{layer}_{kind}_is_locked",
            f"{layer}_{kind}_status",
            collection,
        )
        for layer in ("logical", "dimensional")
        for kind, collection in (
            ("submodel", "submodels"),
            ("entity", "entities"),
            ("attribute", "attributes"),
            ("relationship", "relationships"),
        )
    },
    "model_object_binding": (
        "model_object_binding_is_locked",
        "model_object_binding_status",
        "objects",
    ),
    "model_attribute_binding": (
        "model_attribute_binding_is_locked",
        "model_attribute_binding_status",
        "attributes",
    ),
    "mapping_dependency": (
        "mapping_source_system_dependency_is_locked",
        "mapping_source_system_dependency_status",
        "dependencies",
    ),
    "mapping_object": ("object_mapping_is_locked", "object_mapping_status", "objects"),
    "mapping_attribute": ("attribute_mapping_is_locked", "attribute_mapping_status", "attributes"),
    "generated_code": ("generated_code_is_locked", "generated_code_status", "artifacts"),
    "generated_code_source_system": (
        "generated_code_source_system_is_locked",
        "generated_code_source_system_status",
        "source_systems",
    ),
    "validation_group": ("is_locked", "is_active", "groups"),
    "validation_check": ("is_locked", "is_active", "checks"),
}


def review_lifecycle(record: ModelingRecord, dataset: ModelReviewDataset) -> tuple[bool, str]:
    lock_field, status_field, _ = REVIEW_FIELDS[dataset]
    status = getattr(record, status_field)
    return bool(getattr(record, lock_field)), (
        "active" if status else "inactive"
    ) if status_field == "is_active" else status


@dataclass(frozen=True, slots=True)
class ModelReviewDecision:
    dataset: ModelReviewDataset
    record_id: int
    selected: bool
    reason: str
    original: ModelingRecord = field(repr=False)
    reviewed: ModelingRecord = field(repr=False)


def plan_model_record_review(
    review: ModelReviewSnapshot,
    *,
    dataset: ModelReviewDataset,
    record_ids: list[int],
    action: RecordReviewAction,
) -> tuple[ModelReviewDecision, ...]:
    """Close lifecycle dependencies using existing canonical identities only."""
    selected = review.records_by_id.get(dataset, {})
    if (
        not record_ids
        or len(record_ids) != len(set(record_ids))
        or any(i not in selected for i in record_ids)
    ):
        raise WorkbenchError("model_record_not_found", "A selected record is unavailable.")
    records: dict[RecordIdentity, ModelingRecord] = {
        (name, i): row
        for name, rows in review.records_by_id.items()
        if name in REVIEW_FIELDS
        for i, row in rows.items()
    }
    keys: dict[tuple[ModelReviewDataset, tuple[object, ...]], RecordIdentity] = {
        (
            name,
            tuple(
                normalize_model_key_value(getattr(row, f))
                for f in DATASETS_BY_NAME[name].canonical_key
            ),
        ): identity
        for identity, row in records.items()
        for name in (identity[0],)
    }
    required: dict[RecordIdentity, str] = {(dataset, i): "Selected record." for i in record_ids}
    if action in {"deactivate", "reactivate"}:
        parents: dict[RecordIdentity, set[RecordIdentity]] = defaultdict(set)
        children: dict[RecordIdentity, set[RecordIdentity]] = defaultdict(set)

        def link(child: RecordIdentity, parent_dataset: ModelReviewDataset, *key: object) -> None:
            parent = keys.get((parent_dataset, tuple(normalize_model_key_value(v) for v in key)))
            if parent is not None:
                parents[child].add(parent)
                children[parent].add(child)

        for identity, record in records.items():
            name, _ = identity
            v = record.model_dump()
            if name == "conceptual_relationship":
                for side in ("from", "to"):
                    link(identity, "conceptual_object", v[f"{side}_conceptual_object_name"])
            elif name in {"logical_attribute", "dimensional_attribute"}:
                layer = name.split("_")[0]
                link(
                    identity, cast(ModelReviewDataset, layer + "_entity"), v[layer + "_entity_name"]
                )
            elif name in {"logical_relationship", "dimensional_relationship"}:
                layer = name.split("_")[0]
                for side in ("from", "to"):
                    link(
                        identity,
                        cast(ModelReviewDataset, layer + "_attribute"),
                        v[f"{side}_{layer}_entity_name"],
                        v[f"{side}_{layer}_attribute_name"],
                    )
            elif name in {
                "model_object_binding",
                "model_attribute_binding",
                "mapping_object",
                "mapping_attribute",
                "generated_code",
                "generated_code_source_system",
            }:
                entity = (v["modeled_entity_type"], v["modeled_entity_name"])
                layer = str(entity[0]).split("_")[0]
                if name == "model_object_binding":
                    link(identity, cast(ModelReviewDataset, entity[0]), entity[1])
                elif name == "model_attribute_binding":
                    link(identity, "model_object_binding", *entity)
                    link(
                        identity,
                        cast(ModelReviewDataset, layer + "_attribute"),
                        entity[1],
                        v["modeled_attribute_name"],
                    )
                elif name == "mapping_object":
                    link(identity, "model_object_binding", *entity)
                    link(identity, "mapping_dependency", entity[0], v["source_system_code"])
                elif name == "mapping_attribute":
                    link(identity, "mapping_object", *entity, v["source_system_code"])
                    link(identity, "model_attribute_binding", *entity, v["modeled_attribute_name"])
                elif name == "generated_code":
                    link(identity, "model_object_binding", *entity)
                else:
                    link(identity, "generated_code", *entity, v["artifact_name"])
                    link(identity, "mapping_object", *entity, v["source_system_code"])
            elif name == "validation_check":
                link(
                    identity,
                    "validation_group",
                    v["tenant_code"],
                    v["system_code"],
                    v["validation_group_name"],
                )

        # Coverage is bidirectional for active bindings/mappings. Retiring one
        # covered child retires its complete parent; reactivation restores only
        # historical rows for currently active (or selected) modeled Attributes.
        for identity, row in records.items():
            name, _ = identity
            v = row.model_dump()
            if name == "model_attribute_binding":
                entity = (v["modeled_entity_type"], v["modeled_entity_name"])
                attr = keys.get(
                    (
                        cast(ModelReviewDataset, str(entity[0]).split("_")[0] + "_attribute"),
                        tuple(
                            normalize_model_key_value(x)
                            for x in (entity[1], v["modeled_attribute_name"])
                        ),
                    )
                )
                binding = keys.get(
                    ("model_object_binding", tuple(normalize_model_key_value(x) for x in entity))
                )
                if (
                    binding is not None
                    and attr is not None
                    and (
                        review_lifecycle(records[attr], attr[0])[1] == "active"
                        or action == "reactivate"
                    )
                ):
                    link(binding, "model_attribute_binding", *entity, v["modeled_attribute_name"])
            elif name == "mapping_attribute":
                entity = (v["modeled_entity_type"], v["modeled_entity_name"])
                binding = keys.get(
                    (
                        "model_attribute_binding",
                        tuple(
                            normalize_model_key_value(x)
                            for x in (*entity, v["modeled_attribute_name"])
                        ),
                    )
                )
                header = keys.get(
                    (
                        "mapping_object",
                        tuple(
                            normalize_model_key_value(x) for x in (*entity, v["source_system_code"])
                        ),
                    )
                )
                if (
                    binding is not None
                    and header is not None
                    and (
                        review_lifecycle(records[binding], binding[0])[1] == "active"
                        or action == "reactivate"
                    )
                ):
                    link(
                        header,
                        "mapping_attribute",
                        *entity,
                        v["modeled_attribute_name"],
                        v["source_system_code"],
                    )
            elif name == "generated_code_source_system":
                code = keys.get(
                    (
                        "generated_code",
                        tuple(
                            normalize_model_key_value(v[f])
                            for f in ("modeled_entity_type", "modeled_entity_name", "artifact_name")
                        ),
                    )
                )
                if code is not None:
                    link(
                        code,
                        "generated_code_source_system",
                        v["modeled_entity_type"],
                        v["modeled_entity_name"],
                        v["artifact_name"],
                        v["source_system_code"],
                    )

        active_mappings: dict[str, set[RecordIdentity]] = defaultdict(set)
        active_groups: dict[str, set[RecordIdentity]] = defaultdict(set)
        for key, row in records.items():
            if review_lifecycle(row, key[0])[1] != "active":
                continue
            if key[0] == "mapping_object":
                active_mappings[
                    normalize_model_key_value(row.model_dump()["source_system_code"])
                ].add(key)
            elif key[0] == "validation_group":
                active_groups[normalize_model_key_value(row.model_dump()["system_code"])].add(key)
        code_by_entity: dict[tuple[str, str], set[RecordIdentity]] = defaultdict(set)
        for key, row in records.items():
            if key[0] == "generated_code" and review_lifecycle(row, key[0])[1] == "active":
                value = row.model_dump()
                code_by_entity[
                    (
                        value["modeled_entity_type"],
                        normalize_model_key_value(value["modeled_entity_name"]),
                    )
                ].add(key)
        queue = deque(required)
        while queue:
            identity = queue.popleft()
            for dependent in (children if action == "deactivate" else parents).get(identity, ()):
                status = review_lifecycle(records[dependent], dependent[0])[1]
                if dependent not in required and ((status == "active") == (action == "deactivate")):
                    required[dependent] = (
                        "Required by the selected lifecycle change and active dependency coverage."
                    )
                    queue.append(dependent)
            if action == "deactivate" and identity[0] == "generated_code":
                # Retire the applied Code bundle together. Removing just one
                # System's artifact must not leave the target apparently current.
                value = records[identity].model_dump()
                entity = (
                    value["modeled_entity_type"],
                    normalize_model_key_value(value["modeled_entity_name"]),
                )
                for key in code_by_entity[entity] - required.keys():
                    required[key] = (
                        "Retire the target's Code bundle to preserve "
                        "complete System assignment coverage."
                    )
                    queue.append(key)
            if action == "deactivate" and identity[0] == "mapping_object":
                system = normalize_model_key_value(
                    records[identity].model_dump()["source_system_code"]
                )
                active_mappings[system].discard(identity)
                if not active_mappings[system]:
                    for key in active_groups[system] - required.keys():
                        required[key] = (
                            "This System loses its last active Mapping; "
                            "retire its Validation Group and Checks."
                        )
                        queue.append(key)
        if len(required) > 50_000:
            raise WorkbenchError(
                "review_conflict", "The complete review exceeds Model Change Set limits."
            )
    decisions: list[ModelReviewDecision] = []
    for (name, record_id), reason in required.items():
        original = records[(name, record_id)]
        lock_field, status_field, _ = REVIEW_FIELDS[name]
        values = original.model_dump(mode="json")
        if action in {"lock", "unlock"}:
            values[lock_field] = action == "lock"
        else:
            values[status_field] = (
                (action == "reactivate")
                if status_field == "is_active"
                else ("active" if action == "reactivate" else "inactive")
            )
        decisions.append(
            ModelReviewDecision(
                dataset=name,
                record_id=record_id,
                selected=name == dataset and record_id in record_ids,
                reason=reason,
                original=original,
                reviewed=DATASETS_BY_NAME[name].row_model.model_validate(values, strict=False),
            )
        )
    return tuple(
        sorted(decisions, key=lambda item: (not item.selected, item.dataset, item.record_id))
    )


@dataclass(frozen=True, slots=True)
class PreparedModelReview:
    decisions: tuple[ModelReviewDecision, ...] = field(repr=False)
    validation: ValidatedModelChangeSet = field(repr=False)
    plan_digest: str


def prepare_model_record_review(
    review: ModelReviewSnapshot,
    *,
    physical_scope: PhysicalModelCatalog,
    dataset: ModelReviewDataset,
    record_ids: list[int],
    action: RecordReviewAction,
) -> PreparedModelReview:
    decisions = plan_model_record_review(
        review, dataset=dataset, record_ids=record_ids, action=action
    )
    snapshot = review.snapshot
    if action == "unlock":
        originals = [item.original for item in decisions]
        lock_field, _, collection = REVIEW_FIELDS[dataset]
        section = DATASETS_BY_NAME[dataset].section
        section_value = getattr(snapshot, section)
        snapshot = snapshot.model_copy(
            update={
                section: section_value.model_copy(
                    update={
                        collection: tuple(
                            record.model_copy(update={lock_field: False})
                            if record in originals
                            else record
                            for record in getattr(section_value, collection)
                        )
                    }
                )
            }
        )
    documents: dict[ModelChangeSetDataset, list[dict[str, object]]] = {}
    for item in decisions:
        documents.setdefault(item.dataset, []).append(item.reviewed.model_dump(mode="json"))
    validation = validate_future_graph(
        snapshot=snapshot,
        staged_documents=documents,
        physical_scope=physical_scope,
        code_authoring=action not in {"lock", "unlock"},
    )
    digest = hashlib.sha256(
        json.dumps(
            {
                "model_id": review.snapshot.model_id,
                "model_revision": review.snapshot.model_revision,
                "dataset": dataset,
                "record_ids": sorted(record_ids),
                "action": action,
                "candidate_digest": validation.candidate_digest,
                "decisions": [
                    {
                        "dataset": item.dataset,
                        "record_id": item.record_id,
                        "original": item.original.model_dump(mode="json"),
                    }
                    for item in decisions
                ],
                "issues": [asdict(issue) for issue in validation.issues],
            },
            ensure_ascii=False,
            allow_nan=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode()
    ).hexdigest()
    return PreparedModelReview(decisions=decisions, validation=validation, plan_digest=digest)
