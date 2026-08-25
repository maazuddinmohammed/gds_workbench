"""Small typing helpers shared by PostgreSQL integration tests."""

from __future__ import annotations


def require_row[RowT](row: RowT | None) -> RowT:
    """Return an expected query row or fail at the query boundary."""
    if row is None:
        raise AssertionError("expected database query to return one row")
    return row
