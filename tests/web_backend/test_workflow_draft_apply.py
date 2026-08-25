from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from typing import Any, LiteralString, cast
from uuid import UUID

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from gds_etl_workbench.adapters.auth.identity import IdentityProvider
from gds_etl_workbench.application.authorization import AuthorizationService
from gds_etl_workbench.configuration import AuthMode
from gds_etl_workbench.domain.authorization import ActorKind, RequestPrincipal
from gds_etl_workbench.domain.errors import (
    DependencyUnavailableError,
    InvalidRequestError,
    ModelChangeSetNotFoundError,
)
from gds_etl_workbench.infrastructure.postgres import WriteTransaction

from gds_workbench_api.features.workflows.authoring.change_set_apply import (
    ApplyWorkflowDraftRequest,
    ApplyWorkflowDraftResult,
    DatabaseWorkflowDraftApplyService,
)
from gds_workbench_api.features.workflows.authoring.change_set_apply_router import (
    WorkflowDraftApplyService,
    create_workflow_draft_apply_router,
)

_MAPPING_PROFILE_SCHEMA_DIGEST = (
    "b3b324170019b51d2b812c3735fa6215e463209ea39e4099b44c786b956da8fa"
)


class StaticWorkflowDraftApplyService:
    async def apply(
        self,
        principal: RequestPrincipal,
        *,
        tenant_id: int,
        model_id: int,
        workflow_run_id: int,
        command: ApplyWorkflowDraftRequest,
        idempotency_key: UUID,
    ) -> ApplyWorkflowDraftResult:
        assert principal.actor_kind is ActorKind.HUMAN
        assert (tenant_id, model_id, workflow_run_id) == (7, 18, 44)
        assert command.expected_model_revision == 4
        assert command.expected_draft_revision == 2
        assert command.expected_candidate_digest == "d" * 64
        assert idempotency_key == UUID("aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa")
        return ApplyWorkflowDraftResult(
            model_id=model_id,
            workflow_run_id=workflow_run_id,
            model_change_set_id=UUID("bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb"),
            replayed=False,
            draft_revision=2,
            candidate_digest="d" * 64,
            action_count=3,
            model_revision=5,
            applied_at=datetime(2026, 8, 24, 16, 0, tzinfo=UTC),
        )


def _identity_provider() -> IdentityProvider:
    return IdentityProvider(
        AuthMode.DEV,
        local_tenant_id=UUID("11111111-1111-1111-1111-111111111111"),
        local_principal_object_id=UUID("22222222-2222-2222-2222-222222222222"),
    )


def test_workflow_draft_apply_route_is_explicit_and_fenced() -> None:
    app = FastAPI()
    app.include_router(
        create_workflow_draft_apply_router(
            identity_provider=_identity_provider(),
            service=cast(
                WorkflowDraftApplyService,
                StaticWorkflowDraftApplyService(),
            ),
        )
    )

    with TestClient(app) as client:
        response = client.post(
            "/api/v1/tenants/7/models/18/runs/44/draft/apply",
            headers={"Idempotency-Key": "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa"},
            json={
                "expected_model_revision": 4,
                "expected_draft_revision": 2,
                "expected_candidate_digest": "d" * 64,
            },
        )

    assert response.status_code == 200
    assert response.json() == {
        "schema_version": "1.0",
        "model_id": 18,
        "workflow_run_id": 44,
        "model_change_set_id": "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb",
        "replayed": False,
        "draft_revision": 2,
        "candidate_digest": "d" * 64,
        "action_count": 3,
        "model_revision": 5,
        "applied_at": "2026-08-24T16:00:00Z",
    }


class MissingMappingDraftTransaction:
    def __init__(self, *, profile_schema_digest: str, model_workflow: str) -> None:
        self.profile_schema_digest = profile_schema_digest
        self.model_workflow = model_workflow

    async def fetch_one(
        self,
        query: LiteralString,
        parameters: tuple[Any, ...] = (),
    ) -> dict[str, Any] | None:
        if "FROM model.model AS target_model" in query:
            return {
                "model_id": 18,
                "tenant_id": 7,
                "model_name": "Customer 360",
                "model_revision": 4,
            }
        if "security.authorize_tenant_operation" in query or "WITH actor AS" in query:
            return {
                "principal_id": 41,
                "principal_display_name": "Maaz",
                "is_super_admin": False,
                "effective_role": "architect",
                "authorized": True,
                "denial_code": None,
                "lock_owner_display_name": None,
                "lock_expires_time": datetime(2026, 8, 24, 17, 0, tzinfo=UTC),
            }
        if "application.lock_authoring_workflow_run" in query:
            assert "mapping_profile_schema_digest" in query
            assert "mapping_object_output_template_id" in query
            assert "mapping_attribute_output_template_id" in query
            return {
                "workflow_run_id": 44,
                "model_id": 18,
                "model_workflow": self.model_workflow,
                "workflow_execution_mode": "one_shot",
                "actor_principal_id": 41,
                "workflow_run_state": "completed",
                "correlation_id": UUID("cccccccc-cccc-4ccc-8ccc-cccccccccccc"),
                "mapping_profile_key": "mapping.standard",
                "mapping_profile_version": "1.0.0",
                "mapping_profile_schema_digest": self.profile_schema_digest,
                "mapping_object_output_template_id": 501,
                "mapping_attribute_output_template_id": 502,
            }
        if "model_change_set.workflow_run_id" in query:
            return None
        raise AssertionError(f"unexpected draft apply query: {query}")


class MissingMappingDraftDatabase:
    def __init__(
        self,
        *,
        profile_schema_digest: str = _MAPPING_PROFILE_SCHEMA_DIGEST,
        model_workflow: str = "mapping",
    ) -> None:
        self.profile_schema_digest = profile_schema_digest
        self.model_workflow = model_workflow

    @asynccontextmanager
    async def write_transaction(self) -> AsyncGenerator[WriteTransaction]:
        yield cast(
            WriteTransaction,
            MissingMappingDraftTransaction(
                profile_schema_digest=self.profile_schema_digest,
                model_workflow=self.model_workflow,
            ),
        )


@pytest.mark.asyncio
async def test_completed_mapping_run_reaches_validated_draft_lookup() -> None:
    service = DatabaseWorkflowDraftApplyService(
        database=MissingMappingDraftDatabase(),
        authorizer=AuthorizationService(),
    )
    principal = RequestPrincipal(
        actor_kind=ActorKind.HUMAN,
        entra_tenant_id=UUID("11111111-1111-1111-1111-111111111111"),
        entra_object_id=UUID("22222222-2222-2222-2222-222222222222"),
    )

    with pytest.raises(ModelChangeSetNotFoundError):
        await service.apply(
            principal,
            tenant_id=7,
            model_id=18,
            workflow_run_id=44,
            command=ApplyWorkflowDraftRequest(
                expected_model_revision=4,
                expected_draft_revision=2,
                expected_candidate_digest="d" * 64,
            ),
            idempotency_key=UUID("aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa"),
        )


@pytest.mark.asyncio
async def test_mapping_profile_drift_is_rejected_before_draft_lookup() -> None:
    service = DatabaseWorkflowDraftApplyService(
        database=MissingMappingDraftDatabase(profile_schema_digest="b" * 64),
        authorizer=AuthorizationService(),
    )
    principal = RequestPrincipal(
        actor_kind=ActorKind.HUMAN,
        entra_tenant_id=UUID("11111111-1111-1111-1111-111111111111"),
        entra_object_id=UUID("22222222-2222-2222-2222-222222222222"),
    )

    with pytest.raises(DependencyUnavailableError):
        await service.apply(
            principal,
            tenant_id=7,
            model_id=18,
            workflow_run_id=44,
            command=ApplyWorkflowDraftRequest(
                expected_model_revision=4,
                expected_draft_revision=2,
                expected_candidate_digest="d" * 64,
            ),
            idempotency_key=UUID("aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa"),
        )


@pytest.mark.asyncio
async def test_apply_whitelist_message_includes_mapping() -> None:
    service = DatabaseWorkflowDraftApplyService(
        database=MissingMappingDraftDatabase(model_workflow="profiling"),
        authorizer=AuthorizationService(),
    )
    principal = RequestPrincipal(
        actor_kind=ActorKind.HUMAN,
        entra_tenant_id=UUID("11111111-1111-1111-1111-111111111111"),
        entra_object_id=UUID("22222222-2222-2222-2222-222222222222"),
    )

    with pytest.raises(InvalidRequestError, match="Dimensional, or Mapping authoring"):
        await service.apply(
            principal,
            tenant_id=7,
            model_id=18,
            workflow_run_id=44,
            command=ApplyWorkflowDraftRequest(
                expected_model_revision=4,
                expected_draft_revision=2,
                expected_candidate_digest="d" * 64,
            ),
            idempotency_key=UUID("aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa"),
        )
