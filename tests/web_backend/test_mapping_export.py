from io import BytesIO
from typing import Any
from unittest.mock import AsyncMock, MagicMock
from uuid import UUID

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from gds_etl_workbench.adapters.auth.identity import IdentityProvider
from gds_etl_workbench.application.authorization import AuthorizationService
from gds_etl_workbench.configuration import AuthMode
from gds_etl_workbench.domain.authorization import RequestPrincipal, ToolPolicy
from gds_etl_workbench.domain.errors import InvalidRequestError
from gds_etl_workbench.infrastructure.postgres import ReadIsolation
from gds_workbench_api.features.mapping.read_contracts import MappingEntityType
from gds_workbench_api.features.mapping.read_router import create_mapping_review_router
from gds_workbench_api.features.mapping.read_service import (
    DatabaseMappingReviewService,
    MappingReadDatabase,
)
from gds_workbench_api.features.models import ModelRevisionConflictError
from openpyxl import load_workbook


def setup_export(
    *,
    revision: int = 4,
    rows: int = 2,
    size: int = 100,
    template: str | None = None,
    entities_count: int = 1,
) -> tuple[DatabaseMappingReviewService, MagicMock, MagicMock, MagicMock]:
    transaction = MagicMock()
    transaction.fetch_one = AsyncMock(
        side_effect=[
            {
                "model_revision": revision,
                "model_name": "Customer model",
                "tenant_name": "Demo",
            },
            {"rows": rows, "document_bytes": size},
        ]
    )
    transaction.fetch_all = AsyncMock(
        side_effect=[
            [
                {
                    "mapping_object_id": 81,
                    "modeled_entity_id": 41,
                    "modeled_entity_schema_name": "silver",
                    "modeled_entity_name": "Customer",
                    "definition": "Customer records",
                    "classification": "master",
                    "object_dependency_order": 2,
                    "system_code": "CRM",
                    "document_bytes": 100,
                    "output_template_code": template,
                }
            ]
            * entities_count,
            [
                {
                    "mapping_object_id": 81,
                    "document": {
                        "source_tables": [
                            {"object_schema": "bronze", "object_name": "Customer"}
                        ],
                        "filter_criteria": "active = true",
                        "sample_query": "SELECT 1",
                    },
                }
            ],
            [
                {
                    "mapping_object_id": 81,
                    "ordinal_position": 1,
                    "attribute_name": "Name",
                    "data_type": "STRING",
                    "is_nullable": True,
                    "is_natural_key": False,
                    "is_surrogate_key": False,
                    "output_template_code": None,
                    "document": {
                        "transformation_logic": "TRIM(Name)",
                        "default_record": None,
                        "source_columns": [
                            {
                                "entity_schema_name": "silver",
                                "entity_name": "Source",
                                "attribute_name": "Name",
                            }
                        ],
                    },
                },
                {
                    "mapping_object_id": 81,
                    "ordinal_position": 2,
                    "attribute_name": "ID",
                    "data_type": "BIGINT",
                    "is_nullable": False,
                    "is_natural_key": False,
                    "is_surrogate_key": True,
                    "output_template_code": None,
                    "document": None,
                },
            ],
        ]
    )
    database = MagicMock(spec=MappingReadDatabase)
    database.read_transaction.return_value.__aenter__.return_value = transaction
    authorizer = MagicMock(spec=AuthorizationService)
    service = DatabaseMappingReviewService(
        database=database, authorizer=authorizer, cursor_signing_key=b"test-key"
    )
    return service, database, transaction, authorizer


@pytest.mark.parametrize(
    "layer,zone", [("logical_entity", "Silver"), ("dimensional_entity", "Gold")]
)
async def test_exports_saved_mapping_under_one_authorized_repeatable_read(
    layer: MappingEntityType, zone: str
) -> None:
    service, database, transaction, authorizer = setup_export()
    principal = MagicMock(spec=RequestPrincipal)
    download = await service.export_workbook(
        principal,
        tenant_id=7,
        model_id=18,
        entity_type=layer,
        source_system_code=" CRM ",
        expected_model_revision=4,
    )
    authorizer.authorize_tenant.assert_awaited_once_with(
        transaction, principal, tenant_id=7, model_id=18, policy=ToolPolicy.TENANT_READ
    )
    database.read_transaction.assert_called_once_with(
        isolation=ReadIsolation.REPEATABLE_READ
    )
    assert transaction.fetch_all.call_args_list[0].args[1] == (7, 18, layer, "crm", 201)
    assert "model.tenant_id = %s" in transaction.fetch_all.call_args_list[0].args[0]
    assert transaction.fetch_all.call_args_list[1].args[1] == (18, [81])
    workbook = load_workbook(BytesIO(download.content))
    try:
        sheet = workbook["Customer"]
        assert sheet["B4"].value == zone
        assert sheet["B10"].value == "bronze|Customer"
        assert sheet["G15"].value == "TRIM(Name)"
        assert sheet["I15"].value == "silver|Source|Name"
        assert sheet["G16"].value is None  # Unauthored columns stay blank.
        assert sheet["D16"].value is True
        assert sheet["F16"].value is True
    finally:
        workbook.close()


async def test_export_authorization_precedes_all_record_reads() -> None:
    service, _, transaction, authorizer = setup_export()
    authorizer.authorize_tenant.side_effect = PermissionError()
    with pytest.raises(PermissionError):
        await service.export_workbook(
            MagicMock(),
            tenant_id=7,
            model_id=18,
            entity_type="logical_entity",
            source_system_code="CRM",
            expected_model_revision=4,
        )
    transaction.fetch_one.assert_not_awaited()
    transaction.fetch_all.assert_not_awaited()


@pytest.mark.parametrize(
    "settings,error,reads",
    [
        ({"revision": 5}, ModelRevisionConflictError, 0),
        ({"entities_count": 0}, InvalidRequestError, 1),
        ({"entities_count": 201}, InvalidRequestError, 1),
        ({"rows": 50001}, InvalidRequestError, 1),
        ({"size": 17 * 1024 * 1024}, InvalidRequestError, 1),
        ({"template": "custom_mapping"}, InvalidRequestError, 3),
    ],
)
async def test_export_rejects_stale_empty_oversized_or_uninterpretable_records(
    settings: dict[str, Any], error: type[Exception], reads: int
):
    service, _, transaction, _ = setup_export(**settings)
    with pytest.raises(error):
        await service.export_workbook(
            MagicMock(),
            tenant_id=7,
            model_id=18,
            entity_type="logical_entity",
            source_system_code="CRM",
            expected_model_revision=4,
        )
    assert transaction.fetch_all.await_count == reads


def test_mapping_export_route_streams_only_download_with_strict_request() -> None:
    service, _, _, _ = setup_export()
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
    with TestClient(app) as client:
        path = "/api/v1/tenants/7/models/18/mapping/export"
        command = {
            "entity_type": "dimensional_entity",
            "source_system_code": "CRM",
            "expected_model_revision": 4,
        }
        for patch in (
            {"expected_model_revision": 0},
            {"source_system_code": " "},
            {"entity_type": "invalid"},
            {"extra": 1},
        ):
            assert client.post(path, json={**command, **patch}).status_code == 422
        response = client.post(path, json=command)
        assert response.status_code == 200
        assert response.headers["cache-control"] == "no-store"
        assert response.headers["x-content-type-options"] == "nosniff"
        assert response.headers["content-type"].endswith("spreadsheetml.sheet")
        assert (
            'filename="gds_mapping_dimensional__model_18__r4.xlsx"'
            in response.headers["content-disposition"]
        )
        assert response.content.startswith(b"PK")
