"""Logical and Dimensional review reads through the web role on a disposable database."""

# Fixture imports reuse only disposable databases and synthetic identities.
# pyright: reportPrivateUsage=false
from __future__ import annotations

from collections.abc import Mapping
from typing import LiteralString
from uuid import uuid4

import pytest
from gds_etl_workbench.application.authorization import AuthorizationService
from gds_workbench_api.database import WebPostgresDatabase
from gds_workbench_api.features.dimensional import (
    DatabaseDimensionalService,
    DimensionalAttributeContextSource,
    DimensionalAttributeFilters,
    DimensionalContextSource,
    DimensionalLogicalEntitySource,
    DimensionalObjectFilters,
    DimensionalRelationshipFilters,
)
from gds_workbench_api.features.logical import (
    DatabaseLogicalService,
    EntitySubjectArea,
    LogicalAttributeContextSource,
    LogicalAttributeFilters,
    LogicalContextSource,
    LogicalEntityFilters,
    LogicalObjectSource,
    LogicalRelationshipFilters,
)

from tests.mcp.conftest import DisposablePostgres
from tests.mcp.test_database_project_change_set_round_trip import (
    StaticIdentityProvider,
    _seed_project_foundation,
)


def _required_id(row: Mapping[str, object] | None, field: str) -> int:
    if row is None:
        raise AssertionError(f"expected database ID field {field}")
    value = row[field]
    if not isinstance(value, int) or isinstance(value, bool) or value <= 0:
        raise AssertionError(f"expected positive database ID field {field}")
    return value


@pytest.mark.asyncio
async def test_logical_and_dimensional_reads_round_trip_through_web_role(
    web_postgres_database: DisposablePostgres,
) -> None:
    fixture = web_postgres_database
    project_id, tenant_id = _seed_project_foundation(
        fixture, code_prefix=f"MODELED_{uuid4().hex[:12]}"
    )
    with fixture.connect_owner() as connection:

        def insert(query: LiteralString, parameters: tuple[object, ...], field: str) -> int:
            return _required_id(connection.execute(query, parameters).fetchone(), field)

        objects = {
            row["object_name"]: row["object_id"]
            for row in connection.execute(
                "SELECT object_id, object_name FROM core.object "
                "WHERE source_tenant_id = %s AND object_schema = 'src'",
                (tenant_id,),
            ).fetchall()
        }
        for object_id in objects.values():
            connection.execute(
                "INSERT INTO project.project_input_scope (project_id, object_id) VALUES (%s, %s)",
                (project_id, object_id),
            )
        # Customers sit in the active Sales area and the inactive Archive area; Orders
        # sit only in an area whose membership was removed.
        sales_id = insert(
            "INSERT INTO workflow.subject_area (project_id, subject_area_name, "
            "subject_area_definition) VALUES (%s, 'Sales', 'Selling to customers.') "
            "RETURNING subject_area_id",
            (project_id,),
            "subject_area_id",
        )
        archive_id = insert(
            "INSERT INTO workflow.subject_area (project_id, subject_area_name, "
            "subject_area_definition, subject_area_is_active) "
            "VALUES (%s, 'Archive', 'Retired tables.', FALSE) RETURNING subject_area_id",
            (project_id,),
            "subject_area_id",
        )
        fulfilment_id = insert(
            "INSERT INTO workflow.subject_area (project_id, subject_area_name, "
            "subject_area_definition) VALUES (%s, 'Fulfilment', 'Shipping orders.') "
            "RETURNING subject_area_id",
            (project_id,),
            "subject_area_id",
        )
        for area_id, object_name, is_active in (
            (sales_id, "customers", True),
            (archive_id, "customers", True),
            (fulfilment_id, "orders", False),
        ):
            connection.execute(
                "INSERT INTO workflow.subject_area_table (project_id, subject_area_id, "
                "object_id, subject_area_table_is_active) VALUES (%s, %s, %s, %s)",
                (project_id, area_id, objects[object_name], is_active),
            )
        context_group_id = insert(
            "INSERT INTO project.context_group (project_id, name, context_type_id) "
            "VALUES (%s, 'Modeled rules', (SELECT context_type_id FROM reference.context_type "
            "WHERE name = 'Business Requirement')) RETURNING context_group_id",
            (project_id,),
            "context_group_id",
        )
        context_record_id = str(uuid4())
        connection.execute(
            "INSERT INTO project.context_record (project_id, context_group_id, "
            "context_record_id, context_text, status) VALUES (%s, %s, %s::UUID, %s, "
            "'deprecated')",
            (
                project_id,
                context_group_id,
                context_record_id,
                "One record represents one governed business occurrence.",
            ),
        )

        customer_id = insert(
            "INSERT INTO workflow.logical_entity (project_id, logical_entity_schema_name, "
            "logical_entity_name, logical_entity_definition, logical_entity_type, "
            "logical_entity_grain) VALUES (%s, 'silver', 'Customer', 'A governed Customer.', "
            "'core', 'One Customer') RETURNING logical_entity_id",
            (project_id,),
            "logical_entity_id",
        )
        order_id = insert(
            "INSERT INTO workflow.logical_entity (project_id, logical_entity_schema_name, "
            "logical_entity_name, logical_entity_definition, logical_entity_type, "
            "logical_entity_grain, logical_entity_is_active) VALUES (%s, 'silver', 'Order', "
            "'A submitted Order.', 'transaction', 'One Order', FALSE) "
            "RETURNING logical_entity_id",
            (project_id,),
            "logical_entity_id",
        )
        customer_source_id = insert(
            "INSERT INTO workflow.logical_entity_source_mapping (project_id, "
            "logical_entity_id, source_object_id) VALUES (%s, %s, %s) "
            "RETURNING logical_entity_source_mapping_id",
            (project_id, customer_id, objects["customers"]),
            "logical_entity_source_mapping_id",
        )
        connection.execute(
            "INSERT INTO workflow.logical_entity_source_mapping (project_id, "
            "logical_entity_id, context_record_id, logical_entity_source_mapping_rationale, "
            "logical_entity_source_mapping_is_active) "
            "VALUES (%s, %s, %s, 'Defines Customer grain.', FALSE)",
            (project_id, customer_id, context_record_id),
        )
        connection.execute(
            "INSERT INTO workflow.logical_entity_source_mapping (project_id, "
            "logical_entity_id, source_object_id) VALUES (%s, %s, %s)",
            (project_id, order_id, objects["orders"]),
        )
        customer_attribute_id = insert(
            "INSERT INTO workflow.logical_attribute (project_id, logical_entity_id, "
            "logical_attribute_name, logical_attribute_definition, "
            "logical_attribute_data_type, logical_attribute_is_nullable, "
            "logical_attribute_is_surrogate_key, logical_attribute_ordinal_position) "
            "VALUES (%s, %s, 'Customer ID', 'Stable Customer ID.', 'BIGINT', FALSE, TRUE, 1) "
            "RETURNING logical_attribute_id",
            (project_id, customer_id),
            "logical_attribute_id",
        )
        order_customer_attribute_id = insert(
            "INSERT INTO workflow.logical_attribute (project_id, logical_entity_id, "
            "logical_attribute_name, logical_attribute_definition, "
            "logical_attribute_data_type, logical_attribute_is_nullable, "
            "logical_attribute_ordinal_position) VALUES (%s, %s, 'Customer ID', "
            "'Referenced Customer ID.', 'BIGINT', FALSE, 1) RETURNING logical_attribute_id",
            (project_id, order_id),
            "logical_attribute_id",
        )
        connection.execute(
            "INSERT INTO workflow.logical_attribute_source_mapping (project_id, "
            "logical_entity_id, logical_attribute_id, context_record_id, "
            "logical_attribute_source_mapping_is_active) VALUES (%s, %s, %s, %s, FALSE)",
            (project_id, customer_id, customer_attribute_id, context_record_id),
        )
        logical_relationship_id = insert(
            "INSERT INTO workflow.logical_relationship (project_id, "
            "logical_relationship_from_entity_id, logical_relationship_from_attribute_id, "
            "logical_relationship_to_entity_id, logical_relationship_to_attribute_id, "
            "logical_relationship_basis) VALUES (%s, %s, %s, %s, %s, 'Governed identifier.') "
            "RETURNING logical_relationship_id",
            (project_id, order_id, order_customer_attribute_id, customer_id, customer_attribute_id),
            "logical_relationship_id",
        )

        fact_id = insert(
            "INSERT INTO workflow.dimensional_entity (project_id, "
            "dimensional_entity_schema_name, dimensional_entity_name, "
            "dimensional_entity_definition, dimensional_entity_type, dimensional_fact_type, "
            "dimensional_entity_grain_definition) VALUES (%s, 'gold', 'Fact Order', "
            "'Submitted Orders.', 'fact', 'transaction', 'One submitted Order') "
            "RETURNING dimensional_entity_id",
            (project_id,),
            "dimensional_entity_id",
        )
        dimension_id = insert(
            "INSERT INTO workflow.dimensional_entity (project_id, "
            "dimensional_entity_schema_name, dimensional_entity_name, "
            "dimensional_entity_definition, dimensional_entity_type) VALUES (%s, 'gold', "
            "'Dim Customer', 'Customer descriptors.', 'dimension') "
            "RETURNING dimensional_entity_id",
            (project_id,),
            "dimensional_entity_id",
        )
        # The fact's Logical source is inactive, so it reaches no Subject Area.
        for entity_id, logical_id in ((dimension_id, customer_id), (fact_id, order_id)):
            connection.execute(
                "INSERT INTO workflow.dimensional_entity_source_mapping (project_id, "
                "dimensional_entity_id, source_logical_entity_id) VALUES (%s, %s, %s)",
                (project_id, entity_id, logical_id),
            )
        connection.execute(
            "INSERT INTO workflow.dimensional_entity_source_mapping (project_id, "
            "dimensional_entity_id, context_record_id, "
            "dimensional_entity_source_mapping_rationale, "
            "dimensional_entity_source_mapping_is_active) "
            "VALUES (%s, %s, %s, 'Defines Fact Order grain.', FALSE)",
            (project_id, fact_id, context_record_id),
        )
        fact_customer_key_id = insert(
            "INSERT INTO workflow.dimensional_attribute (project_id, dimensional_entity_id, "
            "dimensional_attribute_name, dimensional_attribute_definition, "
            "dimensional_attribute_data_type, dimensional_attribute_is_nullable, "
            "dimensional_attribute_ordinal_position) VALUES (%s, %s, 'Customer Key', "
            "'Customer foreign key.', 'BIGINT', FALSE, 1) RETURNING dimensional_attribute_id",
            (project_id, fact_id),
            "dimensional_attribute_id",
        )
        dimension_customer_key_id = insert(
            "INSERT INTO workflow.dimensional_attribute (project_id, dimensional_entity_id, "
            "dimensional_attribute_name, dimensional_attribute_definition, "
            "dimensional_attribute_data_type, dimensional_attribute_is_nullable, "
            "dimensional_attribute_ordinal_position, dimensional_attribute_is_surrogate_key) "
            "VALUES (%s, %s, 'Customer Key', 'Customer surrogate key.', 'BIGINT', FALSE, 1, "
            "TRUE) RETURNING dimensional_attribute_id",
            (project_id, dimension_id),
            "dimensional_attribute_id",
        )
        connection.execute(
            "INSERT INTO workflow.dimensional_attribute_source_mapping (project_id, "
            "dimensional_entity_id, dimensional_attribute_id, context_record_id, "
            "dimensional_attribute_source_mapping_rationale, "
            "dimensional_attribute_source_mapping_is_active) "
            "VALUES (%s, %s, %s, %s, 'Defines the conformed Customer key.', FALSE)",
            (project_id, fact_id, fact_customer_key_id, context_record_id),
        )
        dimensional_relationship_id = insert(
            "INSERT INTO workflow.dimensional_relationship (project_id, "
            "dimensional_relationship_from_entity_id, "
            "dimensional_relationship_from_attribute_id, "
            "dimensional_relationship_to_entity_id, dimensional_relationship_to_attribute_id, "
            "dimensional_relationship_role_name) VALUES (%s, %s, %s, %s, %s, "
            "'ordering_customer') RETURNING dimensional_relationship_id",
            (
                project_id,
                fact_id,
                fact_customer_key_id,
                dimension_id,
                dimension_customer_key_id,
            ),
            "dimensional_relationship_id",
        )

    database = WebPostgresDatabase(
        dsn=fixture.web_runtime_dsn(),
        pool_min=1,
        pool_max=1,
        pool_timeout_seconds=5,
    )
    authorizer = AuthorizationService()
    key = b"development-only-key-32-bytes-long"
    logical = DatabaseLogicalService(database=database, authorizer=authorizer, cursor_signing_key=key)
    dimensional = DatabaseDimensionalService(
        database=database, authorizer=authorizer, cursor_signing_key=key
    )
    principal = StaticIdentityProvider().request_principal(None)
    scope = {"tenant_id": tenant_id, "project_id": project_id}

    await database.open()
    try:
        logical_entities = await logical.list_entities(
            principal,
            **scope,
            filters=LogicalEntityFilters(active=True, subject_area_id=sales_id),
            page_size=10,
            cursor=None,
        )
        inactive_entities = await logical.list_entities(
            principal,
            **scope,
            filters=LogicalEntityFilters(active=False),
            page_size=10,
            cursor=None,
        )
        removed_member_entities = await logical.list_entities(
            principal,
            **scope,
            filters=LogicalEntityFilters(subject_area_id=fulfilment_id),
            page_size=10,
            cursor=None,
        )
        logical_entity = await logical.read_entity(
            principal, **scope, logical_entity_id=customer_id
        )
        logical_attributes = await logical.list_attributes(
            principal,
            **scope,
            filters=LogicalAttributeFilters(logical_entity_id=customer_id, active=True),
            page_size=10,
            cursor=None,
        )
        logical_attribute = await logical.read_attribute(
            principal, **scope, logical_attribute_id=customer_attribute_id
        )
        logical_relationships = await logical.list_relationships(
            principal,
            **scope,
            filters=LogicalRelationshipFilters(
                logical_entity_id=customer_id, name_exact="customer id"
            ),
            page_size=10,
            cursor=None,
        )
        logical_relationship = await logical.read_relationship(
            principal, **scope, logical_relationship_id=logical_relationship_id
        )

        dimensional_objects = await dimensional.list_objects(
            principal,
            **scope,
            filters=DimensionalObjectFilters(active=True, subject_area_id=sales_id),
            page_size=10,
            cursor=None,
        )
        logical_areas = await logical.list_subject_areas(principal, **scope)
        dimensional_areas = await dimensional.list_subject_areas(principal, **scope)
        dimensional_fact = await dimensional.read_object(
            principal, **scope, dimensional_entity_id=fact_id
        )
        dimensional_dimension = await dimensional.read_object(
            principal, **scope, dimensional_entity_id=dimension_id
        )
        dimensional_attributes = await dimensional.list_attributes(
            principal,
            **scope,
            filters=DimensionalAttributeFilters(dimensional_entity_id=fact_id),
            page_size=10,
            cursor=None,
        )
        dimensional_attribute = await dimensional.read_attribute(
            principal, **scope, dimensional_attribute_id=fact_customer_key_id
        )
        dimensional_relationships = await dimensional.list_relationships(
            principal,
            **scope,
            filters=DimensionalRelationshipFilters(dimensional_entity_id=fact_id, active=True),
            page_size=10,
            cursor=None,
        )
        dimensional_relationship = await dimensional.read_relationship(
            principal, **scope, dimensional_relationship_id=dimensional_relationship_id
        )
    finally:
        await database.close()

    assert [item.logical_entity_id for item in logical_entities.items] == [customer_id]
    assert [item.logical_entity_id for item in inactive_entities.items] == [order_id]
    assert removed_member_entities.items == ()
    assert logical_entity.workflow_run_id is None
    assert logical_entity.logical_entity_type == "core"
    # Only active areas are derived; Archive is inactive.
    # The layer's Subject Areas tab: active areas only, active Objects, and the same
    # Entities the Subject Area filter finds.
    assert logical_entities.items and dimensional_objects.items
    assert [
        (area.subject_area_name, area.table_count, area.entity_count)
        for area in logical_areas.items
    ] == [("Fulfilment", 0, 0), ("Sales", 1, len(logical_entities.items))]
    assert [
        (area.subject_area_name, area.table_count, area.entity_count)
        for area in dimensional_areas.items
    ] == [("Fulfilment", 0, 0), ("Sales", 1, len(dimensional_objects.items))]
    assert logical_entity.subject_areas == (
        EntitySubjectArea(subject_area_id=sales_id, subject_area_name="Sales"),
    )
    object_source, context_source = logical_entity.sources
    assert isinstance(object_source, LogicalObjectSource)
    assert object_source.logical_entity_source_mapping_id == customer_source_id
    assert object_source.source_object.object_name == "customers"
    assert object_source.rationale is None and object_source.is_active
    assert isinstance(context_source, LogicalContextSource)
    assert context_source.is_active is False
    assert context_source.context_record.status == "deprecated"
    assert context_source.context_record.context_record_id == context_record_id
    assert [item.logical_attribute_id for item in logical_attributes.items] == [
        customer_attribute_id
    ]
    assert isinstance(logical_attribute.sources[0], LogicalAttributeContextSource)
    assert logical_attribute.sources[0].is_active is False
    assert logical_attribute.sources[0].rationale is None
    assert [item.logical_relationship_id for item in logical_relationships.items] == [
        logical_relationship_id
    ]
    assert logical_relationship.from_logical_entity_id == order_id
    assert logical_relationship.to_logical_entity_id == customer_id
    assert logical_relationship.logical_relationship_cardinality == "many_to_one"
    assert logical_relationship.logical_relationship_basis == "Governed identifier."

    # The fact reaches no area: its Logical source (Order) is inactive.
    assert [item.dimensional_entity_id for item in dimensional_objects.items] == [dimension_id]
    assert dimensional_fact.subject_areas == ()
    assert dimensional_dimension.subject_areas == (
        EntitySubjectArea(subject_area_id=sales_id, subject_area_name="Sales"),
    )
    assert dimensional_fact.dimensional_fact_type == "transaction"
    logical_source, dimensional_context_source = dimensional_fact.sources
    assert isinstance(logical_source, DimensionalLogicalEntitySource)
    assert logical_source.source_logical_entity.logical_entity_id == order_id
    assert isinstance(dimensional_context_source, DimensionalContextSource)
    assert dimensional_context_source.is_active is False
    assert dimensional_context_source.context_record.status == "deprecated"
    assert [item.dimensional_attribute_id for item in dimensional_attributes.items] == [
        fact_customer_key_id
    ]
    assert isinstance(dimensional_attribute.sources[0], DimensionalAttributeContextSource)
    assert dimensional_attribute.sources[0].is_active is False
    assert [item.dimensional_relationship_id for item in dimensional_relationships.items] == [
        dimensional_relationship_id
    ]
    assert dimensional_relationship.to_dimensional_entity_id == dimension_id
    assert dimensional_relationship.dimensional_relationship_role_name == "ordering_customer"
    assert dimensional_relationship.dimensional_relationship_basis is None
