"""Bounded active Model Scope Objects for one authorized Model."""

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
from gds_etl_workbench.domain.errors import WorkbenchError
from gds_etl_workbench.infrastructure.postgres import Database, ReadIsolation

from .common import POLICY, authorize_model_read

_TOOL_NAME = "get_model_scope"
_MAX_SCOPE_OBJECTS = 2_000

_MODEL_SCOPE_SQL: LiteralString = """
SELECT model_scope.model_scope_id,
       model_scope.object_id,
       tenant.tenant_id,
       tenant.tenant_code,
       tenant.tenant_name,
       system.system_id,
       system.system_code,
       system.system_name,
       connection.connection_id,
       connection.connection_code,
       connection.connection_name,
       object.object_schema,
       object.object_name,
       object_type.object_type_id,
       object_type.object_type_code,
       object_type.object_type_name,
       zone.zone_code,
       model_scope.model_scope_is_locked,
       model_scope.is_active,
       count(*) OVER () AS total_object_count
  FROM model.model_scope AS model_scope
  JOIN core.object AS object
    ON object.object_id = model_scope.object_id
   AND object.is_active
  JOIN core.connection AS connection
    ON connection.connection_id = object.connection_id
   AND connection.is_active
  JOIN core.tenant AS tenant
    ON tenant.tenant_id = connection.tenant_id
   AND tenant.is_active
  JOIN core.system AS system
    ON system.system_id = connection.system_id
   AND system.is_active
  JOIN reference.object_type AS object_type
    ON object_type.object_type_id = object.object_type_id
   AND object_type.is_active
  JOIN reference.zone AS zone
    ON zone.zone_id = object.zone_id
   AND zone.is_active
 WHERE model_scope.model_id = %s
   AND model_scope.is_active
 ORDER BY lower(tenant.tenant_code),
          lower(system.system_code),
          lower(connection.connection_code),
          lower(object.object_schema),
          lower(object.object_name),
          model_scope.object_id
 LIMIT %s
"""


class ContractModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class ModelScopeObject(ContractModel):
    model_scope_id: int = Field(gt=0)
    object_id: int = Field(gt=0)
    tenant_id: int = Field(gt=0)
    tenant_code: str = Field(min_length=1, max_length=100)
    tenant_name: str = Field(min_length=1, max_length=200)
    system_id: int = Field(gt=0)
    system_code: str = Field(min_length=1, max_length=100)
    system_name: str = Field(min_length=1, max_length=200)
    connection_id: int = Field(gt=0)
    connection_code: str = Field(min_length=1, max_length=100)
    connection_name: str = Field(min_length=1, max_length=200)
    object_schema: str = Field(min_length=1, max_length=400)
    object_name: str = Field(min_length=1, max_length=400)
    object_type_id: int = Field(gt=0)
    object_type_code: str = Field(min_length=1, max_length=100)
    object_type_name: str = Field(min_length=1, max_length=200)
    zone_code: str = Field(min_length=1, max_length=100)
    model_scope_is_locked: bool
    is_active: Literal[True]


class GetModelScopeResult(ContractModel):
    schema_version: Literal["1.0"] = "1.0"
    model_id: int = Field(gt=0)
    model_revision: int = Field(gt=0)
    object_count: int = Field(ge=0)
    objects: tuple[ModelScopeObject, ...] = Field(max_length=_MAX_SCOPE_OBJECTS)
    objects_truncated: bool


class ModelScopeToolError(Exception):
    """A bounded Model Scope failure safe for MCP serialization."""


def register_get_model_scope_tool(
    server: MCPServer[None],
    *,
    database: Database,
    identity_provider: IdentityProvider,
    authorizer: AuthorizationService,
    audit: ToolCallAuditMiddleware,
) -> None:
    @server.tool(
        description=(
            "Get active Objects in one authorized Model Scope with expanded Tenant, "
            "System, Connection, Object Type, Zone, and physical Object names."
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
    async def get_model_scope(
        ctx: Context[None],
        model_id: Annotated[int, Field(gt=0)],
        schema_version: Literal["1.0"] = "1.0",
    ) -> GetModelScopeResult:
        del schema_version
        try:
            principal = identity_provider.request_principal(ctx.request_context.request)
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
                    _MODEL_SCOPE_SQL,
                    (model.model_id, _MAX_SCOPE_OBJECTS + 1),
                )
            object_count = 0 if not rows else int(rows[0]["total_object_count"])
            return GetModelScopeResult(
                model_id=model.model_id,
                model_revision=model.model_revision,
                object_count=object_count,
                objects=tuple(
                    ModelScopeObject(
                        **{
                            name: value
                            for name, value in row.items()
                            if name != "total_object_count"
                        }
                    )
                    for row in rows[:_MAX_SCOPE_OBJECTS]
                ),
                objects_truncated=object_count > _MAX_SCOPE_OBJECTS,
            )
        except AuthenticationError as error:
            raise ModelScopeToolError(f"{error.public_code}: {error.message}") from None
        except WorkbenchError as error:
            raise ModelScopeToolError(f"{error.code}: {error.message}") from None
        except Exception:
            raise ModelScopeToolError(
                "internal_error: The operation could not be completed."
            ) from None

    audit.register_tool(
        _TOOL_NAME,
        policy=POLICY,
        summarize_input=_audit_input,
        retain_arguments={"model_id", "schema_version"},
    )


def _audit_input(arguments: Mapping[str, Any]) -> dict[str, str | int]:
    model_id = arguments.get("model_id")
    return {
        "schema_version": (
            "1.0" if arguments.get("schema_version", "1.0") == "1.0" else "invalid"
        ),
        "model_id": model_id if type(model_id) is int and model_id > 0 else "invalid",
    }
