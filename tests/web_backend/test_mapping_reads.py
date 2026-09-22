from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock
from uuid import UUID

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from gds_etl_workbench.adapters.auth.identity import IdentityProvider
from gds_etl_workbench.application.authorization import AuthorizationService
from gds_etl_workbench.configuration import AuthMode
from gds_etl_workbench.domain.authorization import ToolPolicy
from gds_etl_workbench.domain.errors import InvalidRequestError
from gds_workbench_api.features.mapping.read_router import create_mapping_review_router
from gds_workbench_api.features.mapping.read_service import (
    DatabaseMappingReviewService,
    MappingReadDatabase,
)


def test_attribute_reads_scope_sql_and_pagination_to_the_parent_object() -> None:
    row = {
        "mapping_attribute_id": 91,
        "mapping_object_id": 81,
        "target": {
            "object": {
                "object_id": 501,
                "tenant_id": 7,
                "tenant_code": "DEMO",
                "tenant_name": "Demo",
                "system_id": 2,
                "system_code": "CRM",
                "system_name": "CRM",
                "connection_id": 3,
                "connection_code": "DEMO",
                "object_schema": "silver",
                "object_name": "customer",
                "zone_code": "silver",
            },
            "attribute_id": 601,
            "attribute_name": "name",
            "attribute_ordinal_position": 1,
            "attribute_data_type": "string",
        },
        "source": {
            "entity": {"entity_type": "logical_entity", "entity_id": 41, "entity_name": "Customer"},
            "attribute_id": 51,
            "attribute_name": "name",
        },
        "source_system": {"system_id": 2, "system_code": "CRM", "system_name": "CRM"},
        "status": "active",
        "is_locked": False,
        "updated_at": datetime(2026, 9, 1, tzinfo=UTC),
    }
    transaction = MagicMock()
    transaction.fetch_one = AsyncMock(return_value={"model_revision": 4})
    transaction.fetch_all = AsyncMock(
        side_effect=[
            [row, {**row, "mapping_attribute_id": 92}],
            [{**row, "mapping_attribute_id": 92}],
        ]
    )
    database = MagicMock(spec=MappingReadDatabase)
    database.read_transaction.return_value.__aenter__.return_value = transaction
    authorizer = MagicMock(spec=AuthorizationService)
    service = DatabaseMappingReviewService(
        database=database,
        authorizer=authorizer,
        cursor_signing_key=b"mapping-read-test-key",
    )
    app = FastAPI()
    app.include_router(
        create_mapping_review_router(
            identity_provider=IdentityProvider(
                AuthMode.DEV,
                local_tenant_id=UUID("11111111-1111-1111-1111-111111111111"),
                local_principal_object_id=UUID("22222222-2222-2222-2222-222222222222"),
            ),
            service=service,
        )
    )
    path = "/api/v1/tenants/7/models/18/mapping/attributes"
    with TestClient(app) as client:
        first = client.get(path, params={"mapping_object_id": 81, "page_size": 1})
        assert first.status_code == 200
        assert [item["mapping_attribute_id"] for item in first.json()["items"]] == [91]
        cursor = first.json()["next_cursor"]
        assert cursor
        second = client.get(
            path, params={"mapping_object_id": 81, "page_size": 1, "cursor": cursor}
        )
        assert second.status_code == 200
        assert [item["mapping_attribute_id"] for item in second.json()["items"]] == [92]
        assert second.json()["next_cursor"] is None
        with pytest.raises(InvalidRequestError):
            client.get(path, params={"mapping_object_id": 82, "page_size": 1, "cursor": cursor})
        for invalid in (0, -1, "invalid"):
            assert client.get(path, params={"mapping_object_id": invalid}).status_code == 422

    assert transaction.fetch_all.await_count == 2
    for offset, call in enumerate(transaction.fetch_all.call_args_list):
        sql, parameters = call.args
        assert "target_model.tenant_id = %s" in sql
        assert "object_mapping.mapping_object_id = %s" in sql
        assert parameters[:2] == (7, 18)
        assert parameters[-4:] == (81, 81, 2, offset)
    assert authorizer.authorize_tenant.await_count == 2
    assert authorizer.authorize_tenant.call_args.kwargs == {
        "tenant_id": 7,
        "model_id": 18,
        "policy": ToolPolicy.TENANT_READ,
    }
