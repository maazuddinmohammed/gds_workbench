"""Run creation reports stable prerequisites without exposing database diagnostics."""

# Shared fixture transaction provides governed authorization without a database.
from typing import Any, LiteralString
from uuid import UUID

import pytest
from fastapi.testclient import TestClient
from gds_etl_workbench.adapters.auth.identity import IdentityProvider
from gds_etl_workbench.application.authorization import AuthorizationService
from gds_etl_workbench.configuration import AuthMode
from gds_workbench_api.capabilities import load_default_agent_capabilities
from gds_workbench_api.features.workflows.commands import DatabaseWorkflowCommandService
from gds_workbench_api.main import create_app

from tests.web_backend.test_workflow_commands import (
    MappingWorkflowCommandDatabase,
    MappingWorkflowCommandTransaction,
)


@pytest.mark.parametrize(
    "database_message,public_code",
    [
        (
            "Selected Code Generation target has no active applied SQL Mapping",
            "code_mapping_incomplete",
        ),
        ("Selected Code Generation System is unavailable", "code_system_unavailable"),
        (
            "Selected Code Generation target lacks complete applied SQL Mapping",
            "code_mapping_incomplete",
        ),
        (
            "No usable prompt is assigned to Workflow Stage sql_generation",
            "workflow_prompt_unavailable",
        ),
        ("Code Generation has no eligible target set", "code_no_eligible_targets"),
        ("private diagnostic sentinel: database connection failed", "dependency_unavailable"),
    ],
)
def test_code_creation_reports_safe_prerequisites_over_http(
    database_message: str,
    public_code: str,
) -> None:
    class PrerequisiteTransaction(MappingWorkflowCommandTransaction):
        async def fetch_one(
            self,
            query: LiteralString,
            parameters: tuple[Any, ...] = (),
        ) -> dict[str, Any] | None:
            if "application.create_workflow_run" in query:
                raise RuntimeError(database_message)
            return await super().fetch_one(query, parameters)

    service = DatabaseWorkflowCommandService(
        database=MappingWorkflowCommandDatabase(PrerequisiteTransaction()),
        authorizer=AuthorizationService(),
        agent_capability_registry=load_default_agent_capabilities(),
    )
    app = create_app(
        identity_provider=IdentityProvider(
            AuthMode.DEV,
            local_tenant_id=UUID("11111111-1111-1111-1111-111111111111"),
            local_principal_object_id=UUID("22222222-2222-2222-2222-222222222222"),
        ),
        workflow_command_service=service,
    )
    with TestClient(app) as client:
        response = client.post(
            "/api/v1/tenants/7/models/18/runs",
            headers={"Idempotency-Key": "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb"},
            json={
                "expected_model_revision": 4,
                "model_workflow": "code_generation",
                "selected_entity_ids": [101],
                "selected_system_codes": ["CRM"],
                "modeled_entity_type": "logical_entity",
                "code_generation_coverage_mode": "selected_targets",
            },
        )
    assert response.status_code == (503 if public_code == "dependency_unavailable" else 400)
    error = response.json()["error"]
    assert error["code"] == public_code
    assert database_message not in response.text
    assert error["retryable"] == (public_code == "dependency_unavailable")
    assert str(UUID(error["correlation_id"])) == response.headers["X-Correlation-ID"]
