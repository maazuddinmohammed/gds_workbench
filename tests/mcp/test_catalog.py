from __future__ import annotations

from dataclasses import dataclass, field

import pytest

from gds_etl_workbench.application.cursor import CursorCodec
from gds_etl_workbench.application.ports import ReadinessRecord, TenantRecord
from gds_etl_workbench.catalog.feature import CatalogFeature
from gds_etl_workbench.contracts.catalog import ListTenantsRequest
from gds_etl_workbench.domain.authorization import RequestPrincipal, TenantRole
from gds_etl_workbench.domain.errors import InvalidRequestError


@dataclass
class RecordingRepository:
    records: list[TenantRecord]
    calls: list[tuple[int, int]] = field(default_factory=list)

    async def open(self) -> None: ...

    async def close(self) -> None: ...

    async def readiness(self) -> ReadinessRecord:
        return ReadinessRecord(ready=True, code="ready")

    async def list_tenants(
        self, principal: RequestPrincipal, *, limit: int, offset: int
    ) -> list[TenantRecord]:
        self.calls.append((limit, offset))
        return self.records[offset : offset + limit]


def tenant(tenant_id: int, name: str) -> TenantRecord:
    return TenantRecord(
        tenant_id=tenant_id,
        tenant_code=f"T{tenant_id}",
        tenant_name=name,
        tenant_description=None,
        tenant_visibility="private",
        effective_role=TenantRole.VIEWER,
    )


@pytest.mark.asyncio
async def test_list_tenants_pages_with_a_signed_cursor() -> None:
    repository = RecordingRepository([tenant(1, "Alpha"), tenant(2, "Beta")])
    feature = CatalogFeature(repository, CursorCodec(b"a" * 32))

    first = await feature.list_tenants(
        RequestPrincipal.development(), ListTenantsRequest(page_size=1)
    )
    second = await feature.list_tenants(
        RequestPrincipal.development(),
        ListTenantsRequest(page_size=1, cursor=first.next_cursor),
    )

    assert [item.tenant_name for item in first.tenants] == ["Alpha"]
    assert [item.tenant_name for item in second.tenants] == ["Beta"]
    assert second.next_cursor is None
    assert repository.calls == [(2, 0), (2, 1)]


@pytest.mark.asyncio
async def test_tampered_cursor_is_rejected_before_repository_access() -> None:
    repository = RecordingRepository([tenant(1, "Alpha")])
    feature = CatalogFeature(repository, CursorCodec(b"a" * 32))
    valid = feature.cursors.encode(collection="list_tenants", offset=1)

    with pytest.raises(InvalidRequestError, match="cursor"):
        await feature.list_tenants(
            RequestPrincipal.development(),
            ListTenantsRequest(cursor=f"{valid[:-1]}x"),
        )

    assert repository.calls == []
