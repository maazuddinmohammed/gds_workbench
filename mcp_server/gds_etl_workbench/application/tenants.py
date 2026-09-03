"""Authorized Tenant queries shared by MCP and web adapters."""

from __future__ import annotations

from typing import Any, LiteralString

from gds_etl_workbench.application.authorization import ResolvedPrincipal
from gds_etl_workbench.domain.authorization import ActorKind
from gds_etl_workbench.domain.errors import AuthorizationDeniedError
from gds_etl_workbench.infrastructure.postgres import ReadTransaction

_AUTHORIZED_TENANTS_SQL: LiteralString = """
WITH actor (principal_id, is_super_admin) AS (
    VALUES (%s::BIGINT, %s::BOOLEAN)
)
SELECT tenant.tenant_id,
       tenant.tenant_code,
       tenant.tenant_name,
       left(tenant.tenant_description, 2000) AS tenant_description,
       tenant.tenant_visibility,
       CASE
           WHEN actor.is_super_admin THEN 'super_admin'
           WHEN membership.tenant_role IS NOT NULL THEN membership.tenant_role
           ELSE 'viewer'
       END AS effective_role
  FROM actor
 CROSS JOIN core.tenant AS tenant
  LEFT JOIN security.tenant_principal_access AS membership
    ON membership.tenant_id = tenant.tenant_id
   AND membership.principal_id = actor.principal_id
   AND membership.is_active
   AND (
       membership.access_expires_time IS NULL
       OR membership.access_expires_time > CURRENT_TIMESTAMP
   )
 WHERE tenant.is_active
   AND (
       %s::BOOLEAN
       OR NOT EXISTS (
           SELECT 1
             FROM core.connection AS owned_connection
            WHERE owned_connection.tenant_id = tenant.tenant_id
              AND owned_connection.is_global_data_store
       )
   )
   AND (
       actor.is_super_admin
       OR tenant.tenant_visibility = 'global'
       OR membership.tenant_id IS NOT NULL
   )
 ORDER BY lower(tenant.tenant_name), tenant.tenant_id
 LIMIT %s OFFSET %s
"""

_DEV_TENANTS_SQL: LiteralString = """
SELECT tenant.tenant_id,
       tenant.tenant_code,
       tenant.tenant_name,
       left(tenant.tenant_description, 2000) AS tenant_description,
       tenant.tenant_visibility,
       'development' AS effective_role
  FROM core.tenant AS tenant
 WHERE tenant.is_active
   AND (
       %s::BOOLEAN
       OR NOT EXISTS (
           SELECT 1
             FROM core.connection AS owned_connection
            WHERE owned_connection.tenant_id = tenant.tenant_id
              AND owned_connection.is_global_data_store
       )
   )
 ORDER BY lower(tenant.tenant_name), tenant.tenant_id
 LIMIT %s OFFSET %s
"""


async def query_visible_tenants(
    transaction: ReadTransaction,
    principal: ResolvedPrincipal,
    *,
    limit: int,
    offset: int,
    include_global_data_store_owner_tenants: bool = True,
) -> list[dict[str, Any]]:
    """Query authorized Tenants, optionally omitting GDS Connection owners.

    The owner classification uses every retained Connection marked as a Global
    Data Store, including inactive Connections. Connection activity controls
    operational availability; it does not turn the owner into a Workbench Tenant.
    """
    if principal.actor_kind is ActorKind.DEVELOPMENT:
        return await transaction.fetch_all(
            _DEV_TENANTS_SQL,
            (include_global_data_store_owner_tenants, limit, offset),
        )
    if principal.principal_id is None:
        raise AuthorizationDeniedError()
    return await transaction.fetch_all(
        _AUTHORIZED_TENANTS_SQL,
        (
            principal.principal_id,
            principal.is_super_admin,
            include_global_data_store_owner_tenants,
            limit,
            offset,
        ),
    )


__all__ = ["query_visible_tenants"]
