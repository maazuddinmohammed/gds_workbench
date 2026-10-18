"""Context reads remain authorized, bounded, portable and cursor-scoped."""

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from typing import Any, LiteralString
from uuid import UUID

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from gds_etl_workbench.adapters.auth.identity import IdentityProvider
from gds_etl_workbench.application.authorization import AuthorizationService
from gds_etl_workbench.configuration import AuthMode
from gds_etl_workbench.domain.authorization import ActorKind, RequestPrincipal
from gds_etl_workbench.domain.errors import InvalidRequestError, WorkbenchError
from gds_etl_workbench.infrastructure.postgres import ReadIsolation
from gds_workbench_api.features.context import (
    DatabaseContextService,
    create_context_router,
)
from gds_workbench_api.features.context.authoring import SaveContextRecordRequest
from gds_workbench_api.features.context.contracts import (
    ContextGroupFilters,
    ContextPayloadNotSafeError,
    ContextRecordFilters,
)
from gds_workbench_api.features.project_change_sets.contracts import (
    ReviewProjectRecordsRequest,
)
from gds_workbench_api.main import create_app
from pydantic import ValidationError

RECORD_ID = "00000000-0000-4000-8000-000000000001"
NOW = datetime(2026, 8, 24, 14, 0, tzinfo=UTC)
TYPE = {
    "context_type_id": 3,
    "context_type_name": "Business Requirement",
    "context_type_description": "Required business outcomes.",
}
GROUP = {
    "context_group_id": 101,
    "context_group_name": "Customer requirements",
    "context_type": TYPE,
    "source_system": None,
    "is_active": True,
}


class ContextTransaction:
    authorized = True
    project_exists = True
    oversized = False
    calls: list[tuple[str, tuple[Any, ...]]]

    def __init__(self) -> None:
        self.calls = []

    async def fetch_one(
        self, query: LiteralString, parameters: tuple[Any, ...] = ()
    ) -> dict[str, Any] | None:
        self.calls.append((query, parameters))
        if "security.entra_principal_identity" in query:
            return {
                "principal_id": 41,
                "principal_display_name": "Reviewer",
                "is_super_admin": False,
                "effective_role": "viewer",
                "authorized": self.authorized,
                "denial_code": None if self.authorized else "tenant_access_denied",
                "lock_owner_display_name": None,
                "lock_expires_time": None,
            }
        if "SELECT project_revision" in query:
            return {"project_revision": 4} if self.project_exists else None
        assert "owned_project.tenant_id = %s" in query and "owned_project.project_id = %s" in query
        if "record.context_record_id = %s::UUID" in query:
            assert parameters == (7, 18, RECORD_ID)
            return {
                **self.record(),
                "context_text": "A Customer is one governed party.",
                "source_reference": "Customer requirements, section 2",
                "created_at": NOW,
                "text_is_oversized": self.oversized,
                "source_is_oversized": False,
            }
        assert parameters == (7, 18, 101)
        return {
            **self.group(),
            "context_group_description": "Customer meaning and requirements.",
            "created_at": NOW,
        }

    async def fetch_all(
        self, query: LiteralString, parameters: tuple[Any, ...] = ()
    ) -> list[dict[str, Any]]:
        self.calls.append((query, parameters))
        if "FROM reference.context_type" in query:
            assert parameters == ()
            return [TYPE]
        if "FROM core.system" in query:
            assert "WHERE is_active" in query
            limit, offset = parameters
            rows = [
                {"system_id": 9, "system_code": "CRM", "system_name": "Customer system"},
                {"system_id": 10, "system_code": "ERP", "system_name": "Orders system"},
            ]
            return rows[offset : offset + limit]
        assert "owned_project.tenant_id = %s" in query and "owned_project.project_id = %s" in query
        assert parameters[:2] == (7, 18)
        limit, offset = parameters[-2:]
        rows = (
            [
                self.record(),
                {
                    **self.record(),
                    "context_record_id": "00000000-0000-4000-8000-000000000002",
                },
            ]
            if "AS context_text_preview" in query
            else [self.group(), {**self.group(), "context_group_id": 102}]
        )
        return rows[offset : offset + limit]

    @staticmethod
    def group() -> dict[str, Any]:
        return {
            **GROUP,
            "record_count": 2,
            "active_record_count": 2,
            "locked_record_count": 1,
            "updated_at": NOW,
        }

    @staticmethod
    def record() -> dict[str, Any]:
        return {
            "context_record_id": RECORD_ID,
            "group": GROUP,
            "context_text_preview": "A Customer is one governed party.",
            "text_truncated": False,
            "source_reference_preview": "Customer requirements, section 2",
            "source_reference_truncated": False,
            "status": "active",
            "is_locked": True,
            "updated_at": NOW,
        }


class ContextDatabase:
    def __init__(self) -> None:
        self.transaction = ContextTransaction()

    @asynccontextmanager
    async def read_transaction(
        self, *, isolation: ReadIsolation = ReadIsolation.READ_COMMITTED
    ) -> AsyncGenerator[ContextTransaction]:
        assert isolation is ReadIsolation.REPEATABLE_READ
        yield self.transaction


def principal() -> RequestPrincipal:
    return RequestPrincipal(
        actor_kind=ActorKind.HUMAN,
        entra_tenant_id=UUID("11111111-1111-1111-1111-111111111111"),
        entra_object_id=UUID("22222222-2222-2222-2222-222222222222"),
    )


def service(database: ContextDatabase) -> DatabaseContextService:
    return DatabaseContextService(
        database=database,
        authorizer=AuthorizationService(),
        cursor_signing_key=b"development-only-key-32-bytes-long",
    )


async def test_context_catalog_and_details_require_project_authority() -> None:
    database = ContextDatabase()
    reader = service(database)
    types = await reader.list_types(principal(), tenant_id=7, project_id=18)
    assert types.items[0].context_type_name == "Business Requirement"
    group = await reader.read_group(principal(), tenant_id=7, project_id=18, context_group_id=101)
    assert group.context_group_description == "Customer meaning and requirements."
    detail = await reader.read_record(
        principal(), tenant_id=7, project_id=18, context_record_id=RECORD_ID
    )
    assert detail.context_record_id == RECORD_ID
    assert detail.source_reference == "Customer requirements, section 2"
    assert (
        not {"record_key", "record_type", "details", "confidence", "applicable_layers"}
        & detail.model_dump().keys()
    )
    database.transaction.project_exists = False
    with pytest.raises(WorkbenchError):
        await reader.list_types(principal(), tenant_id=7, project_id=18)
    database.transaction.authorized = False
    with pytest.raises(WorkbenchError):
        await reader.read_record(
            principal(), tenant_id=7, project_id=18, context_record_id=RECORD_ID
        )


async def test_context_pages_bind_cursor_to_filters_and_project() -> None:
    database = ContextDatabase()
    reader = service(database)
    filters = ContextGroupFilters(
        context_type_id=3, source_system_id=9, active=True, name_prefix=" CUST "
    )
    page = await reader.list_groups(
        principal(),
        tenant_id=7,
        project_id=18,
        filters=filters,
        page_size=1,
        cursor=None,
    )
    assert page.project_revision == 4 and page.next_cursor
    assert database.transaction.calls[-1][1] == (
        7,
        18,
        3,
        3,
        9,
        9,
        True,
        True,
        "cust",
        "cust",
        2,
        0,
    )
    second = await reader.list_groups(
        principal(),
        tenant_id=7,
        project_id=18,
        filters=filters,
        page_size=1,
        cursor=page.next_cursor,
    )
    assert second.items[0].context_group_id == 102
    with pytest.raises(InvalidRequestError):
        await reader.list_groups(
            principal(),
            tenant_id=7,
            project_id=19,
            filters=filters,
            page_size=1,
            cursor=page.next_cursor,
        )
    with pytest.raises(InvalidRequestError):
        await reader.list_groups(
            principal(),
            tenant_id=7,
            project_id=18,
            filters=ContextGroupFilters(),
            page_size=1,
            cursor=page.next_cursor,
        )


async def test_context_record_filters_and_bounded_detail() -> None:
    database = ContextDatabase()
    reader = service(database)
    filters = ContextRecordFilters(
        group_id=101,
        context_type_id=3,
        source_system_id=9,
        status="active",
        locked=True,
        text_search=" CUSTOMER ",
    )
    page = await reader.list_records(
        principal(),
        tenant_id=7,
        project_id=18,
        filters=filters,
        page_size=1,
        cursor=None,
    )
    assert page.items[0].context_text_preview == "A Customer is one governed party."
    assert database.transaction.calls[-1][1] == (
        7,
        18,
        101,
        101,
        3,
        3,
        9,
        9,
        "active",
        "active",
        True,
        True,
        "customer",
        "customer",
        2,
        0,
    )
    database.transaction.oversized = True
    with pytest.raises(ContextPayloadNotSafeError):
        await reader.read_record(
            principal(), tenant_id=7, project_id=18, context_record_id=RECORD_ID
        )


def test_context_http_routes_and_uuid_validation() -> None:
    application = FastAPI()
    application.include_router(
        create_context_router(
            identity_provider=IdentityProvider(
                AuthMode.DEV,
                local_tenant_id=principal().entra_tenant_id,
                local_principal_object_id=principal().entra_object_id,
            ),
            service=service(ContextDatabase()),
        )
    )
    client = TestClient(application)
    prefix = "/api/v1/tenants/7/projects/18/context"
    assert client.get(prefix + "/types").json()["items"][0]["context_type_id"] == 3
    assert client.get(prefix + "/groups", params={"page_size": 1}).status_code == 200
    assert client.get(prefix + "/records/" + RECORD_ID).status_code == 200
    assert client.get(prefix + "/records/123").status_code == 422
    assert (
        client.get(prefix + "/records", params={"applicable_layer": "logical"}).status_code == 422
    )


def test_context_source_system_options_are_bounded_and_project_authorized() -> None:
    database = ContextDatabase()
    application = create_app(
        identity_provider=IdentityProvider(
            AuthMode.DEV,
            local_tenant_id=principal().entra_tenant_id,
            local_principal_object_id=principal().entra_object_id,
        ),
        context_service=service(database),
    )
    client = TestClient(application)
    path = "/api/v1/tenants/7/projects/18/context/source-systems"
    first = client.get(path, params={"page_size": 1})
    assert first.status_code == 200
    page = first.json()
    assert page["items"] == [
        {"system_id": 9, "system_code": "CRM", "system_name": "Customer system"}
    ]
    assert page["next_cursor"]
    second = client.get(path, params={"page_size": 1, "cursor": page["next_cursor"]})
    assert second.status_code == 200
    assert second.json()["items"][0]["system_id"] == 10
    assert second.json()["next_cursor"] is None
    for invalid_path, params in (
        (path.replace("projects/18", "projects/19"), {"page_size": 1}),
        (path.replace("tenants/7", "tenants/8"), {"page_size": 1}),
        (path, {"page_size": 2}),
    ):
        assert (
            client.get(invalid_path, params={**params, "cursor": page["next_cursor"]}).status_code
            == 422
        )
    assert client.get(path, params={"page_size": 201}).status_code == 422
    assert client.get(path, params={"is_active": False}).status_code == 422
    database.transaction.project_exists = False
    assert client.get(path).status_code == 404
    database.transaction.authorized = False
    assert client.get(path).status_code == 403


def test_context_write_bounds_and_dataset_specific_review_ids() -> None:
    fields = {
        "action": "create",
        "expected_project_revision": 1,
        "context_record_id": RECORD_ID,
        "context_group_id": 101,
        "context_text": "Customer IDs must be stable.",
    }
    assert SaveContextRecordRequest.model_validate(fields).context_record_id == RECORD_ID
    updates: tuple[dict[str, object], ...] = (
        {"context_record_id": "customer.id"},
        {"context_text": " "},
        {"context_text": "x" * 262145},
        {"source_reference": "é" * 32769},
        {"details": {}},
        {"action": "save"},
    )
    for update in updates:
        with pytest.raises(ValidationError):
            SaveContextRecordRequest.model_validate({**fields, **update})
    base = {
        "dataset": "context_record",
        "record_ids": [RECORD_ID],
        "action": "lock",
        "expected_project_revision": 1,
    }
    assert ReviewProjectRecordsRequest.model_validate(base).record_ids == [RECORD_ID]
    updates = (
        {"record_ids": [1]},
        {"dataset": "logical_entity"},
        {"action": "delete"},
    )
    for update in updates:
        with pytest.raises(ValidationError):
            ReviewProjectRecordsRequest.model_validate({**base, **update})
