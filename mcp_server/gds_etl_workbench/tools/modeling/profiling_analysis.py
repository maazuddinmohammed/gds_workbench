"""Applied Profiling and Analysis reads for one governed Model."""

# Pyright cannot see that @server.tool registers these nested handlers.
# pyright: reportUnusedFunction=false

from __future__ import annotations

from collections.abc import Mapping
from decimal import Decimal
from typing import TYPE_CHECKING, Annotated, Any, Literal, LiteralString

from pydantic import Field, model_validator

from gds_etl_workbench.adapters.auth.identity import AuthenticationError, IdentityProvider
from gds_etl_workbench.application.authorization import AuthorizationService
from gds_etl_workbench.application.cursor import CursorCodec
from gds_etl_workbench.domain.errors import WorkbenchError
from gds_etl_workbench.domain.modeling_records import ANALYSIS_VALIDATION_FIELDS
from gds_etl_workbench.infrastructure.postgres import Database, ReadIsolation

from .common import (
    MAX_OBJECT_FILTER,
    POLICY,
    ContractModel,
    ModelObjectSelection,
    authorize_model_read,
    summarize_model_object_input,
    validate_model_object_selection,
)

if TYPE_CHECKING:
    from mcp.server.mcpserver import Context, MCPServer

    from gds_etl_workbench.adapters.mcp.tool_audit import ToolCallAuditMiddleware

_MAX_PAGE_SIZE = 200

PROFILING_SQL: LiteralString = """
WITH requested_model AS (
    SELECT %s::BIGINT AS model_id
),
eligible_attributes AS MATERIALIZED (
    SELECT eligibility.*
      FROM requested_model
      CROSS JOIN LATERAL workflow.list_model_attribute_eligibility(
          requested_model.model_id
      ) AS eligibility
)
SELECT profile.object_id,
       tenant.tenant_code,
       system.system_code,
       connection.connection_code,
       object_record.object_schema,
       object_record.object_name,
       profile.attribute_id,
       attribute.attribute_name,
       profile.row_count,
       profile.non_null_count,
       profile.null_count,
       profile.blank_count,
       profile.distinct_count,
       profile.min_data_length,
       profile.max_data_length,
       profile.avg_data_length,
       profile.percent_populated,
       profile.percent_duplicates,
       profile.percent_null,
       profile.percent_blank,
       profile.percent_distinct
  FROM workflow.attribute_profile AS profile
  JOIN eligible_attributes AS eligible_attribute
    ON eligible_attribute.object_id = profile.object_id
   AND eligible_attribute.attribute_id = profile.attribute_id
   AND eligible_attribute.model_id = profile.model_id
   AND eligible_attribute.is_bronze_source_eligible
  JOIN core.object AS object_record
    ON object_record.object_id = profile.object_id
  JOIN core.connection AS connection
    ON connection.connection_id = object_record.connection_id
  JOIN core.tenant AS tenant
    ON tenant.tenant_id = eligible_attribute.object_tenant_id
  JOIN core.system AS system
    ON system.system_id = connection.system_id
  JOIN core.attribute AS attribute
    ON attribute.attribute_id = profile.attribute_id
   AND attribute.object_id = profile.object_id
 WHERE (
       cardinality(%s::BIGINT[]) = 0
       OR profile.object_id = ANY(%s::BIGINT[])
   )
 ORDER BY lower(object_record.object_schema),
          lower(object_record.object_name),
          attribute.attribute_ordinal_position,
          profile.attribute_id
 LIMIT %s OFFSET %s
"""

ANALYSIS_SQL: LiteralString = """
WITH requested_model AS (
    SELECT %s::BIGINT AS model_id
),
eligible_attributes AS MATERIALIZED (
    SELECT eligibility.*
      FROM requested_model
      CROSS JOIN LATERAL workflow.list_model_attribute_eligibility(
          requested_model.model_id
      ) AS eligibility
)
SELECT result.from_object_id,
       from_tenant.tenant_code AS from_tenant_code,
       from_system.system_code AS from_system_code,
       from_connection.connection_code AS from_connection_code,
       from_object.object_schema AS from_object_schema,
       from_object.object_name AS from_object_name,
       result.from_attribute_id,
       from_attribute.attribute_name AS from_attribute_name,
       result.to_object_id,
       to_tenant.tenant_code AS to_tenant_code,
       to_system.system_code AS to_system_code,
       to_connection.connection_code AS to_connection_code,
       to_object.object_schema AS to_object_schema,
       to_object.object_name AS to_object_name,
       result.to_attribute_id,
       to_attribute.attribute_name AS to_attribute_name,
       result.relationship_kind,
       result.relationship_confidence,
       result.relationship_basis,
       result.validation_policy_version,
       result.validation_result,
       result.validation_source_non_null_count,
       result.validation_source_distinct_count,
       result.validation_target_non_null_count,
       result.validation_target_distinct_count,
       result.validation_source_missing_target_count,
       result.validation_unused_target_count,
       result.validation_duplicate_target_key_count,
       result.analysis_result_status,
       result.analysis_result_is_locked
  FROM workflow.analysis_result AS result
  JOIN eligible_attributes AS eligible_from_attribute
    ON eligible_from_attribute.object_id = result.from_object_id
   AND eligible_from_attribute.attribute_id = result.from_attribute_id
   AND eligible_from_attribute.model_id = result.model_id
   AND eligible_from_attribute.is_bronze_source_eligible
  JOIN eligible_attributes AS eligible_to_attribute
    ON eligible_to_attribute.object_id = result.to_object_id
   AND eligible_to_attribute.attribute_id = result.to_attribute_id
   AND eligible_to_attribute.model_id = result.model_id
   AND eligible_to_attribute.is_bronze_source_eligible
  JOIN core.object AS from_object
    ON from_object.object_id = result.from_object_id
  JOIN core.connection AS from_connection
    ON from_connection.connection_id = from_object.connection_id
  JOIN core.tenant AS from_tenant
    ON from_tenant.tenant_id = eligible_from_attribute.object_tenant_id
  JOIN core.system AS from_system
    ON from_system.system_id = from_connection.system_id
  JOIN core.attribute AS from_attribute
    ON from_attribute.attribute_id = result.from_attribute_id
   AND from_attribute.object_id = result.from_object_id
  JOIN core.object AS to_object
    ON to_object.object_id = result.to_object_id
  JOIN core.connection AS to_connection
    ON to_connection.connection_id = to_object.connection_id
  JOIN core.tenant AS to_tenant
    ON to_tenant.tenant_id = eligible_to_attribute.object_tenant_id
  JOIN core.system AS to_system
    ON to_system.system_id = to_connection.system_id
  JOIN core.attribute AS to_attribute
    ON to_attribute.attribute_id = result.to_attribute_id
   AND to_attribute.object_id = result.to_object_id
 WHERE (
       cardinality(%s::BIGINT[]) = 0
       OR result.from_object_id = ANY(%s::BIGINT[])
       OR result.to_object_id = ANY(%s::BIGINT[])
   )
 ORDER BY result.from_object_id,
          result.from_attribute_id,
          result.to_object_id,
          result.to_attribute_id,
          lower(result.relationship_kind)
 LIMIT %s OFFSET %s
"""


class ProfileResult(ContractModel):
    object_id: int = Field(gt=0)
    tenant_code: str = Field(min_length=1, max_length=100)
    system_code: str = Field(min_length=1, max_length=100)
    connection_code: str = Field(min_length=1, max_length=100)
    object_schema: str = Field(min_length=1, max_length=400)
    object_name: str = Field(min_length=1, max_length=400)
    attribute_id: int = Field(gt=0)
    attribute_name: str = Field(min_length=1, max_length=400)
    row_count: int = Field(ge=0)
    non_null_count: int = Field(ge=0)
    null_count: int = Field(ge=0)
    blank_count: int | None = Field(default=None, ge=0)
    distinct_count: int | None = Field(default=None, ge=0)
    min_data_length: int | None = Field(default=None, ge=0)
    max_data_length: int | None = Field(default=None, ge=0)
    avg_data_length: Decimal | None = Field(default=None, ge=0)
    percent_populated: Decimal | None = Field(default=None, ge=0, le=100)
    percent_duplicates: Decimal | None = Field(default=None, ge=0, le=100)
    percent_null: Decimal | None = Field(default=None, ge=0, le=100)
    percent_blank: Decimal | None = Field(default=None, ge=0, le=100)
    percent_distinct: Decimal | None = Field(default=None, ge=0, le=100)


class GetModelProfilingResult(ContractModel):
    schema_version: Literal["1.0"] = "1.0"
    model_id: int = Field(gt=0)
    model_revision: int = Field(gt=0)
    profiles: tuple[ProfileResult, ...] = Field(max_length=_MAX_PAGE_SIZE)
    next_cursor: str | None = Field(default=None, max_length=2048)


class AnalysisRelationshipResult(ContractModel):
    from_object_id: int = Field(gt=0)
    from_tenant_code: str = Field(min_length=1, max_length=100)
    from_system_code: str = Field(min_length=1, max_length=100)
    from_connection_code: str = Field(min_length=1, max_length=100)
    from_object_schema: str = Field(min_length=1, max_length=400)
    from_object_name: str = Field(min_length=1, max_length=400)
    from_attribute_id: int = Field(gt=0)
    from_attribute_name: str = Field(min_length=1, max_length=400)
    to_object_id: int = Field(gt=0)
    to_tenant_code: str = Field(min_length=1, max_length=100)
    to_system_code: str = Field(min_length=1, max_length=100)
    to_connection_code: str = Field(min_length=1, max_length=100)
    to_object_schema: str = Field(min_length=1, max_length=400)
    to_object_name: str = Field(min_length=1, max_length=400)
    to_attribute_id: int = Field(gt=0)
    to_attribute_name: str = Field(min_length=1, max_length=400)
    relationship_kind: str = Field(min_length=1, max_length=100)
    relationship_confidence: Literal["low", "medium", "high"]
    relationship_basis: str = Field(min_length=1)
    validation_policy_version: str | None = Field(
        default=None,
        min_length=1,
        max_length=50,
        pattern=r"^[0-9]+\.[0-9]+\.[0-9]+$",
    )
    validation_result: Literal["supported", "inconclusive", "unsupported"] | None = None
    validation_source_non_null_count: int | None = Field(default=None, ge=0)
    validation_source_distinct_count: int | None = Field(default=None, ge=0)
    validation_target_non_null_count: int | None = Field(default=None, ge=0)
    validation_target_distinct_count: int | None = Field(default=None, ge=0)
    validation_source_missing_target_count: int | None = Field(default=None, ge=0)
    validation_unused_target_count: int | None = Field(default=None, ge=0)
    validation_duplicate_target_key_count: int | None = Field(default=None, ge=0)
    analysis_result_status: Literal["active", "needs_review", "inactive", "deprecated"]
    analysis_result_is_locked: bool

    @model_validator(mode="after")
    def validate_validation_fields(self) -> AnalysisRelationshipResult:
        values = tuple(getattr(self, field) for field in ANALYSIS_VALIDATION_FIELDS)
        if any(value is None for value in values) and not all(value is None for value in values):
            raise ValueError("Analysis validation fields must all be present or all be absent.")
        return self


class GetModelAnalysisResult(ContractModel):
    schema_version: Literal["1.0"] = "1.0"
    model_id: int = Field(gt=0)
    model_revision: int = Field(gt=0)
    from_relationships: tuple[AnalysisRelationshipResult, ...] = Field(max_length=_MAX_PAGE_SIZE)
    to_relationships: tuple[AnalysisRelationshipResult, ...] = Field(max_length=_MAX_PAGE_SIZE)
    next_cursor: str | None = Field(default=None, max_length=2048)


class ModelingReadToolError(Exception):
    """A bounded Model-read failure safe for MCP serialization."""


def register_profiling_analysis_tools(
    server: MCPServer[None],
    *,
    database: Database,
    identity_provider: IdentityProvider,
    authorizer: AuthorizationService,
    audit: ToolCallAuditMiddleware,
    cursor_signing_key: bytes,
) -> None:
    from mcp.server.mcpserver import Context as McpContext
    from mcp.types import ToolAnnotations

    globals()["Context"] = McpContext
    cursors = CursorCodec(cursor_signing_key)

    @server.tool(
        description=(
            "Get applied Attribute Profiles for one Model. An empty Object-ID list "
            "selects the complete bounded Model collection."
        ),
        annotations=ToolAnnotations(
            read_only_hint=True,
            destructive_hint=False,
            idempotent_hint=True,
            open_world_hint=False,
        ),
        meta={"gds/toolPolicy": POLICY.value},
        structured_output=True,
    )
    async def get_model_profiling(
        ctx: Context[None],
        model_id: Annotated[int, Field(gt=0)],
        object_ids: Annotated[tuple[int, ...], Field(max_length=MAX_OBJECT_FILTER)] = (),
        page_size: Annotated[int, Field(ge=1, le=_MAX_PAGE_SIZE)] = 50,
        cursor: Annotated[str | None, Field(max_length=2048)] = None,
        schema_version: Literal["1.0"] = "1.0",
    ) -> GetModelProfilingResult:
        del schema_version
        try:
            request = ModelObjectSelection(model_id=model_id, object_ids=object_ids)
            collection = _collection_name("get_model_profiling", request, page_size)
            offset = cursors.decode(cursor, collection=collection)
            principal = identity_provider.request_principal(ctx.request_context.request)
            async with database.read_transaction(
                isolation=ReadIsolation.REPEATABLE_READ
            ) as transaction:
                model = await authorize_model_read(
                    transaction,
                    authorizer=authorizer,
                    principal=principal,
                    model_id=request.model_id,
                )
                await validate_model_object_selection(
                    transaction,
                    model_id=model.model_id,
                    object_ids=request.object_ids,
                )
                rows = await transaction.fetch_all(
                    PROFILING_SQL,
                    (
                        model.model_id,
                        list(request.object_ids),
                        list(request.object_ids),
                        page_size + 1,
                        offset,
                    ),
                )
            next_cursor = _next_cursor(
                cursors,
                collection=collection,
                offset=offset,
                page_size=page_size,
                row_count=len(rows),
            )
            return GetModelProfilingResult(
                model_id=model.model_id,
                model_revision=model.model_revision,
                profiles=tuple(ProfileResult(**row) for row in rows[:page_size]),
                next_cursor=next_cursor,
            )
        except AuthenticationError as error:
            raise ModelingReadToolError(f"{error.public_code}: {error.message}") from None
        except WorkbenchError as error:
            raise ModelingReadToolError(f"{error.code}: {error.message}") from None
        except Exception:
            raise ModelingReadToolError(
                "internal_error: The operation could not be completed."
            ) from None

    @server.tool(
        description=(
            "Get applied Analysis relationships for one Model, divided by whether the "
            "selected physical Objects are the from or to endpoint. An empty Object-ID "
            "list selects all rows in both directional collections."
        ),
        annotations=ToolAnnotations(
            read_only_hint=True,
            destructive_hint=False,
            idempotent_hint=True,
            open_world_hint=False,
        ),
        meta={"gds/toolPolicy": POLICY.value},
        structured_output=True,
    )
    async def get_model_analysis(
        ctx: Context[None],
        model_id: Annotated[int, Field(gt=0)],
        object_ids: Annotated[tuple[int, ...], Field(max_length=MAX_OBJECT_FILTER)] = (),
        page_size: Annotated[int, Field(ge=1, le=_MAX_PAGE_SIZE)] = 50,
        cursor: Annotated[str | None, Field(max_length=2048)] = None,
        schema_version: Literal["1.0"] = "1.0",
    ) -> GetModelAnalysisResult:
        del schema_version
        try:
            request = ModelObjectSelection(model_id=model_id, object_ids=object_ids)
            collection = _collection_name("get_model_analysis", request, page_size)
            offset = cursors.decode(cursor, collection=collection)
            principal = identity_provider.request_principal(ctx.request_context.request)
            async with database.read_transaction(
                isolation=ReadIsolation.REPEATABLE_READ
            ) as transaction:
                model = await authorize_model_read(
                    transaction,
                    authorizer=authorizer,
                    principal=principal,
                    model_id=request.model_id,
                )
                await validate_model_object_selection(
                    transaction,
                    model_id=model.model_id,
                    object_ids=request.object_ids,
                )
                rows = await transaction.fetch_all(
                    ANALYSIS_SQL,
                    (
                        model.model_id,
                        list(request.object_ids),
                        list(request.object_ids),
                        list(request.object_ids),
                        page_size + 1,
                        offset,
                    ),
                )
            selected = set(request.object_ids)
            page = rows[:page_size]
            relationships = tuple(AnalysisRelationshipResult(**row) for row in page)
            return GetModelAnalysisResult(
                model_id=model.model_id,
                model_revision=model.model_revision,
                from_relationships=tuple(
                    relationship
                    for relationship in relationships
                    if not selected or relationship.from_object_id in selected
                ),
                to_relationships=tuple(
                    relationship
                    for relationship in relationships
                    if not selected or relationship.to_object_id in selected
                ),
                next_cursor=_next_cursor(
                    cursors,
                    collection=collection,
                    offset=offset,
                    page_size=page_size,
                    row_count=len(rows),
                ),
            )
        except AuthenticationError as error:
            raise ModelingReadToolError(f"{error.public_code}: {error.message}") from None
        except WorkbenchError as error:
            raise ModelingReadToolError(f"{error.code}: {error.message}") from None
        except Exception:
            raise ModelingReadToolError(
                "internal_error: The operation could not be completed."
            ) from None

    for tool_name in ("get_model_profiling", "get_model_analysis"):
        audit.register_tool(
            tool_name,
            policy=POLICY,
            summarize_input=_audit_input,
            retain_arguments={"model_id", "page_size", "schema_version"},
        )


def _collection_name(
    tool_name: str,
    request: ModelObjectSelection,
    page_size: int,
) -> str:
    object_filter = ",".join(str(object_id) for object_id in request.object_ids)
    return f"{tool_name}:{request.model_id}:{object_filter}:{page_size}"


def _next_cursor(
    cursors: CursorCodec,
    *,
    collection: str,
    offset: int,
    page_size: int,
    row_count: int,
) -> str | None:
    if row_count <= page_size:
        return None
    return cursors.encode(collection=collection, offset=offset + page_size)


def _audit_input(arguments: Mapping[str, Any]) -> dict[str, str | int | bool]:
    metadata = summarize_model_object_input(arguments)
    page_size = arguments.get("page_size", 50)
    return {
        **metadata,
        "page_size": (
            page_size if type(page_size) is int and 1 <= page_size <= _MAX_PAGE_SIZE else "invalid"
        ),
        "cursor_provided": arguments.get("cursor") is not None,
    }
