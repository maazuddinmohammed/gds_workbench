from __future__ import annotations

from collections.abc import Mapping
from typing import Protocol
from uuid import uuid4

import pytest
from gds_etl_workbench.application.authorization import AuthorizationService
from gds_etl_workbench.domain.authorization import ActorKind, RequestPrincipal
from psycopg import Connection

from gds_workbench_api.database import WebPostgresDatabase
from gds_workbench_api.features.code_generation import (
    CodeGenerationTargetFilters,
    DatabaseCodeGenerationService,
    GeneratedSqlArtifactNotFoundError,
)
from gds_workbench_api.features.mapping import (
    DatabaseMappingReviewService,
    MappingAttributeNotFoundError,
    MappingDependencyFilters,
    MappingObjectNotFoundError,
)


class DisposablePostgresFixture(Protocol):
    def connect_owner(self) -> Connection[dict[str, object]]: ...

    def web_runtime_dsn(self) -> str: ...


def _required_id(row: Mapping[str, object] | None, field: str) -> int:
    if row is None:
        raise AssertionError(f"expected database ID field {field}")
    value = row.get(field)
    if not isinstance(value, int) or isinstance(value, bool) or value <= 0:
        raise AssertionError(f"expected positive database ID field {field}")
    return value


@pytest.mark.asyncio
async def test_mapping_and_code_reads_round_trip_through_web_role(
    web_postgres_database: DisposablePostgresFixture,
) -> None:
    entra_tenant_id = uuid4()
    entra_object_id = uuid4()
    suffix = uuid4().hex
    with web_postgres_database.connect_owner() as connection:
        project_id = _required_id(
            connection.execute(
                """
                INSERT INTO core.project (project_code, project_name)
                VALUES (%s, %s)
                RETURNING project_id
                """,
                (f"map_code_{suffix}", f"Mapping Code Project {suffix}"),
            ).fetchone(),
            "project_id",
        )
        tenant_id = _required_id(
            connection.execute(
                """
                INSERT INTO core.tenant (
                    project_id,
                    tenant_code,
                    tenant_name,
                    tenant_catalog,
                    gds_admin_catalog
                ) VALUES (%s, %s, %s, %s, %s)
                RETURNING tenant_id
                """,
                (
                    project_id,
                    f"MAP_CODE_{suffix}",
                    f"Mapping Code Tenant {suffix}",
                    f"map_code_catalog_{suffix}",
                    f"map_code_admin_{suffix}",
                ),
            ).fetchone(),
            "tenant_id",
        )
        principal_id = _required_id(
            connection.execute(
                """
                INSERT INTO security.principal (
                    principal_type,
                    principal_display_name,
                    principal_email
                ) VALUES ('user', %s, %s)
                RETURNING principal_id
                """,
                (
                    f"Mapping Code Reviewer {suffix}",
                    f"mapping-code-{suffix}@example.test",
                ),
            ).fetchone(),
            "principal_id",
        )
        connection.execute(
            """
            INSERT INTO security.entra_principal_identity (
                principal_id,
                principal_type,
                entra_tenant_id,
                entra_object_id
            ) VALUES (%s, 'user', %s, %s)
            """,
            (principal_id, entra_tenant_id, entra_object_id),
        )
        connection.execute(
            """
            INSERT INTO security.tenant_principal_access (
                tenant_id,
                principal_id,
                tenant_role,
                granted_by_principal_id
            ) VALUES (%s, %s, 'viewer', %s)
            """,
            (tenant_id, principal_id, principal_id),
        )
        model_id = _required_id(
            connection.execute(
                """
                INSERT INTO model.model (tenant_id, model_name)
                VALUES (%s, %s)
                RETURNING model_id
                """,
                (tenant_id, f"Mapping Code Model {suffix}"),
            ).fetchone(),
            "model_id",
        )

    database = WebPostgresDatabase(
        dsn=web_postgres_database.web_runtime_dsn(),
        pool_min=1,
        pool_max=2,
        pool_timeout_seconds=5,
    )
    principal = RequestPrincipal(
        actor_kind=ActorKind.HUMAN,
        entra_tenant_id=entra_tenant_id,
        entra_object_id=entra_object_id,
    )
    mapping_service = DatabaseMappingReviewService(
        database=database,
        authorizer=AuthorizationService(),
        cursor_signing_key=b"database-mapping-code-test-key",
    )
    code_service = DatabaseCodeGenerationService(
        database=database,
        authorizer=AuthorizationService(),
        cursor_signing_key=b"database-mapping-code-test-key",
    )

    await database.open()
    try:
        dependencies = await mapping_service.list_dependencies(
            principal,
            tenant_id=tenant_id,
            model_id=model_id,
            filters=MappingDependencyFilters(),
            page_size=25,
            cursor=None,
        )
        objects = await mapping_service.list_objects(
            principal,
            tenant_id=tenant_id,
            model_id=model_id,
            filters=MappingDependencyFilters(),
            page_size=25,
            cursor=None,
        )
        attributes = await mapping_service.list_attributes(
            principal,
            tenant_id=tenant_id,
            model_id=model_id,
            filters=MappingDependencyFilters(),
            page_size=25,
            cursor=None,
        )
        targets = await code_service.list_targets(
            principal,
            tenant_id=tenant_id,
            model_id=model_id,
            filters=CodeGenerationTargetFilters(),
            page_size=25,
            cursor=None,
        )

        assert dependencies.items == ()
        assert objects.items == ()
        assert attributes.items == ()
        assert targets.items == ()
        assert dependencies.model_revision == objects.model_revision
        assert objects.model_revision == attributes.model_revision
        assert attributes.model_revision == targets.model_revision

        with pytest.raises(MappingObjectNotFoundError):
            await mapping_service.read_object(
                principal,
                tenant_id=tenant_id,
                model_id=model_id,
                mapping_object_id=1,
            )
        with pytest.raises(MappingAttributeNotFoundError):
            await mapping_service.read_attribute(
                principal,
                tenant_id=tenant_id,
                model_id=model_id,
                mapping_attribute_id=1,
            )
        with pytest.raises(GeneratedSqlArtifactNotFoundError):
            await code_service.read_artifact(
                principal,
                tenant_id=tenant_id,
                model_id=model_id,
                generated_sql_artifact_id=1,
            )
        with pytest.raises(GeneratedSqlArtifactNotFoundError):
            await code_service.read_artifacts_for_download(
                principal,
                tenant_id=tenant_id,
                model_id=model_id,
                generated_sql_artifact_ids=(1,),
            )
    finally:
        await database.close()
