"""Web full-graph reads bypass export ceilings; MCP defaults retain them."""

# pyright: reportPrivateUsage=false
from typing import Any, LiteralString, cast

import pytest
from gds_etl_workbench.application.model_read import ModelReadContext
from gds_etl_workbench.application.model_snapshot import build_model_snapshot
from gds_etl_workbench.domain.errors import InvalidRequestError
from gds_etl_workbench.infrastructure.postgres import ReadTransaction
from gds_workbench_api.features.workflows.authoring.context import PostgresAgentContextRepository

from tests.mcp.model_test_fixtures import model_details, model_input_scope_records


class SnapshotRows:
    def __init__(self, *, rows_per_dataset: int, include_total: bool) -> None:
        self.limits: list[object] = []
        self.datasets: dict[str, list[dict[str, Any]]] = {}
        for layer in ("logical", "dimensional") if include_total else ("logical",):
            self.datasets[f"workflow.{layer}_submodel AS submodel"] = [
                {
                    f"{layer}_submodel_id": index + 1,
                    f"{layer}_submodel_name": f"Submodel {index}",
                    f"{layer}_submodel_definition": "Synthetic definition",
                    f"{layer}_submodel_status": "active",
                    f"{layer}_submodel_is_locked": False,
                }
                for index in range(rows_per_dataset)
            ]
        if include_total:
            scope = model_input_scope_records()[0]
            self.datasets["model.model_input_scope AS scope"] = [
                {**scope, "object_name": f"Object {index}"} for index in range(rows_per_dataset)
            ]

    async def fetch_all(
        self, query: LiteralString, parameters: tuple[Any, ...] = ()
    ) -> list[dict[str, Any]]:
        if "FROM model.model AS target_model" in query:
            return [model_details()]
        assert "LIMIT %s" in query
        limit = parameters[-2] if "OFFSET %s" in query else parameters[-1]
        self.limits.append(limit)
        empty: list[dict[str, Any]] = []
        rows = next(
            (rows for fragment, rows in self.datasets.items() if f"FROM {fragment}" in query), empty
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
    model = ModelReadContext(model_id=18, tenant_id=7, model_name="SalesModel", model_revision=1)
    transaction = SnapshotRows(rows_per_dataset=rows_per_dataset, include_total=include_total)
    with pytest.raises(InvalidRequestError, match=error):
        await build_model_snapshot(cast(ReadTransaction, transaction), model)
    assert all(limit == 20_001 for limit in transaction.limits)

    transaction.limits.clear()
    web_loader = PostgresAgentContextRepository()._snapshot_loader
    snapshot = await web_loader(cast(ReadTransaction, transaction), model)
    assert len(snapshot.logical.submodels) == rows_per_dataset
    if include_total:
        assert len(snapshot.dimensional.submodels) == rows_per_dataset
        assert len(snapshot.model_input_scope.objects) == rows_per_dataset
    assert transaction.limits and all(limit is None for limit in transaction.limits)


@pytest.mark.asyncio
async def test_unlimited_web_snapshot_still_rejects_duplicate_canonical_keys() -> None:
    transaction = SnapshotRows(rows_per_dataset=2, include_total=False)
    rows = transaction.datasets["workflow.logical_submodel AS submodel"]
    rows[1]["logical_submodel_name"] = rows[0]["logical_submodel_name"]
    with pytest.raises(InvalidRequestError, match="duplicate canonical key"):
        await build_model_snapshot(
            cast(ReadTransaction, transaction),
            ModelReadContext(model_id=18, tenant_id=7, model_name="SalesModel", model_revision=1),
            enforce_row_limits=False,
        )
