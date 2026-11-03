"""Tenant-scoped read-only Output Template HTTP routes."""

from typing import Annotated

from atlas_mcp.application.identity import IdentityProvider
from atlas_mcp.domain.authorization import RequestPrincipal
from fastapi import APIRouter, Depends, Path, Query

from atlas_platform.dependencies import principal_dependency
from atlas_platform.features.output_templates.contracts import (
    OutputTemplateDetail,
    OutputTemplateModeledEntityType,
    OutputTemplatePage,
    OutputTemplateTargetType,
)
from atlas_platform.features.output_templates.service import OutputTemplateService


def create_output_templates_router(
    *,
    identity_provider: IdentityProvider,
    service: OutputTemplateService,
) -> APIRouter:
    authenticate = principal_dependency(identity_provider)
    router = APIRouter(
        prefix="/api/v1/tenants/{tenant_id}/output-templates",
        tags=["output-templates"],
    )
    tenant_path = Path(gt=0)
    template_path = Path(gt=0)

    async def list_templates(
        tenant_id: Annotated[int, tenant_path],
        target_type: Annotated[OutputTemplateTargetType | None, Query()] = None,
        entity_type: Annotated[OutputTemplateModeledEntityType | None, Query()] = None,
        active: Annotated[bool | None, Query()] = True,
        page_size: Annotated[int, Query(ge=1, le=200)] = 50,
        cursor: Annotated[str | None, Query(max_length=2048)] = None,
        *,
        principal: RequestPrincipal = Depends(authenticate),
    ) -> OutputTemplatePage:
        return await service.list_templates(
            principal,
            tenant_id=tenant_id,
            target_type=target_type,
            entity_type=entity_type,
            active=active,
            page_size=page_size,
            cursor=cursor,
        )

    async def read_template(
        tenant_id: Annotated[int, tenant_path],
        output_template_id: Annotated[int, template_path],
        *,
        principal: RequestPrincipal = Depends(authenticate),
    ) -> OutputTemplateDetail:
        return await service.read_template(
            principal,
            tenant_id=tenant_id,
            output_template_id=output_template_id,
        )

    router.add_api_route(
        "",
        list_templates,
        methods=["GET"],
        response_model=OutputTemplatePage,
    )
    router.add_api_route(
        "/{output_template_id}",
        read_template,
        methods=["GET"],
        response_model=OutputTemplateDetail,
    )
    return router
