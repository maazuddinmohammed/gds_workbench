from __future__ import annotations

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from typing import Any, LiteralString, cast
from uuid import UUID

import pytest
from fastapi.testclient import TestClient
from gds_etl_workbench.adapters.auth.identity import IdentityProvider
from gds_etl_workbench.configuration import AuthMode
from gds_etl_workbench.domain.authorization import ActorKind, RequestPrincipal
from gds_etl_workbench.domain.databricks import DatabricksSqlConnection
from gds_etl_workbench.domain.errors import (
    DatabricksStatementFailedError,
    DependencyUnavailableError,
    TenantWorkflowConflictError,
)
from gds_etl_workbench.infrastructure.postgres import (
    ReadIsolation,
    ReadTransaction,
    WriteTransaction,
)
from gds_workbench_api.features.profiling.workflow import (
    DatabaseProfilingWorkflowRepository,
    ExecuteProfilingRunRequest,
)
from gds_workbench_api.main import create_app
from gds_workbench_runtime.profiling.execution import (
    ProfileAttribute,
    ProfileMetric,
    ProfileObject,
    ProfileQuery,
)
from gds_workbench_runtime.profiling.workflow import (
    ProfilingCommitResult,
    ProfilingExecutionContext,
    ProfilingExecutionTarget,
    ProfilingRunStart,
    ProfilingWorkflowOrchestrator,
    _intermediate_progress_points,
)

_CLAIM_TOKEN = UUID("33333333-3333-3333-3333-333333333333")


def test_profiling_progress_points_are_bounded() -> None:
    assert _intermediate_progress_points(8) == frozenset()
    assert _intermediate_progress_points(80) == frozenset(range(10, 80, 10))
    points = _intermediate_progress_points(50_000)
    assert len(points) <= 8
    assert 50_000 not in points


def _principal() -> RequestPrincipal:
    return RequestPrincipal(
        actor_kind=ActorKind.HUMAN,
        entra_tenant_id=UUID("11111111-1111-1111-1111-111111111111"),
        entra_object_id=UUID("22222222-2222-2222-2222-222222222222"),
    )


def _target(*, object_id: int, attribute_id: int) -> ProfilingExecutionTarget:
    return ProfilingExecutionTarget(
        object=ProfileObject(
            object_id=object_id,
            connection_id=91,
            catalog="northwind",
            schema="bronze_crm",
            table=f"object_{object_id}",
            batch_attribute_name=None,
            attributes=(
                ProfileAttribute(
                    attribute_id=attribute_id,
                    name=f"attribute_{attribute_id}",
                    data_type="BIGINT",
                ),
            ),
        ),
        connection=DatabricksSqlConnection(
            server_hostname="sensitive-host",
            http_path="sensitive-path",
            access_token="sensitive-token",
        ),
    )


@dataclass
class _Repository:
    context: ProfilingExecutionContext
    events: list[tuple[int, str, str, int | None, int | None]] = field(
        default_factory=lambda: []
    )
    committed_profiles: list[dict[str, object]] | None = None
    failed: tuple[str, str] | None = None
    fail_persistence: bool = False

    async def start(
        self,
        principal: RequestPrincipal,
        *,
        tenant_id: int,
        model_id: int,
        workflow_run_id: int,
        expected_model_revision: int,
    ) -> ProfilingRunStart:
        assert principal == _principal()
        assert (tenant_id, model_id, workflow_run_id, expected_model_revision) == (
            7,
            18,
            1048,
            4,
        )
        return ProfilingRunStart(
            changed=True,
            workflow_run_id=workflow_run_id,
            workflow_run_state="running",
            model_revision=expected_model_revision,
        )

    async def load_context(
        self,
        principal: RequestPrincipal,
        *,
        tenant_id: int,
        model_id: int,
        workflow_run_id: int,
        expected_model_revision: int,
    ) -> ProfilingExecutionContext:
        assert principal == _principal()
        assert (tenant_id, model_id, workflow_run_id, expected_model_revision) == (
            7,
            18,
            1048,
            4,
        )
        return self.context

    async def append_event(
        self,
        principal: RequestPrincipal,
        *,
        workflow_run_id: int,
        expected_model_revision: int,
        workflow_run_claim_token: UUID,
        sequence: int,
        stage: str,
        status: str,
        message: str,
        current: int | None,
        total: int | None,
        finding_count: int,
    ) -> None:
        del principal, workflow_run_id, expected_model_revision, message, finding_count
        assert workflow_run_claim_token == _CLAIM_TOKEN
        self.events.append((sequence, stage, status, current, total))

    async def commit(
        self,
        principal: RequestPrincipal,
        *,
        workflow_run_id: int,
        expected_model_revision: int,
        workflow_run_claim_token: UUID,
        profiles: list[dict[str, object]],
    ) -> ProfilingCommitResult:
        del principal, workflow_run_id
        assert expected_model_revision == 4
        assert workflow_run_claim_token == _CLAIM_TOKEN
        self.committed_profiles = profiles
        return ProfilingCommitResult(
            changed=True,
            workflow_run_id=1048,
            model_id=18,
            model_revision=5,
            submitted_profile_count=len(profiles),
            changed_profile_count=len(profiles),
            workflow_run_state="completed",
        )

    async def fail(
        self,
        principal: RequestPrincipal,
        *,
        workflow_run_id: int,
        expected_model_revision: int,
        workflow_run_claim_token: UUID,
        failure_code: str,
        safe_failure_message: str,
    ) -> None:
        del principal, workflow_run_id, expected_model_revision
        assert workflow_run_claim_token == _CLAIM_TOKEN
        if self.fail_persistence:
            raise DependencyUnavailableError()
        self.failed = (failure_code, safe_failure_message)


@dataclass
class _Executor:
    fail: bool = False
    calls: list[tuple[int, tuple[int, ...], int]] = field(default_factory=lambda: [])

    async def execute(
        self,
        *,
        connection: DatabricksSqlConnection,
        query: ProfileQuery,
        timeout_seconds: int,
    ) -> tuple[ProfileMetric, ...]:
        assert "sensitive" not in repr(connection)
        self.calls.append((query.object_id, query.attribute_ids, timeout_seconds))
        if self.fail:
            raise DatabricksStatementFailedError(1)
        return tuple(
            ProfileMetric(
                attribute_id=attribute_id,
                row_count=10,
                non_null_count=8,
                null_count=2,
                blank_count=None,
                distinct_count=8,
                min_data_length=None,
                max_data_length=None,
                avg_data_length=None,
                percent_populated=80.0,
                percent_duplicates=0.0,
                percent_null=20.0,
                percent_blank=None,
                percent_distinct=100.0,
            )
            for attribute_id in query.attribute_ids
        )


@pytest.mark.asyncio
async def test_profiling_run_executes_all_queries_then_commits_one_complete_payload() -> (
    None
):
    repository = _Repository(
        context=ProfilingExecutionContext(
            workflow_run_id=1048,
            model_id=18,
            model_revision=4,
            requested_batch_id=None,
            targets=(
                _target(object_id=101, attribute_id=1001),
                _target(object_id=102, attribute_id=1002),
            ),
        )
    )
    executor = _Executor()
    orchestrator = ProfilingWorkflowOrchestrator(
        repository=repository,
        executor=executor,
    )

    start = await orchestrator.start(
        _principal(),
        tenant_id=7,
        model_id=18,
        workflow_run_id=1048,
        expected_model_revision=4,
    )
    await orchestrator.execute_started(
        _principal(),
        tenant_id=7,
        model_id=18,
        workflow_run_id=1048,
        expected_model_revision=start.model_revision,
        workflow_run_claim_token=_CLAIM_TOKEN,
    )

    assert start.workflow_run_state == "running"
    assert executor.calls == [(101, (1001,), 300), (102, (1002,), 300)]
    assert repository.failed is None
    assert repository.committed_profiles is not None
    assert [profile["attribute_id"] for profile in repository.committed_profiles] == [
        1001,
        1002,
    ]
    assert all(
        len(str(profile["source_context_digest"])) == 64
        for profile in repository.committed_profiles
    )
    assert repository.events == [
        (2, "profiling.prepare", "running", 0, 2),
        (3, "profiling.execute", "running", 2, 2),
    ]


@pytest.mark.asyncio
async def test_profiling_run_bounds_large_object_progress() -> None:
    object_count = 80
    repository = _Repository(
        context=ProfilingExecutionContext(
            workflow_run_id=1048,
            model_id=18,
            model_revision=4,
            requested_batch_id=None,
            targets=tuple(
                _target(object_id=100 + position, attribute_id=1_000 + position)
                for position in range(1, object_count + 1)
            ),
        )
    )
    orchestrator = ProfilingWorkflowOrchestrator(
        repository=repository,
        executor=_Executor(),
    )

    await orchestrator.execute_started(
        _principal(),
        tenant_id=7,
        model_id=18,
        workflow_run_id=1048,
        expected_model_revision=4,
        workflow_run_claim_token=_CLAIM_TOKEN,
    )

    assert len(repository.events) == 9
    assert [event[0] for event in repository.events] == list(range(2, 11))
    assert [event[3] for event in repository.events] == [
        0,
        10,
        20,
        30,
        40,
        50,
        60,
        70,
        80,
    ]
    assert all(event[4] == object_count for event in repository.events)


@pytest.mark.asyncio
async def test_profiling_failure_is_safe_and_never_commits_partial_profiles() -> None:
    repository = _Repository(
        context=ProfilingExecutionContext(
            workflow_run_id=1048,
            model_id=18,
            model_revision=4,
            requested_batch_id=None,
            targets=(_target(object_id=101, attribute_id=1001),),
        )
    )
    orchestrator = ProfilingWorkflowOrchestrator(
        repository=repository,
        executor=_Executor(fail=True),
    )

    await orchestrator.execute_started(
        _principal(),
        tenant_id=7,
        model_id=18,
        workflow_run_id=1048,
        expected_model_revision=4,
        workflow_run_claim_token=_CLAIM_TOKEN,
    )

    assert repository.committed_profiles is None
    assert repository.failed == (
        "databricks_statement_failed",
        "Databricks rejected a Profiling query. Check registered metadata "
        "and Warehouse permissions.",
    )


@pytest.mark.asyncio
async def test_profiling_propagates_when_terminal_failure_cannot_be_persisted() -> None:
    repository = _Repository(
        context=ProfilingExecutionContext(
            workflow_run_id=1048,
            model_id=18,
            model_revision=4,
            requested_batch_id=None,
            targets=(_target(object_id=101, attribute_id=1001),),
        ),
        fail_persistence=True,
    )
    orchestrator = ProfilingWorkflowOrchestrator(
        repository=repository,
        executor=_Executor(fail=True),
    )

    with pytest.raises(DependencyUnavailableError):
        await orchestrator.execute_started(
            _principal(),
            tenant_id=7,
            model_id=18,
            workflow_run_id=1048,
            expected_model_revision=4,
            workflow_run_claim_token=_CLAIM_TOKEN,
        )

    assert repository.committed_profiles is None
    assert repository.failed is None


@dataclass
class _StaticWorkflowService:
    changed: bool = True
    executed: list[tuple[int, int, int, int]] = field(default_factory=lambda: [])

    async def start(
        self,
        principal: RequestPrincipal,
        *,
        tenant_id: int,
        model_id: int,
        workflow_run_id: int,
        expected_model_revision: int,
    ) -> ProfilingRunStart:
        assert principal.actor_kind is ActorKind.HUMAN
        return ProfilingRunStart(
            changed=self.changed,
            workflow_run_id=workflow_run_id,
            workflow_run_state="running",
            model_revision=expected_model_revision,
        )

    async def execute_started(
        self,
        principal: RequestPrincipal,
        *,
        tenant_id: int,
        model_id: int,
        workflow_run_id: int,
        expected_model_revision: int,
        workflow_run_claim_token: UUID,
    ) -> None:
        assert principal.actor_kind is ActorKind.HUMAN
        assert workflow_run_claim_token == _CLAIM_TOKEN
        self.executed.append(
            (tenant_id, model_id, workflow_run_id, expected_model_revision)
        )


def _client(service: _StaticWorkflowService) -> TestClient:
    return TestClient(
        create_app(
            identity_provider=IdentityProvider(
                AuthMode.DEV,
                local_tenant_id=UUID("11111111-1111-1111-1111-111111111111"),
                local_principal_object_id=UUID("22222222-2222-2222-2222-222222222222"),
            ),
            profiling_workflow_service=service,
        )
    )


def test_execute_endpoint_starts_without_process_local_profiling() -> None:
    service = _StaticWorkflowService()
    with _client(service) as client:
        response = client.post(
            "/api/v1/tenants/7/models/18/profiling/runs/1048/execute",
            json={"expected_model_revision": 4},
        )

    assert response.status_code == 202
    assert (
        ExecuteProfilingRunRequest.model_validate(
            {"expected_model_revision": 4}, strict=True
        ).expected_model_revision
        == 4
    )
    assert response.json() == {
        "changed": True,
        "workflow_run_id": 1048,
        "workflow_run_state": "running",
        "model_revision": 4,
    }
    assert service.executed == []


def test_execute_endpoint_does_not_duplicate_an_already_started_run() -> None:
    service = _StaticWorkflowService(changed=False)
    with _client(service) as client:
        response = client.post(
            "/api/v1/tenants/7/models/18/profiling/runs/1048/execute",
            json={"expected_model_revision": 4},
        )

    assert response.status_code == 200
    assert service.executed == []


@dataclass
class _DatabaseTransaction:
    calls: list[tuple[str, tuple[Any, ...]]] = field(default_factory=lambda: [])
    claim_assertion_fails: bool = False
    start_error: str | None = None

    async def fetch_one(
        self,
        query: LiteralString,
        parameters: tuple[Any, ...] = (),
    ) -> dict[str, Any] | None:
        self.calls.append((query, parameters))
        if "application.start_workflow_run" in query:
            if self.start_error is not None:
                raise RuntimeError(self.start_error)
            return {
                "changed": True,
                "workflow_run_id": 1048,
                "workflow_run_state": "running",
                "started_time": "ignored",
            }
        if "application.assert_workflow_run_claim" in query:
            assert parameters == (1048, _CLAIM_TOKEN)
            if self.claim_assertion_fails:
                return None
            return {"assert_workflow_run_claim": None}
        if "application.persist_profiling_results" in query:
            return {
                "changed": True,
                "workflow_run_id": 1048,
                "model_id": 18,
                "model_revision": 5,
                "submitted_profile_count": 2,
                "changed_profile_count": 2,
            }
        if "application.complete_workflow_run" in query:
            assert parameters[-2:] == (5, 2)
            return {
                "changed": True,
                "workflow_run_id": 1048,
                "workflow_run_state": "completed",
                "completed_time": "ignored",
            }
        if "application.append_workflow_run_event" in query:
            return {"model_event_log_id": 44}
        if "application.fail_workflow_run" in query:
            return {"changed": True}
        assert "FROM application.workflow_run AS run" in query
        return {"model_revision": 4, "model_workflow": "profiling"}

    async def fetch_all(
        self,
        query: LiteralString,
        parameters: tuple[Any, ...] = (),
    ) -> list[dict[str, Any]]:
        self.calls.append((query, parameters))
        if "application.get_profiling_connection_values" in query:
            return [
                {
                    "workflow_run_id": 1048,
                    "model_id": 18,
                    "model_revision": 4,
                    "gds_connection_id": 91,
                    "environment_code": "DEV",
                    "failure_code": None,
                    "failure_message": None,
                    "databricks_host_name": "sensitive-host",
                    "databricks_http_path": "sensitive-path",
                    "databricks_token": "sensitive-token",
                }
            ]
        assert "application.get_profiling_execution_context" in query
        base = {
            "workflow_run_id": 1048,
            "model_id": 18,
            "model_revision": 4,
            "requested_batch_id": "10428",
            "selection_order": 1,
            "source_tenant_id": 7,
            "source_tenant_code": "NWA",
            "gds_connection_id": 91,
            "relation_catalog": "northwind",
            "relation_schema": "bronze_crm",
            "relation_object": "customer_raw",
            "system_id": 31,
            "system_code": "CRM",
            "object_id": 101,
            "batch_attribute_name": "batch_id",
        }
        return [
            {
                **base,
                "attribute_id": 1001,
                "attribute_name": "customer_id",
                "attribute_data_type": "BIGINT",
                "attribute_ordinal_position": 1,
                "is_batch_attribute": False,
            },
            {
                **base,
                "attribute_id": 1002,
                "attribute_name": "batch_id",
                "attribute_data_type": "BIGINT",
                "attribute_ordinal_position": 2,
                "is_batch_attribute": True,
            },
        ]


@dataclass
class _Database:
    transaction: _DatabaseTransaction = field(default_factory=_DatabaseTransaction)
    write_transactions: int = 0

    @asynccontextmanager
    async def read_transaction(
        self,
        *,
        isolation: ReadIsolation = ReadIsolation.READ_COMMITTED,
    ) -> AsyncGenerator[ReadTransaction]:
        del isolation
        yield cast(ReadTransaction, self.transaction)

    @asynccontextmanager
    async def write_transaction(
        self,
        *,
        isolation: ReadIsolation = ReadIsolation.READ_COMMITTED,
    ) -> AsyncGenerator[WriteTransaction]:
        del isolation
        self.write_transactions += 1
        yield cast(WriteTransaction, self.transaction)


@pytest.mark.asyncio
async def test_database_repository_starts_run_without_leaking_database_fields() -> None:
    database = _Database()
    repository = DatabaseProfilingWorkflowRepository(
        database=database,
        environment_code="DEV",
    )

    result = await repository.start(
        _principal(),
        tenant_id=7,
        model_id=18,
        workflow_run_id=1048,
        expected_model_revision=4,
    )

    assert result.model_dump() == {
        "changed": True,
        "workflow_run_id": 1048,
        "workflow_run_state": "running",
        "model_revision": 4,
    }


@pytest.mark.asyncio
async def test_database_repository_maps_tenant_workflow_conflict() -> None:
    database = _Database()
    database.transaction.start_error = "tenant_workflow_conflict"
    repository = DatabaseProfilingWorkflowRepository(
        database=database,
        environment_code="DEV",
    )

    with pytest.raises(TenantWorkflowConflictError):
        await repository.start(
            _principal(),
            tenant_id=7,
            model_id=18,
            workflow_run_id=1048,
            expected_model_revision=4,
        )


@pytest.mark.asyncio
async def test_database_repository_groups_context_without_exposing_credentials() -> (
    None
):
    database = _Database()
    repository = DatabaseProfilingWorkflowRepository(
        database=database,
        environment_code="DEV",
    )

    context = await repository.load_context(
        _principal(),
        tenant_id=7,
        model_id=18,
        workflow_run_id=1048,
        expected_model_revision=4,
    )

    assert context.requested_batch_id == "10428"
    assert len(context.targets) == 1
    target = context.targets[0]
    assert target.object.catalog == "northwind"
    assert target.object.schema_name == "bronze_crm"
    assert [item.attribute_id for item in target.object.attributes] == [1001, 1002]
    assert "sensitive-host" not in repr(context)
    assert "sensitive-path" not in repr(context)
    assert "sensitive-token" not in repr(context)
    assert database.write_transactions == 1


@pytest.mark.asyncio
async def test_database_repository_persists_and_completes_in_one_transaction() -> None:
    database = _Database()
    repository = DatabaseProfilingWorkflowRepository(
        database=database,
        environment_code="DEV",
    )

    result = await repository.commit(
        _principal(),
        workflow_run_id=1048,
        expected_model_revision=4,
        workflow_run_claim_token=_CLAIM_TOKEN,
        profiles=[{"attribute_id": 1001}, {"attribute_id": 1002}],
    )

    assert result.workflow_run_state == "completed"
    assert result.model_revision == 5
    assert database.write_transactions == 1
    write_calls = [query for query, _parameters in database.transaction.calls]
    assert "application.assert_workflow_run_claim" in write_calls[0]
    assert "application.persist_profiling_results" in write_calls[1]
    assert "application.complete_workflow_run" in write_calls[2]


@pytest.mark.asyncio
async def test_database_repository_fences_event_and_failure_before_writing() -> None:
    event_database = _Database()
    event_repository = DatabaseProfilingWorkflowRepository(
        database=event_database,
        environment_code="DEV",
    )

    await event_repository.append_event(
        _principal(),
        workflow_run_id=1048,
        expected_model_revision=4,
        workflow_run_claim_token=_CLAIM_TOKEN,
        sequence=2,
        stage="profiling.prepare",
        status="running",
        message="Profiling queries prepared.",
        current=0,
        total=1,
        finding_count=0,
    )

    event_calls = [query for query, _parameters in event_database.transaction.calls]
    assert "application.assert_workflow_run_claim" in event_calls[0]
    assert "application.append_workflow_run_event" in event_calls[1]

    failure_database = _Database()
    failure_repository = DatabaseProfilingWorkflowRepository(
        database=failure_database,
        environment_code="DEV",
    )

    await failure_repository.fail(
        _principal(),
        workflow_run_id=1048,
        expected_model_revision=4,
        workflow_run_claim_token=_CLAIM_TOKEN,
        failure_code="profiling_failed",
        safe_failure_message="Profiling failed safely.",
    )

    failure_calls = [query for query, _parameters in failure_database.transaction.calls]
    assert "application.assert_workflow_run_claim" in failure_calls[0]
    assert "application.fail_workflow_run" in failure_calls[1]


@pytest.mark.asyncio
@pytest.mark.parametrize("operation", ["event", "commit", "failure"])
async def test_database_repository_stops_before_any_write_when_claim_fence_fails(
    operation: str,
) -> None:
    database = _Database()
    database.transaction.claim_assertion_fails = True
    repository = DatabaseProfilingWorkflowRepository(
        database=database,
        environment_code="DEV",
    )

    with pytest.raises(DependencyUnavailableError):
        if operation == "event":
            await repository.append_event(
                _principal(),
                workflow_run_id=1048,
                expected_model_revision=4,
                workflow_run_claim_token=_CLAIM_TOKEN,
                sequence=2,
                stage="profiling.prepare",
                status="running",
                message="Profiling queries prepared.",
                current=0,
                total=1,
                finding_count=0,
            )
        elif operation == "commit":
            await repository.commit(
                _principal(),
                workflow_run_id=1048,
                expected_model_revision=4,
                workflow_run_claim_token=_CLAIM_TOKEN,
                profiles=[{"attribute_id": 1001}],
            )
        else:
            await repository.fail(
                _principal(),
                workflow_run_id=1048,
                expected_model_revision=4,
                workflow_run_claim_token=_CLAIM_TOKEN,
                failure_code="profiling_failed",
                safe_failure_message="Profiling failed safely.",
            )

    assert len(database.transaction.calls) == 1
    assert "application.assert_workflow_run_claim" in database.transaction.calls[0][0]
