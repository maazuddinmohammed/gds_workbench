"""Removed Mapping System order cannot be read, authored, reviewed, or staged."""

from typing import cast
from unittest.mock import MagicMock
from uuid import UUID

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from gds_etl_workbench.adapters.auth.identity import IdentityProvider
from gds_etl_workbench.configuration import AuthMode

from gds_workbench_api.features.mapping.read_router import create_mapping_review_router
from gds_workbench_api.features.mapping.read_service import MappingReviewService
from gds_workbench_api.features.model_change_sets.router import (
    ModelChangeSetService,
    create_model_change_sets_router,
)
from gds_workbench_api.features.workflows.authoring.prompt_inputs import get_prompt_input_contract


def test_removed_system_order_routes_and_dataset_fail_before_service_access() -> None:
    identity = IdentityProvider(
        AuthMode.DEV,
        local_tenant_id=UUID("11111111-1111-1111-1111-111111111111"),
        local_principal_object_id=UUID("22222222-2222-2222-2222-222222222222"),
    )
    reads = MagicMock(spec=MappingReviewService)
    commands = MagicMock(spec=ModelChangeSetService)
    app = FastAPI()
    app.include_router(create_mapping_review_router(identity_provider=identity, service=reads))
    app.include_router(
        create_model_change_sets_router(identity_provider=identity, service=commands)
    )
    model = "/api/v1/tenants/7/models/18"
    review = {
        "dataset": "mapping_dependency",
        "record_ids": [1],
        "action": "lock",
        "expected_model_revision": 4,
    }
    with TestClient(app) as client:
        assert client.get(model + "/mapping/dependencies").status_code == 404
        assert client.post(model + "/change-sets/mapping/dependencies", json={}).status_code == 404
        assert (
            client.get(
                model + "/change-sets/review/records",
                params={"dataset": "mapping_dependency", "expected_model_revision": 4},
            ).status_code
            == 422
        )
        assert client.post(model + "/change-sets/review/preview", json=review).status_code == 422
        assert (
            client.post(
                model + "/change-sets/review",
                headers={"Idempotency-Key": "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa"},
                json=review,
            ).status_code
            == 422
        )
        assert (
            client.put(
                model + "/change-sets/bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb/stage",
                headers={"Idempotency-Key": "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa"},
                json={
                    "expected_draft_revision": 1,
                    "changes": [{"dataset": "mapping_dependency", "records": [{}]}],
                },
            ).status_code
            == 422
        )
    assert not reads.mock_calls and not commands.mock_calls


@pytest.mark.parametrize("mode", ("one_shot", "tool_assisted"))
def test_legacy_mapping_system_graph_resolver_is_removed_but_entity_order_remains(
    mode: str,
) -> None:
    prefix = f"workflow.mapping.{mode}.mapping_authoring.inputs."
    assert (
        get_prompt_input_contract(
            model_workflow="mapping",
            workflow_execution_mode=mode,
            stage_code="mapping_authoring",
            resolver_key=prefix + "source_dependencies",
        )
        is None
    )
    contract = get_prompt_input_contract(
        model_workflow="mapping",
        workflow_execution_mode="one_shot",
        stage_code="mapping_authoring",
        resolver_key="workflow.mapping.one_shot.mapping_authoring.inputs.target_dependencies",
    )
    assert contract is not None
    example = cast(dict[str, object], contract.example)
    assert example["nodes"]
