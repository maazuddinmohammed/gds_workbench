"""Least-privilege PostgreSQL access for durable Workflow Run claims."""

from contextlib import AbstractAsyncContextManager
from datetime import datetime
from typing import LiteralString, Protocol
from uuid import UUID

from gds_etl_workbench.domain.errors import DependencyUnavailableError
from gds_etl_workbench.infrastructure.postgres import ReadIsolation, WriteTransaction
from pydantic import BaseModel, ConfigDict, Field

from .contracts import WorkflowExecutionClaim

_CLAIM_NEXT_SQL: LiteralString = """
SELECT claimed.*
  FROM application.claim_next_workflow_run(%s::INTEGER) AS claimed
"""

_RENEW_CLAIM_SQL: LiteralString = """
SELECT renewed.*
  FROM application.renew_workflow_run_claim(
       %s::BIGINT,
       %s::UUID,
       %s::INTEGER
  ) AS renewed
"""

_RELEASE_CLAIM_SQL: LiteralString = """
SELECT application.release_workflow_run_claim(
           %s::BIGINT,
           %s::UUID
       ) AS released
"""


class WorkflowClaimLease(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    workflow_run_id: int = Field(gt=0)
    workflow_run_claim_heartbeat_time: datetime
    workflow_run_claim_expires_time: datetime


class WorkflowClaimDatabase(Protocol):
    def write_transaction(
        self,
        *,
        isolation: ReadIsolation = ReadIsolation.READ_COMMITTED,
    ) -> AbstractAsyncContextManager[WriteTransaction]: ...


class DatabaseWorkflowClaimRepository:
    def __init__(self, *, database: WorkflowClaimDatabase) -> None:
        self._database = database

    async def claim_next(
        self,
        *,
        lease_duration_seconds: int,
    ) -> WorkflowExecutionClaim | None:
        _validate_lease_duration(lease_duration_seconds)
        async with self._database.write_transaction() as transaction:
            row = await transaction.fetch_one(
                _CLAIM_NEXT_SQL,
                (lease_duration_seconds,),
            )
        if row is None:
            return None
        return WorkflowExecutionClaim.model_validate(row, strict=False)

    async def renew(
        self,
        *,
        workflow_run_id: int,
        workflow_run_claim_token: UUID,
        lease_duration_seconds: int,
    ) -> WorkflowClaimLease:
        _validate_lease_duration(lease_duration_seconds)
        async with self._database.write_transaction() as transaction:
            row = await transaction.fetch_one(
                _RENEW_CLAIM_SQL,
                (
                    workflow_run_id,
                    workflow_run_claim_token,
                    lease_duration_seconds,
                ),
            )
        if row is None:
            raise DependencyUnavailableError()
        return WorkflowClaimLease.model_validate(row, strict=False)

    async def release(
        self,
        *,
        workflow_run_id: int,
        workflow_run_claim_token: UUID,
    ) -> bool:
        async with self._database.write_transaction() as transaction:
            row = await transaction.fetch_one(
                _RELEASE_CLAIM_SQL,
                (workflow_run_id, workflow_run_claim_token),
            )
        if row is None or row.get("released") is not True:
            raise DependencyUnavailableError()
        return True


def _validate_lease_duration(value: int) -> None:
    if isinstance(value, bool) or value < 1 or value > 300:
        raise ValueError("Workflow Run lease duration must be between 1 and 300 seconds")


__all__ = [
    "DatabaseWorkflowClaimRepository",
    "WorkflowClaimDatabase",
    "WorkflowClaimLease",
]
