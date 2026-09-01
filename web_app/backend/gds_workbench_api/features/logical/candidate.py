"""Normalize one non-deleting Logical agent candidate into canonical changes."""

from __future__ import annotations

from collections.abc import Callable, Sequence
from copy import deepcopy
from typing import cast

from gds_etl_workbench.domain.errors import InvalidRequestError
from gds_etl_workbench.domain.modeling_records import (
    AttributeAssertionSourceRecord,
    AttributePhysicalSourceRecord,
    LogicalAssertionSourceRecord,
    LogicalAttributeRecord,
    LogicalEntityRecord,
    LogicalObjectSourceRecord,
    LogicalRelationshipRecord,
    LogicalSubmodelRecord,
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
from gds_etl_workbench.tools.snapshots.model.contracts import LogicalSection
from pydantic import BaseModel, ConfigDict, Field, JsonValue, model_validator

from gds_workbench_api.features.workflows.authoring.repair import (
    AgentCandidateValidation,
    AgentValidationIssue,
    enrich_agent_output_model_definitions,
    parse_pydantic_candidate,
)

type _EntitySource = LogicalObjectSourceRecord | LogicalAssertionSourceRecord
type _AttributeSource = AttributePhysicalSourceRecord | AttributeAssertionSourceRecord


class _LogicalCandidate(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    submodels: list[LogicalSubmodelRecord] = Field(max_length=20_000)
    entities: list[LogicalEntityRecord] = Field(max_length=20_000)
    attributes: list[LogicalAttributeRecord] = Field(max_length=20_000)
    relationships: list[LogicalRelationshipRecord] = Field(max_length=20_000)

    @model_validator(mode="after")
    def validate_size(self) -> _LogicalCandidate:
        count = (
            len(self.submodels)
            + len(self.entities)
            + len(self.attributes)
            + len(self.relationships)
        )
        if count > 20_000:
            raise ValueError("Logical candidates must be bounded")
        return self


class _NormalizedCandidate(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    submodels: tuple[LogicalSubmodelRecord, ...]
    entities: tuple[LogicalEntityRecord, ...]
    attributes: tuple[LogicalAttributeRecord, ...]
    relationships: tuple[LogicalRelationshipRecord, ...]
    issues: tuple[AgentValidationIssue, ...]


class LogicalCandidateValidator:
    """Enforce selection, locks, references, and omission-is-not-delete semantics."""

    def __init__(
        self,
        *,
        selected_object_keys: tuple[PhysicalObjectKey, ...],
        selected_attribute_keys: tuple[PhysicalAttributeKey, ...],
        assertion_record_keys: tuple[str, ...],
        applied: LogicalSection | None,
    ) -> None:
        if not selected_object_keys or len(selected_object_keys) > 50_000:
            raise ValueError("Logical Object selection must be bounded and nonempty")
        if len(selected_attribute_keys) > 50_000:
            raise ValueError("Logical Attribute selection must be bounded")
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
            raise ValueError("Logical candidate evidence keys must be unique")

        self._applied = applied or LogicalSection(
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
            raise ValueError("Applied Logical records must be unique")

    def output_schema(self) -> dict[str, JsonValue]:
        schema = cast(dict[str, JsonValue], deepcopy(_LogicalCandidate.model_json_schema()))
        _set_lock_fields_false(schema)
        enrich_agent_output_model_definitions(schema)
        return schema

    async def validate(self, candidate: JsonValue) -> AgentCandidateValidation:
        return AgentCandidateValidation(issues=self._normalize(candidate).issues)

    def parse_validated(self, candidate: JsonValue) -> tuple[StageModelChange, ...]:
        normalized = self._normalize(candidate)
        if normalized.issues:
            raise InvalidRequestError("The Logical candidate is invalid.")

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
            changes.append(StageModelChange(dataset="logical_submodel", records=changed_submodels))
        if changed_entities:
            changes.append(StageModelChange(dataset="logical_entity", records=changed_entities))
        if changed_attributes:
            changes.append(
                StageModelChange(dataset="logical_attribute", records=changed_attributes)
            )
        if changed_relationships:
            changes.append(
                StageModelChange(
                    dataset="logical_relationship",
                    records=changed_relationships,
                )
            )
        return tuple(changes)

    def _normalize(self, candidate: JsonValue) -> _NormalizedCandidate:
        parsed, parse_issues = parse_pydantic_candidate(_LogicalCandidate, candidate)
        if parsed is None:
            return _NormalizedCandidate(
                submodels=(),
                entities=(),
                attributes=(),
                relationships=(),
                issues=parse_issues,
            )

        issues: list[AgentValidationIssue] = []
        raw_submodels: list[dict[str, object]] = []
        for index, record in enumerate(parsed.submodels):
            if record.logical_submodel_is_locked:
                _lock_forbidden(("submodels", index), issues)
            raw_submodels.append(
                _merge_submodel(record, self._applied_submodels.get(_submodel_key(record)))
            )
        raw_entities: list[dict[str, object]] = []
        for index, record in enumerate(parsed.entities):
            _validate_entity_authority(record, index=index, issues=issues)
            self._validate_entity_evidence(record, index=index, issues=issues)
            raw_entities.append(
                _merge_entity(record, self._applied_entities.get(_entity_key(record)))
            )
        raw_attributes: list[dict[str, object]] = []
        for index, record in enumerate(parsed.attributes):
            _validate_attribute_authority(record, index=index, issues=issues)
            self._validate_attribute_evidence(record, index=index, issues=issues)
            raw_attributes.append(
                _merge_attribute(record, self._applied_attributes.get(_attribute_key(record)))
            )
        raw_relationships: list[dict[str, object]] = []
        for index, record in enumerate(parsed.relationships):
            if record.logical_relationship_is_locked:
                _lock_forbidden(("relationships", index), issues)
            raw_relationships.append(
                _merge_relationship(
                    record,
                    self._applied_relationships.get(_relationship_key(record)),
                )
            )

        submodels, submodel_issues = validate_staged_records("logical_submodel", raw_submodels)
        entities, entity_issues = validate_staged_records("logical_entity", raw_entities)
        attributes, attribute_issues = validate_staged_records("logical_attribute", raw_attributes)
        relationships, relationship_issues = validate_staged_records(
            "logical_relationship", raw_relationships
        )
        issues.extend(
            _model_issues(submodel_issues + entity_issues + attribute_issues + relationship_issues)
        )
        typed_submodels = cast(tuple[LogicalSubmodelRecord, ...], submodels)
        typed_entities = cast(tuple[LogicalEntityRecord, ...], entities)
        typed_attributes = cast(tuple[LogicalAttributeRecord, ...], attributes)
        typed_relationships = cast(tuple[LogicalRelationshipRecord, ...], relationships)

        self._validate_locks(
            typed_submodels,
            typed_entities,
            typed_attributes,
            typed_relationships,
            issues,
        )
        self._validate_references(
            typed_submodels,
            typed_entities,
            typed_attributes,
            typed_relationships,
            issues,
        )
        return _NormalizedCandidate(
            submodels=typed_submodels,
            entities=typed_entities,
            attributes=typed_attributes,
            relationships=typed_relationships,
            issues=tuple(issues),
        )

    def _validate_entity_evidence(
        self,
        record: LogicalEntityRecord,
        *,
        index: int,
        issues: list[AgentValidationIssue],
    ) -> None:
        for source_index, source in enumerate(record.sources):
            if isinstance(source, LogicalObjectSourceRecord):
                valid = _physical_object_key(source.source_object) in self._selected_object_keys
                code = "candidate.source_outside_selection"
                message = "Physical Object source must belong to this immutable run selection."
            else:
                valid = (
                    normalize_model_key_value(source.assertion_record.modeling_assertion_record_key)
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

    def _validate_attribute_evidence(
        self,
        record: LogicalAttributeRecord,
        *,
        index: int,
        issues: list[AgentValidationIssue],
    ) -> None:
        for source_index, source in enumerate(record.sources):
            if isinstance(source, AttributePhysicalSourceRecord):
                valid = (
                    _physical_attribute_key(source.source_attribute)
                    in self._selected_attribute_keys
                )
                code = "candidate.source_outside_selection"
                message = "Physical Attribute source must belong to this immutable run selection."
            else:
                valid = (
                    normalize_model_key_value(source.assertion_record.modeling_assertion_record_key)
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

    def _validate_locks(
        self,
        submodels: tuple[LogicalSubmodelRecord, ...],
        entities: tuple[LogicalEntityRecord, ...],
        attributes: tuple[LogicalAttributeRecord, ...],
        relationships: tuple[LogicalRelationshipRecord, ...],
        issues: list[AgentValidationIssue],
    ) -> None:
        for index, record in enumerate(submodels):
            if (existing := self._applied_submodels.get(_submodel_key(record))) is not None:
                _append_locked_change_issues(
                    existing, record, path=("submodels", index), issues=issues
                )
        for index, record in enumerate(entities):
            if (existing := self._applied_entities.get(_entity_key(record))) is not None:
                _append_locked_change_issues(
                    existing, record, path=("entities", index), issues=issues
                )
        for index, record in enumerate(attributes):
            if (existing := self._applied_attributes.get(_attribute_key(record))) is not None:
                _append_locked_change_issues(
                    existing, record, path=("attributes", index), issues=issues
                )
        for index, record in enumerate(relationships):
            existing = self._applied_relationships.get(_relationship_key(record))
            if existing is not None:
                _append_locked_change_issues(
                    existing, record, path=("relationships", index), issues=issues
                )

    def _validate_references(
        self,
        submodels: tuple[LogicalSubmodelRecord, ...],
        entities: tuple[LogicalEntityRecord, ...],
        attributes: tuple[LogicalAttributeRecord, ...],
        relationships: tuple[LogicalRelationshipRecord, ...],
        issues: list[AgentValidationIssue],
    ) -> None:
        submodel_keys = set(self._applied_submodels)
        submodel_keys.update(_submodel_key(record) for record in submodels)
        entity_keys = set(self._applied_entities)
        entity_keys.update(_entity_key(record) for record in entities)
        attribute_keys = set(self._applied_attributes)
        attribute_keys.update(_attribute_key(record) for record in attributes)

        for index, entity in enumerate(entities):
            if any(
                normalize_model_key_value(membership.submodel_name) not in submodel_keys
                for membership in entity.submodels
            ):
                issues.append(
                    AgentValidationIssue(
                        code="candidate.submodel_missing",
                        path=("entities", index, "submodels"),
                        message="Every Logical Entity Submodel must exist.",
                    )
                )
        for index, attribute in enumerate(attributes):
            if normalize_model_key_value(attribute.logical_entity_name) not in entity_keys:
                issues.append(
                    AgentValidationIssue(
                        code="candidate.entity_missing",
                        path=("attributes", index, "logical_entity_name"),
                        message="Every Logical Attribute Entity must exist.",
                    )
                )
        for index, relationship in enumerate(relationships):
            endpoints = (
                (
                    normalize_model_key_value(relationship.from_logical_entity_name),
                    normalize_model_key_value(relationship.from_logical_attribute_name),
                ),
                (
                    normalize_model_key_value(relationship.to_logical_entity_name),
                    normalize_model_key_value(relationship.to_logical_attribute_name),
                ),
            )
            if any(endpoint not in attribute_keys for endpoint in endpoints):
                issues.append(
                    AgentValidationIssue(
                        code="candidate.relationship_endpoint_missing",
                        path=("relationships", index),
                        message="Both Logical Relationship endpoints must exist.",
                    )
                )


def _merge_submodel(
    record: LogicalSubmodelRecord,
    existing: LogicalSubmodelRecord | None,
) -> dict[str, object]:
    value = cast(dict[str, object], record.model_dump(mode="json"))
    value["logical_submodel_is_locked"] = (
        existing.logical_submodel_is_locked if existing is not None else False
    )
    return value


def _merge_entity(
    record: LogicalEntityRecord,
    existing: LogicalEntityRecord | None,
) -> dict[str, object]:
    value = cast(dict[str, object], record.model_dump(mode="json"))
    value["logical_entity_is_locked"] = (
        existing.logical_entity_is_locked if existing is not None else False
    )
    value["submodels"] = _merge_memberships(
        record.submodels,
        () if existing is None else existing.submodels,
    )
    value["sources"] = _merge_entity_sources(
        record.sources,
        () if existing is None else existing.sources,
    )
    return value


def _merge_attribute(
    record: LogicalAttributeRecord,
    existing: LogicalAttributeRecord | None,
) -> dict[str, object]:
    value = cast(dict[str, object], record.model_dump(mode="json"))
    value["logical_attribute_is_locked"] = (
        existing.logical_attribute_is_locked if existing is not None else False
    )
    value["sources"] = _merge_attribute_sources(
        record.sources,
        () if existing is None else existing.sources,
    )
    return value


def _merge_relationship(
    record: LogicalRelationshipRecord,
    existing: LogicalRelationshipRecord | None,
) -> dict[str, object]:
    value = cast(dict[str, object], record.model_dump(mode="json"))
    value["logical_relationship_is_locked"] = (
        existing.logical_relationship_is_locked if existing is not None else False
    )
    return value


def _merge_memberships(
    candidate: Sequence[SubmodelMembershipRecord],
    existing: Sequence[SubmodelMembershipRecord],
) -> list[dict[str, object]]:
    return _merge_nested(
        candidate,
        existing,
        key=_membership_key,
        lock_field="membership_is_locked",
    )


def _merge_entity_sources(
    candidate: Sequence[_EntitySource],
    existing: Sequence[_EntitySource],
) -> list[dict[str, object]]:
    return _merge_nested(candidate, existing, key=_entity_source_key, lock_field="is_locked")


def _merge_attribute_sources(
    candidate: Sequence[_AttributeSource],
    existing: Sequence[_AttributeSource],
) -> list[dict[str, object]]:
    return _merge_nested(
        candidate,
        existing,
        key=_attribute_source_key,
        lock_field="is_locked",
    )


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
        nested_key = key(applied_record)
        candidate_record = candidate_by_key.get(nested_key)
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


def _validate_entity_authority(
    record: LogicalEntityRecord,
    *,
    index: int,
    issues: list[AgentValidationIssue],
) -> None:
    if record.logical_entity_is_locked:
        _lock_forbidden(("entities", index), issues)
    for nested_index, membership in enumerate(record.submodels):
        if membership.membership_is_locked:
            _lock_forbidden(("entities", index, "submodels", nested_index), issues)
    for nested_index, source in enumerate(record.sources):
        if source.is_locked:
            _lock_forbidden(("entities", index, "sources", nested_index), issues)


def _validate_attribute_authority(
    record: LogicalAttributeRecord,
    *,
    index: int,
    issues: list[AgentValidationIssue],
) -> None:
    if record.logical_attribute_is_audit_column:
        issues.append(
            AgentValidationIssue(
                code="candidate.audit_column_forbidden",
                path=("attributes", index, "logical_attribute_is_audit_column"),
                message="Logical audit columns are projected deterministically.",
            )
        )
    if record.logical_attribute_is_locked:
        _lock_forbidden(("attributes", index), issues)
    for nested_index, source in enumerate(record.sources):
        if source.is_locked:
            _lock_forbidden(("attributes", index, "sources", nested_index), issues)


def _lock_forbidden(path: tuple[str | int, ...], issues: list[AgentValidationIssue]) -> None:
    issues.append(
        AgentValidationIssue(
            code="candidate.lock_forbidden",
            path=path,
            message="Only a user may change Logical lock state.",
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


def _record_locked(path: tuple[str | int, ...], issues: list[AgentValidationIssue]) -> None:
    issues.append(
        AgentValidationIssue(
            code="candidate.record_locked",
            path=path,
            message="A locked applied Logical record cannot be changed.",
        )
    )


def _top_lock(record: object) -> bool:
    if isinstance(record, LogicalSubmodelRecord):
        return record.logical_submodel_is_locked
    if isinstance(record, LogicalEntityRecord):
        return record.logical_entity_is_locked
    if isinstance(record, LogicalAttributeRecord):
        return record.logical_attribute_is_locked
    if isinstance(record, LogicalRelationshipRecord):
        return record.logical_relationship_is_locked
    raise TypeError("Unsupported Logical record")


def _model_issues(
    issues: tuple[ModelValidationIssue, ...],
) -> tuple[AgentValidationIssue, ...]:
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


def _submodel_key(record: LogicalSubmodelRecord) -> str:
    return normalize_model_key_value(record.logical_submodel_name)


def _entity_key(record: LogicalEntityRecord) -> str:
    return normalize_model_key_value(record.logical_entity_name)


def _attribute_key(record: LogicalAttributeRecord) -> tuple[str, str]:
    return (
        normalize_model_key_value(record.logical_entity_name),
        normalize_model_key_value(record.logical_attribute_name),
    )


def _relationship_key(record: LogicalRelationshipRecord) -> tuple[str, str, str, str, str]:
    return (
        normalize_model_key_value(record.from_logical_entity_name),
        normalize_model_key_value(record.from_logical_attribute_name),
        normalize_model_key_value(record.to_logical_entity_name),
        normalize_model_key_value(record.to_logical_attribute_name),
        normalize_model_key_value(record.logical_relationship_name),
    )


def _membership_key(record: SubmodelMembershipRecord) -> tuple[str, ...]:
    return (normalize_model_key_value(record.submodel_name),)


def _entity_source_key(record: _EntitySource) -> tuple[str, ...]:
    if isinstance(record, LogicalObjectSourceRecord):
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
    if isinstance(record, (LogicalObjectSourceRecord, LogicalAssertionSourceRecord)):
        return _entity_source_key(record)
    if isinstance(record, (AttributePhysicalSourceRecord, AttributeAssertionSourceRecord)):
        return _attribute_source_key(record)
    raise TypeError("Unsupported Logical nested source")


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


__all__ = ["LogicalCandidateValidator"]
