from __future__ import annotations

from collections.abc import Sequence
from datetime import UTC, datetime
from typing import cast
from uuid import UUID

import pytest
from gds_etl_workbench.domain.authorization import ActorKind, RequestPrincipal
from gds_etl_workbench.domain.errors import InvalidRequestError
from gds_etl_workbench.tools.change_sets.model import StageModelChange
from pydantic import JsonValue
from test_mapping_attribute_candidate import (
    _candidate as _attribute_candidate,  # pyright: ignore[reportPrivateUsage]
)
from test_mapping_attribute_candidate import (
    _preparation as _base_preparation,  # pyright: ignore[reportPrivateUsage]
)
from test_mapping_header_candidate import (
    _candidate as _header_candidate,  # pyright: ignore[reportPrivateUsage]
)

from gds_workbench_api.capabilities import AgentRunSelection
from gds_workbench_api.features.mapping.attribute_candidate import (
    build_mapping_attribute_batch_plans,
)
from gds_workbench_api.features.mapping.candidate import (
    MappingHeaderCandidateValidator,
)
from gds_workbench_api.features.mapping.execution_context import (
    InMemoryMappingContextToolCatalog,
)
from gds_workbench_api.features.mapping import MappingPreparation
from gds_workbench_api.features.mapping.service import (
    DatabaseMappingExecutor,
    MappingExecutionFailedError,
)
from gds_workbench_api.features.workflows.authoring.agent_execution import (
    AgentExecutionRequest,
    AgentExecutionResult,
)
from gds_workbench_api.features.workflows.authoring.change_set_handoff import (
    WorkflowChangeSetFinalizationResult,
    WorkflowChangeSetHandoffResult,
)
from gds_workbench_api.features.workflows.authoring.lifecycle import (
    AgentWorkflowEvent,
    AgentWorkflowTerminalResult,
)
from gds_workbench_api.features.workflows.authoring.no_op import (
    AuthoringNoOpReceipt,
    AuthoringNoOpRequest,
)
from gds_workbench_api.features.workflows.authoring.plan import (
    AgentRunPlan,
    FrozenAgentStage,
    ModelWorkflow,
    WorkflowExecutionMode,
)
from gds_workbench_api.prompt_rendering import PromptComponentTemplates

_CLAIM_TOKEN = UUID("55555555-5555-5555-5555-555555555555")


def _principal() -> RequestPrincipal:
    return RequestPrincipal(
        actor_kind=ActorKind.HUMAN,
        entra_tenant_id=UUID("11111111-1111-1111-1111-111111111111"),
        entra_object_id=UUID("22222222-2222-2222-2222-222222222222"),
    )


def _agent_plan(mode: WorkflowExecutionMode) -> AgentRunPlan:
    stage_codes = (
        ("header_mapper", "attribute_mapper", "target_validator")
        if mode == "detailed_coverage"
        else ("mapping_authoring",)
    )
    stages = tuple(
        FrozenAgentStage(
            workflow_stage_id=100 + index,
            stage_code=stage_code,
            stage_order=index * 10,
            prompt_template_version_id=200 + index,
            prompt_template_digest=f"{index:x}" * 64,
            templates=PromptComponentTemplates(
                system="Author one governed Mapping candidate.",
                instruction="Return only the validated Mapping output.",
            ),
            variables=(),
        )
        for index, stage_code in enumerate(stage_codes, 1)
    )
    return AgentRunPlan(
        workflow_run_id=1048,
        model_id=18,
        correlation_id=UUID("33333333-3333-3333-3333-333333333333"),
        model_revision=7,
        model_workflow="mapping",
        workflow_execution_mode=mode,
        modeled_entity_type="logical_entity",
        selected_scope_digest="a" * 64,
        selected_object_ids=(501,),
        selection=AgentRunSelection(
            sdk_code="langchain_create_agent",
            provider_code="databricks",
            model_code="databricks-primary",
            reasoning_effort_code="medium",
            max_turns=8,
            validation_retry_count=1,
        ),
        stages=stages,
    )


def _preparation(
    mode: WorkflowExecutionMode = "one_shot",
    *,
    preservation_only: bool = False,
) -> MappingPreparation:
    preparation = _base_preparation()
    plan = preparation.plan.model_copy(update={"agent_plan": _agent_plan(mode)})
    readiness = preparation.readiness
    if preservation_only:
        readiness = readiness.model_copy(
            update={
                "package_action": "preserve",
                "headers": tuple(
                    item.model_copy(
                        update={
                            "action": "preserve",
                            "attribute_actions": tuple(
                                child.model_copy(update={"action": "preserve"})
                                for child in item.attribute_actions
                            ),
                        }
                    )
                    for item in readiness.headers
                ),
            }
        )
    return preparation.model_copy(update={"plan": plan, "readiness": readiness})


def _complete_candidate(preparation: MappingPreparation) -> JsonValue:
    raw_header = cast(JsonValue, _header_candidate())
    header = MappingHeaderCandidateValidator(preparation=preparation).parse_validated(
        raw_header
    )
    plans = build_mapping_attribute_batch_plans(
        preparation=preparation,
        package=header.package,
    )
    batches = [
        cast(JsonValue, _attribute_candidate(preparation, header.package))
        for _plan in plans
    ]
    return cast(
        JsonValue,
        {
            "schema_version": "1.0",
            "header": raw_header,
            "attribute_batches": batches,
        },
    )


class _PreparationService:
    def __init__(self, preparation: MappingPreparation) -> None:
        self.preparation = preparation
        self.calls: list[tuple[int, int, int, int]] = []

    async def prepare(
        self,
        principal: RequestPrincipal,
        *,
        tenant_id: int,
        model_id: int,
        workflow_run_id: int,
        expected_model_revision: int,
    ) -> MappingPreparation:
        del principal
        self.calls.append(
            (tenant_id, model_id, workflow_run_id, expected_model_revision)
        )
        return self.preparation


class _Agent:
    def __init__(self, responses: Sequence[JsonValue | Exception]) -> None:
        self.responses = list(responses)
        self.requests: list[AgentExecutionRequest] = []

    async def execute(self, request: AgentExecutionRequest) -> AgentExecutionResult:
        self.requests.append(request)
        response = self.responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return AgentExecutionResult(
            candidate=response,
            turn_count=1,
            tool_call_count=0,
        )


class _Handoff:
    def __init__(self) -> None:
        self.calls: list[tuple[StageModelChange, ...]] = []
        self.final_events: list[AgentWorkflowEvent] = []

    async def finalize(
        self,
        principal: RequestPrincipal,
        *,
        tenant_id: int,
        model_id: int,
        workflow_run_id: int,
        workflow_run_claim_token: UUID,
        expected_workflow: ModelWorkflow,
        expected_model_revision: int,
        changes: tuple[StageModelChange, ...],
        final_event: AgentWorkflowEvent,
    ) -> WorkflowChangeSetFinalizationResult:
        del principal
        assert tenant_id == 7
        assert workflow_run_claim_token == _CLAIM_TOKEN
        assert expected_workflow == "mapping"
        self.calls.append(changes)
        self.final_events.append(final_event)
        return WorkflowChangeSetFinalizationResult(
            handoff=WorkflowChangeSetHandoffResult(
                model_id=model_id,
                workflow_run_id=workflow_run_id,
                model_change_set_id=UUID("44444444-4444-4444-4444-444444444444"),
                replayed=False,
                draft_revision=1,
                candidate_digest="d" * 64,
                staged_record_count=sum(len(change.records) for change in changes),
                validated_at=datetime(2026, 8, 24, tzinfo=UTC),
            ),
            completion=AgentWorkflowTerminalResult(
                changed=True,
                workflow_run_id=workflow_run_id,
                workflow_run_state="completed",
                completed_at=datetime(2026, 8, 24, tzinfo=UTC),
            ),
        )


class _NoOp:
    def __init__(self) -> None:
        self.requests: list[AuthoringNoOpRequest] = []

    async def complete(
        self,
        principal: RequestPrincipal,
        *,
        tenant_id: int,
        model_id: int,
        workflow_run_id: int,
        workflow_run_claim_token: UUID,
        request: AuthoringNoOpRequest,
    ) -> AuthoringNoOpReceipt:
        del principal
        assert tenant_id == 7
        assert workflow_run_claim_token == _CLAIM_TOKEN
        self.requests.append(request)
        return AuthoringNoOpReceipt(
            model_id=model_id,
            model_revision=request.expected_model_revision,
            workflow_run_id=workflow_run_id,
            workflow_run_state="completed",
            model_workflow="mapping",
            workflow_execution_mode=request.expected_execution_mode,
            correlation_id=request.expected_correlation_id,
            candidate_digest=request.candidate_digest,
            replayed=False,
            final_event=request.final_event,
            completed_at=datetime(2026, 8, 24, tzinfo=UTC),
        )


class _Lifecycle:
    def __init__(self) -> None:
        self.events: list[AgentWorkflowEvent] = []
        self.failed: tuple[str, str] | None = None

    async def append_event(
        self,
        principal: RequestPrincipal,
        *,
        workflow_run_id: int,
        workflow_run_claim_token: UUID,
        expected_model_revision: int,
        event: AgentWorkflowEvent,
    ) -> None:
        del principal
        assert workflow_run_id == 1048
        assert workflow_run_claim_token == _CLAIM_TOKEN
        assert expected_model_revision == 7
        self.events.append(event)

    async def fail(
        self,
        principal: RequestPrincipal,
        *,
        workflow_run_id: int,
        workflow_run_claim_token: UUID,
        expected_model_revision: int,
        failure_code: str,
        safe_failure_message: str,
    ) -> AgentWorkflowTerminalResult:
        del principal
        assert workflow_run_claim_token == _CLAIM_TOKEN
        self.failed = (failure_code, safe_failure_message)
        return AgentWorkflowTerminalResult(
            changed=True,
            workflow_run_id=workflow_run_id,
            workflow_run_state="failed",
            completed_at=datetime(2026, 8, 24, tzinfo=UTC),
        )


def _service(
    *,
    preparation: MappingPreparation,
    agent: _Agent,
) -> tuple[DatabaseMappingExecutor, _Handoff, _NoOp, _Lifecycle]:
    handoff = _Handoff()
    no_op = _NoOp()
    lifecycle = _Lifecycle()
    return (
        DatabaseMappingExecutor(
            preparation_service=_PreparationService(preparation),
            agent_executor=agent,
            handoff=handoff,
            no_op=no_op,
            lifecycle=lifecycle,
        ),
        handoff,
        no_op,
        lifecycle,
    )


@pytest.mark.asyncio
async def test_one_shot_mapping_hands_off_one_complete_atomic_contract() -> None:
    preparation = _preparation()
    agent = _Agent([_complete_candidate(preparation)])
    service, handoff, no_op, lifecycle = _service(
        preparation=preparation,
        agent=agent,
    )

    result = await service.execute_started(
        _principal(),
        tenant_id=7,
        model_id=18,
        workflow_run_id=1048,
        workflow_run_claim_token=_CLAIM_TOKEN,
        expected_model_revision=7,
    )

    assert isinstance(result, WorkflowChangeSetHandoffResult)
    assert [request.stage for request in agent.requests] == ["mapping_authoring"]
    assert [change.dataset for change in handoff.calls[0]] == [
        "mapping_object",
        "mapping_attribute",
    ]
    assert no_op.requests == []
    assert lifecycle.failed is None


@pytest.mark.asyncio
async def test_tool_assisted_mapping_uses_only_immutable_local_context_tools() -> None:
    preparation = _preparation("tool_assisted")
    agent = _Agent([_complete_candidate(preparation)])
    service, handoff, _no_op, lifecycle = _service(
        preparation=preparation,
        agent=agent,
    )

    await service.execute_started(
        _principal(),
        tenant_id=7,
        model_id=18,
        workflow_run_id=1048,
        workflow_run_claim_token=_CLAIM_TOKEN,
        expected_model_revision=7,
    )

    catalog = agent.requests[0].local_tool_catalog
    assert isinstance(catalog, InMemoryMappingContextToolCatalog)
    assert agent.requests[0].allowed_tool_names == catalog.allowed_tool_names
    assert len(handoff.calls) == 1
    assert lifecycle.failed is None


@pytest.mark.asyncio
async def test_detailed_mapping_runs_fixed_workers_then_same_atomic_contract() -> None:
    preparation = _preparation("detailed_coverage")
    complete = cast(dict[str, JsonValue], _complete_candidate(preparation))
    raw_header = complete["header"]
    raw_batches = cast(list[JsonValue], complete["attribute_batches"])
    agent = _Agent([raw_header, *raw_batches, complete])
    service, handoff, _no_op, lifecycle = _service(
        preparation=preparation,
        agent=agent,
    )

    await service.execute_started(
        _principal(),
        tenant_id=7,
        model_id=18,
        workflow_run_id=1048,
        workflow_run_claim_token=_CLAIM_TOKEN,
        expected_model_revision=7,
    )

    assert [request.stage for request in agent.requests] == [
        "header_mapper",
        "attribute_mapper",
        "target_validator",
    ]
    assert all(request.allowed_tool_names == () for request in agent.requests)
    assert [change.dataset for change in handoff.calls[0]] == [
        "mapping_object",
        "mapping_attribute",
    ]
    assert len(lifecycle.events) >= 3
    assert lifecycle.failed is None


@pytest.mark.asyncio
async def test_preservation_only_mapping_finishes_as_no_op_without_agent_call() -> None:
    preparation = _preparation(preservation_only=True)
    agent = _Agent([])
    service, handoff, no_op, lifecycle = _service(
        preparation=preparation,
        agent=agent,
    )

    result = await service.execute_started(
        _principal(),
        tenant_id=7,
        model_id=18,
        workflow_run_id=1048,
        workflow_run_claim_token=_CLAIM_TOKEN,
        expected_model_revision=7,
    )

    assert isinstance(result, AuthoringNoOpReceipt)
    assert agent.requests == []
    assert handoff.calls == []
    assert len(no_op.requests) == 1
    assert lifecycle.failed is None


@pytest.mark.asyncio
async def test_mapping_failure_is_safe_and_never_hands_off_partial_output() -> None:
    preparation = _preparation()
    agent = _Agent([RuntimeError("token=secret; raw provider trace")])
    service, handoff, _no_op, lifecycle = _service(
        preparation=preparation,
        agent=agent,
    )

    with pytest.raises(MappingExecutionFailedError) as raised:
        await service.execute_started(
            _principal(),
            tenant_id=7,
            model_id=18,
            workflow_run_id=1048,
            workflow_run_claim_token=_CLAIM_TOKEN,
            expected_model_revision=7,
        )

    assert handoff.calls == []
    assert lifecycle.failed is not None
    assert "secret" not in str(raised.value)


@pytest.mark.asyncio
async def test_mapping_rejects_wrong_claim_before_agent_or_handoff() -> None:
    preparation = _preparation()
    agent = _Agent([_complete_candidate(preparation)])
    service, handoff, _no_op, lifecycle = _service(
        preparation=preparation,
        agent=agent,
    )

    with pytest.raises(MappingExecutionFailedError):
        await service.execute_started(
            _principal(),
            tenant_id=7,
            model_id=18,
            workflow_run_id=1048,
            workflow_run_claim_token=UUID("66666666-6666-6666-6666-666666666666"),
            expected_model_revision=7,
        )

    assert agent.requests == []
    assert handoff.calls == []
    assert lifecycle.events == []
    assert lifecycle.failed is None


@pytest.mark.asyncio
async def test_mapping_rejects_wrong_frozen_stage_plan_before_agent_execution() -> None:
    preparation = _preparation()
    bad_agent_plan = preparation.plan.agent_plan.model_copy(
        update={"model_workflow": "logical"}
    )
    preparation = preparation.model_copy(
        update={
            "plan": preparation.plan.model_copy(update={"agent_plan": bad_agent_plan})
        }
    )
    agent = _Agent([_complete_candidate(_preparation())])
    service, handoff, _no_op, lifecycle = _service(
        preparation=preparation,
        agent=agent,
    )

    with pytest.raises(InvalidRequestError):
        await service.execute_started(
            _principal(),
            tenant_id=7,
            model_id=18,
            workflow_run_id=1048,
            workflow_run_claim_token=_CLAIM_TOKEN,
            expected_model_revision=7,
        )

    assert agent.requests == []
    assert handoff.calls == []
    assert lifecycle.failed is not None
