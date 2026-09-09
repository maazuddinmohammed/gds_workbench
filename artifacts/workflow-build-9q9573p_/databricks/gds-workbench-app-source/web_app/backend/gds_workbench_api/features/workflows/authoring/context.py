"""Bounded, read-only context for one frozen agent authoring run."""

from __future__ import annotations

import json
from collections.abc import Awaitable, Callable, Mapping
from copy import deepcopy
from dataclasses import dataclass, field
from hashlib import sha256
from typing import Any, Literal, LiteralString, cast

from gds_etl_workbench.application.change_sets.model import load_model_physical_scope
from gds_etl_workbench.application.change_sets.model_validation import PhysicalModelCatalog
from gds_etl_workbench.application.model_read import ModelReadContext
from gds_etl_workbench.application.model_snapshot import build_model_snapshot
from gds_etl_workbench.domain.errors import WorkbenchError
from gds_etl_workbench.domain.metadata_records import AttributeRecord, ObjectRecord
from gds_etl_workbench.domain.modeling_records import (
    AnalysisResultRecord,
    ModelDetailsRecord,
    ProfilingProfileRecord,
    normalize_model_key_value,
)
from gds_etl_workbench.domain.snapshots.model import (
    AssertionSection,
    ConceptualSection,
    DimensionalSection,
    LogicalSection,
    MappingSection,
    ModelDataset,
    ModelSnapshot,
    model_snapshot_records,
)
from gds_etl_workbench.infrastructure.postgres import ReadTransaction
from pydantic import BaseModel, ConfigDict, Field, JsonValue

from gds_workbench_api.features.assertions.contracts import validate_safe_json
from gds_workbench_api.features.workflows.authoring.agent_execution import (
    AgentContextToolRequestError,
    AgentContextToolResultTooLargeError,
    LocalAgentToolDefinition,
)
from gds_workbench_api.features.workflows.authoring.tool_configuration import (
    registered_tool_definitions,
)

from .context_inputs import project_context_inputs
from .context_readers import FrozenContextReaders
from .plan import AgentRunPlan, ModelWorkflow, WorkflowExecutionMode
from .repair import AgentContextTooLargeError, load_default_agent_context_policy

type SnapshotLoader = Callable[
    [ReadTransaction, ModelReadContext],
    Awaitable[ModelSnapshot],
]
type PhysicalScopeLoader = Callable[
    [ReadTransaction, ModelReadContext], Awaitable[PhysicalModelCatalog]
]
type PhysicalObjectKey = tuple[str, str, str, str, str]

_TOOL_TRANSCRIPT_CONTEXT_DIVISOR = 2
_CONTEXT_FRAGMENT_KEY = "__gds_context_fragment__"
_CONTEXT_FRAGMENT_ENCODING = "canonical_json"
_PAGE_SIZE_SENTINEL = 9_999_999_999

_FORBIDDEN_PROVIDER_JSON_KEYS = frozenset(
    {
        "access_token",
        "api_key",
        "authorization",
        "bearer_token",
        "client_secret",
        "connection_value",
        "connection_values",
        "dsn",
        "http_path",
        "id",
        "password",
        "private_key",
        "refresh_token",
        "server_hostname",
    }
)
_FORBIDDEN_PROVIDER_JSON_KEY_PARTS = (
    "apikey",
    "bearertoken",
    "connectionstring",
    "credential",
    "password",
    "physicalrows",
    "privatekey",
    "rawprompt",
    "rawrows",
    "secret",
    "tooloutput",
)
_FORBIDDEN_PROVIDER_JSON_VALUE_PARTS = (
    "access_token=",
    "api_key=",
    "apikey=",
    "authorization: bearer ",
    "client_secret=",
    "connection_string=",
    "connectionstring=",
    "dsn=",
    "password=",
    "private_key=",
    "raw prompt",
    "raw tool output",
    "raw_prompt",
    "raw_tool_output",
    "refresh_token=",
    "secret_reference=",
    "tool output",
    "tool_output",
)
_FORBIDDEN_PROVIDER_JSON_VALUE_PREFIXES = (
    "bearer ",
    "jdbc:",
    "mongodb://",
    "postgres://",
    "postgresql://",
    "sk-",
    "sqlserver://",
)

_MODEL_FENCE_SQL: LiteralString = """
SELECT model_id,
       tenant_id,
       model_name,
       model_revision
  FROM model.model
 WHERE tenant_id = %s
   AND model_id = %s
   AND model_revision = %s
   AND is_active
"""

_SELECTED_OBJECTS_SQL: LiteralString = """
WITH selected AS (
    SELECT object_id, selection_order
      FROM unnest(%s::BIGINT[]) WITH ORDINALITY
           AS selected_object(object_id, selection_order)
), eligible_objects AS MATERIALIZED (
    SELECT eligibility.*
      FROM workflow.list_model_object_eligibility(%s) AS eligibility
)
SELECT selected.selection_order,
       eligibility.object_id,
       placement_tenant.tenant_code AS tenant_code,
       system.system_code,
       connection.connection_code,
       source_tenant.tenant_code AS source_tenant_code,
       object_record.object_schema,
       object_record.object_name,
       object_record.fc_object_schema,
       object_record.fc_object_name,
       object_record.object_transformation,
       object_record.object_description,
       object_record.batch_attribute_name,
       object_type.object_type_code,
       eligibility.zone_code,
       object_record.is_locked,
       object_record.is_active
  FROM selected
  JOIN eligible_objects AS eligibility
    ON eligibility.object_id = selected.object_id
  JOIN core.object AS object_record
    ON object_record.object_id = eligibility.object_id
   AND object_record.connection_id = eligibility.connection_id
  JOIN core.connection AS connection
    ON connection.connection_id = eligibility.connection_id
   AND connection.system_id = eligibility.system_id
  JOIN core.tenant AS placement_tenant
    ON placement_tenant.tenant_id = connection.tenant_id
  JOIN core.tenant AS source_tenant
    ON source_tenant.tenant_id = object_record.source_tenant_id
  JOIN core.system AS system
    ON system.system_id = eligibility.system_id
  JOIN reference.object_type AS object_type
    ON object_type.object_type_id = object_record.object_type_id
 WHERE %s <> 'dimensional'
    OR eligibility.is_dimensional_source_eligible
 ORDER BY selected.selection_order
"""

_SELECTED_ATTRIBUTES_SQL: LiteralString = """
WITH selected AS (
    SELECT object_id, selection_order
      FROM unnest(%s::BIGINT[]) WITH ORDINALITY
           AS selected_object(object_id, selection_order)
), eligible_attributes AS MATERIALIZED (
    SELECT eligibility.*
      FROM workflow.list_model_attribute_eligibility(%s) AS eligibility
)
SELECT selected.selection_order,
       eligibility.object_id,
       eligibility.attribute_id,
       placement_tenant.tenant_code AS tenant_code,
       system.system_code,
       connection.connection_code,
       object_record.object_schema,
       object_record.object_name,
       attribute.attribute_name,
       attribute.fc_attribute_name,
       attribute.attribute_ordinal_position,
       attribute.attribute_description,
       attribute.attribute_data_type,
       attribute.attribute_inferred_data_type,
       attribute.attribute_nullability,
       attribute.attribute_custom_code,
       attribute.is_surrogate_key,
       attribute.is_natural_key,
       attribute.is_meta_data,
       attribute.is_masking_required,
       attribute.is_mapped,
       attribute.is_purge,
       attribute.is_locked,
       attribute.is_active
  FROM selected
  JOIN eligible_attributes AS eligibility
    ON eligibility.object_id = selected.object_id
  JOIN core.object AS object_record
    ON object_record.object_id = eligibility.object_id
   AND object_record.connection_id = eligibility.connection_id
  JOIN core.attribute AS attribute
    ON attribute.attribute_id = eligibility.attribute_id
   AND attribute.object_id = eligibility.object_id
  JOIN core.connection AS connection
    ON connection.connection_id = eligibility.connection_id
   AND connection.system_id = eligibility.system_id
  JOIN core.tenant AS placement_tenant
    ON placement_tenant.tenant_id = connection.tenant_id
  JOIN core.system AS system
    ON system.system_id = eligibility.system_id
 WHERE %s <> 'dimensional'
    OR eligibility.is_dimensional_source_eligible
 ORDER BY selected.selection_order,
          attribute.attribute_ordinal_position,
          attribute.attribute_id
 LIMIT %s
"""


_PROMPT_SOURCE_CONTEXT_SQL: LiteralString = """
SELECT target.object_id,
       zone.zone_description,
       source.object_schema AS source_object_schema,
       source.object_name AS source_object_name,
       source.object_description AS source_object_description,
       source_tenant.tenant_code,
       source_tenant.tenant_description,
       source_system.system_code,
       source_system.system_description,
       system_type.system_type_code,
       system_type.system_type_description,
       source_connection.connection_code,
       source_connection.connection_description,
       connection_type.connection_type_code,
       connection_type.connection_type_description,
       source_zone.zone_description AS source_zone_description
  FROM core.object AS target
  JOIN reference.zone AS zone ON zone.zone_id = target.zone_id
  LEFT JOIN LATERAL (
      SELECT target.object_id AS source_object_id WHERE zone.zone_code = 'source'
      UNION
      SELECT mapping.source_object_id
        FROM core.ingestion_object_mapping AS mapping
       WHERE mapping.target_object_id = target.object_id
         AND mapping.is_active AND zone.zone_code = 'bronze'
  ) AS origin ON TRUE
  LEFT JOIN core.object AS source
    ON source.object_id = origin.source_object_id
   AND source.is_active AND source.source_tenant_id = target.source_tenant_id
  LEFT JOIN core.connection AS source_connection
    ON source_connection.connection_id = source.connection_id
   AND source_connection.tenant_id = target.source_tenant_id AND source_connection.is_active
  LEFT JOIN core.tenant AS source_tenant
    ON source_tenant.tenant_id = source_connection.tenant_id AND source_tenant.is_active
  LEFT JOIN core.system AS source_system
    ON source_system.system_id = source_connection.system_id AND source_system.is_active
  LEFT JOIN reference.system_type AS system_type
    ON system_type.system_type_id = source_system.system_type_id
  LEFT JOIN reference.connection_type AS connection_type
    ON connection_type.connection_type_id = source_connection.connection_type_id
  LEFT JOIN reference.zone AS source_zone
    ON source_zone.zone_id = source.zone_id AND source_zone.zone_code = 'source'
 WHERE target.object_id = ANY(%s::BIGINT[]) AND target.source_tenant_id = %s
 ORDER BY target.object_id, source.object_id
"""

_PROFILE_PROVENANCE_SQL: LiteralString = """
SELECT tenant.tenant_code, system.system_code, connection.connection_code,
       object_record.object_schema, object_record.object_name, attribute.attribute_name,
       profile.updated_time AS profiled_at,
       CASE WHEN run.workflow_run_id IS NULL THEN NULL
            WHEN run.requested_batch_id IS NULL THEN 'all_rows' ELSE 'batch' END AS row_scope,
       NULL::TEXT AS batch_attribute_name,
       run.requested_batch_id AS batch_id
  FROM workflow.attribute_profile AS profile
  JOIN core.object AS object_record ON object_record.object_id = profile.object_id
  JOIN core.attribute AS attribute ON attribute.attribute_id = profile.attribute_id
  JOIN core.connection AS connection ON connection.connection_id = object_record.connection_id
  JOIN core.tenant AS tenant ON tenant.tenant_id = connection.tenant_id
  JOIN core.system AS system ON system.system_id = connection.system_id
  LEFT JOIN application.workflow_run AS run
    ON run.workflow_run_id = profile.workflow_run_id AND run.model_id = profile.model_id
   AND run.model_workflow = 'profiling'
 WHERE profile.model_id = %s AND profile.object_id = ANY(%s::BIGINT[])
 ORDER BY profile.object_id, profile.attribute_id
"""


class AgentContextUnavailableError(WorkbenchError):
    def __init__(self) -> None:
        super().__init__(
            code="agent_context_unavailable",
            message="The revision-fenced agent context is unavailable or incomplete.",
        )


class AgentContextLimits(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    max_selected_objects: int = Field(ge=1, le=50_000)
    max_selected_attributes: int = Field(ge=1, le=50_000)
    max_total_records: int = Field(ge=1, le=100_000)
    one_shot_max_context_bytes: int = Field(ge=1, le=10 * 1024 * 1024)
    stage_max_context_bytes: int = Field(ge=1, le=10 * 1024 * 1024)
    max_tool_result_bytes: int = Field(ge=1, le=10 * 1024 * 1024)
    max_tool_catalog_bytes: int = Field(
        default=10 * 1024 * 1024,
        ge=1,
        le=10 * 1024 * 1024,
    )
    max_tool_page_records: int = Field(default=200, ge=1, le=1_000)


def load_default_agent_context_limits() -> AgentContextLimits:
    policy = load_default_agent_context_policy()
    return AgentContextLimits(
        max_selected_objects=1_000,
        max_selected_attributes=20_000,
        max_total_records=50_000,
        one_shot_max_context_bytes=policy.one_shot_max_context_bytes,
        stage_max_context_bytes=policy.stage_max_context_bytes,
        max_tool_result_bytes=policy.stage_max_context_bytes,
        max_tool_catalog_bytes=10 * 1024 * 1024,
        max_tool_page_records=200,
    )


class SelectedObjectContext(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    selection_order: int = Field(gt=0)
    object: ObjectRecord = Field(repr=False)
    attributes: tuple[AttributeRecord, ...] = Field(repr=False)


class ApplicableAppliedRecords(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    conceptual: ConceptualSection | None = Field(default=None, repr=False)
    logical: LogicalSection | None = Field(default=None, repr=False)
    dimensional: DimensionalSection | None = Field(default=None, repr=False)
    mapping: MappingSection | None = Field(default=None, repr=False)


class AgentModelDependency(BaseModel):
    """Read-only dependency identity and state, without generated code or Mapping bodies."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    dataset: ModelDataset
    record: dict[str, JsonValue] = Field(repr=False)


class AgentAuthoringContext(BaseModel):
    """Safe typed content only; no prompts, secrets, physical rows, or tool output."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    schema_version: Literal["1.0"] = "1.0"
    workflow_run_id: int = Field(gt=0)
    model_id: int = Field(gt=0)
    model_name: str = Field(min_length=1, max_length=255)
    model_revision: int = Field(gt=0)
    model_workflow: ModelWorkflow
    workflow_execution_mode: WorkflowExecutionMode | None
    modeled_entity_type: Literal["logical_entity", "dimensional_entity"] | None
    selected_scope_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    model_details: ModelDetailsRecord = Field(repr=False)
    selected_objects: tuple[SelectedObjectContext, ...] = Field(repr=False)
    profiles: tuple[ProfilingProfileRecord, ...] = Field(repr=False)
    analysis_relationships: tuple[AnalysisResultRecord, ...] = Field(repr=False)
    assertion: AssertionSection = Field(repr=False)
    applied: ApplicableAppliedRecords = Field(repr=False)
    read_only_dependencies: tuple[AgentModelDependency, ...] = Field(default=(), repr=False)
    source_context: tuple[dict[str, JsonValue], ...] = Field(default=(), repr=False)
    gds_context: tuple[dict[str, JsonValue], ...] = Field(default=(), repr=False)
    ingestion_mapping: tuple[dict[str, JsonValue], ...] = Field(default=(), repr=False)
    profile_provenance: tuple[dict[str, JsonValue], ...] = Field(default=(), repr=False)
    logical_bindings: tuple[dict[str, JsonValue], ...] = Field(default=(), repr=False)


class InMemoryAgentContextToolCatalog:
    """Page immutable preloaded records without database or external calls."""

    def __init__(
        self,
        *,
        context: AgentAuthoringContext,
        max_result_bytes: int,
        max_catalog_bytes: int,
        max_page_records: int,
        max_cumulative_result_bytes: int | None = None,
    ) -> None:
        cumulative_result_bytes = (
            max_result_bytes if max_cumulative_result_bytes is None else max_cumulative_result_bytes
        )
        if max_result_bytes < 1 or cumulative_result_bytes < max_result_bytes:
            raise AgentContextTooLargeError()
        self._max_result_bytes = max_result_bytes
        self._max_cumulative_result_bytes = cumulative_result_bytes
        self._max_page_records = max_page_records
        raw_datasets = _context_datasets(context)
        (
            self._datasets,
            dataset_record_counts,
            fragmented_record_counts,
        ) = _bounded_context_datasets(
            raw_datasets,
            max_result_bytes=max_result_bytes,
        )
        self._readers = FrozenContextReaders(
            workflow=context.model_workflow,
            values=project_context_inputs(context.model_dump(mode="json")),
            max_result_bytes=max_result_bytes,
            max_page_records=max_page_records,
            max_cumulative_result_bytes=cumulative_result_bytes,
        )
        self._definitions = registered_tool_definitions(
            context.model_workflow, max_page_records=max_page_records
        )
        self._manifest = _context_manifest(
            context,
            self._datasets,
            dataset_record_counts=dataset_record_counts,
            fragmented_record_counts=fragmented_record_counts,
        )
        if _json_bytes(cast(JsonValue, self._manifest)) > max_result_bytes:
            self._manifest = _compact_context_manifest(self._manifest)
        if _json_bytes(cast(JsonValue, self._manifest)) > max_result_bytes:
            raise AgentContextTooLargeError()
        self._serialized_size_bytes = _json_bytes(
            cast(
                JsonValue,
                {
                    "manifest": self._manifest,
                    "datasets": {name: list(rows) for name, rows in self._datasets.items()},
                    "prompt_values": self._readers.prompt_values,
                },
            )
        )
        if self._serialized_size_bytes > max_catalog_bytes:
            raise AgentContextTooLargeError()

    @property
    def prompt_values(self) -> dict[str, Any]:
        return self._readers.prompt_values

    @property
    def manifest(self) -> JsonValue:
        return cast(JsonValue, deepcopy(self._manifest))

    @property
    def definitions(self) -> tuple[LocalAgentToolDefinition, ...]:
        return self._definitions

    @property
    def allowed_tool_names(self) -> tuple[str, ...]:
        return tuple(definition.name for definition in self._definitions)

    @property
    def serialized_size_bytes(self) -> int:
        return self._serialized_size_bytes

    @property
    def max_result_bytes(self) -> int:
        return self._max_result_bytes

    @property
    def max_cumulative_result_bytes(self) -> int:
        return self._max_cumulative_result_bytes

    def invoke(
        self,
        tool_name: str,
        arguments: Mapping[str, JsonValue],
    ) -> JsonValue:
        if tool_name in self.allowed_tool_names:
            return self._readers.invoke(tool_name, arguments)
        if tool_name == "get_agent_context_manifest":
            if arguments:
                raise AgentContextToolRequestError()
            result = self.manifest
        elif tool_name == "get_agent_context_dataset":
            result = self._read_dataset(arguments)
        else:
            raise AgentContextToolRequestError()
        result_bytes = _json_bytes(result)
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
            or limit > self._max_page_records
        ):
            raise AgentContextToolRequestError()
        rows = self._datasets[dataset]
        if offset > len(rows):
            raise AgentContextToolRequestError()
        total_count = len(rows)
        end_limit = min(offset + limit, total_count)
        items: list[JsonValue] = []
        end = offset
        while end < end_limit:
            candidate_items = [*items, deepcopy(rows[end])]
            candidate_end = end + 1
            candidate = _dataset_page(
                dataset=dataset,
                total_count=total_count,
                offset=offset,
                items=candidate_items,
                next_offset=candidate_end if candidate_end < total_count else None,
            )
            if _json_bytes(candidate) > self._max_result_bytes:
                if not items:
                    raise AgentContextToolResultTooLargeError()
                break
            items = candidate_items
            end = candidate_end
        result = _dataset_page(
            dataset=dataset,
            total_count=total_count,
            offset=offset,
            items=items,
            next_offset=end if end < total_count else None,
        )
        if _json_bytes(result) > self._max_result_bytes:
            raise AgentContextToolResultTooLargeError()
        return result

    def __repr__(self) -> str:
        return f"InMemoryAgentContextToolCatalog(datasets={len(self._datasets)})"


@dataclass(frozen=True, slots=True)
class AgentContextBundle:
    context: AgentAuthoringContext = field(repr=False)
    embedded_context: JsonValue = field(repr=False)
    tool_catalog: InMemoryAgentContextToolCatalog | None = field(default=None, repr=False)
    snapshot: ModelSnapshot | None = field(default=None, repr=False)
    physical_scope: PhysicalModelCatalog | None = field(default=None, repr=False)

    def __repr__(self) -> str:
        return (
            f"AgentContextBundle(model_id={self.context.model_id}, "
            f"model_revision={self.context.model_revision}, "
            f"tool_assisted={self.tool_catalog is not None})"
        )


class PostgresAgentContextRepository:
    """Load one Model and final-recheck its revision under any read isolation."""

    def __init__(
        self,
        *,
        snapshot_loader: SnapshotLoader = build_model_snapshot,
        physical_scope_loader: PhysicalScopeLoader = load_model_physical_scope,
        limits: AgentContextLimits | None = None,
    ) -> None:
        self._snapshot_loader = snapshot_loader
        self._physical_scope_loader = physical_scope_loader
        self._limits = limits or load_default_agent_context_limits()

    async def load(
        self,
        transaction: ReadTransaction,
        *,
        tenant_id: int,
        plan: AgentRunPlan,
    ) -> AgentContextBundle:
        if len(plan.selected_object_ids) > self._limits.max_selected_objects:
            raise AgentContextTooLargeError()

        try:
            model_row = await transaction.fetch_one(
                _MODEL_FENCE_SQL,
                (tenant_id, plan.model_id, plan.model_revision),
            )
            if model_row is None:
                raise AgentContextUnavailableError()
            model = _model_context(model_row, tenant_id=tenant_id, plan=plan)

            object_rows = await transaction.fetch_all(
                _SELECTED_OBJECTS_SQL,
                (
                    list(plan.selected_object_ids),
                    plan.model_id,
                    plan.model_workflow,
                ),
            )
            attribute_rows = await transaction.fetch_all(
                _SELECTED_ATTRIBUTES_SQL,
                (
                    list(plan.selected_object_ids),
                    plan.model_id,
                    plan.model_workflow,
                    self._limits.max_selected_attributes + 1,
                ),
            )
            if len(attribute_rows) > self._limits.max_selected_attributes:
                raise AgentContextTooLargeError()
            selected = _selected_objects(
                plan=plan,
                object_rows=object_rows,
                attribute_rows=attribute_rows,
            )
            snapshot = await self._snapshot_loader(transaction, model)
            physical_scope = (
                await self._physical_scope_loader(transaction, model)
                if plan.model_workflow in {"conceptual", "logical", "dimensional"}
                else None
            )
            context = _assemble_context(
                plan=plan,
                model=model,
                selected=selected,
                snapshot=snapshot,
            )
            source_rows = await transaction.fetch_all(
                _PROMPT_SOURCE_CONTEXT_SQL, (list(plan.selected_object_ids), tenant_id)
            )
            provenance_rows = await transaction.fetch_all(
                _PROFILE_PROVENANCE_SQL, (plan.model_id, list(plan.selected_object_ids))
            )
            context = _with_prompt_evidence(
                context,
                plan=plan,
                snapshot=snapshot,
                source_rows=source_rows,
                provenance_rows=provenance_rows,
            )
            if _context_record_count(context) > self._limits.max_total_records:
                raise AgentContextTooLargeError()

            _validate_nested_provider_json(
                context,
                maximum_bytes=max(
                    self._limits.one_shot_max_context_bytes,
                    self._limits.stage_max_context_bytes,
                    self._limits.max_tool_catalog_bytes,
                ),
            )
            full_context = _provider_context(context)
            tool_catalog = None
            if plan.workflow_execution_mode == "tool_assisted":
                tool_catalog = InMemoryAgentContextToolCatalog(
                    context=context,
                    max_result_bytes=_tool_result_budget(
                        limits=self._limits,
                        max_turns=plan.selection.max_turns,
                    ),
                    max_cumulative_result_bytes=_tool_transcript_allowance(self._limits),
                    max_catalog_bytes=self._limits.max_tool_catalog_bytes,
                    max_page_records=self._limits.max_tool_page_records,
                )
                embedded = tool_catalog.manifest
            else:
                embedded = full_context
            if (
                plan.workflow_execution_mode in (None, "one_shot")
                and _json_bytes(embedded) > self._limits.one_shot_max_context_bytes
            ) or (
                plan.workflow_execution_mode == "tool_assisted"
                and _json_bytes(embedded) > self._limits.stage_max_context_bytes
            ):
                raise AgentContextTooLargeError()

            final_model_row = await transaction.fetch_one(
                _MODEL_FENCE_SQL,
                (tenant_id, plan.model_id, plan.model_revision),
            )
            if (
                final_model_row is None
                or _model_context(
                    final_model_row,
                    tenant_id=tenant_id,
                    plan=plan,
                )
                != model
            ):
                raise AgentContextUnavailableError()
            return AgentContextBundle(
                context=context,
                embedded_context=embedded,
                tool_catalog=tool_catalog,
                snapshot=snapshot,
                physical_scope=physical_scope,
            )
        except (AgentContextTooLargeError, AgentContextUnavailableError):
            raise
        except Exception:
            raise AgentContextUnavailableError() from None


async def load_frozen_model_graph(
    transaction: ReadTransaction,
    *,
    tenant_id: int,
    plan: AgentRunPlan,
) -> tuple[ModelSnapshot, PhysicalModelCatalog]:
    """Load backend-only validation evidence inside an authorized repeatable-read context."""
    row = await transaction.fetch_one(
        _MODEL_FENCE_SQL, (tenant_id, plan.model_id, plan.model_revision)
    )
    if row is None:
        raise AgentContextUnavailableError()
    model = _model_context(row, tenant_id=tenant_id, plan=plan)
    return await build_model_snapshot(transaction, model), await load_model_physical_scope(
        transaction, model
    )


def _model_context(
    row: Mapping[str, Any],
    *,
    tenant_id: int,
    plan: AgentRunPlan,
) -> ModelReadContext:
    values = (
        row.get("model_id"),
        row.get("tenant_id"),
        row.get("model_name"),
        row.get("model_revision"),
    )
    if (
        values[0] != plan.model_id
        or values[1] != tenant_id
        or not isinstance(values[2], str)
        or not values[2]
        or values[3] != plan.model_revision
    ):
        raise AgentContextUnavailableError()
    return ModelReadContext(
        model_id=plan.model_id,
        tenant_id=tenant_id,
        model_name=values[2],
        model_revision=plan.model_revision,
    )


def _selected_objects(
    *,
    plan: AgentRunPlan,
    object_rows: list[dict[str, Any]],
    attribute_rows: list[dict[str, Any]],
) -> tuple[SelectedObjectContext, ...]:
    if len(object_rows) != len(plan.selected_object_ids):
        raise AgentContextUnavailableError()

    object_by_id: dict[int, tuple[int, ObjectRecord]] = {}
    for expected_order, (expected_id, row) in enumerate(
        zip(plan.selected_object_ids, object_rows, strict=True),
        start=1,
    ):
        object_id = row.get("object_id")
        selection_order = row.get("selection_order")
        if object_id != expected_id or selection_order != expected_order:
            raise AgentContextUnavailableError()
        record = ObjectRecord.model_validate(
            {
                key: value
                for key, value in row.items()
                if key not in {"object_id", "selection_order"}
            },
            strict=False,
        )
        object_by_id[expected_id] = (expected_order, record)

    attributes_by_object: dict[int, list[AttributeRecord]] = {
        object_id: [] for object_id in plan.selected_object_ids
    }
    seen_attribute_ids: set[int] = set()
    for row in attribute_rows:
        object_id = row.get("object_id")
        attribute_id = row.get("attribute_id")
        if (
            not isinstance(object_id, int)
            or object_id not in object_by_id
            or not isinstance(attribute_id, int)
            or attribute_id <= 0
            or attribute_id in seen_attribute_ids
        ):
            raise AgentContextUnavailableError()
        seen_attribute_ids.add(attribute_id)
        record = AttributeRecord.model_validate(
            {
                key: value
                for key, value in row.items()
                if key not in {"object_id", "attribute_id", "selection_order"}
            },
            strict=False,
        )
        if _physical_key(record) != _physical_key(object_by_id[object_id][1]):
            raise AgentContextUnavailableError()
        attributes_by_object[object_id].append(record)

    selected: list[SelectedObjectContext] = []
    for object_id in plan.selected_object_ids:
        selection_order, object_record = object_by_id[object_id]
        attributes = attributes_by_object[object_id]
        ordinals = [attribute.attribute_ordinal_position for attribute in attributes]
        names = [normalize_model_key_value(attribute.attribute_name) for attribute in attributes]
        if len(ordinals) != len(set(ordinals)) or len(names) != len(set(names)):
            raise AgentContextUnavailableError()
        selected.append(
            SelectedObjectContext(
                selection_order=selection_order,
                object=object_record,
                attributes=tuple(attributes),
            )
        )
    return tuple(selected)


def _assemble_context(
    *,
    plan: AgentRunPlan,
    model: ModelReadContext,
    selected: tuple[SelectedObjectContext, ...],
    snapshot: ModelSnapshot,
) -> AgentAuthoringContext:
    if (
        snapshot.model_id != model.model_id
        or snapshot.model_name != model.model_name
        or snapshot.model_revision != model.model_revision
    ):
        raise AgentContextUnavailableError()

    selected_keys = {_physical_key(item.object) for item in selected}
    if len(selected_keys) != len(selected):
        raise AgentContextUnavailableError()
    scope_keys = {_physical_key(item) for item in snapshot.model_input_scope.objects}
    if plan.model_workflow == "dimensional":
        active_dependencies = {
            (
                dependency.modeled_entity_type,
                normalize_model_key_value(dependency.source_system_code),
            )
            for dependency in snapshot.mapping.dependencies
            if dependency.mapping_source_system_dependency_status == "active"
        }
        mapped_logical_entities = {
            normalize_model_key_value(mapping.modeled_entity_name)
            for mapping in snapshot.mapping.objects
            if mapping.modeled_entity_type == "logical_entity"
            and mapping.object_mapping_status == "active"
            and mapping.mapping_transformation_document is not None
            and (
                mapping.modeled_entity_type,
                normalize_model_key_value(mapping.source_system_code),
            )
            in active_dependencies
        }
        eligible_keys = {
            _physical_key(binding)
            for binding in snapshot.model_binding.objects
            if binding.modeled_entity_type == "logical_entity"
            and binding.model_object_binding_status == "active"
            and normalize_model_key_value(binding.modeled_entity_name) in mapped_logical_entities
        }
        if not selected_keys <= eligible_keys or any(
            item.object.zone_code != "silver" for item in selected
        ):
            raise AgentContextUnavailableError()
    elif not selected_keys <= scope_keys:
        raise AgentContextUnavailableError()

    profiles = tuple(
        profile
        for profile in snapshot.profiling.profiles
        if _physical_key(profile) in selected_keys
    )
    analysis_relationships = tuple(
        relationship
        for relationship in snapshot.analysis.relationships
        if _analysis_endpoint_key(relationship, "from") in selected_keys
        or _analysis_endpoint_key(relationship, "to") in selected_keys
    )

    assertion_layer = "mapping" if plan.model_workflow == "code_generation" else plan.model_workflow
    assertion_records = tuple(
        record
        for record in snapshot.assertion.records
        if assertion_layer in record.modeling_assertion_applicable_layers
    )
    assertion_document_names = {
        normalize_model_key_value(record.modeling_assertion_document_name)
        for record in assertion_records
    }
    assertion_documents = tuple(
        document
        for document in snapshot.assertion.documents
        if normalize_model_key_value(document.modeling_assertion_document_name)
        in assertion_document_names
    )

    applied = _applicable_applied_records(plan, snapshot)
    return AgentAuthoringContext(
        workflow_run_id=plan.workflow_run_id,
        model_id=model.model_id,
        model_name=model.model_name,
        model_revision=model.model_revision,
        model_workflow=plan.model_workflow,
        workflow_execution_mode=plan.workflow_execution_mode,
        modeled_entity_type=plan.modeled_entity_type,
        selected_scope_digest=plan.selected_scope_digest,
        model_details=snapshot.model_input_scope.details,
        selected_objects=selected,
        profiles=profiles,
        analysis_relationships=analysis_relationships,
        assertion=AssertionSection(
            documents=assertion_documents,
            records=assertion_records,
        ),
        applied=applied,
        read_only_dependencies=(
            modeled_layer_dependencies(
                snapshot,
                modeled_entity_type=(
                    "logical_entity" if plan.model_workflow == "logical" else "dimensional_entity"
                ),
            )
            if plan.model_workflow in {"logical", "dimensional"}
            else ()
        ),
    )


def _with_prompt_evidence(
    context: AgentAuthoringContext,
    *,
    plan: AgentRunPlan,
    snapshot: ModelSnapshot,
    source_rows: list[dict[str, Any]],
    provenance_rows: list[dict[str, Any]],
) -> AgentAuthoringContext:
    from .context_inputs import OBJECT_FIELDS, natural_key

    selected = dict(zip(plan.selected_object_ids, context.selected_objects, strict=True))
    sources: dict[tuple[Any, ...], dict[str, JsonValue]] = {}
    placements: dict[tuple[Any, ...], dict[str, JsonValue]] = {}
    mappings: dict[tuple[Any, ...], dict[str, JsonValue]] = {}
    for row in source_rows:
        if row["object_id"] not in selected:
            raise AgentContextUnavailableError()
        obj = selected[row["object_id"]].object.model_dump(mode="json")
        key = {name: obj[name] for name in OBJECT_FIELDS}
        if obj["zone_code"] != "source":
            placement = {name: obj[name] for name in (*OBJECT_FIELDS[:3], "zone_code")}
            placement["zone_description"] = row["zone_description"]
            placements[(*natural_key(obj, OBJECT_FIELDS[:3]), obj["zone_code"])] = placement
        if row["tenant_code"] is None or row["source_object_name"] is None:
            continue
        source = {
            name: row[name]
            for name in (
                "tenant_code",
                "tenant_description",
                "system_code",
                "system_description",
                "system_type_code",
                "system_type_description",
                "connection_code",
                "connection_description",
                "connection_type_code",
                "connection_type_description",
            )
        }
        source.update(zone_code="source", zone_description=row["source_zone_description"])
        sources[natural_key(source, OBJECT_FIELDS[:3])] = source
        if obj["zone_code"] == "bronze":
            source_key = {name: row[name] for name in OBJECT_FIELDS[:3]}
            source_key.update(
                object_schema=row["source_object_schema"],
                object_name=row["source_object_name"],
                object_description=row["source_object_description"],
            )
            mappings[(*natural_key(source_key), *natural_key(key))] = {
                "source": source_key,
                "target": key,
            }
    provenance: list[dict[str, Any]] = []
    for row in provenance_rows:
        value = dict(row)
        value["profiled_at"] = (
            row["profiled_at"].isoformat() if row["profiled_at"] is not None else None
        )
        provenance.append(value)
    bindings: list[dict[str, Any]] = []
    if plan.model_workflow == "dimensional":
        for selected_object in context.selected_objects:
            key = _physical_key(selected_object.object)
            matches = [
                b
                for b in snapshot.model_binding.objects
                if b.modeled_entity_type == "logical_entity"
                and b.model_object_binding_status == "active"
                and _physical_key(b) == key
            ]
            if len(matches) != 1:
                raise AgentContextUnavailableError()
            binding = matches[0]
            attrs: list[dict[str, str]] = []
            for attr in selected_object.attributes:
                candidates = [
                    a
                    for a in snapshot.model_binding.attributes
                    if a.modeled_entity_type == "logical_entity"
                    and a.model_attribute_binding_status == "active"
                    and normalize_model_key_value(a.modeled_entity_name)
                    == normalize_model_key_value(binding.modeled_entity_name)
                    and normalize_model_key_value(a.attribute_name)
                    == normalize_model_key_value(attr.attribute_name)
                ]
                if len(candidates) != 1:
                    raise AgentContextUnavailableError()
                attrs.append(
                    {
                        "attribute_name": attr.attribute_name,
                        "logical_attribute_name": candidates[0].modeled_attribute_name,
                    }
                )
            bindings.append(
                {
                    **{f: getattr(binding, f) for f in OBJECT_FIELDS},
                    "logical_entity_name": binding.modeled_entity_name,
                    "attributes": attrs,
                }
            )
    return context.model_copy(
        update={
            "source_context": tuple(sources.values()),
            "gds_context": tuple(placements.values()),
            "ingestion_mapping": tuple(mappings.values()),
            "profile_provenance": tuple(provenance),
            "logical_bindings": tuple(bindings),
        }
    )


def modeled_layer_dependencies(
    snapshot: ModelSnapshot, *, modeled_entity_type: Literal["logical_entity", "dimensional_entity"]
) -> tuple[AgentModelDependency, ...]:
    """Preserve direct downstream references for authoring and repair of either modeled layer."""

    records = model_snapshot_records(snapshot)
    return tuple(
        AgentModelDependency(
            dataset=dataset,
            record=record.model_dump(
                mode="json",
                exclude={
                    "mapping_transformation_document",
                    "attribute_mapping_transformation_document",
                    "generated_code_content",
                },
            ),
        )
        for dataset in (
            "model_object_binding",
            "model_attribute_binding",
            "mapping_dependency",
            "mapping_object",
            "mapping_attribute",
            "generated_code",
            "generated_code_source_system",
        )
        for record in records[dataset]
        if getattr(record, "modeled_entity_type", None) == modeled_entity_type
    )


def _applicable_applied_records(
    plan: AgentRunPlan,
    snapshot: ModelSnapshot,
) -> ApplicableAppliedRecords:
    conceptual = None
    logical = None
    dimensional = None
    mapping = None
    if plan.model_workflow == "conceptual":
        conceptual = snapshot.conceptual
    elif plan.model_workflow == "logical":
        conceptual = snapshot.conceptual
        logical = snapshot.logical
    elif plan.model_workflow == "dimensional":
        logical = snapshot.logical
        dimensional = snapshot.dimensional
        mapping = snapshot.mapping
    elif plan.model_workflow in ("mapping", "code_generation"):
        mapping = snapshot.mapping
        if plan.modeled_entity_type == "logical_entity":
            logical = snapshot.logical
        elif plan.modeled_entity_type == "dimensional_entity":
            dimensional = snapshot.dimensional
    return ApplicableAppliedRecords(
        conceptual=conceptual,
        logical=logical,
        dimensional=dimensional,
        mapping=mapping,
    )


def _physical_key(value: object) -> PhysicalObjectKey:
    return cast(
        PhysicalObjectKey,
        tuple(
            normalize_model_key_value(getattr(value, field_name))
            for field_name in (
                "tenant_code",
                "system_code",
                "connection_code",
                "object_schema",
                "object_name",
            )
        ),
    )


def _analysis_endpoint_key(
    relationship: AnalysisResultRecord,
    endpoint: Literal["from", "to"],
) -> PhysicalObjectKey:
    return cast(
        PhysicalObjectKey,
        tuple(
            normalize_model_key_value(getattr(relationship, f"{endpoint}_{field_name}"))
            for field_name in (
                "tenant_code",
                "system_code",
                "connection_code",
                "object_schema",
                "object_name",
            )
        ),
    )


def _context_record_count(context: AgentAuthoringContext) -> int:
    count = 0
    pending: list[object] = [context]
    while pending:
        item = pending.pop()
        if isinstance(item, BaseModel):
            count += 1
            pending.extend(getattr(item, field_name) for field_name in type(item).model_fields)
        elif isinstance(item, (list, tuple)):
            pending.extend(cast(list[object] | tuple[object, ...], item))
    return count


def _tool_result_budget(*, limits: AgentContextLimits, max_turns: int) -> int:
    transcript_allowance = _tool_transcript_allowance(limits)
    return min(
        limits.max_tool_result_bytes,
        max(1, transcript_allowance // max_turns),
    )


def _tool_transcript_allowance(limits: AgentContextLimits) -> int:
    return max(
        1,
        limits.stage_max_context_bytes // _TOOL_TRANSCRIPT_CONTEXT_DIVISOR,
    )


def _validate_nested_provider_json(
    context: AgentAuthoringContext,
    *,
    maximum_bytes: int,
) -> None:
    pending: list[object] = [context]
    while pending:
        item = pending.pop()
        if isinstance(item, BaseModel):
            for field_name in type(item).model_fields:
                field_value = getattr(item, field_name)
                if isinstance(field_value, dict):
                    validate_safe_json(
                        cast(dict[str, JsonValue], field_value),
                        maximum_bytes=maximum_bytes,
                        label="Agent context JSON",
                    )
                else:
                    pending.append(field_value)
        elif isinstance(item, (list, tuple)):
            pending.extend(cast(list[object] | tuple[object, ...], item))


def reject_forbidden_provider_json(
    value: JsonValue,
    *,
    allow_identity_keys: bool = False,
    reject_sensitive_values: bool = False,
) -> None:
    """Reject credentials, raw provider evidence, and optionally database IDs."""

    pending: list[JsonValue] = [value]
    while pending:
        item = pending.pop()
        if isinstance(item, list):
            pending.extend(item)
        elif isinstance(item, dict):
            for key, child in item.items():
                normalized_key = key.strip().lower().replace("-", "_")
                compact_key = normalized_key.replace("_", "")
                if (
                    normalized_key in _FORBIDDEN_PROVIDER_JSON_KEYS
                    or (
                        not allow_identity_keys
                        and normalized_key != "batch_id"
                        and (normalized_key.endswith("_id") or normalized_key.endswith("_ids"))
                    )
                    or any(
                        forbidden_part in compact_key
                        for forbidden_part in _FORBIDDEN_PROVIDER_JSON_KEY_PARTS
                    )
                ):
                    raise AgentContextUnavailableError()
                pending.append(child)
        elif reject_sensitive_values and isinstance(item, str):
            normalized_value = item.strip().lower()
            if (
                normalized_value.startswith(_FORBIDDEN_PROVIDER_JSON_VALUE_PREFIXES)
                or any(
                    forbidden_part in normalized_value
                    for forbidden_part in _FORBIDDEN_PROVIDER_JSON_VALUE_PARTS
                )
                or (
                    normalized_value.startswith("eyj")
                    and normalized_value.count(".") == 2
                    and len(normalized_value) > 40
                )
            ):
                raise AgentContextUnavailableError()


def _context_datasets(
    context: AgentAuthoringContext,
) -> dict[str, tuple[JsonValue, ...]]:
    selected_objects: list[JsonValue] = []
    selected_attributes: list[JsonValue] = []
    for selected in context.selected_objects:
        selected_objects.append(
            cast(
                JsonValue,
                {
                    "selection_order": selected.selection_order,
                    **selected.object.model_dump(mode="json"),
                    "attribute_count": len(selected.attributes),
                },
            )
        )
        selected_attributes.extend(
            cast(
                JsonValue,
                {
                    "selection_order": selected.selection_order,
                    **attribute.model_dump(mode="json"),
                },
            )
            for attribute in selected.attributes
        )

    datasets: dict[str, tuple[JsonValue, ...]] = {
        "model_details": (cast(JsonValue, context.model_details.model_dump(mode="json")),),
        "selected_object": tuple(selected_objects),
        "selected_attribute": tuple(selected_attributes),
        "profiling_profile": tuple(
            cast(JsonValue, record.model_dump(mode="json")) for record in context.profiles
        ),
        "analysis_result": tuple(
            cast(JsonValue, record.model_dump(mode="json"))
            for record in context.analysis_relationships
        ),
        "modeling_assertion_document": tuple(
            cast(JsonValue, record.model_dump(mode="json"))
            for record in context.assertion.documents
        ),
        "modeling_assertion_record": tuple(
            cast(JsonValue, record.model_dump(mode="json")) for record in context.assertion.records
        ),
    }
    conceptual = context.applied.conceptual
    if conceptual is not None:
        datasets["conceptual_object"] = _dump_records(conceptual.objects)
        datasets["conceptual_relationship"] = _dump_records(conceptual.relationships)
    logical = context.applied.logical
    if logical is not None:
        datasets["logical_submodel"] = _dump_records(logical.submodels)
        datasets["logical_entity"] = _dump_records(logical.entities)
        datasets["logical_attribute"] = _dump_records(logical.attributes)
        datasets["logical_relationship"] = _dump_records(logical.relationships)
    dimensional = context.applied.dimensional
    if dimensional is not None:
        datasets["dimensional_submodel"] = _dump_records(dimensional.submodels)
        datasets["dimensional_entity"] = _dump_records(dimensional.entities)
        datasets["dimensional_attribute"] = _dump_records(dimensional.attributes)
        datasets["dimensional_relationship"] = _dump_records(dimensional.relationships)
    mapping = context.applied.mapping
    if mapping is not None:
        datasets["mapping_dependency"] = _dump_records(mapping.dependencies)
        datasets["mapping_object"] = _dump_records(mapping.objects)
        datasets["mapping_attribute"] = _dump_records(mapping.attributes)
    dependencies: dict[str, list[JsonValue]] = {}
    for dependency in context.read_only_dependencies:
        dependencies.setdefault(f"read_only_{dependency.dataset}", []).append(dependency.record)
    datasets.update({name: tuple(records) for name, records in dependencies.items()})
    return datasets


def _dump_records(records: tuple[BaseModel, ...]) -> tuple[JsonValue, ...]:
    return tuple(cast(JsonValue, record.model_dump(mode="json")) for record in records)


def _bounded_context_datasets(
    datasets: Mapping[str, tuple[JsonValue, ...]],
    *,
    max_result_bytes: int,
) -> tuple[
    dict[str, tuple[JsonValue, ...]],
    dict[str, int],
    dict[str, int],
]:
    bounded: dict[str, tuple[JsonValue, ...]] = {}
    record_counts: dict[str, int] = {}
    fragmented_record_counts: dict[str, int] = {}
    for dataset, rows in datasets.items():
        record_counts[dataset] = len(rows)
        items: list[JsonValue] = []
        fragmented_count = 0
        for record_index, row in enumerate(rows):
            if isinstance(row, dict) and _CONTEXT_FRAGMENT_KEY in row:
                raise AgentContextUnavailableError()
            if _single_dataset_item_fits(
                dataset=dataset,
                item=row,
                max_result_bytes=max_result_bytes,
            ):
                items.append(row)
                continue
            items.extend(
                _fragment_dataset_record(
                    dataset=dataset,
                    record_index=record_index,
                    row=row,
                    max_result_bytes=max_result_bytes,
                )
            )
            fragmented_count += 1
        bounded[dataset] = tuple(items)
        if fragmented_count:
            fragmented_record_counts[dataset] = fragmented_count
    return bounded, record_counts, fragmented_record_counts


def _single_dataset_item_fits(
    *,
    dataset: str,
    item: JsonValue,
    max_result_bytes: int,
) -> bool:
    return (
        _json_bytes(
            _dataset_page(
                dataset=dataset,
                total_count=_PAGE_SIZE_SENTINEL,
                offset=_PAGE_SIZE_SENTINEL,
                items=[item],
                next_offset=_PAGE_SIZE_SENTINEL,
            )
        )
        <= max_result_bytes
    )


def _fragment_dataset_record(
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
        high = min(len(canonical_text) - position, max_result_bytes)
        accepted = 0
        while low <= high:
            midpoint = (low + high) // 2
            probe = _context_fragment(
                record_index=_PAGE_SIZE_SENTINEL,
                fragment_index=_PAGE_SIZE_SENTINEL,
                fragment_count=_PAGE_SIZE_SENTINEL,
                record_sha256=digest,
                json_text=canonical_text[position : position + midpoint],
            )
            if _single_dataset_item_fits(
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

    fragment_count = len(parts)
    fragments = tuple(
        _context_fragment(
            record_index=record_index,
            fragment_index=fragment_index,
            fragment_count=fragment_count,
            record_sha256=digest,
            json_text=part,
        )
        for fragment_index, part in enumerate(parts)
    )
    if not all(
        _single_dataset_item_fits(
            dataset=dataset,
            item=fragment,
            max_result_bytes=max_result_bytes,
        )
        for fragment in fragments
    ):
        raise AgentContextTooLargeError()
    return fragments


def _context_fragment(
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


def _dataset_page(
    *,
    dataset: str,
    total_count: int,
    offset: int,
    items: list[JsonValue],
    next_offset: int | None,
) -> JsonValue:
    return cast(
        JsonValue,
        {
            "dataset": dataset,
            "total_count": total_count,
            "offset": offset,
            "items": items,
            "next_offset": next_offset,
        },
    )


def _context_manifest(
    context: AgentAuthoringContext,
    datasets: Mapping[str, tuple[JsonValue, ...]],
    *,
    dataset_record_counts: Mapping[str, int],
    fragmented_record_counts: Mapping[str, int],
) -> dict[str, JsonValue]:
    selected_objects: list[JsonValue] = []
    for selected in context.selected_objects:
        selected_objects.append(
            cast(
                JsonValue,
                {
                    "selection_order": selected.selection_order,
                    "tenant_code": selected.object.tenant_code,
                    "system_code": selected.object.system_code,
                    "connection_code": selected.object.connection_code,
                    "object_schema": selected.object.object_schema,
                    "object_name": selected.object.object_name,
                    "zone_code": selected.object.zone_code,
                    "attribute_count": len(selected.attributes),
                },
            )
        )
    manifest: dict[str, JsonValue] = {
        "schema_version": "1.0",
        "model_name": context.model_name,
        "model_revision": context.model_revision,
        "model_workflow": context.model_workflow,
        "workflow_execution_mode": context.workflow_execution_mode,
        "modeled_entity_type": context.modeled_entity_type,
        "selected_scope_digest": context.selected_scope_digest,
        "selected_objects": selected_objects,
        "dataset_counts": {name: len(rows) for name, rows in datasets.items()},
        "dataset_record_counts": dict(dataset_record_counts),
        "dataset_count_semantics": {
            "dataset_counts": "retrieval_items_and_page_total_count",
            "dataset_record_counts": "source_records",
        },
    }
    if fragmented_record_counts:
        manifest["fragmented_record_counts"] = dict(fragmented_record_counts)
        manifest["fragment_contract"] = {
            "normal_item": f"JSON record without {_CONTEXT_FRAGMENT_KEY}",
            "fragment_marker_field": _CONTEXT_FRAGMENT_KEY,
            "encoding": _CONTEXT_FRAGMENT_ENCODING,
            "payload_field": "json_text",
            "reassembly_fields": [
                "record_index",
                "fragment_index",
                "fragment_count",
                "record_sha256",
            ],
            "reassembly": (
                "Group by record_index and record_sha256; require fragment_index 0 through "
                "fragment_count minus 1 exactly once; concatenate json_text in that order; "
                "verify the SHA-256 of its UTF-8 bytes; then parse the canonical JSON."
            ),
        }
    return manifest


def _compact_context_manifest(manifest: dict[str, JsonValue]) -> dict[str, JsonValue]:
    compact = deepcopy(manifest)
    compact.pop("selected_objects", None)
    compact["selected_objects_dataset"] = "selected_object"
    return compact


def _provider_context(context: AgentAuthoringContext) -> JsonValue:
    provider_context = cast(
        JsonValue,
        context.model_dump(
            mode="json",
            exclude={"workflow_run_id", "model_id"},
        ),
    )
    reject_forbidden_provider_json(provider_context)
    return provider_context


def _json_bytes(value: JsonValue) -> int:
    return len(_json_text(value).encode("utf-8"))


def _json_text(value: JsonValue) -> str:
    try:
        return json.dumps(
            value,
            ensure_ascii=False,
            allow_nan=False,
            separators=(",", ":"),
            sort_keys=True,
        )
    except (TypeError, ValueError):
        raise AgentContextUnavailableError() from None
