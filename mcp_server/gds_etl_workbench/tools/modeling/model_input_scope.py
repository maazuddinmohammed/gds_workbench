"""Bounded active Model Input Scope for one authorized Model."""

# Pyright cannot see that @server.tool registers this nested handler.
# pyright: reportUnusedFunction=false

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
from gds_etl_workbench.domain.errors import WorkbenchError
from gds_etl_workbench.infrastructure.postgres import Database, ReadIsolation

from .common import POLICY, authorize_model_read

_TOOL_NAME = "get_model_input_scope"
_MAX_OBJECTS = 2_000

_MODEL_INPUT_SCOPE_SQL: LiteralString = """
SELECT scope.model_input_scope_id,
       object.object_id,
       source_tenant.tenant_id AS source_tenant_id,
       source_tenant.tenant_code AS source_tenant_code,
       source_tenant.tenant_name AS source_tenant_name,
       placement_tenant.tenant_id AS placement_tenant_id,
       placement_tenant.tenant_code AS placement_tenant_code,
       placement_tenant.tenant_name AS placement_tenant_name,
       system.system_id,
       system.system_code,
       system.system_name,
       connection.connection_id,
       connection.connection_code,
       connection.connection_name,
       connection.foreign_catalog,
       object.object_schema,
       object.object_name,
       object.fc_object_schema,
       object.fc_object_name,
       object_type.object_type_id,
       object_type.object_type_code,
       object_type.object_type_name,
       zone.zone_code,
       scope.model_input_scope_is_locked,
       TRUE AS is_active,
       count(*) OVER () AS total_object_count
  FROM model.model_input_scope AS scope
  JOIN model.model
    ON model.model_id = scope.model_id
   AND model.is_active
  JOIN core.object AS object
    ON object.object_id = scope.object_id
   AND object.source_tenant_id = model.tenant_id
   AND object.is_active
  JOIN core.tenant AS source_tenant
    ON source_tenant.tenant_id = object.source_tenant_id
   AND source_tenant.is_active
  JOIN core.connection AS connection
    ON connection.connection_id = object.connection_id
   AND connection.is_active
  JOIN core.tenant AS placement_tenant
    ON placement_tenant.tenant_id = connection.tenant_id
   AND placement_tenant.is_active
  JOIN core.system AS system
    ON system.system_id = connection.system_id
   AND system.is_active
  JOIN reference.object_type AS object_type
    ON object_type.object_type_id = object.object_type_id
   AND object_type.is_active
  JOIN reference.zone AS zone
    ON zone.zone_id = object.zone_id
   AND zone.is_active
   AND zone.zone_code IN ('source', 'bronze')
 WHERE scope.model_id = %s
   AND scope.is_active
 ORDER BY lower(placement_tenant.tenant_code),
          lower(system.system_code),
          lower(connection.connection_code),
          lower(object.object_schema),
          lower(object.object_name),
          scope.object_id
 LIMIT %s OFFSET %s
"""


class ContractModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class ModelInputScopeObject(ContractModel):
    model_input_scope_id: int = Field(gt=0)
    object_id: int = Field(gt=0)
    source_tenant_id: int = Field(gt=0)
    source_tenant_code: str = Field(min_length=1, max_length=100)
    source_tenant_name: str = Field(min_length=1, max_length=200)
    placement_tenant_id: int = Field(gt=0)
    placement_tenant_code: str = Field(min_length=1, max_length=100)
    placement_tenant_name: str = Field(min_length=1, max_length=200)
    system_id: int = Field(gt=0)
    system_code: str = Field(min_length=1, max_length=100)
    system_name: str = Field(min_length=1, max_length=200)
    connection_id: int = Field(gt=0)
    connection_code: str = Field(min_length=1, max_length=100)
    connection_name: str = Field(min_length=1, max_length=200)
    foreign_catalog: str | None = Field(default=None, min_length=1, max_length=400)
    object_schema: str = Field(min_length=1, max_length=400)
    object_name: str = Field(min_length=1, max_length=400)
    fc_object_schema: str | None = Field(default=None, min_length=1, max_length=400)
    fc_object_name: str | None = Field(default=None, min_length=1, max_length=400)
    object_type_id: int = Field(gt=0)
    object_type_code: str = Field(min_length=1, max_length=100)
    object_type_name: str = Field(min_length=1, max_length=200)
    zone_code: Literal["source", "bronze"]
    model_input_scope_is_locked: bool
    is_active: Literal[True]


class GetModelInputScopeResult(ContractModel):
    schema_version: Literal["1.0"] = "1.0"
    model_id: int = Field(gt=0)
    model_revision: int = Field(gt=0)
    object_count: int = Field(ge=0)
    objects: tuple[ModelInputScopeObject, ...] = Field(max_length=_MAX_OBJECTS)
    objects_truncated: bool
    next_cursor: str | None = Field(default=None, max_length=2048)


class ModelInputScopeToolError(Exception):
    """A bounded Model Input Scope failure safe for MCP serialization."""


def register_get_model_input_scope_tool(
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
            "Get active Source or Bronze Objects selected as inputs for one Model. Returns "
            "source ownership, physical placement, and foreign-catalog coordinates."
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
    async def get_model_input_scope(
        ctx: Context[None],
        model_id: Annotated[int, Field(gt=0)],
        page_size: Annotated[int, Field(ge=1, le=_MAX_OBJECTS)] = _MAX_OBJECTS,
        cursor: Annotated[str | None, Field(max_length=2048)] = None,
        schema_version: Literal["1.0"] = "1.0",
    ) -> GetModelInputScopeResult:
        del schema_version
        try:
            principal = identity_provider.request_principal(ctx.request_context.request)
            collection = f"{_TOOL_NAME}:{model_id}:{page_size}"
            offset = cursors.decode(cursor, collection=collection)
            async with database.read_transaction(
                isolation=ReadIsolation.REPEATABLE_READ
            ) as transaction:
                model = await authorize_model_read(
                    transaction,
                    authorizer=authorizer,
                    principal=principal,
                    model_id=model_id,
                )
                rows = await transaction.fetch_all(
                    _MODEL_INPUT_SCOPE_SQL,
                    (model.model_id, page_size + 1, offset),
                )
            return GetModelInputScopeResult(
                model_id=model.model_id,
                model_revision=model.model_revision,
                object_count=0 if not rows else int(rows[0]["total_object_count"]),
                objects=tuple(
                    ModelInputScopeObject(
                        **{
                            name: value
                            for name, value in row.items()
                            if name != "total_object_count"
                        }
                    )
                    for row in rows[:page_size]
                ),
                objects_truncated=len(rows) > page_size,
                next_cursor=(
                    cursors.encode(collection=collection, offset=offset + page_size)
                    if len(rows) > page_size
                    else None
                ),
            )
        except AuthenticationError as error:
            raise ModelInputScopeToolError(f"{error.public_code}: {error.message}") from None
        except WorkbenchError as error:
            raise ModelInputScopeToolError(f"{error.code}: {error.message}") from None
        except Exception:
            raise ModelInputScopeToolError(
                "internal_error: The operation could not be completed."
            ) from None

    audit.register_tool(
        _TOOL_NAME,
        policy=POLICY,
        summarize_input=_audit_input,
        retain_arguments={"model_id", "page_size", "schema_version"},
    )


def _audit_input(arguments: Mapping[str, Any]) -> dict[str, str | int | bool]:
    model_id = arguments.get("model_id")
    page_size = arguments.get("page_size", _MAX_OBJECTS)
    return {
        "schema_version": "1.0" if arguments.get("schema_version", "1.0") == "1.0" else "invalid",
        "model_id": model_id if type(model_id) is int and model_id > 0 else "invalid",
        "page_size": (
            page_size if type(page_size) is int and 1 <= page_size <= _MAX_OBJECTS else "invalid"
        ),
        "cursor_provided": arguments.get("cursor") is not None,
    }
