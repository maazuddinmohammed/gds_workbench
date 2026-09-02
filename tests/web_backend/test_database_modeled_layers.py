from __future__ import annotations

from collections.abc import Mapping
from typing import Protocol
from uuid import uuid4

import pytest
from gds_etl_workbench.application.authorization import AuthorizationService
from gds_etl_workbench.domain.authorization import ActorKind, RequestPrincipal
from psycopg import Connection

from gds_workbench_api.database import WebPostgresDatabase
from gds_workbench_api.features.dimensional import (
    DatabaseDimensionalService,
    DimensionalAssertionSource,
    DimensionalAttributeAssertionSource,
    DimensionalAttributeFilters,
    DimensionalRelationshipFilters,
)
from gds_workbench_api.features.logical import (
    DatabaseLogicalService,
    LogicalAssertionSource,
    LogicalAttributeAssertionSource,
    LogicalAttributeFilters,
    LogicalEntityFilters,
    LogicalRelationshipFilters,
    ModeledFilters,
)


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
async def test_logical_and_dimensional_reads_round_trip_through_web_role(
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
                (f"modeled_{suffix}", f"Modeled Project {suffix}"),
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
                    f"MODELED_{suffix}",
                    f"Modeled Tenant {suffix}",
                    f"modeled_catalog_{suffix}",
                    f"modeled_admin_{suffix}",
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
                    f"Modeled Reviewer {suffix}",
                    f"modeled_{suffix}@example.test",
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
                (tenant_id, f"Modeled Review {suffix}"),
            ).fetchone(),
            "model_id",
        )
        document_id = _required_id(
            connection.execute(
                """
                INSERT INTO model.modeling_assertion_document (
                    model_id,
                    modeling_assertion_document_name
                ) VALUES (%s, %s)
                RETURNING modeling_assertion_document_id
                """,
                (model_id, f"Modeled rules {suffix}"),
            ).fetchone(),
            "modeling_assertion_document_id",
        )
        assertion_id = _required_id(
            connection.execute(
                """
                INSERT INTO model.modeling_assertion_record (
                    model_id,
                    modeling_assertion_document_id,
                    modeling_assertion_record_key,
                    modeling_assertion_record_type,
                    modeling_assertion_text,
                    modeling_assertion_applicable_layers,
                    modeling_assertion_confidence
                ) VALUES (%s, %s, %s, 'grain_rule', %s,
                          ARRAY['logical', 'dimensional'], 'high')
                RETURNING modeling_assertion_record_id
                """,
                (
                    model_id,
                    document_id,
                    f"modeled.grain-{suffix}",
                    "One record represents one governed business occurrence.",
                ),
            ).fetchone(),
            "modeling_assertion_record_id",
        )

        logical_submodel_id = _required_id(
            connection.execute(
                """
                INSERT INTO workflow.logical_submodel (
                    model_id,
                    logical_submodel_name,
                    logical_submodel_definition
                ) VALUES (%s, 'Customer Domain', 'Governed Customer entities.')
                RETURNING logical_submodel_id
                """,
                (model_id,),
            ).fetchone(),
            "logical_submodel_id",
        )
        customer_id = _required_id(
            connection.execute(
                """
                INSERT INTO workflow.logical_entity (
                    model_id,
                    logical_entity_name,
                    logical_entity_definition,
                    logical_entity_type,
                    logical_entity_grain,
                    logical_entity_confidence,
                    logical_entity_status
                ) VALUES (%s, 'Customer', 'A governed Customer.', 'core',
                          'One Customer', 'high', 'active')
                RETURNING logical_entity_id
                """,
                (model_id,),
            ).fetchone(),
            "logical_entity_id",
        )
        order_id = _required_id(
            connection.execute(
                """
                INSERT INTO workflow.logical_entity (
                    model_id,
                    logical_entity_name,
                    logical_entity_definition,
                    logical_entity_type,
                    logical_entity_grain
                ) VALUES (%s, 'Order', 'A submitted Order.', 'transaction',
                          'One Order')
                RETURNING logical_entity_id
                """,
                (model_id,),
            ).fetchone(),
            "logical_entity_id",
        )
        connection.execute(
            """
            INSERT INTO workflow.logical_entity_submodel (
                model_id,
                logical_entity_id,
                logical_submodel_id
            ) VALUES (%s, %s, %s)
            """,
            (model_id, customer_id, logical_submodel_id),
        )
        connection.execute(
            """
            INSERT INTO workflow.logical_entity_source_mapping (
                model_id,
                logical_entity_id,
                support_source_type,
                modeling_assertion_record_id,
                logical_entity_source_mapping_rationale
            ) VALUES (%s, %s, 'assertion', %s, 'Defines Customer grain.')
            """,
            (model_id, customer_id, assertion_id),
        )
        customer_attribute_id = _required_id(
            connection.execute(
                """
                INSERT INTO workflow.logical_attribute (
                    model_id,
                    logical_entity_id,
                    logical_attribute_name,
                    logical_attribute_definition,
                    logical_attribute_data_type,
                    logical_attribute_is_nullable,
                    logical_attribute_is_primary_key,
                    logical_attribute_is_surrogate_key,
                    logical_attribute_ordinal_position
                ) VALUES (%s, %s, 'Customer ID', 'Stable Customer ID.',
                          'BIGINT', FALSE, TRUE, TRUE, 1)
                RETURNING logical_attribute_id
                """,
                (model_id, customer_id),
            ).fetchone(),
            "logical_attribute_id",
        )
        order_customer_attribute_id = _required_id(
            connection.execute(
                """
                INSERT INTO workflow.logical_attribute (
                    model_id,
                    logical_entity_id,
                    logical_attribute_name,
                    logical_attribute_definition,
                    logical_attribute_data_type,
                    logical_attribute_is_nullable,
                    logical_attribute_ordinal_position
                ) VALUES (%s, %s, 'Customer ID', 'Referenced Customer ID.',
                          'BIGINT', FALSE, 1)
                RETURNING logical_attribute_id
                """,
                (model_id, order_id),
            ).fetchone(),
            "logical_attribute_id",
        )
        connection.execute(
            """
            INSERT INTO workflow.logical_attribute_source_mapping (
                model_id,
                logical_entity_id,
                logical_attribute_id,
                support_source_type,
                modeling_assertion_record_id,
                logical_attribute_source_mapping_rationale
            ) VALUES (%s, %s, %s, 'assertion', %s,
                      'Defines the Customer identifier.')
            """,
            (model_id, customer_id, customer_attribute_id, assertion_id),
        )
        logical_relationship_id = _required_id(
            connection.execute(
                """
                INSERT INTO workflow.logical_relationship (
                    model_id,
                    logical_relationship_name,
                    logical_relationship_definition,
                    logical_relationship_from_entity_id,
                    logical_relationship_from_attribute_id,
                    logical_relationship_to_entity_id,
                    logical_relationship_to_attribute_id,
                    logical_relationship_cardinality,
                    logical_relationship_basis,
                    logical_relationship_cardinality_basis
                ) VALUES (%s, 'Order references Customer',
                          'Each Order references one Customer.', %s, %s, %s, %s,
                          'many_to_one', 'Governed identifier.',
                          'Many Orders may reference one Customer.')
                RETURNING logical_relationship_id
                """,
                (
                    model_id,
                    order_id,
                    order_customer_attribute_id,
                    customer_id,
                    customer_attribute_id,
                ),
            ).fetchone(),
            "logical_relationship_id",
        )

        dimensional_submodel_id = _required_id(
            connection.execute(
                """
                INSERT INTO workflow.dimensional_submodel (
                    model_id,
                    dimensional_submodel_name,
                    dimensional_submodel_definition
                ) VALUES (%s, 'Sales Mart', 'Governed Sales dimensional model.')
                RETURNING dimensional_submodel_id
                """,
                (model_id,),
            ).fetchone(),
            "dimensional_submodel_id",
        )
        fact_id = _required_id(
            connection.execute(
                """
                INSERT INTO workflow.dimensional_entity (
                    model_id,
                    dimensional_entity_name,
                    dimensional_entity_definition,
                    dimensional_entity_type,
                    dimensional_fact_type,
                    dimensional_entity_grain_definition,
                    dimensional_entity_confidence,
                    dimensional_entity_status
                ) VALUES (%s, 'Fact Order', 'Submitted Orders.', 'fact',
                          'transaction', 'One submitted Order', 'high',
                          'active')
                RETURNING dimensional_entity_id
                """,
                (model_id,),
            ).fetchone(),
            "dimensional_entity_id",
        )
        dimension_id = _required_id(
            connection.execute(
                """
                INSERT INTO workflow.dimensional_entity (
                    model_id,
                    dimensional_entity_name,
                    dimensional_entity_definition,
                    dimensional_entity_type
                ) VALUES (%s, 'Dim Customer', 'Customer descriptors.', 'dimension')
                RETURNING dimensional_entity_id
                """,
                (model_id,),
            ).fetchone(),
            "dimensional_entity_id",
        )
        connection.execute(
            """
            INSERT INTO workflow.dimensional_entity_submodel (
                model_id,
                dimensional_entity_id,
                dimensional_submodel_id
            ) VALUES (%s, %s, %s)
            """,
            (model_id, fact_id, dimensional_submodel_id),
        )
        connection.execute(
            """
            INSERT INTO workflow.dimensional_entity_source_mapping (
                model_id,
                dimensional_entity_id,
                support_source_type,
                modeling_assertion_record_id,
                dimensional_entity_source_role,
                dimensional_entity_source_mapping_rationale
            ) VALUES (%s, %s, 'assertion', %s, 'grain_rule',
                      'Defines Fact Order grain.')
            """,
            (model_id, fact_id, assertion_id),
        )
        fact_customer_key_id = _required_id(
            connection.execute(
                """
                INSERT INTO workflow.dimensional_attribute (
                    model_id,
                    dimensional_entity_id,
                    dimensional_attribute_name,
                    dimensional_attribute_definition,
                    dimensional_attribute_data_type,
                    dimensional_attribute_is_nullable,
                    dimensional_attribute_ordinal_position,
                    dimensional_attribute_role,
                    dimensional_attribute_key_role,
                    dimensional_attribute_is_grain_component
                ) VALUES (%s, %s, 'Customer Key', 'Customer foreign key.',
                          'BIGINT', FALSE, 1, 'key', 'foreign', TRUE)
                RETURNING dimensional_attribute_id
                """,
                (model_id, fact_id),
            ).fetchone(),
            "dimensional_attribute_id",
        )
        dimension_customer_key_id = _required_id(
            connection.execute(
                """
                INSERT INTO workflow.dimensional_attribute (
                    model_id,
                    dimensional_entity_id,
                    dimensional_attribute_name,
                    dimensional_attribute_definition,
                    dimensional_attribute_data_type,
                    dimensional_attribute_is_nullable,
                    dimensional_attribute_ordinal_position,
                    dimensional_attribute_role,
                    dimensional_attribute_key_role
                ) VALUES (%s, %s, 'Customer Key', 'Customer surrogate key.',
                          'BIGINT', FALSE, 1, 'key', 'surrogate')
                RETURNING dimensional_attribute_id
                """,
                (model_id, dimension_id),
            ).fetchone(),
            "dimensional_attribute_id",
        )
        connection.execute(
            """
            INSERT INTO workflow.dimensional_attribute_source_mapping (
                model_id,
                dimensional_entity_id,
                dimensional_attribute_id,
                support_source_type,
                modeling_assertion_record_id,
                dimensional_attribute_source_mapping_rationale
            ) VALUES (%s, %s, %s, 'assertion', %s,
                      'Defines the conformed Customer key.')
            """,
            (model_id, fact_id, fact_customer_key_id, assertion_id),
        )
        dimensional_relationship_id = _required_id(
            connection.execute(
                """
                INSERT INTO workflow.dimensional_relationship (
                    model_id,
                    dimensional_relationship_name,
                    dimensional_relationship_definition,
                    dimensional_relationship_from_entity_id,
                    dimensional_relationship_from_attribute_id,
                    dimensional_relationship_to_entity_id,
                    dimensional_relationship_to_attribute_id,
                    dimensional_relationship_kind,
                    dimensional_relationship_cardinality,
                    dimensional_relationship_is_optional,
                    dimensional_relationship_role_name,
                    dimensional_relationship_basis,
                    dimensional_relationship_cardinality_basis
                ) VALUES (%s, 'Order to Customer',
                          'Fact Order references Dim Customer.', %s, %s, %s, %s,
                          'fact_dimension', 'many_to_one', FALSE, 'ordering_customer',
                          'Conformed Customer key.', 'Many facts per Customer.')
                RETURNING dimensional_relationship_id
                """,
                (
                    model_id,
                    fact_id,
                    fact_customer_key_id,
                    dimension_id,
                    dimension_customer_key_id,
                ),
            ).fetchone(),
            "dimensional_relationship_id",
        )

    database = WebPostgresDatabase(
        dsn=web_postgres_database.web_runtime_dsn(),
        pool_min=1,
        pool_max=1,
        pool_timeout_seconds=5,
    )
    authorizer = AuthorizationService()
    key = b"development-only-key-32-bytes-long"
    logical = DatabaseLogicalService(
        database=database,
        authorizer=authorizer,
        cursor_signing_key=key,
    )
    dimensional = DatabaseDimensionalService(
        database=database,
        authorizer=authorizer,
        cursor_signing_key=key,
    )
    principal = RequestPrincipal(
        actor_kind=ActorKind.HUMAN,
        entra_tenant_id=entra_tenant_id,
        entra_object_id=entra_object_id,
    )

    await database.open()
    try:
        logical_entities = await logical.list_entities(
            principal,
            tenant_id=tenant_id,
            model_id=model_id,
            filters=LogicalEntityFilters(
                status="active",
                name_exact="customer",
                logical_submodel_id=logical_submodel_id,
            ),
            page_size=10,
            cursor=None,
        )
        logical_entity = await logical.read_entity(
            principal,
            tenant_id=tenant_id,
            model_id=model_id,
            logical_entity_id=customer_id,
        )
        logical_attributes = await logical.list_attributes(
            principal,
            tenant_id=tenant_id,
            model_id=model_id,
            filters=LogicalAttributeFilters(logical_entity_id=customer_id),
            page_size=10,
            cursor=None,
        )
        logical_attribute = await logical.read_attribute(
            principal,
            tenant_id=tenant_id,
            model_id=model_id,
            logical_attribute_id=customer_attribute_id,
        )
        logical_relationships = await logical.list_relationships(
            principal,
            tenant_id=tenant_id,
            model_id=model_id,
            filters=LogicalRelationshipFilters(logical_entity_id=customer_id),
            page_size=10,
            cursor=None,
        )
        logical_relationship = await logical.read_relationship(
            principal,
            tenant_id=tenant_id,
            model_id=model_id,
            logical_relationship_id=logical_relationship_id,
        )
        logical_submodels = await logical.list_submodels(
            principal,
            tenant_id=tenant_id,
            model_id=model_id,
            filters=ModeledFilters(name_exact="customer domain"),
            page_size=10,
            cursor=None,
        )
        logical_submodel = await logical.read_submodel(
            principal,
            tenant_id=tenant_id,
            model_id=model_id,
            logical_submodel_id=logical_submodel_id,
        )

        dimensional_objects = await dimensional.list_objects(
            principal,
            tenant_id=tenant_id,
            model_id=model_id,
            filters=ModeledFilters(status="active", name_exact="fact order"),
            page_size=10,
            cursor=None,
        )
        dimensional_object = await dimensional.read_object(
            principal,
            tenant_id=tenant_id,
            model_id=model_id,
            dimensional_entity_id=fact_id,
        )
        dimensional_attributes = await dimensional.list_attributes(
            principal,
            tenant_id=tenant_id,
            model_id=model_id,
            filters=DimensionalAttributeFilters(dimensional_entity_id=fact_id),
            page_size=10,
            cursor=None,
        )
        dimensional_attribute = await dimensional.read_attribute(
            principal,
            tenant_id=tenant_id,
            model_id=model_id,
            dimensional_attribute_id=fact_customer_key_id,
        )
        dimensional_relationships = await dimensional.list_relationships(
            principal,
            tenant_id=tenant_id,
            model_id=model_id,
            filters=DimensionalRelationshipFilters(dimensional_entity_id=fact_id),
            page_size=10,
            cursor=None,
        )
        dimensional_relationship = await dimensional.read_relationship(
            principal,
            tenant_id=tenant_id,
            model_id=model_id,
            dimensional_relationship_id=dimensional_relationship_id,
        )
    finally:
        await database.close()

    assert [item.logical_entity_id for item in logical_entities.items] == [customer_id]
    assert logical_entity.workflow_run_id is None
    assert logical_entity.submodels[0].logical_submodel_id == logical_submodel_id
    assert isinstance(logical_entity.sources[0], LogicalAssertionSource)
    assert logical_entity.sources[0].assertion_record.modeling_assertion_record_id == (
        assertion_id
    )
    assert logical_attributes.items[0].logical_attribute_id == customer_attribute_id
    assert isinstance(logical_attribute.sources[0], LogicalAttributeAssertionSource)
    assert logical_relationships.items[0].logical_relationship_id == (
        logical_relationship_id
    )
    assert logical_relationship.to_logical_entity_id == customer_id
    assert logical_submodels.items[0].entity_count == 1
    assert logical_submodel.entities[0].logical_entity_id == customer_id

    assert [item.dimensional_entity_id for item in dimensional_objects.items] == [
        fact_id
    ]
    assert dimensional_object.submodels[0].dimensional_submodel_id == (
        dimensional_submodel_id
    )
    assert isinstance(dimensional_object.sources[0], DimensionalAssertionSource)
    assert dimensional_attributes.items[0].dimensional_attribute_id == (
        fact_customer_key_id
    )
    assert isinstance(
        dimensional_attribute.sources[0],
        DimensionalAttributeAssertionSource,
    )
    assert dimensional_relationships.items[0].dimensional_relationship_id == (
        dimensional_relationship_id
    )
    assert dimensional_relationship.to_dimensional_entity_id == dimension_id
