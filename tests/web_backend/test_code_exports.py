"""Bulk SQL exports retain all active files with bounded, safe provenance."""

import json
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from io import BytesIO
from typing import Any, LiteralString
from uuid import UUID
from zipfile import ZIP_STORED, ZipFile

import pytest
from fastapi.testclient import TestClient
from gds_etl_workbench.application.authorization import AuthorizationService
from gds_etl_workbench.domain.authorization import ActorKind, RequestPrincipal
from gds_etl_workbench.domain.errors import WorkbenchError
from gds_etl_workbench.infrastructure.postgres import ReadIsolation
from gds_workbench_api.features.code_generation import downloads
from gds_workbench_api.features.code_generation.contracts import (
    MAX_BULK_SQL_BYTES,
    MAX_EXPORT_ARTIFACTS,
    ExportSqlArtifactsRequest,
    SqlArtifactBundleLimitExceededError,
    SqlArtifactDownload,
)
from gds_workbench_api.features.code_generation.downloads import build_sql_zip
from gds_workbench_api.features.code_generation.read_service import DatabaseCodeGenerationService
from gds_workbench_api.main import create_app
from pydantic import JsonValue

from tests.web_backend.test_code_generation import (
    SqlDownloadTransaction,
    StaticCodeGenerationService,
    _identity_provider,  # pyright: ignore[reportPrivateUsage]
)


def artifact(identifier: int, name: str) -> SqlArtifactDownload:
    return SqlArtifactDownload.model_validate(
        {
            "generated_sql_artifact_id": identifier,
            "artifact_name": name,
            "entity_type": "logical_entity",
            "target": {
                "entity_id": identifier,
                "entity_type": "logical_entity",
                "entity_schema_name": "silver",
                "entity_name": "Customer",
            },
            "generated_sql": "SELECT 'é';\n",
            "generated_sql_byte_count": len("SELECT 'é';\n".encode()),
            "artifact_is_current": False,
            "source_system_codes": ("CRM",),
        }
    )


def test_bulk_zip_preserves_sql_names_currentness_and_is_deterministic() -> None:
    artifacts = tuple(
        artifact(index, name)
        for index, name in enumerate(
            ("CON.sql", "a__4.sql", "a.sql", "A.sql", "../../NUL.sql", "lpt1.sql"), 1
        )
    )
    manifest: dict[str, JsonValue] = {"scope": "active_sql", "project_revision": 4}
    content = build_sql_zip(artifacts, max_artifacts=MAX_EXPORT_ARTIFACTS, manifest=manifest)
    assert content == build_sql_zip(
        artifacts, max_artifacts=MAX_EXPORT_ARTIFACTS, manifest=manifest
    )
    with ZipFile(BytesIO(content)) as archive:
        names = archive.namelist()
        assert len(names) == len(set(name.casefold() for name in names)) == 7
        assert "_con.sql" in names and "_nul.sql" in names and "_lpt1.sql" in names
        assert all("/" not in name and "\\" not in name for name in names)
        assert all(member.compress_type == ZIP_STORED for member in archive.infolist())
        metadata = json.loads(archive.read("manifest.json"))
        assert metadata["scope"] == "active_sql"
        for row in metadata["artifacts"]:
            assert archive.read(row["filename"]) == "SELECT 'é';\n".encode()
            assert row["artifact_is_current"] is False
            assert row["source_system_codes"] == ["CRM"]
            assert row["target"]["entity_schema_name"] == "silver"


def test_bulk_route_returns_manifest_and_rejects_unscoped_or_extra_inputs() -> None:
    app = create_app(
        identity_provider=_identity_provider(),
        code_generation_service=StaticCodeGenerationService(),
    )
    path = "/api/v1/tenants/7/projects/18/code-generation/downloads/all.zip"
    with TestClient(app) as client:
        command = {"entity_type": "logical_entity", "expected_project_revision": 4}
        response = client.post(path, json=command)
        assert response.status_code == 200
        assert response.headers["content-type"] == "application/zip"
        assert response.headers["cache-control"] == "no-store"
        assert response.headers["x-content-type-options"] == "nosniff"
        assert response.headers["x-gds-export-scope"] == "active_sql"
        assert response.headers["x-gds-artifact-count"] == "2"
        assert response.headers["x-gds-project-revision"] == "4"
        assert response.headers["content-disposition"] == (
            'attachment; filename="gds_sql_logical__project_18__r4.zip"'
        )
        with ZipFile(BytesIO(response.content)) as archive:
            assert len(json.loads(archive.read("manifest.json"))["artifacts"]) == 2
        for invalid in ({}, {**command, "expected_project_revision": 0}, {**command, "all": True}):
            assert client.post(path, json=invalid).status_code == 422


def test_manifest_bytes_share_the_sql_bundle_limit(monkeypatch: pytest.MonkeyPatch) -> None:
    record = artifact(1, "customer.sql")
    monkeypatch.setattr(downloads, "MAX_BULK_SQL_BYTES", record.generated_sql_byte_count + 8)
    with pytest.raises(SqlArtifactBundleLimitExceededError):
        build_sql_zip((record,), manifest={"scope": "active_sql"})


class ExportTransaction(SqlDownloadTransaction):
    authorized = True
    revision = 4
    count = 26
    byte_count = 1024
    content_read = False

    async def fetch_one(
        self, query: LiteralString, parameters: tuple[Any, ...] = ()
    ) -> dict[str, Any] | None:
        if "SELECT target_project.project_revision" in query:
            assert parameters == (7, 18)
            return {"project_revision": self.revision}
        if "AS total_export_bytes" in query:
            assert parameters == ("logical_entity", 7, 18, "logical_entity")
            assert "owned_project.tenant_id = %s" in query
            assert "artifact.generated_code_status = 'active'" in query
            assert "LEFT JOIN LATERAL workflow.list_code_generation_target_context" in query
            assert "artifact.code_input_digest = context.code_input_digest" not in query
            return {"artifact_count": self.count, "total_export_bytes": self.byte_count}
        row = await super().fetch_one(query, parameters)
        assert row is not None
        row["authorized"] = self.authorized
        row["denial_code"] = None if self.authorized else "tenant_access_denied"
        return row

    async def fetch_all(
        self, query: LiteralString, parameters: tuple[Any, ...] = ()
    ) -> list[dict[str, Any]]:
        if "artifact.generated_code_content AS generated_sql" not in query:
            return []
        self.content_read = True
        assert parameters == ("logical_entity", 7, 18, "logical_entity", MAX_EXPORT_ARTIFACTS + 1)
        return [artifact(index, f"file_{index}.sql").model_dump() for index in range(1, 27)]


class ExportDatabase:
    def __init__(self, transaction: ExportTransaction) -> None:
        self.transaction = transaction

    @asynccontextmanager
    async def read_transaction(
        self, *, isolation: ReadIsolation = ReadIsolation.READ_COMMITTED
    ) -> AsyncGenerator[ExportTransaction]:
        assert isolation is ReadIsolation.REPEATABLE_READ
        yield self.transaction


@pytest.mark.parametrize(
    "setting,value,error",
    [
        ("authorized", False, "authorization_denied"),
        ("revision", 5, "project_revision_conflict"),
        ("count", 0, "generated_sql_export_empty"),
        ("count", MAX_EXPORT_ARTIFACTS + 1, "generated_sql_bundle_limit_exceeded"),
        ("byte_count", MAX_BULK_SQL_BYTES + 1, "generated_sql_bundle_limit_exceeded"),
        ("count", 26, None),
    ],
)
async def test_bulk_service_authorizes_and_bounds_before_loading_all_sql(
    setting: str, value: object, error: str | None
) -> None:
    transaction = ExportTransaction()
    setattr(transaction, setting, value)
    service = DatabaseCodeGenerationService(
        database=ExportDatabase(transaction),
        authorizer=AuthorizationService(),
        cursor_signing_key=b"development-only-key-32-bytes-long",
    )
    principal = RequestPrincipal(
        actor_kind=ActorKind.HUMAN,
        entra_tenant_id=UUID("11111111-1111-1111-1111-111111111111"),
        entra_object_id=UUID("22222222-2222-2222-2222-222222222222"),
    )
    command = ExportSqlArtifactsRequest(entity_type="logical_entity", expected_project_revision=4)
    if error is not None:
        with pytest.raises(WorkbenchError) as raised:
            await service.read_all_artifacts_for_download(
                principal, tenant_id=7, project_id=18, command=command
            )
        assert raised.value.code == error
        assert not transaction.content_read
    else:
        records = await service.read_all_artifacts_for_download(
            principal, tenant_id=7, project_id=18, command=command
        )
        assert len(records) == 26 and all(record.artifact_is_current is False for record in records)
