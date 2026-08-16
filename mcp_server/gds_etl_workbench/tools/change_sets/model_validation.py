"""Shared Model Change Set record, uniqueness, and future-graph validation."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any, cast

from pydantic import ValidationError

from gds_etl_workbench.domain.modeling_records import (
    ModelingRecord,
    normalize_model_key_value,
)
from gds_etl_workbench.tools.snapshots.model.contracts import (
    DATASETS,
    DATASETS_BY_NAME,
    ModelingDatasetDefinition,
    ModelSnapshot,
    model_snapshot_records,
)

from .action_review import (
    ActionReviewKey,
    ChangeAction,
    DatasetActionReview,
    classify_record_action,
)

MAX_VALIDATION_ISSUES = 1000
MAX_REVIEW_KEYS = 100


@dataclass(frozen=True, slots=True)
class ModelValidationIssue:
    code: str
    dataset: str
    record_number: int | None
    fields: tuple[str, ...]
    message: str


type PhysicalObjectNaturalKey = tuple[str, str, str, str, str]
type PhysicalAttributeNaturalKey = tuple[str, str, str, str, str, str]


@dataclass(frozen=True, slots=True)
class PhysicalModelScope:
    model_tenant_code: str
    active_system_codes: frozenset[str]
    objects: frozenset[PhysicalObjectNaturalKey]
    attributes: frozenset[PhysicalAttributeNaturalKey]
    other_model_names: frozenset[str] = frozenset()


@dataclass(frozen=True, slots=True)
class ValidatedModelChangeSet:
    records: dict[str, tuple[ModelingRecord, ...]]
    phase: str
    candidate_digest: str | None
    issues: tuple[ModelValidationIssue, ...]
    action_review: tuple[DatasetActionReview, ...]

    @property
    def valid(self) -> bool:
        return not self.issues


def validate_staged_records(
    dataset: str,
    raw_records: list[dict[str, object]],
) -> tuple[tuple[ModelingRecord, ...], tuple[ModelValidationIssue, ...]]:
    definition = DATASETS_BY_NAME[dataset]
    records: list[ModelingRecord] = []
    issues: list[ModelValidationIssue] = []
    seen: set[tuple[object, ...]] = set()
    for record_number, raw in enumerate(raw_records, start=1):
        try:
            encoded = json.dumps(raw, ensure_ascii=False, separators=(",", ":"))
            record = definition.row_model.model_validate_json(encoded, strict=True)
        except (TypeError, ValueError, ValidationError):
            issues.append(
                ModelValidationIssue(
                    code="record_schema_invalid",
                    dataset=dataset,
                    record_number=record_number,
                    fields=(),
                    message=f"Record does not match the exact {dataset} schema.",
                )
            )
            continue
        key = _canonical_key(definition, record)
        if key in seen:
            issues.append(
                ModelValidationIssue(
                    code="duplicate_canonical_key",
                    dataset=dataset,
                    record_number=record_number,
                    fields=definition.canonical_key,
                    message="Record duplicates a canonical key in the staged dataset.",
                )
            )
            continue
        seen.add(key)
        records.append(record)
    return tuple(records), tuple(issues)


def validate_future_graph(
    *,
    snapshot: ModelSnapshot,
    staged_documents: dict[str, list[dict[str, object]]],
    physical_scope: PhysicalModelScope,
) -> ValidatedModelChangeSet:
    effective = model_snapshot_records(snapshot)
    staged: dict[str, tuple[ModelingRecord, ...]] = {}
    schema_issues: list[ModelValidationIssue] = []
    uniqueness_issues: list[ModelValidationIssue] = []
    for dataset, raw_records in staged_documents.items():
        records, dataset_issues = validate_staged_records(dataset, raw_records)
        staged[dataset] = records
        schema_issues.extend(
            issue for issue in dataset_issues if issue.code == "record_schema_invalid"
        )
        uniqueness_issues.extend(
            issue for issue in dataset_issues if issue.code == "duplicate_canonical_key"
        )
    if schema_issues:
        return _failed(staged, "schema", None, schema_issues)

    candidate_digest = _candidate_digest(staged)

    future: dict[str, tuple[ModelingRecord, ...]] = {}
    lock_issues: list[ModelValidationIssue] = []
    for definition in DATASETS:
        current = effective[definition.name]
        changes = staged.get(definition.name, ())
        by_key = {_canonical_key(definition, record): record for record in current}
        for record in changes:
            key = _canonical_key(definition, record)
            existing = by_key.get(key)
            if existing is not None and _record_is_locked(existing) and existing != record:
                lock_issues.append(
                    ModelValidationIssue(
                        code="record_locked",
                        dataset=definition.name,
                        record_number=None,
                        fields=definition.canonical_key,
                        message="A locked applied record cannot be changed.",
                    )
                )
            if existing is not None:
                _validate_locked_nested_records(
                    dataset=definition.name,
                    existing=existing,
                    changed=record,
                    issues=lock_issues,
                )
            by_key[key] = record
        future[definition.name] = tuple(by_key.values())
    if lock_issues:
        return _failed(staged, "locks", candidate_digest, lock_issues)

    scope_issues: list[ModelValidationIssue] = []
    _validate_model_details(future, physical_scope, scope_issues)
    _validate_physical_scope(staged, future["model_scope"], physical_scope, scope_issues)
    if scope_issues:
        return _failed(staged, "model_scope", candidate_digest, scope_issues)
    if uniqueness_issues:
        return _failed(staged, "uniqueness", candidate_digest, uniqueness_issues)

    reference_issues: list[ModelValidationIssue] = []
    _validate_references(future, reference_issues)
    if reference_issues:
        return _failed(staged, "references", candidate_digest, reference_issues)

    return ValidatedModelChangeSet(
        records=staged,
        phase="complete",
        candidate_digest=candidate_digest,
        issues=(),
        action_review=_build_action_review(effective, staged),
    )


def _failed(
    records: dict[str, tuple[ModelingRecord, ...]],
    phase: str,
    candidate_digest: str | None,
    issues: list[ModelValidationIssue],
) -> ValidatedModelChangeSet:
    return ValidatedModelChangeSet(
        records=records,
        phase=phase,
        candidate_digest=candidate_digest,
        issues=tuple(issues[:MAX_VALIDATION_ISSUES]),
        action_review=(),
    )


def _candidate_digest(records: dict[str, tuple[ModelingRecord, ...]]) -> str:
    candidate_document = {
        dataset: [record.model_dump(mode="json") for record in dataset_records]
        for dataset, dataset_records in sorted(records.items())
    }
    candidate_bytes = json.dumps(
        candidate_document,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(candidate_bytes).hexdigest()


def _build_action_review(
    current: dict[str, tuple[ModelingRecord, ...]],
    staged: dict[str, tuple[ModelingRecord, ...]],
) -> tuple[DatasetActionReview, ...]:
    remaining_keys = MAX_REVIEW_KEYS
    summaries: list[DatasetActionReview] = []
    for definition in DATASETS:
        staged_records = staged.get(definition.name, ())
        if not staged_records:
            continue
        current_by_key = {
            _canonical_key(definition, record): record for record in current[definition.name]
        }
        counts: dict[ChangeAction, int] = {
            "insert": 0,
            "update": 0,
            "deactivate": 0,
            "reactivate": 0,
            "no_change": 0,
        }
        keys: list[ActionReviewKey] = []
        for record in staged_records:
            key = _canonical_key(definition, record)
            existing = current_by_key.get(key)
            values = record.model_dump(mode="json")
            action = classify_record_action(
                existing.model_dump(mode="json") if existing is not None else None,
                values,
                active_state=_model_active_state,
            )
            counts[action] += 1
            if remaining_keys > 0:
                keys.append(
                    ActionReviewKey(
                        action=action,
                        natural_key={column: values[column] for column in definition.canonical_key},
                    )
                )
                remaining_keys -= 1
        summaries.append(
            DatasetActionReview(
                dataset=definition.name,
                insert_count=counts["insert"],
                update_count=counts["update"],
                deactivate_count=counts["deactivate"],
                reactivate_count=counts["reactivate"],
                no_change_count=counts["no_change"],
                keys=tuple(keys),
                keys_truncated=len(keys) < len(staged_records),
            )
        )
    return tuple(summaries)


def _model_active_state(values: Mapping[str, object]) -> bool | None:
    active = values.get("is_active")
    if isinstance(active, bool):
        return active
    status = next(
        (value for name, value in values.items() if name.endswith("_status")),
        None,
    )
    if status == "active":
        return True
    if status in {"inactive", "deprecated"}:
        return False
    return None


def _validate_model_details(
    future: dict[str, tuple[Any, ...]],
    catalog: PhysicalModelScope,
    issues: list[ModelValidationIssue],
) -> None:
    details = future["model_details"]
    if len(details) != 1:
        issues.append(
            ModelValidationIssue(
                code="model_details_invalid",
                dataset="model_details",
                record_number=None,
                fields=(),
                message="The future Model must contain exactly one Model details record.",
            )
        )
        return
    if normalize_model_key_value(details[0].model_name) in catalog.other_model_names:
        issues.append(
            ModelValidationIssue(
                code="model_name_conflict",
                dataset="model_details",
                record_number=None,
                fields=("model_name",),
                message="Another active Model in this Tenant already uses this name.",
            )
        )


def _validate_physical_scope(
    staged: Mapping[str, tuple[Any, ...]],
    future_scope_records: tuple[Any, ...],
    catalog: PhysicalModelScope,
    issues: list[ModelValidationIssue],
) -> None:
    active_scope_objects: set[PhysicalObjectNaturalKey] = set()
    for record in future_scope_records:
        natural_key = _physical_object_key(record)
        if natural_key not in catalog.objects:
            _scope_missing(
                issues,
                "model_scope",
                "object_name",
                "Referenced physical Object is not available to this Model Tenant.",
            )
        elif record.is_active:
            active_scope_objects.add(natural_key)
    scope = PhysicalModelScope(
        model_tenant_code=catalog.model_tenant_code,
        active_system_codes=catalog.active_system_codes,
        objects=frozenset(active_scope_objects),
        attributes=frozenset(
            attribute
            for attribute in catalog.attributes
            if attribute[:5] in active_scope_objects
        ),
        other_model_names=catalog.other_model_names,
    )

    for record in staged.get("profiling_profile", ()):
        _require_attribute_scope(record, "profiling_profile", "attribute_name", scope, issues)
    for record in staged.get("analysis_result", ()):
        for endpoint in ("from", "to"):
            key = tuple(
                normalize_model_key_value(getattr(record, f"{endpoint}_{field}"))
                for field in (
                    "tenant_code",
                    "system_code",
                    "connection_code",
                    "object_schema",
                    "object_name",
                    "attribute_name",
                )
            )
            if key not in scope.attributes:
                _scope_missing(
                    issues,
                    "analysis_result",
                    f"{endpoint}_attribute_name",
                    "Referenced physical Attribute is not active in this Model Scope.",
                )

    for record in staged.get("modeling_assertion_document", ()):
        if record.tenant_code is not None and normalize_model_key_value(
            record.tenant_code
        ) != normalize_model_key_value(scope.model_tenant_code):
            _scope_missing(
                issues,
                "modeling_assertion_document",
                "tenant_code",
                "Assertion document Tenant does not own this Model.",
            )
        if (
            record.system_code is not None
            and normalize_model_key_value(record.system_code) not in scope.active_system_codes
        ):
            _scope_missing(
                issues,
                "modeling_assertion_document",
                "system_code",
                "Referenced System is not active.",
            )

    for dataset in ("conceptual_object", "conceptual_relationship"):
        for record in staged.get(dataset, ()):
            for support in record.supports:
                if support.support_source_type == "object":
                    _require_object_scope(
                        support.source_object,
                        dataset,
                        "source_object",
                        scope,
                        issues,
                    )

    for layer in ("logical", "dimensional"):
        for record in staged.get(f"{layer}_entity", ()):
            for source in record.sources:
                if source.support_source_type == "object":
                    _require_object_scope(
                        source.source_object,
                        f"{layer}_entity",
                        "source_object",
                        scope,
                        issues,
                    )
        for record in staged.get(f"{layer}_attribute", ()):
            for source in record.sources:
                if source.support_source_type == "attribute":
                    _require_attribute_scope(
                        source.source_attribute,
                        f"{layer}_attribute",
                        "source_attribute",
                        scope,
                        issues,
                    )

    for record in staged.get("mapping_dependency", ()):
        _require_active_system(
            record.source_system_code,
            "mapping_dependency",
            scope,
            issues,
        )
    for record in staged.get("mapping_object", ()):
        _require_object_scope(record, "mapping_object", "object_name", scope, issues)
        _require_active_system(
            record.source_system_code,
            "mapping_object",
            scope,
            issues,
        )
    for record in staged.get("mapping_attribute", ()):
        _require_attribute_scope(record, "mapping_attribute", "attribute_name", scope, issues)
        _require_active_system(
            record.source_system_code,
            "mapping_attribute",
            scope,
            issues,
        )


def _require_object_scope(
    key: Any,
    dataset: str,
    field: str,
    scope: PhysicalModelScope,
    issues: list[ModelValidationIssue],
) -> None:
    natural_key = _physical_object_key(key)
    if natural_key not in scope.objects:
        _scope_missing(
            issues,
            dataset,
            field,
            "Referenced physical Object is not active in this Model Scope.",
        )


def _physical_object_key(key: Any) -> PhysicalObjectNaturalKey:
    return cast(
        PhysicalObjectNaturalKey,
        tuple(
            normalize_model_key_value(getattr(key, name))
            for name in (
                "tenant_code",
                "system_code",
                "connection_code",
                "object_schema",
                "object_name",
            )
        ),
    )


def _require_attribute_scope(
    key: Any,
    dataset: str,
    field: str,
    scope: PhysicalModelScope,
    issues: list[ModelValidationIssue],
) -> None:
    natural_key = tuple(
        normalize_model_key_value(getattr(key, name))
        for name in (
            "tenant_code",
            "system_code",
            "connection_code",
            "object_schema",
            "object_name",
            "attribute_name",
        )
    )
    if natural_key not in scope.attributes:
        _scope_missing(
            issues,
            dataset,
            field,
            "Referenced physical Attribute is not active in this Model Scope.",
        )


def _require_active_system(
    system_code: str,
    dataset: str,
    scope: PhysicalModelScope,
    issues: list[ModelValidationIssue],
) -> None:
    if normalize_model_key_value(system_code) not in scope.active_system_codes:
        _scope_missing(
            issues,
            dataset,
            "source_system_code",
            "Referenced source System is not active.",
        )


def _scope_missing(
    issues: list[ModelValidationIssue],
    dataset: str,
    field: str,
    message: str,
) -> None:
    issues.append(
        ModelValidationIssue(
            code="model_scope_reference_invalid",
            dataset=dataset,
            record_number=None,
            fields=(field,),
            message=message,
        )
    )


def _validate_references(
    future: dict[str, tuple[Any, ...]],
    issues: list[ModelValidationIssue],
) -> None:
    assertion_documents = {
        normalize_model_key_value(record.modeling_assertion_document_name)
        for record in future["modeling_assertion_document"]
    }
    assertion_records = {
        normalize_model_key_value(record.modeling_assertion_record_key): record
        for record in future["modeling_assertion_record"]
    }
    for record in future["modeling_assertion_record"]:
        if (
            normalize_model_key_value(record.modeling_assertion_document_name)
            not in assertion_documents
        ):
            _missing(issues, "modeling_assertion_record", "modeling_assertion_document_name")

    conceptual_objects = {
        normalize_model_key_value(record.conceptual_object_name)
        for record in future["conceptual_object"]
    }
    for record in future["conceptual_object"]:
        _validate_supports(
            record.supports,
            layer="conceptual",
            dataset="conceptual_object",
            assertion_records=assertion_records,
            issues=issues,
        )
    for record in future["conceptual_relationship"]:
        if (
            normalize_model_key_value(record.from_conceptual_object_name) not in conceptual_objects
            or normalize_model_key_value(record.to_conceptual_object_name) not in conceptual_objects
        ):
            _missing(issues, "conceptual_relationship", "conceptual_object_name")
        _validate_supports(
            record.supports,
            layer="conceptual",
            dataset="conceptual_relationship",
            assertion_records=assertion_records,
            issues=issues,
        )

    _validate_modeled_layer(future, "logical", assertion_records, issues)
    _validate_modeled_layer(future, "dimensional", assertion_records, issues)

    dependencies = {
        (record.modeled_entity_type, normalize_model_key_value(record.source_system_code))
        for record in future["mapping_dependency"]
    }
    logical_entities = {
        normalize_model_key_value(record.logical_entity_name) for record in future["logical_entity"]
    }
    dimensional_entities = {
        normalize_model_key_value(record.dimensional_entity_name)
        for record in future["dimensional_entity"]
    }
    logical_attributes = {
        (
            normalize_model_key_value(record.logical_entity_name),
            normalize_model_key_value(record.logical_attribute_name),
        )
        for record in future["logical_attribute"]
    }
    dimensional_attributes = {
        (
            normalize_model_key_value(record.dimensional_entity_name),
            normalize_model_key_value(record.dimensional_attribute_name),
        )
        for record in future["dimensional_attribute"]
    }
    mapping_objects: set[tuple[object, ...]] = set()
    for record in future["mapping_object"]:
        if (
            record.modeled_entity_type,
            normalize_model_key_value(record.source_system_code),
        ) not in dependencies:
            _missing(issues, "mapping_object", "mapping_dependency")
        entity_names = (
            logical_entities
            if record.modeled_entity_type == "logical_entity"
            else dimensional_entities
        )
        if normalize_model_key_value(record.modeled_entity_name) not in entity_names:
            _missing(issues, "mapping_object", "modeled_entity_name")
        mapping_objects.add(_mapping_object_reference(record))
    for record in future["mapping_attribute"]:
        if _mapping_object_reference(record) not in mapping_objects:
            _missing(issues, "mapping_attribute", "mapping_object")
        modeled_attributes = (
            logical_attributes
            if record.modeled_entity_type == "logical_entity"
            else dimensional_attributes
        )
        if (
            normalize_model_key_value(record.modeled_entity_name),
            normalize_model_key_value(record.modeled_attribute_name),
        ) not in modeled_attributes:
            _missing(issues, "mapping_attribute", "modeled_attribute_name")


def _validate_modeled_layer(
    future: dict[str, tuple[Any, ...]],
    layer: str,
    assertion_records: dict[object, Any],
    issues: list[ModelValidationIssue],
) -> None:
    submodels = {
        normalize_model_key_value(getattr(record, f"{layer}_submodel_name"))
        for record in future[f"{layer}_submodel"]
    }
    entities = {
        normalize_model_key_value(getattr(record, f"{layer}_entity_name"))
        for record in future[f"{layer}_entity"]
    }
    attributes = {
        (
            normalize_model_key_value(getattr(record, f"{layer}_entity_name")),
            normalize_model_key_value(getattr(record, f"{layer}_attribute_name")),
        )
        for record in future[f"{layer}_attribute"]
    }
    for record in future[f"{layer}_entity"]:
        if any(
            normalize_model_key_value(membership.submodel_name) not in submodels
            for membership in record.submodels
        ):
            _missing(issues, f"{layer}_entity", "submodel_name")
        _validate_sources(
            record.sources,
            layer=layer,
            dataset=f"{layer}_entity",
            assertion_records=assertion_records,
            issues=issues,
        )
    for record in future[f"{layer}_attribute"]:
        entity_name = normalize_model_key_value(getattr(record, f"{layer}_entity_name"))
        if entity_name not in entities:
            _missing(issues, f"{layer}_attribute", f"{layer}_entity_name")
        _validate_sources(
            record.sources,
            layer=layer,
            dataset=f"{layer}_attribute",
            assertion_records=assertion_records,
            issues=issues,
        )
    for record in future[f"{layer}_relationship"]:
        endpoints = (
            (
                normalize_model_key_value(getattr(record, f"from_{layer}_entity_name")),
                normalize_model_key_value(getattr(record, f"from_{layer}_attribute_name")),
            ),
            (
                normalize_model_key_value(getattr(record, f"to_{layer}_entity_name")),
                normalize_model_key_value(getattr(record, f"to_{layer}_attribute_name")),
            ),
        )
        if any(endpoint not in attributes for endpoint in endpoints):
            _missing(issues, f"{layer}_relationship", f"{layer}_attribute_name")


def _validate_supports(
    supports: tuple[Any, ...],
    *,
    layer: str,
    dataset: str,
    assertion_records: dict[object, Any],
    issues: list[ModelValidationIssue],
) -> None:
    for support in supports:
        if support.support_source_type == "assertion":
            _validate_assertion_reference(
                support.assertion_record.modeling_assertion_record_key,
                layer,
                dataset,
                assertion_records,
                issues,
            )


def _validate_sources(
    sources: tuple[Any, ...],
    *,
    layer: str,
    dataset: str,
    assertion_records: dict[object, Any],
    issues: list[ModelValidationIssue],
) -> None:
    for source in sources:
        if source.support_source_type == "assertion":
            _validate_assertion_reference(
                source.assertion_record.modeling_assertion_record_key,
                layer,
                dataset,
                assertion_records,
                issues,
            )


def _validate_assertion_reference(
    key: str,
    layer: str,
    dataset: str,
    assertion_records: dict[object, Any],
    issues: list[ModelValidationIssue],
) -> None:
    assertion = assertion_records.get(normalize_model_key_value(key))
    if assertion is None:
        _missing(issues, dataset, "modeling_assertion_record_key")
    elif layer not in assertion.modeling_assertion_applicable_layers:
        issues.append(
            ModelValidationIssue(
                code="assertion_layer_invalid",
                dataset=dataset,
                record_number=None,
                fields=("modeling_assertion_record_key",),
                message="Referenced Assertion does not apply to this modeling layer.",
            )
        )


def _mapping_object_reference(record: Any) -> tuple[object, ...]:
    return (
        normalize_model_key_value(record.tenant_code),
        normalize_model_key_value(record.system_code),
        normalize_model_key_value(record.connection_code),
        normalize_model_key_value(record.object_schema),
        normalize_model_key_value(record.object_name),
        normalize_model_key_value(record.source_system_code),
        record.modeled_entity_type,
        normalize_model_key_value(record.modeled_entity_name),
    )


def _missing(issues: list[ModelValidationIssue], dataset: str, field: str) -> None:
    issues.append(
        ModelValidationIssue(
            code="reference_not_found",
            dataset=dataset,
            record_number=None,
            fields=(field,),
            message="Referenced record is not present in the future Model graph.",
        )
    )


def _record_is_locked(record: Any) -> bool:
    return any(
        value is True
        for name, value in record.__dict__.items()
        if name.endswith("_is_locked") or name == "is_locked"
    )


def _validate_locked_nested_records(
    *,
    dataset: str,
    existing: ModelingRecord,
    changed: ModelingRecord,
    issues: list[ModelValidationIssue],
) -> None:
    for field in ("supports", "submodels", "sources"):
        existing_items = getattr(existing, field, ())
        changed_items = getattr(changed, field, ())
        changed_by_key = {_nested_record_key(item): item for item in changed_items}
        for existing_item in existing_items:
            changed_item = changed_by_key.get(_nested_record_key(existing_item))
            if (
                changed_item is not None
                and _record_is_locked(existing_item)
                and existing_item != changed_item
            ):
                issues.append(
                    ModelValidationIssue(
                        code="record_locked",
                        dataset=dataset,
                        record_number=None,
                        fields=(field,),
                        message=f"A locked applied nested {field} record cannot be changed.",
                    )
                )


def _nested_record_key(record: Any) -> tuple[object, ...]:
    submodel_name = getattr(record, "submodel_name", None)
    if submodel_name is not None:
        return ("submodel", normalize_model_key_value(submodel_name))

    source_type = record.support_source_type
    if source_type == "assertion":
        return (
            source_type,
            normalize_model_key_value(record.assertion_record.modeling_assertion_record_key),
        )
    physical_key = record.source_attribute if source_type == "attribute" else record.source_object
    return (
        source_type,
        normalize_model_key_value(physical_key.tenant_code),
        normalize_model_key_value(physical_key.system_code),
        normalize_model_key_value(physical_key.connection_code),
        normalize_model_key_value(physical_key.object_schema),
        normalize_model_key_value(physical_key.object_name),
        *(
            (normalize_model_key_value(physical_key.attribute_name),)
            if source_type == "attribute"
            else ()
        ),
    )


def _canonical_key(
    definition: ModelingDatasetDefinition,
    record: ModelingRecord,
) -> tuple[object, ...]:
    return tuple(
        normalize_model_key_value(getattr(record, field)) for field in definition.canonical_key
    )
