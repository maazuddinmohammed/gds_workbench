"""Bounded Model headers and policy templates for one authorized Tenant."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Annotated, Any, Literal, LiteralString

from mcp.server.mcpserver import Context, MCPServer
from mcp.types import ToolAnnotations
from pydantic import BaseModel, ConfigDict, Field, JsonValue

from gds_etl_workbench.adapters.auth.identity import AuthenticationError, IdentityProvider
from gds_etl_workbench.adapters.mcp.tool_audit import ToolCallAuditMiddleware
from gds_etl_workbench.application.authorization import AuthorizationService
from gds_etl_workbench.domain.authorization import ToolPolicy
from gds_etl_workbench.domain.errors import WorkbenchError
from gds_etl_workbench.infrastructure.postgres import Database, ReadIsolation

_TOOL_NAME = "get_model"
_MAX_MODELS = 200
POLICY = ToolPolicy.TENANT_READ

_MODELS_SQL: LiteralString = """
SELECT model.model_id,
       model.model_name,
       left(model.model_description, 2000) AS model_description,
       model.model_revision,
       model.silver_model_naming_template,
       model.silver_model_audit_columns_template,
       model.gold_model_naming_template,
       model.gold_model_technical_columns_template,
       model.gold_model_audit_columns_template,
       count(model_scope.object_id) AS model_scope_object_count,
       count(*) OVER () AS total_model_count
  FROM model.model AS model
  LEFT JOIN model.model_scope AS model_scope
    ON model_scope.model_id = model.model_id
   AND model_scope.is_active
 WHERE model.tenant_id = %s
   AND model.is_active
 GROUP BY model.model_id
 ORDER BY lower(model.model_name), model.model_id
 LIMIT %s
"""


class ContractModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class ModelDetails(ContractModel):
    model_id: int = Field(gt=0)
    model_name: str = Field(min_length=1, max_length=255)
    model_description: str | None = Field(default=None, max_length=2000)
    model_revision: int = Field(gt=0)
    silver_model_naming_template: dict[str, JsonValue] | None
    silver_model_audit_columns_template: dict[str, JsonValue] | None
    gold_model_naming_template: dict[str, JsonValue] | None
    gold_model_technical_columns_template: dict[str, JsonValue] | None
    gold_model_audit_columns_template: dict[str, JsonValue] | None
    model_scope_object_count: int = Field(ge=0)


class GetModelResult(ContractModel):
    schema_version: Literal["1.0"] = "1.0"
    tenant_id: int = Field(gt=0)
    model_count: int = Field(ge=0)
    models: tuple[ModelDetails, ...] = Field(max_length=_MAX_MODELS)
    models_truncated: bool


class SafeToolError(Exception):
    """A tool failure whose text is safe for the MCP SDK to serialize."""


def register_get_model_tool(
    server: MCPServer[None],
    *,
    database: Database,
    identity_provider: IdentityProvider,
    authorizer: AuthorizationService,
    audit: ToolCallAuditMiddleware,
) -> None:
    @server.tool(
        description=(
            "Get active Model details for one authorized Tenant, including revision, "
            "naming/audit policy templates, and current Model Scope Object count."
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
    async def get_model(
        ctx: Context[None],
        tenant_id: Annotated[int, Field(gt=0)],
        schema_version: Literal["1.0"] = "1.0",
    ) -> GetModelResult:
        del schema_version
        try:
            principal = identity_provider.request_principal(ctx.request_context.request)
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
                    (tenant_id, _MAX_MODELS + 1),
                )
            model_count = 0 if not rows else int(rows[0]["total_model_count"])
            return GetModelResult(
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
                    for row in rows[:_MAX_MODELS]
                ),
                models_truncated=model_count > _MAX_MODELS,
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
        retain_arguments={"tenant_id", "schema_version"},
        tenant_argument="tenant_id",
    )


def _audit_input_metadata(arguments: Mapping[str, Any]) -> dict[str, str | int]:
    tenant_id = arguments.get("tenant_id")
    return {
        "schema_version": (
            "1.0" if arguments.get("schema_version", "1.0") == "1.0" else "invalid"
        ),
        "tenant_id": tenant_id if type(tenant_id) is int and tenant_id > 0 else "invalid",
    }
