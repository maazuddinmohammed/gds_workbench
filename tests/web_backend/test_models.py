from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from typing import Any, LiteralString
from uuid import UUID

import pytest
from fastapi.testclient import TestClient
from gds_etl_workbench.adapters.auth.identity import IdentityProvider
from gds_etl_workbench.application.authorization import AuthorizationService
from gds_etl_workbench.configuration import AuthMode
from gds_etl_workbench.domain.authorization import ActorKind, RequestPrincipal
from gds_etl_workbench.infrastructure.postgres import ReadIsolation

from gds_workbench_api.main import create_app
from gds_workbench_api.features.models import (
    DatabaseModelService,
    ModelCollection,
    ModelDetail,
    ModelLedgerRecord,
    ModelStatus,
)


class StaticModelService:
    async def list_models(
        self,
        principal: RequestPrincipal,
        *,
        tenant_id: int,
        model_status: ModelStatus,
        page_size: int,
        cursor: str | None,
    ) -> ModelCollection:
        assert principal.actor_kind is ActorKind.HUMAN
        assert (tenant_id, model_status, page_size, cursor) == (7, "active", 25, None)
        return ModelCollection(
            items=(
                ModelLedgerRecord(
                    model_id=18,
                    model_name="Customer 360",
                    model_description="Cross-system customer domain",
                    model_revision=18,
                    model_scope_object_count=25,
                    latest_workflow="analysis",
                    latest_run_status="completed",
                    updated_at=datetime(2026, 8, 24, 14, 0, tzinfo=UTC),
                ),
            ),
            next_cursor=None,
        )

    async def read_model(
        self,
        principal: RequestPrincipal,
        *,
        tenant_id: int,
        model_id: int,
    ) -> ModelDetail:
        assert principal.actor_kind is ActorKind.HUMAN
        assert (tenant_id, model_id) == (7, 18)
        return ModelDetail(
            model_id=18,
            tenant_id=7,
            model_name="Customer 360",
            model_description="Cross-system customer domain",
            model_revision=18,
            model_scope_object_count=25,
            silver_model_naming_instructions="Use business names.",
            silver_model_audit_columns_template={"columns": ["created_at"]},
            gold_model_naming_instructions=None,
            gold_model_technical_columns_template=None,
            gold_model_audit_columns_template=None,
            default_agent_sdk_code="langchain_create_agent",
            default_agent_provider_code="microsoft_foundry",
            default_agent_model_code="gpt-5.6",
            default_reasoning_effort_code="medium",
            default_max_turns=10,
            default_validation_retry_count=2,
            is_active=True,
            updated_at=datetime(2026, 8, 24, 14, 0, tzinfo=UTC),
        )


def test_model_ledger_is_tenant_scoped_and_contains_current_workflow_state() -> None:
    app = create_app(
        identity_provider=IdentityProvider(
            AuthMode.DEV,
            local_tenant_id=UUID("11111111-1111-1111-1111-111111111111"),
            local_principal_object_id=UUID("22222222-2222-2222-2222-222222222222"),
        ),
        model_service=StaticModelService(),
    )

    with TestClient(app) as client:
        response = client.get("/api/v1/tenants/7/models?status=active&page_size=25")

    assert response.status_code == 200
    assert response.json() == {
        "items": [
            {
                "model_id": 18,
                "model_name": "Customer 360",
                "model_description": "Cross-system customer domain",
                "model_revision": 18,
                "model_scope_object_count": 25,
                "latest_workflow": "analysis",
                "latest_run_status": "completed",
                "updated_at": "2026-08-24T14:00:00Z",
            }
        ],
        "next_cursor": None,
    }


def test_model_detail_exposes_server_stored_settings_without_raw_prompts() -> None:
    app = create_app(
        identity_provider=IdentityProvider(
            AuthMode.DEV,
            local_tenant_id=UUID("11111111-1111-1111-1111-111111111111"),
            local_principal_object_id=UUID("22222222-2222-2222-2222-222222222222"),
        ),
        model_service=StaticModelService(),
    )

    with TestClient(app) as client:
        response = client.get("/api/v1/tenants/7/models/18")

    assert response.status_code == 200
    detail = response.json()
    assert detail["model_name"] == "Customer 360"
    assert detail["default_agent_provider_code"] == "microsoft_foundry"
    assert detail["model_scope_object_count"] == 25
    assert "prompt_text" not in detail


class ModelTransaction:
    def __init__(self) -> None:
        self.offsets: list[int] = []

    async def fetch_one(
        self,
        query: LiteralString,
        parameters: tuple[Any, ...] = (),
    ) -> dict[str, Any] | None:
        if "FROM model.model AS model" in query:
            assert parameters == (7, 18)
            return {
                "model_id": 18,
                "tenant_id": 7,
                "model_name": "Customer 360",
                "model_description": "Cross-system customer domain",
                "model_revision": 18,
                "model_scope_object_count": 25,
                "silver_model_naming_instructions": None,
                "silver_model_audit_columns_template": None,
                "gold_model_naming_instructions": None,
                "gold_model_technical_columns_template": None,
                "gold_model_audit_columns_template": None,
                "default_agent_sdk_code": None,
                "default_agent_provider_code": None,
                "default_agent_model_code": None,
                "default_reasoning_effort_code": None,
                "default_max_turns": None,
                "default_validation_retry_count": None,
                "is_active": True,
                "updated_at": datetime(2026, 8, 24, 14, 0, tzinfo=UTC),
            }
        assert "security.entra_principal_identity" in query
        assert parameters[-1] == 7
        return {
            "principal_id": 41,
            "principal_display_name": "Maaz",
            "is_super_admin": False,
            "effective_role": "tenant_admin",
            "authorized": True,
            "denial_code": None,
            "lock_owner_display_name": None,
            "lock_expires_time": None,
        }

    async def fetch_all(
        self,
        query: LiteralString,
        parameters: tuple[Any, ...] = (),
    ) -> list[dict[str, Any]]:
        assert "application.workflow_run" in query
        assert "workflow_run.workflow_run_state" in query
        assert "workflow_run.workflow_run_status" not in query
        assert parameters[:2] == (7, True)
        limit, offset = parameters[2:]
        assert limit == 2
        self.offsets.append(offset)
        rows = [
            {
                "model_id": 18,
                "model_name": "Customer 360",
                "model_description": None,
                "model_revision": 18,
                "model_scope_object_count": 25,
                "latest_workflow": "analysis",
                "latest_run_status": "completed",
                "updated_at": datetime(2026, 8, 24, 14, 0, tzinfo=UTC),
            },
            {
                "model_id": 19,
                "model_name": "Finance Core",
                "model_description": None,
                "model_revision": 6,
                "model_scope_object_count": 42,
                "latest_workflow": "logical",
                "latest_run_status": "completed",
                "updated_at": datetime(2026, 8, 23, 14, 0, tzinfo=UTC),
            },
        ]
        return rows[offset : offset + limit]


class ModelDatabase:
    def __init__(self) -> None:
        self.transaction = ModelTransaction()

    @asynccontextmanager
    async def read_transaction(
        self,
        *,
        isolation: ReadIsolation = ReadIsolation.READ_COMMITTED,
    ) -> AsyncGenerator[ModelTransaction]:
        assert isolation is ReadIsolation.REPEATABLE_READ
        yield self.transaction


@pytest.mark.asyncio
async def test_database_model_ledger_uses_signed_paging_and_tenant_authorization() -> (
    None
):
    database = ModelDatabase()
    service = DatabaseModelService(
        database=database,
        authorizer=AuthorizationService(),
        cursor_signing_key=b"development-only-key-32-bytes-long",
    )
    principal = RequestPrincipal(
        actor_kind=ActorKind.HUMAN,
        entra_tenant_id=UUID("11111111-1111-1111-1111-111111111111"),
        entra_object_id=UUID("22222222-2222-2222-2222-222222222222"),
    )

    first = await service.list_models(
        principal,
        tenant_id=7,
        model_status="active",
        page_size=1,
        cursor=None,
    )
    second = await service.list_models(
        principal,
        tenant_id=7,
        model_status="active",
        page_size=1,
        cursor=first.next_cursor,
    )

    assert [item.model_name for item in first.items] == ["Customer 360"]
    assert [item.model_name for item in second.items] == ["Finance Core"]
    assert second.next_cursor is None
    assert database.transaction.offsets == [0, 1]


@pytest.mark.asyncio
async def test_database_model_detail_is_authorized_and_tenant_scoped() -> None:
    database = ModelDatabase()
    service = DatabaseModelService(
        database=database,
        authorizer=AuthorizationService(),
        cursor_signing_key=b"development-only-key-32-bytes-long",
    )
    principal = RequestPrincipal(
        actor_kind=ActorKind.HUMAN,
        entra_tenant_id=UUID("11111111-1111-1111-1111-111111111111"),
        entra_object_id=UUID("22222222-2222-2222-2222-222222222222"),
    )

    detail = await service.read_model(
        principal,
        tenant_id=7,
        model_id=18,
    )

    assert detail.model_name == "Customer 360"
    assert detail.model_scope_object_count == 25
