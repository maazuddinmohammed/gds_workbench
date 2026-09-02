from __future__ import annotations

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, LiteralString
from uuid import UUID

import pytest
from fastapi.testclient import TestClient
from gds_etl_workbench.adapters.auth.identity import IdentityProvider
from gds_etl_workbench.application.authorization import AuthorizationService
from gds_etl_workbench.configuration import AuthMode
from gds_etl_workbench.domain.authorization import ActorKind, RequestPrincipal
from gds_etl_workbench.domain.errors import InvalidRequestError
from gds_etl_workbench.infrastructure.postgres import ReadIsolation
from gds_etl_workbench.tools.change_sets.model_validation import (
    validation_code_context_digest,
    validation_mapping_context_digest,
)

from gds_workbench_api.features.validation import (
    ValidationEligibleSystem,
    ValidationEligibleSystemCollection,
    ValidationLedger,
    ValidationValidationCheck,
    ValidationValidationGroup,
)
from gds_workbench_api.features.validation.context import (
    _CONTEXT_BOUNDS_SQL,  # pyright: ignore[reportPrivateUsage]
)
from gds_workbench_api.features.validation.read_service import (
    _CURRENT_CONTEXT_SQL,  # pyright: ignore[reportPrivateUsage]
    _LEDGER_GROUPS_SQL,  # pyright: ignore[reportPrivateUsage]
    DatabaseValidationReadService,
    _assemble_ledger_groups,  # pyright: ignore[reportPrivateUsage]
    _ledger_digest_context,  # pyright: ignore[reportPrivateUsage]
)
from gds_workbench_api.features.workflows.authoring.lifecycle import (
    AgentWorkflowRunStart,
)
from gds_workbench_api.main import create_app


def _context_row() -> dict[str, object]:
    return {
        "object_id": 91,
        "modeled_entity_type": "logical_entity",
        "modeled_entity_name": "Customer",
        "tenant_code": "acme",
        "system_code": "warehouse",
        "connection_code": "gold",
        "object_schema": "sales",
        "object_name": "customer",
        "source_system_codes": ["erp"],
        "code_input_digest": "a" * 64,
        "generated_code": [
            {
                "modeled_entity_type": "logical_entity",
                "modeled_entity_name": "Customer",
                "artifact_name": "customer.sql",
                "artifact_type": "transformation_sql",
                "source_system_codes": ["erp"],
                "generated_code_digest": "c" * 64,
                "generated_code_status": "active",
            }
        ],
    }


def _group_row(
    *,
    group_id: int,
    system_id: int,
    system_code: str,
    mapping_digest: str,
    code_digest: str | None,
    active: bool = True,
) -> dict[str, object]:
    return {
        "validation_group_id": group_id,
        "system_id": system_id,
        "system_code": system_code,
        "validation_group_name": "reconciliation",
        "validation_group_description": "Reconcile target counts.",
        "mapping_context_digest": mapping_digest,
        "code_context_digest": code_digest,
        "is_active": active,
    }


def _check_row(*, group_id: int) -> dict[str, object]:
    return {
        "validation_group_id": group_id,
        "validation_check_id": 501,
        "validation_check_name": "counts_match",
        "validation_check_description": None,
        "validation_category_code": "business.reconciliation",
        "validation_severity": "blocking",
        "validation_query_sql": "SELECT count(*) FROM catalog.silver.customer",
        "validation_comparison_query_sql": (
            "SELECT count(*) FROM catalog.gold.dim_customer"
        ),
        "validation_result_data_type": "integer",
        "validation_comparison_operator": "equal",
        "validation_comparison_value_type": "query",
        "validation_comparison_value": None,
        "validation_check_is_active": True,
    }


def test_ledger_currentness_uses_canonical_mapping_and_code_digests() -> None:
    context_rows = [_context_row()]
    contexts, generated = _ledger_digest_context(context_rows)
    mapping_digest = validation_mapping_context_digest(contexts, "erp")
    code_digest = validation_code_context_digest(contexts, generated, "erp")
    assert mapping_digest is not None
    assert code_digest is not None

    groups = _assemble_ledger_groups(
        group_rows=[
            _group_row(
                group_id=41,
                system_id=7,
                system_code="erp",
                mapping_digest=mapping_digest,
                code_digest=code_digest,
            ),
            _group_row(
                group_id=42,
                system_id=8,
                system_code="retired_source",
                mapping_digest="d" * 64,
                code_digest=None,
                active=False,
            ),
        ],
        check_rows=[_check_row(group_id=41)],
        context_rows=context_rows,
    )

    current, retained = groups
    assert current.validation_group_is_current is True
    assert current.mapping_context_is_current is True
    assert current.code_context_is_current is True
    assert [check.validation_check_id for check in current.checks] == [501]
    assert retained.mapping_context_is_current is False
    assert retained.code_context_is_current is False
    assert retained.validation_group_is_current is False


def test_ledger_currentness_normalizes_mixed_case_target_natural_keys() -> None:
    context_row = {
        **_context_row(),
        "tenant_code": "Acme",
        "system_code": "WAREHOUSE",
        "connection_code": "Gold",
        "object_schema": "Sales",
        "object_name": "Customer",
    }
    contexts, generated = _ledger_digest_context([context_row])
    mapping_digest = validation_mapping_context_digest(contexts, "ERP")
    code_digest = validation_code_context_digest(contexts, generated, "erp")
    assert mapping_digest is not None
    assert code_digest is not None

    groups = _assemble_ledger_groups(
        group_rows=[
            _group_row(
                group_id=41,
                system_id=7,
                system_code="ErP",
                mapping_digest=mapping_digest,
                code_digest=code_digest,
            )
        ],
        check_rows=[_check_row(group_id=41)],
        context_rows=[context_row],
    )

    assert groups[0].mapping_context_is_current is True
    assert groups[0].code_context_is_current is True
    assert groups[0].validation_group_is_current is True


def test_ledger_currentness_queries_are_lightweight_and_preflight_bytes() -> None:
    assert "generated.generated_code_content" not in _CURRENT_CONTEXT_SQL
    assert "context.source_context," not in _CURRENT_CONTEXT_SQL
    assert "source_system.source_system_codes" in _CURRENT_CONTEXT_SQL
    assert "octet_length(applied_check.validation_query_sql)" in _CONTEXT_BOUNDS_SQL
    assert "relevant_context.generated_code_bytes" in _CONTEXT_BOUNDS_SQL
    assert "validation_group.is_active" not in _LEDGER_GROUPS_SQL.split(" WHERE ", 1)[1]


def _principal() -> RequestPrincipal:
    return RequestPrincipal(
        actor_kind=ActorKind.HUMAN,
        entra_tenant_id=UUID("11111111-1111-1111-1111-111111111111"),
        entra_object_id=UUID("22222222-2222-2222-2222-222222222222"),
    )


def _authorization_row() -> dict[str, object]:
    return {
        "principal_id": 41,
        "principal_display_name": "Maaz",
        "is_super_admin": False,
        "effective_role": "viewer",
        "authorized": True,
        "denial_code": None,
        "lock_owner_display_name": None,
        "lock_expires_time": None,
    }


class EligibleSystemsTransaction:
    async def fetch_one(
        self,
        query: LiteralString,
        parameters: tuple[Any, ...] = (),
    ) -> dict[str, Any] | None:
        if "security.entra_principal_identity" in query:
            assert parameters[-1] == 7
            return _authorization_row()
        assert "SELECT target_model.model_revision" in query
        assert parameters == (7, 18)
        return {"model_revision": 4}

    async def fetch_all(
        self,
        query: LiteralString,
        parameters: tuple[Any, ...] = (),
    ) -> list[dict[str, Any]]:
        assert "LIMIT 1001" in query
        assert "workflow.list_code_generation_target_context" in query
        assert parameters == (7, 18)
        return [
            {
                "system_id": 9,
                "system_code": "erp",
                "system_name": "ERP",
                "mapping_target_count": 3,
                "current_code_target_count": 2,
                "has_applied_validation": True,
            }
        ]


class EligibleSystemsDatabase:
    @asynccontextmanager
    async def read_transaction(
        self,
        *,
        isolation: ReadIsolation = ReadIsolation.READ_COMMITTED,
    ) -> AsyncGenerator[EligibleSystemsTransaction]:
        assert isolation is ReadIsolation.REPEATABLE_READ
        yield EligibleSystemsTransaction()


@pytest.mark.asyncio
async def test_database_validation_eligible_systems_are_authorized_and_bounded() -> None:
    service = DatabaseValidationReadService(
        database=EligibleSystemsDatabase(),
        authorizer=AuthorizationService(),
    )

    result = await service.list_eligible_systems(
        _principal(),
        tenant_id=7,
        model_id=18,
    )

    assert result.model_revision == 4
    assert [item.system_code for item in result.items] == ["erp"]
    assert result.is_truncated is False


class LedgerTransaction:
    def __init__(self, *, ledger_bytes: int = 4096) -> None:
        self.ledger_bytes = ledger_bytes
        contexts, generated = _ledger_digest_context([_context_row()])
        self.mapping_digest = validation_mapping_context_digest(contexts, "erp")
        self.code_digest = validation_code_context_digest(contexts, generated, "erp")

    async def fetch_one(
        self,
        query: LiteralString,
        parameters: tuple[Any, ...] = (),
    ) -> dict[str, Any] | None:
        if "security.entra_principal_identity" in query:
            return _authorization_row()
        if "SELECT target_model.model_revision" in query:
            return {"model_revision": 4}
        assert "octet_length(validation_check.validation_query_sql)" in query
        assert parameters == (7, 18)
        return {
            "group_count": 1,
            "check_count": 1,
            "ledger_bytes": self.ledger_bytes,
        }

    async def fetch_all(
        self,
        query: LiteralString,
        parameters: tuple[Any, ...] = (),
    ) -> list[dict[str, Any]]:
        assert parameters == (7, 18)
        if "validation_check.validation_query_sql" in query:
            return [_check_row(group_id=41)]
        if "validation_group.validation_group_description" in query:
            assert self.mapping_digest is not None
            return [
                _group_row(
                    group_id=41,
                    system_id=9,
                    system_code="erp",
                    mapping_digest=self.mapping_digest,
                    code_digest=self.code_digest,
                )
            ]
        assert "generated.generated_code_content" not in query
        assert "source_system.source_system_codes" in query
        return [_context_row()]


class LedgerDatabase:
    def __init__(self, *, ledger_bytes: int = 4096) -> None:
        self.transaction = LedgerTransaction(ledger_bytes=ledger_bytes)

    @asynccontextmanager
    async def read_transaction(
        self,
        *,
        isolation: ReadIsolation = ReadIsolation.READ_COMMITTED,
    ) -> AsyncGenerator[LedgerTransaction]:
        assert isolation is ReadIsolation.REPEATABLE_READ
        yield self.transaction


@pytest.mark.asyncio
async def test_database_validation_ledger_preflights_and_computes_currentness() -> None:
    service = DatabaseValidationReadService(
        database=LedgerDatabase(),
        authorizer=AuthorizationService(),
    )

    result = await service.read_ledger(_principal(), tenant_id=7, model_id=18)

    assert result.model_revision == 4
    assert result.groups[0].validation_group_is_current is True
    assert result.groups[0].checks[0].validation_check_id == 501


@pytest.mark.asyncio
async def test_database_validation_ledger_rejects_oversize_before_full_fetch() -> None:
    service = DatabaseValidationReadService(
        database=LedgerDatabase(ledger_bytes=32 * 1024 * 1024 + 1),
        authorizer=AuthorizationService(),
    )

    with pytest.raises(InvalidRequestError, match="bounded size"):
        await service.read_ledger(_principal(), tenant_id=7, model_id=18)


@dataclass
class StaticValidationService:
    async def list_eligible_systems(
        self,
        principal: RequestPrincipal,
        *,
        tenant_id: int,
        model_id: int,
    ) -> ValidationEligibleSystemCollection:
        assert principal.actor_kind is ActorKind.HUMAN
        assert (tenant_id, model_id) == (7, 18)
        return ValidationEligibleSystemCollection(
            model_id=18,
            model_revision=4,
            items=(
                ValidationEligibleSystem(
                    system_id=9,
                    system_code="erp",
                    system_name="ERP",
                    mapping_target_count=3,
                    current_code_target_count=2,
                    has_applied_validation=True,
                ),
            ),
            is_truncated=False,
        )

    async def read_ledger(
        self,
        principal: RequestPrincipal,
        *,
        tenant_id: int,
        model_id: int,
    ) -> ValidationLedger:
        del principal
        assert (tenant_id, model_id) == (7, 18)
        return ValidationLedger(
            model_id=18,
            model_revision=4,
            groups=(
                ValidationValidationGroup(
                    validation_group_id=41,
                    system_id=9,
                    system_code="erp",
                    validation_group_name="reconciliation",
                    validation_group_description=None,
                    mapping_context_is_current=True,
                    code_context_is_current=True,
                    validation_group_is_current=True,
                    is_active=True,
                    checks=(
                        ValidationValidationCheck(
                            validation_check_id=501,
                            validation_check_name="executes",
                            validation_check_description=None,
                            validation_category_code="technical.execution",
                            validation_severity="blocking",
                            validation_query_sql="SELECT 1",
                            validation_comparison_query_sql=None,
                            validation_result_data_type=None,
                            validation_comparison_operator="executes_successfully",
                            validation_comparison_value_type="none",
                            validation_comparison_value=None,
                            is_active=True,
                        ),
                    ),
                ),
            ),
        )


class StaticValidationWorkflow:
    async def start(
        self,
        principal: RequestPrincipal,
        *,
        tenant_id: int,
        model_id: int,
        workflow_run_id: int,
        expected_model_revision: int,
    ) -> AgentWorkflowRunStart:
        del principal
        assert (tenant_id, model_id, workflow_run_id, expected_model_revision) == (
            7,
            18,
            1048,
            4,
        )
        return AgentWorkflowRunStart(
            changed=True,
            workflow_run_id=1048,
            workflow_run_state="running",
            started_at=datetime(2026, 8, 31, 12, 0, tzinfo=UTC),
            model_revision=4,
        )


def _client() -> TestClient:
    return TestClient(
        create_app(
            identity_provider=IdentityProvider(
                AuthMode.DEV,
                local_tenant_id=UUID("11111111-1111-1111-1111-111111111111"),
                local_principal_object_id=UUID("22222222-2222-2222-2222-222222222222"),
            ),
            validation_read_service=StaticValidationService(),
            validation_workflow_service=StaticValidationWorkflow(),
        )
    )


def test_validation_read_routes_publish_exact_frontend_contract() -> None:
    with _client() as client:
        systems = client.get("/api/v1/tenants/7/models/18/validation/systems")
        ledger = client.get("/api/v1/tenants/7/models/18/validation/ledger")

    assert systems.status_code == 200
    assert systems.json()["items"][0]["current_code_target_count"] == 2
    assert ledger.status_code == 200
    assert ledger.json()["groups"][0]["validation_group_is_current"] is True
    assert ledger.json()["groups"][0]["checks"][0]["validation_query_sql"] == "SELECT 1"


def test_validation_execute_route_uses_existing_agent_run_start_contract() -> None:
    with _client() as client:
        response = client.post(
            "/api/v1/tenants/7/models/18/validation/runs/1048/execute",
            json={"expected_model_revision": 4},
        )

    assert response.status_code == 202
    assert response.json()["workflow_run_state"] == "running"
