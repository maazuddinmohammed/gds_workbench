"""Logical foreign-key lookups use modeled schemas without registered Objects."""

# Reuse the governed disposable Mapping fixture.
# pyright: reportPrivateUsage=false

from typing import Any, LiteralString, cast

from gds_etl_workbench.application.mapping_context import project_mapping_inputs
from gds_workbench_api.database import WebPostgresDatabase
from gds_workbench_api.features.mapping import assess_mapping_readiness
from gds_workbench_api.features.mapping.preparation_contracts import MappingModeledEntity
from gds_workbench_api.features.workflows.authoring.downstream_contracts import CONTRACTS
from jsonschema import Draft202012Validator
from psycopg.types.json import Jsonb

from tests.mcp.conftest import DisposablePostgres
from tests.web_backend.test_database_mapping_source_context import _load, _seed_mapping_scope
from tests.web_backend.test_database_model_change_sets import _required_id


async def test_logical_peer_lookup_metadata_is_authorized_and_invalidates_code(
    web_postgres_database: DisposablePostgres,
) -> None:
    scope = _seed_mapping_scope(web_postgres_database, dimensional=False)
    schemas = Jsonb([
        {"schema_name": "silver", "description": None},
        {"schema_name": "lookups", "description": "Shared business keys."},
    ])
    with web_postgres_database.connect_owner() as connection:
        connection.execute(
            "UPDATE model.model SET logical_schemas = %s WHERE model_id = %s",
            (schemas, scope.plan.model_id),
        )
        foreign_model_id = _required_id(
            connection.execute(
                "INSERT INTO model.model (tenant_id,model_name,logical_schemas) "
                "VALUES (%s,'Lookup isolation',%s) RETURNING model_id",
                (scope.tenant_id, schemas),
            ).fetchone(),
            "model_id",
        )
        ids: dict[str, int] = {}
        for name, model_id, status, source_system_id, has_document in (
            ("Customer", scope.plan.model_id, "active", scope.source_system_id, True),
            ("Inactive", scope.plan.model_id, "inactive", scope.source_system_id, True),
            ("Unmapped", scope.plan.model_id, "active", scope.source_system_id, False),
            ("OtherSystem", scope.plan.model_id, "active", scope.other_system_id, True),
            ("OtherModel", foreign_model_id, "active", scope.source_system_id, True),
        ):
            entity_id = _required_id(
                connection.execute(
                    """
                    INSERT INTO workflow.logical_entity (
                        model_id,logical_entity_schema_name,logical_entity_name,
                        logical_entity_definition,logical_entity_type,
                        logical_entity_grain,logical_entity_status
                    ) VALUES (%s,'lookups',%s,'Customer lookup.','core','One customer.',%s)
                    RETURNING logical_entity_id
                    """,
                    (model_id, name, status),
                ).fetchone(),
                "logical_entity_id",
            )
            ids[name] = entity_id
            connection.execute(
                """
                INSERT INTO workflow.logical_attribute (
                    model_id,logical_entity_id,logical_attribute_name,
                    logical_attribute_definition,logical_attribute_data_type,
                    logical_attribute_ordinal_position,logical_attribute_is_surrogate_key,
                    logical_attribute_is_nullable
                ) VALUES (%s,%s,'CustomerKey','Customer surrogate key.','bigint',1,TRUE,FALSE)
                """,
                (model_id, entity_id),
            )
            connection.execute(
                """
                INSERT INTO workflow.mapping_object (
                    model_id,modeled_entity_type,logical_entity_id,
                    source_system_id,mapping_transformation_document
                ) VALUES (%s,'logical_entity',%s,%s,%s)
                """,
                (model_id, entity_id, source_system_id, Jsonb({}) if has_document else None),
            )

    mapping_context = await _load(web_postgres_database, scope)
    assert {
        source.object.entity_id
        for source in mapping_context.sources
        if isinstance(source.object, MappingModeledEntity)
    } == {ids["Customer"]}
    assert assess_mapping_readiness(plan=scope.plan, context=mapping_context).ready

    runtime = WebPostgresDatabase(
        dsn=web_postgres_database.web_runtime_dsn(),
        pool_min=1, pool_max=1, pool_timeout_seconds=5,
    )
    await runtime.open()
    try:
        async with runtime.read_transaction() as transaction:
            sources = await transaction.fetch_all(
                "SELECT * FROM workflow.list_mapping_source_objects(%s,%s,'logical_entity',%s)",
                (scope.plan.model_id, scope.logical_entity_id, scope.source_system_id),
            )
        modeled_sources = [row for row in sources if row["source_logical_entity_id"] is not None]
        assert len(modeled_sources) == 1
        assert modeled_sources[0]["source_logical_entity_id"] == ids["Customer"]
        assert modeled_sources[0]["source_object_id"] is None
        assert modeled_sources[0]["role"] == "lookup"
        assert {row["source_object_id"] for row in sources if row["source_object_id"]} == {
            scope.source_object_id, scope.bronze_object_id,
        }

        async def current() -> dict[str, Any]:
            async with runtime.read_transaction() as transaction:
                row = await transaction.fetch_one(
                    "SELECT * FROM workflow.list_code_generation_target_context(%s,'logical_entity',NULL) "
                    "WHERE modeled_entity_id=%s",
                    (scope.plan.model_id, scope.logical_entity_id),
                )
            assert row is not None
            return row

        initial = await current()
        projected = project_mapping_inputs(initial["source_context"])
        for name, value in projected.items():
            validator = cast(Any, Draft202012Validator(CONTRACTS["code_generation"][name]["value_schema"]))
            assert validator.is_valid(value), f"Code prompt input schema mismatch: {name}"
        lookup = next(
            row["object"] for row in initial["source_context"]["physical_sources"]
            if row["role"] == "lookup"
        )
        assert "object_id" not in lookup
        assert lookup["modeled_entity_id"] == ids["Customer"]
        assert lookup["object_schema"] == lookup["logical_entity_schema_name"] == "lookups"
        assert lookup["object_name"] == lookup["logical_entity_name"] == "Customer"
        assert lookup["tenant_catalog"] == f"shared_{scope.plan.model_id}"
        assert lookup["source_tenant_id"] == scope.tenant_id
        assert lookup["attributes"][0]["attribute_name"] == "CustomerKey"
        assert lookup["attributes"][0]["is_surrogate_key"] is True
        assert await current() == initial

        changes: tuple[LiteralString, ...] = (
            "UPDATE workflow.logical_attribute SET logical_attribute_data_type='decimal(18,0)' WHERE logical_entity_id=%s",
            "UPDATE workflow.logical_entity SET logical_entity_schema_name='silver' WHERE logical_entity_id=%s",
            "UPDATE workflow.mapping_object SET object_mapping_status='inactive' WHERE logical_entity_id=%s",
        )
        prior = initial
        for statement in changes:
            with web_postgres_database.connect_owner() as connection:
                connection.execute(statement, (ids["Customer"],))
            changed = await current()
            assert changed["code_input_digest"] != prior["code_input_digest"]
            assert await current() == changed
            prior = changed
        assert all(row["role"] != "lookup" for row in prior["source_context"]["physical_sources"])
    finally:
        await runtime.close()


async def test_dimensional_peer_lookup_uses_gold_schema_and_tracks_changes(
    web_postgres_database: DisposablePostgres,
) -> None:
    scope = _seed_mapping_scope(web_postgres_database)
    target_id = scope.plan.pair.modeled_entity_id
    with web_postgres_database.connect_owner() as connection:
        connection.execute(
            "UPDATE workflow.dimensional_entity SET dimensional_entity_name='FactOrders', "
            "dimensional_entity_type='fact',dimensional_fact_type='transaction' WHERE dimensional_entity_id=%s",
            (target_id,),
        )
        lookup_id = _required_id(
            connection.execute(
                """
                INSERT INTO workflow.dimensional_entity (
                    model_id,dimensional_entity_schema_name,dimensional_entity_name,
                    dimensional_entity_definition,dimensional_entity_type
                ) VALUES (%s,'gold','Customer','Customer dimension.','dimension')
                RETURNING dimensional_entity_id
                """,
                (scope.plan.model_id,),
            ).fetchone(),
            "dimensional_entity_id",
        )
        connection.execute(
            """
            INSERT INTO workflow.dimensional_attribute (
                model_id,dimensional_entity_id,dimensional_attribute_name,
                dimensional_attribute_definition,dimensional_attribute_data_type,
                dimensional_attribute_ordinal_position,dimensional_attribute_role,
                dimensional_attribute_key_role,dimensional_attribute_is_nullable
            ) VALUES (%s,%s,'CustomerKey','Customer surrogate key.','bigint',1,'key','surrogate',FALSE)
            """,
            (scope.plan.model_id, lookup_id),
        )
        for entity_id in (target_id, lookup_id):
            mapping_id = _required_id(
                connection.execute(
                    """
                    INSERT INTO workflow.mapping_object (
                        model_id,modeled_entity_type,dimensional_entity_id,
                        source_system_id,mapping_transformation_document
                    ) VALUES (%s,'dimensional_entity',%s,%s,'{}'::JSONB)
                    RETURNING mapping_object_id
                    """,
                    (scope.plan.model_id, entity_id, scope.source_system_id),
                ).fetchone(),
                "mapping_object_id",
            )
            connection.execute(
                """
                INSERT INTO workflow.mapping_attribute (
                    mapping_object_id,model_id,modeled_entity_type,dimensional_entity_id,
                    dimensional_attribute_id,attribute_mapping_transformation_document
                ) SELECT %s,model_id,'dimensional_entity',dimensional_entity_id,
                         dimensional_attribute_id,'{}'::JSONB
                    FROM workflow.dimensional_attribute WHERE dimensional_entity_id=%s
                """,
                (mapping_id, entity_id),
            )

    mapping_context = await _load(web_postgres_database, scope)
    assert {
        (source.object.entity_type, source.object.entity_id)
        for source in mapping_context.sources
        if isinstance(source.object, MappingModeledEntity)
    } == {("logical_entity", scope.logical_entity_id), ("dimensional_entity", lookup_id)}
    assert assess_mapping_readiness(
        plan=scope.plan.model_copy(update={"operation": "extend"}), context=mapping_context
    ).ready

    runtime = WebPostgresDatabase(
        dsn=web_postgres_database.web_runtime_dsn(),
        pool_min=1, pool_max=1, pool_timeout_seconds=5,
    )
    await runtime.open()
    try:
        async def current() -> dict[str, Any]:
            async with runtime.read_transaction() as transaction:
                row = await transaction.fetch_one(
                    "SELECT * FROM workflow.list_code_generation_target_context(%s,'dimensional_entity',NULL) "
                    "WHERE modeled_entity_id=%s",
                    (scope.plan.model_id, target_id),
                )
            assert row is not None
            return row

        initial = await current()
        projected = project_mapping_inputs(initial["source_context"])
        for name, value in projected.items():
            validator = cast(Any, Draft202012Validator(CONTRACTS["code_generation"][name]["value_schema"]))
            assert validator.is_valid(value), f"Code prompt input schema mismatch: {name}"
        lookup = next(
            row["object"] for row in initial["source_context"]["physical_sources"]
            if row["role"] == "lookup"
        )
        assert "object_id" not in lookup
        assert lookup["modeled_entity_id"] == lookup_id
        assert lookup["object_schema"] == lookup["dimensional_entity_schema_name"] == "gold"
        assert lookup["object_name"] == lookup["dimensional_entity_name"] == "Customer"
        assert lookup["tenant_catalog"] == f"shared_{scope.plan.model_id}"
        assert lookup["zone_code"] == "gold"
        assert lookup["attributes"][0]["dimensional_attribute_name"] == "CustomerKey"
        assert lookup["attributes"][0]["is_surrogate_key"] is True
        assert await current() == initial
        with web_postgres_database.connect_owner() as connection:
            connection.execute(
                "UPDATE workflow.dimensional_attribute SET dimensional_attribute_data_type='decimal(18,0)' "
                "WHERE dimensional_entity_id=%s",
                (lookup_id,),
            )
        assert (await current())["code_input_digest"] != initial["code_input_digest"]
    finally:
        await runtime.close()
