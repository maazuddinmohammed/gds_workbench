"""One-run diagnostics expose bounded metadata under a SELECT-only fixture role."""

# pyright: reportPrivateUsage=false
from collections.abc import Iterator
from pathlib import Path
from typing import Any, LiteralString, cast

import pytest
from gds_workbench_api.features.workflows.authoring.lifecycle import (
    AgentWorkflowEvent,
    DatabaseAgentWorkflowLifecycle,
)
from gds_workbench_api.features.workflows.usage.service import DatabaseWorkflowUsageRecorder
from psycopg.pq import TransactionStatus

from tests.mcp.conftest import DisposablePostgres, disposable_postgres
from tests.web_backend.test_database_workflow_usage import _run

INSPECT_SQL = (
    Path(__file__).parents[2] / "deployment/databricks_ui/inspect_workflow_recovery.sql"
).read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def recovery_diagnostic_database() -> Iterator[DisposablePostgres]:
    for database in disposable_postgres():
        with database.connect_owner() as connection:
            connection.execute("CREATE ROLE fixture_recovery_reader NOLOGIN")
            connection.execute(
                "GRANT USAGE ON SCHEMA application, project TO fixture_recovery_reader"
            )
            connection.execute(
                "GRANT SELECT ON application.workflow_run, project.project_event_log "
                "TO fixture_recovery_reader"
            )
        yield database


def _inspect(
    database: DisposablePostgres, *, run_id: int, tenant_id: int, project_id: int
) -> dict[str, Any]:
    # Only fixture-produced integers replace the documented filter, never SQL text.
    statement = INSPECT_SQL.replace(
        "VALUES (18::BIGINT, 2::BIGINT, 4::BIGINT)",
        f"VALUES ({run_id:d}::BIGINT, {tenant_id:d}::BIGINT, {project_id:d}::BIGINT)",
    )
    with database.connect_owner() as connection:
        connection.execute("SET ROLE fixture_recovery_reader")
        permission = connection.execute(
            "SELECT NOT EXISTS (SELECT 1 FROM pg_proc AS proc "
            "JOIN pg_namespace AS namespace ON namespace.oid=proc.pronamespace "
            "WHERE namespace.nspname='application' "
            "AND has_function_privilege(current_user,proc.oid,'EXECUTE')) AS no_functions"
        ).fetchone()
        assert permission == {"no_functions": True}
        connection.commit()
        connection.autocommit = True
        cursor = connection.execute(cast(LiteralString, statement), prepare=False)
        rows: list[dict[str, Any]] = []
        while True:
            if cursor.description is not None:
                rows.extend(cursor.fetchall())
            if not cursor.nextset():
                break
        assert connection.info.transaction_status is TransactionStatus.IDLE
    assert len(rows) == 1
    assert rows[0]["read_only_transaction"] is True
    return rows[0]


async def test_recovery_diagnostic_reports_boundaries_without_raw_data_or_function_calls(
    recovery_diagnostic_database: DisposablePostgres,
) -> None:
    context, claim, runtime = _run(recovery_diagnostic_database, workflow="profiling")
    filters = {
        "run_id": claim.workflow_run_id,
        "tenant_id": context.tenant_id,
        "project_id": context.project_id,
    }
    initial = _inspect(recovery_diagnostic_database, **filters)
    assert initial["run_found"] and initial["state"] == "running"
    assert initial["claim_present"] and initial["claim_unexpired"]
    assert initial["recovery_count"] == 0
    assert initial["usage_tracking_version"] is None
    assert initial["profiling_prepare_event_count"] == 0
    assert initial["heartbeat_seconds_after_claim"] == 0
    assert initial["lease_seconds_remaining"] > 0

    await runtime.open()
    try:
        async with DatabaseWorkflowUsageRecorder(database=runtime).track_run(claim):
            pass
        initialized = _inspect(recovery_diagnostic_database, **filters)
        assert initialized["usage_tracking_version"] == 1
        assert initialized["usage_tracked_recovery_count"] == 0
        assert initialized["profiling_prepare_event_count"] == 0
        lifecycle = DatabaseAgentWorkflowLifecycle(database=runtime)
        for sequence, stage in enumerate(
            ["profiling.prepare", "profiling.execute", "profiling.persist"], start=2
        ):
            await lifecycle.append_event(
                claim.principal,
                workflow_run_id=claim.workflow_run_id,
                expected_project_revision=claim.project_revision,
                workflow_run_claim_token=claim.workflow_run_claim_token,
                event=AgentWorkflowEvent(
                    sequence=sequence,
                    attempt=1,
                    stage=stage,
                    status="running",
                    message="Fixture event content must stay private",
                    finding_count=0,
                ),
            )
        await lifecycle.fail(
            claim.principal,
            workflow_run_id=claim.workflow_run_id,
            expected_project_revision=claim.project_revision,
            workflow_run_claim_token=claim.workflow_run_claim_token,
            failure_code="workflow_run_recovery_exhausted",
            safe_failure_message="Fixture failure content must stay private",
        )
    finally:
        await runtime.close()

    terminal = _inspect(recovery_diagnostic_database, **filters)
    assert terminal["state"] == "failed" and terminal["recovery_exhausted"]
    assert not terminal["claim_present"] and terminal["claim_unexpired"] is None
    assert terminal["seconds_since_claim"] is None
    assert terminal["seconds_since_heartbeat"] is None
    assert terminal["lease_seconds_remaining"] is None
    assert terminal["run_seconds"] >= 0
    assert terminal["total_event_count"] == 5
    assert terminal["lifecycle_event_count"] == 2
    assert terminal["profiling_prepare_event_count"] == 1
    assert terminal["profiling_execute_event_count"] == 1
    assert terminal["other_stage_event_count"] == 1
    assert set(terminal) == {
        "read_only_transaction",
        "run_found",
        "workflow",
        "state",
        "recovery_exhausted",
        "recovery_count",
        "run_seconds",
        "claim_present",
        "claim_unexpired",
        "seconds_since_claim",
        "heartbeat_seconds_after_claim",
        "seconds_since_heartbeat",
        "lease_seconds_remaining",
        "usage_tracking_version",
        "usage_tracked_recovery_count",
        "usage_history_incomplete",
        "total_event_count",
        "lifecycle_event_count",
        "profiling_prepare_event_count",
        "profiling_execute_event_count",
        "other_stage_event_count",
    }
    assert "content must stay private" not in str(terminal)
    for mismatch in ({"tenant_id": context.tenant_id + 1}, {"project_id": context.project_id + 1}):
        missing = _inspect(recovery_diagnostic_database, **(filters | mismatch))
        assert not missing["run_found"] and missing["state"] is None
        assert missing["total_event_count"] == 0
