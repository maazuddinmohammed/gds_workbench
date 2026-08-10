from __future__ import annotations

from typing import TYPE_CHECKING, cast
from uuid import UUID

import pytest

from gds_etl_workbench.application.authorization import ResolvedPrincipal
from gds_etl_workbench.domain.authorization import ActorKind
from gds_etl_workbench.tools.tenants.list_tenants import _query_visible_tenants

if TYPE_CHECKING:
    from conftest import DisposablePostgres
    from psycopg import Connection


def test_greenfield_schema_omits_workflow_grant_structures(
    postgres_database: DisposablePostgres,
) -> None:
    with postgres_database.connect_owner() as connection:
        row = connection.execute(
            """
            SELECT to_regclass('workflow.workflow_grant') AS workflow_grant,
                   to_regclass('workflow.workflow_run_summary') AS workflow_run_summary
            """
        ).fetchone()

    assert row == {"workflow_grant": None, "workflow_run_summary": None}


@pytest.mark.asyncio
async def test_list_tenants_sql_enforces_visibility_with_one_bound_actor(
    postgres_database: DisposablePostgres,
) -> None:
    entra_tenant_id = UUID("10000000-0000-0000-0000-000000000010")
    entra_object_id = UUID("20000000-0000-0000-0000-000000000010")
    with postgres_database.connect_owner() as connection:
        visible_private_id = _seed_private_tenant(connection, "LIST_SQL_MEMBER")
        _seed_private_tenant(connection, "LIST_SQL_HIDDEN")
        principal_id = _seed_user_actor(
            connection,
            tenant_id=visible_private_id,
            display_name="List SQL Developer",
            email="list.sql.developer@example.test",
            entra_tenant_id=entra_tenant_id,
            entra_object_id=entra_object_id,
            tenant_role="developer",
        )
        project = connection.execute(
            """
            INSERT INTO core.project (project_code, project_name)
            VALUES ('LIST_SQL_GLOBAL', 'List SQL Global Project')
            RETURNING project_id
            """
        ).fetchone()
        assert project is not None
        connection.execute(
            """
            INSERT INTO core.tenant (
                project_id,
                tenant_code,
                tenant_name,
                tenant_catalog,
                gds_admin_catalog,
                tenant_visibility
            )
            VALUES (%s, 'LIST_SQL_GLOBAL', 'List SQL Global Tenant',
                    'list_sql_global', 'list_sql_global_admin', 'global')
            """,
            (project["project_id"],),
        )

    database = postgres_database.create_runtime_adapter()
    await database.open()
    try:
        async with database.read_transaction() as transaction:
            rows = await _query_visible_tenants(
                transaction,
                ResolvedPrincipal(
                    principal_id=principal_id,
                    actor_kind=ActorKind.HUMAN,
                    display_name="List SQL Developer",
                    is_super_admin=False,
                ),
                limit=200,
                offset=0,
            )
    finally:
        await database.close()

    role_by_code = {row["tenant_code"]: row["effective_role"] for row in rows}
    assert role_by_code["LIST_SQL_GLOBAL"] == "viewer"
    assert role_by_code["LIST_SQL_MEMBER"] == "developer"
    assert "LIST_SQL_HIDDEN" not in role_by_code


def test_global_tenant_read_grants_implicit_viewer_access(
    postgres_database: DisposablePostgres,
) -> None:
    entra_tenant_id = UUID("10000000-0000-0000-0000-000000000001")
    entra_object_id = UUID("20000000-0000-0000-0000-000000000001")
    with postgres_database.connect_owner() as connection:
        project = connection.execute(
            """
            INSERT INTO core.project (project_code, project_name)
            VALUES ('AUTH_GLOBAL', 'Authorization Global Project')
            RETURNING project_id
            """
        ).fetchone()
        assert project is not None
        tenant = connection.execute(
            """
            INSERT INTO core.tenant (
                project_id,
                tenant_code,
                tenant_name,
                tenant_catalog,
                gds_admin_catalog,
                tenant_visibility
            )
            VALUES (%s, 'AUTH_GLOBAL', 'Authorization Global Tenant',
                    'global_catalog', 'global_admin', 'global')
            RETURNING tenant_id
            """,
            (project["project_id"],),
        ).fetchone()
        assert tenant is not None
        principal = connection.execute(
            """
            INSERT INTO security.principal (
                principal_type,
                principal_display_name,
                principal_email
            )
            VALUES ('user', 'Global Reader', 'global.reader@example.test')
            RETURNING principal_id
            """
        ).fetchone()
        assert principal is not None
        connection.execute(
            """
            INSERT INTO security.entra_principal_identity (
                principal_id,
                principal_type,
                entra_tenant_id,
                entra_object_id
            )
            VALUES (%s, 'user', %s, %s)
            """,
            (principal["principal_id"], entra_tenant_id, entra_object_id),
        )

    with postgres_database.connect_runtime() as connection:
        decision = connection.execute(
            """
            SELECT *
              FROM security.authorize_tenant_operation(%s, %s, %s, %s, %s)
            """,
            (
                entra_tenant_id,
                entra_object_id,
                "user",
                tenant["tenant_id"],
                "tenant_read",
            ),
        ).fetchone()

    assert decision is not None
    assert decision["authorized"] is True
    assert decision["effective_role"] == "viewer"
    assert decision["denial_code"] is None


def test_metadata_write_requires_an_owned_active_tenant_lock(
    postgres_database: DisposablePostgres,
) -> None:
    entra_tenant_id = UUID("10000000-0000-0000-0000-000000000002")
    entra_object_id = UUID("20000000-0000-0000-0000-000000000002")
    with postgres_database.connect_owner() as connection:
        project = connection.execute(
            """
            INSERT INTO core.project (project_code, project_name)
            VALUES ('AUTH_WRITE', 'Authorization Write Project')
            RETURNING project_id
            """
        ).fetchone()
        assert project is not None
        tenant = connection.execute(
            """
            INSERT INTO core.tenant (
                project_id,
                tenant_code,
                tenant_name,
                tenant_catalog,
                gds_admin_catalog,
                tenant_visibility
            )
            VALUES (%s, 'AUTH_WRITE', 'Authorization Write Tenant',
                    'write_catalog', 'write_admin', 'private')
            RETURNING tenant_id
            """,
            (project["project_id"],),
        ).fetchone()
        assert tenant is not None
        principal = connection.execute(
            """
            INSERT INTO security.principal (
                principal_type,
                principal_display_name,
                principal_email
            )
            VALUES ('user', 'Metadata Developer', 'metadata.developer@example.test')
            RETURNING principal_id
            """
        ).fetchone()
        assert principal is not None
        connection.execute(
            """
            INSERT INTO security.entra_principal_identity (
                principal_id,
                principal_type,
                entra_tenant_id,
                entra_object_id
            )
            VALUES (%s, 'user', %s, %s)
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
            VALUES (%s, %s, 'developer', %s)
            """,
            (
                tenant["tenant_id"],
                principal["principal_id"],
                principal["principal_id"],
            ),
        )

    with postgres_database.connect_runtime() as connection:
        decision = connection.execute(
            """
            SELECT *
              FROM security.authorize_tenant_operation(%s, %s, %s, %s, %s)
            """,
            (
                entra_tenant_id,
                entra_object_id,
                "user",
                tenant["tenant_id"],
                "tenant_metadata_write",
            ),
        ).fetchone()
        acquired = connection.execute(
            """
            SELECT acquired
              FROM security.acquire_tenant_lock(
                  %s::UUID, %s::UUID, 'user'::VARCHAR, %s::BIGINT,
                  NULL::INTEGER, 'Metadata write'::VARCHAR
              )
            """,
            (entra_tenant_id, entra_object_id, tenant["tenant_id"]),
        ).fetchone()
        allowed = connection.execute(
            """
            SELECT authorized,
                   denial_code,
                   lock_expires_time IS NOT NULL AS has_lock_expiry
              FROM security.authorize_tenant_operation(%s, %s, %s, %s, %s)
            """,
            (
                entra_tenant_id,
                entra_object_id,
                "user",
                tenant["tenant_id"],
                "tenant_metadata_write",
            ),
        ).fetchone()

    assert decision is not None
    assert decision["authorized"] is False
    assert decision["effective_role"] == "developer"
    assert decision["denial_code"] == "tenant_lock_required"
    assert acquired == {"acquired": True}
    assert allowed == {
        "authorized": True,
        "denial_code": None,
        "has_lock_expiry": True,
    }


def test_registered_workload_without_super_admin_authority_is_denied(
    postgres_database: DisposablePostgres,
) -> None:
    entra_tenant_id = UUID("10000000-0000-0000-0000-000000000003")
    entra_object_id = UUID("20000000-0000-0000-0000-000000000003")
    application_id = UUID("30000000-0000-0000-0000-000000000003")
    with postgres_database.connect_owner() as connection:
        project = connection.execute(
            """
            INSERT INTO core.project (project_code, project_name)
            VALUES ('AUTH_WORKLOAD', 'Authorization Workload Project')
            RETURNING project_id
            """
        ).fetchone()
        assert project is not None
        tenant = connection.execute(
            """
            INSERT INTO core.tenant (
                project_id,
                tenant_code,
                tenant_name,
                tenant_catalog,
                gds_admin_catalog,
                tenant_visibility
            )
            VALUES (%s, 'AUTH_WORKLOAD', 'Authorization Workload Tenant',
                    'workload_catalog', 'workload_admin', 'global')
            RETURNING tenant_id
            """,
            (project["project_id"],),
        ).fetchone()
        assert tenant is not None
        principal = connection.execute(
            """
            INSERT INTO security.principal (
                principal_type,
                principal_display_name,
                service_principal_application_id,
                service_principal_type,
                is_super_admin
            )
            VALUES (
                'service_principal',
                'Unprivileged Workflow',
                %s,
                'application',
                FALSE
            )
            RETURNING principal_id
            """,
            (application_id,),
        ).fetchone()
        assert principal is not None
        connection.execute(
            """
            INSERT INTO security.entra_principal_identity (
                principal_id,
                principal_type,
                entra_tenant_id,
                entra_object_id
            )
            VALUES (%s, 'service_principal', %s, %s)
            """,
            (principal["principal_id"], entra_tenant_id, entra_object_id),
        )

    with postgres_database.connect_runtime() as connection:
        decision = connection.execute(
            """
            SELECT *
              FROM security.authorize_tenant_operation(%s, %s, %s, %s, %s)
            """,
            (
                entra_tenant_id,
                entra_object_id,
                "service_principal",
                tenant["tenant_id"],
                "tenant_read",
            ),
        ).fetchone()

    assert decision is not None
    assert decision["authorized"] is False
    assert decision["denial_code"] == "authorization_denied"


def test_developer_acquires_a_default_tenant_lock_with_an_audit_event(
    postgres_database: DisposablePostgres,
) -> None:
    entra_tenant_id = UUID("10000000-0000-0000-0000-000000000004")
    entra_object_id = UUID("20000000-0000-0000-0000-000000000004")
    with postgres_database.connect_owner() as connection:
        project = connection.execute(
            """
            INSERT INTO core.project (project_code, project_name)
            VALUES ('AUTH_LOCK', 'Authorization Lock Project')
            RETURNING project_id
            """
        ).fetchone()
        assert project is not None
        tenant = connection.execute(
            """
            INSERT INTO core.tenant (
                project_id,
                tenant_code,
                tenant_name,
                tenant_catalog,
                gds_admin_catalog,
                tenant_visibility
            )
            VALUES (%s, 'AUTH_LOCK', 'Authorization Lock Tenant',
                    'lock_catalog', 'lock_admin', 'private')
            RETURNING tenant_id
            """,
            (project["project_id"],),
        ).fetchone()
        assert tenant is not None
        principal = connection.execute(
            """
            INSERT INTO security.principal (
                principal_type,
                principal_display_name,
                principal_email
            )
            VALUES ('user', 'Lock Developer', 'lock.developer@example.test')
            RETURNING principal_id
            """
        ).fetchone()
        assert principal is not None
        connection.execute(
            """
            INSERT INTO security.entra_principal_identity (
                principal_id,
                principal_type,
                entra_tenant_id,
                entra_object_id
            )
            VALUES (%s, 'user', %s, %s)
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
            VALUES (%s, %s, 'developer', %s)
            """,
            (
                tenant["tenant_id"],
                principal["principal_id"],
                principal["principal_id"],
            ),
        )

    with postgres_database.connect_runtime() as connection:
        result = connection.execute(
            """
            SELECT acquired,
                   denial_code,
                   owner_display_name,
                   purpose,
                   EXTRACT(EPOCH FROM (expires_time - acquired_time))::INTEGER
                       AS duration_seconds
              FROM security.acquire_tenant_lock(
                  %s::UUID,
                  %s::UUID,
                  %s::VARCHAR,
                  %s::BIGINT,
                  %s::INTEGER,
                  %s::VARCHAR
              )
            """,
            (
                entra_tenant_id,
                entra_object_id,
                "user",
                tenant["tenant_id"],
                None,
                "Edit source metadata",
            ),
        ).fetchone()

    assert result == {
        "acquired": True,
        "denial_code": None,
        "owner_display_name": "Lock Developer",
        "purpose": "Edit source metadata",
        "duration_seconds": 3600,
    }
    with postgres_database.connect_owner() as connection:
        event = connection.execute(
            """
            SELECT tenant_lock_event_type, lock_owner_principal_id,
                   lock_acted_by_principal_id
              FROM security.tenant_lock_event
             WHERE tenant_id = %s
            """,
            (tenant["tenant_id"],),
        ).fetchone()
    assert event == {
        "tenant_lock_event_type": "acquired",
        "lock_owner_principal_id": principal["principal_id"],
        "lock_acted_by_principal_id": principal["principal_id"],
    }


def test_explicit_override_replaces_the_lock_and_audits_the_reason(
    postgres_database: DisposablePostgres,
) -> None:
    first_tenant_id = UUID("10000000-0000-0000-0000-000000000005")
    first_object_id = UUID("20000000-0000-0000-0000-000000000005")
    second_tenant_id = UUID("10000000-0000-0000-0000-000000000006")
    second_object_id = UUID("20000000-0000-0000-0000-000000000006")
    with postgres_database.connect_owner() as connection:
        tenant_id = _seed_private_tenant(connection, "AUTH_OVERRIDE")
        first_principal_id = _seed_user_actor(
            connection,
            tenant_id=tenant_id,
            display_name="First Developer",
            email="first.override@example.test",
            entra_tenant_id=first_tenant_id,
            entra_object_id=first_object_id,
            tenant_role="developer",
        )
        second_principal_id = _seed_user_actor(
            connection,
            tenant_id=tenant_id,
            display_name="Second Developer",
            email="second.override@example.test",
            entra_tenant_id=second_tenant_id,
            entra_object_id=second_object_id,
            tenant_role="developer",
        )

    with postgres_database.connect_runtime() as connection:
        acquired = connection.execute(
            """
            SELECT acquired
              FROM security.acquire_tenant_lock(
                  %s::UUID, %s::UUID, 'user'::VARCHAR, %s::BIGINT,
                  NULL::INTEGER, 'First edit'::VARCHAR
              )
            """,
            (first_tenant_id, first_object_id, tenant_id),
        ).fetchone()
        assert acquired == {"acquired": True}
        overridden = connection.execute(
            """
            SELECT acquired, denial_code, owner_display_name, purpose
              FROM security.override_tenant_lock(
                  %s::UUID,
                  %s::UUID,
                  'user'::VARCHAR,
                  %s::BIGINT,
                  NULL::INTEGER,
                  'Second edit'::VARCHAR,
                  'Coordinated handoff'::VARCHAR
              )
            """,
            (second_tenant_id, second_object_id, tenant_id),
        ).fetchone()

    assert overridden == {
        "acquired": True,
        "denial_code": None,
        "owner_display_name": "Second Developer",
        "purpose": "Second edit",
    }
    with postgres_database.connect_owner() as connection:
        events = connection.execute(
            """
            SELECT tenant_lock_event_type,
                   lock_owner_principal_id,
                   lock_acted_by_principal_id,
                   tenant_lock_event_reason
              FROM security.tenant_lock_event
             WHERE tenant_id = %s
             ORDER BY tenant_lock_event_id
            """,
            (tenant_id,),
        ).fetchall()
    assert events == [
        {
            "tenant_lock_event_type": "acquired",
            "lock_owner_principal_id": first_principal_id,
            "lock_acted_by_principal_id": first_principal_id,
            "tenant_lock_event_reason": None,
        },
        {
            "tenant_lock_event_type": "force_unlocked",
            "lock_owner_principal_id": first_principal_id,
            "lock_acted_by_principal_id": second_principal_id,
            "tenant_lock_event_reason": "Coordinated handoff",
        },
        {
            "tenant_lock_event_type": "acquired",
            "lock_owner_principal_id": second_principal_id,
            "lock_acted_by_principal_id": second_principal_id,
            "tenant_lock_event_reason": None,
        },
    ]


def test_only_the_owner_can_renew_a_tenant_lock(
    postgres_database: DisposablePostgres,
) -> None:
    entra_tenant_id = UUID("10000000-0000-0000-0000-000000000007")
    entra_object_id = UUID("20000000-0000-0000-0000-000000000007")
    with postgres_database.connect_owner() as connection:
        tenant_id = _seed_private_tenant(connection, "AUTH_RENEW")
        principal_id = _seed_user_actor(
            connection,
            tenant_id=tenant_id,
            display_name="Renewing Developer",
            email="renewing.developer@example.test",
            entra_tenant_id=entra_tenant_id,
            entra_object_id=entra_object_id,
            tenant_role="developer",
        )

    with postgres_database.connect_runtime() as connection:
        acquired = connection.execute(
            """
            SELECT acquired
              FROM security.acquire_tenant_lock(
                  %s::UUID, %s::UUID, 'user'::VARCHAR, %s::BIGINT,
                  1::INTEGER, 'Renewable edit'::VARCHAR
              )
            """,
            (entra_tenant_id, entra_object_id, tenant_id),
        ).fetchone()
        assert acquired == {"acquired": True}
        renewed = connection.execute(
            """
            SELECT renewed,
                   denial_code,
                   owner_display_name,
                   EXTRACT(EPOCH FROM (expires_time - acquired_time))::INTEGER
                       AS duration_seconds
              FROM security.renew_tenant_lock(
                  %s::UUID,
                  %s::UUID,
                  'user'::VARCHAR,
                  %s::BIGINT,
                  120::INTEGER
              )
            """,
            (entra_tenant_id, entra_object_id, tenant_id),
        ).fetchone()

    assert renewed == {
        "renewed": True,
        "denial_code": None,
        "owner_display_name": "Renewing Developer",
        "duration_seconds": 7200,
    }
    with postgres_database.connect_owner() as connection:
        events = connection.execute(
            """
            SELECT tenant_lock_event_type, lock_owner_principal_id,
                   lock_acted_by_principal_id
              FROM security.tenant_lock_event
             WHERE tenant_id = %s
             ORDER BY tenant_lock_event_id
            """,
            (tenant_id,),
        ).fetchall()
    assert events == [
        {
            "tenant_lock_event_type": "acquired",
            "lock_owner_principal_id": principal_id,
            "lock_acted_by_principal_id": principal_id,
        },
        {
            "tenant_lock_event_type": "renewed",
            "lock_owner_principal_id": principal_id,
            "lock_acted_by_principal_id": principal_id,
        },
    ]


def test_owner_release_removes_the_lock_and_records_an_event(
    postgres_database: DisposablePostgres,
) -> None:
    entra_tenant_id = UUID("10000000-0000-0000-0000-000000000008")
    entra_object_id = UUID("20000000-0000-0000-0000-000000000008")
    with postgres_database.connect_owner() as connection:
        tenant_id = _seed_private_tenant(connection, "AUTH_RELEASE")
        principal_id = _seed_user_actor(
            connection,
            tenant_id=tenant_id,
            display_name="Releasing Developer",
            email="releasing.developer@example.test",
            entra_tenant_id=entra_tenant_id,
            entra_object_id=entra_object_id,
            tenant_role="developer",
        )

    with postgres_database.connect_runtime() as connection:
        acquired = connection.execute(
            """
            SELECT acquired
              FROM security.acquire_tenant_lock(
                  %s::UUID, %s::UUID, 'user'::VARCHAR, %s::BIGINT,
                  NULL::INTEGER, 'Release test'::VARCHAR
              )
            """,
            (entra_tenant_id, entra_object_id, tenant_id),
        ).fetchone()
        assert acquired == {"acquired": True}
        released = connection.execute(
            """
            SELECT released, denial_code, owner_display_name
              FROM security.release_tenant_lock(
                  %s::UUID,
                  %s::UUID,
                  'user'::VARCHAR,
                  %s::BIGINT
              )
            """,
            (entra_tenant_id, entra_object_id, tenant_id),
        ).fetchone()

    assert released == {
        "released": True,
        "denial_code": None,
        "owner_display_name": "Releasing Developer",
    }
    with postgres_database.connect_owner() as connection:
        state = connection.execute(
            """
            SELECT NOT EXISTS (
                       SELECT 1 FROM security.tenant_lock WHERE tenant_id = %s
                   ) AS lock_removed,
                   (
                       SELECT tenant_lock_event_type
                         FROM security.tenant_lock_event
                        WHERE tenant_id = %s
                        ORDER BY tenant_lock_event_id DESC
                        LIMIT 1
                   ) AS last_event
            """,
            (tenant_id, tenant_id),
        ).fetchone()
    assert state == {"lock_removed": True, "last_event": "released"}
    assert principal_id > 0


def test_expiry_operation_removes_stale_locks_and_records_events(
    postgres_database: DisposablePostgres,
) -> None:
    entra_tenant_id = UUID("10000000-0000-0000-0000-000000000009")
    entra_object_id = UUID("20000000-0000-0000-0000-000000000009")
    with postgres_database.connect_owner() as connection:
        tenant_id = _seed_private_tenant(connection, "AUTH_EXPIRE")
        principal_id = _seed_user_actor(
            connection,
            tenant_id=tenant_id,
            display_name="Expired Developer",
            email="expired.developer@example.test",
            entra_tenant_id=entra_tenant_id,
            entra_object_id=entra_object_id,
            tenant_role="developer",
        )
        connection.execute(
            """
            INSERT INTO security.tenant_lock (
                tenant_id,
                locked_by_principal_id,
                tenant_lock_purpose,
                tenant_lock_acquired_time,
                tenant_lock_expires_time
            )
            VALUES (
                %s,
                %s,
                'Expired edit',
                CURRENT_TIMESTAMP - INTERVAL '2 hours',
                CURRENT_TIMESTAMP - INTERVAL '1 hour'
            )
            """,
            (tenant_id, principal_id),
        )

    with postgres_database.connect_runtime() as connection:
        result = connection.execute(
            "SELECT security.expire_tenant_locks(100) AS expired_count"
        ).fetchone()

    assert result == {"expired_count": 1}
    with postgres_database.connect_owner() as connection:
        state = connection.execute(
            """
            SELECT NOT EXISTS (
                       SELECT 1 FROM security.tenant_lock WHERE tenant_id = %s
                   ) AS lock_removed,
                   (
                       SELECT tenant_lock_event_type
                         FROM security.tenant_lock_event
                        WHERE tenant_id = %s
                        ORDER BY tenant_lock_event_id DESC
                        LIMIT 1
                   ) AS last_event,
                   (
                       SELECT lock_acted_by_principal_id
                         FROM security.tenant_lock_event
                        WHERE tenant_id = %s
                        ORDER BY tenant_lock_event_id DESC
                        LIMIT 1
                   ) AS acted_by
            """,
            (tenant_id, tenant_id, tenant_id),
        ).fetchone()
    assert state == {
        "lock_removed": True,
        "last_event": "expired",
        "acted_by": None,
    }


@pytest.mark.asyncio
async def test_runtime_adapter_accepts_the_authorization_schema(
    postgres_database: DisposablePostgres,
) -> None:
    database = postgres_database.create_runtime_adapter()
    await database.open()
    try:
        readiness = await database.readiness()
        expired_count = await database.expire_tenant_locks()
    finally:
        await database.close()

    assert readiness.ready is True
    assert readiness.code == "ready"
    assert expired_count >= 0


def _seed_private_tenant(
    connection: Connection[dict[str, object]],
    code: str,
) -> int:
    project = connection.execute(
        """
        INSERT INTO core.project (project_code, project_name)
        VALUES (%s, %s)
        RETURNING project_id
        """,
        (code, f"{code} Project"),
    ).fetchone()
    assert project is not None
    tenant = connection.execute(
        """
        INSERT INTO core.tenant (
            project_id,
            tenant_code,
            tenant_name,
            tenant_catalog,
            gds_admin_catalog,
            tenant_visibility
        )
        VALUES (%s, %s, %s, %s, %s, 'private')
        RETURNING tenant_id
        """,
        (
            project["project_id"],
            code,
            f"{code} Tenant",
            f"{code.lower()}_catalog",
            f"{code.lower()}_admin",
        ),
    ).fetchone()
    assert tenant is not None
    return cast(int, tenant["tenant_id"])


def _seed_user_actor(
    connection: Connection[dict[str, object]],
    *,
    tenant_id: int,
    display_name: str,
    email: str,
    entra_tenant_id: UUID,
    entra_object_id: UUID,
    tenant_role: str,
) -> int:
    principal = connection.execute(
        """
        INSERT INTO security.principal (
            principal_type,
            principal_display_name,
            principal_email
        )
        VALUES ('user', %s, %s)
        RETURNING principal_id
        """,
        (display_name, email),
    ).fetchone()
    assert principal is not None
    principal_id = cast(int, principal["principal_id"])
    connection.execute(
        """
        INSERT INTO security.entra_principal_identity (
            principal_id,
            principal_type,
            entra_tenant_id,
            entra_object_id
        )
        VALUES (%s, 'user', %s, %s)
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
        )
        VALUES (%s, %s, %s, %s)
        """,
        (tenant_id, principal_id, tenant_role, principal_id),
    )
    return principal_id
