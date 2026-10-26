"""Normalize one non-deleting Dimensional agent candidate into canonical changes."""

from __future__ import annotations

import json
from collections.abc import Callable, Iterable, Sequence
from copy import deepcopy
from typing import Any, cast

from gds_etl_workbench.application.change_sets.project import StageProjectChange
from gds_etl_workbench.application.change_sets.project_validation import (
    validate_staged_records,
)
from gds_etl_workbench.domain.errors import InvalidRequestError
from gds_etl_workbench.domain.modeling_policy import GoldAuditPolicy, GoldTechnicalPolicy
from gds_etl_workbench.domain.modeling_records import (
    AttributeContextSourceRecord,
    AttributeLogicalSourceRecord,
    DimensionalAttributeRecord,
    DimensionalEntityRecord,
    DimensionalLogicalEntitySourceRecord,
    DimensionalRelationshipRecord,
    LogicalAttributeKey,
    LogicalContextSourceRecord,
    LogicalEntityKey,
    normalize_project_key_value,
)
from gds_etl_workbench.domain.snapshots.project import DimensionalSection
from pydantic import BaseModel, ConfigDict, Field, JsonValue, model_validator

from gds_workbench_api.features.dimensional.policy import (
    dimensional_policy_attribute_keys,
)
from gds_workbench_api.features.dimensional.policy import (
    dimensional_relationship_key as _relationship_key,
)
from gds_workbench_api.features.workflows.authoring.repair import (
    MAX_COVERAGE_SOURCE_REFS,
    AgentCandidateValidation,
    AgentValidationIssue,
    enrich_agent_output_project_definitions,
    parse_pydantic_candidate,
    project_validation_issues,
)

type _EntitySource = DimensionalLogicalEntitySourceRecord | LogicalContextSourceRecord
type _AttributeSource = AttributeLogicalSourceRecord | AttributeContextSourceRecord


class _DimensionalCandidate(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    entities: list[DimensionalEntityRecord] = Field(max_length=20_000)
    attributes: list[DimensionalAttributeRecord] = Field(max_length=20_000)
    relationships: list[DimensionalRelationshipRecord] = Field(max_length=20_000)

    @model_validator(mode="after")
    def validate_size(self) -> _DimensionalCandidate:
        # Every call returns only changes; empty arrays mean no change.
        count = len(self.entities) + len(self.attributes) + len(self.relationships)
        if count > 20_000:
            raise ValueError("Dimensional candidates must be bounded")
        return self


class _NormalizedCandidate(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    entities: tuple[DimensionalEntityRecord, ...]
    attributes: tuple[DimensionalAttributeRecord, ...]
    relationships: tuple[DimensionalRelationshipRecord, ...]
    issues: tuple[AgentValidationIssue, ...]


class DimensionalCandidateValidator:
    """Validate a complete agent proposal against one immutable Silver selection."""

    def __init__(
        self,
        *,
        selected_entity_keys: tuple[LogicalEntityKey, ...],
        selected_attribute_keys: tuple[LogicalAttributeKey, ...],
        context_record_ids: tuple[str, ...],
        applied: DimensionalSection | None,
        fact_types: tuple[str, ...] = (),
        coverage_threshold_percent: int = 60,
        raw_technical_template: dict[str, object] | None = None,
        raw_audit_template: dict[str, object] | None = None,
    ) -> None:
        if (
            type(coverage_threshold_percent) is not int
            or not 1 <= coverage_threshold_percent <= 100
        ):
            raise ValueError("Coverage threshold must be a whole number from 1 to 100")
        self._technical = (
            GoldTechnicalPolicy.model_validate_json(json.dumps(raw_technical_template))
            if raw_technical_template is not None
            else None
        )
        self._audit = (
            GoldAuditPolicy.model_validate_json(json.dumps(raw_audit_template))
            if raw_audit_template is not None
            else None
        )
        self._coverage_threshold_percent = coverage_threshold_percent
        if not selected_entity_keys or len(selected_entity_keys) > 50_000:
            raise ValueError("Dimensional Object selection must be bounded and nonempty")
        if len(selected_attribute_keys) > 50_000:
            raise ValueError("Dimensional Attribute selection must be bounded")
        self._selected_entity_keys = {
            _logical_entity_key(item): item for item in selected_entity_keys
        }
        self._selected_attribute_keys = {
            _logical_attribute_key(item) for item in selected_attribute_keys
        }
        self._context_record_ids = {
            normalize_project_key_value(item) for item in context_record_ids
        }
        if (
            len(self._selected_entity_keys) != len(selected_entity_keys)
            or len(self._selected_attribute_keys) != len(selected_attribute_keys)
            or len(self._context_record_ids) != len(context_record_ids)
        ):
            raise ValueError("Dimensional candidate evidence keys must be unique")

        self._applied = applied or DimensionalSection(entities=(), attributes=(), relationships=())
        # Active codes of reference.dimensional_fact_type, as frozen in the run's snapshot.
        self._fact_types = tuple(dict.fromkeys(fact_types))
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
                (len(self._applied_entities), len(self._applied.entities)),
                (len(self._applied_attributes), len(self._applied.attributes)),
                (len(self._applied_relationships), len(self._applied.relationships)),
            )
        ):
            raise ValueError("Applied Dimensional records must be unique")

    def output_schema(self) -> dict[str, JsonValue]:
        schema = cast(dict[str, JsonValue], deepcopy(_DimensionalCandidate.model_json_schema()))
        schema["description"] = (
            "Aim to cover all selected Logical Entities through active source mappings in the "
            "resulting Dimensional Model. "
            f"The backend coverage target is {self._coverage_threshold_percent}% of distinct "
            "Logical Entities selected for this run, rounded up, including unchanged applied "
            "records. Below this target, use repair feedback to improve supported coverage. "
            "Repair source_refs lists up to 50 missing input identities per attempt. "
            "Consolidation "
            "is allowed when supported by grain and business meaning. Do not return a sample "
            "or invent source mappings merely to claim coverage. Dimensional Attributes may "
            "select and aggregate relevant Logical Attributes for the analytical design.\n\n"
            "Coverage repair instructions:\n"
            "1. Read context.repair.validation_issues. The coverage message states the "
            "covered/selected count, required count and number of additional distinct inputs "
            "needed. At the default 60% target, 15/30 requires 3 more Logical Entities "
            "to reach 18/30, "
            "not 3 more output dimensions/facts and not necessarily all 15 missing inputs.\n"
            "2. Each source_refs entry is a missing selected Logical Entity's complete "
            "schema/name identity. Match it to the supplied Logical design, source evidence "
            "and analytical requirements; use enabled readers when needed. Check whether "
            "its support is absent, inactive, on an inactive Entity or attached to the wrong "
            "identity. The list is bounded and may be shortened further when "
            "source_refs_truncated is true; do not treat it as the entire selection.\n"
            "3. Where the evidence supports an existing or proposed dimension, fact or "
            "bridge's analytical role and grain, add or correct its entities[].sources "
            "entry with support_source_type 'logical_entity', the exact "
            "source_logical_entity identity and is_active true; its parent "
            "dimensional_entity_is_active must also be true. Otherwise create a separate "
            "well-supported Entity with its required Attributes and valid references. "
            "Preserve locks and deliberate inactive records; never reactivate them, merge "
            "incompatible grains or invent links merely to increase coverage.\n"
            "4. Preserve valid work from repair.previous_candidate. Attempts are not "
            "automatically accumulated: return the complete corrected candidate, not a "
            "patch containing only the missing inputs. Unchanged applied records need not "
            "be repeated. If previous_candidate_omitted is true, rebuild from the rendered "
            "evidence and enabled readers.\n"
            "5. Recount distinct selected Logical Entities across active proposed and "
            "retained support, and resolve every other validation issue. Repeated "
            "references, unselected sources, Context-only support and Attribute-only "
            "mappings do not increase Entity coverage. Keep unsupported gaps unresolved "
            "using existing definition/rationale fields where appropriate. Return only "
            "the candidate JSON; do not add a coverage report or new output fields."
        )
        _set_lock_fields_false(schema)
        enrich_agent_output_project_definitions(schema)
        entity_schema = cast(
            dict[str, Any], cast(dict[str, JsonValue], schema["$defs"])["DimensionalEntityRecord"]
        )
        entity_schema["properties"]["dimensional_fact_type"] = {
            "anyOf": [{"enum": list(self._fact_types)}, {"type": "null"}],
            "description": "An active fact type code for facts; null for dimensions and bridges.",
        }
        # The shared Change Set rule asks for technical and audit Attributes; this
        # workflow projects them.
        attribute_schema = cast(
            dict[str, JsonValue],
            cast(dict[str, JsonValue], schema["$defs"])["DimensionalAttributeRecord"],
        )
        attribute_schema["x-gds-population-rules"] = [
            "Author business Attributes only; the backend projects surrogate-key, "
            "foreign-key, Type 2 and audit Attributes from Project policy."
            if rule.startswith("Include every physical target Attribute")
            else rule
            for rule in cast(list[str], attribute_schema["x-gds-population-rules"])
        ]
        return schema

    async def validate(self, candidate: JsonValue) -> AgentCandidateValidation:
        return AgentCandidateValidation(issues=self._normalize(candidate).issues)

    def validate_coverage(self, candidate: JsonValue) -> tuple[AgentValidationIssue, ...]:
        normalized = self._normalize(candidate)
        if normalized.issues:
            return normalized.issues
        entities = {
            **self._applied_entities,
            **{_entity_key(record): record for record in normalized.entities},
        }
        return self.coverage_of(entities.values())

    def coverage_of(
        self, entities: Iterable[DimensionalEntityRecord]
    ) -> tuple[AgentValidationIssue, ...]:
        """Distinct selected Logical Entities with active support on active Entities."""
        covered = {
            _logical_entity_key(source.source_logical_entity)
            for record in entities
            if record.dimensional_entity_is_active
            for source in record.sources
            if isinstance(source, DimensionalLogicalEntitySourceRecord) and source.is_active
        }
        missing = self._selected_entity_keys.keys() - covered
        total = len(self._selected_entity_keys)
        covered_count = total - len(missing)
        required = (total * self._coverage_threshold_percent + 99) // 100
        if covered_count >= required:
            return ()
        return (
            AgentValidationIssue(
                code="candidate.entity_coverage_incomplete",
                path=("dimensional_entity",),
                message=(
                    f"Coverage {covered_count}/{total} "
                    f"is below {self._coverage_threshold_percent}%; at least {required} distinct "
                    f"selected Logical Entities are required ({required - covered_count} more). "
                    f"{len(missing)} of {total} selected Logical Entities lack active support."
                ),
                source_refs=tuple(
                    self._selected_entity_keys[key].model_dump(mode="json")
                    for key in sorted(missing)[:MAX_COVERAGE_SOURCE_REFS]
                ),
            ),
        )

    def parse_validated(self, candidate: JsonValue) -> tuple[StageProjectChange, ...]:
        normalized = self._normalize(candidate)
        if normalized.issues:
            raise InvalidRequestError("The Dimensional candidate is invalid.")

        entities = {_entity_key(record): record for record in normalized.entities}
        attributes = {_attribute_key(record): record for record in normalized.attributes}
        relationships = {_relationship_key(record): record for record in normalized.relationships}
        # Retiring a saved Entity retires its unlocked saved Attributes, and retiring an
        # Attribute retires the saved Relationships that use it, as Logical retire does.
        retired_entities = {
            key for key, record in entities.items() if not record.dimensional_entity_is_active
        }
        for key, record in self._applied_attributes.items():
            if (
                key[:2] in retired_entities
                and key not in attributes
                and record.dimensional_attribute_is_active
                and not record.dimensional_attribute_is_locked
            ):
                attributes[key] = record.model_copy(
                    update={"dimensional_attribute_is_active": False}
                )
        retired_attributes = {
            key for key, record in attributes.items() if not record.dimensional_attribute_is_active
        }
        for key, record in self._applied_relationships.items():
            if (
                key not in relationships
                and record.dimensional_relationship_is_active
                and not record.dimensional_relationship_is_locked
                and {_endpoint(record, "from"), _endpoint(record, "to")} & retired_attributes
            ):
                relationships[key] = record.model_copy(
                    update={"dimensional_relationship_is_active": False}
                )
        # A saved Fact or Bridge edge starts at its projected foreign key; retiring the edge
        # retires that key too.
        effective_entities = {**self._applied_entities, **entities}
        for key, record in relationships.items():
            saved = self._applied_relationships.get(key)
            from_key = _endpoint(record, "from")
            child = effective_entities.get(from_key[:2])
            foreign_key = attributes.get(from_key) or self._applied_attributes.get(from_key)
            if (
                saved is not None
                and saved.dimensional_relationship_is_active
                and not record.dimensional_relationship_is_active
                and child is not None
                and child.dimensional_entity_type in ("fact", "bridge")
                and foreign_key is not None
                and foreign_key.dimensional_attribute_is_active
                and not foreign_key.dimensional_attribute_is_locked
            ):
                attributes[from_key] = foreign_key.model_copy(
                    update={"dimensional_attribute_is_active": False}
                )

        changes: list[StageProjectChange] = []
        changed_entities = [
            record.model_dump(mode="json")
            for record in entities.values()
            if self._applied_entities.get(_entity_key(record)) != record
        ]
        changed_attributes = [
            record.model_dump(mode="json")
            for record in attributes.values()
            if self._applied_attributes.get(_attribute_key(record)) != record
        ]
        changed_relationships = [
            record.model_dump(mode="json")
            for record in relationships.values()
            if self._applied_relationships.get(_relationship_key(record)) != record
        ]
        if changed_entities:
            changes.append(
                StageProjectChange(dataset="dimensional_entity", records=changed_entities)
            )
        if changed_attributes:
            changes.append(
                StageProjectChange(dataset="dimensional_attribute", records=changed_attributes)
            )
        if changed_relationships:
            changes.append(
                StageProjectChange(
                    dataset="dimensional_relationship",
                    records=changed_relationships,
                )
            )
        return tuple(changes)

    def _normalize(self, candidate: JsonValue) -> _NormalizedCandidate:
        parsed, parse_issues = parse_pydantic_candidate(_DimensionalCandidate, candidate)
        if parsed is None:
            return _NormalizedCandidate(
                entities=(),
                attributes=(),
                relationships=(),
                issues=parse_issues,
            )

        issues: list[AgentValidationIssue] = []
        raw_entities: list[dict[str, object]] = []
        for index, entity in enumerate(parsed.entities):
            existing = self._applied_entities.get(_entity_key(entity))
            merged = _merge_entity(entity, existing)
            unchanged_applied = existing is not None and merged == existing.model_dump(mode="json")
            raw_entities.append(merged)
            if entity.dimensional_entity_is_locked:
                _lock_forbidden(("entities", index), issues)
            if (
                entity.dimensional_fact_type is not None
                and entity.dimensional_fact_type not in self._fact_types
            ):
                issues.append(
                    AgentValidationIssue(
                        code="candidate.fact_type_unknown",
                        path=("entities", index, "dimensional_fact_type"),
                        message="Use an active code from dimensional_fact_types.",
                    )
                )
            for source_index, source in enumerate(entity.sources):
                if source.is_locked:
                    _lock_forbidden(("entities", index, "sources", source_index), issues)
                if isinstance(source, DimensionalLogicalEntitySourceRecord):
                    valid = (
                        unchanged_applied
                        or _logical_entity_key(source.source_logical_entity)
                        in self._selected_entity_keys
                    )
                    code = "candidate.source_outside_selection"
                    message = "Logical Entity source must belong to this immutable run selection."
                else:
                    valid = (
                        normalize_project_key_value(source.context_record.context_record_id)
                        in self._context_record_ids
                    )
                    code = "candidate.context_unavailable"
                    message = "Context source must exist in this immutable run context."
                if not valid:
                    issues.append(
                        AgentValidationIssue(
                            code=code,
                            path=("entities", index, "sources", source_index),
                            message=message,
                        )
                    )
        effective_entities = {
            **self._applied_entities,
            **{_entity_key(record): record for record in parsed.entities},
        }
        effective_relationships = {
            **self._applied_relationships,
            **{_relationship_key(record): record for record in parsed.relationships},
        }
        reserved_keys: set[tuple[str, str, str]] = (
            dimensional_policy_attribute_keys(
                entities=tuple(effective_entities.values()),
                relationships=tuple(effective_relationships.values()),
                applied=self._applied,
                technical=self._technical,
                audit=self._audit,
            )
            if self._technical is not None
            else set()
        )
        raw_attributes: list[dict[str, object]] = []
        for index, attribute in enumerate(parsed.attributes):
            existing = self._applied_attributes.get(_attribute_key(attribute))
            merged = _merge_attribute(attribute, existing)
            unchanged_applied = existing is not None and merged == existing.model_dump(mode="json")
            raw_attributes.append(merged)
            if (
                _attribute_key(attribute) in reserved_keys
                or attribute.dimensional_attribute_is_surrogate_key
                or attribute.dimensional_attribute_is_audit_column
            ):
                issues.append(
                    AgentValidationIssue(
                        code="candidate.policy_column_forbidden",
                        path=("attributes", index, "dimensional_attribute_name"),
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
                if isinstance(source, AttributeLogicalSourceRecord):
                    valid = (
                        unchanged_applied
                        or _logical_attribute_key(source.source_logical_attribute)
                        in self._selected_attribute_keys
                    )
                    code = "candidate.source_outside_selection"
                    message = (
                        "Logical Attribute source must belong to this immutable run selection."
                    )
                else:
                    valid = (
                        normalize_project_key_value(source.context_record.context_record_id)
                        in self._context_record_ids
                    )
                    code = "candidate.context_unavailable"
                    message = "Context source must exist in this immutable run context."
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

        entities, entity_issues = validate_staged_records(
            "dimensional_entity",
            raw_entities,
        )
        attributes, attribute_issues = validate_staged_records(
            "dimensional_attribute",
            raw_attributes,
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
        typed_entities = cast(tuple[DimensionalEntityRecord, ...], entities)
        typed_attributes = cast(tuple[DimensionalAttributeRecord, ...], attributes)
        typed_relationships = cast(tuple[DimensionalRelationshipRecord, ...], relationships)
        issues.extend(
            project_validation_issues(entity_issues + attribute_issues + relationship_issues)
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

        entity_keys = set(self._applied_entities)
        entity_keys.update(_entity_key(record) for record in typed_entities)
        attribute_keys = set(self._applied_attributes)
        attribute_keys.update(_attribute_key(record) for record in typed_attributes)
        for index, attribute in enumerate(typed_attributes):
            if (
                normalize_project_key_value(attribute.dimensional_entity_schema_name),
                normalize_project_key_value(attribute.dimensional_entity_name),
            ) not in entity_keys:
                issues.append(
                    AgentValidationIssue(
                        code="candidate.entity_missing",
                        path=("attributes", index, "dimensional_entity_name"),
                        message="Every Dimensional Attribute Entity must exist.",
                    )
                )
        for index, relationship in enumerate(typed_relationships):
            endpoints = (_endpoint(relationship, "from"), _endpoint(relationship, "to"))
            if any(endpoint not in attribute_keys for endpoint in endpoints):
                issues.append(
                    AgentValidationIssue(
                        code="candidate.relationship_endpoint_missing",
                        path=("relationships", index),
                        message="Both Dimensional Relationship endpoints must exist.",
                    )
                )
        return _NormalizedCandidate(
            entities=typed_entities,
            attributes=typed_attributes,
            relationships=typed_relationships,
            issues=tuple(issues),
        )


def _merge_entity(
    record: DimensionalEntityRecord,
    existing: DimensionalEntityRecord | None,
) -> dict[str, object]:
    value = cast(dict[str, object], record.model_dump(mode="json"))
    value["dimensional_entity_is_locked"] = (
        existing.dimensional_entity_is_locked if existing is not None else False
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
    for field_name, key_function, lock_field in (("sources", _nested_source_key, "is_locked"),):
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


def _entity_key(record: DimensionalEntityRecord) -> tuple[str, str]:
    return (
        normalize_project_key_value(record.dimensional_entity_schema_name),
        normalize_project_key_value(record.dimensional_entity_name),
    )


def _attribute_key(record: DimensionalAttributeRecord) -> tuple[str, str, str]:
    return (
        normalize_project_key_value(record.dimensional_entity_schema_name),
        normalize_project_key_value(record.dimensional_entity_name),
        normalize_project_key_value(record.dimensional_attribute_name),
    )


def _endpoint(record: DimensionalRelationshipRecord, side: str) -> tuple[str, str, str]:
    return (
        normalize_project_key_value(getattr(record, f"{side}_dimensional_entity_schema_name")),
        normalize_project_key_value(getattr(record, f"{side}_dimensional_entity_name")),
        normalize_project_key_value(getattr(record, f"{side}_dimensional_attribute_name")),
    )


def _entity_source_key(record: _EntitySource) -> tuple[str, ...]:
    if isinstance(record, DimensionalLogicalEntitySourceRecord):
        return ("logical_entity", *_logical_entity_key(record.source_logical_entity))
    return (
        "context_record",
        normalize_project_key_value(record.context_record.context_record_id),
    )


def _attribute_source_key(record: _AttributeSource) -> tuple[str, ...]:
    if isinstance(record, AttributeLogicalSourceRecord):
        return ("logical_attribute", *_logical_attribute_key(record.source_logical_attribute))
    return (
        "context_record",
        normalize_project_key_value(record.context_record.context_record_id),
    )


def _nested_source_key(record: object) -> tuple[str, ...]:
    if isinstance(record, (DimensionalLogicalEntitySourceRecord, LogicalContextSourceRecord)):
        return _entity_source_key(record)
    if isinstance(record, (AttributeLogicalSourceRecord, AttributeContextSourceRecord)):
        return _attribute_source_key(record)
    raise TypeError("Unsupported Dimensional nested source")


def _logical_entity_key(record: LogicalEntityKey) -> tuple[str, str]:
    return (
        normalize_project_key_value(record.logical_entity_schema_name),
        normalize_project_key_value(record.logical_entity_name),
    )


def _logical_attribute_key(record: LogicalAttributeKey) -> tuple[str, str, str]:
    return (
        *_logical_entity_key(record),
        normalize_project_key_value(record.logical_attribute_name),
    )


__all__ = ["DimensionalCandidateValidator"]
