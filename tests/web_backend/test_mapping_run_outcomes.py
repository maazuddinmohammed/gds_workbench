"""Bounded Mapping coverage reads without interpreting event prose."""

# pyright: reportPrivateUsage=false
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from typing import Any, LiteralString
from uuid import UUID

import pytest
from gds_etl_workbench.application.authorization import AuthorizationService
from gds_etl_workbench.domain.authorization import ActorKind, RequestPrincipal
from gds_etl_workbench.infrastructure.postgres import ReadIsolation, ReadTransaction
from gds_workbench_api.features.workflows.overview.contracts import WorkflowMetric
from gds_workbench_api.features.workflows.overview.service import _section_state
from gds_workbench_api.features.workflows.runs import service as run_service
from gds_workbench_api.features.workflows.runs.contracts import MappingRunOutcome, RunState
from gds_workbench_api.features.workflows.usage.read_service import WorkflowTokenUsageSummary


class MappingRunTransaction:
    def __init__(self, *, failure_count: int = 1, run_state: RunState = "completed") -> None:
        self.failure_count = failure_count
        self.run_state = run_state
        self.failure_reads = 0
        self.summary_run_ids: list[int] = []

    def run_row(self, *, run_id: int = 1048, workflow: str = "mapping") -> dict[str, Any]:
        return {
            "workflow_run_id": run_id,
            "model_workflow": workflow,
            "workflow_run_state": self.run_state,
            "selected_scope_count": 2,
            "actor_display_name": "Reviewer",
            "created_at": datetime(2026, 9, 28, tzinfo=UTC),
        }

    async def fetch_one(
        self, query: LiteralString, parameters: tuple[Any, ...] = ()
    ) -> dict[str, Any] | None:
        if "security.entra_principal_identity" in query:
            assert parameters[-1] == 7
            return {
                "principal_id": 41,
                "principal_display_name": "Reviewer",
                "is_super_admin": False,
                "effective_role": "tenant_admin",
                "authorized": True,
                "denial_code": None,
                "lock_owner_display_name": None,
                "lock_expires_time": None,
            }
        if query == run_service._MODEL_EXISTS_SQL:
            assert parameters == (7, 18)
            return {"model_id": 18}
        assert query == run_service._RUN_DETAIL_SQL
        assert parameters == (7, 18, 1048)
        return {
            **self.run_row(),
            "correlation_id": UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"),
        }

    async def fetch_all(
        self, query: LiteralString, parameters: tuple[Any, ...] = ()
    ) -> list[dict[str, Any]]:
        if "SELECT DISTINCT object.source_tenant_id" in query:
            return []
        if "core.tenant AS tenant" in query and "effective_role" in query:
            return []
        if query == run_service._RUNS_SQL:
            assert parameters[:2] == (7, 18)
            return [
                self.run_row(),
                self.run_row(run_id=1049, workflow="logical"),
                self.run_row(run_id=1050),  # Pagination lookahead is not projected.
            ]
        assert parameters == (7, 18, [1048])
        if query == run_service._MAPPING_SUMMARIES_SQL:
            self.summary_run_ids = parameters[2]
            if self.failure_count < 0:
                return []  # Legacy Run without typed pair outcomes.
            return [{
                "workflow_run_id": 1048,
                "completed_pair_count": 0 if self.run_state == "failed" else 1,
                "preserved_pair_count": 0,
                "no_source_pair_count": 0,
                "failed_pair_count": self.failure_count,
            }]
        assert query == run_service._MAPPING_FAILURES_SQL
        self.failure_reads += 1
        return [
            {
                "source_system_id": 2,
                "system_code": "CRM",
                "modeled_entity_id": index + 10,
                "entity_schema_name": "silver",
                "entity_name": f"Entity{index}",
                "message": "Required source evidence is unavailable.",
            }
            for index in range(min(self.failure_count, 201))
        ]


class MappingRunDatabase:
    def __init__(self, transaction: MappingRunTransaction) -> None:
        self.transaction = transaction

    @asynccontextmanager
    async def read_transaction(
        self, *, isolation: ReadIsolation = ReadIsolation.READ_COMMITTED
    ) -> AsyncGenerator[MappingRunTransaction]:
        assert isolation is ReadIsolation.REPEATABLE_READ
        yield self.transaction


def _service(transaction: MappingRunTransaction) -> run_service.DatabaseWorkflowRunService:
    return run_service.DatabaseWorkflowRunService(
        database=MappingRunDatabase(transaction),
        authorizer=AuthorizationService(),
        cursor_signing_key=b"mapping-read-fixture-only-key-32-bytes",
    )


def _principal() -> RequestPrincipal:
    return RequestPrincipal(
        actor_kind=ActorKind.HUMAN,
        entra_tenant_id=UUID("11111111-1111-1111-1111-111111111111"),
        entra_object_id=UUID("22222222-2222-2222-2222-222222222222"),
    )


async def _usage(
    transaction: ReadTransaction, *, tenant_id: int, model_id: int, workflow_run_id: int
) -> WorkflowTokenUsageSummary:
    assert (tenant_id, model_id, workflow_run_id) == (7, 18, 1048)
    return WorkflowTokenUsageSummary()


@pytest.mark.asyncio
async def test_ledger_projects_coverage_only_for_mapping_runs_on_the_requested_page() -> None:
    transaction = MappingRunTransaction()
    result = await _service(transaction).list_runs(
        _principal(), tenant_id=7, model_id=18, workflow=None,
        run_state=None, page_size=2, cursor=None,
    )
    assert result.next_cursor is not None
    assert len(result.items) == 2
    assert transaction.summary_run_ids == [1048]
    assert result.items[0].mapping_outcome == MappingRunOutcome(
        completed_pair_count=1, preserved_pair_count=0, no_source_pair_count=0, failed_pair_count=1,
    )
    assert result.items[1].mapping_outcome is None
    assert transaction.failure_reads == 0


@pytest.mark.asyncio
@pytest.mark.parametrize("state", ["completed", "failed"])
async def test_detail_exposes_bounded_failed_pairs_for_partial_and_all_failed_runs(
    monkeypatch: pytest.MonkeyPatch, state: RunState,
) -> None:
    monkeypatch.setattr(run_service, "read_run_token_usage", _usage)
    transaction = MappingRunTransaction(failure_count=205, run_state=state)
    detail = await _service(transaction).read_run(
        _principal(), tenant_id=7, model_id=18, workflow_run_id=1048,
    )
    assert detail.mapping_outcome is not None
    assert detail.mapping_outcome.failed_pair_count == 205
    assert len(detail.mapping_failures) == 200
    assert detail.mapping_failures_truncated
    assert detail.mapping_failures[0].model_dump() == {
        "source_system_id": 2,
        "system_code": "CRM",
        "modeled_entity_id": 10,
        "entity_schema_name": "silver",
        "entity_name": "Entity0",
        "message": "Required source evidence is unavailable.",
    }


@pytest.mark.asyncio
async def test_legacy_run_has_no_inferred_mapping_outcome(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(run_service, "read_run_token_usage", _usage)
    transaction = MappingRunTransaction(failure_count=-1)
    detail = await _service(transaction).read_run(
        _principal(), tenant_id=7, model_id=18, workflow_run_id=1048,
    )
    assert detail.mapping_outcome is None
    assert detail.mapping_failures == ()
    assert not detail.mapping_failures_truncated
    assert transaction.failure_reads == 0


@pytest.mark.parametrize("run_state", ["completed", "completed_with_repair", "running", "failed"])
@pytest.mark.parametrize("result_count", [0, 1])
def test_partial_mapping_ribbon_does_not_claim_complete_coverage(
    run_state: RunState, result_count: int,
) -> None:
    metric = WorkflowMetric(
        model_id=18, model_revision=4, workflow="mapping", result_count=result_count,
        locked_count=0, latest_run_state=run_state,
    )
    outcome = MappingRunOutcome(
        completed_pair_count=1, preserved_pair_count=0, no_source_pair_count=0, failed_pair_count=1,
    )
    assert _section_state(metric, mapping_outcome=outcome) == (
        run_state if run_state in ("running", "failed") else "results_available"
    )
