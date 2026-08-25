"""Transaction-local fencing for durable Workflow Run workers."""

from typing import Any, LiteralString, Protocol
from uuid import UUID

from gds_etl_workbench.domain.errors import DependencyUnavailableError

_ASSERT_CLAIM_SQL: LiteralString = """
SELECT application.assert_workflow_run_claim(
           %s::BIGINT,
           %s::UUID
       ) AS asserted
"""


class WorkflowClaimFenceTransaction(Protocol):
    async def fetch_one(
        self,
        query: LiteralString,
        parameters: tuple[Any, ...] = (),
    ) -> dict[str, Any] | None: ...


async def assert_workflow_run_claim(
    transaction: WorkflowClaimFenceTransaction,
    *,
    workflow_run_id: int,
    workflow_run_claim_token: UUID,
) -> None:
    """Lock and verify the live claim before writes in this transaction."""
    row = await transaction.fetch_one(
        _ASSERT_CLAIM_SQL,
        (workflow_run_id, workflow_run_claim_token),
    )
    if row is None:
        raise DependencyUnavailableError()


__all__ = ["WorkflowClaimFenceTransaction", "assert_workflow_run_claim"]
