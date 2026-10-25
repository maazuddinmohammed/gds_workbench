"""Reject unusable startup contexts before they consume durable claim recovery."""

# pyright: reportPrivateUsage=false

from collections.abc import Iterator
from dataclasses import replace

import pytest
from gds_workbench_api.database import WebPostgresDatabase
from gds_workbench_api.features.workflows.authoring.lifecycle import (
    DatabaseAgentWorkflowLifecycle,
)
from gds_workbench_api.features.workflows.execution import (
    DatabaseWorkflowClaimRepository,
    WorkerRunResult,
    WorkflowExecutionDispatcher,
    WorkflowExecutionWorker,
)
from gds_workbench_api.features.workflows.usage.service import DatabaseWorkflowUsageRecorder
from test_workflow_execution_dispatcher import _services

from tests.mcp.conftest import DisposablePostgres, disposable_postgres
from tests.mcp.database_test_support import require_row
from tests.mcp.test_database_workflow_run_lifecycle import seed_workflow_context
from tests.web_backend.test_database_workflow_run_claims import _create_run, _expire_claim


@pytest.fixture
def startup_postgres_database() -> Iterator[DisposablePostgres]:
    # An intentionally unclaimable run must not leak into the next scenario's queue.
    yield from disposable_postgres()


@pytest.mark.asyncio
@pytest.mark.parametrize("claim_state", ["unclaimed", "live", "expired"])
@pytest.mark.parametrize(
    ("guard", "failure_code", "failure_message"),
    [
        (
            "revision",
            "workflow_run_revision_stale",
            "Project changed after this Workflow Run started. Start a new run.",
        ),
        (
            "lock",
            "workflow_run_authorization_unavailable",
            "Workflow Run requires current write access and its owner’s Tenant Lock. "
            "Restore access and start a new run.",
        ),
    ],
)
async def test_startup_guards_fail_before_dispatch_but_preserve_live_claims(
    startup_postgres_database: DisposablePostgres,
    guard: str,
    failure_code: str,
    failure_message: str,
    claim_state: str,
) -> None:
    live_claim = claim_state == "live"
    context = seed_workflow_context(startup_postgres_database)
    with startup_postgres_database.connect_owner() as connection:
        run_id = _create_run(connection, context, start=True)

    database = WebPostgresDatabase(
        dsn=startup_postgres_database.web_runtime_dsn(),
        pool_min=1,
        pool_max=2,
        pool_timeout_seconds=5,
    )
    claims = DatabaseWorkflowClaimRepository(database=database)
    services, executors = _services()
    services = replace(
        services,
        usage_recorder=DatabaseWorkflowUsageRecorder(database=database),
        lifecycle=DatabaseAgentWorkflowLifecycle(database=database),
    )
    worker = WorkflowExecutionWorker(
        claims=claims,
        dispatcher=WorkflowExecutionDispatcher(services),
        lease_duration_seconds=30,
        heartbeat_interval_seconds=10,
    )
    await database.open()
    try:
        if claim_state != "unclaimed":
            claim = await claims.claim_next(lease_duration_seconds=300)
            assert claim is not None and claim.workflow_run_id == run_id
        with startup_postgres_database.connect_owner() as connection:
            if claim_state == "expired":
                _expire_claim(connection, run_id)
            if guard == "revision":
                connection.execute(
                    "UPDATE project.project SET project_revision = project_revision + 1 "
                    "WHERE project_id = %s",
                    (context.project_id,),
                )
            else:
                connection.execute(
                    "UPDATE security.tenant_lock SET "
                    "tenant_lock_acquired_time = clock_timestamp() - INTERVAL '2 minutes', "
                    "tenant_lock_expires_time = clock_timestamp() - INTERVAL '1 second' "
                    "WHERE tenant_id = %s",
                    (context.tenant_id,),
                )

        outcome = await worker.run_once()
    finally:
        await database.close()

    assert not any(executor.calls for executor in executors.values())
    assert outcome is WorkerRunResult.IDLE
    with startup_postgres_database.connect_owner() as connection:
        run = require_row(
            connection.execute(
                "SELECT workflow_run_state, failure_code, failure_message, "
                "workflow_run_recovery_count, usage_tracking_version, "
                "workflow_run_claim_token_digest IS NOT NULL AS has_claim "
                "FROM application.workflow_run WHERE workflow_run_id = %s",
                (run_id,),
            ).fetchone()
        )
        events = connection.execute(
            "SELECT project_event_log_status, project_event_log_message "
            "FROM project.project_event_log WHERE workflow_run_id = %s "
            "ORDER BY project_event_log_sequence",
            (run_id,),
        ).fetchall()
    assert run == {
        "workflow_run_state": "running" if live_claim else "failed",
        "failure_code": None if live_claim else failure_code,
        "failure_message": None if live_claim else failure_message,
        "workflow_run_recovery_count": 0,
        "usage_tracking_version": None,
        "has_claim": live_claim,
    }
    assert [event["project_event_log_status"] for event in events] == (
        ["started"] if live_claim else ["started", "failed"]
    )
    if not live_claim:
        assert events[-1]["project_event_log_message"] == failure_message


@pytest.mark.asyncio
async def test_valid_startup_still_tracks_usage_and_dispatches_its_executor(
    startup_postgres_database: DisposablePostgres,
) -> None:
    context = seed_workflow_context(startup_postgres_database)
    with startup_postgres_database.connect_owner() as connection:
        run_id = _create_run(connection, context, start=True)
    database = WebPostgresDatabase(
        dsn=startup_postgres_database.web_runtime_dsn(),
        pool_min=1,
        pool_max=2,
        pool_timeout_seconds=5,
    )
    services, executors = _services()
    services = replace(
        services,
        usage_recorder=DatabaseWorkflowUsageRecorder(database=database),
        lifecycle=DatabaseAgentWorkflowLifecycle(database=database),
    )
    worker = WorkflowExecutionWorker(
        claims=DatabaseWorkflowClaimRepository(database=database),
        dispatcher=WorkflowExecutionDispatcher(services),
        lease_duration_seconds=30,
        heartbeat_interval_seconds=10,
    )
    await database.open()
    try:
        assert await worker.run_once() is WorkerRunResult.COMPLETED
    finally:
        await database.close()
    assert [name for name, executor in executors.items() if executor.calls] == ["subject_area"]
    assert executors["subject_area"].calls[0]["workflow_run_id"] == run_id
    with startup_postgres_database.connect_owner() as connection:
        usage = require_row(
            connection.execute(
                "SELECT usage_tracking_version, usage_tracked_recovery_count "
                "FROM application.workflow_run WHERE workflow_run_id = %s",
                (run_id,),
            ).fetchone()
        )
    assert usage == {"usage_tracking_version": 1, "usage_tracked_recovery_count": 0}
