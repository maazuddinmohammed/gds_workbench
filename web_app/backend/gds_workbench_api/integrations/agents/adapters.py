"""Concrete, non-logging adapters for the two supported agent SDKs."""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from contextlib import AbstractContextManager
from typing import Any, Literal, Protocol, cast, runtime_checkable

import langchain.agents as langchain_agents
import langsmith.run_helpers as langsmith_run_helpers
from agents import (
    Agent,
    FunctionTool,
    ModelSettings,
    OpenAIResponsesModel,
    RunConfig,
    Runner,
    Tool,
    ToolCallItem,
)
from gds_etl_workbench.domain.errors import InvalidRequestError, WorkbenchError
from langchain_core.tools import BaseTool, StructuredTool
from langchain_openai import ChatOpenAI
from openai import AsyncOpenAI
from openai.types.shared import Reasoning
from pydantic import JsonValue, TypeAdapter

from gds_workbench_api.features.workflows.authoring.agent_execution import (
    AgentExecutionFailedError,
    AgentExecutionRequest,
    AgentExecutionResult,
    LocalAgentToolCatalog,
    LocalAgentToolDefinition,
)
from gds_workbench_api.integrations.agents.configuration import (
    AgentProviderConnection,
)

_JSON_VALUE: TypeAdapter[JsonValue] = TypeAdapter(JsonValue)
_JSON_OBJECT: TypeAdapter[dict[str, JsonValue]] = TypeAdapter(dict[str, JsonValue])


class _LangChainGraph(Protocol):
    async def ainvoke(
        self,
        values: Mapping[str, object],
        config: Mapping[str, object],
    ) -> object: ...


class _CreateAgent(Protocol):
    def __call__(
        self,
        *,
        model: object,
        tools: Sequence[BaseTool],
        system_prompt: str,
        response_format: dict[str, JsonValue],
        name: str,
    ) -> _LangChainGraph: ...


class _TracingContext(Protocol):
    def __call__(self, *, enabled: bool) -> AbstractContextManager[None]: ...


@runtime_checkable
class _AgentMessage(Protocol):
    type: str
    tool_calls: Sequence[object]


create_agent = cast(_CreateAgent, vars(langchain_agents)["create_agent"])
tracing_context = cast(_TracingContext, vars(langsmith_run_helpers)["tracing_context"])


class _ConfiguredAdapter:
    sdk_code: str

    def __init__(
        self,
        *,
        connections: tuple[AgentProviderConnection, ...],
    ) -> None:
        provider_codes = [connection.provider_code for connection in connections]
        if len(provider_codes) != len(set(provider_codes)):
            raise ValueError("Agent provider connections must be unique")
        self._connections = {connection.provider_code: connection for connection in connections}

    def __repr__(self) -> str:
        return f"{type(self).__name__}(configured_providers={len(self._connections)})"

    def _connection(self, request: AgentExecutionRequest) -> AgentProviderConnection:
        if request.selection.sdk_code != self.sdk_code:
            raise InvalidRequestError("The selected agent SDK is incompatible.")
        connection = self._connections.get(request.selection.provider_code)
        if connection is None:
            raise InvalidRequestError("The selected agent provider is unavailable.")
        return connection

    @staticmethod
    def _tool_catalog(request: AgentExecutionRequest) -> LocalAgentToolCatalog | None:
        catalog = request.local_tool_catalog
        if request.execution_mode != "tool_assisted":
            if catalog is not None or request.allowed_tool_names:
                raise InvalidRequestError("A selected local agent tool is unavailable.")
            return None
        if catalog is None:
            raise InvalidRequestError("A selected local agent tool is unavailable.")
        names = tuple(definition.name for definition in catalog.definitions)
        if not names or names != request.allowed_tool_names or len(names) != len(set(names)):
            raise InvalidRequestError("A selected local agent tool is unavailable.")
        return catalog


class LangChainCreateAgentAdapter(_ConfiguredAdapter):
    sdk_code = "langchain_create_agent"

    async def execute(self, request: AgentExecutionRequest) -> AgentExecutionResult:
        connection = self._connection(request)
        try:
            with tracing_context(enabled=False):
                tools: Sequence[BaseTool] = _langchain_tools(self._tool_catalog(request))
                model = ChatOpenAI(
                    model=request.selection.model_code,
                    api_key=connection.api_key,
                    base_url=connection.base_url,
                    timeout=connection.timeout_seconds,
                    max_retries=2,
                    reasoning_effort=request.selection.reasoning_effort_code,
                    store=False,
                )
                graph = create_agent(
                    model=model,
                    tools=tools,
                    system_prompt=_system_prompt(request),
                    response_format=request.output_schema,
                    name=f"{request.workflow}_{request.stage}",
                )
                raw_state = await graph.ainvoke(
                    {
                        "messages": [
                            {
                                "role": "user",
                                "content": _input_payload(request),
                            }
                        ]
                    },
                    config={"recursion_limit": request.selection.max_turns * 2 + 1},
                )
            if not isinstance(raw_state, Mapping):
                raise AgentExecutionFailedError()
            state = cast(Mapping[object, object], raw_state)
            candidate = _candidate(state.get("structured_response"))
            messages = state.get("messages")
            if not isinstance(messages, Sequence) or isinstance(messages, str | bytes):
                raise AgentExecutionFailedError()
            ai_messages = [
                message
                for message in cast(Sequence[object], messages)
                if isinstance(message, _AgentMessage) and message.type == "ai"
            ]
            turn_count = len(ai_messages)
            tool_call_count = sum(len(message.tool_calls) for message in ai_messages)
            return AgentExecutionResult(
                candidate=candidate,
                turn_count=turn_count,
                tool_call_count=tool_call_count,
            )
        except WorkbenchError:
            raise
        except Exception:
            raise AgentExecutionFailedError() from None


class OpenAIAgentsSdkAdapter(_ConfiguredAdapter):
    sdk_code = "openai_agents_sdk"

    async def execute(self, request: AgentExecutionRequest) -> AgentExecutionResult:
        connection = self._connection(request)
        client: AsyncOpenAI | None = None
        try:
            tools = cast(Sequence[Tool], _openai_tools(self._tool_catalog(request)))
            client = AsyncOpenAI(
                api_key=connection.api_key.get_secret_value(),
                base_url=connection.base_url,
                timeout=connection.timeout_seconds,
                max_retries=2,
            )
            model = OpenAIResponsesModel(
                model=request.selection.model_code,
                openai_client=client,
            )
            reasoning_effort = cast(
                Literal["low", "medium", "high"],
                request.selection.reasoning_effort_code,
            )
            agent = Agent(
                name=f"{request.workflow}_{request.stage}",
                instructions=_system_prompt(request),
                model=model,
                model_settings=ModelSettings(
                    reasoning=Reasoning(effort=reasoning_effort),
                    parallel_tool_calls=False,
                    store=False,
                    timeout=float(connection.timeout_seconds),
                ),
                tools=list(tools),
                output_type=str,
            )
            result = await Runner.run(
                agent,
                _input_payload(request),
                max_turns=request.selection.max_turns,
                run_config=RunConfig(
                    tracing_disabled=True,
                    trace_include_sensitive_data=False,
                    workflow_name="GDS Workbench agent stage",
                ),
            )
            return AgentExecutionResult(
                candidate=_candidate(result.final_output),
                turn_count=len(result.raw_responses),
                tool_call_count=sum(isinstance(item, ToolCallItem) for item in result.new_items),
            )
        except WorkbenchError:
            raise
        except Exception:
            raise AgentExecutionFailedError() from None
        finally:
            if client is not None:
                await client.close()


def _system_prompt(request: AgentExecutionRequest) -> str:
    if request.tool_instruction is None:
        return request.system_prompt
    return f"{request.system_prompt}\n\n{request.tool_instruction}"


def _langchain_tools(
    catalog: LocalAgentToolCatalog | None,
) -> tuple[StructuredTool, ...]:
    if catalog is None:
        return ()
    return tuple(_langchain_tool(catalog, definition) for definition in catalog.definitions)


def _langchain_tool(
    catalog: LocalAgentToolCatalog,
    definition: LocalAgentToolDefinition,
) -> StructuredTool:
    async def invoke(**arguments: JsonValue) -> JsonValue:
        return catalog.invoke(definition.name, arguments)

    return StructuredTool.from_function(
        coroutine=invoke,
        name=definition.name,
        description=definition.description,
        args_schema=cast(Any, definition.input_schema),
        infer_schema=False,
    )


def _openai_tools(
    catalog: LocalAgentToolCatalog | None,
) -> tuple[FunctionTool, ...]:
    if catalog is None:
        return ()
    return tuple(_openai_tool(catalog, definition) for definition in catalog.definitions)


def _openai_tool(
    catalog: LocalAgentToolCatalog,
    definition: LocalAgentToolDefinition,
) -> FunctionTool:
    async def invoke(_: object, raw_arguments: str) -> str:
        try:
            value = _JSON_OBJECT.validate_json(raw_arguments, strict=True)
        except ValueError:
            raise InvalidRequestError("The local agent tool arguments are invalid.") from None
        result = catalog.invoke(
            definition.name,
            value,
        )
        return json.dumps(
            result,
            ensure_ascii=False,
            allow_nan=False,
            separators=(",", ":"),
            sort_keys=True,
        )

    return FunctionTool(
        name=definition.name,
        description=definition.description,
        params_json_schema=cast(dict[str, Any], definition.input_schema),
        on_invoke_tool=invoke,
        strict_json_schema=True,
    )


def _input_payload(request: AgentExecutionRequest) -> str:
    return json.dumps(
        {
            "instruction": request.instruction_prompt,
            "context": request.context,
            "required_output_schema": request.output_schema,
        },
        ensure_ascii=False,
        allow_nan=False,
        separators=(",", ":"),
        sort_keys=True,
    )


def _candidate(value: object) -> JsonValue:
    try:
        if isinstance(value, str):
            return _JSON_VALUE.validate_json(value, strict=True)
        return _JSON_VALUE.validate_python(value, strict=True)
    except ValueError:
        raise AgentExecutionFailedError() from None
