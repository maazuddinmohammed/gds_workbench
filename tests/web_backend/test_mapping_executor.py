from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace
from typing import cast
from unittest.mock import AsyncMock, patch
from uuid import UUID

import pytest
from gds_etl_workbench.application.change_sets.model import StageModelChange
from gds_etl_workbench.domain.authorization import ActorKind, RequestPrincipal
from gds_workbench_api.features.mapping.preparation_contracts import (
    MappingPreparation,
    MappingRunContext,
)
from gds_workbench_api.features.mapping.service import (
    DatabaseMappingExecutor,
    MappingChangeSetHandoff,
    MappingLifecycle,
    MappingNoOpCompleter,
    MappingPreparationService,
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
from gds_workbench_api.features.workflows.authoring.no_op import AuthoringNoOpReceipt
from gds_workbench_api.features.workflows.authoring.plan import WorkflowExecutionMode
from gds_workbench_api.features.workflows.authoring.repair import (
    AgentContextPolicy,
    AgentContextTooLargeError,
)
from gds_workbench_api.integrations.agents.composition import LocalFakeAgentAdapter
from gds_workbench_api.prompt_rendering import (
    PromptComponentTemplates,
    PromptVariableDefinition,
)
from mapping_fixtures import mapping_preparation
from pydantic import JsonValue


class _RecordingFake:
    def __init__(self) -> None:
        self.requests: list[AgentExecutionRequest] = []
        self.fake = LocalFakeAgentAdapter(sdk_code="openai_agents_sdk")

    async def execute(self, request: AgentExecutionRequest) -> AgentExecutionResult:
        self.requests.append(request)
        return await self.fake.execute(request)


def _executor(
    preparation: MappingPreparation,
    agent: _RecordingFake,
    policy: AgentContextPolicy | None = None,
) -> tuple[DatabaseMappingExecutor, AsyncMock, AsyncMock, AsyncMock]:
    async def finalize(
        _: RequestPrincipal,
        *,
        changes: tuple[StageModelChange, ...],
        **__: object,
    ) -> WorkflowChangeSetFinalizationResult:
        return WorkflowChangeSetFinalizationResult(
            handoff=WorkflowChangeSetHandoffResult(
                model_id=18,
                workflow_run_id=1048,
                model_change_set_id=UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"),
                replayed=False,
                draft_revision=1,
                candidate_digest="c" * 64,
                staged_record_count=sum(len(change.records) for change in changes),
                validated_at=datetime.now(UTC),
            ),
            completion=AgentWorkflowTerminalResult(
                changed=True,
                workflow_run_id=1048,
                workflow_run_state="completed",
                completed_at=datetime.now(UTC),
            ),
        )

    handoff = AsyncMock(side_effect=finalize)
    no_op = AsyncMock(
        return_value=AuthoringNoOpReceipt(
            model_id=18,
            model_revision=7,
            workflow_run_id=1048,
            workflow_run_state="completed",
            model_workflow="mapping",
            workflow_execution_mode=preparation.plan.agent_plan.workflow_execution_mode,
            correlation_id=preparation.plan.correlation_id,
            candidate_digest="d" * 64,
            replayed=False,
            completed_at=datetime.now(UTC),
            final_event=AgentWorkflowEvent(
                sequence=3,
                attempt=1,
                stage="mapping.backend_validation",
                status="running",
                message="No effective change.",
                current=1,
                total=1,
                finding_count=0,
            ),
        )
    )
    fail = AsyncMock()
    service = DatabaseMappingExecutor(
        preparation_service=cast(
            MappingPreparationService,
            SimpleNamespace(
                prepare=AsyncMock(return_value=preparation),
            ),
        ),
        agent_executor=agent,
        handoff=cast(MappingChangeSetHandoff, SimpleNamespace(finalize=handoff)),
        no_op=cast(MappingNoOpCompleter, SimpleNamespace(complete=no_op)),
        lifecycle=cast(MappingLifecycle, SimpleNamespace(append_event=AsyncMock(), fail=fail)),
        context_policy=policy,
    )
    return service, handoff, no_op, fail


async def _execute(
    service: DatabaseMappingExecutor,
) -> WorkflowChangeSetHandoffResult | AuthoringNoOpReceipt:
    return await service.execute_started(
        RequestPrincipal(
            actor_kind=ActorKind.HUMAN,
            entra_tenant_id=UUID("11111111-1111-1111-1111-111111111111"),
            entra_object_id=UUID("22222222-2222-2222-2222-222222222222"),
        ),
        tenant_id=7,
        model_id=18,
        workflow_run_id=1048,
        workflow_run_claim_token=UUID("44444444-4444-4444-4444-444444444444"),
        expected_model_revision=7,
    )


@pytest.mark.parametrize("mode", ("one_shot", "tool_assisted"))
async def test_mapping_local_fake_completes_each_mode(
    mode: WorkflowExecutionMode,
) -> None:
    agent = _RecordingFake()
    service, handoff, no_op, fail = _executor(mapping_preparation(execution_mode=mode), agent)

    from gds_etl_workbench.application.change_sets.model_validation import (
        validate_future_graph,
    )

    with patch(
        "gds_workbench_api.features.mapping.service.validate_future_graph",
        wraps=validate_future_graph,
    ) as validate:
        result = await _execute(service)
    validate.assert_called_once()
    assert validate.call_args.kwargs["snapshot"].model_id == 18
    assert set(validate.call_args.kwargs["staged_documents"]) == {
        "mapping_object",
        "mapping_attribute",
    }

    assert isinstance(result, WorkflowChangeSetHandoffResult)
    assert result.staged_record_count == 2
    handoff.assert_awaited_once()
    no_op.assert_not_awaited()
    fail.assert_not_awaited()
    assert [request.stage for request in agent.requests] == ["mapping_authoring"]


@pytest.mark.parametrize("oversized", (False, True))
async def test_mapping_description_limits_follow_the_bounded_request(
    oversized: bool,
) -> None:
    preparation = mapping_preparation(execution_mode="one_shot")
    raw = preparation.context.model_dump(mode="json")
    long_description = "Synthetic descriptive metadata. " * 100
    raw["source_system"]["system_description"] = long_description
    raw["target"]["object_description"] = long_description
    raw["target"]["attributes"][0]["attribute_description"] = long_description
    raw["sources"][0]["object"]["object_description"] = long_description
    raw["sources"][0]["object"]["attributes"][0]["attribute_description"] = (
        "x" * 600_000 if oversized else long_description
    )
    entity = raw["headers"][0]["modeled_entity"]
    entity["entity_definition"] = long_description
    entity["grain"] = long_description
    entity["attributes"][0]["attribute_definition"] = long_description
    context = MappingRunContext.model_validate(raw, strict=False)
    assert context.model_dump(mode="json") == raw
    plan = preparation.plan.agent_plan
    stage = plan.stages[0].model_copy(
        update={
            "templates": PromptComponentTemplates(
                system="Mapping system.", instruction="{{ source_evidence }}"
            ),
            "variables": (
                PromptVariableDefinition(
                    name="source_evidence",
                    resolver_key="workflow.mapping.common.mapping_authoring.inputs.source_evidence",
                    data_type="json",
                    is_required=True,
                ),
            ),
        }
    )
    preparation = preparation.model_copy(
        update={
            "context": context,
            "plan": preparation.plan.model_copy(
                update={"agent_plan": plan.model_copy(update={"stages": (stage,)})}
            ),
        }
    )
    agent = _RecordingFake()
    service, handoff, _, fail = _executor(preparation, agent)

    if oversized:
        with pytest.raises(AgentContextTooLargeError):
            await _execute(service)
        assert agent.requests == []
        handoff.assert_not_awaited()
        fail.assert_awaited_once()
    else:
        await _execute(service)
        original = cast(
            dict[str, JsonValue],
            cast(dict[str, JsonValue], agent.requests[0].context)["original_context"],
        )
        values = cast(dict[str, JsonValue], original["values"])
        source = cast(list[dict[str, JsonValue]], values["source_evidence"])[0]
        source_object = cast(dict[str, JsonValue], source["object"])
        attribute = cast(list[dict[str, JsonValue]], source_object["attributes"])[0]
        assert attribute["attribute_description"] == long_description
        handoff.assert_awaited_once()
        fail.assert_not_awaited()


async def test_mapping_requires_private_validation_context_before_provider() -> None:
    preparation = mapping_preparation()
    assert "snapshot" not in preparation.model_dump()
    assert "physical_scope" not in preparation.model_dump()
    agent = _RecordingFake()
    service, handoff, _, fail = _executor(preparation.model_copy(update={"snapshot": None}), agent)
    from gds_etl_workbench.domain.errors import InvalidRequestError

    with pytest.raises(InvalidRequestError):
        await _execute(service)
    assert not agent.requests
    handoff.assert_not_awaited()
    fail.assert_awaited_once()


@pytest.mark.parametrize("selected_tools", [(), ("get_existing_mapping",)])
async def test_mapping_saved_reader_selection_is_enforced(selected_tools: tuple[str, ...]) -> None:
    preparation = mapping_preparation(execution_mode="tool_assisted")
    plan = preparation.plan.agent_plan
    plan = plan.model_copy(
        update={
            "stages": (
                plan.stages[0].model_copy(
                    update={
                        "agent_tool_names": selected_tools,
                    }
                ),
            )
        }
    )
    preparation = preparation.model_copy(
        update={"plan": preparation.plan.model_copy(update={"agent_plan": plan})}
    )
    agent = _RecordingFake()
    service, handoff, _, fail = _executor(preparation, agent)
    await _execute(service)
    assert agent.requests[0].allowed_tool_names == selected_tools
    assert agent.requests[0].local_tool_catalog is not None
    from gds_etl_workbench.domain.errors import InvalidRequestError

    with pytest.raises(InvalidRequestError):
        agent.requests[0].local_tool_catalog.invoke("get_mapping_sources", {})
    handoff.assert_awaited_once()
    fail.assert_not_awaited()
