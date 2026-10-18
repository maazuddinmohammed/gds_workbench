from __future__ import annotations

from collections.abc import Mapping
from typing import Protocol
from uuid import uuid4

import pytest
from gds_etl_workbench.application.authorization import AuthorizationService
from gds_etl_workbench.domain.authorization import ActorKind, RequestPrincipal
from gds_workbench_api.database import WebPostgresDatabase
from gds_workbench_api.features.conceptual import (
    ConceptualContextSupport,
    ConceptualFilters,
    DatabaseConceptualService,
)
from psycopg import Connection


class DisposablePostgresFixture(Protocol):
    def connect_owner(self) -> Connection[dict[str, object]]: ...

    def web_runtime_dsn(self) -> str: ...


def _required_id(row: Mapping[str, object] | None, field: str) -> int:
    if row is None or not isinstance(row.get(field), int):
        raise AssertionError(f"expected database ID field {field}")
    value = row[field]
    if not isinstance(value, int) or isinstance(value, bool) or value <= 0:
        raise AssertionError(f"expected positive database ID field {field}")
    return value


@pytest.mark.asyncio
async def test_conceptual_review_reads_round_trip_through_the_web_role(
    web_postgres_database: DisposablePostgresFixture,
) -> None:
    entra_tenant_id = uuid4()
    entra_object_id = uuid4()
    suffix = uuid4().hex
    with web_postgres_database.connect_owner() as connection:
        lane_id = _required_id(
            connection.execute(
                """
                INSERT INTO core.lane (lane_code, lane_name)
                VALUES (%s, %s)
                RETURNING lane_id
                """,
                (f"conceptual_{suffix}", f"Conceptual Project {suffix}"),
            ).fetchone(),
            "lane_id",
        )
        tenant_id = _required_id(
            connection.execute(
                """
                INSERT INTO core.tenant (
                    lane_id,
                    tenant_code,
                    tenant_name,
                    tenant_catalog,
                    gds_admin_catalog
                ) VALUES (%s, %s, %s, %s, %s)
                RETURNING tenant_id
                """,
                (
                    lane_id,
                    f"CONCEPTUAL_{suffix}",
                    f"Conceptual Tenant {suffix}",
                    f"conceptual_catalog_{suffix}",
                    f"conceptual_admin_{suffix}",
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
                    f"Conceptual Reviewer {suffix}",
                    f"conceptual_{suffix}@example.test",
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
        project_id = _required_id(
            connection.execute(
                """
                INSERT INTO project.project (tenant_id, project_name)
                VALUES (%s, %s)
                RETURNING project_id
                """,
                (tenant_id, f"Conceptual Review {suffix}"),
            ).fetchone(),
            "project_id",
        )
        context_group_id = _required_id(
            connection.execute(
                """
                INSERT INTO project.context_group (
                    project_id,
                    name, context_type_id
                ) VALUES (%s, %s, (SELECT context_type_id FROM reference.context_type
                                     WHERE name = 'Business Requirement'))
                RETURNING context_group_id
                """,
                (project_id, f"Customer rules {suffix}"),
            ).fetchone(),
            "context_group_id",
        )
        context_record_id = str(uuid4())
        connection.execute(
            """
            INSERT INTO project.context_record (
                project_id, context_group_id, context_record_id, context_text
            ) VALUES (%s, %s, %s::UUID, %s)
            """,
            (
                project_id,
                context_group_id,
                context_record_id,
                "Each Order belongs to one Customer.",
            ),
        )

        customer_id = _required_id(
            connection.execute(
                """
                INSERT INTO workflow.conceptual_object (
                    project_id,
                    conceptual_object_name,
                    conceptual_object_definition,
                    conceptual_object_type,
                    conceptual_object_grain,
                    conceptual_object_aliases,
                    conceptual_object_status
                ) VALUES (%s, 'Customer', 'A governed party.',
                          'business_entity', 'One governed party',
                          ARRAY['Client'], 'active')
                RETURNING conceptual_object_id
                """,
                (project_id,),
            ).fetchone(),
            "conceptual_object_id",
        )
        order_id = _required_id(
            connection.execute(
                """
                INSERT INTO workflow.conceptual_object (
                    project_id,
                    conceptual_object_name,
                    conceptual_object_definition,
                    conceptual_object_type,
                    conceptual_object_grain
                ) VALUES (%s, 'Order', 'A purchase commitment.',
                          'business_event', 'One submitted Order')
                RETURNING conceptual_object_id
                """,
                (project_id,),
            ).fetchone(),
            "conceptual_object_id",
        )
        relationship_id = _required_id(
            connection.execute(
                """
                INSERT INTO workflow.conceptual_relationship (
                    project_id,
                    from_conceptual_object_id,
                    to_conceptual_object_id,
                    conceptual_relationship_name,
                    conceptual_relationship_type,
                    conceptual_relationship_definition,
                    conceptual_relationship_cardinality,
                    conceptual_relationship_basis,
                    conceptual_relationship_cardinality_basis,
                    conceptual_relationship_status
                ) VALUES (%s, %s, %s, 'Customer places Order',
                          'association', 'A Customer may place Orders.',
                          'one_to_many', 'Governed business rule.',
                          'One Customer key appears on many Orders.',
                          'active')
                RETURNING conceptual_relationship_id
                """,
                (project_id, customer_id, order_id),
            ).fetchone(),
            "conceptual_relationship_id",
        )
        connection.execute(
            """
            INSERT INTO workflow.conceptual_support (
                project_id,
                supported_artifact_type,
                conceptual_object_id,
                support_source_type,
                context_record_id,
                conceptual_support_role,
                conceptual_support_reason
            ) VALUES (%s, 'conceptual_object', %s, 'context_record', %s,
                      'business_rule', 'The Context record defines Customer grain.')
            """,
            (project_id, customer_id, context_record_id),
        )
        connection.execute(
            """
            INSERT INTO workflow.conceptual_support (
                project_id,
                supported_artifact_type,
                conceptual_relationship_id,
                support_source_type,
                context_record_id,
                conceptual_support_role,
                conceptual_support_reason
            ) VALUES (%s, 'conceptual_relationship', %s, 'context_record', %s,
                      'cardinality', 'The Context record defines the relationship.')
            """,
            (project_id, relationship_id, context_record_id),
        )

    database = WebPostgresDatabase(
        dsn=web_postgres_database.web_runtime_dsn(),
        pool_min=1,
        pool_max=1,
        pool_timeout_seconds=5,
    )
    service = DatabaseConceptualService(
        database=database,
        authorizer=AuthorizationService(),
        cursor_signing_key=b"development-only-key-32-bytes-long",
    )
    principal = RequestPrincipal(
        actor_kind=ActorKind.HUMAN,
        entra_tenant_id=entra_tenant_id,
        entra_object_id=entra_object_id,
    )

    await database.open()
    try:
        objects = await service.list_objects(
            principal,
            tenant_id=tenant_id,
            project_id=project_id,
            filters=ConceptualFilters(
                status="active",
                name_prefix="cust",
            ),
            page_size=50,
            cursor=None,
        )
        object_detail = await service.read_object(
            principal,
            tenant_id=tenant_id,
            project_id=project_id,
            conceptual_object_id=customer_id,
        )
        relationships = await service.list_relationships(
            principal,
            tenant_id=tenant_id,
            project_id=project_id,
            filters=ConceptualFilters(
                status="active",
                name_exact="customer places order",
            ),
            page_size=50,
            cursor=None,
        )
        relationship_detail = await service.read_relationship(
            principal,
            tenant_id=tenant_id,
            project_id=project_id,
            conceptual_relationship_id=relationship_id,
        )
    finally:
        await database.close()

    assert [item.conceptual_object_name for item in objects.items] == ["Customer"]
    assert object_detail.workflow_run_id is None
    assert isinstance(object_detail.supports[0], ConceptualContextSupport)
    assert [item.conceptual_relationship_name for item in relationships.items] == [
        "Customer places Order"
    ]
    assert relationship_detail.workflow_run_id is None
    assert isinstance(relationship_detail.supports[0], ConceptualContextSupport)
