from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from typing import Any, LiteralString, cast
from uuid import UUID

import pytest
from fastapi.testclient import TestClient
from gds_etl_workbench.adapters.auth.identity import IdentityProvider
from gds_etl_workbench.application.authorization import AuthorizationService
from gds_etl_workbench.configuration import AuthMode
from gds_etl_workbench.domain.authorization import ActorKind, RequestPrincipal
from gds_etl_workbench.infrastructure.postgres import WriteTransaction
from pydantic import ValidationError

from gds_workbench_api.capabilities import load_default_agent_capabilities
from gds_workbench_api.main import create_app
from gds_workbench_api.features.workflows.commands import (
    CreateWorkflowRunRequest,
    DatabaseWorkflowCommandService,
    WorkflowRunCommandResult,
)


class StaticWorkflowCommandService:
    async def create_run(
        self,
        principal: RequestPrincipal,
        *,
        tenant_id: int,
        model_id: int,
        correlation_id: UUID,
        command: CreateWorkflowRunRequest,
    ) -> WorkflowRunCommandResult:
        assert principal.actor_kind is ActorKind.HUMAN
        assert (tenant_id, model_id, correlation_id) == (
            7,
            18,
            UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"),
        )
        assert command.selected_object_ids == [101, 102]
        return WorkflowRunCommandResult(
            created=True,
            workflow_run_id=1048,
            workflow_run_state="queued",
            correlation_id=correlation_id,
            prompt_snapshot_count=2,
            model_revision=4,
            selected_scope_digest="a" * 64,
            selected_scope_count=2,
            code_generation_coverage_mode=None,
            sql_generation_guide_id=None,
            sql_generation_guide_version_id=None,
            sql_generation_guide_digest=None,
            created_at=datetime(2026, 8, 24, 14, 0, tzinfo=UTC),
        )


def _app() -> TestClient:
    app = create_app(
        identity_provider=IdentityProvider(
            AuthMode.DEV,
            local_tenant_id=UUID("11111111-1111-1111-1111-111111111111"),
            local_principal_object_id=UUID("22222222-2222-2222-2222-222222222222"),
        ),
        workflow_command_service=StaticWorkflowCommandService(),
    )
    return TestClient(app)


def test_agentic_run_is_explicit_and_queues_one_atomic_run() -> None:
    with _app() as client:
        response = client.post(
            "/api/v1/tenants/7/models/18/runs",
            headers={"Idempotency-Key": "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"},
            json={
                "expected_model_revision": 4,
                "model_workflow": "conceptual",
                "workflow_execution_mode": "tool_assisted",
                "selected_object_ids": [101, 102],
                "agent": {
                    "sdk_code": "openai_agents_sdk",
                    "provider_code": "openai",
                    "model_code": "gpt-5.6-openai",
                    "reasoning_effort_code": "high",
                    "max_turns": 15,
                    "validation_retry_count": 2,
                },
                "prompt_overrides": {"12": 91, "13": 93},
            },
        )

    assert response.status_code == 201
    assert response.json() == {
        "created": True,
        "workflow_run_id": 1048,
        "workflow_run_state": "queued",
        "correlation_id": "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
        "prompt_snapshot_count": 2,
        "model_revision": 4,
        "selected_scope_digest": "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
        "selected_scope_count": 2,
        "code_generation_coverage_mode": None,
        "sql_generation_guide_id": None,
        "sql_generation_guide_version_id": None,
        "sql_generation_guide_digest": None,
        "created_at": "2026-08-24T14:00:00Z",
    }


def test_deterministic_and_agentic_inputs_cannot_be_mixed() -> None:
    with _app() as client:
        response = client.post(
            "/api/v1/tenants/7/models/18/runs",
            headers={"Idempotency-Key": "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"},
            json={
                "expected_model_revision": 4,
                "model_workflow": "profiling",
                "workflow_execution_mode": None,
                "selected_object_ids": [101],
                "agent": {
                    "sdk_code": "openai_agents_sdk",
                    "provider_code": "openai",
                    "model_code": "gpt-5.6-openai",
                    "reasoning_effort_code": "high",
                    "max_turns": 15,
                    "validation_retry_count": 2,
                },
                "prompt_overrides": {},
            },
        )

    assert response.status_code == 422


@pytest.mark.parametrize(
    ("coverage_mode", "selected_object_ids"),
    (("selected_targets", [101, 102]), ("all_eligible_targets", [])),
)
def test_code_generation_coverage_is_explicit(
    coverage_mode: str,
    selected_object_ids: list[int],
) -> None:
    command = CreateWorkflowRunRequest.model_validate(
        {
            "expected_model_revision": 4,
            "model_workflow": "code_generation",
            "selected_object_ids": selected_object_ids,
            "modeled_entity_type": "logical_entity",
            "code_generation_coverage_mode": coverage_mode,
            "sql_generation_guide_version_id": 91,
            "prompt_overrides": {},
        },
        strict=True,
    )

    assert command.code_generation_coverage_mode == coverage_mode
    assert command.sql_generation_guide_version_id == 91


@pytest.mark.parametrize(
    ("coverage_mode", "selected_object_ids"),
    (("selected_targets", []), ("all_eligible_targets", [101])),
)
def test_code_generation_rejects_mismatched_coverage_intent(
    coverage_mode: str,
    selected_object_ids: list[int],
) -> None:
    with pytest.raises(ValidationError, match="Code Generation coverage"):
        CreateWorkflowRunRequest.model_validate(
            {
                "expected_model_revision": 4,
                "model_workflow": "code_generation",
                "selected_object_ids": selected_object_ids,
                "modeled_entity_type": "logical_entity",
                "code_generation_coverage_mode": coverage_mode,
                "prompt_overrides": {},
            },
            strict=True,
        )


def test_mapping_request_selects_one_pair_without_choosing_the_route() -> None:
    command = CreateWorkflowRunRequest.model_validate(
        {
            "expected_model_revision": 4,
            "model_workflow": "mapping",
            "workflow_execution_mode": "one_shot",
            "selected_object_ids": [101],
            "mapping_operation": "build",
            "mapping_coverage_mode": "selected_targets",
            "mapping_artifact_type": "sql_file",
            "mapping_source_system_id": 77,
            "mapping_object_output_template_id": 501,
            "mapping_attribute_output_template_id": 502,
            "prompt_overrides": {},
        },
        strict=True,
    )

    assert command.modeled_entity_type is None
    assert command.mapping_operation == "build"
    assert command.mapping_coverage_mode == "selected_targets"
    assert command.mapping_artifact_type == "sql_file"
    assert command.mapping_source_system_id == 77
    assert command.mapping_object_output_template_id == 501
    assert command.mapping_attribute_output_template_id == 502


@pytest.mark.parametrize(
    ("object_template_id", "attribute_template_id"),
    ((501, None), (None, 502)),
)
def test_mapping_request_allows_each_output_template_selection_independently(
    object_template_id: int | None,
    attribute_template_id: int | None,
) -> None:
    command = CreateWorkflowRunRequest.model_validate(
        {
            "expected_model_revision": 4,
            "model_workflow": "mapping",
            "workflow_execution_mode": "one_shot",
            "selected_object_ids": [101],
            "mapping_operation": "build",
            "mapping_coverage_mode": "selected_targets",
            "mapping_artifact_type": "sql_file",
            "mapping_source_system_id": 77,
            "mapping_object_output_template_id": object_template_id,
            "mapping_attribute_output_template_id": attribute_template_id,
            "prompt_overrides": {},
        },
        strict=True,
    )

    assert command.mapping_object_output_template_id == object_template_id
    assert command.mapping_attribute_output_template_id == attribute_template_id


@pytest.mark.parametrize(
    ("field_name", "field_value"),
    (
        ("mapping_object_output_template_id", 0),
        ("mapping_object_output_template_id", -1),
        ("mapping_attribute_output_template_id", 0),
        ("mapping_attribute_output_template_id", -1),
    ),
)
def test_mapping_request_rejects_nonpositive_output_template_id(
    field_name: str,
    field_value: int,
) -> None:
    payload: dict[str, object] = {
        "expected_model_revision": 4,
        "model_workflow": "mapping",
        "workflow_execution_mode": "one_shot",
        "selected_object_ids": [101],
        "mapping_operation": "build",
        "mapping_coverage_mode": "selected_targets",
        "mapping_artifact_type": "sql_file",
        "mapping_source_system_id": 77,
        "prompt_overrides": {},
        field_name: field_value,
    }

    with pytest.raises(ValidationError):
        CreateWorkflowRunRequest.model_validate(payload, strict=True)


@pytest.mark.parametrize(
    "field_name",
    (
        "mapping_object_output_template_id",
        "mapping_attribute_output_template_id",
    ),
)
def test_non_mapping_request_rejects_output_template_selection(
    field_name: str,
) -> None:
    payload: dict[str, object] = {
        "expected_model_revision": 4,
        "model_workflow": "profiling",
        "selected_object_ids": [101],
        "prompt_overrides": {},
        field_name: 501,
    }

    with pytest.raises(ValidationError, match="Mapping inputs are unavailable"):
        CreateWorkflowRunRequest.model_validate(payload, strict=True)


@pytest.mark.parametrize(
    "invalid_fields",
    (
        {"modeled_entity_type": "logical_entity"},
        {"mapping_source_system_id": None},
    ),
)
def test_mapping_request_rejects_a_caller_route_or_incomplete_pair(
    invalid_fields: dict[str, object],
) -> None:
    payload: dict[str, object] = {
        "expected_model_revision": 4,
        "model_workflow": "mapping",
        "workflow_execution_mode": "one_shot",
        "selected_object_ids": [101],
        "mapping_operation": "build",
        "mapping_coverage_mode": "selected_targets",
        "mapping_artifact_type": "sql_file",
        "mapping_source_system_id": 77,
        "prompt_overrides": {},
    }
    payload.update(invalid_fields)

    with _app() as client:
        response = client.post(
            "/api/v1/tenants/7/models/18/runs",
            headers={"Idempotency-Key": "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"},
            json=payload,
        )

    assert response.status_code == 422


class WorkflowCommandTransaction:
    async def fetch_one(
        self,
        query: LiteralString,
        parameters: tuple[Any, ...] = (),
    ) -> dict[str, Any] | None:
        if "security.authorize_tenant_operation" in query:
            assert parameters[-2:] == (7, "tenant_model_write")
            return {
                "principal_id": 41,
                "principal_display_name": "Maaz",
                "is_super_admin": False,
                "effective_role": "tenant_admin",
                "authorized": True,
                "denial_code": None,
                "lock_owner_display_name": "Maaz",
                "lock_expires_time": datetime(2026, 8, 24, 15, 0, tzinfo=UTC),
            }
        if "FROM model.model AS target_model" in query:
            assert parameters == (7, 18)
            return {"model_revision": 4}
        assert "application.create_workflow_run" in query
        assert len(parameters) == 26
        assert parameters[3:7] == (18, 4, "profiling", None)
        assert parameters[13] == [101, 102]
        assert parameters[15] == "10428"
        assert parameters[18:] == (None, None, None, None, None, None, None, None)
        return {
            "created": True,
            "workflow_run_id": 1048,
            "workflow_run_state": "queued",
            "correlation_id": UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"),
            "prompt_snapshot_count": 0,
            "model_revision": 4,
            "selected_scope_digest": "a" * 64,
            "selected_scope_count": 2,
            "code_generation_coverage_mode": None,
            "sql_generation_guide_id": None,
            "sql_generation_guide_version_id": None,
            "sql_generation_guide_digest": None,
            "created_at": datetime(2026, 8, 24, 14, 0, tzinfo=UTC),
        }


class WorkflowCommandDatabase:
    @asynccontextmanager
    async def write_transaction(
        self,
    ) -> AsyncGenerator[WriteTransaction]:
        yield cast(WriteTransaction, WorkflowCommandTransaction())


@pytest.mark.asyncio
async def test_database_command_derives_actor_and_calls_only_governed_function() -> (
    None
):
    service = DatabaseWorkflowCommandService(
        database=WorkflowCommandDatabase(),
        authorizer=AuthorizationService(),
        agent_capability_registry=load_default_agent_capabilities(),
    )
    principal = RequestPrincipal(
        actor_kind=ActorKind.HUMAN,
        entra_tenant_id=UUID("11111111-1111-1111-1111-111111111111"),
        entra_object_id=UUID("22222222-2222-2222-2222-222222222222"),
    )
    command = CreateWorkflowRunRequest.model_validate(
        {
            "expected_model_revision": 4,
            "model_workflow": "profiling",
            "workflow_execution_mode": None,
            "selected_object_ids": [101, 102],
            "requested_batch_id": "10428",
            "prompt_overrides": {},
        },
        strict=True,
    )

    result = await service.create_run(
        principal,
        tenant_id=7,
        model_id=18,
        correlation_id=UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"),
        command=command,
    )

    assert result.workflow_run_id == 1048
    assert result.workflow_run_state == "queued"


class MappingWorkflowCommandTransaction(WorkflowCommandTransaction):
    async def fetch_one(
        self,
        query: LiteralString,
        parameters: tuple[Any, ...] = (),
    ) -> dict[str, Any] | None:
        if "application.create_workflow_run" not in query:
            return await super().fetch_one(query, parameters)
        assert len(parameters) == 26
        assert parameters[3:7] == (18, 4, "mapping", "one_shot")
        assert parameters[13] == [101]
        assert parameters[18:] == (
            "build",
            "selected_targets",
            "sql_file",
            77,
            501,
            502,
            None,
            None,
        )
        return {
            "created": True,
            "workflow_run_id": 1049,
            "workflow_run_state": "queued",
            "correlation_id": UUID("bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb"),
            "prompt_snapshot_count": 1,
            "model_revision": 4,
            "selected_scope_digest": "b" * 64,
            "selected_scope_count": 1,
            "code_generation_coverage_mode": None,
            "sql_generation_guide_id": None,
            "sql_generation_guide_version_id": None,
            "sql_generation_guide_digest": None,
            "created_at": datetime(2026, 8, 24, 14, 1, tzinfo=UTC),
        }


class MappingWorkflowCommandDatabase:
    @asynccontextmanager
    async def write_transaction(
        self,
    ) -> AsyncGenerator[WriteTransaction]:
        yield cast(WriteTransaction, MappingWorkflowCommandTransaction())


@pytest.mark.asyncio
async def test_database_command_forwards_mapping_output_template_ids() -> None:
    service = DatabaseWorkflowCommandService(
        database=MappingWorkflowCommandDatabase(),
        authorizer=AuthorizationService(),
        agent_capability_registry=load_default_agent_capabilities(),
    )
    principal = RequestPrincipal(
        actor_kind=ActorKind.HUMAN,
        entra_tenant_id=UUID("11111111-1111-1111-1111-111111111111"),
        entra_object_id=UUID("22222222-2222-2222-2222-222222222222"),
    )
    command = CreateWorkflowRunRequest.model_validate(
        {
            "expected_model_revision": 4,
            "model_workflow": "mapping",
            "workflow_execution_mode": "one_shot",
            "selected_object_ids": [101],
            "mapping_operation": "build",
            "mapping_coverage_mode": "selected_targets",
            "mapping_artifact_type": "sql_file",
            "mapping_source_system_id": 77,
            "mapping_object_output_template_id": 501,
            "mapping_attribute_output_template_id": 502,
            "prompt_overrides": {},
        },
        strict=True,
    )

    result = await service.create_run(
        principal,
        tenant_id=7,
        model_id=18,
        correlation_id=UUID("bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb"),
        command=command,
    )

    assert result.workflow_run_id == 1049
