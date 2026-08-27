"""Normalize one non-deleting Dimensional agent candidate into canonical changes."""

from __future__ import annotations

import json
from collections.abc import Callable, Sequence
from copy import deepcopy
from typing import cast

from gds_etl_workbench.domain.errors import InvalidRequestError
from gds_etl_workbench.domain.modeling_records import (
    AttributeAssertionSourceRecord,
    AttributePhysicalSourceRecord,
    DimensionalAssertionSourceRecord,
    DimensionalAttributeRecord,
    DimensionalEntityRecord,
    DimensionalObjectSourceRecord,
    DimensionalRelationshipRecord,
    DimensionalSubmodelRecord,
    PhysicalAttributeKey,
    PhysicalObjectKey,
    SubmodelMembershipRecord,
    normalize_model_key_value,
)
from gds_etl_workbench.tools.change_sets.model import StageModelChange
from gds_etl_workbench.tools.change_sets.model_validation import (
    ModelValidationIssue,
    validate_staged_records,
)
from gds_etl_workbench.tools.snapshots.model.contracts import DimensionalSection
from pydantic import BaseModel, ConfigDict, Field, JsonValue, ValidationError, model_validator

from gds_workbench_api.features.workflows.authoring.repair import (
    AgentCandidateValidation,
    AgentValidationIssue,
)

type _EntitySource = DimensionalObjectSourceRecord | DimensionalAssertionSourceRecord
type _AttributeSource = AttributePhysicalSourceRecord | AttributeAssertionSourceRecord


class _DimensionalCandidate(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    submodels: list[DimensionalSubmodelRecord] = Field(max_length=20_000)
    entities: list[DimensionalEntityRecord] = Field(max_length=20_000)
    attributes: list[DimensionalAttributeRecord] = Field(max_length=20_000)
    relationships: list[DimensionalRelationshipRecord] = Field(max_length=20_000)

    @model_validator(mode="after")
    def validate_size(self) -> _DimensionalCandidate:
        count = (
            len(self.submodels)
            + len(self.entities)
            + len(self.attributes)
            + len(self.relationships)
        )
        if not 1 <= count <= 20_000:
            raise ValueError("Dimensional candidates must be bounded and nonempty")
        return self


class _NormalizedCandidate(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    submodels: tuple[DimensionalSubmodelRecord, ...]
    entities: tuple[DimensionalEntityRecord, ...]
    attributes: tuple[DimensionalAttributeRecord, ...]
    relationships: tuple[DimensionalRelationshipRecord, ...]
    issues: tuple[AgentValidationIssue, ...]


class DimensionalCandidateValidator:
    """Validate a complete agent proposal against one immutable Silver selection."""

    def __init__(
        self,
        *,
        selected_object_keys: tuple[PhysicalObjectKey, ...],
        selected_attribute_keys: tuple[PhysicalAttributeKey, ...],
        assertion_record_keys: tuple[str, ...],
        applied: DimensionalSection | None,
    ) -> None:
        if not selected_object_keys or len(selected_object_keys) > 50_000:
            raise ValueError("Dimensional Object selection must be bounded and nonempty")
        if len(selected_attribute_keys) > 50_000:
            raise ValueError("Dimensional Attribute selection must be bounded")
        self._selected_object_keys = {_physical_object_key(item) for item in selected_object_keys}
        self._selected_attribute_keys = {
            _physical_attribute_key(item) for item in selected_attribute_keys
        }
        self._assertion_record_keys = {
            normalize_model_key_value(item) for item in assertion_record_keys
        }
        if (
            len(self._selected_object_keys) != len(selected_object_keys)
            or len(self._selected_attribute_keys) != len(selected_attribute_keys)
            or len(self._assertion_record_keys) != len(assertion_record_keys)
        ):
            raise ValueError("Dimensional candidate evidence keys must be unique")

        self._applied = applied or DimensionalSection(
            submodels=(), entities=(), attributes=(), relationships=()
        )
        self._applied_submodels = {
            _submodel_key(record): record for record in self._applied.submodels
        }
        self._applied_entities = {_entity_key(record): record for record in self._applied.entities}
        self._applied_attributes = {
            _attribute_key(record): record for record in self._applied.attributes
        }
        self._applied_relationships = {
            _relationship_key(record): record for record in self._applied.relationships
        }
        if any(
            actual != expected
            for actual, expected in (
                (len(self._applied_submodels), len(self._applied.submodels)),
                (len(self._applied_entities), len(self._applied.entities)),
                (len(self._applied_attributes), len(self._applied.attributes)),
                (len(self._applied_relationships), len(self._applied.relationships)),
            )
        ):
            raise ValueError("Applied Dimensional records must be unique")

    def output_schema(self) -> dict[str, JsonValue]:
        schema = cast(dict[str, JsonValue], deepcopy(_DimensionalCandidate.model_json_schema()))
        _set_lock_fields_false(schema)
        return schema

    async def validate(self, candidate: JsonValue) -> AgentCandidateValidation:
        return AgentCandidateValidation(issues=self._normalize(candidate).issues)

    def parse_validated(self, candidate: JsonValue) -> tuple[StageModelChange, ...]:
        normalized = self._normalize(candidate)
        if normalized.issues:
            raise InvalidRequestError("The Dimensional candidate is invalid.")

        changes: list[StageModelChange] = []
        changed_submodels = [
            record.model_dump(mode="json")
            for record in normalized.submodels
            if self._applied_submodels.get(_submodel_key(record)) != record
        ]
        changed_entities = [
            record.model_dump(mode="json")
            for record in normalized.entities
            if self._applied_entities.get(_entity_key(record)) != record
        ]
        changed_attributes = [
            record.model_dump(mode="json")
            for record in normalized.attributes
            if self._applied_attributes.get(_attribute_key(record)) != record
        ]
        changed_relationships = [
            record.model_dump(mode="json")
            for record in normalized.relationships
            if self._applied_relationships.get(_relationship_key(record)) != record
        ]
        if changed_submodels:
            changes.append(
                StageModelChange(dataset="dimensional_submodel", records=changed_submodels)
            )
        if changed_entities:
            changes.append(StageModelChange(dataset="dimensional_entity", records=changed_entities))
        if changed_attributes:
            changes.append(
                StageModelChange(dataset="dimensional_attribute", records=changed_attributes)
            )
        if changed_relationships:
            changes.append(
                StageModelChange(
                    dataset="dimensional_relationship",
                    records=changed_relationships,
                )
            )
        return tuple(changes)

    def _normalize(self, candidate: JsonValue) -> _NormalizedCandidate:
        parsed = _parse_candidate(candidate)
        if parsed is None:
            return _NormalizedCandidate(
                submodels=(),
                entities=(),
                attributes=(),
                relationships=(),
                issues=(
                    AgentValidationIssue(
                        code="candidate.schema_invalid",
                        path=(),
                        message="The candidate does not match the Dimensional schema.",
                    ),
                ),
            )

        issues: list[AgentValidationIssue] = []
        for index, submodel in enumerate(parsed.submodels):
            if submodel.dimensional_submodel_is_locked:
                _lock_forbidden(("submodels", index), issues)
        for index, entity in enumerate(parsed.entities):
            if entity.dimensional_entity_is_locked:
                _lock_forbidden(("entities", index), issues)
            for nested_index, membership in enumerate(entity.submodels):
                if membership.membership_is_locked:
                    _lock_forbidden(("entities", index, "submodels", nested_index), issues)
            for source_index, source in enumerate(entity.sources):
                if source.is_locked:
                    _lock_forbidden(("entities", index, "sources", source_index), issues)
                if isinstance(source, DimensionalObjectSourceRecord):
                    valid = _physical_object_key(source.source_object) in self._selected_object_keys
                    code = "candidate.source_outside_selection"
                    message = "Silver Object source must belong to this immutable run selection."
                else:
                    valid = (
                        normalize_model_key_value(
                            source.assertion_record.modeling_assertion_record_key
                        )
                        in self._assertion_record_keys
                    )
                    code = "candidate.assertion_unavailable"
                    message = "Assertion source must exist in this immutable run context."
                if not valid:
                    issues.append(
                        AgentValidationIssue(
                            code=code,
                            path=("entities", index, "sources", source_index),
                            message=message,
                        )
                    )
        for index, attribute in enumerate(parsed.attributes):
            if (
                attribute.dimensional_attribute_role in ("technical", "audit")
                or attribute.dimensional_attribute_key_role in ("surrogate", "foreign")
                or attribute.dimensional_attribute_is_audit_column
            ):
                issues.append(
                    AgentValidationIssue(
                        code="candidate.policy_column_forbidden",
                        path=("attributes", index, "dimensional_attribute_role"),
                        message=(
                            "Dimensional surrogate, foreign-key, technical, and audit "
                            "Attributes are projected deterministically."
                        ),
                    )
                )
            if attribute.dimensional_attribute_is_locked:
                _lock_forbidden(("attributes", index), issues)
            for source_index, source in enumerate(attribute.sources):
                if source.is_locked:
                    _lock_forbidden(("attributes", index, "sources", source_index), issues)
                if isinstance(source, AttributePhysicalSourceRecord):
                    valid = (
                        _physical_attribute_key(source.source_attribute)
                        in self._selected_attribute_keys
                    )
                    code = "candidate.source_outside_selection"
                    message = "Silver Attribute source must belong to this immutable run selection."
                else:
                    valid = (
                        normalize_model_key_value(
                            source.assertion_record.modeling_assertion_record_key
                        )
                        in self._assertion_record_keys
                    )
                    code = "candidate.assertion_unavailable"
                    message = "Assertion source must exist in this immutable run context."
                if not valid:
                    issues.append(
                        AgentValidationIssue(
                            code=code,
                            path=("attributes", index, "sources", source_index),
                            message=message,
                        )
                    )

        for index, relationship in enumerate(parsed.relationships):
            if relationship.dimensional_relationship_is_locked:
                _lock_forbidden(("relationships", index), issues)

        submodels, submodel_issues = validate_staged_records(
            "dimensional_submodel",
            [
                _merge_submodel(record, self._applied_submodels.get(_submodel_key(record)))
                for record in parsed.submodels
            ],
        )
        entities, entity_issues = validate_staged_records(
            "dimensional_entity",
            [
                _merge_entity(record, self._applied_entities.get(_entity_key(record)))
                for record in parsed.entities
            ],
        )
        attributes, attribute_issues = validate_staged_records(
            "dimensional_attribute",
            [
                _merge_attribute(
                    record,
                    self._applied_attributes.get(_attribute_key(record)),
                )
                for record in parsed.attributes
            ],
        )
        relationships, relationship_issues = validate_staged_records(
            "dimensional_relationship",
            [
                _merge_relationship(
                    record,
                    self._applied_relationships.get(_relationship_key(record)),
                )
                for record in parsed.relationships
            ],
        )
        typed_submodels = cast(tuple[DimensionalSubmodelRecord, ...], submodels)
        typed_entities = cast(tuple[DimensionalEntityRecord, ...], entities)
        typed_attributes = cast(tuple[DimensionalAttributeRecord, ...], attributes)
        typed_relationships = cast(tuple[DimensionalRelationshipRecord, ...], relationships)
        issues.extend(
            _model_issues(submodel_issues + entity_issues + attribute_issues + relationship_issues)
        )
        for index, record in enumerate(typed_submodels):
            existing = self._applied_submodels.get(_submodel_key(record))
            if existing is not None:
                _append_locked_change_issues(
                    existing,
                    record,
                    path=("submodels", index),
                    issues=issues,
                )
        for index, record in enumerate(typed_entities):
            existing = self._applied_entities.get(_entity_key(record))
            if existing is not None:
                _append_locked_change_issues(
                    existing,
                    record,
                    path=("entities", index),
                    issues=issues,
                )
        for index, record in enumerate(typed_attributes):
            existing = self._applied_attributes.get(_attribute_key(record))
            if existing is not None:
                _append_locked_change_issues(
                    existing,
                    record,
                    path=("attributes", index),
                    issues=issues,
                )
        for index, record in enumerate(typed_relationships):
            existing = self._applied_relationships.get(_relationship_key(record))
            if existing is not None:
                _append_locked_change_issues(
                    existing,
                    record,
                    path=("relationships", index),
                    issues=issues,
                )

        submodel_keys = set(self._applied_submodels)
        submodel_keys.update(_submodel_key(record) for record in typed_submodels)
        entity_keys = set(self._applied_entities)
        entity_keys.update(_entity_key(record) for record in typed_entities)
        attribute_keys = set(self._applied_attributes)
        attribute_keys.update(_attribute_key(record) for record in typed_attributes)
        for index, entity in enumerate(typed_entities):
            if any(
                normalize_model_key_value(membership.submodel_name) not in submodel_keys
                for membership in entity.submodels
            ):
                issues.append(
                    AgentValidationIssue(
                        code="candidate.submodel_missing",
                        path=("entities", index, "submodels"),
                        message="Every Dimensional Entity Submodel must exist.",
                    )
                )
        for index, attribute in enumerate(typed_attributes):
            if normalize_model_key_value(attribute.dimensional_entity_name) not in entity_keys:
                issues.append(
                    AgentValidationIssue(
                        code="candidate.entity_missing",
                        path=("attributes", index, "dimensional_entity_name"),
                        message="Every Dimensional Attribute Entity must exist.",
                    )
                )
        for index, relationship in enumerate(typed_relationships):
            endpoints = (
                (
                    normalize_model_key_value(relationship.from_dimensional_entity_name),
                    normalize_model_key_value(relationship.from_dimensional_attribute_name),
                ),
                (
                    normalize_model_key_value(relationship.to_dimensional_entity_name),
                    normalize_model_key_value(relationship.to_dimensional_attribute_name),
                ),
            )
            if any(endpoint not in attribute_keys for endpoint in endpoints):
                issues.append(
                    AgentValidationIssue(
                        code="candidate.relationship_endpoint_missing",
                        path=("relationships", index),
                        message="Both Dimensional Relationship endpoints must exist.",
                    )
                )
        return _NormalizedCandidate(
            submodels=typed_submodels,
            entities=typed_entities,
            attributes=typed_attributes,
            relationships=typed_relationships,
            issues=tuple(issues),
        )


def _parse_candidate(candidate: JsonValue) -> _DimensionalCandidate | None:
    try:
        return _DimensionalCandidate.model_validate_json(
            json.dumps(candidate, ensure_ascii=False, allow_nan=False, separators=(",", ":")),
            strict=True,
        )
    except (TypeError, ValueError, ValidationError):
        return None


def _merge_submodel(
    record: DimensionalSubmodelRecord,
    existing: DimensionalSubmodelRecord | None,
) -> dict[str, object]:
    value = cast(dict[str, object], record.model_dump(mode="json"))
    value["dimensional_submodel_is_locked"] = (
        existing.dimensional_submodel_is_locked if existing is not None else False
    )
    return value


def _merge_entity(
    record: DimensionalEntityRecord,
    existing: DimensionalEntityRecord | None,
) -> dict[str, object]:
    value = cast(dict[str, object], record.model_dump(mode="json"))
    value["dimensional_entity_is_locked"] = (
        existing.dimensional_entity_is_locked if existing is not None else False
    )
    value["submodels"] = _merge_nested(
        record.submodels,
        () if existing is None else existing.submodels,
        key=_membership_key,
        lock_field="membership_is_locked",
    )
    value["sources"] = _merge_nested(
        record.sources,
        () if existing is None else existing.sources,
        key=_entity_source_key,
        lock_field="is_locked",
    )
    return value


def _merge_attribute(
    record: DimensionalAttributeRecord,
    existing: DimensionalAttributeRecord | None,
) -> dict[str, object]:
    value = cast(dict[str, object], record.model_dump(mode="json"))
    value["dimensional_attribute_is_locked"] = (
        existing.dimensional_attribute_is_locked if existing is not None else False
    )
    value["sources"] = _merge_nested(
        record.sources,
        () if existing is None else existing.sources,
        key=_attribute_source_key,
        lock_field="is_locked",
    )
    return value


def _merge_relationship(
    record: DimensionalRelationshipRecord,
    existing: DimensionalRelationshipRecord | None,
) -> dict[str, object]:
    value = cast(dict[str, object], record.model_dump(mode="json"))
    value["dimensional_relationship_is_locked"] = (
        existing.dimensional_relationship_is_locked if existing is not None else False
    )
    return value


def _merge_nested[T: BaseModel](
    candidate: Sequence[T],
    existing: Sequence[T],
    *,
    key: Callable[[T], tuple[str, ...]],
    lock_field: str,
) -> list[dict[str, object]]:
    candidate_by_key = {key(item): item for item in candidate}
    existing_by_key = {key(item): item for item in existing}
    merged: list[dict[str, object]] = []
    for applied_record in existing:
        candidate_record = candidate_by_key.get(key(applied_record))
        if candidate_record is None:
            merged.append(cast(dict[str, object], applied_record.model_dump(mode="json")))
            continue
        value = cast(dict[str, object], candidate_record.model_dump(mode="json"))
        value[lock_field] = getattr(applied_record, lock_field)
        merged.append(value)
    for candidate_record in candidate:
        if key(candidate_record) in existing_by_key:
            continue
        value = cast(dict[str, object], candidate_record.model_dump(mode="json"))
        value[lock_field] = False
        merged.append(value)
    return merged


def _model_issues(issues: tuple[ModelValidationIssue, ...]) -> tuple[AgentValidationIssue, ...]:
    return tuple(
        AgentValidationIssue(
            code=f"candidate.{issue.code}",
            path=(
                issue.dataset,
                *((issue.record_number - 1,) if issue.record_number is not None else ()),
                *issue.fields,
            ),
            message=issue.message,
        )
        for issue in issues
    )


def _lock_forbidden(
    path: tuple[str | int, ...],
    issues: list[AgentValidationIssue],
) -> None:
    issues.append(
        AgentValidationIssue(
            code="candidate.lock_forbidden",
            path=path,
            message="Only a user may change Dimensional lock state.",
        )
    )


def _append_locked_change_issues(
    existing: object,
    changed: object,
    *,
    path: tuple[str | int, ...],
    issues: list[AgentValidationIssue],
) -> None:
    if _top_lock(existing) and existing != changed:
        _record_locked(path, issues)
        return
    for field_name, key_function, lock_field in (
        ("submodels", _membership_key, "membership_is_locked"),
        ("sources", _nested_source_key, "is_locked"),
    ):
        applied_nested = getattr(existing, field_name, ())
        changed_nested = {key_function(item): item for item in getattr(changed, field_name, ())}
        for index, applied_record in enumerate(applied_nested):
            candidate_record = changed_nested.get(key_function(applied_record))
            if (
                getattr(applied_record, lock_field)
                and candidate_record is not None
                and applied_record != candidate_record
            ):
                _record_locked(path + (field_name, index), issues)


def _record_locked(
    path: tuple[str | int, ...],
    issues: list[AgentValidationIssue],
) -> None:
    issues.append(
        AgentValidationIssue(
            code="candidate.record_locked",
            path=path,
            message="A locked applied Dimensional record cannot be changed.",
        )
    )


def _top_lock(record: object) -> bool:
    if isinstance(record, DimensionalSubmodelRecord):
        return record.dimensional_submodel_is_locked
    if isinstance(record, DimensionalEntityRecord):
        return record.dimensional_entity_is_locked
    if isinstance(record, DimensionalAttributeRecord):
        return record.dimensional_attribute_is_locked
    if isinstance(record, DimensionalRelationshipRecord):
        return record.dimensional_relationship_is_locked
    raise TypeError("Unsupported Dimensional record")


def _set_lock_fields_false(value: JsonValue) -> None:
    if isinstance(value, list):
        for child in value:
            _set_lock_fields_false(child)
        return
    if not isinstance(value, dict):
        return
    properties = value.get("properties")
    if isinstance(properties, dict):
        for name, property_schema in properties.items():
            if isinstance(property_schema, dict) and (
                name.endswith("_is_locked") or name == "is_locked"
            ):
                property_schema["const"] = False
    for child in value.values():
        _set_lock_fields_false(child)


def _submodel_key(record: DimensionalSubmodelRecord) -> str:
    return normalize_model_key_value(record.dimensional_submodel_name)


def _entity_key(record: DimensionalEntityRecord) -> str:
    return normalize_model_key_value(record.dimensional_entity_name)


def _attribute_key(record: DimensionalAttributeRecord) -> tuple[str, str]:
    return (
        normalize_model_key_value(record.dimensional_entity_name),
        normalize_model_key_value(record.dimensional_attribute_name),
    )


def _relationship_key(
    record: DimensionalRelationshipRecord,
) -> tuple[str, str, str, str, str, str | None]:
    return (
        normalize_model_key_value(record.from_dimensional_entity_name),
        normalize_model_key_value(record.from_dimensional_attribute_name),
        normalize_model_key_value(record.to_dimensional_entity_name),
        normalize_model_key_value(record.to_dimensional_attribute_name),
        normalize_model_key_value(record.dimensional_relationship_kind),
        normalize_model_key_value(record.dimensional_relationship_role_name),
    )


def _membership_key(record: SubmodelMembershipRecord) -> tuple[str, ...]:
    return (normalize_model_key_value(record.submodel_name),)


def _entity_source_key(record: _EntitySource) -> tuple[str, ...]:
    if isinstance(record, DimensionalObjectSourceRecord):
        return ("object", *_physical_object_key(record.source_object))
    return (
        "assertion",
        normalize_model_key_value(record.assertion_record.modeling_assertion_record_key),
    )


def _attribute_source_key(record: _AttributeSource) -> tuple[str, ...]:
    if isinstance(record, AttributePhysicalSourceRecord):
        return ("attribute", *_physical_attribute_key(record.source_attribute))
    return (
        "assertion",
        normalize_model_key_value(record.assertion_record.modeling_assertion_record_key),
    )


def _nested_source_key(record: object) -> tuple[str, ...]:
    if isinstance(record, (DimensionalObjectSourceRecord, DimensionalAssertionSourceRecord)):
        return _entity_source_key(record)
    if isinstance(record, (AttributePhysicalSourceRecord, AttributeAssertionSourceRecord)):
        return _attribute_source_key(record)
    raise TypeError("Unsupported Dimensional nested source")


def _physical_object_key(record: PhysicalObjectKey) -> tuple[str, str, str, str, str]:
    return tuple(
        normalize_model_key_value(getattr(record, field))
        for field in (
            "tenant_code",
            "system_code",
            "connection_code",
            "object_schema",
            "object_name",
        )
    )


def _physical_attribute_key(
    record: PhysicalAttributeKey,
) -> tuple[str, str, str, str, str, str]:
    return (*_physical_object_key(record), normalize_model_key_value(record.attribute_name))


__all__ = ["DimensionalCandidateValidator"]
