"""Metadata imports accept only server-resolved selections and revision witnesses."""

from typing import Literal
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from gds_etl_workbench.adapters.auth.identity import IdentityProvider
from gds_etl_workbench.configuration import AuthMode
from gds_workbench_api.features.metadata_enrichment.review import (
    ReviewEnrichmentRequest,
    ReviewEnrichmentResult,
)
from gds_workbench_api.main import create_app
from pydantic import ValidationError


@pytest.mark.parametrize("action", ["import", "reimport"])
@pytest.mark.parametrize("record_type", ["object", "attribute"])
def test_import_route_passes_only_selection_and_identity(
    action: Literal["import", "reimport"], record_type: Literal["object", "attribute"]
) -> None:
    identity = IdentityProvider(
        AuthMode.DEV, local_tenant_id=uuid4(), local_principal_object_id=uuid4()
    )
    service = AsyncMock()
    service.review_records.return_value = ReviewEnrichmentResult.model_validate(
        {
            "review_event_id": 1,
            "action_count": 0,
            "records": [
                {
                    "record_id": 3,
                    "review_revision": "a" * 64,
                    "is_active": True,
                    "is_locked": False,
                }
            ],
        }
    )
    document = {
        "expected_project_revision": 4,
        "record_type": record_type,
        "action": action,
        "records": [{"record_id": 3, "expected_revision": "a" * 64}],
    }
    key = uuid4()
    with TestClient(
        create_app(identity_provider=identity, enrichment_review_service=service)
    ) as client:
        response = client.post(
            "/api/v1/tenants/1/projects/2/metadata-enrichment/review",
            json=document,
            headers={"Idempotency-Key": str(key)},
        )
    assert response.status_code == 200
    assert response.json()["action_count"] == 0
    service.review_records.assert_awaited_once_with(
        identity.authenticate(None),
        tenant_id=1,
        project_id=2,
        command=ReviewEnrichmentRequest.model_validate(document),
        idempotency_key=key,
    )


@pytest.mark.parametrize("action", ["import", "reimport"])
@pytest.mark.parametrize(
    "patch",
    [
        {"description": "Browser-supplied source"},
        {"description": None},
        {"attribute_inferred_data_type": "STRING"},
        {"is_pii": True},
        {"expected_revision": "bad"},
        {"record_id": 0},
    ],
)
def test_import_rejects_browser_values_and_invalid_witnesses(
    action: str, patch: dict[str, object]
) -> None:
    with pytest.raises(ValidationError):
        ReviewEnrichmentRequest.model_validate(
            {
                "expected_project_revision": 1,
                "record_type": "attribute",
                "action": action,
                "records": [{"record_id": 3, "expected_revision": "a" * 64, **patch}],
            }
        )


@pytest.mark.parametrize("count", [0, 2, 201])
def test_import_rejects_empty_duplicate_or_oversized_selections(count: int) -> None:
    with pytest.raises(ValidationError):
        ReviewEnrichmentRequest.model_validate(
            {
                "expected_project_revision": 1,
                "record_type": "object",
                "action": "import",
                "records": [{"record_id": 3, "expected_revision": "a" * 64}] * count,
            }
        )
