"""Deterministic local-fake Subject Area answers."""

from __future__ import annotations

from typing import cast

from gds_etl_workbench.domain.errors import InvalidRequestError
from pydantic import JsonValue


def fake_subject_area_candidate(*, scope_tables: tuple[dict[str, JsonValue], ...]) -> JsonValue:
    """Group tables in table_index order, four per area; neighbouring areas share one table."""
    table_ids: list[JsonValue] = []
    for table in scope_tables:
        table_id = table.get("table")
        if not isinstance(table_id, str):
            raise InvalidRequestError("The local fake agent context is invalid.")
        table_ids.append(table_id)
    areas: list[dict[str, JsonValue]] = []
    start = 0
    while start < len(table_ids):
        areas.append(
            {
                "name": f"Business Area {len(areas) + 1}",
                "definition": "A locally generated Subject Area over related Input Scope tables.",
                "tables": table_ids[start : start + 4],
            }
        )
        if start + 4 >= len(table_ids):
            break
        start += 3
    return cast(JsonValue, {"areas": areas, "unassigned": [], "retire": []})
