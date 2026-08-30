from __future__ import annotations

import json
from collections.abc import Generator, Mapping
from contextlib import contextmanager
from types import SimpleNamespace
from typing import Any, cast

import pytest
from gds_etl_workbench.domain.errors import WorkbenchError
from pydantic import JsonValue, SecretStr, ValidationError

from gds_workbench_api.capabilities import AgentRunSelection
from gds_workbench_api.features.workflows.authoring.agent_execution import (
    AgentExecutionRequest,
    LocalAgentToolDefinition,
)
from gds_workbench_api.integrations.agents import adapters as agent_adapters
from gds_workbench_api.integrations.agents.adapters import (
    LangChainCreateAgentAdapter,
    OpenAIProviderCredentials,
    OpenAIAgentsSdkAdapter,
)
from gds_workbench_api.integrations.agents.configuration import AgentProviderConnection


class _Catalog:
    definitions = (
        LocalAgentToolDefinition(
            name="get_agent_context_manifest",
            description="Return the immutable context manifest.",
            input_schema={
                "type": "object",
                "properties": {},
                "additionalProperties": False,
            },
        ),
        LocalAgentToolDefinition(
            name="get_agent_context_dataset",
            description="Return one bounded page from an immutable context dataset.",
            input_schema={
                "type": "object",
                "properties": {
                    "dataset": {"type": "string"},
                    "offset": {"type": "integer", "minimum": 0},
                    "limit": {"type": "integer", "minimum": 1, "maximum": 200},
                },
                "required": ["dataset", "offset", "limit"],
                "additionalProperties": False,
            },
        ),
    )

    def __init__(self, *, max_cumulative_result_bytes: int = 4096) -> None:
        self.max_cumulative_result_bytes = max_cumulative_result_bytes
        self.calls: list[tuple[str, Mapping[str, JsonValue]]] = []

    def invoke(
        self,
        tool_name: str,
        arguments: Mapping[str, JsonValue],
    ) -> JsonValue:
        self.calls.append((tool_name, arguments))
        if tool_name == "get_agent_context_manifest":
            return {"datasets": [{"name": "selected_objects", "count": 1}]}
        return {
            "dataset": arguments["dataset"],
            "offset": arguments["offset"],
            "items": [{"object_name": "customer_raw"}],
            "next_offset": None,
        }


class _ModelAuthentication:
    async def authenticate(self) -> OpenAIProviderCredentials:
        return OpenAIProviderCredentials(
            api_key=SecretStr("short-lived-databricks-token"),
            base_url="https://fixture.azuredatabricks.net/serving-endpoints",
        )


def _selection(*, sdk_code: str) -> AgentRunSelection:
    return AgentRunSelection(
        sdk_code=sdk_code,
        provider_code="databricks",
        model_code="databricks-primary",
        reasoning_effort_code="medium",
        max_turns=6,
        validation_retry_count=2,
    )


def _request(
    *, sdk_code: str, catalog: _Catalog | None = None
) -> AgentExecutionRequest:
    catalog = catalog or _Catalog()
    return AgentExecutionRequest(
        workflow_run_id=1048,
        workflow="conceptual",
        stage="candidate_authoring",
        execution_mode="tool_assisted",
        selection=_selection(sdk_code=sdk_code),
        system_prompt="private system prompt",
        instruction_prompt="private instruction prompt",
        tool_instruction="Use only the supplied local tools.",
        context={"datasets": [{"name": "selected_objects", "count": 1}]},
        output_schema={"type": "object"},
        allowed_tool_names=tuple(item.name for item in catalog.definitions),
        local_tool_catalog=catalog,
    )


def test_tool_catalog_is_ephemeral_and_names_must_match_exactly() -> None:
    catalog = _Catalog()
    request = _request(sdk_code="langchain_create_agent", catalog=catalog)

    assert request.local_tool_catalog is catalog
    assert "local_tool_catalog" not in request.model_dump()
    rendered = repr(request)
    assert "customer_raw" not in rendered
    assert "private system prompt" not in rendered
    schema = AgentExecutionRequest.model_json_schema(mode="validation")
    assert "local_tool_catalog" not in schema["properties"]

    with pytest.raises(ValidationError):
        _request(sdk_code="langchain_create_agent", catalog=catalog).model_copy(
            update={"allowed_tool_names": ("get_agent_context_manifest",)},
        ).model_validate(
            {
                **request.model_dump(),
                "allowed_tool_names": ("get_agent_context_manifest",),
                "local_tool_catalog": catalog,
            },
            strict=True,
        )
    with pytest.raises(ValidationError):
        AgentExecutionRequest.model_validate(
            {
                **request.model_dump(),
                "execution_mode": "one_shot",
                "allowed_tool_names": request.allowed_tool_names,
                "local_tool_catalog": catalog,
            },
            strict=True,
        )
    with pytest.raises(ValidationError):
        AgentExecutionRequest.model_validate(
            {
                **request.model_dump(),
                "execution_mode": "detailed_coverage",
                "allowed_tool_names": request.allowed_tool_names,
                "local_tool_catalog": catalog,
            },
            strict=True,
        )


def test_each_provider_conversation_has_a_fresh_cumulative_tool_budget() -> None:
    probe = _Catalog()
    manifest = probe.invoke("get_agent_context_manifest", {})
    manifest_bytes = len(
        json.dumps(
            manifest,
            ensure_ascii=False,
            allow_nan=False,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("utf-8")
    )
    catalog = _Catalog(max_cumulative_result_bytes=manifest_bytes)
    wrapper = getattr(agent_adapters, "_PerExecutionToolCatalog")

    first_conversation = wrapper(catalog)
    assert first_conversation.invoke("get_agent_context_manifest", {}) == manifest
    with pytest.raises(WorkbenchError) as captured:
        first_conversation.invoke("get_agent_context_manifest", {})

    second_conversation = wrapper(catalog)
    assert second_conversation.invoke("get_agent_context_manifest", {}) == manifest
    assert captured.value.code == "agent_context_tool_result_too_large"


@pytest.mark.asyncio
async def test_langchain_adapter_wraps_only_the_attached_local_catalog(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, Any] = {}
    catalog = _Catalog()

    @contextmanager
    def fake_tracing_context(**kwargs: object) -> Generator[None]:
        captured["tracing"] = kwargs
        yield

    def fake_model(**_: object) -> str:
        return "model"

    class FakeGraph:
        async def ainvoke(
            self,
            values: dict[str, Any],
            config: dict[str, Any],
        ) -> dict[str, Any]:
            del values, config
            tools = cast(list[Any], captured["tools"])
            manifest = await tools[0].ainvoke({})
            dataset = await tools[1].ainvoke(
                {"dataset": "selected_objects", "offset": 0, "limit": 1}
            )
            captured["tool_results"] = (manifest, dataset)
            return {
                "messages": [
                    SimpleNamespace(
                        type="ai",
                        tool_calls=[{"name": "local"}],
                        content='{"objects":[],"relationships":[]}',
                    )
                ],
            }

    monkeypatch.setattr(agent_adapters, "ChatOpenAI", fake_model)
    monkeypatch.setattr(agent_adapters, "tracing_context", fake_tracing_context)

    def fake_create_agent(**kwargs: Any) -> FakeGraph:
        captured["tools"] = kwargs["tools"]
        return FakeGraph()

    monkeypatch.setattr(agent_adapters, "create_agent", fake_create_agent)
    adapter = LangChainCreateAgentAdapter(
        connections=(
            AgentProviderConnection(
                provider_code="databricks",
                model_code="databricks-primary",
                model_endpoint="production-agent-endpoint",
                timeout_seconds=90,
            ),
        ),
        model_authentications={"databricks": _ModelAuthentication()},
    )

    result = await adapter.execute(
        _request(sdk_code="langchain_create_agent", catalog=catalog)
    )

    tools = cast(list[Any], captured["tools"])
    assert [tool.name for tool in tools] == list(
        _request(sdk_code="langchain_create_agent").allowed_tool_names
    )
    assert captured["tool_results"] == (
        {"datasets": [{"name": "selected_objects", "count": 1}]},
        {
            "dataset": "selected_objects",
            "offset": 0,
            "items": [{"object_name": "customer_raw"}],
            "next_offset": None,
        },
    )
    assert result.candidate == {"objects": [], "relationships": []}
    assert captured["tracing"] == {"enabled": False}
    assert [name for name, _ in catalog.calls] == list(
        _request(sdk_code="langchain_create_agent").allowed_tool_names
    )


@pytest.mark.asyncio
async def test_openai_agents_adapter_wraps_only_the_attached_local_catalog(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, Any] = {}
    catalog = _Catalog()

    class FakeClient:
        def __init__(self, **_: Any) -> None: ...

        async def close(self) -> None: ...

    class FakeAgent:
        def __init__(self, **kwargs: Any) -> None:
            captured["tools"] = kwargs["tools"]

    class FakeRunner:
        @staticmethod
        async def run(*_: Any, **__: Any) -> SimpleNamespace:
            tools = cast(list[Any], captured["tools"])
            manifest = await tools[0].on_invoke_tool(None, "{}")
            dataset = await tools[1].on_invoke_tool(
                None,
                json.dumps({"dataset": "selected_objects", "offset": 0, "limit": 1}),
            )
            captured["tool_results"] = (json.loads(manifest), json.loads(dataset))
            return SimpleNamespace(
                final_output='{"objects":[],"relationships":[]}',
                raw_responses=[object()],
                new_items=[],
            )

    def fake_model(**_: object) -> str:
        return "model"

    monkeypatch.setattr(agent_adapters, "AsyncOpenAI", FakeClient)
    monkeypatch.setattr(agent_adapters, "OpenAIChatCompletionsModel", fake_model)
    monkeypatch.setattr(agent_adapters, "Agent", FakeAgent)
    monkeypatch.setattr(agent_adapters, "Runner", FakeRunner)
    adapter = OpenAIAgentsSdkAdapter(
        connections=(
            AgentProviderConnection(
                provider_code="databricks",
                model_code="databricks-primary",
                model_endpoint="production-agent-endpoint",
                timeout_seconds=90,
            ),
        ),
        model_authentications={"databricks": _ModelAuthentication()},
    )

    result = await adapter.execute(
        _request(sdk_code="openai_agents_sdk", catalog=catalog)
    )

    tools = cast(list[Any], captured["tools"])
    assert [tool.name for tool in tools] == list(
        _request(sdk_code="openai_agents_sdk").allowed_tool_names
    )
    assert captured["tool_results"][0]["datasets"][0]["count"] == 1
    assert captured["tool_results"][1]["items"][0]["object_name"] == "customer_raw"
    assert result.tool_call_count == 0


@pytest.mark.asyncio
async def test_tool_wrapper_construction_failure_is_redacted(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fail(_: object) -> tuple[object, ...]:
        raise RuntimeError("sensitive schema diagnostic")

    monkeypatch.setattr(agent_adapters, "_langchain_tools", fail)
    adapter = LangChainCreateAgentAdapter(
        connections=(
            AgentProviderConnection(
                provider_code="databricks",
                model_code="databricks-primary",
                model_endpoint="production-agent-endpoint",
                timeout_seconds=90,
            ),
        ),
        model_authentications={"databricks": _ModelAuthentication()},
    )

    with pytest.raises(WorkbenchError) as captured:
        await adapter.execute(_request(sdk_code="langchain_create_agent"))

    error = captured.value
    assert getattr(error, "code", None) == "agent_execution_failed"
    assert "sensitive" not in str(error)
