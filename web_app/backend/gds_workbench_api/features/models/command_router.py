"""Governed complete-Model command HTTP routes."""

from typing import Annotated

from fastapi import APIRouter, Depends, Path, status
from gds_etl_workbench.application.identity import IdentityProvider
from gds_etl_workbench.domain.authorization import RequestPrincipal

from gds_workbench_api.dependencies import principal_dependency
from gds_workbench_api.features.models.command_contracts import (
    ArchiveModelRequest,
    CompleteModelRequest,
    ModelCommandResult,
    UpdateModelRequest,
)
from gds_workbench_api.features.models.command_service import ModelCommandService

type PositivePathId = Annotated[int, Path(gt=0)]


def create_model_commands_router(
    *,
    identity_provider: IdentityProvider,
    service: ModelCommandService,
) -> APIRouter:
    authenticate = principal_dependency(identity_provider)
    router = APIRouter(prefix="/api/v1/tenants/{tenant_id}/models", tags=["models"])

    async def create_model(
        tenant_id: PositivePathId,
        command: CompleteModelRequest,
        *,
        principal: RequestPrincipal = Depends(authenticate),
    ) -> ModelCommandResult:
        return await service.create_model(
            principal,
            tenant_id=tenant_id,
            request=command,
        )

    router.add_api_route(
        "",
        create_model,
        methods=["POST"],
        response_model=ModelCommandResult,
        status_code=status.HTTP_201_CREATED,
    )

    async def update_model(
        tenant_id: PositivePathId,
        model_id: PositivePathId,
        command: UpdateModelRequest,
        *,
        principal: RequestPrincipal = Depends(authenticate),
    ) -> ModelCommandResult:
        return await service.update_model(
            principal,
            tenant_id=tenant_id,
            model_id=model_id,
            request=command,
        )

    router.add_api_route(
        "/{model_id}",
        update_model,
        methods=["PUT"],
        response_model=ModelCommandResult,
    )

    async def archive_model(
        tenant_id: PositivePathId,
        model_id: PositivePathId,
        command: ArchiveModelRequest,
        *,
        principal: RequestPrincipal = Depends(authenticate),
    ) -> ModelCommandResult:
        return await service.archive_model(
            principal,
            tenant_id=tenant_id,
            model_id=model_id,
            request=command,
        )

    router.add_api_route(
        "/{model_id}/archive",
        archive_model,
        methods=["POST"],
        response_model=ModelCommandResult,
    )

    return router
