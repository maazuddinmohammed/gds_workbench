from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from typing import Any, LiteralString, cast
from uuid import UUID

import pytest
from fastapi.testclient import TestClient
from gds_etl_workbench.adapters.auth.identity import IdentityProvider
from gds_etl_workbench.application.authorization import AuthorizationService
from gds_etl_workbench.configuration import AuthMode
from gds_etl_workbench.domain.authorization import ActorKind, RequestPrincipal
from gds_etl_workbench.domain.errors import InvalidRequestError
from psycopg.types.json import Jsonb

from gds_workbench_api.capabilities import load_default_agent_capabilities
from gds_workbench_api.configuration import RuntimeSettings
from gds_workbench_api.features.models import (
    ArchiveModelRequest,
    CompleteModelRequest,
    DatabaseModelCommandService,
    ModelCommandResult,
    ModelNotFoundError,
    UpdateModelRequest,
)
from gds_workbench_api.main import create_app
from gds_workbench_api.runtime import RuntimeDatabase, create_runtime_app


class StaticModelCommandService:
    async def create_model(
        self,
        principal: RequestPrincipal,
        *,
        tenant_id: int,
        request: CompleteModelRequest,
    ) -> ModelCommandResult:
        assert principal.actor_kind is ActorKind.HUMAN
        assert tenant_id == 7
        assert request.model_name == "Customer 360"
        assert request.silver_model_audit_columns_template == {
            "columns": [{"name": "created_at", "type": "timestamp"}]
        }
        assert request.default_agent_model_code == "databricks-primary"
        return ModelCommandResult(
            model_id=18,
            tenant_id=7,
            model_revision=1,
            is_active=True,
            updated_at=datetime(2026, 8, 24, 14, 0, tzinfo=UTC),
        )

    async def update_model(
        self,
        principal: RequestPrincipal,
        *,
        tenant_id: int,
        model_id: int,
        request: UpdateModelRequest,
    ) -> ModelCommandResult:
        assert principal.actor_kind is ActorKind.HUMAN
        assert (tenant_id, model_id, request.expected_model_revision) == (7, 18, 4)
        assert request.model_name == "Customer 360"
        return ModelCommandResult(
            model_id=18,
            tenant_id=7,
            model_revision=5,
            is_active=True,
            updated_at=datetime(2026, 8, 24, 14, 5, tzinfo=UTC),
        )

    async def archive_model(
        self,
        principal: RequestPrincipal,
        *,
        tenant_id: int,
        model_id: int,
        request: ArchiveModelRequest,
    ) -> ModelCommandResult:
        assert principal.actor_kind is ActorKind.HUMAN
        assert (tenant_id, model_id, request.expected_model_revision) == (7, 18, 5)
        return ModelCommandResult(
            model_id=18,
            tenant_id=7,
            model_revision=6,
            is_active=False,
            updated_at=datetime(2026, 8, 24, 14, 10, tzinfo=UTC),
        )


def _identity_provider() -> IdentityProvider:
    return IdentityProvider(
        AuthMode.DEV,
        local_tenant_id=UUID("11111111-1111-1111-1111-111111111111"),
        local_principal_object_id=UUID("22222222-2222-2222-2222-222222222222"),
    )


def _complete_model_payload() -> dict[str, object]:
    return {
        "model_name": "Customer 360",
        "model_description": "Cross-system customer domain",
        "silver_model_naming_instructions": "Use snake case.",
        "silver_model_audit_columns_template": {
            "columns": [{"name": "created_at", "type": "timestamp"}]
        },
        "gold_model_naming_instructions": "Use business names.",
        "gold_model_technical_columns_template": {
            "columns": [{"name": "customer_key", "type": "bigint"}]
        },
        "gold_model_audit_columns_template": {
            "columns": [{"name": "updated_at", "type": "timestamp"}]
        },
        "default_agent_sdk_code": "langchain_create_agent",
        "default_agent_provider_code": "databricks",
        "default_agent_model_code": "databricks-primary",
        "default_reasoning_effort_code": "medium",
        "default_max_turns": 10,
        "default_validation_retry_count": 2,
    }


def test_create_model_route_accepts_one_complete_server_identity_command() -> None:
    app = create_app(
        identity_provider=_identity_provider(),
        model_command_service=StaticModelCommandService(),
    )

    with TestClient(app) as client:
        response = client.post(
            "/api/v1/tenants/7/models",
            json=_complete_model_payload(),
        )

    assert response.status_code == 201
    assert response.json() == {
        "model_id": 18,
        "tenant_id": 7,
        "model_revision": 1,
        "is_active": True,
        "updated_at": "2026-08-24T14:00:00Z",
    }


def test_update_model_route_requires_complete_replacement_and_revision() -> None:
    app = create_app(
        identity_provider=_identity_provider(),
        model_command_service=StaticModelCommandService(),
    )
    payload = _complete_model_payload() | {"expected_model_revision": 4}

    with TestClient(app) as client:
        response = client.put("/api/v1/tenants/7/models/18", json=payload)

    assert response.status_code == 200
    assert response.json()["model_revision"] == 5


def test_archive_model_route_is_explicit_and_revision_fenced() -> None:
    app = create_app(
        identity_provider=_identity_provider(),
        model_command_service=StaticModelCommandService(),
    )

    with TestClient(app) as client:
        response = client.post(
            "/api/v1/tenants/7/models/18/archive",
            json={"expected_model_revision": 5},
        )

    assert response.status_code == 200
    assert response.json()["is_active"] is False


class CreateModelTransaction:
    def __init__(self) -> None:
        self.create_parameters: tuple[Any, ...] | None = None

    async def fetch_one(
        self,
        query: LiteralString,
        parameters: tuple[Any, ...] = (),
    ) -> dict[str, Any] | None:
        if "security.authorize_tenant_operation" in query:
            assert parameters == (
                UUID("11111111-1111-1111-1111-111111111111"),
                UUID("22222222-2222-2222-2222-222222222222"),
                "user",
                7,
                "tenant_model_write",
            )
            return {
                "principal_id": 41,
                "principal_display_name": "Maaz",
                "is_super_admin": False,
                "effective_role": "tenant_admin",
                "authorized": True,
                "denial_code": None,
                "lock_owner_display_name": None,
                "lock_expires_time": datetime(2026, 8, 24, 15, 0, tzinfo=UTC),
            }
        assert "application.create_model" in query
        self.create_parameters = parameters
        return {
            "model_id": 18,
            "tenant_id": 7,
            "model_revision": 1,
            "is_active": True,
            "updated_at": datetime(2026, 8, 24, 14, 0, tzinfo=UTC),
        }

    async def fetch_all(
        self,
        query: LiteralString,
        parameters: tuple[Any, ...] = (),
    ) -> list[dict[str, Any]]:
        raise AssertionError((query, parameters))


class CreateModelDatabase:
    def __init__(self) -> None:
        self.transaction = CreateModelTransaction()

    @asynccontextmanager
    async def write_transaction(self) -> AsyncGenerator[CreateModelTransaction]:
        yield self.transaction


@pytest.mark.asyncio
async def test_database_create_model_authorizes_lock_and_passes_full_identity_command() -> None:
    database = CreateModelDatabase()
    service = DatabaseModelCommandService(
        database=database,
        authorizer=AuthorizationService(),
        agent_capability_registry=load_default_agent_capabilities(),
    )
    request = CompleteModelRequest.model_validate(_complete_model_payload())
    principal = RequestPrincipal(
        actor_kind=ActorKind.HUMAN,
        entra_tenant_id=UUID("11111111-1111-1111-1111-111111111111"),
        entra_object_id=UUID("22222222-2222-2222-2222-222222222222"),
    )

    created = await service.create_model(principal, tenant_id=7, request=request)

    assert created.model_id == 18
    parameters = database.transaction.create_parameters
    assert parameters is not None
    assert parameters[:7] == (
        principal.entra_tenant_id,
        principal.entra_object_id,
        "user",
        7,
        "Customer 360",
        "Cross-system customer domain",
        "Use snake case.",
    )
    assert isinstance(parameters[7], Jsonb)
    assert parameters[7].obj == request.silver_model_audit_columns_template
    assert parameters[8] == "Use business names."
    assert isinstance(parameters[9], Jsonb)
    assert isinstance(parameters[10], Jsonb)
    assert parameters[11:] == (
        "langchain_create_agent",
        "databricks",
        "databricks-primary",
        "medium",
        10,
        2,
    )


class RevisionCommandTransaction:
    def __init__(self) -> None:
        self.function_calls: list[tuple[str, tuple[Any, ...]]] = []
        self.owner_checks: list[tuple[Any, ...]] = []

    async def fetch_one(
        self,
        query: LiteralString,
        parameters: tuple[Any, ...] = (),
    ) -> dict[str, Any] | None:
        if "security.authorize_tenant_operation" in query:
            assert parameters[3:] == (7, "tenant_model_write")
            return {
                "principal_id": 41,
                "principal_display_name": "Maaz",
                "is_super_admin": False,
                "effective_role": "tenant_admin",
                "authorized": True,
                "denial_code": None,
                "lock_owner_display_name": None,
                "lock_expires_time": datetime(2026, 8, 24, 15, 0, tzinfo=UTC),
            }
        if "FROM model.model AS target_model" in query:
            self.owner_checks.append(parameters)
            return {"model_revision": 4}
        if "application.update_model" in query:
            self.function_calls.append(("update", parameters))
            return {
                "model_id": 18,
                "tenant_id": 7,
                "model_revision": 5,
                "is_active": True,
                "updated_at": datetime(2026, 8, 24, 14, 5, tzinfo=UTC),
            }
        if "application.archive_model" in query:
            self.function_calls.append(("archive", parameters))
            return {
                "model_id": 18,
                "tenant_id": 7,
                "model_revision": 6,
                "is_active": False,
                "updated_at": datetime(2026, 8, 24, 14, 10, tzinfo=UTC),
            }
        raise AssertionError((query, parameters))

    async def fetch_all(
        self,
        query: LiteralString,
        parameters: tuple[Any, ...] = (),
    ) -> list[dict[str, Any]]:
        raise AssertionError((query, parameters))


class RevisionCommandDatabase:
    def __init__(self) -> None:
        self.transaction = RevisionCommandTransaction()

    @asynccontextmanager
    async def write_transaction(self) -> AsyncGenerator[RevisionCommandTransaction]:
        yield self.transaction


@pytest.mark.asyncio
async def test_revision_commands_precheck_path_tenant_and_call_only_governed_functions() -> None:
    database = RevisionCommandDatabase()
    service = DatabaseModelCommandService(
        database=database,
        authorizer=AuthorizationService(),
        agent_capability_registry=load_default_agent_capabilities(),
    )
    principal = RequestPrincipal(
        actor_kind=ActorKind.HUMAN,
        entra_tenant_id=UUID("11111111-1111-1111-1111-111111111111"),
        entra_object_id=UUID("22222222-2222-2222-2222-222222222222"),
    )

    updated = await service.update_model(
        principal,
        tenant_id=7,
        model_id=18,
        request=UpdateModelRequest.model_validate(
            _complete_model_payload() | {"expected_model_revision": 4}
        ),
    )
    archived = await service.archive_model(
        principal,
        tenant_id=7,
        model_id=18,
        request=ArchiveModelRequest(expected_model_revision=5),
    )
    assert (updated.model_revision, archived.model_revision) == (5, 6)
    assert database.transaction.owner_checks == [(7, 18), (7, 18)]
    identity = (
        principal.entra_tenant_id,
        principal.entra_object_id,
        "user",
    )
    update_call, archive_call = database.transaction.function_calls
    assert update_call[0] == "update"
    assert update_call[1][:5] == identity + (18, 4)
    assert update_call[1][5:11] == (
        "Customer 360",
        "Cross-system customer domain",
        "Use snake case.",
        update_call[1][8],
        "Use business names.",
        update_call[1][10],
    )
    assert isinstance(update_call[1][8], Jsonb)
    assert isinstance(update_call[1][10], Jsonb)
    assert isinstance(update_call[1][11], Jsonb)
    assert update_call[1][12:] == (
        "langchain_create_agent",
        "databricks",
        "databricks-primary",
        "medium",
        10,
        2,
    )
    assert archive_call == ("archive", identity + (18, 5))


@pytest.mark.parametrize(
    "extra_values",
    [
        {"entra_tenant_id": "11111111-1111-1111-1111-111111111111"},
        {"silver_model_naming_instructions": "   "},
        {"default_agent_sdk_code": ""},
        {"silver_model_audit_columns_template": {"value": "x" * (32 * 1024)}},
        {
            "default_agent_provider_code": None,
            "default_agent_model_code": None,
            "default_reasoning_effort_code": None,
            "default_max_turns": None,
            "default_validation_retry_count": None,
        },
    ],
)
def test_model_commands_reject_identity_injection_and_partial_agent_defaults(
    extra_values: dict[str, object],
) -> None:
    app = create_app(
        identity_provider=_identity_provider(),
        model_command_service=StaticModelCommandService(),
    )

    with TestClient(app) as client:
        response = client.post(
            "/api/v1/tenants/7/models",
            json=_complete_model_payload() | extra_values,
        )

    assert response.status_code == 422


class NoWriteDatabase:
    def __init__(self) -> None:
        self.entered = False

    @asynccontextmanager
    async def write_transaction(self) -> AsyncGenerator[RevisionCommandTransaction]:
        self.entered = True
        yield RevisionCommandTransaction()


@pytest.mark.asyncio
async def test_agent_registry_rejects_incompatible_defaults_before_database_access() -> None:
    database = NoWriteDatabase()
    service = DatabaseModelCommandService(
        database=database,
        authorizer=AuthorizationService(),
        agent_capability_registry=load_default_agent_capabilities(),
    )
    incompatible = _complete_model_payload() | {"default_agent_model_code": "unavailable-model"}
    principal = RequestPrincipal(
        actor_kind=ActorKind.HUMAN,
        entra_tenant_id=UUID("11111111-1111-1111-1111-111111111111"),
        entra_object_id=UUID("22222222-2222-2222-2222-222222222222"),
    )

    with pytest.raises(InvalidRequestError):
        await service.create_model(
            principal,
            tenant_id=7,
            request=CompleteModelRequest.model_validate(incompatible),
        )

    assert database.entered is False


class FailingFunctionTransaction:
    def __init__(self, message: str) -> None:
        self.message = message

    async def fetch_one(
        self,
        query: LiteralString,
        parameters: tuple[Any, ...] = (),
    ) -> dict[str, Any] | None:
        if "security.authorize_tenant_operation" in query:
            return {
                "principal_id": 41,
                "principal_display_name": "Maaz",
                "is_super_admin": False,
                "effective_role": "tenant_admin",
                "authorized": True,
                "denial_code": None,
                "lock_owner_display_name": None,
                "lock_expires_time": datetime(2026, 8, 24, 15, 0, tzinfo=UTC),
            }
        if "FROM model.model AS target_model" in query:
            assert parameters == (7, 18)
            return {"model_revision": 4}
        raise RuntimeError(self.message)

    async def fetch_all(
        self,
        query: LiteralString,
        parameters: tuple[Any, ...] = (),
    ) -> list[dict[str, Any]]:
        raise AssertionError((query, parameters))


class FailingFunctionDatabase:
    def __init__(self, message: str) -> None:
        self.transaction = FailingFunctionTransaction(message)

    @asynccontextmanager
    async def write_transaction(self) -> AsyncGenerator[FailingFunctionTransaction]:
        yield self.transaction


@pytest.mark.parametrize(
    ("database_message", "expected_status", "expected_code"),
    [
        ("stale_model_revision", 409, "model_revision_conflict"),
        ("Model is unavailable", 404, "model_not_found"),
        ("Model update denied: tenant_lock_required", 409, "tenant_lock_required"),
        ("Model update denied: authorization_denied", 403, "authorization_denied"),
        ("database password=secret-value", 503, "dependency_unavailable"),
    ],
)
def test_database_model_failures_are_mapped_without_raw_message_disclosure(
    database_message: str,
    expected_status: int,
    expected_code: str,
) -> None:
    service = DatabaseModelCommandService(
        database=FailingFunctionDatabase(database_message),
        authorizer=AuthorizationService(),
        agent_capability_registry=load_default_agent_capabilities(),
    )
    app = create_app(
        identity_provider=_identity_provider(),
        model_command_service=service,
    )

    with TestClient(app, raise_server_exceptions=False) as client:
        response = client.put(
            "/api/v1/tenants/7/models/18",
            json=_complete_model_payload() | {"expected_model_revision": 4},
        )

    assert response.status_code == expected_status
    assert response.json()["error"]["code"] == expected_code
    assert database_message not in response.text


class RejectedPrecheckTransaction:
    def __init__(self, *, authorized: bool) -> None:
        self.authorized = authorized
        self.model_owner_checked = False
        self.function_called = False

    async def fetch_one(
        self,
        query: LiteralString,
        parameters: tuple[Any, ...] = (),
    ) -> dict[str, Any] | None:
        if "security.authorize_tenant_operation" in query:
            return {
                "principal_id": 41,
                "principal_display_name": "Maaz",
                "is_super_admin": False,
                "effective_role": "tenant_admin",
                "authorized": self.authorized,
                "denial_code": None if self.authorized else "tenant_locked",
                "lock_owner_display_name": "Other Architect",
                "lock_expires_time": datetime(2026, 8, 24, 15, 0, tzinfo=UTC),
            }
        if "FROM model.model AS target_model" in query:
            assert parameters == (7, 18)
            self.model_owner_checked = True
            return None
        self.function_called = True
        raise AssertionError("a rejected precheck must not call a Model function")

    async def fetch_all(
        self,
        query: LiteralString,
        parameters: tuple[Any, ...] = (),
    ) -> list[dict[str, Any]]:
        raise AssertionError((query, parameters))


class RejectedPrecheckDatabase:
    def __init__(self, *, authorized: bool) -> None:
        self.transaction = RejectedPrecheckTransaction(authorized=authorized)

    @asynccontextmanager
    async def write_transaction(self) -> AsyncGenerator[RejectedPrecheckTransaction]:
        yield self.transaction


@pytest.mark.asyncio
async def test_cross_tenant_model_id_is_not_found_before_canonical_mutation() -> None:
    database = RejectedPrecheckDatabase(authorized=True)
    service = DatabaseModelCommandService(
        database=database,
        authorizer=AuthorizationService(),
        agent_capability_registry=load_default_agent_capabilities(),
    )
    principal = RequestPrincipal(
        actor_kind=ActorKind.HUMAN,
        entra_tenant_id=UUID("11111111-1111-1111-1111-111111111111"),
        entra_object_id=UUID("22222222-2222-2222-2222-222222222222"),
    )

    with pytest.raises(ModelNotFoundError):
        await service.archive_model(
            principal,
            tenant_id=7,
            model_id=18,
            request=ArchiveModelRequest(expected_model_revision=5),
        )

    assert database.transaction.model_owner_checked is True
    assert database.transaction.function_called is False


def test_owned_tenant_lock_is_required_before_model_lookup_or_mutation() -> None:
    database = RejectedPrecheckDatabase(authorized=False)
    service = DatabaseModelCommandService(
        database=database,
        authorizer=AuthorizationService(),
        agent_capability_registry=load_default_agent_capabilities(),
    )
    app = create_app(
        identity_provider=_identity_provider(),
        model_command_service=service,
    )

    with TestClient(app) as client:
        response = client.post(
            "/api/v1/tenants/7/models/18/archive",
            json={"expected_model_revision": 5},
        )

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "tenant_locked"
    assert database.transaction.model_owner_checked is False
    assert database.transaction.function_called is False


def test_runtime_wires_all_complete_model_command_routes() -> None:
    settings = RuntimeSettings.from_environment(
        {
            "GDS_WEB_ENVIRONMENT": "local",
            "GDS_WEB_DATABASE_DSN": "postgresql://fixture.invalid/workbench",
            "GDS_WEB_CURSOR_SIGNING_KEY": "development-only-key-32-bytes-long",
            "GDS_WEB_DATABRICKS_ENVIRONMENT_CODE": "TEST",
            "GDS_WEB_LOCAL_ENTRA_TENANT_ID": ("11111111-1111-1111-1111-111111111111"),
            "GDS_WEB_LOCAL_PRINCIPAL_OBJECT_ID": ("22222222-2222-2222-2222-222222222222"),
        }
    )
    app = create_runtime_app(
        settings=settings,
        database=cast(RuntimeDatabase, NoWriteDatabase()),
    )

    paths = app.openapi()["paths"]
    assert "post" in paths["/api/v1/tenants/{tenant_id}/models"]
    assert "put" in paths["/api/v1/tenants/{tenant_id}/models/{model_id}"]
    assert "post" in paths["/api/v1/tenants/{tenant_id}/models/{model_id}/archive"]
    assert "put" not in paths["/api/v1/tenants/{tenant_id}/models/{model_id}/input-scope"]
