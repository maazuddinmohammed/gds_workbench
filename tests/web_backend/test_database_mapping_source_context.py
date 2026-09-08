"""Mapping resolves physical sources by route and ownership under the runtime role."""

# Existing disposable fixture builders deliberately share their private seed helpers.
# pyright: reportPrivateUsage=false

from dataclasses import dataclass
from typing import LiteralString
from uuid import uuid4

import pytest
from gds_workbench_api.database import WebPostgresDatabase
from gds_workbench_api.features.mapping import (
    MappingRunContext,
    MappingRunPlan,
    assess_mapping_readiness,
)
from gds_workbench_api.features.mapping.preparation_contracts import (
    MappingRunContextUnavailableError,
)
from gds_workbench_api.features.mapping.preparation_repository import (
    PostgresMappingRunContextRepository,
)

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
    silver_object_id: int
    plan: MappingRunPlan


def _seed_mapping_scope(database: DisposablePostgres, *, dimensional: bool = True) -> MappingScope:
    model_id, tenant_id, attribute_id, entra_tenant_id, entra_object_id, _ = _seed_profile_model(
        database
    )
    silver_object_id = _make_scope_object_dimensional_eligible(database, model_id=model_id)
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
                (seed["project_id"], f"GDS_{model_id}", f"shared_{model_id}", f"admin_{model_id}"),
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
            "UPDATE core.object SET connection_id = %s WHERE object_id IN (%s, %s)",
            (placement_connection_id, bronze_object_id, silver_object_id),
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
            ) SELECT %s, binding.logical_entity_id, 'object', source.object_id,
                     source.mapping_order, 'Registered source fixture.'
                FROM workflow.model_object_binding AS binding
                CROSS JOIN (VALUES (%s::BIGINT, 2), (%s::BIGINT, 1))
                    AS source(object_id, mapping_order)
               WHERE binding.model_id = %s AND binding.object_id = %s
            """,
            (model_id, source_object_id, bronze_object_id, model_id, silver_object_id),
        )
        target_object_id = silver_object_id
        if dimensional:
            target_object_id = _required_id(
                connection.execute(
                    """
                    INSERT INTO core.object (
                        connection_id, source_tenant_id, object_schema,
                        object_name, object_type_id, zone_id
                    ) SELECT %s, %s, 'gold', 'orders', %s, zone_id
                        FROM reference.zone WHERE lower(btrim(zone_code)) = 'gold'
                    RETURNING object_id
                    """,
                    (placement_connection_id, tenant_id, seed["object_type_id"]),
                ).fetchone(),
                "object_id",
            )
            target_attribute_id = _required_id(
                connection.execute(
                    """
                    INSERT INTO core.attribute (
                        object_id, attribute_name, attribute_ordinal_position,
                        attribute_data_type, attribute_nullability
                    ) VALUES (%s, 'customer_id', 1, 'bigint', FALSE) RETURNING attribute_id
                    """,
                    (target_object_id,),
                ).fetchone(),
                "attribute_id",
            )
            entity_id = _required_id(
                connection.execute(
                    """
                    INSERT INTO workflow.dimensional_entity (
                        model_id, dimensional_entity_name, dimensional_entity_definition,
                        dimensional_entity_type, dimensional_entity_grain_definition
                    ) VALUES (%s, 'Customer', 'One customer.', 'dimension', 'One customer.')
                    RETURNING dimensional_entity_id
                    """,
                    (model_id,),
                ).fetchone(),
                "dimensional_entity_id",
            )
            modeled_attribute_id = _required_id(
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
            binding_id = _required_id(
                connection.execute(
                    """
                    INSERT INTO workflow.model_object_binding (
                        model_id, object_id, modeled_entity_type, dimensional_entity_id
                    ) VALUES (%s, %s, 'dimensional_entity', %s)
                    RETURNING model_object_binding_id
                    """,
                    (model_id, target_object_id, entity_id),
                ).fetchone(),
                "model_object_binding_id",
            )
            connection.execute(
                """
                INSERT INTO workflow.model_attribute_binding (
                    model_object_binding_id, dimensional_attribute_id, attribute_id
                ) VALUES (%s, %s, %s)
                """,
                (binding_id, modeled_attribute_id, target_attribute_id),
            )
            connection.execute(
                """
                INSERT INTO workflow.dimensional_entity_source_mapping (
                    model_id, dimensional_entity_id, support_source_type, source_object_id,
                    dimensional_entity_source_role, dimensional_entity_source_mapping_order,
                    dimensional_entity_source_mapping_rationale
                ) VALUES (%s, %s, 'object', %s, 'support', 1, 'Applied Silver source.')
                """,
                (model_id, entity_id, silver_object_id),
            )
            connection.execute(
                """
                INSERT INTO workflow.mapping_source_system_dependency (
                    model_id, modeled_entity_type, source_system_id
                ) VALUES (%s, 'dimensional_entity', %s)
                """,
                (model_id, source_system_id),
            )
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
        operation = "build" if dimensional else "extend"
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
            """
            INSERT INTO application.workflow_run_mapping_target_selection (
                workflow_run_id, model_id, object_id, source_system_id, selection_order
            ) VALUES (%s, %s, %s, %s, 1)
            """,
            (run_id, model_id, target_object_id, source_system_id),
        )
    plan_data = mapping_preparation().plan.model_dump(mode="python")
    plan_data["agent_plan"].update(
        workflow_run_id=run_id,
        model_id=model_id,
        model_revision=1,
        correlation_id=correlation_id,
        modeled_entity_type=entity_type,
        selected_object_ids=(target_object_id,),
    )
    plan_data.update(
        actor_principal_id=actor_id,
        pair={
            "target_object_id": target_object_id,
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
        silver_object_id,
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


async def test_dimensional_mapping_uses_owned_silver_outside_input_scope_on_shared_storage(
    web_postgres_database: DisposablePostgres,
) -> None:
    scope = _seed_mapping_scope(web_postgres_database)
    with web_postgres_database.connect_owner() as connection:
        assert (
            connection.execute(
                "SELECT 1 FROM model.model_input_scope WHERE model_id = %s AND object_id = %s",
                (scope.plan.model_id, scope.silver_object_id),
            ).fetchone()
            is None
        )
    context = await _load(web_postgres_database, scope)
    assert [item.object.object_id for item in context.sources] == [scope.silver_object_id]
    assert context.target.source_tenant_id == scope.tenant_id
    assert context.target.tenant_id == scope.placement_tenant_id != scope.tenant_id
    assert context.target.tenant_catalog == f"shared_{scope.plan.model_id}"
    assert context.sources[0].object.source_tenant_id == scope.tenant_id
    assert context.sources[0].object.tenant_id == scope.placement_tenant_id
    assert context.sources[0].object.scope_is_active
    assert assess_mapping_readiness(plan=scope.plan, context=context).ready


async def test_logical_mapping_keeps_ordered_source_and_ingested_bronze_inputs(
    web_postgres_database: DisposablePostgres,
) -> None:
    scope = _seed_mapping_scope(web_postgres_database, dimensional=False)
    context = await _load(web_postgres_database, scope)
    assert [item.object.object_id for item in context.sources] == [
        scope.bronze_object_id,
        scope.source_object_id,
    ]
    assert [item.object.zone_code for item in context.sources] == ["bronze", "source"]
    assert context.sources[0].object.tenant_id == scope.placement_tenant_id
    assert all(item.object.source_tenant_id == scope.tenant_id for item in context.sources)
    assert assess_mapping_readiness(plan=scope.plan, context=context).ready


@pytest.mark.parametrize(
    "change",
    [
        "inactive_object",
        "inactive_binding",
        "inactive_mapping",
        "unmapped",
        "wrong_system",
        "foreign_owner",
    ],
)
async def test_dimensional_mapping_rejects_unavailable_or_unrelated_silver(
    web_postgres_database: DisposablePostgres,
    change: str,
) -> None:
    scope = _seed_mapping_scope(web_postgres_database)
    statements: dict[str, tuple[LiteralString, tuple[object, ...]]] = {
        "inactive_object": (
            "UPDATE core.object SET is_active = FALSE WHERE object_id = %s",
            (scope.silver_object_id,),
        ),
        "inactive_binding": (
            """UPDATE workflow.model_object_binding SET model_object_binding_status = 'inactive'
                WHERE model_id = %s AND object_id = %s""",
            (scope.plan.model_id, scope.silver_object_id),
        ),
        "inactive_mapping": (
            """UPDATE workflow.mapping_object SET object_mapping_status = 'inactive'
                WHERE model_id = %s""",
            (scope.plan.model_id,),
        ),
        "unmapped": (
            """UPDATE workflow.mapping_object SET mapping_transformation_document = NULL
                WHERE model_id = %s""",
            (scope.plan.model_id,),
        ),
        "wrong_system": (
            "UPDATE workflow.mapping_object SET source_system_id = %s WHERE model_id = %s",
            (scope.other_system_id, scope.plan.model_id),
        ),
        "foreign_owner": (
            "UPDATE core.object SET source_tenant_id = %s WHERE object_id = %s",
            (scope.placement_tenant_id, scope.silver_object_id),
        ),
    }
    with web_postgres_database.connect_owner() as connection:
        if change == "wrong_system":
            connection.execute(
                """
                INSERT INTO workflow.mapping_source_system_dependency (
                    model_id, modeled_entity_type, source_system_id
                ) VALUES (%s, 'logical_entity', %s)
                """,
                (scope.plan.model_id, scope.other_system_id),
            )
        query, parameters = statements[change]
        connection.execute(query, parameters)
        if change == "wrong_system":
            # It remains eligible for Dimensional modeling, but not this selected System.
            assert connection.execute(
                """SELECT is_dimensional_source_eligible
                     FROM workflow.list_model_object_eligibility(%s) WHERE object_id = %s""",
                (scope.plan.model_id, scope.silver_object_id),
            ).fetchone() == {"is_dimensional_source_eligible": True}
    context = await _load(web_postgres_database, scope)
    assert not context.sources
    assert "source.objects_missing" in {
        item.code for item in assess_mapping_readiness(plan=scope.plan, context=context).issues
    }


async def test_mapping_target_rejects_foreign_source_tenant_despite_shared_placement(
    web_postgres_database: DisposablePostgres,
) -> None:
    scope = _seed_mapping_scope(web_postgres_database)
    with web_postgres_database.connect_owner() as connection:
        connection.execute(
            "UPDATE core.object SET source_tenant_id = %s WHERE object_id = %s",
            (scope.placement_tenant_id, scope.plan.pair.target_object_id),
        )
    with pytest.raises(MappingRunContextUnavailableError):
        await _load(web_postgres_database, scope)
