"""Applied Dimensional Submodel, Entity, Attribute, and Relationship reads."""

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
    DimensionalAttributeRecord,
    DimensionalEntityRecord,
    DimensionalRelationshipRecord,
    DimensionalSubmodelRecord,
)
from gds_etl_workbench.infrastructure.postgres import Database

from .common import POLICY, ContractModel
from .modeled_layer_common import (
    DIMENSIONAL,
    MAX_ID_FILTER,
    MAX_PAGE_SIZE,
    AttributeAssertionSourceResult,
    AttributePhysicalSourceResult,
    DimensionalAssertionSourceResult,
    DimensionalObjectSourceResult,
    LayerToolError,
    SubmodelMembershipResult,
    audit_input,
    read_attributes,
    read_entities,
    read_relationships,
    read_submodels,
)

type EntitySourceResult = Annotated[
    DimensionalObjectSourceResult | DimensionalAssertionSourceResult,
    Field(discriminator="support_source_type"),
]
type AttributeSourceResult = Annotated[
    AttributePhysicalSourceResult | AttributeAssertionSourceResult,
    Field(discriminator="support_source_type"),
]


class DimensionalSubmodelResult(DimensionalSubmodelRecord):
    dimensional_submodel_id: int = Field(gt=0)
    entity_count: int = Field(ge=0)


class DimensionalEntityResult(DimensionalEntityRecord):
    dimensional_entity_id: int = Field(gt=0)
    submodels: tuple[SubmodelMembershipResult, ...]
    sources: tuple[EntitySourceResult, ...]


class DimensionalAttributeResult(DimensionalAttributeRecord):
    dimensional_attribute_id: int = Field(gt=0)
    dimensional_entity_id: int = Field(gt=0)
    sources: tuple[AttributeSourceResult, ...]


class DimensionalRelationshipResult(DimensionalRelationshipRecord):
    dimensional_relationship_id: int = Field(gt=0)
    from_dimensional_entity_id: int = Field(gt=0)
    from_dimensional_attribute_id: int = Field(gt=0)
    to_dimensional_entity_id: int = Field(gt=0)
    to_dimensional_attribute_id: int = Field(gt=0)


class GetModelDimensionalSubmodelsResult(ContractModel):
    schema_version: Literal["1.0"] = "1.0"
    model_id: int = Field(gt=0)
    model_revision: int = Field(gt=0)
    submodels: tuple[DimensionalSubmodelResult, ...] = Field(max_length=MAX_PAGE_SIZE)
    next_cursor: str | None = Field(default=None, max_length=2048)


class GetModelDimensionalEntitiesResult(ContractModel):
    schema_version: Literal["1.0"] = "1.0"
    model_id: int = Field(gt=0)
    model_revision: int = Field(gt=0)
    entities: tuple[DimensionalEntityResult, ...] = Field(max_length=MAX_PAGE_SIZE)
    next_cursor: str | None = Field(default=None, max_length=2048)


class GetModelDimensionalAttributesResult(ContractModel):
    schema_version: Literal["1.0"] = "1.0"
    model_id: int = Field(gt=0)
    model_revision: int = Field(gt=0)
    attributes: tuple[DimensionalAttributeResult, ...] = Field(max_length=MAX_PAGE_SIZE)
    next_cursor: str | None = Field(default=None, max_length=2048)


class GetModelDimensionalRelationshipsResult(ContractModel):
    schema_version: Literal["1.0"] = "1.0"
    model_id: int = Field(gt=0)
    model_revision: int = Field(gt=0)
    relationships: tuple[DimensionalRelationshipResult, ...] = Field(max_length=MAX_PAGE_SIZE)
    next_cursor: str | None = Field(default=None, max_length=2048)


def register_dimensional_tools(
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
        description=("Get applied Dimensional Submodels and each Submodel's unique Entity count."),
        annotations=_annotations(),
        meta={"gds/toolPolicy": POLICY.value},
        structured_output=True,
    )
    async def get_model_dimensional_submodels(
        ctx: Context[None],
        model_id: Annotated[int, Field(gt=0)],
        page_size: Annotated[int, Field(ge=1, le=MAX_PAGE_SIZE)] = 50,
        cursor: Annotated[str | None, Field(max_length=2048)] = None,
        schema_version: Literal["1.0"] = "1.0",
    ) -> GetModelDimensionalSubmodelsResult:
        del schema_version
        try:
            page = await read_submodels(
                database=database,
                authorizer=authorizer,
                principal=identity_provider.request_principal(ctx.request_context.request),
                cursors=cursors,
                config=DIMENSIONAL,
                model_id=model_id,
                page_size=page_size,
                cursor=cursor,
            )
            return GetModelDimensionalSubmodelsResult(
                model_id=page.model.model_id,
                model_revision=page.model.model_revision,
                submodels=tuple(
                    DimensionalSubmodelResult.model_validate(row, strict=False) for row in page.rows
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
        "get_model_dimensional_submodels",
        policy=POLICY,
        summarize_input=audit_input,
        retain_arguments={"model_id", "page_size", "schema_version"},
    )

    @server.tool(
        description=(
            "Get applied Dimensional Entity cards with Submodel memberships and "
            "sources. An empty supporting Object-ID list selects all Entities."
        ),
        annotations=_annotations(),
        meta={"gds/toolPolicy": POLICY.value},
        structured_output=True,
    )
    async def get_model_dimensional_entities(
        ctx: Context[None],
        model_id: Annotated[int, Field(gt=0)],
        supporting_object_ids: Annotated[tuple[int, ...], Field(max_length=MAX_ID_FILTER)] = (),
        page_size: Annotated[int, Field(ge=1, le=MAX_PAGE_SIZE)] = 50,
        cursor: Annotated[str | None, Field(max_length=2048)] = None,
        schema_version: Literal["1.0"] = "1.0",
    ) -> GetModelDimensionalEntitiesResult:
        del schema_version
        try:
            page = await read_entities(
                database=database,
                authorizer=authorizer,
                principal=identity_provider.request_principal(ctx.request_context.request),
                cursors=cursors,
                config=DIMENSIONAL,
                model_id=model_id,
                supporting_object_ids=supporting_object_ids,
                page_size=page_size,
                cursor=cursor,
            )
            return GetModelDimensionalEntitiesResult(
                model_id=page.model.model_id,
                model_revision=page.model.model_revision,
                entities=tuple(
                    DimensionalEntityResult.model_validate(row, strict=False) for row in page.rows
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
        "get_model_dimensional_entities",
        policy=POLICY,
        summarize_input=lambda arguments: audit_input(arguments, "supporting_object_ids"),
        retain_arguments={"model_id", "page_size", "schema_version"},
    )

    @server.tool(
        description=(
            "Get applied Dimensional Attributes and their sources. An empty "
            "Dimensional Entity-ID list selects all Attributes."
        ),
        annotations=_annotations(),
        meta={"gds/toolPolicy": POLICY.value},
        structured_output=True,
    )
    async def get_model_dimensional_attributes(
        ctx: Context[None],
        model_id: Annotated[int, Field(gt=0)],
        dimensional_entity_ids: Annotated[tuple[int, ...], Field(max_length=MAX_ID_FILTER)] = (),
        page_size: Annotated[int, Field(ge=1, le=MAX_PAGE_SIZE)] = 50,
        cursor: Annotated[str | None, Field(max_length=2048)] = None,
        schema_version: Literal["1.0"] = "1.0",
    ) -> GetModelDimensionalAttributesResult:
        del schema_version
        try:
            page = await read_attributes(
                database=database,
                authorizer=authorizer,
                principal=identity_provider.request_principal(ctx.request_context.request),
                cursors=cursors,
                config=DIMENSIONAL,
                model_id=model_id,
                entity_ids=dimensional_entity_ids,
                page_size=page_size,
                cursor=cursor,
            )
            return GetModelDimensionalAttributesResult(
                model_id=page.model.model_id,
                model_revision=page.model.model_revision,
                attributes=tuple(
                    DimensionalAttributeResult.model_validate(row, strict=False)
                    for row in page.rows
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
        "get_model_dimensional_attributes",
        policy=POLICY,
        summarize_input=lambda arguments: audit_input(arguments, "dimensional_entity_ids"),
        retain_arguments={"model_id", "page_size", "schema_version"},
    )

    @server.tool(
        description=(
            "Get applied Dimensional Relationships touching selected Dimensional "
            "Entities. An empty Entity-ID list selects all Relationships."
        ),
        annotations=_annotations(),
        meta={"gds/toolPolicy": POLICY.value},
        structured_output=True,
    )
    async def get_model_dimensional_relationships(
        ctx: Context[None],
        model_id: Annotated[int, Field(gt=0)],
        dimensional_entity_ids: Annotated[tuple[int, ...], Field(max_length=MAX_ID_FILTER)] = (),
        page_size: Annotated[int, Field(ge=1, le=MAX_PAGE_SIZE)] = 50,
        cursor: Annotated[str | None, Field(max_length=2048)] = None,
        schema_version: Literal["1.0"] = "1.0",
    ) -> GetModelDimensionalRelationshipsResult:
        del schema_version
        try:
            page = await read_relationships(
                database=database,
                authorizer=authorizer,
                principal=identity_provider.request_principal(ctx.request_context.request),
                cursors=cursors,
                config=DIMENSIONAL,
                model_id=model_id,
                entity_ids=dimensional_entity_ids,
                page_size=page_size,
                cursor=cursor,
            )
            return GetModelDimensionalRelationshipsResult(
                model_id=page.model.model_id,
                model_revision=page.model.model_revision,
                relationships=tuple(
                    DimensionalRelationshipResult.model_validate(row, strict=False)
                    for row in page.rows
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
        "get_model_dimensional_relationships",
        policy=POLICY,
        summarize_input=lambda arguments: audit_input(arguments, "dimensional_entity_ids"),
        retain_arguments={"model_id", "page_size", "schema_version"},
    )


def _annotations() -> ToolAnnotations:
    return ToolAnnotations(
        read_only_hint=True,
        destructive_hint=False,
        idempotent_hint=True,
        open_world_hint=False,
    )
