"""Workflow-owned agent execution contracts and adapter dispatch."""

from collections.abc import Mapping
from typing import Literal, Protocol, Self, runtime_checkable

from gds_etl_workbench.domain.errors import InvalidRequestError, WorkbenchError
from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    JsonValue,
    field_validator,
    model_validator,
)
from pydantic.json_schema import SkipJsonSchema

from gds_workbench_api.capabilities import (
    AgentCapabilityRegistry,
    AgentRunSelection,
)

type AgenticWorkflow = Literal[
    "analysis_inference",
    "conceptual",
    "logical",
    "dimensional",
    "mapping",
    "code_generation",
    "validation",
]
type AgentExecutionMode = Literal[
    "one_shot",
    "tool_assisted",
    "detailed_coverage",
]

AGENT_OUTPUT_CONTRACT_INSTRUCTION = (
    "Return exactly one JSON object with no Markdown or surrounding text. Treat "
    "required_output_schema as authoritative. Before returning, verify every required "
    "field, omit fields forbidden by additionalProperties, and satisfy every declared "
    "JSON Schema constraint, including types, enum, const, format, patterns, and string, "
    "numeric, object, and array bounds."
)


class LocalAgentToolDefinition(BaseModel):
    """One safe local tool surface exposed to an agent for a single Run."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    name: str = Field(pattern=r"^[a-z][a-z0-9_]{0,99}$")
    description: str = Field(min_length=1, max_length=500)
    input_schema: dict[str, JsonValue] = Field(repr=False)

    @field_validator("description")
    @classmethod
    def validate_description(cls, value: str) -> str:
        if not value.strip() or "\x00" in value:
            raise ValueError("Local agent tool descriptions must be nonblank")
        return value

    @field_validator("input_schema")
    @classmethod
    def validate_input_schema(
        cls,
        value: dict[str, JsonValue],
    ) -> dict[str, JsonValue]:
        if value.get("type") != "object" or value.get("additionalProperties") is not False:
            raise ValueError("Local agent tool schemas must be closed JSON objects")
        return value


@runtime_checkable
class LocalAgentToolCatalog(Protocol):
    """Immutable, in-process tool catalog; implementations must perform no I/O."""

    @property
    def definitions(self) -> tuple[LocalAgentToolDefinition, ...]: ...

    @property
    def max_cumulative_result_bytes(self) -> int: ...

    def invoke(
        self,
        tool_name: str,
        arguments: Mapping[str, JsonValue],
    ) -> JsonValue: ...


class AgentExecutionRequest(BaseModel):
    """Ephemeral input. Prompt and context fields never belong in persistence/logs."""

    model_config = ConfigDict(
        arbitrary_types_allowed=True,
        extra="forbid",
        frozen=True,
        strict=True,
    )

    workflow_run_id: int = Field(gt=0)
    workflow: AgenticWorkflow
    stage: str = Field(pattern=r"^[a-z][a-z0-9_.-]{0,99}$")
    execution_mode: AgentExecutionMode
    selection: AgentRunSelection
    system_prompt: str = Field(min_length=1, max_length=1_000_000, repr=False)
    instruction_prompt: str = Field(min_length=1, max_length=1_000_000, repr=False)
    tool_instruction: str | None = Field(
        default=None,
        max_length=1_000_000,
        repr=False,
    )
    context: JsonValue = Field(repr=False)
    output_schema: dict[str, JsonValue] = Field(repr=False)
    allowed_tool_names: tuple[str, ...] = Field(default=(), max_length=50)
    local_tool_catalog: SkipJsonSchema[LocalAgentToolCatalog | None] = Field(
        default=None,
        exclude=True,
        repr=False,
    )

    @field_validator("system_prompt", "instruction_prompt", "tool_instruction")
    @classmethod
    def validate_prompt_component(cls, value: str | None) -> str | None:
        if value is not None and (not value.strip() or "\x00" in value):
            raise ValueError("Agent Prompt components must be nonblank")
        return value

    @field_validator("allowed_tool_names")
    @classmethod
    def validate_tool_names(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        if len(set(value)) != len(value) or any(
            not item or len(item) > 100 or not item.replace("_", "a").isalnum() for item in value
        ):
            raise ValueError("Agent tool names must be unique bounded identifiers")
        return value

    @model_validator(mode="after")
    def validate_local_tool_catalog(self) -> Self:
        catalog = self.local_tool_catalog
        if self.execution_mode != "tool_assisted":
            if catalog is not None or self.allowed_tool_names:
                raise ValueError("Only tool-assisted execution accepts local tools")
            return self

        if catalog is None:
            raise ValueError("Tool-assisted execution requires one local tool catalog")

        definition_names = tuple(definition.name for definition in catalog.definitions)
        if (
            not definition_names
            or len(definition_names) != len(set(definition_names))
            or definition_names != self.allowed_tool_names
        ):
            raise ValueError("The local tool catalog must match the explicit Run tool list")
        return self

    def with_selection(self, selection: AgentRunSelection) -> Self:
        return self.model_copy(update={"selection": selection})


class AgentExecutionResult(BaseModel):
    """Ephemeral candidate; authoritative workflow validation happens afterward."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    candidate: JsonValue = Field(repr=False)
    turn_count: int = Field(gt=0, le=50)
    tool_call_count: int = Field(ge=0, le=1_000)


class AgentExecutionAdapter(Protocol):
    sdk_code: str

    async def execute(self, request: AgentExecutionRequest) -> AgentExecutionResult: ...


class AgentExecutionResource(Protocol):
    async def close(self) -> None: ...


class AgentExecutionFailedError(WorkbenchError):
    def __init__(self) -> None:
        super().__init__(
            code="agent_execution_failed",
            message="The selected agent could not complete this stage.",
        )


class AgentContextToolResultTooLargeError(WorkbenchError):
    """A local Agent port result exceeded its configured byte allowance."""

    def __init__(self) -> None:
        super().__init__(
            code="agent_context_tool_result_too_large",
            message="The local agent context tool result exceeds its safe bound.",
        )


class AgentExecutionRouter:
    """Validate one explicit selection and dispatch to exactly one registered adapter."""

    def __init__(
        self,
        *,
        capabilities: AgentCapabilityRegistry,
        adapters: tuple[AgentExecutionAdapter, ...],
        resources: tuple[AgentExecutionResource, ...] = (),
    ) -> None:
        sdk_codes = [adapter.sdk_code for adapter in adapters]
        if len(sdk_codes) != len(set(sdk_codes)):
            raise ValueError("Agent adapter SDK codes must be unique")
        registered = {sdk.code for sdk in capabilities.sdks}
        if any(code not in registered for code in sdk_codes):
            raise ValueError("Every agent adapter SDK code must be registered")
        self._capabilities = capabilities
        self._adapters = {adapter.sdk_code: adapter for adapter in adapters}
        self._resources = resources
        self._closed = False

    async def execute(self, request: AgentExecutionRequest) -> AgentExecutionResult:
        self._capabilities.validate_selection(
            request.selection,
            execution_mode=request.execution_mode,
        )
        adapter = self._adapters.get(request.selection.sdk_code)
        if adapter is None:
            raise InvalidRequestError("The selected agent SDK is unavailable.")
        try:
            result = await adapter.execute(request)
            if result.turn_count > request.selection.max_turns:
                raise AgentExecutionFailedError()
            return result
        except WorkbenchError:
            raise
        except Exception:
            raise AgentExecutionFailedError() from None

    async def close(self) -> None:
        if self._closed:
            return
        for resource in reversed(self._resources):
            await resource.close()
        self._closed = True
