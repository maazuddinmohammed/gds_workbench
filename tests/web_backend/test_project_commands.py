from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from types import SimpleNamespace
from typing import Any, LiteralString, cast
from uuid import UUID

import pytest
from fastapi.testclient import TestClient
from gds_etl_workbench.adapters.auth.identity import IdentityProvider
from gds_etl_workbench.application.authorization import AuthorizationService
from gds_etl_workbench.configuration import AuthMode
from gds_etl_workbench.domain.authorization import ActorKind, RequestPrincipal
from gds_etl_workbench.domain.errors import InvalidRequestError
from gds_workbench_api.capabilities import load_default_agent_capabilities
from gds_workbench_api.configuration import RuntimeSettings
from gds_workbench_api.features.projects import (
    ArchiveProjectRequest,
    CompleteProjectRequest,
    DatabaseProjectCommandService,
    ProjectCommandResult,
    ProjectNotFoundError,
    UpdateProjectRequest,
)
from gds_workbench_api.main import create_app
from gds_workbench_api.runtime import RuntimeDatabase, create_runtime_app
from psycopg.types.json import Jsonb


class StaticProjectCommandService:
    async def set_project_lock(
        self,
        principal: RequestPrincipal,
        *,
        tenant_id: int,
        project_id: int,
        request: Any,
    ) -> ProjectCommandResult:
        assert principal.actor_kind is ActorKind.HUMAN
        assert (tenant_id, project_id, request.expected_project_revision) == (7, 18, 4)
        return ProjectCommandResult(
            project_id=18,
            tenant_id=7,
            project_revision=5,
            is_active=True,
            updated_at=datetime(2026, 8, 24, 14, 5, tzinfo=UTC),
        )

    async def create_project(
        self,
        principal: RequestPrincipal,
        *,
        tenant_id: int,
        request: CompleteProjectRequest,
    ) -> ProjectCommandResult:
        assert principal.actor_kind is ActorKind.HUMAN
        assert tenant_id == 7
        assert request.project_name == "Customer 360"
        assert request.silver_model_audit_columns_template == {
            "columns": [{"name": "created_at", "type": "timestamp"}]
        }
        assert request.default_agent_model_code == "foundry-primary"
        return ProjectCommandResult(
            project_id=18,
            tenant_id=7,
            project_revision=1,
            is_active=True,
            updated_at=datetime(2026, 8, 24, 14, 0, tzinfo=UTC),
        )

    async def update_project(
        self,
        principal: RequestPrincipal,
        *,
        tenant_id: int,
        project_id: int,
        request: UpdateProjectRequest,
    ) -> ProjectCommandResult:
        assert principal.actor_kind is ActorKind.HUMAN
        assert (tenant_id, project_id, request.expected_project_revision) == (7, 18, 4)
        assert request.project_name == "Customer 360"
        return ProjectCommandResult(
            project_id=18,
            tenant_id=7,
            project_revision=5,
            is_active=True,
            updated_at=datetime(2026, 8, 24, 14, 5, tzinfo=UTC),
        )

    async def archive_project(
        self,
        principal: RequestPrincipal,
        *,
        tenant_id: int,
        project_id: int,
        request: ArchiveProjectRequest,
    ) -> ProjectCommandResult:
        assert principal.actor_kind is ActorKind.HUMAN
        assert (tenant_id, project_id, request.expected_project_revision) == (7, 18, 5)
        return ProjectCommandResult(
            project_id=18,
            tenant_id=7,
            project_revision=6,
            is_active=False,
            updated_at=datetime(2026, 8, 24, 14, 10, tzinfo=UTC),
        )


def _identity_provider() -> IdentityProvider:
    return IdentityProvider(
        AuthMode.DEV,
        local_tenant_id=UUID("11111111-1111-1111-1111-111111111111"),
        local_principal_object_id=UUID("22222222-2222-2222-2222-222222222222"),
    )


def _complete_project_payload() -> dict[str, object]:
    return {
        "project_name": "Customer 360",
        "project_description": "Cross-system customer domain",
        "logical_schemas": [
            {"schema_name": "silver", "description": "Operational entities"}
        ],
        "dimensional_schemas": [{"schema_name": "gold", "description": None}],
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
        "default_agent_sdk_code": "openai_agents_sdk",
        "default_agent_provider_code": "microsoft_foundry",
        "default_agent_model_code": "foundry-primary",
        "default_reasoning_effort_code": "medium",
        "default_max_turns": 10,
        "default_validation_retry_count": 2,
        "default_mapping_source_system_id": 32,
        "logical_entity_scd_type": "type_2",
        "dimensional_entity_scd_type": "type_1",
    }


def test_create_project_route_accepts_one_complete_server_identity_command() -> None:
    app = create_app(
        identity_provider=_identity_provider(),
        project_command_service=StaticProjectCommandService(),
    )

    with TestClient(app) as client:
        response = client.post(
            "/api/v1/tenants/7/projects",
            json=_complete_project_payload(),
        )

    assert response.status_code == 201
    assert response.json() == {
        "project_id": 18,
        "tenant_id": 7,
        "project_revision": 1,
        "is_active": True,
        "updated_at": "2026-08-24T14:00:00Z",
    }


def test_update_project_route_requires_complete_replacement_and_revision() -> None:
    app = create_app(
        identity_provider=_identity_provider(),
        project_command_service=StaticProjectCommandService(),
    )
    payload = _complete_project_payload() | {"expected_project_revision": 4}

    with TestClient(app) as client:
        response = client.put("/api/v1/tenants/7/projects/18", json=payload)

    assert response.status_code == 200
    assert response.json()["project_revision"] == 5


def test_archive_project_route_is_explicit_and_revision_fenced() -> None:
    app = create_app(
        identity_provider=_identity_provider(),
        project_command_service=StaticProjectCommandService(),
    )

    with TestClient(app) as client:
        response = client.post(
            "/api/v1/tenants/7/projects/18/archive",
            json={"expected_project_revision": 5},
        )

    assert response.status_code == 200
    assert response.json()["is_active"] is False


class CreateProjectTransaction:
    def __init__(self, role: str = "tenant_admin") -> None:
        self.role = role
        self.create_parameters: tuple[Any, ...] | None = None

    async def fetch_one(
        self,
        query: LiteralString,
        parameters: tuple[Any, ...] = (),
    ) -> dict[str, Any] | None:
        if "project.assert_writable" in query:
            return {"assert_writable": None}
        if "security.authorize_tenant_operation" in query:
            assert parameters == (
                UUID("11111111-1111-1111-1111-111111111111"),
                UUID("22222222-2222-2222-2222-222222222222"),
                "user",
                7,
                "tenant_project_write",
            )
            return {
                "principal_id": 41,
                "principal_display_name": "Maaz",
                "is_super_admin": self.role == "super_admin",
                "effective_role": self.role,
                "authorized": True,
                "denial_code": None,
                "lock_owner_display_name": None,
                "lock_expires_time": datetime(2026, 8, 24, 15, 0, tzinfo=UTC),
            }
        assert "application.create_project" in query
        assert query.count("%s") == len(parameters)
        self.create_parameters = parameters
        return {
            "project_id": 18,
            "tenant_id": 7,
            "project_revision": 1,
            "is_active": True,
            "updated_at": datetime(2026, 8, 24, 14, 0, tzinfo=UTC),
        }

    async def fetch_all(
        self,
        query: LiteralString,
        parameters: tuple[Any, ...] = (),
    ) -> list[dict[str, Any]]:
        # No retained cross-Tenant scope in this isolated service fixture.
        if "SELECT DISTINCT object.source_tenant_id" in query:
            return []
        if "core.tenant AS tenant" in query and "effective_role" in query:
            return []
        raise AssertionError((query, parameters))


class CreateProjectDatabase:
    def __init__(self, role: str = "tenant_admin") -> None:
        self.transaction = CreateProjectTransaction(role)

    @asynccontextmanager
    async def write_transaction(self) -> AsyncGenerator[CreateProjectTransaction]:
        yield self.transaction


@pytest.mark.parametrize(
    "role", ["viewer", "developer", "architect", "tenant_admin", "super_admin"]
)
def test_project_creation_is_admin_only_even_when_project_write_policy_allows_it(
    role: str,
) -> None:
    database = CreateProjectDatabase(role)
    app = create_app(
        identity_provider=_identity_provider(),
        project_command_service=DatabaseProjectCommandService(
            database=database,
            authorizer=AuthorizationService(),
            agent_capability_registry=load_default_agent_capabilities(),
        ),
    )
    with TestClient(app) as client:
        response = client.post(
            "/api/v1/tenants/7/projects", json={"project_name": "New Project"}
        )
    allowed = role in {"tenant_admin", "super_admin"}
    assert response.status_code == (201 if allowed else 403)
    assert (database.transaction.create_parameters is not None) is allowed


@pytest.mark.parametrize(
    "constraint", ["ux_project_tenant_name_ci", "other_private_constraint"]
)
def test_project_creation_duplicate_name_is_safe_and_distinct_from_other_database_errors(
    constraint: str,
) -> None:
    class UniqueFailureError(Exception):
        sqlstate = "23505"
        diag = SimpleNamespace(constraint_name=constraint)

    class DuplicateTransaction(CreateProjectTransaction):
        async def fetch_one(
            self, query: LiteralString, parameters: tuple[Any, ...] = ()
        ) -> dict[str, Any] | None:
            if "project.assert_writable" in query:
                return {"assert_writable": None}
            if "application.create_project" in query:
                try:
                    raise UniqueFailureError("private database details")
                except UniqueFailureError as error:
                    from gds_etl_workbench.domain.errors import (
                        DependencyUnavailableError,
                    )

                    raise DependencyUnavailableError() from error
            return await super().fetch_one(query, parameters)

    database = CreateProjectDatabase()
    database.transaction = DuplicateTransaction()
    app = create_app(
        identity_provider=_identity_provider(),
        project_command_service=DatabaseProjectCommandService(
            database=database,
            authorizer=AuthorizationService(),
            agent_capability_registry=load_default_agent_capabilities(),
        ),
    )
    with TestClient(app) as client:
        response = client.post(
            "/api/v1/tenants/7/projects", json={"project_name": "New Project"}
        )
    assert response.status_code == (
        409 if constraint == "ux_project_tenant_name_ci" else 503
    )
    assert response.json()["error"]["code"] == (
        "project_name_conflict"
        if constraint == "ux_project_tenant_name_ci"
        else "dependency_unavailable"
    )
    assert "private" not in response.text


@pytest.mark.asyncio
async def test_database_create_project_authorizes_lock_and_passes_full_identity_command() -> (
    None
):
    database = CreateProjectDatabase()
    service = DatabaseProjectCommandService(
        database=database,
        authorizer=AuthorizationService(),
        agent_capability_registry=load_default_agent_capabilities(),
    )
    request = CompleteProjectRequest.model_validate(_complete_project_payload())
    principal = RequestPrincipal(
        actor_kind=ActorKind.HUMAN,
        entra_tenant_id=UUID("11111111-1111-1111-1111-111111111111"),
        entra_object_id=UUID("22222222-2222-2222-2222-222222222222"),
    )

    created = await service.create_project(principal, tenant_id=7, request=request)

    assert created.project_id == 18
    parameters = database.transaction.create_parameters
    assert parameters is not None
    assert parameters[:6] == (
        principal.entra_tenant_id,
        principal.entra_object_id,
        "user",
        7,
        "Customer 360",
        "Cross-system customer domain",
    )
    assert isinstance(parameters[6], Jsonb)
    assert parameters[6].obj == _complete_project_payload()["logical_schemas"]
    assert isinstance(parameters[7], Jsonb)
    assert parameters[7].obj == _complete_project_payload()["dimensional_schemas"]
    assert parameters[8] == "Use snake case."
    assert isinstance(parameters[9], Jsonb)
    assert parameters[9].obj == request.silver_model_audit_columns_template
    assert parameters[10] == "Use business names."
    assert isinstance(parameters[11], Jsonb)
    assert isinstance(parameters[12], Jsonb)
    assert parameters[13:] == (
        "openai_agents_sdk",
        "microsoft_foundry",
        "foundry-primary",
        "medium",
        10,
        2,
        32,
        "type_2",
        "type_1",
        None,
        None,
        False,
        False,
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
        if "project.assert_writable" in query:
            return {"assert_writable": None}
        if "security.authorize_tenant_operation" in query:
            assert parameters[3:] == (7, "tenant_project_write")
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
        if "FROM project.project AS target_project" in query:
            self.owner_checks.append(parameters)
            return {"project_revision": 4}
        if "application.update_project" in query:
            assert query.count("%s") == len(parameters)
            self.function_calls.append(("update", parameters))
            return {
                "project_id": 18,
                "tenant_id": 7,
                "project_revision": 5,
                "is_active": True,
                "updated_at": datetime(2026, 8, 24, 14, 5, tzinfo=UTC),
            }
        if "application.archive_project" in query:
            self.function_calls.append(("archive", parameters))
            return {
                "project_id": 18,
                "tenant_id": 7,
                "project_revision": 6,
                "is_active": False,
                "updated_at": datetime(2026, 8, 24, 14, 10, tzinfo=UTC),
            }
        raise AssertionError((query, parameters))

    async def fetch_all(
        self,
        query: LiteralString,
        parameters: tuple[Any, ...] = (),
    ) -> list[dict[str, Any]]:
        # No retained cross-Tenant scope in this isolated service fixture.
        if "SELECT DISTINCT object.source_tenant_id" in query:
            return []
        if "core.tenant AS tenant" in query and "effective_role" in query:
            return []
        raise AssertionError((query, parameters))


class RevisionCommandDatabase:
    def __init__(self) -> None:
        self.transaction = RevisionCommandTransaction()

    @asynccontextmanager
    async def write_transaction(self) -> AsyncGenerator[RevisionCommandTransaction]:
        yield self.transaction


@pytest.mark.asyncio
async def test_revision_commands_precheck_path_tenant_and_call_only_governed_functions() -> (
    None
):
    database = RevisionCommandDatabase()
    service = DatabaseProjectCommandService(
        database=database,
        authorizer=AuthorizationService(),
        agent_capability_registry=load_default_agent_capabilities(),
    )
    principal = RequestPrincipal(
        actor_kind=ActorKind.HUMAN,
        entra_tenant_id=UUID("11111111-1111-1111-1111-111111111111"),
        entra_object_id=UUID("22222222-2222-2222-2222-222222222222"),
    )

    updated = await service.update_project(
        principal,
        tenant_id=7,
        project_id=18,
        request=UpdateProjectRequest.model_validate(
            _complete_project_payload() | {"expected_project_revision": 4}
        ),
    )
    archived = await service.archive_project(
        principal,
        tenant_id=7,
        project_id=18,
        request=ArchiveProjectRequest(expected_project_revision=5),
    )
    assert (updated.project_revision, archived.project_revision) == (5, 6)
    assert database.transaction.owner_checks == [(7, 18), (7, 18)]
    identity = (
        principal.entra_tenant_id,
        principal.entra_object_id,
        "user",
    )
    update_call, archive_call = database.transaction.function_calls
    assert update_call[0] == "update"
    assert update_call[1][:5] == identity + (18, 4)
    assert update_call[1][5:7] == ("Customer 360", "Cross-system customer domain")
    assert isinstance(update_call[1][7], Jsonb)
    assert update_call[1][7].obj == _complete_project_payload()["logical_schemas"]
    assert isinstance(update_call[1][8], Jsonb)
    assert update_call[1][8].obj == _complete_project_payload()["dimensional_schemas"]
    assert update_call[1][9] == "Use snake case."
    assert isinstance(update_call[1][10], Jsonb)
    assert update_call[1][11] == "Use business names."
    assert isinstance(update_call[1][12], Jsonb)
    assert isinstance(update_call[1][13], Jsonb)
    assert update_call[1][14:] == (
        "openai_agents_sdk",
        "microsoft_foundry",
        "foundry-primary",
        "medium",
        10,
        2,
        32,
        "type_2",
        "type_1",
        None,
        None,
        False,
        False,
    )
    assert archive_call == ("archive", identity + (18, 5))


@pytest.mark.parametrize(
    "extra_values",
    [
        {"entra_tenant_id": "11111111-1111-1111-1111-111111111111"},
        {"silver_model_naming_instructions": "   "},
        {"default_agent_sdk_code": ""},
        {"default_mapping_source_system_id": 0},
        {"default_mapping_source_system_id": True},
        {"dimensional_entity_scd_type": "type_3"},
        {"dimensional_entity_scd_type": True},
        {"logical_entity_scd_type": "type_3"},
        {"logical_entity_scd_type": "SCD2"},
        {"logical_entity_scd_type": 2},
        {"logical_entity_scd_type": True},
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
def test_project_commands_reject_identity_injection_and_partial_agent_defaults(
    extra_values: dict[str, object],
) -> None:
    app = create_app(
        identity_provider=_identity_provider(),
        project_command_service=StaticProjectCommandService(),
    )

    with TestClient(app) as client:
        response = client.post(
            "/api/v1/tenants/7/projects",
            json=_complete_project_payload() | extra_values,
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
async def test_agent_registry_rejects_incompatible_defaults_before_database_access() -> (
    None
):
    database = NoWriteDatabase()
    service = DatabaseProjectCommandService(
        database=database,
        authorizer=AuthorizationService(),
        agent_capability_registry=load_default_agent_capabilities(),
    )
    incompatible = _complete_project_payload() | {
        "default_agent_model_code": "unavailable-project"
    }
    principal = RequestPrincipal(
        actor_kind=ActorKind.HUMAN,
        entra_tenant_id=UUID("11111111-1111-1111-1111-111111111111"),
        entra_object_id=UUID("22222222-2222-2222-2222-222222222222"),
    )

    with pytest.raises(InvalidRequestError):
        await service.create_project(
            principal,
            tenant_id=7,
            request=CompleteProjectRequest.model_validate(incompatible),
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
        if "project.assert_writable" in query:
            return {"assert_writable": None}
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
        if "FROM project.project AS target_project" in query:
            assert parameters == (7, 18)
            return {"project_revision": 4}
        raise RuntimeError(self.message)

    async def fetch_all(
        self,
        query: LiteralString,
        parameters: tuple[Any, ...] = (),
    ) -> list[dict[str, Any]]:
        # No retained cross-Tenant scope in this isolated service fixture.
        if "SELECT DISTINCT object.source_tenant_id" in query:
            return []
        if "core.tenant AS tenant" in query and "effective_role" in query:
            return []
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
        ("stale_project_revision", 409, "project_revision_conflict"),
        (
            "A referenced Project schema cannot be removed or renamed",
            409,
            "project_schema_conflict",
        ),
        (
            "A referenced Project schema cannot be removed or renamed: private database detail",
            503,
            "dependency_unavailable",
        ),
        ("Project is unavailable", 404, "project_not_found"),
        (
            "Default Mapping System is unavailable for this Tenant",
            422,
            "invalid_request",
        ),
        ("Project update denied: tenant_lock_required", 409, "tenant_lock_required"),
        ("Project update denied: authorization_denied", 403, "authorization_denied"),
        ("database password=secret-value", 503, "dependency_unavailable"),
    ],
)
def test_database_project_failures_are_mapped_without_raw_message_disclosure(
    database_message: str,
    expected_status: int,
    expected_code: str,
) -> None:
    service = DatabaseProjectCommandService(
        database=FailingFunctionDatabase(database_message),
        authorizer=AuthorizationService(),
        agent_capability_registry=load_default_agent_capabilities(),
    )
    app = create_app(
        identity_provider=_identity_provider(),
        project_command_service=service,
    )

    with TestClient(app, raise_server_exceptions=False) as client:
        response = client.put(
            "/api/v1/tenants/7/projects/18",
            json=_complete_project_payload() | {"expected_project_revision": 4},
        )

    assert response.status_code == expected_status
    assert response.json()["error"]["code"] == expected_code
    assert response.json()["error"]["retryable"] == (expected_status == 503)
    assert database_message not in response.text


class RejectedPrecheckTransaction:
    def __init__(self, *, authorized: bool) -> None:
        self.authorized = authorized
        self.project_owner_checked = False
        self.function_called = False

    async def fetch_one(
        self,
        query: LiteralString,
        parameters: tuple[Any, ...] = (),
    ) -> dict[str, Any] | None:
        if "project.assert_writable" in query:
            return {"assert_writable": None}
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
        if "FROM project.project AS target_project" in query:
            assert parameters == (7, 18)
            self.project_owner_checked = True
            return None
        self.function_called = True
        raise AssertionError("a rejected precheck must not call a Project function")

    async def fetch_all(
        self,
        query: LiteralString,
        parameters: tuple[Any, ...] = (),
    ) -> list[dict[str, Any]]:
        # No retained cross-Tenant scope in this isolated service fixture.
        if "SELECT DISTINCT object.source_tenant_id" in query:
            return []
        if "core.tenant AS tenant" in query and "effective_role" in query:
            return []
        raise AssertionError((query, parameters))


class RejectedPrecheckDatabase:
    def __init__(self, *, authorized: bool) -> None:
        self.transaction = RejectedPrecheckTransaction(authorized=authorized)

    @asynccontextmanager
    async def write_transaction(self) -> AsyncGenerator[RejectedPrecheckTransaction]:
        yield self.transaction


@pytest.mark.asyncio
async def test_cross_tenant_project_id_is_not_found_before_canonical_mutation() -> None:
    database = RejectedPrecheckDatabase(authorized=True)
    service = DatabaseProjectCommandService(
        database=database,
        authorizer=AuthorizationService(),
        agent_capability_registry=load_default_agent_capabilities(),
    )
    principal = RequestPrincipal(
        actor_kind=ActorKind.HUMAN,
        entra_tenant_id=UUID("11111111-1111-1111-1111-111111111111"),
        entra_object_id=UUID("22222222-2222-2222-2222-222222222222"),
    )

    with pytest.raises(ProjectNotFoundError):
        await service.archive_project(
            principal,
            tenant_id=7,
            project_id=18,
            request=ArchiveProjectRequest(expected_project_revision=5),
        )

    assert database.transaction.project_owner_checked is True
    assert database.transaction.function_called is False


@pytest.mark.parametrize("action", ["create", "archive"])
def test_owned_tenant_lock_is_required_before_project_lookup_or_mutation(
    action: str,
) -> None:
    database = RejectedPrecheckDatabase(authorized=False)
    service = DatabaseProjectCommandService(
        database=database,
        authorizer=AuthorizationService(),
        agent_capability_registry=load_default_agent_capabilities(),
    )
    app = create_app(
        identity_provider=_identity_provider(),
        project_command_service=service,
    )

    with TestClient(app) as client:
        response = client.post(
            "/api/v1/tenants/7/projects"
            if action == "create"
            else "/api/v1/tenants/7/projects/18/archive",
            json={"project_name": "New Project"}
            if action == "create"
            else {"expected_project_revision": 5},
        )

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "tenant_locked"
    assert database.transaction.project_owner_checked is False
    assert database.transaction.function_called is False


def test_runtime_wires_all_complete_project_command_routes() -> None:
    settings = RuntimeSettings.from_environment(
        {
            "GDS_WEB_ENVIRONMENT": "local",
            "GDS_WEB_DATABASE_DSN": "postgresql://fixture.invalid/workbench",
            "GDS_WEB_CURSOR_SIGNING_KEY": "development-only-key-32-bytes-long",
            "GDS_WEB_DATABRICKS_ENVIRONMENT_CODE": "TEST",
            "GDS_WEB_LOCAL_ENTRA_TENANT_ID": ("11111111-1111-1111-1111-111111111111"),
            "GDS_WEB_LOCAL_PRINCIPAL_OBJECT_ID": (
                "22222222-2222-2222-2222-222222222222"
            ),
        }
    )
    app = create_runtime_app(
        settings=settings,
        database=cast(RuntimeDatabase, NoWriteDatabase()),
    )

    paths = app.openapi()["paths"]
    assert "post" in paths["/api/v1/tenants/{tenant_id}/projects"]
    assert "put" in paths["/api/v1/tenants/{tenant_id}/projects/{project_id}"]
    assert "post" in paths["/api/v1/tenants/{tenant_id}/projects/{project_id}/archive"]
    assert (
        "put"
        not in paths["/api/v1/tenants/{tenant_id}/projects/{project_id}/input-scope"]
    )


@pytest.mark.parametrize("scd_type", (None, "type_1", "type_2"))
def test_project_commands_preserve_explicit_logical_scd_choice(
    scd_type: str | None,
) -> None:
    payload = _complete_project_payload() | {"logical_entity_scd_type": scd_type}
    request = CompleteProjectRequest.model_validate(payload)
    update = UpdateProjectRequest.model_validate(
        payload | {"expected_project_revision": 4}
    )
    assert request.logical_entity_scd_type == update.logical_entity_scd_type == scd_type
    assert request.model_dump()["logical_entity_scd_type"] == scd_type


def test_omitted_logical_scd_choice_is_unspecified() -> None:
    assert (
        CompleteProjectRequest(project_name="Customer 360").logical_entity_scd_type
        is None
    )


def test_project_lock_route_accepts_only_lock_and_expected_revision() -> None:
    app = create_app(
        identity_provider=_identity_provider(),
        project_command_service=StaticProjectCommandService(),
    )
    with TestClient(app) as client:
        response = client.put(
            "/api/v1/tenants/7/projects/18/lock",
            json={"expected_project_revision": 4, "is_locked": True},
        )
        assert response.status_code == 200
        assert response.json()["project_revision"] == 5
        assert (
            client.put(
                "/api/v1/tenants/7/projects/18/lock", json={"is_locked": False}
            ).status_code
            == 422
        )
        assert (
            client.put(
                "/api/v1/tenants/7/projects/18/lock",
                json={
                    "expected_project_revision": 4,
                    "is_locked": True,
                    "actor": "agent",
                },
            ).status_code
            == 422
        )


@pytest.mark.parametrize(
    "field",
    ["logical_coverage_threshold_percent", "dimensional_coverage_threshold_percent"],
)
@pytest.mark.parametrize("value", [0, 101, -1, 69.5, 70.0, True, "70"])
def test_coverage_settings_reject_non_integer_or_out_of_range_values(
    field: str, value: object
) -> None:
    with pytest.raises(ValueError):
        CompleteProjectRequest.model_validate(
            {"project_name": "Coverage", field: value}
        )


@pytest.mark.parametrize("value", [1, 69, 70, 100, None])
def test_coverage_settings_preserve_valid_values_and_database_default(
    value: int | None,
) -> None:
    request = CompleteProjectRequest(
        project_name="Coverage", logical_coverage_threshold_percent=value
    )
    assert request.logical_coverage_threshold_percent == value
    assert request.dimensional_coverage_threshold_percent is None


@pytest.mark.parametrize(
    "field",
    ["logical_enforce_coverage_threshold", "dimensional_enforce_coverage_threshold"],
)
@pytest.mark.parametrize("value", [None, 0, 1, "true", "false"])
def test_coverage_enforcement_requires_boolean(field: str, value: object) -> None:
    with pytest.raises(ValueError):
        CompleteProjectRequest.model_validate(
            {"project_name": "Coverage", field: value}
        )


def test_coverage_enforcement_defaults_off_and_remains_independent() -> None:
    request = CompleteProjectRequest(project_name="Coverage")
    assert request.logical_enforce_coverage_threshold is False
    assert request.dimensional_enforce_coverage_threshold is False
    request = CompleteProjectRequest(
        project_name="Coverage", logical_enforce_coverage_threshold=True
    )
    assert request.logical_enforce_coverage_threshold is True
    assert request.dimensional_enforce_coverage_threshold is False
