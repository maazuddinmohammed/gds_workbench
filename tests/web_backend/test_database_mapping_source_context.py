"""Mapping resolves physical sources by route and ownership under the runtime role."""

# Existing disposable fixture builders deliberately share their private seed helpers.
# pyright: reportPrivateUsage=false

from dataclasses import dataclass, replace
from uuid import uuid4

import pytest
from gds_workbench_api.database import WebPostgresDatabase
from gds_workbench_api.features.mapping import (
    MappingRunContext,
    MappingRunPlan,
    assess_mapping_readiness,
)
from gds_workbench_api.features.mapping.preparation_contracts import (
    MappingModeledEntity,
    MappingPhysicalObject,
    MappingRunContextUnavailableError,
)
from gds_workbench_api.features.mapping.preparation_repository import (
    PostgresMappingRunContextRepository,
)
from psycopg import sql

from tests.mcp.conftest import DisposablePostgres
from tests.web_backend.mapping_fixtures import mapping_preparation
from tests.web_backend.test_database_model_change_sets import (
    _make_scope_object_dimensional_eligible,
    _required_id,
    _seed_profile_model,
)


@dataclass(frozen=True)
class MappingScope:
    tenant_id: int
    placement_tenant_id: int
    source_system_id: int
    other_system_id: int
    placement_connection_id: int
    bronze_object_id: int
    source_object_id: int
    logical_entity_id: int
    plan: MappingRunPlan


def _seed_mapping_scope(
    database: DisposablePostgres,
    *,
    dimensional: bool = True,
    create_run: bool = True,
    generate: bool = False,
) -> MappingScope:
    model_id, tenant_id, attribute_id, entra_tenant_id, entra_object_id, _ = (
        _seed_profile_model(database)
    )
    logical_entity_id = _make_scope_object_dimensional_eligible(
        database, model_id=model_id
    )
    with database.connect_owner() as connection:
        seed = connection.execute(
            """
            SELECT object.object_id, object.connection_id, object.object_type_id,
                   connection.system_id, connection.connection_type_id,
                   system.system_type_id, tenant.project_id
              FROM core.attribute AS attribute
              JOIN core.object AS object USING (object_id)
              JOIN core.connection AS connection USING (connection_id)
              JOIN core.system AS system USING (system_id)
              JOIN core.tenant AS tenant ON tenant.tenant_id = connection.tenant_id
             WHERE attribute.attribute_id = %s
            """,
            (attribute_id,),
        ).fetchone()
        assert seed is not None
        bronze_object_id = _required_id(seed, "object_id")
        source_system_id = _required_id(seed, "system_id")
        placement_tenant_id = _required_id(
            connection.execute(
                """
                INSERT INTO core.tenant (
                    project_id, tenant_code, tenant_name, tenant_catalog, gds_admin_catalog
                ) VALUES (%s, %s, 'Shared GDS fixture', %s, %s) RETURNING tenant_id
                """,
                (
                    seed["project_id"],
                    f"GDS_{model_id}",
                    f"shared_{model_id}",
                    f"admin_{model_id}",
                ),
            ).fetchone(),
            "tenant_id",
        )
        other_system_id = _required_id(
            connection.execute(
                """
                INSERT INTO core.system (system_code, system_name, system_type_id)
                VALUES (%s, 'Shared store fixture', %s) RETURNING system_id
                """,
                (f"GDS_{model_id}", seed["system_type_id"]),
            ).fetchone(),
            "system_id",
        )
        placement_connection_id = _required_id(
            connection.execute(
                """
                INSERT INTO core.connection (
                    tenant_id, system_id, connection_code, connection_name,
                    connection_type_id, is_global_data_store
                ) VALUES (%s, %s, %s, 'Shared store', %s, TRUE) RETURNING connection_id
                """,
                (
                    placement_tenant_id,
                    other_system_id,
                    f"STORE_{model_id}",
                    seed["connection_type_id"],
                ),
            ).fetchone(),
            "connection_id",
        )
        connection.execute(
            "UPDATE core.object SET connection_id = %s WHERE object_id = %s",
            (placement_connection_id, bronze_object_id),
        )
        connection.execute(
            "UPDATE core.tenant SET gds_connection_id=%s WHERE tenant_id=%s",
            (placement_connection_id, tenant_id),
        )
        for zone in ("source", "gold"):
            connection.execute(
                """
                INSERT INTO reference.zone (zone_code, zone_name)
                SELECT %s, %s WHERE NOT EXISTS (
                    SELECT 1 FROM reference.zone WHERE lower(btrim(zone_code)) = %s
                )
                """,
                (zone, zone.title(), zone),
            )
        source_object_id = _required_id(
            connection.execute(
                """
                INSERT INTO core.object (
                    connection_id, source_tenant_id, object_schema,
                    object_name, object_type_id, zone_id
                ) SELECT %s, %s, 'source', 'orders', %s, zone_id
                    FROM reference.zone WHERE lower(btrim(zone_code)) = 'source'
                RETURNING object_id
                """,
                (seed["connection_id"], tenant_id, seed["object_type_id"]),
            ).fetchone(),
            "object_id",
        )
        connection.execute(
            """
            INSERT INTO core.attribute (
                object_id, attribute_name, attribute_ordinal_position,
                attribute_data_type, attribute_nullability
            ) VALUES (%s, 'customer_id', 1, 'bigint', FALSE)
            """,
            (source_object_id,),
        )
        connection.execute(
            "INSERT INTO model.model_input_scope (model_id, object_id) VALUES (%s, %s)",
            (model_id, source_object_id),
        )
        connection.execute(
            """
            INSERT INTO core.ingestion_object_mapping (source_object_id, target_object_id)
            VALUES (%s, %s)
            """,
            (source_object_id, bronze_object_id),
        )
        connection.execute(
            """
            INSERT INTO workflow.logical_entity_source_mapping (
                model_id, logical_entity_id, support_source_type, source_object_id,
                logical_entity_source_mapping_order, logical_entity_source_mapping_rationale
            ) SELECT %s, entity.logical_entity_id, 'object', source.object_id,
                     source.mapping_order, 'Registered source fixture.'
                FROM workflow.logical_entity AS entity
                CROSS JOIN (VALUES (%s::BIGINT, 2), (%s::BIGINT, 1))
                    AS source(object_id, mapping_order)
               WHERE entity.model_id = %s AND entity.logical_entity_id = %s
            """,
            (model_id, source_object_id, bronze_object_id, model_id, logical_entity_id),
        )
        modeled_entity_id = logical_entity_id
        if dimensional:
            entity_id = _required_id(
                connection.execute(
                    """
                    INSERT INTO workflow.dimensional_entity (
                        model_id, dimensional_entity_schema_name, dimensional_entity_name,
                        dimensional_entity_definition,
                        dimensional_entity_type, dimensional_entity_grain_definition
                    ) VALUES (%s, 'gold', 'Customer', 'One customer.', 'dimension', 'One customer.')
                    RETURNING dimensional_entity_id
                    """,
                    (model_id,),
                ).fetchone(),
                "dimensional_entity_id",
            )
            _required_id(
                connection.execute(
                    """
                    INSERT INTO workflow.dimensional_attribute (
                        model_id, dimensional_entity_id, dimensional_attribute_name,
                        dimensional_attribute_definition, dimensional_attribute_data_type,
                        dimensional_attribute_ordinal_position, dimensional_attribute_role
                    ) VALUES (%s, %s, 'customer_id', 'Customer identifier.', 'bigint', 1, 'key')
                    RETURNING dimensional_attribute_id
                    """,
                    (model_id, entity_id),
                ).fetchone(),
                "dimensional_attribute_id",
            )
            connection.execute(
                """
                INSERT INTO workflow.dimensional_entity_source_mapping (
                    model_id, dimensional_entity_id, support_source_type, source_logical_entity_id,
                    dimensional_entity_source_role, dimensional_entity_source_mapping_order,
                    dimensional_entity_source_mapping_rationale
                ) VALUES (%s, %s, 'logical_entity', %s, 'support', 1, 'Applied Logical source.')
                """,
                (model_id, entity_id, logical_entity_id),
            )
            modeled_entity_id = entity_id
        actor = connection.execute(
            """
            SELECT principal_id, entra_principal_identity_id
              FROM security.entra_principal_identity
             WHERE entra_tenant_id = %s AND entra_object_id = %s
            """,
            (entra_tenant_id, entra_object_id),
        ).fetchone()
        assert actor is not None
        actor_id = _required_id(actor, "principal_id")
        correlation_id = uuid4()
        entity_type = "dimensional_entity" if dimensional else "logical_entity"
        route = "dimensional_to_gold" if dimensional else "logical_to_silver"
        operation = "generate" if generate else "build" if dimensional else "extend"
        run_id = 1  # Unused placeholder when a caller creates its own governed Run.
        if create_run:
            run_id = _required_id(
                connection.execute(
                    """
                    INSERT INTO application.workflow_run (
                        tenant_id, model_id, model_revision, model_workflow,
                        workflow_execution_mode, actor_principal_id,
                        actor_entra_principal_identity_id, agent_sdk_code, agent_provider_code,
                        agent_model_code, reasoning_effort_code, max_turns,
                        validation_retry_count, selected_scope_digest, selected_scope_count,
                        workflow_run_state, correlation_id, started_time,
                        modeled_entity_type, mapping_operation, mapping_coverage_mode, mapping_route
                    ) VALUES (%s, %s, 1, 'mapping', 'one_shot', %s, %s,
                        'openai_agents_sdk', 'databricks', 'test-model', 'medium', 8, 1,
                        %s, 1, 'running', %s, CURRENT_TIMESTAMP, %s, %s, 'selected_targets', %s)
                    RETURNING workflow_run_id
                    """,
                    (
                        tenant_id,
                        model_id,
                        actor_id,
                        actor["entra_principal_identity_id"],
                        "a" * 64,
                        correlation_id,
                        entity_type,
                        operation,
                        route,
                    ),
                ).fetchone(),
                "workflow_run_id",
            )
            connection.execute(
                """WITH selected AS (
                 INSERT INTO application.workflow_run_entity_selection (
                    workflow_run_id,model_id,modeled_entity_type,modeled_entity_id,
                    modeled_entity_schema_name,modeled_entity_name,selection_order)
                 SELECT %s,model_id,modeled_entity_type,modeled_entity_id,
                    modeled_entity_schema_name,modeled_entity_name,1
                 FROM workflow.modeled_entity WHERE model_id=%s AND modeled_entity_type=%s
                   AND modeled_entity_id=%s RETURNING workflow_run_entity_selection_id)
                 INSERT INTO application.workflow_run_mapping_target_selection (
                   workflow_run_id,model_id,workflow_run_entity_selection_id,source_system_id,selection_order)
                 SELECT %s,%s,workflow_run_entity_selection_id,%s,1 FROM selected""",
                (
                    run_id,
                    model_id,
                    entity_type,
                    modeled_entity_id,
                    run_id,
                    model_id,
                    source_system_id,
                ),
            )
    plan_data = mapping_preparation().plan.model_dump(mode="python")
    plan_data["agent_plan"].update(
        workflow_run_id=run_id,
        model_id=model_id,
        model_revision=1,
        correlation_id=correlation_id,
        modeled_entity_type=entity_type,
        selected_object_ids=(),
        selected_entity_ids=(modeled_entity_id,),
    )
    plan_data.update(
        actor_principal_id=actor_id,
        pair={
            "modeled_entity_id": modeled_entity_id,
            "source_system_id": source_system_id,
        },
        route=route,
        operation=operation,
    )
    return MappingScope(
        tenant_id,
        placement_tenant_id,
        source_system_id,
        other_system_id,
        placement_connection_id,
        bronze_object_id,
        source_object_id,
        logical_entity_id,
        MappingRunPlan.model_validate(plan_data),
    )


async def _load(database: DisposablePostgres, scope: MappingScope) -> MappingRunContext:
    runtime = WebPostgresDatabase(
        dsn=database.web_runtime_dsn(), pool_min=1, pool_max=1, pool_timeout_seconds=5
    )
    await runtime.open()
    try:
        async with runtime.read_transaction() as transaction:
            return await PostgresMappingRunContextRepository().load(
                transaction, tenant_id=scope.tenant_id, plan=scope.plan
            )
    finally:
        await runtime.close()


def _seed_assertion_mapping_target(
    database: DisposablePostgres,
    scope: MappingScope,
    *,
    dimensional: bool,
) -> tuple[int, int]:
    """An explicit generated reference Entity, using only disposable fixture state."""
    layer = "dimensional" if dimensional else "logical"
    with database.connect_owner() as connection:
        connection.execute(
            "UPDATE model.model SET default_mapping_source_system_id=%s WHERE model_id=%s",
            (scope.source_system_id, scope.plan.model_id),
        )
        document_id = _required_id(
            connection.execute(
                """INSERT INTO model.modeling_assertion_document
                (model_id, modeling_assertion_document_name)
                VALUES (%s, 'Generated reference values')
                RETURNING modeling_assertion_document_id""",
                (scope.plan.model_id,),
            ).fetchone(),
            "modeling_assertion_document_id",
        )
        assertion_id = _required_id(
            connection.execute(
                """INSERT INTO model.modeling_assertion_record
                (model_id, modeling_assertion_document_id, modeling_assertion_record_key,
                 modeling_assertion_record_type, modeling_assertion_text)
                VALUES (%s,%s,'generated_reference','business_rule',
                    'Produce one row with reference_id equal to 1.')
                RETURNING modeling_assertion_record_id""",
                (scope.plan.model_id, document_id),
            ).fetchone(),
            "modeling_assertion_record_id",
        )
        entity_id = _required_id(
            connection.execute(
                sql.SQL(
                    "INSERT INTO workflow.{} (model_id, {}, {}, {}, {}, {}) "
                    "VALUES (%s,%s,'GeneratedReference','Generated reference.',%s,'One row.') "
                    "RETURNING {} AS entity_id"
                ).format(
                    sql.Identifier(f"{layer}_entity"),
                    sql.Identifier(f"{layer}_entity_schema_name"),
                    sql.Identifier(f"{layer}_entity_name"),
                    sql.Identifier(f"{layer}_entity_definition"),
                    sql.Identifier(f"{layer}_entity_type"),
                    sql.Identifier(
                        f"{layer}_entity_grain_definition"
                        if dimensional
                        else "logical_entity_grain"
                    ),
                    sql.Identifier(f"{layer}_entity_id"),
                ),
                (
                    scope.plan.model_id,
                    "gold" if dimensional else "silver",
                    "dimension" if dimensional else "reference",
                ),
            ).fetchone(),
            "entity_id",
        )
        connection.execute(
            sql.SQL(
                "INSERT INTO workflow.{} (model_id, {}, {}, {}, {}, {}, {}, {}) "
                "VALUES (%s,%s,'reference_id','Generated key.','bigint',1,%s,FALSE)"
            ).format(
                sql.Identifier(f"{layer}_attribute"),
                sql.Identifier(f"{layer}_entity_id"),
                sql.Identifier(f"{layer}_attribute_name"),
                sql.Identifier(f"{layer}_attribute_definition"),
                sql.Identifier(f"{layer}_attribute_data_type"),
                sql.Identifier(f"{layer}_attribute_ordinal_position"),
                sql.Identifier(
                    "dimensional_attribute_role"
                    if dimensional
                    else "logical_attribute_is_surrogate_key"
                ),
                sql.Identifier(f"{layer}_attribute_is_nullable"),
            ),
            (scope.plan.model_id, entity_id, "key" if dimensional else True),
        )
        extra_columns = (
            sql.SQL(", dimensional_entity_source_role") if dimensional else sql.SQL("")
        )
        extra_values = sql.SQL(", 'support'") if dimensional else sql.SQL("")
        connection.execute(
            sql.SQL(
                "INSERT INTO workflow.{} (model_id, {}, support_source_type, "
                "modeling_assertion_record_id, {}{}) "
                "VALUES (%s,%s,'assertion',%s,'Explicit generated reference rule.'{})"
            ).format(
                sql.Identifier(f"{layer}_entity_source_mapping"),
                sql.Identifier(f"{layer}_entity_id"),
                sql.Identifier(f"{layer}_entity_source_mapping_rationale"),
                extra_columns,
                extra_values,
            ),
            (scope.plan.model_id, entity_id, assertion_id),
        )
    return entity_id, assertion_id


@pytest.mark.parametrize("dimensional", [False, True])
def test_assertion_fallback_has_one_pair_and_no_unrelated_candidate_sources(
    web_postgres_database: DisposablePostgres,
    dimensional: bool,
) -> None:
    from gds_workbench_api.features.mapping.read_service import (
        _MAPPING_GENERATION_TARGETS_SQL,
    )

    scope = _seed_mapping_scope(
        web_postgres_database, dimensional=False, create_run=False
    )
    entity_id, assertion_id = _seed_assertion_mapping_target(
        web_postgres_database,
        scope,
        dimensional=dimensional,
    )
    entity_type = "dimensional_entity" if dimensional else "logical_entity"
    with web_postgres_database.connect_owner() as connection:
        assert connection.execute(
            "SELECT workflow.is_assertion_only_mapping_target(%s,%s,%s) AS eligible",
            (scope.plan.model_id, entity_id, entity_type),
        ).fetchone() == {"eligible": True}
        pairs = connection.execute(
            _MAPPING_GENERATION_TARGETS_SQL,
            (
                scope.tenant_id,
                scope.plan.model_id,
                entity_type,
                scope.tenant_id,
                scope.plan.model_id,
                200,
                0,
            ),
        ).fetchall()
        selected = [row for row in pairs if row["entity_id"] == entity_id]
        assert len(selected) == 1
        assert selected[0]["source_system"]["system_id"] == scope.source_system_id
        assert selected[0]["has_sources"] is True
        assert (
            connection.execute(
                "SELECT * FROM workflow.list_mapping_source_objects(%s,%s,%s,%s)",
                (scope.plan.model_id, entity_id, entity_type, scope.source_system_id),
            ).fetchall()
            == []
        )
        assert connection.execute(
            "SELECT workflow.is_assertion_only_mapping_target(%s,%s,'logical_entity') AS eligible",
            (scope.plan.model_id, scope.logical_entity_id),
        ).fetchone() == {"eligible": False}
        connection.execute(
            "UPDATE model.modeling_assertion_document SET system_id=%s WHERE "
            "modeling_assertion_document_id=(SELECT modeling_assertion_document_id "
            "FROM model.modeling_assertion_record WHERE modeling_assertion_record_id=%s)",
            (scope.other_system_id, assertion_id),
        )
        assert connection.execute(
            "SELECT workflow.is_assertion_only_mapping_target(%s,%s,%s) AS eligible",
            (scope.plan.model_id, entity_id, entity_type),
        ).fetchone() == {"eligible": False}
        connection.execute(
            "UPDATE model.modeling_assertion_document SET system_id=NULL WHERE "
            "modeling_assertion_document_id=(SELECT modeling_assertion_document_id "
            "FROM model.modeling_assertion_record WHERE modeling_assertion_record_id=%s)",
            (assertion_id,),
        )
        connection.execute(
            "UPDATE model.modeling_assertion_record "
            "SET modeling_assertion_record_status='inactive' "
            "WHERE modeling_assertion_record_id=%s",
            (assertion_id,),
        )
        assert connection.execute(
            "SELECT workflow.is_assertion_only_mapping_target(%s,%s,%s) AS eligible",
            (scope.plan.model_id, entity_id, entity_type),
        ).fetchone() == {"eligible": False}
        connection.execute(
            "UPDATE model.modeling_assertion_record "
            "SET modeling_assertion_record_status='active' WHERE modeling_assertion_record_id=%s",
            (assertion_id,),
        )
        connection.execute(
            "UPDATE core.connection SET is_active=FALSE WHERE tenant_id=%s AND system_id=%s",
            (scope.tenant_id, scope.source_system_id),
        )
        pairs = connection.execute(
            _MAPPING_GENERATION_TARGETS_SQL,
            (
                scope.tenant_id,
                scope.plan.model_id,
                entity_type,
                scope.tenant_id,
                scope.plan.model_id,
                200,
                0,
            ),
        ).fetchall()
        assert not any(row["entity_id"] == entity_id for row in pairs)


async def test_dimensional_mapping_uses_logical_entities_without_registered_targets(
    web_postgres_database: DisposablePostgres,
) -> None:
    scope = _seed_mapping_scope(web_postgres_database)
    with web_postgres_database.connect_owner() as connection:
        connection.execute(
            "UPDATE model.model SET logical_entity_scd_type='type_1', "
            "dimensional_entity_scd_type='type_2' WHERE model_id=%s",
            (scope.plan.model_id,),
        )
    context = await _load(web_postgres_database, scope)
    assert context.authoring.logical_entity_scd_type == "type_1"
    assert context.authoring.dimensional_entity_scd_type == "type_2"
    assert context.target.entity_schema_name == "gold"
    assert context.target.entity_id == scope.plan.pair.modeled_entity_id
    assert [
        item.object.entity_id
        for item in context.sources
        if isinstance(item.object, MappingModeledEntity)
    ] == [scope.logical_entity_id]
    assert {
        item.object.object_id
        for item in context.upstream_physical_sources
        if isinstance(item.object, MappingPhysicalObject)
    } == {scope.source_object_id, scope.bronze_object_id}
    # The shared lake's physical System differs from its originating business System.
    bronze = next(
        item.object
        for item in context.upstream_physical_sources
        if isinstance(item.object, MappingPhysicalObject)
        and item.object.object_id == scope.bronze_object_id
    )
    assert isinstance(bronze, MappingPhysicalObject)
    assert bronze.system_id == scope.other_system_id
    assert context.source_system.system_id == scope.source_system_id
    assert assess_mapping_readiness(plan=scope.plan, context=context).ready


async def test_logical_mapping_keeps_ordered_source_and_ingested_bronze_inputs(
    web_postgres_database: DisposablePostgres,
) -> None:
    scope = _seed_mapping_scope(web_postgres_database, dimensional=False)
    context = await _load(web_postgres_database, scope)
    assert {
        item.object.object_id
        for item in context.sources
        if isinstance(item.object, MappingPhysicalObject)
    } == {scope.source_object_id, scope.bronze_object_id}
    assert context.target.entity_id == scope.logical_entity_id
    assert context.upstream_physical_sources == ()
    assert assess_mapping_readiness(plan=scope.plan, context=context).ready


async def test_mapping_target_requires_owning_model_tenant(
    web_postgres_database: DisposablePostgres,
) -> None:
    scope = _seed_mapping_scope(web_postgres_database)
    with pytest.raises(MappingRunContextUnavailableError):
        await _load(
            web_postgres_database, replace(scope, tenant_id=scope.placement_tenant_id)
        )


@pytest.mark.parametrize("dimensional", [False, True])
async def test_mapping_pairs_do_not_require_registered_targets_or_dependency_rows(
    web_postgres_database: DisposablePostgres,
    dimensional: bool,
) -> None:
    from gds_workbench_api.features.mapping.read_service import (
        _MAPPING_GENERATION_TARGETS_SQL,
    )

    scope = _seed_mapping_scope(web_postgres_database, dimensional=dimensional)
    with web_postgres_database.connect_owner() as connection:
        pairs = connection.execute(
            _MAPPING_GENERATION_TARGETS_SQL,
            (
                scope.tenant_id,
                scope.plan.model_id,
                scope.plan.modeled_entity_type,
                scope.tenant_id,
                scope.plan.model_id,
                200,
                0,
            ),
        ).fetchall()
        assert {
            (row["entity_id"], row["source_system"]["system_id"]) for row in pairs
        } == {(scope.plan.pair.modeled_entity_id, scope.source_system_id)}
    context = await _load(web_postgres_database, scope)
    assert assess_mapping_readiness(plan=scope.plan, context=context).ready
