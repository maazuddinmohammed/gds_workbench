from __future__ import annotations

from typing import TYPE_CHECKING, cast
from uuid import UUID, uuid4

import pytest
from gds_etl_workbench.application.authorization import (
    AuthorizationService,
    ResolvedPrincipal,
)
from gds_etl_workbench.application.tenants import query_visible_tenants
from gds_etl_workbench.domain.authorization import (
    ActorKind,
    RequestPrincipal,
    TenantRole,
    ToolPolicy,
)
from gds_etl_workbench.domain.errors import (
    AuthorizationDeniedError,
    TenantNotFoundError,
)
from gds_etl_workbench.infrastructure.postgres import ReadIsolation
from psycopg.errors import ForeignKeyViolation, InvalidParameterValue, UniqueViolation

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


def test_authorization_rejects_a_null_policy(
    postgres_database: DisposablePostgres,
) -> None:
    with (
        postgres_database.connect_owner() as connection,
        pytest.raises(InvalidParameterValue, match="unsupported authorization policy"),
    ):
        connection.execute(
            """
            SELECT *
              FROM security.authorize_tenant_operation(
                  %s::UUID, %s::UUID, 'user'::VARCHAR,
                  1::BIGINT, NULL::VARCHAR
              )
            """,
            (UUID(int=1), UUID(int=2)),
        )


def test_authorization_rejects_a_null_expected_principal_type(
    postgres_database: DisposablePostgres,
) -> None:
    with (
        postgres_database.connect_owner() as connection,
        pytest.raises(InvalidParameterValue, match="unsupported Principal type"),
    ):
        connection.execute(
            """
            SELECT *
              FROM security.authorize_tenant_operation(
                  %s::UUID, %s::UUID, NULL::VARCHAR,
                  1::BIGINT, 'tenant_read'::VARCHAR
              )
            """,
            (UUID(int=1), UUID(int=2)),
        )


def test_context_tables_replace_legacy_assertion_and_evidence_tables(
    postgres_database: DisposablePostgres,
) -> None:
    with postgres_database.connect_owner() as connection:
        row = connection.execute(
            """
            SELECT to_regclass('reference.context_type')
                       AS context_type,
                   to_regclass('project.context_group')
                       AS context_group,
                   to_regclass('project.context_record')
                       AS context_record,
                   to_regnamespace('model') AS legacy_model_schema,
                   to_regclass('core.project') AS legacy_core_project,
                   to_regclass('project.modeling_assertion_document')
                       AS legacy_assertion_document,
                   to_regclass('project.modeling_assertion_record')
                       AS legacy_assertion_record,
                   to_regclass('project.modeling_evidence_document')
                       AS evidence_document,
                   to_regclass('project.modeling_evidence_record')
                       AS evidence_record
            """
        ).fetchone()

    assert row == {
        "context_type": "reference.context_type",
        "context_group": "project.context_group",
        "context_record": "project.context_record",
        "legacy_model_schema": None,
        "legacy_core_project": None,
        "legacy_assertion_document": None,
        "legacy_assertion_record": None,
        "evidence_document": None,
        "evidence_record": None,
    }


@pytest.mark.asyncio
async def test_runtime_resolves_an_active_human_principal(
    postgres_database: DisposablePostgres,
) -> None:
    entra_tenant_id = UUID("10000000-0000-0000-0000-000000000011")
    entra_object_id = UUID("20000000-0000-0000-0000-000000000011")
    with postgres_database.connect_owner() as connection:
        principal = connection.execute(
            """
            INSERT INTO security.principal (
                principal_type,
                principal_display_name,
                principal_email
            )
            VALUES ('user', 'Runtime Reader', 'runtime.reader@example.test')
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

    database = postgres_database.create_runtime_adapter()
    await database.open()
    try:
        async with database.read_transaction() as transaction:
            resolved = await AuthorizationService().resolve_principal(
                transaction,
                RequestPrincipal(
                    actor_kind=ActorKind.HUMAN,
                    entra_tenant_id=entra_tenant_id,
                    entra_object_id=entra_object_id,
                ),
            )
    finally:
        await database.close()

    assert resolved == ResolvedPrincipal(
        principal_id=principal["principal_id"],
        actor_kind=ActorKind.HUMAN,
        display_name="Runtime Reader",
        is_super_admin=False,
    )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "isolation",
    [ReadIsolation.READ_COMMITTED, ReadIsolation.REPEATABLE_READ],
)
async def test_runtime_authorizes_human_tenant_read_in_a_read_only_transaction(
    postgres_database: DisposablePostgres,
    isolation: ReadIsolation,
) -> None:
    identity_suffix = 12 if isolation is ReadIsolation.READ_COMMITTED else 15
    entra_tenant_id = UUID(f"10000000-0000-0000-0000-{identity_suffix:012d}")
    entra_object_id = UUID(f"20000000-0000-0000-0000-{identity_suffix:012d}")
    with postgres_database.connect_owner() as connection:
        tenant_id = _seed_private_tenant(
            connection,
            f"RUNTIME_TENANT_READ_{isolation.value.upper()}",
        )
        principal_id = _seed_user_actor(
            connection,
            tenant_id=tenant_id,
            display_name="Runtime Tenant Reader",
            email=f"runtime.tenant.reader.{isolation.value}@example.test",
            entra_tenant_id=entra_tenant_id,
            entra_object_id=entra_object_id,
            tenant_role="viewer",
        )

    database = postgres_database.create_runtime_adapter()
    await database.open()
    try:
        async with database.read_transaction(isolation=isolation) as transaction:
            decision = await AuthorizationService().authorize_tenant(
                transaction,
                RequestPrincipal(
                    actor_kind=ActorKind.HUMAN,
                    entra_tenant_id=entra_tenant_id,
                    entra_object_id=entra_object_id,
                ),
                tenant_id=tenant_id,
                policy=ToolPolicy.TENANT_READ,
            )
    finally:
        await database.close()

    assert decision.principal.principal_id == principal_id
    assert decision.effective_role is TenantRole.VIEWER
    assert decision.lock_expires_time is None


@pytest.mark.asyncio
async def test_runtime_hides_a_private_tenant_without_access(
    postgres_database: DisposablePostgres,
) -> None:
    entra_tenant_id = UUID("10000000-0000-0000-0000-000000000013")
    entra_object_id = UUID("20000000-0000-0000-0000-000000000013")
    with postgres_database.connect_owner() as connection:
        tenant_id = _seed_private_tenant(connection, "RUNTIME_PRIVATE_HIDDEN")
        principal = connection.execute(
            """
            INSERT INTO security.principal (
                principal_type,
                principal_display_name,
                principal_email
            )
            VALUES ('user', 'Private Outsider', 'private.outsider@example.test')
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

    database = postgres_database.create_runtime_adapter()
    await database.open()
    try:
        with pytest.raises(TenantNotFoundError):
            async with database.read_transaction() as transaction:
                await AuthorizationService().authorize_tenant(
                    transaction,
                    RequestPrincipal(
                        actor_kind=ActorKind.HUMAN,
                        entra_tenant_id=entra_tenant_id,
                        entra_object_id=entra_object_id,
                    ),
                    tenant_id=tenant_id,
                    policy=ToolPolicy.TENANT_READ,
                )
    finally:
        await database.close()


@pytest.mark.asyncio
async def test_runtime_denies_a_non_admin_workload_tenant_read(
    postgres_database: DisposablePostgres,
) -> None:
    entra_tenant_id = UUID("10000000-0000-0000-0000-000000000014")
    entra_object_id = UUID("20000000-0000-0000-0000-000000000014")
    application_id = UUID("30000000-0000-0000-0000-000000000014")
    with postgres_database.connect_owner() as connection:
        tenant_id = _seed_private_tenant(connection, "RUNTIME_WORKLOAD_DENIED")
        principal = connection.execute(
            """
            INSERT INTO security.principal (
                principal_type,
                principal_display_name,
                service_principal_application_id,
                service_principal_type,
                is_super_admin
            )
            VALUES ('service_principal', 'Runtime Workflow', %s, 'application', FALSE)
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

    database = postgres_database.create_runtime_adapter()
    await database.open()
    try:
        with pytest.raises(AuthorizationDeniedError):
            async with database.read_transaction() as transaction:
                await AuthorizationService().authorize_tenant(
                    transaction,
                    RequestPrincipal(
                        actor_kind=ActorKind.WORKLOAD,
                        entra_tenant_id=entra_tenant_id,
                        entra_object_id=entra_object_id,
                    ),
                    tenant_id=tenant_id,
                    policy=ToolPolicy.TENANT_READ,
                )
    finally:
        await database.close()


def test_mcp_schema_owns_change_sets_and_tool_call_log(
    postgres_database: DisposablePostgres,
) -> None:
    with postgres_database.connect_owner() as connection:
        row = connection.execute(
            """
            SELECT to_regclass('mcp.project_change_set') AS project_change_set,
                   to_regclass('mcp.project_change_set_event')
                       AS project_change_set_event,
                   to_regclass('mcp.metadata_change_set')
                       AS metadata_change_set,
                   to_regclass('mcp.metadata_change_set_event')
                       AS metadata_change_set_event,
                   to_regclass('mcp.tool_call_log') AS tool_call_log,
                   to_regclass('workflow.project_change_set')
                       AS old_project_change_set,
                   to_regclass('workflow.metadata_change_set')
                       AS old_metadata_change_set,
                   to_regclass('security.mcp_tool_call_log')
                       AS old_tool_call_log
            """
        ).fetchone()

    assert row == {
        "project_change_set": "mcp.project_change_set",
        "project_change_set_event": "mcp.project_change_set_event",
        "metadata_change_set": "mcp.metadata_change_set",
        "metadata_change_set_event": "mcp.metadata_change_set_event",
        "tool_call_log": "mcp.tool_call_log",
        "old_project_change_set": None,
        "old_metadata_change_set": None,
        "old_tool_call_log": None,
    }


def test_artifact_lock_event_tables_are_absent(
    postgres_database: DisposablePostgres,
) -> None:
    with postgres_database.connect_owner() as connection:
        row = connection.execute(
            """
            SELECT to_regclass('security.artifact_lock_event')
                       AS artifact_lock_event,
                   to_regclass('security.metadata_artifact_lock_event')
                       AS metadata_artifact_lock_event
            """
        ).fetchone()

    assert row == {
        "artifact_lock_event": None,
        "metadata_artifact_lock_event": None,
    }


def test_project_change_set_uses_context_contract_names(
    postgres_database: DisposablePostgres,
) -> None:
    with postgres_database.connect_owner() as connection:
        columns = connection.execute(
            """
            SELECT EXISTS (
                       SELECT 1 FROM information_schema.columns
                        WHERE table_schema = 'mcp'
                          AND table_name = 'project_change_set'
                          AND column_name = 'base_context_digest'
                   ) AS base_context_digest,
                   EXISTS (
                       SELECT 1 FROM information_schema.columns
                        WHERE table_schema = 'mcp'
                          AND table_name = 'project_change_set'
                          AND column_name = 'context_document'
                   ) AS context_document,
                   EXISTS (
                       SELECT 1 FROM information_schema.columns
                        WHERE table_schema = 'mcp'
                          AND table_name = 'project_change_set'
                          AND column_name = 'base_evidence_digest'
                   ) AS base_evidence_digest,
                   EXISTS (
                       SELECT 1 FROM information_schema.columns
                        WHERE table_schema = 'mcp'
                          AND table_name = 'project_change_set'
                          AND column_name = 'evidence_document'
                   ) AS evidence_document
            """
        ).fetchone()
        constraints = connection.execute(
            """
            SELECT conname, pg_get_constraintdef(oid) AS definition
              FROM pg_constraint
             WHERE conname IN (
                 'ck_change_set_event_section'
             )
             ORDER BY conname
            """
        ).fetchall()

    assert columns == {
        "base_context_digest": True,
        "context_document": True,
        "base_evidence_digest": False,
        "evidence_document": False,
    }
    assert len(constraints) == 1
    for constraint in constraints:
        assert "context" in constraint["definition"]
        assert "evidence" not in constraint["definition"]


def test_logical_entity_source_accepts_a_context_record(
    postgres_database: DisposablePostgres,
) -> None:
    with postgres_database.connect_owner() as connection:
        project_id, context_record_id = _seed_project_context(
            connection,
            tenant_code="LOGICAL_CONTEXT",
            project_name="Logical Context Project",
            group_name="Logical Design Notes",
            context_text="Orders have an independent lifecycle.",
        )
        logical_entity = connection.execute(
            """
            INSERT INTO workflow.logical_entity (
                project_id,
                logical_entity_schema_name,
                logical_entity_name,
                logical_entity_definition,
                logical_entity_type,
                logical_entity_grain
            )
            VALUES (%s, 'silver', 'Order', 'A customer order.', 'transaction', 'One order')
            RETURNING logical_entity_id
            """,
            (project_id,),
        ).fetchone()
        assert logical_entity is not None
        source = connection.execute(
            """
            INSERT INTO workflow.logical_entity_source_mapping (
                project_id,
                logical_entity_id,
                context_record_id,
                logical_entity_source_mapping_rationale
            )
            VALUES (%s, %s, %s,
                    'The Context Record establishes the entity boundary.')
            RETURNING source_object_id,
                      context_record_id
            """,
            (
                project_id,
                logical_entity["logical_entity_id"],
                context_record_id,
            ),
        ).fetchone()

    assert source == {
        "source_object_id": None,
        "context_record_id": context_record_id,
    }


def test_logical_attribute_source_accepts_a_context_record(
    postgres_database: DisposablePostgres,
) -> None:
    with postgres_database.connect_owner() as connection:
        project_id, context_record_id = _seed_project_context(
            connection,
            tenant_code="LOGICAL_ATTRIBUTE_CONTEXT",
            project_name="Logical Attribute Context Project",
            group_name="Logical Attribute Notes",
            context_text="Every order has a business order number.",
        )
        logical_entity = connection.execute(
            """
            INSERT INTO workflow.logical_entity (
                project_id,
                logical_entity_schema_name,
                logical_entity_name,
                logical_entity_definition,
                logical_entity_type,
                logical_entity_grain
            )
            VALUES (%s, 'silver', 'Order', 'A customer order.', 'transaction', 'One order')
            RETURNING logical_entity_id
            """,
            (project_id,),
        ).fetchone()
        assert logical_entity is not None
        logical_attribute = connection.execute(
            """
            INSERT INTO workflow.logical_attribute (
                project_id,
                logical_entity_id,
                logical_attribute_name,
                logical_attribute_definition,
                logical_attribute_data_type,
                logical_attribute_ordinal_position
            )
            VALUES (%s, %s, 'Order Number', 'Business order identifier.',
                    'varchar(50)', 1)
            RETURNING logical_attribute_id
            """,
            (project_id, logical_entity["logical_entity_id"]),
        ).fetchone()
        assert logical_attribute is not None
        source = connection.execute(
            """
            INSERT INTO workflow.logical_attribute_source_mapping (
                project_id,
                logical_entity_id,
                logical_attribute_id,
                context_record_id,
                logical_attribute_source_mapping_rationale
            )
            VALUES (%s, %s, %s, %s,
                    'The Context Record establishes the business Attribute.')
            RETURNING logical_entity_source_mapping_id,
                      source_object_id,
                      source_attribute_id,
                      context_record_id
            """,
            (
                project_id,
                logical_entity["logical_entity_id"],
                logical_attribute["logical_attribute_id"],
                context_record_id,
            ),
        ).fetchone()

    assert source == {
        "logical_entity_source_mapping_id": None,
        "source_object_id": None,
        "source_attribute_id": None,
        "context_record_id": context_record_id,
    }


def test_dimensional_entity_source_accepts_a_context_record(
    postgres_database: DisposablePostgres,
) -> None:
    with postgres_database.connect_owner() as connection:
        project_id, context_record_id = _seed_project_context(
            connection,
            tenant_code="DIMENSIONAL_CONTEXT",
            project_name="Dimensional Context Project",
            group_name="Dimensional Design Notes",
            context_text="Customers require a reusable analytical dimension.",
        )
        dimensional_entity = connection.execute(
            """
            INSERT INTO workflow.dimensional_entity (
                project_id,
                dimensional_entity_schema_name,
                dimensional_entity_name,
                dimensional_entity_definition,
                dimensional_entity_type
            )
            VALUES (%s, 'gold', 'Customer', 'Reusable customer dimension.', 'dimension')
            RETURNING dimensional_entity_id
            """,
            (project_id,),
        ).fetchone()
        assert dimensional_entity is not None
        source = connection.execute(
            """
            INSERT INTO workflow.dimensional_entity_source_mapping (
                project_id,
                dimensional_entity_id,
                context_record_id,
                dimensional_entity_source_mapping_rationale
            )
            VALUES (%s, %s, %s,
                    'The Context Record establishes the reusable Dimension.')
            RETURNING source_logical_entity_id,
                      context_record_id
            """,
            (
                project_id,
                dimensional_entity["dimensional_entity_id"],
                context_record_id,
            ),
        ).fetchone()

    assert source == {
        "source_logical_entity_id": None,
        "context_record_id": context_record_id,
    }


def test_dimensional_attribute_source_accepts_a_context_record(
    postgres_database: DisposablePostgres,
) -> None:
    with postgres_database.connect_owner() as connection:
        project_id, context_record_id = _seed_project_context(
            connection,
            tenant_code="DIMENSIONAL_ATTRIBUTE_CONTEXT",
            project_name="Dimensional Attribute Context Project",
            group_name="Dimensional Attribute Notes",
            context_text="Customer segment is required for reporting.",
        )
        dimensional_entity = connection.execute(
            """
            INSERT INTO workflow.dimensional_entity (
                project_id,
                dimensional_entity_schema_name,
                dimensional_entity_name,
                dimensional_entity_definition,
                dimensional_entity_type
            )
            VALUES (%s, 'gold', 'Customer', 'Reusable customer dimension.', 'dimension')
            RETURNING dimensional_entity_id
            """,
            (project_id,),
        ).fetchone()
        assert dimensional_entity is not None
        dimensional_attribute = connection.execute(
            """
            INSERT INTO workflow.dimensional_attribute (
                project_id,
                dimensional_entity_id,
                dimensional_attribute_name,
                dimensional_attribute_definition,
                dimensional_attribute_data_type,
                dimensional_attribute_ordinal_position
            )
            VALUES (%s, %s, 'Customer Segment', 'Reporting segment.',
                    'varchar(100)', 1)
            RETURNING dimensional_attribute_id
            """,
            (project_id, dimensional_entity["dimensional_entity_id"]),
        ).fetchone()
        assert dimensional_attribute is not None
        source = connection.execute(
            """
            INSERT INTO workflow.dimensional_attribute_source_mapping (
                project_id,
                dimensional_entity_id,
                dimensional_attribute_id,
                context_record_id,
                dimensional_attribute_source_mapping_rationale
            )
            VALUES (%s, %s, %s, %s,
                    'The Context Record establishes the analytical Attribute.')
            RETURNING dimensional_entity_source_mapping_id,
                      source_logical_entity_id,
                      source_logical_attribute_id,
                      context_record_id
            """,
            (
                project_id,
                dimensional_entity["dimensional_entity_id"],
                dimensional_attribute["dimensional_attribute_id"],
                context_record_id,
            ),
        ).fetchone()

    assert source == {
        "dimensional_entity_source_mapping_id": None,
        "source_logical_entity_id": None,
        "source_logical_attribute_id": None,
        "context_record_id": context_record_id,
    }


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
            INSERT INTO core.lane (lane_code, lane_name)
            VALUES ('LIST_SQL_GLOBAL', 'List SQL Global Project')
            RETURNING lane_id
            """
        ).fetchone()
        assert project is not None
        connection.execute(
            """
            INSERT INTO core.tenant (
                lane_id,
                tenant_code,
                tenant_name,
                tenant_catalog,
                gds_admin_catalog,
                tenant_visibility
            )
            VALUES (%s, 'LIST_SQL_GLOBAL', 'List SQL Global Tenant',
                    'list_sql_global', 'list_sql_global_admin', 'global')
            """,
            (project["lane_id"],),
        )

    database = postgres_database.create_runtime_adapter()
    await database.open()
    try:
        async with database.read_transaction() as transaction:
            rows = await query_visible_tenants(
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
            INSERT INTO core.lane (lane_code, lane_name)
            VALUES ('AUTH_GLOBAL', 'Authorization Global Project')
            RETURNING lane_id
            """
        ).fetchone()
        assert project is not None
        tenant = connection.execute(
            """
            INSERT INTO core.tenant (
                lane_id,
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
            (project["lane_id"],),
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
            INSERT INTO core.lane (lane_code, lane_name)
            VALUES ('AUTH_WRITE', 'Authorization Write Project')
            RETURNING lane_id
            """
        ).fetchone()
        assert project is not None
        tenant = connection.execute(
            """
            INSERT INTO core.tenant (
                lane_id,
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
            (project["lane_id"],),
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
            INSERT INTO core.lane (lane_code, lane_name)
            VALUES ('AUTH_WORKLOAD', 'Authorization Workload Project')
            RETURNING lane_id
            """
        ).fetchone()
        assert project is not None
        tenant = connection.execute(
            """
            INSERT INTO core.tenant (
                lane_id,
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
            (project["lane_id"],),
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
            INSERT INTO core.lane (lane_code, lane_name)
            VALUES ('AUTH_LOCK', 'Authorization Lock Project')
            RETURNING lane_id
            """
        ).fetchone()
        assert project is not None
        tenant = connection.execute(
            """
            INSERT INTO core.tenant (
                lane_id,
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
            (project["lane_id"],),
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


def test_developer_checks_an_unlocked_tenant(
    postgres_database: DisposablePostgres,
) -> None:
    entra_tenant_id = UUID("10000000-0000-0000-0000-000000000030")
    entra_object_id = UUID("20000000-0000-0000-0000-000000000030")
    with postgres_database.connect_owner() as connection:
        tenant_id = _seed_private_tenant(connection, "AUTH_CHECK_UNLOCKED")
        _seed_user_actor(
            connection,
            tenant_id=tenant_id,
            display_name="Checking Developer",
            email="checking.developer@example.test",
            entra_tenant_id=entra_tenant_id,
            entra_object_id=entra_object_id,
            tenant_role="developer",
        )

    with postgres_database.connect_runtime() as connection:
        result = connection.execute(
            """
            SELECT *
              FROM security.check_tenant_lock(
                  %s::UUID,
                  %s::UUID,
                  'user'::VARCHAR,
                  %s::BIGINT
              )
            """,
            (entra_tenant_id, entra_object_id, tenant_id),
        ).fetchone()

    assert result == {
        "authorized": True,
        "denial_code": None,
        "is_locked": False,
        "owner_display_name": None,
        "owned_by_current_principal": None,
        "purpose": None,
        "acquired_time": None,
        "expires_time": None,
    }


def test_developer_checks_a_lock_owned_by_another_principal(
    postgres_database: DisposablePostgres,
) -> None:
    owner_tenant_id = UUID("10000000-0000-0000-0000-000000000031")
    owner_object_id = UUID("20000000-0000-0000-0000-000000000031")
    checker_tenant_id = UUID("10000000-0000-0000-0000-000000000032")
    checker_object_id = UUID("20000000-0000-0000-0000-000000000032")
    with postgres_database.connect_owner() as connection:
        tenant_id = _seed_private_tenant(connection, "AUTH_CHECK_LOCKED")
        _seed_user_actor(
            connection,
            tenant_id=tenant_id,
            display_name="Lock Owner",
            email="check.owner@example.test",
            entra_tenant_id=owner_tenant_id,
            entra_object_id=owner_object_id,
            tenant_role="developer",
        )
        _seed_user_actor(
            connection,
            tenant_id=tenant_id,
            display_name="Lock Checker",
            email="lock.checker@example.test",
            entra_tenant_id=checker_tenant_id,
            entra_object_id=checker_object_id,
            tenant_role="developer",
        )

    with postgres_database.connect_runtime() as connection:
        acquired = connection.execute(
            """
            SELECT acquired
              FROM security.acquire_tenant_lock(
                  %s::UUID, %s::UUID, 'user'::VARCHAR, %s::BIGINT,
                  30::INTEGER, 'Metadata edit'::VARCHAR
              )
            """,
            (owner_tenant_id, owner_object_id, tenant_id),
        ).fetchone()
        assert acquired == {"acquired": True}
        result = connection.execute(
            """
            SELECT authorized,
                   denial_code,
                   is_locked,
                   owner_display_name,
                   owned_by_current_principal,
                   purpose,
                   acquired_time IS NOT NULL AS has_acquired_time,
                   expires_time > acquired_time AS has_future_expiry
              FROM security.check_tenant_lock(
                  %s::UUID,
                  %s::UUID,
                  'user'::VARCHAR,
                  %s::BIGINT
              )
            """,
            (checker_tenant_id, checker_object_id, tenant_id),
        ).fetchone()

    assert result == {
        "authorized": True,
        "denial_code": None,
        "is_locked": True,
        "owner_display_name": "Lock Owner",
        "owned_by_current_principal": False,
        "purpose": "Metadata edit",
        "has_acquired_time": True,
        "has_future_expiry": True,
    }


def test_acquire_fails_when_the_current_principal_already_owns_the_lock(
    postgres_database: DisposablePostgres,
) -> None:
    entra_tenant_id = UUID("10000000-0000-0000-0000-000000000033")
    entra_object_id = UUID("20000000-0000-0000-0000-000000000033")
    with postgres_database.connect_owner() as connection:
        tenant_id = _seed_private_tenant(connection, "AUTH_ACQUIRE_STRICT")
        _seed_user_actor(
            connection,
            tenant_id=tenant_id,
            display_name="Strict Lock Owner",
            email="strict.lock.owner@example.test",
            entra_tenant_id=entra_tenant_id,
            entra_object_id=entra_object_id,
            tenant_role="developer",
        )

    with postgres_database.connect_runtime() as connection:
        first = connection.execute(
            """
            SELECT acquired
              FROM security.acquire_tenant_lock(
                  %s::UUID, %s::UUID, 'user'::VARCHAR, %s::BIGINT,
                  60::INTEGER, 'First edit'::VARCHAR
              )
            """,
            (entra_tenant_id, entra_object_id, tenant_id),
        ).fetchone()
        second = connection.execute(
            """
            SELECT acquired, denial_code, owner_display_name, purpose
              FROM security.acquire_tenant_lock(
                  %s::UUID, %s::UUID, 'user'::VARCHAR, %s::BIGINT,
                  60::INTEGER, 'Second edit'::VARCHAR
              )
            """,
            (entra_tenant_id, entra_object_id, tenant_id),
        ).fetchone()

    assert first == {"acquired": True}
    assert second == {
        "acquired": False,
        "denial_code": "tenant_locked",
        "owner_display_name": "Strict Lock Owner",
        "purpose": "First edit",
    }


def test_explicit_override_releases_another_principals_lock_and_audits_the_reason(
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
            SELECT overridden,
                   denial_code,
                   previous_owner_display_name,
                   previous_purpose
              FROM security.override_tenant_lock(
                  %s::UUID,
                  %s::UUID,
                  'user'::VARCHAR,
                  %s::BIGINT,
                  'Coordinated handoff'::VARCHAR
              )
            """,
            (second_tenant_id, second_object_id, tenant_id),
        ).fetchone()
        checked = connection.execute(
            """
            SELECT is_locked
              FROM security.check_tenant_lock(
                  %s::UUID, %s::UUID, 'user'::VARCHAR, %s::BIGINT
              )
            """,
            (second_tenant_id, second_object_id, tenant_id),
        ).fetchone()

    assert overridden == {
        "overridden": True,
        "denial_code": None,
        "previous_owner_display_name": "First Developer",
        "previous_purpose": "First edit",
    }
    assert checked == {"is_locked": False}
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
    ]


def test_override_does_not_release_the_current_principals_lock(
    postgres_database: DisposablePostgres,
) -> None:
    entra_tenant_id = UUID("10000000-0000-0000-0000-000000000034")
    entra_object_id = UUID("20000000-0000-0000-0000-000000000034")
    with postgres_database.connect_owner() as connection:
        tenant_id = _seed_private_tenant(connection, "AUTH_OVERRIDE_OWN")
        _seed_user_actor(
            connection,
            tenant_id=tenant_id,
            display_name="Own Lock Developer",
            email="own.lock.developer@example.test",
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
                  60::INTEGER, 'Own edit'::VARCHAR
              )
            """,
            (entra_tenant_id, entra_object_id, tenant_id),
        ).fetchone()
        assert acquired == {"acquired": True}
        overridden = connection.execute(
            """
            SELECT overridden,
                   denial_code,
                   previous_owner_display_name,
                   previous_owned_by_current_principal
              FROM security.override_tenant_lock(
                  %s::UUID, %s::UUID, 'user'::VARCHAR, %s::BIGINT,
                  'Wrong operation'::VARCHAR
              )
            """,
            (entra_tenant_id, entra_object_id, tenant_id),
        ).fetchone()
        checked = connection.execute(
            """
            SELECT is_locked, owned_by_current_principal
              FROM security.check_tenant_lock(
                  %s::UUID, %s::UUID, 'user'::VARCHAR, %s::BIGINT
              )
            """,
            (entra_tenant_id, entra_object_id, tenant_id),
        ).fetchone()

    assert overridden == {
        "overridden": False,
        "denial_code": "tenant_locked",
        "previous_owner_display_name": "Own Lock Developer",
        "previous_owned_by_current_principal": True,
    }
    assert checked == {
        "is_locked": True,
        "owned_by_current_principal": True,
    }


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

    with postgres_database.connect_owner() as connection:
        expected = connection.execute(
            """
            SELECT least(count(*)::INTEGER, 100) AS expired_count
              FROM security.tenant_lock
             WHERE tenant_lock_expires_time <= CURRENT_TIMESTAMP
            """
        ).fetchone()

    with postgres_database.connect_runtime() as connection:
        result = connection.execute(
            "SELECT security.expire_tenant_locks(100) AS expired_count"
        ).fetchone()

    assert expected is not None
    assert expected["expired_count"] >= 1
    assert result == expected
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


def test_expiry_operation_rejects_a_null_batch_limit(
    postgres_database: DisposablePostgres,
) -> None:
    with (
        postgres_database.connect_runtime() as connection,
        pytest.raises(InvalidParameterValue, match="expiry batch limit"),
    ):
        connection.execute("SELECT security.expire_tenant_locks(NULL)")


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
        INSERT INTO core.lane (lane_code, lane_name)
        VALUES (%s, %s)
        RETURNING lane_id
        """,
        (code, f"{code} Project"),
    ).fetchone()
    assert project is not None
    tenant = connection.execute(
        """
        INSERT INTO core.tenant (
            lane_id,
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
            project["lane_id"],
            code,
            f"{code} Tenant",
            f"{code.lower()}_catalog",
            f"{code.lower()}_admin",
        ),
    ).fetchone()
    assert tenant is not None
    return cast(int, tenant["tenant_id"])


def test_context_uuid_and_group_ownership_cannot_cross_projects(
    postgres_database: DisposablePostgres,
) -> None:
    with postgres_database.connect_owner() as connection:
        first_project, first_record = _seed_project_context(
            connection,
            tenant_code="CONTEXT_OWNER_A",
            project_name="Context owner A",
            group_name="Rules",
            context_text="Owner A rule",
        )
        second_project, _ = _seed_project_context(
            connection,
            tenant_code="CONTEXT_OWNER_B",
            project_name="Context owner B",
            group_name="Rules",
            context_text="Owner B rule",
        )
        first_group = connection.execute(
            "SELECT context_group_id FROM project.context_group WHERE project_id=%s",
            (first_project,),
        ).fetchone()
        second_group = connection.execute(
            "SELECT context_group_id FROM project.context_group WHERE project_id=%s",
            (second_project,),
        ).fetchone()
        assert first_group is not None and second_group is not None
    with pytest.raises(ForeignKeyViolation):
        with postgres_database.connect_owner() as connection:
            connection.execute(
                "INSERT INTO project.context_record "
                "(context_record_id, project_id, context_group_id, context_text) VALUES (%s,%s,%s,'Wrong owner')",
                (uuid4(), second_project, first_group["context_group_id"]),
            )
    with pytest.raises(UniqueViolation):
        with postgres_database.connect_owner() as connection:
            connection.execute(
                "INSERT INTO project.context_record "
                "(context_record_id, project_id, context_group_id, context_text) VALUES (%s,%s,%s,'Reused identity')",
                (first_record, second_project, second_group["context_group_id"]),
            )


def _seed_project_context(
    connection: Connection[dict[str, object]],
    *,
    tenant_code: str,
    project_name: str,
    group_name: str,
    context_text: str,
) -> tuple[int, UUID]:
    tenant_id = _seed_private_tenant(connection, tenant_code)
    project = connection.execute(
        """
        INSERT INTO project.project (tenant_id, project_name, logical_schemas, dimensional_schemas)
        VALUES (%s, %s, '[{"schema_name":"silver","description":null}]'::JSONB,
                '[{"schema_name":"gold","description":null}]'::JSONB)
        RETURNING project_id
        """,
        (tenant_id, project_name),
    ).fetchone()
    assert project is not None
    project_id = cast(int, project["project_id"])
    group = connection.execute(
        """
        INSERT INTO project.context_group (
            project_id,
            name, context_type_id
        )
        VALUES (%s, %s, (SELECT context_type_id FROM reference.context_type WHERE name='Business Requirement'))
        RETURNING context_group_id
        """,
        (project_id, group_name),
    ).fetchone()
    assert group is not None
    record = connection.execute(
        """
        INSERT INTO project.context_record (
            project_id,
            context_group_id,
            context_record_id,
            context_text
        )
        VALUES (%s, %s, %s, %s)
        RETURNING context_record_id
        """,
        (
            project_id,
            group["context_group_id"],
            uuid4(),
            context_text,
        ),
    ).fetchone()
    assert record is not None
    return project_id, cast(UUID, record["context_record_id"])


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
