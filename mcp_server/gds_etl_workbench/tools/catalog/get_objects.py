"""Bounded batch Object and Attribute details for one authorized Tenant."""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Mapping
from typing import Annotated, Any, Literal, LiteralString

from mcp.server.mcpserver import Context, MCPServer
from mcp.types import ToolAnnotations
from pydantic import BaseModel, ConfigDict, Field, field_validator

from gds_etl_workbench.adapters.auth.identity import AuthenticationError, IdentityProvider
from gds_etl_workbench.adapters.mcp.tool_audit import ToolCallAuditMiddleware
from gds_etl_workbench.application.authorization import AuthorizationService
from gds_etl_workbench.domain.authorization import ToolPolicy
from gds_etl_workbench.domain.errors import InvalidRequestError, WorkbenchError
from gds_etl_workbench.infrastructure.postgres import Database, ReadIsolation

from .visibility import VISIBLE_OBJECTS_CTE

type ZoneCode = Literal["source", "bronze", "silver", "gold"]

_TOOL_NAME = "get_objects"
_MAX_OBJECTS = 25
_MAX_ATTRIBUTES = 2000
POLICY = ToolPolicy.TENANT_READ

_OBJECTS_SQL: LiteralString = f"""
{VISIBLE_OBJECTS_CTE}
SELECT object.object_id,
       object.object_schema,
       object.object_name,
       left(object.object_description, 2000) AS object_description,
       object.object_type_id,
       object_type.object_type_code,
       object_type.object_type_name,
       zone.zone_code AS zone,
       object.batch_attribute_name,
       object.is_locked,
       object.is_active,
       connection.connection_id,
       connection.connection_code,
       connection.connection_name,
       system.system_id,
       system.system_code,
       system.system_name
  FROM unnest(%s::BIGINT[]) WITH ORDINALITY AS requested(object_id, ordinal)
  JOIN visible_objects ON visible_objects.object_id = requested.object_id
  JOIN core.object AS object ON object.object_id = visible_objects.object_id
  JOIN reference.object_type AS object_type
    ON object_type.object_type_id = object.object_type_id
  JOIN reference.zone AS zone ON zone.zone_id = object.zone_id
  JOIN core.connection AS connection
    ON connection.connection_id = object.connection_id
  JOIN core.system AS system ON system.system_id = connection.system_id
 ORDER BY requested.ordinal
"""

_ATTRIBUTES_SQL: LiteralString = """
SELECT attribute.attribute_id,
       attribute.object_id,
       attribute.attribute_name,
       attribute.attribute_ordinal_position,
       left(attribute.attribute_description, 2000) AS attribute_description,
       attribute.attribute_data_type,
       attribute.attribute_nullability,
       attribute.is_surrogate_key,
       attribute.is_natural_key,
       attribute.is_meta_data,
       attribute.is_masking_required,
       attribute.is_mapped,
       attribute.is_purge,
       attribute.is_locked,
       attribute.is_active
  FROM core.attribute AS attribute
 WHERE attribute.object_id = ANY(%s::BIGINT[])
 ORDER BY attribute.object_id,
          attribute.attribute_ordinal_position,
          attribute.attribute_id
 LIMIT %s
"""


class ContractModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class GetObjectsRequest(ContractModel):
    tenant_id: int = Field(gt=0)
    object_ids: tuple[int, ...] = Field(min_length=1, max_length=_MAX_OBJECTS)

    @field_validator("object_ids")
    @classmethod
    def validate_object_ids(cls, value: tuple[int, ...]) -> tuple[int, ...]:
        if any(object_id <= 0 for object_id in value) or len(set(value)) != len(value):
            raise ValueError("Object IDs must be unique positive integers.")
        return value


class AttributeDetails(ContractModel):
    attribute_id: int = Field(gt=0)
    attribute_name: str = Field(min_length=1, max_length=400)
    attribute_ordinal_position: int = Field(gt=0)
    attribute_description: str | None = Field(default=None, max_length=2000)
    attribute_data_type: str = Field(min_length=1, max_length=100)
    attribute_nullability: bool
    is_surrogate_key: bool
    is_natural_key: bool
    is_meta_data: bool
    is_masking_required: bool
    is_mapped: bool
    is_purge: bool
    is_locked: bool
    is_active: bool


class ObjectDetails(ContractModel):
    object_id: int = Field(gt=0)
    object_schema: str = Field(min_length=1, max_length=400)
    object_name: str = Field(min_length=1, max_length=400)
    object_description: str | None = Field(default=None, max_length=2000)
    object_type_id: int = Field(gt=0)
    object_type_code: str = Field(min_length=1, max_length=100)
    object_type_name: str = Field(min_length=1, max_length=200)
    zone: ZoneCode
    batch_attribute_name: str | None = Field(default=None, max_length=400)
    connection_id: int = Field(gt=0)
    connection_code: str = Field(min_length=1, max_length=100)
    connection_name: str = Field(min_length=1, max_length=200)
    system_id: int = Field(gt=0)
    system_code: str = Field(min_length=1, max_length=100)
    system_name: str = Field(min_length=1, max_length=200)
    is_locked: bool
    is_active: bool
    attributes: tuple[AttributeDetails, ...]


class GetObjectsResult(ContractModel):
    schema_version: Literal["1.0"] = "1.0"
    tenant_id: int = Field(gt=0)
    objects: tuple[ObjectDetails, ...] = Field(max_length=_MAX_OBJECTS)


class SafeToolError(Exception):
    """A tool failure whose text is safe for the MCP SDK to serialize."""


def register_get_objects_tool(
    server: MCPServer[None],
    *,
    database: Database,
    identity_provider: IdentityProvider,
    authorizer: AuthorizationService,
    audit: ToolCallAuditMiddleware,
) -> None:
    @server.tool(
        description=(
            "Get up to 25 authorized physical Objects and their bounded Attribute "
            "definitions. Use list_objects first to discover Object IDs."
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
    async def get_objects(
        ctx: Context[None],
        tenant_id: Annotated[int, Field(gt=0)],
        object_ids: Annotated[list[int], Field(min_length=1, max_length=_MAX_OBJECTS)],
        schema_version: Literal["1.0"] = "1.0",
    ) -> GetObjectsResult:
        try:
            request = GetObjectsRequest(tenant_id=tenant_id, object_ids=tuple(object_ids))
            principal = identity_provider.request_principal(ctx.request_context.request)
            async with database.read_transaction(
                isolation=ReadIsolation.REPEATABLE_READ
            ) as transaction:
                await authorizer.authorize_tenant(
                    transaction,
                    principal,
                    tenant_id=request.tenant_id,
                    policy=POLICY,
                )
                object_rows = await transaction.fetch_all(
                    _OBJECTS_SQL,
                    (request.tenant_id, list(request.object_ids)),
                )
                if len(object_rows) != len(request.object_ids):
                    raise InvalidRequestError("One or more Objects were not found.")
                attribute_rows = await transaction.fetch_all(
                    _ATTRIBUTES_SQL,
                    (list(request.object_ids), _MAX_ATTRIBUTES + 1),
                )
            if len(attribute_rows) > _MAX_ATTRIBUTES:
                raise InvalidRequestError("The requested Object details are too large.")
            attributes_by_object: dict[int, list[AttributeDetails]] = defaultdict(list)
            for row in attribute_rows:
                object_id = row.pop("object_id")
                attributes_by_object[object_id].append(AttributeDetails(**row))
            return GetObjectsResult(
                tenant_id=request.tenant_id,
                objects=tuple(
                    ObjectDetails(
                        **row,
                        attributes=tuple(attributes_by_object[row["object_id"]]),
                    )
                    for row in object_rows
                ),
            )
        except AuthenticationError as error:
            raise SafeToolError(f"{error.public_code}: {error.message}") from None
        except WorkbenchError as error:
            raise SafeToolError(f"{error.code}: {error.message}") from None
        except Exception:
            raise SafeToolError("internal_error: The operation could not be completed.") from None

    audit.register_tool(
        _TOOL_NAME,
        policy=POLICY,
        summarize_input=_audit_input_metadata,
        tenant_argument="tenant_id",
    )


def _audit_input_metadata(arguments: Mapping[str, Any]) -> dict[str, str | int]:
    tenant_id = arguments.get("tenant_id")
    object_ids = arguments.get("object_ids")
    return {
        "schema_version": "1.0" if arguments.get("schema_version", "1.0") == "1.0" else "invalid",
        "tenant_id": tenant_id if type(tenant_id) is int and tenant_id > 0 else "invalid",
        "object_count": len(object_ids) if isinstance(object_ids, list) else "invalid",
    }
