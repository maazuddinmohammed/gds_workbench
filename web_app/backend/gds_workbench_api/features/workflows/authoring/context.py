"""Bounded, read-only context for one frozen agent authoring run."""

from __future__ import annotations

import json
from collections.abc import Awaitable, Callable, Mapping
from copy import deepcopy
from dataclasses import dataclass, field
from typing import Any, Literal, LiteralString, cast

from gds_etl_workbench.domain.errors import WorkbenchError
from gds_etl_workbench.domain.metadata_records import AttributeRecord, ObjectRecord
from gds_etl_workbench.domain.modeling_records import (
    AnalysisResultRecord,
    ModelDetailsRecord,
    ProfilingProfileRecord,
    normalize_model_key_value,
)
from gds_etl_workbench.infrastructure.postgres import ReadTransaction
from gds_etl_workbench.tools.modeling.common import ModelReadContext
from gds_etl_workbench.tools.snapshots.model.contracts import (
    AssertionSection,
    ConceptualSection,
    DimensionalSection,
    LogicalSection,
    MappingSection,
    ModelSnapshot,
)
from gds_etl_workbench.tools.snapshots.model.selection import build_model_snapshot
from pydantic import BaseModel, ConfigDict, Field, JsonValue

from gds_workbench_api.features.assertions.contracts import validate_safe_json
from gds_workbench_api.features.workflows.authoring.agent_execution import (
    LocalAgentToolDefinition,
)

from .plan import AgentRunPlan, ModelWorkflow, WorkflowExecutionMode
from .repair import AgentContextTooLargeError, load_default_agent_context_policy

type SnapshotLoader = Callable[
    [ReadTransaction, ModelReadContext],
    Awaitable[ModelSnapshot],
]
type PhysicalObjectKey = tuple[str, str, str, str, str]

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
       tenant.tenant_code,
       system.system_code,
       connection.connection_code,
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
  JOIN core.tenant AS tenant
    ON tenant.tenant_id = eligibility.object_tenant_id
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
       tenant.tenant_code,
       system.system_code,
       connection.connection_code,
       object_record.object_schema,
       object_record.object_name,
       attribute.attribute_name,
       attribute.fc_attribute_name,
       attribute.attribute_ordinal_position,
       attribute.attribute_description,
       attribute.attribute_data_type,
       attribute.attribute_nullability,
       attribute.attribute_custom_code,
       attribute.is_surrogate_key,
       attribute.is_natural_key,
       attribute.is_meta_data,
       attribute.is_masking_required,
       attribute.is_mapped,
       attribute.is_purge,
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
  JOIN core.tenant AS tenant
    ON tenant.tenant_id = eligibility.object_tenant_id
  JOIN core.system AS system
    ON system.system_id = eligibility.system_id
 WHERE %s <> 'dimensional'
    OR eligibility.is_dimensional_source_eligible
 ORDER BY selected.selection_order,
          attribute.attribute_ordinal_position,
          attribute.attribute_id
 LIMIT %s
"""


class AgentContextUnavailableError(WorkbenchError):
    def __init__(self) -> None:
        super().__init__(
            code="agent_context_unavailable",
            message="The revision-fenced agent context is unavailable or incomplete.",
        )


class AgentContextToolRequestError(WorkbenchError):
    def __init__(self) -> None:
        super().__init__(
            code="agent_context_tool_request_invalid",
            message="The local agent context tool request is invalid.",
        )


class AgentContextToolResultTooLargeError(WorkbenchError):
    def __init__(self) -> None:
        super().__init__(
            code="agent_context_tool_result_too_large",
            message="The local agent context tool result exceeds its safe bound.",
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


class InMemoryAgentContextToolCatalog:
    """Page immutable preloaded records without database or external calls."""

    def __init__(
        self,
        *,
        context: AgentAuthoringContext,
        max_result_bytes: int,
        max_catalog_bytes: int,
        max_page_records: int,
    ) -> None:
        self._datasets = _context_datasets(context)
        self._max_result_bytes = max_result_bytes
        self._max_page_records = max_page_records
        self._definitions = (
            LocalAgentToolDefinition(
                name="get_agent_context_manifest",
                description="Return the immutable manifest for this Workflow Run context.",
                input_schema={
                    "type": "object",
                    "properties": {},
                    "additionalProperties": False,
                },
            ),
            LocalAgentToolDefinition(
                name="get_agent_context_dataset",
                description=(
                    "Return one bounded page from an immutable Workflow Run context dataset."
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
                        },
                    },
                    "required": ["dataset", "offset", "limit"],
                    "additionalProperties": False,
                },
            ),
        )
        self._manifest = _context_manifest(context, self._datasets)
        self._serialized_size_bytes = _json_bytes(
            cast(
                JsonValue,
                {
                    "manifest": self._manifest,
                    "datasets": {name: list(rows) for name, rows in self._datasets.items()},
                },
            )
        )
        if self._serialized_size_bytes > max_catalog_bytes:
            raise AgentContextTooLargeError()

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

    def invoke(
        self,
        tool_name: str,
        arguments: Mapping[str, JsonValue],
    ) -> JsonValue:
        if tool_name == "get_agent_context_manifest":
            if arguments:
                raise AgentContextToolRequestError()
            result = self.manifest
        elif tool_name == "get_agent_context_dataset":
            result = self._read_dataset(arguments)
        else:
            raise AgentContextToolRequestError()
        if _json_bytes(result) > self._max_result_bytes:
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
        return f"InMemoryAgentContextToolCatalog(datasets={len(self._datasets)})"


@dataclass(frozen=True, slots=True)
class AgentContextBundle:
    context: AgentAuthoringContext = field(repr=False)
    embedded_context: JsonValue = field(repr=False)
    tool_catalog: InMemoryAgentContextToolCatalog | None = field(default=None, repr=False)

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
        limits: AgentContextLimits | None = None,
    ) -> None:
        self._snapshot_loader = snapshot_loader
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
            context = _assemble_context(
                plan=plan,
                model=model,
                selected=selected,
                snapshot=snapshot,
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
                    max_result_bytes=self._limits.max_tool_result_bytes,
                    max_catalog_bytes=self._limits.max_tool_catalog_bytes,
                    max_page_records=self._limits.max_tool_page_records,
                )
                embedded = tool_catalog.manifest
            else:
                embedded = full_context
            byte_limit = (
                self._limits.one_shot_max_context_bytes
                if plan.workflow_execution_mode in (None, "one_shot")
                else self._limits.stage_max_context_bytes
            )
            if _json_bytes(embedded) > byte_limit:
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
            )
        except (AgentContextTooLargeError, AgentContextUnavailableError):
            raise
        except Exception:
            raise AgentContextUnavailableError() from None


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
    scope_keys = {_physical_key(item) for item in snapshot.model_scope.objects}
    if not selected_keys <= scope_keys:
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
        model_details=snapshot.model_scope.details,
        selected_objects=selected,
        profiles=profiles,
        analysis_relationships=analysis_relationships,
        assertion=AssertionSection(
            documents=assertion_documents,
            records=assertion_records,
        ),
        applied=applied,
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
    return datasets


def _dump_records(records: tuple[BaseModel, ...]) -> tuple[JsonValue, ...]:
    return tuple(cast(JsonValue, record.model_dump(mode="json")) for record in records)


def _context_manifest(
    context: AgentAuthoringContext,
    datasets: Mapping[str, tuple[JsonValue, ...]],
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
    return {
        "schema_version": "1.0",
        "model_name": context.model_name,
        "model_revision": context.model_revision,
        "model_workflow": context.model_workflow,
        "workflow_execution_mode": context.workflow_execution_mode,
        "modeled_entity_type": context.modeled_entity_type,
        "selected_scope_digest": context.selected_scope_digest,
        "selected_objects": selected_objects,
        "dataset_counts": {name: len(rows) for name, rows in datasets.items()},
    }


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
    try:
        return len(
            json.dumps(
                value,
                ensure_ascii=False,
                allow_nan=False,
                separators=(",", ":"),
                sort_keys=True,
            ).encode("utf-8")
        )
    except (TypeError, ValueError):
        raise AgentContextUnavailableError() from None
