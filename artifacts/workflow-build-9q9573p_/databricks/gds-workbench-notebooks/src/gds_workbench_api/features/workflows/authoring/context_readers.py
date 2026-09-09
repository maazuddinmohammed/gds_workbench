"""Optional typed readers over immutable workflow-local prompt values; no I/O."""

from __future__ import annotations

import json
from collections.abc import Mapping
from copy import deepcopy
from hashlib import sha256
from secrets import token_hex
from typing import Any, NoReturn, cast

from jsonschema import Draft202012Validator
from pydantic import JsonValue

from .agent_execution import (
    AgentContextToolRequestError,
    AgentContextToolResultTooLargeError,
    LocalAgentToolDefinition,
)
from .context_contracts import workflow_input_contracts
from .context_inputs import OBJECT_FIELDS, model_key_fields, natural_key

# (variable, optional selector, exact selector identity fields).
type ReaderSpecs = dict[str, tuple[str, str | None, tuple[str, ...]]]


def workflow_reader_specs(workflow: str) -> ReaderSpecs:
    specs: ReaderSpecs = {
        "get_source_context": ("source_context", None, ()),
        "get_gds_context": ("gds_context", None, ()),
        "get_objects": ("object_context", "source_connection_key", OBJECT_FIELDS[:3]),
        "get_object_details": ("object_attribute_context", "object_keys", OBJECT_FIELDS),
        "get_object_relationships": ("object_relationship_context", "object_keys", OBJECT_FIELDS),
        "get_modeling_assertions": (
            "modeling_assertions",
            "assertion_keys",
            ("modeling_assertion_record_key",),
        ),
    }
    if workflow == "dimensional":
        specs.pop("get_source_context")
        specs.pop("get_object_relationships")
        specs["get_objects"] = ("object_context", "object_keys", OBJECT_FIELDS)
        specs["get_logical_bindings"] = ("logical_bindings", "object_keys", OBJECT_FIELDS)
    if workflow in {"conceptual", "logical"}:
        for kind in ("object", "relationship"):
            specs[f"list_conceptual_{kind}s"] = (
                f"conceptual_{kind}_list",
                "object_keys",
                OBJECT_FIELDS,
            )
            specs[f"get_conceptual_{kind}s"] = (
                f"conceptual_{kind}s",
                "conceptual_object_names" if kind == "object" else "relationship_keys",
                model_key_fields("conceptual", kind),
            )
    for family in (
        ("logical",)
        if workflow == "logical"
        else ("logical", "dimensional")
        if workflow == "dimensional"
        else ()
    ):
        for kind in ("submodel", "entity", "attribute", "relationship"):
            plural = "entities" if kind == "entity" else kind + "s"
            selector = (
                None
                if kind == "submodel"
                else "object_keys"
                if kind == "entity"
                else f"{family}_entity_names"
            )
            fields = OBJECT_FIELDS if kind == "entity" else (f"{family}_entity_name",)
            specs[f"list_{family}_{plural}"] = (f"{family}_{kind}_list", selector, fields)
            get_selector = (
                f"{family}_{kind}_names"
                if kind in {"submodel", "entity"}
                else "attribute_keys"
                if kind == "attribute"
                else "relationship_keys"
            )
            specs[f"get_{family}_{plural}"] = (
                f"{family}_{plural}",
                get_selector,
                model_key_fields(family, kind),
            )
    return specs


def reader_definitions(
    workflow: str, specs: ReaderSpecs | None = None
) -> tuple[LocalAgentToolDefinition, ...]:
    definitions: list[LocalAgentToolDefinition] = []
    contracts: dict[str, dict[str, Any]] = workflow_input_contracts(workflow)
    if workflow in {"mapping", "code_generation", "validation"}:
        from .downstream_contracts import CONTRACTS

        contracts = {
            name: {
                "schema": spec["value_schema"],
                "description": spec["description"],
                "example": spec["example"],
            }
            for name, spec in CONTRACTS[workflow].items()
        }
    for name, (variable, selector, fields) in (specs or workflow_reader_specs(workflow)).items():
        properties: dict[str, Any] = {"cursor": {"type": ["string", "null"], "minLength": 1}}
        if selector:
            key_schema: dict[str, Any] = {
                "type": "object",
                "properties": {
                    field: {"type": ["string", "null"]}
                    if field.endswith("role_name")
                    else {"type": "string", "minLength": 1, "pattern": r"\S"}
                    for field in fields
                },
                "required": list(fields),
                "additionalProperties": False,
            }
            if selector.endswith("_names") or selector == "assertion_keys":
                key_schema = {"type": "string", "minLength": 1, "pattern": r"\S"}
            properties[selector] = (
                {"anyOf": [key_schema, {"type": "null"}]}
                if selector == "source_connection_key"
                else {"type": "array", "items": key_schema}
            )
        description = (
            f"Read frozen {variable}. Omitted or empty selection returns all eligible records, "
            "paged. Continue with cursor alone; copy complete natural keys from prior results. "
            "Unknown keys fail; no database queries or new measurements."
        )
        if name == "get_objects" and workflow != "dimensional":
            description = (
                "Return scoped Objects, optionally narrowed by the full Source Connection key "
                "from get_source_context. Bronze follows registered ingestion links and retains "
                "actual GDS Object keys. Omitted/null selects all. Continue with cursor alone."
            )
        if (
            name.startswith("list_conceptual_")
            or name.endswith("_entities")
            and name.startswith("list_")
        ):
            description += (
                " Silver filters match approved Logical bindings."
                if workflow == "dimensional" and name == "list_logical_entities"
                else " Physical filters match own direct supports/sources only."
            )
        contract = contracts.get(variable, {})
        schema: dict[str, Any] = contract.get("schema", {})
        item_schema: Any = schema.get("items")
        if schema.get("type") == "object":
            item_schema = {name: value for name, value in schema.items() if name != "$defs"}
        if item_schema is None:
            item_schema = next(
                (
                    option["items"]
                    for option in schema.get("anyOf", [])
                    if option.get("type") == "array"
                ),
                cast(dict[str, Any], {}),
            )
        result_schema: dict[str, Any] = {
            "type": "object",
            "additionalProperties": False,
            "properties": {
                "items": {"type": "array", "items": item_schema},
                "next_cursor": {"type": ["string", "null"], "minLength": 1},
                "is_complete": {"type": "boolean"},
                "incomplete_object_key": {
                    "anyOf": [
                        {"type": "null"},
                        {
                            "type": "object",
                            "properties": {
                                f: {"type": "string", "minLength": 1} for f in OBJECT_FIELDS
                            },
                            "required": list(OBJECT_FIELDS),
                            "additionalProperties": False,
                        },
                    ]
                },
            },
            "required": ["items", "next_cursor", "is_complete", "incomplete_object_key"],
            "$defs": schema.get("$defs", {}),
        }
        if variable not in {"object_attribute_context", "object_relationship_context"}:
            result_schema["properties"]["incomplete_object_key"] = {"type": "null"}
        result_schema["allOf"] = [
            {
                "if": {"properties": {"is_complete": {"const": True}}},
                "then": {
                    "properties": {
                        "next_cursor": {"type": "null"},
                        "incomplete_object_key": {"type": "null"},
                    }
                },
                "else": {
                    "properties": {
                        "next_cursor": {"type": "string", "minLength": 1},
                        "items": {"minItems": 1},
                    }
                },
            }
        ]
        definitions.append(
            LocalAgentToolDefinition(
                name=name,
                description=description,
                input_schema={
                    "type": "object",
                    "properties": properties,
                    "additionalProperties": False,
                },
                result_schema=result_schema,
                example={
                    "arguments": {},
                    "result": {
                        "items": [],
                        "next_cursor": None,
                        "is_complete": True,
                        "incomplete_object_key": None,
                    },
                },
                default_behavior="No selection or empty selectors return all eligible records, "
                "paged. Continue with the returned cursor alone.",
            )
        )
    return tuple(definitions)


class FrozenContextReaders:
    """One frozen catalog; cursors bind the run, tool, selection and record position."""

    def __init__(
        self,
        *,
        workflow: str,
        values: Mapping[str, Any],
        max_result_bytes: int,
        max_page_records: int,
        max_cumulative_result_bytes: int,
        readers: ReaderSpecs | None = None,
    ) -> None:
        self.workflow = workflow
        self._values = deepcopy(dict(values))
        self._specs = readers if readers is not None else workflow_reader_specs(workflow)
        self.definitions = reader_definitions(workflow, self._specs)
        self._schemas: dict[str, Any] = {
            d.name: Draft202012Validator(d.input_schema) for d in self.definitions
        }
        self._max_result_bytes = max_result_bytes
        self._max_page_records = max_page_records
        self.max_cumulative_result_bytes = max_cumulative_result_bytes
        self._nonce = token_hex(16)
        self._cursors: dict[str, tuple[str, Any, int, int]] = {}

    @property
    def prompt_values(self) -> dict[str, Any]:
        return deepcopy(self._values)

    def _invalid(self) -> NoReturn:
        raise AgentContextToolRequestError()

    def invoke(self, tool_name: str, arguments: Mapping[str, JsonValue]) -> dict[str, Any]:
        if tool_name not in self._specs or not self._schemas[tool_name].is_valid(dict(arguments)):
            self._invalid()
        variable, selector, _ = self._specs[tool_name]
        selection = arguments.get(selector) if selector else None
        cursor = arguments.get("cursor")
        offset, child = 0, 0
        if cursor is not None:
            if selection not in (None, []):
                self._invalid()
            if not isinstance(cursor, str) or cursor not in self._cursors:
                self._invalid()
            saved_tool, selection, offset, child = self._cursors[cursor]
            if saved_tool != tool_name:
                self._invalid()
        rows = self._select(tool_name, selection)
        items: list[Any] = []
        incomplete: dict[str, Any] | None = None
        while offset < len(rows) and len(items) < self._max_page_records:
            row = deepcopy(rows[offset])
            if variable in {"object_attribute_context", "object_relationship_context"}:
                columns = (
                    ("attributes",)
                    if variable == "object_attribute_context"
                    else ("incoming_relationships", "outgoing_relationships")
                )
                children = [(column, item) for column in columns for item in row[column]]
                piece = {
                    k: v for k, v in row.items() if k not in (*columns, "selected_attribute_names")
                }
                piece.update({column: [] for column in columns})
                if "selected_attribute_names" in row:
                    piece["selected_attribute_names"] = []
                accepted = child
                # Empty groups still represent known empty evidence.
                for index in range(child, len(children)):
                    column, value = children[index]
                    probe = deepcopy(piece)
                    probe[column].append(value)
                    if (
                        column == "attributes"
                        and value["attribute_name"] in row["selected_attribute_names"]
                    ):
                        probe["selected_attribute_names"].append(value["attribute_name"])
                    marker = (
                        {f: row[f] for f in OBJECT_FIELDS} if index + 1 < len(children) else None
                    )
                    if not self._fits([*items, probe], "x" * 64, marker):
                        break
                    piece, accepted = probe, index + 1
                if accepted == child and children:
                    if items:
                        break
                    raise AgentContextToolResultTooLargeError()
                if not self._fits([*items, piece], "x" * 64, None):
                    if items:
                        break
                    raise AgentContextToolResultTooLargeError()
                items.append(piece)
                if accepted < len(children):
                    child = accepted
                    incomplete = {f: row[f] for f in OBJECT_FIELDS}
                    break
                offset, child = offset + 1, 0
            else:
                if not self._fits(
                    [*items, row], "x" * 64 if offset + 1 < len(rows) else None, None
                ):
                    if items:
                        break
                    raise AgentContextToolResultTooLargeError()
                items.append(row)
                offset += 1
        next_cursor = None
        if offset < len(rows):
            state = (tool_name, selection, offset, child)
            next_cursor = sha256(
                (
                    self._nonce
                    + json.dumps(state, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
                ).encode()
            ).hexdigest()
            self._cursors[next_cursor] = state
        result = self._page(items, next_cursor, incomplete)
        if not self._fits(items, next_cursor, incomplete):
            raise AgentContextToolResultTooLargeError()
        return result

    def _page(
        self, items: list[Any], cursor: str | None, incomplete: dict[str, Any] | None
    ) -> dict[str, Any]:
        return {
            "items": items,
            "next_cursor": cursor,
            "is_complete": cursor is None,
            "incomplete_object_key": incomplete,
        }

    def _fits(
        self, items: list[Any], cursor: str | None, incomplete: dict[str, Any] | None
    ) -> bool:
        return (
            len(
                json.dumps(
                    self._page(items, cursor, incomplete),
                    ensure_ascii=False,
                    allow_nan=False,
                    separators=(",", ":"),
                ).encode()
            )
            <= self._max_result_bytes
        )

    def _select(self, tool: str, selection: Any) -> list[dict[str, Any]]:
        variable, selector, fields = self._specs[tool]
        raw_rows = self._values.get(variable)
        if not isinstance(raw_rows, list):
            self._invalid()
        rows = cast(list[dict[str, Any]], raw_rows)
        if selection in (None, []):
            return rows
        if selector == "source_connection_key":
            wanted = natural_key(selection, fields)
            if wanted not in {natural_key(r, fields) for r in self._values["source_context"]}:
                self._invalid()
            matching = {
                natural_key(link["target"])
                for link in self._values["ingestion_mapping"]
                if natural_key(link["source"], fields) == wanted
            }
            return [
                r
                for r in rows
                if (r["zone_code"] == "source" and natural_key(r, fields) == wanted)
                or natural_key(r) in matching
            ]
        wanted = {
            natural_key({fields[0]: r} if isinstance(r, str) else r, fields) for r in selection
        }
        if selector == "object_keys":
            available = {natural_key(r) for r in self._values["object_context"]}
            if not wanted <= available:
                self._invalid()
            if tool.startswith("list_"):
                full_name = variable.removesuffix("_list")
                full_name = (
                    full_name[: -len("entity")] + "entities"
                    if full_name.endswith("entity")
                    else full_name + "s"
                )
                full_rows = self._values[full_name]
                if self.workflow == "dimensional" and tool == "list_logical_entities":
                    names = {
                        r["logical_entity_name"]
                        for r in self._values["logical_bindings"]
                        if natural_key(r) in wanted
                    }
                    return [r for r in rows if r["logical_entity_name"] in names]
                matched: list[dict[str, Any]] = []
                for compact, full in zip(rows, full_rows, strict=True):
                    supports = full.get("supports", full.get("sources", []))
                    if any(
                        isinstance(s.get("source_object"), dict)
                        and natural_key(s["source_object"]) in wanted
                        for s in supports
                    ):
                        matched.append(compact)
                return matched
            return [r for r in rows if natural_key(r) in wanted]
        if tool.startswith("list_") and selector and selector.endswith("_entity_names"):
            family = selector.removesuffix("_entity_names")
            if not wanted <= {natural_key(r, fields) for r in self._values[f"{family}_entities"]}:
                self._invalid()
            if variable.endswith("relationship_list"):
                return [
                    r
                    for r in rows
                    if any(
                        natural_key({fields[0]: r[f"{side}_{family}_entity_name"]}, fields)
                        in wanted
                        for side in ("from", "to")
                    )
                ]
            return [r for r in rows if natural_key(r, fields) in wanted]
        if not wanted <= {natural_key(r, fields) for r in rows}:
            self._invalid()
        return [r for r in rows if natural_key(r, fields) in wanted]
