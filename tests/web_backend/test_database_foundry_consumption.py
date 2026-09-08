"""Real SDK plus disposable PostgreSQL receipts; HTTP is wholly in-memory."""

# pyright: reportPrivateUsage=false
from decimal import Decimal
from uuid import UUID

import httpx2
import pytest
from gds_etl_workbench.application.authorization import AuthorizationService
from gds_workbench_api.features.workflows.authoring.lifecycle import DatabaseAgentWorkflowLifecycle
from gds_workbench_api.features.workflows.runs import DatabaseWorkflowRunService
from gds_workbench_api.features.workflows.usage.contracts import FoundryModelPricing
from gds_workbench_api.features.workflows.usage.service import DatabaseWorkflowUsageRecorder

from tests.mcp.conftest import DisposablePostgres
from tests.web_backend.test_agent_usage import _request, _response, _router
from tests.web_backend.test_database_workflow_usage import _run


async def test_sdk_usage_and_cost_survive_a_later_workflow_failure_and_read_replay(
    web_postgres_database: DisposablePostgres,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    context, claim, database = _run(web_postgres_database)
    price = FoundryModelPricing(
        basis="Synthetic uniform input rates",
        input_usd_per_million=Decimal("2"),
        cached_input_usd_per_million=Decimal("2"),
        cache_write_input_usd_per_million=Decimal("2"),
        output_usd_per_million=Decimal("4"),
    )
    recorder = DatabaseWorkflowUsageRecorder(
        database=database, pricing_by_model={"foundry-primary": price}
    )
    sends = 0

    def transport(request: httpx2.Request) -> httpx2.Response:
        nonlocal sends
        sends += 1
        request_id = request.extensions.get("gds_model_request_id")
        assert isinstance(request_id, UUID)
        # The receipt and rate snapshot must already be committed before the paid boundary.
        with web_postgres_database.connect_owner() as connection:
            row = connection.execute(
                "SELECT completed_time,pricing_basis,pricing_input_usd_per_million "
                "FROM application.workflow_run_model_request WHERE request_id=%s",
                (request_id,),
            ).fetchone()
        assert row is not None and row["completed_time"] is None
        assert row["pricing_basis"] == price.basis
        assert row["pricing_input_usd_per_million"] == Decimal(2)
        return httpx2.Response(
            200,
            json=_response({"prompt_tokens": 10, "completion_tokens": 2, "total_tokens": 12}),
        )

    router = _router(monkeypatch, recorder, transport)
    runs = DatabaseWorkflowRunService(
        database=database,
        authorizer=AuthorizationService(),
        cursor_signing_key=b"fixture-only-usage-read-key-32-bytes",
    )
    await database.open()
    try:
        async with recorder.track_run(claim):
            candidate = await router.execute(
                _request().model_copy(
                    update={"workflow_run_id": claim.workflow_run_id, "workflow": "conceptual"}
                )
            )
            assert candidate.candidate == {"result": "valid"}
        await DatabaseAgentWorkflowLifecycle(database=database).fail(
            claim.principal,
            workflow_run_id=claim.workflow_run_id,
            expected_model_revision=claim.model_revision,
            workflow_run_claim_token=claim.workflow_run_claim_token,
            failure_code="fixture_later_failure",
            safe_failure_message="Fixture execution stopped after model completion.",
        )
        first = await runs.read_run(
            claim.principal,
            tenant_id=context.tenant_id,
            model_id=context.model_id,
            workflow_run_id=claim.workflow_run_id,
        )
        replay = await runs.read_run(
            claim.principal,
            tenant_id=context.tenant_id,
            model_id=context.model_id,
            workflow_run_id=claim.workflow_run_id,
        )
        assert first.workflow_run_state == "failed"
        assert first.token_usage == replay.token_usage
        assert first.token_usage.status == "complete"
        assert first.token_usage.request_count == 1 and first.token_usage.total_tokens == 12
        estimate = first.token_usage.cost_estimate
        assert estimate.status == "estimated" and estimate.priced_request_count == 1
        assert estimate.amount is not None and Decimal(estimate.amount) == Decimal("0.000028")
        assert estimate.pricing_bases == (price.basis,)
        assert sends == 1
        assert "Private" not in first.token_usage.model_dump_json()
    finally:
        await router.close()
        await database.close()
