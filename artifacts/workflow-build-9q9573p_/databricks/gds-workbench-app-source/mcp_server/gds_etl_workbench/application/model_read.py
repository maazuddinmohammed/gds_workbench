"""Shared Model read authorization and context contracts."""

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

_MODEL_CONTEXT_SQL: LiteralString = """
SELECT target_model.model_id,
       target_model.tenant_id,
       tenant.tenant_code,
       target_model.model_name,
       target_model.model_revision,
       ARRAY(
           SELECT other_model.model_name
             FROM model.model AS other_model
            WHERE other_model.tenant_id = target_model.tenant_id
              AND other_model.model_id <> target_model.model_id
              AND other_model.is_active
            ORDER BY lower(btrim(other_model.model_name))
       ) AS other_active_model_names
  FROM model.model AS target_model
  JOIN core.tenant AS tenant
    ON tenant.tenant_id = target_model.tenant_id
   AND tenant.is_active
 WHERE target_model.model_id = %s
   AND target_model.is_active
"""


class ContractModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


@dataclass(frozen=True, slots=True)
class ModelReadContext:
    model_id: int
    tenant_id: int
    model_name: str
    model_revision: int
    tenant_code: str | None = None
    other_active_model_names: tuple[str, ...] = ()
    readable_source_tenant_ids: tuple[int, ...] = ()


async def authorize_model_read(
    transaction: ReadTransaction,
    *,
    authorizer: AuthorizationService,
    principal: RequestPrincipal,
    model_id: int,
) -> ModelReadContext:
    row = await transaction.fetch_one(_MODEL_CONTEXT_SQL, (model_id,))
    if row is None:
        raise InvalidRequestError("Model was not found.")
    authorization = await authorizer.authorize_tenant(
        transaction,
        principal,
        tenant_id=row["tenant_id"],
        policy=POLICY,
        model_id=model_id,
    )
    readable = authorization.readable_source_tenant_ids
    return ModelReadContext(
        model_id=row["model_id"],
        tenant_id=row["tenant_id"],
        model_name=row["model_name"],
        model_revision=row["model_revision"],
        tenant_code=row.get("tenant_code"),
        readable_source_tenant_ids=readable,
        other_active_model_names=tuple(row.get("other_active_model_names") or ()),
    )


_MODEL_SOURCE_TENANTS_SQL: LiteralString = """
SELECT DISTINCT object.source_tenant_id
  FROM model.model_input_scope AS scope
  JOIN core.object AS object ON object.object_id = scope.object_id
 WHERE scope.model_id = %s
"""


async def require_model_source_access(
    transaction: ReadTransaction, model_id: int, readable: tuple[int, ...]
) -> None:
    """Protect current and historical input references when access is revoked."""
    sources = await transaction.fetch_all(_MODEL_SOURCE_TENANTS_SQL, (model_id,))
    if any(row["source_tenant_id"] not in readable for row in sources):
        raise InvalidRequestError("Access to the Model's Source Tenant metadata is required.")


async def authorize_model_sources(
    transaction: ReadTransaction, authorization: TenantAuthorization, model_id: int
) -> tuple[int, ...]:
    """Apply Source Tenant access after the caller authorizes the owning Model Tenant."""
    readable = await readable_tenant_ids(transaction, authorization.principal)
    await require_model_source_access(transaction, model_id, readable)
    return readable
