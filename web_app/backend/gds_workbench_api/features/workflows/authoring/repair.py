"""Bounded validation-repair loop with immutable original context."""

from __future__ import annotations

import json
import re
from collections.abc import Iterable
from copy import deepcopy
from hashlib import sha256
from importlib.resources import files
from itertools import islice
from typing import Literal, Protocol, cast

from gds_etl_workbench.application.change_sets.contracts import MAX_MODEL_STAGE_PAYLOAD_BYTES
from gds_etl_workbench.domain.errors import WorkbenchError
from gds_etl_workbench.domain.snapshots.model import (
    CHANGE_SET_DATASETS,
    DATASETS_BY_NAME,
    build_model_dataset_schema,
)
from jsonschema import Draft202012Validator
from jsonschema.exceptions import SchemaError
from jsonschema.exceptions import ValidationError as JsonSchemaValidationError
from pydantic import BaseModel, ConfigDict, Field, JsonValue, ValidationError, field_validator

from gds_workbench_api.features.workflows.authoring.agent_execution import (
    AGENT_OUTPUT_CONTRACT_INSTRUCTION,
    AgentExecutionRequest,
    AgentExecutionResult,
)


class AgentValidationIssue(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    code: str = Field(pattern=r"^[a-z][a-z0-9_.-]{0,99}$")
    path: tuple[str | int, ...] = Field(max_length=20)
    message: str = Field(min_length=1, max_length=500)

    @field_validator("path")
    @classmethod
    def validate_path(cls, value: tuple[str | int, ...]) -> tuple[str | int, ...]:
        if any(
            isinstance(item, bool)
            or (isinstance(item, int) and item < 0)
            or (isinstance(item, str) and (not item or len(item) > 100))
            for item in value
        ):
            raise ValueError("Agent validation issue path is invalid")
        return value

    @field_validator("message")
    @classmethod
    def validate_message(cls, value: str) -> str:
        if not value.strip() or "\x00" in value:
            raise ValueError("Agent validation issue message is invalid")
        return value


class AgentCandidateValidation(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    issues: tuple[AgentValidationIssue, ...] = Field(max_length=200)


_MODEL_RECORD_DATASETS = {
    definition.row_model.__name__: definition.name for definition in CHANGE_SET_DATASETS
}
_SEMANTIC_SCHEMA_KEYS = (
    "description",
    "x-gds-population-guidance",
    "examples",
)
_MAX_PYDANTIC_VALIDATION_ISSUES = 100


def enrich_agent_output_model_definitions(schema: dict[str, JsonValue]) -> None:
    """Reuse exact Model field guidance without changing agent-output constraints."""

    raw_definitions = schema.get("$defs")
    if not isinstance(raw_definitions, dict):
        return
    definitions = cast(dict[str, object], raw_definitions)
    for definition_name, dataset in _MODEL_RECORD_DATASETS.items():
        raw_definition = definitions.get(definition_name)
        if not isinstance(raw_definition, dict):
            continue
        canonical = build_model_dataset_schema(DATASETS_BY_NAME[dataset])
        definition = cast(dict[str, object], raw_definition)
        _copy_semantic_schema_guidance(definition, canonical)
        rules = canonical.get("x-gds-population-rules")
        if isinstance(rules, list):
            definition["x-gds-population-rules"] = deepcopy(cast(list[object], rules))
        canonical_definitions = canonical.get("$defs")
        if not isinstance(canonical_definitions, dict):
            continue
        nested_definitions = cast(dict[str, object], canonical_definitions)
        for nested_name, raw_nested in nested_definitions.items():
            target_nested = definitions.get(nested_name)
            if isinstance(raw_nested, dict) and isinstance(target_nested, dict):
                _copy_semantic_schema_guidance(
                    cast(dict[str, object], target_nested),
                    cast(dict[str, object], raw_nested),
                )


def _copy_semantic_schema_guidance(
    target: dict[str, object],
    source: dict[str, object],
) -> None:
    """Copy human guidance only; validation keywords remain target-owned."""

    for key in _SEMANTIC_SCHEMA_KEYS:
        value = source.get(key)
        if isinstance(value, str) and value.strip():
            target[key] = value
        elif key == "examples" and isinstance(value, list) and value:
            target[key] = deepcopy(cast(list[object], value))

    raw_target_properties = target.get("properties")
    raw_source_properties = source.get("properties")
    if not isinstance(raw_target_properties, dict) or not isinstance(raw_source_properties, dict):
        return
    target_properties = cast(dict[str, object], raw_target_properties)
    source_properties = cast(dict[str, object], raw_source_properties)
    for field, raw_target_property in target_properties.items():
        raw_source_property = source_properties.get(field)
        if isinstance(raw_target_property, dict) and isinstance(raw_source_property, dict):
            _copy_semantic_schema_guidance(
                cast(dict[str, object], raw_target_property),
                cast(dict[str, object], raw_source_property),
            )


def parse_pydantic_candidate[CandidateT: BaseModel](
    model: type[CandidateT],
    candidate: JsonValue,
    *,
    maximum_issues: int = _MAX_PYDANTIC_VALIDATION_ISSUES,
) -> tuple[CandidateT | None, tuple[AgentValidationIssue, ...]]:
    """Parse strict JSON and return bounded, value-free Pydantic diagnostics."""

    if not 1 <= maximum_issues <= 200:
        raise ValueError("maximum_issues must be between 1 and 200")
    try:
        raw = json.dumps(
            candidate,
            ensure_ascii=False,
            allow_nan=False,
            separators=(",", ":"),
        )
    except (TypeError, ValueError):
        return None, (_pydantic_fallback_issue(),)
    try:
        return model.model_validate_json(raw, strict=True), ()
    except ValidationError as error:
        issues = pydantic_validation_issues(error, maximum_issues=maximum_issues)
        return None, issues or (_pydantic_fallback_issue(),)
    except (TypeError, ValueError):
        return None, (_pydantic_fallback_issue(),)


def pydantic_validation_issues(
    error: ValidationError,
    *,
    path_prefix: tuple[str | int, ...] = (),
    maximum_issues: int = _MAX_PYDANTIC_VALIDATION_ISSUES,
) -> tuple[AgentValidationIssue, ...]:
    """Translate Pydantic failures without copying messages, context, or input values."""

    if not 1 <= maximum_issues <= 200:
        raise ValueError("maximum_issues must be between 1 and 200")
    safe_prefix = _safe_output_path(cast(tuple[object, ...], path_prefix))
    raw_errors = error.errors(
        include_url=False,
        include_context=False,
        include_input=False,
    )
    issues: list[AgentValidationIssue] = []
    seen: set[tuple[str, tuple[str | int, ...]]] = set()
    for raw_error in raw_errors:
        raw_location = raw_error.get("loc", ())
        path = _safe_output_path((*safe_prefix, *cast(tuple[object, ...], raw_location)))
        error_type = raw_error.get("type")
        code, message = _pydantic_diagnostic(error_type)
        identity = (code, path)
        if identity in seen:
            continue
        seen.add(identity)
        issues.append(AgentValidationIssue(code=code, path=path, message=message))
        if len(issues) == maximum_issues:
            break
    issues.sort(key=lambda issue: (_path_sort_key(issue.path), issue.code))
    return tuple(issues)


def _pydantic_diagnostic(error_type: str) -> tuple[str, str]:
    if error_type in {"value_error", "assertion_error"}:
        return (
            "candidate.cross_field_invalid",
            "Fields at this path violate a cross-field rule in the output contract.",
        )
    if error_type == "missing":
        return "candidate.schema_required", "A required candidate field is missing."
    if error_type == "extra_forbidden":
        return (
            "candidate.schema_additional_property",
            "The candidate contains a field that the output contract does not allow.",
        )
    if error_type in {"literal_error", "enum", "union_tag_invalid", "union_tag_not_found"}:
        return (
            "candidate.schema_value",
            "The candidate field does not use an allowed contract value.",
        )
    if error_type in {
        "string_too_short",
        "string_too_long",
        "too_short",
        "too_long",
        "greater_than",
        "greater_than_equal",
        "less_than",
        "less_than_equal",
        "multiple_of",
    }:
        return (
            "candidate.schema_bound",
            "The candidate field violates a declared output bound.",
        )
    if error_type == "string_pattern_mismatch":
        return (
            "candidate.schema_pattern",
            "The candidate field does not match the required pattern.",
        )
    if error_type.endswith("_type") or error_type.endswith("_parsing"):
        return "candidate.schema_type", "The candidate field has the wrong JSON type."
    return "candidate.schema_invalid", "The candidate field violates the output contract."


def _pydantic_fallback_issue() -> AgentValidationIssue:
    return AgentValidationIssue(
        code="candidate.schema_invalid",
        path=(),
        message="The candidate does not match the required output contract.",
    )


class AgentContextPolicy(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    schema_version: Literal["1.0"] = "1.0"
    one_shot_max_context_bytes: int = Field(ge=1, le=10 * 1024 * 1024)
    stage_max_context_bytes: int = Field(ge=1, le=10 * 1024 * 1024)
    max_candidate_bytes: int = Field(ge=1, le=10 * 1024 * 1024)
    max_validation_issues: int = Field(ge=1, le=200)


class AgentAuthoringResult(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    candidate: JsonValue = Field(repr=False)
    attempt_count: int = Field(ge=1, le=6)
    was_repaired: bool
    turn_count: int = Field(ge=1, le=300)
    tool_call_count: int = Field(ge=0, le=6_000)


class AgentExecutor(Protocol):
    async def execute(self, request: AgentExecutionRequest) -> AgentExecutionResult: ...


class AgentCandidateValidator(Protocol):
    async def validate(self, candidate: JsonValue) -> AgentCandidateValidation: ...


class AgentContextTooLargeError(WorkbenchError):
    def __init__(self) -> None:
        super().__init__(
            code="agent_context_too_large",
            message=(
                "The selected execution mode cannot accept this context. "
                "Choose another mode explicitly."
            ),
        )


class AgentCandidateValidationError(WorkbenchError):
    def __init__(self) -> None:
        super().__init__(
            code="agent_candidate_validation_failed",
            message="The agent candidate did not pass complete backend validation.",
        )


class ValidationRepairRunner:
    """Return one complete validated candidate or fail without a writable result."""

    def __init__(
        self,
        *,
        executor: AgentExecutor,
        policy: AgentContextPolicy,
    ) -> None:
        self._executor = executor
        self._policy = policy

    async def run(
        self,
        *,
        request: AgentExecutionRequest,
        validator: AgentCandidateValidator,
        max_candidate_bytes: int | None = None,
    ) -> AgentAuthoringResult:
        candidate_byte_limit = (
            self._policy.max_candidate_bytes if max_candidate_bytes is None else max_candidate_bytes
        )
        if not 1 <= candidate_byte_limit <= MAX_MODEL_STAGE_PAYLOAD_BYTES:
            raise ValueError("max_candidate_bytes must fit the Stage payload envelope")
        original_context = deepcopy(request.context)
        context_limit = (
            self._policy.one_shot_max_context_bytes
            if request.execution_mode == "one_shot"
            else self._policy.stage_max_context_bytes
        )
        context_budget = _request_context_budget(
            request=request,
            maximum_bytes=context_limit,
        )
        output_schema_validator = _output_schema_validator(request.output_schema)
        attempt_count = 0
        turn_count = 0
        tool_call_count = 0
        repair: dict[str, JsonValue] | None = None

        while True:
            attempt_context = _bounded_attempt_context(
                original_context=original_context,
                repair=repair,
                maximum_bytes=context_budget,
            )
            attempt_request = request.model_copy(update={"context": attempt_context})
            if agent_request_envelope_bytes(attempt_request) > context_limit:
                raise AgentContextTooLargeError()
            execution = await self._executor.execute(attempt_request)
            attempt_count += 1
            turn_count += execution.turn_count
            tool_call_count += execution.tool_call_count
            if _json_bytes(execution.candidate) > candidate_byte_limit:
                raise AgentCandidateValidationError()

            schema_issues = _output_schema_issues(
                output_schema_validator,
                execution.candidate,
                maximum_issues=self._policy.max_validation_issues,
            )
            if schema_issues:
                validation = AgentCandidateValidation(issues=schema_issues)
            else:
                try:
                    validation = await validator.validate(execution.candidate)
                except WorkbenchError:
                    raise
                except Exception:
                    raise AgentCandidateValidationError() from None
            if len(validation.issues) > self._policy.max_validation_issues:
                raise AgentCandidateValidationError()
            if not validation.issues:
                return AgentAuthoringResult(
                    candidate=execution.candidate,
                    attempt_count=attempt_count,
                    was_repaired=attempt_count > 1,
                    turn_count=turn_count,
                    tool_call_count=tool_call_count,
                )
            if attempt_count > request.selection.validation_retry_count:
                raise AgentCandidateValidationError()

            repair = {
                "attempt": attempt_count,
                "previous_candidate": execution.candidate,
                "validation_issues": [issue.model_dump(mode="json") for issue in validation.issues],
            }


def _bounded_attempt_context(
    *,
    original_context: JsonValue,
    repair: dict[str, JsonValue] | None,
    maximum_bytes: int,
) -> JsonValue:
    attempt = cast(
        JsonValue,
        {
            "original_context": deepcopy(original_context),
            "repair": deepcopy(repair),
        },
    )
    if _json_bytes(attempt) <= maximum_bytes:
        return attempt
    if repair is None:
        raise AgentContextTooLargeError()

    previous_candidate = repair.get("previous_candidate")
    raw_issues = repair.get("validation_issues")
    if not isinstance(raw_issues, list) or not raw_issues:
        raise AgentCandidateValidationError()
    compact_repair: dict[str, JsonValue] = {
        "attempt": repair.get("attempt"),
        "previous_candidate": None,
        "previous_candidate_digest": sha256(_json_data(previous_candidate)).hexdigest(),
        "previous_candidate_omitted": True,
        "validation_issue_count": len(raw_issues),
        "validation_issues": [],
    }
    compact_attempt = cast(
        JsonValue,
        {
            "original_context": deepcopy(original_context),
            "repair": compact_repair,
        },
    )
    accepted_issues: list[JsonValue] = []
    for issue in raw_issues:
        compact_repair["validation_issues"] = [*accepted_issues, issue]
        if _json_bytes(compact_attempt) > maximum_bytes:
            compact_repair["validation_issues"] = accepted_issues
            break
        accepted_issues.append(issue)
    if not accepted_issues or _json_bytes(compact_attempt) > maximum_bytes:
        raise AgentCandidateValidationError()
    return compact_attempt


def _request_context_budget(
    *,
    request: AgentExecutionRequest,
    maximum_bytes: int,
) -> int:
    empty_context_size = agent_request_envelope_bytes(request.model_copy(update={"context": None}))
    available = maximum_bytes - empty_context_size + _json_bytes(None)
    if available < 1:
        raise AgentContextTooLargeError()
    return available


def agent_request_envelope_bytes(request: AgentExecutionRequest) -> int:
    """Return the exact canonical UTF-8 size sent to an agent adapter."""

    system_sections = [request.system_prompt]
    if request.tool_instruction is not None:
        system_sections.append(request.tool_instruction)
    system_sections.append(AGENT_OUTPUT_CONTRACT_INSTRUCTION)
    envelope = cast(
        JsonValue,
        {
            "system": "\n\n".join(system_sections),
            "input": {
                "instruction": request.instruction_prompt,
                "context": request.context,
                "required_output_schema": request.output_schema,
            },
            "tools": [
                definition.model_dump(mode="json")
                for definition in (
                    ()
                    if request.local_tool_catalog is None
                    else request.local_tool_catalog.definitions
                )
            ],
        },
    )
    return _json_bytes(envelope)


def _json_bytes(value: JsonValue) -> int:
    return len(_json_data(value))


def _json_data(value: JsonValue) -> bytes:
    try:
        return json.dumps(
            value,
            ensure_ascii=False,
            allow_nan=False,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("utf-8")
    except (TypeError, ValueError):
        raise AgentCandidateValidationError() from None


def _output_schema_validator(
    schema: dict[str, JsonValue],
) -> Draft202012Validator:
    try:
        Draft202012Validator.check_schema(schema)
        return Draft202012Validator(schema)
    except SchemaError:
        raise AgentCandidateValidationError() from None


def _output_schema_issues(
    validator: Draft202012Validator,
    candidate: JsonValue,
    *,
    maximum_issues: int,
) -> tuple[AgentValidationIssue, ...]:
    error_iterator = cast(
        Iterable[JsonSchemaValidationError],
        validator.iter_errors(candidate),  # pyright: ignore[reportUnknownMemberType]
    )
    raw_errors = tuple(islice(error_iterator, maximum_issues + 1))
    issues: list[AgentValidationIssue] = []
    for error in raw_errors:
        issues.extend(_output_schema_error_issues(error))
        if len(issues) > maximum_issues:
            break
    issues.sort(key=lambda issue: (_path_sort_key(issue.path), issue.code))
    return tuple(issues[:maximum_issues])


def _output_schema_error_issues(
    error: JsonSchemaValidationError,
) -> tuple[AgentValidationIssue, ...]:
    path = _safe_output_path(tuple(error.absolute_path))
    validator_name = error.validator if isinstance(error.validator, str) else ""
    validator_value: object = error.validator_value
    instance_value: object = error.instance
    if (
        validator_name == "required"
        and isinstance(validator_value, list)
        and isinstance(instance_value, dict)
    ):
        required = cast(list[object], validator_value)
        instance = cast(dict[object, object], instance_value)
        missing = sorted(
            field for field in required if isinstance(field, str) and field not in instance
        )
        return tuple(
            _output_schema_issue(
                code="candidate.output_schema_required",
                path=_safe_output_path((*path, field)),
                message="A required output field is missing.",
            )
            for field in missing
        )
    schema_value: object = error.schema
    if (
        validator_name == "additionalProperties"
        and isinstance(instance_value, dict)
        and isinstance(schema_value, dict)
    ):
        instance = cast(dict[object, object], instance_value)
        schema = cast(dict[object, object], schema_value)
        properties_value = schema.get("properties")
        patterns_value = schema.get("patternProperties")
        allowed: set[str]
        if isinstance(properties_value, dict):
            allowed = {
                field
                for field in cast(dict[object, object], properties_value)
                if isinstance(field, str)
            }
        else:
            allowed = set()
        pattern_names = (
            tuple(
                pattern
                for pattern in cast(dict[object, object], patterns_value)
                if isinstance(pattern, str)
            )
            if isinstance(patterns_value, dict)
            else ()
        )
        try:
            extras = sorted(
                field
                for field in instance
                if isinstance(field, str)
                and field not in allowed
                and not any(re.search(pattern, field) is not None for pattern in pattern_names)
            )
        except re.error:
            raise AgentCandidateValidationError() from None
        if extras:
            return tuple(
                _output_schema_issue(
                    code="candidate.output_schema_additional_property",
                    path=_safe_output_path((*path, field)),
                    message="The output contains a field that the schema does not allow.",
                )
                for field in extras
            )
    diagnostics: dict[str, tuple[str, str]] = {
        "type": (
            "candidate.output_schema_type",
            "The output field has the wrong JSON type.",
        ),
        "enum": (
            "candidate.output_schema_enum",
            "The output field is not one of the allowed values.",
        ),
        "const": (
            "candidate.output_schema_const",
            "The output field does not match the required constant.",
        ),
        "pattern": (
            "candidate.output_schema_pattern",
            "The output field does not match the required pattern.",
        ),
        "minLength": (
            "candidate.output_schema_string_bound",
            "The output string is shorter than the allowed minimum.",
        ),
        "maxLength": (
            "candidate.output_schema_string_bound",
            "The output string exceeds the allowed maximum length.",
        ),
        "minItems": (
            "candidate.output_schema_array_bound",
            "The output array contains too few items.",
        ),
        "maxItems": (
            "candidate.output_schema_array_bound",
            "The output array contains too many items.",
        ),
        "minimum": (
            "candidate.output_schema_number_bound",
            "The output number is below the allowed minimum.",
        ),
        "maximum": (
            "candidate.output_schema_number_bound",
            "The output number exceeds the allowed maximum.",
        ),
        "exclusiveMinimum": (
            "candidate.output_schema_number_bound",
            "The output number is not above the exclusive minimum.",
        ),
        "exclusiveMaximum": (
            "candidate.output_schema_number_bound",
            "The output number is not below the exclusive maximum.",
        ),
        "anyOf": (
            "candidate.output_schema_shape",
            "The output field does not match an allowed schema shape.",
        ),
        "oneOf": (
            "candidate.output_schema_shape",
            "The output field does not match exactly one allowed schema shape.",
        ),
    }
    code, message = diagnostics.get(
        validator_name,
        (
            "candidate.output_schema_invalid",
            "The output field does not match the required schema.",
        ),
    )
    return (_output_schema_issue(code=code, path=path, message=message),)


def _output_schema_issue(
    *,
    code: str,
    path: tuple[str | int, ...],
    message: str,
) -> AgentValidationIssue:
    return AgentValidationIssue(code=code, path=path, message=message)


def _safe_output_path(path: tuple[object, ...]) -> tuple[str | int, ...]:
    if len(path) > 20:
        raise AgentCandidateValidationError()
    safe: list[str | int] = []
    for item in path:
        if isinstance(item, bool):
            raise AgentCandidateValidationError()
        if isinstance(item, int):
            if item < 0:
                raise AgentCandidateValidationError()
            safe.append(item)
            continue
        if not isinstance(item, str) or not item or len(item) > 100 or "\x00" in item:
            raise AgentCandidateValidationError()
        safe.append(item)
    return tuple(safe)


def _path_sort_key(path: tuple[str | int, ...]) -> tuple[str, ...]:
    return tuple(f"{type(item).__name__}:{item}" for item in path)


def load_default_agent_context_policy() -> AgentContextPolicy:
    resource = files("gds_workbench_api").joinpath("config/agent_execution.json")
    raw = resource.read_bytes()
    if len(raw) > 64 * 1024:
        raise ValueError("agent execution configuration is too large")
    return AgentContextPolicy.model_validate_json(raw, strict=True)
