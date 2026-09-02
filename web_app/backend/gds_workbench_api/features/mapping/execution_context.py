"""Safe provider context and local read-only tools for Mapping authoring."""

from __future__ import annotations

import json
from collections.abc import Mapping
from copy import deepcopy
from dataclasses import dataclass, field
from hashlib import sha256
from typing import cast

from pydantic import BaseModel, ConfigDict, Field, JsonValue

from gds_workbench_api.features.workflows.authoring.agent_execution import (
    AgentContextToolResultTooLargeError,
    LocalAgentToolDefinition,
)
from gds_workbench_api.features.workflows.authoring.context import (
    AgentContextToolRequestError,
    reject_forbidden_provider_json,
)
from gds_workbench_api.features.workflows.authoring.plan import (
    WorkflowExecutionMode,
)
from gds_workbench_api.features.workflows.authoring.repair import (
    AgentContextTooLargeError,
    load_default_agent_context_policy,
)

from .preparation_contracts import MappingPreparation

_CONTEXT_FRAGMENT_KEY = "__gds_context_fragment__"
_CONTEXT_FRAGMENT_ENCODING = "canonical_json"
_PAGE_SIZE_SENTINEL = 9_999_999_999


class MappingExecutionContextLimits(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    max_tool_result_bytes: int = Field(ge=1, le=10 * 1024 * 1024)
    max_tool_transcript_bytes: int = Field(
        default=256 * 1024,
        ge=1,
        le=10 * 1024 * 1024,
    )
    max_tool_catalog_bytes: int = Field(ge=1, le=128 * 1024 * 1024)
    max_tool_page_records: int = Field(ge=1, le=1_000)


def load_default_mapping_execution_context_limits() -> MappingExecutionContextLimits:
    policy = load_default_agent_context_policy()
    return MappingExecutionContextLimits(
        max_tool_result_bytes=2 * 1024 * 1024,
        max_tool_transcript_bytes=max(1, policy.stage_max_context_bytes // 2),
        max_tool_catalog_bytes=128 * 1024 * 1024,
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
        raw_datasets = _mapping_context_datasets(preparation)
        for rows in raw_datasets.values():
            for row in rows:
                reject_forbidden_provider_json(
                    row,
                    allow_identity_keys=True,
                    reject_sensitive_values=True,
                )
        self._limits = limits
        max_turns = preparation.plan.agent_plan.selection.max_turns
        self._max_result_bytes = min(
            limits.max_tool_result_bytes,
            max(1, limits.max_tool_transcript_bytes // max_turns),
        )
        self._total_result_budget_bytes = limits.max_tool_transcript_bytes
        (
            self._datasets,
            dataset_record_counts,
            fragmented_record_counts,
        ) = _bounded_mapping_context_datasets(
            raw_datasets,
            max_result_bytes=self._max_result_bytes,
        )
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
                description=(
                    "Return one byte-bounded page from the immutable Mapping context. "
                    "Continue only from next_offset. A large record is returned as ordered "
                    "canonical-JSON fragments; concatenate json_text by fragment_index, "
                    "verify record_sha256, then parse the complete JSON."
                ),
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
        self._manifest = _mapping_context_manifest(
            preparation,
            self._datasets,
            dataset_record_counts=dataset_record_counts,
            fragmented_record_counts=fragmented_record_counts,
        )
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

    @property
    def max_cumulative_result_bytes(self) -> int:
        """Maximum serialized tool output allowed for one provider execution."""

        return self._total_result_budget_bytes

    @property
    def max_result_bytes(self) -> int:
        return self._max_result_bytes

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
        result_bytes = _json_size(result)
        if result_bytes > self._max_result_bytes:
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
        maximum_end = min(offset + limit, len(rows))
        if offset == maximum_end:
            return _mapping_dataset_page(
                dataset=dataset,
                rows=rows,
                offset=offset,
                end=maximum_end,
            )

        low = offset + 1
        high = maximum_end
        accepted_end: int | None = None
        while low <= high:
            candidate_end = (low + high) // 2
            candidate = _mapping_dataset_page(
                dataset=dataset,
                rows=rows,
                offset=offset,
                end=candidate_end,
            )
            if _json_size(candidate) <= self._max_result_bytes:
                accepted_end = candidate_end
                low = candidate_end + 1
            else:
                high = candidate_end - 1
        if accepted_end is None:
            raise AgentContextToolResultTooLargeError()
        return _mapping_dataset_page(
            dataset=dataset,
            rows=rows,
            offset=offset,
            end=accepted_end,
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
    target = context.target.model_dump(mode="json")
    target["attributes"] = []
    sources: list[JsonValue] = []
    source_attributes: list[JsonValue] = []
    for source in context.sources:
        source_document = source.model_dump(mode="json")
        source_object = cast(dict[str, JsonValue], source_document["object"])
        source_object["attributes"] = []
        sources.append(cast(JsonValue, source_document))
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
    header_documents: list[JsonValue] = []
    for header in context.headers:
        entity = header.modeled_entity
        entity_document = entity.model_dump(mode="json")
        entity_document["attributes"] = []
        modeled_entities.append(cast(JsonValue, entity_document))
        header_document = header.model_dump(mode="json")
        header_document["modeled_entity"] = deepcopy(entity_document)
        header_document["attribute_mappings"] = []
        for attribute in entity.attributes:
            modeled_attributes.append(
                cast(
                    JsonValue,
                    {
                        "model_object_binding_id": header.model_object_binding_id,
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
                        "model_object_binding_id": header.model_object_binding_id,
                        "mapping_object_id": header.mapping_object_id,
                        **child.model_dump(mode="json"),
                    },
                )
            )
        header_documents.append(cast(JsonValue, header_document))
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
        "target": (cast(JsonValue, target),),
        "target_attribute": tuple(
            cast(JsonValue, item.model_dump(mode="json")) for item in context.target.attributes
        ),
        "source": tuple(sources),
        "source_attribute": tuple(source_attributes),
        "header": tuple(header_documents),
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
    *,
    dataset_record_counts: Mapping[str, int],
    fragmented_record_counts: Mapping[str, int],
) -> JsonValue:
    plan = preparation.plan
    manifest: dict[str, JsonValue] = {
        "schema_version": "1.0",
        "workflow": "mapping",
        "workflow_run_id": plan.workflow_run_id,
        "model_id": plan.model_id,
        "model_revision": plan.model_revision,
        "pair": plan.pair.model_dump(mode="json"),
        "datasets": [
            {
                "name": name,
                "record_count": dataset_record_counts[name],
                "retrieval_item_count": len(items),
                "fragmented_record_count": fragmented_record_counts.get(name, 0),
            }
            for name, items in sorted(datasets.items())
        ],
    }
    if fragmented_record_counts:
        manifest["fragment_contract"] = {
            "marker_field": _CONTEXT_FRAGMENT_KEY,
            "encoding": _CONTEXT_FRAGMENT_ENCODING,
            "payload_field": "json_text",
            "reassembly": (
                "Group by record_index and record_sha256; require fragment_index zero through "
                "fragment_count minus one exactly once; concatenate json_text in that order; "
                "verify SHA-256 over UTF-8; then parse canonical JSON."
            ),
        }
    return cast(JsonValue, manifest)


def _bounded_mapping_context_datasets(
    datasets: Mapping[str, tuple[JsonValue, ...]],
    *,
    max_result_bytes: int,
) -> tuple[dict[str, tuple[JsonValue, ...]], dict[str, int], dict[str, int]]:
    bounded: dict[str, tuple[JsonValue, ...]] = {}
    record_counts: dict[str, int] = {}
    fragmented_record_counts: dict[str, int] = {}
    for dataset, rows in datasets.items():
        record_counts[dataset] = len(rows)
        items: list[JsonValue] = []
        fragmented_count = 0
        for record_index, row in enumerate(rows):
            if isinstance(row, dict) and _CONTEXT_FRAGMENT_KEY in row:
                raise AgentContextTooLargeError()
            if _mapping_page_item_fits(
                dataset=dataset,
                item=row,
                max_result_bytes=max_result_bytes,
            ):
                items.append(row)
                continue
            try:
                fragments = _fragment_mapping_context_record(
                    dataset=dataset,
                    record_index=record_index,
                    row=row,
                    max_result_bytes=max_result_bytes,
                )
            except AgentContextTooLargeError:
                # Preserve catalog construction for limits too small to hold even
                # the fragment envelope. Invocation then reports the established
                # tool-result-too-large error without silently dropping the row.
                items.append(row)
                continue
            items.extend(fragments)
            fragmented_count += 1
        bounded[dataset] = tuple(items)
        if fragmented_count:
            fragmented_record_counts[dataset] = fragmented_count
    return bounded, record_counts, fragmented_record_counts


def _mapping_page_item_fits(
    *,
    dataset: str,
    item: JsonValue,
    max_result_bytes: int,
) -> bool:
    return (
        _json_size(
            cast(
                JsonValue,
                {
                    "dataset": dataset,
                    "total_count": _PAGE_SIZE_SENTINEL,
                    "offset": _PAGE_SIZE_SENTINEL,
                    "items": [item],
                    "next_offset": _PAGE_SIZE_SENTINEL,
                },
            )
        )
        <= max_result_bytes
    )


def _fragment_mapping_context_record(
    *,
    dataset: str,
    record_index: int,
    row: JsonValue,
    max_result_bytes: int,
) -> tuple[JsonValue, ...]:
    canonical_text = _json_text(row)
    digest = sha256(canonical_text.encode("utf-8")).hexdigest()
    parts: list[str] = []
    position = 0
    while position < len(canonical_text):
        low = 1
        high = len(canonical_text) - position
        accepted = 0
        while low <= high:
            midpoint = (low + high) // 2
            probe = _mapping_context_fragment(
                record_index=_PAGE_SIZE_SENTINEL,
                fragment_index=_PAGE_SIZE_SENTINEL,
                fragment_count=_PAGE_SIZE_SENTINEL,
                record_sha256=digest,
                json_text=canonical_text[position : position + midpoint],
            )
            if _mapping_page_item_fits(
                dataset=dataset,
                item=probe,
                max_result_bytes=max_result_bytes,
            ):
                accepted = midpoint
                low = midpoint + 1
            else:
                high = midpoint - 1
        if accepted == 0:
            raise AgentContextTooLargeError()
        parts.append(canonical_text[position : position + accepted])
        position += accepted

    fragments = tuple(
        _mapping_context_fragment(
            record_index=record_index,
            fragment_index=fragment_index,
            fragment_count=len(parts),
            record_sha256=digest,
            json_text=part,
        )
        for fragment_index, part in enumerate(parts)
    )
    if not all(
        _mapping_page_item_fits(
            dataset=dataset,
            item=fragment,
            max_result_bytes=max_result_bytes,
        )
        for fragment in fragments
    ):
        raise AgentContextTooLargeError()
    return fragments


def _mapping_context_fragment(
    *,
    record_index: int,
    fragment_index: int,
    fragment_count: int,
    record_sha256: str,
    json_text: str,
) -> JsonValue:
    return cast(
        JsonValue,
        {
            _CONTEXT_FRAGMENT_KEY: {
                "record_index": record_index,
                "fragment_index": fragment_index,
                "fragment_count": fragment_count,
                "record_sha256": record_sha256,
                "encoding": _CONTEXT_FRAGMENT_ENCODING,
            },
            "json_text": json_text,
        },
    )


def _mapping_dataset_page(
    *,
    dataset: str,
    rows: tuple[JsonValue, ...],
    offset: int,
    end: int,
) -> JsonValue:
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


def _json_size(value: JsonValue) -> int:
    return len(_json_text(value).encode("utf-8"))


def _json_text(value: JsonValue) -> str:
    try:
        return json.dumps(
            value,
            ensure_ascii=False,
            allow_nan=False,
            sort_keys=True,
            separators=(",", ":"),
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
