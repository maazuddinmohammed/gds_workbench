"""Data-only Jinja rendering for workflow-local Prompt variables."""

from __future__ import annotations

import json
import math
from collections.abc import Mapping
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any, Literal, cast

from gds_etl_workbench.domain.errors import InvalidRequestError
from jinja2 import StrictUndefined, TemplateError, meta, nodes
from jinja2.runtime import LoopContext, Undefined
from jinja2.sandbox import ImmutableSandboxedEnvironment
from pydantic import BaseModel, ConfigDict, Field, JsonValue, TypeAdapter

type PromptVariableDataType = Literal["text", "integer", "number", "boolean", "json"]
_JSON_VALUE_ADAPTER: TypeAdapter[JsonValue] = TypeAdapter(JsonValue)
_ALLOWED_NODES = frozenset(
    {
        "Template",
        "Output",
        "TemplateData",
        "Name",
        "Const",
        "Getattr",
        "Getitem",
        "Slice",
        "List",
        "Tuple",
        "Dict",
        "Pair",
        "If",
        "For",
        "Compare",
        "Operand",
        "And",
        "Or",
        "Not",
        "CondExpr",
        "Filter",
        "Test",
        "Keyword",
    }
)
_ALLOWED_FILTERS = frozenset(
    {
        "map",
        "selectattr",
        "rejectattr",
        "select",
        "reject",
        "list",
        "length",
        "join",
        "default",
        "tojson",
        "sort",
        "unique",
        "first",
        "last",
    }
)
_ALLOWED_TESTS = frozenset(
    {
        "defined",
        "undefined",
        "none",
        "boolean",
        "true",
        "false",
        "string",
        "number",
        "mapping",
        "sequence",
        "eq",
        "equalto",
        "ne",
        "in",
    }
)


class PromptVariableDefinition(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)
    name: str = Field(pattern=r"^[a-z][a-z0-9_]{0,99}$")
    resolver_key: str = Field(min_length=1, max_length=200, pattern=r"^[a-z][a-z0-9_.-]{0,199}$")
    data_type: PromptVariableDataType
    is_required: bool


class PromptComponentTemplates(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)
    system: str = Field(min_length=1, repr=False)
    instruction: str = Field(min_length=1, repr=False)
    tool_instruction: str | None = Field(default=None, repr=False)


@dataclass(frozen=True, slots=True)
class RenderedPrompt:
    system: str = field(repr=False)
    instruction: str = field(repr=False)
    tool_instruction: str | None = field(repr=False)
    warning_codes: tuple[str, ...] = ()
    unknown_placeholders: tuple[str, ...] = ()


def _finalize(value: object) -> str:
    if isinstance(value, Undefined):
        raise InvalidRequestError("A Prompt variable or field is unavailable.")
    if isinstance(value, (str, Decimal)):
        return str(value)
    try:
        return json.dumps(
            value, ensure_ascii=False, allow_nan=False, separators=(",", ":"), sort_keys=True
        )
    except ValueError, TypeError:
        raise InvalidRequestError("A Prompt expression has an invalid value.") from None


class _DataEnvironment(ImmutableSandboxedEnvironment):
    """Dictionary keys only: no Python attribute or callable access."""

    def getattr(self, obj: Any, attribute: str) -> Any:
        if isinstance(obj, dict):
            return self.getitem(obj, attribute)
        if isinstance(obj, LoopContext) and attribute in {
            "index",
            "index0",
            "first",
            "last",
            "length",
        }:
            return getattr(obj, attribute)
        return self.undefined(name=attribute)

    def getitem(self, obj: Any, argument: Any) -> Any:
        if isinstance(argument, str) and argument.startswith("_"):
            return self.undefined(name=argument)
        if isinstance(obj, dict) and isinstance(argument, str):
            return cast(Any, obj)[argument] if argument in obj else self.undefined(name=argument)
        if isinstance(obj, (list, tuple, str)) and isinstance(argument, (int, slice)):
            try:
                return cast(Any, obj)[argument]
            except IndexError, TypeError, ValueError:
                pass
        return self.undefined(name="field")

    def is_safe_callable(self, obj: Any) -> bool:
        return False


def render_prompt(
    *,
    templates: PromptComponentTemplates,
    variables: tuple[PromptVariableDefinition, ...],
    resolver_values: Mapping[str, object],
) -> RenderedPrompt:
    """Render once; unknown names/fields fail before a model request. Missing known data is null."""
    by_name = {variable.name: variable for variable in variables}
    if len(by_name) != len(variables):
        raise InvalidRequestError("Prompt variable definitions are invalid.")
    env = _DataEnvironment(undefined=StrictUndefined, autoescape=False, finalize=_finalize)
    env.globals.clear()
    env.filters = {key: val for key, val in env.filters.items() if key in _ALLOWED_FILTERS}
    env.tests = {key: val for key, val in env.tests.items() if key in _ALLOWED_TESTS}
    # tojson emits compact JSON data, not HTML-escaped text; finalization must not quote it again.
    env.filters.update(tojson=_finalize)
    output: list[str | None] = []
    for component in (templates.system, templates.instruction, templates.tool_instruction):
        if component is None:
            output.append(None)
            continue
        try:
            tree = env.parse(component)
            for node in tree.find_all(nodes.Node):
                if type(node).__name__ not in _ALLOWED_NODES:
                    raise InvalidRequestError("The Prompt uses unsupported template syntax.")
                if isinstance(node, nodes.For) and node.recursive:
                    raise InvalidRequestError("Recursive Prompt loops are not supported.")
                if isinstance(node, (nodes.Name, nodes.Getattr)) and (
                    node.name if isinstance(node, nodes.Name) else node.attr
                ).startswith("_"):
                    raise InvalidRequestError("The Prompt uses an unsupported field.")
                if isinstance(node, nodes.Filter) and node.name not in _ALLOWED_FILTERS:
                    raise InvalidRequestError("The Prompt uses an unsupported filter.")
                if isinstance(node, nodes.Test) and node.name not in _ALLOWED_TESTS:
                    raise InvalidRequestError("The Prompt uses an unsupported test.")
            referenced = meta.find_undeclared_variables(tree)
            if referenced - by_name.keys():
                raise InvalidRequestError("The Prompt references an unknown variable.")
            values: dict[str, object] = {}
            for name in referenced:
                variable = by_name[name]
                value = resolver_values.get(variable.resolver_key)
                if value is not None:
                    _validate_value(variable.data_type, value)
                values[name] = value
            compiled = env.compile(tree)
            template = env.template_class.from_code(env, compiled, {}, None)
            output.append(template.render(values))
        except InvalidRequestError:
            raise
        except TemplateError, TypeError, ValueError, RecursionError, OverflowError:
            raise InvalidRequestError(
                "The Prompt contains invalid syntax, fields, or expressions."
            ) from None
    return RenderedPrompt(
        system=output[0] or "", instruction=output[1] or "", tool_instruction=output[2]
    )


def _validate_value(data_type: PromptVariableDataType, value: object) -> None:
    valid = True
    if data_type == "text":
        valid = isinstance(value, str)
    elif data_type == "integer":
        valid = isinstance(value, int) and not isinstance(value, bool)
    elif data_type == "number":
        valid = isinstance(value, (int, float, Decimal)) and not isinstance(value, bool)
        if isinstance(value, (float, Decimal)):
            valid = math.isfinite(value)
    elif data_type == "boolean":
        valid = isinstance(value, bool)
    else:
        try:
            _JSON_VALUE_ADAPTER.validate_python(value, strict=True)
        except ValueError:
            valid = False
    if not valid:
        raise InvalidRequestError("A Prompt variable has an invalid resolved type.")
