"""Safe provider context and local read-only tools for Mapping authoring."""

from __future__ import annotations

import json
from collections.abc import Mapping
from copy import deepcopy
from dataclasses import dataclass, field
from typing import cast

from pydantic import BaseModel, ConfigDict, Field, JsonValue

from gds_workbench_api.features.workflows.authoring.agent_execution import (
    LocalAgentToolDefinition,
)
from gds_workbench_api.features.workflows.authoring.context import (
    AgentContextToolRequestError,
    AgentContextToolResultTooLargeError,
    reject_forbidden_provider_json,
)
from gds_workbench_api.features.workflows.authoring.plan import (
    WorkflowExecutionMode,
)
from gds_workbench_api.features.workflows.authoring.repair import (
    AgentContextTooLargeError,
)

from .preparation_contracts import MappingPreparation


class MappingExecutionContextLimits(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    max_tool_result_bytes: int = Field(ge=1, le=10 * 1024 * 1024)
    max_tool_catalog_bytes: int = Field(ge=1, le=10 * 1024 * 1024)
    max_tool_page_records: int = Field(ge=1, le=1_000)


def load_default_mapping_execution_context_limits() -> MappingExecutionContextLimits:
    return MappingExecutionContextLimits(
        max_tool_result_bytes=2 * 1024 * 1024,
        max_tool_catalog_bytes=10 * 1024 * 1024,
        max_tool_page_records=200,
    )


class InMemoryMappingContextToolCatalog:
    """Page one immutable prepared Mapping snapshot without database access."""

    def __init__(
        self,
        *,
        preparation: MappingPreparation,
        limits: MappingExecutionContextLimits,
    ) -> None:
        self._datasets = _mapping_context_datasets(preparation)
        for rows in self._datasets.values():
            for row in rows:
                reject_forbidden_provider_json(
                    row,
                    allow_identity_keys=True,
                    reject_sensitive_values=True,
                )
        self._limits = limits
        self._definitions = (
            LocalAgentToolDefinition(
                name="get_mapping_context_manifest",
                description="Return the immutable manifest for this Mapping Run context.",
                input_schema={
                    "type": "object",
                    "properties": {},
                    "additionalProperties": False,
                },
            ),
            LocalAgentToolDefinition(
                name="get_mapping_context_dataset",
                description="Return one bounded page from the immutable Mapping context.",
                input_schema={
                    "type": "object",
                    "properties": {
                        "dataset": {"type": "string"},
                        "offset": {"type": "integer", "minimum": 0},
                        "limit": {
                            "type": "integer",
                            "minimum": 1,
                            "maximum": limits.max_tool_page_records,
                        },
                    },
                    "required": ["dataset", "offset", "limit"],
                    "additionalProperties": False,
                },
            ),
        )
        self._manifest = _mapping_context_manifest(preparation, self._datasets)
        self._serialized_size_bytes = _json_size(
            cast(
                JsonValue,
                {
                    "manifest": self._manifest,
                    "datasets": {name: list(items) for name, items in self._datasets.items()},
                },
            )
        )
        if self._serialized_size_bytes > limits.max_tool_catalog_bytes:
            raise AgentContextTooLargeError()

    @property
    def manifest(self) -> JsonValue:
        return deepcopy(self._manifest)

    @property
    def definitions(self) -> tuple[LocalAgentToolDefinition, ...]:
        return self._definitions

    @property
    def allowed_tool_names(self) -> tuple[str, ...]:
        return tuple(item.name for item in self._definitions)

    @property
    def serialized_size_bytes(self) -> int:
        return self._serialized_size_bytes

    def invoke(
        self,
        tool_name: str,
        arguments: Mapping[str, JsonValue],
    ) -> JsonValue:
        if tool_name == "get_mapping_context_manifest":
            if arguments:
                raise AgentContextToolRequestError()
            result = self.manifest
        elif tool_name == "get_mapping_context_dataset":
            result = self._read_dataset(arguments)
        else:
            raise AgentContextToolRequestError()
        if _json_size(result) > self._limits.max_tool_result_bytes:
            raise AgentContextToolResultTooLargeError()
        return result

    def _read_dataset(self, arguments: Mapping[str, JsonValue]) -> JsonValue:
        if set(arguments) != {"dataset", "offset", "limit"}:
            raise AgentContextToolRequestError()
        dataset = arguments.get("dataset")
        offset = arguments.get("offset")
        limit = arguments.get("limit")
        if (
            not isinstance(dataset, str)
            or dataset not in self._datasets
            or isinstance(offset, bool)
            or not isinstance(offset, int)
            or offset < 0
            or isinstance(limit, bool)
            or not isinstance(limit, int)
            or limit < 1
            or limit > self._limits.max_tool_page_records
        ):
            raise AgentContextToolRequestError()
        rows = self._datasets[dataset]
        if offset > len(rows):
            raise AgentContextToolRequestError()
        end = min(offset + limit, len(rows))
        return cast(
            JsonValue,
            {
                "dataset": dataset,
                "total_count": len(rows),
                "offset": offset,
                "items": deepcopy(list(rows[offset:end])),
                "next_offset": end if end < len(rows) else None,
            },
        )

    def __repr__(self) -> str:
        return f"InMemoryMappingContextToolCatalog(datasets={len(self._datasets)})"


@dataclass(frozen=True, slots=True)
class MappingExecutionContext:
    embedded_context: JsonValue = field(repr=False)
    tool_catalog: InMemoryMappingContextToolCatalog | None = field(
        default=None,
        repr=False,
    )


def build_mapping_execution_context(
    *,
    preparation: MappingPreparation,
    execution_mode: WorkflowExecutionMode,
    limits: MappingExecutionContextLimits | None = None,
) -> MappingExecutionContext:
    """Build complete embedded context or an explicit tool-assisted manifest."""

    selected_limits = limits or load_default_mapping_execution_context_limits()
    if execution_mode == "tool_assisted":
        catalog = InMemoryMappingContextToolCatalog(
            preparation=preparation,
            limits=selected_limits,
        )
        return MappingExecutionContext(
            embedded_context=catalog.manifest,
            tool_catalog=catalog,
        )
    return MappingExecutionContext(
        embedded_context=_mapping_provider_context(preparation),
    )


def _mapping_provider_context(preparation: MappingPreparation) -> JsonValue:
    plan = preparation.plan
    context = preparation.context
    provider_context = cast(
        JsonValue,
        {
            "schema_version": "1.0",
            "workflow": "mapping",
            "run": {
                "workflow_run_id": plan.workflow_run_id,
                "model_id": plan.model_id,
                "model_revision": plan.model_revision,
                "correlation_id": str(plan.correlation_id),
                "modeled_entity_type": plan.modeled_entity_type,
                "pair": plan.pair.model_dump(mode="json"),
                "operation": plan.operation,
                "coverage_mode": plan.coverage_mode,
                "route": plan.route,
                "artifact_type": plan.artifact_type,
                "profile": plan.profile.model_dump(mode="json"),
                "output_template_selections": (
                    plan.output_template_selections.model_dump(mode="json")
                ),
            },
            "source_system": context.source_system.model_dump(mode="json"),
            "source_system_dependency": context.dependency.model_dump(mode="json"),
            "source_system_dependency_graph": (context.dependency_graph.model_dump(mode="json")),
            "target_dependency_graph": (context.target_dependency_graph.model_dump(mode="json")),
            "target": context.target.model_dump(mode="json"),
            "sources": [item.model_dump(mode="json") for item in context.sources],
            "headers": [item.model_dump(mode="json") for item in context.headers],
            "authoring": context.authoring.model_dump(mode="json"),
            "output_templates": context.output_templates.model_dump(mode="json"),
            "readiness": preparation.readiness.model_dump(mode="json"),
        },
    )
    reject_forbidden_provider_json(
        provider_context,
        allow_identity_keys=True,
        reject_sensitive_values=True,
    )
    return provider_context


def _mapping_context_datasets(
    preparation: MappingPreparation,
) -> dict[str, tuple[JsonValue, ...]]:
    context = preparation.context
    sources = tuple(cast(JsonValue, item.model_dump(mode="json")) for item in context.sources)
    source_attributes: list[JsonValue] = []
    for source in context.sources:
        for attribute in source.object.attributes:
            source_attributes.append(
                cast(
                    JsonValue,
                    {
                        "source_mapping_id": source.source_mapping_id,
                        "modeled_entity_id": source.modeled_entity_id,
                        "object_id": source.object.object_id,
                        **attribute.model_dump(mode="json"),
                    },
                )
            )
    modeled_entities: list[JsonValue] = []
    modeled_attributes: list[JsonValue] = []
    existing_attributes: list[JsonValue] = []
    for header in context.headers:
        entity = header.modeled_entity
        modeled_entities.append(cast(JsonValue, entity.model_dump(mode="json")))
        for attribute in entity.attributes:
            modeled_attributes.append(
                cast(
                    JsonValue,
                    {
                        "mapping_object_id": header.mapping_object_id,
                        "modeled_entity_id": entity.entity_id,
                        **attribute.model_dump(mode="json"),
                    },
                )
            )
        for child in header.attribute_mappings:
            existing_attributes.append(
                cast(
                    JsonValue,
                    {
                        "mapping_object_id": header.mapping_object_id,
                        **child.model_dump(mode="json"),
                    },
                )
            )
    return {
        "run": (cast(dict[str, JsonValue], _mapping_provider_context(preparation))["run"],),
        "source_system": (cast(JsonValue, context.source_system.model_dump(mode="json")),),
        "source_system_dependency": (cast(JsonValue, context.dependency.model_dump(mode="json")),),
        "source_dependency_node": tuple(
            cast(JsonValue, item.model_dump(mode="json")) for item in context.dependency_graph.nodes
        ),
        "source_dependency_edge": tuple(
            cast(JsonValue, item.model_dump(mode="json")) for item in context.dependency_graph.edges
        ),
        "target_dependency_node": tuple(
            cast(JsonValue, item.model_dump(mode="json"))
            for item in context.target_dependency_graph.nodes
        ),
        "target_dependency_edge": tuple(
            cast(JsonValue, item.model_dump(mode="json"))
            for item in context.target_dependency_graph.edges
        ),
        "target": (cast(JsonValue, context.target.model_dump(mode="json")),),
        "target_attribute": tuple(
            cast(JsonValue, item.model_dump(mode="json")) for item in context.target.attributes
        ),
        "source": sources,
        "source_attribute": tuple(source_attributes),
        "header": tuple(cast(JsonValue, item.model_dump(mode="json")) for item in context.headers),
        "modeled_entity": tuple(modeled_entities),
        "modeled_attribute": tuple(modeled_attributes),
        "existing_mapping_attribute": tuple(existing_attributes),
        "output_template": tuple(
            cast(JsonValue, item.model_dump(mode="json"))
            for item in context.output_templates.definitions
        ),
        "authoring": (cast(JsonValue, context.authoring.model_dump(mode="json")),),
        "readiness_header": tuple(
            cast(JsonValue, item.model_dump(mode="json")) for item in preparation.readiness.headers
        ),
        "readiness_issue": tuple(
            cast(JsonValue, item.model_dump(mode="json")) for item in preparation.readiness.issues
        ),
    }


def _mapping_context_manifest(
    preparation: MappingPreparation,
    datasets: Mapping[str, tuple[JsonValue, ...]],
) -> JsonValue:
    plan = preparation.plan
    return cast(
        JsonValue,
        {
            "schema_version": "1.0",
            "workflow": "mapping",
            "workflow_run_id": plan.workflow_run_id,
            "model_id": plan.model_id,
            "model_revision": plan.model_revision,
            "pair": plan.pair.model_dump(mode="json"),
            "profile": plan.profile.model_dump(mode="json"),
            "datasets": [
                {"name": name, "record_count": len(items)}
                for name, items in sorted(datasets.items())
            ],
        },
    )


def _json_size(value: JsonValue) -> int:
    try:
        return len(
            json.dumps(
                value,
                ensure_ascii=False,
                allow_nan=False,
                sort_keys=True,
                separators=(",", ":"),
            ).encode("utf-8")
        )
    except (TypeError, ValueError):
        raise AgentContextToolRequestError() from None


__all__ = [
    "InMemoryMappingContextToolCatalog",
    "MappingExecutionContext",
    "MappingExecutionContextLimits",
    "build_mapping_execution_context",
    "load_default_mapping_execution_context_limits",
]
