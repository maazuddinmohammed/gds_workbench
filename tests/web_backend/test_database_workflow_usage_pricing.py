"""Frozen operator pricing, using only the fixture-created disposable database."""

# pyright: reportPrivateUsage=false
from datetime import UTC, datetime
from decimal import Decimal
from uuid import uuid4

import pytest
from gds_etl_workbench.domain.errors import DependencyUnavailableError
from gds_workbench_api.features.workflows.authoring.lifecycle import workflow_identity_triple
from gds_workbench_api.features.workflows.execution.contracts import WorkflowExecutionClaim
from gds_workbench_api.features.workflows.usage.contracts import (
    FoundryModelPricing,
    ModelTokenUsage,
)
from gds_workbench_api.features.workflows.usage.service import DatabaseWorkflowUsageRecorder
from psycopg.errors import RaiseException
from psycopg.types.json import Jsonb

from tests.mcp.conftest import DisposablePostgres
from tests.mcp.database_test_support import require_row
from tests.mcp.test_database_workflow_run_lifecycle import _claim_specific_workflow_run
from tests.web_backend.test_database_workflow_usage import _invocation, _run

BEGIN_REQUEST_SQL = """
SELECT application.begin_workflow_run_model_request(
    %s,%s,%s,%s,%s,%s,%s,%s,'candidate_authoring',1,1,%s
) AS request_id
"""


def _pricing() -> FoundryModelPricing:
    return FoundryModelPricing(
        basis="Operator schedule 2026-09",
        input_usd_per_million=Decimal("2.12500001"),
        cached_input_usd_per_million=Decimal("0.5"),
        cache_write_input_usd_per_million=Decimal("3.25"),
        output_usd_per_million=Decimal("8"),
        valid_from=datetime(2026, 1, 1, tzinfo=UTC),
        valid_until=datetime(2027, 1, 1, tzinfo=UTC),
        max_input_tokens=128_000,
    )


def _pricing_rows(database: DisposablePostgres, claim: WorkflowExecutionClaim):
    with database.connect_owner() as connection:
        return connection.execute(
            "SELECT request_id,completed_time,pricing_basis,pricing_input_usd_per_million,"
            "pricing_cached_input_usd_per_million,pricing_cache_write_input_usd_per_million,"
            "pricing_output_usd_per_million,pricing_valid_from,pricing_valid_until,"
            "pricing_max_input_tokens FROM application.workflow_run_model_request "
            "WHERE workflow_run_id=%s ORDER BY started_time,request_id",
            (claim.workflow_run_id,),
        ).fetchall()


@pytest.mark.asyncio
async def test_pricing_uses_frozen_run_model_and_exact_normalized_replay(
    web_postgres_database: DisposablePostgres,
) -> None:
    _, claim, runtime = _run(web_postgres_database)
    price = _pricing()
    mapping = {
        "foundry-primary": price,
        "another-deployment": price.model_copy(update={"basis": "Other"}),
    }
    recorder = DatabaseWorkflowUsageRecorder(database=runtime, pricing_by_model=mapping)
    # Runtime configuration is copied; a caller's later mutation cannot reprice it.
    mapping["foundry-primary"] = price.model_copy(update={"basis": "Later"})
    invocation_id = uuid4()
    await runtime.open()
    try:
        async with recorder.track_run(claim):
            invocation = _invocation(recorder, claim, invocation_id=invocation_id)
            request_id = await invocation.begin_request(1)
            row = _pricing_rows(web_postgres_database, claim)[0]
            assert row["completed_time"] is None
            assert row["pricing_basis"] == price.basis
            assert row["pricing_input_usd_per_million"] == price.input_usd_per_million
            assert row["pricing_cached_input_usd_per_million"] == price.cached_input_usd_per_million
            assert (
                row["pricing_cache_write_input_usd_per_million"]
                == price.cache_write_input_usd_per_million
            )
            assert row["pricing_output_usd_per_million"] == price.output_usd_per_million
            assert row["pricing_valid_from"] == price.valid_from
            assert row["pricing_valid_until"] == price.valid_until
            assert row["pricing_max_input_tokens"] == price.max_input_tokens
            replay = price.model_dump(mode="json")
            replay["output_usd_per_million"] = 8
            replay["valid_from"] = "2026-01-01T01:00:00+01:00"
            parameters = workflow_identity_triple(claim.principal) + (
                claim.workflow_run_id,
                claim.model_revision,
                claim.workflow_run_claim_token,
                request_id,
                invocation_id,
            )
            async with runtime.write_transaction() as transaction:
                result = await transaction.fetch_one(
                    BEGIN_REQUEST_SQL, parameters + (Jsonb(replay),)
                )
                assert result is not None and result["request_id"] == request_id
            for changed in (None, {**replay, "output_usd_per_million": "9"}):
                with pytest.raises(DependencyUnavailableError):
                    async with runtime.write_transaction() as transaction:
                        await transaction.fetch_one(
                            BEGIN_REQUEST_SQL,
                            parameters + (Jsonb(changed) if changed is not None else None,),
                        )
            await invocation.complete_request(
                request_id, ModelTokenUsage(input_tokens=2, output_tokens=1, total_tokens=3)
            )
            assert await invocation.begin_request(1) == request_id
        # Re-entering an already tracked claim still returns its frozen model code.
        async with recorder.track_run(claim):
            await _invocation(recorder, claim).begin_request(1)
    finally:
        await runtime.close()
    assert [row["pricing_basis"] for row in _pricing_rows(web_postgres_database, claim)] == [
        price.basis,
        price.basis,
    ]


@pytest.mark.asyncio
async def test_sql_rejects_invalid_pricing_before_persisting_receipts(
    web_postgres_database: DisposablePostgres,
) -> None:
    _, claim, runtime = _run(web_postgres_database)
    valid = _pricing().model_dump(mode="json")
    invalid: list[object] = [
        [],
        {},
        {**valid, "extra": "forbidden"},
        {**valid, "basis": "unsafe\nlabel"},
        {**valid, "basis": "x" * 81},
        {**valid, "input_usd_per_million": None},
        {**valid, "input_usd_per_million": True},
        {**valid, "input_usd_per_million": "NaN"},
        {**valid, "input_usd_per_million": "Infinity"},
        {**valid, "input_usd_per_million": "-0.00000001"},
        {**valid, "input_usd_per_million": "1000000.00000001"},
        {**valid, "input_usd_per_million": "0.000000001"},
        {**valid, "valid_from": "2026-01-01T00:00:00"},
        {**valid, "valid_from": "infinity"},
        {**valid, "valid_until": valid["valid_from"]},
        {**valid, "valid_until": "2025-01-01T00:00:00Z"},
        {**valid, "max_input_tokens": 0},
        {**valid, "max_input_tokens": 1_000_000_000_001},
        {**valid, "max_input_tokens": 1.5},
        {**valid, "max_input_tokens": True},
    ]
    await runtime.open()
    try:
        async with DatabaseWorkflowUsageRecorder(database=runtime).track_run(claim):
            for payload in invalid:
                with pytest.raises(DependencyUnavailableError):
                    async with runtime.write_transaction() as transaction:
                        await transaction.fetch_one(
                            BEGIN_REQUEST_SQL,
                            workflow_identity_triple(claim.principal)
                            + (
                                claim.workflow_run_id,
                                claim.model_revision,
                                claim.workflow_run_claim_token,
                                uuid4(),
                                uuid4(),
                                Jsonb(payload),
                            ),
                        )
    finally:
        await runtime.close()
    assert _pricing_rows(web_postgres_database, claim) == []


@pytest.mark.asyncio
async def test_pricing_zero_and_maximum_bounds_are_exact_and_pending_schedule_is_immutable(
    web_postgres_database: DisposablePostgres,
) -> None:
    _, claim, runtime = _run(web_postgres_database)
    price = FoundryModelPricing(
        basis="Bounded schedule",
        input_usd_per_million=Decimal("1E+6"),
        cached_input_usd_per_million=Decimal("0"),
        cache_write_input_usd_per_million=Decimal("0.00000001"),
        output_usd_per_million=Decimal("1000000"),
        max_input_tokens=1_000_000_000_000,
    )
    await runtime.open()
    try:
        recorder = DatabaseWorkflowUsageRecorder(
            database=runtime, pricing_by_model={"foundry-primary": price}
        )
        async with recorder.track_run(claim):
            invocation = _invocation(recorder, claim)
            request_id = await invocation.begin_request(1)
            with (
                pytest.raises(RaiseException),
                web_postgres_database.connect_owner() as connection,
            ):
                connection.execute(
                    "UPDATE application.workflow_run_model_request SET "
                    "pricing_input_usd_per_million=1,completed_time=clock_timestamp() "
                    "WHERE request_id=%s",
                    (request_id,),
                )
            await invocation.complete_request(request_id, ModelTokenUsage())
    finally:
        await runtime.close()
    row = _pricing_rows(web_postgres_database, claim)[0]
    assert row["pricing_input_usd_per_million"] == Decimal("1000000.00000000")
    assert row["pricing_cached_input_usd_per_million"] == Decimal(0)
    assert row["pricing_cache_write_input_usd_per_million"] == Decimal("0.00000001")
    assert row["pricing_output_usd_per_million"] == Decimal("1000000.00000000")
    assert row["pricing_valid_from"] is None and row["pricing_valid_until"] is None
    assert row["pricing_max_input_tokens"] == 1_000_000_000_000


@pytest.mark.asyncio
async def test_recovered_run_freezes_new_schedule_without_repricing_old_request(
    web_postgres_database: DisposablePostgres,
) -> None:
    _, claim, runtime = _run(web_postgres_database)
    price = _pricing()
    await runtime.open()
    try:
        recorder = DatabaseWorkflowUsageRecorder(
            database=runtime, pricing_by_model={"foundry-primary": price}
        )
        async with recorder.track_run(claim):
            await _invocation(recorder, claim).begin_request(1)
        with web_postgres_database.connect_owner() as connection:
            connection.execute(
                "UPDATE application.workflow_run SET "
                "workflow_run_claimed_time=clock_timestamp()-interval '3 seconds', "
                "workflow_run_claim_heartbeat_time=clock_timestamp()-interval '2 seconds', "
                "workflow_run_claim_expires_time=clock_timestamp()-interval '1 second' "
                "WHERE workflow_run_id=%s",
                (claim.workflow_run_id,),
            )
        replacement = WorkflowExecutionClaim.model_validate(
            _claim_specific_workflow_run(web_postgres_database, claim.workflow_run_id)
        )
        changed = price.model_copy(
            update={"basis": "New schedule", "input_usd_per_million": Decimal("4")}
        )
        recorder = DatabaseWorkflowUsageRecorder(
            database=runtime, pricing_by_model={"foundry-primary": changed}
        )
        async with recorder.track_run(replacement):
            await _invocation(recorder, replacement).begin_request(1)
    finally:
        await runtime.close()
    rows = _pricing_rows(web_postgres_database, claim)
    assert [row["pricing_basis"] for row in rows] == [price.basis, "New schedule"]
    assert [row["pricing_input_usd_per_million"] for row in rows] == [
        price.input_usd_per_million,
        Decimal("4"),
    ]


@pytest.mark.asyncio
@pytest.mark.parametrize("workflow", ["conceptual", "profiling"])
async def test_tracking_returns_frozen_model_on_replay_and_optional_pricing_defaults_unknown(
    web_postgres_database: DisposablePostgres,
    workflow: str,
) -> None:
    _, claim, runtime = _run(web_postgres_database, workflow=workflow)
    with web_postgres_database.connect_owner() as connection:
        for _ in range(2):
            row = require_row(
                connection.execute(
                    "SELECT application.begin_workflow_run_usage(%s,%s,%s,%s,%s,%s) AS model",
                    workflow_identity_triple(claim.principal)
                    + (claim.workflow_run_id, claim.model_revision, claim.workflow_run_claim_token),
                ).fetchone()
            )
            assert row["model"] == ("foundry-primary" if workflow == "conceptual" else None)
        if workflow == "conceptual":
            # An old caller can omit the final optional pricing argument.
            connection.execute(
                "SELECT application.begin_workflow_run_model_request("
                "%s,%s,%s,%s,%s,%s,%s,%s,'candidate_authoring',1,1)",
                workflow_identity_triple(claim.principal)
                + (
                    claim.workflow_run_id,
                    claim.model_revision,
                    claim.workflow_run_claim_token,
                    uuid4(),
                    uuid4(),
                ),
            )
    await runtime.close()
    rows = _pricing_rows(web_postgres_database, claim)
    assert len(rows) == (1 if workflow == "conceptual" else 0)
    assert all(row["pricing_basis"] is None for row in rows)
