"""Process Groups resolved through one authorized Tenant's Copy Groups."""

from __future__ import annotations

from collections.abc import Mapping
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

type ActiveState = Literal["active", "inactive", "all"]
type ZoneCode = Literal["source", "bronze", "silver", "gold"]

_LIST_TOOL = "list_process_groups"
_GET_TOOL = "get_process_group"
_MAX_PROCESSES = 500
POLICY = ToolPolicy.TENANT_READ

_LIST_SQL: LiteralString = """
SELECT process_group.process_group_id,
       process_group.process_group_name,
       left(process_group.process_group_description, 2000)
           AS process_group_description,
       process_group.copy_group_id,
       copy_group.copy_group_name,
       system.system_id,
       system.system_code,
       system.system_name,
       zone.zone_code AS declared_zone,
       process_group.is_active,
       (SELECT count(*) FROM core.process
         WHERE process.process_group_id = process_group.process_group_id)
           AS process_count
  FROM core.copy_group
  JOIN core.process_group
    ON process_group.copy_group_id = copy_group.copy_group_id
   AND process_group.tenant_id = copy_group.tenant_id
   AND process_group.system_id = copy_group.system_id
  JOIN core.system ON system.system_id = process_group.system_id
  JOIN reference.zone ON zone.zone_id = process_group.zone_id
 WHERE copy_group.tenant_id = %s
   AND (%s::BIGINT IS NULL OR process_group.system_id = %s)
   AND (%s::VARCHAR IS NULL OR zone.zone_code = %s)
   AND (
       %s = 'all'
       OR (%s = 'active' AND process_group.is_active)
       OR (%s = 'inactive' AND NOT process_group.is_active)
   )
 ORDER BY lower(process_group.process_group_name), process_group.process_group_id
 LIMIT %s OFFSET %s
"""

_GROUP_SQL: LiteralString = """
SELECT process_group.process_group_id,
       process_group.process_group_name,
       left(process_group.process_group_description, 2000)
           AS process_group_description,
       process_group.copy_group_id,
       copy_group.copy_group_name,
       system.system_id,
       system.system_code,
       system.system_name,
       zone.zone_code AS declared_zone,
       process_group.is_active,
       (SELECT count(*) FROM core.process
         WHERE process.process_group_id = process_group.process_group_id)
           AS process_count
  FROM core.copy_group
  JOIN core.process_group
    ON process_group.copy_group_id = copy_group.copy_group_id
   AND process_group.tenant_id = copy_group.tenant_id
   AND process_group.system_id = copy_group.system_id
  JOIN core.system ON system.system_id = process_group.system_id
  JOIN reference.zone ON zone.zone_id = process_group.zone_id
 WHERE copy_group.tenant_id = %s
   AND process_group.process_group_id = %s
"""

_PROCESSES_SQL: LiteralString = """
SELECT process.process_id,
       process.process_execution_order,
       process.is_active,
       process_type.process_type_name,
       object.object_id,
       object.object_schema,
       object.object_name,
       object_zone.zone_code AS zone,
       connection.connection_id,
       connection.connection_code,
       connection.connection_name,
       owning_tenant.tenant_id AS owning_tenant_id,
       owning_tenant.tenant_name AS owning_tenant_name
  FROM core.copy_group
  JOIN core.process_group
    ON process_group.copy_group_id = copy_group.copy_group_id
   AND process_group.tenant_id = copy_group.tenant_id
   AND process_group.system_id = copy_group.system_id
  JOIN core.process ON process.process_group_id = process_group.process_group_id
  JOIN reference.process_type ON process_type.process_type_id = process.process_type_id
  JOIN core.object
    ON object.object_id = process.object_id
   AND object.connection_id = process.connection_id
  JOIN reference.zone AS object_zone ON object_zone.zone_id = object.zone_id
  JOIN core.connection ON connection.connection_id = process.connection_id
  JOIN core.tenant AS owning_tenant ON owning_tenant.tenant_id = connection.tenant_id
 WHERE copy_group.tenant_id = %s
   AND process_group.process_group_id = %s
 ORDER BY process.process_execution_order, process.process_id
 LIMIT 501
"""


class ContractModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class ProcessGroupSummary(ContractModel):
    process_group_id: int = Field(gt=0)
    process_group_name: str = Field(min_length=1, max_length=200)
    process_group_description: str | None = Field(default=None, max_length=2000)
    copy_group_id: int = Field(gt=0)
    copy_group_name: str = Field(min_length=1, max_length=200)
    system_id: int = Field(gt=0)
    system_code: str = Field(min_length=1, max_length=100)
    system_name: str = Field(min_length=1, max_length=200)
    declared_zone: ZoneCode
    process_count: int = Field(ge=0)
    is_active: bool


class ListProcessGroupsResult(ContractModel):
    schema_version: Literal["1.0"] = "1.0"
    tenant_id: int = Field(gt=0)
    process_groups: tuple[ProcessGroupSummary, ...] = Field(max_length=200)
    next_cursor: str | None = Field(default=None, max_length=2048)


class ProcessObjectReference(ContractModel):
    object_id: int = Field(gt=0)
    object_schema: str = Field(min_length=1, max_length=400)
    object_name: str = Field(min_length=1, max_length=400)
    zone: ZoneCode
    owning_tenant_id: int = Field(gt=0)
    owning_tenant_name: str = Field(min_length=1, max_length=200)


class ProcessDetails(ContractModel):
    process_id: int = Field(gt=0)
    process_execution_order: int = Field(gt=0)
    process_type_name: str = Field(min_length=1, max_length=200)
    object: ProcessObjectReference
    connection_id: int = Field(gt=0)
    connection_code: str = Field(min_length=1, max_length=100)
    connection_name: str = Field(min_length=1, max_length=200)
    is_active: bool


class GetProcessGroupResult(ContractModel):
    schema_version: Literal["1.0"] = "1.0"
    tenant_id: int = Field(gt=0)
    process_group: ProcessGroupSummary
    processes: tuple[ProcessDetails, ...] = Field(max_length=_MAX_PROCESSES)
    processes_truncated: bool


class SafeToolError(Exception):
    """A tool failure whose text is safe for the MCP SDK to serialize."""


def register_process_group_tools(
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
        description=(
            "List Process Groups reached through Copy Groups owned by one authorized Tenant."
        ),
        annotations=_annotations(),
        meta={"gds/toolPolicy": POLICY.value},
        structured_output=True,
    )
    async def list_process_groups(
        ctx: Context[None],
        tenant_id: Annotated[int, Field(gt=0)],
        system_id: Annotated[int | None, Field(gt=0)] = None,
        zone: ZoneCode | None = None,
        active_state: ActiveState = "active",
        page_size: Annotated[int, Field(ge=1, le=200)] = 50,
        cursor: Annotated[str | None, Field(max_length=2048)] = None,
        schema_version: Literal["1.0"] = "1.0",
    ) -> ListProcessGroupsResult:
        try:
            principal = identity_provider.request_principal(ctx.request_context.request)
            collection = f"{_LIST_TOOL}:{tenant_id}:{system_id or 0}:{zone or 'all'}:{active_state}"
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
                        zone,
                        zone,
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
            return ListProcessGroupsResult(
                tenant_id=tenant_id,
                process_groups=tuple(ProcessGroupSummary(**row) for row in rows[:page_size]),
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
            "Get one Process Group and its ordered Process/Object associations. Internal "
            "executable names and locations are never returned."
        ),
        annotations=_annotations(),
        meta={"gds/toolPolicy": POLICY.value},
        structured_output=True,
    )
    async def get_process_group(
        ctx: Context[None],
        tenant_id: Annotated[int, Field(gt=0)],
        process_group_id: Annotated[int, Field(gt=0)],
        schema_version: Literal["1.0"] = "1.0",
    ) -> GetProcessGroupResult:
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
                    (tenant_id, process_group_id),
                )
                if group is None:
                    raise InvalidRequestError("Process Group was not found.")
                rows = await transaction.fetch_all(
                    _PROCESSES_SQL,
                    (tenant_id, process_group_id),
                )
            return GetProcessGroupResult(
                tenant_id=tenant_id,
                process_group=ProcessGroupSummary(**group),
                processes=tuple(_process(row) for row in rows[:_MAX_PROCESSES]),
                processes_truncated=len(rows) > _MAX_PROCESSES,
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
            "zone",
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
        retain_arguments={"tenant_id", "process_group_id", "schema_version"},
        tenant_argument="tenant_id",
    )


def _annotations() -> ToolAnnotations:
    return ToolAnnotations(
        read_only_hint=True,
        destructive_hint=False,
        idempotent_hint=True,
        open_world_hint=False,
    )


def _process(row: Mapping[str, Any]) -> ProcessDetails:
    return ProcessDetails(
        process_id=row["process_id"],
        process_execution_order=row["process_execution_order"],
        process_type_name=row["process_type_name"],
        object=ProcessObjectReference(
            object_id=row["object_id"],
            object_schema=row["object_schema"],
            object_name=row["object_name"],
            zone=row["zone"],
            owning_tenant_id=row["owning_tenant_id"],
            owning_tenant_name=row["owning_tenant_name"],
        ),
        connection_id=row["connection_id"],
        connection_code=row["connection_code"],
        connection_name=row["connection_name"],
        is_active=row["is_active"],
    )


def _list_audit(arguments: Mapping[str, Any]) -> dict[str, str | int | bool]:
    zone = arguments.get("zone")
    active_state = arguments.get("active_state", "active")
    return {
        "tenant_id": _positive_int(arguments.get("tenant_id")),
        "system_filter_provided": arguments.get("system_id") is not None,
        "zone": (
            "all"
            if zone is None
            else zone
            if zone in {"source", "bronze", "silver", "gold"}
            else "invalid"
        ),
        "active_state": (
            active_state if active_state in {"active", "inactive", "all"} else "invalid"
        ),
        "page_size": _page_size(arguments.get("page_size", 50)),
        "cursor_provided": arguments.get("cursor") is not None,
    }


def _get_audit(arguments: Mapping[str, Any]) -> dict[str, str | int]:
    return {
        "tenant_id": _positive_int(arguments.get("tenant_id")),
        "process_group_id": _positive_int(arguments.get("process_group_id")),
    }


def _positive_int(value: object) -> int | str:
    return value if type(value) is int and value > 0 else "invalid"


def _page_size(value: object) -> int | str:
    return value if type(value) is int and 1 <= value <= 200 else "invalid"
