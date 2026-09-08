"""OpenAI Agents SDK execution and Microsoft Foundry authentication."""

from __future__ import annotations

import asyncio
import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from threading import Lock
from typing import Any, Protocol, cast

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
from gds_etl_workbench.domain.errors import InvalidRequestError, WorkbenchError
from openai import AsyncOpenAI, DefaultAsyncHttpxClient
from openai.types.shared import Reasoning, ReasoningEffort
from pydantic import JsonValue, SecretStr, TypeAdapter

from gds_workbench_api.features.workflows.authoring.agent_execution import (
    AGENT_OUTPUT_CONTRACT_INSTRUCTION,
    AgentContextToolResultTooLargeError,
    AgentExecutionFailedError,
    AgentExecutionRequest,
    AgentExecutionResult,
    LocalAgentToolCatalog,
    LocalAgentToolDefinition,
    agent_input_payload,
)
from gds_workbench_api.integrations.agents.configuration import (
    AgentProviderConnection,
)
from gds_workbench_api.integrations.agents.usage import ProviderUsageHooks

_JSON_VALUE: TypeAdapter[JsonValue] = TypeAdapter(JsonValue)
_JSON_OBJECT: TypeAdapter[dict[str, JsonValue]] = TypeAdapter(dict[str, JsonValue])


@dataclass(frozen=True, slots=True)
class OpenAIProviderCredentials:
    api_key: SecretStr = field(repr=False)
    base_url: str


class ModelAuthentication(Protocol):
    async def authenticate(self) -> OpenAIProviderCredentials: ...


class ManagedModelAuthentication(ModelAuthentication, Protocol):
    async def close(self) -> None: ...


class FoundryApiKeyAuthentication:
    """Use one deployment-provided API key for a direct Foundry endpoint."""

    def __init__(self, *, base_url: str, api_key: SecretStr) -> None:
        self._base_url = base_url.rstrip("/") + "/"
        self._api_key = api_key
        self._closed = False

    async def authenticate(self) -> OpenAIProviderCredentials:
        if self._closed:
            raise RuntimeError("Foundry API key authentication is closed")
        return OpenAIProviderCredentials(
            api_key=self._api_key,
            base_url=self._base_url,
        )

    async def close(self) -> None:
        self._closed = True

    def __repr__(self) -> str:
        return "FoundryApiKeyAuthentication()"


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


class OpenAIAgentsSdkAdapter:
    sdk_code = "openai_agents_sdk"

    def __init__(
        self,
        *,
        connections: tuple[AgentProviderConnection, ...],
        model_authentications: Mapping[str, ModelAuthentication] | None = None,
    ) -> None:
        connection_keys = [
            (connection.provider_code, connection.model_code) for connection in connections
        ]
        if len(connection_keys) != len(set(connection_keys)):
            raise ValueError("Agent provider/model connections must be unique")
        self._connections = {
            (connection.provider_code, connection.model_code): connection
            for connection in connections
        }
        provider_codes = {connection.provider_code for connection in connections}
        self._model_authentications = dict(model_authentications or {})
        if provider_codes != set(self._model_authentications):
            raise ValueError("Every Agent provider connection requires one authentication adapter")

    def __repr__(self) -> str:
        return f"{type(self).__name__}(configured_models={len(self._connections)})"

    def _connection(self, request: AgentExecutionRequest) -> AgentProviderConnection:
        if request.selection.sdk_code != self.sdk_code:
            raise InvalidRequestError("The selected agent SDK is incompatible.")
        connection = self._connections.get(
            (request.selection.provider_code, request.selection.model_code)
        )
        if connection is None:
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
        if names != request.allowed_tool_names or len(names) != len(set(names)):
            raise InvalidRequestError("A selected local agent tool is unavailable.")
        if catalog.max_cumulative_result_bytes < 1:
            raise InvalidRequestError("A selected local agent tool is unavailable.")
        return _PerExecutionToolCatalog(catalog)

    async def execute(self, request: AgentExecutionRequest) -> AgentExecutionResult:
        connection = self._connection(request)
        client: AsyncOpenAI | None = None
        http_client = None
        hooks: ProviderUsageHooks | None = None
        try:
            credentials = await self._authentication(connection).authenticate()
            tools = cast(Sequence[Tool], _openai_tools(self._tool_catalog(request)))
            if request.model_request_recorder is not None:
                hooks = ProviderUsageHooks(request.model_request_recorder)
                http_client = DefaultAsyncHttpxClient(
                    event_hooks={"request": [hooks.on_request], "response": [hooks.on_response]},
                )
            client = AsyncOpenAI(
                api_key=credentials.api_key.get_secret_value(),
                base_url=credentials.base_url,
                timeout=connection.timeout_seconds,
                max_retries=2,
                http_client=http_client,
            )
            model = OpenAIChatCompletionsModel(
                model=connection.model_endpoint,
                openai_client=client,
            )
            if request.selection.reasoning_effort_code == "default":
                model_settings = ModelSettings(
                    parallel_tool_calls=False,
                    timeout=float(connection.timeout_seconds),
                )
            else:
                reasoning_effort = cast(
                    ReasoningEffort,
                    request.selection.reasoning_effort_code,
                )
                model_settings = ModelSettings(
                    reasoning=Reasoning(effort=reasoning_effort),
                    parallel_tool_calls=False,
                    timeout=float(connection.timeout_seconds),
                )
            model_settings.extra_body = {"response_format": {"type": "json_object"}}
            agent = Agent(
                name=f"{request.workflow}_{request.stage}",
                instructions=_system_prompt(request),
                model=model,
                model_settings=model_settings,
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
            if hooks is not None and hooks.error is not None:
                raise hooks.error
            return AgentExecutionResult(
                candidate=_candidate(result.final_output),
                turn_count=len(result.raw_responses),
                tool_call_count=sum(isinstance(item, ToolCallItem) for item in result.new_items),
            )
        except WorkbenchError:
            raise
        except Exception:
            if hooks is not None and hooks.error is not None:
                raise hooks.error from None
            raise AgentExecutionFailedError() from None
        finally:
            if client is not None:
                await client.close()
            elif http_client is not None:
                await http_client.aclose()


class _PerExecutionToolCatalog:
    """Apply one fresh cumulative result budget to one provider conversation."""

    def __init__(self, catalog: LocalAgentToolCatalog) -> None:
        self._catalog = catalog
        self._maximum_bytes = catalog.max_cumulative_result_bytes
        self._used_bytes = 0
        self._budget_lock = Lock()

    @property
    def definitions(self) -> tuple[LocalAgentToolDefinition, ...]:
        return self._catalog.definitions

    @property
    def max_cumulative_result_bytes(self) -> int:
        return self._maximum_bytes

    def invoke(
        self,
        tool_name: str,
        arguments: Mapping[str, JsonValue],
    ) -> JsonValue:
        result = self._catalog.invoke(tool_name, arguments)
        result_bytes = len(
            json.dumps(
                result,
                ensure_ascii=False,
                allow_nan=False,
                separators=(",", ":"),
                sort_keys=True,
            ).encode("utf-8")
        )
        with self._budget_lock:
            if self._used_bytes + result_bytes > self._maximum_bytes:
                raise AgentContextToolResultTooLargeError()
            self._used_bytes += result_bytes
        return result


def _system_prompt(request: AgentExecutionRequest) -> str:
    sections = [request.system_prompt]
    if request.tool_instruction is not None:
        sections.append(request.tool_instruction)
    sections.append(AGENT_OUTPUT_CONTRACT_INSTRUCTION)
    return "\n\n".join(sections)


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
        strict_json_schema=False,
    )


def _input_payload(request: AgentExecutionRequest) -> str:
    return json.dumps(
        agent_input_payload(request),
        ensure_ascii=False,
        allow_nan=False,
        separators=(",", ":"),
        sort_keys=True,
    )


def _candidate(value: object) -> JsonValue:
    def unique_object(pairs: list[tuple[str, JsonValue]]) -> dict[str, JsonValue]:
        result = dict(pairs)
        if len(result) != len(pairs):
            raise ValueError("Candidate object keys must be unique")
        return result

    try:
        if isinstance(value, str):
            # Reject repeated keys before JSON parsing can silently keep only the last value.
            decoded: object = json.loads(value, object_pairs_hook=unique_object)
            return _JSON_VALUE.validate_python(decoded, strict=True)
        return _JSON_VALUE.validate_python(value, strict=True)
    except (ValueError, RecursionError):
        if isinstance(value, str):
            # Keep malformed output ephemeral so the schema gate can request a repair.
            return value
        raise AgentExecutionFailedError() from None
