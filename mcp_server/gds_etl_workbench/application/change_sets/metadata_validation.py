"""Metadata Change Set validation using the shared Snapshot contract registry."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import cast

from pydantic import ValidationError

from gds_etl_workbench.domain.snapshots.metadata import (
    DATASETS,
    OBJECT_KEY,
    DatasetDefinition,
    EncodedDataset,
    ReferenceDefinition,
    normalize_natural_key_value,
)

from .action_review import (
    ActionReviewKey,
    DatasetActionReview,
    classify_record_action,
)

MAX_VALIDATION_ISSUES = 100
MAX_REVIEW_KEYS = 100


@dataclass(frozen=True, slots=True)
class ValidationIssue:
    code: str
    dataset: str
    record_number: int | None
    fields: tuple[str, ...]
    message: str

    def as_document(self) -> dict[str, object]:
        return {
            "code": self.code,
            "dataset": self.dataset,
            "record_number": self.record_number,
            "fields": list(self.fields),
            "message": self.message,
        }


@dataclass(frozen=True, slots=True)
class MetadataChangeSetValidation:
    valid: bool
    phase: str
    candidate_digest: str | None
    staged_record_count: int
    issues: tuple[ValidationIssue, ...]
    action_review: tuple[DatasetActionReview, ...]

    def outcome_document(self) -> dict[str, object]:
        return {
            "schema_version": "1.0",
            "valid": self.valid,
            "phase": self.phase,
            "staged_record_count": self.staged_record_count,
            "error_count": len(self.issues),
            "errors": [issue.as_document() for issue in self.issues],
            "action_review": [summary.as_document() for summary in self.action_review],
        }


@dataclass(frozen=True, slots=True)
class _Row:
    dataset: str
    record_number: int
    values: dict[str, object]
    staged: bool


def rows_from_snapshot(
    encoded_datasets: Sequence[EncodedDataset],
) -> dict[str, list[dict[str, object]]]:
    """Decode already-validated Snapshot JSONL without exposing it through MCP."""
    return {
        encoded.definition.name: [
            cast(dict[str, object], json.loads(line))
            for line in encoded.rows_jsonl.decode("utf-8").splitlines()
        ]
        for encoded in encoded_datasets
    }


def validate_metadata_documents(
    *,
    tenant_code: str,
    current_rows_by_dataset: Mapping[str, Sequence[Mapping[str, object]]],
    staged_rows_by_dataset: Mapping[str, Sequence[Mapping[str, object]]],
) -> MetadataChangeSetValidation:
    """Validate one full pending document set, stopping after the first failed phase."""
    staged_count = sum(len(rows) for rows in staged_rows_by_dataset.values())
    current, staged, issues = _validate_schemas(
        current_rows_by_dataset,
        staged_rows_by_dataset,
    )
    if issues:
        return _failed("schema", staged_count, issues)

    digest = _candidate_digest(staged)
    issues = _validate_object_locks(current, staged)
    if issues:
        return _failed("locks", staged_count, issues, digest)

    issues = _validate_tenant_scope(tenant_code, current, staged)
    if issues:
        return _failed("tenant_scope", staged_count, issues, digest)

    issues = _validate_staged_uniqueness(staged)
    if issues:
        return _failed("uniqueness", staged_count, issues, digest)

    effective = _overlay_rows(current, staged)
    issues = _validate_effective_uniqueness(effective)
    if issues:
        return _failed("uniqueness", staged_count, issues, digest)

    issues = _validate_references(effective)
    if issues:
        return _failed("references", staged_count, issues, digest)

    return MetadataChangeSetValidation(
        valid=True,
        phase="complete",
        candidate_digest=digest,
        staged_record_count=staged_count,
        issues=(),
        action_review=_build_action_review(current, staged),
    )


def _build_action_review(
    current: Sequence[_Row],
    staged: Sequence[_Row],
) -> tuple[DatasetActionReview, ...]:
    current_by_key: dict[tuple[str, tuple[object, ...]], _Row] = {}
    for row in current:
        definition = _definition(row.dataset)
        current_by_key[
            (definition.record_type, _normalized_key(definition.canonical_key, row.values))
        ] = row

    remaining_keys = MAX_REVIEW_KEYS
    summaries: list[DatasetActionReview] = []
    for definition in DATASETS:
        dataset_rows = [row for row in staged if row.dataset == definition.name]
        if not dataset_rows:
            continue
        counts = {name: 0 for name in ("insert", "update", "deactivate", "reactivate", "no_change")}
        keys: list[ActionReviewKey] = []
        for row in dataset_rows:
            key = _normalized_key(definition.canonical_key, row.values)
            existing = current_by_key.get((definition.record_type, key))
            action = classify_record_action(
                existing.values if existing is not None else None,
                row.values,
                active_state=_metadata_active_state,
            )
            counts[action] += 1
            if remaining_keys > 0:
                keys.append(
                    ActionReviewKey(
                        action=action,
                        natural_key={
                            column: row.values[column] for column in definition.canonical_key
                        },
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
                keys_truncated=len(keys) < len(dataset_rows),
            )
        )
    return tuple(summaries)


def _metadata_active_state(values: Mapping[str, object]) -> bool | None:
    active = values.get("is_active")
    return active if isinstance(active, bool) else None


def _validate_schemas(
    current_rows_by_dataset: Mapping[str, Sequence[Mapping[str, object]]],
    staged_rows_by_dataset: Mapping[str, Sequence[Mapping[str, object]]],
) -> tuple[list[_Row], list[_Row], list[ValidationIssue]]:
    current: list[_Row] = []
    staged: list[_Row] = []
    issues: list[ValidationIssue] = []
    for definition in DATASETS:
        for is_staged, source, target in (
            (False, current_rows_by_dataset.get(definition.name, ()), current),
            (True, staged_rows_by_dataset.get(definition.name, ()), staged),
        ):
            if is_staged and not definition.change_set_eligible and source:
                issues.append(
                    ValidationIssue(
                        "dataset_not_changeable",
                        definition.name,
                        None,
                        (),
                        "Dataset cannot be changed through a Metadata Change Set.",
                    )
                )
                continue
            for record_number, raw in enumerate(source, start=1):
                try:
                    values = definition.row_model.model_validate(raw).model_dump(mode="json")
                except ValidationError as error:
                    first = error.errors(include_url=False, include_input=False)[0]
                    fields = tuple(str(part) for part in first["loc"])
                    issues.append(
                        ValidationIssue(
                            "schema_invalid",
                            definition.name,
                            record_number,
                            fields,
                            str(first["msg"]),
                        )
                    )
                    if len(issues) >= MAX_VALIDATION_ISSUES:
                        return current, staged, issues
                    continue
                invalid_fixed = tuple(
                    field
                    for field, expected in definition.fixed_values
                    if values[field] != expected
                )
                if invalid_fixed:
                    issues.append(
                        ValidationIssue(
                            "fixed_value_invalid",
                            definition.name,
                            record_number,
                            invalid_fixed,
                            "Record does not match the selected dataset.",
                        )
                    )
                target.append(_Row(definition.name, record_number, values, is_staged))
                if len(issues) >= MAX_VALIDATION_ISSUES:
                    return current, staged, issues
    return current, staged, issues


def _validate_object_locks(
    current: Sequence[_Row],
    staged: Sequence[_Row],
) -> list[ValidationIssue]:
    locked_object_keys = {
        _normalized_key(OBJECT_KEY, row.values)
        for row in current
        if _definition(row.dataset).record_type == "object" and row.values["is_locked"] is True
    }
    issues: list[ValidationIssue] = []
    for row in staged:
        record_type = _definition(row.dataset).record_type
        if record_type not in {"object", "attribute"}:
            continue
        if _normalized_key(OBJECT_KEY, row.values) not in locked_object_keys:
            continue
        issues.append(
            ValidationIssue(
                "object_locked",
                row.dataset,
                row.record_number,
                OBJECT_KEY,
                "Object is locked; neither it nor its Attributes can be changed.",
            )
        )
        if len(issues) >= MAX_VALIDATION_ISSUES:
            break
    return issues


def _validate_tenant_scope(
    tenant_code: str,
    current: Sequence[_Row],
    staged: Sequence[_Row],
) -> list[ValidationIssue]:
    normalized_tenant = normalize_natural_key_value("tenant_code", tenant_code)
    owned_connections = {
        _normalized_key(
            ("tenant_code", "system_code", "connection_code"),
            row.values,
        )
        for row in current
        if row.dataset == "connection"
        and normalize_natural_key_value("tenant_code", row.values["tenant_code"])
        == normalized_tenant
    }
    configured_gds_connections = {
        (
            _normalize_key_value("tenant_code", row.values["gds_connection_tenant_code"]),
            _normalize_key_value("system_code", row.values["gds_connection_system_code"]),
            _normalize_key_value("connection_code", row.values["gds_connection_code"]),
        )
        for row in current
        if row.dataset == "tenant"
        and normalize_natural_key_value("tenant_code", row.values["tenant_code"])
        == normalized_tenant
        and row.values["gds_connection_tenant_code"] is not None
        and row.values["gds_connection_system_code"] is not None
        and row.values["gds_connection_code"] is not None
    }
    effective_objects: dict[tuple[object, ...], Mapping[str, object]] = {}
    for row in (*current, *staged):
        if _definition(row.dataset).record_type == "object":
            effective_objects[
                _normalized_key(_definition(row.dataset).canonical_key, row.values)
            ] = row.values

    issues: list[ValidationIssue] = []
    for row in staged:
        owner_fields = _tenant_owner_fields(row.dataset)
        mismatched_owner = tuple(
            field
            for field in owner_fields
            if normalize_natural_key_value(field, row.values[field]) != normalized_tenant
        )
        if mismatched_owner:
            issues.append(
                ValidationIssue(
                    "tenant_scope_mismatch",
                    row.dataset,
                    row.record_number,
                    mismatched_owner,
                    "Record is not owned by the locked Tenant.",
                )
            )
            continue
        for object_values, fields in _referenced_object_values(row, effective_objects):
            if not _object_is_mutable(
                object_values,
                owned_connections,
                configured_gds_connections,
                normalized_tenant,
            ):
                issues.append(
                    ValidationIssue(
                        "tenant_scope_mismatch",
                        row.dataset,
                        row.record_number,
                        fields,
                        "Referenced Object is not owned by the locked Tenant.",
                    )
                )
                break
        if len(issues) >= MAX_VALIDATION_ISSUES:
            break
    return issues


def _tenant_owner_fields(dataset: str) -> tuple[str, ...]:
    if dataset in {
        "copy_group",
        "member_group",
        "copy_group_control",
        "process_group",
        "process",
    }:
        return ("tenant_code",)
    if dataset == "copy":
        return ("tenant_code",)
    return ()


def _referenced_object_values(
    row: _Row,
    effective_objects: Mapping[tuple[object, ...], Mapping[str, object]],
) -> tuple[tuple[Mapping[str, object], tuple[str, ...]], ...]:
    record_type = _definition(row.dataset).record_type
    if record_type == "object":
        return ((row.values, OBJECT_KEY),)
    if record_type == "attribute":
        values = effective_objects.get(_normalized_key(OBJECT_KEY, row.values))
        return ((values, OBJECT_KEY),) if values is not None else ()
    if row.dataset in {
        "ingestion_object_mapping",
        "ingestion_attribute_mapping",
        "copy",
    }:
        references: list[tuple[Mapping[str, object], tuple[str, ...]]] = []
        for prefix in ("source", "target"):
            fields = tuple(f"{prefix}_{column}" for column in OBJECT_KEY)
            key = tuple(
                _normalize_key_value(column, row.values[field])
                for column, field in zip(OBJECT_KEY, fields, strict=True)
            )
            values = effective_objects.get(key)
            if values is not None:
                references.append((values, fields))
        return tuple(references)
    if row.dataset == "process":
        fields = (
            "object_tenant_code",
            "object_system_code",
            "object_connection_code",
            "object_schema",
            "object_name",
        )
        key = tuple(
            _normalize_key_value(column, row.values[field])
            for column, field in zip(OBJECT_KEY, fields, strict=True)
        )
        values = effective_objects.get(key)
        return ((values, fields),) if values is not None else ()
    return ()


def _object_is_mutable(
    values: Mapping[str, object],
    owned_connections: set[tuple[object, ...]],
    configured_gds_connections: set[tuple[object, ...]],
    normalized_tenant: object,
) -> bool:
    if (
        normalize_natural_key_value("source_tenant_code", values["source_tenant_code"])
        != normalized_tenant
    ):
        return False
    connection_key = _normalized_key(
        ("tenant_code", "system_code", "connection_code"),
        values,
    )
    zone_code = normalize_natural_key_value("zone_code", values["zone_code"])
    if zone_code == "source":
        return connection_key in owned_connections
    return zone_code in {"bronze", "silver", "gold"} and (
        connection_key in configured_gds_connections
    )


def _validate_staged_uniqueness(rows: Sequence[_Row]) -> list[ValidationIssue]:
    return _find_duplicate_constraints(rows, staged_only=True)


def _validate_effective_uniqueness(rows: Sequence[_Row]) -> list[ValidationIssue]:
    return _find_duplicate_constraints(rows, staged_only=False)


def _find_duplicate_constraints(
    rows: Sequence[_Row],
    *,
    staged_only: bool,
) -> list[ValidationIssue]:
    issues: list[ValidationIssue] = []
    for record_type, definitions in _definitions_by_record_type().items():
        relevant = [row for row in rows if _definition(row.dataset).record_type == record_type]
        constraints = tuple(
            dict.fromkeys(
                constraint
                for definition in definitions
                for constraint in definition.unique_constraints
            )
        )
        for constraint in constraints:
            seen: dict[tuple[object, ...], _Row] = {}
            for row in relevant:
                key = _normalized_key(constraint, row.values)
                first = seen.get(key)
                if first is None:
                    seen[key] = row
                    continue
                report = row if row.staged else first if first.staged else None
                if report is None and not staged_only:
                    continue
                if report is None:
                    report = row
                issues.append(
                    ValidationIssue(
                        "duplicate_unique_key",
                        report.dataset,
                        report.record_number,
                        constraint,
                        "Unique key is duplicated in the effective metadata.",
                    )
                )
                if len(issues) >= MAX_VALIDATION_ISSUES:
                    return issues
    return issues


def _overlay_rows(current: Sequence[_Row], staged: Sequence[_Row]) -> list[_Row]:
    effective: dict[tuple[str, tuple[object, ...]], _Row] = {}
    for row in (*current, *staged):
        definition = _definition(row.dataset)
        key = (definition.record_type, _normalized_key(definition.canonical_key, row.values))
        effective[key] = row
    return list(effective.values())


def _validate_references(rows: Sequence[_Row]) -> list[ValidationIssue]:
    keys_by_record_type: dict[str, set[tuple[object, ...]]] = {}
    for row in rows:
        definition = _definition(row.dataset)
        keys_by_record_type.setdefault(definition.record_type, set()).add(
            _normalized_key(definition.canonical_key, row.values)
        )

    issues: list[ValidationIssue] = []
    for row in rows:
        for reference in _definition(row.dataset).references:
            issue = _reference_issue(row, reference, keys_by_record_type)
            if issue is not None:
                issues.append(issue)
                if len(issues) >= MAX_VALIDATION_ISSUES:
                    return issues
    return issues


def _reference_issue(
    row: _Row,
    reference: ReferenceDefinition,
    keys_by_record_type: Mapping[str, set[tuple[object, ...]]],
) -> ValidationIssue | None:
    values = tuple(row.values[column] for column in reference.columns)
    if reference.nullable and any(value is None for value in values):
        return None
    if any(value is None for value in values):
        return ValidationIssue(
            "reference_incomplete",
            row.dataset,
            row.record_number,
            reference.columns,
            "Natural-key reference is only partially populated.",
        )
    target_key = tuple(
        _normalize_key_value(column, value)
        for column, value in zip(reference.target_columns, values, strict=True)
    )
    if target_key in keys_by_record_type.get(reference.target_record_type, set()):
        return None
    return ValidationIssue(
        "reference_not_found",
        row.dataset,
        row.record_number,
        reference.columns,
        f"Referenced {reference.target_record_type} was not found.",
    )


def _candidate_digest(rows: Sequence[_Row]) -> str:
    documents: dict[str, list[dict[str, object]]] = {
        definition.name: [] for definition in DATASETS if definition.change_set_eligible
    }
    for row in rows:
        documents[row.dataset].append(row.values)
    for dataset, document in documents.items():
        definition = _definition(dataset)
        document.sort(key=lambda item: _normalized_key(definition.canonical_key, item))
    payload = json.dumps(
        documents,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _failed(
    phase: str,
    staged_count: int,
    issues: Sequence[ValidationIssue],
    digest: str | None = None,
) -> MetadataChangeSetValidation:
    return MetadataChangeSetValidation(
        valid=False,
        phase=phase,
        candidate_digest=digest,
        staged_record_count=staged_count,
        issues=tuple(issues[:MAX_VALIDATION_ISSUES]),
        action_review=(),
    )


def _definition(dataset: str) -> DatasetDefinition:
    for definition in DATASETS:
        if definition.name == dataset:
            return definition
    raise KeyError(dataset)


def _definitions_by_record_type() -> dict[str, tuple[DatasetDefinition, ...]]:
    grouped: dict[str, list[DatasetDefinition]] = {}
    for definition in DATASETS:
        grouped.setdefault(definition.record_type, []).append(definition)
    return {name: tuple(definitions) for name, definitions in grouped.items()}


def _normalized_key(
    columns: tuple[str, ...],
    row: Mapping[str, object],
) -> tuple[object, ...]:
    return tuple(_normalize_key_value(column, row[column]) for column in columns)


def _normalize_key_value(column: str, value: object) -> object:
    return normalize_natural_key_value(column, value)
