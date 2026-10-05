"""Real disposable-PostgreSQL profiling, with Databricks replaced by aggregate fixtures."""

from __future__ import annotations

from typing import Any
from uuid import UUID, uuid4

import pytest
from psycopg.errors import ObjectNotInPrerequisiteState, RaiseException
from psycopg.types.json import Jsonb

from gds_etl_workbench.application.profiling.execution import ProfileMetric
from gds_etl_workbench.application.profiling.service import (
    ProfilingService,
    ProfilingWorker,
    plan_context,
)
from gds_etl_workbench.domain.authorization import ActorKind, RequestPrincipal
from gds_etl_workbench.infrastructure.postgres import PostgresDatabase
from tests.mcp.test_database_profiling_execution_context import (
    _seed_profiling_execution,
)

_START = "SELECT mcp.start_mcp_profiling_run(%s,%s,'user',%s,%s,%s,%s,%s,%s) AS result"
_WORKER = "SELECT mcp.mcp_profiling_worker(%s,%s,%s,%s) AS result"


@pytest.fixture(scope="module")
def postgres_database(bootstrap_postgres_database: Any) -> Any:
    """Claims inspect all running jobs; keep this module's jobs in a separate container."""
    return bootstrap_postgres_database


def start(
    database: Any,
    seed: Any,
    *,
    batches: list[str] | None = None,
    request: UUID | None = None,
) -> dict[str, Any]:
    context = seed.context
    with database.connect_runtime() as connection:
        return connection.execute(
            _START,
            (
                context.entra_tenant_id,
                context.entra_object_id,
                context.model_id,
                context.model_revision,
                list(context.selected_object_ids),
                batches,
                seed.environment_code,
                request or uuid4(),
            ),
        ).fetchone()["result"]


def operation(
    database: Any,
    name: str,
    run: int | None = None,
    claim: str | None = None,
    payload: object = None,
) -> Any:
    with database.connect_runtime() as connection:
        return connection.execute(
            _WORKER, (name, run, claim, Jsonb(payload))
        ).fetchone()["result"]


def test_start_requires_batches_and_identical_retry_reuses_run(
    postgres_database: Any,
) -> None:
    seed = _seed_profiling_execution(postgres_database, start=False)
    with pytest.raises(RaiseException, match="profiling_batch_ids_required"):
        start(postgres_database, seed)
    request = uuid4()
    first = start(postgres_database, seed, batches=["2", "1", "2"], request=request)
    assert first["batch_ids"] == ["1", "2"]
    assert all(
        " IN (" in q.sql for target in plan_context(first) for q in target.queries
    )
    second = start(postgres_database, seed, batches=["1", "2"], request=request)
    assert first["status"] == second["status"]
    assert second["context"] is None
    with pytest.raises(RaiseException, match="profiling_request_conflict"):
        start(postgres_database, seed, batches=["3"], request=request)
    with postgres_database.connect_runtime() as connection:
        connection.execute(
            "SELECT mcp.cancel_mcp_profiling_run(%s,%s,'user',%s)",
            (
                seed.context.entra_tenant_id,
                seed.context.entra_object_id,
                first["status"]["run_id"],
            ),
        )


def test_cancel_revokes_claim_and_web_worker_cannot_claim_mcp(
    postgres_database: Any,
) -> None:
    seed = _seed_profiling_execution(postgres_database, start=False)
    run = start(postgres_database, seed, batches=["1"])["status"]["run_id"]
    with postgres_database.connect_owner() as connection:
        connection.execute("SET ROLE gds_web_write")
        assert (
            connection.execute(
                "SELECT * FROM application.claim_next_workflow_run(60)"
            ).fetchone()
            is None
        )
    claim = operation(postgres_database, "claim")
    assert claim["workflow_run_id"] == run
    with postgres_database.connect_runtime() as connection:
        result = connection.execute(
            "SELECT mcp.cancel_mcp_profiling_run(%s,%s,'user',%s) AS result",
            (seed.context.entra_tenant_id, seed.context.entra_object_id, run),
        ).fetchone()["result"]
    assert result["state"] == "cancelled"
    assert result["saved_profile_count"] == 0
    with pytest.raises(RaiseException):
        operation(
            postgres_database, "complete", run, claim["workflow_run_claim_token"], []
        )


class AggregateExecutor:
    async def execute(
        self, *, connection: Any, query: Any, timeout_seconds: int
    ) -> tuple[ProfileMetric, ...]:
        del connection, timeout_seconds
        assert " IN (" in query.sql
        assert query.parameters == ("1", "2")
        return tuple(
            ProfileMetric(
                attribute_id=attribute,
                row_count=10,
                non_null_count=10,
                null_count=0,
                blank_count=0,
                distinct_count=5,
                min_data_length=1,
                max_data_length=2,
                avg_data_length=1.5,
                percent_populated=100.0,
                percent_duplicates=50.0,
                percent_null=0.0,
                percent_blank=0.0,
                percent_distinct=50.0,
            )
            for attribute in query.attribute_ids
        )


@pytest.mark.asyncio
async def test_worker_saves_profiles_atomically_and_status_reports_saved(
    postgres_database: Any,
) -> None:
    seed = _seed_profiling_execution(postgres_database, start=False)
    started = start(postgres_database, seed, batches=["1", "2"])
    database = PostgresDatabase(
        dsn=postgres_database.runtime_dsn(),
        pool_min=1,
        pool_max=2,
        pool_timeout_seconds=5,
        require_runtime_role=True,
        expected_schema_version="1.0.0",
    )
    await database.open()
    try:
        service = ProfilingService(database)
        worker = ProfilingWorker(service, AggregateExecutor())
        claim = await service.worker_operation("claim")
        await worker.run_claim(claim)
        principal = RequestPrincipal(
            ActorKind.HUMAN, seed.context.entra_tenant_id, seed.context.entra_object_id
        )
        status = await service.status(principal, started["status"]["run_id"])
        assert status.state == "completed"
        assert status.saved_profile_count == len(seed.attributes)
        assert status.completed_object_count == len(seed.context.selected_object_ids)
        assert status.model_revision == seed.context.model_revision + 1
    finally:
        await database.close()


def test_context_change_fails_before_execution(postgres_database: Any) -> None:
    seed = _seed_profiling_execution(postgres_database, start=False)
    start(postgres_database, seed, batches=["1"])
    claim = operation(postgres_database, "claim")
    with postgres_database.connect_owner() as connection:
        connection.execute(
            "UPDATE core.object SET object_name = object_name || '_changed' WHERE object_id = %s",
            (seed.context.selected_object_ids[0],),
        )
    with pytest.raises(RaiseException, match="profiling_scope_changed"):
        operation(
            postgres_database,
            "context",
            claim["workflow_run_id"],
            claim["workflow_run_claim_token"],
        )

    with postgres_database.connect_runtime() as connection:
        connection.execute(
            "SELECT mcp.cancel_mcp_profiling_run(%s,%s,'user',%s)",
            (
                seed.context.entra_tenant_id,
                seed.context.entra_object_id,
                claim["workflow_run_id"],
            ),
        )


@pytest.mark.parametrize("zone", ["bronze", "source"])
@pytest.mark.asyncio
async def test_unbatched_source_and_bronze_use_registered_relations(
    postgres_database: Any, zone: str
) -> None:
    seed = _seed_profiling_execution(postgres_database, start=False)
    with postgres_database.connect_owner() as connection:
        connection.execute(
            "UPDATE core.object SET batch_attribute_name = NULL WHERE object_id = ANY(%s)",
            (list(seed.context.selected_object_ids),),
        )
        if zone == "source":
            zone_row = connection.execute(
                "SELECT zone_id FROM reference.zone WHERE lower(zone_code) = 'source'"
            ).fetchone()
            if zone_row is None:
                zone_row = connection.execute(
                    "INSERT INTO reference.zone(zone_code,zone_name) VALUES ('source','Source') RETURNING zone_id"
                ).fetchone()
            connection.execute(
                "UPDATE core.connection SET has_foreign_catalog = TRUE, foreign_catalog = 'foreign_catalog' WHERE connection_id = %s",
                (seed.connection_id,),
            )
            connection.execute(
                "UPDATE core.object SET zone_id = %s, fc_object_schema = 'remote', fc_object_name = object_name WHERE object_id = ANY(%s)",
                (zone_row["zone_id"], list(seed.context.selected_object_ids)),
            )
            connection.execute(
                "UPDATE core.attribute SET fc_attribute_name = 'remote_' || attribute_name WHERE object_id = ANY(%s)",
                (list(seed.context.selected_object_ids),),
            )

    class Executor(AggregateExecutor):
        async def execute(
            self, *, connection: Any, query: Any, timeout_seconds: int
        ) -> tuple[ProfileMetric, ...]:
            assert " WHERE " not in query.sql and query.parameters == ()
            if zone == "source":
                assert "`foreign_catalog`.`remote`." in query.sql
                assert "`remote_profile_attribute_" in query.sql
            else:
                assert f"`{seed.relation_catalog}`." in query.sql
            from dataclasses import replace

            return await super().execute(
                connection=connection,
                query=replace(query, sql=" IN (", parameters=("1", "2")),
                timeout_seconds=timeout_seconds,
            )

    started = start(postgres_database, seed)
    database = PostgresDatabase(
        dsn=postgres_database.runtime_dsn(),
        pool_min=1,
        pool_max=2,
        pool_timeout_seconds=5,
        require_runtime_role=True,
    )
    await database.open()
    try:
        service = ProfilingService(database)
        worker = ProfilingWorker(service, Executor())
        await worker.run_claim(await service.worker_operation("claim"))
        status = await service.status(
            RequestPrincipal(
                ActorKind.HUMAN,
                seed.context.entra_tenant_id,
                seed.context.entra_object_id,
            ),
            started["status"]["run_id"],
        )
        assert status.state == "completed"
    finally:
        await database.close()


def test_locked_model_and_protected_scope_reject_before_queries(
    postgres_database: Any,
) -> None:
    seed = _seed_profiling_execution(postgres_database, start=False)
    with postgres_database.connect_owner() as connection:
        connection.execute(
            "SELECT * FROM application.cancel_workflow_run(%s,%s,'user',%s,%s,%s)",
            (
                seed.context.entra_tenant_id,
                seed.context.entra_object_id,
                seed.context.tenant_id,
                seed.context.model_id,
                seed.workflow_run_id,
            ),
        )
        connection.execute(
            "UPDATE model.model SET is_locked = TRUE WHERE model_id = %s",
            (seed.context.model_id,),
        )
    with pytest.raises(ObjectNotInPrerequisiteState, match="model_locked"):
        start(postgres_database, seed, batches=["1"])
    # A separate fixture Model verifies masking; an agent never unlocks the first Model.
    protected = _seed_profiling_execution(postgres_database, start=False)
    with postgres_database.connect_owner() as connection:
        connection.execute(
            "UPDATE core.attribute SET is_masking_required = TRUE WHERE object_id = %s",
            (protected.context.selected_object_ids[0],),
        )
    with pytest.raises(RaiseException, match="profiling_protected_scope"):
        start(postgres_database, protected, batches=["1"])


def test_expired_worker_claim_can_be_recovered_but_old_claim_cannot_save(
    postgres_database: Any,
) -> None:
    seed = _seed_profiling_execution(postgres_database, start=False)
    run = start(postgres_database, seed, batches=["1"])["status"]["run_id"]
    first = operation(postgres_database, "claim")
    with postgres_database.connect_owner() as connection:
        connection.execute(
            "UPDATE application.workflow_run SET workflow_run_claimed_time = clock_timestamp() - interval '2 minutes', workflow_run_claim_heartbeat_time = clock_timestamp() - interval '2 minutes', workflow_run_claim_expires_time = clock_timestamp() - interval '1 minute' WHERE workflow_run_id = %s",
            (run,),
        )
    recovered = operation(postgres_database, "claim")
    assert recovered["workflow_run_id"] == run
    assert recovered["workflow_run_recovery_count"] == 1
    assert recovered["workflow_run_claim_token"] != first["workflow_run_claim_token"]
    with pytest.raises(RaiseException):
        operation(
            postgres_database, "complete", run, first["workflow_run_claim_token"], []
        )
    operation(postgres_database, "fail", run, recovered["workflow_run_claim_token"])
