"""Subject Area review reads through the restricted web role on a disposable database."""

# Fixture imports reuse only disposable databases and synthetic identities.
# pyright: reportPrivateUsage=false
from uuid import uuid4

import pytest
from gds_etl_workbench.application.authorization import AuthorizationService
from gds_etl_workbench.domain.authorization import ActorKind, RequestPrincipal
from gds_etl_workbench.domain.errors import AuthorizationDeniedError, TenantNotFoundError
from tests.mcp.conftest import DisposablePostgres
from tests.mcp.database_test_support import require_row
from tests.web_backend.test_database_project_change_sets import _seed_profile_project

from gds_workbench_api.database import WebPostgresDatabase
from gds_workbench_api.features.subject_areas import (
    DatabaseSubjectAreaService,
    SubjectAreaNotFoundError,
)


async def test_subject_area_reads_count_active_bronze_scope_and_memberships(
    web_postgres_database: DisposablePostgres,
) -> None:
    database = web_postgres_database
    project_id, tenant_id, _, entra_tenant_id, entra_object_id, _ = _seed_profile_project(database)
    with database.connect_owner() as connection:
        # The seeded Scope holds Bronze sales.orders with one column. Add two Bronze Scope
        # tables, one Source-zone Scope table and one Bronze table outside the Scope.
        placement = require_row(
            connection.execute(
                "SELECT object.object_id, object.connection_id, object.source_tenant_id, "
                "object.object_type_id, object.zone_id "
                "FROM project.project_input_scope AS scope "
                "JOIN core.object AS object USING (object_id) WHERE scope.project_id = %s",
                (project_id,),
            ).fetchone()
        )
        connection.execute(
            "INSERT INTO reference.zone (zone_code, zone_name) SELECT 'source', 'Source' "
            "WHERE NOT EXISTS (SELECT 1 FROM reference.zone "
            "WHERE lower(btrim(zone_code)) = 'source')"
        )
        objects = {"orders": placement["object_id"]}
        for name, columns in (("customers", 3), ("payments", 2), ("source_orders", 1)):
            objects[name] = require_row(
                connection.execute(
                    """
                    INSERT INTO core.object (
                        connection_id, source_tenant_id, object_schema, object_name,
                        object_type_id, zone_id
                    ) VALUES (
                        %s, %s, 'sales', %s, %s,
                        CASE WHEN %s THEN (SELECT zone_id FROM reference.zone
                                            WHERE lower(btrim(zone_code)) = 'source')
                             ELSE %s END
                    ) RETURNING object_id
                    """,
                    (
                        placement["connection_id"],
                        placement["source_tenant_id"],
                        name,
                        placement["object_type_id"],
                        name == "source_orders",
                        placement["zone_id"],
                    ),
                ).fetchone()
            )["object_id"]
            connection.execute(
                "INSERT INTO core.attribute (object_id, attribute_name, "
                "attribute_ordinal_position, attribute_data_type) "
                "SELECT %s, 'column_' || number, number, 'bigint' "
                "FROM generate_series(1, %s) AS number",
                (objects[name], columns),
            )
            connection.execute(
                "INSERT INTO project.project_input_scope (project_id, object_id) VALUES (%s, %s)",
                (project_id, objects[name]),
            )
        connection.execute(
            "INSERT INTO core.object (connection_id, source_tenant_id, object_schema, "
            "object_name, object_type_id, zone_id) VALUES (%s, %s, 'sales', 'archive', %s, %s)",
            (
                placement["connection_id"],
                placement["source_tenant_id"],
                placement["object_type_id"],
                placement["zone_id"],
            ),
        )
        areas = {
            row["subject_area_name"]: row["subject_area_id"]
            for row in connection.execute(
                """
                INSERT INTO workflow.subject_area (
                    project_id, subject_area_name, subject_area_definition, subject_area_is_active
                ) VALUES (%s, 'Sales', 'Orders and the customers who place them.', TRUE),
                         (%s, 'Customers', 'Customer identities.', TRUE),
                         (%s, 'Billing', 'A retired billing grouping.', FALSE)
                RETURNING subject_area_id, subject_area_name
                """,
                (project_id, project_id, project_id),
            ).fetchall()
        }
        memberships = {
            (area, table): require_row(
                connection.execute(
                    """
                    INSERT INTO workflow.subject_area_table (
                        project_id, subject_area_id, object_id,
                        subject_area_table_is_active, subject_area_table_is_locked
                    ) VALUES (%s, %s, %s, %s, %s)
                    RETURNING subject_area_table_id
                    """,
                    (project_id, areas[area], objects[table], is_active, locked),
                ).fetchone()
            )["subject_area_table_id"]
            for area, table, is_active, locked in (
                ("Sales", "orders", True, False),
                ("Sales", "customers", True, False),
                ("Sales", "payments", False, False),
                ("Sales", "source_orders", True, False),
                ("Customers", "customers", True, True),
                ("Billing", "payments", True, False),
            )
        }
        # Another Project of the same Tenant groups the same table in its own area.
        other_project_id = require_row(
            connection.execute(
                "INSERT INTO project.project (tenant_id, project_name) VALUES (%s, %s) "
                "RETURNING project_id",
                (tenant_id, f"Other Subject Areas {uuid4().hex}"),
            ).fetchone()
        )["project_id"]
        connection.execute(
            "INSERT INTO project.project_input_scope (project_id, object_id) VALUES (%s, %s)",
            (other_project_id, objects["orders"]),
        )
        other_area_id = require_row(
            connection.execute(
                "INSERT INTO workflow.subject_area (project_id, subject_area_name, "
                "subject_area_definition) VALUES (%s, 'Sales', 'Other sales.') "
                "RETURNING subject_area_id",
                (other_project_id,),
            ).fetchone()
        )["subject_area_id"]
        connection.execute(
            "INSERT INTO workflow.subject_area_table (project_id, subject_area_id, object_id) "
            "VALUES (%s, %s, %s)",
            (other_project_id, other_area_id, objects["orders"]),
        )
    _, _, _, outsider_tenant_id, outsider_object_id, _ = _seed_profile_project(database)

    runtime = WebPostgresDatabase(
        dsn=database.web_runtime_dsn(), pool_min=1, pool_max=1, pool_timeout_seconds=5
    )
    service = DatabaseSubjectAreaService(database=runtime, authorizer=AuthorizationService())
    principal = RequestPrincipal(
        actor_kind=ActorKind.HUMAN,
        entra_tenant_id=entra_tenant_id,
        entra_object_id=entra_object_id,
    )
    await runtime.open()
    try:
        page = await service.list_subject_areas(
            principal, tenant_id=tenant_id, project_id=project_id
        )
        tables = await service.list_scope_tables(
            principal, tenant_id=tenant_id, project_id=project_id
        )
        detail = await service.read_subject_area(
            principal,
            tenant_id=tenant_id,
            project_id=project_id,
            subject_area_id=areas["Sales"],
        )
        with pytest.raises(SubjectAreaNotFoundError):
            await service.read_subject_area(
                principal,
                tenant_id=tenant_id,
                project_id=project_id,
                subject_area_id=other_area_id,
            )
        for identity, error in (
            ((uuid4(), uuid4()), AuthorizationDeniedError),
            ((outsider_tenant_id, outsider_object_id), TenantNotFoundError),
        ):
            with pytest.raises(error):
                await service.list_subject_areas(
                    RequestPrincipal(
                        actor_kind=ActorKind.HUMAN,
                        entra_tenant_id=identity[0],
                        entra_object_id=identity[1],
                    ),
                    tenant_id=tenant_id,
                    project_id=project_id,
                )
    finally:
        await runtime.close()

    # Only active Bronze Scope tables count; payments has no active membership. A shared
    # table is in another active area of this Project, so the other Project's Sales area
    # does not make orders shared.
    assert (page.project_id, page.project_revision) == (project_id, 1)
    assert (page.scope_table_count, page.unassigned_table_count) == (3, 1)
    assert [
        (
            item.subject_area_name,
            item.subject_area_is_active,
            item.table_count,
            item.column_count,
            item.shared_table_count,
            item.workflow_run_id,
        )
        for item in page.items
    ] == [
        ("Billing", False, 0, 0, 0, None),
        ("Customers", True, 1, 3, 1, None),
        ("Sales", True, 2, 4, 1, None),
    ]
    assert [
        (
            item.object_name,
            item.zone_code,
            item.column_count,
            [
                (
                    area.subject_area_id,
                    area.subject_area_name,
                    area.subject_area_table_id,
                    area.subject_area_table_is_locked,
                )
                for area in item.areas
            ],
        )
        for item in tables.items
    ] == [
        (
            "customers",
            "bronze",
            3,
            [
                (areas["Customers"], "Customers", memberships[("Customers", "customers")], True),
                (areas["Sales"], "Sales", memberships[("Sales", "customers")], False),
            ],
        ),
        (
            "orders",
            "bronze",
            1,
            [(areas["Sales"], "Sales", memberships[("Sales", "orders")], False)],
        ),
        ("payments", "bronze", 2, []),
    ]
    assert {item.object_id for item in tables.items} == {
        objects["orders"],
        objects["customers"],
        objects["payments"],
    }
    assert (
        detail.subject_area_name,
        detail.table_count,
        detail.column_count,
        detail.shared_table_count,
    ) == ("Sales", 2, 4, 1)
    assert (detail.project_id, detail.project_revision) == (project_id, 1)
    assert [table.object_name for table in detail.tables] == ["customers", "orders"]
