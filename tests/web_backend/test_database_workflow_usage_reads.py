"""Run usage read semantics against fixture-created disposable PostgreSQL only."""

# pyright: reportPrivateUsage=false
from contextlib import nullcontext

import pytest
from gds_etl_workbench.application.authorization import AuthorizationService
from gds_workbench_api.features.workflows.authoring.lifecycle import (
    DatabaseAgentWorkflowLifecycle,
)
from gds_workbench_api.features.workflows.execution.contracts import (
    WorkflowExecutionClaim,
)
from gds_workbench_api.features.workflows.runs import (
    DatabaseWorkflowRunService,
    WorkflowRunNotFoundError,
)
from gds_workbench_api.features.workflows.usage.contracts import ModelTokenUsage
from gds_workbench_api.features.workflows.usage.read_service import (
    WorkflowTokenUsageSummary,
    read_run_token_usage,
)
from gds_workbench_api.features.workflows.usage.service import (
    DatabaseWorkflowUsageRecorder,
)

from tests.mcp.conftest import DisposablePostgres
from tests.mcp.test_database_workflow_run_lifecycle import _claim_specific_workflow_run
from tests.web_backend.test_database_workflow_usage import _invocation, _run


@pytest.mark.parametrize(
    "scenario",
    [
        "zero",
        "reported",
        "optional_missing",
        "core_partial",
        "missing",
        "pending",
        "gap",
        "untracked_recovery",
    ],
)
async def test_run_summary_distinguishes_reported_zero_unknown_and_partial_usage(
    web_postgres_database: DisposablePostgres,
    scenario: str,
) -> None:
    context, claim, runtime = _run(web_postgres_database)
    runs = DatabaseWorkflowRunService(
        database=runtime,
        authorizer=AuthorizationService(),
        cursor_signing_key=b"fixture-only-usage-read-key-32-bytes",
    )
    recorder = DatabaseWorkflowUsageRecorder(database=runtime)
    await runtime.open()
    try:
        legacy = await runs.read_run(
            claim.principal,
            tenant_id=context.tenant_id,
            model_id=context.model_id,
            workflow_run_id=claim.workflow_run_id,
        )
        assert legacy.token_usage == WorkflowTokenUsageSummary()
        if scenario == "untracked_recovery":
            async with recorder.track_run(claim):
                pass
        if scenario in {"gap", "untracked_recovery"}:
            with web_postgres_database.connect_owner() as connection:
                connection.execute(
                    "UPDATE application.workflow_run SET "
                    "workflow_run_claimed_time=clock_timestamp()-interval '3 seconds', "
                    "workflow_run_claim_heartbeat_time=clock_timestamp()-interval '2 seconds', "
                    "workflow_run_claim_expires_time="
                    "clock_timestamp()-interval '1 second' WHERE workflow_run_id=%s",
                    (claim.workflow_run_id,),
                )
            claim = WorkflowExecutionClaim.model_validate(
                _claim_specific_workflow_run(web_postgres_database, claim.workflow_run_id)
            )
        async with nullcontext() if scenario == "untracked_recovery" else recorder.track_run(claim):
            if scenario not in {"zero", "gap", "untracked_recovery"}:
                first = _invocation(recorder, claim)
                request_id = await first.begin_request(1)
                await first.complete_request(
                    request_id,
                    ModelTokenUsage(
                        input_tokens=10,
                        output_tokens=4,
                        total_tokens=14,
                        cached_input_tokens=3,
                        cache_write_input_tokens=0,
                        reasoning_output_tokens=2,
                    ),
                )
                # A repair is a separate invocation and must be included once.
                repair = _invocation(recorder, claim, authoring_attempt=2)
                request_id = await repair.begin_request(1)
                usage = {
                    "reported": ModelTokenUsage(
                        input_tokens=20,
                        output_tokens=6,
                        total_tokens=26,
                        cached_input_tokens=4,
                        cache_write_input_tokens=0,
                        reasoning_output_tokens=1,
                    ),
                    "optional_missing": ModelTokenUsage(
                        input_tokens=20,
                        output_tokens=6,
                        total_tokens=26,
                        other_token_types=True,
                    ),
                    "core_partial": ModelTokenUsage(input_tokens=9),
                    "missing": ModelTokenUsage(),
                }.get(scenario)
                if usage is not None:
                    await repair.complete_request(request_id, usage)
                    await repair.complete_request(request_id, usage)
        active = await runs.read_run(
            claim.principal,
            tenant_id=context.tenant_id,
            model_id=context.model_id,
            workflow_run_id=claim.workflow_run_id,
        )
        assert active.token_usage.status == "recording"
        await DatabaseAgentWorkflowLifecycle(database=runtime).fail(
            claim.principal,
            workflow_run_id=claim.workflow_run_id,
            expected_model_revision=claim.model_revision,
            workflow_run_claim_token=claim.workflow_run_claim_token,
            failure_code="fixture_failure",
            safe_failure_message="Fixture execution stopped.",
        )
        terminal = await runs.read_run(
            claim.principal,
            tenant_id=context.tenant_id,
            model_id=context.model_id,
            workflow_run_id=claim.workflow_run_id,
        )
        summary = terminal.token_usage
        assert terminal.workflow_run_state == "failed"
        assert summary.history_incomplete is (scenario in {"gap", "untracked_recovery"})
        assert summary.status == (
            "partial"
            if scenario in {"core_partial", "missing", "pending", "gap", "untracked_recovery"}
            else "complete"
        )
        assert summary.model_dump(exclude={"status"}) == active.token_usage.model_dump(
            exclude={"status"}
        )
        assert summary.request_count == (
            summary.reported_request_count
            + summary.pending_request_count
            + summary.missing_usage_request_count
        )
        if scenario in {"zero", "gap", "untracked_recovery"}:
            assert summary.request_count == 0
            assert summary.cost_estimate.status == (
                "estimated" if scenario == "zero" else "unavailable"
            )
            assert summary.cost_estimate.amount == ("0" if scenario == "zero" else None)
            assert (
                summary.input_tokens,
                summary.output_tokens,
                summary.total_tokens,
                summary.cached_input_tokens,
                summary.cache_write_input_tokens,
                summary.reasoning_output_tokens,
            ) == (
                (0, 0, 0, 0, 0, 0) if scenario == "zero" else (None, None, None, None, None, None)
            )
        else:
            assert summary.request_count == 2
            assert summary.cost_estimate.status == "unpriced"
            assert summary.cost_estimate.amount is None
            assert summary.cost_estimate.unpriced_request_count == 2
            assert summary.cost_estimate.unpriced_reasons["pricing_not_configured"] == 2
            assert summary.reported_request_count == (
                2 if scenario in {"reported", "optional_missing"} else 1
            )
            assert summary.pending_request_count == (1 if scenario == "pending" else 0)
            assert summary.missing_usage_request_count == (
                1 if scenario in {"core_partial", "missing"} else 0
            )
            expected_core = (
                (30, 10, 40)
                if scenario in {"reported", "optional_missing"}
                else (19, 4, 14)
                if scenario == "core_partial"
                else (10, 4, 14)
            )
            assert (
                summary.input_tokens,
                summary.output_tokens,
                summary.total_tokens,
            ) == expected_core
            assert (
                summary.cached_input_tokens,
                summary.cache_write_input_tokens,
                summary.reasoning_output_tokens,
            ) == ((7, 0, 3) if scenario == "reported" else (None, None, None))

        async with runtime.read_transaction() as transaction:
            assert (
                await read_run_token_usage(
                    transaction,
                    tenant_id=context.tenant_id + 99999,
                    model_id=context.model_id,
                    workflow_run_id=claim.workflow_run_id,
                )
                is None
            )
            assert (
                await read_run_token_usage(
                    transaction,
                    tenant_id=context.tenant_id,
                    model_id=context.model_id + 99999,
                    workflow_run_id=claim.workflow_run_id,
                )
                is None
            )
        with pytest.raises(WorkflowRunNotFoundError):
            await runs.read_run(
                claim.principal,
                tenant_id=context.tenant_id,
                model_id=context.model_id + 99999,
                workflow_run_id=claim.workflow_run_id,
            )
    finally:
        await runtime.close()
