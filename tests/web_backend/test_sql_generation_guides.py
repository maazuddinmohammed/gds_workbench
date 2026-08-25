from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from typing import Any, LiteralString, cast
from uuid import UUID

import pytest
from fastapi import FastAPI
from fastapi.routing import APIRoute
from fastapi.testclient import TestClient
from gds_etl_workbench.adapters.auth.identity import IdentityProvider
from gds_etl_workbench.application.authorization import AuthorizationService
from gds_etl_workbench.configuration import AuthMode
from gds_etl_workbench.domain.authorization import ActorKind, RequestPrincipal
from gds_etl_workbench.domain.errors import (
    AuthorizationDeniedError,
    DependencyUnavailableError,
)
from gds_etl_workbench.infrastructure.postgres import ReadIsolation

from gds_workbench_api.features.sql_generation_guides import (
    DatabaseSqlGenerationGuideService,
    SaveSqlGenerationGuideDraftRequest,
    SqlGenerationGuideConflictError,
    SqlGenerationGuideDatabase,
    SqlGenerationGuidePage,
    SqlGenerationGuideService,
    SqlGenerationGuideSummary,
    create_sql_generation_guides_router,
)

NOW = datetime(2026, 8, 24, 14, 0, tzinfo=UTC)
PRINCIPAL = RequestPrincipal(
    actor_kind=ActorKind.HUMAN,
    entra_tenant_id=UUID("11111111-1111-1111-1111-111111111111"),
    entra_object_id=UUID("22222222-2222-2222-2222-222222222222"),
)


def _authorization_row(*, is_super_admin: bool = False) -> dict[str, Any]:
    return {
        "principal_id": 41,
        "principal_display_name": "Guide Admin",
        "is_super_admin": is_super_admin,
        "effective_role": "super_admin" if is_super_admin else "architect",
        "authorized": True,
        "denial_code": None,
        "lock_owner_display_name": None,
        "lock_expires_time": None,
    }


def _guide_summary_row(guide_id: int, code: str) -> dict[str, Any]:
    return {
        "sql_generation_guide_id": guide_id,
        "sql_generation_guide_code": code,
        "sql_generation_guide_name": code.replace("_", " ").title(),
        "sql_generation_guide_description": None,
        "is_default": guide_id == 101,
        "is_active": True,
        "latest_version_id": guide_id + 1000,
        "latest_version_number": 2,
        "latest_version_status": "published",
        "latest_version_digest": "a" * 64,
        "latest_version_updated_at": NOW,
        "updated_at": NOW,
    }


class GuideListTransaction:
    def __init__(self) -> None:
        self.offsets: list[int] = []

    async def fetch_one(
        self,
        query: LiteralString,
        parameters: tuple[Any, ...] = (),
    ) -> dict[str, Any] | None:
        assert "security.entra_principal_identity" in query
        assert parameters[-1] == 7
        return _authorization_row()

    async def fetch_all(
        self,
        query: LiteralString,
        parameters: tuple[Any, ...] = (),
    ) -> list[dict[str, Any]]:
        assert "FROM application.sql_generation_guide AS guide" in query
        assert "sql_generation_guide_content" not in query
        limit, offset = parameters
        assert limit == 2
        self.offsets.append(offset)
        rows = [
            _guide_summary_row(101, "default_sql"),
            _guide_summary_row(102, "strict_sql"),
        ]
        return rows[offset : offset + limit]


class GuideListDatabase:
    def __init__(self) -> None:
        self.transaction = GuideListTransaction()

    @asynccontextmanager
    async def read_transaction(
        self,
        *,
        isolation: ReadIsolation = ReadIsolation.READ_COMMITTED,
    ) -> AsyncGenerator[GuideListTransaction]:
        assert isolation is ReadIsolation.REPEATABLE_READ
        yield self.transaction


@pytest.mark.asyncio
async def test_guide_list_is_tenant_authorized_content_free_and_signed_page_bounded() -> None:
    database = GuideListDatabase()
    service = DatabaseSqlGenerationGuideService(
        database=cast(SqlGenerationGuideDatabase, database),
        authorizer=AuthorizationService(),
        cursor_signing_key=b"development-only-key-32-bytes-long",
    )

    first = await service.list_guides(
        PRINCIPAL,
        tenant_id=7,
        page_size=1,
        cursor=None,
    )
    second = await service.list_guides(
        PRINCIPAL,
        tenant_id=7,
        page_size=1,
        cursor=first.next_cursor,
    )

    assert [item.sql_generation_guide_code for item in first.items] == ["default_sql"]
    assert [item.sql_generation_guide_code for item in second.items] == ["strict_sql"]
    assert second.next_cursor is None
    assert database.transaction.offsets == [0, 1]
    assert "sql_generation_guide_content" not in first.model_dump_json()


def _guide_version_row(version_id: int, number: int, content: str) -> dict[str, Any]:
    return {
        "sql_generation_guide_version_id": version_id,
        "sql_generation_guide_id": 101,
        "sql_generation_guide_version_number": number,
        "sql_generation_guide_content": content,
        "sql_generation_guide_digest": "b" * 64,
        "sql_generation_guide_version_status": "published",
        "published_at": NOW,
        "retired_at": None,
        "created_at": NOW,
        "updated_at": NOW,
    }


class GuideDetailTransaction:
    def __init__(self) -> None:
        self.calls: list[str] = []
        self.offsets: list[int] = []

    async def fetch_one(
        self,
        query: LiteralString,
        parameters: tuple[Any, ...] = (),
    ) -> dict[str, Any] | None:
        if "security.entra_principal_identity" in query:
            self.calls.append("authorize")
            assert parameters[-1] == 7
            return _authorization_row()
        self.calls.append("guide")
        assert "FROM application.sql_generation_guide AS guide" in query
        assert "sql_generation_guide_content" not in query
        assert parameters == (101,)
        return _guide_summary_row(101, "default_sql")

    async def fetch_all(
        self,
        query: LiteralString,
        parameters: tuple[Any, ...] = (),
    ) -> list[dict[str, Any]]:
        self.calls.append("versions")
        assert "sql_generation_guide_content" in query
        guide_id, limit, offset = parameters
        assert guide_id == 101
        assert limit == 2
        self.offsets.append(offset)
        rows = [
            _guide_version_row(1102, 2, "RAW_GUIDE_TWO"),
            _guide_version_row(1101, 1, "RAW_GUIDE_ONE"),
        ]
        return rows[offset : offset + limit]


class GuideDetailDatabase:
    def __init__(self) -> None:
        self.transaction = GuideDetailTransaction()

    @asynccontextmanager
    async def read_transaction(
        self,
        *,
        isolation: ReadIsolation = ReadIsolation.READ_COMMITTED,
    ) -> AsyncGenerator[GuideDetailTransaction]:
        assert isolation is ReadIsolation.REPEATABLE_READ
        yield self.transaction


@pytest.mark.asyncio
async def test_guide_detail_authorizes_before_bounded_content_history() -> None:
    database = GuideDetailDatabase()
    service = DatabaseSqlGenerationGuideService(
        database=cast(SqlGenerationGuideDatabase, database),
        authorizer=AuthorizationService(),
        cursor_signing_key=b"development-only-key-32-bytes-long",
    )

    first = await service.read_guide(
        PRINCIPAL,
        tenant_id=7,
        sql_generation_guide_id=101,
        history_page_size=1,
        history_cursor=None,
    )
    second = await service.read_guide(
        PRINCIPAL,
        tenant_id=7,
        sql_generation_guide_id=101,
        history_page_size=1,
        history_cursor=first.history_next_cursor,
    )

    assert first.versions[0].sql_generation_guide_content == "RAW_GUIDE_TWO"
    assert second.versions[0].sql_generation_guide_content == "RAW_GUIDE_ONE"
    assert second.history_next_cursor is None
    assert "RAW_GUIDE_TWO" not in repr(first)
    assert database.transaction.calls == [
        "authorize",
        "guide",
        "versions",
        "authorize",
        "guide",
        "versions",
    ]
    assert database.transaction.offsets == [0, 1]


class SaveDraftTransaction:
    def __init__(self, *, is_super_admin: bool = True) -> None:
        self.calls: list[str] = []
        self.is_super_admin = is_super_admin

    async def fetch_one(
        self,
        query: LiteralString,
        parameters: tuple[Any, ...] = (),
    ) -> dict[str, Any] | None:
        if "security.entra_principal_identity" in query:
            self.calls.append("authorize")
            assert parameters[-1] == 7
            return _authorization_row(is_super_admin=self.is_super_admin)
        if "FROM application.sql_generation_guide AS guide" in query:
            self.calls.append("guide")
            assert parameters == (101,)
            return {"sql_generation_guide_id": 101}
        self.calls.append("save_draft")
        assert "application.save_sql_generation_guide_draft" in query
        assert "INSERT INTO application.sql_generation_guide_version" not in query
        assert parameters == (
            PRINCIPAL.entra_tenant_id,
            PRINCIPAL.entra_object_id,
            "user",
            101,
            1101,
            "RAW_GUIDE_DRAFT",
            NOW,
        )
        return {
            "sql_generation_guide_version_id": 1101,
            "sql_generation_guide_id": 101,
            "sql_generation_guide_version_number": 2,
            "sql_generation_guide_digest": "c" * 64,
            "sql_generation_guide_version_status": "draft",
            "published_at": None,
            "retired_at": None,
            "created_at": NOW,
            "updated_at": NOW,
        }


class SaveDraftDatabase:
    def __init__(self, *, is_super_admin: bool = True) -> None:
        self.transaction = SaveDraftTransaction(is_super_admin=is_super_admin)

    @asynccontextmanager
    async def write_transaction(self) -> AsyncGenerator[SaveDraftTransaction]:
        yield self.transaction


@pytest.mark.asyncio
async def test_super_admin_saves_fenced_draft_through_governed_function() -> None:
    database = SaveDraftDatabase()
    service = DatabaseSqlGenerationGuideService(
        database=cast(SqlGenerationGuideDatabase, database),
        authorizer=AuthorizationService(),
        cursor_signing_key=b"development-only-key-32-bytes-long",
    )
    body = SaveSqlGenerationGuideDraftRequest(
        expected_sql_generation_guide_version_id=1101,
        expected_updated_at=NOW,
        sql_generation_guide_content="RAW_GUIDE_DRAFT",
    )

    saved = await service.save_draft(
        PRINCIPAL,
        tenant_id=7,
        sql_generation_guide_id=101,
        body=body,
    )

    assert saved.sql_generation_guide_version_status == "draft"
    assert "RAW_GUIDE_DRAFT" not in repr(body)
    assert "sql_generation_guide_content" not in saved.model_dump_json()
    assert database.transaction.calls == ["authorize", "guide", "save_draft"]


@pytest.mark.asyncio
async def test_guide_mutation_denies_non_super_admin_without_loading_guide() -> None:
    database = SaveDraftDatabase(is_super_admin=False)
    service = DatabaseSqlGenerationGuideService(
        database=cast(SqlGenerationGuideDatabase, database),
        authorizer=AuthorizationService(),
        cursor_signing_key=b"development-only-key-32-bytes-long",
    )

    with pytest.raises(AuthorizationDeniedError):
        await service.save_draft(
            PRINCIPAL,
            tenant_id=7,
            sql_generation_guide_id=101,
            body=SaveSqlGenerationGuideDraftRequest(
                sql_generation_guide_content="RAW_DENIED_GUIDE",
            ),
        )

    assert database.transaction.calls == ["authorize"]


class _FakeDiagnostic:
    message_primary = "stale_sql_generation_guide_draft RAW_GUIDE_SENTINEL"


class _FakeDatabaseError(Exception):
    diag = _FakeDiagnostic()


class StaleDraftTransaction(SaveDraftTransaction):
    async def fetch_one(
        self,
        query: LiteralString,
        parameters: tuple[Any, ...] = (),
    ) -> dict[str, Any] | None:
        if "application.save_sql_generation_guide_draft" in query:
            raise _FakeDatabaseError
        return await super().fetch_one(query, parameters)


class StaleDraftDatabase:
    @asynccontextmanager
    async def write_transaction(self) -> AsyncGenerator[StaleDraftTransaction]:
        try:
            yield StaleDraftTransaction()
        except _FakeDatabaseError as error:
            raise DependencyUnavailableError from error


@pytest.mark.asyncio
async def test_stale_draft_failure_is_sanitized_to_stable_conflict() -> None:
    service = DatabaseSqlGenerationGuideService(
        database=cast(SqlGenerationGuideDatabase, StaleDraftDatabase()),
        authorizer=AuthorizationService(),
        cursor_signing_key=b"development-only-key-32-bytes-long",
    )

    with pytest.raises(SqlGenerationGuideConflictError) as captured:
        await service.save_draft(
            PRINCIPAL,
            tenant_id=7,
            sql_generation_guide_id=101,
            body=SaveSqlGenerationGuideDraftRequest(
                expected_sql_generation_guide_version_id=1101,
                expected_updated_at=NOW,
                sql_generation_guide_content="RAW_GUIDE_SENTINEL",
            ),
        )

    assert captured.value.code == "sql_generation_guide_conflict"
    assert "RAW_GUIDE_SENTINEL" not in str(captured.value)
    assert "RAW_GUIDE_SENTINEL" not in repr(captured.value)


class TransitionVersionTransaction:
    def __init__(self, *, expected_status: str, target_status: str) -> None:
        self.expected_status = expected_status
        self.target_status = target_status
        self.calls: list[str] = []

    async def fetch_one(
        self,
        query: LiteralString,
        parameters: tuple[Any, ...] = (),
    ) -> dict[str, Any] | None:
        if "security.entra_principal_identity" in query:
            self.calls.append("authorize")
            return _authorization_row(is_super_admin=True)
        if "application.sql_generation_guide_version AS version" in query:
            self.calls.append("bind_version")
            assert parameters == (1101, 101)
            return {"sql_generation_guide_version_id": 1101}
        self.calls.append("transition")
        assert "application.transition_sql_generation_guide_version" in query
        assert parameters == (
            PRINCIPAL.entra_tenant_id,
            PRINCIPAL.entra_object_id,
            "user",
            1101,
            self.expected_status,
            self.target_status,
        )
        return {
            "sql_generation_guide_version_id": 1101,
            "sql_generation_guide_id": 101,
            "sql_generation_guide_version_number": 2,
            "sql_generation_guide_digest": "c" * 64,
            "sql_generation_guide_version_status": self.target_status,
            "published_at": NOW,
            "retired_at": NOW if self.target_status == "retired" else None,
            "created_at": NOW,
            "updated_at": NOW,
        }


class TransitionVersionDatabase:
    def __init__(self, *, expected_status: str, target_status: str) -> None:
        self.transaction = TransitionVersionTransaction(
            expected_status=expected_status,
            target_status=target_status,
        )

    @asynccontextmanager
    async def write_transaction(self) -> AsyncGenerator[TransitionVersionTransaction]:
        yield self.transaction


@pytest.mark.asyncio
async def test_super_admin_publishes_path_bound_draft_through_governed_function() -> None:
    database = TransitionVersionDatabase(
        expected_status="draft",
        target_status="published",
    )
    service = DatabaseSqlGenerationGuideService(
        database=cast(SqlGenerationGuideDatabase, database),
        authorizer=AuthorizationService(),
        cursor_signing_key=b"development-only-key-32-bytes-long",
    )

    published = await service.publish_version(
        PRINCIPAL,
        tenant_id=7,
        sql_generation_guide_id=101,
        sql_generation_guide_version_id=1101,
    )

    assert published.sql_generation_guide_version_status == "published"
    assert database.transaction.calls == ["authorize", "bind_version", "transition"]


@pytest.mark.asyncio
async def test_super_admin_retires_path_bound_published_version() -> None:
    database = TransitionVersionDatabase(
        expected_status="published",
        target_status="retired",
    )
    service = DatabaseSqlGenerationGuideService(
        database=cast(SqlGenerationGuideDatabase, database),
        authorizer=AuthorizationService(),
        cursor_signing_key=b"development-only-key-32-bytes-long",
    )

    retired = await service.retire_version(
        PRINCIPAL,
        tenant_id=7,
        sql_generation_guide_id=101,
        sql_generation_guide_version_id=1101,
    )

    assert retired.sql_generation_guide_version_status == "retired"
    assert retired.retired_at == NOW
    assert database.transaction.calls == ["authorize", "bind_version", "transition"]


class GuideRouterService:
    async def list_guides(
        self,
        principal: RequestPrincipal,
        *,
        tenant_id: int,
        page_size: int,
        cursor: str | None,
    ) -> SqlGenerationGuidePage:
        assert principal.actor_kind is ActorKind.HUMAN
        assert (tenant_id, page_size, cursor) == (7, 1, None)
        return SqlGenerationGuidePage(
            tenant_id=tenant_id,
            items=(
                SqlGenerationGuideSummary.model_validate(_guide_summary_row(101, "default_sql")),
            ),
            next_cursor=None,
        )


def test_authenticated_router_exposes_only_bounded_guide_management_routes() -> None:
    router = create_sql_generation_guides_router(
        identity_provider=IdentityProvider(
            AuthMode.DEV,
            local_tenant_id=PRINCIPAL.entra_tenant_id,
            local_principal_object_id=PRINCIPAL.entra_object_id,
        ),
        service=cast(SqlGenerationGuideService, GuideRouterService()),
    )
    api_routes = [route for route in router.routes if isinstance(route, APIRoute)]
    route_methods: set[tuple[str, str]] = set()
    for route in api_routes:
        assert route.methods is not None
        route_methods.update((route.path, method) for method in route.methods)
    base = "/api/v1/tenants/{tenant_id}/sql-generation-guides"
    assert route_methods == {
        (base, "GET"),
        (f"{base}/{{sql_generation_guide_id}}", "GET"),
        (f"{base}/{{sql_generation_guide_id}}/draft", "PUT"),
        (
            f"{base}/{{sql_generation_guide_id}}/versions/"
            "{sql_generation_guide_version_id}/publish",
            "POST",
        ),
        (
            f"{base}/{{sql_generation_guide_id}}/versions/"
            "{sql_generation_guide_version_id}/retire",
            "POST",
        ),
    }
    app = FastAPI()
    app.include_router(router)

    with TestClient(app) as client:
        response = client.get(
            "/api/v1/tenants/7/sql-generation-guides",
            params={"page_size": 1},
        )
        rejected = client.get(
            "/api/v1/tenants/7/sql-generation-guides",
            params={"page_size": 201},
        )

    assert response.status_code == 200
    assert response.json()["items"][0]["sql_generation_guide_code"] == "default_sql"
    assert rejected.status_code == 422
