"""Real enrichment worker and PostgreSQL with delayed, synthetic provider output."""

# pyright: reportPrivateUsage=false
import asyncio
from collections.abc import Iterator
from typing import Any, LiteralString
from uuid import uuid4

import gds_workbench_api.database as database_module
import pytest
from gds_etl_workbench.application.authorization import AuthorizationService
from gds_workbench_api.capabilities import load_default_agent_capabilities
from gds_workbench_api.database import WebPostgresDatabase
from gds_workbench_api.features.workflows.authoring.agent_execution import (
    AgentExecutionRequest,
    AgentExecutionResult,
)
from gds_workbench_api.features.workflows.execution import (
    DatabaseWorkflowClaimRepository,
    WorkerRunResult,
    WorkflowExecutionDispatcher,
    WorkflowExecutionWorker,
)
from gds_workbench_api.features.workflows.execution.assembly import create_workflow_runtime_services
from gds_workbench_api.integrations.agents.composition import LocalFakeAgentAdapter
from gds_workbench_api.integrations.agents.configuration import AgentRuntimeConfiguration
from gds_workbench_api.integrations.databricks import create_databricks_execution_adapters

from tests.mcp.conftest import DisposablePostgres, disposable_postgres
from tests.mcp.enrichment_test_support import seed_project_enrichment
from tests.mcp.test_database_global_prompt_seed import (
    REFERENCE_SEED,
    _apply_sql,
    _render_seed,
    _seed_super_admin,
)
from tests.mcp.test_database_metadata_enrichment_registration import _create
from tests.mcp.test_database_profiling_persistence import _seed_attributes
from tests.mcp.test_database_workflow_run_lifecycle import seed_workflow_context


@pytest.fixture(scope="module")
def enrichment_worker_postgres() -> Iterator[DisposablePostgres]:
    for database in disposable_postgres():
        _apply_sql(database, REFERENCE_SEED.read_text(encoding="utf-8"))
        _seed_super_admin(database)
        _apply_sql(database, _render_seed())
        yield database


@pytest.mark.parametrize("delayed_boundary", ["context", "provider"])
async def test_enrichment_worker_completes_after_initial_lease_expires(
    enrichment_worker_postgres: DisposablePostgres,
    monkeypatch: pytest.MonkeyPatch,
    delayed_boundary: str,
) -> None:
    fixture = enrichment_worker_postgres
    context = seed_workflow_context(fixture)
    _seed_attributes(fixture, context)
    with fixture.connect_owner() as connection:
        connection.execute(
            "UPDATE project.project SET default_agent_sdk_code='openai_agents_sdk', "
            "default_agent_provider_code='microsoft_foundry', "
            "default_agent_model_code='foundry-primary' WHERE project_id=%s",
            (context.project_id,),
        )
        seed_project_enrichment(connection, context.project_id)
    run_id = _create(fixture, context, correlation_id=uuid4())["workflow_run_id"]
    with fixture.connect_owner() as connection:
        connection.execute(
            "SELECT application.start_workflow_run(%s,%s,'user',%s,%s)",
            (context.entra_tenant_id, context.entra_object_id, run_id, context.project_revision),
        )
    database = WebPostgresDatabase(
        dsn=fixture.web_runtime_dsn(), pool_min=2, pool_max=3, pool_timeout_seconds=5
    )
    services = create_workflow_runtime_services(
        database=database,
        authorizer=AuthorizationService(),
        agent_runtime=AgentRuntimeConfiguration(mode="fake", timeout_seconds=120, connections=()),
        agent_capability_registry=load_default_agent_capabilities(),
        databricks_environment_code="fixture",
        databricks_execution=create_databricks_execution_adapters("fake"),
    )
    original_fetch = database_module._WebTransaction.fetch_one
    original_execute = LocalFakeAgentAdapter.execute
    delay_observed = False
    provider_calls = 0

    async def assert_renewed_after_delay() -> None:
        await asyncio.sleep(2.25)
        async with database.read_transaction() as transaction:
            lease = await transaction.fetch_one(
                "SELECT clock_timestamp() > workflow_run_claimed_time + interval '2 seconds' "
                "AS initial_lease_elapsed, "
                "workflow_run_claim_heartbeat_time > workflow_run_claimed_time AS renewed, "
                "workflow_run_claim_expires_time > clock_timestamp() AS live "
                "FROM application.workflow_run WHERE workflow_run_id=%s",
                (run_id,),
            )
        assert lease == {"initial_lease_elapsed": True, "renewed": True, "live": True}

    async def delayed_fetch(
        self: database_module._WebTransaction,
        query: LiteralString,
        parameters: tuple[Any, ...] = (),
    ) -> dict[str, Any] | None:
        nonlocal delay_observed
        row = await original_fetch(self, query, parameters)
        if (
            delayed_boundary == "context"
            and "application.get_metadata_enrichment_execution_context" in query
        ):
            assert not delay_observed
            delay_observed = True
            # The real REPEATABLE READ transaction remains open until plan load.
            # Its context row lock must allow the independent heartbeat to update.
            await assert_renewed_after_delay()
        return row

    async def delayed_execute(
        self: LocalFakeAgentAdapter, request: AgentExecutionRequest
    ) -> AgentExecutionResult:
        nonlocal delay_observed, provider_calls
        assert request.workflow == "metadata_enrichment"
        provider_calls += 1
        if delayed_boundary == "provider" and not delay_observed:
            delay_observed = True
            await assert_renewed_after_delay()
        return await original_execute(self, request)

    monkeypatch.setattr(database_module._WebTransaction, "fetch_one", delayed_fetch)
    monkeypatch.setattr(LocalFakeAgentAdapter, "execute", delayed_execute)
    try:
        await database.open()
        assert (await database.readiness()).ready
        worker = WorkflowExecutionWorker(
            claims=DatabaseWorkflowClaimRepository(database=database),
            dispatcher=WorkflowExecutionDispatcher(services.execution_services()),
            lease_duration_seconds=2,
            heartbeat_interval_seconds=0.2,
        )
        assert await asyncio.wait_for(worker.run_once(), timeout=15) is WorkerRunResult.COMPLETED
        async with database.read_transaction() as transaction:
            state = await transaction.fetch_one(
                "SELECT workflow_run_state, failure_code, workflow_run_recovery_count, "
                "usage_tracking_version, usage_tracked_recovery_count, "
                "workflow_run_claim_token_digest IS NULL AS claim_cleared "
                "FROM application.workflow_run WHERE workflow_run_id=%s",
                (run_id,),
            )
            events = await transaction.fetch_one(
                "SELECT count(*) FILTER (WHERE project_event_log_stage='metadata_evidence') "
                "AS evidence_count, count(*) FILTER (WHERE project_event_log_stage="
                "'candidate_authoring') > 0 AS authored "
                "FROM project.project_event_log WHERE workflow_run_id=%s",
                (run_id,),
            )
        with fixture.connect_owner() as connection:
            results = connection.execute(
                "SELECT count(*) > 0 AS saved FROM application.metadata_enrichment_result "
                "WHERE workflow_run_id=%s",
                (run_id,),
            ).fetchone()
        assert state == {
            "workflow_run_state": "completed",
            "failure_code": None,
            "workflow_run_recovery_count": 0,
            "usage_tracking_version": 1,
            "usage_tracked_recovery_count": 0,
            "claim_cleared": True,
        }
        assert delay_observed and provider_calls > 0
        assert events == {"evidence_count": 1, "authored": True}
        assert results == {"saved": True}
    finally:
        await services.close()
        await database.close()
