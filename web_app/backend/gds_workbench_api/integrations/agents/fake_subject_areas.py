"""Deterministic local-fake Subject Area answers."""

from __future__ import annotations

from typing import cast

from gds_etl_workbench.domain.errors import InvalidRequestError
from pydantic import JsonValue


def fake_subject_area_candidate(
    *,
    scope_tables: tuple[dict[str, JsonValue], ...],
    max_columns: int,
) -> JsonValue:
    """Pack tables into areas in table_index order, each within the column cap."""
    areas: list[dict[str, JsonValue]] = []
    unassigned: list[JsonValue] = []
    current: list[JsonValue] = []
    columns = 0
    for table in scope_tables:
        table_id, count = table.get("table"), table.get("column_count")
        if not isinstance(table_id, str) or not isinstance(count, int):
            raise InvalidRequestError("The local fake agent context is invalid.")
        if count > max_columns:
            unassigned.append(table_id)
            continue
        if current and columns + count > max_columns:
            areas.append(_area(len(areas) + 1, current))
            current, columns = [], 0
        current.append(table_id)
        columns += count
    if current:
        areas.append(_area(len(areas) + 1, current))
    return cast(JsonValue, {"areas": areas, "unassigned": unassigned, "retire": []})


def _area(position: int, tables: list[JsonValue]) -> dict[str, JsonValue]:
    return {
        "name": f"Business Area {position}",
        "definition": "A locally generated Subject Area over related Input Scope tables.",
        "tables": tables,
    }
