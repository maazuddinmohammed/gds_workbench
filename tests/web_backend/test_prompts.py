from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, LiteralString, Protocol, cast
from uuid import UUID, uuid4

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
from psycopg import Connection
from pydantic import ValidationError

from gds_workbench_api.database import WebPostgresDatabase
from gds_workbench_api.features.prompts import (
    CreatePromptTemplateRequest,
    DatabasePromptService,
    PromptConflictError,
    PromptDatabase,
    PromptService,
    PromptStage,
    PromptStageCatalog,
    PromptTemplateFilters,
    SavePromptDraftRequest,
    SetModelPromptAssignmentRequest,
    UpdatePromptTemplateRequest,
    create_prompts_router,
)


class DisposablePostgres(Protocol):
    def connect_owner(self) -> Connection[dict[str, Any]]: ...

    def web_runtime_dsn(self) -> str: ...


NOW = datetime(2026, 8, 24, 14, 0, tzinfo=UTC)
PRINCIPAL = RequestPrincipal(
    actor_kind=ActorKind.HUMAN,
    entra_tenant_id=UUID("11111111-1111-1111-1111-111111111111"),
    entra_object_id=UUID("22222222-2222-2222-2222-222222222222"),
)


class StageCatalogTransaction:
    async def fetch_one(
        self,
        query: LiteralString,
        parameters: tuple[Any, ...] = (),
    ) -> dict[str, Any] | None:
        assert "security.entra_principal_identity" in query
        assert parameters[-1] == 7
        return {
            "principal_id": 41,
            "principal_display_name": "Prompt Architect",
            "is_super_admin": False,
            "effective_role": "architect",
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
        assert "application.workflow_stage_variable" in query
        assert parameters == (2001,)
        return [
            {
                "workflow_stage_id": 12,
                "model_workflow": "analysis",
                "workflow_execution_mode": "one_shot",
                "workflow_stage_code": "analyze_sources",
                "workflow_stage_name": "Analyze sources",
                "workflow_stage_description": None,
                "workflow_stage_order": 10,
                "variable_name": "stage_context",
                "variable_resolver_key": "stage_context",
                "variable_data_type": "json",
                "variable_is_required": True,
                "variable_description": "Governed source context",
                "variable_example": {"objects": []},
                "variable_order": 10,
            },
            {
                "workflow_stage_id": 12,
                "model_workflow": "analysis",
                "workflow_execution_mode": "one_shot",
                "workflow_stage_code": "analyze_sources",
                "workflow_stage_name": "Analyze sources",
                "workflow_stage_description": None,
                "workflow_stage_order": 10,
                "variable_name": "naming_instructions",
                "variable_resolver_key": "model.naming_instructions",
                "variable_data_type": "text",
                "variable_is_required": False,
                "variable_description": "Optional model naming instructions",
                "variable_example": "Use business language.",
                "variable_order": 20,
            },
        ]


class StageCatalogDatabase:
    @asynccontextmanager
    async def read_transaction(
        self,
        *,
        isolation: ReadIsolation = ReadIsolation.READ_COMMITTED,
    ) -> AsyncGenerator[StageCatalogTransaction]:
        assert isolation is ReadIsolation.REPEATABLE_READ
        yield StageCatalogTransaction()


@pytest.mark.asyncio
async def test_stage_catalog_returns_only_agentic_stages_with_allowed_variables() -> (
    None
):
    service = DatabasePromptService(
        database=cast(PromptDatabase, StageCatalogDatabase()),
        authorizer=AuthorizationService(),
        cursor_signing_key=b"development-only-key-32-bytes-long",
    )

    catalog = await service.list_stages(PRINCIPAL, tenant_id=7)

    assert len(catalog.items) == 1
    assert catalog.items[0].workflow_stage_code == "analyze_sources"
    assert [variable.name for variable in catalog.items[0].allowed_variables] == [
        "stage_context",
        "naming_instructions",
    ]


class TemplateListTransaction:
    def __init__(self) -> None:
        self.offsets: list[int] = []

    async def fetch_one(
        self,
        query: LiteralString,
        parameters: tuple[Any, ...] = (),
    ) -> dict[str, Any] | None:
        assert "security.entra_principal_identity" in query
        return {
            "principal_id": 41,
            "principal_display_name": "Prompt Architect",
            "is_super_admin": False,
            "effective_role": "architect",
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
        assert "FROM application.prompt_template AS template" in query
        assert "system_prompt_template" not in query
        assert parameters[:-2] == (
            7,
            "analysis",
            "analysis",
            "one_shot",
            "one_shot",
            "analyze_sources",
            "analyze_sources",
            "published",
            "published",
        )
        limit, offset = parameters[-2:]
        assert limit == 2
        self.offsets.append(offset)
        rows = [
            _template_summary_row(101, "global_analysis", "global", None),
            _template_summary_row(102, "tenant_analysis", "tenant", 7),
        ]
        return rows[offset : offset + limit]


class TemplateListDatabase:
    def __init__(self) -> None:
        self.transaction = TemplateListTransaction()

    @asynccontextmanager
    async def read_transaction(
        self,
        *,
        isolation: ReadIsolation = ReadIsolation.READ_COMMITTED,
    ) -> AsyncGenerator[TemplateListTransaction]:
        assert isolation is ReadIsolation.REPEATABLE_READ
        yield self.transaction


def _template_summary_row(
    template_id: int,
    code: str,
    scope: str,
    owner_tenant_id: int | None,
) -> dict[str, Any]:
    return {
        "prompt_template_id": template_id,
        "workflow_stage_id": 12,
        "model_workflow": "analysis",
        "workflow_execution_mode": "one_shot",
        "workflow_stage_code": "analyze_sources",
        "workflow_stage_name": "Analyze sources",
        "prompt_template_ownership_scope": scope,
        "owner_tenant_id": owner_tenant_id,
        "prompt_template_code": code,
        "prompt_template_name": code.replace("_", " ").title(),
        "prompt_template_description": None,
        "is_active": True,
        "latest_version_id": template_id + 1000,
        "latest_version_number": 1,
        "latest_version_status": "published",
        "latest_version_digest": "a" * 64,
        "latest_version_updated_at": NOW,
        "updated_at": NOW,
    }


@pytest.mark.asyncio
async def test_template_list_is_visible_scope_filtered_and_signed_page_bounded() -> (
    None
):
    database = TemplateListDatabase()
    service = DatabasePromptService(
        database=cast(PromptDatabase, database),
        authorizer=AuthorizationService(),
        cursor_signing_key=b"development-only-key-32-bytes-long",
    )
    filters = PromptTemplateFilters(
        model_workflow="analysis",
        workflow_execution_mode="one_shot",
        workflow_stage_code=" Analyze_Sources ",
        version_status="published",
    )

    first = await service.list_templates(
        PRINCIPAL,
        tenant_id=7,
        filters=filters,
        page_size=1,
        cursor=None,
    )
    second = await service.list_templates(
        PRINCIPAL,
        tenant_id=7,
        filters=filters,
        page_size=1,
        cursor=first.next_cursor,
    )

    assert [item.prompt_template_code for item in first.items] == ["global_analysis"]
    assert [item.prompt_template_code for item in second.items] == ["tenant_analysis"]
    assert second.next_cursor is None
    assert database.transaction.offsets == [0, 1]


class TemplateDetailTransaction:
    def __init__(self) -> None:
        self.calls: list[str] = []

    async def fetch_one(
        self,
        query: LiteralString,
        parameters: tuple[Any, ...] = (),
    ) -> dict[str, Any] | None:
        if "security.entra_principal_identity" in query:
            self.calls.append("authorize")
            assert parameters[-1] == 7
            return {
                "principal_id": 41,
                "principal_display_name": "Prompt Architect",
                "is_super_admin": False,
                "effective_role": "architect",
                "authorized": True,
                "denial_code": None,
                "lock_owner_display_name": None,
                "lock_expires_time": None,
            }
        self.calls.append("header")
        assert "FROM application.prompt_template AS template" in query
        assert "system_prompt_template" not in query
        assert parameters == (101, 7)
        return _template_summary_row(101, "tenant_analysis", "tenant", 7)

    async def fetch_all(
        self,
        query: LiteralString,
        parameters: tuple[Any, ...] = (),
    ) -> list[dict[str, Any]]:
        if "application.workflow_stage_variable" in query:
            self.calls.append("variables")
            assert parameters == (12, 101)
            return [
                {
                    "name": "stage_context",
                    "resolver_key": "stage_context",
                    "data_type": "json",
                    "is_required": True,
                    "description": "Governed source context",
                    "example": None,
                    "order": 10,
                }
            ]
        self.calls.append("versions")
        assert "system_prompt_template" in query
        assert parameters == (101, 201)
        return [
            {
                "prompt_template_version_id": 1101,
                "prompt_template_id": 101,
                "workflow_stage_id": 12,
                "prompt_template_version_number": 1,
                "system_prompt_template": "RAW_SYSTEM_SENTINEL {{stage_context}}",
                "instruction_prompt_template": "RAW_INSTRUCTION_SENTINEL",
                "tool_instruction_prompt_template": None,
                "prompt_template_digest": "a" * 64,
                "prompt_template_version_status": "published",
                "published_at": NOW,
                "retired_at": None,
                "created_at": NOW,
                "updated_at": NOW,
            }
        ]


class TemplateDetailDatabase:
    def __init__(self) -> None:
        self.transaction = TemplateDetailTransaction()

    @asynccontextmanager
    async def read_transaction(
        self,
        *,
        isolation: ReadIsolation = ReadIsolation.READ_COMMITTED,
    ) -> AsyncGenerator[TemplateDetailTransaction]:
        assert isolation is ReadIsolation.REPEATABLE_READ
        yield self.transaction


@pytest.mark.asyncio
async def test_template_detail_authorizes_before_returning_bounded_raw_version_history() -> (
    None
):
    database = TemplateDetailDatabase()
    service = DatabasePromptService(
        database=cast(PromptDatabase, database),
        authorizer=AuthorizationService(),
        cursor_signing_key=b"development-only-key-32-bytes-long",
    )

    detail = await service.read_template(
        PRINCIPAL,
        tenant_id=7,
        prompt_template_id=101,
    )

    assert detail.template.owner_tenant_id == 7
    assert detail.allowed_variables[0].name == "stage_context"
    assert detail.versions[0].system_prompt_template.startswith("RAW_SYSTEM_SENTINEL")
    assert database.transaction.calls == [
        "authorize",
        "header",
        "variables",
        "versions",
    ]


class CreateTemplateTransaction:
    def __init__(self) -> None:
        self.calls: list[str] = []

    async def fetch_one(
        self,
        query: LiteralString,
        parameters: tuple[Any, ...] = (),
    ) -> dict[str, Any] | None:
        if "security.authorize_tenant_operation" in query:
            self.calls.append("authorize_model_write")
            assert parameters[-2:] == (7, "tenant_model_write")
            return {
                "principal_id": 41,
                "principal_display_name": "Prompt Architect",
                "is_super_admin": False,
                "effective_role": "architect",
                "authorized": True,
                "denial_code": None,
                "lock_owner_display_name": None,
                "lock_expires_time": NOW,
            }
        self.calls.append("save_prompt_template")
        assert "application.save_prompt_template" in query
        assert "INSERT INTO application.prompt_template" not in query
        assert parameters == (
            PRINCIPAL.entra_tenant_id,
            PRINCIPAL.entra_object_id,
            "user",
            None,
            12,
            "tenant",
            7,
            "tenant_analysis",
            "Tenant Analysis",
            "Tenant-owned analysis prompt",
            True,
            None,
        )
        return {
            "prompt_template_id": 101,
            "workflow_stage_id": 12,
            "prompt_template_ownership_scope": "tenant",
            "owner_tenant_id": 7,
            "prompt_template_code": "tenant_analysis",
            "prompt_template_name": "Tenant Analysis",
            "prompt_template_description": "Tenant-owned analysis prompt",
            "is_active": True,
            "created_at": NOW,
            "updated_at": NOW,
        }

    async def fetch_all(
        self,
        query: LiteralString,
        parameters: tuple[Any, ...] = (),
    ) -> list[dict[str, Any]]:
        raise AssertionError((query, parameters))


class CreateTemplateDatabase:
    def __init__(self) -> None:
        self.transaction = CreateTemplateTransaction()

    @asynccontextmanager
    async def write_transaction(self) -> AsyncGenerator[CreateTemplateTransaction]:
        yield self.transaction


@pytest.mark.asyncio
async def test_create_tenant_template_binds_owner_server_side_and_calls_governed_function() -> (
    None
):
    database = CreateTemplateDatabase()
    service = DatabasePromptService(
        database=cast(PromptDatabase, database),
        authorizer=AuthorizationService(),
        cursor_signing_key=b"development-only-key-32-bytes-long",
    )

    created = await service.create_template(
        PRINCIPAL,
        tenant_id=7,
        body=CreatePromptTemplateRequest(
            workflow_stage_id=12,
            prompt_template_ownership_scope="tenant",
            prompt_template_code=" Tenant_Analysis ",
            prompt_template_name="Tenant Analysis",
            prompt_template_description="Tenant-owned analysis prompt",
        ),
    )

    assert created.prompt_template_id == 101
    assert created.owner_tenant_id == 7
    assert database.transaction.calls == [
        "authorize_model_write",
        "save_prompt_template",
    ]


class GlobalCreateTransaction(CreateTemplateTransaction):
    def __init__(self, *, is_super_admin: bool) -> None:
        super().__init__()
        self.is_super_admin = is_super_admin

    async def fetch_one(
        self,
        query: LiteralString,
        parameters: tuple[Any, ...] = (),
    ) -> dict[str, Any] | None:
        if "security.entra_principal_identity" in query:
            self.calls.append("authorize_read")
            return {
                "principal_id": 41,
                "principal_display_name": "Prompt Admin",
                "is_super_admin": self.is_super_admin,
                "effective_role": "super_admin" if self.is_super_admin else "architect",
                "authorized": True,
                "denial_code": None,
                "lock_owner_display_name": None,
                "lock_expires_time": None,
            }
        self.calls.append("save_global_prompt_template")
        assert "application.save_prompt_template" in query
        assert parameters[5:8] == ("global", None, "global_analysis")
        return {
            "prompt_template_id": 201,
            "workflow_stage_id": 12,
            "prompt_template_ownership_scope": "global",
            "owner_tenant_id": None,
            "prompt_template_code": "global_analysis",
            "prompt_template_name": "Global Analysis",
            "prompt_template_description": None,
            "is_active": True,
            "created_at": NOW,
            "updated_at": NOW,
        }


class GlobalCreateDatabase:
    def __init__(self, *, is_super_admin: bool) -> None:
        self.transaction = GlobalCreateTransaction(is_super_admin=is_super_admin)

    @asynccontextmanager
    async def write_transaction(self) -> AsyncGenerator[GlobalCreateTransaction]:
        yield self.transaction


@pytest.mark.asyncio
async def test_global_template_mutation_requires_super_admin_and_passes_null_owner() -> (
    None
):
    body = CreatePromptTemplateRequest(
        workflow_stage_id=12,
        prompt_template_ownership_scope="global",
        prompt_template_code="global_analysis",
        prompt_template_name="Global Analysis",
    )
    denied_database = GlobalCreateDatabase(is_super_admin=False)
    denied_service = DatabasePromptService(
        database=cast(PromptDatabase, denied_database),
        authorizer=AuthorizationService(),
        cursor_signing_key=b"development-only-key-32-bytes-long",
    )

    with pytest.raises(AuthorizationDeniedError):
        await denied_service.create_template(PRINCIPAL, tenant_id=7, body=body)

    assert denied_database.transaction.calls == ["authorize_read"]
    allowed_database = GlobalCreateDatabase(is_super_admin=True)
    allowed_service = DatabasePromptService(
        database=cast(PromptDatabase, allowed_database),
        authorizer=AuthorizationService(),
        cursor_signing_key=b"development-only-key-32-bytes-long",
    )
    created = await allowed_service.create_template(PRINCIPAL, tenant_id=7, body=body)
    assert created.owner_tenant_id is None
    assert allowed_database.transaction.calls == [
        "authorize_read",
        "save_global_prompt_template",
    ]


class UpdateTemplateTransaction:
    def __init__(self) -> None:
        self.calls: list[str] = []

    async def fetch_one(
        self,
        query: LiteralString,
        parameters: tuple[Any, ...] = (),
    ) -> dict[str, Any] | None:
        if "security.entra_principal_identity" in query:
            self.calls.append("authorize_read")
            assert parameters[-1] == 7
            return {
                "principal_id": 41,
                "principal_display_name": "Prompt Architect",
                "is_super_admin": False,
                "effective_role": "architect",
                "authorized": True,
                "denial_code": None,
                "lock_owner_display_name": None,
                "lock_expires_time": None,
            }
        if "security.authorize_tenant_operation" in query:
            self.calls.append("authorize_model_write")
            assert parameters[-2:] == (7, "tenant_model_write")
            return {
                "principal_id": 41,
                "principal_display_name": "Prompt Architect",
                "is_super_admin": False,
                "effective_role": "architect",
                "authorized": True,
                "denial_code": None,
                "lock_owner_display_name": None,
                "lock_expires_time": NOW,
            }
        if "FROM application.prompt_template AS template" in query:
            self.calls.append("load_context")
            assert parameters == (101, 7)
            return {
                "prompt_template_id": 101,
                "workflow_stage_id": 12,
                "prompt_template_ownership_scope": "tenant",
                "owner_tenant_id": 7,
                "prompt_template_code": "tenant_analysis",
            }
        self.calls.append("save_prompt_template")
        assert "application.save_prompt_template" in query
        assert parameters == (
            PRINCIPAL.entra_tenant_id,
            PRINCIPAL.entra_object_id,
            "user",
            101,
            12,
            "tenant",
            7,
            "tenant_analysis",
            "Renamed Tenant Analysis",
            None,
            False,
            NOW,
        )
        return {
            "prompt_template_id": 101,
            "workflow_stage_id": 12,
            "prompt_template_ownership_scope": "tenant",
            "owner_tenant_id": 7,
            "prompt_template_code": "tenant_analysis",
            "prompt_template_name": "Renamed Tenant Analysis",
            "prompt_template_description": None,
            "is_active": False,
            "created_at": NOW,
            "updated_at": NOW,
        }

    async def fetch_all(
        self,
        query: LiteralString,
        parameters: tuple[Any, ...] = (),
    ) -> list[dict[str, Any]]:
        raise AssertionError((query, parameters))


class UpdateTemplateDatabase:
    def __init__(self) -> None:
        self.transaction = UpdateTemplateTransaction()

    @asynccontextmanager
    async def write_transaction(self) -> AsyncGenerator[UpdateTemplateTransaction]:
        yield self.transaction


@pytest.mark.asyncio
async def test_update_template_uses_server_loaded_immutable_identity_and_timestamp_fence() -> (
    None
):
    database = UpdateTemplateDatabase()
    service = DatabasePromptService(
        database=cast(PromptDatabase, database),
        authorizer=AuthorizationService(),
        cursor_signing_key=b"development-only-key-32-bytes-long",
    )

    updated = await service.update_template(
        PRINCIPAL,
        tenant_id=7,
        prompt_template_id=101,
        body=UpdatePromptTemplateRequest(
            prompt_template_name="Renamed Tenant Analysis",
            prompt_template_description=None,
            is_active=False,
            expected_updated_at=NOW,
        ),
    )

    assert updated.prompt_template_name == "Renamed Tenant Analysis"
    assert database.transaction.calls == [
        "authorize_read",
        "load_context",
        "authorize_model_write",
        "save_prompt_template",
    ]


class SaveDraftTransaction(UpdateTemplateTransaction):
    async def fetch_one(
        self,
        query: LiteralString,
        parameters: tuple[Any, ...] = (),
    ) -> dict[str, Any] | None:
        if "application.save_prompt_template_draft" not in query:
            return await super().fetch_one(query, parameters)
        self.calls.append("save_prompt_template_draft")
        assert "UPDATE application.prompt_template_version" not in query
        assert parameters == (
            PRINCIPAL.entra_tenant_id,
            PRINCIPAL.entra_object_id,
            "user",
            101,
            1101,
            "System {{future_variable}}",
            "Analyze {{stage_context}}",
            None,
            NOW,
        )
        return {
            "prompt_template_version_id": 1101,
            "prompt_template_id": 101,
            "workflow_stage_id": 12,
            "prompt_template_version_number": 1,
            "system_prompt_template": "System {{future_variable}}",
            "instruction_prompt_template": "Analyze {{stage_context}}",
            "tool_instruction_prompt_template": None,
            "prompt_template_digest": "b" * 64,
            "prompt_template_version_status": "draft",
            "published_at": None,
            "retired_at": None,
            "created_at": NOW,
            "updated_at": NOW,
        }


class SaveDraftDatabase:
    def __init__(self) -> None:
        self.transaction = SaveDraftTransaction()

    @asynccontextmanager
    async def write_transaction(self) -> AsyncGenerator[SaveDraftTransaction]:
        yield self.transaction


@pytest.mark.asyncio
async def test_save_draft_passes_raw_bodies_and_both_stale_fences_to_governed_function() -> (
    None
):
    database = SaveDraftDatabase()
    service = DatabasePromptService(
        database=cast(PromptDatabase, database),
        authorizer=AuthorizationService(),
        cursor_signing_key=b"development-only-key-32-bytes-long",
    )

    draft = await service.save_draft(
        PRINCIPAL,
        tenant_id=7,
        prompt_template_id=101,
        body=SavePromptDraftRequest(
            expected_prompt_template_version_id=1101,
            expected_updated_at=NOW,
            system_prompt_template="System {{future_variable}}",
            instruction_prompt_template="Analyze {{stage_context}}",
            tool_instruction_prompt_template=None,
        ),
    )

    assert draft.prompt_template_version_status == "draft"
    assert "future_variable" in draft.system_prompt_template
    assert database.transaction.calls == [
        "authorize_read",
        "load_context",
        "authorize_model_write",
        "save_prompt_template_draft",
    ]


class TransitionVersionTransaction(UpdateTemplateTransaction):
    def __init__(self, *, expected_status: str, target_status: str) -> None:
        super().__init__()
        self.expected_status = expected_status
        self.target_status = target_status

    async def fetch_one(
        self,
        query: LiteralString,
        parameters: tuple[Any, ...] = (),
    ) -> dict[str, Any] | None:
        if "application.transition_prompt_template_version" in query:
            self.calls.append("transition_prompt_template_version")
            assert "UPDATE application.prompt_template_version" not in query
            assert parameters == (
                PRINCIPAL.entra_tenant_id,
                PRINCIPAL.entra_object_id,
                "user",
                1101,
                self.expected_status,
                self.target_status,
            )
            return {
                "prompt_template_version_id": 1101,
                "prompt_template_id": 101,
                "workflow_stage_id": 12,
                "prompt_template_version_number": 1,
                "system_prompt_template": "System",
                "instruction_prompt_template": "Analyze",
                "tool_instruction_prompt_template": None,
                "prompt_template_digest": "b" * 64,
                "prompt_template_version_status": self.target_status,
                "published_at": NOW,
                "retired_at": NOW if self.target_status == "retired" else None,
                "created_at": NOW,
                "updated_at": NOW,
            }
        if "FROM application.prompt_template_version AS version" in query:
            self.calls.append("bind_version")
            assert parameters == (1101, 101, 12)
            return {"prompt_template_version_id": 1101}
        return await super().fetch_one(query, parameters)


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
@pytest.mark.parametrize(
    ("operation", "expected_status", "target_status"),
    [
        ("publish", "draft", "published"),
        ("retire", "published", "retired"),
    ],
)
async def test_publish_and_retire_bind_version_and_use_fixed_governed_transition(
    operation: str,
    expected_status: str,
    target_status: str,
) -> None:
    database = TransitionVersionDatabase(
        expected_status=expected_status,
        target_status=target_status,
    )
    service = DatabasePromptService(
        database=cast(PromptDatabase, database),
        authorizer=AuthorizationService(),
        cursor_signing_key=b"development-only-key-32-bytes-long",
    )

    if operation == "publish":
        version = await service.publish_version(
            PRINCIPAL,
            tenant_id=7,
            prompt_template_id=101,
            prompt_template_version_id=1101,
        )
    else:
        version = await service.retire_version(
            PRINCIPAL,
            tenant_id=7,
            prompt_template_id=101,
            prompt_template_version_id=1101,
        )

    assert version.prompt_template_version_status == target_status
    assert database.transaction.calls == [
        "authorize_read",
        "load_context",
        "authorize_model_write",
        "bind_version",
        "transition_prompt_template_version",
    ]


class AssignmentListTransaction:
    def __init__(self) -> None:
        self.calls: list[str] = []

    async def fetch_one(
        self,
        query: LiteralString,
        parameters: tuple[Any, ...] = (),
    ) -> dict[str, Any] | None:
        if "security.entra_principal_identity" in query:
            self.calls.append("authorize_read")
            assert parameters[-1] == 7
            return {
                "principal_id": 41,
                "principal_display_name": "Prompt Architect",
                "is_super_admin": False,
                "effective_role": "architect",
                "authorized": True,
                "denial_code": None,
                "lock_owner_display_name": None,
                "lock_expires_time": None,
            }
        self.calls.append("bind_model_owner")
        assert "FROM model.model AS target_model" in query
        assert "connection_id" not in query
        assert parameters == (7, 18)
        return {"model_id": 18, "tenant_id": 7}

    async def fetch_all(
        self,
        query: LiteralString,
        parameters: tuple[Any, ...] = (),
    ) -> list[dict[str, Any]]:
        self.calls.append("list_effective")
        assert "application.prompt_assignment" in query
        assert "system_prompt_template" not in query
        assert parameters == (18, 201)
        return [
            _assignment_state_row(
                workflow_stage_id=12,
                stage_code="analyze_sources",
                model_assignment_id=501,
                global_assignment_id=401,
            ),
            _assignment_state_row(
                workflow_stage_id=13,
                stage_code="review_analysis",
                model_assignment_id=None,
                global_assignment_id=402,
            ),
        ]


def _assignment_state_row(
    *,
    workflow_stage_id: int,
    stage_code: str,
    model_assignment_id: int | None,
    global_assignment_id: int | None,
) -> dict[str, Any]:
    row: dict[str, Any] = {
        "workflow_stage_id": workflow_stage_id,
        "model_workflow": "analysis",
        "workflow_execution_mode": "one_shot",
        "workflow_stage_code": stage_code,
        "workflow_stage_name": stage_code.replace("_", " ").title(),
        "workflow_stage_order": workflow_stage_id,
    }
    for prefix, assignment_id, scope, owner_tenant_id in (
        ("model", model_assignment_id, "model_default", 7),
        ("global", global_assignment_id, "global_default", None),
    ):
        row.update(
            {
                f"{prefix}_assignment_id": assignment_id,
                f"{prefix}_version_id": None
                if assignment_id is None
                else assignment_id + 1000,
                f"{prefix}_version_number": None if assignment_id is None else 1,
                f"{prefix}_version_digest": None if assignment_id is None else "c" * 64,
                f"{prefix}_template_id": None
                if assignment_id is None
                else assignment_id + 2000,
                f"{prefix}_template_ownership_scope": (
                    None
                    if assignment_id is None
                    else ("tenant" if prefix == "model" else "global")
                ),
                f"{prefix}_owner_tenant_id": (
                    None if assignment_id is None else owner_tenant_id
                ),
                f"{prefix}_template_code": (
                    None if assignment_id is None else f"{prefix}_{stage_code}"
                ),
                f"{prefix}_template_name": (
                    None if assignment_id is None else f"{prefix.title()} {stage_code}"
                ),
                f"{prefix}_assigned_at": None if assignment_id is None else NOW,
                f"{prefix}_assignment_scope": None if assignment_id is None else scope,
            }
        )
    return row


class AssignmentListDatabase:
    def __init__(self) -> None:
        self.transaction = AssignmentListTransaction()

    @asynccontextmanager
    async def read_transaction(
        self,
        *,
        isolation: ReadIsolation = ReadIsolation.READ_COMMITTED,
    ) -> AsyncGenerator[AssignmentListTransaction]:
        assert isolation is ReadIsolation.REPEATABLE_READ
        yield self.transaction


@pytest.mark.asyncio
async def test_model_assignments_bind_model_owner_and_resolve_model_over_global_default() -> (
    None
):
    database = AssignmentListDatabase()
    service = DatabasePromptService(
        database=cast(PromptDatabase, database),
        authorizer=AuthorizationService(),
        cursor_signing_key=b"development-only-key-32-bytes-long",
    )

    assignments = await service.list_model_assignments(
        PRINCIPAL,
        tenant_id=7,
        model_id=18,
    )

    assert [item.effective_source for item in assignments.items] == [
        "model_default",
        "global_default",
    ]
    assert assignments.items[0].effective_assignment is not None
    assert assignments.items[0].effective_assignment.prompt_assignment_id == 501
    assert assignments.items[1].effective_assignment is not None
    assert assignments.items[1].effective_assignment.prompt_assignment_id == 402
    assert database.transaction.calls == [
        "authorize_read",
        "bind_model_owner",
        "list_effective",
    ]


class SetAssignmentTransaction:
    def __init__(self, *, clear: bool) -> None:
        self.clear = clear
        self.calls: list[str] = []

    async def fetch_one(
        self,
        query: LiteralString,
        parameters: tuple[Any, ...] = (),
    ) -> dict[str, Any] | None:
        if "security.authorize_tenant_operation" in query:
            self.calls.append("authorize_model_write")
            assert parameters[-2:] == (7, "tenant_model_write")
            return {
                "principal_id": 41,
                "principal_display_name": "Prompt Architect",
                "is_super_admin": False,
                "effective_role": "architect",
                "authorized": True,
                "denial_code": None,
                "lock_owner_display_name": None,
                "lock_expires_time": NOW,
            }
        if "FROM model.model AS target_model" in query:
            self.calls.append("bind_model_owner")
            assert parameters == (7, 18)
            return {"model_id": 18, "tenant_id": 7}
        self.calls.append("set_prompt_assignment")
        assert "application.set_prompt_assignment" in query
        assert "INSERT INTO application.prompt_assignment" not in query
        assert parameters == (
            PRINCIPAL.entra_tenant_id,
            PRINCIPAL.entra_object_id,
            "user",
            12,
            "model_default",
            18,
            None if self.clear else 1101,
            501 if self.clear else None,
        )
        return None if self.clear else {"prompt_assignment_id": 501}

    async def fetch_all(
        self,
        query: LiteralString,
        parameters: tuple[Any, ...] = (),
    ) -> list[dict[str, Any]]:
        self.calls.append("read_effective")
        assert "application.prompt_assignment" in query
        assert parameters == (18, 201)
        return [
            _assignment_state_row(
                workflow_stage_id=12,
                stage_code="analyze_sources",
                model_assignment_id=None if self.clear else 501,
                global_assignment_id=401,
            )
        ]


class SetAssignmentDatabase:
    def __init__(self, *, clear: bool) -> None:
        self.transaction = SetAssignmentTransaction(clear=clear)

    @asynccontextmanager
    async def write_transaction(self) -> AsyncGenerator[SetAssignmentTransaction]:
        yield self.transaction


@pytest.mark.asyncio
@pytest.mark.parametrize("clear", [False, True])
async def test_set_and_clear_model_assignment_use_owned_lock_and_governed_function(
    clear: bool,
) -> None:
    database = SetAssignmentDatabase(clear=clear)
    service = DatabasePromptService(
        database=cast(PromptDatabase, database),
        authorizer=AuthorizationService(),
        cursor_signing_key=b"development-only-key-32-bytes-long",
    )

    state = await service.set_model_assignment(
        PRINCIPAL,
        tenant_id=7,
        model_id=18,
        workflow_stage_id=12,
        body=SetModelPromptAssignmentRequest(
            prompt_template_version_id=None if clear else 1101,
            expected_prompt_assignment_id=501 if clear else None,
        ),
    )

    assert state.effective_source == ("global_default" if clear else "model_default")
    assert database.transaction.calls == [
        "authorize_model_write",
        "bind_model_owner",
        "set_prompt_assignment",
        "read_effective",
    ]


class _FakeDiagnostic:
    message_primary = "stale_prompt_template_draft RAW_PROMPT_SENTINEL"


class _FakeDatabaseError(Exception):
    diag = _FakeDiagnostic()


class StaleDraftTransaction(SaveDraftTransaction):
    async def fetch_one(
        self,
        query: LiteralString,
        parameters: tuple[Any, ...] = (),
    ) -> dict[str, Any] | None:
        if "application.save_prompt_template_draft" in query:
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
async def test_stale_database_failure_maps_to_stable_conflict_without_raw_text() -> (
    None
):
    service = DatabasePromptService(
        database=cast(PromptDatabase, StaleDraftDatabase()),
        authorizer=AuthorizationService(),
        cursor_signing_key=b"development-only-key-32-bytes-long",
    )

    with pytest.raises(PromptConflictError) as captured:
        await service.save_draft(
            PRINCIPAL,
            tenant_id=7,
            prompt_template_id=101,
            body=SavePromptDraftRequest(
                expected_prompt_template_version_id=1101,
                expected_updated_at=NOW,
                system_prompt_template="RAW_PROMPT_SENTINEL",
                instruction_prompt_template="Analyze",
            ),
        )

    assert captured.value.code == "prompt_conflict"
    assert "RAW_PROMPT_SENTINEL" not in captured.value.message


def test_prompt_write_dtos_forbid_identity_fields_and_bound_raw_utf8_content() -> None:
    with pytest.raises(ValidationError):
        CreatePromptTemplateRequest.model_validate(
            {
                "workflow_stage_id": 12,
                "prompt_template_ownership_scope": "tenant",
                "prompt_template_code": "tenant_analysis",
                "prompt_template_name": "Tenant Analysis",
                "owner_tenant_id": 99,
                "entra_object_id": str(PRINCIPAL.entra_object_id),
            },
            strict=True,
        )
    with pytest.raises(ValidationError):
        SavePromptDraftRequest(
            expected_prompt_template_version_id=1101,
            expected_updated_at=None,
            system_prompt_template="System",
            instruction_prompt_template="Instruction",
        )
    with pytest.raises(ValidationError):
        SavePromptDraftRequest(
            system_prompt_template="é" * 131_073,
            instruction_prompt_template="Instruction",
        )


class StageRouterService:
    async def list_stages(
        self,
        principal: RequestPrincipal,
        *,
        tenant_id: int,
    ) -> PromptStageCatalog:
        assert principal.actor_kind is ActorKind.HUMAN
        assert tenant_id == 7
        return PromptStageCatalog(
            tenant_id=tenant_id,
            items=(
                PromptStage(
                    workflow_stage_id=12,
                    model_workflow="analysis",
                    workflow_execution_mode="one_shot",
                    workflow_stage_code="analyze_sources",
                    workflow_stage_name="Analyze sources",
                    workflow_stage_description=None,
                    workflow_stage_order=10,
                    allowed_variables=(),
                ),
            ),
        )


def test_single_authenticated_router_exposes_bounded_prompt_library_surface() -> None:
    router = create_prompts_router(
        identity_provider=IdentityProvider(
            AuthMode.DEV,
            local_tenant_id=UUID("11111111-1111-1111-1111-111111111111"),
            local_principal_object_id=UUID("22222222-2222-2222-2222-222222222222"),
        ),
        service=cast(PromptService, StageRouterService()),
    )
    api_routes = [route for route in router.routes if isinstance(route, APIRoute)]
    route_methods: set[tuple[str, str]] = set()
    for route in api_routes:
        assert route.methods is not None
        route_methods.update((route.path, method) for method in route.methods)
    assert route_methods == {
        ("/api/v1/tenants/{tenant_id}/prompts/stages", "GET"),
        ("/api/v1/tenants/{tenant_id}/prompts/templates", "GET"),
        ("/api/v1/tenants/{tenant_id}/prompts/templates", "POST"),
        (
            "/api/v1/tenants/{tenant_id}/prompts/templates/{prompt_template_id}",
            "GET",
        ),
        (
            "/api/v1/tenants/{tenant_id}/prompts/templates/{prompt_template_id}",
            "PUT",
        ),
        (
            "/api/v1/tenants/{tenant_id}/prompts/templates/{prompt_template_id}/draft",
            "PUT",
        ),
        (
            "/api/v1/tenants/{tenant_id}/prompts/templates/{prompt_template_id}/versions/"
            "{prompt_template_version_id}/publish",
            "POST",
        ),
        (
            "/api/v1/tenants/{tenant_id}/prompts/templates/{prompt_template_id}/versions/"
            "{prompt_template_version_id}/retire",
            "POST",
        ),
        (
            "/api/v1/tenants/{tenant_id}/prompts/models/{model_id}/assignments",
            "GET",
        ),
        (
            "/api/v1/tenants/{tenant_id}/prompts/models/{model_id}/assignments/{workflow_stage_id}",
            "PUT",
        ),
    }
    app = FastAPI()
    app.include_router(router)

    with TestClient(app) as client:
        response = client.get("/api/v1/tenants/7/prompts/stages")
        rejected_owner = client.post(
            "/api/v1/tenants/7/prompts/templates",
            json={
                "workflow_stage_id": 12,
                "prompt_template_ownership_scope": "tenant",
                "prompt_template_code": "tenant_analysis",
                "prompt_template_name": "Tenant Analysis",
                "owner_tenant_id": 99,
            },
        )

    assert response.status_code == 200
    assert response.json()["items"][0]["workflow_stage_code"] == "analyze_sources"
    assert rejected_owner.status_code == 422


@dataclass(frozen=True, slots=True)
class _DatabasePromptContext:
    tenant_id: int
    model_id: int
    workflow_stage_id: int
    entra_tenant_id: UUID
    entra_object_id: UUID


def _required_id(row: dict[str, Any] | None, field: str) -> int:
    assert row is not None
    value = row[field]
    assert isinstance(value, int) and not isinstance(value, bool) and value > 0
    return value


def _seed_database_prompt_context(
    database: DisposablePostgres,
) -> _DatabasePromptContext:
    suffix = uuid4().hex[:12]
    entra_tenant_id = uuid4()
    entra_object_id = uuid4()
    with database.connect_owner() as connection:
        project_id = _required_id(
            connection.execute(
                """
                INSERT INTO core.project (project_code, project_name)
                VALUES (%s, %s)
                RETURNING project_id
                """,
                (f"WEB_PROMPT_PROJECT_{suffix}", f"Web Prompt Project {suffix}"),
            ).fetchone(),
            "project_id",
        )
        tenant_id = _required_id(
            connection.execute(
                """
                INSERT INTO core.tenant (
                    project_id,
                    tenant_code,
                    tenant_name,
                    tenant_catalog,
                    gds_admin_catalog
                ) VALUES (%s, %s, %s, %s, %s)
                RETURNING tenant_id
                """,
                (
                    project_id,
                    f"WEB_PROMPT_TENANT_{suffix}",
                    f"Web Prompt Tenant {suffix}",
                    f"web_prompt_{suffix}",
                    f"web_prompt_admin_{suffix}",
                ),
            ).fetchone(),
            "tenant_id",
        )
        model_id = _required_id(
            connection.execute(
                """
                INSERT INTO model.model (tenant_id, model_name)
                VALUES (%s, %s)
                RETURNING model_id
                """,
                (tenant_id, f"Web Prompt Model {suffix}"),
            ).fetchone(),
            "model_id",
        )
        workflow_stage_id = _required_id(
            connection.execute(
                """
                INSERT INTO application.workflow_stage (
                    model_workflow,
                    workflow_execution_mode,
                    workflow_stage_code,
                    workflow_stage_name,
                    workflow_stage_order,
                    workflow_stage_is_agentic
                )
                SELECT 'analysis',
                       'one_shot',
                       %s,
                       %s,
                       coalesce(max(stage.workflow_stage_order), 0) + 1,
                       TRUE
                  FROM application.workflow_stage AS stage
                 WHERE stage.model_workflow = 'analysis'
                   AND stage.workflow_execution_mode = 'one_shot'
                RETURNING workflow_stage_id
                """,
                (f"web_prompt_{suffix}", f"Web Prompt Stage {suffix}"),
            ).fetchone(),
            "workflow_stage_id",
        )
        connection.execute(
            """
            INSERT INTO application.workflow_stage_variable (
                workflow_stage_id,
                workflow_stage_variable_name,
                workflow_stage_variable_resolver_key,
                workflow_stage_variable_data_type,
                workflow_stage_variable_is_required,
                workflow_stage_variable_description,
                workflow_stage_variable_order
            ) VALUES (%s, 'stage_context', 'stage_context', 'json', TRUE, %s, 10)
            """,
            (workflow_stage_id, "Governed test context"),
        )
        principal_id = _required_id(
            connection.execute(
                """
                INSERT INTO security.principal (
                    principal_type,
                    principal_display_name,
                    principal_email
                ) VALUES ('user', %s, %s)
                RETURNING principal_id
                """,
                (
                    f"Web Prompt Architect {suffix}",
                    f"web_prompt_{suffix}@example.test",
                ),
            ).fetchone(),
            "principal_id",
        )
        connection.execute(
            """
            INSERT INTO security.entra_principal_identity (
                principal_id,
                principal_type,
                entra_tenant_id,
                entra_object_id
            ) VALUES (%s, 'user', %s, %s)
            """,
            (principal_id, entra_tenant_id, entra_object_id),
        )
        connection.execute(
            """
            INSERT INTO security.tenant_principal_access (
                tenant_id,
                principal_id,
                tenant_role,
                granted_by_principal_id
            ) VALUES (%s, %s, 'architect', %s)
            """,
            (tenant_id, principal_id, principal_id),
        )
        connection.execute(
            """
            INSERT INTO security.tenant_lock (
                tenant_id,
                locked_by_principal_id,
                tenant_lock_purpose,
                tenant_lock_expires_time
            ) VALUES (
                %s,
                %s,
                'Web Prompt integration test',
                CURRENT_TIMESTAMP + INTERVAL '30 minutes'
            )
            """,
            (tenant_id, principal_id),
        )
    return _DatabasePromptContext(
        tenant_id=tenant_id,
        model_id=model_id,
        workflow_stage_id=workflow_stage_id,
        entra_tenant_id=entra_tenant_id,
        entra_object_id=entra_object_id,
    )


@pytest.mark.asyncio
async def test_prompt_library_round_trip_uses_disposable_database_web_role(
    web_postgres_database: DisposablePostgres,
) -> None:
    context = _seed_database_prompt_context(web_postgres_database)
    database = WebPostgresDatabase(
        dsn=web_postgres_database.web_runtime_dsn(),
        pool_min=1,
        pool_max=1,
        pool_timeout_seconds=5,
    )
    service = DatabasePromptService(
        database=database,
        authorizer=AuthorizationService(),
        cursor_signing_key=b"development-only-key-32-bytes-long",
    )
    principal = RequestPrincipal(
        actor_kind=ActorKind.HUMAN,
        entra_tenant_id=context.entra_tenant_id,
        entra_object_id=context.entra_object_id,
    )

    await database.open()
    try:
        stages = await service.list_stages(principal, tenant_id=context.tenant_id)
        created = await service.create_template(
            principal,
            tenant_id=context.tenant_id,
            body=CreatePromptTemplateRequest(
                workflow_stage_id=context.workflow_stage_id,
                prompt_template_ownership_scope="tenant",
                prompt_template_code=f"web_prompt_{uuid4().hex[:12]}",
                prompt_template_name="Web Prompt Integration",
            ),
        )
        draft = await service.save_draft(
            principal,
            tenant_id=context.tenant_id,
            prompt_template_id=created.prompt_template_id,
            body=SavePromptDraftRequest(
                system_prompt_template="System {{future_variable}}",
                instruction_prompt_template="Instruction {{stage_context}}",
            ),
        )
        published = await service.publish_version(
            principal,
            tenant_id=context.tenant_id,
            prompt_template_id=created.prompt_template_id,
            prompt_template_version_id=draft.prompt_template_version_id,
        )
        page = await service.list_templates(
            principal,
            tenant_id=context.tenant_id,
            filters=PromptTemplateFilters(version_status="published"),
            page_size=50,
            cursor=None,
        )
        detail = await service.read_template(
            principal,
            tenant_id=context.tenant_id,
            prompt_template_id=created.prompt_template_id,
        )
        assigned = await service.set_model_assignment(
            principal,
            tenant_id=context.tenant_id,
            model_id=context.model_id,
            workflow_stage_id=context.workflow_stage_id,
            body=SetModelPromptAssignmentRequest(
                prompt_template_version_id=published.prompt_template_version_id,
            ),
        )
        listed_assignments = await service.list_model_assignments(
            principal,
            tenant_id=context.tenant_id,
            model_id=context.model_id,
        )
        assert assigned.model_assignment is not None
        cleared = await service.set_model_assignment(
            principal,
            tenant_id=context.tenant_id,
            model_id=context.model_id,
            workflow_stage_id=context.workflow_stage_id,
            body=SetModelPromptAssignmentRequest(
                prompt_template_version_id=None,
                expected_prompt_assignment_id=(
                    assigned.model_assignment.prompt_assignment_id
                ),
            ),
        )
        retired = await service.retire_version(
            principal,
            tenant_id=context.tenant_id,
            prompt_template_id=created.prompt_template_id,
            prompt_template_version_id=published.prompt_template_version_id,
        )
        updated = await service.update_template(
            principal,
            tenant_id=context.tenant_id,
            prompt_template_id=created.prompt_template_id,
            body=UpdatePromptTemplateRequest(
                prompt_template_name="Web Prompt Integration Retired",
                prompt_template_description=None,
                is_active=False,
                expected_updated_at=created.updated_at,
            ),
        )
    finally:
        await database.close()

    matching_stage = next(
        stage
        for stage in stages.items
        if stage.workflow_stage_id == context.workflow_stage_id
    )
    assert [variable.name for variable in matching_stage.allowed_variables] == [
        "stage_context"
    ]
    assert [item.prompt_template_id for item in page.items] == [
        created.prompt_template_id
    ]
    assert detail.versions[0].system_prompt_template == "System {{future_variable}}"
    matching_assignment = next(
        item
        for item in listed_assignments.items
        if item.workflow_stage_id == context.workflow_stage_id
    )
    assert matching_assignment.effective_source == "model_default"
    assert cleared.effective_source == "none"
    assert retired.prompt_template_version_status == "retired"
    assert updated.is_active is False
