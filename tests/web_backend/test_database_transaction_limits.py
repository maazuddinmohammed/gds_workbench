"""Web transactions end stuck waits instead of hanging; disposable fixture only."""

# Reuse fixture-only setup helpers.
# pyright: reportPrivateUsage=false

import asyncio
from collections.abc import Iterator
from pathlib import Path
from typing import LiteralString, cast

import pytest
from gds_workbench_api import database as database_module
from gds_workbench_api.database import WebPostgresDatabase
from gds_workbench_api.features.workflows.execution import (
    DatabaseWorkflowClaimRepository,
    WorkerRunResult,
    WorkflowClaimRunner,
    WorkflowExecutionClaim,
)
from gds_workbench_api.features.workflows.execution.fence import assert_workflow_run_claim
from gds_workbench_api.features.workflows.execution.worker import workflow_failure_category

from tests.mcp.conftest import DisposablePostgres, disposable_postgres
from tests.web_backend.test_database_workflow_usage import _run

APPLICATION_REFERENCE_SEED = (
    Path(__file__).parents[2] / "database" / "seed" / "04_application_reference.sql"
)


@pytest.fixture(scope="module")
def limits_postgres() -> Iterator[DisposablePostgres]:
    for database in disposable_postgres():
        with database.connect_owner() as connection:
            connection.execute(
                cast(LiteralString, APPLICATION_REFERENCE_SEED.read_text(encoding="utf-8"))
            )
        yield database


@pytest.mark.asyncio
async def test_every_web_transaction_bounds_lock_statement_and_idle_waits(
    limits_postgres: DisposablePostgres,
) -> None:
    database = WebPostgresDatabase(
        dsn=limits_postgres.web_runtime_dsn(), pool_min=1, pool_max=1, pool_timeout_seconds=5
    )
    await database.open()
    try:
        for open_transaction in (database.read_transaction, database.write_transaction):
            async with open_transaction() as transaction:
                limits = await transaction.fetch_one(
                    "SELECT current_setting('lock_timeout') AS lock_wait, "
                    "current_setting('statement_timeout') AS statement, "
                    "current_setting('idle_in_transaction_session_timeout') AS idle"
                )
            assert limits == {"lock_wait": "1min", "statement": "10min", "idle": "5min"}
    finally:
        await database.close()


@pytest.mark.asyncio
async def test_heartbeat_ends_a_held_run_lock_wait_with_a_contention_error(
    limits_postgres: DisposablePostgres,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Shorten only the lock wait so the test is quick; production uses the same mechanism.
    monkeypatch.setattr(
        database_module,
        "_TRANSACTION_LIMITS_SQL",
        database_module._TRANSACTION_LIMITS_SQL.replace("'60s'", "'1s'"),
    )
    _, claim, runtime = _run(limits_postgres, workflow="profiling")
    claims = DatabaseWorkflowClaimRepository(database=runtime)
    await runtime.open()
    try:
        # An uncommitted holder of the Run row previously blocked renewal indefinitely.
        with limits_postgres.connect_owner() as holder:
            holder.execute(
                "SELECT 1 FROM application.workflow_run WHERE workflow_run_id=%s FOR UPDATE",
                (claim.workflow_run_id,),
            )
            with pytest.raises(Exception) as failure:
                await asyncio.wait_for(
                    claims.renew(
                        workflow_run_id=claim.workflow_run_id,
                        workflow_run_claim_token=claim.workflow_run_claim_token,
                        lease_duration_seconds=30,
                    ),
                    timeout=15,
                )
            holder.rollback()
        assert workflow_failure_category(failure.value) == "database_contention"

        lease = await claims.renew(
            workflow_run_id=claim.workflow_run_id,
            workflow_run_claim_token=claim.workflow_run_claim_token,
            lease_duration_seconds=30,
        )
        assert lease.workflow_run_id == claim.workflow_run_id
    finally:
        await runtime.close()


@pytest.mark.asyncio
async def test_long_fenced_write_does_not_cost_the_run_its_live_claim(
    limits_postgres: DisposablePostgres,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Draft staging and validation hold the Run row while the heartbeat waits for it.
    monkeypatch.setattr(
        database_module,
        "_TRANSACTION_LIMITS_SQL",
        database_module._TRANSACTION_LIMITS_SQL.replace("'60s'", "'1s'"),
    )
    _, claim, _ = _run(limits_postgres, workflow="profiling")
    database = WebPostgresDatabase(
        dsn=limits_postgres.web_runtime_dsn(), pool_min=2, pool_max=2, pool_timeout_seconds=5
    )

    class LongFencedWrite:
        async def execute(self, claim: WorkflowExecutionClaim) -> object:
            async with database.write_transaction() as transaction:
                await assert_workflow_run_claim(
                    transaction,
                    workflow_run_id=claim.workflow_run_id,
                    workflow_run_claim_token=claim.workflow_run_claim_token,
                )
                await asyncio.sleep(3)
            return object()

    runner = WorkflowClaimRunner(
        claims=DatabaseWorkflowClaimRepository(database=database),
        dispatcher=LongFencedWrite(),
        lease_duration_seconds=30,
        heartbeat_interval_seconds=0.5,
    )
    await database.open()
    try:
        assert await asyncio.wait_for(runner.run(claim), timeout=20) is (WorkerRunResult.COMPLETED)
    finally:
        await database.close()
