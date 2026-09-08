"""Usage receipts against a fixture-created disposable PostgreSQL container only."""

# pyright: reportPrivateUsage=false
from uuid import UUID, uuid4

import pytest
from gds_etl_workbench.domain.authorization import RequestPrincipal
from gds_etl_workbench.domain.errors import DependencyUnavailableError, InvalidRequestError
from gds_workbench_api.database import _READINESS_SQL, WebPostgresDatabase
from gds_workbench_api.features.workflows.execution.contracts import WorkflowExecutionClaim
from gds_workbench_api.features.workflows.usage.contracts import ModelTokenUsage
from gds_workbench_api.features.workflows.usage.service import DatabaseWorkflowUsageRecorder

from tests.mcp.conftest import DisposablePostgres
from tests.mcp.database_test_support import require_row
from tests.mcp.test_database_workflow_run_lifecycle import (
    CREATE_WORKFLOW_RUN_SQL,
    _claim_specific_workflow_run,
    create_workflow_run_parameters,
    seed_workflow_context,
)


def _run(database: DisposablePostgres, *, workflow: str = "conceptual"):
    context = seed_workflow_context(database)
    with database.connect_owner() as connection:
        row = require_row(
            connection.execute(
                CREATE_WORKFLOW_RUN_SQL,
                create_workflow_run_parameters(
                    context,
                    correlation_id=uuid4(),
                    workflow=workflow,
                    execution_mode="one_shot" if workflow == "conceptual" else None,
                    agent_configuration=(
                        "openai_agents_sdk",
                        "microsoft_foundry",
                        "foundry-primary",
                        "default",
                        10,
                        2,
                    )
                    if workflow == "conceptual"
                    else (None, None, None, None, None, None),
                ),
            ).fetchone()
        )
        run_id = row["workflow_run_id"]
        connection.execute(
            "SELECT application.start_workflow_run(%s,%s,'user',%s,%s)",
            (context.entra_tenant_id, context.entra_object_id, run_id, context.model_revision),
        )
    claim = WorkflowExecutionClaim.model_validate(_claim_specific_workflow_run(database, run_id))
    runtime = WebPostgresDatabase(
        dsn=database.web_runtime_dsn(), pool_min=1, pool_max=1, pool_timeout_seconds=5
    )
    return context, claim, runtime


def _rows(database: DisposablePostgres, claim: WorkflowExecutionClaim):
    with database.connect_owner() as connection:
        return connection.execute(
            "SELECT request_id,invocation_id,authoring_attempt,request_ordinal,"
            "input_tokens,output_tokens,total_tokens,cached_input_tokens,"
            "cache_write_input_tokens,reasoning_output_tokens,other_token_types,completed_time "
            "FROM application.workflow_run_model_request WHERE workflow_run_id=%s "
            "ORDER BY authoring_attempt,request_ordinal",
            (claim.workflow_run_id,),
        ).fetchall()


def _invocation(
    recorder: DatabaseWorkflowUsageRecorder,
    claim: WorkflowExecutionClaim,
    *,
    workflow_run_id: int | None = None,
    stage_code: str = "candidate_authoring",
    invocation_id: UUID | None = None,
    authoring_attempt: int = 1,
):
    return recorder.make_invocation_recorder(
        workflow_run_id=workflow_run_id or claim.workflow_run_id,
        stage_code=stage_code,
        invocation_id=invocation_id or uuid4(),
        authoring_attempt=authoring_attempt,
    )


@pytest.mark.asyncio
async def test_receipts_are_exact_idempotent_and_preserve_partial_failed_attempts(
    web_postgres_database: DisposablePostgres,
) -> None:
    _, claim, runtime = _run(web_postgres_database)
    await runtime.open()
    recorder = DatabaseWorkflowUsageRecorder(database=runtime)
    usage = ModelTokenUsage(
        input_tokens=10,
        output_tokens=4,
        total_tokens=14,
        cached_input_tokens=3,
        cache_write_input_tokens=0,
        reasoning_output_tokens=2,
    )
    try:
        async with runtime._transaction(read_only=True) as connection:
            readiness = await (await connection.execute(_READINESS_SQL)).fetchone()
        assert readiness is not None
        assert readiness["schema_ready"] and readiness["privileges_ready"]
        with pytest.raises(InvalidRequestError):
            _invocation(recorder, claim)
        async with recorder.track_run(claim):
            first = _invocation(recorder, claim)
            request_id = await first.begin_request(1)
            assert await first.begin_request(1) == request_id
            await first.complete_request(request_id, usage)
            await first.complete_request(request_id, usage)
            with pytest.raises(DependencyUnavailableError):
                await first.complete_request(request_id, ModelTokenUsage(input_tokens=11))
            # A later transport failure leaves a pending receipt; prior numeric evidence survives.
            pending = await first.begin_request(2)
            repair = _invocation(recorder, claim, authoring_attempt=2)
            missing = await repair.begin_request(1)
            await repair.complete_request(missing, ModelTokenUsage())
            with pytest.raises(InvalidRequestError):
                await repair.complete_request(request_id, usage)
        with pytest.raises(InvalidRequestError):
            await first.begin_request(3)
    finally:
        await runtime.close()
    rows = _rows(web_postgres_database, claim)
    assert len(rows) == 3
    assert rows[0]["input_tokens"] == 10 and rows[0]["cached_input_tokens"] == 3
    assert rows[1]["request_id"] == pending and rows[1]["completed_time"] is None
    assert rows[2]["completed_time"] is not None and rows[2]["input_tokens"] is None


@pytest.mark.asyncio
@pytest.mark.parametrize("failure", ["actor", "claim", "revision", "lock", "expired"])
async def test_usage_rechecks_actor_claim_revision_and_tenant_lock(
    web_postgres_database: DisposablePostgres,
    failure: str,
) -> None:
    context, claim, runtime = _run(web_postgres_database)
    if failure == "actor":
        claim = claim.model_copy(update={"actor_entra_object_id": uuid4()})
    elif failure == "claim":
        claim = claim.model_copy(update={"workflow_run_claim_token": uuid4()})
    elif failure == "revision":
        claim = claim.model_copy(update={"model_revision": claim.model_revision + 1})
    else:
        with web_postgres_database.connect_owner() as connection:
            if failure == "lock":
                connection.execute(
                    "UPDATE security.tenant_lock SET "
                    "tenant_lock_acquired_time=clock_timestamp()-interval '2 minutes', "
                    "tenant_lock_expires_time="
                    "clock_timestamp()-interval '1 second' WHERE tenant_id=%s",
                    (context.tenant_id,),
                )
            else:
                connection.execute(
                    "UPDATE application.workflow_run SET "
                    "workflow_run_claimed_time=clock_timestamp()-interval '3 seconds', "
                    "workflow_run_claim_heartbeat_time=clock_timestamp()-interval '2 seconds', "
                    "workflow_run_claim_expires_time="
                    "clock_timestamp()-interval '1 second' WHERE workflow_run_id=%s",
                    (claim.workflow_run_id,),
                )
    await runtime.open()
    try:
        with pytest.raises(DependencyUnavailableError):
            async with DatabaseWorkflowUsageRecorder(database=runtime).track_run(claim):
                pytest.fail("Invalid usage binding was accepted")
    finally:
        await runtime.close()
    assert _rows(web_postgres_database, claim) == []


@pytest.mark.asyncio
async def test_new_requests_require_frozen_stage_and_bounded_attempts(
    web_postgres_database: DisposablePostgres,
) -> None:
    _, claim, runtime = _run(web_postgres_database)
    await runtime.open()
    recorder = DatabaseWorkflowUsageRecorder(database=runtime)
    try:
        async with recorder.track_run(claim):
            with pytest.raises(InvalidRequestError):
                _invocation(recorder, claim, workflow_run_id=claim.workflow_run_id + 1)
            for invocation in (
                _invocation(recorder, claim, stage_code="unfrozen_stage"),
                _invocation(recorder, claim, authoring_attempt=4),
            ):
                with pytest.raises(DependencyUnavailableError):
                    await invocation.begin_request(1)
            invocation = _invocation(recorder, claim)
            for ordinal in (0, 151, True):
                with pytest.raises(InvalidRequestError):
                    await invocation.begin_request(ordinal)
    finally:
        await runtime.close()
    assert _rows(web_postgres_database, claim) == []


@pytest.mark.asyncio
@pytest.mark.parametrize("track_first", [False, True])
async def test_recovery_preserves_pending_and_marks_pretracking_history_unknown(
    web_postgres_database: DisposablePostgres,
    track_first: bool,
) -> None:
    _, claim, runtime = _run(web_postgres_database)
    await runtime.open()
    recorder = DatabaseWorkflowUsageRecorder(database=runtime)
    pending = None
    try:
        if track_first:
            async with recorder.track_run(claim):
                pending = await _invocation(recorder, claim).begin_request(1)
        with web_postgres_database.connect_owner() as connection:
            connection.execute(
                "UPDATE application.workflow_run SET "
                "workflow_run_claimed_time=clock_timestamp()-interval '3 seconds', "
                "workflow_run_claim_heartbeat_time=clock_timestamp()-interval '2 seconds', "
                "workflow_run_claim_expires_time="
                "clock_timestamp()-interval '1 second' WHERE workflow_run_id=%s",
                (claim.workflow_run_id,),
            )
        replacement = WorkflowExecutionClaim.model_validate(
            _claim_specific_workflow_run(web_postgres_database, claim.workflow_run_id)
        )
        assert replacement.workflow_run_recovery_count == 1
        async with recorder.track_run(replacement):
            invocation = _invocation(recorder, replacement)
            request_id = await invocation.begin_request(1)
            await invocation.complete_request(
                request_id,
                ModelTokenUsage(
                    input_tokens=0,
                    output_tokens=0,
                    total_tokens=0,
                    cached_input_tokens=0,
                    cache_write_input_tokens=0,
                    reasoning_output_tokens=0,
                ),
            )
        with pytest.raises(DependencyUnavailableError):
            async with recorder.track_run(claim):
                pytest.fail("Old claim must be fenced")
    finally:
        await runtime.close()
    with web_postgres_database.connect_owner() as connection:
        row = require_row(
            connection.execute(
                "SELECT usage_tracking_version,usage_tracked_recovery_count,"
                "usage_history_incomplete FROM application.workflow_run WHERE workflow_run_id=%s",
                (claim.workflow_run_id,),
            ).fetchone()
        )
    assert row == {
        "usage_tracking_version": 1,
        "usage_tracked_recovery_count": 1,
        "usage_history_incomplete": not track_first,
    }
    if track_first:
        assert any(
            row["request_id"] == pending and row["completed_time"] is None
            for row in _rows(web_postgres_database, claim)
        )


@pytest.mark.asyncio
async def test_deterministic_tracking_is_distinct_from_untracked_history(
    web_postgres_database: DisposablePostgres,
) -> None:
    _, claim, runtime = _run(web_postgres_database, workflow="profiling")
    with web_postgres_database.connect_owner() as connection:
        assert (
            require_row(
                connection.execute(
                    "SELECT usage_tracking_version FROM application.workflow_run "
                    "WHERE workflow_run_id=%s",
                    (claim.workflow_run_id,),
                ).fetchone()
            )["usage_tracking_version"]
            is None
        )
    await runtime.open()
    try:
        async with DatabaseWorkflowUsageRecorder(database=runtime).track_run(claim):
            pass
    finally:
        await runtime.close()
    with web_postgres_database.connect_owner() as connection:
        assert (
            require_row(
                connection.execute(
                    "SELECT usage_tracking_version FROM application.workflow_run "
                    "WHERE workflow_run_id=%s",
                    (claim.workflow_run_id,),
                ).fetchone()
            )["usage_tracking_version"]
            == 1
        )
    assert _rows(web_postgres_database, claim) == []


@pytest.mark.asyncio
async def test_database_rejects_invalid_numeric_receipts_independently(
    web_postgres_database: DisposablePostgres,
) -> None:
    _, claim, runtime = _run(web_postgres_database)
    await runtime.open()
    recorder = DatabaseWorkflowUsageRecorder(database=runtime)
    try:
        async with recorder.track_run(claim):
            invocation = _invocation(recorder, claim)
            request_id = await invocation.begin_request(1)
            for invalid in (
                ModelTokenUsage.model_construct(input_tokens=-1),
                ModelTokenUsage.model_construct(output_tokens=1_000_000_000_001),
                ModelTokenUsage.model_construct(input_tokens=2, cached_input_tokens=3),
                ModelTokenUsage.model_construct(input_tokens=2, output_tokens=3, total_tokens=4),
            ):
                with pytest.raises(DependencyUnavailableError):
                    await invocation.complete_request(request_id, invalid)
            await invocation.complete_request(
                request_id, ModelTokenUsage(input_tokens=0, output_tokens=0, total_tokens=0)
            )
    finally:
        await runtime.close()
    rows = _rows(web_postgres_database, claim)
    assert len(rows) == 1 and rows[0]["total_tokens"] == 0


@pytest.mark.asyncio
@pytest.mark.parametrize("terminal", ["completed", "failed"])
async def test_dispatcher_records_before_terminal_transition_clears_claim(
    web_postgres_database: DisposablePostgres,
    terminal: str,
) -> None:
    from gds_workbench_api.features.workflows.authoring.lifecycle import workflow_identity_triple
    from gds_workbench_api.features.workflows.execution.dispatcher import (
        WorkflowExecutionDispatcher,
        WorkflowExecutionServices,
    )

    _, claim, runtime = _run(web_postgres_database)
    await runtime.open()
    recorder = DatabaseWorkflowUsageRecorder(database=runtime)

    class Executor:
        async def execute_started(
            self, principal: RequestPrincipal, **arguments: int | UUID
        ) -> str:
            assert arguments["workflow_run_id"] == claim.workflow_run_id
            invocation = _invocation(recorder, claim)
            request_id = await invocation.begin_request(1)
            await invocation.complete_request(
                request_id, ModelTokenUsage(input_tokens=6, output_tokens=2, total_tokens=8)
            )
            async with runtime.write_transaction() as transaction:
                if terminal == "completed":
                    await transaction.fetch_one(
                        "SELECT application.complete_workflow_run(%s,%s,%s,%s,%s,%s)",
                        workflow_identity_triple(principal)
                        + (claim.workflow_run_id, claim.model_revision, 0),
                    )
                else:
                    await transaction.fetch_one(
                        "SELECT application.fail_workflow_run(%s,%s,%s,%s,%s,%s,%s)",
                        workflow_identity_triple(principal)
                        + (
                            claim.workflow_run_id,
                            claim.model_revision,
                            "agent_execution_failed",
                            "The agent could not finish.",
                        ),
                    )
            return terminal

    executor = Executor()
    services = WorkflowExecutionServices(
        profiling=executor,
        analysis_inference=executor,
        analysis_validation=executor,
        conceptual=executor,
        logical=executor,
        dimensional=executor,
        mapping=executor,
        code_generation=executor,
        validation=executor,
        metadata_enrichment=executor,
        usage_recorder=recorder,
    )
    try:
        assert await WorkflowExecutionDispatcher(services).execute(claim) == terminal
        with pytest.raises(InvalidRequestError):
            _invocation(recorder, claim)
    finally:
        await runtime.close()
    with web_postgres_database.connect_owner() as connection:
        run = require_row(
            connection.execute(
                "SELECT workflow_run_state,workflow_run_claim_token_digest "
                "FROM application.workflow_run WHERE workflow_run_id=%s",
                (claim.workflow_run_id,),
            ).fetchone()
        )
    assert run == {"workflow_run_state": terminal, "workflow_run_claim_token_digest": None}
    assert sum(row["total_tokens"] for row in _rows(web_postgres_database, claim)) == 8
