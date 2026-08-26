from uuid import uuid4

import pytest
from gds_etl_workbench.application.authorization import AuthorizationService
from gds_etl_workbench.domain.authorization import ActorKind, RequestPrincipal
from tests.mcp.conftest import DisposablePostgres

from gds_workbench_api.database import WebPostgresDatabase
from gds_workbench_api.features.tenants import DatabaseTenantService
from gds_workbench_api.features.session import DatabaseSessionService


@pytest.mark.asyncio
async def test_tenant_entry_round_trip_uses_only_the_web_runtime_role(
    web_postgres_database: DisposablePostgres,
) -> None:
    entra_tenant_id = uuid4()
    entra_object_id = uuid4()
    suffix = uuid4().hex
    with web_postgres_database.connect_owner() as connection:
        project = connection.execute(
            """
            INSERT INTO core.project (project_code, project_name)
            VALUES (%s, %s)
            RETURNING project_id
            """,
            (f"web_project_{suffix}", f"Web Project {suffix}"),
        ).fetchone()
        assert project is not None
        tenant = connection.execute(
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
                project["project_id"],
                f"WEB_{suffix}",
                f"Web Tenant {suffix}",
                f"web_catalog_{suffix}",
                f"web_admin_{suffix}",
            ),
        ).fetchone()
        assert tenant is not None
        principal = connection.execute(
            """
            INSERT INTO security.principal (
                principal_type,
                principal_display_name,
                principal_email
            ) VALUES ('user', %s, %s)
            RETURNING principal_id
            """,
            (f"Web User {suffix}", f"web_{suffix}@example.test"),
        ).fetchone()
        assert principal is not None
        connection.execute(
            """
            INSERT INTO security.entra_principal_identity (
                principal_id,
                principal_type,
                entra_tenant_id,
                entra_object_id
            ) VALUES (%s, 'user', %s, %s)
            """,
            (principal["principal_id"], entra_tenant_id, entra_object_id),
        )
        connection.execute(
            """
            INSERT INTO security.tenant_principal_access (
                tenant_id,
                principal_id,
                tenant_role,
                granted_by_principal_id
            ) VALUES (%s, %s, 'tenant_admin', %s)
            """,
            (
                tenant["tenant_id"],
                principal["principal_id"],
                principal["principal_id"],
            ),
        )

    database = WebPostgresDatabase(
        dsn=web_postgres_database.web_runtime_dsn(),
        pool_min=1,
        pool_max=1,
        pool_timeout_seconds=5,
    )
    authorizer = AuthorizationService()
    session_service = DatabaseSessionService(
        database=database,
        authorizer=authorizer,
    )
    tenant_service = DatabaseTenantService(
        database=database,
        authorizer=authorizer,
        cursor_signing_key=b"development-only-key-32-bytes-long",
    )
    request_principal = RequestPrincipal(
        actor_kind=ActorKind.HUMAN,
        entra_tenant_id=entra_tenant_id,
        entra_object_id=entra_object_id,
    )

    await database.open()
    try:
        tenants = await tenant_service.list_tenants(
            request_principal,
            page_size=50,
            cursor=None,
        )
        selected = await tenant_service.select_tenant(
            request_principal,
            tenant_id=tenant["tenant_id"],
        )
        session = await session_service.read_session(request_principal)
    finally:
        await database.close()

    assert [item.tenant_id for item in tenants.items] == [tenant["tenant_id"]]
    assert selected.tenant_id == tenant["tenant_id"]
    assert session.last_tenant_id == tenant["tenant_id"]
