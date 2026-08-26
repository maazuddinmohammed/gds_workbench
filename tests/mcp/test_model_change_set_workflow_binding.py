from __future__ import annotations

from collections.abc import Callable, Mapping
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest

from gds_etl_workbench.domain.errors import (
    InvalidRequestError,
    ModelChangeSetNotActiveError,
)
from gds_etl_workbench.tools.change_sets.model import (
    _EXPIRE_OWNED_SQL,
    _FIND_ONGOING_SQL,
    _require_mcp_writable_pending,
    _require_mutable,
)


def test_generic_mcp_draft_lookup_excludes_workflow_bound_change_sets() -> None:
    assert "workflow_run_id IS NULL" in _FIND_ONGOING_SQL
    assert "workflow_run_id IS NULL" in _EXPIRE_OWNED_SQL


@pytest.mark.parametrize("guard", [_require_mutable, _require_mcp_writable_pending])
def test_generic_mcp_mutations_reject_workflow_bound_change_sets(
    guard: Callable[[Mapping[str, Any]], None],
) -> None:
    row = {
        "workflow_run_id": 1048,
        "model_change_set_status": "active",
        "expires_time": datetime.now(UTC) + timedelta(hours=1),
        "conceptual_document": {},
        "profiling_document": {},
        "analysis_document": {},
        "assertion_document": {},
        "logical_document": {},
        "dimensional_document": {},
        "mapping_document": {},
        "model_scope_document": {},
    }

    with pytest.raises(InvalidRequestError, match="Workflow-bound"):
        guard(row)


def test_model_change_set_mutability_uses_the_database_expiry_decision() -> None:
    row = {
        "workflow_run_id": None,
        "model_change_set_status": "active",
        "is_expired": False,
        "expires_time": datetime.now(UTC) - timedelta(hours=1),
    }

    _require_mutable(row)

    row["is_expired"] = True
    with pytest.raises(ModelChangeSetNotActiveError):
        _require_mutable(row)
