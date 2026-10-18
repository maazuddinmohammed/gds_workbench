"""Project dictionary reads and a consistent, authorized workbook export."""

# pyright: reportPrivateUsage=false

import re
from typing import Annotated, LiteralString

from fastapi import APIRouter, Depends, Path, Response
from gds_etl_workbench.application.identity import IdentityProvider
from gds_etl_workbench.domain.authorization import RequestPrincipal, ToolPolicy
from gds_etl_workbench.domain.errors import InvalidRequestError
from gds_etl_workbench.infrastructure.postgres import ReadIsolation
from starlette.concurrency import run_in_threadpool

from gds_workbench_api.dependencies import principal_dependency
from gds_workbench_api.features.project_input_scope.contracts import (
    ProjectInputScopeAttribute,
    ProjectInputScopeObject,
)
from gds_workbench_api.features.project_input_scope.router import create_input_scope_router
from gds_workbench_api.features.project_input_scope.service import (
    _ENRICHMENT_ATTRIBUTES_SQL,
    _ENRICHMENT_OBJECT_SQL,
    DatabaseProjectInputScopeService,
)
from gds_workbench_api.features.projects import ProjectNotFoundError

from .workbook import MAX_DICTIONARY_ROWS, build_enrichment_workbook

_EXPORT_ATTRIBUTES_SQL: LiteralString = (
    _ENRICHMENT_ATTRIBUTES_SQL.replace(
        "SELECT attribute.attribute_id,", "SELECT attribute.object_id, attribute.attribute_id,"
    ).replace("attribute.object_id = %s", "attribute.object_id = ANY(%s::BIGINT[])")
    + " LIMIT 50001"
)


class DatabaseEnrichmentDictionaryService(DatabaseProjectInputScopeService):
    async def export_workbook(
        self,
        principal: RequestPrincipal,
        *,
        tenant_id: int,
        project_id: int,
    ) -> tuple[str, bytes]:
        async with self._database.read_transaction(
            isolation=ReadIsolation.REPEATABLE_READ
        ) as transaction:
            await self._authorizer.authorize_tenant(
                transaction,
                principal,
                tenant_id=tenant_id,
                policy=ToolPolicy.TENANT_READ,
                project_id=project_id,
            )
            project = await transaction.fetch_one(
                "SELECT project_name FROM project.project "
                "WHERE tenant_id = %s AND project_id = %s AND is_active",
                (tenant_id, project_id),
            )
            if project is None:
                raise ProjectNotFoundError()
            objects = await transaction.fetch_all(
                _ENRICHMENT_OBJECT_SQL[0],
                (tenant_id, project_id, None, None, None, None, None, None, None, None, 1001, 0),
            )
            if len(objects) > 1000:
                raise InvalidRequestError("Enrichment export supports at most 1,000 Objects.")
            attributes = await transaction.fetch_all(
                _EXPORT_ATTRIBUTES_SQL,
                (project_id, [obj["object_id"] for obj in objects]),
            )
            if len(attributes) > MAX_DICTIONARY_ROWS:
                raise InvalidRequestError("Enrichment export supports at most 50,000 Attributes.")
        grouped: dict[int, list[ProjectInputScopeAttribute]] = {}
        for row in attributes:
            grouped.setdefault(row["object_id"], []).append(
                ProjectInputScopeAttribute.model_validate(
                    {key: value for key, value in row.items() if key != "object_id"}
                )
            )
        rows: list[tuple[ProjectInputScopeObject, ProjectInputScopeAttribute | None]] = []
        for item in objects:
            obj = ProjectInputScopeObject.model_validate(item)
            rows.extend((obj, attr) for attr in grouped.get(obj.object_id, [None]))
        try:
            content = await run_in_threadpool(build_enrichment_workbook, rows)
        except ValueError:
            raise InvalidRequestError(
                "The enrichment dictionary exceeds Excel export limits."
            ) from None
        name = re.sub(r"[^A-Za-z0-9_-]+", "_", project["project_name"]).strip("_")[:100]
        return f"{name or 'Project'}_Enrichment.xlsx", content


def create_enrichment_dictionary_router(
    *,
    identity_provider: IdentityProvider,
    service: DatabaseEnrichmentDictionaryService,
) -> APIRouter:
    router = APIRouter()
    router.include_router(
        create_input_scope_router(
            identity_provider=identity_provider,
            service=service,
            enrichment=True,
        )
    )
    authenticate = principal_dependency(identity_provider)

    async def export_workbook(
        tenant_id: Annotated[int, Path(gt=0)],
        project_id: Annotated[int, Path(gt=0)],
        principal: RequestPrincipal = Depends(authenticate),
    ) -> Response:
        filename, content = await service.export_workbook(
            principal,
            tenant_id=tenant_id,
            project_id=project_id,
        )
        return Response(
            content,
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            headers={
                "Content-Disposition": f'attachment; filename="{filename}"',
                "Cache-Control": "no-store",
            },
        )

    router.add_api_route(
        "/api/v1/tenants/{tenant_id}/projects/{project_id}/metadata-enrichment/export",
        export_workbook,
        methods=["GET"],
    )

    return router
