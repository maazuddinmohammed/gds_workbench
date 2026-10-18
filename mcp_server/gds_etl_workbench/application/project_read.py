"""Shared Project read authorization and context contracts."""

from __future__ import annotations

from dataclasses import dataclass
from typing import LiteralString

from pydantic import BaseModel, ConfigDict

from gds_etl_workbench.application.authorization import (
    AuthorizationService,
    TenantAuthorization,
    readable_tenant_ids,
)
from gds_etl_workbench.domain.authorization import RequestPrincipal, ToolPolicy
from gds_etl_workbench.domain.errors import InvalidRequestError
from gds_etl_workbench.infrastructure.postgres import ReadTransaction

POLICY = ToolPolicy.TENANT_READ

_PROJECT_CONTEXT_SQL: LiteralString = """
SELECT target_project.project_id,
       target_project.tenant_id,
       tenant.tenant_code,
       target_project.project_name,
       target_project.project_revision,
       target_project.is_locked,
       ARRAY(
           SELECT other_project.project_name
             FROM project.project AS other_project
            WHERE other_project.tenant_id = target_project.tenant_id
              AND other_project.project_id <> target_project.project_id
              AND other_project.is_active
            ORDER BY lower(btrim(other_project.project_name))
       ) AS other_active_project_names
  FROM project.project AS target_project
  JOIN core.tenant AS tenant
    ON tenant.tenant_id = target_project.tenant_id
   AND tenant.is_active
 WHERE target_project.project_id = %s
   AND target_project.is_active
"""


class ContractModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


@dataclass(frozen=True, slots=True)
class ProjectReadContext:
    project_id: int
    tenant_id: int
    project_name: str
    project_revision: int
    is_locked: bool = False
    tenant_code: str | None = None
    other_active_project_names: tuple[str, ...] = ()
    readable_source_tenant_ids: tuple[int, ...] = ()


async def authorize_project_read(
    transaction: ReadTransaction,
    *,
    authorizer: AuthorizationService,
    principal: RequestPrincipal,
    project_id: int,
) -> ProjectReadContext:
    row = await transaction.fetch_one(_PROJECT_CONTEXT_SQL, (project_id,))
    if row is None:
        raise InvalidRequestError("Project was not found.")
    authorization = await authorizer.authorize_tenant(
        transaction,
        principal,
        tenant_id=row["tenant_id"],
        policy=POLICY,
        project_id=project_id,
    )
    readable = authorization.readable_source_tenant_ids
    return ProjectReadContext(
        project_id=row["project_id"],
        tenant_id=row["tenant_id"],
        project_name=row["project_name"],
        project_revision=row["project_revision"],
        is_locked=bool(row.get("is_locked", False)),
        tenant_code=row.get("tenant_code"),
        readable_source_tenant_ids=readable,
        other_active_project_names=tuple(row.get("other_active_project_names") or ()),
    )


_PROJECT_SOURCE_TENANTS_SQL: LiteralString = """
SELECT DISTINCT object.source_tenant_id
  FROM project.project_input_scope AS scope
  JOIN core.object AS object ON object.object_id = scope.object_id
 WHERE scope.project_id = %s
"""


async def require_project_source_access(
    transaction: ReadTransaction, project_id: int, readable: tuple[int, ...]
) -> None:
    """Protect current and historical input references when access is revoked."""
    sources = await transaction.fetch_all(_PROJECT_SOURCE_TENANTS_SQL, (project_id,))
    if any(row["source_tenant_id"] not in readable for row in sources):
        raise InvalidRequestError("Access to the Project's Source Tenant metadata is required.")


async def authorize_project_sources(
    transaction: ReadTransaction, authorization: TenantAuthorization, project_id: int
) -> tuple[int, ...]:
    """Apply Source Tenant access after the caller authorizes the owning Project Tenant."""
    readable = await readable_tenant_ids(transaction, authorization.principal)
    await require_project_source_access(transaction, project_id, readable)
    return readable
