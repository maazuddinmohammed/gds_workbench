"""Shared Model Change Set schema, graph, and physical-reference validation."""

from __future__ import annotations

import hashlib
import json
from collections import Counter
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any, cast

from pydantic import ValidationError

from gds_etl_workbench.domain.databricks_sql import validate_databricks_sql
from gds_etl_workbench.domain.errors import InvalidRequestError
from gds_etl_workbench.domain.model_policy import GoldAuditPolicy, GoldTechnicalPolicy
from gds_etl_workbench.domain.modeling_records import (
    AttributeEnrichmentRecord,
    ModelDetailsRecord,
    ModelingRecord,
    ObjectEnrichmentRecord,
    has_mapping_transformation_content,
    normalize_model_key_value,
)
from gds_etl_workbench.domain.snapshots.model import (
    CHANGE_SET_DATASETS_BY_NAME,
    DATASETS,
    ModelChangeSetDataset,
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

type PhysicalObjectNaturalKey = tuple[str, str, str, str, str]
type PhysicalAttributeNaturalKey = tuple[str, str, str, str, str, str]
type ModeledEntityKey = tuple[str, str, str]
type ModeledAttributeKey = tuple[str, str, str, str]


@dataclass(frozen=True, slots=True)
class ModelValidationIssue:
    code: str
    dataset: str
    record_number: int | None
    fields: tuple[str, ...]
    message: str


@dataclass(frozen=True, slots=True)
class CodeGenerationTargetContext:
    """Internal currentness input. These fields are never agent-authored records."""

    modeled_entity_schema_name: str
    modeled_entity_type: str
    modeled_entity_name: str
    source_system_codes: frozenset[str]
    code_input_digest: str


@dataclass(frozen=True, slots=True)
class PhysicalModelCatalog:
    model_tenant_code: str
    active_system_codes: frozenset[str]
    objects: frozenset[PhysicalObjectNaturalKey]
    attributes: frozenset[PhysicalAttributeNaturalKey]
    model_input_objects: frozenset[PhysicalObjectNaturalKey]
    model_input_attributes: frozenset[PhysicalAttributeNaturalKey]
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
    dataset: ModelChangeSetDataset,
    raw_records: list[dict[str, object]],
) -> tuple[tuple[ModelingRecord, ...], tuple[ModelValidationIssue, ...]]:
    definition = CHANGE_SET_DATASETS_BY_NAME[dataset]
    records: list[ModelingRecord] = []
    issues: list[ModelValidationIssue] = []
    seen: set[tuple[object, ...]] = set()
    for record_number, raw in enumerate(raw_records, start=1):
        try:
            encoded = json.dumps(raw, ensure_ascii=False, separators=(",", ":"))
            record = definition.row_model.model_validate_json(encoded, strict=True)
            if isinstance(record, ModelDetailsRecord):
                for template in (
                    record.silver_model_audit_columns_template,
                    record.gold_model_audit_columns_template,
                ):
                    if template is not None:
                        GoldAuditPolicy.model_validate_json(json.dumps(template), strict=True)
                if record.gold_model_technical_columns_template is not None:
                    GoldTechnicalPolicy.model_validate_json(
                        json.dumps(record.gold_model_technical_columns_template), strict=True
                    )
        except ValidationError as error:
            for detail in error.errors(include_url=False, include_input=False)[:20]:
                issues.append(
                    ModelValidationIssue(
                        code="record_schema_invalid",
                        dataset=dataset,
                        record_number=record_number,
                        fields=tuple(str(part) for part in detail["loc"][:20]),
                        message=str(detail["msg"])[:300],
                    )
                )
                if len(issues) >= MAX_VALIDATION_ISSUES:
                    return tuple(records), tuple(issues)
            continue
        except TypeError, ValueError:
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
    staged_documents: dict[ModelChangeSetDataset, list[dict[str, object]]],
    physical_scope: PhysicalModelCatalog,
    code_authoring: bool = True,
) -> ValidatedModelChangeSet:
    # Only the governed, field-only human lifecycle review uses False. It can
    # retain stale Code; Code authoring requires available Mapping and exact System assignments.
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
    retained_keys: dict[str, set[tuple[object, ...]]] = {}
    lock_issues: list[ModelValidationIssue] = []
    mapping_document_issues: list[ModelValidationIssue] = []
    for definition in DATASETS:
        current = effective[definition.name]
        changes = staged.get(definition.name, ())
        by_key = {_canonical_key(definition, record): record for record in current}
        retained_keys[definition.name] = set(by_key)
        for record in changes:
            key = _canonical_key(definition, record)
            existing = by_key.get(key)
            if existing is not None and _record_is_locked(existing) and existing != record:
                _issue(
                    lock_issues,
                    "record_locked",
                    definition.name,
                    definition.canonical_key,
                    "A locked applied record cannot be changed.",
                )
            if isinstance(record, (ObjectEnrichmentRecord, AttributeEnrichmentRecord)):
                if record.expected_revision != getattr(existing, "expected_revision", None):
                    _issue(
                        lock_issues,
                        "enrichment_revision_conflict",
                        definition.name,
                        ("expected_revision",),
                        "Enrichment changed since this draft; refresh and reconcile the findings.",
                    )
                if record.is_locked != (
                    _record_is_locked(existing) if existing is not None else False
                ):
                    _issue(
                        lock_issues,
                        "enrichment_lock_read_only",
                        definition.name,
                        ("is_locked",),
                        "Preserve enrichment locks; Change Sets cannot toggle them.",
                    )
                if definition.name == "attribute_enrichment" and existing != record:
                    parent_key = _physical_object_key(record)
                    if any(
                        _record_is_locked(item) and _physical_object_key(item) == parent_key
                        for item in effective["object_enrichment"]
                    ):
                        _issue(
                            lock_issues,
                            "enrichment_parent_locked",
                            definition.name,
                            definition.canonical_key,
                            "A locked Object enrichment also protects its Attribute findings.",
                        )
            if existing is not None:
                _validate_locked_nested_records(
                    dataset=definition.name,
                    existing=existing,
                    changed=record,
                    issues=lock_issues,
                )
            if existing is None or not _retains_physical_history(existing, record):
                retained_keys[definition.name].discard(key)
            if definition.name in ("mapping_object", "mapping_attribute"):
                object_level = definition.name == "mapping_object"
                field = (
                    "mapping_transformation_document"
                    if object_level
                    else "attribute_mapping_transformation_document"
                )
                status_field = (
                    "object_mapping_status" if object_level else "attribute_mapping_status"
                )
                document = getattr(record, field)
                # Preserve historical documents byte-for-byte; require explicit NULL
                # only when an empty document is newly authored or reactivated.
                if (
                    getattr(record, status_field) == "active"
                    and document is not None
                    and not has_mapping_transformation_content(document)
                    and (
                        existing is None
                        or getattr(existing, field) != document
                        or getattr(existing, status_field) != "active"
                    )
                ):
                    _issue(
                        mapping_document_issues,
                        "mapping_document_empty",
                        definition.name,
                        (field,),
                        "A content-free Mapping document must be explicit null; "
                        "do not invent transformation logic.",
                    )
            by_key[key] = record
        future[definition.name] = tuple(by_key.values())
    if lock_issues:
        return _failed(staged, "locks", candidate_digest, lock_issues)

    scope_issues: list[ModelValidationIssue] = []
    if staged.get("model_details") and effective["model_details"]:
        previous = cast(ModelDetailsRecord, effective["model_details"][0])
        changed = cast(ModelDetailsRecord, staged["model_details"][0])
        if previous.model_name != changed.model_name:
            _issue(
                scope_issues,
                "model_identity_read_only",
                "model_details",
                ("model_name",),
                "Model name is immutable in Change Sets; preserve the Snapshot identity.",
            )
        system_code = changed.default_mapping_source_system_code
        if (
            system_code is not None
            and system_code != previous.default_mapping_source_system_code
            and normalize_model_key_value(system_code) not in physical_scope.active_system_codes
        ):
            _issue(
                scope_issues,
                "default_mapping_source_system_unavailable",
                "model_details",
                ("default_mapping_source_system_code",),
                "Default Mapping source must identify an active registered System code.",
            )
    _validate_model_details(future, physical_scope, scope_issues)
    _validate_physical_scope(
        future,
        physical_scope,
        scope_issues,
        retained_keys=retained_keys,
        applied_input_objects=frozenset(
            _physical_object_key(record)
            for record in effective["model_input_scope"]
            if getattr(record, "is_active", False)
        ),
    )
    if scope_issues:
        return _failed(staged, "model_input_scope", candidate_digest, scope_issues)
    if uniqueness_issues:
        return _failed(staged, "uniqueness", candidate_digest, uniqueness_issues)

    reference_issues = mapping_document_issues
    _validate_references(future, reference_issues)
    _validate_active_dependencies(
        future,
        reference_issues,
        existing_mapping_objects=frozenset(
            _mapping_object_reference(record) for record in effective["mapping_object"]
        ),
        code_authoring_entities=frozenset(
            _entity_key(record)
            for dataset in ("generated_code", "generated_code_source_system")
            for record in staged.get(dataset, ())
            if code_authoring
        ),
    )
    if reference_issues:
        return _failed(staged, "references", candidate_digest, reference_issues)

    return ValidatedModelChangeSet(
        records=staged,
        phase="complete",
        candidate_digest=candidate_digest,
        issues=(),
        action_review=build_model_action_review(effective, staged),
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
    document = {
        dataset: [record.model_dump(mode="json") for record in dataset_records]
        for dataset, dataset_records in sorted(records.items())
    }
    return _sha256(document)


def build_model_action_review(
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
    status = next((value for name, value in values.items() if name.endswith("_status")), None)
    if status == "active":
        return True
    if status in {"inactive", "deprecated"}:
        return False
    return None


def _retains_physical_history(existing: ModelingRecord, changed: ModelingRecord) -> bool:
    """Permit retained evidence and lifecycle review without accepting new authored content."""
    if type(existing) is not type(changed):
        return False
    for field in type(existing).model_fields:
        previous = getattr(existing, field)
        current = getattr(changed, field)
        if previous == current:
            continue
        if (
            (field == "is_locked" or field.endswith("_is_locked"))
            and isinstance(previous, bool)
            and isinstance(current, bool)
        ):
            continue
        if field == "is_active" and previous is True and current is False:
            continue
        if (field == "status" or field.endswith("_status")) and (
            previous == "active" and current == "inactive"
        ):
            continue
        if (
            field in {"supports", "sources", "submodels"}
            and isinstance(previous, tuple)
            and isinstance(current, tuple)
        ):
            previous_items = cast(tuple[object, ...], previous)
            current_items = cast(tuple[object, ...], current)
            if len(previous_items) == len(current_items) and all(
                isinstance(before, ModelingRecord)
                and isinstance(after, ModelingRecord)
                and _retains_physical_history(before, after)
                for before, after in zip(previous_items, current_items, strict=True)
            ):
                continue
        return False
    return True


def _validate_model_details(
    future: Mapping[str, tuple[Any, ...]],
    catalog: PhysicalModelCatalog,
    issues: list[ModelValidationIssue],
) -> None:
    details = future["model_details"]
    if len(details) != 1:
        _issue(
            issues,
            "model_details_invalid",
            "model_details",
            (),
            "The future Model must contain exactly one Model details record.",
        )
    elif normalize_model_key_value(details[0].model_name) in catalog.other_model_names:
        _issue(
            issues,
            "model_name_conflict",
            "model_details",
            ("model_name",),
            "Another active Model in this Tenant already uses this name.",
        )

    if len(details) == 1:
        for layer in ("logical", "dimensional"):
            allowed = {
                normalize_model_key_value(schema.schema_name)
                for schema in getattr(details[0], f"{layer}_schemas")
            }
            for record in future[f"{layer}_entity"]:
                if (
                    normalize_model_key_value(getattr(record, f"{layer}_entity_schema_name"))
                    not in allowed
                ):
                    _issue(
                        issues,
                        "entity_schema_not_configured",
                        f"{layer}_entity",
                        (f"{layer}_entity_schema_name",),
                        "Entity schema must be configured in the Model's layer schema list.",
                    )


def _validate_physical_scope(
    future: Mapping[str, tuple[Any, ...]],
    catalog: PhysicalModelCatalog,
    issues: list[ModelValidationIssue],
    *,
    retained_keys: Mapping[str, set[tuple[object, ...]]],
    applied_input_objects: frozenset[PhysicalObjectNaturalKey],
) -> None:
    def retained(dataset: ModelChangeSetDataset, record: ModelingRecord) -> bool:
        key = _canonical_key(CHANGE_SET_DATASETS_BY_NAME[dataset], record)
        return key in retained_keys[dataset]

    input_objects: set[PhysicalObjectNaturalKey] = set()
    for record in future["model_input_scope"]:
        key = _physical_object_key(record)
        if key not in catalog.objects:
            _scope_missing(
                issues,
                "model_input_scope",
                "object_name",
                "Referenced physical Object is not available to this Model Tenant.",
            )
        elif key not in catalog.model_input_objects and not retained("model_input_scope", record):
            _scope_missing(
                issues,
                "model_input_scope",
                "object_name",
                "Model Input Scope accepts only Source or Bronze Objects.",
            )
        elif record.is_active and key in catalog.model_input_objects:
            input_objects.add(key)
    input_attributes = {key for key in catalog.model_input_attributes if key[:5] in input_objects}

    enrichment_objects = input_objects & applied_input_objects
    enrichment_attributes = {key for key in input_attributes if key[:5] in enrichment_objects}
    for record in future["object_enrichment"]:
        _require_object(
            record,
            "object_enrichment",
            "object_name",
            catalog.objects if retained("object_enrichment", record) else enrichment_objects,
            "Enrichment Object is not in active Model Input Scope.",
            issues,
        )
    for record in future["attribute_enrichment"]:
        _require_attribute(
            record,
            "attribute_enrichment",
            "attribute_name",
            catalog.attributes
            if retained("attribute_enrichment", record)
            else enrichment_attributes,
            "Enrichment Attribute is not in active Model Input Scope.",
            issues,
        )
    for record in future["profiling_profile"]:
        _require_attribute(
            record,
            "profiling_profile",
            "attribute_name",
            catalog.attributes if retained("profiling_profile", record) else input_attributes,
            "Profile Attribute is not in active Model Input Scope.",
            issues,
        )
    for record in future["analysis_result"]:
        eligible_attributes = (
            catalog.attributes if retained("analysis_result", record) else input_attributes
        )
        for endpoint in ("from", "to"):
            key = cast(
                PhysicalAttributeNaturalKey,
                tuple(
                    normalize_model_key_value(getattr(record, f"{endpoint}_{field}"))
                    for field in (
                        "tenant_code",
                        "system_code",
                        "connection_code",
                        "object_schema",
                        "object_name",
                        "attribute_name",
                    )
                ),
            )
            if key not in eligible_attributes:
                _scope_missing(
                    issues,
                    "analysis_result",
                    f"{endpoint}_attribute_name",
                    "Analysis Attribute is not in active Model Input Scope.",
                )

    for record in future["modeling_assertion_document"]:
        if record.tenant_code is not None and normalize_model_key_value(
            record.tenant_code
        ) != normalize_model_key_value(catalog.model_tenant_code):
            _scope_missing(
                issues,
                "modeling_assertion_document",
                "tenant_code",
                "Assertion document Tenant does not own this Model.",
            )
        if record.system_code is not None:
            _require_active_system(
                record.system_code,
                "modeling_assertion_document",
                catalog,
                issues,
                field="system_code",
            )

    for dataset in ("conceptual_object", "conceptual_relationship"):
        for record in future[dataset]:
            for support in record.supports:
                if support.support_source_type == "object":
                    _require_object(
                        support.source_object,
                        dataset,
                        "source_object",
                        catalog.objects if retained(dataset, record) else input_objects,
                        "Physical support is not in active Model Input Scope.",
                        issues,
                    )
    for dataset in ("logical_entity", "logical_attribute"):
        for record in future[dataset]:
            for source in record.sources:
                if source.support_source_type == "object":
                    _require_object(
                        source.source_object,
                        dataset,
                        "source_object",
                        catalog.objects if retained(dataset, record) else input_objects,
                        "Logical source Object is not in active Model Input Scope.",
                        issues,
                    )
                elif source.support_source_type == "attribute":
                    _require_attribute(
                        source.source_attribute,
                        dataset,
                        "source_attribute",
                        catalog.attributes if retained(dataset, record) else input_attributes,
                        "Logical source Attribute is not in active Model Input Scope.",
                        issues,
                    )

    for record in future["mapping_object"]:
        _require_active_system(record.source_system_code, "mapping_object", catalog, issues)
    for record in future["mapping_attribute"]:
        _require_active_system(record.source_system_code, "mapping_attribute", catalog, issues)
    for record in future["generated_code_source_system"]:
        _require_active_system(
            record.source_system_code,
            "generated_code_source_system",
            catalog,
            issues,
        )
    for dataset in ("validation_group", "validation_check"):
        for record in future[dataset]:
            if normalize_model_key_value(record.tenant_code) != normalize_model_key_value(
                catalog.model_tenant_code
            ):
                _scope_missing(
                    issues,
                    dataset,
                    "tenant_code",
                    "Validation record Tenant does not own this Model.",
                )
            _require_active_system(
                record.system_code,
                dataset,
                catalog,
                issues,
                field="system_code",
            )
            if dataset == "validation_check" and record.is_active:
                _validate_validation_query(
                    record.validation_query_sql,
                    dataset=dataset,
                    field="validation_query_sql",
                    must_return_rows=(
                        record.validation_comparison_operator != "executes_successfully"
                    ),
                    issues=issues,
                )
                if record.validation_comparison_query_sql is not None:
                    _validate_validation_query(
                        record.validation_comparison_query_sql,
                        dataset=dataset,
                        field="validation_comparison_query_sql",
                        must_return_rows=True,
                        issues=issues,
                    )


def _validate_references(
    future: Mapping[str, tuple[Any, ...]],
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
            dataset="conceptual_relationship",
            assertion_records=assertion_records,
            issues=issues,
        )

    _validate_modeled_layer(future, "logical", assertion_records, issues)
    _validate_modeled_layer(future, "dimensional", assertion_records, issues)

    logical_entities = {_entity_key(row): row for row in future["logical_entity"]}
    logical_attributes = {_attribute_key(row): row for row in future["logical_attribute"]}
    for dataset in ("dimensional_entity", "dimensional_attribute"):
        for record in future[dataset]:
            active = getattr(record, f"{dataset}_status") == "active"
            for source in record.sources:
                if source.support_source_type == "logical_entity":
                    target = logical_entities.get(_entity_key(source.source_logical_entity))
                    parent = target
                    is_active = target is not None and target.logical_entity_status == "active"
                elif source.support_source_type == "logical_attribute":
                    key = source.source_logical_attribute
                    target = logical_attributes.get(_attribute_key(key))
                    parent = logical_entities.get(_entity_key(key))
                    is_active = (
                        target is not None
                        and target.logical_attribute_status == "active"
                        and parent is not None
                        and parent.logical_entity_status == "active"
                    )
                else:
                    continue
                if target is None or parent is None:
                    _missing(issues, dataset, "sources")
                elif active and source.status == "active" and not is_active:
                    _active_invalid(
                        issues,
                        dataset,
                        "sources",
                        "Active Dimensional support requires an active Logical source.",
                    )

    entities = _modeled_entities(future)
    attributes = _modeled_attributes(future)
    mapping_objects = {_mapping_object_reference(record) for record in future["mapping_object"]}
    for record in future["mapping_object"]:
        if _entity_key(record) not in entities:
            _missing(issues, "mapping_object", "modeled_entity_name")
    for record in future["mapping_attribute"]:
        if _mapping_object_reference(record) not in mapping_objects:
            _missing(issues, "mapping_attribute", "mapping_object")
        if _attribute_key(record) not in attributes:
            _missing(issues, "mapping_attribute", "modeled_attribute_name")

    artifacts = {_artifact_reference(record) for record in future["generated_code"]}
    for record in future["generated_code"]:
        if _entity_key(record) not in entities:
            _missing(issues, "generated_code", "modeled_entity_name")
    for record in future["generated_code_source_system"]:
        if _artifact_reference(record) not in artifacts:
            _missing(issues, "generated_code_source_system", "generated_code")

    validation_groups = {
        _validation_group_reference(record) for record in future["validation_group"]
    }
    for record in future["validation_check"]:
        if _validation_group_reference(record) not in validation_groups:
            _missing(issues, "validation_check", "validation_group_name")


def _validate_active_dependencies(
    future: Mapping[str, tuple[Any, ...]],
    issues: list[ModelValidationIssue],
    *,
    existing_mapping_objects: frozenset[tuple[str, str, str, str]],
    code_authoring_entities: frozenset[ModeledEntityKey],
) -> None:
    active_conceptual_objects = {
        normalize_model_key_value(record.conceptual_object_name)
        for record in future["conceptual_object"]
        if record.conceptual_object_status == "active"
    }
    for record in future["conceptual_relationship"]:
        if record.conceptual_relationship_status == "active" and (
            normalize_model_key_value(record.from_conceptual_object_name)
            not in active_conceptual_objects
            or normalize_model_key_value(record.to_conceptual_object_name)
            not in active_conceptual_objects
        ):
            _active_invalid(
                issues,
                "conceptual_relationship",
                "conceptual_object_name",
                "Active Conceptual Relationship requires active endpoint Objects.",
            )
    active_entities = {
        _entity_key(record)
        for layer in ("logical", "dimensional")
        for record in future[f"{layer}_entity"]
        if getattr(record, f"{layer}_entity_status") == "active"
    }
    active_attributes = {
        _attribute_key(record)
        for layer in ("logical", "dimensional")
        for record in future[f"{layer}_attribute"]
        if getattr(record, f"{layer}_attribute_status") == "active"
    }
    for layer in ("logical", "dimensional"):
        for record in future[f"{layer}_attribute"]:
            if (
                getattr(record, f"{layer}_attribute_status") == "active"
                and _entity_key(record) not in active_entities
            ):
                _active_invalid(
                    issues,
                    f"{layer}_attribute",
                    f"{layer}_entity_name",
                    f"Active {layer.title()} Attribute requires an active parent Entity.",
                )
        for record in future[f"{layer}_relationship"]:
            if getattr(record, f"{layer}_relationship_status") != "active":
                continue
            endpoints = (
                (
                    f"{layer}_entity",
                    normalize_model_key_value(
                        getattr(record, f"{side}_{layer}_entity_schema_name")
                    ),
                    normalize_model_key_value(getattr(record, f"{side}_{layer}_entity_name")),
                    normalize_model_key_value(getattr(record, f"{side}_{layer}_attribute_name")),
                )
                for side in ("from", "to")
            )
            if any(
                endpoint not in active_attributes or endpoint[:3] not in active_entities
                for endpoint in endpoints
            ):
                _active_invalid(
                    issues,
                    f"{layer}_relationship",
                    f"{layer}_attribute_name",
                    f"Active {layer.title()} Relationship requires active endpoint "
                    "Attributes and Entities.",
                )
    active_mapping_objects: set[tuple[str, str, str, str]] = set()
    mapping_object_transformations: set[tuple[str, str, str, str]] = set()
    active_mapping_attributes: set[tuple[str, str, str, str, str]] = set()
    mapping_systems_by_entity: dict[ModeledEntityKey, set[str]] = {}
    for record in future["mapping_object"]:
        if record.object_mapping_status != "active":
            continue
        entity = _entity_key(record)
        system = normalize_model_key_value(record.source_system_code)
        if entity not in active_entities:
            _active_invalid(
                issues,
                "mapping_object",
                "modeled_entity_name",
                "Active Mapping Object requires an active Entity.",
            )
            continue
        reference = _mapping_object_reference(record)
        active_mapping_objects.add(reference)
        if record.mapping_transformation_document is not None:
            mapping_object_transformations.add(reference)
        mapping_systems_by_entity.setdefault(entity, set()).add(system)

    for record in future["mapping_attribute"]:
        if record.attribute_mapping_status != "active":
            continue
        if (
            _mapping_object_reference(record) not in active_mapping_objects
            or _attribute_key(record) not in active_attributes
        ):
            _active_invalid(
                issues,
                "mapping_attribute",
                "modeled_attribute_name",
                "Active Mapping Attribute requires active Mapping and modeled Attribute.",
            )
            continue
        if record.attribute_mapping_transformation_document is None:
            continue  # An explicit blank is retained without inventing transformation logic.
        entity_type, entity_schema, entity_name, attribute_name = _attribute_key(record)
        active_mapping_attributes.add(
            (
                entity_type,
                entity_schema,
                entity_name,
                normalize_model_key_value(record.source_system_code),
                attribute_name,
            )
        )

    code_mapping_systems_by_entity: dict[ModeledEntityKey, set[str]] = {}
    for entity, systems in mapping_systems_by_entity.items():
        entity_attributes = {
            attribute[3] for attribute in active_attributes if attribute[:3] == entity
        }
        for system in systems:
            has_object_transformation = (*entity, system) in mapping_object_transformations
            if (
                (*entity, system) not in existing_mapping_objects
                and not has_object_transformation
                and not any(
                    (*entity, system, attribute_name) in active_mapping_attributes
                    for attribute_name in entity_attributes
                )
            ):
                _active_invalid(
                    issues,
                    "mapping_object",
                    "mapping_transformation_document",
                    "New active Mapping requires an Object or Attribute transformation.",
                )
            # Code can be authored from partial Mapping. Keep every System with
            # evidence; cleared saved pairs remain stored but do not require SQL.
            if has_object_transformation or any(
                (*entity, system, attribute_name) in active_mapping_attributes
                for attribute_name in entity_attributes
            ):
                code_mapping_systems_by_entity.setdefault(entity, set()).add(system)

    active_artifacts = {
        _artifact_reference(record): record
        for record in future["generated_code"]
        if record.generated_code_status == "active"
    }
    system_assignments: Counter[tuple[ModeledEntityKey, str]] = Counter()
    for record in active_artifacts.values():
        if _entity_key(record) not in active_entities:
            _active_invalid(
                issues,
                "generated_code",
                "modeled_entity_name",
                "Active Code artifact requires an active modeled Entity.",
            )
        elif _entity_key(
            record
        ) in code_authoring_entities and not code_mapping_systems_by_entity.get(
            _entity_key(record)
        ):
            _active_invalid(
                issues,
                "generated_code",
                "modeled_entity_name",
                "Code authoring requires an active Object or Attribute transformation.",
            )
    for record in future["generated_code_source_system"]:
        if record.generated_code_source_system_status != "active":
            continue
        reference = _artifact_reference(record)
        system = normalize_model_key_value(record.source_system_code)
        entity = _entity_key(record)
        if reference not in active_artifacts or system not in mapping_systems_by_entity.get(
            entity, set()
        ):
            _active_invalid(
                issues,
                "generated_code_source_system",
                "source_system_code",
                "Active Code source assignment requires active Code and Mapping.",
            )
            continue
        system_assignments[(entity, system)] += 1
    for entity, systems in mapping_systems_by_entity.items():
        if not any(_entity_key(record) == entity for record in active_artifacts.values()):
            continue
        for system in systems:
            # Upstream Mapping may outgrow unchanged Code. Input digests mark that Code
            # stale; only Code authoring can supply its missing System assignments.
            count = system_assignments[(entity, system)]
            if count > 1 or (
                count == 0
                and entity in code_authoring_entities
                and system in code_mapping_systems_by_entity.get(entity, set())
            ):
                _active_invalid(
                    issues,
                    "generated_code_source_system",
                    "source_system_code",
                    "Each mapped source System must be assigned to exactly one active artifact.",
                )

    active_groups = {
        _validation_group_reference(record)
        for record in future["validation_group"]
        if record.is_active
    }
    active_mapping_systems = {
        system for systems in mapping_systems_by_entity.values() for system in systems
    }
    for record in future["validation_group"]:
        if (
            record.is_active
            and normalize_model_key_value(record.system_code) not in active_mapping_systems
        ):
            _active_invalid(
                issues,
                "validation_group",
                "system_code",
                "Active Validation Group requires active Mapping for its source System.",
            )
    for record in future["validation_check"]:
        if record.is_active and _validation_group_reference(record) not in active_groups:
            _active_invalid(
                issues,
                "validation_check",
                "validation_group_name",
                "Active Validation Check requires an active Validation Group.",
            )


def validation_mapping_context_digest(
    contexts: tuple[CodeGenerationTargetContext, ...],
    source_system_code: str,
) -> str | None:
    """Hash server-derived Code inputs relevant to one source System."""
    normalized_system = normalize_model_key_value(source_system_code)
    entries: list[dict[str, object]] = [
        {
            "modeled_entity_type": context.modeled_entity_type,
            "modeled_entity_name": normalize_model_key_value(context.modeled_entity_name),
            "modeled_entity_schema_name": normalize_model_key_value(
                context.modeled_entity_schema_name
            ),
            "code_input_digest": context.code_input_digest,
        }
        for context in contexts
        if normalized_system
        in {normalize_model_key_value(code) for code in context.source_system_codes}
    ]
    return _context_entries_digest(entries)


def validation_code_context_digest(
    contexts: tuple[CodeGenerationTargetContext, ...],
    generated_code_records: tuple[Any, ...],
    source_system_code: str,
) -> str | None:
    """Hash current active Code artifacts relevant to one source System."""
    normalized_system = normalize_model_key_value(source_system_code)
    relevant = {
        (
            context.modeled_entity_type,
            normalize_model_key_value(context.modeled_entity_schema_name),
            normalize_model_key_value(context.modeled_entity_name),
        ): context
        for context in contexts
        if normalized_system
        in {normalize_model_key_value(code) for code in context.source_system_codes}
    }
    entries: list[dict[str, object]] = []
    for record in generated_code_records:
        if getattr(record, "generated_code_status", None) != "active":
            continue
        entity_type = getattr(record, "modeled_entity_type", None)
        entity_name = getattr(record, "modeled_entity_name", None)
        entity_schema = getattr(record, "modeled_entity_schema_name", None)
        if not all(isinstance(value, str) for value in (entity_type, entity_schema, entity_name)):
            continue
        key = _entity_key(record)
        context = relevant.get(key)
        if context is None:
            continue
        raw_sources = getattr(record, "source_system_codes", None)
        if raw_sources is not None and normalized_system not in {
            normalize_model_key_value(code) for code in raw_sources
        }:
            continue
        content = getattr(record, "generated_code_content", None)
        digest = getattr(record, "generated_code_digest", None)
        if not isinstance(digest, str) and isinstance(content, str):
            digest = hashlib.sha256(content.encode("utf-8")).hexdigest()
        if not isinstance(digest, str):
            continue
        entries.append(
            {
                "modeled_entity_type": key[0],
                "modeled_entity_name": key[2],
                "modeled_entity_schema_name": normalize_model_key_value(
                    context.modeled_entity_schema_name
                ),
                "artifact_name": getattr(record, "artifact_name", ""),
                "artifact_type": getattr(record, "artifact_type", ""),
                "code_input_digest": context.code_input_digest,
                "generated_code_digest": digest,
            }
        )
    return _context_entries_digest(entries)


def _context_entries_digest(entries: list[dict[str, object]]) -> str | None:
    if not entries:
        return None
    entries.sort(key=lambda value: json.dumps(value, sort_keys=True, separators=(",", ":")))
    return _sha256(entries)


def _validate_validation_query(
    query: str,
    *,
    dataset: str,
    field: str,
    must_return_rows: bool,
    issues: list[ModelValidationIssue],
) -> None:
    try:
        validated = validate_databricks_sql(query)
    except InvalidRequestError:
        _issue(
            issues,
            "validation_query_invalid",
            dataset,
            (field,),
            "Validation query is not governed read-only Databricks SQL.",
        )
        return
    if must_return_rows and not validated.final_returns_rows:
        _issue(
            issues,
            "validation_query_result_invalid",
            dataset,
            (field,),
            "Validation query must end with a row-returning statement.",
        )


def _validate_modeled_layer(
    future: Mapping[str, tuple[Any, ...]],
    layer: str,
    assertion_records: dict[object, Any],
    issues: list[ModelValidationIssue],
) -> None:
    submodels = {
        normalize_model_key_value(getattr(record, f"{layer}_submodel_name"))
        for record in future[f"{layer}_submodel"]
    }
    entities = {_entity_key(record): record for record in future[f"{layer}_entity"]}
    attributes = {_attribute_key(record) for record in future[f"{layer}_attribute"]}
    for record in future[f"{layer}_entity"]:
        if any(
            normalize_model_key_value(membership.submodel_name) not in submodels
            for membership in record.submodels
        ):
            _missing(issues, f"{layer}_entity", "submodel_name")
        _validate_supports(
            record.sources,
            dataset=f"{layer}_entity",
            assertion_records=assertion_records,
            issues=issues,
        )
    for record in future[f"{layer}_attribute"]:
        if _entity_key(record) not in entities:
            _missing(issues, f"{layer}_attribute", f"{layer}_entity_name")
        if layer == "dimensional" and (owner := entities.get(_entity_key(record))) is not None:
            for source in record.sources:
                if source.support_source_type != "logical_attribute":
                    continue
                source_entity = _entity_key(source.source_logical_attribute)
                parents = [
                    support
                    for support in owner.sources
                    if support.support_source_type == "logical_entity"
                    and _entity_key(support.source_logical_entity) == source_entity
                ]
                if not parents:
                    _missing(issues, "dimensional_attribute", "sources")
                elif (
                    record.dimensional_attribute_status == "active"
                    and source.status == "active"
                    and not any(parent.status == "active" for parent in parents)
                ):
                    _active_invalid(
                        issues,
                        "dimensional_attribute",
                        "sources",
                        "Active Attribute support requires active support on its parent Entity.",
                    )
        _validate_supports(
            record.sources,
            dataset=f"{layer}_attribute",
            assertion_records=assertion_records,
            issues=issues,
        )
    for record in future[f"{layer}_relationship"]:
        endpoints = (
            (
                f"{layer}_entity",
                normalize_model_key_value(getattr(record, f"{side}_{layer}_entity_schema_name")),
                normalize_model_key_value(getattr(record, f"{side}_{layer}_entity_name")),
                normalize_model_key_value(getattr(record, f"{side}_{layer}_attribute_name")),
            )
            for side in ("from", "to")
        )
        if any(endpoint not in attributes for endpoint in endpoints):
            _missing(issues, f"{layer}_relationship", f"{layer}_attribute_name")


def _validate_supports(
    supports: tuple[Any, ...],
    *,
    dataset: str,
    assertion_records: dict[object, Any],
    issues: list[ModelValidationIssue],
) -> None:
    for support in supports:
        if (
            support.support_source_type == "assertion"
            and normalize_model_key_value(support.assertion_record.modeling_assertion_record_key)
            not in assertion_records
        ):
            _missing(issues, dataset, "modeling_assertion_record_key")


def _modeled_entities(future: Mapping[str, tuple[Any, ...]]) -> set[ModeledEntityKey]:
    return {
        _entity_key(record)
        for layer in ("logical", "dimensional")
        for record in future[f"{layer}_entity"]
    }


def _modeled_attributes(future: Mapping[str, tuple[Any, ...]]) -> set[ModeledAttributeKey]:
    return {
        _attribute_key(record)
        for layer in ("logical", "dimensional")
        for record in future[f"{layer}_attribute"]
    }


def _entity_key(record: Any) -> ModeledEntityKey:
    entity_type = getattr(record, "modeled_entity_type", None)
    if entity_type is None:
        entity_type = (
            "logical_entity" if hasattr(record, "logical_entity_name") else "dimensional_entity"
        )
    name = getattr(record, "modeled_entity_name", None)
    schema = getattr(record, "modeled_entity_schema_name", None)
    if name is None:
        name = getattr(record, f"{entity_type}_name")
        schema = getattr(record, f"{entity_type}_schema_name")
    assert isinstance(schema, str) and isinstance(name, str)
    return entity_type, normalize_model_key_value(schema), normalize_model_key_value(name)


def _attribute_key(record: Any) -> ModeledAttributeKey:
    entity = _entity_key(record)
    name = getattr(record, "modeled_attribute_name", None)
    if name is None:
        name = getattr(record, f"{entity[0].removesuffix('_entity')}_attribute_name")
    return *entity, normalize_model_key_value(name)


def _mapping_object_reference(record: Any) -> tuple[str, str, str, str]:
    return *_entity_key(record), normalize_model_key_value(record.source_system_code)


def _artifact_reference(record: Any) -> tuple[str, str, str, str]:
    return *_entity_key(record), normalize_model_key_value(record.artifact_name)


def _validation_group_reference(record: Any) -> tuple[str, str, str]:
    return (
        normalize_model_key_value(record.tenant_code),
        normalize_model_key_value(record.system_code),
        normalize_model_key_value(record.validation_group_name),
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


def _physical_attribute_key(key: Any) -> PhysicalAttributeNaturalKey:
    return cast(
        PhysicalAttributeNaturalKey,
        tuple(
            normalize_model_key_value(getattr(key, name))
            for name in (
                "tenant_code",
                "system_code",
                "connection_code",
                "object_schema",
                "object_name",
                "attribute_name",
            )
        ),
    )


def _require_object(
    key: Any,
    dataset: str,
    field: str,
    eligible: set[PhysicalObjectNaturalKey] | frozenset[PhysicalObjectNaturalKey],
    message: str,
    issues: list[ModelValidationIssue],
) -> None:
    if _physical_object_key(key) not in eligible:
        _scope_missing(issues, dataset, field, message)


def _require_attribute(
    key: Any,
    dataset: str,
    field: str,
    eligible: set[PhysicalAttributeNaturalKey] | frozenset[PhysicalAttributeNaturalKey],
    message: str,
    issues: list[ModelValidationIssue],
) -> None:
    if _physical_attribute_key(key) not in eligible:
        _scope_missing(issues, dataset, field, message)


def _require_active_system(
    system_code: str,
    dataset: str,
    scope: PhysicalModelCatalog,
    issues: list[ModelValidationIssue],
    *,
    field: str = "source_system_code",
) -> None:
    if normalize_model_key_value(system_code) not in scope.active_system_codes:
        _scope_missing(issues, dataset, field, "Referenced System is not active.")


def _scope_missing(
    issues: list[ModelValidationIssue],
    dataset: str,
    field: str,
    message: str,
) -> None:
    _issue(issues, "model_input_reference_invalid", dataset, (field,), message)


def _active_invalid(
    issues: list[ModelValidationIssue],
    dataset: str,
    field: str,
    message: str,
) -> None:
    _issue(issues, "active_dependency_invalid", dataset, (field,), message)


def _missing(issues: list[ModelValidationIssue], dataset: str, field: str) -> None:
    _issue(
        issues,
        "reference_not_found",
        dataset,
        (field,),
        "Referenced record is not present in the future Model graph.",
    )


def _issue(
    issues: list[ModelValidationIssue],
    code: str,
    dataset: str,
    fields: tuple[str, ...],
    message: str,
) -> None:
    if len(issues) < MAX_VALIDATION_ISSUES:
        issues.append(
            ModelValidationIssue(
                code=code,
                dataset=dataset,
                record_number=None,
                fields=fields,
                message=message,
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
        changed_by_key = {_nested_record_key(item): item for item in getattr(changed, field, ())}
        for existing_item in getattr(existing, field, ()):
            changed_item = changed_by_key.get(_nested_record_key(existing_item))
            if (
                changed_item is not None
                and _record_is_locked(existing_item)
                and existing_item != changed_item
            ):
                _issue(
                    issues,
                    "record_locked",
                    dataset,
                    (field,),
                    f"A locked applied nested {field} record cannot be changed.",
                )


def _nested_record_key(record: Any) -> tuple[object, ...]:
    submodel_name = getattr(record, "submodel_name", None)
    if submodel_name is not None:
        return "submodel", normalize_model_key_value(submodel_name)
    source_type = record.support_source_type
    if source_type == "assertion":
        return (
            source_type,
            normalize_model_key_value(record.assertion_record.modeling_assertion_record_key),
        )
    if source_type == "logical_entity":
        return source_type, *_entity_key(record.source_logical_entity)
    if source_type == "logical_attribute":
        return source_type, *_attribute_key(record.source_logical_attribute)
    physical = record.source_attribute if source_type == "attribute" else record.source_object
    return (
        source_type,
        *_physical_object_key(physical),
        *(
            (normalize_model_key_value(physical.attribute_name),)
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


def _sha256(value: object) -> str:
    return hashlib.sha256(
        json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
