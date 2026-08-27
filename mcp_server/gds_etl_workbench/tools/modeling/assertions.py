"""Applied Modeling Assertion reads for one governed Model."""

# Pyright cannot see that @server.tool registers these nested handlers.
# pyright: reportUnusedFunction=false

from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Annotated, Any, Literal, LiteralString, cast

from pydantic import Field

from gds_etl_workbench.adapters.auth.identity import AuthenticationError, IdentityProvider
from gds_etl_workbench.application.authorization import AuthorizationService
from gds_etl_workbench.application.cursor import CursorCodec
from gds_etl_workbench.domain.errors import InvalidRequestError, WorkbenchError
from gds_etl_workbench.domain.modeling_records import (
    ModelingAssertionDocumentRecord,
    ModelingAssertionRecordRecord,
)
from gds_etl_workbench.infrastructure.postgres import Database, ReadIsolation

from .common import MAX_OBJECT_FILTER, POLICY, ContractModel, authorize_model_read

if TYPE_CHECKING:
    from mcp.server.mcpserver import Context, MCPServer
    from mcp.types import ToolAnnotations

    from gds_etl_workbench.adapters.mcp.tool_audit import ToolCallAuditMiddleware

_MAX_PAGE_SIZE = 200

DOCUMENTS_SQL: LiteralString = """
SELECT document.modeling_assertion_document_id,
       document.modeling_assertion_document_name,
       tenant.tenant_code,
       system.system_code,
       document.modeling_assertion_file_pattern,
       document.modeling_assertion_document_type,
       document.modeling_assertion_document_description,
       document.modeling_assertion_document_metadata,
       document.is_active
  FROM model.modeling_assertion_document AS document
  LEFT JOIN core.tenant AS tenant
    ON tenant.tenant_id = document.tenant_id
  LEFT JOIN core.system AS system
    ON system.system_id = document.system_id
 WHERE document.model_id = %s
 ORDER BY lower(document.modeling_assertion_document_name),
          document.modeling_assertion_document_id
 LIMIT %s OFFSET %s
"""

_DOCUMENT_COUNT_SQL: LiteralString = """
SELECT count(*) AS document_count
  FROM model.modeling_assertion_document
 WHERE model_id = %s
   AND modeling_assertion_document_id = ANY(%s::BIGINT[])
"""

RECORDS_SQL: LiteralString = """
SELECT record.modeling_assertion_record_id,
       record.modeling_assertion_document_id,
       record.modeling_assertion_record_key,
       document.modeling_assertion_document_name,
       record.modeling_assertion_record_type,
       record.modeling_assertion_text,
       record.modeling_assertion_details,
       record.modeling_assertion_source_location,
       record.modeling_assertion_applicable_layers,
       record.modeling_assertion_confidence,
       record.modeling_assertion_record_status,
       record.modeling_assertion_record_is_locked
  FROM model.modeling_assertion_record AS record
  JOIN model.modeling_assertion_document AS document
    ON document.modeling_assertion_document_id = record.modeling_assertion_document_id
   AND document.model_id = record.model_id
 WHERE record.model_id = %s
   AND (
       cardinality(%s::BIGINT[]) = 0
       OR record.modeling_assertion_document_id = ANY(%s::BIGINT[])
   )
 ORDER BY lower(document.modeling_assertion_document_name),
          lower(record.modeling_assertion_record_key),
          record.modeling_assertion_record_id
 LIMIT %s OFFSET %s
"""


class AssertionDocumentResult(ModelingAssertionDocumentRecord):
    modeling_assertion_document_id: int = Field(gt=0)


class AssertionRecordResult(ModelingAssertionRecordRecord):
    modeling_assertion_record_id: int = Field(gt=0)
    modeling_assertion_document_id: int = Field(gt=0)


class GetModelingAssertionDocumentsResult(ContractModel):
    schema_version: Literal["1.0"] = "1.0"
    model_id: int = Field(gt=0)
    model_revision: int = Field(gt=0)
    documents: tuple[AssertionDocumentResult, ...] = Field(max_length=_MAX_PAGE_SIZE)
    next_cursor: str | None = Field(default=None, max_length=2048)


class GetModelingAssertionRecordsResult(ContractModel):
    schema_version: Literal["1.0"] = "1.0"
    model_id: int = Field(gt=0)
    model_revision: int = Field(gt=0)
    records: tuple[AssertionRecordResult, ...] = Field(max_length=_MAX_PAGE_SIZE)
    next_cursor: str | None = Field(default=None, max_length=2048)


class ModelingAssertionToolError(Exception):
    """A bounded Assertion-read failure safe for MCP serialization."""


def register_modeling_assertion_tools(
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
        description="Get all applied Modeling Assertion Documents for one Model.",
        annotations=_annotations(),
        meta={"gds/toolPolicy": POLICY.value},
        structured_output=True,
    )
    async def get_modeling_assertion_documents(
        ctx: Context[None],
        model_id: Annotated[int, Field(gt=0)],
        page_size: Annotated[int, Field(ge=1, le=_MAX_PAGE_SIZE)] = 50,
        cursor: Annotated[str | None, Field(max_length=2048)] = None,
        schema_version: Literal["1.0"] = "1.0",
    ) -> GetModelingAssertionDocumentsResult:
        del schema_version
        try:
            collection = f"get_modeling_assertion_documents:{model_id}:{page_size}"
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
                    DOCUMENTS_SQL,
                    (model.model_id, page_size + 1, offset),
                )
            return GetModelingAssertionDocumentsResult(
                model_id=model.model_id,
                model_revision=model.model_revision,
                documents=tuple(
                    AssertionDocumentResult.model_validate(row, strict=False)
                    for row in rows[:page_size]
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
            raise ModelingAssertionToolError(f"{error.public_code}: {error.message}") from None
        except WorkbenchError as error:
            raise ModelingAssertionToolError(f"{error.code}: {error.message}") from None
        except Exception:
            raise ModelingAssertionToolError(
                "internal_error: The operation could not be completed."
            ) from None

    audit.register_tool(
        "get_modeling_assertion_documents",
        policy=POLICY,
        summarize_input=_audit_model_input,
        retain_arguments={"model_id", "page_size", "schema_version"},
    )

    @server.tool(
        description=(
            "Get applied Modeling Assertion Records for one Model. An empty "
            "Document-ID list selects all Records."
        ),
        annotations=_annotations(),
        meta={"gds/toolPolicy": POLICY.value},
        structured_output=True,
    )
    async def get_modeling_assertion_records(
        ctx: Context[None],
        model_id: Annotated[int, Field(gt=0)],
        modeling_assertion_document_ids: Annotated[
            tuple[int, ...],
            Field(max_length=MAX_OBJECT_FILTER),
        ] = (),
        page_size: Annotated[int, Field(ge=1, le=_MAX_PAGE_SIZE)] = 50,
        cursor: Annotated[str | None, Field(max_length=2048)] = None,
        schema_version: Literal["1.0"] = "1.0",
    ) -> GetModelingAssertionRecordsResult:
        del schema_version
        try:
            _validate_ids(modeling_assertion_document_ids)
            selected = ",".join(str(document_id) for document_id in modeling_assertion_document_ids)
            collection = f"get_modeling_assertion_records:{model_id}:{selected}:{page_size}"
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
                if modeling_assertion_document_ids:
                    count = await transaction.fetch_one(
                        _DOCUMENT_COUNT_SQL,
                        (model.model_id, list(modeling_assertion_document_ids)),
                    )
                    if count is None or count["document_count"] != len(
                        modeling_assertion_document_ids
                    ):
                        raise InvalidRequestError(
                            "One or more Assertion Documents are not in the Model."
                        )
                rows = await transaction.fetch_all(
                    RECORDS_SQL,
                    (
                        model.model_id,
                        list(modeling_assertion_document_ids),
                        list(modeling_assertion_document_ids),
                        page_size + 1,
                        offset,
                    ),
                )
            return GetModelingAssertionRecordsResult(
                model_id=model.model_id,
                model_revision=model.model_revision,
                records=tuple(
                    AssertionRecordResult.model_validate(row, strict=False)
                    for row in rows[:page_size]
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
            raise ModelingAssertionToolError(f"{error.public_code}: {error.message}") from None
        except WorkbenchError as error:
            raise ModelingAssertionToolError(f"{error.code}: {error.message}") from None
        except Exception:
            raise ModelingAssertionToolError(
                "internal_error: The operation could not be completed."
            ) from None

    audit.register_tool(
        "get_modeling_assertion_records",
        policy=POLICY,
        summarize_input=_audit_record_input,
        retain_arguments={"model_id", "page_size", "schema_version"},
    )


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


def _audit_model_input(arguments: Mapping[str, Any]) -> dict[str, str | int | bool]:
    model_id = arguments.get("model_id")
    page_size = arguments.get("page_size", 50)
    return {
        "schema_version": ("1.0" if arguments.get("schema_version", "1.0") == "1.0" else "invalid"),
        "model_id": model_id if type(model_id) is int and model_id > 0 else "invalid",
        "page_size": (
            page_size if type(page_size) is int and 1 <= page_size <= _MAX_PAGE_SIZE else "invalid"
        ),
        "cursor_provided": arguments.get("cursor") is not None,
    }


def _audit_record_input(arguments: Mapping[str, Any]) -> dict[str, str | int | bool]:
    metadata = _audit_model_input(arguments)
    ids = arguments.get("modeling_assertion_document_ids", [])
    return {
        **metadata,
        "document_count": len(cast(list[object], ids)) if isinstance(ids, list) else "invalid",
    }
