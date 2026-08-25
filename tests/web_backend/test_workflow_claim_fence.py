from __future__ import annotations

from typing import Any, LiteralString
from uuid import UUID

import pytest
from gds_etl_workbench.domain.errors import DependencyUnavailableError

from gds_workbench_api.features.workflows.execution.fence import (
    assert_workflow_run_claim,
)


class RecordingTransaction:
    def __init__(self, row: dict[str, Any] | None) -> None:
        self.row = row
        self.calls: list[tuple[LiteralString, tuple[Any, ...]]] = []

    async def fetch_one(
        self,
        query: LiteralString,
        parameters: tuple[Any, ...] = (),
    ) -> dict[str, Any] | None:
        self.calls.append((query, parameters))
        return self.row


@pytest.mark.asyncio
async def test_claim_fence_calls_only_the_exact_database_assertion() -> None:
    token = UUID("10000000-0000-4000-8000-000000000001")
    transaction = RecordingTransaction({"asserted": None})

    await assert_workflow_run_claim(
        transaction,
        workflow_run_id=1048,
        workflow_run_claim_token=token,
    )

    assert len(transaction.calls) == 1
    query, parameters = transaction.calls[0]
    assert "application.assert_workflow_run_claim" in query
    assert parameters == (1048, token)


@pytest.mark.asyncio
async def test_claim_fence_rejects_a_missing_database_result() -> None:
    with pytest.raises(DependencyUnavailableError):
        await assert_workflow_run_claim(
            RecordingTransaction(None),
            workflow_run_id=1048,
            workflow_run_claim_token=UUID("10000000-0000-4000-8000-000000000001"),
        )
