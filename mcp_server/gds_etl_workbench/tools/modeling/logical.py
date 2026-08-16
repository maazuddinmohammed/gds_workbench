"""Applied Logical Submodel, Entity, Attribute, and Relationship reads."""

# Pyright cannot see that @server.tool registers these nested handlers.
# pyright: reportUnusedFunction=false
# Immutable Pydantic read cards intentionally specialize nested write-record fields with IDs.
# pyright: reportIncompatibleVariableOverride=false

from __future__ import annotations

from typing import Annotated, Literal

from mcp.server.mcpserver import Context, MCPServer
from mcp.types import ToolAnnotations
from pydantic import Field

from gds_etl_workbench.adapters.auth.identity import AuthenticationError, IdentityProvider
from gds_etl_workbench.adapters.mcp.tool_audit import ToolCallAuditMiddleware
from gds_etl_workbench.application.authorization import AuthorizationService
from gds_etl_workbench.application.cursor import CursorCodec
from gds_etl_workbench.domain.errors import WorkbenchError
from gds_etl_workbench.domain.modeling_records import (
    LogicalAttributeRecord,
    LogicalEntityRecord,
    LogicalRelationshipRecord,
    LogicalSubmodelRecord,
)
from gds_etl_workbench.infrastructure.postgres import Database

from .common import POLICY, ContractModel
from .modeled_layer_common import (
    LOGICAL,
    MAX_ID_FILTER,
    MAX_PAGE_SIZE,
    AttributeAssertionSourceResult,
    AttributePhysicalSourceResult,
    LayerToolError,
    LogicalAssertionSourceResult,
    LogicalObjectSourceResult,
    SubmodelMembershipResult,
    audit_input,
    read_attributes,
    read_entities,
    read_relationships,
    read_submodels,
)

type EntitySourceResult = Annotated[
    LogicalObjectSourceResult | LogicalAssertionSourceResult,
    Field(discriminator="support_source_type"),
]
type AttributeSourceResult = Annotated[
    AttributePhysicalSourceResult | AttributeAssertionSourceResult,
    Field(discriminator="support_source_type"),
]


class LogicalSubmodelResult(LogicalSubmodelRecord):
    logical_submodel_id: int = Field(gt=0)
    entity_count: int = Field(ge=0)


class LogicalEntityResult(LogicalEntityRecord):
    logical_entity_id: int = Field(gt=0)
    submodels: tuple[SubmodelMembershipResult, ...]
    sources: tuple[EntitySourceResult, ...]


class LogicalAttributeResult(LogicalAttributeRecord):
    logical_attribute_id: int = Field(gt=0)
    logical_entity_id: int = Field(gt=0)
    sources: tuple[AttributeSourceResult, ...]


class LogicalRelationshipResult(LogicalRelationshipRecord):
    logical_relationship_id: int = Field(gt=0)
    from_logical_entity_id: int = Field(gt=0)
    from_logical_attribute_id: int = Field(gt=0)
    to_logical_entity_id: int = Field(gt=0)
    to_logical_attribute_id: int = Field(gt=0)


class GetModelLogicalSubmodelsResult(ContractModel):
    schema_version: Literal["1.0"] = "1.0"
    model_id: int = Field(gt=0)
    model_revision: int = Field(gt=0)
    submodels: tuple[LogicalSubmodelResult, ...] = Field(max_length=MAX_PAGE_SIZE)
    next_cursor: str | None = Field(default=None, max_length=2048)


class GetModelLogicalEntitiesResult(ContractModel):
    schema_version: Literal["1.0"] = "1.0"
    model_id: int = Field(gt=0)
    model_revision: int = Field(gt=0)
    entities: tuple[LogicalEntityResult, ...] = Field(max_length=MAX_PAGE_SIZE)
    next_cursor: str | None = Field(default=None, max_length=2048)


class GetModelLogicalAttributesResult(ContractModel):
    schema_version: Literal["1.0"] = "1.0"
    model_id: int = Field(gt=0)
    model_revision: int = Field(gt=0)
    attributes: tuple[LogicalAttributeResult, ...] = Field(max_length=MAX_PAGE_SIZE)
    next_cursor: str | None = Field(default=None, max_length=2048)


class GetModelLogicalRelationshipsResult(ContractModel):
    schema_version: Literal["1.0"] = "1.0"
    model_id: int = Field(gt=0)
    model_revision: int = Field(gt=0)
    relationships: tuple[LogicalRelationshipResult, ...] = Field(max_length=MAX_PAGE_SIZE)
    next_cursor: str | None = Field(default=None, max_length=2048)


def register_logical_tools(
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
        description=("Get applied Logical Submodels and each Submodel's unique Entity count."),
        annotations=_annotations(),
        meta={"gds/toolPolicy": POLICY.value},
        structured_output=True,
    )
    async def get_model_logical_submodels(
        ctx: Context[None],
        model_id: Annotated[int, Field(gt=0)],
        page_size: Annotated[int, Field(ge=1, le=MAX_PAGE_SIZE)] = 50,
        cursor: Annotated[str | None, Field(max_length=2048)] = None,
        schema_version: Literal["1.0"] = "1.0",
    ) -> GetModelLogicalSubmodelsResult:
        del schema_version
        try:
            page = await read_submodels(
                database=database,
                authorizer=authorizer,
                principal=identity_provider.request_principal(ctx.request_context.request),
                cursors=cursors,
                config=LOGICAL,
                model_id=model_id,
                page_size=page_size,
                cursor=cursor,
            )
            return GetModelLogicalSubmodelsResult(
                model_id=page.model.model_id,
                model_revision=page.model.model_revision,
                submodels=tuple(
                    LogicalSubmodelResult.model_validate(row, strict=False) for row in page.rows
                ),
                next_cursor=page.next_cursor,
            )
        except AuthenticationError as error:
            raise LayerToolError(f"{error.public_code}: {error.message}") from None
        except WorkbenchError as error:
            raise LayerToolError(f"{error.code}: {error.message}") from None
        except Exception:
            raise LayerToolError("internal_error: The operation could not be completed.") from None

    audit.register_tool(
        "get_model_logical_submodels",
        policy=POLICY,
        summarize_input=audit_input,
        retain_arguments={"model_id", "page_size", "schema_version"},
    )

    @server.tool(
        description=(
            "Get applied Logical Entity cards with Submodel memberships and sources. "
            "An empty supporting Object-ID list selects all Entities."
        ),
        annotations=_annotations(),
        meta={"gds/toolPolicy": POLICY.value},
        structured_output=True,
    )
    async def get_model_logical_entities(
        ctx: Context[None],
        model_id: Annotated[int, Field(gt=0)],
        supporting_object_ids: Annotated[tuple[int, ...], Field(max_length=MAX_ID_FILTER)] = (),
        page_size: Annotated[int, Field(ge=1, le=MAX_PAGE_SIZE)] = 50,
        cursor: Annotated[str | None, Field(max_length=2048)] = None,
        schema_version: Literal["1.0"] = "1.0",
    ) -> GetModelLogicalEntitiesResult:
        del schema_version
        try:
            page = await read_entities(
                database=database,
                authorizer=authorizer,
                principal=identity_provider.request_principal(ctx.request_context.request),
                cursors=cursors,
                config=LOGICAL,
                model_id=model_id,
                supporting_object_ids=supporting_object_ids,
                page_size=page_size,
                cursor=cursor,
            )
            return GetModelLogicalEntitiesResult(
                model_id=page.model.model_id,
                model_revision=page.model.model_revision,
                entities=tuple(
                    LogicalEntityResult.model_validate(row, strict=False) for row in page.rows
                ),
                next_cursor=page.next_cursor,
            )
        except AuthenticationError as error:
            raise LayerToolError(f"{error.public_code}: {error.message}") from None
        except WorkbenchError as error:
            raise LayerToolError(f"{error.code}: {error.message}") from None
        except Exception:
            raise LayerToolError("internal_error: The operation could not be completed.") from None

    audit.register_tool(
        "get_model_logical_entities",
        policy=POLICY,
        summarize_input=lambda arguments: audit_input(arguments, "supporting_object_ids"),
        retain_arguments={"model_id", "page_size", "schema_version"},
    )

    @server.tool(
        description=(
            "Get applied Logical Attributes and their sources. An empty Logical "
            "Entity-ID list selects all Attributes."
        ),
        annotations=_annotations(),
        meta={"gds/toolPolicy": POLICY.value},
        structured_output=True,
    )
    async def get_model_logical_attributes(
        ctx: Context[None],
        model_id: Annotated[int, Field(gt=0)],
        logical_entity_ids: Annotated[tuple[int, ...], Field(max_length=MAX_ID_FILTER)] = (),
        page_size: Annotated[int, Field(ge=1, le=MAX_PAGE_SIZE)] = 50,
        cursor: Annotated[str | None, Field(max_length=2048)] = None,
        schema_version: Literal["1.0"] = "1.0",
    ) -> GetModelLogicalAttributesResult:
        del schema_version
        try:
            page = await read_attributes(
                database=database,
                authorizer=authorizer,
                principal=identity_provider.request_principal(ctx.request_context.request),
                cursors=cursors,
                config=LOGICAL,
                model_id=model_id,
                entity_ids=logical_entity_ids,
                page_size=page_size,
                cursor=cursor,
            )
            return GetModelLogicalAttributesResult(
                model_id=page.model.model_id,
                model_revision=page.model.model_revision,
                attributes=tuple(
                    LogicalAttributeResult.model_validate(row, strict=False) for row in page.rows
                ),
                next_cursor=page.next_cursor,
            )
        except AuthenticationError as error:
            raise LayerToolError(f"{error.public_code}: {error.message}") from None
        except WorkbenchError as error:
            raise LayerToolError(f"{error.code}: {error.message}") from None
        except Exception:
            raise LayerToolError("internal_error: The operation could not be completed.") from None

    audit.register_tool(
        "get_model_logical_attributes",
        policy=POLICY,
        summarize_input=lambda arguments: audit_input(arguments, "logical_entity_ids"),
        retain_arguments={"model_id", "page_size", "schema_version"},
    )

    @server.tool(
        description=(
            "Get applied Logical Relationships touching selected Logical Entities. "
            "An empty Entity-ID list selects all Relationships."
        ),
        annotations=_annotations(),
        meta={"gds/toolPolicy": POLICY.value},
        structured_output=True,
    )
    async def get_model_logical_relationships(
        ctx: Context[None],
        model_id: Annotated[int, Field(gt=0)],
        logical_entity_ids: Annotated[tuple[int, ...], Field(max_length=MAX_ID_FILTER)] = (),
        page_size: Annotated[int, Field(ge=1, le=MAX_PAGE_SIZE)] = 50,
        cursor: Annotated[str | None, Field(max_length=2048)] = None,
        schema_version: Literal["1.0"] = "1.0",
    ) -> GetModelLogicalRelationshipsResult:
        del schema_version
        try:
            page = await read_relationships(
                database=database,
                authorizer=authorizer,
                principal=identity_provider.request_principal(ctx.request_context.request),
                cursors=cursors,
                config=LOGICAL,
                model_id=model_id,
                entity_ids=logical_entity_ids,
                page_size=page_size,
                cursor=cursor,
            )
            return GetModelLogicalRelationshipsResult(
                model_id=page.model.model_id,
                model_revision=page.model.model_revision,
                relationships=tuple(
                    LogicalRelationshipResult.model_validate(row, strict=False) for row in page.rows
                ),
                next_cursor=page.next_cursor,
            )
        except AuthenticationError as error:
            raise LayerToolError(f"{error.public_code}: {error.message}") from None
        except WorkbenchError as error:
            raise LayerToolError(f"{error.code}: {error.message}") from None
        except Exception:
            raise LayerToolError("internal_error: The operation could not be completed.") from None

    audit.register_tool(
        "get_model_logical_relationships",
        policy=POLICY,
        summarize_input=lambda arguments: audit_input(arguments, "logical_entity_ids"),
        retain_arguments={"model_id", "page_size", "schema_version"},
    )


def _annotations() -> ToolAnnotations:
    return ToolAnnotations(
        read_only_hint=True,
        destructive_hint=False,
        idempotent_hint=True,
        open_world_hint=False,
    )
