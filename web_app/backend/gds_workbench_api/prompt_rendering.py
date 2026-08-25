"""Ephemeral allowlisted Prompt rendering for agent stages."""

from __future__ import annotations

import json
import math
import re
from collections.abc import Mapping
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Literal

from gds_etl_workbench.domain.errors import InvalidRequestError
from pydantic import BaseModel, ConfigDict, Field, JsonValue, TypeAdapter

type PromptVariableDataType = Literal[
    "text",
    "integer",
    "number",
    "boolean",
    "json",
]

_PLACEHOLDER = re.compile(r"\{\{\s*([a-z][a-z0-9_]{0,99})\s*\}\}")
_MAX_COMPONENT_BYTES = 1_000_000
_JSON_VALUE_ADAPTER: TypeAdapter[JsonValue] = TypeAdapter(JsonValue)


class PromptVariableDefinition(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    name: str = Field(pattern=r"^[a-z][a-z0-9_]{0,99}$")
    resolver_key: str = Field(
        min_length=1,
        max_length=200,
        pattern=r"^[a-z][a-z0-9_.-]{0,199}$",
    )
    data_type: PromptVariableDataType
    is_required: bool


class PromptComponentTemplates(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    system: str = Field(min_length=1, max_length=_MAX_COMPONENT_BYTES, repr=False)
    instruction: str = Field(min_length=1, max_length=_MAX_COMPONENT_BYTES, repr=False)
    tool_instruction: str | None = Field(
        default=None,
        max_length=_MAX_COMPONENT_BYTES,
        repr=False,
    )


@dataclass(frozen=True, slots=True)
class RenderedPrompt:
    system: str = field(repr=False)
    instruction: str = field(repr=False)
    tool_instruction: str | None = field(repr=False)
    warning_codes: tuple[str, ...]
    unknown_placeholders: tuple[str, ...]


def render_prompt(
    *,
    templates: PromptComponentTemplates,
    variables: tuple[PromptVariableDefinition, ...],
    resolver_values: Mapping[str, object],
) -> RenderedPrompt:
    """Resolve registered variables without persisting or exposing rendered content."""
    by_name: dict[str, PromptVariableDefinition] = {}
    rendered_values: dict[str, str] = {}
    unresolved_optional: set[str] = set()
    for variable in variables:
        if variable.name in by_name:
            raise InvalidRequestError("Prompt variable definitions are invalid.")
        by_name[variable.name] = variable
        if variable.resolver_key not in resolver_values:
            if variable.is_required:
                raise InvalidRequestError("A required Prompt variable is unavailable.")
            unresolved_optional.add(variable.name)
            continue
        rendered_values[variable.name] = _render_value(
            variable.data_type,
            resolver_values[variable.resolver_key],
        )

    unknown: list[str] = []
    optional_used = False

    def replace(match: re.Match[str]) -> str:
        nonlocal optional_used
        name = match.group(1)
        if name in rendered_values:
            return rendered_values[name]
        if name in unresolved_optional:
            optional_used = True
            return match.group(0)
        if name not in unknown:
            unknown.append(name)
        return match.group(0)

    rendered_components = tuple(
        None if component is None else _bounded_component(_PLACEHOLDER.sub(replace, component))
        for component in (
            templates.system,
            templates.instruction,
            templates.tool_instruction,
        )
    )
    warnings: list[str] = []
    if unknown:
        warnings.append("unknown_prompt_placeholder")
    if optional_used:
        warnings.append("unresolved_optional_prompt_variable")
    return RenderedPrompt(
        system=rendered_components[0] or "",
        instruction=rendered_components[1] or "",
        tool_instruction=rendered_components[2],
        warning_codes=tuple(warnings),
        unknown_placeholders=tuple(unknown),
    )


def _render_value(data_type: PromptVariableDataType, value: object) -> str:
    if data_type == "text":
        if not isinstance(value, str):
            raise InvalidRequestError("A Prompt variable has an invalid resolved type.")
        rendered = value
    elif data_type == "integer":
        if not isinstance(value, int) or isinstance(value, bool):
            raise InvalidRequestError("A Prompt variable has an invalid resolved type.")
        rendered = str(value)
    elif data_type == "number":
        if (
            not isinstance(value, (int, float, Decimal))
            or isinstance(value, bool)
            or (isinstance(value, float) and not math.isfinite(value))
            or (isinstance(value, Decimal) and not value.is_finite())
        ):
            raise InvalidRequestError("A Prompt variable has an invalid resolved type.")
        rendered = str(value)
    elif data_type == "boolean":
        if not isinstance(value, bool):
            raise InvalidRequestError("A Prompt variable has an invalid resolved type.")
        rendered = "true" if value else "false"
    else:
        try:
            json_value = _JSON_VALUE_ADAPTER.validate_python(value, strict=True)
        except ValueError:
            raise InvalidRequestError("A Prompt variable has an invalid resolved type.") from None
        rendered = json.dumps(
            json_value,
            ensure_ascii=False,
            allow_nan=False,
            separators=(",", ":"),
            sort_keys=True,
        )
    return _bounded_component(rendered)


def _bounded_component(value: str) -> str:
    if len(value.encode("utf-8")) > _MAX_COMPONENT_BYTES:
        raise InvalidRequestError("Rendered Prompt content exceeds the supported size.")
    return value
