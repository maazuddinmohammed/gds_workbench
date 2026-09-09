"""HTTP routes for reviewing and downloading stored SQL artifacts."""

from typing import Annotated

from fastapi import APIRouter, Path, Query, Request, Response
from gds_etl_workbench.application.identity import IdentityProvider

from .contracts import (
    MAX_SELECTED_ARTIFACTS,
    CodeGenerationTargetFilters,
    CodeGenerationTargetPage,
    CodeGenerationTargetQuery,
    GeneratedSqlArtifactDetail,
)
from .downloads import build_selected_sql_zip, sql_artifact_filename
from .read_service import CodeGenerationService


def create_code_generation_router(
    *,
    identity_provider: IdentityProvider,
    service: CodeGenerationService,
) -> APIRouter:
    """Create stored SQL routes for application composition."""
    router = APIRouter(
        prefix="/api/v1/tenants/{tenant_id}/models/{model_id}/code-generation",
        tags=["code-generation"],
    )

    async def list_targets(
        request: Request,
        tenant_id: Annotated[int, Path(gt=0)],
        model_id: Annotated[int, Path(gt=0)],
        query: Annotated[CodeGenerationTargetQuery, Query()],
    ) -> CodeGenerationTargetPage:
        filters = CodeGenerationTargetFilters.model_validate(
            {
                "entity_type": query.entity_type,
                "system_id": query.system_id,
                "system_code": query.system_code,
                "source_system_id": query.source_system_id,
                "source_system_code": query.source_system_code,
            },
            strict=True,
        )
        principal = identity_provider.authenticate(request.headers)
        return await service.list_targets(
            principal,
            tenant_id=tenant_id,
            model_id=model_id,
            filters=filters,
            page_size=query.page_size,
            cursor=query.cursor,
        )

    router.add_api_route(
        "/targets",
        list_targets,
        methods=["GET"],
        response_model=CodeGenerationTargetPage,
    )

    async def read_artifact(
        request: Request,
        tenant_id: Annotated[int, Path(gt=0)],
        model_id: Annotated[int, Path(gt=0)],
        generated_sql_artifact_id: Annotated[int, Path(gt=0)],
    ) -> GeneratedSqlArtifactDetail:
        principal = identity_provider.authenticate(request.headers)
        return await service.read_artifact(
            principal,
            tenant_id=tenant_id,
            model_id=model_id,
            generated_sql_artifact_id=generated_sql_artifact_id,
        )

    router.add_api_route(
        "/artifacts/{generated_sql_artifact_id}",
        read_artifact,
        methods=["GET"],
        response_model=GeneratedSqlArtifactDetail,
    )

    async def download_artifact(
        request: Request,
        tenant_id: Annotated[int, Path(gt=0)],
        model_id: Annotated[int, Path(gt=0)],
        generated_sql_artifact_id: Annotated[int, Path(gt=0)],
    ) -> Response:
        principal = identity_provider.authenticate(request.headers)
        artifact = await service.read_artifact(
            principal,
            tenant_id=tenant_id,
            model_id=model_id,
            generated_sql_artifact_id=generated_sql_artifact_id,
        )
        filename = sql_artifact_filename(artifact)
        return Response(
            content=artifact.generated_sql.encode(),
            media_type="application/sql",
            headers={
                "Cache-Control": "no-store",
                "Content-Disposition": f'attachment; filename="{filename}"',
                "X-Content-Type-Options": "nosniff",
            },
        )

    router.add_api_route(
        "/artifacts/{generated_sql_artifact_id}/download.sql",
        download_artifact,
        methods=["GET"],
        response_class=Response,
    )

    async def download_selected_artifacts(
        request: Request,
        tenant_id: Annotated[int, Path(gt=0)],
        model_id: Annotated[int, Path(gt=0)],
        artifact_ids: Annotated[
            list[int],
            Query(
                alias="artifact_id",
                min_length=1,
                max_length=MAX_SELECTED_ARTIFACTS,
            ),
        ],
    ) -> Response:
        principal = identity_provider.authenticate(request.headers)
        artifacts = await service.read_artifacts_for_download(
            principal,
            tenant_id=tenant_id,
            model_id=model_id,
            generated_sql_artifact_ids=tuple(artifact_ids),
        )
        content = build_selected_sql_zip(artifacts)
        filename = f"gds_sql_artifacts__model_{model_id}__{len(artifacts)}.zip"
        return Response(
            content=content,
            media_type="application/zip",
            headers={
                "Cache-Control": "no-store",
                "Content-Disposition": f'attachment; filename="{filename}"',
                "X-Content-Type-Options": "nosniff",
                "X-GDS-Artifact-Count": str(len(artifacts)),
            },
        )

    router.add_api_route(
        "/downloads/selected.zip",
        download_selected_artifacts,
        methods=["GET"],
        response_class=Response,
    )
    return router
