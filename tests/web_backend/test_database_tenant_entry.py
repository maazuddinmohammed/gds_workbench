from uuid import uuid4

import pytest
from gds_etl_workbench.application.authorization import (
    AuthorizationService,
    ResolvedPrincipal,
)
from gds_etl_workbench.domain.authorization import ActorKind, RequestPrincipal
from gds_etl_workbench.application.tenants import query_visible_tenants
from tests.mcp.conftest import DisposablePostgres

from gds_workbench_api.database import WebPostgresDatabase
from gds_workbench_api.features.session import DatabaseSessionService
from gds_workbench_api.features.tenants import DatabaseTenantService


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
    assert session.email == f"web_{suffix}@example.test"
    assert session.last_tenant_id == tenant["tenant_id"]


@pytest.mark.asyncio
async def test_tenant_entry_pages_only_non_global_data_store_owner_tenants(
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
            (f"web_selector_project_{suffix}", f"Web Selector Project {suffix}"),
        ).fetchone()
        system_type = connection.execute(
            """
            INSERT INTO reference.system_type (system_type_code, system_type_name)
            VALUES (%s, %s)
            RETURNING system_type_id
            """,
            (
                f"web_selector_system_{suffix}",
                f"Web Selector System {suffix}",
            ),
        ).fetchone()
        connection_type = connection.execute(
            """
            INSERT INTO reference.connection_type (
                connection_type_code,
                connection_type_name
            ) VALUES (%s, %s)
            RETURNING connection_type_id
            """,
            (
                f"web_selector_connection_{suffix}",
                f"Web Selector Connection {suffix}",
            ),
        ).fetchone()
        assert project is not None
        assert system_type is not None
        assert connection_type is not None

        tenant_rows = connection.execute(
            """
            INSERT INTO core.tenant (
                project_id,
                tenant_code,
                tenant_name,
                tenant_catalog,
                gds_admin_catalog
            ) VALUES (%s, %s, %s, %s, %s),
                     (%s, %s, %s, %s, %s),
                     (%s, %s, %s, %s, %s),
                     (%s, %s, %s, %s, %s)
            RETURNING tenant_id, tenant_code
            """,
            (
                project["project_id"],
                f"WEB_SELECTOR_GDS_{suffix}",
                f"!00 Web Selector Global Data Store {suffix}",
                f"web_selector_gds_catalog_{suffix}",
                f"web_selector_gds_admin_{suffix}",
                project["project_id"],
                f"WEB_SELECTOR_INACTIVE_GDS_{suffix}",
                f"!01 Web Selector Inactive Global Data Store {suffix}",
                f"web_selector_inactive_gds_catalog_{suffix}",
                f"web_selector_inactive_gds_admin_{suffix}",
                project["project_id"],
                f"WEB_SELECTOR_A_{suffix}",
                f"!10 Web Selector Tenant {suffix}",
                f"web_selector_a_catalog_{suffix}",
                f"web_selector_a_admin_{suffix}",
                project["project_id"],
                f"WEB_SELECTOR_B_{suffix}",
                f"!11 Web Selector Tenant {suffix}",
                f"web_selector_b_catalog_{suffix}",
                f"web_selector_b_admin_{suffix}",
            ),
        ).fetchall()
        tenant_by_code = {row["tenant_code"]: row for row in tenant_rows}
        gds_owner_tenant = tenant_by_code[f"WEB_SELECTOR_GDS_{suffix}"]
        inactive_gds_owner_tenant = tenant_by_code[
            f"WEB_SELECTOR_INACTIVE_GDS_{suffix}"
        ]
        regular_tenant_a = tenant_by_code[f"WEB_SELECTOR_A_{suffix}"]
        regular_tenant_b = tenant_by_code[f"WEB_SELECTOR_B_{suffix}"]
        system = connection.execute(
            """
            INSERT INTO core.system (system_code, system_name, system_type_id)
            VALUES (%s, %s, %s)
            RETURNING system_id
            """,
            (
                f"WEB_SELECTOR_SYSTEM_{suffix}",
                f"Web Selector System {suffix}",
                system_type["system_type_id"],
            ),
        ).fetchone()
        assert system is not None
        connection.execute(
            """
            INSERT INTO core.connection (
                tenant_id,
                system_id,
                connection_code,
                connection_name,
                connection_type_id,
                is_global_data_store,
                is_active
            ) VALUES (%s, %s, %s, %s, %s, TRUE, TRUE),
                     (%s, %s, %s, %s, %s, TRUE, FALSE)
            """,
            (
                gds_owner_tenant["tenant_id"],
                system["system_id"],
                f"WEB_SELECTOR_GDS_{suffix}",
                f"Web Selector Global Data Store {suffix}",
                connection_type["connection_type_id"],
                inactive_gds_owner_tenant["tenant_id"],
                system["system_id"],
                f"WEB_SELECTOR_INACTIVE_GDS_{suffix}",
                f"Web Selector Inactive Global Data Store {suffix}",
                connection_type["connection_type_id"],
            ),
        )
        principal = connection.execute(
            """
            INSERT INTO security.principal (
                principal_type,
                principal_display_name,
                principal_email
            ) VALUES ('user', %s, %s)
            RETURNING principal_id
            """,
            (f"Web Selector User {suffix}", f"web_selector_{suffix}@example.test"),
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
            )
            VALUES (%s, %s, 'tenant_admin', %s),
                   (%s, %s, 'tenant_admin', %s),
                   (%s, %s, 'tenant_admin', %s),
                   (%s, %s, 'tenant_admin', %s)
            """,
            (
                regular_tenant_a["tenant_id"],
                principal["principal_id"],
                principal["principal_id"],
                regular_tenant_b["tenant_id"],
                principal["principal_id"],
                principal["principal_id"],
                gds_owner_tenant["tenant_id"],
                principal["principal_id"],
                principal["principal_id"],
                inactive_gds_owner_tenant["tenant_id"],
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
    tenant_service = DatabaseTenantService(
        database=database,
        authorizer=AuthorizationService(),
        cursor_signing_key=b"development-only-key-32-bytes-long",
    )
    request_principal = RequestPrincipal(
        actor_kind=ActorKind.HUMAN,
        entra_tenant_id=entra_tenant_id,
        entra_object_id=entra_object_id,
    )

    await database.open()
    try:
        async with database.read_transaction() as transaction:
            shared_visible_rows = await query_visible_tenants(
                transaction,
                ResolvedPrincipal(
                    principal_id=principal["principal_id"],
                    actor_kind=ActorKind.HUMAN,
                    display_name=f"Web Selector User {suffix}",
                    is_super_admin=False,
                ),
                limit=10,
                offset=0,
            )
        first_page = await tenant_service.list_tenants(
            request_principal,
            page_size=1,
            cursor=None,
        )
        assert first_page.next_cursor is not None
        second_page = await tenant_service.list_tenants(
            request_principal,
            page_size=1,
            cursor=first_page.next_cursor,
        )
    finally:
        await database.close()

    shared_visible_tenant_ids = {row["tenant_id"] for row in shared_visible_rows}
    assert gds_owner_tenant["tenant_id"] in shared_visible_tenant_ids
    assert inactive_gds_owner_tenant["tenant_id"] in shared_visible_tenant_ids
    assert [item.tenant_id for item in first_page.items] == [
        regular_tenant_a["tenant_id"]
    ]
    assert [item.tenant_id for item in second_page.items] == [
        regular_tenant_b["tenant_id"]
    ]
