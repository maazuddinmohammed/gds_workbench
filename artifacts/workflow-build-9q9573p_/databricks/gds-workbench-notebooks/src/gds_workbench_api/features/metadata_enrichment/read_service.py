"""Authorize exact Run identity before reading its durable field outcomes."""

import json
from contextlib import AbstractAsyncContextManager
from typing import Any, Protocol, cast

from gds_etl_workbench.application.authorization import AuthorizationService
from gds_etl_workbench.domain.authorization import RequestPrincipal, ToolPolicy
from gds_etl_workbench.domain.errors import DependencyUnavailableError, InvalidRequestError
from gds_etl_workbench.infrastructure.postgres import ReadIsolation, WriteTransaction
from pydantic import ValidationError

from gds_workbench_api.features.workflows.authoring.lifecycle import workflow_identity_triple
from gds_workbench_api.features.workflows.runs import WorkflowRunNotFoundError

from .read_contracts import MetadataEnrichmentResultPage


class MetadataEnrichmentReadDatabase(Protocol):
    def write_transaction(
        self, *, isolation: ReadIsolation = ReadIsolation.READ_COMMITTED
    ) -> AbstractAsyncContextManager[WriteTransaction]: ...


class MetadataEnrichmentReadService(Protocol):
    async def read_results(
        self,
        principal: RequestPrincipal,
        *,
        tenant_id: int,
        model_id: int,
        workflow_run_id: int,
        limit: int = 100,
        offset: int = 0,
    ) -> MetadataEnrichmentResultPage: ...


class DatabaseMetadataEnrichmentReadService:
    def __init__(
        self, *, database: MetadataEnrichmentReadDatabase, authorizer: AuthorizationService
    ) -> None:
        self._database = database
        self._authorizer = authorizer

    async def read_results(
        self,
        principal: RequestPrincipal,
        *,
        tenant_id: int,
        model_id: int,
        workflow_run_id: int,
        limit: int = 100,
        offset: int = 0,
    ) -> MetadataEnrichmentResultPage:
        if not 1 <= limit <= 200 or not 0 <= offset <= 10_200:
            raise InvalidRequestError("The metadata enrichment result page is invalid.")
        # The governed read takes authorization share locks, which PostgreSQL
        # forbids in a READ ONLY transaction. Every application statement is SELECT.
        async with self._database.write_transaction(
            isolation=ReadIsolation.REPEATABLE_READ
        ) as transaction:
            await self._authorizer.authorize_tenant(
                transaction,
                principal,
                tenant_id=tenant_id,
                policy=ToolPolicy.TENANT_READ,
            )
            route = await transaction.fetch_one(
                """
                SELECT run.workflow_run_id
                  FROM application.workflow_run AS run
                  JOIN model.model AS model USING (model_id, tenant_id)
                 WHERE run.tenant_id = %s AND run.model_id = %s
                   AND run.workflow_run_id = %s AND model.is_active
                   AND run.model_workflow = 'metadata_enrichment'
                """,
                (tenant_id, model_id, workflow_run_id),
            )
            if route is None:
                raise WorkflowRunNotFoundError()
            row = await transaction.fetch_one(
                "SELECT application.get_metadata_enrichment_results(%s,%s,%s,%s,%s,%s) AS result",
                workflow_identity_triple(principal) + (workflow_run_id, limit, offset),
            )
        try:
            if row is None or not isinstance(row["result"], dict):
                raise ValueError("Missing enrichment result")
            payload = cast(dict[str, Any], row["result"])
            next_offset = offset + len(payload["results"])
            page = MetadataEnrichmentResultPage.model_validate_json(
                json.dumps(
                    {
                        **payload,
                        "limit": limit,
                        "offset": offset,
                        "next_offset": next_offset
                        if next_offset < payload["total_count"]
                        else None,
                    },
                    ensure_ascii=False,
                    allow_nan=False,
                ),
                strict=True,
            )
            if (page.tenant_id, page.model_id, page.workflow_run_id) != (
                tenant_id,
                model_id,
                workflow_run_id,
            ):
                raise ValueError("Enrichment result identity differs from the route")
            return page
        except (KeyError, TypeError, ValueError, ValidationError):
            raise DependencyUnavailableError() from None
