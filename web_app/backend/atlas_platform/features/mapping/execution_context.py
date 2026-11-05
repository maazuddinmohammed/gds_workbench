"""Safe provider context and local read-only tools for Mapping authoring."""

from __future__ import annotations

import json
import re
from collections.abc import Iterator, Mapping
from copy import deepcopy
from dataclasses import dataclass, field
from functools import lru_cache
from hashlib import sha256
from typing import Any, cast

from atlas_mcp.application.mapping_context import without_internal_fields
from atlas_mcp.domain.snapshots.project import ProjectSnapshot
from pydantic import BaseModel, ConfigDict, Field, JsonValue

from atlas_platform.features.context.context import (
    select_context_records,
    with_cited_context_records,
)
from atlas_platform.features.workflows.authoring.agent_execution import (
    AgentContextToolResultTooLargeError,
    LocalAgentToolDefinition,
)
from atlas_platform.features.workflows.authoring.context import (
    AgentContextToolRequestError,
    reject_forbidden_provider_json,
)
from atlas_platform.features.workflows.authoring.context_inputs import (
    OBJECT_FIELDS,
    natural_key,
)
from atlas_platform.features.workflows.authoring.downstream_inputs import (
    DownstreamContextReaders,
    build_downstream_readers,
    compact_mapping_basis,
    project_downstream_inputs,
)
from atlas_platform.features.workflows.authoring.plan import (
    WorkflowExecutionMode,
)
from atlas_platform.features.workflows.authoring.repair import (
    AgentContextTooLargeError,
    load_default_agent_context_policy,
)
from atlas_platform.features.workflows.authoring.tool_configuration import (
    registered_tool_definitions,
)
from atlas_platform.prompt_rendering import referenced_prompt_names

from .preparation_contracts import MappingModeledEntity, MappingPreparation, MappingSource

# Dimensional links store only their endpoints (child -> parent). Their kind comes from
# the two Entity types; anything else is a plain reference.
_DIMENSIONAL_LINK_KINDS = {
    ("fact", "dimension"): "fact_dimension",
    ("bridge", "dimension"): "bridge_dimension",
    ("dimension", "dimension"): "dimension_outrigger",
}
_CONTEXT_FRAGMENT_KEY = "__gds_context_fragment__"
_CONTEXT_FRAGMENT_ENCODING = "canonical_json"
_PAGE_SIZE_SENTINEL = 9_999_999_999


class MappingExecutionContextLimits(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    max_tool_result_bytes: int | None = Field(default=None, ge=1)
    max_tool_transcript_bytes: int | None = Field(default=None, ge=1)
    max_tool_catalog_bytes: int | None = Field(default=None, ge=1)
    max_tool_page_records: int = Field(ge=1, le=1_000)

    def result_bytes_per_turn(self, max_turns: int) -> int | None:
        return min(
            (
                value
                for value in (
                    self.max_tool_result_bytes,
                    None
                    if self.max_tool_transcript_bytes is None
                    else max(1, self.max_tool_transcript_bytes // max_turns),
                )
                if value is not None
            ),
            default=None,
        )


def load_default_mapping_execution_context_limits() -> MappingExecutionContextLimits:
    policy = load_default_agent_context_policy()
    return MappingExecutionContextLimits(
        max_tool_transcript_bytes=None
        if policy.stage_max_context_bytes is None
        else max(1, policy.stage_max_context_bytes // 2),
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
        self._max_result_bytes = limits.result_bytes_per_turn(max_turns)
        self._total_result_budget_bytes = limits.max_tool_transcript_bytes
        (
            self._datasets,
            dataset_record_counts,
            fragmented_record_counts,
        ) = _bounded_mapping_context_datasets(
            raw_datasets,
            max_result_bytes=self._max_result_bytes,
        )
        self._definitions = registered_tool_definitions(
            "mapping", max_page_records=limits.max_tool_page_records
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
        if (
            limits.max_tool_catalog_bytes is not None
            and self._serialized_size_bytes > limits.max_tool_catalog_bytes
        ):
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
    def max_cumulative_result_bytes(self) -> int | None:
        """Maximum serialized tool output allowed for one provider execution."""

        return self._total_result_budget_bytes

    @property
    def max_result_bytes(self) -> int | None:
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
        if self._max_result_bytes is not None and result_bytes > self._max_result_bytes:
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
            if self._max_result_bytes is None or _json_size(candidate) <= self._max_result_bytes:
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
    tool_catalog: InMemoryMappingContextToolCatalog | DownstreamContextReaders | None = field(
        default=None,
        repr=False,
    )


def build_mapping_execution_context(
    *,
    preparation: MappingPreparation,
    execution_mode: WorkflowExecutionMode,
    limits: MappingExecutionContextLimits | None = None,
) -> MappingExecutionContext:
    """Prepare author-selected natural-key values and optional frozen readers."""

    selected_limits = limits or load_default_mapping_execution_context_limits()
    stage = preparation.plan.agent_plan.stages[0]
    referenced = referenced_prompt_names(stage.templates)
    only_pair_inputs = (
        execution_mode == "one_shot"
        and selected_limits.max_tool_catalog_bytes is None
        and "mapping_basis" in referenced
        and referenced
        <= {
            "mapping_basis",
            "mapping_route",
            "source_system",
            "authoring_policy",
            "object_output_template",
            "attribute_output_template",
        }
    )
    # When the frozen template requests only the pair, the full legacy catalog
    # isn't read. In particular, don't materialize all peer Mapping documents.
    raw = cast(
        dict[str, JsonValue],
        _mapping_provider_context(preparation, include_upstream=not only_pair_inputs),
    )
    # Only the original frozen evidence counts towards the catalog size. The
    # compact projection is derived when its template or reader requests it.
    values = project_downstream_inputs("mapping", raw, include_mapping_basis=False)
    if (
        selected_limits.max_tool_catalog_bytes is not None
        and _json_size(cast(JsonValue, values)) > selected_limits.max_tool_catalog_bytes
    ):
        raise AgentContextTooLargeError()
    pair = _MappingPairBasis(preparation, values)
    if pair.deferred or pair.has_lookups or only_pair_inputs:
        values["mapping_basis"] = pair.cards(pair.focus or set(pair.sources))
    embedded = cast(JsonValue, {"__gds_downstream_inputs__": "mapping", "values": values})
    if execution_mode == "tool_assisted":
        catalog = build_downstream_readers(
            "mapping",
            values,
            max_result_bytes=selected_limits.result_bytes_per_turn(
                preparation.plan.agent_plan.selection.max_turns
            ),
            max_page_records=selected_limits.max_tool_page_records,
            max_cumulative_result_bytes=selected_limits.max_tool_transcript_bytes,
        )
        if pair.deferred or pair.has_lookups:
            # Cursors can request the same selection over many pages. Cache only the last
            # selection so arbitrary combinations cannot grow the retained result set.
            catalog.mapping_pair_pages = lru_cache(maxsize=1)(pair.read)
            # The embedded resolver values are public to the caller. Keep them detached
            # from the frozen rows used to service later source-detail reads.
            embedded = cast(
                JsonValue,
                {
                    "__gds_downstream_inputs__": "mapping",
                    "values": catalog.prompt_values,
                },
            )
            pair.values = {
                key: values[key]
                for key in ("target_metadata", "existing_mapping", "readiness", "mapping_basis")
            }
        return MappingExecutionContext(
            embedded_context=embedded,
            tool_catalog=catalog,
        )
    return MappingExecutionContext(
        embedded_context=embedded,
    )


class _MappingPairBasis:
    """Separate eligible sources from evidence needed to author this frozen pair."""

    def __init__(self, preparation: MappingPreparation, values: dict[str, Any]) -> None:
        self.preparation = preparation
        self.values = values
        priority = {"support": 0, "lookup": 1, "candidate": 2}
        ordered = sorted(
            zip(preparation.context.sources, values["source_evidence"], strict=True),
            key=lambda pair: priority[pair[0].role],
        )
        self.sources = {f"s{i}": pair for i, pair in enumerate(ordered, 1)}
        self.has_lookups = any(source.role == "lookup" for source, _ in self.sources.values())
        self.focus = {ref for ref, (source, _) in self.sources.items() if source.role == "support"}
        self.deferred: set[str] = set()
        self.join_summaries: list[dict[str, Any]] = []
        self.join_details: dict[str, list[dict[str, Any]]] = {}
        if len(self.focus) == len(self.sources):
            return

        support = values["mapping_support"]
        target = preparation.context.target
        layer = preparation.plan.modeled_entity_type.removesuffix("_entity")
        # Stored custom Mapping documents and scoped Context may refer to another
        # eligible source by name, even when its role in the catalog is "candidate".
        header = values["existing_mapping"][0]
        mentions: list[Any] = [
            target.entity_definition,
            target.grain,
            *(a.attribute_definition for a in target.attributes),
            *(s.rationale for s, _ in self.sources.values() if s.role == "support"),
            header["transformation_document"],
            *(attr["transformation_document"] for attr in header["attribute_mappings"]),
        ]
        physical: set[tuple[Any, ...]] = set()
        modeled: set[tuple[str, str, str]] = set()
        for attr in support["attribute_lineage"]:
            for source_link in attr["sources"]:
                if source_link.get("rationale"):
                    mentions.append(source_link["rationale"])
                if source_link["support_source_type"] == "attribute":
                    physical.add(natural_key(source_link["source_attribute"]))
                elif source_link["support_source_type"] == "logical_attribute":
                    key = source_link["source_logical_attribute"]
                    modeled.add(
                        (
                            "logical_entity",
                            key["logical_entity_schema_name"].casefold(),
                            key["logical_entity_name"].casefold(),
                        )
                    )
        for rel in support["modeled_relationships"]:
            if (
                rel[f"from_{layer}_entity_name"].casefold() == target.entity_name.casefold()
                and rel[f"from_{layer}_entity_schema_name"].casefold()
                == target.entity_schema_name.casefold()
            ):
                modeled.add(
                    (
                        target.entity_type,
                        rel[f"to_{layer}_entity_schema_name"].casefold(),
                        rel[f"to_{layer}_entity_name"].casefold(),
                    )
                )
                mentions.append(rel.get(f"{layer}_relationship_basis"))
        # The related dimension can use another Silver input to populate the key
        # this target looks up. Only consider already eligible Silver sources.
        if layer == "dimensional" and preparation.snapshot is not None:
            for entity in preparation.snapshot.dimensional.entities:
                if (
                    entity.dimensional_entity_is_active
                    and (
                        "dimensional_entity",
                        entity.dimensional_entity_schema_name.casefold(),
                        entity.dimensional_entity_name.casefold(),
                    )
                    in modeled
                ):
                    for link in entity.sources:
                        if link.is_active and link.support_source_type == "logical_entity":
                            key = link.source_logical_entity
                            modeled.add(
                                (
                                    "logical_entity",
                                    key.logical_entity_schema_name.casefold(),
                                    key.logical_entity_name.casefold(),
                                )
                            )
        for ref, (source, row) in self.sources.items():
            obj = source.object
            if isinstance(obj, MappingModeledEntity):
                if (
                    obj.entity_type,
                    obj.entity_schema_name.casefold(),
                    obj.entity_name.casefold(),
                ) in modeled:
                    self.focus.add(ref)
            elif natural_key(row["object"]) in physical:
                self.focus.add(ref)
        # Include routed and cited Context for the target and its structural sources.
        # Context cited solely by a different eligible peer stays with that peer.
        mentions.extend(_mapping_support(self.scoped(self.focus))["context_records"])
        text = json.dumps(mentions, ensure_ascii=False).casefold().replace("`", "")
        for ref, (source, _) in self.sources.items():
            if ref in self.focus:
                continue
            obj = source.object
            if isinstance(obj, MappingModeledEntity):
                name, schema = obj.entity_name, obj.entity_schema_name
            else:
                name, schema = obj.object_name, obj.object_schema
            # Qualified SQL resolves the schema. An unqualified or opaque name keeps
            # every eligible namesake as a competing source; never choose by order.
            name_token = re.escape(name.casefold())
            schema_token = re.escape(schema.casefold())
            pattern = rf"(?:(?<![\w.]){name_token}|(?<!\w){schema_token}\.{name_token})(?!\w)"
            if re.search(pattern, text):
                self.focus.add(ref)
        if not any(self.sources[ref][0].role != "lookup" for ref in self.focus):
            # A lookup alone cannot establish the driver. Retain every possible
            # driver for discovery when direct lineage does not identify one.
            self.focus.update(
                ref for ref, (source, _) in self.sources.items() if source.role != "lookup"
            )
        if self.focus:
            self.deferred = self.sources.keys() - self.focus
        if not self.deferred:
            return

        # Keep the join when just one endpoint is in focus. One-hop adjacency is
        # evidence about two columns, not a reason to import another whole table.
        physical_refs = {
            natural_key(row["object"]): ref
            for ref, (source, row) in self.sources.items()
            if not isinstance(source.object, MappingModeledEntity)
        }
        for row in support["source_relationships"]:
            first, second = (
                physical_refs[natural_key({k: row[f"{side}_{k}"] for k in OBJECT_FIELDS})]
                for side in ("from", "to")
            )
            if (first in self.focus) == (second in self.focus):
                continue
            summary = {
                "from_source_ref": first,
                "to_source_ref": second,
                **{
                    k: row[k]
                    for k in (
                        "from_attribute_name",
                        "to_attribute_name",
                        "relationship_kind",
                        "inferred_cardinality",
                        "validation_result",
                        "validation_source_missing_target_count",
                        "validation_duplicate_target_key_count",
                    )
                },
            }
            self.join_summaries.append({"kind": "analysis_relationship", "record": summary})
            deferred = first if first in self.deferred else second
            self.join_details.setdefault(deferred, []).append(
                {"kind": "analysis_relationship", "record": row}
            )
        logical_refs = {
            (obj.entity_schema_name.casefold(), obj.entity_name.casefold()): ref
            for ref, (source, _) in self.sources.items()
            if isinstance(obj := source.object, MappingModeledEntity)
            and obj.entity_type == "logical_entity"
        }
        snapshot = preparation.snapshot
        if logical_refs and snapshot is not None:
            attributes = {
                (
                    a.logical_entity_schema_name.casefold(),
                    a.logical_entity_name.casefold(),
                    a.logical_attribute_name.casefold(),
                )
                for a in snapshot.logical.attributes
                if a.logical_attribute_is_active
                and (a.logical_entity_schema_name.casefold(), a.logical_entity_name.casefold())
                in logical_refs
            }
            for child, parent, row in _eligible_logical_relationships(snapshot, attributes):
                first, second = logical_refs[child[:2]], logical_refs[parent[:2]]
                if (first in self.focus) == (second in self.focus):
                    continue
                card = {"kind": "source_logical_relationship", "record": row}
                self.join_summaries.append(card)
                deferred = first if first in self.deferred else second
                self.join_details.setdefault(deferred, []).append(card)

    def scoped(self, refs: set[str]) -> MappingPreparation:
        sources: tuple[MappingSource, ...] = tuple(
            source for ref, (source, _) in self.sources.items() if ref in refs
        )
        context = self.preparation.context.model_copy(update={"sources": sources})
        return self.preparation.model_copy(update={"context": context})

    def cards(
        self, refs: set[str], *, include_mapping_details: bool = False
    ) -> list[dict[str, Any]]:
        scoped = self.scoped(refs)
        ordered = [ref for ref in self.sources if ref in refs]
        support = _mapping_support(scoped)
        cards = compact_mapping_basis(
            {
                **self.values,
                "source_evidence": [self.sources[ref][1] for ref in ordered],
                "mapping_support_records": _mapping_support_records(scoped, support),
            },
            source_refs=ordered,
        )
        if not include_mapping_details and self.has_lookups:
            lookups = {
                (
                    source.object.entity_type,
                    source.object.entity_schema_name.casefold(),
                    source.object.entity_name.casefold(),
                ): (ref, source.object)
                for ref, (source, _) in self.sources.items()
                if ref in refs
                and source.role == "lookup"
                and isinstance(source.object, MappingModeledEntity)
            }
            # The core carries only lookup key rules for this branch or a namespace
            # named by its saved evidence. Other Systems and non-key fields remain
            # available by the same source ref; their documents can be arbitrarily wide.
            namespace_evidence = json.dumps(
                [
                    support["modeled_relationships"],
                    support["attribute_lineage"],
                    support["context_records"],
                    self.values["existing_mapping"],
                    self.preparation.context.target.entity_definition,
                    *(a.attribute_definition for a in self.preparation.context.target.attributes),
                ],
                ensure_ascii=False,
            ).casefold()
            deferred_systems: dict[str, set[str]] = {}
            kept: list[dict[str, Any]] = []
            for card in cards:
                row = card["record"]
                if card["kind"] not in {"source_object_mapping", "source_attribute_mapping"}:
                    kept.append(card)
                    continue
                identity = (
                    row["modeled_entity_type"],
                    row["modeled_entity_schema_name"].casefold(),
                    row["modeled_entity_name"].casefold(),
                )
                if identity not in lookups:
                    kept.append(card)
                    continue
                ref, parent = lookups[identity]
                system = row["source_system_code"]
                named_system = system.casefold() == (
                    self.preparation.context.source_system.system_code.casefold()
                ) or re.search(rf"(?<!\w){re.escape(system.casefold())}(?!\w)", namespace_evidence)
                key_fields = {
                    attribute.attribute_name.casefold()
                    for attribute in parent.attributes
                    if attribute.is_natural_key
                    or attribute.is_surrogate_key
                    or attribute.attribute_name.casefold() == "sourcesystemid"
                    or re.search(
                        rf"(?<!\w){re.escape(attribute.attribute_name.casefold())}(?!\w)",
                        namespace_evidence,
                    )
                }
                for relationship in support["modeled_relationships"]:
                    layer = parent.entity_type.removesuffix("_entity")
                    if (
                        relationship[f"to_{layer}_entity_schema_name"].casefold(),
                        relationship[f"to_{layer}_entity_name"].casefold(),
                    ) == identity[1:]:
                        key_fields.add(relationship[f"to_{layer}_attribute_name"].casefold())
                if named_system and (
                    card["kind"] == "source_object_mapping"
                    or row["modeled_attribute_name"].casefold() in key_fields
                ):
                    kept.append(card)
                else:
                    deferred_systems.setdefault(ref, set()).add(system)
            used_templates = {
                card["record"]["output_template_code"].casefold()
                for card in kept
                if card["kind"] in {"source_object_mapping", "source_attribute_mapping"}
                and card["record"].get("output_template_code") is not None
            }
            cards = [
                card
                for card in kept
                if card["kind"] != "source_mapping_template"
                or card["record"]["code"].casefold() in used_templates
            ]
            for card in cards:
                if card["kind"] == "source" and card["record"].get("ref") in deferred_systems:
                    card["record"]["deferred_mapping_systems"] = sorted(
                        deferred_systems[card["record"]["ref"]], key=str.casefold
                    )
        if refs == self.focus:
            cards.extend(self.source_directory(set(self.join_details)))
            cards.extend(self.join_summaries)
        reject_forbidden_provider_json(
            cast(JsonValue, cards), allow_identity_keys=True, reject_sensitive_values=True
        )
        return cards

    def read(self, selection: tuple[str, ...]) -> list[dict[str, Any]]:
        if selection:
            refs = set(selection)
            if not refs <= self.sources.keys():
                raise KeyError("unknown source reference")
            # Include this selection's upstream Mapping, lineage and profiles.
            # Target/field/role instructions were already supplied on the core pages.
            details = [
                card
                for card in self.cards(refs, include_mapping_details=True)
                if card["kind"] not in {"target", "field", "target_relationship"}
            ]
            for ref in dict.fromkeys(selection):
                details.extend(self.join_details.get(ref, ()))
            return details
        return [
            *self.values["mapping_basis"],
            *self.source_directory(self.deferred - self.join_details.keys()),
        ]

    def source_directory(self, refs: set[str]) -> list[dict[str, Any]]:
        cards: list[dict[str, Any]] = []
        for ref, (source, row) in self.sources.items():
            if ref not in refs:
                continue
            obj = row["object"]
            identity = (
                ("entity_type", "entity_schema_name", "entity_name")
                if isinstance(source.object, MappingModeledEntity)
                else OBJECT_FIELDS
            )
            cards.append(
                {
                    "kind": "source",
                    "record": {
                        **{key: obj[key] for key in identity},
                        "ref": ref,
                        "role": source.role,
                        "deferred": True,
                    },
                }
            )
        return cards


def _eligible_logical_relationships(
    snapshot: ProjectSnapshot, attributes: set[tuple[str, str, str]]
) -> Iterator[tuple[tuple[str, str, str], tuple[str, str, str], dict[str, Any]]]:
    for rel in snapshot.logical.relationships:
        first = (
            rel.from_logical_entity_schema_name.casefold(),
            rel.from_logical_entity_name.casefold(),
            rel.from_logical_attribute_name.casefold(),
        )
        second = (
            rel.to_logical_entity_schema_name.casefold(),
            rel.to_logical_entity_name.casefold(),
            rel.to_logical_attribute_name.casefold(),
        )
        if rel.logical_relationship_is_active and first in attributes and second in attributes:
            yield first, second, rel.model_dump(mode="json")


def _mapping_provider_context(
    preparation: MappingPreparation, *, include_upstream: bool = True
) -> JsonValue:
    plan = preparation.plan
    context = preparation.context
    support = _mapping_support(preparation)
    provider_context = cast(
        JsonValue,
        {
            "schema_version": "1.0",
            "workflow": "mapping",
            "run": {
                "workflow_run_id": plan.workflow_run_id,
                "project_id": plan.project_id,
                "project_revision": plan.project_revision,
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
            "mapping_support": support,
            "mapping_support_records": (
                _mapping_support_records(preparation, support) if include_upstream else []
            ),
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


def _mapping_support(preparation: MappingPreparation) -> dict[str, Any]:
    """Only persisted evidence relevant to this Entity and its eligible physical sources."""
    snapshot = preparation.snapshot
    result: dict[str, Any] = {
        "attribute_lineage": [],
        "modeled_relationships": [],
        "source_relationships": [],
        "profiles": [],
        "context_records": [],
    }
    if snapshot is None:
        return result
    layer = "logical" if preparation.plan.route == "logical_to_silver" else "dimensional"
    section = snapshot.logical if layer == "logical" else snapshot.dimensional
    entity_name = preparation.context.headers[0].modeled_entity.entity_name.casefold()
    entity_schema = preparation.context.headers[0].modeled_entity.entity_schema_name.casefold()
    source_keys = {
        natural_key(item.object.model_dump())
        for item in preparation.context.sources
        if not isinstance(item.object, MappingModeledEntity)
    }
    logical_keys = {
        (item.object.entity_schema_name.casefold(), item.object.entity_name.casefold())
        for item in preparation.context.sources
        if isinstance(item.object, MappingModeledEntity)
        and item.object.entity_type == "logical_entity"
    }
    dimensional_keys = {
        (item.object.entity_schema_name.casefold(), item.object.entity_name.casefold())
        for item in preparation.context.sources
        if isinstance(item.object, MappingModeledEntity)
        and item.object.entity_type == "dimensional_entity"
    }
    # Context the target cites as support reaches the prompt whatever its Type.
    cited_context = {
        source.context_record.context_record_id
        for entity in section.entities
        if getattr(entity, f"{layer}_entity_name").casefold() == entity_name
        and getattr(entity, f"{layer}_entity_schema_name").casefold() == entity_schema
        for source in entity.sources
        if source.is_active and source.support_source_type == "context_record"
    }
    # So does Context an upstream Logical Entity cites: its evidence records keep the citation.
    for upstream in (
        *(row for row in snapshot.logical.entities if row.logical_entity_is_active),
        *(row for row in snapshot.logical.attributes if row.logical_attribute_is_active),
    ):
        if (
            upstream.logical_entity_schema_name.casefold(),
            upstream.logical_entity_name.casefold(),
        ) in logical_keys:
            cited_context.update(
                source.context_record.context_record_id
                for source in upstream.sources
                if source.is_active and source.support_source_type == "context_record"
            )
    for upstream in (
        *(row for row in snapshot.dimensional.entities if row.dimensional_entity_is_active),
        *(row for row in snapshot.dimensional.attributes if row.dimensional_attribute_is_active),
    ):
        if (
            upstream.dimensional_entity_schema_name.casefold(),
            upstream.dimensional_entity_name.casefold(),
        ) in dimensional_keys:
            cited_context.update(
                source.context_record.context_record_id
                for source in upstream.sources
                if source.is_active and source.support_source_type == "context_record"
            )
    for attribute in section.attributes:
        if (
            getattr(attribute, f"{layer}_entity_name").casefold() != entity_name
            or getattr(attribute, f"{layer}_entity_schema_name").casefold() != entity_schema
            or not getattr(attribute, f"{layer}_attribute_is_active")
        ):
            continue
        sources: list[dict[str, Any]] = []
        for source in attribute.sources:
            if not source.is_active:
                continue
            if source.support_source_type == "context_record":
                cited_context.add(source.context_record.context_record_id)
            if (
                source.support_source_type == "context_record"
                or (
                    source.support_source_type == "attribute"
                    and natural_key(source.source_attribute.model_dump()) in source_keys
                )
                or (
                    source.support_source_type == "logical_attribute"
                    and (
                        source.source_logical_attribute.logical_entity_schema_name.casefold(),
                        source.source_logical_attribute.logical_entity_name.casefold(),
                    )
                    in logical_keys
                )
            ):
                sources.append(source.model_dump(mode="json", exclude={"is_active", "is_locked"}))
        result["attribute_lineage"].append(
            {
                "modeled_attribute_name": getattr(attribute, f"{layer}_attribute_name"),
                "sources": sources,
                **{
                    name.removeprefix(f"{layer}_attribute_"): value
                    for name, value in attribute.model_dump(mode="json").items()
                    if name.endswith(("_is_primary_key", "_is_natural_key", "_is_surrogate_key"))
                },
            }
        )
    dimensional = layer == "dimensional"
    entity_types = {
        (row.dimensional_entity_schema_name.casefold(), row.dimensional_entity_name.casefold()): (
            row.dimensional_entity_type
        )
        for row in (snapshot.dimensional.entities if dimensional else ())
    }
    nullable_columns = {
        (
            row.dimensional_entity_schema_name.casefold(),
            row.dimensional_entity_name.casefold(),
            row.dimensional_attribute_name.casefold(),
        ): row.dimensional_attribute_is_nullable
        for row in (snapshot.dimensional.attributes if dimensional else ())
    }
    for relationship in section.relationships:
        row = relationship.model_dump(mode="json")
        child = (
            row[f"from_{layer}_entity_schema_name"].casefold(),
            row[f"from_{layer}_entity_name"].casefold(),
        )
        parent = (
            row[f"to_{layer}_entity_schema_name"].casefold(),
            row[f"to_{layer}_entity_name"].casefold(),
        )
        if not row[f"{layer}_relationship_is_active"] or (entity_schema, entity_name) not in {
            child,
            parent,
        }:
            continue
        evidence = {
            key: value
            for key, value in row.items()
            if not key.endswith(("_is_locked", "_is_active"))
        }
        if dimensional:
            # Worked out, never stored: kind from the Entity types, optional from the
            # foreign key's nullability, and always many-to-one.
            evidence["dimensional_relationship_kind"] = _DIMENSIONAL_LINK_KINDS.get(
                (entity_types.get(child, ""), entity_types.get(parent, "")), "reference"
            )
            evidence["dimensional_relationship_cardinality"] = "many_to_one"
            evidence["dimensional_relationship_is_optional"] = nullable_columns.get(
                (*child, row["from_dimensional_attribute_name"].casefold()), True
            )
        result["modeled_relationships"].append(evidence)
    for relationship in snapshot.analysis.relationships:
        row = relationship.model_dump(mode="json")
        if row["analysis_result_status"] == "active" and all(
            natural_key({key: row[f"{side}_{key}"] for key in OBJECT_FIELDS}) in source_keys
            for side in ("from", "to")
        ):
            result["source_relationships"].append(
                {
                    key: value
                    for key, value in row.items()
                    if key
                    not in {
                        "analysis_result_status",
                        "analysis_result_is_locked",
                        "validation_policy_version",
                    }
                }
            )
    for profile in snapshot.profiling.profiles:
        row = profile.model_dump(mode="json")
        if natural_key(row) in source_keys:
            result["profiles"].append(row)
    context_section = snapshot.context.model_dump(mode="json")
    result["context_records"] = with_cited_context_records(
        context_section,
        select_context_records(
            context_section,
            source_scope=[
                {
                    "tenant_code": snapshot.project_tenant_code,
                    "system_code": preparation.context.source_system.system_code,
                },
                *(source.object.model_dump(mode="json") for source in preparation.context.sources),
            ],
            workflow="mapping",
        ),
        cited_context,
    )
    return result


def _mapping_support_records(
    preparation: MappingPreparation, support: dict[str, Any]
) -> list[dict[str, Any]]:
    """Page evidence records independently, keeping upstream lineage out of input eligibility."""
    kinds = {
        "attribute_lineage": "target_attribute_lineage",
        "modeled_relationships": "target_relationship",
        "source_relationships": "analysis_relationship",
        "profiles": "profile",
        "context_records": "context_record",
    }
    records = [
        {"evidence_type": kinds[name], "record": deepcopy(row)}
        for name, rows in support.items()
        for row in rows
    ]
    snapshot = preparation.snapshot
    if snapshot is None:
        return records
    logical_keys = {
        (source.object.entity_schema_name.casefold(), source.object.entity_name.casefold())
        for source in preparation.context.sources
        if isinstance(source.object, MappingModeledEntity)
        and source.object.entity_type == "logical_entity"
    }
    dimensional_keys = {
        (source.object.entity_schema_name.casefold(), source.object.entity_name.casefold())
        for source in preparation.context.sources
        if isinstance(source.object, MappingModeledEntity)
        and source.object.entity_type == "dimensional_entity"
    }
    if not logical_keys and not dimensional_keys:
        return records
    target = preparation.context.target
    layer = target.entity_type.removesuffix("_entity")
    parent_keys = {
        (
            target.entity_type,
            row[f"to_{layer}_entity_schema_name"].casefold(),
            row[f"to_{layer}_entity_name"].casefold(),
        )
        for row in support["modeled_relationships"]
        if row[f"from_{layer}_entity_schema_name"].casefold()
        == target.entity_schema_name.casefold()
        and row[f"from_{layer}_entity_name"].casefold() == target.entity_name.casefold()
    }
    physical = {
        natural_key(source.object.model_dump()): source.object
        for source in (*preparation.context.sources, *preparation.context.upstream_physical_sources)
        if not isinstance(source.object, MappingModeledEntity)
        and source.object.is_active
        and source.object.scope_is_active
        and source.object.tenant_is_active
        and source.object.system_is_active
        and source.object.connection_is_active
    }
    input_keys = {
        natural_key(row.model_dump())
        for row in snapshot.project_input_scope.objects
        if row.is_active
    }
    physical = {key: obj for key, obj in physical.items() if key in input_keys}
    attribute_keys = {
        (*key, attribute.attribute_name.casefold())
        for key, obj in physical.items()
        for attribute in obj.attributes
        if attribute.is_active
    }
    lineage_objects: set[tuple[Any, ...]] = set()
    lineage_attributes: set[tuple[Any, ...]] = set()
    selected_attributes: set[tuple[str, str, str]] = set()
    applicable_context_records = {
        row["context_record_id"].casefold() for row in support["context_records"]
    }
    for entity in snapshot.logical.entities:
        key = (entity.logical_entity_schema_name.casefold(), entity.logical_entity_name.casefold())
        if key not in logical_keys or not entity.logical_entity_is_active:
            continue
        row = entity.model_dump(mode="json")
        row["sources"] = []
        for source in entity.sources:
            if not source.is_active:
                continue
            if source.support_source_type == "object":
                physical_key = natural_key(source.source_object.model_dump())
                if physical_key not in physical:
                    if (
                        "logical_entity",
                        *key,
                    ) not in parent_keys or physical_key not in input_keys:
                        continue
                else:
                    lineage_objects.add(physical_key)
            elif (
                source.context_record.context_record_id.casefold() not in applicable_context_records
            ):
                continue
            cast(list[dict[str, Any]], row["sources"]).append(source.model_dump(mode="json"))
        records.append({"evidence_type": "source_logical_entity", "record": row})
    for attribute in snapshot.logical.attributes:
        key = (
            attribute.logical_entity_schema_name.casefold(),
            attribute.logical_entity_name.casefold(),
        )
        if key not in logical_keys or not attribute.logical_attribute_is_active:
            continue
        selected_attributes.add((*key, attribute.logical_attribute_name.casefold()))
        row = attribute.model_dump(mode="json")
        row["sources"] = []
        for source in attribute.sources:
            if not source.is_active:
                continue
            if source.support_source_type == "attribute":
                physical_key = (
                    *natural_key(source.source_attribute.model_dump()),
                    source.source_attribute.attribute_name.casefold(),
                )
                if physical_key not in attribute_keys:
                    if ("logical_entity", *key) not in parent_keys or physical_key[
                        :-1
                    ] not in input_keys:
                        continue
                else:
                    lineage_attributes.add(physical_key)
                    lineage_objects.add(physical_key[:-1])
            elif (
                source.context_record.context_record_id.casefold() not in applicable_context_records
            ):
                continue
            cast(list[dict[str, Any]], row["sources"]).append(source.model_dump(mode="json"))
        records.append({"evidence_type": "source_logical_attribute", "record": row})
    for _, _, row in _eligible_logical_relationships(snapshot, selected_attributes):
        records.append({"evidence_type": "source_logical_relationship", "record": row})
    # A Gold lookup's key can originate in a different Silver Entity from the
    # fact's driver. Keep that saved lineage as evidence, never as input eligibility.
    active_logical_keys = {
        (row.logical_entity_schema_name.casefold(), row.logical_entity_name.casefold())
        for row in snapshot.logical.entities
        if row.logical_entity_is_active
    }
    active_logical_attributes = {
        (
            row.logical_entity_schema_name.casefold(),
            row.logical_entity_name.casefold(),
            row.logical_attribute_name.casefold(),
        )
        for row in snapshot.logical.attributes
        if row.logical_attribute_is_active
        and (row.logical_entity_schema_name.casefold(), row.logical_entity_name.casefold())
        in active_logical_keys
    }
    dimensional_attributes: set[tuple[str, str, str]] = set()
    for kind, rows in (
        ("source_dimensional_entity", snapshot.dimensional.entities),
        ("source_dimensional_attribute", snapshot.dimensional.attributes),
    ):
        for item in rows:
            row = item.model_dump(mode="json")
            key = (
                row["dimensional_entity_schema_name"].casefold(),
                row["dimensional_entity_name"].casefold(),
            )
            if (
                key not in dimensional_keys
                or not row[
                    "dimensional_attribute_is_active"
                    if kind == "source_dimensional_attribute"
                    else "dimensional_entity_is_active"
                ]
            ):
                continue
            if kind == "source_dimensional_attribute":
                dimensional_attributes.add((*key, row["dimensional_attribute_name"].casefold()))
            sources = row["sources"]
            row["sources"] = []
            for source in sources:
                if not source["is_active"]:
                    continue
                source_type = source["support_source_type"]
                if source_type == "context_record":
                    if (
                        source["context_record"]["context_record_id"].casefold()
                        not in applicable_context_records
                    ):
                        continue
                else:
                    upstream = source[f"source_{source_type}"]
                    logical_key = (
                        upstream["logical_entity_schema_name"].casefold(),
                        upstream["logical_entity_name"].casefold(),
                    )
                    if logical_key not in active_logical_keys or (
                        source_type == "logical_attribute"
                        and (*logical_key, upstream["logical_attribute_name"].casefold())
                        not in active_logical_attributes
                    ):
                        continue
                cast(list[dict[str, Any]], row["sources"]).append(source)
            records.append({"evidence_type": kind, "record": row})
    system_code = preparation.context.source_system.system_code.casefold()
    template_codes: set[str] = set()
    for kind, mappings in (
        ("source_object_mapping", snapshot.mapping.objects),
        ("source_attribute_mapping", snapshot.mapping.attributes),
    ):
        for mapping in mappings:
            row = mapping.model_dump(mode="json")
            key = (
                mapping.modeled_entity_schema_name.casefold(),
                mapping.modeled_entity_name.casefold(),
            )
            status = row[
                "object_mapping_status"
                if kind == "source_object_mapping"
                else "attribute_mapping_status"
            ]
            if (
                key
                not in (
                    logical_keys
                    if mapping.modeled_entity_type == "logical_entity"
                    else dimensional_keys
                )
                or (
                    mapping.source_system_code.casefold() != system_code
                    and (mapping.modeled_entity_type, *key) not in parent_keys
                )
                or status != "active"
            ):
                continue
            if kind == "source_attribute_mapping" and (
                *key,
                row["modeled_attribute_name"].casefold(),
            ) not in (
                selected_attributes
                if mapping.modeled_entity_type == "logical_entity"
                else dimensional_attributes
            ):
                continue
            records.append({"evidence_type": kind, "record": row})
            if mapping.output_template_code is not None:
                template_codes.add(mapping.output_template_code.casefold())
    for template in preparation.context.output_templates.definitions:
        if template.code.casefold() in template_codes:
            records.append(
                {
                    "evidence_type": "source_mapping_template",
                    "record": without_internal_fields(template.model_dump(mode="json")),
                }
            )
    # Physical records are explanatory provenance only. Gold still maps Logical inputs.
    for key, obj in physical.items():
        if key not in lineage_objects:
            continue
        row = without_internal_fields(obj.model_dump(mode="json", exclude={"attributes"}))
        records.append({"evidence_type": "physical_object", "record": row})
        for attribute in obj.attributes:
            if (*key, attribute.attribute_name.casefold()) in lineage_attributes:
                row = {
                    **{field: getattr(obj, field) for field in OBJECT_FIELDS},
                    **without_internal_fields(attribute.model_dump(mode="json")),
                }
                records.append({"evidence_type": "physical_attribute", "record": row})
    if preparation.plan.route == "dimensional_to_gold":
        for profile in snapshot.profiling.profiles:
            if (
                *natural_key(profile.model_dump()),
                profile.attribute_name.casefold(),
            ) in lineage_attributes:
                records.append(
                    {"evidence_type": "profile", "record": profile.model_dump(mode="json")}
                )
        for relationship in snapshot.analysis.relationships:
            row = relationship.model_dump(mode="json")
            if relationship.analysis_result_status == "active" and all(
                (
                    *natural_key({field: row[f"{side}_{field}"] for field in OBJECT_FIELDS}),
                    row[f"{side}_attribute_name"].casefold(),
                )
                in lineage_attributes
                for side in ("from", "to")
            ):
                records.append({"evidence_type": "analysis_relationship", "record": row})
    return records


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
                        **(
                            {
                                f"{source.object.entity_type}_schema_name": (
                                    source.object.entity_schema_name
                                ),
                                f"{source.object.entity_type}_name": source.object.entity_name,
                            }
                            if isinstance(source.object, MappingModeledEntity)
                            else {"object_id": source.object.object_id}
                        ),
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
                        "modeled_entity_id": header.modeled_entity_id,
                        "mapping_object_id": header.mapping_object_id,
                        **child.model_dump(mode="json"),
                    },
                )
            )
        header_documents.append(cast(JsonValue, header_document))
    return {
        "run": (cast(dict[str, JsonValue], _mapping_provider_context(preparation))["run"],),
        "source_system": (cast(JsonValue, context.source_system.model_dump(mode="json")),),
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
        "project_id": plan.project_id,
        "project_revision": plan.project_revision,
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
    max_result_bytes: int | None,
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
            if max_result_bytes is None or _mapping_page_item_fits(
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
    except TypeError, ValueError:
        raise AgentContextToolRequestError() from None


__all__ = [
    "InMemoryMappingContextToolCatalog",
    "MappingExecutionContext",
    "MappingExecutionContextLimits",
    "build_mapping_execution_context",
    "load_default_mapping_execution_context_limits",
]
