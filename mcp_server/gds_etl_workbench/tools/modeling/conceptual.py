"""Applied Conceptual Object and Relationship card reads."""

# Pyright cannot see that @server.tool registers these nested handlers.
# pyright: reportUnusedFunction=false
# Immutable Pydantic read cards intentionally specialize nested write-record fields with IDs.
# pyright: reportIncompatibleVariableOverride=false

from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Annotated, Any, Literal, LiteralString, cast

from pydantic import Field

from gds_etl_workbench.adapters.auth.identity import AuthenticationError, IdentityProvider
from gds_etl_workbench.application.authorization import AuthorizationService
from gds_etl_workbench.application.cursor import CursorCodec
from gds_etl_workbench.domain.errors import InvalidRequestError, WorkbenchError
from gds_etl_workbench.domain.modeling_records import (
    AssertionRecordKey,
    AssertionSupportRecord,
    ConceptualObjectRecord,
    ConceptualRelationshipRecord,
    ObjectSupportRecord,
    PhysicalObjectKey,
)
from gds_etl_workbench.infrastructure.postgres import Database, ReadIsolation, ReadTransaction

from .common import (
    MAX_OBJECT_FILTER,
    POLICY,
    ContractModel,
    authorize_model_read,
    validate_model_object_selection,
)

if TYPE_CHECKING:
    from mcp.server.mcpserver import Context, MCPServer
    from mcp.types import ToolAnnotations

    from gds_etl_workbench.adapters.mcp.tool_audit import ToolCallAuditMiddleware

_MAX_PAGE_SIZE = 200

_ELIGIBLE_OBJECTS_CTE = """
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
"""

_SUPPORT_JSON_SQL = """
COALESCE((
    SELECT jsonb_agg(
               CASE support.support_source_type
                   WHEN 'object' THEN jsonb_build_object(
                       'conceptual_support_id', support.conceptual_support_id,
                       'support_source_type', 'object',
                       'source_object', jsonb_build_object(
                           'object_id', source_object.object_id,
                           'tenant_code', source_tenant.tenant_code,
                           'system_code', source_system.system_code,
                           'connection_code', source_connection.connection_code,
                           'object_schema', source_object.object_schema,
                           'object_name', source_object.object_name
                       ),
                       'support_role', support.conceptual_support_role,
                       'support_reason', support.conceptual_support_reason,
                       'support_reason_detail', support.conceptual_support_reason_detail,
                       'support_confidence', support.conceptual_support_confidence,
                       'support_status', support.conceptual_support_status,
                       'support_is_locked', support.conceptual_support_is_locked
                   )
                   ELSE jsonb_build_object(
                       'conceptual_support_id', support.conceptual_support_id,
                       'support_source_type', 'assertion',
                       'assertion_record', jsonb_build_object(
                           'modeling_assertion_record_id',
                               assertion_record.modeling_assertion_record_id,
                           'modeling_assertion_record_key',
                               assertion_record.modeling_assertion_record_key
                       ),
                       'support_role', support.conceptual_support_role,
                       'support_reason', support.conceptual_support_reason,
                       'support_reason_detail', support.conceptual_support_reason_detail,
                       'support_confidence', support.conceptual_support_confidence,
                       'support_status', support.conceptual_support_status,
                       'support_is_locked', support.conceptual_support_is_locked
                   )
               END
               ORDER BY support.conceptual_support_id
           )
      FROM workflow.conceptual_support AS support
      LEFT JOIN core.object AS source_object
        ON source_object.object_id = support.source_object_id
      LEFT JOIN core.connection AS source_connection
        ON source_connection.connection_id = source_object.connection_id
      LEFT JOIN eligible_objects AS source_eligibility
        ON source_eligibility.object_id = support.source_object_id
       AND source_eligibility.model_id = support.model_id
       AND source_eligibility.is_bronze_source_eligible
      LEFT JOIN core.tenant AS source_tenant
        ON source_tenant.tenant_id = source_eligibility.object_tenant_id
      LEFT JOIN core.system AS source_system
        ON source_system.system_id = source_connection.system_id
      LEFT JOIN model.modeling_assertion_record AS assertion_record
        ON assertion_record.modeling_assertion_record_id = support.modeling_assertion_record_id
       AND assertion_record.model_id = support.model_id
     WHERE support.model_id = parent.model_id
       AND support.supported_artifact_type = '{supported_artifact_type}'
       AND support.{parent_id_column} = parent.{parent_id_column}
       AND (
           support.support_source_type <> 'object'
           OR EXISTS (
               SELECT 1
                 FROM eligible_objects AS eligibility
                WHERE eligibility.object_id = support.source_object_id
                  AND eligibility.model_id = support.model_id
                  AND eligibility.is_bronze_source_eligible
           )
       )
), '[]'::JSONB) AS supports
"""

CONCEPTUAL_OBJECTS_SQL: LiteralString = f"""
{_ELIGIBLE_OBJECTS_CTE}
SELECT parent.conceptual_object_id,
       parent.conceptual_object_name,
       parent.conceptual_object_definition,
       parent.conceptual_object_type,
       parent.conceptual_object_grain,
       parent.conceptual_object_aliases,
       parent.conceptual_object_confidence,
       parent.conceptual_object_status,
       parent.conceptual_object_is_locked,
       {
    _SUPPORT_JSON_SQL.format(
        supported_artifact_type="conceptual_object",
        parent_id_column="conceptual_object_id",
    )
}
  FROM workflow.conceptual_object AS parent
 WHERE parent.model_id = (SELECT model_id FROM requested_model)
   AND (
       cardinality(%s::BIGINT[]) = 0
       OR EXISTS (
           SELECT 1
             FROM workflow.conceptual_support AS selected_support
            WHERE selected_support.model_id = parent.model_id
              AND selected_support.conceptual_object_id = parent.conceptual_object_id
              AND selected_support.support_source_type = 'object'
              AND selected_support.source_object_id = ANY(%s::BIGINT[])
              AND EXISTS (
                  SELECT 1
                    FROM eligible_objects AS eligibility
                   WHERE eligibility.object_id = selected_support.source_object_id
                     AND eligibility.model_id = selected_support.model_id
                     AND eligibility.is_bronze_source_eligible
              )
       )
   )
 ORDER BY lower(parent.conceptual_object_name), parent.conceptual_object_id
 LIMIT %s OFFSET %s
"""

CONCEPTUAL_RELATIONSHIPS_SQL: LiteralString = f"""
{_ELIGIBLE_OBJECTS_CTE}
SELECT parent.conceptual_relationship_id,
       parent.from_conceptual_object_id,
       from_object.conceptual_object_name AS from_conceptual_object_name,
       parent.to_conceptual_object_id,
       to_object.conceptual_object_name AS to_conceptual_object_name,
       parent.conceptual_relationship_name,
       parent.conceptual_relationship_type,
       parent.conceptual_relationship_definition,
       parent.conceptual_relationship_cardinality,
       parent.conceptual_relationship_basis,
       parent.conceptual_relationship_cardinality_basis,
       parent.conceptual_relationship_confidence,
       parent.conceptual_relationship_status,
       parent.conceptual_relationship_is_locked,
       {
    _SUPPORT_JSON_SQL.format(
        supported_artifact_type="conceptual_relationship",
        parent_id_column="conceptual_relationship_id",
    )
}
  FROM workflow.conceptual_relationship AS parent
  JOIN workflow.conceptual_object AS from_object
    ON from_object.conceptual_object_id = parent.from_conceptual_object_id
   AND from_object.model_id = parent.model_id
  JOIN workflow.conceptual_object AS to_object
    ON to_object.conceptual_object_id = parent.to_conceptual_object_id
   AND to_object.model_id = parent.model_id
 WHERE parent.model_id = (SELECT model_id FROM requested_model)
   AND (
       cardinality(%s::BIGINT[]) = 0
       OR parent.from_conceptual_object_id = ANY(%s::BIGINT[])
       OR parent.to_conceptual_object_id = ANY(%s::BIGINT[])
   )
 ORDER BY parent.from_conceptual_object_id,
          parent.to_conceptual_object_id,
          lower(parent.conceptual_relationship_name),
          parent.conceptual_relationship_id
 LIMIT %s OFFSET %s
"""

_CONCEPTUAL_OBJECT_COUNT_SQL: LiteralString = """
SELECT count(*) AS object_count
  FROM workflow.conceptual_object
 WHERE model_id = %s
   AND conceptual_object_id = ANY(%s::BIGINT[])
"""


class ReadPhysicalObjectKey(PhysicalObjectKey):
    object_id: int = Field(gt=0)


class ReadAssertionRecordKey(AssertionRecordKey):
    modeling_assertion_record_id: int = Field(gt=0)


class ObjectSupportResult(ObjectSupportRecord):
    conceptual_support_id: int = Field(gt=0)
    source_object: ReadPhysicalObjectKey


class AssertionSupportResult(AssertionSupportRecord):
    conceptual_support_id: int = Field(gt=0)
    assertion_record: ReadAssertionRecordKey


type SupportResult = Annotated[
    ObjectSupportResult | AssertionSupportResult,
    Field(discriminator="support_source_type"),
]


class ConceptualObjectResult(ConceptualObjectRecord):
    conceptual_object_id: int = Field(gt=0)
    supports: tuple[SupportResult, ...]


class ConceptualRelationshipResult(ConceptualRelationshipRecord):
    conceptual_relationship_id: int = Field(gt=0)
    from_conceptual_object_id: int = Field(gt=0)
    to_conceptual_object_id: int = Field(gt=0)
    supports: tuple[SupportResult, ...]


class GetModelConceptualObjectsResult(ContractModel):
    schema_version: Literal["1.0"] = "1.0"
    model_id: int = Field(gt=0)
    model_revision: int = Field(gt=0)
    objects: tuple[ConceptualObjectResult, ...] = Field(max_length=_MAX_PAGE_SIZE)
    next_cursor: str | None = Field(default=None, max_length=2048)


class GetModelConceptualRelationshipsResult(ContractModel):
    schema_version: Literal["1.0"] = "1.0"
    model_id: int = Field(gt=0)
    model_revision: int = Field(gt=0)
    relationships: tuple[ConceptualRelationshipResult, ...] = Field(max_length=_MAX_PAGE_SIZE)
    next_cursor: str | None = Field(default=None, max_length=2048)


class ConceptualToolError(Exception):
    """A bounded Conceptual-read failure safe for MCP serialization."""


def register_conceptual_tools(
    server: MCPServer[None],
    *,
    database: Database,
    identity_provider: IdentityProvider,
    authorizer: AuthorizationService,
    audit: ToolCallAuditMiddleware,
    cursor_signing_key: bytes,
) -> None:
    from mcp.server.mcpserver import Context as McpContext

    globals()["Context"] = McpContext
    cursors = CursorCodec(cursor_signing_key)

    @server.tool(
        description=(
            "Get applied Conceptual Object cards, including all support. An empty "
            "supporting Object-ID list selects all Conceptual Objects."
        ),
        annotations=_annotations(),
        meta={"gds/toolPolicy": POLICY.value},
        structured_output=True,
    )
    async def get_model_conceptual_objects(
        ctx: Context[None],
        model_id: Annotated[int, Field(gt=0)],
        supporting_object_ids: Annotated[tuple[int, ...], Field(max_length=MAX_OBJECT_FILTER)] = (),
        page_size: Annotated[int, Field(ge=1, le=_MAX_PAGE_SIZE)] = 50,
        cursor: Annotated[str | None, Field(max_length=2048)] = None,
        schema_version: Literal["1.0"] = "1.0",
    ) -> GetModelConceptualObjectsResult:
        del schema_version
        try:
            _validate_ids(supporting_object_ids)
            collection = _collection(
                "get_model_conceptual_objects", model_id, supporting_object_ids, page_size
            )
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
                await validate_model_object_selection(
                    transaction,
                    model_id=model.model_id,
                    object_ids=supporting_object_ids,
                )
                rows = await transaction.fetch_all(
                    CONCEPTUAL_OBJECTS_SQL,
                    (
                        model.model_id,
                        list(supporting_object_ids),
                        list(supporting_object_ids),
                        page_size + 1,
                        offset,
                    ),
                )
            return GetModelConceptualObjectsResult(
                model_id=model.model_id,
                model_revision=model.model_revision,
                objects=tuple(
                    ConceptualObjectResult.model_validate(row, strict=False)
                    for row in rows[:page_size]
                ),
                next_cursor=_next_cursor(cursors, collection, offset, page_size, len(rows)),
            )
        except AuthenticationError as error:
            raise ConceptualToolError(f"{error.public_code}: {error.message}") from None
        except WorkbenchError as error:
            raise ConceptualToolError(f"{error.code}: {error.message}") from None
        except Exception:
            raise ConceptualToolError(
                "internal_error: The operation could not be completed."
            ) from None

    audit.register_tool(
        "get_model_conceptual_objects",
        policy=POLICY,
        summarize_input=lambda arguments: _audit_input(arguments, "supporting_object_ids"),
        retain_arguments={"model_id", "page_size", "schema_version"},
    )

    @server.tool(
        description=(
            "Get applied Conceptual Relationship cards, including all support. An "
            "empty Conceptual Object-ID list selects all Relationships."
        ),
        annotations=_annotations(),
        meta={"gds/toolPolicy": POLICY.value},
        structured_output=True,
    )
    async def get_model_conceptual_relationships(
        ctx: Context[None],
        model_id: Annotated[int, Field(gt=0)],
        conceptual_object_ids: Annotated[tuple[int, ...], Field(max_length=MAX_OBJECT_FILTER)] = (),
        page_size: Annotated[int, Field(ge=1, le=_MAX_PAGE_SIZE)] = 50,
        cursor: Annotated[str | None, Field(max_length=2048)] = None,
        schema_version: Literal["1.0"] = "1.0",
    ) -> GetModelConceptualRelationshipsResult:
        del schema_version
        try:
            _validate_ids(conceptual_object_ids)
            collection = _collection(
                "get_model_conceptual_relationships",
                model_id,
                conceptual_object_ids,
                page_size,
            )
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
                await _validate_conceptual_objects(
                    transaction,
                    model_id=model.model_id,
                    conceptual_object_ids=conceptual_object_ids,
                )
                rows = await transaction.fetch_all(
                    CONCEPTUAL_RELATIONSHIPS_SQL,
                    (
                        model.model_id,
                        list(conceptual_object_ids),
                        list(conceptual_object_ids),
                        list(conceptual_object_ids),
                        page_size + 1,
                        offset,
                    ),
                )
            return GetModelConceptualRelationshipsResult(
                model_id=model.model_id,
                model_revision=model.model_revision,
                relationships=tuple(
                    ConceptualRelationshipResult.model_validate(row, strict=False)
                    for row in rows[:page_size]
                ),
                next_cursor=_next_cursor(cursors, collection, offset, page_size, len(rows)),
            )
        except AuthenticationError as error:
            raise ConceptualToolError(f"{error.public_code}: {error.message}") from None
        except WorkbenchError as error:
            raise ConceptualToolError(f"{error.code}: {error.message}") from None
        except Exception:
            raise ConceptualToolError(
                "internal_error: The operation could not be completed."
            ) from None

    audit.register_tool(
        "get_model_conceptual_relationships",
        policy=POLICY,
        summarize_input=lambda arguments: _audit_input(arguments, "conceptual_object_ids"),
        retain_arguments={"model_id", "page_size", "schema_version"},
    )


async def _validate_conceptual_objects(
    transaction: ReadTransaction,
    *,
    model_id: int,
    conceptual_object_ids: tuple[int, ...],
) -> None:
    if not conceptual_object_ids:
        return
    row = await transaction.fetch_one(
        _CONCEPTUAL_OBJECT_COUNT_SQL,
        (model_id, list(conceptual_object_ids)),
    )
    if row is None or row["object_count"] != len(conceptual_object_ids):
        raise InvalidRequestError("One or more Conceptual Objects are not in the Model.")


def _annotations() -> ToolAnnotations:
    from mcp.types import ToolAnnotations

    return ToolAnnotations(
        read_only_hint=True,
        destructive_hint=False,
        idempotent_hint=True,
        open_world_hint=False,
    )


def _validate_ids(ids: tuple[int, ...]) -> None:
    if any(identifier <= 0 for identifier in ids) or len(set(ids)) != len(ids):
        raise InvalidRequestError("IDs must be unique positive integers.")


def _collection(tool: str, model_id: int, ids: tuple[int, ...], page_size: int) -> str:
    return f"{tool}:{model_id}:{','.join(str(identifier) for identifier in ids)}:{page_size}"


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


def _audit_input(arguments: Mapping[str, Any], id_argument: str) -> dict[str, str | int | bool]:
    model_id = arguments.get("model_id")
    ids = arguments.get(id_argument, [])
    page_size = arguments.get("page_size", 50)
    return {
        "schema_version": ("1.0" if arguments.get("schema_version", "1.0") == "1.0" else "invalid"),
        "model_id": model_id if type(model_id) is int and model_id > 0 else "invalid",
        "selected_id_count": (len(cast(list[object], ids)) if isinstance(ids, list) else "invalid"),
        "page_size": (
            page_size if type(page_size) is int and 1 <= page_size <= _MAX_PAGE_SIZE else "invalid"
        ),
        "cursor_provided": arguments.get("cursor") is not None,
    }
