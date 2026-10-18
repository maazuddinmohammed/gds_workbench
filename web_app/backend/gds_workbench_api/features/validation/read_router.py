"""Validation eligibility and applied-ledger HTTP routes."""

from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Path, Query, Response
from gds_etl_workbench.application.identity import IdentityProvider
from gds_etl_workbench.domain.authorization import RequestPrincipal

from gds_workbench_api.dependencies import principal_dependency
from gds_workbench_api.features.projects.command_contracts import ProjectRevisionConflictError

from .contracts import ExportValidationRequest, ValidationEligibleSystemCollection, ValidationLedger
from .downloads import build_validation_zip
from .read_service import ValidationReadService


def create_validation_read_router(
    *,
    identity_provider: IdentityProvider,
    service: ValidationReadService,
) -> APIRouter:
    authenticate = principal_dependency(identity_provider)
    router = APIRouter(
        prefix="/api/v1/tenants/{tenant_id}/projects/{project_id}/validation",
        tags=["validation"],
    )

    async def list_eligible_systems(
        tenant_id: Annotated[int, Path(gt=0)],
        project_id: Annotated[int, Path(gt=0)],
        *,
        entity_type: Annotated[
            Literal["logical_entity", "dimensional_entity"] | None, Query()
        ] = None,
        principal: RequestPrincipal = Depends(authenticate),
    ) -> ValidationEligibleSystemCollection:
        return await service.list_eligible_systems(
            principal,
            tenant_id=tenant_id,
            project_id=project_id,
            entity_type=entity_type,
        )

    router.add_api_route(
        "/systems",
        list_eligible_systems,
        methods=["GET"],
        response_model=ValidationEligibleSystemCollection,
    )

    async def read_ledger(
        tenant_id: Annotated[int, Path(gt=0)],
        project_id: Annotated[int, Path(gt=0)],
        *,
        entity_type: Annotated[
            Literal["logical_entity", "dimensional_entity"] | None, Query()
        ] = None,
        principal: RequestPrincipal = Depends(authenticate),
    ) -> ValidationLedger:
        return await service.read_ledger(
            principal,
            tenant_id=tenant_id,
            project_id=project_id,
            entity_type=entity_type,
        )

    router.add_api_route(
        "/ledger",
        read_ledger,
        methods=["GET"],
        response_model=ValidationLedger,
    )

    async def download_all_checks(
        tenant_id: Annotated[int, Path(gt=0)],
        project_id: Annotated[int, Path(gt=0)],
        command: ExportValidationRequest,
        *,
        principal: RequestPrincipal = Depends(authenticate),
    ) -> Response:
        # The ledger supplies one authorized, bounded, repeatable-read snapshot.
        ledger = await service.read_ledger(
            principal,
            tenant_id=tenant_id,
            project_id=project_id,
            entity_type=command.entity_type,
        )
        if ledger.project_revision != command.expected_project_revision:
            raise ProjectRevisionConflictError()
        content, check_count = build_validation_zip(ledger, command)
        layer = "logical" if command.entity_type == "logical_entity" else "dimensional"
        filename = f"gds_validation_{layer}__project_{project_id}__r{ledger.project_revision}.zip"
        return Response(
            content=content,
            media_type="application/zip",
            headers={
                "Cache-Control": "no-store",
                "Content-Disposition": f'attachment; filename="{filename}"',
                "X-Content-Type-Options": "nosniff",
                "X-GDS-Check-Count": str(check_count),
                "X-GDS-Export-Scope": "active_validation_checks",
                "X-GDS-Project-Revision": str(ledger.project_revision),
            },
        )

    router.add_api_route(
        "/downloads/all.zip", download_all_checks, methods=["POST"], response_class=Response
    )
    return router


__all__ = ["create_validation_read_router"]
