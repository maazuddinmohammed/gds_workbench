from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta
from typing import Any, LiteralString
from uuid import UUID

import pytest
from gds_etl_workbench.infrastructure.postgres import ReadIsolation

from gds_workbench_api.features.workflows.execution import (
    DatabaseWorkflowClaimRepository,
)


class ClaimTransaction:
    def __init__(self) -> None:
        self.calls: list[tuple[str, tuple[Any, ...]]] = []
        self.return_no_claim = False
        self.claim_token = UUID("44444444-4444-4444-4444-444444444444")
        self.now = datetime(2026, 8, 24, 16, 0, tzinfo=UTC)

    async def fetch_one(
        self,
        query: LiteralString,
        parameters: tuple[Any, ...] = (),
    ) -> dict[str, Any] | None:
        self.calls.append((query, parameters))
        if "claim_next_workflow_run" in query:
            if self.return_no_claim:
                return None
            return {
                "workflow_run_id": 701,
                "tenant_id": 7,
                "model_id": 18,
                "model_revision": 4,
                "model_workflow": "analysis",
                "workflow_execution_mode": "one_shot",
                "correlation_id": UUID("11111111-1111-1111-1111-111111111111"),
                "actor_principal_type": "user",
                "actor_entra_tenant_id": UUID("22222222-2222-2222-2222-222222222222"),
                "actor_entra_object_id": UUID("33333333-3333-3333-3333-333333333333"),
                "workflow_run_claim_token": self.claim_token,
                "workflow_run_claimed_time": self.now,
                "workflow_run_claim_expires_time": self.now + timedelta(seconds=30),
                "workflow_run_recovery_count": 2,
            }
        if "renew_workflow_run_claim" in query:
            return {
                "workflow_run_id": 701,
                "workflow_run_claim_heartbeat_time": self.now + timedelta(seconds=10),
                "workflow_run_claim_expires_time": self.now + timedelta(seconds=40),
            }
        if "release_workflow_run_claim" in query:
            return {"released": True}
        raise AssertionError("unexpected query")

    async def fetch_all(
        self,
        query: LiteralString,
        parameters: tuple[Any, ...] = (),
    ) -> list[dict[str, Any]]:
        raise AssertionError("claim repository must not issue collection queries")


class ClaimDatabase:
    def __init__(self) -> None:
        self.transaction = ClaimTransaction()
        self.isolations: list[ReadIsolation] = []

    @asynccontextmanager
    async def write_transaction(
        self,
        *,
        isolation: ReadIsolation = ReadIsolation.READ_COMMITTED,
    ) -> AsyncGenerator[ClaimTransaction]:
        self.isolations.append(isolation)
        yield self.transaction


@pytest.mark.asyncio
async def test_repository_claims_and_validates_one_internal_run_contract() -> None:
    database = ClaimDatabase()
    repository = DatabaseWorkflowClaimRepository(database=database)

    claim = await repository.claim_next(lease_duration_seconds=30)

    assert claim is not None
    assert claim.workflow_run_id == 701
    assert claim.tenant_id == 7
    assert claim.workflow_execution_mode == "one_shot"
    assert claim.workflow_run_recovery_count == 2
    assert database.isolations == [ReadIsolation.READ_COMMITTED]
    query, parameters = database.transaction.calls[0]
    assert "application.claim_next_workflow_run(%s::INTEGER)" in query
    assert parameters == (30,)


@pytest.mark.asyncio
async def test_repository_returns_none_when_no_run_is_claimable() -> None:
    database = ClaimDatabase()
    database.transaction.return_no_claim = True

    claim = await DatabaseWorkflowClaimRepository(database=database).claim_next(
        lease_duration_seconds=30
    )

    assert claim is None


@pytest.mark.asyncio
async def test_repository_renews_and_releases_only_with_the_raw_claim_token() -> None:
    database = ClaimDatabase()
    repository = DatabaseWorkflowClaimRepository(database=database)
    token = database.transaction.claim_token

    lease = await repository.renew(
        workflow_run_id=701,
        workflow_run_claim_token=token,
        lease_duration_seconds=30,
    )
    released = await repository.release(
        workflow_run_id=701,
        workflow_run_claim_token=token,
    )

    assert lease.workflow_run_id == 701
    assert (
        lease.workflow_run_claim_expires_time
        == database.transaction.now + timedelta(seconds=40)
    )
    assert released is True
    renew_query, renew_parameters = database.transaction.calls[0]
    release_query, release_parameters = database.transaction.calls[1]
    assert "application.renew_workflow_run_claim" in renew_query
    assert renew_parameters == (701, token, 30)
    assert "application.release_workflow_run_claim" in release_query
    assert release_parameters == (701, token)
