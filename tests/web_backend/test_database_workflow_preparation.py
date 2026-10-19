"""Actual preparation reads must allow lease renewals before execution starts."""

# Shared fixture lifecycle helpers are confined to disposable database tests.
# pyright: reportPrivateUsage=false

import asyncio
from typing import TYPE_CHECKING
from unittest.mock import AsyncMock
from uuid import UUID

import pytest
from gds_etl_workbench.domain.authorization import ActorKind, RequestPrincipal
from gds_etl_workbench.domain.errors import WorkbenchError
from gds_workbench_api.database import WebPostgresDatabase
from gds_workbench_api.features.metadata_enrichment.contracts import MetadataEnrichmentContext
from gds_workbench_api.features.metadata_enrichment.evidence import MetadataEvidenceReader
from gds_workbench_api.features.metadata_enrichment.repository import (
    MetadataEnrichmentRepository,
)
from gds_workbench_api.features.metadata_enrichment.service import (
    DatabaseMetadataEnrichmentExecutor,
)
from gds_workbench_api.features.workflows.authoring.lifecycle import (
    DatabaseAgentWorkflowLifecycle,
)
from gds_workbench_api.features.workflows.authoring.plan import (
    AgentRunPlan,
    AgentRunPlanTransaction,
    PostgresAgentRunPlanRepository,
)
from gds_workbench_api.features.workflows.execution import DatabaseWorkflowClaimRepository

from tests.mcp.enrichment_test_support import seed_project_enrichment
from tests.mcp.test_database_metadata_enrichment_execution import _start

if TYPE_CHECKING:
    from tests.mcp.conftest import DisposablePostgres


@pytest.mark.asyncio
async def test_enrichment_preparation_keeps_claim_alive_while_loading_context(
    web_postgres_database: DisposablePostgres,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fixture = web_postgres_database
    context, run_id, claim_token, _ = _start(fixture)
    with fixture.connect_owner() as connection:
        seed_project_enrichment(connection, context.project_id)
    principal = RequestPrincipal(
        actor_kind=ActorKind.HUMAN,
        entra_tenant_id=context.entra_tenant_id,
        entra_object_id=context.entra_object_id,
    )
    database = WebPostgresDatabase(
        dsn=fixture.web_runtime_dsn(), pool_min=2, pool_max=2, pool_timeout_seconds=5
    )
    claims = DatabaseWorkflowClaimRepository(database=database)
    repository = MetadataEnrichmentRepository(database, environment_code="test")
    plan_loaded = asyncio.Event()
    finish_preparation = asyncio.Event()
    original_load = PostgresAgentRunPlanRepository.load

    async def slow_plan_load(
        self: PostgresAgentRunPlanRepository,
        transaction: AgentRunPlanTransaction,
        *,
        tenant_id: int,
        project_id: int,
        workflow_run_id: int,
    ) -> AgentRunPlan:
        plan = await original_load(
            self,
            transaction,
            tenant_id=tenant_id,
            project_id=project_id,
            workflow_run_id=workflow_run_id,
        )
        plan_loaded.set()
        await finish_preparation.wait()
        # Analysis connection resolution repeats its context read in the same
        # snapshot; exercise that lock pattern after heartbeats changed the Run.
        await transaction.fetch_all(
            "SELECT application.get_metadata_enrichment_execution_context"
            "(%s, %s, 'user', %s, %s) AS context",
            (
                context.entra_tenant_id,
                context.entra_object_id,
                workflow_run_id,
                context.project_revision,
            ),
        )
        return plan

    monkeypatch.setattr(PostgresAgentRunPlanRepository, "load", slow_plan_load)
    await database.open()
    preparation = None
    try:
        await claims.renew(
            workflow_run_id=run_id,
            workflow_run_claim_token=claim_token,
            lease_duration_seconds=2,
        )
        preparation = asyncio.create_task(
            repository.load(
                principal,
                tenant_id=context.tenant_id,
                project_id=context.project_id,
                workflow_run_id=run_id,
                expected_project_revision=context.project_revision,
                workflow_run_claim_token=claim_token,
            )
        )
        await asyncio.wait_for(plan_loaded.wait(), timeout=3)
        # Hold the real preparation transaction longer than its starting lease.
        # Every heartbeat must commit while preparation remains unfinished.
        for _ in range(3):
            await asyncio.sleep(0.75)
            await asyncio.wait_for(
                claims.renew(
                    workflow_run_id=run_id,
                    workflow_run_claim_token=claim_token,
                    lease_duration_seconds=2,
                ),
                timeout=0.75,
            )
            assert not preparation.done()
        finish_preparation.set()
        plan, loaded = await asyncio.wait_for(preparation, timeout=3)
        assert plan.workflow_run_id == loaded.workflow_run_id == run_id
    finally:
        finish_preparation.set()
        if preparation is not None:
            await asyncio.gather(preparation, return_exceptions=True)
        await database.close()


@pytest.mark.asyncio
@pytest.mark.parametrize("revocation", ["cancel", "release"])
async def test_enrichment_rechecks_claim_after_preparation_before_provider_calls(
    web_postgres_database: DisposablePostgres,
    monkeypatch: pytest.MonkeyPatch,
    revocation: str,
) -> None:
    fixture = web_postgres_database
    context, run_id, claim_token, _ = _start(fixture)
    with fixture.connect_owner() as connection:
        seed_project_enrichment(connection, context.project_id)
    principal = RequestPrincipal(
        actor_kind=ActorKind.HUMAN,
        entra_tenant_id=context.entra_tenant_id,
        entra_object_id=context.entra_object_id,
    )
    database = WebPostgresDatabase(
        dsn=fixture.web_runtime_dsn(), pool_min=2, pool_max=2, pool_timeout_seconds=5
    )
    repository = MetadataEnrichmentRepository(database, environment_code="test")
    lifecycle = DatabaseAgentWorkflowLifecycle(database=database)
    agent = AsyncMock()
    evidence = AsyncMock(side_effect=AssertionError("External evidence must remain unused"))
    monkeypatch.setattr(MetadataEvidenceReader, "collect", evidence)
    executor = DatabaseMetadataEnrichmentExecutor(
        repository=repository, agent_executor=agent, lifecycle=lifecycle
    )
    prepared = asyncio.Event()
    resume = asyncio.Event()
    original_load = repository.load

    async def stop_after_preparation(
        principal: RequestPrincipal,
        *,
        tenant_id: int,
        project_id: int,
        workflow_run_id: int,
        expected_project_revision: int,
        workflow_run_claim_token: UUID,
    ) -> tuple[AgentRunPlan, MetadataEnrichmentContext]:
        result = await original_load(
            principal,
            tenant_id=tenant_id,
            project_id=project_id,
            workflow_run_id=workflow_run_id,
            expected_project_revision=expected_project_revision,
            workflow_run_claim_token=workflow_run_claim_token,
        )
        prepared.set()
        await resume.wait()
        return result

    monkeypatch.setattr(repository, "load", stop_after_preparation)
    await database.open()
    execution = asyncio.create_task(
        executor.execute_started(
            principal,
            tenant_id=context.tenant_id,
            project_id=context.project_id,
            workflow_run_id=run_id,
            expected_project_revision=context.project_revision,
            workflow_run_claim_token=claim_token,
        )
    )
    try:
        await asyncio.wait_for(prepared.wait(), timeout=3)
        if revocation == "release":
            await DatabaseWorkflowClaimRepository(database=database).release(
                workflow_run_id=run_id, workflow_run_claim_token=claim_token
            )
        else:
            async with database.write_transaction() as transaction:
                await transaction.fetch_one(
                    "SELECT * FROM application.cancel_workflow_run(%s, %s, 'user', %s, %s, %s)",
                    (
                        context.entra_tenant_id,
                        context.entra_object_id,
                        context.tenant_id,
                        context.project_id,
                        run_id,
                    ),
                )
        resume.set()
        with pytest.raises(WorkbenchError):
            await asyncio.wait_for(execution, timeout=3)
        evidence.assert_not_awaited()
        agent.execute.assert_not_awaited()
    finally:
        resume.set()
        await asyncio.gather(execution, return_exceptions=True)
        await database.close()
