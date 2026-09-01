"""Normalize one non-deleting Conceptual agent candidate into canonical changes."""

from __future__ import annotations

from collections.abc import Sequence
from copy import deepcopy
from typing import cast

from gds_etl_workbench.domain.errors import InvalidRequestError
from gds_etl_workbench.domain.modeling_records import (
    ConceptualObjectRecord,
    ConceptualRelationshipRecord,
    ObjectSupportRecord,
    PhysicalObjectKey,
    SupportRecord,
    normalize_model_key_value,
)
from gds_etl_workbench.tools.change_sets.model import StageModelChange
from gds_etl_workbench.tools.change_sets.model_validation import (
    ModelValidationIssue,
    validate_staged_records,
)
from gds_etl_workbench.tools.snapshots.model.contracts import ConceptualSection
from pydantic import BaseModel, ConfigDict, Field, JsonValue, model_validator

from gds_workbench_api.features.workflows.authoring.repair import (
    AgentCandidateValidation,
    AgentValidationIssue,
    enrich_agent_output_model_definitions,
    parse_pydantic_candidate,
)


class _ConceptualCandidate(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    objects: list[ConceptualObjectRecord] = Field(max_length=20_000)
    relationships: list[ConceptualRelationshipRecord] = Field(max_length=20_000)

    @model_validator(mode="after")
    def validate_size(self) -> _ConceptualCandidate:
        count = len(self.objects) + len(self.relationships)
        if count > 20_000:
            raise ValueError("Conceptual candidates must be bounded")
        return self


class _NormalizedCandidate(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    objects: tuple[ConceptualObjectRecord, ...]
    relationships: tuple[ConceptualRelationshipRecord, ...]
    issues: tuple[AgentValidationIssue, ...]


class ConceptualCandidateValidator:
    """Enforce selection, locks, references, and omission-is-not-delete semantics."""

    def __init__(
        self,
        *,
        selected_object_keys: tuple[PhysicalObjectKey, ...],
        assertion_record_keys: tuple[str, ...],
        applied: ConceptualSection | None,
    ) -> None:
        if not selected_object_keys or len(selected_object_keys) > 50_000:
            raise ValueError("Conceptual selection must be bounded and nonempty")
        selected = {_physical_key(item) for item in selected_object_keys}
        assertions = {normalize_model_key_value(item) for item in assertion_record_keys}
        if len(selected) != len(selected_object_keys) or len(assertions) != len(
            assertion_record_keys
        ):
            raise ValueError("Conceptual candidate evidence keys must be unique")
        self._selected_object_keys = selected
        self._assertion_record_keys = assertions
        self._applied = applied or ConceptualSection(objects=(), relationships=())
        self._applied_objects = {_object_key(record): record for record in self._applied.objects}
        self._applied_relationships = {
            _relationship_key(record): record for record in self._applied.relationships
        }
        if len(self._applied_objects) != len(self._applied.objects) or len(
            self._applied_relationships
        ) != len(self._applied.relationships):
            raise ValueError("Applied Conceptual records must be unique")

    def output_schema(self) -> dict[str, JsonValue]:
        schema = cast(dict[str, JsonValue], deepcopy(_ConceptualCandidate.model_json_schema()))
        _set_lock_fields_false(schema)
        enrich_agent_output_model_definitions(schema)
        return schema

    async def validate(self, candidate: JsonValue) -> AgentCandidateValidation:
        return AgentCandidateValidation(issues=self._normalize(candidate).issues)

    def parse_validated(self, candidate: JsonValue) -> tuple[StageModelChange, ...]:
        normalized = self._normalize(candidate)
        if normalized.issues:
            raise InvalidRequestError("The Conceptual candidate is invalid.")

        changed_objects = [
            record.model_dump(mode="json")
            for record in normalized.objects
            if self._applied_objects.get(_object_key(record)) != record
        ]
        changed_relationships = [
            record.model_dump(mode="json")
            for record in normalized.relationships
            if self._applied_relationships.get(_relationship_key(record)) != record
        ]
        changes: list[StageModelChange] = []
        if changed_objects:
            changes.append(
                StageModelChange(
                    dataset="conceptual_object",
                    records=changed_objects,
                )
            )
        if changed_relationships:
            changes.append(
                StageModelChange(
                    dataset="conceptual_relationship",
                    records=changed_relationships,
                )
            )
        return tuple(changes)

    def _normalize(self, candidate: JsonValue) -> _NormalizedCandidate:
        parsed, parse_issues = parse_pydantic_candidate(_ConceptualCandidate, candidate)
        if parsed is None:
            return _NormalizedCandidate(
                objects=(),
                relationships=(),
                issues=parse_issues,
            )

        issues: list[AgentValidationIssue] = []
        raw_objects: list[dict[str, object]] = []
        for index, record in enumerate(parsed.objects):
            self._validate_agent_authority(
                record,
                path=("objects", index),
                issues=issues,
            )
            self._validate_agent_evidence(
                record.supports,
                path=("objects", index, "supports"),
                issues=issues,
            )
            existing = self._applied_objects.get(_object_key(record))
            raw_objects.append(_merge_object(record, existing))

        raw_relationships: list[dict[str, object]] = []
        for index, record in enumerate(parsed.relationships):
            self._validate_agent_authority(
                record,
                path=("relationships", index),
                issues=issues,
            )
            self._validate_agent_evidence(
                record.supports,
                path=("relationships", index, "supports"),
                issues=issues,
            )
            existing = self._applied_relationships.get(_relationship_key(record))
            raw_relationships.append(_merge_relationship(record, existing))

        object_records, object_issues = validate_staged_records(
            "conceptual_object",
            raw_objects,
        )
        relationship_records, relationship_issues = validate_staged_records(
            "conceptual_relationship",
            raw_relationships,
        )
        issues.extend(_model_issues(object_issues + relationship_issues))
        objects = cast(tuple[ConceptualObjectRecord, ...], object_records)
        relationships = cast(
            tuple[ConceptualRelationshipRecord, ...],
            relationship_records,
        )

        self._validate_locks(objects, relationships, issues)
        effective_object_keys = set(self._applied_objects)
        effective_object_keys.update(_object_key(record) for record in objects)
        for index, relationship in enumerate(relationships):
            if (
                normalize_model_key_value(relationship.from_conceptual_object_name)
                not in effective_object_keys
                or normalize_model_key_value(relationship.to_conceptual_object_name)
                not in effective_object_keys
            ):
                issues.append(
                    AgentValidationIssue(
                        code="candidate.relationship_endpoint_missing",
                        path=("relationships", index),
                        message="Both Conceptual Relationship endpoints must exist.",
                    )
                )

        return _NormalizedCandidate(
            objects=objects,
            relationships=relationships,
            issues=tuple(issues),
        )

    def _validate_agent_authority(
        self,
        record: ConceptualObjectRecord | ConceptualRelationshipRecord,
        *,
        path: tuple[str | int, ...],
        issues: list[AgentValidationIssue],
    ) -> None:
        top_locked = (
            record.conceptual_object_is_locked
            if isinstance(record, ConceptualObjectRecord)
            else record.conceptual_relationship_is_locked
        )
        if top_locked:
            issues.append(
                AgentValidationIssue(
                    code="candidate.lock_forbidden",
                    path=path,
                    message="Only a user may change Conceptual lock state.",
                )
            )
        for support_index, support in enumerate(record.supports):
            if support.support_is_locked:
                issues.append(
                    AgentValidationIssue(
                        code="candidate.lock_forbidden",
                        path=path + ("supports", support_index),
                        message="Only a user may change Conceptual lock state.",
                    )
                )

    def _validate_agent_evidence(
        self,
        supports: Sequence[SupportRecord],
        *,
        path: tuple[str | int, ...],
        issues: list[AgentValidationIssue],
    ) -> None:
        for index, support in enumerate(supports):
            if isinstance(support, ObjectSupportRecord):
                valid = _physical_key(support.source_object) in self._selected_object_keys
                code = "candidate.support_outside_selection"
                message = "Physical support must belong to this immutable run selection."
            else:
                valid = (
                    normalize_model_key_value(
                        support.assertion_record.modeling_assertion_record_key
                    )
                    in self._assertion_record_keys
                )
                code = "candidate.assertion_unavailable"
                message = "Assertion support must exist in this immutable run context."
            if not valid:
                issues.append(
                    AgentValidationIssue(
                        code=code,
                        path=path + (index,),
                        message=message,
                    )
                )

    def _validate_locks(
        self,
        objects: tuple[ConceptualObjectRecord, ...],
        relationships: tuple[ConceptualRelationshipRecord, ...],
        issues: list[AgentValidationIssue],
    ) -> None:
        for index, record in enumerate(objects):
            existing = self._applied_objects.get(_object_key(record))
            if existing is not None:
                _append_locked_change_issues(
                    existing,
                    record,
                    path=("objects", index),
                    issues=issues,
                )
        for index, record in enumerate(relationships):
            existing = self._applied_relationships.get(_relationship_key(record))
            if existing is not None:
                _append_locked_change_issues(
                    existing,
                    record,
                    path=("relationships", index),
                    issues=issues,
                )


def _merge_object(
    record: ConceptualObjectRecord,
    existing: ConceptualObjectRecord | None,
) -> dict[str, object]:
    merged = cast(dict[str, object], record.model_dump(mode="json"))
    merged["conceptual_object_is_locked"] = (
        existing.conceptual_object_is_locked if existing is not None else False
    )
    merged["supports"] = _merge_supports(
        record.supports,
        () if existing is None else existing.supports,
    )
    return merged


def _merge_relationship(
    record: ConceptualRelationshipRecord,
    existing: ConceptualRelationshipRecord | None,
) -> dict[str, object]:
    merged = cast(dict[str, object], record.model_dump(mode="json"))
    merged["conceptual_relationship_is_locked"] = (
        existing.conceptual_relationship_is_locked if existing is not None else False
    )
    merged["supports"] = _merge_supports(
        record.supports,
        () if existing is None else existing.supports,
    )
    return merged


def _merge_supports(
    candidate: Sequence[SupportRecord],
    existing: Sequence[SupportRecord],
) -> list[dict[str, object]]:
    candidate_by_key = {_support_key(item): item for item in candidate}
    existing_by_key = {_support_key(item): item for item in existing}
    merged: list[dict[str, object]] = []
    for applied_support in existing:
        key = _support_key(applied_support)
        candidate_support = candidate_by_key.get(key)
        if candidate_support is None:
            merged.append(cast(dict[str, object], applied_support.model_dump(mode="json")))
            continue
        value = cast(dict[str, object], candidate_support.model_dump(mode="json"))
        value["support_is_locked"] = applied_support.support_is_locked
        merged.append(value)
    for candidate_support in candidate:
        if _support_key(candidate_support) in existing_by_key:
            continue
        value = cast(dict[str, object], candidate_support.model_dump(mode="json"))
        value["support_is_locked"] = False
        merged.append(value)
    return merged


def _append_locked_change_issues(
    existing: ConceptualObjectRecord | ConceptualRelationshipRecord,
    changed: ConceptualObjectRecord | ConceptualRelationshipRecord,
    *,
    path: tuple[str | int, ...],
    issues: list[AgentValidationIssue],
) -> None:
    top_locked = (
        existing.conceptual_object_is_locked
        if isinstance(existing, ConceptualObjectRecord)
        else existing.conceptual_relationship_is_locked
    )
    if top_locked and existing != changed:
        issues.append(
            AgentValidationIssue(
                code="candidate.record_locked",
                path=path,
                message="A locked applied Conceptual record cannot be changed.",
            )
        )
        return
    changed_supports = {_support_key(item): item for item in changed.supports}
    for support_index, applied_support in enumerate(existing.supports):
        candidate_support = changed_supports.get(_support_key(applied_support))
        if (
            applied_support.support_is_locked
            and candidate_support is not None
            and applied_support != candidate_support
        ):
            issues.append(
                AgentValidationIssue(
                    code="candidate.record_locked",
                    path=path + ("supports", support_index),
                    message="A locked applied Conceptual support cannot be changed.",
                )
            )


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


def _object_key(record: ConceptualObjectRecord) -> str:
    return normalize_model_key_value(record.conceptual_object_name)


def _relationship_key(record: ConceptualRelationshipRecord) -> tuple[str, str, str]:
    return (
        normalize_model_key_value(record.from_conceptual_object_name),
        normalize_model_key_value(record.to_conceptual_object_name),
        normalize_model_key_value(record.conceptual_relationship_name),
    )


def _support_key(record: SupportRecord) -> tuple[str, ...]:
    if isinstance(record, ObjectSupportRecord):
        return ("object", *_physical_key(record.source_object))
    return (
        "assertion",
        normalize_model_key_value(record.assertion_record.modeling_assertion_record_key),
    )


def _physical_key(record: PhysicalObjectKey) -> tuple[str, str, str, str, str]:
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
            if isinstance(property_schema, dict) and name.endswith("_is_locked"):
                property_schema["const"] = False
    for child in value.values():
        _set_lock_fields_false(child)


__all__ = ["ConceptualCandidateValidator"]
