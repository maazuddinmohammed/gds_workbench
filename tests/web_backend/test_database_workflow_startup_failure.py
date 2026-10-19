"""A startup error terminalizes only through the existing guarded lifecycle."""

# pyright: reportPrivateUsage=false

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from dataclasses import replace
from typing import Any, LiteralString

import pytest
from gds_etl_workbench.domain.errors import DependencyUnavailableError
from gds_etl_workbench.infrastructure.postgres import raise_postgres_error
from gds_workbench_api.features.workflows.authoring.lifecycle import (
    DatabaseAgentWorkflowLifecycle,
)
from gds_workbench_api.features.workflows.execution import WorkflowExecutionDispatcher
from gds_workbench_api.features.workflows.usage.service import (
    DatabaseWorkflowUsageRecorder,
)
from psycopg.errors import UndefinedFunction

from tests.mcp.conftest import DisposablePostgres
from tests.mcp.database_test_support import require_row
from tests.web_backend.test_database_workflow_usage import _run
from tests.web_backend.test_workflow_execution_dispatcher import _services


async def test_usage_startup_failure_is_saved_without_recovery_replays(
    web_postgres_database: DisposablePostgres,
) -> None:
    _, claim, runtime = _run(web_postgres_database)

    class UnavailableUsageDatabase:
        @asynccontextmanager
        async def write_transaction(self) -> AsyncGenerator[Any]:
            yield self

        async def fetch_one(self, query: LiteralString, parameters: tuple[Any, ...] = ()) -> Any:
            assert "application.begin_workflow_run_usage" in query
            # Match the real adapter's redacted exception boundary without changing
            # the fixture's schema or accessing any external database.
            raise_postgres_error(UndefinedFunction("synthetic-private-diagnostic"))

    services, executors = _services()
    services = replace(
        services,
        usage_recorder=DatabaseWorkflowUsageRecorder(database=UnavailableUsageDatabase()),
        lifecycle=DatabaseAgentWorkflowLifecycle(database=runtime),
    )
    await runtime.open()
    try:
        with pytest.raises(DependencyUnavailableError):
            await WorkflowExecutionDispatcher(services).execute(claim)
    finally:
        await runtime.close()

    assert not any(executor.calls for executor in executors.values())
    with web_postgres_database.connect_owner() as connection:
        row = require_row(
            connection.execute(
                "SELECT workflow_run_state, failure_code, failure_message, "
                "workflow_run_recovery_count, "
                "workflow_run_claim_token_digest IS NULL AS claim_cleared "
                "FROM application.workflow_run WHERE workflow_run_id=%s",
                (claim.workflow_run_id,),
            ).fetchone()
        )
    assert row["workflow_run_state"] == "failed"
    assert row["failure_code"] == "workflow_usage_unavailable"
    assert row["workflow_run_recovery_count"] == 0
    assert row["claim_cleared"] is True
    assert "synthetic-private-diagnostic" not in row["failure_message"]
