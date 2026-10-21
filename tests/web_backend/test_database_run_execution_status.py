"""Run detail separates queued Runs from executing ones; disposable fixture only."""

# Reuse fixture-only setup helpers.
# pyright: reportPrivateUsage=false

from gds_etl_workbench.application.authorization import AuthorizationService
from gds_workbench_api.features.workflows.execution import DatabaseWorkflowClaimRepository
from gds_workbench_api.features.workflows.runs import (
    DatabaseWorkflowRunService,
    WorkflowRunDetail,
)
from gds_workbench_api.features.workflows.usage.service import DatabaseWorkflowUsageRecorder

from tests.mcp.conftest import DisposablePostgres
from tests.web_backend.test_database_workflow_usage import _invocation, _run


async def test_run_detail_reports_waiting_for_a_worker_or_for_the_model(
    web_postgres_database: DisposablePostgres,
) -> None:
    context, claim, runtime = _run(web_postgres_database)
    runs = DatabaseWorkflowRunService(
        database=runtime,
        authorizer=AuthorizationService(),
        cursor_signing_key=b"fixture-only-execution-status-key-32",
    )
    recorder = DatabaseWorkflowUsageRecorder(database=runtime)

    async def read() -> WorkflowRunDetail:
        return await runs.read_run(
            claim.principal,
            tenant_id=context.tenant_id,
            project_id=context.project_id,
            workflow_run_id=claim.workflow_run_id,
        )

    await runtime.open()
    try:
        executing = await read()
        assert (executing.execution_status, executing.model_request_started_at) == (
            "executing",
            None,
        )

        async with recorder.track_run(claim):
            await _invocation(recorder, claim).begin_request(1)
            waiting_on_model = await read()
        assert waiting_on_model.execution_status == "executing"
        assert waiting_on_model.model_request_started_at is not None

        await DatabaseWorkflowClaimRepository(database=runtime).release(
            workflow_run_id=claim.workflow_run_id,
            workflow_run_claim_token=claim.workflow_run_claim_token,
        )
        queued = await read()
        # The released attempt never answers its model call, so it no longer counts.
        assert (queued.execution_status, queued.model_request_started_at) == (
            "waiting_for_worker",
            None,
        )
    finally:
        await runtime.close()
