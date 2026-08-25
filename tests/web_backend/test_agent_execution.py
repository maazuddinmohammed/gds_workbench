from dataclasses import dataclass, field

import pytest
from gds_etl_workbench.domain.errors import WorkbenchError

from gds_workbench_api.capabilities import (
    AgentRunSelection,
    load_default_agent_capabilities,
)
from gds_workbench_api.features.workflows.authoring.agent_execution import (
    AgentExecutionRequest,
    AgentExecutionResult,
    AgentExecutionRouter,
)


def _selection(*, sdk_code: str = "langchain_create_agent") -> AgentRunSelection:
    return AgentRunSelection(
        sdk_code=sdk_code,
        provider_code="microsoft_foundry",
        model_code="gpt-5.6",
        reasoning_effort_code="medium",
        max_turns=7,
        validation_retry_count=2,
    )


def _request(*, sdk_code: str = "langchain_create_agent") -> AgentExecutionRequest:
    return AgentExecutionRequest(
        workflow_run_id=1048,
        workflow="conceptual",
        stage="object_contribution",
        execution_mode="detailed_coverage",
        selection=_selection(sdk_code=sdk_code),
        system_prompt="sensitive-system-prompt",
        instruction_prompt="sensitive-instruction-prompt",
        tool_instruction="sensitive-tool-instruction",
        context={"private": "bounded-metadata-context"},
        output_schema={"type": "object"},
        allowed_tool_names=(),
    )


@dataclass
class _Adapter:
    sdk_code: str = "langchain_create_agent"
    requests: list[AgentExecutionRequest] = field(
        default_factory=lambda: list[AgentExecutionRequest]()
    )

    async def execute(self, request: AgentExecutionRequest) -> AgentExecutionResult:
        self.requests.append(request)
        return AgentExecutionResult(
            candidate={"objects": []},
            turn_count=3,
            tool_call_count=1,
        )


@pytest.mark.asyncio
async def test_router_validates_and_dispatches_exact_sdk_without_exposing_content() -> (
    None
):
    adapter = _Adapter()
    router = AgentExecutionRouter(
        capabilities=load_default_agent_capabilities(),
        adapters=(adapter,),
    )

    request = _request()
    result = await router.execute(request)

    assert adapter.requests == [request]
    assert result.candidate == {"objects": []}
    assert result.turn_count == 3
    rendered = repr(request) + repr(result)
    assert "sensitive-system-prompt" not in rendered
    assert "sensitive-instruction-prompt" not in rendered
    assert "sensitive-tool-instruction" not in rendered
    assert "bounded-metadata-context" not in rendered
    assert "objects" not in repr(result)


def test_router_rejects_duplicate_or_unregistered_adapters() -> None:
    capabilities = load_default_agent_capabilities()

    with pytest.raises(ValueError, match="unique"):
        AgentExecutionRouter(
            capabilities=capabilities,
            adapters=(_Adapter(), _Adapter()),
        )

    with pytest.raises(ValueError, match="registered"):
        AgentExecutionRouter(
            capabilities=capabilities,
            adapters=(_Adapter(sdk_code="unknown_sdk"),),
        )


@pytest.mark.asyncio
async def test_router_rejects_incompatible_selection_before_adapter_call() -> None:
    adapter = _Adapter()
    router = AgentExecutionRouter(
        capabilities=load_default_agent_capabilities(),
        adapters=(adapter,),
    )
    request = _request().with_selection(
        AgentRunSelection(
            sdk_code="langchain_create_agent",
            provider_code="openai",
            model_code="gpt-5.6",
            reasoning_effort_code="medium",
            max_turns=7,
            validation_retry_count=2,
        )
    )

    with pytest.raises(WorkbenchError) as caught:
        await router.execute(request)

    assert caught.value.code == "invalid_request"
    assert adapter.requests == []


@dataclass
class _FailingAdapter:
    sdk_code: str = "langchain_create_agent"

    async def execute(self, request: AgentExecutionRequest) -> AgentExecutionResult:
        del request
        raise RuntimeError("provider leaked a sensitive diagnostic")


@pytest.mark.asyncio
async def test_router_converts_unexpected_adapter_failure_to_stable_safe_error() -> (
    None
):
    router = AgentExecutionRouter(
        capabilities=load_default_agent_capabilities(),
        adapters=(_FailingAdapter(),),
    )

    with pytest.raises(WorkbenchError) as caught:
        await router.execute(_request())

    assert caught.value.code == "agent_execution_failed"
    assert "sensitive" not in caught.value.message
