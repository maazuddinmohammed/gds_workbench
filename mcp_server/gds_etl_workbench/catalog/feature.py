"""Tenant catalog use case."""

from dataclasses import dataclass

from gds_etl_workbench.application.cursor import CursorCodec
from gds_etl_workbench.application.ports import StateRepository
from gds_etl_workbench.contracts.catalog import (
    ListTenantsRequest,
    ListTenantsResult,
    TenantSummary,
)
from gds_etl_workbench.domain.authorization import Capability, RequestPrincipal, has_capability
from gds_etl_workbench.domain.errors import AuthorizationDeniedError

_COLLECTION = "list_tenants"


@dataclass(frozen=True, slots=True)
class CatalogFeature:
    repository: StateRepository
    cursors: CursorCodec

    async def list_tenants(
        self, principal: RequestPrincipal, request: ListTenantsRequest
    ) -> ListTenantsResult:
        offset = self.cursors.decode(request.cursor, collection=_COLLECTION)
        records = await self.repository.list_tenants(
            principal,
            limit=request.page_size + 1,
            offset=offset,
        )
        visible_records = records[: request.page_size]
        if any(
            not has_capability(record.effective_role, Capability.READ_TENANT)
            for record in visible_records
        ):
            raise AuthorizationDeniedError()

        next_cursor = None
        if len(records) > request.page_size:
            next_cursor = self.cursors.encode(
                collection=_COLLECTION,
                offset=offset + request.page_size,
            )
        return ListTenantsResult(
            tenants=tuple(
                TenantSummary(
                    tenant_id=record.tenant_id,
                    tenant_code=record.tenant_code,
                    tenant_name=record.tenant_name,
                    tenant_description=record.tenant_description,
                    tenant_visibility=record.tenant_visibility,  # type: ignore[arg-type]
                    effective_role=record.effective_role,
                )
                for record in visible_records
            ),
            next_cursor=next_cursor,
        )
