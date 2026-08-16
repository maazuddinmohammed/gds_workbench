"""Tenant-owned Copy Group summary and bounded detail tools."""

from __future__ import annotations

from collections.abc import Mapping
from datetime import date, datetime
from typing import Annotated, Any, Literal, LiteralString

from mcp.server.mcpserver import Context, MCPServer
from mcp.types import ToolAnnotations
from pydantic import BaseModel, ConfigDict, Field

from gds_etl_workbench.adapters.auth.identity import AuthenticationError, IdentityProvider
from gds_etl_workbench.adapters.mcp.tool_audit import ToolCallAuditMiddleware
from gds_etl_workbench.application.authorization import AuthorizationService
from gds_etl_workbench.application.cursor import CursorCodec
from gds_etl_workbench.domain.authorization import ToolPolicy
from gds_etl_workbench.domain.errors import InvalidRequestError, WorkbenchError
from gds_etl_workbench.infrastructure.postgres import Database, ReadIsolation
from gds_etl_workbench.tools.catalog.visibility import VISIBLE_OBJECTS_CTE

type ActiveState = Literal["active", "inactive", "all"]
type ZoneCode = Literal["source", "bronze", "silver", "gold"]

_LIST_TOOL = "list_copy_groups"
_GET_TOOL = "get_copy_group"
_MAX_DETAILS = 200
POLICY = ToolPolicy.TENANT_READ

_LIST_SQL: LiteralString = """
SELECT copy_group.copy_group_id,
       copy_group.copy_group_name,
       left(copy_group.copy_group_description, 2000) AS copy_group_description,
       copy_group.is_member_group_required,
       copy_group.is_active,
       system.system_id,
       system.system_code,
       system.system_name,
       (SELECT count(*) FROM core.copy
         WHERE copy.copy_group_id = copy_group.copy_group_id) AS copy_count,
       (SELECT count(*) FROM core.copy_group_control AS control
         WHERE control.copy_group_id = copy_group.copy_group_id) AS control_count,
       (SELECT count(*) FROM core.process_group
         WHERE process_group.copy_group_id = copy_group.copy_group_id
           AND process_group.tenant_id = copy_group.tenant_id
           AND process_group.system_id = copy_group.system_id) AS process_group_count
  FROM core.copy_group
  JOIN core.system ON system.system_id = copy_group.system_id
 WHERE copy_group.tenant_id = %s
   AND (%s::BIGINT IS NULL OR copy_group.system_id = %s)
   AND (
       %s = 'all'
       OR (%s = 'active' AND copy_group.is_active)
       OR (%s = 'inactive' AND NOT copy_group.is_active)
   )
 ORDER BY lower(copy_group.copy_group_name), copy_group.copy_group_id
 LIMIT %s OFFSET %s
"""

_GROUP_SQL: LiteralString = """
SELECT copy_group.copy_group_id,
       copy_group.copy_group_name,
       left(copy_group.copy_group_description, 2000) AS copy_group_description,
       copy_group.is_member_group_required,
       copy_group.is_active,
       system.system_id,
       system.system_code,
       system.system_name,
       (SELECT count(*) FROM core.copy
         WHERE copy.copy_group_id = copy_group.copy_group_id) AS copy_count,
       (SELECT count(*) FROM core.copy_group_control AS control
         WHERE control.copy_group_id = copy_group.copy_group_id) AS control_count,
       (SELECT count(*) FROM core.process_group
         WHERE process_group.copy_group_id = copy_group.copy_group_id
           AND process_group.tenant_id = copy_group.tenant_id
           AND process_group.system_id = copy_group.system_id) AS process_group_count
  FROM core.copy_group
  JOIN core.system ON system.system_id = copy_group.system_id
 WHERE copy_group.tenant_id = %s
   AND copy_group.copy_group_id = %s
"""

_COPIES_SQL: LiteralString = f"""
{VISIBLE_OBJECTS_CTE}
SELECT copy.copy_id,
       copy.copy_source_order,
       copy.copy_source_record_limit,
       copy.copy_source_record_limit_attribute,
       chunk_type.chunk_type_name,
       file_type.file_type_name,
       source_operation.data_operation_name AS source_data_operation_name,
       target_operation.data_operation_name AS target_data_operation_name,
       copy.copy_source_initial_sql_script IS NOT NULL AS has_initial_sql,
       copy.copy_source_incremental_sql_script IS NOT NULL AS has_incremental_sql,
       copy.copy_source_file_name IS NOT NULL AS has_file_source,
       copy.is_active,
       mapping.ingestion_object_mapping_id,
       source_object.object_id AS source_object_id,
       source_object.object_schema AS source_object_schema,
       source_object.object_name AS source_object_name,
       source_zone.zone_code AS source_zone,
       target_object.object_id AS target_object_id,
       target_object.object_schema AS target_object_schema,
       target_object.object_name AS target_object_name,
       target_zone.zone_code AS target_zone
  FROM core.copy
  JOIN core.copy_group
    ON copy_group.copy_group_id = copy.copy_group_id
   AND copy_group.tenant_id = %s
   AND copy_group.copy_group_id = %s
  JOIN core.ingestion_object_mapping AS mapping
    ON mapping.ingestion_object_mapping_id = copy.ingestion_object_mapping_id
  JOIN visible_objects AS source_visible
    ON source_visible.object_id = mapping.source_object_id
  JOIN visible_objects AS target_visible
    ON target_visible.object_id = mapping.target_object_id
  JOIN core.object AS source_object ON source_object.object_id = mapping.source_object_id
  JOIN reference.zone AS source_zone ON source_zone.zone_id = source_object.zone_id
  JOIN core.object AS target_object ON target_object.object_id = mapping.target_object_id
  JOIN reference.zone AS target_zone ON target_zone.zone_id = target_object.zone_id
  LEFT JOIN reference.chunk_type ON chunk_type.chunk_type_id = copy.chunk_type_id
  LEFT JOIN reference.file_type ON file_type.file_type_id = copy.source_file_type_id
  JOIN reference.data_operation AS source_operation
    ON source_operation.data_operation_id = copy.source_data_operation_id
  JOIN reference.data_operation AS target_operation
    ON target_operation.data_operation_id = copy.target_data_operation_id
 ORDER BY copy.copy_source_order, copy.copy_id
 LIMIT 201
"""

_CONTROLS_SQL: LiteralString = """
SELECT control.copy_group_control_id,
       control.member_group_id,
       member_group.member_group_name,
       left(member_group.member_group_description, 2000) AS member_group_description,
       member_group.member_group_initial_load_date,
       member_group.is_active AS member_group_is_active,
       control.copy_group_control_initial_load_date,
       control.copy_group_control_last_run_time,
       control.copy_group_control_last_run_value IS NOT NULL AS has_last_run_value
  FROM core.copy_group_control AS control
  JOIN core.copy_group
    ON copy_group.copy_group_id = control.copy_group_id
   AND copy_group.tenant_id = control.tenant_id
   AND copy_group.system_id = control.system_id
  LEFT JOIN core.member_group
    ON member_group.member_group_id = control.member_group_id
   AND member_group.tenant_id = control.tenant_id
   AND member_group.system_id = control.system_id
 WHERE copy_group.tenant_id = %s
   AND copy_group.copy_group_id = %s
 ORDER BY control.copy_group_control_id
 LIMIT 201
"""


class ContractModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class CopyGroupSummary(ContractModel):
    copy_group_id: int = Field(gt=0)
    copy_group_name: str = Field(min_length=1, max_length=200)
    copy_group_description: str | None = Field(default=None, max_length=2000)
    system_id: int = Field(gt=0)
    system_code: str = Field(min_length=1, max_length=100)
    system_name: str = Field(min_length=1, max_length=200)
    is_member_group_required: bool
    copy_count: int = Field(ge=0)
    control_count: int = Field(ge=0)
    process_group_count: int = Field(ge=0)
    is_active: bool


class ListCopyGroupsResult(ContractModel):
    schema_version: Literal["1.0"] = "1.0"
    tenant_id: int = Field(gt=0)
    copy_groups: tuple[CopyGroupSummary, ...] = Field(max_length=200)
    next_cursor: str | None = Field(default=None, max_length=2048)


class CopyObjectReference(ContractModel):
    object_id: int = Field(gt=0)
    object_schema: str = Field(min_length=1, max_length=400)
    object_name: str = Field(min_length=1, max_length=400)
    zone: ZoneCode


class CopyDetails(ContractModel):
    copy_id: int = Field(gt=0)
    copy_source_order: int = Field(gt=0)
    ingestion_object_mapping_id: int = Field(gt=0)
    source_object: CopyObjectReference
    target_object: CopyObjectReference
    copy_source_record_limit: int | None = Field(default=None, ge=0)
    copy_source_record_limit_attribute: str | None = Field(default=None, max_length=400)
    chunk_type_name: str | None = Field(default=None, max_length=200)
    file_type_name: str | None = Field(default=None, max_length=200)
    source_data_operation_name: str = Field(min_length=1, max_length=200)
    target_data_operation_name: str = Field(min_length=1, max_length=200)
    has_initial_sql: bool
    has_incremental_sql: bool
    has_file_source: bool
    is_active: bool


class CopyGroupControlDetails(ContractModel):
    copy_group_control_id: int = Field(gt=0)
    member_group_id: int | None = Field(default=None, gt=0)
    member_group_name: str | None = Field(default=None, max_length=200)
    member_group_description: str | None = Field(default=None, max_length=2000)
    member_group_initial_load_date: date | None
    member_group_is_active: bool | None
    copy_group_control_initial_load_date: date | None
    copy_group_control_last_run_time: datetime | None
    has_last_run_value: bool


class GetCopyGroupResult(ContractModel):
    schema_version: Literal["1.0"] = "1.0"
    tenant_id: int = Field(gt=0)
    copy_group: CopyGroupSummary
    copies: tuple[CopyDetails, ...] = Field(max_length=_MAX_DETAILS)
    copies_truncated: bool
    controls: tuple[CopyGroupControlDetails, ...] = Field(max_length=_MAX_DETAILS)
    controls_truncated: bool


class SafeToolError(Exception):
    """A tool failure whose text is safe for the MCP SDK to serialize."""


def register_copy_group_tools(
    server: MCPServer[None],
    *,
    database: Database,
    identity_provider: IdentityProvider,
    authorizer: AuthorizationService,
    audit: ToolCallAuditMiddleware,
    cursor_signing_key: bytes,
) -> None:
    cursors = CursorCodec(cursor_signing_key)

    @server.tool(
        description="List Copy Groups owned by one authorized Tenant.",
        annotations=_annotations(),
        meta={"gds/toolPolicy": POLICY.value},
        structured_output=True,
    )
    async def list_copy_groups(
        ctx: Context[None],
        tenant_id: Annotated[int, Field(gt=0)],
        system_id: Annotated[int | None, Field(gt=0)] = None,
        active_state: ActiveState = "active",
        page_size: Annotated[int, Field(ge=1, le=200)] = 50,
        cursor: Annotated[str | None, Field(max_length=2048)] = None,
        schema_version: Literal["1.0"] = "1.0",
    ) -> ListCopyGroupsResult:
        try:
            principal = identity_provider.request_principal(ctx.request_context.request)
            collection = f"{_LIST_TOOL}:{tenant_id}:{system_id or 0}:{active_state}"
            offset = cursors.decode(cursor, collection=collection)
            async with database.read_transaction(
                isolation=ReadIsolation.REPEATABLE_READ
            ) as transaction:
                await authorizer.authorize_tenant(
                    transaction, principal, tenant_id=tenant_id, policy=POLICY
                )
                rows = await transaction.fetch_all(
                    _LIST_SQL,
                    (
                        tenant_id,
                        system_id,
                        system_id,
                        active_state,
                        active_state,
                        active_state,
                        page_size + 1,
                        offset,
                    ),
                )
            next_cursor = (
                cursors.encode(collection=collection, offset=offset + page_size)
                if len(rows) > page_size
                else None
            )
            return ListCopyGroupsResult(
                tenant_id=tenant_id,
                copy_groups=tuple(CopyGroupSummary(**row) for row in rows[:page_size]),
                next_cursor=next_cursor,
            )
        except AuthenticationError as error:
            raise SafeToolError(f"{error.public_code}: {error.message}") from None
        except WorkbenchError as error:
            raise SafeToolError(f"{error.code}: {error.message}") from None
        except Exception:
            raise SafeToolError("internal_error: The operation could not be completed.") from None

    @server.tool(
        description=(
            "Get one Tenant-owned Copy Group with bounded Copies and Controls. "
            "SQL scripts and raw checkpoint values are never returned."
        ),
        annotations=_annotations(),
        meta={"gds/toolPolicy": POLICY.value},
        structured_output=True,
    )
    async def get_copy_group(
        ctx: Context[None],
        tenant_id: Annotated[int, Field(gt=0)],
        copy_group_id: Annotated[int, Field(gt=0)],
        schema_version: Literal["1.0"] = "1.0",
    ) -> GetCopyGroupResult:
        try:
            principal = identity_provider.request_principal(ctx.request_context.request)
            async with database.read_transaction(
                isolation=ReadIsolation.REPEATABLE_READ
            ) as transaction:
                await authorizer.authorize_tenant(
                    transaction, principal, tenant_id=tenant_id, policy=POLICY
                )
                group = await transaction.fetch_one(
                    _GROUP_SQL,
                    (tenant_id, copy_group_id),
                )
                if group is None:
                    raise InvalidRequestError("Copy Group was not found.")
                copy_rows = await transaction.fetch_all(
                    _COPIES_SQL,
                    (tenant_id, tenant_id, copy_group_id),
                )
                control_rows = await transaction.fetch_all(
                    _CONTROLS_SQL,
                    (tenant_id, copy_group_id),
                )
            return GetCopyGroupResult(
                tenant_id=tenant_id,
                copy_group=CopyGroupSummary(**group),
                copies=tuple(_copy(row) for row in copy_rows[:_MAX_DETAILS]),
                copies_truncated=len(copy_rows) > _MAX_DETAILS,
                controls=tuple(
                    CopyGroupControlDetails(**row) for row in control_rows[:_MAX_DETAILS]
                ),
                controls_truncated=len(control_rows) > _MAX_DETAILS,
            )
        except AuthenticationError as error:
            raise SafeToolError(f"{error.public_code}: {error.message}") from None
        except WorkbenchError as error:
            raise SafeToolError(f"{error.code}: {error.message}") from None
        except Exception:
            raise SafeToolError("internal_error: The operation could not be completed.") from None

    audit.register_tool(
        _LIST_TOOL,
        policy=POLICY,
        summarize_input=_list_audit,
        retain_arguments={
            "tenant_id",
            "system_id",
            "active_state",
            "page_size",
            "schema_version",
        },
        tenant_argument="tenant_id",
    )
    audit.register_tool(
        _GET_TOOL,
        policy=POLICY,
        summarize_input=_get_audit,
        retain_arguments={"tenant_id", "copy_group_id", "schema_version"},
        tenant_argument="tenant_id",
    )


def _annotations() -> ToolAnnotations:
    return ToolAnnotations(
        read_only_hint=True,
        destructive_hint=False,
        idempotent_hint=True,
        open_world_hint=False,
    )


def _copy(row: Mapping[str, Any]) -> CopyDetails:
    return CopyDetails(
        copy_id=row["copy_id"],
        copy_source_order=row["copy_source_order"],
        ingestion_object_mapping_id=row["ingestion_object_mapping_id"],
        source_object=_copy_object(row, prefix="source"),
        target_object=_copy_object(row, prefix="target"),
        copy_source_record_limit=row["copy_source_record_limit"],
        copy_source_record_limit_attribute=row["copy_source_record_limit_attribute"],
        chunk_type_name=row["chunk_type_name"],
        file_type_name=row["file_type_name"],
        source_data_operation_name=row["source_data_operation_name"],
        target_data_operation_name=row["target_data_operation_name"],
        has_initial_sql=row["has_initial_sql"],
        has_incremental_sql=row["has_incremental_sql"],
        has_file_source=row["has_file_source"],
        is_active=row["is_active"],
    )


def _copy_object(
    row: Mapping[str, Any], *, prefix: Literal["source", "target"]
) -> CopyObjectReference:
    return CopyObjectReference(
        object_id=row[f"{prefix}_object_id"],
        object_schema=row[f"{prefix}_object_schema"],
        object_name=row[f"{prefix}_object_name"],
        zone=row[f"{prefix}_zone"],
    )


def _list_audit(arguments: Mapping[str, Any]) -> dict[str, str | int | bool]:
    active_state = arguments.get("active_state", "active")
    return {
        "tenant_id": _positive_int(arguments.get("tenant_id")),
        "system_filter_provided": arguments.get("system_id") is not None,
        "active_state": (
            active_state if active_state in {"active", "inactive", "all"} else "invalid"
        ),
        "page_size": _page_size(arguments.get("page_size", 50)),
        "cursor_provided": arguments.get("cursor") is not None,
    }


def _get_audit(arguments: Mapping[str, Any]) -> dict[str, str | int]:
    return {
        "tenant_id": _positive_int(arguments.get("tenant_id")),
        "copy_group_id": _positive_int(arguments.get("copy_group_id")),
    }


def _positive_int(value: object) -> int | str:
    return value if type(value) is int and value > 0 else "invalid"


def _page_size(value: object) -> int | str:
    return value if type(value) is int and 1 <= value <= 200 else "invalid"
