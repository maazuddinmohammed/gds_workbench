"""The web execute boundary starts exactly the fixed enrichment workflow."""

from datetime import UTC, datetime
from unittest.mock import AsyncMock
from uuid import UUID

import pytest
from fastapi.testclient import TestClient
from gds_etl_workbench.adapters.auth.identity import IdentityProvider
from gds_etl_workbench.configuration import AuthMode
from gds_etl_workbench.domain.authorization import ActorKind, RequestPrincipal
from gds_workbench_api.features.metadata_enrichment.service import (
    DatabaseMetadataEnrichmentExecutor,
)
from gds_workbench_api.features.workflows.authoring.lifecycle import (
    AgentWorkflowRunStart,
)
from gds_workbench_api.main import create_app


@pytest.mark.parametrize("changed", [True, False])
def test_web_start_uses_governed_fixed_target_and_supports_retry(changed: bool) -> None:
    principal = RequestPrincipal(
        actor_kind=ActorKind.HUMAN,
        entra_tenant_id=UUID("11111111-1111-1111-1111-111111111111"),
        entra_object_id=UUID("22222222-2222-2222-2222-222222222222"),
    )
    lifecycle = AsyncMock()
    lifecycle.start.return_value = AgentWorkflowRunStart(
        changed=changed,
        workflow_run_id=71,
        workflow_run_state="running",
        started_at=datetime(2026, 9, 5, tzinfo=UTC),
        model_revision=4,
    )
    executor = DatabaseMetadataEnrichmentExecutor(
        repository=AsyncMock(),
        agent_executor=AsyncMock(),
        lifecycle=lifecycle,
    )
    app = create_app(
        identity_provider=IdentityProvider(
            AuthMode.DEV,
            local_tenant_id=principal.entra_tenant_id,
            local_principal_object_id=principal.entra_object_id,
        ),
        metadata_enrichment_workflow_service=executor,
    )
    route = "/api/v1/tenants/2/models/3/metadata-enrichment/runs/71/execute"
    with TestClient(app) as client:
        response = client.post(
            route,
            json={
                "execution_mode": "one_shot",
                "expected_model_revision": 4,
            },
        )
        assert response.status_code == (202 if changed else 200)
        assert response.json()["workflow_run_id"] == 71
        for invalid in (
            {"execution_mode": "tool_assisted", "expected_model_revision": 4},
            {"execution_mode": "one_shot", "expected_model_revision": 0},
            {"execution_mode": "one_shot", "expected_model_revision": 4, "actor_id": 9},
        ):
            assert client.post(route, json=invalid).status_code == 422
    lifecycle.start.assert_awaited_once_with(
        principal,
        tenant_id=2,
        model_id=3,
        workflow_run_id=71,
        expected_workflow="metadata_enrichment",
        expected_execution_mode="one_shot",
        expected_model_revision=4,
    )


@pytest.mark.parametrize(
    "patch",
    [
        {"selected_object_ids": [1, 2]},
        {"selected_object_ids": [2]},
        {"model_workflow": "logical"},
        {"workflow_execution_mode": "tool_assisted"},
        {"description_targets": []},
        {
            "description_targets": [
                {"object_id": 1, "attribute_id": None, "expected_revision": "a" * 64}
            ]
            * 2
        },
        {
            "description_targets": [
                {"object_id": 1, "attribute_id": None, "expected_revision": "a" * 64},
                {"object_id": 1, "attribute_id": 2, "expected_revision": "a" * 64},
            ]
        },
        {
            "selected_object_ids": [1, 2],
            "description_targets": [
                {"object_id": 1, "attribute_id": 3, "expected_revision": "a" * 64},
                {"object_id": 2, "attribute_id": 4, "expected_revision": "a" * 64},
            ],
        },
        {"description_targets": [{"object_id": 1, "attribute_id": None}]},
        {
            "description_targets": [
                {
                    "object_id": 1,
                    "attribute_id": -1,
                    "expected_revision": "a" * 64,
                }
            ]
        },
        {
            "description_targets": [
                {
                    "object_id": 1,
                    "attribute_id": None,
                    "expected_revision": "bad",
                }
            ]
        },
    ],
)
def test_regeneration_requires_exact_scope_and_current_metadata_revision(
    patch: dict[str, object],
) -> None:
    from gds_workbench_api.features.workflows.commands.contracts import (
        CreateWorkflowRunRequest,
    )
    from pydantic import ValidationError

    document: dict[str, object] = {
        "expected_model_revision": 4,
        "model_workflow": "metadata_enrichment",
        "workflow_execution_mode": "one_shot",
        "selected_object_ids": [1],
        "description_targets": [
            {
                "object_id": 1,
                "attribute_id": None,
                "expected_revision": "a" * 64,
            }
        ],
    }
    assert CreateWorkflowRunRequest.model_validate(document).description_targets is not None
    with pytest.raises(ValidationError):
        CreateWorkflowRunRequest.model_validate(document | patch)
