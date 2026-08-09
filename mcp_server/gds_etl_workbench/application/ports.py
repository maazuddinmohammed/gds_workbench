"""Typed persistence boundary used by application features."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from gds_etl_workbench.domain.authorization import RequestPrincipal, TenantRole


@dataclass(frozen=True, slots=True)
class TenantRecord:
    tenant_id: int
    tenant_code: str
    tenant_name: str
    tenant_description: str | None
    tenant_visibility: str
    effective_role: TenantRole


@dataclass(frozen=True, slots=True)
class ReadinessRecord:
    ready: bool
    code: str


class StateRepository(Protocol):
    async def open(self) -> None: ...

    async def close(self) -> None: ...

    async def list_tenants(
        self, principal: RequestPrincipal, *, limit: int, offset: int
    ) -> list[TenantRecord]: ...

    async def readiness(self) -> ReadinessRecord: ...
