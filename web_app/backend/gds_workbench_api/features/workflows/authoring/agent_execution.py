"""Workflow-owned agent execution contracts and adapter dispatch."""

from collections.abc import Mapping
from typing import Literal, Protocol, Self, runtime_checkable
from uuid import UUID, uuid4

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
from gds_workbench_api.features.workflows.usage.contracts import (
    AgentUsageRecorder,
    ModelRequestRecorder,
)

type AgenticWorkflow = Literal[
    "analysis_inference",
    "conceptual",
    "logical",
    "dimensional",
    "mapping",
    "code_generation",
    "validation",
    "metadata_enrichment",
]
type AgentExecutionMode = Literal[
    "one_shot",
    "tool_assisted",
]

type AgentToolName = Literal[
    "get_agent_context_manifest",
    "get_agent_context_dataset",
    "get_mapping_context_manifest",
    "get_mapping_context_dataset",
    "get_source_context",
    "get_gds_context",
    "get_objects",
    "get_object_details",
    "get_object_relationships",
    "get_modeling_assertions",
    "get_selected_logical_entities",
    "list_conceptual_objects",
    "get_conceptual_objects",
    "list_conceptual_relationships",
    "get_conceptual_relationships",
    "list_logical_submodels",
    "get_logical_submodels",
    "list_logical_entities",
    "get_logical_entities",
    "list_logical_attributes",
    "get_logical_attributes",
    "list_logical_relationships",
    "get_logical_relationships",
    "list_dimensional_submodels",
    "get_dimensional_submodels",
    "list_dimensional_entities",
    "get_dimensional_entities",
    "list_dimensional_attributes",
    "get_dimensional_attributes",
    "list_dimensional_relationships",
    "get_dimensional_relationships",
    "get_mapping_target",
    "get_mapping_sources",
    "get_existing_mapping",
    "get_mapping_support",
    "get_mapping_support_records",
    "get_code_target",
    "get_code_sources",
    "get_code_source_systems",
    "get_object_transformations",
    "get_attribute_transformations",
    "get_mapping_evidence",
    "get_current_code",
    "get_applied_groups",
    "get_applied_checks",
]

AGENT_OUTPUT_CONTRACT_INSTRUCTION = (
    "Return exactly one JSON object with no Markdown or surrounding text. Treat "
    "required_output_schema as authoritative. Before returning, verify every required "
    "field, omit fields forbidden by additionalProperties, and satisfy every declared "
    "JSON Schema constraint, including types, enum, const, format, patterns, and string, "
    "numeric, object, and array bounds. The current schema overrides incompatible "
    "formatting instructions or examples in older prompts. Context identities and "
    "manifests are read-only evidence; repeat them only where the schema asks. "
    "The backend preserves existing locks; emit only the authoring values allowed "
    "by the schema. When repair.previous_candidate_omitted is true, regenerate "
    "from the rendered prompt evidence, enabled tools, and validation issues."
)


class LocalAgentToolDefinition(BaseModel):
    """One safe local tool surface exposed to an agent for a single Run."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    name: str = Field(pattern=r"^[a-z][a-z0-9_]{0,99}$")
    description: str = Field(min_length=1, max_length=500)
    input_schema: dict[str, JsonValue] = Field(repr=False)
    result_schema: dict[str, JsonValue] | None = Field(default=None, repr=False)
    example: dict[str, JsonValue] | None = Field(default=None, repr=False)
    default_behavior: str | None = Field(default=None, max_length=500)

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
    def max_cumulative_result_bytes(self) -> int | None: ...

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
    invocation_id: UUID = Field(default_factory=uuid4, exclude=True)
    authoring_attempt: int = Field(default=1, ge=1, le=6, exclude=True)
    model_request_recorder: SkipJsonSchema[ModelRequestRecorder | None] = Field(
        default=None,
        exclude=True,
        repr=False,
    )
    system_prompt: str = Field(min_length=1, repr=False)
    instruction_prompt: str = Field(min_length=1, repr=False)
    tool_instruction: str | None = Field(
        default=None,
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
            len(definition_names) != len(set(definition_names))
            or definition_names != self.allowed_tool_names
        ):
            raise ValueError("The local tool catalog must match the explicit Run tool list")
        return self

    def with_selection(self, selection: AgentRunSelection) -> Self:
        return self.model_copy(update={"selection": selection})


def agent_input_payload(request: AgentExecutionRequest) -> dict[str, JsonValue]:
    """Only author-rendered evidence and backend output/repair controls reach the model."""
    repair = request.context.get("repair") if isinstance(request.context, dict) else None
    return {
        "instruction": request.instruction_prompt,
        "context": {"repair": repair},
        "required_output_schema": request.output_schema,
    }


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


type AgentFailureReason = Literal[
    "execution_failed",
    "context_exhausted",
    "output_truncated",
    "timeout",
    "rate_limited",
    "authentication_failed",
    "provider_unavailable",
    "provider_request_rejected",
    "input_filtered",
    "request_too_large",
    "reasoning_rejected",
    "tool_definition_rejected",
    "conversation_rejected",
    "response_format_rejected",
    "model_unavailable",
    "tool_failed",
    "turn_limit_exceeded",
    "output_refused",
]


class AgentExecutionFailedError(WorkbenchError):
    """Only fixed public diagnostics cross the provider boundary."""

    def __init__(
        self,
        reason: AgentFailureReason = "execution_failed",
        *,
        provider_http_status: int | None = None,
    ) -> None:
        messages: dict[AgentFailureReason, str] = {
            "execution_failed": "The selected agent could not complete this stage.",
            "context_exhausted": (
                "The selected model's context window is full. Reduce the selected scope "
                "or choose a model with a larger context window."
            ),
            "output_truncated": (
                "The selected model stopped at its output limit. "
                "No partial candidate was accepted. "
                "Reduce the selected scope or choose a model with a larger output limit."
            ),
            "timeout": "The selected model timed out. Retry this run.",
            "rate_limited": "The model provider is rate limited. Wait before retrying this run.",
            "authentication_failed": (
                "The model provider rejected authentication or access. "
                "Ask an administrator to check the provider configuration."
            ),
            "provider_unavailable": "The model provider is unavailable. Retry this run later.",
            "provider_request_rejected": (
                "The model provider rejected this request. "
                "Ask an administrator to check this run's model configuration and request."
            ),
            "input_filtered": (
                "The model provider's content filter blocked this request. "
                "Ask an administrator to review this workflow's prompt and inputs "
                "alongside the provider's filter assessment."
            ),
            "request_too_large": (
                "The model provider rejected the request because it is too large. "
                "Review this workflow's prompt and input size, "
                "or choose a model with a larger input limit."
            ),
            "reasoning_rejected": (
                "The model provider rejected the reasoning setting. "
                "Choose Provider default, or ask an administrator to check which "
                "reasoning settings the deployed model supports."
            ),
            "tool_definition_rejected": (
                "The model provider rejected the tool definitions or tool settings. "
                "Ask an administrator to check the deployed model's tool support "
                "and the application's tool configuration."
            ),
            "conversation_rejected": (
                "The model provider rejected the message or tool-response structure. "
                "Ask an administrator to check the application's provider integration."
            ),
            "response_format_rejected": (
                "The model provider rejected the JSON response format. "
                "Ask an administrator to check JSON-object support for the deployed model."
            ),
            "model_unavailable": (
                "The configured model deployment could not be found. "
                "Ask an administrator to check the deployment name and provider endpoint."
            ),
            "tool_failed": (
                "A local agent tool could not complete. No partial candidate was accepted."
            ),
            "turn_limit_exceeded": (
                "The agent reached its turn limit before completing this stage. "
                "Reduce the selected scope or increase the run's turn limit."
            ),
            "output_refused": "The model provider declined to produce this stage's output.",
        }
        message = messages[reason]
        if (
            reason == "provider_request_rejected"
            and type(provider_http_status) is int
            and 400 <= provider_http_status <= 499
        ):
            message += f" Provider HTTP {provider_http_status}."
        super().__init__(code=f"agent_{reason}", message=message)


class AgentContextToolRequestError(WorkbenchError):
    def __init__(self) -> None:
        super().__init__(
            code="agent_context_tool_request_invalid",
            message="The local agent context tool request is invalid.",
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
        usage_recorder: AgentUsageRecorder | None = None,
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
        self._usage_recorder = usage_recorder
        self._closed = False

    async def execute(self, request: AgentExecutionRequest) -> AgentExecutionResult:
        self._capabilities.validate_selection(
            request.selection,
            execution_mode=request.execution_mode,
        )
        adapter = self._adapters.get(request.selection.sdk_code)
        if adapter is None:
            raise InvalidRequestError("The selected agent SDK is unavailable.")
        if self._usage_recorder is not None:
            request = request.model_copy(
                update={
                    "model_request_recorder": self._usage_recorder.make_invocation_recorder(
                        workflow_run_id=request.workflow_run_id,
                        stage_code=request.stage,
                        invocation_id=request.invocation_id,
                        authoring_attempt=request.authoring_attempt,
                    )
                }
            )
        try:
            result = await adapter.execute(request)
            if result.turn_count > request.selection.max_turns:
                raise AgentExecutionFailedError("turn_limit_exceeded")
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
