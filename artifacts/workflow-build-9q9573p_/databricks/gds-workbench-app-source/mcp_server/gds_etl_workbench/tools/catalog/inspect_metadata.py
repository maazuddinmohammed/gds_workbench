"""One focused, bounded reader for physical metadata and orchestration groups."""

# This composed reader intentionally reuses private query contracts from its focused modules.
# Pyright cannot see that @server.tool registers the nested handler.
# pyright: reportPrivateUsage=false, reportUnusedFunction=false

from __future__ import annotations

from collections import defaultdict
from collections.abc import Mapping
from typing import Annotated, Any, Literal, cast

from mcp.server.mcpserver import Context, MCPServer
from mcp.types import ToolAnnotations
from pydantic import BaseModel, ConfigDict, Field

from gds_etl_workbench.adapters.auth.identity import AuthenticationError, IdentityProvider
from gds_etl_workbench.adapters.mcp.tool_audit import ToolCallAuditMiddleware
from gds_etl_workbench.application.authorization import AuthorizationService
from gds_etl_workbench.application.cursor import CursorCodec
from gds_etl_workbench.domain.authorization import ToolPolicy
from gds_etl_workbench.domain.errors import InvalidRequestError, WorkbenchError
from gds_etl_workbench.infrastructure.postgres import Database, ReadIsolation
from gds_etl_workbench.tools.ingestion.copy_groups import (
    _CONTROLS_SQL as COPY_CONTROLS_SQL,
)
from gds_etl_workbench.tools.ingestion.copy_groups import (
    _COPIES_SQL as COPIES_SQL,
)
from gds_etl_workbench.tools.ingestion.copy_groups import (
    _GROUP_SQL as COPY_GROUP_SQL,
)
from gds_etl_workbench.tools.ingestion.copy_groups import (
    _LIST_SQL as COPY_GROUP_LIST_SQL,
)
from gds_etl_workbench.tools.ingestion.copy_groups import (
    CopyGroupControlDetails,
    CopyGroupSummary,
    _copy,
)
from gds_etl_workbench.tools.processing.process_groups import (
    _GROUP_SQL as PROCESS_GROUP_SQL,
)
from gds_etl_workbench.tools.processing.process_groups import (
    _LIST_SQL as PROCESS_GROUP_LIST_SQL,
)
from gds_etl_workbench.tools.processing.process_groups import (
    _PROCESSES_SQL as PROCESSES_SQL,
)
from gds_etl_workbench.tools.processing.process_groups import (
    ProcessGroupSummary,
    _process,
)

from .get_object_lineage import (
    _LINEAGE_SQL as LINEAGE_SQL,
)
from .get_object_lineage import (
    _OBJECT_VISIBLE_SQL as OBJECT_VISIBLE_SQL,
)
from .get_object_lineage import (
    _mapping,
)
from .get_objects import (
    _ATTRIBUTES_SQL as ATTRIBUTES_SQL,
)
from .get_objects import (
    _OBJECTS_SQL as OBJECTS_SQL,
)
from .get_objects import (
    AttributeDetails,
    ObjectDetails,
)
from .list_objects import _LIST_OBJECTS_SQL as LIST_OBJECTS_SQL
from .list_objects import ObjectSummary

type MetadataView = Literal[
    "objects",
    "object_details",
    "object_lineage",
    "copy_groups",
    "copy_group_details",
    "process_groups",
    "process_group_details",
]
type ZoneCode = Literal["source", "bronze", "silver", "gold"]
type ActiveState = Literal["active", "inactive", "all"]
type Direction = Literal["upstream", "downstream", "both"]

_TOOL_NAME = "inspect_metadata"
_MAX_OBJECTS = 25
_MAX_ATTRIBUTES = 2_000
_MAX_DETAILS = 500
POLICY = ToolPolicy.TENANT_READ


class InspectMetadataResult(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal["1.0"] = "1.0"
    tenant_id: int = Field(gt=0)
    view: MetadataView
    payload: dict[str, object]
    next_cursor: str | None = Field(default=None, max_length=2048)


class InspectMetadataToolError(Exception):
    """A bounded reader failure safe for MCP serialization."""


def register_inspect_metadata_tool(
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
            "Read one bounded physical Metadata view. List Objects, Copy Groups, or Process "
            "Groups, or fetch their details and direct Object lineage. Each detail view "
            "requires its matching ID filter; use a Metadata Snapshot for broad authoring."
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
    async def inspect_metadata(
        ctx: Context[None],
        tenant_id: Annotated[int, Field(gt=0)],
        view: Annotated[
            MetadataView,
            Field(
                description=(
                    "objects requires zone; object_details requires object_ids; "
                    "object_lineage requires object_id; copy_group_details requires "
                    "copy_group_id; process_group_details requires process_group_id."
                )
            ),
        ],
        zone: Annotated[
            ZoneCode | None,
            Field(description="Required for objects; optional filter for process_groups."),
        ] = None,
        connection_id: Annotated[
            int | None,
            Field(gt=0, description="Optional Connection filter for the objects view."),
        ] = None,
        system_id: Annotated[
            int | None,
            Field(gt=0, description="Optional System filter for group-list views."),
        ] = None,
        object_ids: Annotated[
            list[int] | None,
            Field(
                max_length=_MAX_OBJECTS,
                description="Required unique positive Object IDs for object_details.",
            ),
        ] = None,
        object_id: Annotated[
            int | None,
            Field(gt=0, description="Required Object ID for object_lineage."),
        ] = None,
        copy_group_id: Annotated[
            int | None,
            Field(gt=0, description="Required Copy Group ID for copy_group_details."),
        ] = None,
        process_group_id: Annotated[
            int | None,
            Field(gt=0, description="Required Process Group ID for process_group_details."),
        ] = None,
        direction: Annotated[
            Direction,
            Field(description="Lineage direction; used only by object_lineage."),
        ] = "both",
        active_state: Annotated[
            ActiveState,
            Field(description="Active-state filter for list views."),
        ] = "active",
        page_size: Annotated[int, Field(ge=1, le=200)] = 50,
        cursor: Annotated[str | None, Field(max_length=2048)] = None,
        schema_version: Literal["1.0"] = "1.0",
    ) -> InspectMetadataResult:
        del schema_version
        try:
            principal = identity_provider.request_principal(ctx.request_context.request)
            collection = (
                f"{_TOOL_NAME}:{tenant_id}:{view}:{zone or 'all'}:"
                f"{connection_id or 0}:{system_id or 0}:{active_state}"
            )
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
                payload, has_more = await _read_view(
                    transaction,
                    tenant_id=tenant_id,
                    view=view,
                    zone=zone,
                    connection_id=connection_id,
                    system_id=system_id,
                    object_ids=object_ids,
                    object_id=object_id,
                    copy_group_id=copy_group_id,
                    process_group_id=process_group_id,
                    direction=direction,
                    active_state=active_state,
                    page_size=page_size,
                    offset=offset,
                )
            return InspectMetadataResult(
                tenant_id=tenant_id,
                view=view,
                payload=payload,
                next_cursor=(
                    cursors.encode(collection=collection, offset=offset + page_size)
                    if has_more
                    else None
                ),
            )
        except AuthenticationError as error:
            raise InspectMetadataToolError(f"{error.public_code}: {error.message}") from None
        except WorkbenchError as error:
            raise InspectMetadataToolError(f"{error.code}: {error.message}") from None
        except Exception:
            raise InspectMetadataToolError(
                "internal_error: The operation could not be completed."
            ) from None

    audit.register_tool(
        _TOOL_NAME,
        policy=POLICY,
        summarize_input=_audit_input,
        retain_arguments={
            "tenant_id",
            "view",
            "zone",
            "connection_id",
            "system_id",
            "object_ids",
            "object_id",
            "copy_group_id",
            "process_group_id",
            "direction",
            "active_state",
            "page_size",
            "schema_version",
        },
        tenant_argument="tenant_id",
    )


async def _read_view(
    transaction: Any,
    *,
    tenant_id: int,
    view: MetadataView,
    zone: ZoneCode | None,
    connection_id: int | None,
    system_id: int | None,
    object_ids: list[int] | None,
    object_id: int | None,
    copy_group_id: int | None,
    process_group_id: int | None,
    direction: Direction,
    active_state: ActiveState,
    page_size: int,
    offset: int,
) -> tuple[dict[str, object], bool]:
    if view == "objects":
        if zone is None:
            raise InvalidRequestError("zone is required for the objects view.")
        rows = await transaction.fetch_all(
            LIST_OBJECTS_SQL,
            (
                tenant_id,
                zone,
                connection_id,
                connection_id,
                active_state,
                active_state,
                active_state,
                page_size + 1,
                offset,
            ),
        )
        return _model_payload("objects", ObjectSummary, rows[:page_size]), len(rows) > page_size

    if view == "object_details":
        requested = object_ids or []
        if (
            not requested
            or len(set(requested)) != len(requested)
            or any(item <= 0 for item in requested)
        ):
            raise InvalidRequestError("object_ids must contain unique positive IDs.")
        object_rows = await transaction.fetch_all(OBJECTS_SQL, (tenant_id, requested))
        if len(object_rows) != len(requested):
            raise InvalidRequestError("One or more Objects were not found.")
        attribute_rows = await transaction.fetch_all(
            ATTRIBUTES_SQL,
            (requested, _MAX_ATTRIBUTES + 1),
        )
        if len(attribute_rows) > _MAX_ATTRIBUTES:
            raise InvalidRequestError("The requested Object details are too large.")
        attributes: dict[int, list[AttributeDetails]] = defaultdict(list)
        for source_row in attribute_rows:
            row = dict(source_row)
            parent_id = cast(int, row.pop("object_id"))
            attributes[parent_id].append(AttributeDetails(**row))
        details = [
            ObjectDetails(
                **row,
                attributes=tuple(attributes[cast(int, row["object_id"])]),
            ).model_dump(mode="json")
            for row in object_rows
        ]
        return {"objects": details}, False

    if view == "object_lineage":
        if object_id is None:
            raise InvalidRequestError("object_id is required for the object_lineage view.")
        visible = await transaction.fetch_one(OBJECT_VISIBLE_SQL, (tenant_id, object_id))
        if visible is None or not visible["is_visible"]:
            raise InvalidRequestError("Object was not found.")
        rows = await transaction.fetch_all(
            LINEAGE_SQL,
            (tenant_id, object_id, direction, object_id, direction, object_id),
        )
        return {
            "object_id": object_id,
            "mappings": [_mapping(row).model_dump(mode="json") for row in rows[:_MAX_DETAILS]],
            "mappings_truncated": len(rows) > _MAX_DETAILS,
        }, False

    if view == "copy_groups":
        rows = await transaction.fetch_all(
            COPY_GROUP_LIST_SQL,
            (
                tenant_id,
                system_id,
                system_id,
                active_state,
                active_state,
                active_state,
                page_size + 1,
                offset,
            ),
        )
        return _model_payload("copy_groups", CopyGroupSummary, rows[:page_size]), len(
            rows
        ) > page_size

    if view == "copy_group_details":
        if copy_group_id is None:
            raise InvalidRequestError("copy_group_id is required for this view.")
        group = await transaction.fetch_one(COPY_GROUP_SQL, (tenant_id, copy_group_id))
        if group is None:
            raise InvalidRequestError("Copy Group was not found.")
        copies = await transaction.fetch_all(COPIES_SQL, (tenant_id, tenant_id, copy_group_id))
        controls = await transaction.fetch_all(
            COPY_CONTROLS_SQL,
            (tenant_id, copy_group_id),
        )
        return {
            "copy_group": CopyGroupSummary(**group).model_dump(mode="json"),
            "copies": [_copy(row).model_dump(mode="json") for row in copies[:_MAX_DETAILS]],
            "copies_truncated": len(copies) > _MAX_DETAILS,
            "controls": [
                CopyGroupControlDetails(**row).model_dump(mode="json")
                for row in controls[:_MAX_DETAILS]
            ],
            "controls_truncated": len(controls) > _MAX_DETAILS,
        }, False

    if view == "process_groups":
        rows = await transaction.fetch_all(
            PROCESS_GROUP_LIST_SQL,
            (
                tenant_id,
                system_id,
                system_id,
                zone,
                zone,
                active_state,
                active_state,
                active_state,
                page_size + 1,
                offset,
            ),
        )
        return _model_payload(
            "process_groups",
            ProcessGroupSummary,
            rows[:page_size],
        ), len(rows) > page_size

    if process_group_id is None:
        raise InvalidRequestError("process_group_id is required for this view.")
    group = await transaction.fetch_one(PROCESS_GROUP_SQL, (tenant_id, process_group_id))
    if group is None:
        raise InvalidRequestError("Process Group was not found.")
    processes = await transaction.fetch_all(PROCESSES_SQL, (tenant_id, process_group_id))
    return {
        "process_group": ProcessGroupSummary(**group).model_dump(mode="json"),
        "processes": [_process(row).model_dump(mode="json") for row in processes[:_MAX_DETAILS]],
        "processes_truncated": len(processes) > _MAX_DETAILS,
    }, False


def _model_payload(
    name: str,
    model: type[BaseModel],
    rows: list[Mapping[str, Any]],
) -> dict[str, object]:
    return {name: [model(**row).model_dump(mode="json") for row in rows]}


def _audit_input(arguments: Mapping[str, Any]) -> dict[str, str | int | bool]:
    tenant_id = arguments.get("tenant_id")
    page_size = arguments.get("page_size", 50)
    object_ids = arguments.get("object_ids")
    return {
        "tenant_id": tenant_id if type(tenant_id) is int and tenant_id > 0 else "invalid",
        "view": cast(str, arguments.get("view", "invalid")),
        "zone_filter_provided": arguments.get("zone") is not None,
        "connection_filter_provided": arguments.get("connection_id") is not None,
        "system_filter_provided": arguments.get("system_id") is not None,
        "object_count": len(cast(list[object], object_ids)) if isinstance(object_ids, list) else 0,
        "page_size": page_size if type(page_size) is int and 1 <= page_size <= 200 else "invalid",
        "cursor_provided": arguments.get("cursor") is not None,
    }
