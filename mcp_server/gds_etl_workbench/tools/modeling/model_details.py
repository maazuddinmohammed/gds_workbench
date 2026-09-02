"""Bounded Model headers and policy fields for one authorized Tenant."""

# Pyright cannot see that @server.tool registers this nested handler.
# pyright: reportUnusedFunction=false

from __future__ import annotations

from collections.abc import Mapping
from typing import Annotated, Any, Literal, LiteralString

from mcp.server.mcpserver import Context, MCPServer
from mcp.types import ToolAnnotations
from pydantic import BaseModel, ConfigDict, Field, JsonValue

from gds_etl_workbench.adapters.auth.identity import AuthenticationError, IdentityProvider
from gds_etl_workbench.adapters.mcp.tool_audit import ToolCallAuditMiddleware
from gds_etl_workbench.application.authorization import AuthorizationService
from gds_etl_workbench.application.cursor import CursorCodec
from gds_etl_workbench.domain.authorization import ToolPolicy
from gds_etl_workbench.domain.errors import WorkbenchError
from gds_etl_workbench.infrastructure.postgres import Database, ReadIsolation

_TOOL_NAME = "list_models"
_MAX_MODELS = 200
POLICY = ToolPolicy.TENANT_READ

_MODELS_SQL: LiteralString = """
SELECT model.model_id,
       model.model_name,
       left(model.model_description, 2000) AS model_description,
       model.model_revision,
       model.silver_model_naming_instructions,
       model.silver_model_audit_columns_template,
       model.gold_model_naming_instructions,
       model.gold_model_technical_columns_template,
       model.gold_model_audit_columns_template,
       count(model_input_scope.object_id) AS model_input_scope_object_count,
       count(*) OVER () AS total_model_count
  FROM model.model AS model
  LEFT JOIN model.model_input_scope AS model_input_scope
    ON model_input_scope.model_id = model.model_id
   AND model_input_scope.is_active
 WHERE model.tenant_id = %s
   AND model.is_active
 GROUP BY model.model_id
 ORDER BY lower(model.model_name), model.model_id
 LIMIT %s OFFSET %s
"""


class ContractModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class ModelDetails(ContractModel):
    model_id: int = Field(gt=0)
    model_name: str = Field(min_length=1, max_length=255)
    model_description: str | None = Field(default=None, max_length=2000)
    model_revision: int = Field(gt=0)
    silver_model_naming_instructions: str | None = Field(default=None, max_length=32768)
    silver_model_audit_columns_template: dict[str, JsonValue] | None
    gold_model_naming_instructions: str | None = Field(default=None, max_length=32768)
    gold_model_technical_columns_template: dict[str, JsonValue] | None
    gold_model_audit_columns_template: dict[str, JsonValue] | None
    model_input_scope_object_count: int = Field(ge=0)


class ListModelsResult(ContractModel):
    schema_version: Literal["1.0"] = "1.0"
    tenant_id: int = Field(gt=0)
    model_count: int = Field(ge=0)
    models: tuple[ModelDetails, ...] = Field(max_length=_MAX_MODELS)
    models_truncated: bool
    next_cursor: str | None = Field(default=None, max_length=2048)


class SafeToolError(Exception):
    """A tool failure whose text is safe for the MCP SDK to serialize."""


def register_list_models_tool(
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
            "List active Models for one authorized Tenant. Returns paginated Model IDs, "
            "names, revisions, naming policies, column templates, and active Input Scope "
            "counts; use the returned model_id with Model-scoped tools."
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
    async def list_models(
        ctx: Context[None],
        tenant_id: Annotated[int, Field(gt=0)],
        page_size: Annotated[int, Field(ge=1, le=_MAX_MODELS)] = _MAX_MODELS,
        cursor: Annotated[str | None, Field(max_length=2048)] = None,
        schema_version: Literal["1.0"] = "1.0",
    ) -> ListModelsResult:
        del schema_version
        try:
            principal = identity_provider.request_principal(ctx.request_context.request)
            collection = f"{_TOOL_NAME}:{tenant_id}:{page_size}"
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
                    _MODELS_SQL,
                    (tenant_id, page_size + 1, offset),
                )
            model_count = 0 if not rows else int(rows[0]["total_model_count"])
            next_cursor = (
                cursors.encode(collection=collection, offset=offset + page_size)
                if len(rows) > page_size
                else None
            )
            return ListModelsResult(
                tenant_id=tenant_id,
                model_count=model_count,
                models=tuple(
                    ModelDetails(
                        **{
                            name: value
                            for name, value in row.items()
                            if name != "total_model_count"
                        }
                    )
                    for row in rows[:page_size]
                ),
                models_truncated=len(rows) > page_size,
                next_cursor=next_cursor,
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
        retain_arguments={"tenant_id", "page_size", "schema_version"},
        tenant_argument="tenant_id",
    )


def _audit_input_metadata(arguments: Mapping[str, Any]) -> dict[str, str | int | bool]:
    tenant_id = arguments.get("tenant_id")
    page_size = arguments.get("page_size", _MAX_MODELS)
    return {
        "schema_version": ("1.0" if arguments.get("schema_version", "1.0") == "1.0" else "invalid"),
        "tenant_id": tenant_id if type(tenant_id) is int and tenant_id > 0 else "invalid",
        "page_size": (
            page_size if type(page_size) is int and 1 <= page_size <= _MAX_MODELS else "invalid"
        ),
        "cursor_provided": arguments.get("cursor") is not None,
    }
