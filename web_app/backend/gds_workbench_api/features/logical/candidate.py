"""Expand one compact Logical agent answer into canonical non-deleting changes.

The agent writes judgment calls only, citing tables by the short ids of table_index (``t1``)
and columns as ``t1.column``. The backend expands that answer into complete Logical
records: physical keys, generated keys, column and dependency order, defaults and saved
values. The expanded records then pass the same selection, lock and reference checks as
any Logical change, and every issue is reported at the agent's own path.
"""

from __future__ import annotations

import re
from collections.abc import Callable, Iterable, Mapping, Sequence
from copy import deepcopy
from dataclasses import dataclass, field
from typing import Annotated, Literal, cast

from gds_etl_workbench.application.change_sets.project import StageProjectChange
from gds_etl_workbench.application.change_sets.project_validation import (
    ProjectValidationIssue,
    validate_staged_records,
)
from gds_etl_workbench.domain.errors import InvalidRequestError
from gds_etl_workbench.domain.modeling_records import (
    AttributeContextSourceRecord,
    AttributePhysicalSourceRecord,
    Code100,
    ContextRecordId,
    LogicalAttributeRecord,
    LogicalContextSourceRecord,
    LogicalEntityRecord,
    LogicalObjectSourceRecord,
    LogicalRelationshipRecord,
    Name400,
    NonblankText,
    PhysicalAttributeKey,
    PhysicalObjectKey,
    normalize_project_key_value,
)
from gds_etl_workbench.domain.snapshots.project import LogicalSection, ProjectChangeSetDataset
from pydantic import BaseModel, ConfigDict, Field, JsonValue, StringConstraints, model_validator

from gds_workbench_api.features.workflows.authoring.repair import (
    MAX_COVERAGE_SOURCE_REFS,
    AgentCandidateValidation,
    AgentValidationIssue,
    parse_pydantic_candidate,
    project_validation_issues,
)

type _EntitySource = LogicalObjectSourceRecord | LogicalContextSourceRecord
type _AttributeSource = AttributePhysicalSourceRecord | AttributeContextSourceRecord
type _Path = tuple[str | int, ...]
type _Key = tuple[str, ...]

_MAX_ITEMS = 20_000
_CONTEXT_ID = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$")

# ---------------------------------------------------------------------------
# What the agent writes.
# ---------------------------------------------------------------------------
_TableId = Annotated[
    str,
    StringConstraints(pattern=r"^t[1-9][0-9]{0,5}$"),
    Field(description="A table id from table_index, such as t1."),
]
_ColumnRef = Annotated[
    str,
    StringConstraints(max_length=420, pattern=r"^t[1-9][0-9]{0,5}\.\S"),
    Field(description="A table id, a dot, then the exact column name: t1.order_no."),
]
_Name = Annotated[str, StringConstraints(min_length=1, max_length=255, pattern=r"\S")]
_Note = NonblankText
_NOTE = (
    "Short reason, only when the value is not a straight copy: a filter, lookup, derivation "
    "or combination of sources."
)
# Mirrors LogicalEntityRecord.logical_entity_type.
_EntityType = Literal[
    "core",
    "reference",
    "transaction",
    "event",
    "bridge",
    "history",
    "snapshot",
    "association",
    "aggregate",
    "other",
]


class _Compact(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)


class _TableSource(_Compact):
    table: _TableId
    note: _Note | None = Field(default=None, description=_NOTE)


class _ColumnSource(_Compact):
    column: _ColumnRef
    note: _Note | None = Field(default=None, description=_NOTE)


class _ContextSource(_Compact):
    context: ContextRecordId = Field(description="A context_record_id from context_records.")
    note: _Note | None = Field(default=None, description=_NOTE)


type _EntitySourceRef = _TableId | _TableSource | _ContextSource
type _AttributeSourceRef = _ColumnRef | _ColumnSource | _ContextSource


class _CompactAttribute(_Compact):
    name: _Name = Field(description="Business name, following naming_instructions.")
    type: Code100 | None = Field(
        default=None,
        description="Databricks SQL type. Required for a new Attribute; omit to keep a saved one.",
    )
    nullable: bool | None = Field(
        default=None,
        description=(
            "Required for a new Attribute that is not a natural key; omit to keep a saved "
            "value. Natural keys are never nullable."
        ),
    )
    natural_key: bool | None = Field(
        default=None,
        description="True for every part of the business key. Omitted: false, or the saved value.",
    )
    from_: (
        _ColumnRef
        | _ColumnSource
        | _ContextSource
        | Annotated[
            tuple[_ColumnRef | _ColumnSource | _ContextSource, ...],
            Field(min_length=1, max_length=100),
        ]
        | None
    ) = Field(
        default=None,
        alias="from",
        description=(
            "Source column(s) or Context record. Omit only for a derived value whose rule the "
            "definition states."
        ),
    )
    definition: NonblankText | None = Field(
        default=None,
        description=(
            "Omit to use the single source column's Project description. Required when there "
            "is no single source column or it has no description."
        ),
    )
    note: _Note | None = Field(default=None, description=_NOTE)


class _CompactEntity(_Compact):
    schema_: Name400 = Field(alias="schema", description="One schema_name from schemas.")
    name: _Name = Field(description="Singular Entity name, following naming_instructions.")
    type: _EntityType | None = Field(
        default=None, description="Required for a new Entity; omit to keep a saved one."
    )
    type_detail: NonblankText | None = Field(
        default=None, description="Required only when type is other."
    )
    definition: NonblankText | None = Field(
        default=None,
        description="What one row is, then what it means. Required for a new Entity.",
    )
    grain: NonblankText | None = Field(
        default=None,
        description="One row per ...: the complete business identity. Required for a new Entity.",
    )
    sources: tuple[_TableId | _TableSource | _ContextSource, ...] = Field(
        default=(),
        max_length=1_000,
        description="Tables or Context records this Entity is built from; saved ones are kept.",
    )
    attributes: tuple[_CompactAttribute, ...] = Field(
        default=(),
        max_length=_MAX_ITEMS,
        description=(
            "Business Attributes in column order. List only new or changed ones; saved ones are "
            "kept. Never list the generated <Entity>ID key or audit columns."
        ),
    )


class _EntityRef(_Compact):
    schema_: Name400 = Field(alias="schema", description="The Entity's schema.")
    entity: _Name = Field(description="The Entity's name.")


class _AttributeRef(_EntityRef):
    attribute: _Name = Field(description="The foreign-key Attribute of the child Entity.")


class _CompactRelationship(_Compact):
    from_: _AttributeRef = Field(
        alias="from", description="The child Entity and its foreign-key Attribute."
    )
    to: _EntityRef = Field(description="The parent Entity; the backend references its key.")
    cardinality: Literal["many_to_one", "one_to_one"] = Field(
        description="many_to_one, or one_to_one only when business meaning makes the foreign "
        "key unique."
    )
    basis: NonblankText = Field(
        description="Why the link and its cardinality hold, citing Analysis or Context."
    )


class _Retirement(_Compact):
    schema_: Name400 = Field(alias="schema", description="Schema of the saved Entity.")
    entity: _Name = Field(description="The saved Entity, retired alone when nothing else is set.")
    attribute: _Name | None = Field(
        default=None, description="A saved Attribute of the Entity, retired with its links."
    )
    to: _EntityRef | None = Field(
        default=None,
        description="With attribute: retire the Relationship from that Attribute to this parent.",
    )
    source: (
        Annotated[str, StringConstraints(min_length=1, max_length=420, pattern=r"\S")] | None
    ) = Field(
        default=None,
        description=(
            "Retire one source: a table id (t1) of the Entity, a column (t1.code) of the "
            "Attribute, or a context_record_id."
        ),
    )

    @model_validator(mode="after")
    def validate_target(self) -> _Retirement:
        if self.to is not None and (self.attribute is None or self.source is not None):
            raise ValueError("A Relationship retirement names its Attribute and parent only.")
        return self


class _CompactLogicalCandidate(_Compact):
    entities: tuple[_CompactEntity, ...] = Field(
        max_length=_MAX_ITEMS,
        description="New Entities, and saved Entities to change: identity plus changed fields.",
    )
    relationships: tuple[_CompactRelationship, ...] = Field(
        max_length=_MAX_ITEMS,
        description="New or changed Relationships, each from a child foreign key to a parent.",
    )
    retire: tuple[_Retirement, ...] = Field(
        max_length=_MAX_ITEMS,
        description=(
            "Saved records to mark inactive. Nothing is deleted. Retiring an Entity also "
            "retires its Attributes and Relationships; retiring an Attribute retires its "
            "Relationships."
        ),
    )

    @model_validator(mode="after")
    def validate_size(self) -> _CompactLogicalCandidate:
        count = (
            len(self.entities)
            + sum(len(entity.attributes) for entity in self.entities)
            + len(self.relationships)
            + len(self.retire)
        )
        if count > _MAX_ITEMS:
            raise ValueError("Logical candidates must be bounded")
        return self


# ---------------------------------------------------------------------------
# What the backend validates and stages.
# ---------------------------------------------------------------------------
class _LogicalCandidate(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    entities: list[LogicalEntityRecord] = Field(max_length=50_000)
    attributes: list[LogicalAttributeRecord] = Field(max_length=100_000)
    relationships: list[LogicalRelationshipRecord] = Field(max_length=50_000)


@dataclass(slots=True)
class _Draft:
    """Expanded records by dataset and identity, each with the agent path it came from."""

    records: dict[str, dict[_Key, dict[str, object]]] = field(
        default_factory=lambda: {name: {} for name in _ARRAYS}
    )
    paths: dict[tuple[str, _Key], _Path] = field(default_factory=dict[tuple[str, _Key], _Path])
    source_paths: dict[tuple[str, _Key], list[_Path]] = field(
        default_factory=dict[tuple[str, _Key], list[_Path]]
    )
    listed_entities: set[_Key] = field(default_factory=set[_Key])
    # Listed Entities already reported; references to them add no second issue.
    rejected_entities: set[_Key] = field(default_factory=set[_Key])
    listed_endpoints: set[_Key] = field(default_factory=set[_Key])
    issues: list[AgentValidationIssue] = field(default_factory=list[AgentValidationIssue])

    def problem(self, code: str, path: _Path, message: str) -> None:
        self.issues.append(AgentValidationIssue(code=code, path=path, message=message))

    def add(
        self,
        dataset: str,
        key: _Key,
        record: dict[str, object],
        path: _Path,
        source_paths: list[_Path] | None = None,
    ) -> dict[str, object]:
        self.records[dataset][key] = record
        self.paths[(dataset, key)] = path
        self.source_paths[(dataset, key)] = source_paths or []
        return record


@dataclass(frozen=True, slots=True)
class _Expansion:
    candidate: dict[str, list[dict[str, object]]]
    # Agent path for each expanded record and nested source, keyed by its expanded path.
    paths: Mapping[_Path, _Path]
    # Agent path for each expanded record, keyed by dataset and normalized identity.
    record_paths: Mapping[tuple[str, _Key], _Path]


class _NormalizedCandidate(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    entities: tuple[LogicalEntityRecord, ...]
    attributes: tuple[LogicalAttributeRecord, ...]
    relationships: tuple[LogicalRelationshipRecord, ...]
    issues: tuple[AgentValidationIssue, ...]


_ARRAYS = {
    "logical_entity": "entities",
    "logical_attribute": "attributes",
    "logical_relationship": "relationships",
}
_AGENT_FIELDS = {
    "logical_entity_schema_name": "schema",
    "logical_entity_name": "name",
    "logical_entity_type": "type",
    "logical_entity_type_detail": "type_detail",
    "logical_entity_definition": "definition",
    "logical_entity_grain": "grain",
    "logical_attribute_name": "name",
    "logical_attribute_definition": "definition",
    "logical_attribute_data_type": "type",
    "logical_attribute_is_nullable": "nullable",
    "logical_attribute_is_natural_key": "natural_key",
    "from_logical_entity_schema_name": "from",
    "from_logical_entity_name": "from",
    "from_logical_attribute_name": "from",
    "to_logical_entity_schema_name": "to",
    "to_logical_entity_name": "to",
    "to_logical_attribute_name": "to",
    "logical_relationship_cardinality": "cardinality",
    "logical_relationship_basis": "basis",
}


class LogicalCandidateValidator:
    """Expand compact answers; enforce selection, locks, references and non-deletion."""

    def __init__(
        self,
        *,
        selected_object_keys: tuple[PhysicalObjectKey, ...],
        selected_attribute_keys: tuple[PhysicalAttributeKey, ...],
        context_record_ids: tuple[str, ...],
        applied: LogicalSection | None,
        coverage_threshold_percent: int = 70,
        attribute_descriptions: Mapping[PhysicalAttributeKey, str] | None = None,
        reserved_attribute_names: tuple[str, ...] = (),
    ) -> None:
        if (
            type(coverage_threshold_percent) is not int
            or not 1 <= coverage_threshold_percent <= 100
        ):
            raise ValueError("Coverage threshold must be a whole number from 1 to 100")
        self._coverage_threshold_percent = coverage_threshold_percent
        if not selected_object_keys or len(selected_object_keys) > 50_000:
            raise ValueError("Logical Object selection must be bounded and nonempty")
        if len(selected_attribute_keys) > 50_000:
            raise ValueError("Logical Attribute selection must be bounded")
        self._selected_object_keys = {
            _physical_object_key(item): item for item in selected_object_keys
        }
        self._selected_attribute_keys = {
            _physical_attribute_key(item) for item in selected_attribute_keys
        }
        self._context_record_ids = {
            normalize_project_key_value(item) for item in context_record_ids
        }
        if (
            len(self._selected_object_keys) != len(selected_object_keys)
            or len(self._selected_attribute_keys) != len(selected_attribute_keys)
            or len(self._context_record_ids) != len(context_record_ids)
        ):
            raise ValueError("Logical candidate evidence keys must be unique")
        # table_index numbers the frozen selection in its order: t1, t2, ...
        self._tables = {
            f"t{position}": key for position, key in enumerate(selected_object_keys, start=1)
        }
        self._table_ids = {
            _physical_object_key(key): table_id for table_id, key in self._tables.items()
        }
        self._columns: dict[tuple[str, str], PhysicalAttributeKey] = {}
        for key in selected_attribute_keys:
            table_id = self._table_ids.get(_physical_object_key(key))
            if table_id is None:
                raise ValueError("Selected Attributes must belong to selected Objects")
            self._columns[(table_id, normalize_project_key_value(key.attribute_name))] = key
        self._descriptions = {
            _physical_attribute_key(key): text
            for key, text in (attribute_descriptions or {}).items()
            if text.strip()
        }
        self._reserved_names = {
            normalize_project_key_value(name) for name in reserved_attribute_names
        }

        self._applied = applied or LogicalSection(
            submodels=(), entities=(), attributes=(), relationships=()
        )
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
            raise ValueError("Applied Logical records must be unique")

    def output_schema(self) -> dict[str, JsonValue]:
        schema = cast(dict[str, JsonValue], deepcopy(_CompactLogicalCandidate.model_json_schema()))
        schema["description"] = (
            "Return only new or changed Logical records in the three arrays; omitted saved "
            "records stay as they are. Cite tables by table_index id (t1) and columns as "
            "t1.column. For a saved Entity or Attribute, send its identity plus only the "
            "fields you change. The backend adds each new Entity's <Entity>ID key, audit "
            "columns, column and dependency order, locks and the parent key of each "
            "Relationship, and copies a missing Attribute definition from its single source "
            "column's Project description. Relationships point from the child's foreign-key "
            "Attribute to the parent Entity. Retire saved records in retire; nothing is "
            f"deleted. Coverage target is {self._coverage_threshold_percent}% of distinct "
            "selected Objects, rounded up, through active Entity sources, including unchanged "
            "saved records. On repair, fix every context.repair.validation_issues entry and "
            "return the complete corrected answer, not a patch."
        )
        return schema

    async def validate(self, candidate: JsonValue) -> AgentCandidateValidation:
        return AgentCandidateValidation(issues=self._normalize(candidate)[0].issues)

    def validate_coverage(
        self,
        candidate: JsonValue,
    ) -> tuple[AgentValidationIssue, ...]:
        """Measure distinct selected Object coverage across the resulting Project."""
        normalized, _ = self._normalize(candidate)
        if normalized.issues:
            return normalized.issues
        entities = {
            **self._applied_entities,
            **{_entity_key(record): record for record in normalized.entities},
        }
        covered_objects = {
            _physical_object_key(source.source_object)
            for record in entities.values()
            if record.logical_entity_status == "active"
            for source in record.sources
            if isinstance(source, LogicalObjectSourceRecord) and source.status == "active"
        }
        missing_objects = self._selected_object_keys.keys() - covered_objects
        total = len(self._selected_object_keys)
        covered = total - len(missing_objects)
        required = (total * self._coverage_threshold_percent + 99) // 100
        if covered >= required:
            return ()
        return (
            AgentValidationIssue(
                code="candidate.object_coverage_incomplete",
                path=("entities",),
                message=(
                    f"Coverage {covered}/{total} is below "
                    f"{self._coverage_threshold_percent}%; at least {required} distinct "
                    f"selected Objects are required ({required - covered} more). "
                    f"{len(missing_objects)} of {total} selected Objects lack active support."
                ),
                source_refs=tuple(
                    {
                        "table": self._table_ids[key],
                        **self._selected_object_keys[key].model_dump(mode="json"),
                    }
                    for key in sorted(missing_objects)[:MAX_COVERAGE_SOURCE_REFS]
                ),
            ),
        )

    def parse_validated(self, candidate: JsonValue) -> tuple[StageProjectChange, ...]:
        normalized, _ = self._normalize(candidate)
        if normalized.issues:
            raise InvalidRequestError("The Logical candidate is invalid.")
        entities = [
            record.model_dump(mode="json")
            for record in normalized.entities
            if self._applied_entities.get(_entity_key(record)) != record
        ]
        attributes = [
            record.model_dump(mode="json")
            for record in normalized.attributes
            if self._applied_attributes.get(_attribute_key(record)) != record
        ]
        relationships = [
            record.model_dump(mode="json")
            for record in normalized.relationships
            if self._applied_relationships.get(_relationship_key(record)) != record
        ]
        changes: list[StageProjectChange] = []
        if entities:
            changes.append(StageProjectChange(dataset="logical_entity", records=entities))
        if attributes:
            changes.append(StageProjectChange(dataset="logical_attribute", records=attributes))
        if relationships:
            changes.append(
                StageProjectChange(dataset="logical_relationship", records=relationships)
            )
        return tuple(changes)

    def agent_issues(
        self,
        candidate: JsonValue,
        issues: tuple[ProjectValidationIssue, ...],
        staged_documents: Mapping[ProjectChangeSetDataset, Sequence[Mapping[str, object]]],
    ) -> tuple[AgentValidationIssue, ...]:
        """Report whole-graph issues on staged records at the agent's own paths."""
        _, expansion = self._normalize(candidate)
        translated: list[AgentValidationIssue] = []
        for issue in issues:
            agent_path: _Path | None = None
            records = staged_documents.get(cast(ProjectChangeSetDataset, issue.dataset), ())
            if expansion is not None and issue.record_number is not None:
                index = issue.record_number - 1
                if 0 <= index < len(records):
                    identity = _record_identity(issue.dataset, records[index])
                    agent_path = expansion.record_paths.get((issue.dataset, identity))
            translated.append(
                AgentValidationIssue(
                    code=f"candidate.{issue.code}",
                    path=_with_agent_field(
                        agent_path or _agent_array_path(issue.dataset), issue.fields
                    ),
                    message=issue.message,
                )
            )
        return tuple(translated)

    def _normalize(self, candidate: JsonValue) -> tuple[_NormalizedCandidate, _Expansion | None]:
        expansion, expansion_issues = self._expand(candidate)
        if expansion is None:
            return _normalized(issues=expansion_issues), None
        parsed, parse_issues = parse_pydantic_candidate(
            _LogicalCandidate, cast(JsonValue, expansion.candidate)
        )
        if parsed is None:
            return _normalized(issues=_translate(expansion, parse_issues)), expansion

        issues: list[AgentValidationIssue] = []
        raw_entities: list[dict[str, object]] = []
        for index, record in enumerate(parsed.entities):
            existing = self._applied_entities.get(_entity_key(record))
            merged = _merge_entity(record, existing)
            self._validate_entity_evidence(
                record,
                unchanged_applied=(
                    existing is not None and merged == existing.model_dump(mode="json")
                ),
                index=index,
                issues=issues,
            )
            raw_entities.append(merged)
        raw_attributes: list[dict[str, object]] = []
        for index, record in enumerate(parsed.attributes):
            existing = self._applied_attributes.get(_attribute_key(record))
            merged = _merge_attribute(record, existing)
            self._validate_attribute_evidence(
                record,
                unchanged_applied=(
                    existing is not None and merged == existing.model_dump(mode="json")
                ),
                index=index,
                issues=issues,
            )
            raw_attributes.append(merged)
        raw_relationships = [
            _merge_relationship(record, self._applied_relationships.get(_relationship_key(record)))
            for record in parsed.relationships
        ]

        entities, entity_issues = validate_staged_records("logical_entity", raw_entities)
        attributes, attribute_issues = validate_staged_records("logical_attribute", raw_attributes)
        relationships, relationship_issues = validate_staged_records(
            "logical_relationship", raw_relationships
        )
        issues.extend(
            project_validation_issues(entity_issues + attribute_issues + relationship_issues)
        )
        normalized = _normalized(
            entities=cast(tuple[LogicalEntityRecord, ...], entities),
            attributes=cast(tuple[LogicalAttributeRecord, ...], attributes),
            relationships=cast(tuple[LogicalRelationshipRecord, ...], relationships),
        )
        self._validate_locks(parsed, normalized, issues)
        self._validate_references(normalized, issues)
        return normalized.model_copy(update={"issues": _translate(expansion, issues)}), expansion

    def _expand(
        self, candidate: JsonValue
    ) -> tuple[_Expansion | None, tuple[AgentValidationIssue, ...]]:
        """Turn the agent's compact answer into complete records plus a path map."""
        parsed, parse_issues = parse_pydantic_candidate(_CompactLogicalCandidate, candidate)
        if parsed is None:
            return None, parse_issues
        draft = _Draft()
        for index, entity in enumerate(parsed.entities):
            self._expand_entity(draft, entity, ("entities", index))
        for index, relationship in enumerate(parsed.relationships):
            self._expand_relationship(draft, relationship, ("relationships", index))
        for index, retirement in enumerate(parsed.retire):
            self._expand_retirement(draft, retirement, ("retire", index))
        if draft.issues:
            return None, tuple(draft.issues)
        self._order_entities(draft)

        candidate_records: dict[str, list[dict[str, object]]] = {}
        paths: dict[_Path, _Path] = {}
        for dataset, array in _ARRAYS.items():
            candidate_records[array] = []
            for index, (key, record) in enumerate(draft.records[dataset].items()):
                candidate_records[array].append(record)
                paths[(array, index)] = draft.paths[(dataset, key)]
                for source_index, path in enumerate(draft.source_paths[(dataset, key)]):
                    paths[(array, index, "sources", source_index)] = path
        return _Expansion(candidate=candidate_records, paths=paths, record_paths=draft.paths), ()

    def _expand_entity(self, draft: _Draft, entity: _CompactEntity, path: _Path) -> None:
        key = (
            normalize_project_key_value(entity.schema_),
            normalize_project_key_value(entity.name),
        )
        if key in draft.records["logical_entity"]:
            draft.problem("candidate.duplicate_record", path, "List each Entity once.")
            return
        saved = self._applied_entities.get(key)
        generated_key = normalize_project_key_value(f"{entity.name}ID")
        if saved is None:
            missing = [
                name for name in ("type", "definition", "grain") if getattr(entity, name) is None
            ]
            if missing:
                draft.rejected_entities.add(key)
                draft.problem(
                    "candidate.new_record_field_required",
                    (*path, missing[0]),
                    "A new Entity needs type, definition and grain.",
                )
                return
            if generated_key in self._reserved_names:
                draft.rejected_entities.add(key)
                draft.problem(
                    "candidate.generated_key_reserved",
                    (*path, "name"),
                    "This Entity's generated <Entity>ID key would match an audit column; "
                    "rename the Entity.",
                )
                return
        saved_sources = {_entity_source_key(item): item for item in saved.sources} if saved else {}
        sources: list[dict[str, object]] = []
        source_paths: list[_Path] = []
        for index, reference in enumerate(entity.sources):
            source = self._entity_source(reference, saved_sources)
            if source is None:
                draft.problem(
                    "candidate.table_unknown",
                    (*path, "sources", index),
                    "Use a table id listed in table_index.",
                )
                continue
            sources.append(source)
            source_paths.append((*path, "sources", index))
        entity_type = entity.type or (saved.logical_entity_type if saved else "core")
        record = draft.add(
            "logical_entity",
            key,
            {
                "logical_entity_schema_name": saved.logical_entity_schema_name
                if saved
                else entity.schema_,
                "logical_entity_name": saved.logical_entity_name if saved else entity.name,
                "logical_entity_definition": entity.definition
                or (saved.logical_entity_definition if saved else ""),
                "logical_entity_type": entity_type,
                "logical_entity_type_detail": (
                    saved.logical_entity_type_detail
                    if entity.type is None and saved is not None
                    else entity.type_detail
                    if entity_type == "other"
                    else None
                ),
                "logical_entity_grain": entity.grain
                or (saved.logical_entity_grain if saved else ""),
                # The backend sets dependency order once every Relationship is known.
                "logical_entity_dependency_order": (
                    saved.logical_entity_dependency_order if saved else 0
                ),
                "logical_entity_status": "active",
                "logical_entity_is_locked": False,
                "submodels": [],
                "sources": sources,
            },
            path,
            source_paths,
        )
        draft.listed_entities.add(key)

        saved_attributes = {
            attribute_key: item
            for attribute_key, item in self._applied_attributes.items()
            if attribute_key[:2] == key
        }
        if saved is None:
            # Every new Entity gets one generated key, first in column order.
            name = f"{entity.name}ID"
            draft.add(
                "logical_attribute",
                (*key, generated_key),
                _attribute_record(
                    record,
                    name=name,
                    definition=f"Generated identifier for {entity.name}.",
                    data_type="BIGINT",
                    nullable=False,
                    natural_key=False,
                    surrogate_key=True,
                    ordinal=1,
                    sources=[],
                ),
                path,
            )
        next_ordinal = 1 + max(
            (
                item.logical_attribute_ordinal_position
                for item in saved_attributes.values()
                if not item.logical_attribute_is_audit_column
            ),
            default=1 if saved is None else 0,
        )
        for index, attribute in enumerate(entity.attributes):
            if self._expand_attribute(
                draft,
                record,
                attribute,
                (*path, "attributes", index),
                saved=saved_attributes.get((*key, normalize_project_key_value(attribute.name))),
                generated_key=generated_key if saved is None else None,
                ordinal=next_ordinal,
            ):
                next_ordinal += 1

    def _expand_attribute(
        self,
        draft: _Draft,
        entity: Mapping[str, object],
        attribute: _CompactAttribute,
        path: _Path,
        *,
        saved: LogicalAttributeRecord | None,
        generated_key: str | None,
        ordinal: int,
    ) -> bool:
        """Add one Attribute; return whether it took the next new column position."""
        name = normalize_project_key_value(attribute.name)
        key = (*_entity_identity(entity), name)
        if name == generated_key:
            draft.problem(
                "candidate.generated_key_reserved",
                (*path, "name"),
                "<Entity>ID is the generated key of a new Entity; name the source identifier "
                "differently, such as Source<Entity>ID.",
            )
            return False
        if key in draft.records["logical_attribute"]:
            draft.problem(
                "candidate.duplicate_record", (*path, "name"), "List each Attribute once."
            )
            return False
        if name in self._reserved_names or (
            saved is not None and saved.logical_attribute_is_audit_column
        ):
            draft.problem(
                "candidate.audit_name_reserved",
                (*path, "name"),
                "The backend adds audit columns; give a business Attribute a distinct name, "
                "such as SourceCreatedDate.",
            )
            return False
        natural_key = (
            attribute.natural_key
            if attribute.natural_key is not None
            else saved.logical_attribute_is_natural_key
            if saved is not None
            else False
        )
        if saved is None and (
            attribute.type is None or (attribute.nullable is None and not natural_key)
        ):
            draft.problem(
                "candidate.new_record_field_required",
                path,
                "A new Attribute needs type, and nullable unless it is a natural key.",
            )
            return False
        references: tuple[_AttributeSourceRef, ...] = (
            ()
            if attribute.from_ is None
            else attribute.from_
            if isinstance(attribute.from_, tuple)
            else (attribute.from_,)
        )
        if references and saved is not None and saved.logical_attribute_is_surrogate_key:
            draft.problem(
                "candidate.generated_key_unsourced",
                (*path, "from"),
                "A generated key has no sources.",
            )
            return False
        saved_sources = (
            {_attribute_source_key(item): item for item in saved.sources} if saved else {}
        )
        sources: list[dict[str, object]] = []
        source_paths: list[_Path] = []
        columns: list[PhysicalAttributeKey] = []
        for index, reference in enumerate(references):
            source_path = (
                (*path, "from", index) if isinstance(attribute.from_, tuple) else (*path, "from")
            )
            source = self._attribute_source(reference, attribute.note, saved_sources)
            if source is None:
                draft.problem(
                    "candidate.column_unknown",
                    source_path,
                    "Use t<n>.<column> with a table id from table_index and one of that "
                    "table's listed columns.",
                )
                continue
            if source["support_source_type"] == "attribute":
                columns.append(PhysicalAttributeKey.model_validate(source["source_attribute"]))
            sources.append(source)
            source_paths.append(source_path)
        definition = (
            attribute.definition
            or (saved.logical_attribute_definition if saved else None)
            or (
                self._descriptions.get(_physical_attribute_key(columns[0]))
                if len(columns) == 1
                else None
            )
        )
        if definition is None:
            draft.problem(
                "candidate.definition_required",
                (*path, "definition"),
                "Write a definition: this Attribute has no single source column with a Project "
                "description.",
            )
            return False
        draft.add(
            "logical_attribute",
            key,
            _attribute_record(
                entity,
                name=saved.logical_attribute_name if saved else attribute.name,
                definition=definition,
                data_type=attribute.type or (saved.logical_attribute_data_type if saved else ""),
                nullable=(
                    False
                    if natural_key
                    else attribute.nullable
                    if attribute.nullable is not None
                    else saved.logical_attribute_is_nullable
                    if saved is not None
                    else True
                ),
                natural_key=natural_key,
                surrogate_key=saved.logical_attribute_is_surrogate_key if saved else False,
                ordinal=saved.logical_attribute_ordinal_position if saved else ordinal,
                sources=sources,
            ),
            path,
            source_paths,
        )
        return saved is None

    def _expand_relationship(
        self, draft: _Draft, relationship: _CompactRelationship, path: _Path
    ) -> None:
        child_key = (
            normalize_project_key_value(relationship.from_.schema_),
            normalize_project_key_value(relationship.from_.entity),
        )
        parent_key = (
            normalize_project_key_value(relationship.to.schema_),
            normalize_project_key_value(relationship.to.entity),
        )
        if {child_key, parent_key} & draft.rejected_entities:
            return
        child = self._current("logical_entity", draft, child_key)
        parent = self._current("logical_entity", draft, parent_key)
        if child is None or parent is None:
            draft.problem(
                "candidate.entity_missing",
                (*path, "from" if child is None else "to"),
                "A Relationship endpoint Entity must be saved or listed in entities.",
            )
            return
        parent_attribute = next(
            (
                record
                for attribute_key in (
                    *draft.records["logical_attribute"],
                    *self._applied_attributes,
                )
                if attribute_key[:2] == parent_key
                and (record := self._current("logical_attribute", draft, attribute_key)) is not None
                and record["logical_attribute_is_surrogate_key"] is True
                and record["logical_attribute_status"] == "active"
            ),
            None,
        )
        if parent_attribute is None:
            draft.problem(
                "candidate.parent_key_missing",
                (*path, "to"),
                "The parent Entity has no active generated key to reference.",
            )
            return
        foreign_key = self._current(
            "logical_attribute",
            draft,
            (*child_key, normalize_project_key_value(relationship.from_.attribute)),
        )
        from_name = (
            cast(str, foreign_key["logical_attribute_name"])
            if foreign_key is not None
            else relationship.from_.attribute
        )
        to_name = cast(str, parent_attribute["logical_attribute_name"])
        endpoints = (
            *child_key,
            normalize_project_key_value(from_name),
            *parent_key,
            normalize_project_key_value(to_name),
        )
        if endpoints in draft.listed_endpoints:
            draft.problem("candidate.duplicate_record", path, "List each Relationship once.")
            return
        draft.listed_endpoints.add(endpoints)
        saved = min(
            (record for key, record in self._applied_relationships.items() if key[:6] == endpoints),
            key=lambda record: (
                record.logical_relationship_status != "active",
                _relationship_key(record),
            ),
            default=None,
        )
        child_name = cast(str, child["logical_entity_name"])
        parent_name = cast(str, parent["logical_entity_name"])
        # The foreign-key column carries the role, so it names a new Relationship.
        name = saved.logical_relationship_name if saved else from_name
        draft.add(
            "logical_relationship",
            (*endpoints, normalize_project_key_value(name)),
            {
                "from_logical_entity_schema_name": child["logical_entity_schema_name"],
                "to_logical_entity_schema_name": parent["logical_entity_schema_name"],
                "logical_relationship_name": name,
                "logical_relationship_definition": (
                    saved.logical_relationship_definition
                    if saved
                    else f"{child_name} references {parent_name} through {from_name}."
                ),
                "from_logical_entity_name": child_name,
                "from_logical_attribute_name": from_name,
                "to_logical_entity_name": parent_name,
                "to_logical_attribute_name": to_name,
                "logical_relationship_cardinality": relationship.cardinality,
                "logical_relationship_basis": relationship.basis,
                # One basis covers the link and its cardinality; an unchanged saved pair stays.
                "logical_relationship_cardinality_basis": (
                    saved.logical_relationship_cardinality_basis
                    if saved is not None
                    and saved.logical_relationship_basis == relationship.basis
                    and saved.logical_relationship_cardinality == relationship.cardinality
                    else relationship.basis
                ),
                "logical_relationship_status": "active",
                "logical_relationship_is_locked": False,
            },
            path,
        )

    def _expand_retirement(self, draft: _Draft, item: _Retirement, path: _Path) -> None:
        entity_key = (
            normalize_project_key_value(item.schema_),
            normalize_project_key_value(item.entity),
        )
        saved_entity = self._applied_entities.get(entity_key)
        attribute_key = (
            None
            if item.attribute is None
            else (*entity_key, normalize_project_key_value(item.attribute))
        )
        saved_attribute = (
            None if attribute_key is None else self._applied_attributes.get(attribute_key)
        )
        if saved_entity is None or (attribute_key is not None and saved_attribute is None):
            draft.problem("candidate.record_missing", path, "Only saved records can be retired.")
            return

        if item.to is not None and attribute_key is not None:
            parent_key = (
                normalize_project_key_value(item.to.schema_),
                normalize_project_key_value(item.to.entity),
            )
            found = {
                key
                for key in self._applied_relationships
                if key[:3] == attribute_key and key[3:5] == parent_key
            }
            if not found:
                draft.problem("candidate.record_missing", path, "No saved Relationship matches.")
            elif any(key[:6] in draft.listed_endpoints for key in found):
                draft.problem(
                    "candidate.retire_conflict",
                    path,
                    "Do not list a Relationship and also retire it.",
                )
            else:
                self._retire_relationships(draft, path, lambda key: key in found)
            return

        if item.source is not None:
            # One nested source of a saved Entity or Attribute.
            dataset = "logical_entity" if attribute_key is None else "logical_attribute"
            saved_record: LogicalEntityRecord | LogicalAttributeRecord = (
                saved_entity if saved_attribute is None else saved_attribute
            )
            target = self._source_identity(item.source, column=attribute_key is not None)
            saved_source = next(
                (
                    source
                    for source in saved_record.sources
                    if target is not None and _nested_source_key(source) == target
                ),
                None,
            )
            if saved_source is None:
                draft.problem("candidate.record_missing", path, "No saved source matches.")
                return
            record_key = entity_key if attribute_key is None else attribute_key
            record = draft.records[dataset].get(record_key) or draft.add(
                dataset,
                record_key,
                {**saved_record.model_dump(mode="json"), "sources": []},
                path,
            )
            cast(list[object], record["sources"]).append(
                {**saved_source.model_dump(mode="json"), "status": "inactive"}
            )
            draft.source_paths[(dataset, record_key)].append(path)
            return

        if attribute_key is not None and saved_attribute is not None:
            if attribute_key in draft.records["logical_attribute"]:
                draft.problem(
                    "candidate.retire_conflict",
                    path,
                    "Do not list an Attribute and also retire it.",
                )
                return
            self._retire_attribute(draft, saved_attribute, path)
            return

        if entity_key in draft.records["logical_entity"]:
            draft.problem(
                "candidate.retire_conflict", path, "Do not list an Entity and also retire it."
            )
            return
        # Omitted sources stay; the copy only changes the lifecycle.
        draft.add(
            "logical_entity",
            entity_key,
            {
                **saved_entity.model_dump(mode="json"),
                "logical_entity_status": "inactive",
                "sources": [],
            },
            path,
        )
        for key, saved_attribute in self._applied_attributes.items():
            if (
                key[:2] == entity_key
                and key not in draft.records["logical_attribute"]
                and saved_attribute.logical_attribute_status == "active"
            ):
                self._retire_attribute(draft, saved_attribute, path)
        self._retire_relationships(draft, path, lambda key: entity_key in (key[:2], key[3:5]))

    def _retire_attribute(self, draft: _Draft, saved: LogicalAttributeRecord, path: _Path) -> None:
        key = _attribute_key(saved)
        draft.add(
            "logical_attribute",
            key,
            {
                **saved.model_dump(mode="json"),
                "logical_attribute_status": "inactive",
                "sources": [],
            },
            path,
        )
        self._retire_relationships(
            draft, path, lambda relationship: key in (relationship[:3], relationship[3:6])
        )

    def _retire_relationships(
        self, draft: _Draft, path: _Path, matches: Callable[[_Key], bool]
    ) -> None:
        """Retire active saved Relationships the agent did not list itself."""
        for key, saved in self._applied_relationships.items():
            if (
                saved.logical_relationship_status == "active"
                and key[:6] not in draft.listed_endpoints
                and key not in draft.records["logical_relationship"]
                and matches(key)
            ):
                draft.add(
                    "logical_relationship",
                    key,
                    {**saved.model_dump(mode="json"), "logical_relationship_status": "inactive"},
                    path,
                )

    def _order_entities(self, draft: _Draft) -> None:
        """Parents first: a listed Entity sits one above its highest parent.

        A saved Entity keeps a saved order that already satisfies this. Entities in a cycle keep
        their saved order, or zero.
        """
        relationships = {
            key: (key[:2], key[3:5])
            for key, record in self._applied_relationships.items()
            if record.logical_relationship_status == "active"
        }
        for key, record in draft.records["logical_relationship"].items():
            if record["logical_relationship_status"] == "active":
                relationships[key] = (key[:2], key[3:5])
            else:
                relationships.pop(key, None)
        parents: dict[_Key, set[_Key]] = {}
        children: dict[_Key, set[_Key]] = {}
        for child, parent in relationships.values():
            if child != parent:
                parents.setdefault(child, set()).add(parent)
                children.setdefault(parent, set()).add(child)
        orders = {
            key: record.logical_entity_dependency_order
            for key, record in self._applied_entities.items()
        }
        nodes = {*orders, *draft.records["logical_entity"], *parents, *children}
        waiting = {key: len(parents.get(key, ())) for key in nodes}
        ready = [key for key, count in waiting.items() if count == 0]
        while ready:
            key = ready.pop()
            if key in draft.listed_entities:
                required = 1 + max(
                    (orders.get(parent, 0) for parent in parents.get(key, ())), default=-1
                )
                orders[key] = max(orders.get(key, 0), required)
            for child in children.get(key, ()):
                waiting[child] -= 1
                if waiting[child] == 0:
                    ready.append(child)
        for key in draft.listed_entities:
            draft.records["logical_entity"][key]["logical_entity_dependency_order"] = orders.get(
                key, 0
            )

    def _current(self, dataset: str, draft: _Draft, key: _Key) -> dict[str, object] | None:
        """The record as this answer leaves it: listed, else saved."""
        record = draft.records[dataset].get(key)
        if record is not None:
            return record
        saved: BaseModel | None = (
            self._applied_entities.get(key)
            if dataset == "logical_entity"
            else self._applied_attributes.get(key)
        )
        return None if saved is None else cast(dict[str, object], saved.model_dump(mode="json"))

    def _entity_source(
        self,
        reference: _EntitySourceRef,
        saved_sources: Mapping[_Key, _EntitySource],
    ) -> dict[str, object] | None:
        note = None if isinstance(reference, str) else reference.note
        if isinstance(reference, _ContextSource):
            identity: _Key = ("context_record", normalize_project_key_value(reference.context))
            source: dict[str, object] = {
                "support_source_type": "context_record",
                "context_record": {"context_record_id": reference.context},
                "rationale": note or "A Context record supports this Entity.",
            }
        else:
            table = self._tables.get(reference if isinstance(reference, str) else reference.table)
            if table is None:
                return None
            identity = ("object", *_physical_object_key(table))
            source = {
                "support_source_type": "object",
                "source_object": table.model_dump(mode="json"),
                "rationale": note or f"Built from {table.object_schema}.{table.object_name}.",
            }
        saved = saved_sources.get(identity)
        if saved is not None and note is None:
            # A repeated source keeps its saved rationale and order.
            return {**saved.model_dump(mode="json"), "status": "active", "is_locked": False}
        return {**source, "source_order": None, "status": "active", "is_locked": False}

    def _attribute_source(
        self,
        reference: _AttributeSourceRef,
        attribute_note: str | None,
        saved_sources: Mapping[_Key, _AttributeSource],
    ) -> dict[str, object] | None:
        note = (None if isinstance(reference, str) else reference.note) or attribute_note
        if isinstance(reference, _ContextSource):
            identity: _Key = ("context_record", normalize_project_key_value(reference.context))
            source: dict[str, object] = {
                "support_source_type": "context_record",
                "context_record": {"context_record_id": reference.context},
                "rationale": note or "A Context record supports this Attribute.",
            }
        else:
            column = self._column(reference if isinstance(reference, str) else reference.column)
            if column is None:
                return None
            identity = ("attribute", *_physical_attribute_key(column))
            source = {
                "support_source_type": "attribute",
                "source_attribute": column.model_dump(mode="json"),
                "rationale": note or f"Copied from {column.object_name}.{column.attribute_name}.",
            }
        saved = saved_sources.get(identity)
        if saved is not None and note is None:
            return {**saved.model_dump(mode="json"), "status": "active", "is_locked": False}
        return {**source, "source_order": None, "status": "active", "is_locked": False}

    def _column(self, reference: str) -> PhysicalAttributeKey | None:
        table_id, _, column = reference.partition(".")
        return self._columns.get((table_id, normalize_project_key_value(column)))

    def _source_identity(self, reference: str, *, column: bool) -> _Key | None:
        """Identify a saved source named by a table id, a column or a Context record id."""
        if _CONTEXT_ID.match(reference):
            return ("context_record", normalize_project_key_value(reference))
        if column:
            key = self._column(reference)
            return None if key is None else ("attribute", *_physical_attribute_key(key))
        table = self._tables.get(reference)
        return None if table is None else ("object", *_physical_object_key(table))

    def _validate_entity_evidence(
        self,
        record: LogicalEntityRecord,
        *,
        unchanged_applied: bool,
        index: int,
        issues: list[AgentValidationIssue],
    ) -> None:
        for source_index, source in enumerate(record.sources):
            # Retiring evidence never needs it to be in this run.
            if source.status != "active":
                continue
            if isinstance(source, LogicalObjectSourceRecord):
                valid = (
                    unchanged_applied
                    or _physical_object_key(source.source_object) in self._selected_object_keys
                )
                code = "candidate.source_outside_selection"
                message = "Physical Object source must belong to this immutable run selection."
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

    def _validate_attribute_evidence(
        self,
        record: LogicalAttributeRecord,
        *,
        unchanged_applied: bool,
        index: int,
        issues: list[AgentValidationIssue],
    ) -> None:
        for source_index, source in enumerate(record.sources):
            if source.status != "active":
                continue
            if isinstance(source, AttributePhysicalSourceRecord):
                valid = (
                    unchanged_applied
                    or _physical_attribute_key(source.source_attribute)
                    in self._selected_attribute_keys
                )
                code = "candidate.source_outside_selection"
                message = "Physical Attribute source must belong to this immutable run selection."
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

    def _validate_locks(
        self,
        expanded: _LogicalCandidate,
        normalized: _NormalizedCandidate,
        issues: list[AgentValidationIssue],
    ) -> None:
        def check(
            path: _Path,
            existing: LogicalEntityRecord
            | LogicalAttributeRecord
            | LogicalRelationshipRecord
            | None,
            merged: BaseModel,
            returned_sources: Sequence[_EntitySource | _AttributeSource],
        ) -> None:
            if existing is None:
                return
            if _top_lock(existing) and existing != merged:
                _record_locked(path, issues)
                return
            # Only nested records this answer returned can change a locked one.
            saved_nested = {
                _nested_source_key(source): source for source in getattr(existing, "sources", ())
            }
            for index, source in enumerate(returned_sources):
                saved = saved_nested.get(_nested_source_key(source))
                if (
                    saved is not None
                    and saved.is_locked
                    and _without_lock(saved) != _without_lock(source)
                ):
                    _record_locked((*path, "sources", index), issues)

        for index, (merged, returned) in enumerate(
            zip(normalized.entities, expanded.entities, strict=True)
        ):
            check(
                ("entities", index),
                self._applied_entities.get(_entity_key(merged)),
                merged,
                returned.sources,
            )
        for index, (merged, returned) in enumerate(
            zip(normalized.attributes, expanded.attributes, strict=True)
        ):
            check(
                ("attributes", index),
                self._applied_attributes.get(_attribute_key(merged)),
                merged,
                returned.sources,
            )
        for index, merged in enumerate(normalized.relationships):
            check(
                ("relationships", index),
                self._applied_relationships.get(_relationship_key(merged)),
                merged,
                (),
            )

    def _validate_references(
        self,
        normalized: _NormalizedCandidate,
        issues: list[AgentValidationIssue],
    ) -> None:
        entity_keys = set(self._applied_entities)
        entity_keys.update(_entity_key(record) for record in normalized.entities)
        attribute_keys = set(self._applied_attributes)
        attribute_keys.update(_attribute_key(record) for record in normalized.attributes)
        for index, attribute in enumerate(normalized.attributes):
            if _attribute_key(attribute)[:2] not in entity_keys:
                issues.append(
                    AgentValidationIssue(
                        code="candidate.entity_missing",
                        path=("attributes", index),
                        message="Every Logical Attribute Entity must exist.",
                    )
                )
        for index, relationship in enumerate(normalized.relationships):
            if _relationship_key(relationship)[:3] not in attribute_keys:
                issues.append(
                    AgentValidationIssue(
                        code="candidate.relationship_endpoint_missing",
                        path=("relationships", index, "from_logical_attribute_name"),
                        message=(
                            "The foreign-key Attribute must be saved or listed under its "
                            "child Entity."
                        ),
                    )
                )


def _normalized(
    *,
    entities: tuple[LogicalEntityRecord, ...] = (),
    attributes: tuple[LogicalAttributeRecord, ...] = (),
    relationships: tuple[LogicalRelationshipRecord, ...] = (),
    issues: tuple[AgentValidationIssue, ...] = (),
) -> _NormalizedCandidate:
    return _NormalizedCandidate(
        entities=entities, attributes=attributes, relationships=relationships, issues=issues
    )


def _attribute_record(
    entity: Mapping[str, object],
    *,
    name: str,
    definition: str,
    data_type: str,
    nullable: bool,
    natural_key: bool,
    surrogate_key: bool,
    ordinal: int,
    sources: list[dict[str, object]],
) -> dict[str, object]:
    return {
        "logical_entity_schema_name": entity["logical_entity_schema_name"],
        "logical_entity_name": entity["logical_entity_name"],
        "logical_attribute_name": name,
        "logical_attribute_definition": definition,
        "logical_attribute_data_type": data_type,
        "logical_attribute_is_nullable": nullable,
        "logical_attribute_is_natural_key": natural_key,
        "logical_attribute_is_surrogate_key": surrogate_key,
        "logical_attribute_ordinal_position": ordinal,
        "logical_attribute_is_audit_column": False,
        "logical_attribute_status": "active",
        "logical_attribute_is_locked": False,
        "sources": sources,
    }


def _translate(
    expansion: _Expansion, issues: Iterable[AgentValidationIssue]
) -> tuple[AgentValidationIssue, ...]:
    """Move issues on expanded records to the agent's own answer paths."""
    translated: list[AgentValidationIssue] = []
    seen: set[tuple[str, _Path]] = set()
    for issue in issues:
        path = issue.path
        if path and path[0] in _ARRAYS:
            path = (_ARRAYS[path[0]], *path[1:])
        agent_path: _Path | None = None
        rest: _Path = path[1:]
        for length in range(min(len(path), 4), 1, -1):
            if (agent_path := expansion.paths.get(path[:length])) is not None:
                rest = path[length:]
                break
        if agent_path is None:
            head = str(path[0]) if path else "entities"
            agent_path = _agent_array_path(
                {
                    "entities": "logical_entity",
                    "attributes": "logical_attribute",
                    "relationships": "logical_relationship",
                }.get(head, head)
            )
        agent_path = _with_agent_field(
            agent_path, tuple(item for item in rest if isinstance(item, str))
        )
        if (issue.code, agent_path) not in seen:
            seen.add((issue.code, agent_path))
            translated.append(issue.model_copy(update={"path": agent_path}))
    return tuple(translated)


def _agent_array_path(dataset: str) -> _Path:
    """The answer array for a Logical dataset; other datasets keep their own name."""
    return {
        "logical_entity": ("entities",),
        "logical_attribute": ("entities", "attributes"),
        "logical_relationship": ("relationships",),
    }.get(dataset, (dataset,))


def _with_agent_field(path: _Path, fields: tuple[str, ...]) -> _Path:
    """Name the first field the agent writes; computed fields stay at the record path."""
    if path and path[0] == "retire":
        return path
    if path and path[0] not in ("entities", "relationships"):
        # A dependent dataset the agent never writes keeps its own field names.
        return (*path, *fields)
    for name in fields:
        if name in _AGENT_FIELDS:
            return (*path, _AGENT_FIELDS[name])
        if name == "sources" and path[-1:] not in (("sources",), ("from",)):
            return (*path, "from" if "attributes" in path else "sources")
    return path


def _record_identity(dataset: str, record: Mapping[str, object]) -> _Key:
    fields = {
        "logical_entity": ("logical_entity_schema_name", "logical_entity_name"),
        "logical_attribute": (
            "logical_entity_schema_name",
            "logical_entity_name",
            "logical_attribute_name",
        ),
    }.get(
        dataset,
        (
            "from_logical_entity_schema_name",
            "from_logical_entity_name",
            "from_logical_attribute_name",
            "to_logical_entity_schema_name",
            "to_logical_entity_name",
            "to_logical_attribute_name",
            "logical_relationship_name",
        ),
    )
    return tuple(normalize_project_key_value(str(record.get(name, ""))) for name in fields)


def _entity_identity(record: Mapping[str, object]) -> _Key:
    return _record_identity("logical_entity", record)


def _merge_entity(
    record: LogicalEntityRecord,
    existing: LogicalEntityRecord | None,
) -> dict[str, object]:
    value = cast(dict[str, object], record.model_dump(mode="json"))
    value["logical_entity_is_locked"] = (
        existing.logical_entity_is_locked if existing is not None else False
    )
    # Submodel memberships are no longer authored; saved ones stay as they are.
    value["submodels"] = (
        [] if existing is None else [item.model_dump(mode="json") for item in existing.submodels]
    )
    value["sources"] = _merge_nested(
        record.sources,
        () if existing is None else existing.sources,
        key=_entity_source_key,
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
    value["sources"] = _merge_nested(
        record.sources,
        () if existing is None else existing.sources,
        key=_attribute_source_key,
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


def _merge_nested[T: _EntitySource | _AttributeSource](
    candidate: Sequence[T],
    existing: Sequence[T],
    *,
    key: Callable[[T], _Key],
) -> list[dict[str, object]]:
    """Returned nested records replace saved ones; omitted saved ones are kept."""
    candidate_by_key = {key(item): item for item in candidate}
    existing_keys = {key(item) for item in existing}
    merged: list[dict[str, object]] = []
    for applied_record in existing:
        candidate_record = candidate_by_key.get(key(applied_record))
        if candidate_record is None:
            merged.append(cast(dict[str, object], applied_record.model_dump(mode="json")))
            continue
        value = cast(dict[str, object], candidate_record.model_dump(mode="json"))
        value["is_locked"] = applied_record.is_locked
        merged.append(value)
    for candidate_record in candidate:
        if key(candidate_record) not in existing_keys:
            value = cast(dict[str, object], candidate_record.model_dump(mode="json"))
            value["is_locked"] = False
            merged.append(value)
    return merged


def _record_locked(path: _Path, issues: list[AgentValidationIssue]) -> None:
    issues.append(
        AgentValidationIssue(
            code="candidate.record_locked",
            path=path,
            message="A locked saved Logical record cannot be changed.",
        )
    )


def _top_lock(
    record: LogicalEntityRecord | LogicalAttributeRecord | LogicalRelationshipRecord,
) -> bool:
    if isinstance(record, LogicalEntityRecord):
        return record.logical_entity_is_locked
    if isinstance(record, LogicalAttributeRecord):
        return record.logical_attribute_is_locked
    return record.logical_relationship_is_locked


def _without_lock(record: BaseModel) -> dict[str, object]:
    value = cast(dict[str, object], record.model_dump(mode="json"))
    value.pop("is_locked", None)
    return value


def _entity_key(record: LogicalEntityRecord) -> _Key:
    return (
        normalize_project_key_value(record.logical_entity_schema_name),
        normalize_project_key_value(record.logical_entity_name),
    )


def _attribute_key(record: LogicalAttributeRecord) -> _Key:
    return (
        normalize_project_key_value(record.logical_entity_schema_name),
        normalize_project_key_value(record.logical_entity_name),
        normalize_project_key_value(record.logical_attribute_name),
    )


def _relationship_key(record: LogicalRelationshipRecord) -> _Key:
    return (
        normalize_project_key_value(record.from_logical_entity_schema_name),
        normalize_project_key_value(record.from_logical_entity_name),
        normalize_project_key_value(record.from_logical_attribute_name),
        normalize_project_key_value(record.to_logical_entity_schema_name),
        normalize_project_key_value(record.to_logical_entity_name),
        normalize_project_key_value(record.to_logical_attribute_name),
        normalize_project_key_value(record.logical_relationship_name),
    )


def _entity_source_key(record: _EntitySource) -> _Key:
    if isinstance(record, LogicalObjectSourceRecord):
        return ("object", *_physical_object_key(record.source_object))
    return ("context_record", normalize_project_key_value(record.context_record.context_record_id))


def _attribute_source_key(record: _AttributeSource) -> _Key:
    if isinstance(record, AttributePhysicalSourceRecord):
        return ("attribute", *_physical_attribute_key(record.source_attribute))
    return ("context_record", normalize_project_key_value(record.context_record.context_record_id))


def _nested_source_key(record: _EntitySource | _AttributeSource) -> _Key:
    if isinstance(record, (LogicalObjectSourceRecord, LogicalContextSourceRecord)):
        return _entity_source_key(record)
    return _attribute_source_key(record)


def _physical_object_key(record: PhysicalObjectKey) -> _Key:
    return (
        normalize_project_key_value(record.tenant_code),
        normalize_project_key_value(record.system_code),
        normalize_project_key_value(record.connection_code),
        normalize_project_key_value(record.object_schema),
        normalize_project_key_value(record.object_name),
    )


def _physical_attribute_key(record: PhysicalAttributeKey) -> _Key:
    return (*_physical_object_key(record), normalize_project_key_value(record.attribute_name))


__all__ = ["LogicalCandidateValidator"]
