"""Paginated physical Object summaries for one authorized Tenant and Zone."""

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
from gds_etl_workbench.domain.errors import WorkbenchError
from gds_etl_workbench.infrastructure.postgres import Database, ReadIsolation

from .visibility import VISIBLE_OBJECTS_CTE

type ZoneCode = Literal["source", "bronze", "silver", "gold"]
type ActiveState = Literal["active", "inactive", "all"]

_TOOL_NAME = "list_objects"
POLICY = ToolPolicy.TENANT_READ

_LIST_OBJECTS_SQL: LiteralString = f"""
{VISIBLE_OBJECTS_CTE}
SELECT object.object_id,
       object.object_schema,
       object.object_name,
       left(object.object_description, 2000) AS object_description,
       object_type.object_type_code,
       object_type.object_type_name,
       zone.zone_code AS zone,
       connection.connection_id,
       connection.connection_code,
       connection.connection_name,
       system.system_id,
       system.system_code,
       system.system_name,
       (
           SELECT count(*)
             FROM core.attribute
            WHERE attribute.object_id = object.object_id
       ) AS attribute_count,
       EXISTS (
           SELECT 1
             FROM core.ingestion_object_mapping AS mapping
             JOIN visible_objects AS source_visible
               ON source_visible.object_id = mapping.source_object_id
             JOIN visible_objects AS target_visible
               ON target_visible.object_id = mapping.target_object_id
            WHERE mapping.source_object_id = object.object_id
               OR mapping.target_object_id = object.object_id
       ) AS has_ingestion_mapping,
       visible_objects.is_owned_by_tenant,
       visible_objects.is_discovered_by_scope,
       visible_objects.is_copy_referenced,
       visible_objects.is_process_referenced,
       visible_objects.is_model_scope_referenced,
       object.is_active
  FROM visible_objects
  JOIN core.object AS object ON object.object_id = visible_objects.object_id
  JOIN reference.object_type AS object_type
    ON object_type.object_type_id = object.object_type_id
  JOIN reference.zone AS zone ON zone.zone_id = object.zone_id
  JOIN core.connection AS connection
    ON connection.connection_id = object.connection_id
  JOIN core.system AS system ON system.system_id = connection.system_id
 WHERE zone.zone_code = %s
   AND (%s::BIGINT IS NULL OR connection.connection_id = %s)
   AND (
       %s = 'all'
       OR (%s = 'active' AND object.is_active)
       OR (%s = 'inactive' AND NOT object.is_active)
   )
 ORDER BY lower(object.object_schema), lower(object.object_name), object.object_id
 LIMIT %s OFFSET %s
"""


class ContractModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class ObjectSummary(ContractModel):
    object_id: int = Field(gt=0)
    object_schema: str = Field(min_length=1, max_length=400)
    object_name: str = Field(min_length=1, max_length=400)
    object_description: str | None = Field(default=None, max_length=2000)
    object_type_code: str = Field(min_length=1, max_length=100)
    object_type_name: str = Field(min_length=1, max_length=200)
    zone: ZoneCode
    connection_id: int = Field(gt=0)
    connection_code: str = Field(min_length=1, max_length=100)
    connection_name: str = Field(min_length=1, max_length=200)
    system_id: int = Field(gt=0)
    system_code: str = Field(min_length=1, max_length=100)
    system_name: str = Field(min_length=1, max_length=200)
    attribute_count: int = Field(ge=0)
    has_ingestion_mapping: bool
    is_owned_by_tenant: bool
    is_discovered_by_scope: bool
    is_copy_referenced: bool
    is_process_referenced: bool
    is_model_scope_referenced: bool
    is_active: bool


class ListObjectsResult(ContractModel):
    schema_version: Literal["1.0"] = "1.0"
    tenant_id: int = Field(gt=0)
    zone: ZoneCode
    objects: tuple[ObjectSummary, ...] = Field(max_length=200)
    next_cursor: str | None = Field(default=None, max_length=2048)


class SafeToolError(Exception):
    """A tool failure whose text is safe for the MCP SDK to serialize."""


def register_list_objects_tool(
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
        name=_TOOL_NAME,
        description=(
            "List authorized physical Objects for one Tenant and exact Source, Bronze, "
            "Silver, or Gold Zone. Results explain their Tenant inclusion and whether "
            "an ingestion mapping exists."
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
    async def _list_objects(
        ctx: Context[None],
        tenant_id: Annotated[int, Field(gt=0)],
        zone: ZoneCode,
        connection_id: Annotated[int | None, Field(gt=0)] = None,
        active_state: ActiveState = "active",
        page_size: Annotated[int, Field(ge=1, le=200)] = 50,
        cursor: Annotated[str | None, Field(max_length=2048)] = None,
        schema_version: Literal["1.0"] = "1.0",
    ) -> ListObjectsResult:
        try:
            principal = identity_provider.request_principal(ctx.request_context.request)
            collection = f"{_TOOL_NAME}:{tenant_id}:{zone}:{connection_id or 0}:{active_state}"
            offset = cursors.decode(cursor, collection=collection)
            async with database.read_transaction(
                isolation=ReadIsolation.REPEATABLE_READ
            ) as transaction:
                await authorizer.authorize_tenant(
                    transaction,
                    principal,
                    tenant_id=tenant_id,
                    policy=POLICY,
                )
                rows = await transaction.fetch_all(
                    _LIST_OBJECTS_SQL,
                    (
                        tenant_id,
                        zone,
                        connection_id,
                        connection_id,
                        active_state,
                        active_state,
                        active_state,
                        page_size + 1,
                        offset,
                    ),
                )
            next_cursor = None
            if len(rows) > page_size:
                next_cursor = cursors.encode(
                    collection=collection,
                    offset=offset + page_size,
                )
            return ListObjectsResult(
                tenant_id=tenant_id,
                zone=zone,
                objects=tuple(ObjectSummary(**row) for row in rows[:page_size]),
                next_cursor=next_cursor,
            )
        except AuthenticationError as error:
            raise SafeToolError(f"{error.public_code}: {error.message}") from None
        except WorkbenchError as error:
            raise SafeToolError(f"{error.code}: {error.message}") from None
        except Exception:
            raise SafeToolError("internal_error: The operation could not be completed.") from None

    del _list_objects
    audit.register_tool(
        _TOOL_NAME,
        policy=POLICY,
        summarize_input=_audit_input_metadata,
        retain_arguments={
            "tenant_id",
            "zone",
            "connection_id",
            "active_state",
            "page_size",
            "schema_version",
        },
        tenant_argument="tenant_id",
    )


def _audit_input_metadata(arguments: Mapping[str, Any]) -> dict[str, str | int | bool]:
    tenant_id = arguments.get("tenant_id")
    page_size = arguments.get("page_size", 50)
    zone = arguments.get("zone")
    active_state = arguments.get("active_state", "active")
    return {
        "schema_version": "1.0" if arguments.get("schema_version", "1.0") == "1.0" else "invalid",
        "tenant_id": tenant_id if type(tenant_id) is int and tenant_id > 0 else "invalid",
        "zone": zone if zone in {"source", "bronze", "silver", "gold"} else "invalid",
        "active_state": (
            active_state if active_state in {"active", "inactive", "all"} else "invalid"
        ),
        "connection_filter_provided": arguments.get("connection_id") is not None,
        "page_size": (page_size if type(page_size) is int and 1 <= page_size <= 200 else "invalid"),
        "cursor_provided": arguments.get("cursor") is not None,
    }
