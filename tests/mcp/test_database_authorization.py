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


def test_modeling_assertion_tables_replace_modeling_evidence_tables(
    postgres_database: DisposablePostgres,
) -> None:
    with postgres_database.connect_owner() as connection:
        row = connection.execute(
            """
            SELECT to_regclass('model.modeling_assertion_document')
                       AS assertion_document,
                   to_regclass('model.modeling_assertion_record')
                       AS assertion_record,
                   to_regclass('model.modeling_evidence_document')
                       AS evidence_document,
                   to_regclass('model.modeling_evidence_record')
                       AS evidence_record
            """
        ).fetchone()

    assert row == {
        "assertion_document": "model.modeling_assertion_document",
        "assertion_record": "model.modeling_assertion_record",
        "evidence_document": None,
        "evidence_record": None,
    }


def test_mcp_schema_owns_change_sets_and_tool_call_log(
    postgres_database: DisposablePostgres,
) -> None:
    with postgres_database.connect_owner() as connection:
        row = connection.execute(
            """
            SELECT to_regclass('mcp.model_change_set') AS model_change_set,
                   to_regclass('mcp.model_change_set_event')
                       AS model_change_set_event,
                   to_regclass('mcp.metadata_change_set')
                       AS metadata_change_set,
                   to_regclass('mcp.metadata_change_set_event')
                       AS metadata_change_set_event,
                   to_regclass('mcp.tool_call_log') AS tool_call_log,
                   to_regclass('workflow.model_change_set')
                       AS old_model_change_set,
                   to_regclass('workflow.metadata_change_set')
                       AS old_metadata_change_set,
                   to_regclass('security.mcp_tool_call_log')
                       AS old_tool_call_log
            """
        ).fetchone()

    assert row == {
        "model_change_set": "mcp.model_change_set",
        "model_change_set_event": "mcp.model_change_set_event",
        "metadata_change_set": "mcp.metadata_change_set",
        "metadata_change_set_event": "mcp.metadata_change_set_event",
        "tool_call_log": "mcp.tool_call_log",
        "old_model_change_set": None,
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


def test_model_change_set_uses_assertion_contract_names(
    postgres_database: DisposablePostgres,
) -> None:
    with postgres_database.connect_owner() as connection:
        columns = connection.execute(
            """
            SELECT EXISTS (
                       SELECT 1 FROM information_schema.columns
                        WHERE table_schema = 'mcp'
                          AND table_name = 'model_change_set'
                          AND column_name = 'base_assertion_digest'
                   ) AS base_assertion_digest,
                   EXISTS (
                       SELECT 1 FROM information_schema.columns
                        WHERE table_schema = 'mcp'
                          AND table_name = 'model_change_set'
                          AND column_name = 'assertion_document'
                   ) AS assertion_document,
                   EXISTS (
                       SELECT 1 FROM information_schema.columns
                        WHERE table_schema = 'mcp'
                          AND table_name = 'model_change_set'
                          AND column_name = 'base_evidence_digest'
                   ) AS base_evidence_digest,
                   EXISTS (
                       SELECT 1 FROM information_schema.columns
                        WHERE table_schema = 'mcp'
                          AND table_name = 'model_change_set'
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
        "base_assertion_digest": True,
        "assertion_document": True,
        "base_evidence_digest": False,
        "evidence_document": False,
    }
    assert len(constraints) == 1
    for constraint in constraints:
        assert "assertion" in constraint["definition"]
        assert "evidence" not in constraint["definition"]


def test_conceptual_support_accepts_an_assertion_record_source(
    postgres_database: DisposablePostgres,
) -> None:
    with postgres_database.connect_owner() as connection:
        model_id, assertion_record_id = _seed_model_assertion(
            connection,
            tenant_code="ASSERTION_SUPPORT",
            model_name="Assertion Support Model",
            document_name="Architecture Notes",
            assertion_text="Orders belong to customers.",
            applicable_layer="conceptual",
        )
        conceptual_object = connection.execute(
            """
            INSERT INTO workflow.conceptual_object (
                model_id,
                conceptual_object_name,
                conceptual_object_definition,
                conceptual_object_type,
                conceptual_object_grain
            )
            VALUES (%s, 'Order', 'A customer order.', 'business_object', 'One order')
            RETURNING conceptual_object_id
            """,
            (model_id,),
        ).fetchone()
        assert conceptual_object is not None
        support = connection.execute(
            """
            INSERT INTO workflow.conceptual_support (
                model_id,
                supported_artifact_type,
                conceptual_object_id,
                support_source_type,
                modeling_assertion_record_id,
                conceptual_support_reason
            )
            VALUES (%s, 'conceptual_object', %s, 'assertion', %s,
                    'The assertion establishes the business concept.')
            RETURNING support_source_type,
                      source_object_id,
                      modeling_assertion_record_id
            """,
            (
                model_id,
                conceptual_object["conceptual_object_id"],
                assertion_record_id,
            ),
        ).fetchone()

    assert support == {
        "support_source_type": "assertion",
        "source_object_id": None,
        "modeling_assertion_record_id": assertion_record_id,
    }


def test_logical_entity_source_accepts_an_assertion_record(
    postgres_database: DisposablePostgres,
) -> None:
    with postgres_database.connect_owner() as connection:
        model_id, assertion_record_id = _seed_model_assertion(
            connection,
            tenant_code="LOGICAL_ASSERTION",
            model_name="Logical Assertion Model",
            document_name="Logical Design Notes",
            assertion_text="Orders have an independent lifecycle.",
            applicable_layer="logical",
        )
        logical_entity = connection.execute(
            """
            INSERT INTO workflow.logical_entity (
                model_id,
                logical_entity_name,
                logical_entity_definition,
                logical_entity_type,
                logical_entity_grain
            )
            VALUES (%s, 'Order', 'A customer order.', 'transaction', 'One order')
            RETURNING logical_entity_id
            """,
            (model_id,),
        ).fetchone()
        assert logical_entity is not None
        source = connection.execute(
            """
            INSERT INTO workflow.logical_entity_source_mapping (
                model_id,
                logical_entity_id,
                support_source_type,
                modeling_assertion_record_id,
                logical_entity_source_mapping_rationale
            )
            VALUES (%s, %s, 'assertion', %s,
                    'The assertion establishes the entity boundary.')
            RETURNING support_source_type,
                      source_object_id,
                      modeling_assertion_record_id
            """,
            (
                model_id,
                logical_entity["logical_entity_id"],
                assertion_record_id,
            ),
        ).fetchone()

    assert source == {
        "support_source_type": "assertion",
        "source_object_id": None,
        "modeling_assertion_record_id": assertion_record_id,
    }


def test_logical_attribute_source_accepts_an_assertion_record(
    postgres_database: DisposablePostgres,
) -> None:
    with postgres_database.connect_owner() as connection:
        model_id, assertion_record_id = _seed_model_assertion(
            connection,
            tenant_code="LOGICAL_ATTRIBUTE_ASSERTION",
            model_name="Logical Attribute Assertion Model",
            document_name="Logical Attribute Notes",
            assertion_text="Every order has a business order number.",
            applicable_layer="logical",
        )
        logical_entity = connection.execute(
            """
            INSERT INTO workflow.logical_entity (
                model_id,
                logical_entity_name,
                logical_entity_definition,
                logical_entity_type,
                logical_entity_grain
            )
            VALUES (%s, 'Order', 'A customer order.', 'transaction', 'One order')
            RETURNING logical_entity_id
            """,
            (model_id,),
        ).fetchone()
        assert logical_entity is not None
        logical_attribute = connection.execute(
            """
            INSERT INTO workflow.logical_attribute (
                model_id,
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
            (model_id, logical_entity["logical_entity_id"]),
        ).fetchone()
        assert logical_attribute is not None
        source = connection.execute(
            """
            INSERT INTO workflow.logical_attribute_source_mapping (
                model_id,
                logical_entity_id,
                logical_attribute_id,
                support_source_type,
                modeling_assertion_record_id,
                logical_attribute_source_mapping_rationale
            )
            VALUES (%s, %s, %s, 'assertion', %s,
                    'The assertion establishes the business Attribute.')
            RETURNING support_source_type,
                      logical_entity_source_mapping_id,
                      source_object_id,
                      source_attribute_id,
                      modeling_assertion_record_id
            """,
            (
                model_id,
                logical_entity["logical_entity_id"],
                logical_attribute["logical_attribute_id"],
                assertion_record_id,
            ),
        ).fetchone()

    assert source == {
        "support_source_type": "assertion",
        "logical_entity_source_mapping_id": None,
        "source_object_id": None,
        "source_attribute_id": None,
        "modeling_assertion_record_id": assertion_record_id,
    }


def test_dimensional_entity_source_accepts_an_assertion_record(
    postgres_database: DisposablePostgres,
) -> None:
    with postgres_database.connect_owner() as connection:
        model_id, assertion_record_id = _seed_model_assertion(
            connection,
            tenant_code="DIMENSIONAL_ASSERTION",
            model_name="Dimensional Assertion Model",
            document_name="Dimensional Design Notes",
            assertion_text="Customers require a reusable analytical dimension.",
            applicable_layer="dimensional",
        )
        dimensional_entity = connection.execute(
            """
            INSERT INTO workflow.dimensional_entity (
                model_id,
                dimensional_entity_name,
                dimensional_entity_definition,
                dimensional_entity_type
            )
            VALUES (%s, 'Customer', 'Reusable customer dimension.', 'dimension')
            RETURNING dimensional_entity_id
            """,
            (model_id,),
        ).fetchone()
        assert dimensional_entity is not None
        source = connection.execute(
            """
            INSERT INTO workflow.dimensional_entity_source_mapping (
                model_id,
                dimensional_entity_id,
                support_source_type,
                modeling_assertion_record_id,
                dimensional_entity_source_role,
                dimensional_entity_source_mapping_rationale
            )
            VALUES (%s, %s, 'assertion', %s, 'business_basis',
                    'The assertion establishes the reusable Dimension.')
            RETURNING support_source_type,
                      source_object_id,
                      modeling_assertion_record_id
            """,
            (
                model_id,
                dimensional_entity["dimensional_entity_id"],
                assertion_record_id,
            ),
        ).fetchone()

    assert source == {
        "support_source_type": "assertion",
        "source_object_id": None,
        "modeling_assertion_record_id": assertion_record_id,
    }


def test_dimensional_attribute_source_accepts_an_assertion_record(
    postgres_database: DisposablePostgres,
) -> None:
    with postgres_database.connect_owner() as connection:
        model_id, assertion_record_id = _seed_model_assertion(
            connection,
            tenant_code="DIMENSIONAL_ATTRIBUTE_ASSERTION",
            model_name="Dimensional Attribute Assertion Model",
            document_name="Dimensional Attribute Notes",
            assertion_text="Customer segment is required for reporting.",
            applicable_layer="dimensional",
        )
        dimensional_entity = connection.execute(
            """
            INSERT INTO workflow.dimensional_entity (
                model_id,
                dimensional_entity_name,
                dimensional_entity_definition,
                dimensional_entity_type
            )
            VALUES (%s, 'Customer', 'Reusable customer dimension.', 'dimension')
            RETURNING dimensional_entity_id
            """,
            (model_id,),
        ).fetchone()
        assert dimensional_entity is not None
        dimensional_attribute = connection.execute(
            """
            INSERT INTO workflow.dimensional_attribute (
                model_id,
                dimensional_entity_id,
                dimensional_attribute_name,
                dimensional_attribute_definition,
                dimensional_attribute_data_type,
                dimensional_attribute_ordinal_position,
                dimensional_attribute_role
            )
            VALUES (%s, %s, 'Customer Segment', 'Reporting segment.',
                    'varchar(100)', 1, 'descriptor')
            RETURNING dimensional_attribute_id
            """,
            (model_id, dimensional_entity["dimensional_entity_id"]),
        ).fetchone()
        assert dimensional_attribute is not None
        source = connection.execute(
            """
            INSERT INTO workflow.dimensional_attribute_source_mapping (
                model_id,
                dimensional_entity_id,
                dimensional_attribute_id,
                support_source_type,
                modeling_assertion_record_id,
                dimensional_attribute_source_mapping_rationale
            )
            VALUES (%s, %s, %s, 'assertion', %s,
                    'The assertion establishes the analytical Attribute.')
            RETURNING support_source_type,
                      dimensional_entity_source_mapping_id,
                      source_object_id,
                      source_attribute_id,
                      modeling_assertion_record_id
            """,
            (
                model_id,
                dimensional_entity["dimensional_entity_id"],
                dimensional_attribute["dimensional_attribute_id"],
                assertion_record_id,
            ),
        ).fetchone()

    assert source == {
        "support_source_type": "assertion",
        "dimensional_entity_source_mapping_id": None,
        "source_object_id": None,
        "source_attribute_id": None,
        "modeling_assertion_record_id": assertion_record_id,
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


def _seed_model_assertion(
    connection: Connection[dict[str, object]],
    *,
    tenant_code: str,
    model_name: str,
    document_name: str,
    assertion_text: str,
    applicable_layer: str,
) -> tuple[int, int]:
    tenant_id = _seed_private_tenant(connection, tenant_code)
    model = connection.execute(
        """
        INSERT INTO model.model (tenant_id, model_name)
        VALUES (%s, %s)
        RETURNING model_id
        """,
        (tenant_id, model_name),
    ).fetchone()
    assert model is not None
    model_id = cast(int, model["model_id"])
    document = connection.execute(
        """
        INSERT INTO model.modeling_assertion_document (
            model_id,
            modeling_assertion_document_name
        )
        VALUES (%s, %s)
        RETURNING modeling_assertion_document_id
        """,
        (model_id, document_name),
    ).fetchone()
    assert document is not None
    assertion = connection.execute(
        """
        INSERT INTO model.modeling_assertion_record (
            model_id,
            modeling_assertion_document_id,
            modeling_assertion_record_type,
            modeling_assertion_text,
            modeling_assertion_applicable_layers
        )
        VALUES (%s, %s, 'business_rule', %s, %s)
        RETURNING modeling_assertion_record_id
        """,
        (
            model_id,
            document["modeling_assertion_document_id"],
            assertion_text,
            [applicable_layer],
        ),
    ).fetchone()
    assert assertion is not None
    return model_id, cast(int, assertion["modeling_assertion_record_id"])


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
