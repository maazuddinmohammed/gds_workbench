from types import SimpleNamespace
from typing import Any, cast

import pytest
from gds_etl_workbench.domain.errors import WorkbenchError
from pydantic import SecretStr

from gds_workbench_api.capabilities import AgentRunSelection
from gds_workbench_api.features.workflows.authoring.agent_execution import AgentExecutionRequest
from gds_workbench_api.integrations.agents import adapters as agent_adapters
from gds_workbench_api.integrations.agents.adapters import (
    LangChainCreateAgentAdapter,
    OpenAIAgentsSdkAdapter,
)
from gds_workbench_api.integrations.agents.configuration import (
    AgentProviderConnection,
)


def _request(
    *,
    sdk_code: str,
    provider_code: str,
    model_code: str,
) -> AgentExecutionRequest:
    return AgentExecutionRequest(
        workflow_run_id=1048,
        workflow="logical",
        stage="entity_consolidation",
        execution_mode="one_shot",
        selection=AgentRunSelection(
            sdk_code=sdk_code,
            provider_code=provider_code,
            model_code=model_code,
            reasoning_effort_code="high",
            max_turns=6,
            validation_retry_count=2,
        ),
        system_prompt="sensitive system",
        instruction_prompt="sensitive instruction",
        tool_instruction=None,
        context={"scope": [1, 2]},
        output_schema={"type": "object"},
    )


@pytest.mark.asyncio
async def test_langchain_adapter_uses_structured_output_and_bounded_turns(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, Any] = {}

    class FakeGraph:
        async def ainvoke(
            self,
            values: dict[str, Any],
            config: dict[str, Any],
        ) -> dict[str, Any]:
            captured["values"] = values
            captured["config"] = config
            return {
                "structured_response": {"entities": []},
                "messages": [
                    SimpleNamespace(type="ai", tool_calls=[]),
                    SimpleNamespace(type="ai", tool_calls=[{"name": "local"}]),
                ],
            }

    def fake_model(**kwargs: Any) -> str:
        captured["model"] = kwargs
        return "model"

    def fake_create_agent(**kwargs: Any) -> FakeGraph:
        captured["agent"] = kwargs
        return FakeGraph()

    monkeypatch.setattr(agent_adapters, "ChatOpenAI", fake_model)
    monkeypatch.setattr(agent_adapters, "create_agent", fake_create_agent)
    adapter = LangChainCreateAgentAdapter(
        connections=(
            AgentProviderConnection(
                provider_code="microsoft_foundry",
                api_key=SecretStr("hidden-key"),
                base_url="https://foundry.invalid/openai/v1/",
                timeout_seconds=90,
            ),
        ),
    )

    result = await adapter.execute(
        _request(
            sdk_code="langchain_create_agent",
            provider_code="microsoft_foundry",
            model_code="gpt-5.6",
        )
    )

    assert result.candidate == {"entities": []}
    assert result.turn_count == 2
    assert result.tool_call_count == 1
    assert captured["agent"]["response_format"] == {"type": "object"}
    assert captured["config"] == {"recursion_limit": 13}
    assert captured["model"]["store"] is False
    assert "hidden-key" not in repr(adapter)
    assert "foundry.invalid" not in repr(adapter)


@pytest.mark.asyncio
async def test_openai_agents_adapter_disables_tracing_and_parses_json(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, Any] = {}

    class FakeClient:
        def __init__(self, **kwargs: Any) -> None:
            captured["client"] = kwargs

        async def close(self) -> None:
            captured["closed"] = True

    class FakeModel:
        def __init__(self, **kwargs: Any) -> None:
            captured["model"] = kwargs

    class FakeAgent:
        def __init__(self, **kwargs: Any) -> None:
            captured["agent"] = kwargs

    class FakeToolCall:
        pass

    class FakeRunner:
        @staticmethod
        async def run(*args: Any, **kwargs: Any) -> SimpleNamespace:
            captured["run"] = (args, kwargs)
            return SimpleNamespace(
                final_output='{"relationships":[]}',
                raw_responses=[object(), object(), object()],
                new_items=[FakeToolCall(), object()],
            )

    monkeypatch.setattr(agent_adapters, "AsyncOpenAI", FakeClient)
    monkeypatch.setattr(agent_adapters, "OpenAIResponsesModel", FakeModel)
    monkeypatch.setattr(agent_adapters, "Agent", FakeAgent)
    monkeypatch.setattr(agent_adapters, "Runner", FakeRunner)
    monkeypatch.setattr(agent_adapters, "ToolCallItem", FakeToolCall)
    adapter = OpenAIAgentsSdkAdapter(
        connections=(
            AgentProviderConnection(
                provider_code="openai",
                api_key=SecretStr("hidden-openai-key"),
                base_url="https://api.openai.example/v1/",
                timeout_seconds=80,
            ),
        ),
    )

    result = await adapter.execute(
        _request(
            sdk_code="openai_agents_sdk",
            provider_code="openai",
            model_code="gpt-5.6-sol",
        )
    )

    assert result.candidate == {"relationships": []}
    assert result.turn_count == 3
    assert result.tool_call_count == 1
    _, run_kwargs = cast(tuple[tuple[Any, ...], dict[str, Any]], captured["run"])
    assert run_kwargs["max_turns"] == 6
    assert run_kwargs["run_config"].tracing_disabled is True
    assert run_kwargs["run_config"].trace_include_sensitive_data is False
    assert captured["closed"] is True


@pytest.mark.asyncio
async def test_adapter_rejects_provider_without_configured_connection() -> None:
    adapter = LangChainCreateAgentAdapter(connections=())

    with pytest.raises(WorkbenchError) as caught:
        await adapter.execute(
            _request(
                sdk_code="langchain_create_agent",
                provider_code="microsoft_foundry",
                model_code="gpt-5.6",
            )
        )

    assert caught.value.code == "invalid_request"
