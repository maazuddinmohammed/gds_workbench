"""Concrete, non-logging adapters for the two supported agent SDKs."""

from __future__ import annotations

import asyncio
import json
from collections.abc import Mapping, Sequence
from contextlib import AbstractContextManager
from dataclasses import dataclass, field
from typing import Any, Literal, Protocol, cast, runtime_checkable
from urllib.parse import urlsplit

import langchain.agents as langchain_agents
import langsmith.run_helpers as langsmith_run_helpers
from agents import (
    Agent,
    FunctionTool,
    ModelSettings,
    OpenAIChatCompletionsModel,
    RunConfig,
    Runner,
    Tool,
    ToolCallItem,
)
from azure.identity.aio import ClientSecretCredential as AsyncClientSecretCredential
from databricks.sdk import WorkspaceClient
from gds_etl_workbench.domain.errors import InvalidRequestError, WorkbenchError
from langchain_core.tools import BaseTool, StructuredTool
from langchain_openai import ChatOpenAI
from openai import AsyncOpenAI
from openai.types.shared import Reasoning
from pydantic import JsonValue, SecretStr, TypeAdapter

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
        name: str,
    ) -> _LangChainGraph: ...


class _TracingContext(Protocol):
    def __call__(self, *, enabled: bool) -> AbstractContextManager[None]: ...


@runtime_checkable
class _AgentMessage(Protocol):
    type: str
    tool_calls: Sequence[object]
    content: object


create_agent = cast(_CreateAgent, vars(langchain_agents)["create_agent"])
tracing_context = cast(_TracingContext, vars(langsmith_run_helpers)["tracing_context"])


@dataclass(frozen=True, slots=True)
class OpenAIProviderCredentials:
    api_key: SecretStr = field(repr=False)
    base_url: str


class ModelAuthentication(Protocol):
    async def authenticate(self) -> OpenAIProviderCredentials: ...


class ManagedModelAuthentication(ModelAuthentication, Protocol):
    async def close(self) -> None: ...


class DatabricksModelAuthentication:
    """Resolve short-lived app service-principal credentials through unified auth."""

    async def authenticate(self) -> OpenAIProviderCredentials:
        return await asyncio.to_thread(self._authenticate)

    @staticmethod
    def _authenticate() -> OpenAIProviderCredentials:
        workspace = WorkspaceClient(
            auth_type="oauth-m2m",
            debug_headers=False,
            product="gds-workbench-web",
            product_version="0.1.0",
        )
        headers = workspace.config.authenticate()
        authorization = next(
            (value for name, value in headers.items() if name.lower() == "authorization"),
            "",
        )
        scheme, _, access_token = authorization.partition(" ")
        host = (workspace.config.host or "").rstrip("/")
        parsed_host = urlsplit(host)
        if (
            scheme.lower() != "bearer"
            or not access_token
            or parsed_host.scheme != "https"
            or not parsed_host.hostname
            or parsed_host.username is not None
            or parsed_host.password is not None
            or parsed_host.path not in {"", "/"}
            or parsed_host.query
            or parsed_host.fragment
        ):
            raise RuntimeError("Databricks model authentication is unavailable")
        return OpenAIProviderCredentials(
            api_key=SecretStr(access_token),
            base_url=f"{host}/serving-endpoints",
        )

    def __repr__(self) -> str:
        return "DatabricksModelAuthentication()"

    async def close(self) -> None:
        return None


class FoundryModelAuthentication:
    """Resolve a short-lived Entra token for one direct Foundry OpenAI endpoint."""

    def __init__(
        self,
        *,
        base_url: str,
        token_scope: str,
        tenant_id: str,
        client_id: str,
        client_secret: SecretStr,
    ) -> None:
        self._base_url = base_url.rstrip("/") + "/"
        self._token_scope = token_scope
        self._credential = AsyncClientSecretCredential(
            tenant_id=tenant_id,
            client_id=client_id,
            client_secret=client_secret.get_secret_value(),
        )
        self._close_lock = asyncio.Lock()
        self._closed = False

    async def authenticate(self) -> OpenAIProviderCredentials:
        if self._closed:
            raise RuntimeError("Foundry model authentication is closed")
        token = await self._credential.get_token(self._token_scope)
        if not token.token:
            raise RuntimeError("Foundry model authentication is unavailable")
        return OpenAIProviderCredentials(
            api_key=SecretStr(token.token),
            base_url=self._base_url,
        )

    async def close(self) -> None:
        async with self._close_lock:
            if self._closed:
                return
            await self._credential.close()
            self._closed = True

    def __repr__(self) -> str:
        return "FoundryModelAuthentication()"


class _ConfiguredAdapter:
    sdk_code: str

    def __init__(
        self,
        *,
        connections: tuple[AgentProviderConnection, ...],
        model_authentications: Mapping[str, ModelAuthentication] | None = None,
    ) -> None:
        provider_codes = [connection.provider_code for connection in connections]
        if len(provider_codes) != len(set(provider_codes)):
            raise ValueError("Agent provider connections must be unique")
        self._connections = {connection.provider_code: connection for connection in connections}
        if model_authentications is None:
            self._model_authentications = (
                {"databricks": DatabricksModelAuthentication()}
                if "databricks" in self._connections
                else {}
            )
        else:
            self._model_authentications = dict(model_authentications)
        if set(self._connections) != set(self._model_authentications):
            raise ValueError("Every Agent provider connection requires one authentication adapter")

    def __repr__(self) -> str:
        return f"{type(self).__name__}(configured_providers={len(self._connections)})"

    def _connection(self, request: AgentExecutionRequest) -> AgentProviderConnection:
        if request.selection.sdk_code != self.sdk_code:
            raise InvalidRequestError("The selected agent SDK is incompatible.")
        connection = self._connections.get(request.selection.provider_code)
        if connection is None or connection.model_code != request.selection.model_code:
            raise InvalidRequestError("The selected agent provider is unavailable.")
        return connection

    def _authentication(self, connection: AgentProviderConnection) -> ModelAuthentication:
        authentication = self._model_authentications.get(connection.provider_code)
        if authentication is None:
            raise InvalidRequestError("The selected agent provider is unavailable.")
        return authentication

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
            credentials = await self._authentication(connection).authenticate()
            with tracing_context(enabled=False):
                tools: Sequence[BaseTool] = _langchain_tools(self._tool_catalog(request))
                model = ChatOpenAI(
                    model=connection.model_endpoint,
                    api_key=credentials.api_key,
                    base_url=credentials.base_url,
                    timeout=connection.timeout_seconds,
                    max_retries=2,
                    reasoning_effort=request.selection.reasoning_effort_code,
                )
                graph = create_agent(
                    model=model,
                    tools=tools,
                    system_prompt=_system_prompt(request),
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
            messages = state.get("messages")
            if not isinstance(messages, Sequence) or isinstance(messages, str | bytes):
                raise AgentExecutionFailedError()
            ai_messages = [
                message
                for message in cast(Sequence[object], messages)
                if isinstance(message, _AgentMessage) and message.type == "ai"
            ]
            if not ai_messages:
                raise AgentExecutionFailedError()
            candidate = _candidate(_message_text(ai_messages[-1].content))
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
            credentials = await self._authentication(connection).authenticate()
            tools = cast(Sequence[Tool], _openai_tools(self._tool_catalog(request)))
            client = AsyncOpenAI(
                api_key=credentials.api_key.get_secret_value(),
                base_url=credentials.base_url,
                timeout=connection.timeout_seconds,
                max_retries=2,
            )
            model = OpenAIChatCompletionsModel(
                model=connection.model_endpoint,
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
    sections = [request.system_prompt]
    if request.tool_instruction is not None:
        sections.append(request.tool_instruction)
    sections.append("Return exactly one JSON object with no Markdown or surrounding text.")
    return "\n\n".join(sections)


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


def _message_text(content: object) -> str:
    if isinstance(content, str) and content:
        return content
    if not isinstance(content, Sequence) or isinstance(content, str | bytes):
        raise AgentExecutionFailedError()
    parts: list[str] = []
    for block in cast(Sequence[object], content):
        if not isinstance(block, Mapping):
            continue
        block_mapping = cast(Mapping[object, object], block)
        if block_mapping.get("type") != "text":
            continue
        text = block_mapping.get("text")
        if isinstance(text, str) and text:
            parts.append(text)
    if not parts:
        raise AgentExecutionFailedError()
    return "".join(parts)
