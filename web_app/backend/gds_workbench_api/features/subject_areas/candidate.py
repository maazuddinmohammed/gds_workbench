"""Expand one Subject Area agent answer into canonical non-deleting changes.

The agent groups the whole Input Scope into named areas, citing tables by table_index id.
A listed area's tables replace its saved unlocked memberships; unlisted saved areas stay
as they are; retire marks saved areas inactive. The backend checks every table id, keeps
locks, accounts for every Scope table, caps each area's column count, and reports issues
at the agent's own answer paths.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from copy import deepcopy
from dataclasses import dataclass, field
from typing import Annotated, cast

from gds_etl_workbench.application.change_sets.project import StageProjectChange
from gds_etl_workbench.application.change_sets.project_validation import ProjectValidationIssue
from gds_etl_workbench.domain.errors import InvalidRequestError
from gds_etl_workbench.domain.modeling_records import (
    NonblankText,
    PhysicalObjectKey,
    SubjectAreaTableRecord,
    normalize_project_key_value,
)
from gds_etl_workbench.domain.snapshots.project import (
    ProjectChangeSetDataset,
    SubjectAreaSection,
)
from pydantic import BaseModel, ConfigDict, Field, JsonValue, StringConstraints

from gds_workbench_api.features.workflows.authoring.repair import (
    MAX_COVERAGE_SOURCE_REFS,
    AgentCandidateValidation,
    AgentValidationIssue,
    parse_pydantic_candidate,
)

type _Path = tuple[str | int, ...]
type _Key = tuple[str, ...]

_TableId = Annotated[
    str,
    StringConstraints(pattern=r"^t[1-9][0-9]{0,5}$"),
    Field(description="A table id from table_index, such as t1."),
]
_Name = Annotated[str, StringConstraints(min_length=1, max_length=255, pattern=r"\S")]


class _Answer(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)


class _AreaAnswer(_Answer):
    name: _Name = Field(description="Business capability name, such as Sales or Support.")
    definition: NonblankText | None = Field(
        default=None,
        description=(
            "What the area covers, in one or two sentences. Required for a new area; omit "
            "to keep a saved one."
        ),
    )
    tables: tuple[_TableId, ...] = Field(
        max_length=50_000,
        description=(
            "Every table that belongs in this area. The list replaces the area's saved "
            "tables; locked tables stay. A table may belong to several areas."
        ),
    )


class _SubjectAreaAnswer(_Answer):
    areas: tuple[_AreaAnswer, ...] = Field(
        max_length=1_000,
        description="New areas, and saved areas to change. Unlisted saved areas stay as saved.",
    )
    unassigned: tuple[_TableId, ...] = Field(
        max_length=50_000,
        description="Tables that fit no area yet. Every table is in an area or here.",
    )
    retire: tuple[_Name, ...] = Field(
        max_length=1_000,
        description="Saved area names to mark inactive with their tables. Nothing is deleted.",
    )


@dataclass(slots=True)
class _Draft:
    areas: dict[_Key, dict[str, object]] = field(default_factory=dict[_Key, dict[str, object]])
    tables: dict[_Key, dict[str, object]] = field(default_factory=dict[_Key, dict[str, object]])
    paths: dict[tuple[str, _Key], _Path] = field(default_factory=dict[tuple[str, _Key], _Path])
    issues: list[AgentValidationIssue] = field(default_factory=list[AgentValidationIssue])

    def problem(self, code: str, path: _Path, message: str) -> None:
        self.issues.append(AgentValidationIssue(code=code, path=path, message=message))


class SubjectAreaCandidateValidator:
    """Check and expand a Subject Area answer over the run's whole Input Scope."""

    def __init__(
        self,
        *,
        selected_object_keys: tuple[PhysicalObjectKey, ...],
        column_counts: tuple[int, ...],
        applied: SubjectAreaSection | None,
        max_subject_area_columns: int,
    ) -> None:
        if not selected_object_keys or len(selected_object_keys) > 50_000:
            raise ValueError("Subject Area selection must be bounded and nonempty")
        if len(column_counts) != len(selected_object_keys) or any(
            count < 0 for count in column_counts
        ):
            raise ValueError("Each selected table needs one column count")
        if max_subject_area_columns < 1:
            raise ValueError("The Subject Area column cap must be positive")
        # table_index numbers the frozen selection in its order: t1, t2, ...
        self._tables = {
            f"t{position}": key for position, key in enumerate(selected_object_keys, start=1)
        }
        self._table_ids = {_object_key(key): table for table, key in self._tables.items()}
        if len(self._table_ids) != len(self._tables):
            raise ValueError("Subject Area selection keys must be unique")
        self._columns = {
            f"t{position}": count for position, count in enumerate(column_counts, start=1)
        }
        self._max_columns = max_subject_area_columns
        self._applied = applied or SubjectAreaSection(areas=(), tables=())
        self._applied_areas = {
            normalize_project_key_value(record.subject_area_name): record
            for record in self._applied.areas
        }
        self._applied_tables = {_membership_key(record): record for record in self._applied.tables}
        if len(self._applied_areas) != len(self._applied.areas) or len(self._applied_tables) != len(
            self._applied.tables
        ):
            raise ValueError("Applied Subject Area records must be unique")

    def output_schema(self) -> dict[str, JsonValue]:
        schema = cast(dict[str, JsonValue], deepcopy(_SubjectAreaAnswer.model_json_schema()))
        schema["description"] = (
            "Group every Input Scope table into Subject Areas: business capabilities that each "
            "Logical Build call can model on its own. Cite tables by table_index id. Return "
            "new areas and saved areas you change; a listed area's tables replace its saved "
            "unlocked tables. Put each remaining table in unassigned. Retire saved areas by "
            f"name; nothing is deleted. Keep each area at or below {self._max_columns} "
            "columns in total. On repair, fix every context.repair.validation_issues entry "
            "and return the complete corrected answer, not a patch."
        )
        return schema

    async def validate(self, candidate: JsonValue) -> AgentCandidateValidation:
        _, issues = self._expand(candidate)
        return AgentCandidateValidation(issues=issues)

    def parse_validated(self, candidate: JsonValue) -> tuple[StageProjectChange, ...]:
        draft, issues = self._expand(candidate)
        if issues or draft is None:
            raise InvalidRequestError("The Subject Area candidate is invalid.")
        areas = [
            record
            for key, record in draft.areas.items()
            if (saved := self._applied_areas.get(key[0])) is None
            or saved.model_dump(mode="json") != record
        ]
        tables = [
            record
            for key, record in draft.tables.items()
            if (saved := self._applied_tables.get(key)) is None
            or saved.model_dump(mode="json") != record
        ]
        changes: list[StageProjectChange] = []
        if areas:
            changes.append(StageProjectChange(dataset="subject_area", records=areas))
        if tables:
            changes.append(StageProjectChange(dataset="subject_area_table", records=tables))
        return tuple(changes)

    def agent_issues(
        self,
        candidate: JsonValue,
        issues: tuple[ProjectValidationIssue, ...],
        staged_documents: Mapping[ProjectChangeSetDataset, Sequence[Mapping[str, object]]],
    ) -> tuple[AgentValidationIssue, ...]:
        """Report whole-graph issues on staged records at the agent's own paths."""
        draft, _ = self._expand(candidate)
        translated: list[AgentValidationIssue] = []
        for issue in issues:
            path: _Path | None = None
            records = staged_documents.get(cast(ProjectChangeSetDataset, issue.dataset), ())
            if draft is not None and issue.record_number is not None:
                index = issue.record_number - 1
                if 0 <= index < len(records):
                    record = records[index]
                    key = (
                        (normalize_project_key_value(str(record.get("subject_area_name", ""))),)
                        if issue.dataset == "subject_area"
                        else _membership_key(record)
                    )
                    path = draft.paths.get((issue.dataset, key))
            if path is None:
                path = (
                    ("areas",)
                    if issue.dataset == "subject_area"
                    else ("areas", "tables")
                    if issue.dataset == "subject_area_table"
                    else (issue.dataset, *issue.fields)
                )
            translated.append(
                AgentValidationIssue(
                    code=f"candidate.{issue.code}", path=path, message=issue.message
                )
            )
        return tuple(translated)

    def _expand(
        self, candidate: JsonValue
    ) -> tuple[_Draft | None, tuple[AgentValidationIssue, ...]]:
        parsed, parse_issues = parse_pydantic_candidate(_SubjectAreaAnswer, candidate)
        if parsed is None:
            return None, parse_issues
        draft = _Draft()
        retired = {normalize_project_key_value(name) for name in parsed.retire}
        for index, area in enumerate(parsed.areas):
            self._expand_area(draft, area, ("areas", index), retired=retired)
        for index, name in enumerate(parsed.retire):
            self._retire_area(draft, name, ("retire", index))
        self._check_accounting(draft, parsed)
        return (None, tuple(draft.issues)) if draft.issues else (draft, ())

    def _expand_area(
        self, draft: _Draft, area: _AreaAnswer, path: _Path, *, retired: set[str]
    ) -> None:
        name = normalize_project_key_value(area.name)
        if (name,) in draft.areas:
            draft.problem("candidate.duplicate_record", (*path, "name"), "List each area once.")
            return
        if name in retired:
            draft.problem(
                "candidate.retire_conflict", (*path, "name"), "Do not list an area and retire it."
            )
            return
        saved = self._applied_areas.get(name)
        if saved is None and area.definition is None:
            draft.problem(
                "candidate.new_record_field_required",
                (*path, "definition"),
                "A new area needs a definition.",
            )
            return
        saved_members = {
            key: membership
            for key, membership in self._applied_tables.items()
            if key[0] == name and key[1:] in self._table_ids
        }
        listed: list[str] = []
        for index, table in enumerate(area.tables):
            previous = (
                saved_members.get((name, *_object_key(self._tables[table])))
                if table in self._tables
                else None
            )
            if table not in self._tables:
                draft.problem(
                    "candidate.table_unknown",
                    (*path, "tables", index),
                    "Use a table id listed in table_index.",
                )
            elif table in listed:
                draft.problem(
                    "candidate.duplicate_record",
                    (*path, "tables", index),
                    "List each table once per area.",
                )
            elif (
                previous is not None
                and previous.subject_area_table_is_locked
                and previous.subject_area_table_status != "active"
            ):
                draft.problem(
                    "candidate.record_locked",
                    (*path, "tables", index),
                    "This table is locked out of the area; leave it out of tables.",
                )
            else:
                listed.append(table)
        area_name = saved.subject_area_name if saved is not None else area.name
        record: dict[str, object] = {
            "subject_area_name": area_name,
            "subject_area_definition": area.definition
            or (saved.subject_area_definition if saved is not None else ""),
            "subject_area_status": "active",
            "subject_area_is_locked": saved.subject_area_is_locked if saved is not None else False,
        }
        draft.areas[(name,)] = record
        draft.paths[("subject_area", (name,))] = path

        # A listed area's tables replace its saved unlocked memberships.
        members: dict[_Key, dict[str, object]] = {}
        for table in listed:
            key = (name, *_object_key(self._tables[table]))
            previous = saved_members.get(key)
            members[key] = _membership(
                area_name,
                self._tables[table],
                active=True,
                locked=previous.subject_area_table_is_locked if previous is not None else False,
            )
        for key, membership in saved_members.items():
            if key in members:
                continue
            if membership.subject_area_table_is_locked:
                # Locked tables stay, whatever the answer lists.
                if membership.subject_area_table_status == "active":
                    listed.append(self._table_ids[key[1:]])
                continue
            members[key] = {
                **membership.model_dump(mode="json"),
                "subject_area_table_status": "inactive",
            }
        if (
            saved is not None
            and saved.subject_area_is_locked
            and (
                saved.model_dump(mode="json") != record
                or any(
                    (previous := saved_members.get(key)) is None
                    or previous.model_dump(mode="json") != member
                    for key, member in members.items()
                )
            )
        ):
            draft.problem(
                "candidate.record_locked",
                path,
                "A locked area cannot change; leave it out of the answer.",
            )
            return
        columns = sum(self._columns[table] for table in set(listed))
        if columns > self._max_columns:
            draft.problem(
                "candidate.subject_area_too_large",
                (*path, "tables"),
                f"This area holds {columns} columns; the limit is {self._max_columns}. "
                "Split it into narrower areas.",
            )
        for key, member in members.items():
            draft.tables[key] = member
            draft.paths[("subject_area_table", key)] = path

    def _retire_area(self, draft: _Draft, name: str, path: _Path) -> None:
        key = normalize_project_key_value(name)
        saved = self._applied_areas.get(key)
        if saved is None:
            draft.problem("candidate.record_missing", path, "Only saved areas can be retired.")
            return
        members = {
            member_key: membership
            for member_key, membership in self._applied_tables.items()
            if member_key[0] == key
        }
        if saved.subject_area_is_locked or any(
            membership.subject_area_table_is_locked
            and membership.subject_area_table_status == "active"
            for membership in members.values()
        ):
            draft.problem(
                "candidate.record_locked",
                path,
                "A locked area, or one with locked tables, cannot be retired.",
            )
            return
        draft.areas[(key,)] = {
            **saved.model_dump(mode="json"),
            "subject_area_status": "inactive",
        }
        draft.paths[("subject_area", (key,))] = path
        for member_key, membership in members.items():
            if membership.subject_area_table_status == "active":
                draft.tables[member_key] = {
                    **membership.model_dump(mode="json"),
                    "subject_area_table_status": "inactive",
                }
                draft.paths[("subject_area_table", member_key)] = path

    def _check_accounting(self, draft: _Draft, parsed: _SubjectAreaAnswer) -> None:
        """Every Scope table sits in an active area or is explicitly unassigned."""
        active_areas = {
            name
            for name, area in self._applied_areas.items()
            if area.subject_area_status == "active"
        }
        for (name,), area in draft.areas.items():
            if area["subject_area_status"] == "active":
                active_areas.add(name)
            else:
                active_areas.discard(name)
        memberships = {
            key: membership.subject_area_table_status == "active"
            for key, membership in self._applied_tables.items()
        }
        memberships.update(
            {
                key: record["subject_area_table_status"] == "active"
                for key, record in draft.tables.items()
            }
        )
        assigned = {
            self._table_ids[key[1:]]
            for key, active in memberships.items()
            if active and key[0] in active_areas and key[1:] in self._table_ids
        }
        for index, table in enumerate(parsed.unassigned):
            if table not in self._tables:
                draft.problem(
                    "candidate.table_unknown",
                    ("unassigned", index),
                    "Use a table id listed in table_index.",
                )
            elif table in assigned:
                draft.problem(
                    "candidate.unassigned_conflict",
                    ("unassigned", index),
                    "A table in an area is not unassigned; remove it from one of the lists.",
                )
        unassigned = set(parsed.unassigned)
        missing = [
            table for table in self._tables if table not in assigned and table not in unassigned
        ]
        if missing:
            draft.issues.append(
                AgentValidationIssue(
                    code="candidate.table_unaccounted",
                    path=("unassigned",),
                    message=(
                        f"{len(missing)} of {len(self._tables)} tables are in no active area "
                        "and not in unassigned. Place each one in an area or in unassigned."
                    ),
                    source_refs=tuple(
                        {"table": table, **self._tables[table].model_dump(mode="json")}
                        for table in missing[:MAX_COVERAGE_SOURCE_REFS]
                    ),
                )
            )


def _membership(
    area_name: str, key: PhysicalObjectKey, *, active: bool, locked: bool
) -> dict[str, object]:
    return {
        "subject_area_name": area_name,
        **key.model_dump(mode="json"),
        "subject_area_table_status": "active" if active else "inactive",
        "subject_area_table_is_locked": locked,
    }


def _object_key(record: PhysicalObjectKey | SubjectAreaTableRecord) -> _Key:
    return (
        normalize_project_key_value(record.tenant_code),
        normalize_project_key_value(record.system_code),
        normalize_project_key_value(record.connection_code),
        normalize_project_key_value(record.object_schema),
        normalize_project_key_value(record.object_name),
    )


def _membership_key(record: SubjectAreaTableRecord | Mapping[str, object]) -> _Key:
    values = record if isinstance(record, Mapping) else record.model_dump(mode="json")
    return tuple(
        normalize_project_key_value(str(values.get(name, "")))
        for name in (
            "subject_area_name",
            "tenant_code",
            "system_code",
            "connection_code",
            "object_schema",
            "object_name",
        )
    )


__all__ = ["SubjectAreaCandidateValidator"]
