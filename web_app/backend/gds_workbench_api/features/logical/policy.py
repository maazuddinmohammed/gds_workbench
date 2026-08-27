"""Deterministic Logical audit-column projection."""

from __future__ import annotations

import json
from typing import Annotated, Literal, cast

from gds_etl_workbench.domain.errors import InvalidRequestError
from gds_etl_workbench.domain.modeling_records import (
    LogicalAttributeRecord,
    LogicalEntityRecord,
    normalize_model_key_value,
)
from gds_etl_workbench.tools.change_sets.model import StageModelChange
from gds_etl_workbench.tools.change_sets.model_validation import validate_staged_records
from gds_etl_workbench.tools.snapshots.model.contracts import LogicalSection
from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StringConstraints,
    ValidationError,
    model_validator,
)

type _Nonblank255 = Annotated[
    str,
    StringConstraints(min_length=1, max_length=255, pattern=r"\S"),
]
type _Nonblank100 = Annotated[
    str,
    StringConstraints(min_length=1, max_length=100, pattern=r"\S"),
]
type _Nonblank2000 = Annotated[
    str,
    StringConstraints(min_length=1, max_length=2_000, pattern=r"\S"),
]


class LogicalAuditPolicyColumn(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    semantic_name: _Nonblank255
    data_type: _Nonblank100
    nullable: bool
    definition: _Nonblank2000 | None


class LogicalAuditPolicy(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    schema_version: Literal["1.0"] = "1.0"
    columns: tuple[LogicalAuditPolicyColumn, ...] = Field(min_length=1, max_length=32)

    @model_validator(mode="after")
    def validate_names(self) -> LogicalAuditPolicy:
        names = [normalize_model_key_value(column.semantic_name) for column in self.columns]
        if len(names) != len(set(names)):
            raise ValueError("Logical audit policy names must be unique")
        return self


def project_logical_audit_policy(
    *,
    changes: tuple[StageModelChange, ...],
    applied: LogicalSection | None,
    raw_template: dict[str, object] | None,
) -> tuple[StageModelChange, ...]:
    """Add the configured audit columns to every effective active Logical Entity."""

    if raw_template is None:
        return changes
    policy = _parse_policy(raw_template)
    baseline = applied or LogicalSection(submodels=(), entities=(), attributes=(), relationships=())
    changes_by_dataset = {change.dataset: change for change in changes}
    if len(changes_by_dataset) != len(changes) or any(
        not change.dataset.startswith("logical_") for change in changes
    ):
        raise InvalidRequestError("Logical policy projection received invalid input.")

    changed_entities = _parse_records(
        changes_by_dataset.get("logical_entity"),
        dataset="logical_entity",
        record_type=LogicalEntityRecord,
    )
    changed_attributes = _parse_records(
        changes_by_dataset.get("logical_attribute"),
        dataset="logical_attribute",
        record_type=LogicalAttributeRecord,
    )
    entities = {_entity_key(record): record for record in baseline.entities}
    entities.update({_entity_key(record): record for record in changed_entities})
    attributes = {_attribute_key(record): record for record in baseline.attributes}
    attributes.update({_attribute_key(record): record for record in changed_attributes})

    projected: list[LogicalAttributeRecord] = []
    for entity_key, entity in sorted(entities.items()):
        if entity.logical_entity_status not in ("active", "needs_review"):
            continue
        entity_attributes = [record for key, record in attributes.items() if key[0] == entity_key]
        next_ordinal = 1 + max(
            (
                record.logical_attribute_ordinal_position
                for record in entity_attributes
                if not record.logical_attribute_is_audit_column
            ),
            default=0,
        )
        for offset, column in enumerate(policy.columns):
            key = (entity_key, normalize_model_key_value(column.semantic_name))
            existing = attributes.get(key)
            desired = _policy_attribute(
                entity=entity,
                column=column,
                ordinal=next_ordinal + offset,
                existing=existing,
            )
            if existing != desired:
                projected.append(desired)
            attributes[key] = desired

    changed_attribute_by_key = {_attribute_key(record): record for record in changed_attributes}
    for record in projected:
        changed_attribute_by_key[_attribute_key(record)] = record

    output: list[StageModelChange] = []
    for dataset in (
        "logical_submodel",
        "logical_entity",
        "logical_attribute",
        "logical_relationship",
    ):
        if dataset == "logical_attribute":
            records = [
                record.model_dump(mode="json")
                for _, record in sorted(changed_attribute_by_key.items())
            ]
        else:
            change = changes_by_dataset.get(dataset)
            records = [] if change is None else change.records
        if records:
            output.append(StageModelChange(dataset=dataset, records=records))
    return tuple(output)


def _parse_policy(raw_template: dict[str, object]) -> LogicalAuditPolicy:
    try:
        return LogicalAuditPolicy.model_validate_json(
            json.dumps(
                raw_template,
                ensure_ascii=False,
                allow_nan=False,
                separators=(",", ":"),
            ),
            strict=True,
        )
    except (TypeError, ValueError, ValidationError):
        raise InvalidRequestError("The Silver audit-column template is invalid.") from None


def _parse_records[T: BaseModel](
    change: StageModelChange | None,
    *,
    dataset: Literal["logical_entity", "logical_attribute"],
    record_type: type[T],
) -> tuple[T, ...]:
    if change is None:
        return ()
    records, issues = validate_staged_records(dataset, change.records)
    if issues:
        raise InvalidRequestError("Logical policy projection received invalid input.")
    return tuple(cast(T, record) for record in records if isinstance(record, record_type))


def _policy_attribute(
    *,
    entity: LogicalEntityRecord,
    column: LogicalAuditPolicyColumn,
    ordinal: int,
    existing: LogicalAttributeRecord | None,
) -> LogicalAttributeRecord:
    if existing is not None and (
        not existing.logical_attribute_is_audit_column
        or normalize_model_key_value(existing.logical_attribute_data_type)
        != normalize_model_key_value(column.data_type)
        or existing.logical_attribute_is_nullable != column.nullable
        or existing.sources
    ):
        raise InvalidRequestError(
            "A configured Logical audit column conflicts with an existing Attribute."
        )
    desired = LogicalAttributeRecord(
        logical_entity_name=entity.logical_entity_name,
        logical_attribute_name=column.semantic_name,
        logical_attribute_definition=column.definition or column.semantic_name,
        logical_attribute_data_type=column.data_type,
        logical_attribute_is_nullable=column.nullable,
        logical_attribute_is_primary_key=False,
        logical_attribute_is_natural_key=False,
        logical_attribute_is_surrogate_key=False,
        logical_attribute_ordinal_position=ordinal,
        logical_attribute_is_audit_column=True,
        logical_attribute_status="active",
        logical_attribute_is_locked=(
            existing.logical_attribute_is_locked if existing is not None else False
        ),
        sources=(),
    )
    if existing is not None and existing.logical_attribute_is_locked and existing != desired:
        raise InvalidRequestError("A locked Logical audit column cannot be projected.")
    return desired


def _entity_key(record: LogicalEntityRecord) -> str:
    return normalize_model_key_value(record.logical_entity_name)


def _attribute_key(record: LogicalAttributeRecord) -> tuple[str, str]:
    return (
        normalize_model_key_value(record.logical_entity_name),
        normalize_model_key_value(record.logical_attribute_name),
    )


__all__ = [
    "LogicalAuditPolicy",
    "LogicalAuditPolicyColumn",
    "project_logical_audit_policy",
]
