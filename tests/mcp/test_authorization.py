from __future__ import annotations

from typing import Any, LiteralString

import pytest

from gds_etl_workbench.application.authorization import AuthorizationService
from gds_etl_workbench.domain.authorization import (
    RequestPrincipal,
    TenantRole,
    ToolPolicy,
)
from gds_etl_workbench.domain.errors import TenantLockRequiredError


class UnexpectedDatabaseAccess:
    async def fetch_one(
        self, query: LiteralString, parameters: tuple[Any, ...] = ()
    ) -> dict[str, Any] | None:
        raise AssertionError("dev authorization must not query production identity data")

    async def fetch_all(
        self, query: LiteralString, parameters: tuple[Any, ...] = ()
    ) -> list[dict[str, Any]]:
        raise AssertionError("dev authorization must not query production identity data")


@pytest.mark.asyncio
async def test_dev_tenant_read_skips_identity_and_role_checks() -> None:
    decision = await AuthorizationService().authorize_tenant(
        UnexpectedDatabaseAccess(),
        RequestPrincipal.development(),
        tenant_id=1,
        policy=ToolPolicy.TENANT_READ,
    )

    assert decision.effective_role is TenantRole.DEVELOPMENT


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "policy",
    [ToolPolicy.TENANT_METADATA_WRITE, ToolPolicy.TENANT_MODEL_WRITE],
)
async def test_dev_tenant_write_still_requires_a_tenant_lock(
    policy: ToolPolicy,
) -> None:
    with pytest.raises(TenantLockRequiredError):
        await AuthorizationService().authorize_tenant(
            UnexpectedDatabaseAccess(),
            RequestPrincipal.development(),
            tenant_id=1,
            policy=policy,
        )
