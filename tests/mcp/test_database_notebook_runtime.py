from __future__ import annotations

from typing import TYPE_CHECKING
from uuid import UUID

import pytest
from psycopg.errors import CheckViolation, InsufficientPrivilege

if TYPE_CHECKING:
    from conftest import DisposablePostgres


def test_notebook_runtime_identity_and_tenant_lock_surface(
    postgres_database: DisposablePostgres,
) -> None:
    entra_tenant_id = UUID("a1000000-0000-0000-0000-000000000001")
    entra_object_id = UUID("a2000000-0000-0000-0000-000000000001")
    application_id = UUID("a3000000-0000-0000-0000-000000000001")
    environment_code = "prod-us-east_1.v2"

    with postgres_database.connect_notebook_runtime() as connection:
        assert (
            connection.execute(
                "SELECT * FROM security.current_notebook_principal()"
            ).fetchone()
            is None
        )
        denied = connection.execute(
            """
            SELECT authorized, denial_code
              FROM security.check_notebook_tenant_lock(1::BIGINT)
            """
        ).fetchone()
    assert denied == {
        "authorized": False,
        "denial_code": "authorization_denied",
    }

    with postgres_database.connect_owner() as connection:
        project = connection.execute(
            """
            INSERT INTO core.project (project_code, project_name)
            VALUES ('NOTEBOOK_RUNTIME', 'Notebook Runtime Project')
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
            VALUES (
                %s,
                'NOTEBOOK_RUNTIME',
                'Notebook Runtime Tenant',
                'notebook_runtime_catalog',
                'notebook_runtime_admin',
                'private'
            )
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
                'Databricks Notebook Runtime',
                %s,
                'application',
                TRUE
            )
            RETURNING principal_id
            """,
            (application_id,),
        ).fetchone()
        assert principal is not None
        identity = connection.execute(
            """
            INSERT INTO security.entra_principal_identity (
                principal_id,
                principal_type,
                entra_tenant_id,
                entra_object_id
            )
            VALUES (%s, 'service_principal', %s, %s)
            RETURNING entra_principal_identity_id
            """,
            (principal["principal_id"], entra_tenant_id, entra_object_id),
        ).fetchone()
        assert identity is not None
        runtime_role = connection.execute(
            """
            SELECT oid, rolname
              FROM pg_catalog.pg_roles
             WHERE rolname = 'gds_notebook_runtime'
            """
        ).fetchone()
        assert runtime_role is not None
        connection.execute(
            """
            INSERT INTO security.notebook_runtime_principal (
                database_role_oid,
                database_role_name,
                entra_principal_identity_id,
                principal_id,
                principal_type,
                databricks_environment_code
            )
            VALUES (%s, %s, %s, %s, 'service_principal', %s)
            """,
            (
                runtime_role["oid"],
                runtime_role["rolname"],
                identity["entra_principal_identity_id"],
                principal["principal_id"],
                environment_code,
            ),
        )

    tenant_id = tenant["tenant_id"]
    principal_id = principal["principal_id"]
    with postgres_database.connect_notebook_runtime() as connection:
        resolved = connection.execute(
            "SELECT * FROM security.current_notebook_principal()"
        ).fetchone()
        checked = connection.execute(
            """
            SELECT authorized, denial_code, is_locked
              FROM security.check_notebook_tenant_lock(%s::BIGINT)
            """,
            (tenant_id,),
        ).fetchone()
        acquired = connection.execute(
            """
            SELECT acquired,
                   denial_code,
                   owner_display_name,
                   purpose,
                   EXTRACT(EPOCH FROM (expires_time - acquired_time))::INTEGER
                       AS duration_seconds
              FROM security.acquire_notebook_tenant_lock(
                  %s::BIGINT,
                  30::INTEGER,
                  'Notebook workflow'::VARCHAR
              )
            """,
            (tenant_id,),
        ).fetchone()
        owned = connection.execute(
            """
            SELECT is_locked, owned_by_current_principal, purpose
              FROM security.check_notebook_tenant_lock(%s::BIGINT)
            """,
            (tenant_id,),
        ).fetchone()
        renewed = connection.execute(
            """
            SELECT renewed,
                   denial_code,
                   EXTRACT(EPOCH FROM (expires_time - acquired_time))::INTEGER
                       AS duration_seconds
              FROM security.renew_notebook_tenant_lock(
                  %s::BIGINT,
                  45::INTEGER
              )
            """,
            (tenant_id,),
        ).fetchone()
        released = connection.execute(
            """
            SELECT released, denial_code, owner_display_name
              FROM security.release_notebook_tenant_lock(%s::BIGINT)
            """,
            (tenant_id,),
        ).fetchone()
        connection.execute("SET LOCAL ROLE gds_web_write")
        execution_identity = connection.execute(
            """
            SELECT SESSION_USER AS session_user,
                   CURRENT_USER AS current_user,
                   principal.principal_id,
                   principal.principal_display_name,
                   principal.is_super_admin
              FROM security.current_notebook_principal() AS principal
            """
        ).fetchone()
        execution_table_count = connection.execute(
            "SELECT count(*) AS row_count FROM application.workflow_run"
        ).fetchone()

    assert resolved == {
        "database_role_oid": runtime_role["oid"],
        "database_role_name": "gds_notebook_runtime",
        "entra_principal_identity_id": identity["entra_principal_identity_id"],
        "principal_id": principal_id,
        "principal_display_name": "Databricks Notebook Runtime",
        "entra_tenant_id": entra_tenant_id,
        "entra_object_id": entra_object_id,
        "principal_type": "service_principal",
        "databricks_environment_code": environment_code,
        "is_super_admin": True,
    }
    assert checked == {
        "authorized": True,
        "denial_code": None,
        "is_locked": False,
    }
    assert acquired == {
        "acquired": True,
        "denial_code": None,
        "owner_display_name": "Databricks Notebook Runtime",
        "purpose": "Notebook workflow",
        "duration_seconds": 1800,
    }
    assert owned == {
        "is_locked": True,
        "owned_by_current_principal": True,
        "purpose": "Notebook workflow",
    }
    assert renewed == {
        "renewed": True,
        "denial_code": None,
        "duration_seconds": 2700,
    }
    assert released == {
        "released": True,
        "denial_code": None,
        "owner_display_name": "Databricks Notebook Runtime",
    }
    assert execution_identity == {
        "session_user": "gds_notebook_runtime",
        "current_user": "gds_web_write",
        "principal_id": principal_id,
        "principal_display_name": "Databricks Notebook Runtime",
        "is_super_admin": True,
    }
    assert execution_table_count is not None
    assert execution_table_count["row_count"] >= 0

    with postgres_database.connect_owner() as connection:
        events = connection.execute(
            """
            SELECT tenant_lock_event_type,
                   lock_owner_principal_id,
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
        {
            "tenant_lock_event_type": "released",
            "lock_owner_principal_id": principal_id,
            "lock_acted_by_principal_id": principal_id,
        },
    ]

    with (
        postgres_database.connect_owner() as connection,
        pytest.raises(
            CheckViolation,
            match="ck_notebook_runtime_principal_environment_code",
        ),
    ):
        connection.execute(
            """
            UPDATE security.notebook_runtime_principal
               SET databricks_environment_code = '1 invalid environment'
            """
        )

    _assert_binding_fails_closed(
        postgres_database,
        principal_id=principal_id,
        runtime_role_name="renamed_notebook_runtime",
    )
    _assert_binding_fails_closed(
        postgres_database,
        principal_id=principal_id,
        runtime_role_oid=0,
    )
    _assert_binding_fails_closed(
        postgres_database,
        principal_id=principal_id,
        principal_active=False,
    )
    _assert_binding_fails_closed(
        postgres_database,
        principal_id=principal_id,
        principal_is_super_admin=False,
    )

    with (
        postgres_database.connect_notebook_runtime() as connection,
        pytest.raises(InsufficientPrivilege),
    ):
        connection.execute("SELECT principal_id FROM security.principal")

    with (
        postgres_database.connect_notebook_runtime() as connection,
        pytest.raises(InsufficientPrivilege),
    ):
        connection.execute(
            """
            SELECT *
              FROM security.check_tenant_lock(
                  %s::UUID,
                  %s::UUID,
                  'service_principal'::VARCHAR,
                  %s::BIGINT
              )
            """,
            (entra_tenant_id, entra_object_id, tenant_id),
        )

    with (
        postgres_database.connect_notebook_runtime() as connection,
        pytest.raises(InsufficientPrivilege),
    ):
        connection.execute(
            """
            SELECT *
              FROM security.override_tenant_lock(
                  %s::UUID,
                  %s::UUID,
                  'service_principal'::VARCHAR,
                  %s::BIGINT,
                  'not allowed'::VARCHAR
              )
            """,
            (entra_tenant_id, entra_object_id, tenant_id),
        )


def test_notebook_runtime_has_exact_noninherited_execution_membership(
    postgres_database: DisposablePostgres,
) -> None:
    with postgres_database.connect_owner() as connection:
        row = connection.execute(
            """
            SELECT (
                       SELECT count(*) = 1
                         FROM pg_catalog.pg_auth_members AS membership
                         JOIN pg_catalog.pg_roles AS member_role
                           ON member_role.oid = membership.member
                         JOIN pg_catalog.pg_roles AS group_role
                           ON group_role.oid = membership.roleid
                        WHERE member_role.rolname = 'gds_notebook_runtime'
                          AND group_role.rolname = 'gds_web_write'
                          AND NOT membership.admin_option
                          AND NOT membership.inherit_option
                          AND membership.set_option
                   ) AS has_exact_execution_membership,
                   NOT EXISTS (
                       SELECT 1
                         FROM pg_catalog.pg_class AS relation_record
                         JOIN pg_catalog.pg_namespace AS namespace_record
                           ON namespace_record.oid = relation_record.relnamespace
                        WHERE namespace_record.nspname IN (
                                  'reference', 'core', 'security', 'model',
                                  'workflow', 'application', 'mcp'
                              )
                          AND relation_record.relkind IN ('r', 'p', 'v', 'm', 'f')
                          AND (
                              has_table_privilege(
                                  'gds_notebook_runtime',
                                  relation_record.oid,
                                  'SELECT,INSERT,UPDATE,DELETE,TRUNCATE,REFERENCES,TRIGGER,MAINTAIN'
                              )
                              OR has_any_column_privilege(
                                  'gds_notebook_runtime',
                                  relation_record.oid,
                                  'SELECT,INSERT,UPDATE,REFERENCES'
                              )
                          )
                   ) AS has_no_inherited_table_privileges
            """
        ).fetchone()

    assert row == {
        "has_exact_execution_membership": True,
        "has_no_inherited_table_privileges": True,
    }
    with (
        postgres_database.connect_notebook_runtime() as connection,
        pytest.raises(InsufficientPrivilege),
    ):
        connection.execute("SELECT count(*) FROM application.workflow_run")


def _assert_binding_fails_closed(
    postgres_database: DisposablePostgres,
    *,
    principal_id: int,
    runtime_role_name: str | None = None,
    runtime_role_oid: int | None = None,
    principal_active: bool = True,
    principal_is_super_admin: bool = True,
) -> None:
    with postgres_database.connect_owner() as connection:
        connection.execute(
            """
            UPDATE security.notebook_runtime_principal
               SET database_role_name = coalesce(%s, database_role_name)
            """,
            (runtime_role_name,),
        )
        connection.execute(
            """
            UPDATE security.notebook_runtime_principal
               SET database_role_oid = coalesce(%s, database_role_oid)
            """,
            (runtime_role_oid,),
        )
        connection.execute(
            """
            UPDATE security.principal
               SET is_active = %s,
                   is_super_admin = %s
             WHERE principal_id = %s
            """,
            (principal_active, principal_is_super_admin, principal_id),
        )

    with postgres_database.connect_notebook_runtime() as connection:
        resolved = connection.execute(
            "SELECT * FROM security.current_notebook_principal()"
        ).fetchone()
        denied = connection.execute(
            """
            SELECT acquired, denial_code
              FROM security.acquire_notebook_tenant_lock(
                  1::BIGINT,
                  15::INTEGER,
                  'must fail closed'::VARCHAR
              )
            """
        ).fetchone()

    assert resolved is None
    assert denied == {
        "acquired": False,
        "denial_code": "authorization_denied",
    }

    with postgres_database.connect_owner() as connection:
        connection.execute(
            """
            UPDATE security.notebook_runtime_principal
               SET database_role_name = 'gds_notebook_runtime',
                   database_role_oid = (
                       SELECT oid
                         FROM pg_catalog.pg_roles
                        WHERE rolname = 'gds_notebook_runtime'
                   )
            """
        )
        connection.execute(
            """
            UPDATE security.principal
               SET is_active = TRUE,
                   is_super_admin = TRUE
             WHERE principal_id = %s
            """,
            (principal_id,),
        )
