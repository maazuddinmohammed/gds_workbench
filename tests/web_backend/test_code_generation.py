from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from io import BytesIO
from typing import Any, LiteralString
from uuid import UUID
from zipfile import ZIP_STORED, ZipFile

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from gds_etl_workbench.adapters.auth.identity import IdentityProvider
from gds_etl_workbench.application.authorization import AuthorizationService
from gds_etl_workbench.configuration import AuthMode
from gds_etl_workbench.domain.authorization import ActorKind, RequestPrincipal
from gds_etl_workbench.domain.errors import InvalidRequestError
from gds_etl_workbench.infrastructure.postgres import ReadIsolation

from gds_workbench_api.features.code_generation import (
    CodeGenerationTargetFilters,
    CodeGenerationTargetObjectReference,
    CodeGenerationTargetPage,
    CodeGenerationTargetSummary,
    CodeMappingSupport,
    DatabaseCodeGenerationService,
    GeneratedSqlArtifactDetail,
    SqlArtifactBundleLimitExceededError,
    SqlArtifactDownload,
    SqlGenerationGuideProvenance,
    SqlGeneratorProvenance,
    StoredSqlArtifactSummary,
    create_code_generation_router,
)
from gds_workbench_api.features.mapping import (
    ModeledEntityReference,
    SourceSystemReference,
)


class StaticCodeGenerationService:
    target_filters: CodeGenerationTargetFilters | None = None

    async def list_targets(
        self,
        principal: RequestPrincipal,
        *,
        tenant_id: int,
        model_id: int,
        filters: CodeGenerationTargetFilters,
        page_size: int,
        cursor: str | None,
    ) -> CodeGenerationTargetPage:
        assert principal.actor_kind is ActorKind.HUMAN
        assert (tenant_id, model_id, page_size, cursor) == (7, 18, 25, None)
        self.target_filters = filters
        return CodeGenerationTargetPage(
            model_id=18,
            model_revision=4,
            items=(
                CodeGenerationTargetSummary(
                    target=CodeGenerationTargetObjectReference(
                        object_id=501,
                        source_tenant_id=7,
                        source_tenant_code="ACME",
                        source_tenant_name="Acme",
                        tenant_id=7,
                        tenant_code="ACME",
                        tenant_name="Acme",
                        system_id=32,
                        system_code="GDS",
                        system_name="Global Data Store",
                        connection_id=21,
                        connection_code="SILVER",
                        object_schema="silver_crm",
                        object_name="customer",
                        zone_code="silver",
                    ),
                    entity_type="logical_entity",
                    mapping_supports=(
                        CodeMappingSupport(
                            mapping_object_id=401,
                            source=ModeledEntityReference(
                                entity_type="logical_entity",
                                entity_id=101,
                                entity_name="Customer",
                            ),
                            source_system=SourceSystemReference(
                                system_id=31,
                                system_code="CRM",
                                system_name="Customer Relationship Management",
                            ),
                            dependency_order=1,
                        ),
                    ),
                    mapping_support_count=1,
                    mapping_supports_truncated=False,
                    source_systems=(
                        SourceSystemReference(
                            system_id=31,
                            system_code="CRM",
                            system_name="Customer Relationship Management",
                        ),
                        SourceSystemReference(
                            system_id=33,
                            system_code="ERP",
                            system_name="Enterprise Resource Planning",
                        ),
                    ),
                    source_system_count=2,
                    artifacts=(
                        StoredSqlArtifactSummary(
                            generated_sql_artifact_id=901,
                            artifact_name="customer.sql",
                            workflow_run_id=None,
                            generated_at=datetime(2026, 8, 24, 14, 0, tzinfo=UTC),
                            generated_code_status="active",
                            source_system_codes=("CRM", "ERP"),
                            artifact_is_current=True,
                        ),
                    ),
                    artifact_count=1,
                ),
            ),
            next_cursor=None,
        )

    async def read_artifact(
        self,
        principal: RequestPrincipal,
        *,
        tenant_id: int,
        model_id: int,
        generated_sql_artifact_id: int,
    ) -> GeneratedSqlArtifactDetail:
        assert principal.actor_kind is ActorKind.HUMAN
        assert (tenant_id, model_id, generated_sql_artifact_id) == (7, 18, 901)
        target = (
            await self.list_targets(
                principal,
                tenant_id=tenant_id,
                model_id=model_id,
                filters=CodeGenerationTargetFilters(),
                page_size=25,
                cursor=None,
            )
        ).items[0]
        sql = "SELECT customer_id\nFROM silver_crm.customer;\n"
        return GeneratedSqlArtifactDetail(
            generated_sql_artifact_id=901,
            artifact_name="customer.sql",
            model_id=18,
            target=target.target,
            entity_type=target.entity_type,
            source_systems=target.source_systems,
            source_system_count=target.source_system_count,
            mapping_supports=target.mapping_supports,
            mapping_support_count=target.mapping_support_count,
            mapping_supports_truncated=target.mapping_supports_truncated,
            artifact_is_current=True,
            generated_code_status="active",
            guide=SqlGenerationGuideProvenance(
                sql_generation_guide_id=1001,
                sql_generation_guide_code="default_sql",
                sql_generation_guide_name="Default SQL",
                guide_is_active=True,
                sql_generation_guide_version_id=1002,
                sql_generation_guide_version_number=3,
                sql_generation_guide_version_status="published",
                sql_generation_guide_digest="d" * 64,
            ),
            workflow_run_id=None,
            generator=SqlGeneratorProvenance(
                generator_code="gds.sql",
                generator_version="1.0.0",
                generated_by_display_name="Maaz",
            ),
            generated_at=datetime(2026, 8, 24, 14, 0, tzinfo=UTC),
            generated_sql=sql,
            generated_sql_byte_count=len(sql.encode()),
        )

    async def read_artifacts_for_download(
        self,
        principal: RequestPrincipal,
        *,
        tenant_id: int,
        model_id: int,
        generated_sql_artifact_ids: tuple[int, ...],
    ) -> tuple[SqlArtifactDownload, ...]:
        assert principal.actor_kind is ActorKind.HUMAN
        assert (tenant_id, model_id, generated_sql_artifact_ids) == (
            7,
            18,
            (901, 902),
        )
        detail = await self.read_artifact(
            principal,
            tenant_id=tenant_id,
            model_id=model_id,
            generated_sql_artifact_id=901,
        )
        second_target = detail.target.model_copy(
            update={"object_id": 502, "object_name": "order"}
        )
        second_sql = "SELECT order_id\nFROM silver_crm.order;\n"
        return (
            SqlArtifactDownload(
                generated_sql_artifact_id=901,
                artifact_name=detail.artifact_name,
                target=detail.target,
                entity_type=detail.entity_type,
                generated_sql=detail.generated_sql,
                generated_sql_byte_count=detail.generated_sql_byte_count,
            ),
            SqlArtifactDownload(
                generated_sql_artifact_id=902,
                artifact_name="order.sql",
                target=second_target,
                entity_type="logical_entity",
                generated_sql=second_sql,
                generated_sql_byte_count=len(second_sql.encode()),
            ),
        )


def _identity_provider() -> IdentityProvider:
    return IdentityProvider(
        AuthMode.DEV,
        local_tenant_id=UUID("11111111-1111-1111-1111-111111111111"),
        local_principal_object_id=UUID("22222222-2222-2222-2222-222222222222"),
    )


def test_code_generation_targets_are_target_object_first_and_filterable() -> None:
    service = StaticCodeGenerationService()
    app = FastAPI()
    app.include_router(
        create_code_generation_router(
            identity_provider=_identity_provider(),
            service=service,
        )
    )

    with TestClient(app) as client:
        response = client.get(
            "/api/v1/tenants/7/models/18/code-generation/targets",
            params={
                "entity_type": "LOGICAL_ENTITY",
                "system_id": "32",
                "system_code": " GdS ",
                "source_system_code": " CrM ",
                "page_size": "25",
            },
        )

    assert response.status_code == 200
    assert service.target_filters == CodeGenerationTargetFilters(
        entity_type="logical_entity",
        system_id=32,
        system_code="gds",
        source_system_code="crm",
    )
    item = response.json()["items"][0]
    assert item["target"]["object_name"] == "customer"
    assert item["target"]["system_code"] == "GDS"
    assert item["entity_type"] == "logical_entity"
    assert item["mapping_supports"] == [
        {
            "mapping_object_id": 401,
            "source": {
                "entity_type": "logical_entity",
                "entity_id": 101,
                "entity_name": "Customer",
            },
            "source_system": {
                "system_id": 31,
                "system_code": "CRM",
                "system_name": "Customer Relationship Management",
            },
            "dependency_order": 1,
        }
    ]
    assert item["mapping_support_count"] == 1
    assert item["mapping_supports_truncated"] is False
    assert [system["system_code"] for system in item["source_systems"]] == [
        "CRM",
        "ERP",
    ]
    assert item["source_system_count"] == 2
    assert item["target"]["tenant_code"] == "ACME"
    assert item["target"]["system_code"] == "GDS"
    assert item["target"]["source_tenant_code"] == "ACME"
    assert item["artifacts"][0]["generated_sql_artifact_id"] == 901
    assert item["artifacts"][0]["artifact_name"] == "customer.sql"
    assert item["artifacts"][0]["artifact_is_current"] is True
    assert item["artifact_count"] == 1


def test_generated_sql_artifact_detail_returns_only_stored_sql_and_safe_provenance() -> (
    None
):
    app = FastAPI()
    app.include_router(
        create_code_generation_router(
            identity_provider=_identity_provider(),
            service=StaticCodeGenerationService(),
        )
    )

    with TestClient(app) as client:
        response = client.get(
            "/api/v1/tenants/7/models/18/code-generation/artifacts/901"
        )

    assert response.status_code == 200
    payload = response.json()
    assert payload["target"]["object_name"] == "customer"
    assert payload["entity_type"] == "logical_entity"
    assert payload["mapping_supports"][0]["source"]["entity_name"] == "Customer"
    assert payload["artifact_is_current"] is True
    assert [system["system_code"] for system in payload["source_systems"]] == [
        "CRM",
        "ERP",
    ]
    assert payload["guide"]["sql_generation_guide_version_number"] == 3
    assert payload["generator"] == {
        "generator_code": "gds.sql",
        "generator_version": "1.0.0",
        "generated_by_display_name": "Maaz",
    }
    assert payload["workflow_run_id"] is None
    assert payload["generated_sql"] == (
        "SELECT customer_id\nFROM silver_crm.customer;\n"
    )
    detail = GeneratedSqlArtifactDetail.model_validate(payload, strict=False)
    assert "SELECT customer_id" not in repr(detail)
    assert "created_by" not in payload


class UnprovenancedStaticCodeGenerationService(StaticCodeGenerationService):
    async def read_artifact(
        self,
        principal: RequestPrincipal,
        *,
        tenant_id: int,
        model_id: int,
        generated_sql_artifact_id: int,
    ) -> GeneratedSqlArtifactDetail:
        detail = await super().read_artifact(
            principal,
            tenant_id=tenant_id,
            model_id=model_id,
            generated_sql_artifact_id=generated_sql_artifact_id,
        )
        return detail.model_copy(
            update={
                "guide": None,
                "workflow_run_id": None,
                "generator": None,
            }
        )


def test_generated_sql_artifact_detail_allows_missing_workflow_provenance() -> None:
    app = FastAPI()
    app.include_router(
        create_code_generation_router(
            identity_provider=_identity_provider(),
            service=UnprovenancedStaticCodeGenerationService(),
        )
    )

    with TestClient(app) as client:
        response = client.get(
            "/api/v1/tenants/7/models/18/code-generation/artifacts/901"
        )

    assert response.status_code == 200
    assert response.json()["guide"] is None
    assert response.json()["workflow_run_id"] is None
    assert response.json()["generator"] is None


def test_individual_sql_download_has_safe_filename_and_content_headers() -> None:
    app = FastAPI()
    app.include_router(
        create_code_generation_router(
            identity_provider=_identity_provider(),
            service=StaticCodeGenerationService(),
        )
    )

    with TestClient(app) as client:
        response = client.get(
            "/api/v1/tenants/7/models/18/code-generation/artifacts/901/download.sql"
        )

    assert response.status_code == 200
    assert response.content == b"SELECT customer_id\nFROM silver_crm.customer;\n"
    assert response.headers["content-type"] == "application/sql"
    assert response.headers["content-disposition"] == (
        'attachment; filename="customer.sql"'
    )
    assert "\r" not in response.headers["content-disposition"]
    assert "\n" not in response.headers["content-disposition"]
    assert response.headers["cache-control"] == "no-store"
    assert response.headers["x-content-type-options"] == "nosniff"
    assert "x-gds-sha256" not in response.headers
    assert response.headers["content-length"] == str(len(response.content))


def test_selected_sql_zip_is_stored_bounded_and_path_safe() -> None:
    app = FastAPI()
    app.include_router(
        create_code_generation_router(
            identity_provider=_identity_provider(),
            service=StaticCodeGenerationService(),
        )
    )

    with TestClient(app) as client:
        response = client.get(
            "/api/v1/tenants/7/models/18/code-generation/downloads/selected.zip",
            params=[("artifact_id", "901"), ("artifact_id", "902")],
        )

    assert response.status_code == 200
    assert response.headers["content-type"] == "application/zip"
    assert response.headers["content-disposition"] == (
        'attachment; filename="gds_sql_artifacts__model_18__2.zip"'
    )
    assert response.headers["cache-control"] == "no-store"
    assert response.headers["x-content-type-options"] == "nosniff"
    assert response.headers["x-gds-artifact-count"] == "2"
    with ZipFile(BytesIO(response.content)) as archive:
        members = archive.infolist()
        assert [member.filename for member in members] == [
            "customer.sql",
            "order.sql",
        ]
        assert all(member.compress_type == ZIP_STORED for member in members)
        assert all(
            "/" not in member.filename and "\\" not in member.filename
            for member in members
        )
        assert archive.read(members[0]) == (
            b"SELECT customer_id\nFROM silver_crm.customer;\n"
        )
        assert archive.read(members[1]) == b"SELECT order_id\nFROM silver_crm.order;\n"


class UnsafeTargetNameCodeGenerationService(StaticCodeGenerationService):
    async def read_artifacts_for_download(
        self,
        principal: RequestPrincipal,
        *,
        tenant_id: int,
        model_id: int,
        generated_sql_artifact_ids: tuple[int, ...],
    ) -> tuple[SqlArtifactDownload, ...]:
        artifacts = await super().read_artifacts_for_download(
            principal,
            tenant_id=tenant_id,
            model_id=model_id,
            generated_sql_artifact_ids=generated_sql_artifact_ids,
        )
        first = artifacts[0]
        return (
            first.model_copy(
                update={
                    "target": first.target.model_copy(
                        update={
                            "object_schema": "../../Sílver\\CRM\r\n",
                            "object_name": "../../CON",
                        }
                    )
                }
            ),
            artifacts[1],
        )


def test_selected_sql_zip_sanitizes_hostile_target_names() -> None:
    app = FastAPI()
    app.include_router(
        create_code_generation_router(
            identity_provider=_identity_provider(),
            service=UnsafeTargetNameCodeGenerationService(),
        )
    )

    with TestClient(app) as client:
        response = client.get(
            "/api/v1/tenants/7/models/18/code-generation/downloads/selected.zip",
            params=[("artifact_id", "901"), ("artifact_id", "902")],
        )

    assert response.status_code == 200
    with ZipFile(BytesIO(response.content)) as archive:
        names = archive.namelist()
    assert names[0] == "customer.sql"
    assert all(
        separator not in name
        for name in names
        for separator in ("/", "\\", "\r", "\n", "..")
    )


def test_selected_sql_zip_rejects_more_than_twenty_five_artifacts() -> None:
    app = FastAPI()
    app.include_router(
        create_code_generation_router(
            identity_provider=_identity_provider(),
            service=StaticCodeGenerationService(),
        )
    )

    with TestClient(app) as client:
        response = client.get(
            "/api/v1/tenants/7/models/18/code-generation/downloads/selected.zip",
            params=[("artifact_id", str(identifier)) for identifier in range(1, 27)],
        )

    assert response.status_code == 422


def test_stored_sql_routes_expose_no_generation_or_execution_mutation() -> None:
    app = FastAPI()
    app.include_router(
        create_code_generation_router(
            identity_provider=_identity_provider(),
            service=StaticCodeGenerationService(),
        )
    )

    paths = app.openapi()["paths"]
    for path in (
        "/api/v1/tenants/{tenant_id}/models/{model_id}/code-generation/targets",
        (
            "/api/v1/tenants/{tenant_id}/models/{model_id}/code-generation/"
            "artifacts/{generated_sql_artifact_id}"
        ),
        (
            "/api/v1/tenants/{tenant_id}/models/{model_id}/code-generation/"
            "artifacts/{generated_sql_artifact_id}/download.sql"
        ),
        (
            "/api/v1/tenants/{tenant_id}/models/{model_id}/code-generation/downloads/selected.zip"
        ),
    ):
        methods = {method for method in paths[path] if method != "parameters"}
        assert methods == {"get"}


class CodeTargetTransaction:
    async def fetch_one(
        self,
        query: LiteralString,
        parameters: tuple[Any, ...] = (),
    ) -> dict[str, Any] | None:
        if "SELECT target_model.model_revision" in query:
            assert parameters == (7, 18)
            return {"model_revision": 4}
        assert "security.entra_principal_identity" in query
        assert parameters[-1] == 7
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

    async def fetch_all(
        self,
        query: LiteralString,
        parameters: tuple[Any, ...] = (),
    ) -> list[dict[str, Any]]:
        assert "workflow.list_code_generation_target_context" in query
        assert "workflow.list_model_object_eligibility" not in query
        assert "workflow.generated_code" in query
        assert "application.generated_sql_artifact" not in query
        assert "generated.artifact_type = 'sql_file'" in query
        assert "generated.code_input_digest = context.code_input_digest" in query
        assert "artifact.model_revision" not in query
        assert "artifact.source_system_id" not in query
        assert "jsonb_array_elements" in query
        assert "EXISTS" in query
        assert parameters == (
            7,
            18,
            "logical_entity",
            "logical_entity",
            32,
            32,
            "gds",
            "gds",
            31,
            31,
            "crm",
            "crm",
            26,
            0,
        )
        return [
            {
                "target": {
                    "object_id": 501,
                    "source_tenant_id": 7,
                    "source_tenant_code": "ACME",
                    "source_tenant_name": "Acme",
                    "tenant_id": 7,
                    "tenant_code": "ACME",
                    "tenant_name": "Acme",
                    "system_id": 32,
                    "system_code": "GDS",
                    "system_name": "Global Data Store",
                    "connection_id": 21,
                    "connection_code": "SILVER",
                    "object_schema": "silver_crm",
                    "object_name": "customer",
                    "zone_code": "silver",
                },
                "entity_type": "logical_entity",
                "mapping_supports": [
                    {
                        "mapping_object_id": 401,
                        "source": {
                            "entity_type": "logical_entity",
                            "entity_id": 101,
                            "entity_name": "Customer",
                        },
                        "source_system": {
                            "system_id": 31,
                            "system_code": "CRM",
                            "system_name": "Customer Relationship Management",
                        },
                        "dependency_order": 1,
                    }
                ],
                "mapping_support_count": 1,
                "mapping_supports_truncated": False,
                "source_systems": [
                    {
                        "system_id": 31,
                        "system_code": "CRM",
                        "system_name": "Customer Relationship Management",
                    },
                    {
                        "system_id": 33,
                        "system_code": "ERP",
                        "system_name": "Enterprise Resource Planning",
                    },
                ],
                "source_system_count": 2,
                "artifacts": [
                    {
                        "generated_sql_artifact_id": 901,
                        "artifact_name": "customer.sql",
                        "workflow_run_id": None,
                        "generated_at": datetime(2026, 8, 24, 14, 0, tzinfo=UTC),
                        "generated_code_status": "active",
                        "source_system_codes": ["CRM", "ERP"],
                        "artifact_is_current": True,
                    }
                ],
                "artifact_count": 1,
            }
        ]


class CodeTargetDatabase:
    @asynccontextmanager
    async def read_transaction(
        self,
        *,
        isolation: ReadIsolation = ReadIsolation.READ_COMMITTED,
    ) -> AsyncGenerator[CodeTargetTransaction]:
        assert isolation is ReadIsolation.REPEATABLE_READ
        yield CodeTargetTransaction()


@pytest.mark.asyncio
async def test_database_code_targets_require_complete_active_sql_mapping() -> None:
    service = DatabaseCodeGenerationService(
        database=CodeTargetDatabase(),
        authorizer=AuthorizationService(),
        cursor_signing_key=b"development-only-key-32-bytes-long",
    )
    principal = RequestPrincipal(
        actor_kind=ActorKind.HUMAN,
        entra_tenant_id=UUID("11111111-1111-1111-1111-111111111111"),
        entra_object_id=UUID("22222222-2222-2222-2222-222222222222"),
    )

    page = await service.list_targets(
        principal,
        tenant_id=7,
        model_id=18,
        filters=CodeGenerationTargetFilters(
            entity_type="logical_entity",
            system_id=32,
            system_code="gds",
            source_system_id=31,
            source_system_code="crm",
        ),
        page_size=25,
        cursor=None,
    )

    assert page.model_revision == 4
    assert page.items[0].target.object_id == 501
    assert page.items[0].target.tenant_code == "ACME"
    assert page.items[0].target.system_code == "GDS"
    assert page.items[0].target.source_tenant_code == "ACME"
    assert [system.system_code for system in page.items[0].source_systems] == [
        "CRM",
        "ERP",
    ]
    assert page.items[0].artifacts[0].workflow_run_id is None
    assert page.items[0].artifacts[0].artifact_is_current is True


class SqlArtifactTransaction:
    async def fetch_one(
        self,
        query: LiteralString,
        parameters: tuple[Any, ...] = (),
    ) -> dict[str, Any] | None:
        if "workflow.generated_code" in query:
            assert "application.store_generated_sql_artifact" not in query
            assert "application.sql_generation_guide_version" in query
            assert "LEFT JOIN application.workflow_run AS generating_run" in query
            assert (
                "LEFT JOIN LATERAL workflow.list_code_generation_target_context"
                in query
            )
            assert "target_model.is_active" not in query
            assert "AND guide.is_active" not in query
            assert "sql_generation_guide_version_status = 'published'" not in query
            assert "artifact.model_revision" not in query
            assert "current_context.code_input_digest" in query
            assert "artifact.code_input_digest" in query
            assert "artifact.generated_code_content AS generated_sql" in query
            assert "generated_code_digest" not in query
            assert "artifact.artifact_type = 'sql_file'" in query
            assert "artifact.generated_code_status" in query
            assert "artifact.source_system_id" not in query
            assert parameters == (7, 18, 901)
            sql = "SELECT customer_id\nFROM silver_crm.customer;\n"
            return {
                "generated_sql_artifact_id": 901,
                "artifact_name": "customer.sql",
                "model_id": 18,
                "target": {
                    "object_id": 501,
                    "source_tenant_id": 7,
                    "source_tenant_code": "ACME",
                    "source_tenant_name": "Acme",
                    "tenant_id": 7,
                    "tenant_code": "ACME",
                    "tenant_name": "Acme",
                    "system_id": 32,
                    "system_code": "GDS",
                    "system_name": "Global Data Store",
                    "connection_id": 21,
                    "connection_code": "SILVER",
                    "object_schema": "silver_crm",
                    "object_name": "customer",
                    "zone_code": "silver",
                },
                "entity_type": "logical_entity",
                "source_systems": [
                    {
                        "system_id": 31,
                        "system_code": "CRM",
                        "system_name": "Customer Relationship Management",
                    },
                    {
                        "system_id": 33,
                        "system_code": "ERP",
                        "system_name": "Enterprise Resource Planning",
                    },
                ],
                "source_system_count": 2,
                "mapping_supports": [
                    {
                        "mapping_object_id": 401,
                        "source": {
                            "entity_type": "logical_entity",
                            "entity_id": 101,
                            "entity_name": "Customer",
                        },
                        "source_system": {
                            "system_id": 31,
                            "system_code": "CRM",
                            "system_name": "Customer Relationship Management",
                        },
                        "dependency_order": 1,
                    }
                ],
                "mapping_support_count": 1,
                "mapping_supports_truncated": False,
                "artifact_is_current": True,
                "generated_code_status": "active",
                "guide": {
                    "sql_generation_guide_id": 1001,
                    "sql_generation_guide_code": "default_sql",
                    "sql_generation_guide_name": "Default SQL",
                    "guide_is_active": True,
                    "sql_generation_guide_version_id": 1002,
                    "sql_generation_guide_version_number": 3,
                    "sql_generation_guide_version_status": "published",
                    "sql_generation_guide_digest": "d" * 64,
                },
                "workflow_run_id": 1151,
                "generator": {
                    "generator_code": "openai_agents",
                    "generator_version": None,
                    "generated_by_display_name": "Maaz",
                },
                "generated_at": datetime(2026, 8, 24, 14, 0, tzinfo=UTC),
                "generated_sql": sql,
                "generated_sql_byte_count": len(sql.encode()),
            }
        assert "security.entra_principal_identity" in query
        assert parameters[-1] == 7
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

    async def fetch_all(
        self,
        query: LiteralString,
        parameters: tuple[Any, ...] = (),
    ) -> list[dict[str, Any]]:
        raise AssertionError((query, parameters))


class SqlArtifactDatabase:
    @asynccontextmanager
    async def read_transaction(
        self,
        *,
        isolation: ReadIsolation = ReadIsolation.READ_COMMITTED,
    ) -> AsyncGenerator[SqlArtifactTransaction]:
        assert isolation is ReadIsolation.REPEATABLE_READ
        yield SqlArtifactTransaction()


@pytest.mark.asyncio
async def test_database_sql_artifact_is_authorized_and_read_from_persistence() -> None:
    service = DatabaseCodeGenerationService(
        database=SqlArtifactDatabase(),
        authorizer=AuthorizationService(),
        cursor_signing_key=b"development-only-key-32-bytes-long",
    )
    principal = RequestPrincipal(
        actor_kind=ActorKind.HUMAN,
        entra_tenant_id=UUID("11111111-1111-1111-1111-111111111111"),
        entra_object_id=UUID("22222222-2222-2222-2222-222222222222"),
    )

    detail = await service.read_artifact(
        principal,
        tenant_id=7,
        model_id=18,
        generated_sql_artifact_id=901,
    )

    assert detail.target.object_name == "customer"
    assert detail.artifact_is_current is True
    assert [system.system_code for system in detail.source_systems] == ["CRM", "ERP"]
    assert detail.mapping_supports[0].source.entity_name == "Customer"
    assert detail.guide is not None
    assert detail.guide.sql_generation_guide_digest == "d" * 64
    assert detail.generator is not None
    assert detail.generator.generator_code == "openai_agents"
    assert detail.generator.generator_version is None
    assert detail.workflow_run_id == 1151


class UnprovenancedSqlArtifactTransaction(SqlArtifactTransaction):
    async def fetch_one(
        self,
        query: LiteralString,
        parameters: tuple[Any, ...] = (),
    ) -> dict[str, Any] | None:
        row = await super().fetch_one(query, parameters)
        if row is None or "workflow.generated_code" not in query:
            return row
        unprovenanced = dict(row)
        unprovenanced.update(
            {
                "guide": None,
                "workflow_run_id": None,
                "generator": None,
            }
        )
        return unprovenanced


class UnprovenancedSqlArtifactDatabase:
    @asynccontextmanager
    async def read_transaction(
        self,
        *,
        isolation: ReadIsolation = ReadIsolation.READ_COMMITTED,
    ) -> AsyncGenerator[UnprovenancedSqlArtifactTransaction]:
        assert isolation is ReadIsolation.REPEATABLE_READ
        yield UnprovenancedSqlArtifactTransaction()


@pytest.mark.asyncio
async def test_database_sql_artifact_allows_missing_workflow_provenance() -> None:
    service = DatabaseCodeGenerationService(
        database=UnprovenancedSqlArtifactDatabase(),
        authorizer=AuthorizationService(),
        cursor_signing_key=b"development-only-key-32-bytes-long",
    )
    principal = RequestPrincipal(
        actor_kind=ActorKind.HUMAN,
        entra_tenant_id=UUID("11111111-1111-1111-1111-111111111111"),
        entra_object_id=UUID("22222222-2222-2222-2222-222222222222"),
    )

    detail = await service.read_artifact(
        principal,
        tenant_id=7,
        model_id=18,
        generated_sql_artifact_id=901,
    )

    assert detail.workflow_run_id is None
    assert detail.guide is None
    assert detail.generator is None


class InactiveSqlArtifactTransaction(SqlArtifactTransaction):
    async def fetch_one(
        self,
        query: LiteralString,
        parameters: tuple[Any, ...] = (),
    ) -> dict[str, Any] | None:
        row = await super().fetch_one(query, parameters)
        if row is None or "workflow.generated_code" not in query:
            return row
        inactive = dict(row)
        inactive["artifact_is_current"] = False
        return inactive


class InactiveSqlArtifactDatabase:
    @asynccontextmanager
    async def read_transaction(
        self,
        *,
        isolation: ReadIsolation = ReadIsolation.READ_COMMITTED,
    ) -> AsyncGenerator[InactiveSqlArtifactTransaction]:
        assert isolation is ReadIsolation.REPEATABLE_READ
        yield InactiveSqlArtifactTransaction()


@pytest.mark.asyncio
async def test_database_inactive_sql_artifact_is_readable_but_not_current() -> None:
    service = DatabaseCodeGenerationService(
        database=InactiveSqlArtifactDatabase(),
        authorizer=AuthorizationService(),
        cursor_signing_key=b"development-only-key-32-bytes-long",
    )
    principal = RequestPrincipal(
        actor_kind=ActorKind.HUMAN,
        entra_tenant_id=UUID("11111111-1111-1111-1111-111111111111"),
        entra_object_id=UUID("22222222-2222-2222-2222-222222222222"),
    )

    detail = await service.read_artifact(
        principal,
        tenant_id=7,
        model_id=18,
        generated_sql_artifact_id=901,
    )

    assert detail.generated_sql.startswith("SELECT customer_id")
    assert detail.artifact_is_current is False


class StaleSqlArtifactTransaction(SqlArtifactTransaction):
    async def fetch_one(
        self,
        query: LiteralString,
        parameters: tuple[Any, ...] = (),
    ) -> dict[str, Any] | None:
        row = await super().fetch_one(query, parameters)
        if row is None or "workflow.generated_code" not in query:
            return row
        stale = dict(row)
        stale.update(
            {
                "source_systems": [],
                "source_system_count": 0,
                "mapping_supports": [],
                "mapping_support_count": 0,
                "mapping_supports_truncated": False,
                "artifact_is_current": False,
                "guide": {
                    **row["guide"],
                    "guide_is_active": False,
                    "sql_generation_guide_version_status": "retired",
                },
            }
        )
        return stale


class StaleSqlArtifactDatabase:
    @asynccontextmanager
    async def read_transaction(
        self,
        *,
        isolation: ReadIsolation = ReadIsolation.READ_COMMITTED,
    ) -> AsyncGenerator[StaleSqlArtifactTransaction]:
        assert isolation is ReadIsolation.REPEATABLE_READ
        yield StaleSqlArtifactTransaction()


@pytest.mark.asyncio
async def test_database_sql_artifact_remains_readable_when_context_and_guide_are_stale() -> (
    None
):
    service = DatabaseCodeGenerationService(
        database=StaleSqlArtifactDatabase(),
        authorizer=AuthorizationService(),
        cursor_signing_key=b"development-only-key-32-bytes-long",
    )
    principal = RequestPrincipal(
        actor_kind=ActorKind.HUMAN,
        entra_tenant_id=UUID("11111111-1111-1111-1111-111111111111"),
        entra_object_id=UUID("22222222-2222-2222-2222-222222222222"),
    )

    detail = await service.read_artifact(
        principal,
        tenant_id=7,
        model_id=18,
        generated_sql_artifact_id=901,
    )

    assert detail.artifact_is_current is False
    assert detail.source_systems == ()
    assert detail.mapping_supports == ()
    assert detail.guide is not None
    assert detail.guide.guide_is_active is False
    assert detail.guide.sql_generation_guide_version_status == "retired"


class SqlDownloadTransaction:
    async def fetch_one(
        self,
        query: LiteralString,
        parameters: tuple[Any, ...] = (),
    ) -> dict[str, Any] | None:
        if "sum(octet_length" in query:
            assert "workflow.generated_code" in query
            assert "application.generated_sql_artifact" not in query
            assert "artifact.generated_code_content" in query
            assert "artifact.generated_code_id = ANY" in query
            assert "artifact.artifact_type = 'sql_file'" in query
            assert "generated_code_status" not in query
            assert parameters == (7, 18, [901, 902])
            return {"artifact_count": 2, "total_sql_bytes": 72}
        assert "security.entra_principal_identity" in query
        assert parameters[-1] == 7
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

    async def fetch_all(
        self,
        query: LiteralString,
        parameters: tuple[Any, ...] = (),
    ) -> list[dict[str, Any]]:
        assert "workflow.generated_code" in query
        assert "application.generated_sql_artifact" not in query
        assert "application.store_generated_sql_artifact" not in query
        assert "artifact.generated_code_id = ANY" in query
        assert "artifact.generated_code_content AS generated_sql" in query
        assert "generated_code_digest" not in query
        assert "artifact.artifact_type = 'sql_file'" in query
        assert "generated_code_status" not in query
        assert "artifact.source_system_id" not in query
        assert "target_model.is_active" not in query
        assert parameters == (7, 18, [901, 902], [901, 902])
        rows: list[dict[str, Any]] = []
        for artifact_id, object_id, object_name, sql in (
            (901, 501, "customer", "SELECT * FROM silver_crm.customer;\n"),
            (902, 502, "order", "SELECT * FROM silver_crm.order;\n"),
        ):
            rows.append(
                {
                    "generated_sql_artifact_id": artifact_id,
                    "artifact_name": f"{object_name}.sql",
                    "target": {
                        "object_id": object_id,
                        "source_tenant_id": 7,
                        "source_tenant_code": "ACME",
                        "source_tenant_name": "Acme",
                        "tenant_id": 7,
                        "tenant_code": "ACME",
                        "tenant_name": "Acme",
                        "system_id": 32,
                        "system_code": "GDS",
                        "system_name": "Global Data Store",
                        "connection_id": 21,
                        "connection_code": "SILVER",
                        "object_schema": "silver_crm",
                        "object_name": object_name,
                        "zone_code": "silver",
                    },
                    "entity_type": "logical_entity",
                    "generated_sql": sql,
                    "generated_sql_byte_count": len(sql.encode()),
                }
            )
        return rows


class SqlDownloadDatabase:
    @asynccontextmanager
    async def read_transaction(
        self,
        *,
        isolation: ReadIsolation = ReadIsolation.READ_COMMITTED,
    ) -> AsyncGenerator[SqlDownloadTransaction]:
        assert isolation is ReadIsolation.REPEATABLE_READ
        yield SqlDownloadTransaction()


@pytest.mark.asyncio
async def test_database_selected_sql_download_reads_exact_persisted_artifacts() -> None:
    service = DatabaseCodeGenerationService(
        database=SqlDownloadDatabase(),
        authorizer=AuthorizationService(),
        cursor_signing_key=b"development-only-key-32-bytes-long",
    )
    principal = RequestPrincipal(
        actor_kind=ActorKind.HUMAN,
        entra_tenant_id=UUID("11111111-1111-1111-1111-111111111111"),
        entra_object_id=UUID("22222222-2222-2222-2222-222222222222"),
    )

    artifacts = await service.read_artifacts_for_download(
        principal,
        tenant_id=7,
        model_id=18,
        generated_sql_artifact_ids=(901, 902),
    )

    assert [item.generated_sql_artifact_id for item in artifacts] == [901, 902]
    assert artifacts[0].target.object_name == "customer"
    assert artifacts[1].generated_sql.endswith("silver_crm.order;\n")


@pytest.mark.asyncio
async def test_database_selected_sql_download_rejects_duplicate_ids_before_query() -> (
    None
):
    service = DatabaseCodeGenerationService(
        database=SqlDownloadDatabase(),
        authorizer=AuthorizationService(),
        cursor_signing_key=b"development-only-key-32-bytes-long",
    )
    principal = RequestPrincipal(
        actor_kind=ActorKind.HUMAN,
        entra_tenant_id=UUID("11111111-1111-1111-1111-111111111111"),
        entra_object_id=UUID("22222222-2222-2222-2222-222222222222"),
    )

    with pytest.raises(InvalidRequestError):
        await service.read_artifacts_for_download(
            principal,
            tenant_id=7,
            model_id=18,
            generated_sql_artifact_ids=(901, 901),
        )


class OversizeSqlDownloadTransaction(SqlDownloadTransaction):
    async def fetch_one(
        self,
        query: LiteralString,
        parameters: tuple[Any, ...] = (),
    ) -> dict[str, Any] | None:
        if "sum(octet_length" in query:
            assert parameters == (7, 18, [901, 902])
            return {"artifact_count": 2, "total_sql_bytes": (32 * 1024 * 1024) + 1}
        return await super().fetch_one(query, parameters)

    async def fetch_all(
        self,
        query: LiteralString,
        parameters: tuple[Any, ...] = (),
    ) -> list[dict[str, Any]]:
        raise AssertionError((query, parameters))


class OversizeSqlDownloadDatabase:
    @asynccontextmanager
    async def read_transaction(
        self,
        *,
        isolation: ReadIsolation = ReadIsolation.READ_COMMITTED,
    ) -> AsyncGenerator[OversizeSqlDownloadTransaction]:
        assert isolation is ReadIsolation.REPEATABLE_READ
        yield OversizeSqlDownloadTransaction()


@pytest.mark.asyncio
async def test_database_selected_sql_download_rejects_total_before_loading_sql() -> (
    None
):
    service = DatabaseCodeGenerationService(
        database=OversizeSqlDownloadDatabase(),
        authorizer=AuthorizationService(),
        cursor_signing_key=b"development-only-key-32-bytes-long",
    )
    principal = RequestPrincipal(
        actor_kind=ActorKind.HUMAN,
        entra_tenant_id=UUID("11111111-1111-1111-1111-111111111111"),
        entra_object_id=UUID("22222222-2222-2222-2222-222222222222"),
    )

    with pytest.raises(SqlArtifactBundleLimitExceededError):
        await service.read_artifacts_for_download(
            principal,
            tenant_id=7,
            model_id=18,
            generated_sql_artifact_ids=(901, 902),
        )
