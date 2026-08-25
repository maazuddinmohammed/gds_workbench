from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from typing import Never

from fastapi.testclient import TestClient
from gds_etl_workbench.infrastructure.postgres import (
    ReadinessRecord,
    ReadIsolation,
    ReadTransaction,
    WriteTransaction,
)

from gds_workbench_api.configuration import RuntimeSettings
from gds_workbench_api.runtime import create_runtime_app


class LifecycleDatabase:
    def __init__(self) -> None:
        self.opened = False
        self.closed = False

    async def open(self) -> None:
        self.opened = True

    async def close(self) -> None:
        self.closed = True

    async def readiness(self) -> ReadinessRecord:
        assert self.opened
        return ReadinessRecord(ready=True, code="ready")

    @asynccontextmanager
    async def read_transaction(
        self,
        *,
        isolation: ReadIsolation = ReadIsolation.READ_COMMITTED,
    ) -> AsyncGenerator[ReadTransaction]:
        del isolation
        raise AssertionError("health endpoints must not start a read transaction")
        yield _unreachable()

    @asynccontextmanager
    async def write_transaction(
        self,
        *,
        isolation: ReadIsolation = ReadIsolation.READ_COMMITTED,
    ) -> AsyncGenerator[WriteTransaction]:
        del isolation
        raise AssertionError("health endpoints must not start a write transaction")
        yield _unreachable()


def _unreachable() -> Never:
    raise AssertionError("unreachable")


def test_runtime_factory_owns_the_database_lifecycle() -> None:
    settings = RuntimeSettings.from_environment(
        {
            "GDS_WEB_ENVIRONMENT": "local",
            "GDS_WEB_DATABASE_DSN": "postgresql://fixture.invalid/workbench",
            "GDS_WEB_CURSOR_SIGNING_KEY": "development-only-key-32-bytes-long",
            "GDS_WEB_DATABRICKS_ENVIRONMENT_CODE": "TEST",
            "GDS_WEB_LOCAL_ENTRA_TENANT_ID": "11111111-1111-1111-1111-111111111111",
            "GDS_WEB_LOCAL_PRINCIPAL_OBJECT_ID": (
                "22222222-2222-2222-2222-222222222222"
            ),
        }
    )
    database = LifecycleDatabase()

    app = create_runtime_app(settings=settings, database=database)
    assert (
        "/api/v1/tenants/{tenant_id}/models/{model_id}/scope" in app.openapi()["paths"]
    )
    assert "/api/v1/tenants/{tenant_id}/lock/acquire" in app.openapi()["paths"]
    assert "/api/v1/tenants/{tenant_id}/metadata/datasets" in app.openapi()["paths"]
    assert "/api/v1/tenants/{tenant_id}/metadata-change-sets" in app.openapi()["paths"]
    assert "/api/v1/tenants/{tenant_id}/prompts/stages" in app.openapi()["paths"]
    assert "/api/v1/tenants/{tenant_id}/sql-generation-guides" in app.openapi()["paths"]
    assert "/api/v1/tenants/{tenant_id}/output-templates" in app.openapi()["paths"]
    assert (
        "/api/v1/tenants/{tenant_id}/models/{model_id}/profiling"
        in app.openapi()["paths"]
    )
    assert (
        "/api/v1/tenants/{tenant_id}/models/{model_id}/profiling/runs/{workflow_run_id}/execute"
        in app.openapi()["paths"]
    )
    assert (
        "/api/v1/tenants/{tenant_id}/models/{model_id}/conceptual/objects"
        in app.openapi()["paths"]
    )
    assert (
        "/api/v1/tenants/{tenant_id}/models/{model_id}/analysis/"
        "inference-runs/{workflow_run_id}/execute" in app.openapi()["paths"]
    )
    assert (
        "/api/v1/tenants/{tenant_id}/models/{model_id}/analysis/"
        "validation-runs/{workflow_run_id}/execute" in app.openapi()["paths"]
    )
    assert (
        "/api/v1/tenants/{tenant_id}/models/{model_id}/conceptual/"
        "runs/{workflow_run_id}/execute" in app.openapi()["paths"]
    )
    assert (
        "/api/v1/tenants/{tenant_id}/models/{model_id}/runs/"
        "{workflow_run_id}/draft/apply" in app.openapi()["paths"]
    )
    assert (
        "/api/v1/tenants/{tenant_id}/models/{model_id}/assertions/documents"
        in app.openapi()["paths"]
    )
    assert (
        "/api/v1/tenants/{tenant_id}/models/{model_id}/logical/entities"
        in app.openapi()["paths"]
    )
    assert (
        "/api/v1/tenants/{tenant_id}/models/{model_id}/logical/"
        "runs/{workflow_run_id}/execute" in app.openapi()["paths"]
    )
    assert (
        "/api/v1/tenants/{tenant_id}/models/{model_id}/dimensional/objects"
        in app.openapi()["paths"]
    )
    assert (
        "/api/v1/tenants/{tenant_id}/models/{model_id}/dimensional/"
        "runs/{workflow_run_id}/execute" in app.openapi()["paths"]
    )
    assert (
        "/api/v1/tenants/{tenant_id}/models/{model_id}/mapping/dependencies"
        in app.openapi()["paths"]
    )
    assert (
        "/api/v1/tenants/{tenant_id}/models/{model_id}/mapping/"
        "runs/{workflow_run_id}/execute" in app.openapi()["paths"]
    )
    assert (
        "/api/v1/tenants/{tenant_id}/models/{model_id}/code-generation/targets"
        in app.openapi()["paths"]
    )
    assert (
        "/api/v1/tenants/{tenant_id}/models/{model_id}/code-generation/"
        "runs/{workflow_run_id}/execute" in app.openapi()["paths"]
    )
    assert (
        "/api/v1/tenants/{tenant_id}/models/{model_id}/overview"
        in app.openapi()["paths"]
    )

    with TestClient(app, base_url="http://localhost:8000") as client:
        response = client.get("/readyz")
        assert database.opened is True
        assert database.closed is False

    assert response.status_code == 200
    assert database.closed is True
