"""One focused, bounded reader for applied Project datasets."""

# This composed reader intentionally reuses private Snapshot selection queries.
# Pyright cannot see that @server.tool registers the nested handler.
# pyright: reportPrivateUsage=false, reportUnusedFunction=false

from __future__ import annotations

from collections.abc import Mapping
from typing import Annotated, Any, Literal, LiteralString, cast

from mcp.server.mcpserver import Context, MCPServer
from mcp.types import ToolAnnotations
from pydantic import BaseModel, ConfigDict, Field

from gds_etl_workbench.adapters.auth.identity import AuthenticationError, IdentityProvider
from gds_etl_workbench.adapters.mcp.tool_audit import ToolCallAuditMiddleware
from gds_etl_workbench.application.authorization import AuthorizationService
from gds_etl_workbench.application.cursor import CursorCodec
from gds_etl_workbench.application.modeling.context import GROUPS_SQL, RECORDS_SQL, TYPES_SQL
from gds_etl_workbench.application.modeling.enrichment import (
    ATTRIBUTE_ENRICHMENT_SQL,
    OBJECT_ENRICHMENT_SQL,
)
from gds_etl_workbench.application.modeling.modeled_layer import (
    DIMENSIONAL,
    LOGICAL,
    attributes_sql,
    entities_sql,
    relationships_sql,
    submodels_sql,
)
from gds_etl_workbench.application.modeling.profiling_analysis import (
    ANALYSIS_SQL,
    PROFILING_SQL,
)
from gds_etl_workbench.application.modeling.subject_area import (
    CURRENT_SUBJECT_AREA_TABLES_SQL,
    SUBJECT_AREAS_SQL,
)
from gds_etl_workbench.application.project_read import POLICY, authorize_project_read
from gds_etl_workbench.application.project_snapshot import (
    _MAPPING_ATTRIBUTE_SQL,
    _MAPPING_OBJECT_SQL,
    _validate_records,
)
from gds_etl_workbench.domain.errors import InvalidRequestError, WorkbenchError
from gds_etl_workbench.domain.snapshots.project import DATASETS_BY_NAME
from gds_etl_workbench.infrastructure.postgres import Database, ReadIsolation, ReadTransaction

type ReadableProjectDataset = Literal[
    "profiling_profile",
    "object_enrichment",
    "attribute_enrichment",
    "analysis_result",
    "context_type",
    "context_group",
    "context_record",
    "subject_area",
    "subject_area_table",
    "logical_submodel",
    "logical_entity",
    "logical_attribute",
    "logical_relationship",
    "dimensional_submodel",
    "dimensional_entity",
    "dimensional_attribute",
    "dimensional_relationship",
    "mapping_object",
    "mapping_attribute",
]

_TOOL_NAME = "read_project_section"
_MAX_PAGE_SIZE = 200
_MAX_OFFSET = 20_000
_NO_OFFSET_QUERIES: dict[ReadableProjectDataset, LiteralString] = {
    "mapping_object": _MAPPING_OBJECT_SQL,
    "mapping_attribute": _MAPPING_ATTRIBUTE_SQL,
}


class ReadProjectSectionResult(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal["1.0"] = "1.0"
    project_id: int = Field(gt=0)
    project_revision: int = Field(gt=0)
    dataset: ReadableProjectDataset
    records: tuple[dict[str, object], ...] = Field(max_length=_MAX_PAGE_SIZE)
    next_cursor: str | None = Field(default=None, max_length=2048)


class ReadProjectSectionToolError(Exception):
    """A bounded Project reader failure safe for MCP serialization."""


def register_read_project_section_tool(
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
            "Read one bounded applied Project dataset from Profiling, Enrichment, Analysis, "
            "Context, "
            "Subject Areas, Logical, Dimensional, or Mapping. Generated Code and "
            "Validation are Snapshot-only; use a Project Snapshot when either is needed."
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
    async def read_project_section(
        ctx: Context[None],
        project_id: Annotated[int, Field(gt=0)],
        dataset: ReadableProjectDataset,
        page_size: Annotated[int, Field(ge=1, le=_MAX_PAGE_SIZE)] = 50,
        cursor: Annotated[str | None, Field(max_length=2048)] = None,
        schema_version: Literal["1.0"] = "1.0",
    ) -> ReadProjectSectionResult:
        del schema_version
        try:
            collection = f"{_TOOL_NAME}:{project_id}:{dataset}:{page_size}"
            offset = cursors.decode(cursor, collection=collection)
            if offset > _MAX_OFFSET:
                raise InvalidRequestError("The requested Project read offset is too large.")
            principal = identity_provider.request_principal(ctx.request_context.request)
            async with database.read_transaction(
                isolation=ReadIsolation.REPEATABLE_READ
            ) as transaction:
                project = await authorize_project_read(
                    transaction,
                    authorizer=authorizer,
                    principal=principal,
                    project_id=project_id,
                )
                rows = await _read_dataset(
                    transaction,
                    project_id=project.project_id,
                    readable_source_tenant_ids=project.readable_source_tenant_ids,
                    dataset=dataset,
                    page_size=page_size,
                    offset=offset,
                )
            definition = DATASETS_BY_NAME[dataset]
            records = _validate_records(definition, rows[:page_size])
            return ReadProjectSectionResult(
                project_id=project.project_id,
                project_revision=project.project_revision,
                dataset=dataset,
                records=tuple(record.model_dump(mode="json") for record in records),
                next_cursor=(
                    cursors.encode(collection=collection, offset=offset + page_size)
                    if len(rows) > page_size
                    else None
                ),
            )
        except AuthenticationError as error:
            raise ReadProjectSectionToolError(f"{error.public_code}: {error.message}") from None
        except WorkbenchError as error:
            raise ReadProjectSectionToolError(f"{error.code}: {error.message}") from None
        except Exception:
            raise ReadProjectSectionToolError(
                "internal_error: The operation could not be completed."
            ) from None

    audit.register_tool(
        _TOOL_NAME,
        policy=POLICY,
        summarize_input=_audit_input,
        retain_arguments={"project_id", "dataset", "page_size", "schema_version"},
    )


async def _read_dataset(
    transaction: ReadTransaction,
    *,
    project_id: int,
    dataset: ReadableProjectDataset,
    page_size: int,
    offset: int,
    readable_source_tenant_ids: tuple[int, ...] = (),
) -> list[dict[str, object]]:
    limit = page_size + 1
    if dataset in {"object_enrichment", "attribute_enrichment"}:
        query = (
            OBJECT_ENRICHMENT_SQL if dataset == "object_enrichment" else ATTRIBUTE_ENRICHMENT_SQL
        )
        return await transaction.fetch_all(
            query, (project_id, list(readable_source_tenant_ids), True, limit, offset)
        )
    if dataset == "profiling_profile":
        return await transaction.fetch_all(
            PROFILING_SQL,
            (project_id, [], [], limit, offset),
        )
    if dataset == "analysis_result":
        return await transaction.fetch_all(
            ANALYSIS_SQL,
            (project_id, [], [], [], limit, offset),
        )
    if dataset == "context_type":
        return await transaction.fetch_all(TYPES_SQL, (limit, offset))
    if dataset == "context_group":
        return await transaction.fetch_all(GROUPS_SQL, (project_id, limit, offset))
    if dataset == "context_record":
        return await transaction.fetch_all(RECORDS_SQL, (project_id, [], [], limit, offset))
    if dataset == "subject_area":
        return await transaction.fetch_all(SUBJECT_AREAS_SQL, (project_id, limit, offset))
    if dataset == "subject_area_table":
        return await transaction.fetch_all(
            CURRENT_SUBJECT_AREA_TABLES_SQL,
            (project_id, project_id, project_id, list(readable_source_tenant_ids), limit, offset),
        )
    layer, kind = dataset.split("_", 1)
    if layer in {"logical", "dimensional"}:
        config = LOGICAL if layer == "logical" else DIMENSIONAL
        empty_ids: list[int] = []
        if kind == "submodel":
            return await transaction.fetch_all(
                submodels_sql(config),
                (project_id, limit, offset),
            )
        if kind == "entity":
            return await transaction.fetch_all(
                entities_sql(config),
                (project_id, empty_ids, empty_ids, limit, offset),
            )
        if kind == "attribute":
            return await transaction.fetch_all(
                attributes_sql(config),
                (project_id, empty_ids, empty_ids, limit, offset),
            )
        if kind == "relationship":
            return await transaction.fetch_all(
                relationships_sql(config),
                (project_id, empty_ids, empty_ids, empty_ids, limit, offset),
            )
        raise InvalidRequestError("The Project dataset is not readable through this tool.")
    query = _NO_OFFSET_QUERIES.get(dataset)
    if query is None:
        raise InvalidRequestError("The Project dataset is not readable through this tool.")
    rows = await transaction.fetch_all(query, (project_id, offset + limit))
    return rows[offset:]


def _audit_input(arguments: Mapping[str, Any]) -> dict[str, str | int]:
    project_id = arguments.get("project_id")
    page_size = arguments.get("page_size", 50)
    return {
        "schema_version": "1.0" if arguments.get("schema_version", "1.0") == "1.0" else "invalid",
        "project_id": project_id if type(project_id) is int and project_id > 0 else "invalid",
        "dataset": cast(str, arguments.get("dataset", "invalid")),
        "page_size": (
            page_size if type(page_size) is int and 1 <= page_size <= _MAX_PAGE_SIZE else "invalid"
        ),
    }
