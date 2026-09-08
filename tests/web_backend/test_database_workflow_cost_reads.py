"""Exact, bounded cost estimates from disposable PostgreSQL receipt fixtures."""

# pyright: reportPrivateUsage=false
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any
from uuid import uuid4

import pytest
from gds_etl_workbench.application.authorization import AuthorizationService
from gds_workbench_api.features.workflows.execution.contracts import (
    WorkflowExecutionClaim,
)
from gds_workbench_api.features.workflows.runs import DatabaseWorkflowRunService
from gds_workbench_api.features.workflows.usage.contracts import (
    FoundryModelPricing,
    ModelTokenUsage,
)
from gds_workbench_api.features.workflows.usage.service import (
    DatabaseWorkflowUsageRecorder,
)

from tests.mcp.conftest import DisposablePostgres
from tests.mcp.test_database_workflow_run_lifecycle import _claim_specific_workflow_run
from tests.web_backend.test_database_workflow_usage import _invocation, _run


def _pricing(**changes: Any) -> FoundryModelPricing:
    return FoundryModelPricing.model_validate(
        {
            "basis": "Fixture USD schedule",
            "input_usd_per_million": Decimal("2"),
            "cached_input_usd_per_million": Decimal("0.5"),
            "cache_write_input_usd_per_million": Decimal("3"),
            "output_usd_per_million": Decimal("4"),
            **changes,
        }
    )


@pytest.mark.parametrize(
    "case",
    [
        "cache",
        "equal_rates",
        "missing_cached",
        "missing_cache_write",
        "zero_input",
        "tiny",
        "large_precise",
        "unsupported",
        "core_missing",
        "pending",
        "context",
        "expired",
        "future",
    ],
)
async def test_cost_uses_only_applicable_rates_and_sufficient_reported_counts(
    web_postgres_database: DisposablePostgres,
    case: str,
) -> None:
    context, claim, runtime = _run(web_postgres_database)
    pricing = _pricing()
    usage = ModelTokenUsage(
        input_tokens=100,
        output_tokens=20,
        total_tokens=120,
        cached_input_tokens=30,
        cache_write_input_tokens=10,
        reasoning_output_tokens=5,
    )
    reason = None
    expected_amount = Decimal("0.000245")
    if case == "equal_rates":
        pricing = _pricing(
            cached_input_usd_per_million=Decimal("2"),
            cache_write_input_usd_per_million=Decimal("2"),
        )
        usage = ModelTokenUsage(input_tokens=100, output_tokens=20, total_tokens=120)
        expected_amount = Decimal("0.00028")
    elif case in {"missing_cached", "missing_cache_write"}:
        usage = ModelTokenUsage(
            input_tokens=100,
            output_tokens=20,
            total_tokens=120,
            cached_input_tokens=None if case == "missing_cached" else 0,
            cache_write_input_tokens=None if case == "missing_cache_write" else 0,
        )
        reason = "missing_usage"
    elif case == "zero_input":
        usage = ModelTokenUsage(input_tokens=0, output_tokens=7, total_tokens=7)
        expected_amount = Decimal("0.000028")
    elif case in {"tiny", "large_precise"}:
        rate = Decimal("0.00000001") if case == "tiny" else Decimal("999999.99999999")
        pricing = _pricing(input_usd_per_million=rate)
        count = 1 if case == "tiny" else 999999999999
        usage = ModelTokenUsage(
            input_tokens=count,
            output_tokens=0,
            total_tokens=count,
            cached_input_tokens=0,
            cache_write_input_tokens=0,
        )
        expected_amount = (
            Decimal("0.00000000000001")
            if case == "tiny"
            else Decimal("999999999998.99000000000001")
        )
    elif case == "unsupported":
        usage = usage.model_copy(update={"other_token_types": True})
        reason = "unsupported_token_types"
    elif case == "core_missing":
        usage = ModelTokenUsage(input_tokens=100)
        reason = "missing_usage"
    elif case == "pending":
        reason = "missing_usage"
    elif case == "context":
        pricing = _pricing(max_input_tokens=99)
        reason = "context_limit_exceeded"
    elif case in {"expired", "future"}:
        pricing = _pricing(
            **{
                "valid_until" if case == "expired" else "valid_from": datetime.now(UTC)
                + timedelta(days=-1 if case == "expired" else 1)
            }
        )
        reason = "outside_pricing_window"

    recorder = DatabaseWorkflowUsageRecorder(
        database=runtime, pricing_by_model={"foundry-primary": pricing}
    )
    await runtime.open()
    try:
        async with recorder.track_run(claim):
            invocation = _invocation(recorder, claim)
            request_id = await invocation.begin_request(1)
            if case != "pending":
                await invocation.complete_request(request_id, usage)
        detail = await DatabaseWorkflowRunService(
            database=runtime,
            authorizer=AuthorizationService(),
            cursor_signing_key=b"fixture-cost-read-key-32-bytes",
        ).read_run(
            claim.principal,
            tenant_id=context.tenant_id,
            model_id=context.model_id,
            workflow_run_id=claim.workflow_run_id,
        )
        cost = detail.token_usage.cost_estimate
        assert cost.currency == "USD"
        assert cost.priced_request_count + cost.unpriced_request_count == 1
        assert sum(cost.unpriced_reasons.values()) == cost.unpriced_request_count
        if reason is None:
            assert cost.status == "estimated"
            assert cost.amount is not None and Decimal(cost.amount) == expected_amount
            assert "e" not in cost.amount.lower()
            assert cost.pricing_bases == ("Fixture USD schedule",)
        else:
            assert cost.status == "unpriced" and cost.amount is None
            assert cost.pricing_bases == ()
            assert cost.unpriced_reasons[reason] == 1
        if case in {"equal_rates", "zero_input"}:
            assert detail.token_usage.cached_input_tokens is None
            assert detail.token_usage.cache_write_input_tokens is None
        if case == "pending":
            assert detail.token_usage.pending_request_count == 1
    finally:
        await runtime.close()


@pytest.mark.parametrize("history_gap", [False, True])
async def test_mixed_frozen_schedules_sum_exactly_and_preserve_unknown_history(
    web_postgres_database: DisposablePostgres,
    history_gap: bool,
) -> None:
    context, claim, runtime = _run(web_postgres_database)
    if history_gap:
        with web_postgres_database.connect_owner() as connection:
            connection.execute(
                "UPDATE application.workflow_run SET "
                "workflow_run_claimed_time=clock_timestamp()-interval '3 seconds', "
                "workflow_run_claim_heartbeat_time=clock_timestamp()-interval '2 seconds', "
                "workflow_run_claim_expires_time=clock_timestamp()-interval '1 second' "
                "WHERE workflow_run_id=%s",
                (claim.workflow_run_id,),
            )
        claim = WorkflowExecutionClaim.model_validate(
            _claim_specific_workflow_run(web_postgres_database, claim.workflow_run_id)
        )
    schedules: list[FoundryModelPricing | None] = [
        _pricing(basis="Z original", input_usd_per_million=Decimal("999999.99999999")),
        _pricing(basis="A replacement", input_usd_per_million=Decimal("0.00000001")),
    ]
    if not history_gap:
        schedules.append(None)
    await runtime.open()
    try:
        for ordinal, pricing in enumerate(schedules, start=1):
            recorder = DatabaseWorkflowUsageRecorder(
                database=runtime,
                pricing_by_model={"foundry-primary": pricing} if pricing else {},
            )
            async with recorder.track_run(claim):
                invocation = _invocation(recorder, claim)
                request_id = await invocation.begin_request(ordinal)
                usage = ModelTokenUsage(
                    input_tokens=999999999999 if ordinal == 1 else 1,
                    output_tokens=0,
                    total_tokens=999999999999 if ordinal == 1 else 1,
                    cached_input_tokens=0,
                    cache_write_input_tokens=0,
                )
                await invocation.complete_request(request_id, usage)
                await invocation.complete_request(request_id, usage)
        detail = await DatabaseWorkflowRunService(
            database=runtime,
            authorizer=AuthorizationService(),
            cursor_signing_key=b"fixture-cost-read-key-32-bytes",
        ).read_run(
            claim.principal,
            tenant_id=context.tenant_id,
            model_id=context.model_id,
            workflow_run_id=claim.workflow_run_id,
        )
        cost = detail.token_usage.cost_estimate
        assert cost.status == "partial"
        assert cost.priced_request_count == 2
        assert cost.unpriced_request_count == (0 if history_gap else 1)
        assert sum(cost.unpriced_reasons.values()) == cost.unpriced_request_count
        assert cost.unpriced_reasons["pricing_not_configured"] == (0 if history_gap else 1)
        assert cost.pricing_bases == ("A replacement", "Z original")
        assert cost.amount is not None
        assert Decimal(cost.amount) == Decimal("999999999998.99000000000002")
        assert detail.token_usage.history_incomplete is history_gap
    finally:
        await runtime.close()


@pytest.mark.parametrize("at_end", [False, True])
async def test_pricing_window_uses_saved_request_time_and_excludes_its_end(
    web_postgres_database: DisposablePostgres,
    at_end: bool,
) -> None:
    context, claim, runtime = _run(web_postgres_database)
    recorder = DatabaseWorkflowUsageRecorder(database=runtime)
    await runtime.open()
    try:
        async with recorder.track_run(claim):
            pass
        started = datetime(2024, 1, 1, tzinfo=UTC)
        with web_postgres_database.connect_owner() as connection:
            connection.execute(
                (
                    "INSERT INTO application.workflow_run_model_request (\n                   "
                    " request_id, workflow_run_id, invocation_id, stage_code, "
                    "authoring_attempt,\n                    request_ordinal, "
                    "workflow_run_recovery_count, claim_token_digest,\n                    "
                    "started_time, completed_time, input_tokens, output_tokens, "
                    "total_tokens,\n                    pricing_basis, "
                    "pricing_input_usd_per_million, pricing_cached_input_usd_per_million,\n   "
                    "                 pricing_cache_write_input_usd_per_million, "
                    "pricing_output_usd_per_million,\n                    pricing_valid_from, "
                    "pricing_valid_until\n                ) SELECT %s, workflow_run_id, %s, "
                    "'candidate_authoring', 1, 1,\n                    "
                    "workflow_run_recovery_count, workflow_run_claim_token_digest,\n          "
                    "          %s, %s, 1, 0, 1, 'Historical fixture schedule', 1, 1, 1, 1, "
                    "%s, %s\n                  FROM application.workflow_run WHERE "
                    "workflow_run_id=%s"
                ),
                (
                    uuid4(),
                    uuid4(),
                    started,
                    started + timedelta(seconds=1),
                    started - timedelta(days=1) if at_end else started,
                    started if at_end else started + timedelta(days=1),
                    claim.workflow_run_id,
                ),
            )
        detail = await DatabaseWorkflowRunService(
            database=runtime,
            authorizer=AuthorizationService(),
            cursor_signing_key=b"fixture-cost-read-key-32-bytes",
        ).read_run(
            claim.principal,
            tenant_id=context.tenant_id,
            model_id=context.model_id,
            workflow_run_id=claim.workflow_run_id,
        )
        cost = detail.token_usage.cost_estimate
        assert cost.status == ("unpriced" if at_end else "estimated")
        assert cost.unpriced_reasons["outside_pricing_window"] == (1 if at_end else 0)
        if not at_end:
            assert cost.amount is not None and Decimal(cost.amount) == Decimal("0.000001")
    finally:
        await runtime.close()
