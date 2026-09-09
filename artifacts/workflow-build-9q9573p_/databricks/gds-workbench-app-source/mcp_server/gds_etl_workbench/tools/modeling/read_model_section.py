"""One focused, bounded reader for applied Model datasets."""

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
from gds_etl_workbench.application.model_read import POLICY, authorize_model_read
from gds_etl_workbench.application.model_snapshot import (
    _MAPPING_ATTRIBUTE_SQL,
    _MAPPING_DEPENDENCY_SQL,
    _MAPPING_OBJECT_SQL,
    _MODEL_ATTRIBUTE_BINDING_SQL,
    _MODEL_OBJECT_BINDING_SQL,
    _validate_records,
)
from gds_etl_workbench.application.modeling.assertions import DOCUMENTS_SQL, RECORDS_SQL
from gds_etl_workbench.application.modeling.conceptual import (
    CONCEPTUAL_OBJECTS_SQL,
    CONCEPTUAL_RELATIONSHIPS_SQL,
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
from gds_etl_workbench.domain.errors import InvalidRequestError, WorkbenchError
from gds_etl_workbench.domain.snapshots.model import DATASETS_BY_NAME
from gds_etl_workbench.infrastructure.postgres import Database, ReadIsolation, ReadTransaction

type ReadableModelDataset = Literal[
    "profiling_profile",
    "analysis_result",
    "modeling_assertion_document",
    "modeling_assertion_record",
    "conceptual_object",
    "conceptual_relationship",
    "logical_submodel",
    "logical_entity",
    "logical_attribute",
    "logical_relationship",
    "dimensional_submodel",
    "dimensional_entity",
    "dimensional_attribute",
    "dimensional_relationship",
    "model_object_binding",
    "model_attribute_binding",
    "mapping_dependency",
    "mapping_object",
    "mapping_attribute",
]

_TOOL_NAME = "read_model_section"
_MAX_PAGE_SIZE = 200
_MAX_OFFSET = 20_000
_NO_OFFSET_QUERIES: dict[ReadableModelDataset, LiteralString] = {
    "model_object_binding": _MODEL_OBJECT_BINDING_SQL,
    "model_attribute_binding": _MODEL_ATTRIBUTE_BINDING_SQL,
    "mapping_dependency": _MAPPING_DEPENDENCY_SQL,
    "mapping_object": _MAPPING_OBJECT_SQL,
    "mapping_attribute": _MAPPING_ATTRIBUTE_SQL,
}


class ReadModelSectionResult(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal["1.0"] = "1.0"
    model_id: int = Field(gt=0)
    model_revision: int = Field(gt=0)
    dataset: ReadableModelDataset
    records: tuple[dict[str, object], ...] = Field(max_length=_MAX_PAGE_SIZE)
    next_cursor: str | None = Field(default=None, max_length=2048)


class ReadModelSectionToolError(Exception):
    """A bounded Model reader failure safe for MCP serialization."""


def register_read_model_section_tool(
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
            "Read one bounded applied Model dataset from Profiling, Analysis, Assertions, "
            "Conceptual, Logical, Dimensional, Binding, or Mapping. Generated Code and "
            "Validation are Snapshot-only; use a Model Snapshot when either is needed."
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
    async def read_model_section(
        ctx: Context[None],
        model_id: Annotated[int, Field(gt=0)],
        dataset: ReadableModelDataset,
        page_size: Annotated[int, Field(ge=1, le=_MAX_PAGE_SIZE)] = 50,
        cursor: Annotated[str | None, Field(max_length=2048)] = None,
        schema_version: Literal["1.0"] = "1.0",
    ) -> ReadModelSectionResult:
        del schema_version
        try:
            collection = f"{_TOOL_NAME}:{model_id}:{dataset}:{page_size}"
            offset = cursors.decode(cursor, collection=collection)
            if offset > _MAX_OFFSET:
                raise InvalidRequestError("The requested Model read offset is too large.")
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
                rows = await _read_dataset(
                    transaction,
                    model_id=model.model_id,
                    dataset=dataset,
                    page_size=page_size,
                    offset=offset,
                )
            definition = DATASETS_BY_NAME[dataset]
            records = _validate_records(definition, rows[:page_size])
            return ReadModelSectionResult(
                model_id=model.model_id,
                model_revision=model.model_revision,
                dataset=dataset,
                records=tuple(record.model_dump(mode="json") for record in records),
                next_cursor=(
                    cursors.encode(collection=collection, offset=offset + page_size)
                    if len(rows) > page_size
                    else None
                ),
            )
        except AuthenticationError as error:
            raise ReadModelSectionToolError(f"{error.public_code}: {error.message}") from None
        except WorkbenchError as error:
            raise ReadModelSectionToolError(f"{error.code}: {error.message}") from None
        except Exception:
            raise ReadModelSectionToolError(
                "internal_error: The operation could not be completed."
            ) from None

    audit.register_tool(
        _TOOL_NAME,
        policy=POLICY,
        summarize_input=_audit_input,
        retain_arguments={"model_id", "dataset", "page_size", "schema_version"},
    )


async def _read_dataset(
    transaction: ReadTransaction,
    *,
    model_id: int,
    dataset: ReadableModelDataset,
    page_size: int,
    offset: int,
) -> list[dict[str, object]]:
    limit = page_size + 1
    if dataset == "profiling_profile":
        return await transaction.fetch_all(
            PROFILING_SQL,
            (model_id, [], [], limit, offset),
        )
    if dataset == "analysis_result":
        return await transaction.fetch_all(
            ANALYSIS_SQL,
            (model_id, [], [], [], limit, offset),
        )
    if dataset == "modeling_assertion_document":
        return await transaction.fetch_all(DOCUMENTS_SQL, (model_id, limit, offset))
    if dataset == "modeling_assertion_record":
        return await transaction.fetch_all(RECORDS_SQL, (model_id, [], [], limit, offset))
    if dataset == "conceptual_object":
        return await transaction.fetch_all(
            CONCEPTUAL_OBJECTS_SQL,
            (model_id, [], [], limit, offset),
        )
    if dataset == "conceptual_relationship":
        return await transaction.fetch_all(
            CONCEPTUAL_RELATIONSHIPS_SQL,
            (model_id, [], [], [], limit, offset),
        )
    layer, kind = dataset.split("_", 1)
    if layer in {"logical", "dimensional"}:
        config = LOGICAL if layer == "logical" else DIMENSIONAL
        empty_ids: list[int] = []
        if kind == "submodel":
            return await transaction.fetch_all(
                submodels_sql(config),
                (model_id, limit, offset),
            )
        if kind == "entity":
            return await transaction.fetch_all(
                entities_sql(config),
                (model_id, empty_ids, empty_ids, limit, offset),
            )
        if kind == "attribute":
            return await transaction.fetch_all(
                attributes_sql(config),
                (model_id, empty_ids, empty_ids, limit, offset),
            )
        if kind == "relationship":
            return await transaction.fetch_all(
                relationships_sql(config),
                (model_id, empty_ids, empty_ids, empty_ids, limit, offset),
            )
        raise InvalidRequestError("The Model dataset is not readable through this tool.")
    query = _NO_OFFSET_QUERIES.get(dataset)
    if query is None:
        raise InvalidRequestError("The Model dataset is not readable through this tool.")
    rows = await transaction.fetch_all(query, (model_id, offset + limit))
    return rows[offset:]


def _audit_input(arguments: Mapping[str, Any]) -> dict[str, str | int]:
    model_id = arguments.get("model_id")
    page_size = arguments.get("page_size", 50)
    return {
        "schema_version": "1.0" if arguments.get("schema_version", "1.0") == "1.0" else "invalid",
        "model_id": model_id if type(model_id) is int and model_id > 0 else "invalid",
        "dataset": cast(str, arguments.get("dataset", "invalid")),
        "page_size": (
            page_size if type(page_size) is int and 1 <= page_size <= _MAX_PAGE_SIZE else "invalid"
        ),
    }
