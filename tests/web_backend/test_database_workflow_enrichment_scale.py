"""Canonical enrichment at the reported object count, without external providers."""

# Reuse only disposable-fixture setup helpers.
# pyright: reportPrivateUsage=false

import asyncio
from collections.abc import Iterator
from dataclasses import replace
from uuid import uuid4

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
from gds_workbench_api.runtime_diagnostics import RuntimeDiagnostics

from tests.mcp.conftest import DisposablePostgres, disposable_postgres
from tests.mcp.enrichment_test_support import seed_project_enrichment
from tests.mcp.test_database_global_prompt_seed import (
    REFERENCE_SEED,
    _apply_sql,
    _render_seed,
    _seed_super_admin,
)
from tests.mcp.test_database_metadata_enrichment_registration import _create
from tests.mcp.test_database_workflow_run_lifecycle import (
    _seed_bronze_project_input_scope,
    seed_workflow_context,
)


@pytest.fixture(scope="module")
def enrichment_scale_postgres() -> Iterator[DisposablePostgres]:
    for database in disposable_postgres():
        _apply_sql(database, REFERENCE_SEED.read_text(encoding="utf-8"))
        # This separate publisher installs defaults; it is not the workflow actor.
        _seed_super_admin(database)
        _apply_sql(database, _render_seed())
        yield database


async def test_ordinary_architect_completes_91_objects_with_renewed_claim(
    enrichment_scale_postgres: DisposablePostgres,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fixture = enrichment_scale_postgres
    context = seed_workflow_context(fixture)
    context = replace(
        context,
        selected_object_ids=_seed_bronze_project_input_scope(fixture, context, object_count=91),
    )
    with fixture.connect_owner() as connection:
        actor = connection.execute(
            "SELECT principal.is_super_admin, access.tenant_role "
            "FROM security.principal AS principal "
            "JOIN security.tenant_principal_access AS access USING (principal_id) "
            "WHERE principal.principal_id=%s AND access.tenant_id=%s",
            (context.principal_id, context.tenant_id),
        ).fetchone()
        # tenant_project_write requires Architect; Developer is intentionally denied.
        assert actor == {"is_super_admin": False, "tenant_role": "architect"}
        connection.execute(
            "UPDATE project.project SET default_agent_sdk_code='openai_agents_sdk', "
            "default_agent_provider_code='microsoft_foundry', "
            "default_agent_model_code='foundry-primary' WHERE project_id=%s",
            (context.project_id,),
        )
        connection.execute(
            "INSERT INTO core.attribute(object_id,attribute_name,attribute_ordinal_position,"
            "attribute_data_type,is_natural_key) "
            "SELECT object_id, name, ordinal, data_type, natural_key "
            "FROM unnest(%s::BIGINT[]) AS objects(object_id) CROSS JOIN (VALUES "
            "('CustomerID',1,'BIGINT',TRUE), ('CustomerName',2,'STRING',FALSE), "
            "('EmailAddress',3,'STRING',FALSE), ('OrderAmount',4,'DECIMAL(12,2)',FALSE), "
            "('CreatedAt',5,'TIMESTAMP',FALSE), ('IsActive',6,'BOOLEAN',FALSE)"
            ") AS attributes(name,ordinal,data_type,natural_key)",
            (list(context.selected_object_ids),),
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
    diagnostics = RuntimeDiagnostics()
    original_execute = LocalFakeAgentAdapter.execute
    provider_calls = 0
    renewed_during_provider = False

    async def delayed_execute(
        self: LocalFakeAgentAdapter, request: AgentExecutionRequest
    ) -> AgentExecutionResult:
        nonlocal provider_calls, renewed_during_provider
        assert request.workflow == "metadata_enrichment"
        provider_calls += 1
        if provider_calls == 1:
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
            renewed_during_provider = True
        return await original_execute(self, request)

    monkeypatch.setattr(LocalFakeAgentAdapter, "execute", delayed_execute)
    worker = WorkflowExecutionWorker(
        claims=DatabaseWorkflowClaimRepository(database=database),
        dispatcher=WorkflowExecutionDispatcher(
            services.execution_services(), diagnostics=diagnostics
        ),
        lease_duration_seconds=2,
        heartbeat_interval_seconds=0.2,
        diagnostics=diagnostics,
    )
    try:
        await database.open()
        assert (await database.readiness()).ready
        assert await asyncio.wait_for(worker.run_once(), timeout=60) is WorkerRunResult.COMPLETED
        async with database.read_transaction() as transaction:
            state = await transaction.fetch_one(
                "SELECT workflow_run_state, failure_code, selected_scope_count, "
                "workflow_run_recovery_count, usage_tracking_version, "
                "usage_tracked_recovery_count, usage_history_incomplete, "
                "workflow_run_claim_token_digest IS NULL AS claim_cleared "
                "FROM application.workflow_run WHERE workflow_run_id=%s",
                (run_id,),
            )
        with fixture.connect_owner() as connection:
            results = connection.execute(
                "SELECT count(*) AS result_count, count(DISTINCT object_id) AS object_count, "
                "count(DISTINCT attribute_id) AS attribute_count, "
                "count(*) FILTER (WHERE field_name='object_description' AND status='applied') "
                "AS object_descriptions, count(*) FILTER "
                "(WHERE field_name='attribute_description' AND status='applied') "
                "AS attribute_descriptions FROM application.metadata_enrichment_result "
                "WHERE workflow_run_id=%s",
                (run_id,),
            ).fetchone()
        assert state == {
            "workflow_run_state": "completed",
            "failure_code": None,
            "selected_scope_count": 91,
            "workflow_run_recovery_count": 0,
            "usage_tracking_version": 1,
            "usage_tracked_recovery_count": 0,
            "usage_history_incomplete": False,
            "claim_cleared": True,
        }
        assert results == {
            "result_count": 91 + 6 * 546,
            "object_count": 91,
            "attribute_count": 546,
            "object_descriptions": 91,
            "attribute_descriptions": 546,
        }
        assert renewed_during_provider and provider_calls > 0
        assert diagnostics.snapshot().worker.last_poll_result == "completed"
        assert diagnostics.snapshot().worker.last_fault is None
    finally:
        await services.close()
        await database.close()
