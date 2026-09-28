"""Frozen prompt tool permissions over the existing in-process evidence catalog."""

from collections.abc import Mapping
from dataclasses import dataclass

from gds_etl_workbench.domain.errors import InvalidRequestError
from pydantic import JsonValue

from .agent_execution import AgentToolName as AgentToolName
from .agent_execution import LocalAgentToolCatalog, LocalAgentToolDefinition


@dataclass(frozen=True, slots=True)
class ConfiguredToolCatalog:
    """Restrict discovery and invocation together; retain the underlying byte budgets."""

    catalog: LocalAgentToolCatalog
    definitions: tuple[LocalAgentToolDefinition, ...]

    @property
    def prompt_values(self) -> Mapping[str, object]:
        return getattr(self.catalog, "prompt_values", {})

    @property
    def max_cumulative_result_bytes(self) -> int | None:
        return self.catalog.max_cumulative_result_bytes

    def invoke(self, tool_name: str, arguments: Mapping[str, JsonValue]) -> JsonValue:
        if tool_name not in {definition.name for definition in self.definitions}:
            raise InvalidRequestError("This tool is not enabled for the frozen Prompt version.")
        return self.catalog.invoke(tool_name, arguments)


def configure_tools(
    catalog: LocalAgentToolCatalog | None,
    selected_names: tuple[AgentToolName, ...] | None,
    *,
    workflow: str,
    execution_mode: str | None,
) -> LocalAgentToolCatalog | None:
    if selected_names is None:
        return catalog
    tool_mode = execution_mode == "tool_assisted" or (
        execution_mode is None and workflow in {"code_generation", "validation"}
    )
    if not tool_mode or catalog is None:
        raise InvalidRequestError("Only tool-assisted Prompts can configure tools.")
    names = set(selected_names)
    available = {definition.name for definition in catalog.definitions}
    if len(names) != len(selected_names) or not names <= available:
        raise InvalidRequestError("The Prompt tool selection does not support this stage.")
    return ConfiguredToolCatalog(
        catalog=catalog,
        definitions=tuple(
            definition for definition in catalog.definitions if definition.name in names
        ),
    )


def registered_tool_definitions(
    workflow: str,
    *,
    max_page_records: int = 200,
) -> tuple[LocalAgentToolDefinition, ...]:
    """Shared discovery contract; each run supplies its enforced paging limit."""
    if workflow in {"analysis", "conceptual", "logical", "dimensional"}:
        from .context_readers import reader_definitions

        return reader_definitions(workflow)
    if workflow in {"mapping", "code_generation", "validation"}:
        from .context_readers import reader_definitions
        from .downstream_inputs import downstream_reader_specs

        return reader_definitions(workflow, downstream_reader_specs(workflow))
    prefix = "mapping" if workflow == "mapping" else "agent"
    return (
        LocalAgentToolDefinition(
            name=f"get_{prefix}_context_manifest",
            description="Return the immutable manifest for this Workflow Run context.",
            input_schema={"type": "object", "properties": {}, "additionalProperties": False},
        ),
        LocalAgentToolDefinition(
            name=f"get_{prefix}_context_dataset",
            description=(
                "Return one byte-bounded page of immutable context. Continue only from "
                "next_offset; a page may contain fewer items than limit. Reassemble large "
                "records by fragment_index, concatenate json_text, verify record_sha256 "
                "when supplied, then parse the complete JSON."
            ),
            input_schema={
                "type": "object",
                "properties": {
                    "dataset": {"type": "string"},
                    "offset": {"type": "integer", "minimum": 0},
                    "limit": {
                        "type": "integer",
                        "minimum": 1,
                        "maximum": max_page_records,
                        "description": "Maximum retrieval items; a byte cap may return fewer.",
                    },
                },
                "required": ["dataset", "offset", "limit"],
                "additionalProperties": False,
            },
        ),
    )
