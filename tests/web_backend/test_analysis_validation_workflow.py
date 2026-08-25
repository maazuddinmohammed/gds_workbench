from __future__ import annotations

import asyncio
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any, LiteralString, cast
from uuid import UUID

import pytest
from fastapi.testclient import TestClient
from gds_etl_workbench.adapters.auth.identity import IdentityProvider
from gds_etl_workbench.configuration import AuthMode
from gds_etl_workbench.domain.authorization import ActorKind, RequestPrincipal
from gds_etl_workbench.domain.errors import (
    DatabricksStatementFailedError,
    DependencyUnavailableError,
)
from gds_etl_workbench.infrastructure.postgres import (
    ReadIsolation,
    ReadTransaction,
    WriteTransaction,
)
from gds_etl_workbench.tools.databricks.executor import DatabricksSqlConnection
from psycopg.types.json import Jsonb

from gds_workbench_api.features.analysis.validation_execution import (
    AnalysisValidationEndpoint,
    AnalysisValidationEvidence,
    AnalysisValidationPolicy,
    AnalysisValidationQuery,
    AnalysisValidationRelationship,
)
from gds_workbench_api.features.analysis.validation_router import (
    ExecuteAnalysisValidationRunRequest,
)
from gds_workbench_api.features.analysis.validation_service import (
    AnalysisValidationCommitResult,
    AnalysisValidationExecutionContext,
    AnalysisValidationExecutionTarget,
    AnalysisValidationWorkflow,
    DatabaseAnalysisValidationRepository,
)
from gds_workbench_api.features.workflows.authoring.lifecycle import (
    AgentWorkflowEvent,
    AgentWorkflowRunStart,
)
from gds_workbench_api.features.workflows.authoring.plan import (
    ModelWorkflow,
    WorkflowExecutionMode,
)
from gds_workbench_api.main import create_app

_CLAIM_TOKEN = UUID("44444444-4444-4444-4444-444444444444")


def _principal() -> RequestPrincipal:
    return RequestPrincipal(
        actor_kind=ActorKind.HUMAN,
        entra_tenant_id=UUID("11111111-1111-1111-1111-111111111111"),
        entra_object_id=UUID("22222222-2222-2222-2222-222222222222"),
    )


def _relationship(
    analysis_result_id: int,
    *,
    connection_id: int = 91,
) -> AnalysisValidationRelationship:
    return AnalysisValidationRelationship(
        analysis_result_id=analysis_result_id,
        relationship_kind="reference",
        relationship_confidence="high",
        relationship_basis="Registered metadata and aggregate value evidence.",
        analysis_result_status="needs_review",
        analysis_result_is_locked=analysis_result_id % 2 == 0,
        gds_connection_id=connection_id,
        source_context_digest=f"{analysis_result_id:064x}",
        from_endpoint=AnalysisValidationEndpoint(
            relation_catalog="northwind",
            relation_schema="bronze_crm",
            relation_object=f"source_{analysis_result_id}",
            object_id=1000 + analysis_result_id,
            attribute_id=10_000 + analysis_result_id,
            attribute_name="business_id",
            attribute_data_type="BIGINT",
            batch_attribute_name="batch_id",
            batch_attribute_data_type="BIGINT",
        ),
        to_endpoint=AnalysisValidationEndpoint(
            relation_catalog="northwind",
            relation_schema="bronze_crm",
            relation_object=f"target_{analysis_result_id}",
            object_id=2000 + analysis_result_id,
            attribute_id=20_000 + analysis_result_id,
            attribute_name="business_id",
            attribute_data_type="BIGINT",
            batch_attribute_name="batch_id",
            batch_attribute_data_type="BIGINT",
        ),
    )


def _target(analysis_result_id: int) -> AnalysisValidationExecutionTarget:
    return AnalysisValidationExecutionTarget(
        relationship=_relationship(analysis_result_id),
        connection=DatabricksSqlConnection(
            server_hostname="sensitive-host",
            http_path="sensitive-path",
            access_token="sensitive-token",
        ),
    )


def _evidence() -> AnalysisValidationEvidence:
    return AnalysisValidationEvidence(
        validation_source_non_null_count=100,
        validation_source_distinct_count=90,
        validation_target_non_null_count=120,
        validation_target_distinct_count=120,
        validation_source_missing_target_count=0,
        validation_unused_target_count=30,
        validation_duplicate_target_key_count=0,
        validation_result="supported",
    )


def _policy() -> AnalysisValidationPolicy:
    return AnalysisValidationPolicy(
        schema_version="1.0",
        validation_policy_version="1.0.0",
        max_parallel_queries=4,
        max_progress_events=5,
        statement_timeout_seconds=300,
        max_relationships=50_000,
    )


@dataclass
class _Lifecycle:
    bindings: list[tuple[ModelWorkflow, WorkflowExecutionMode | None]] = field(
        default_factory=lambda: []
    )
    events: list[AgentWorkflowEvent] = field(default_factory=lambda: [])
    failure: tuple[str, str] | None = None
    fail_persistence: bool = False

    async def start(
        self,
        principal: RequestPrincipal,
        *,
        tenant_id: int,
        model_id: int,
        workflow_run_id: int,
        expected_workflow: ModelWorkflow,
        expected_execution_mode: WorkflowExecutionMode | None,
        expected_model_revision: int,
    ) -> AgentWorkflowRunStart:
        del principal
        assert (tenant_id, model_id, workflow_run_id) == (7, 18, 1048)
        self.bindings.append((expected_workflow, expected_execution_mode))
        return AgentWorkflowRunStart(
            changed=True,
            workflow_run_id=workflow_run_id,
            workflow_run_state="running",
            started_at=datetime(2026, 8, 24, 10, tzinfo=UTC),
            model_revision=expected_model_revision,
        )

    async def append_event(
        self,
        principal: RequestPrincipal,
        *,
        workflow_run_id: int,
        expected_model_revision: int,
        workflow_run_claim_token: UUID,
        event: AgentWorkflowEvent,
    ) -> None:
        del principal
        assert (workflow_run_id, expected_model_revision) == (1048, 4)
        assert workflow_run_claim_token == _CLAIM_TOKEN
        self.events.append(event)

    async def fail(
        self,
        principal: RequestPrincipal,
        *,
        workflow_run_id: int,
        expected_model_revision: int,
        workflow_run_claim_token: UUID,
        failure_code: str,
        safe_failure_message: str,
    ) -> object:
        del principal
        assert (workflow_run_id, expected_model_revision) == (1048, 4)
        assert workflow_run_claim_token == _CLAIM_TOKEN
        if self.fail_persistence:
            raise DependencyUnavailableError()
        self.failure = (failure_code, safe_failure_message)
        return object()


@dataclass
class _Repository:
    context: AnalysisValidationExecutionContext
    commits: list[list[dict[str, object]]] = field(default_factory=lambda: [])

    async def load_context(
        self,
        principal: RequestPrincipal,
        *,
        tenant_id: int,
        model_id: int,
        workflow_run_id: int,
        expected_model_revision: int,
    ) -> AnalysisValidationExecutionContext:
        assert principal == _principal()
        assert (tenant_id, model_id, workflow_run_id, expected_model_revision) == (
            7,
            18,
            1048,
            4,
        )
        return self.context

    async def commit(
        self,
        principal: RequestPrincipal,
        *,
        workflow_run_id: int,
        expected_model_revision: int,
        workflow_run_claim_token: UUID,
        validation_results: list[dict[str, object]],
    ) -> AnalysisValidationCommitResult:
        assert principal == _principal()
        assert (workflow_run_id, expected_model_revision) == (1048, 4)
        assert workflow_run_claim_token == _CLAIM_TOKEN
        self.commits.append(validation_results)
        return AnalysisValidationCommitResult(
            changed=True,
            workflow_run_id=1048,
            model_id=18,
            model_revision=5,
            submitted_result_count=len(validation_results),
            changed_result_count=len(validation_results),
            workflow_run_state="completed",
        )


@dataclass
class _Executor:
    fail_result_id: int | None = None
    calls: list[int] = field(default_factory=lambda: [])
    active: int = 0
    max_active: int = 0

    async def execute(
        self,
        *,
        connection: DatabricksSqlConnection,
        query: AnalysisValidationQuery,
        timeout_seconds: int,
    ) -> AnalysisValidationEvidence:
        assert "sensitive" not in repr(connection)
        assert timeout_seconds == 300
        self.calls.append(query.analysis_result_id)
        self.active += 1
        self.max_active = max(self.max_active, self.active)
        await asyncio.sleep(0)
        self.active -= 1
        if query.analysis_result_id == self.fail_result_id:
            raise DatabricksStatementFailedError(1)
        return _evidence()


@pytest.mark.asyncio
async def test_validation_workflow_is_deterministic_bounded_and_commits_once() -> None:
    context = AnalysisValidationExecutionContext(
        workflow_run_id=1048,
        model_id=18,
        model_revision=4,
        requested_batch_id="10428",
        targets=tuple(_target(result_id) for result_id in range(1, 46)),
    )
    lifecycle = _Lifecycle()
    repository = _Repository(context=context)
    executor = _Executor()
    workflow = AnalysisValidationWorkflow(
        lifecycle=lifecycle,
        repository=repository,
        executor=executor,
        policy=_policy(),
    )

    await workflow.start(
        _principal(),
        tenant_id=7,
        model_id=18,
        workflow_run_id=1048,
        expected_model_revision=4,
    )
    await workflow.execute_started(
        _principal(),
        tenant_id=7,
        model_id=18,
        workflow_run_id=1048,
        expected_model_revision=4,
        workflow_run_claim_token=_CLAIM_TOKEN,
    )

    assert lifecycle.bindings == [("analysis", None)]
    assert executor.calls == list(range(1, 46))
    assert executor.max_active == 4
    assert len(lifecycle.events) <= _policy().max_progress_events
    assert lifecycle.failure is None
    assert len(repository.commits) == 1
    payload = repository.commits[0]
    assert [item["analysis_result_id"] for item in payload] == list(range(1, 46))
    assert all(
        item["source_context_digest"] == f"{item['analysis_result_id']:064x}"
        for item in payload
    )
    assert all(
        item["validation_policy_version"] == _policy().validation_policy_version
        and item["validation_policy_digest"] == _policy().validation_policy_digest
        for item in payload
    )


@pytest.mark.asyncio
async def test_empty_validation_context_skips_databricks_and_commits_empty() -> None:
    repository = _Repository(
        context=AnalysisValidationExecutionContext(
            workflow_run_id=1048,
            model_id=18,
            model_revision=4,
            requested_batch_id=None,
            targets=(),
        )
    )
    executor = _Executor()
    workflow = AnalysisValidationWorkflow(
        lifecycle=_Lifecycle(),
        repository=repository,
        executor=executor,
        policy=_policy(),
    )

    await workflow.execute_started(
        _principal(),
        tenant_id=7,
        model_id=18,
        workflow_run_id=1048,
        expected_model_revision=4,
        workflow_run_claim_token=_CLAIM_TOKEN,
    )

    assert executor.calls == []
    assert repository.commits == [[]]


@pytest.mark.asyncio
async def test_validation_failure_is_safe_and_never_commits_partial_results() -> None:
    lifecycle = _Lifecycle()
    repository = _Repository(
        context=AnalysisValidationExecutionContext(
            workflow_run_id=1048,
            model_id=18,
            model_revision=4,
            requested_batch_id=None,
            targets=tuple(_target(result_id) for result_id in range(1, 6)),
        )
    )
    workflow = AnalysisValidationWorkflow(
        lifecycle=lifecycle,
        repository=repository,
        executor=_Executor(fail_result_id=3),
        policy=_policy(),
    )

    await workflow.execute_started(
        _principal(),
        tenant_id=7,
        model_id=18,
        workflow_run_id=1048,
        expected_model_revision=4,
        workflow_run_claim_token=_CLAIM_TOKEN,
    )

    assert repository.commits == []
    assert lifecycle.failure is not None
    failure_code, message = lifecycle.failure
    assert failure_code == "databricks_statement_failed"
    assert "sensitive-host" not in message
    assert "sensitive-path" not in message
    assert "sensitive-token" not in message


@pytest.mark.asyncio
async def test_validation_propagates_when_terminal_failure_cannot_be_persisted() -> (
    None
):
    lifecycle = _Lifecycle(fail_persistence=True)
    workflow = AnalysisValidationWorkflow(
        lifecycle=lifecycle,
        repository=_Repository(
            context=AnalysisValidationExecutionContext(
                workflow_run_id=1048,
                model_id=18,
                model_revision=4,
                requested_batch_id=None,
                targets=(_target(1),),
            )
        ),
        executor=_Executor(fail_result_id=1),
        policy=_policy(),
    )

    with pytest.raises(DependencyUnavailableError):
        await workflow.execute_started(
            _principal(),
            tenant_id=7,
            model_id=18,
            workflow_run_id=1048,
            expected_model_revision=4,
            workflow_run_claim_token=_CLAIM_TOKEN,
        )


def _database_context_row() -> dict[str, object]:
    relationship = _relationship(401)
    source = relationship.from_endpoint
    target = relationship.to_endpoint
    return {
        "workflow_run_id": 1048,
        "model_id": 18,
        "model_revision": 4,
        "requested_batch_id": "10428",
        "analysis_result_id": relationship.analysis_result_id,
        "relationship_kind": relationship.relationship_kind,
        "relationship_confidence": relationship.relationship_confidence,
        "relationship_basis": relationship.relationship_basis,
        "analysis_result_status": relationship.analysis_result_status,
        "analysis_result_is_locked": relationship.analysis_result_is_locked,
        "gds_connection_id": relationship.gds_connection_id,
        "source_context_digest": relationship.source_context_digest,
        "from_relation_catalog": source.relation_catalog,
        "from_relation_schema": source.relation_schema,
        "from_relation_object": source.relation_object,
        "from_object_id": source.object_id,
        "from_attribute_id": source.attribute_id,
        "from_attribute_name": source.attribute_name,
        "from_attribute_data_type": source.attribute_data_type,
        "from_batch_attribute_name": source.batch_attribute_name,
        "from_batch_attribute_data_type": source.batch_attribute_data_type,
        "to_relation_catalog": target.relation_catalog,
        "to_relation_schema": target.relation_schema,
        "to_relation_object": target.relation_object,
        "to_object_id": target.object_id,
        "to_attribute_id": target.attribute_id,
        "to_attribute_name": target.attribute_name,
        "to_attribute_data_type": target.attribute_data_type,
        "to_batch_attribute_name": target.batch_attribute_name,
        "to_batch_attribute_data_type": target.batch_attribute_data_type,
    }


@dataclass
class _DatabaseTransaction:
    context_rows: list[dict[str, object]]
    calls: list[tuple[str, tuple[Any, ...]]] = field(default_factory=lambda: [])
    claim_assertion_fails: bool = False

    async def fetch_one(
        self,
        query: LiteralString,
        parameters: tuple[Any, ...] = (),
    ) -> dict[str, Any] | None:
        self.calls.append((query, parameters))
        if "application.assert_workflow_run_claim" in query:
            assert parameters == (1048, _CLAIM_TOKEN)
            if self.claim_assertion_fails:
                return None
            return {"asserted": None}
        if "persist_analysis_validation_results" in query:
            return {
                "changed": True,
                "workflow_run_id": 1048,
                "model_id": 18,
                "model_revision": 5,
                "submitted_result_count": 1,
                "changed_result_count": 1,
            }
        if "complete_workflow_run" in query:
            assert parameters[-2:] == (5, 1)
            return {
                "changed": True,
                "workflow_run_id": 1048,
                "workflow_run_state": "completed",
                "completed_time": datetime(2026, 8, 24, 10, tzinfo=UTC),
            }
        assert "FROM application.workflow_run AS run" in query
        return {
            "model_revision": 4,
            "requested_batch_id": "10428",
            "model_workflow": "analysis",
            "workflow_execution_mode": None,
        }

    async def fetch_all(
        self,
        query: LiteralString,
        parameters: tuple[Any, ...] = (),
    ) -> list[dict[str, Any]]:
        self.calls.append((query, parameters))
        if "get_analysis_validation_connection_values" in query:
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
        assert "get_analysis_validation_execution_context" in query
        return cast(list[dict[str, Any]], self.context_rows)


@dataclass
class _Database:
    context_rows: list[dict[str, object]]
    transaction: _DatabaseTransaction = field(init=False)
    read_isolations: list[ReadIsolation] = field(default_factory=lambda: [])
    write_transactions: int = 0

    def __post_init__(self) -> None:
        self.transaction = _DatabaseTransaction(context_rows=self.context_rows)

    @asynccontextmanager
    async def read_transaction(
        self,
        *,
        isolation: ReadIsolation = ReadIsolation.READ_COMMITTED,
    ) -> AsyncGenerator[ReadTransaction]:
        self.read_isolations.append(isolation)
        yield cast(ReadTransaction, self.transaction)

    @asynccontextmanager
    async def write_transaction(self) -> AsyncGenerator[WriteTransaction]:
        self.write_transactions += 1
        yield cast(WriteTransaction, self.transaction)


@pytest.mark.asyncio
async def test_database_repository_fences_context_credentials_and_environment() -> None:
    database = _Database(context_rows=[_database_context_row()])
    repository = DatabaseAnalysisValidationRepository(
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

    assert database.read_isolations == [ReadIsolation.REPEATABLE_READ]
    assert len(context.targets) == 1
    assert context.targets[0].relationship.source_context_digest == f"{401:064x}"
    assert "sensitive-host" not in repr(context)
    assert "sensitive-path" not in repr(context)
    assert "sensitive-token" not in repr(context)

    binding_query, binding_parameters = database.transaction.calls[0]
    assert "run.model_workflow = 'analysis'" in binding_query
    assert "run.workflow_execution_mode IS NULL" in binding_query
    assert binding_parameters == (7, 18, 1048)
    context_call = next(
        call
        for call in database.transaction.calls
        if "get_analysis_validation_execution_context" in call[0]
    )
    credential_call = next(
        call
        for call in database.transaction.calls
        if "get_analysis_validation_connection_values" in call[0]
    )
    assert context_call[1][-3:] == (1048, 4, "DEV")
    assert credential_call[1][-3:] == (1048, 4, "DEV")


@pytest.mark.asyncio
async def test_database_repository_empty_context_skips_credential_helper() -> None:
    database = _Database(context_rows=[])
    repository = DatabaseAnalysisValidationRepository(
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

    assert context.targets == ()
    assert not any(
        "get_analysis_validation_connection_values" in query
        for query, _parameters in database.transaction.calls
    )


@pytest.mark.asyncio
async def test_database_repository_persists_environment_and_completes_atomically() -> (
    None
):
    database = _Database(context_rows=[])
    repository = DatabaseAnalysisValidationRepository(
        database=database,
        environment_code="DEV",
    )
    validation_results: list[dict[str, object]] = [
        {
            "analysis_result_id": 401,
            "source_context_digest": f"{401:064x}",
            "validation_policy_version": "1.0.0",
            "validation_policy_digest": "a" * 64,
            **_evidence().model_dump(mode="python"),
        }
    ]

    result = await repository.commit(
        _principal(),
        workflow_run_id=1048,
        expected_model_revision=4,
        workflow_run_claim_token=_CLAIM_TOKEN,
        validation_results=validation_results,
    )

    assert result.workflow_run_state == "completed"
    assert result.model_revision == 5
    assert database.write_transactions == 1
    persistence_call = next(
        call
        for call in database.transaction.calls
        if "persist_analysis_validation_results" in call[0]
    )
    completion_call = next(
        call
        for call in database.transaction.calls
        if "complete_workflow_run" in call[0]
    )
    assert persistence_call[1][-2] == "DEV"
    assert isinstance(persistence_call[1][-1], Jsonb)
    assert persistence_call[1][-1].obj == validation_results
    assertion_call = database.transaction.calls[0]
    assert "application.assert_workflow_run_claim" in assertion_call[0]
    assert database.transaction.calls.index(
        persistence_call
    ) < database.transaction.calls.index(completion_call)


@pytest.mark.asyncio
async def test_database_repository_fence_rejection_prevents_validation_writes() -> None:
    database = _Database(context_rows=[])
    database.transaction.claim_assertion_fails = True
    repository = DatabaseAnalysisValidationRepository(
        database=database,
        environment_code="DEV",
    )

    with pytest.raises(DependencyUnavailableError):
        await repository.commit(
            _principal(),
            workflow_run_id=1048,
            expected_model_revision=4,
            workflow_run_claim_token=_CLAIM_TOKEN,
            validation_results=[],
        )

    assert len(database.transaction.calls) == 1
    assert "application.assert_workflow_run_claim" in database.transaction.calls[0][0]


@dataclass
class _StaticValidationService:
    changed: bool = True
    starts: list[tuple[int, int, int, int]] = field(default_factory=lambda: [])
    executions: list[tuple[int, int, int, int]] = field(default_factory=lambda: [])

    async def start(
        self,
        principal: RequestPrincipal,
        *,
        tenant_id: int,
        model_id: int,
        workflow_run_id: int,
        expected_model_revision: int,
    ) -> AgentWorkflowRunStart:
        del principal
        self.starts.append(
            (tenant_id, model_id, workflow_run_id, expected_model_revision)
        )
        return AgentWorkflowRunStart(
            changed=self.changed,
            workflow_run_id=workflow_run_id,
            workflow_run_state="running",
            started_at=datetime(2026, 8, 24, 10, tzinfo=UTC),
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
        del principal
        assert workflow_run_claim_token == _CLAIM_TOKEN
        self.executions.append(
            (tenant_id, model_id, workflow_run_id, expected_model_revision)
        )


def _client(service: _StaticValidationService) -> TestClient:
    return TestClient(
        create_app(
            identity_provider=IdentityProvider(
                AuthMode.DEV,
                local_tenant_id=UUID("11111111-1111-1111-1111-111111111111"),
                local_principal_object_id=UUID("22222222-2222-2222-2222-222222222222"),
            ),
            analysis_validation_workflow_service=service,
        )
    )


def test_validation_route_is_explicit_strict_and_replay_safe() -> None:
    service = _StaticValidationService()
    with _client(service) as client:
        started = client.post(
            "/api/v1/tenants/7/models/18/analysis/validation-runs/1048/execute",
            json={"expected_model_revision": 4},
        )
        rejected = client.post(
            "/api/v1/tenants/7/models/18/analysis/validation-runs/1048/execute",
            json={
                "expected_model_revision": 4,
                "source_context_digest": "a" * 64,
                "databricks_token": "user-supplied-token",
            },
        )

    assert started.status_code == 202
    assert rejected.status_code == 422
    assert (
        ExecuteAnalysisValidationRunRequest.model_validate(
            {"expected_model_revision": 4}, strict=True
        ).expected_model_revision
        == 4
    )
    assert service.starts == [(7, 18, 1048, 4)]
    assert service.executions == []

    replay_service = _StaticValidationService(changed=False)
    with _client(replay_service) as client:
        replay = client.post(
            "/api/v1/tenants/7/models/18/analysis/validation-runs/1048/execute",
            json={"expected_model_revision": 4},
        )
    assert replay.status_code == 200
    assert replay_service.executions == []
