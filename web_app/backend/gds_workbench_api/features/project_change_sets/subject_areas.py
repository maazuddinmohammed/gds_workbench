"""Human Subject Area edits as one validated Change Set: never deletes, keeps locks."""

from collections.abc import Mapping
from typing import Any

from gds_etl_workbench.application.change_sets.project_validation import (
    PhysicalProjectCatalog,
    ValidatedProjectChangeSet,
    validate_future_graph,
)
from gds_etl_workbench.application.project_snapshot import ProjectReviewSnapshot
from gds_etl_workbench.domain.errors import InvalidRequestError, WorkbenchError
from gds_etl_workbench.domain.modeling_records import (
    SubjectAreaRecord,
    SubjectAreaTableRecord,
    normalize_project_key_value,
)

from .contracts import SaveSubjectAreaRequest

_OBJECT_FIELDS = ("tenant_code", "system_code", "connection_code", "object_schema", "object_name")


def prepare_subject_area_change(
    review: ProjectReviewSnapshot,
    command: SaveSubjectAreaRequest,
    scope_tables: Mapping[int, Mapping[str, Any]],
    physical_scope: PhysicalProjectCatalog,
) -> ValidatedProjectChangeSet:
    """Build the area and membership records for one change, then validate the graph.

    A rename creates the new area, moves every active table to it and keeps the old area
    inactive, so history is never deleted.
    """
    areas = {
        normalize_project_key_value(record.subject_area_name): record
        for record in review.snapshot.subject_area.areas
    }
    members = review.snapshot.subject_area.tables
    saved: SubjectAreaRecord | None = None
    if command.subject_area_id is not None:
        record = review.records_by_id.get("subject_area", {}).get(command.subject_area_id)
        if not isinstance(record, SubjectAreaRecord):
            raise WorkbenchError("project_record_not_found", "This Subject Area is unavailable.")
        saved = record
        if saved.subject_area_is_locked:
            raise WorkbenchError("record_locked", "Unlock this Subject Area before editing it.")
    name = command.subject_area_name or (saved.subject_area_name if saved else "")
    key = normalize_project_key_value(name)
    renamed = saved is not None and key != normalize_project_key_value(saved.subject_area_name)
    if (saved is None or renamed) and key in areas:
        raise WorkbenchError(
            "subject_area_name_conflict",
            "A Subject Area with this name already exists, possibly inactive. "
            "Choose another name or reactivate that area.",
        )
    if any(
        object_id not in scope_tables or not scope_tables[object_id]["is_addable"]
        for object_id in command.add_object_ids
    ):
        raise WorkbenchError(
            "subject_area_table_unavailable", "Add only active Bronze Input Scope tables."
        )

    # Saving keeps an area's lifecycle; adding tables makes an inactive area active again.
    area_records: list[dict[str, object]] = [
        {
            "subject_area_name": name,
            "subject_area_definition": command.subject_area_definition
            or (saved.subject_area_definition if saved else ""),
            "subject_area_status": "active"
            if saved is None or command.add_object_ids
            else saved.subject_area_status,
            "subject_area_is_locked": False,
        }
    ]
    table_records: dict[tuple[str, ...], dict[str, object]] = {}
    saved_members = (
        [
            member
            for member in members
            if normalize_project_key_value(member.subject_area_name)
            == normalize_project_key_value(saved.subject_area_name)
        ]
        if saved is not None
        else []
    )
    removed_keys = {
        _object_key(scope_tables[object_id])
        for object_id in command.remove_object_ids
        if object_id in scope_tables
    }
    if len(removed_keys) != len(command.remove_object_ids):
        raise InvalidRequestError("Remove only tables in this Subject Area.")
    for member in saved_members:
        member_key = _object_key(member.model_dump(mode="json"))
        if member_key in removed_keys:
            if member.subject_area_table_is_locked:
                raise WorkbenchError("record_locked", "Unlock this table before removing it.")
            table_records[member_key] = _member(member, status="inactive")
            removed_keys.discard(member_key)
        elif renamed and member.subject_area_table_status == "active":
            if member.subject_area_table_is_locked:
                raise WorkbenchError(
                    "record_locked", "Unlock this area's tables before renaming it."
                )
            # The old area keeps its history; the new area takes the active tables.
            table_records[("old", *member_key)] = _member(member, status="inactive")
            table_records[member_key] = {
                **_member(member, status="active"),
                "subject_area_name": name,
            }
    if removed_keys:
        raise InvalidRequestError("Remove only tables in this Subject Area.")
    for object_id in command.add_object_ids:
        table = scope_tables[object_id]
        member_key = _object_key(table)
        previous = next(
            (
                member
                for member in saved_members
                if _object_key(member.model_dump(mode="json")) == member_key
            ),
            None,
        )
        if (
            previous is not None
            and previous.subject_area_table_is_locked
            and previous.subject_area_table_status != "active"
        ):
            raise WorkbenchError(
                "record_locked", "Unlock this table before adding it back to the area."
            )
        table_records[member_key] = {
            "subject_area_name": name,
            **{field: table[field] for field in _OBJECT_FIELDS},
            "subject_area_table_status": "active",
            "subject_area_table_is_locked": (
                previous.subject_area_table_is_locked if previous is not None else False
            ),
        }
    if saved is not None and renamed:
        area_records.append({**saved.model_dump(mode="json"), "subject_area_status": "inactive"})
    elif saved is not None:
        area_records[0]["subject_area_is_locked"] = saved.subject_area_is_locked
    validation = validate_future_graph(
        snapshot=review.snapshot,
        staged_documents={
            "subject_area": area_records,
            "subject_area_table": list(table_records.values()),
        },
        physical_scope=physical_scope,
    )
    if not validation.valid or validation.candidate_digest is None:
        raise InvalidRequestError(
            "This Subject Area change conflicts with locked records or Input Scope. "
            "Refresh and review the area before saving."
        )
    return validation


def _member(member: SubjectAreaTableRecord, *, status: str) -> dict[str, object]:
    return {**member.model_dump(mode="json"), "subject_area_table_status": status}


def _object_key(values: Mapping[str, Any]) -> tuple[str, ...]:
    return tuple(normalize_project_key_value(str(values[field])) for field in _OBJECT_FIELDS)


__all__ = ["prepare_subject_area_change"]
