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
from gds_etl_workbench.domain.errors import InvalidRequestError
from gds_etl_workbench.infrastructure.postgres import WriteTransaction
from gds_workbench_api.capabilities import (
    AgentCapabilityRegistry,
    AgentModelExecutionProfile,
    AgentRunSelection,
    load_default_agent_capabilities,
)
from gds_workbench_api.features.workflows.commands import (
    CreateWorkflowRunRequest,
    DatabaseWorkflowCommandService,
    WorkflowRunCommandResult,
)
from gds_workbench_api.main import create_app
from pydantic import ValidationError


@pytest.mark.parametrize("mode", [None, "tool_assisted"])
def test_metadata_enrichment_request_requires_one_shot(mode: str | None) -> None:
    with pytest.raises(ValidationError, match="requires one-shot"):
        CreateWorkflowRunRequest.model_validate(
            {
                "expected_model_revision": 4,
                "model_workflow": "metadata_enrichment",
                "workflow_execution_mode": mode,
                "selected_object_ids": [101],
            },
            strict=True,
        )


def test_metadata_enrichment_rejects_an_unbounded_selection() -> None:
    with pytest.raises(ValidationError, match="at most 200"):
        CreateWorkflowRunRequest.model_validate(
            {
                "expected_model_revision": 4,
                "model_workflow": "metadata_enrichment",
                "workflow_execution_mode": "one_shot",
                "selected_object_ids": list(range(1, 202)),
            },
            strict=True,
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
                    "model_code": "foundry-primary",
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
                    "model_code": "foundry-primary",
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


def test_validation_requires_an_exact_case_insensitive_system_selection() -> None:
    command = CreateWorkflowRunRequest.model_validate(
        {
            "expected_model_revision": 4,
            "model_workflow": "validation",
            "workflow_execution_mode": None,
            "selected_object_ids": [],
            "selected_system_codes": [" CRM ", "ERP"],
            "prompt_overrides": {},
        },
        strict=True,
    )

    assert command.selected_object_ids == []
    assert command.selected_system_codes == ["CRM", "ERP"]


@pytest.mark.parametrize(
    "updates",
    (
        {"selected_system_codes": []},
        {"selected_system_codes": ["CRM", "crm"]},
        {"selected_object_ids": [101]},
        {"workflow_execution_mode": "one_shot"},
    ),
)
def test_validation_rejects_ambiguous_scope_or_execution_mode(
    updates: dict[str, object],
) -> None:
    with pytest.raises(ValidationError):
        CreateWorkflowRunRequest.model_validate(
            {
                "expected_model_revision": 4,
                "model_workflow": "validation",
                "workflow_execution_mode": None,
                "selected_object_ids": [],
                "selected_system_codes": ["CRM"],
                "prompt_overrides": {},
                **updates,
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
    async def fetch_all(
        self, query: LiteralString, parameters: tuple[Any, ...] = ()
    ) -> list[dict[str, Any]]:
        assert "SELECT DISTINCT object.source_tenant_id" in query or (
            "core.tenant AS tenant" in query and "effective_role" in query
        )
        return []

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
            return {
                "model_revision": 4,
                "default_agent_sdk_code": "openai_agents_sdk",
                "default_agent_provider_code": "microsoft_foundry",
                "default_agent_model_code": "foundry-primary",
                "default_reasoning_effort_code": "medium",
                "default_max_turns": 10,
                "default_validation_retry_count": 2,
            }
        assert "application.create_workflow_run" in query
        assert len(parameters) == 27
        assert parameters[3:7] == (18, 4, "profiling", None)
        assert parameters[13] == [101, 102]
        assert parameters[14] == []
        assert parameters[16] == "10428"
        assert parameters[19:] == (None, None, None, None, None, None, None, None)
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
async def test_database_command_derives_actor_and_calls_only_governed_function() -> None:
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


@pytest.mark.asyncio
async def test_database_command_validates_agent_against_the_requested_execution_mode() -> None:
    registry = load_default_agent_capabilities()
    databricks_model = next(model for model in registry.models if model.code == "foundry-primary")
    restricted = databricks_model.model_copy(
        update={
            "execution_profiles": (
                AgentModelExecutionProfile(
                    sdk_code="openai_agents_sdk",
                    execution_mode="tool_assisted",
                    reasoning_effort_codes=("medium",),
                ),
            )
        }
    )
    registry = registry.model_copy(
        update={
            "models": tuple(
                restricted if model.code == restricted.code else model for model in registry.models
            )
        }
    )
    service = DatabaseWorkflowCommandService(
        database=WorkflowCommandDatabase(),
        authorizer=AuthorizationService(),
        agent_capability_registry=registry,
    )
    command = CreateWorkflowRunRequest.model_validate(
        {
            "expected_model_revision": 4,
            "model_workflow": "analysis",
            "workflow_execution_mode": "one_shot",
            "selected_object_ids": [101],
            "agent": {
                "sdk_code": "openai_agents_sdk",
                "provider_code": "microsoft_foundry",
                "model_code": "foundry-primary",
                "reasoning_effort_code": "medium",
                "max_turns": 10,
                "validation_retry_count": 2,
            },
            "prompt_overrides": {},
        },
        strict=True,
    )

    with pytest.raises(InvalidRequestError, match="incompatible"):
        await service.create_run(
            RequestPrincipal(
                actor_kind=ActorKind.HUMAN,
                entra_tenant_id=UUID("11111111-1111-1111-1111-111111111111"),
                entra_object_id=UUID("22222222-2222-2222-2222-222222222222"),
            ),
            tenant_id=7,
            model_id=18,
            correlation_id=UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"),
            command=command,
        )


class _RecordingCapabilityRegistry:
    def __init__(self) -> None:
        self.execution_modes: list[str | None] = []
        self.selections: list[AgentRunSelection] = []

    def resolve_default_selection(self, **values: Any) -> AgentRunSelection:
        selection = load_default_agent_capabilities().resolve_default_selection(**values)
        self.validate_selection(selection, execution_mode=values["execution_mode"])
        return selection

    def validate_selection(
        self,
        selection: AgentRunSelection,
        *,
        execution_mode: str | None = None,
    ) -> None:
        self.selections.append(selection)
        self.execution_modes.append(execution_mode)
        raise InvalidRequestError("stop after capability validation")


@pytest.mark.asyncio
async def test_database_command_validates_code_generation_against_internal_tool_assisted_mode() -> (
    None
):
    registry = _RecordingCapabilityRegistry()
    service = DatabaseWorkflowCommandService(
        database=WorkflowCommandDatabase(),
        authorizer=AuthorizationService(),
        agent_capability_registry=cast(AgentCapabilityRegistry, registry),
    )
    command = CreateWorkflowRunRequest.model_validate(
        {
            "expected_model_revision": 4,
            "model_workflow": "code_generation",
            "selected_object_ids": [101],
            "modeled_entity_type": "logical_entity",
            "code_generation_coverage_mode": "selected_targets",
            "agent": {
                "sdk_code": "openai_agents_sdk",
                "provider_code": "microsoft_foundry",
                "model_code": "foundry-primary",
                "reasoning_effort_code": "medium",
                "max_turns": 10,
                "validation_retry_count": 2,
            },
            "prompt_overrides": {},
        },
        strict=True,
    )

    with pytest.raises(InvalidRequestError, match="stop after capability validation"):
        await service.create_run(
            RequestPrincipal(
                actor_kind=ActorKind.HUMAN,
                entra_tenant_id=UUID("11111111-1111-1111-1111-111111111111"),
                entra_object_id=UUID("22222222-2222-2222-2222-222222222222"),
            ),
            tenant_id=7,
            model_id=18,
            correlation_id=UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"),
            command=command,
        )

    assert registry.execution_modes == ["tool_assisted"]


@pytest.mark.asyncio
async def test_database_command_validates_validation_against_internal_tool_assisted_mode() -> None:
    registry = _RecordingCapabilityRegistry()
    service = DatabaseWorkflowCommandService(
        database=WorkflowCommandDatabase(),
        authorizer=AuthorizationService(),
        agent_capability_registry=cast(AgentCapabilityRegistry, registry),
    )
    command = CreateWorkflowRunRequest.model_validate(
        {
            "expected_model_revision": 4,
            "model_workflow": "validation",
            "selected_object_ids": [],
            "selected_system_codes": ["CRM", "ERP"],
            "agent": {
                "sdk_code": "openai_agents_sdk",
                "provider_code": "microsoft_foundry",
                "model_code": "foundry-primary",
                "reasoning_effort_code": "medium",
                "max_turns": 10,
                "validation_retry_count": 2,
            },
            "prompt_overrides": {},
        },
        strict=True,
    )

    with pytest.raises(InvalidRequestError, match="stop after capability validation"):
        await service.create_run(
            RequestPrincipal(
                actor_kind=ActorKind.HUMAN,
                entra_tenant_id=UUID("11111111-1111-1111-1111-111111111111"),
                entra_object_id=UUID("22222222-2222-2222-2222-222222222222"),
            ),
            tenant_id=7,
            model_id=18,
            correlation_id=UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"),
            command=command,
        )

    assert registry.execution_modes == ["tool_assisted"]


class _ImplicitDefaultWorkflowCommandTransaction(WorkflowCommandTransaction):
    def __init__(self, *, model_code: str = "foundry-primary") -> None:
        self.model_code = model_code
        self.create_called = False

    async def fetch_one(
        self,
        query: LiteralString,
        parameters: tuple[Any, ...] = (),
    ) -> dict[str, Any] | None:
        if "FROM model.model AS target_model" in query:
            row = await super().fetch_one(query, parameters)
            assert row is not None
            return {**row, "default_agent_model_code": self.model_code}
        if "application.create_workflow_run" in query:
            self.create_called = True
            raise AssertionError("governed create must follow capability validation")
        return await super().fetch_one(query, parameters)


class _ImplicitDefaultWorkflowCommandDatabase:
    def __init__(self, transaction: _ImplicitDefaultWorkflowCommandTransaction) -> None:
        self.transaction = transaction

    @asynccontextmanager
    async def write_transaction(self) -> AsyncGenerator[WriteTransaction]:
        yield cast(WriteTransaction, self.transaction)


class _SuccessfulImplicitDefaultWorkflowCommandTransaction(WorkflowCommandTransaction):
    def __init__(self) -> None:
        self.create_parameters: tuple[Any, ...] | None = None

    async def fetch_one(
        self,
        query: LiteralString,
        parameters: tuple[Any, ...] = (),
    ) -> dict[str, Any] | None:
        if "application.create_workflow_run" not in query:
            return await super().fetch_one(query, parameters)
        self.create_parameters = parameters
        return {
            "created": True,
            "workflow_run_id": 1050,
            "workflow_run_state": "queued",
            "correlation_id": UUID("cccccccc-cccc-cccc-cccc-cccccccccccc"),
            "prompt_snapshot_count": 1,
            "model_revision": 4,
            "selected_scope_digest": "c" * 64,
            "selected_scope_count": 1,
            "code_generation_coverage_mode": None,
            "sql_generation_guide_id": None,
            "sql_generation_guide_version_id": None,
            "sql_generation_guide_digest": None,
            "created_at": datetime(2026, 8, 24, 14, 2, tzinfo=UTC),
        }


class _SuccessfulImplicitDefaultWorkflowCommandDatabase:
    def __init__(
        self,
        transaction: _SuccessfulImplicitDefaultWorkflowCommandTransaction,
    ) -> None:
        self.transaction = transaction

    @asynccontextmanager
    async def write_transaction(self) -> AsyncGenerator[WriteTransaction]:
        yield cast(WriteTransaction, self.transaction)


@pytest.mark.asyncio
async def test_database_command_passes_validated_defaults_to_governed_creation() -> None:
    transaction = _SuccessfulImplicitDefaultWorkflowCommandTransaction()
    service = DatabaseWorkflowCommandService(
        database=_SuccessfulImplicitDefaultWorkflowCommandDatabase(transaction),
        authorizer=AuthorizationService(),
        agent_capability_registry=load_default_agent_capabilities(),
    )
    command = CreateWorkflowRunRequest.model_validate(
        {
            "expected_model_revision": 4,
            "model_workflow": "conceptual",
            "workflow_execution_mode": "one_shot",
            "selected_object_ids": [101],
            "prompt_overrides": {},
        },
        strict=True,
    )

    result = await service.create_run(
        RequestPrincipal(
            actor_kind=ActorKind.HUMAN,
            entra_tenant_id=UUID("11111111-1111-1111-1111-111111111111"),
            entra_object_id=UUID("22222222-2222-2222-2222-222222222222"),
        ),
        tenant_id=7,
        model_id=18,
        correlation_id=UUID("cccccccc-cccc-cccc-cccc-cccccccccccc"),
        command=command,
    )

    assert result.workflow_run_id == 1050
    assert transaction.create_parameters is not None
    assert transaction.create_parameters[3:7] == (18, 4, "conceptual", "one_shot")
    assert transaction.create_parameters[7:13] == (
        "openai_agents_sdk",
        "microsoft_foundry",
        "foundry-primary",
        "medium",
        10,
        2,
    )


@pytest.mark.parametrize(
    ("payload", "expected_mode"),
    (
        (
            {
                "expected_model_revision": 4,
                "model_workflow": "conceptual",
                "workflow_execution_mode": "one_shot",
                "selected_object_ids": [101],
                "prompt_overrides": {},
            },
            "one_shot",
        ),
        (
            {
                "expected_model_revision": 4,
                "model_workflow": "code_generation",
                "selected_object_ids": [101],
                "modeled_entity_type": "logical_entity",
                "code_generation_coverage_mode": "selected_targets",
                "prompt_overrides": {},
            },
            "tool_assisted",
        ),
    ),
)
@pytest.mark.asyncio
async def test_database_command_validates_implicit_model_agent_default(
    payload: dict[str, object],
    expected_mode: str,
) -> None:
    registry = _RecordingCapabilityRegistry()
    transaction = _ImplicitDefaultWorkflowCommandTransaction()
    service = DatabaseWorkflowCommandService(
        database=_ImplicitDefaultWorkflowCommandDatabase(transaction),
        authorizer=AuthorizationService(),
        agent_capability_registry=cast(AgentCapabilityRegistry, registry),
    )

    with pytest.raises(InvalidRequestError, match="stop after capability validation"):
        await service.create_run(
            RequestPrincipal(
                actor_kind=ActorKind.HUMAN,
                entra_tenant_id=UUID("11111111-1111-1111-1111-111111111111"),
                entra_object_id=UUID("22222222-2222-2222-2222-222222222222"),
            ),
            tenant_id=7,
            model_id=18,
            correlation_id=UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"),
            command=CreateWorkflowRunRequest.model_validate(payload, strict=True),
        )

    assert registry.selections == [
        AgentRunSelection(
            sdk_code="openai_agents_sdk",
            provider_code="microsoft_foundry",
            model_code="foundry-primary",
            reasoning_effort_code="medium",
            max_turns=10,
            validation_retry_count=2,
        )
    ]
    assert registry.execution_modes == [expected_mode]
    assert transaction.create_called is False


@pytest.mark.asyncio
async def test_database_command_recovers_retired_implicit_model_agent_default() -> None:
    class RetiredDefaults(_SuccessfulImplicitDefaultWorkflowCommandTransaction):
        async def fetch_one(
            self,
            query: LiteralString,
            parameters: tuple[Any, ...] = (),
        ) -> dict[str, Any] | None:
            row = await super().fetch_one(query, parameters)
            if row is not None and "FROM model.model AS target_model" in query:
                row.update(
                    default_agent_sdk_code="langchain_create_agent",
                    default_agent_provider_code="databricks",
                    default_agent_model_code="removed-model",
                )
            return row

    transaction = RetiredDefaults()
    service = DatabaseWorkflowCommandService(
        database=_SuccessfulImplicitDefaultWorkflowCommandDatabase(transaction),
        authorizer=AuthorizationService(),
        agent_capability_registry=load_default_agent_capabilities(),
    )
    command = CreateWorkflowRunRequest.model_validate(
        {
            "expected_model_revision": 4,
            "model_workflow": "conceptual",
            "workflow_execution_mode": "one_shot",
            "selected_object_ids": [101],
        },
        strict=True,
    )
    await service.create_run(
        RequestPrincipal(
            actor_kind=ActorKind.HUMAN,
            entra_tenant_id=UUID("11111111-1111-1111-1111-111111111111"),
            entra_object_id=UUID("22222222-2222-2222-2222-222222222222"),
        ),
        tenant_id=7,
        model_id=18,
        correlation_id=UUID("cccccccc-cccc-cccc-cccc-cccccccccccc"),
        command=command,
    )
    assert transaction.create_parameters is not None
    assert transaction.create_parameters[7:10] == (
        "openai_agents_sdk",
        "microsoft_foundry",
        "foundry-primary",
    )


class MappingWorkflowCommandTransaction(WorkflowCommandTransaction):
    create_parameters: tuple[Any, ...] | None = None

    async def fetch_one(
        self,
        query: LiteralString,
        parameters: tuple[Any, ...] = (),
    ) -> dict[str, Any] | None:
        if "application.create_workflow_run" not in query:
            return await super().fetch_one(query, parameters)
        assert len(parameters) == 27
        self.create_parameters = parameters
        assert parameters[3:6] == (18, 4, "mapping")
        assert parameters[6] in {"one_shot", "tool_assisted"}
        assert parameters[13] == [101]
        assert parameters[14] == []
        assert parameters[19:22] == (
            "build",
            "selected_targets",
            77,
        )
        assert parameters[24:] == (None, None, None)
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
    def __init__(self, transaction: MappingWorkflowCommandTransaction) -> None:
        self.transaction = transaction

    @asynccontextmanager
    async def write_transaction(
        self,
    ) -> AsyncGenerator[WriteTransaction]:
        yield cast(WriteTransaction, self.transaction)


@pytest.mark.asyncio
@pytest.mark.parametrize("mode", ("one_shot", "tool_assisted"))
@pytest.mark.parametrize(
    "template_fields",
    (
        {},
        {
            "mapping_object_output_template_id": None,
            "mapping_attribute_output_template_id": None,
        },
        {"mapping_object_output_template_id": 501},
        {"mapping_attribute_output_template_id": 502},
        {
            "mapping_object_output_template_id": 501,
            "mapping_attribute_output_template_id": 502,
        },
    ),
    ids=("omitted", "null", "custom-object", "custom-attribute", "custom-both"),
)
async def test_database_command_forwards_mapping_output_template_selection(
    mode: str, template_fields: dict[str, int | None]
) -> None:
    transaction = MappingWorkflowCommandTransaction()
    service = DatabaseWorkflowCommandService(
        database=MappingWorkflowCommandDatabase(transaction),
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
            "workflow_execution_mode": mode,
            "selected_object_ids": [101],
            "mapping_operation": "build",
            "mapping_coverage_mode": "selected_targets",
            "mapping_source_system_id": 77,
            "prompt_overrides": {},
            **template_fields,
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
    assert transaction.create_parameters is not None
    assert transaction.create_parameters[22:24] == (
        template_fields.get("mapping_object_output_template_id"),
        template_fields.get("mapping_attribute_output_template_id"),
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("target", ("Object", "Attribute"))
async def test_missing_mapping_default_returns_a_clear_controlled_error(
    target: str,
) -> None:
    class MissingDefaultTransaction(MappingWorkflowCommandTransaction):
        async def fetch_one(
            self, query: LiteralString, parameters: tuple[Any, ...] = ()
        ) -> dict[str, Any] | None:
            if "application.create_workflow_run" in query:
                raise RuntimeError(
                    f"Global default Mapping {target} output template is unavailable"
                )
            return await super().fetch_one(query, parameters)

    service = DatabaseWorkflowCommandService(
        database=MappingWorkflowCommandDatabase(MissingDefaultTransaction()),
        authorizer=AuthorizationService(),
        agent_capability_registry=load_default_agent_capabilities(),
    )
    with pytest.raises(InvalidRequestError) as caught:
        await service.create_run(
            RequestPrincipal(
                actor_kind=ActorKind.HUMAN,
                entra_tenant_id=UUID("11111111-1111-1111-1111-111111111111"),
                entra_object_id=UUID("22222222-2222-2222-2222-222222222222"),
            ),
            tenant_id=7,
            model_id=18,
            correlation_id=UUID("bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb"),
            command=CreateWorkflowRunRequest(
                expected_model_revision=4,
                model_workflow="mapping",
                workflow_execution_mode="one_shot",
                selected_object_ids=[101],
                mapping_operation="build",
                mapping_coverage_mode="selected_targets",
                mapping_source_system_id=77,
            ),
        )
    assert caught.value.message == "The global Mapping output templates are unavailable."
