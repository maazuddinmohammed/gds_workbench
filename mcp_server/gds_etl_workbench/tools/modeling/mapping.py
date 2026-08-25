"""Target-Object-driven Mapping dependency, Object, and Attribute reads."""

# Pyright cannot see that @server.tool registers these nested handlers.
# pyright: reportUnusedFunction=false

from __future__ import annotations

from collections.abc import Mapping
from typing import Annotated, Any, Literal, LiteralString, cast

from mcp.server.mcpserver import Context, MCPServer
from mcp.types import ToolAnnotations
from pydantic import Field

from gds_etl_workbench.adapters.auth.identity import AuthenticationError, IdentityProvider
from gds_etl_workbench.adapters.mcp.tool_audit import ToolCallAuditMiddleware
from gds_etl_workbench.application.authorization import AuthorizationService
from gds_etl_workbench.application.cursor import CursorCodec
from gds_etl_workbench.domain.errors import InvalidRequestError, WorkbenchError
from gds_etl_workbench.domain.modeling_records import (
    MappingAttributeRecord,
    MappingDependencyRecord,
    MappingObjectRecord,
)
from gds_etl_workbench.infrastructure.postgres import Database, ReadIsolation

from .common import (
    MAX_OBJECT_FILTER,
    POLICY,
    ContractModel,
    authorize_model_read,
    validate_model_object_selection,
)

_MAX_PAGE_SIZE = 200

MAPPING_DEPENDENCIES_SQL: LiteralString = """
SELECT dependency.mapping_source_system_dependency_id,
       dependency.source_system_id,
       source_system.system_code AS source_system_code,
       source_system.system_name AS source_system_name,
       dependency.modeled_entity_type,
       dependency.source_system_dependency_order,
       dependency.mapping_source_system_dependency_status,
       dependency.mapping_source_system_dependency_is_locked
  FROM workflow.mapping_source_system_dependency AS dependency
  JOIN core.system AS source_system
    ON source_system.system_id = dependency.source_system_id
 WHERE dependency.model_id = %s
 ORDER BY dependency.modeled_entity_type,
          dependency.source_system_dependency_order,
          lower(source_system.system_code),
          dependency.mapping_source_system_dependency_id
 LIMIT %s OFFSET %s
"""

MAPPING_OBJECTS_SQL: LiteralString = """
WITH requested_model AS (
    SELECT %s::BIGINT AS model_id
),
eligible_objects AS MATERIALIZED (
    SELECT eligibility.*
      FROM requested_model
      CROSS JOIN LATERAL workflow.list_model_object_eligibility(
          requested_model.model_id
      ) AS eligibility
)
SELECT mapping.mapping_object_id,
       mapping.object_id,
       tenant.tenant_code,
       object_system.system_code,
       connection.connection_code,
       object.object_schema,
       object.object_name,
       mapping.source_system_id,
       source_system.system_code AS source_system_code,
       source_system.system_name AS source_system_name,
       mapping.modeled_entity_type,
       CASE mapping.modeled_entity_type
           WHEN 'logical_entity' THEN mapping.logical_entity_id
           ELSE mapping.dimensional_entity_id
       END AS modeled_entity_id,
       CASE mapping.modeled_entity_type
           WHEN 'logical_entity' THEN logical_entity.logical_entity_name
           ELSE dimensional_entity.dimensional_entity_name
       END AS modeled_entity_name,
       mapping.object_dependency_order,
       mapping.artifact_type,
       mapping.artifact_generation_instructions,
       mapping.mapping_profile_key,
       mapping.mapping_profile_version,
       mapping.mapping_package_document,
       mapping.object_mapping_transformation_document,
       mapping.object_mapping_status,
       mapping.object_mapping_is_locked
  FROM workflow.mapping_object AS mapping
  JOIN eligible_objects AS eligibility
    ON eligibility.object_id = mapping.object_id
   AND eligibility.model_id = mapping.model_id
   AND (
       (
           mapping.modeled_entity_type = 'logical_entity'
           AND eligibility.is_logical_mapping_target_eligible
       )
       OR (
           mapping.modeled_entity_type = 'dimensional_entity'
           AND eligibility.is_dimensional_mapping_target_eligible
       )
   )
  JOIN core.object AS object
    ON object.object_id = mapping.object_id
  JOIN core.connection AS connection
    ON connection.connection_id = object.connection_id
  JOIN core.tenant AS tenant
    ON tenant.tenant_id = eligibility.object_tenant_id
  JOIN core.system AS object_system
    ON object_system.system_id = connection.system_id
  JOIN core.system AS source_system
    ON source_system.system_id = mapping.source_system_id
  LEFT JOIN workflow.logical_entity AS logical_entity
    ON logical_entity.logical_entity_id = mapping.logical_entity_id
   AND logical_entity.model_id = mapping.model_id
  LEFT JOIN workflow.dimensional_entity AS dimensional_entity
    ON dimensional_entity.dimensional_entity_id = mapping.dimensional_entity_id
   AND dimensional_entity.model_id = mapping.model_id
 WHERE (
       cardinality(%s::BIGINT[]) = 0
       OR mapping.object_id = ANY(%s::BIGINT[])
   )
 ORDER BY mapping.object_dependency_order,
          lower(object.object_schema),
          lower(object.object_name),
          mapping.modeled_entity_type,
          mapping.mapping_object_id
 LIMIT %s OFFSET %s
"""

MAPPING_ATTRIBUTES_SQL: LiteralString = """
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
SELECT attribute_mapping.mapping_attribute_id,
       attribute_mapping.object_id,
       target_object.object_schema,
       target_object.object_name,
       attribute_mapping.attribute_id,
       target_attribute.attribute_name,
       tenant.tenant_code,
       object_system.system_code,
       connection.connection_code,
       object_mapping.source_system_id,
       source_system.system_code AS source_system_code,
       source_system.system_name AS source_system_name,
       attribute_mapping.mapping_object_id,
       attribute_mapping.modeled_entity_type,
       CASE attribute_mapping.modeled_entity_type
           WHEN 'logical_entity' THEN object_mapping.logical_entity_id
           ELSE object_mapping.dimensional_entity_id
       END AS modeled_entity_id,
       CASE attribute_mapping.modeled_entity_type
           WHEN 'logical_entity' THEN logical_entity.logical_entity_name
           ELSE dimensional_entity.dimensional_entity_name
       END AS modeled_entity_name,
       CASE attribute_mapping.modeled_entity_type
           WHEN 'logical_entity' THEN attribute_mapping.logical_attribute_id
           ELSE attribute_mapping.dimensional_attribute_id
       END AS modeled_attribute_id,
       CASE attribute_mapping.modeled_entity_type
           WHEN 'logical_entity' THEN logical_attribute.logical_attribute_name
           ELSE dimensional_attribute.dimensional_attribute_name
       END AS modeled_attribute_name,
       attribute_mapping.attribute_mapping_transformation_document,
       attribute_mapping.attribute_mapping_status,
       attribute_mapping.attribute_mapping_is_locked
  FROM workflow.mapping_attribute AS attribute_mapping
  JOIN eligible_attributes AS eligibility
    ON eligibility.object_id = attribute_mapping.object_id
   AND eligibility.attribute_id = attribute_mapping.attribute_id
   AND eligibility.model_id = attribute_mapping.model_id
   AND (
       (
           attribute_mapping.modeled_entity_type = 'logical_entity'
           AND eligibility.is_logical_mapping_target_eligible
       )
       OR (
           attribute_mapping.modeled_entity_type = 'dimensional_entity'
           AND eligibility.is_dimensional_mapping_target_eligible
       )
   )
  JOIN workflow.mapping_object AS object_mapping
    ON object_mapping.mapping_object_id = attribute_mapping.mapping_object_id
   AND object_mapping.model_id = attribute_mapping.model_id
   AND object_mapping.modeled_entity_type = attribute_mapping.modeled_entity_type
   AND object_mapping.object_id = attribute_mapping.object_id
  JOIN core.object AS target_object
    ON target_object.object_id = attribute_mapping.object_id
  JOIN core.attribute AS target_attribute
    ON target_attribute.attribute_id = attribute_mapping.attribute_id
   AND target_attribute.object_id = attribute_mapping.object_id
  JOIN core.connection AS connection
    ON connection.connection_id = target_object.connection_id
  JOIN core.tenant AS tenant
    ON tenant.tenant_id = eligibility.object_tenant_id
  JOIN core.system AS object_system
    ON object_system.system_id = connection.system_id
  JOIN core.system AS source_system
    ON source_system.system_id = object_mapping.source_system_id
  LEFT JOIN workflow.logical_entity AS logical_entity
    ON logical_entity.logical_entity_id = object_mapping.logical_entity_id
   AND logical_entity.model_id = object_mapping.model_id
  LEFT JOIN workflow.dimensional_entity AS dimensional_entity
    ON dimensional_entity.dimensional_entity_id = object_mapping.dimensional_entity_id
   AND dimensional_entity.model_id = object_mapping.model_id
  LEFT JOIN workflow.logical_attribute AS logical_attribute
    ON logical_attribute.logical_attribute_id = attribute_mapping.logical_attribute_id
   AND logical_attribute.model_id = attribute_mapping.model_id
  LEFT JOIN workflow.dimensional_attribute AS dimensional_attribute
    ON dimensional_attribute.dimensional_attribute_id
        = attribute_mapping.dimensional_attribute_id
   AND dimensional_attribute.model_id = attribute_mapping.model_id
 WHERE (
       cardinality(%s::BIGINT[]) = 0
       OR attribute_mapping.object_id = ANY(%s::BIGINT[])
   )
 ORDER BY lower(target_object.object_schema),
          lower(target_object.object_name),
          target_attribute.attribute_ordinal_position,
          attribute_mapping.modeled_entity_type,
          attribute_mapping.mapping_attribute_id
 LIMIT %s OFFSET %s
"""


class MappingDependencyResult(MappingDependencyRecord):
    mapping_source_system_dependency_id: int = Field(gt=0)
    source_system_id: int = Field(gt=0)
    source_system_name: str = Field(min_length=1, max_length=200)


class MappingObjectResult(MappingObjectRecord):
    mapping_object_id: int = Field(gt=0)
    object_id: int = Field(gt=0)
    source_system_id: int = Field(gt=0)
    source_system_name: str = Field(min_length=1, max_length=200)
    modeled_entity_id: int = Field(gt=0)


class MappingAttributeResult(MappingAttributeRecord):
    mapping_attribute_id: int = Field(gt=0)
    object_id: int = Field(gt=0)
    attribute_id: int = Field(gt=0)
    mapping_object_id: int = Field(gt=0)
    source_system_id: int = Field(gt=0)
    source_system_name: str = Field(min_length=1, max_length=200)
    modeled_entity_id: int = Field(gt=0)
    modeled_attribute_id: int = Field(gt=0)


class GetModelMappingDependenciesResult(ContractModel):
    schema_version: Literal["1.0"] = "1.0"
    model_id: int = Field(gt=0)
    model_revision: int = Field(gt=0)
    dependencies: tuple[MappingDependencyResult, ...] = Field(max_length=_MAX_PAGE_SIZE)
    next_cursor: str | None = Field(default=None, max_length=2048)


class GetModelObjectMappingsResult(ContractModel):
    schema_version: Literal["1.0"] = "1.0"
    model_id: int = Field(gt=0)
    model_revision: int = Field(gt=0)
    mappings: tuple[MappingObjectResult, ...] = Field(max_length=_MAX_PAGE_SIZE)
    next_cursor: str | None = Field(default=None, max_length=2048)


class GetModelAttributeMappingsResult(ContractModel):
    schema_version: Literal["1.0"] = "1.0"
    model_id: int = Field(gt=0)
    model_revision: int = Field(gt=0)
    mappings: tuple[MappingAttributeResult, ...] = Field(max_length=_MAX_PAGE_SIZE)
    next_cursor: str | None = Field(default=None, max_length=2048)


class MappingToolError(Exception):
    """A bounded Mapping-read failure safe for MCP serialization."""


def register_mapping_tools(
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
        description="Get source-System Mapping dependency waves for one Model.",
        annotations=_annotations(),
        meta={"gds/toolPolicy": POLICY.value},
        structured_output=True,
    )
    async def get_model_mapping_dependencies(
        ctx: Context[None],
        model_id: Annotated[int, Field(gt=0)],
        page_size: Annotated[int, Field(ge=1, le=_MAX_PAGE_SIZE)] = 50,
        cursor: Annotated[str | None, Field(max_length=2048)] = None,
        schema_version: Literal["1.0"] = "1.0",
    ) -> GetModelMappingDependenciesResult:
        del schema_version
        try:
            collection = f"get_model_mapping_dependencies:{model_id}:{page_size}"
            offset = cursors.decode(cursor, collection=collection)
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
                    MAPPING_DEPENDENCIES_SQL,
                    (model.model_id, page_size + 1, offset),
                )
            return GetModelMappingDependenciesResult(
                model_id=model.model_id,
                model_revision=model.model_revision,
                dependencies=tuple(
                    MappingDependencyResult.model_validate(row, strict=False)
                    for row in rows[:page_size]
                ),
                next_cursor=_next_cursor(cursors, collection, offset, page_size, len(rows)),
            )
        except AuthenticationError as error:
            raise MappingToolError(f"{error.public_code}: {error.message}") from None
        except WorkbenchError as error:
            raise MappingToolError(f"{error.code}: {error.message}") from None
        except Exception:
            raise MappingToolError(
                "internal_error: The operation could not be completed."
            ) from None

    audit.register_tool(
        "get_model_mapping_dependencies",
        policy=POLICY,
        summarize_input=_audit_input,
        retain_arguments={"model_id", "page_size", "schema_version"},
    )

    @server.tool(
        description=(
            "Get target-driven Object Mappings for one Model. An empty Object-ID "
            "list selects all mapped Objects."
        ),
        annotations=_annotations(),
        meta={"gds/toolPolicy": POLICY.value},
        structured_output=True,
    )
    async def get_model_object_mappings(
        ctx: Context[None],
        model_id: Annotated[int, Field(gt=0)],
        object_ids: Annotated[tuple[int, ...], Field(max_length=MAX_OBJECT_FILTER)] = (),
        page_size: Annotated[int, Field(ge=1, le=_MAX_PAGE_SIZE)] = 50,
        cursor: Annotated[str | None, Field(max_length=2048)] = None,
        schema_version: Literal["1.0"] = "1.0",
    ) -> GetModelObjectMappingsResult:
        del schema_version
        try:
            model, rows, next_cursor = await _read_mappings(
                database=database,
                identity_provider=identity_provider,
                authorizer=authorizer,
                ctx=ctx,
                cursors=cursors,
                tool_name="get_model_object_mappings",
                query=MAPPING_OBJECTS_SQL,
                model_id=model_id,
                object_ids=object_ids,
                page_size=page_size,
                cursor=cursor,
            )
            return GetModelObjectMappingsResult(
                model_id=model.model_id,
                model_revision=model.model_revision,
                mappings=tuple(
                    MappingObjectResult.model_validate(row, strict=False) for row in rows
                ),
                next_cursor=next_cursor,
            )
        except AuthenticationError as error:
            raise MappingToolError(f"{error.public_code}: {error.message}") from None
        except WorkbenchError as error:
            raise MappingToolError(f"{error.code}: {error.message}") from None
        except Exception:
            raise MappingToolError(
                "internal_error: The operation could not be completed."
            ) from None

    audit.register_tool(
        "get_model_object_mappings",
        policy=POLICY,
        summarize_input=_audit_input,
        retain_arguments={"model_id", "page_size", "schema_version"},
    )

    @server.tool(
        description=(
            "Get target-driven Attribute Mappings for one Model. An empty Object-ID "
            "list selects all mapped Attributes."
        ),
        annotations=_annotations(),
        meta={"gds/toolPolicy": POLICY.value},
        structured_output=True,
    )
    async def get_model_attribute_mappings(
        ctx: Context[None],
        model_id: Annotated[int, Field(gt=0)],
        object_ids: Annotated[tuple[int, ...], Field(max_length=MAX_OBJECT_FILTER)] = (),
        page_size: Annotated[int, Field(ge=1, le=_MAX_PAGE_SIZE)] = 50,
        cursor: Annotated[str | None, Field(max_length=2048)] = None,
        schema_version: Literal["1.0"] = "1.0",
    ) -> GetModelAttributeMappingsResult:
        del schema_version
        try:
            model, rows, next_cursor = await _read_mappings(
                database=database,
                identity_provider=identity_provider,
                authorizer=authorizer,
                ctx=ctx,
                cursors=cursors,
                tool_name="get_model_attribute_mappings",
                query=MAPPING_ATTRIBUTES_SQL,
                model_id=model_id,
                object_ids=object_ids,
                page_size=page_size,
                cursor=cursor,
            )
            return GetModelAttributeMappingsResult(
                model_id=model.model_id,
                model_revision=model.model_revision,
                mappings=tuple(
                    MappingAttributeResult.model_validate(row, strict=False) for row in rows
                ),
                next_cursor=next_cursor,
            )
        except AuthenticationError as error:
            raise MappingToolError(f"{error.public_code}: {error.message}") from None
        except WorkbenchError as error:
            raise MappingToolError(f"{error.code}: {error.message}") from None
        except Exception:
            raise MappingToolError(
                "internal_error: The operation could not be completed."
            ) from None

    audit.register_tool(
        "get_model_attribute_mappings",
        policy=POLICY,
        summarize_input=_audit_input,
        retain_arguments={"model_id", "page_size", "schema_version"},
    )


async def _read_mappings(
    *,
    database: Database,
    identity_provider: IdentityProvider,
    authorizer: AuthorizationService,
    ctx: Context[None],
    cursors: CursorCodec,
    tool_name: str,
    query: LiteralString,
    model_id: int,
    object_ids: tuple[int, ...],
    page_size: int,
    cursor: str | None,
) -> tuple[Any, list[dict[str, object]], str | None]:
    _validate_ids(object_ids)
    collection = (
        f"{tool_name}:{model_id}:{','.join(str(object_id) for object_id in object_ids)}:{page_size}"
    )
    offset = cursors.decode(cursor, collection=collection)
    principal = identity_provider.request_principal(ctx.request_context.request)
    async with database.read_transaction(isolation=ReadIsolation.REPEATABLE_READ) as transaction:
        model = await authorize_model_read(
            transaction,
            authorizer=authorizer,
            principal=principal,
            model_id=model_id,
        )
        await validate_model_object_selection(
            transaction,
            model_id=model.model_id,
            object_ids=object_ids,
        )
        rows = await transaction.fetch_all(
            query,
            (
                model.model_id,
                list(object_ids),
                list(object_ids),
                page_size + 1,
                offset,
            ),
        )
    return (
        model,
        rows[:page_size],
        _next_cursor(cursors, collection, offset, page_size, len(rows)),
    )


def _annotations() -> ToolAnnotations:
    return ToolAnnotations(
        read_only_hint=True,
        destructive_hint=False,
        idempotent_hint=True,
        open_world_hint=False,
    )


def _validate_ids(ids: tuple[int, ...]) -> None:
    if any(identifier <= 0 for identifier in ids) or len(set(ids)) != len(ids):
        raise InvalidRequestError("Object IDs must be unique positive integers.")


def _next_cursor(
    cursors: CursorCodec,
    collection: str,
    offset: int,
    page_size: int,
    row_count: int,
) -> str | None:
    if row_count <= page_size:
        return None
    return cursors.encode(collection=collection, offset=offset + page_size)


def _audit_input(arguments: Mapping[str, Any]) -> dict[str, str | int | bool]:
    model_id = arguments.get("model_id")
    object_ids = arguments.get("object_ids", [])
    page_size = arguments.get("page_size", 50)
    return {
        "schema_version": ("1.0" if arguments.get("schema_version", "1.0") == "1.0" else "invalid"),
        "model_id": model_id if type(model_id) is int and model_id > 0 else "invalid",
        "object_count": (
            len(cast(list[object], object_ids)) if isinstance(object_ids, list) else "invalid"
        ),
        "page_size": (
            page_size if type(page_size) is int and 1 <= page_size <= _MAX_PAGE_SIZE else "invalid"
        ),
        "cursor_provided": arguments.get("cursor") is not None,
    }
