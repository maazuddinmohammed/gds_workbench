from collections.abc import AsyncGenerator
from contextlib import AbstractAsyncContextManager, asynccontextmanager
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
from gds_etl_workbench.infrastructure.postgres import WriteTransaction
from gds_etl_workbench.tools.change_sets.model import (
    ModelChangeSetDatasetCount,
    validate_model_stage_changes,
)
from gds_etl_workbench.tools.snapshots.model.contracts import ModelChangeSetDataset
from gds_workbench_api.features.model_change_sets.contracts import (
    ApplyModelChangeSetResult,
    CreateModelChangeSetRequest,
    CreateModelChangeSetResult,
    ExpectedDraftRevisionRequest,
    StageModelChangeSetRequest,
    StageModelChangeSetResult,
)
from gds_workbench_api.features.model_change_sets.router import (
    ModelChangeSetService,
    create_model_change_sets_router,
)
from gds_workbench_api.features.model_change_sets.service import (
    DatabaseModelChangeSetService,
)
from gds_workbench_api.main import create_app


class StaticModelChangeSetService:
    async def create_or_resume(
        self,
        principal: RequestPrincipal,
        *,
        tenant_id: int,
        model_id: int,
        command: CreateModelChangeSetRequest,
        idempotency_key: UUID,
    ) -> CreateModelChangeSetResult:
        assert principal.actor_kind is ActorKind.HUMAN
        assert (tenant_id, model_id) == (7, 18)
        assert command.expected_model_revision == 4
        assert idempotency_key == UUID("aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa")
        return CreateModelChangeSetResult(
            model_id=18,
            model_change_set_id=UUID("bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb"),
            created=True,
            status="active",
            draft_revision=1,
            created_at=datetime(2026, 8, 24, 15, 0, tzinfo=UTC),
            expires_at=datetime(2026, 8, 24, 19, 0, tzinfo=UTC),
        )


class StaticApplyService(StaticModelChangeSetService):
    async def apply(
        self,
        principal: RequestPrincipal,
        *,
        tenant_id: int,
        model_id: int,
        change_set_id: UUID,
        command: ExpectedDraftRevisionRequest,
        idempotency_key: UUID,
    ) -> ApplyModelChangeSetResult:
        assert principal.actor_kind is ActorKind.HUMAN
        assert (tenant_id, model_id, command.expected_draft_revision) == (7, 18, 3)
        assert change_set_id == UUID("bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb")
        assert idempotency_key == UUID("cccccccc-cccc-4ccc-8ccc-cccccccccccc")
        return ApplyModelChangeSetResult(
            model_id=18,
            model_change_set_id=change_set_id,
            draft_revision=3,
            candidate_digest="d" * 64,
            action_count=7,
            model_revision=5,
            applied_at=datetime(2026, 8, 24, 16, 0, tzinfo=UTC),
        )


class StaticStageService(StaticModelChangeSetService):
    async def stage(
        self,
        principal: RequestPrincipal,
        *,
        tenant_id: int,
        model_id: int,
        change_set_id: UUID,
        command: StageModelChangeSetRequest,
        idempotency_key: UUID,
    ) -> StageModelChangeSetResult:
        assert principal.actor_kind is ActorKind.HUMAN
        assert (tenant_id, model_id, command.expected_draft_revision) == (7, 18, 1)
        assert change_set_id == UUID("bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb")
        assert idempotency_key == UUID("cccccccc-cccc-4ccc-8ccc-cccccccccccc")
        staged = validate_model_stage_changes(command.changes)
        return StageModelChangeSetResult(
            model_id=model_id,
            model_change_set_id=change_set_id,
            datasets=tuple(
                ModelChangeSetDatasetCount(
                    dataset=cast(ModelChangeSetDataset, dataset),
                    record_count=len(records),
                )
                for dataset, records in staged.items()
            ),
            draft_revision=2,
            expires_at=datetime(2026, 8, 24, 19, 0, tzinfo=UTC),
        )


def _identity_provider() -> IdentityProvider:
    return IdentityProvider(
        AuthMode.DEV,
        local_tenant_id=UUID("11111111-1111-1111-1111-111111111111"),
        local_principal_object_id=UUID("22222222-2222-2222-2222-222222222222"),
    )


def test_create_model_change_set_route_derives_identity_and_fences_revision() -> None:
    app = FastAPI()
    app.include_router(
        create_model_change_sets_router(
            identity_provider=_identity_provider(),
            service=cast(ModelChangeSetService, StaticModelChangeSetService()),
        )
    )

    with TestClient(app) as client:
        response = client.post(
            "/api/v1/tenants/7/models/18/change-sets",
            headers={"Idempotency-Key": "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa"},
            json={"expected_model_revision": 4},
        )

    assert response.status_code == 201
    assert response.json() == {
        "schema_version": "1.0",
        "model_id": 18,
        "model_change_set_id": "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb",
        "created": True,
        "status": "active",
        "draft_revision": 1,
        "created_at": "2026-08-24T15:00:00Z",
        "expires_at": "2026-08-24T19:00:00Z",
    }


def test_apply_route_is_explicit_revision_fenced_and_idempotency_keyed() -> None:
    app = FastAPI()
    app.include_router(
        create_model_change_sets_router(
            identity_provider=_identity_provider(),
            service=cast(ModelChangeSetService, StaticApplyService()),
        )
    )

    with TestClient(app) as client:
        response = client.post(
            "/api/v1/tenants/7/models/18/change-sets/bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb/apply",
            headers={"Idempotency-Key": "cccccccc-cccc-4ccc-8ccc-cccccccccccc"},
            json={"expected_draft_revision": 3},
        )

    assert response.status_code == 200
    assert response.json()["model_revision"] == 5


def test_assertion_stage_route_accepts_bounded_structured_records() -> None:
    app = create_app(
        identity_provider=_identity_provider(),
        model_change_set_service=cast(ModelChangeSetService, StaticStageService()),
    )

    with TestClient(app) as client:
        response = client.put(
            "/api/v1/tenants/7/models/18/change-sets/bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb/stage",
            headers={"Idempotency-Key": "cccccccc-cccc-4ccc-8ccc-cccccccccccc"},
            json={
                "expected_draft_revision": 1,
                "changes": [
                    {
                        "dataset": "modeling_assertion_document",
                        "records": [
                            {
                                "modeling_assertion_document_name": "Customer rules",
                                "tenant_code": None,
                                "system_code": None,
                                "modeling_assertion_file_pattern": None,
                                "modeling_assertion_document_type": "policy",
                                "modeling_assertion_document_description": None,
                                "modeling_assertion_document_metadata": {
                                    "review_cycle": "quarterly"
                                },
                                "is_active": True,
                            }
                        ],
                    },
                    {
                        "dataset": "modeling_assertion_record",
                        "records": [
                            {
                                "modeling_assertion_record_key": "customer.identity",
                                "modeling_assertion_document_name": "Customer rules",
                                "modeling_assertion_record_type": "identity_rule",
                                "modeling_assertion_text": "Customer identity is stable.",
                                "modeling_assertion_details": {"verified": False},
                                "modeling_assertion_source_location": {"section": "Identity"},
                                "modeling_assertion_applicable_layers": ["logical"],
                                "modeling_assertion_confidence": "high",
                                "modeling_assertion_record_status": "needs_review",
                                "modeling_assertion_record_is_locked": False,
                            }
                        ],
                    },
                ],
            },
        )

    assert response.status_code == 200
    assert response.json()["datasets"] == [
        {"dataset": "modeling_assertion_document", "record_count": 1},
        {"dataset": "modeling_assertion_record", "record_count": 1},
    ]


class NoWriteDatabase:
    def __init__(self) -> None:
        self.write_attempted = False

    def write_transaction(self) -> AbstractAsyncContextManager[WriteTransaction]:
        self.write_attempted = True
        raise AssertionError("Unsafe Assertion staging reached the database")


@pytest.mark.parametrize(
    ("field", "unsafe_value", "raw_marker"),
    [
        (
            "modeling_assertion_details",
            {"review": {"raw_prompt": "sensitive prompt value"}},
            "sensitive prompt value",
        ),
        (
            "modeling_assertion_details",
            {"raw_tool_output": "sensitive tool value"},
            "sensitive tool value",
        ),
        (
            "modeling_assertion_source_location",
            {"file-content": "sensitive file value"},
            "sensitive file value",
        ),
        (
            "modeling_assertion_details",
            {"apiSecret": "sensitive secret value"},
            "sensitive secret value",
        ),
        ("modeling_assertion_text", "x" * 262_145, "x" * 100),
    ],
)
def test_assertion_stage_rejects_unsafe_content_before_database_access(
    field: str,
    unsafe_value: object,
    raw_marker: str,
) -> None:
    database = NoWriteDatabase()
    service = DatabaseModelChangeSetService(
        database=database,
        authorizer=AuthorizationService(),
    )
    app = create_app(
        identity_provider=_identity_provider(),
        model_change_set_service=service,
    )

    record: dict[str, object] = {
        "modeling_assertion_record_key": "customer.identity",
        "modeling_assertion_document_name": "Customer rules",
        "modeling_assertion_record_type": "identity_rule",
        "modeling_assertion_text": "Customer identity is stable.",
        "modeling_assertion_details": {"verified": False},
        "modeling_assertion_source_location": None,
        "modeling_assertion_applicable_layers": ["logical"],
        "modeling_assertion_confidence": "high",
        "modeling_assertion_record_status": "needs_review",
        "modeling_assertion_record_is_locked": False,
    }
    record[field] = unsafe_value

    with TestClient(app) as client:
        response = client.put(
            "/api/v1/tenants/7/models/18/change-sets/bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb/stage",
            headers={"Idempotency-Key": "cccccccc-cccc-4ccc-8ccc-cccccccccccc"},
            json={
                "expected_draft_revision": 1,
                "changes": [
                    {
                        "dataset": "modeling_assertion_record",
                        "records": [record],
                    }
                ],
            },
        )

    assert response.status_code == 422
    assert response.json()["error"]["message"] == (
        "Record does not match the exact modeling_assertion_record schema."
    )
    assert raw_marker not in response.text
    assert database.write_attempted is False


class CreateTransaction:
    def __init__(self) -> None:
        self.created = False

    async def fetch_one(
        self,
        query: LiteralString,
        parameters: tuple[Any, ...] = (),
    ) -> dict[str, Any] | None:
        if "INSERT INTO mcp.model_change_set (" in query:
            self.created = True
            return {
                "model_change_set_id": UUID("bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb"),
                "model_change_set_status": "active",
                "draft_revision": 1,
                "created_time": datetime(2026, 8, 24, 15, 0, tzinfo=UTC),
                "expires_time": datetime(2026, 8, 24, 19, 0, tzinfo=UTC),
            }
        if "FROM model.model AS target_model" in query:
            assert parameters == (7, 18)
            return {
                "model_id": 18,
                "tenant_id": 7,
                "model_name": "Customer 360",
                "model_revision": 4,
            }
        if "security.authorize_tenant_operation" in query:
            assert parameters[-2:] == (7, "tenant_model_write")
            return {
                "principal_id": 41,
                "principal_display_name": "Maaz",
                "is_super_admin": False,
                "effective_role": "architect",
                "authorized": True,
                "denial_code": None,
                "lock_owner_display_name": None,
                "lock_expires_time": datetime(2026, 8, 24, 16, 0, tzinfo=UTC),
            }
        if "model_change_set_status IN ('active', 'validated')" in query:
            assert "workflow_run_id IS NULL" in query
            return None
        if "INSERT INTO mcp.model_change_set_event" in query:
            assert parameters[2] == "created"
            assert parameters[-2] == UUID("aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa")
            return {"model_change_set_event_id": 1}
        raise AssertionError((query, parameters))

    async def fetch_all(
        self,
        query: LiteralString,
        parameters: tuple[Any, ...] = (),
    ) -> list[dict[str, Any]]:
        if "SET model_change_set_status = 'expired'" in query:
            assert "workflow_run_id IS NULL" in query
            return []
        raise AssertionError((query, parameters))


class CreateDatabase:
    def __init__(self) -> None:
        self.transaction = CreateTransaction()

    @asynccontextmanager
    async def write_transaction(self) -> AsyncGenerator[CreateTransaction]:
        yield self.transaction


@pytest.mark.asyncio
async def test_create_service_authorizes_owned_lock_and_current_model_revision() -> None:
    database = CreateDatabase()
    service = DatabaseModelChangeSetService(
        database=database,
        authorizer=AuthorizationService(),
    )

    result = await service.create_or_resume(
        _identity_provider().authenticate({}),
        tenant_id=7,
        model_id=18,
        command=CreateModelChangeSetRequest(expected_model_revision=4),
        idempotency_key=UUID("aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa"),
    )

    assert result.created is True
    assert result.draft_revision == 1
    assert database.transaction.created is True
