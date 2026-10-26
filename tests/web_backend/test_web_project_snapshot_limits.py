"""Web full-graph reads bypass export ceilings; MCP defaults retain them."""

# pyright: reportPrivateUsage=false
from typing import Any, LiteralString, cast

import pytest
from gds_etl_workbench.application.project_read import ProjectReadContext
from gds_etl_workbench.application.project_snapshot import build_project_snapshot
from gds_etl_workbench.domain.errors import InvalidRequestError
from gds_etl_workbench.infrastructure.postgres import ReadTransaction
from tests.mcp.project_test_fixtures import project_details, project_input_scope_records

from gds_workbench_api.features.workflows.authoring.context import (
    PostgresAgentContextRepository,
)


class SnapshotRows:
    """Single-query datasets: Subject Areas, and for the total limit Validation Groups."""

    def __init__(self, *, rows_per_dataset: int, include_total: bool) -> None:
        self.limits: list[object] = []
        self.datasets: dict[str, list[dict[str, Any]]] = {
            "workflow.subject_area AS area": [
                {
                    "subject_area_id": index + 1,
                    "subject_area_name": f"Subject Area {index}",
                    "subject_area_definition": "Synthetic definition",
                    "subject_area_is_active": True,
                    "subject_area_is_locked": False,
                }
                for index in range(rows_per_dataset)
            ]
        }
        if include_total:
            self.datasets["workflow.validation_group AS validation_group"] = [
                {
                    "validation_group_id": index + 1,
                    "tenant_code": "TENANT-A",
                    "system_code": "ERP",
                    "validation_group_name": f"Group {index}",
                    "validation_group_description": None,
                    "is_active": True,
                    "is_locked": False,
                }
                for index in range(rows_per_dataset)
            ]
            scope = project_input_scope_records()[0]
            self.datasets["project.project_input_scope AS scope"] = [
                {**scope, "object_name": f"Object {index}"} for index in range(rows_per_dataset)
            ]

    async def fetch_all(
        self, query: LiteralString, parameters: tuple[Any, ...] = ()
    ) -> list[dict[str, Any]]:
        if "FROM project.project AS target_project" in query:
            return [project_details()]
        assert "LIMIT %s" in query
        limit = parameters[-2] if "OFFSET %s" in query else parameters[-1]
        self.limits.append(limit)
        empty: list[dict[str, Any]] = []
        rows = next(
            (rows for fragment, rows in self.datasets.items() if f"FROM {fragment}" in query),
            empty,
        )
        return rows[:limit] if isinstance(limit, int) else rows


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "rows_per_dataset,include_total,error",
    [(20_001, False, "dataset"), (17_000, True, "bounded row count")],
    ids=["dataset-limit", "total-limit"],
)
async def test_web_default_snapshot_loader_preserves_graph_above_mcp_export_limits(
    rows_per_dataset: int, include_total: bool, error: str
) -> None:
    project = ProjectReadContext(
        project_id=18, tenant_id=7, project_name="SalesProject", project_revision=1
    )
    transaction = SnapshotRows(rows_per_dataset=rows_per_dataset, include_total=include_total)
    with pytest.raises(InvalidRequestError, match=error):
        await build_project_snapshot(cast(ReadTransaction, transaction), project)
    assert all(limit == 20_001 for limit in transaction.limits)

    transaction.limits.clear()
    web_loader = PostgresAgentContextRepository()._snapshot_loader
    snapshot = await web_loader(cast(ReadTransaction, transaction), project)
    assert len(snapshot.subject_area.areas) == rows_per_dataset
    if include_total:
        assert len(snapshot.validation.groups) == rows_per_dataset
        assert len(snapshot.project_input_scope.objects) == rows_per_dataset
    assert transaction.limits and all(limit is None for limit in transaction.limits)


@pytest.mark.asyncio
async def test_unlimited_web_snapshot_still_rejects_duplicate_canonical_keys() -> None:
    transaction = SnapshotRows(rows_per_dataset=2, include_total=False)
    rows = transaction.datasets["workflow.subject_area AS area"]
    rows[1]["subject_area_name"] = rows[0]["subject_area_name"]
    with pytest.raises(InvalidRequestError, match="duplicate canonical key"):
        await build_project_snapshot(
            cast(ReadTransaction, transaction),
            ProjectReadContext(
                project_id=18,
                tenant_id=7,
                project_name="SalesProject",
                project_revision=1,
            ),
            enforce_row_limits=False,
        )
