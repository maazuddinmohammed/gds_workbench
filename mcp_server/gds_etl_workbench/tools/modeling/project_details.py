"""Bounded Project headers and policy fields for one authorized Tenant."""

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
from gds_etl_workbench.domain.modeling_records import ProjectSchemaDefinition
from gds_etl_workbench.infrastructure.postgres import Database, ReadIsolation

_TOOL_NAME = "list_projects"
_MAX_PROJECTS = 200
POLICY = ToolPolicy.TENANT_READ

_PROJECTS_SQL: LiteralString = """
SELECT project.project_id,
       project.project_name,
       left(project.project_description, 2000) AS project_description,
       project.project_revision,
       project.is_locked,
       project.logical_schemas,
       project.dimensional_schemas,
       project.logical_entity_scd_type,
       project.dimensional_entity_scd_type,
       project.logical_coverage_threshold_percent,
       project.dimensional_coverage_threshold_percent,
       project.logical_enforce_coverage_threshold,
       project.dimensional_enforce_coverage_threshold,
       project.silver_model_naming_instructions,
       project.silver_model_audit_columns_template,
       project.gold_model_naming_instructions,
       project.gold_model_technical_columns_template,
       project.gold_model_audit_columns_template,
       count(project_input_scope.object_id) AS project_input_scope_object_count,
       count(*) OVER () AS total_project_count
  FROM project.project AS project
  LEFT JOIN project.project_input_scope AS project_input_scope
    ON project_input_scope.project_id = project.project_id
   AND project_input_scope.is_active
 WHERE project.tenant_id = %s
   AND project.is_active
 GROUP BY project.project_id
 ORDER BY lower(project.project_name), project.project_id
 LIMIT %s OFFSET %s
"""


class ContractModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class ProjectDetails(ContractModel):
    project_id: int = Field(gt=0)
    project_name: str = Field(min_length=1, max_length=255)
    project_description: str | None = Field(default=None, max_length=2000)
    project_revision: int = Field(gt=0)
    is_locked: bool = False
    logical_schemas: tuple[ProjectSchemaDefinition, ...] = Field(default=(), max_length=100)
    dimensional_schemas: tuple[ProjectSchemaDefinition, ...] = Field(default=(), max_length=100)
    logical_entity_scd_type: Literal["type_1", "type_2"] | None = None
    dimensional_entity_scd_type: Literal["type_1", "type_2"] | None = None
    logical_coverage_threshold_percent: int = Field(default=70, ge=1, le=100, strict=True)
    dimensional_coverage_threshold_percent: int = Field(default=60, ge=1, le=100, strict=True)
    logical_enforce_coverage_threshold: bool = Field(default=False, strict=True)
    dimensional_enforce_coverage_threshold: bool = Field(default=False, strict=True)
    silver_model_naming_instructions: str | None = Field(default=None, max_length=32768)
    silver_model_audit_columns_template: dict[str, JsonValue] | None
    gold_model_naming_instructions: str | None = Field(default=None, max_length=32768)
    gold_model_technical_columns_template: dict[str, JsonValue] | None
    gold_model_audit_columns_template: dict[str, JsonValue] | None
    project_input_scope_object_count: int = Field(ge=0)


class ListProjectsResult(ContractModel):
    schema_version: Literal["1.0"] = "1.0"
    tenant_id: int = Field(gt=0)
    project_count: int = Field(ge=0)
    projects: tuple[ProjectDetails, ...] = Field(max_length=_MAX_PROJECTS)
    projects_truncated: bool
    next_cursor: str | None = Field(default=None, max_length=2048)


class SafeToolError(Exception):
    """A tool failure whose text is safe for the MCP SDK to serialize."""


def register_list_projects_tool(
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
            "List active Projects for one authorized Tenant. Returns paginated Project IDs, "
            "names, revisions, lock state, naming policies, column templates, "
            "and active Input Scope "
            "counts; use the returned project_id with Project-scoped tools."
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
    async def list_projects(
        ctx: Context[None],
        tenant_id: Annotated[int, Field(gt=0)],
        page_size: Annotated[int, Field(ge=1, le=_MAX_PROJECTS)] = _MAX_PROJECTS,
        cursor: Annotated[str | None, Field(max_length=2048)] = None,
        schema_version: Literal["1.0"] = "1.0",
    ) -> ListProjectsResult:
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
                    _PROJECTS_SQL,
                    (tenant_id, page_size + 1, offset),
                )
            project_count = 0 if not rows else int(rows[0]["total_project_count"])
            next_cursor = (
                cursors.encode(collection=collection, offset=offset + page_size)
                if len(rows) > page_size
                else None
            )
            return ListProjectsResult(
                tenant_id=tenant_id,
                project_count=project_count,
                projects=tuple(
                    ProjectDetails(
                        **{
                            name: value
                            for name, value in row.items()
                            if name != "total_project_count"
                        }
                    )
                    for row in rows[:page_size]
                ),
                projects_truncated=len(rows) > page_size,
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
    page_size = arguments.get("page_size", _MAX_PROJECTS)
    return {
        "schema_version": ("1.0" if arguments.get("schema_version", "1.0") == "1.0" else "invalid"),
        "tenant_id": tenant_id if type(tenant_id) is int and tenant_id > 0 else "invalid",
        "page_size": (
            page_size if type(page_size) is int and 1 <= page_size <= _MAX_PROJECTS else "invalid"
        ),
        "cursor_provided": arguments.get("cursor") is not None,
    }
