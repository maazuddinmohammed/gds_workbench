"""Enrichment result reads stay authorized, paginated, and free of sample rows."""

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from copy import deepcopy
from typing import Any, LiteralString
from uuid import UUID

import pytest
from fastapi.testclient import TestClient
from gds_etl_workbench.adapters.auth.identity import IdentityProvider
from gds_etl_workbench.application.authorization import AuthorizationService
from gds_etl_workbench.configuration import AuthMode
from gds_etl_workbench.domain.authorization import ActorKind, RequestPrincipal
from gds_etl_workbench.domain.errors import (
    AuthorizationDeniedError,
    DependencyUnavailableError,
    InvalidRequestError,
)
from gds_etl_workbench.infrastructure.postgres import ReadIsolation
from gds_workbench_api.features.metadata_enrichment.read_service import (
    DatabaseMetadataEnrichmentReadService,
)
from gds_workbench_api.features.workflows.runs import WorkflowRunNotFoundError
from gds_workbench_api.main import create_app


def _principal() -> RequestPrincipal:
    return RequestPrincipal(
        actor_kind=ActorKind.HUMAN,
        entra_tenant_id=UUID("11111111-1111-1111-1111-111111111111"),
        entra_object_id=UUID("22222222-2222-2222-2222-222222222222"),
    )


def _payload() -> dict[str, Any]:
    common = {
        "object_id": 41,
        "object_schema": "sales",
        "object_name": "orders",
        "attribute_name": "order_id",
        "storage_type": "string",
        "attribute_id": 51,
        "field_name": "attribute_inferred_data_type",
        "status": "applied",
        "evidence_method": "source_schema",
        "applied_value": "bigint",
        "sample_count": 0,
    }
    return {
        "tenant_id": 7,
        "model_id": 18,
        "model_revision": 4,
        "workflow_run_id": 1048,
        "workflow_run_state": "completed",
        "total_count": 3,
        "result_count": 3,
        "warning_count": 0,
        "counts": {"applied": 1, "existing": 1, "locked": 1},
        "applied_field_counts": {
            "object_description": 0,
            "attribute_description": 0,
            "attribute_inferred_data_type": 1,
        },
        "results": [
            {**common, "result_id": 101},
            {**common, "result_id": 102, "status": "existing", "applied_value": None},
            {
                **common,
                "result_id": 103,
                "status": "locked",
                "applied_value": None,
                "object_name": None,
                "object_schema": None,
                "attribute_name": None,
                "storage_type": None,
            },
        ],
    }


class ReadTransaction:
    def __init__(self) -> None:
        self.payload = _payload()
        self.authorized = True
        self.route_exists = True
        self.calls: list[tuple[LiteralString, tuple[Any, ...]]] = []

    async def fetch_one(
        self,
        query: LiteralString,
        parameters: tuple[Any, ...] = (),
    ) -> dict[str, Any] | None:
        self.calls.append((query, parameters))
        if "security.entra_principal_identity" in query:
            return {
                "principal_id": 77,
                "principal_display_name": "Reviewer",
                "is_super_admin": False,
                "effective_role": "viewer",
                "authorized": self.authorized,
                "denial_code": None if self.authorized else "authorization_denied",
                "lock_owner_display_name": None,
                "lock_expires_time": None,
            }
        if "SELECT run.workflow_run_id" in query:
            assert "run.tenant_id = %s AND run.model_id = %s" in query
            assert "run.model_workflow = 'metadata_enrichment'" in query
            assert parameters == (7, 18, 1048)
            return {"workflow_run_id": 1048} if self.route_exists else None
        assert "application.get_metadata_enrichment_results" in query
        assert parameters[:4] == (
            _principal().entra_tenant_id,
            _principal().entra_object_id,
            "user",
            1048,
        )
        limit, offset = parameters[-2:]
        payload = deepcopy(self.payload)
        payload["results"] = payload["results"][offset : offset + limit]
        return {"result": payload}

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
        raise AssertionError("Results use one bounded governed read")


class ReadDatabase:
    def __init__(self) -> None:
        self.transaction = ReadTransaction()

    @asynccontextmanager
    async def write_transaction(
        self,
        *,
        isolation: ReadIsolation = ReadIsolation.READ_COMMITTED,
    ) -> AsyncGenerator[ReadTransaction]:
        assert isolation is ReadIsolation.REPEATABLE_READ
        yield self.transaction


def _service(database: ReadDatabase) -> DatabaseMetadataEnrichmentReadService:
    return DatabaseMetadataEnrichmentReadService(
        database=database, authorizer=AuthorizationService()
    )


async def test_enrichment_read_pages_keep_whole_run_summary_and_safe_labels() -> None:
    database = ReadDatabase()
    service = _service(database)
    pages = [
        await service.read_results(
            _principal(),
            tenant_id=7,
            model_id=18,
            workflow_run_id=1048,
            limit=1,
            offset=offset,
        )
        for offset in range(4)
    ]
    assert [page.next_offset for page in pages] == [1, 2, None, None]
    assert [page.result_count for page in pages] == [3, 3, 3, 3]
    assert pages[0].results[0].applied_value == "bigint"
    assert pages[0].results[0].storage_type == "string"
    assert pages[2].results[0].object_name is None
    assert not pages[3].results
    assert all(page.counts == {"applied": 1, "existing": 1, "locked": 1} for page in pages)
    assert "sample_values" not in pages[0].model_dump_json()
    assert all(page.applied_field_counts["attribute_inferred_data_type"] == 1 for page in pages)


async def test_enrichment_read_requires_authorization_before_run_lookup() -> None:
    database = ReadDatabase()
    database.transaction.authorized = False
    with pytest.raises(AuthorizationDeniedError):
        await _service(database).read_results(
            _principal(), tenant_id=7, model_id=18, workflow_run_id=1048
        )
    assert len(database.transaction.calls) == 1


async def test_enrichment_read_rejects_foreign_model_or_wrong_workflow_before_result_function() -> (
    None
):
    database = ReadDatabase()
    database.transaction.route_exists = False
    with pytest.raises(WorkflowRunNotFoundError):
        await _service(database).read_results(
            _principal(), tenant_id=7, model_id=18, workflow_run_id=1048
        )
    assert len(database.transaction.calls) == 2


@pytest.mark.parametrize("limit,offset", [(0, 0), (201, 0), (1, -1), (1, 10_201)])
async def test_enrichment_read_revalidates_page_bounds(limit: int, offset: int) -> None:
    database = ReadDatabase()
    with pytest.raises(InvalidRequestError):
        await _service(database).read_results(
            _principal(),
            tenant_id=7,
            model_id=18,
            workflow_run_id=1048,
            limit=limit,
            offset=offset,
        )
    assert not database.transaction.calls


@pytest.mark.parametrize(
    "malformed",
    ["tenant", "counts", "field_counts", "extra", "samples", "field", "value"],
)
async def test_enrichment_read_rejects_malformed_or_unscoped_database_output(
    malformed: str,
) -> None:
    database = ReadDatabase()
    payload = database.transaction.payload
    if malformed == "tenant":
        payload["tenant_id"] = 999
    elif malformed == "counts":
        payload["counts"]["applied"] = 2
    elif malformed == "field_counts":
        payload["applied_field_counts"]["attribute_inferred_data_type"] = 2
    elif malformed == "extra":
        payload["results"][0]["sample_values"] = ["must-never-return"]
    elif malformed == "samples":
        payload["results"][0]["sample_count"] = 51
    elif malformed == "field":
        payload["results"][0]["field_name"] = "object_description"
    else:
        payload["results"][0]["applied_value"] = "é" * 1_001
    with pytest.raises(DependencyUnavailableError):
        await _service(database).read_results(
            _principal(), tenant_id=7, model_id=18, workflow_run_id=1048
        )


def test_enrichment_result_router_publishes_paginated_contract_and_validates_inputs() -> None:
    database = ReadDatabase()
    principal = _principal()
    app = create_app(
        identity_provider=IdentityProvider(
            AuthMode.DEV,
            local_tenant_id=principal.entra_tenant_id,
            local_principal_object_id=principal.entra_object_id,
        ),
        metadata_enrichment_read_service=_service(database),
    )
    with TestClient(app) as client:
        response = client.get(
            "/api/v1/tenants/7/models/18/runs/1048/metadata-enrichment?limit=1&offset=1"
        )
        assert response.status_code == 200
        assert response.json()["results"][0]["status"] == "existing"
        assert response.json()["next_offset"] == 2
        assert response.json()["result_count"] == 3
        for query in ("limit=201", "offset=-1", "offset=10201"):
            assert (
                client.get(
                    f"/api/v1/tenants/7/models/18/runs/1048/metadata-enrichment?{query}"
                ).status_code
                == 422
            )
        database.transaction.route_exists = False
        missing = client.get("/api/v1/tenants/7/models/18/runs/1048/metadata-enrichment")
        assert missing.status_code == 404
        assert missing.json()["error"]["code"] == "workflow_run_not_found"
