"""Governed applied Mapping consumer view with revision/digest-bound pagination."""

# Nested tool handler is registered by MCP.
# pyright: reportUnusedFunction=false
from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from typing import Annotated, Any, Literal, LiteralString, cast

from mcp.server.mcpserver import Context, MCPServer
from mcp.types import ToolAnnotations
from pydantic import BaseModel, ConfigDict, Field

from gds_etl_workbench.adapters.auth.identity import AuthenticationError, IdentityProvider
from gds_etl_workbench.adapters.mcp.tool_audit import ToolCallAuditMiddleware
from gds_etl_workbench.application.authorization import AuthorizationService
from gds_etl_workbench.application.cursor import CursorCodec
from gds_etl_workbench.application.mapping_context import (
    mapping_context_issues,
    project_mapping_inputs,
)
from gds_etl_workbench.application.model_read import POLICY, authorize_model_read
from gds_etl_workbench.domain.errors import InvalidRequestError, WorkbenchError
from gds_etl_workbench.infrastructure.postgres import Database, ReadIsolation

type MappingComponent = Literal[
    "target_metadata",
    "source_metadata",
    "source_systems",
    "object_transformations",
    "attribute_transformations",
]
_MAX_CONTEXT_BYTES = 10 * 1024 * 1024
_MAX_PAGE_BYTES = 256 * 1024
_SQL: LiteralString = """
SELECT code_input_digest,
       octet_length(source_context::TEXT) AS context_bytes,
       CASE WHEN octet_length(source_context::TEXT) <= %s THEN source_context END AS source_context
  FROM workflow.list_code_generation_target_context(%s, %s, NULL)
 WHERE lower(btrim(modeled_entity_name)) = lower(btrim(%s))
 LIMIT 2
"""


class MappingContextResult(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    schema_version: Literal["1.0"] = "1.0"
    model_id: int
    model_revision: int
    context_digest: str
    component: MappingComponent
    records: tuple[dict[str, Any], ...]
    complete: bool
    issues: tuple[str, ...]
    next_cursor: str | None = None


class MappingContextToolError(Exception):
    """Only bounded public errors cross MCP."""


def mapping_context_page(
    *,
    context: dict[str, Any],
    model_id: int,
    model_revision: int,
    entity_type: str,
    entity_name: str,
    component: MappingComponent,
    source_system_codes: list[str],
    page_size: int,
    cursor: str | None,
    expected_context_digest: str | None,
    cursors: CursorCodec,
) -> MappingContextResult:
    canonical = json.dumps(
        context, sort_keys=True, ensure_ascii=False, allow_nan=False, separators=(",", ":")
    )
    if len(canonical.encode("utf-8")) > _MAX_CONTEXT_BYTES:
        raise InvalidRequestError("The Mapping context exceeds the bounded read size.")
    digest = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    if expected_context_digest is not None and expected_context_digest != digest:
        raise InvalidRequestError(
            "Mapping context changed; refresh every component before continuing."
        )
    values = project_mapping_inputs(context)
    wanted = {code.strip().casefold() for code in source_system_codes}
    available = {row["system_code"].strip().casefold() for row in values["source_systems"]}
    if wanted and not wanted <= available:
        raise InvalidRequestError("A selected System is outside the complete applied Mapping.")
    if wanted:
        for name in ("source_metadata", "object_transformations", "attribute_transformations"):
            values[name] = [
                row
                for row in values[name]
                if row["source_system_code"].strip().casefold() in wanted
            ]
        values["source_systems"] = [
            row
            for row in values["source_systems"]
            if row["system_code"].strip().casefold() in wanted
        ]
    issues = mapping_context_issues(values)
    collection = hashlib.sha256(
        json.dumps(
            [
                "read_mapping_context",
                model_id,
                model_revision,
                digest,
                entity_type,
                entity_name.strip().casefold(),
                component,
                sorted(wanted),
                page_size,
            ],
            separators=(",", ":"),
            ensure_ascii=False,
        ).encode("utf-8")
    ).hexdigest()
    offset = cursors.decode(cursor, collection=collection)
    raw_records = values[component]
    records: list[dict[str, Any]] = (
        [cast(dict[str, Any], raw_records)]
        if isinstance(raw_records, dict)
        else cast(list[dict[str, Any]], raw_records)
    )
    if offset > len(records):
        raise InvalidRequestError("The Mapping cursor is outside the current component.")
    page: list[dict[str, Any]] = []
    used = 0
    for row in records[offset : offset + page_size]:
        size = len(json.dumps(row, ensure_ascii=False, allow_nan=False).encode("utf-8"))
        if size > _MAX_PAGE_BYTES:
            raise InvalidRequestError(
                "A Mapping record exceeds the bounded reader; preserve work and resolve its size."
            )
        if used + size > _MAX_PAGE_BYTES:
            break
        page.append(row)
        used += size
    next_offset = offset + len(page)
    return MappingContextResult(
        model_id=model_id,
        model_revision=model_revision,
        context_digest=digest,
        component=component,
        records=tuple(page),
        complete=not issues,
        issues=tuple(issues),
        next_cursor=cursors.encode(collection=collection, offset=next_offset)
        if next_offset < len(records)
        else None,
    )


def register_read_mapping_context_tool(
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
        name="read_mapping_context",
        description=(
            "Read one complete applied target Mapping component for independent SQL/Validation "
            "authoring. Read all five components, preserving expected_context_digest and "
            "expected_model_revision across pages/components. Missing context is reported; "
            "complete=false must be resolved before code generation. No SQL is executed."
        ),
        annotations=ToolAnnotations(
            read_only_hint=True, destructive_hint=False, idempotent_hint=True, open_world_hint=False
        ),
        meta={"gds/toolPolicy": POLICY.value},
        structured_output=True,
    )
    async def read_mapping_context(
        ctx: Context[None],
        model_id: Annotated[int, Field(gt=0)],
        modeled_entity_type: Literal["logical_entity", "dimensional_entity"],
        modeled_entity_name: Annotated[str, Field(min_length=1, max_length=255, pattern=r"\S")],
        component: MappingComponent,
        source_system_codes: Annotated[list[str], Field(max_length=200)] | None = None,
        expected_model_revision: Annotated[int | None, Field(gt=0)] = None,
        expected_context_digest: Annotated[str | None, Field(pattern=r"^[a-f0-9]{64}$")] = None,
        page_size: Annotated[int, Field(ge=1, le=100)] = 50,
        cursor: Annotated[str | None, Field(max_length=2048)] = None,
        schema_version: Literal["1.0"] = "1.0",
    ) -> MappingContextResult:
        del schema_version
        try:
            principal = identity_provider.request_principal(ctx.request_context.request)
            async with database.read_transaction(
                isolation=ReadIsolation.REPEATABLE_READ
            ) as transaction:
                model = await authorize_model_read(
                    transaction, authorizer=authorizer, principal=principal, model_id=model_id
                )
                if (
                    expected_model_revision is not None
                    and expected_model_revision != model.model_revision
                ):
                    raise InvalidRequestError(
                        "Model revision changed; refresh the Mapping context."
                    )
                rows = await transaction.fetch_all(
                    _SQL,
                    (
                        _MAX_CONTEXT_BYTES,
                        model.model_id,
                        modeled_entity_type,
                        modeled_entity_name,
                    ),
                )
                if len(rows) != 1 or not isinstance(rows[0].get("source_context"), dict):
                    raise InvalidRequestError(
                        "The target has no bounded complete eligible Mapping context."
                    )
                context = rows[0]["source_context"]
                if context.get("consumer_context_version") != "atlas-1":
                    raise InvalidRequestError(
                        "The Mapping reader requires the Atlas backend upgrade."
                    )
                owners = {
                    context["target"]["source_tenant_id"],
                    *(row["object"]["source_tenant_id"] for row in context["physical_sources"]),
                }
                if not owners <= {*model.readable_source_tenant_ids, model.tenant_id}:
                    raise InvalidRequestError("Access to every Mapping Source Tenant is required.")
            return mapping_context_page(
                context=context,
                model_id=model.model_id,
                model_revision=model.model_revision,
                entity_type=modeled_entity_type,
                entity_name=modeled_entity_name,
                component=component,
                source_system_codes=source_system_codes or [],
                page_size=page_size,
                cursor=cursor,
                expected_context_digest=expected_context_digest,
                cursors=cursors,
            )
        except AuthenticationError as error:
            raise MappingContextToolError(f"{error.public_code}: {error.message}") from None
        except WorkbenchError as error:
            raise MappingContextToolError(f"{error.code}: {error.message}") from None
        except Exception:
            raise MappingContextToolError(
                "internal_error: The Mapping context is unavailable."
            ) from None

    audit.register_tool(
        "read_mapping_context",
        policy=POLICY,
        summarize_input=_audit_input,
        retain_arguments={"model_id", "component", "page_size", "schema_version"},
    )


def _audit_input(arguments: Mapping[str, Any]) -> dict[str, str | int]:
    return {
        "schema_version": "1.0",
        "model_id": arguments["model_id"] if type(arguments.get("model_id")) is int else "invalid",
        "component": str(arguments.get("component", "invalid")),
        "page_size": arguments.get("page_size", 50)
        if type(arguments.get("page_size", 50)) is int
        else "invalid",
    }
