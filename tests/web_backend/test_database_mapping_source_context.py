"""Mapping resolves physical sources by route and ownership under the runtime role."""

# Existing disposable fixture builders deliberately share their private seed helpers.
# pyright: reportPrivateUsage=false

from dataclasses import dataclass, replace
from typing import Any
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
from gds_etl_workbench.application.change_sets.project_apply import ProjectMaterializer
from gds_etl_workbench.domain.errors import MappingBranchUnavailableError
from gds_etl_workbench.domain.modeling_records import MappingAttributeRecord, MappingObjectRecord
from psycopg import sql

from tests.mcp.conftest import DisposablePostgres
from tests.web_backend.mapping_fixtures import mapping_preparation
from tests.web_backend.test_database_project_change_sets import (
    _make_scope_object_dimensional_eligible,
    _required_id,
    _seed_profile_project,
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
    project_id, tenant_id, attribute_id, entra_tenant_id, entra_object_id, _ = (
        _seed_profile_project(database)
    )
    logical_entity_id = _make_scope_object_dimensional_eligible(
        database, project_id=project_id
    )
    with database.connect_owner() as connection:
        seed = connection.execute(
            """
            SELECT object.object_id, object.connection_id, object.object_type_id,
                   connection.system_id, connection.connection_type_id,
                   system.system_type_id, tenant.lane_id
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
                    lane_id, tenant_code, tenant_name, tenant_catalog, gds_admin_catalog
                ) VALUES (%s, %s, 'Shared GDS fixture', %s, %s) RETURNING tenant_id
                """,
                (
                    seed["lane_id"],
                    f"GDS_{project_id}",
                    f"shared_{project_id}",
                    f"admin_{project_id}",
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
                (f"GDS_{project_id}", seed["system_type_id"]),
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
                    f"STORE_{project_id}",
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
            "INSERT INTO project.project_input_scope (project_id, object_id) VALUES (%s, %s)",
            (project_id, source_object_id),
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
                project_id, logical_entity_id, source_object_id,
                logical_entity_source_mapping_rationale
            ) SELECT %s, entity.logical_entity_id, source.object_id,
                     'Registered source fixture.'
                FROM workflow.logical_entity AS entity
                CROSS JOIN (VALUES (%s::BIGINT), (%s::BIGINT)) AS source(object_id)
               WHERE entity.project_id = %s AND entity.logical_entity_id = %s
            """,
            (
                project_id,
                source_object_id,
                bronze_object_id,
                project_id,
                logical_entity_id,
            ),
        )
        modeled_entity_id = logical_entity_id
        if dimensional:
            entity_id = _required_id(
                connection.execute(
                    """
                    INSERT INTO workflow.dimensional_entity (
                        project_id, dimensional_entity_schema_name, dimensional_entity_name,
                        dimensional_entity_definition,
                        dimensional_entity_type, dimensional_entity_grain_definition
                    ) VALUES (%s, 'gold', 'Customer', 'One customer.', 'dimension', 'One customer.')
                    RETURNING dimensional_entity_id
                    """,
                    (project_id,),
                ).fetchone(),
                "dimensional_entity_id",
            )
            _required_id(
                connection.execute(
                    """
                    INSERT INTO workflow.dimensional_attribute (
                        project_id, dimensional_entity_id, dimensional_attribute_name,
                        dimensional_attribute_definition, dimensional_attribute_data_type,
                        dimensional_attribute_ordinal_position
                    ) VALUES (%s, %s, 'customer_id', 'Customer identifier.', 'bigint', 1)
                    RETURNING dimensional_attribute_id
                    """,
                    (project_id, entity_id),
                ).fetchone(),
                "dimensional_attribute_id",
            )
            connection.execute(
                """
                INSERT INTO workflow.dimensional_entity_source_mapping (
                    project_id, dimensional_entity_id, source_logical_entity_id,
                    dimensional_entity_source_mapping_rationale
                ) VALUES (%s, %s, %s, 'Applied Logical source.')
                """,
                (project_id, entity_id, logical_entity_id),
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
                        tenant_id, project_id, project_revision, project_workflow,
                        workflow_execution_mode, actor_principal_id,
                        actor_entra_principal_identity_id, agent_sdk_code, agent_provider_code,
                        agent_model_code, reasoning_effort_code, max_turns,
                        validation_retry_count, selected_scope_digest, selected_scope_count,
                        workflow_run_state, correlation_id, started_time,
                        modeled_entity_type, mapping_operation, mapping_coverage_mode, mapping_route
                    ) VALUES (%s, %s, 1, 'mapping', 'one_shot', %s, %s,
                        'openai_agents_sdk', 'databricks', 'test-project', 'medium', 8, 1,
                        %s, 1, 'running', %s, CURRENT_TIMESTAMP, %s, %s, 'selected_targets', %s)
                    RETURNING workflow_run_id
                    """,
                    (
                        tenant_id,
                        project_id,
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
                    workflow_run_id,project_id,modeled_entity_type,modeled_entity_id,
                    modeled_entity_schema_name,modeled_entity_name,selection_order)
                 SELECT %s,project_id,modeled_entity_type,modeled_entity_id,
                    modeled_entity_schema_name,modeled_entity_name,1
                 FROM workflow.modeled_entity WHERE project_id=%s AND modeled_entity_type=%s
                   AND modeled_entity_id=%s RETURNING workflow_run_entity_selection_id)
                 INSERT INTO application.workflow_run_mapping_target_selection (
                   workflow_run_id,project_id,workflow_run_entity_selection_id,source_system_id,selection_order)
                 SELECT %s,%s,workflow_run_entity_selection_id,%s,1 FROM selected""",
                (
                    run_id,
                    project_id,
                    entity_type,
                    modeled_entity_id,
                    run_id,
                    project_id,
                    source_system_id,
                ),
            )
    plan_data = mapping_preparation().plan.model_dump(mode="python")
    plan_data["agent_plan"].update(
        workflow_run_id=run_id,
        project_id=project_id,
        project_revision=1,
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


def _seed_context_mapping_target(
    database: DisposablePostgres,
    scope: MappingScope,
    *,
    dimensional: bool,
) -> tuple[int, str]:
    """An Entity supported only by a Context record, using only disposable fixture state."""
    layer = "dimensional" if dimensional else "logical"
    with database.connect_owner() as connection:
        context_group_id = _required_id(
            connection.execute(
                """INSERT INTO project.context_group
                (project_id, name, context_type_id)
                VALUES (%s, 'Generated reference values',
                    (SELECT context_type_id FROM reference.context_type
                     WHERE name = 'Business Requirement'))
                RETURNING context_group_id""",
                (scope.plan.project_id,),
            ).fetchone(),
            "context_group_id",
        )
        context_record_id = str(uuid4())
        connection.execute(
            """INSERT INTO project.context_record
            (project_id, context_group_id, context_record_id, context_text)
            VALUES (%s, %s, %s::UUID,
                    'Produce one row with reference_id equal to 1.')""",
            (scope.plan.project_id, context_group_id, context_record_id),
        )
        entity_id = _required_id(
            connection.execute(
                sql.SQL(
                    "INSERT INTO workflow.{} (project_id, {}, {}, {}, {}, {}) "
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
                    scope.plan.project_id,
                    "gold" if dimensional else "silver",
                    "dimension" if dimensional else "reference",
                ),
            ).fetchone(),
            "entity_id",
        )
        connection.execute(
            sql.SQL(
                "INSERT INTO workflow.{} (project_id, {}, {}, {}, {}, {}, {}, {}) "
                "VALUES (%s,%s,'reference_id','Generated key.','bigint',1,%s,FALSE)"
            ).format(
                sql.Identifier(f"{layer}_attribute"),
                sql.Identifier(f"{layer}_entity_id"),
                sql.Identifier(f"{layer}_attribute_name"),
                sql.Identifier(f"{layer}_attribute_definition"),
                sql.Identifier(f"{layer}_attribute_data_type"),
                sql.Identifier(f"{layer}_attribute_ordinal_position"),
                sql.Identifier(f"{layer}_attribute_is_surrogate_key"),
                sql.Identifier(f"{layer}_attribute_is_nullable"),
            ),
            (scope.plan.project_id, entity_id, True),
        )
        connection.execute(
            sql.SQL(
                "INSERT INTO workflow.{} (project_id, {}, context_record_id, {}) "
                "VALUES (%s,%s,%s,'Explicit generated reference rule.')"
            ).format(
                sql.Identifier(f"{layer}_entity_source_mapping"),
                sql.Identifier(f"{layer}_entity_id"),
                sql.Identifier(f"{layer}_entity_source_mapping_rationale"),
            ),
            (scope.plan.project_id, entity_id, context_record_id),
        )
    return entity_id, context_record_id


def _generation_targets(
    connection: Any, scope: MappingScope, entity_type: str
) -> list[dict[str, Any]]:
    from gds_workbench_api.features.mapping.read_service import (
        _MAPPING_GENERATION_TARGETS_SQL,
    )

    return connection.execute(
        _MAPPING_GENERATION_TARGETS_SQL,
        (
            scope.tenant_id,
            scope.plan.project_id,
            entity_type,
            scope.tenant_id,
            scope.plan.project_id,
            entity_type,
            200,
            0,
        ),
    ).fetchall()


def _branches(connection: Any, project_id: int, entity_type: str) -> set[tuple[int, int]]:
    return {
        (row["modeled_entity_id"], row["source_system_id"])
        for row in connection.execute(
            "SELECT * FROM workflow.list_mapping_branches(%s, %s)", (project_id, entity_type)
        ).fetchall()
    }


def _add_scope_source_table(connection: Any, scope: MappingScope, code: str) -> tuple[int, int]:
    """Another System with one Source table in the Project Input Scope."""
    template = connection.execute(
        """
        SELECT object.object_type_id, object.zone_id, connection.connection_type_id,
               system.system_type_id
          FROM core.object AS object
          JOIN core.connection AS connection USING (connection_id)
          JOIN core.system AS system USING (system_id)
         WHERE object.object_id = %s
        """,
        (scope.source_object_id,),
    ).fetchone()
    assert template is not None
    system_id = _required_id(
        connection.execute(
            "INSERT INTO core.system (system_code, system_name, system_type_id) "
            "VALUES (%s, %s, %s) RETURNING system_id",
            (f"{code}_{scope.plan.project_id}", code, template["system_type_id"]),
        ).fetchone(),
        "system_id",
    )
    connection_id = _required_id(
        connection.execute(
            "INSERT INTO core.connection (tenant_id, system_id, connection_code, "
            "connection_name, connection_type_id) VALUES (%s, %s, %s, %s, %s) "
            "RETURNING connection_id",
            (scope.tenant_id, system_id, f"{code}_SOURCE", code, template["connection_type_id"]),
        ).fetchone(),
        "connection_id",
    )
    object_id = _required_id(
        connection.execute(
            "INSERT INTO core.object (connection_id, source_tenant_id, object_schema, "
            "object_name, object_type_id, zone_id) VALUES (%s, %s, 'source', %s, %s, %s) "
            "RETURNING object_id",
            (
                connection_id,
                scope.tenant_id,
                code.lower(),
                template["object_type_id"],
                template["zone_id"],
            ),
        ).fetchone(),
        "object_id",
    )
    connection.execute(
        "INSERT INTO project.project_input_scope (project_id, object_id) VALUES (%s, %s)",
        (scope.plan.project_id, object_id),
    )
    return system_id, object_id


@pytest.mark.parametrize("dimensional", [False, True])
def test_context_never_adds_a_mapping_branch(
    web_postgres_database: DisposablePostgres,
    dimensional: bool,
) -> None:
    from gds_workbench_api.features.mapping.read_service import _UNSUPPLIED_ENTITY_COUNT_SQL

    scope = _seed_mapping_scope(web_postgres_database, dimensional=False, create_run=False)
    entity_id, context_record_id = _seed_context_mapping_target(
        web_postgres_database, scope, dimensional=dimensional
    )
    entity_type = "dimensional_entity" if dimensional else "logical_entity"
    with web_postgres_database.connect_owner() as connection:
        unsupplied = {
            "unsupplied_entity_count": 1,
        }
        for system_id in (None, scope.source_system_id):
            # Neither a project-wide nor a System-scoped Context Group creates a branch.
            connection.execute(
                "UPDATE project.context_group SET source_system_id=%s WHERE "
                "context_group_id=(SELECT context_group_id "
                "FROM project.context_record WHERE context_record_id=%s)",
                (system_id, context_record_id),
            )
            assert not any(
                branch[0] == entity_id
                for branch in _branches(connection, scope.plan.project_id, entity_type)
            )
            assert not any(
                row["entity_id"] == entity_id
                for row in _generation_targets(connection, scope, entity_type)
            )
            assert (
                connection.execute(
                    _UNSUPPLIED_ENTITY_COUNT_SQL,
                    (
                        scope.tenant_id,
                        scope.plan.project_id,
                        entity_type,
                        scope.plan.project_id,
                        entity_type,
                    ),
                ).fetchone()
                == unsupplied
            )


def test_logical_branches_follow_each_entitys_own_source_systems(
    web_postgres_database: DisposablePostgres,
) -> None:
    scope = _seed_mapping_scope(web_postgres_database, dimensional=False, create_run=False)
    project_id, entity_id = scope.plan.project_id, scope.logical_entity_id
    with web_postgres_database.connect_owner() as connection:
        other_system_id, other_object_id = _add_scope_source_table(connection, scope, "BILLING")
        # A System in Input Scope that none of the Entity's tables come from adds nothing;
        # the Bronze table resolves to its originating System, not its lake placement.
        assert _branches(connection, project_id, "logical_entity") == {
            (entity_id, scope.source_system_id)
        }
        assert {
            (row["entity_id"], row["source_system"]["system_id"])
            for row in _generation_targets(connection, scope, "logical_entity")
        } == {(entity_id, scope.source_system_id)}
        connection.execute(
            "INSERT INTO workflow.logical_entity_source_mapping (project_id, logical_entity_id, "
            "source_object_id, logical_entity_source_mapping_rationale) "
            "VALUES (%s, %s, %s, 'Billing also supplies this Entity.')",
            (project_id, entity_id, other_object_id),
        )
        assert _branches(connection, project_id, "logical_entity") == {
            (entity_id, scope.source_system_id),
            (entity_id, other_system_id),
        }
        connection.execute(
            "UPDATE workflow.logical_entity_source_mapping "
            "SET logical_entity_source_mapping_is_active = FALSE "
            "WHERE project_id = %s AND logical_entity_id = %s AND source_object_id = %s",
            (project_id, entity_id, other_object_id),
        )
        assert _branches(connection, project_id, "logical_entity") == {
            (entity_id, scope.source_system_id)
        }


def test_dimensional_branches_need_complete_applied_logical_mapping(
    web_postgres_database: DisposablePostgres,
) -> None:
    scope = _seed_mapping_scope(web_postgres_database, create_run=False)
    project_id = scope.plan.project_id
    dimensional_id = scope.plan.pair.modeled_entity_id
    with web_postgres_database.connect_owner() as connection:
        assert _branches(connection, project_id, "dimensional_entity") == {
            (dimensional_id, scope.source_system_id)
        }
        connection.execute(
            "UPDATE workflow.mapping_attribute SET attribute_mapping_transformation_document = NULL "
            "WHERE project_id = %s AND logical_entity_id = %s",
            (project_id, scope.logical_entity_id),
        )
        assert _branches(connection, project_id, "dimensional_entity") == set()


def _mapping_pair(
    entity_type: str, schema: str, name: str, system_code: str, status: str = "active"
) -> MappingObjectRecord:
    return MappingObjectRecord.model_validate(
        {
            "modeled_entity_type": entity_type,
            "modeled_entity_schema_name": schema,
            "modeled_entity_name": name,
            "source_system_code": system_code,
            "output_template_code": None,
            "object_dependency_order": 0,
            "mapping_transformation_document": None,
            "object_mapping_status": status,
            "object_mapping_is_locked": False,
        }
    )


async def _apply_change_set(
    database: DisposablePostgres, project_id: int, records: dict[str, tuple[Any, ...]]
) -> None:
    runtime = database.create_runtime_adapter()
    await runtime.open()
    try:
        async with runtime.write_transaction() as transaction:
            await ProjectMaterializer(transaction, project_id, "a" * 64).apply(records)
    finally:
        await runtime.close()


async def test_change_sets_make_mappings_active_only_for_branches(
    web_postgres_database: DisposablePostgres,
) -> None:
    scope = _seed_mapping_scope(web_postgres_database, dimensional=False, create_run=False)
    project_id, entity_id = scope.plan.project_id, scope.logical_entity_id
    with web_postgres_database.connect_owner() as connection:
        billing_id, billing_object_id = _add_scope_source_table(connection, scope, "BILLING")
        codes = {
            row["system_id"]: row["system_code"]
            for row in connection.execute(
                "SELECT system_id, system_code FROM core.system WHERE system_id = ANY(%s)",
                ([scope.source_system_id, billing_id, scope.other_system_id],),
            ).fetchall()
        }
        # An older active Mapping from the lake's own System, which is no branch.
        connection.execute(
            "INSERT INTO workflow.mapping_object (project_id, logical_entity_id, "
            "modeled_entity_type, source_system_id, object_mapping_status) "
            "VALUES (%s, %s, 'logical_entity', %s, 'active')",
            (project_id, entity_id, scope.other_system_id),
        )

    def pair(system_id: int, status: str = "active") -> MappingObjectRecord:
        return _mapping_pair("logical_entity", "silver", "order", codes[system_id], status)

    def apply(*pairs: MappingObjectRecord):
        return _apply_change_set(web_postgres_database, project_id, {"mapping_object": pairs})

    # BILLING is in Input Scope, but none of the Entity's tables come from it.
    with pytest.raises(MappingBranchUnavailableError, match="mapping_object record 2"):
        await apply(pair(scope.source_system_id), pair(billing_id))
    # An inactive pair is no Mapping in use; making it active is checked.
    await apply(pair(billing_id, "inactive"))
    with pytest.raises(MappingBranchUnavailableError, match="mapping_object record 1"):
        await apply(pair(billing_id))
    # An already active pair stays editable and can be retired.
    edited = pair(scope.other_system_id).model_copy(
        update={"mapping_transformation_document": {"steps": ["Older rule."]}}
    )
    await apply(edited)
    await apply(pair(scope.other_system_id, "inactive"))
    with web_postgres_database.connect_owner() as connection:
        connection.execute(
            "INSERT INTO workflow.logical_entity_source_mapping (project_id, logical_entity_id, "
            "source_object_id, logical_entity_source_mapping_rationale) "
            "VALUES (%s, %s, %s, 'Billing also supplies this Entity.')",
            (project_id, entity_id, billing_object_id),
        )
    await apply(pair(billing_id))
    with web_postgres_database.connect_owner() as connection:
        statuses = {
            row["source_system_id"]: row["object_mapping_status"]
            for row in connection.execute(
                "SELECT source_system_id, object_mapping_status FROM workflow.mapping_object "
                "WHERE project_id = %s AND logical_entity_id = %s",
                (project_id, entity_id),
            ).fetchall()
        }
    assert statuses == {
        scope.source_system_id: "active",
        billing_id: "active",
        scope.other_system_id: "inactive",
    }


async def test_change_set_gold_mapping_counts_its_own_logical_mapping(
    web_postgres_database: DisposablePostgres,
) -> None:
    scope = _seed_mapping_scope(web_postgres_database, create_run=False)
    project_id = scope.plan.project_id
    with web_postgres_database.connect_owner() as connection:
        system = connection.execute(
            "SELECT system_code FROM core.system WHERE system_id = %s", (scope.source_system_id,)
        ).fetchone()
        assert system is not None
        # The supporting Logical Mapping lacks its only Attribute rule.
        connection.execute(
            "UPDATE workflow.mapping_attribute SET attribute_mapping_transformation_document = NULL "
            "WHERE project_id = %s AND logical_entity_id = %s",
            (project_id, scope.logical_entity_id),
        )
    gold = _mapping_pair("dimensional_entity", "gold", "Customer", system["system_code"])
    rule = MappingAttributeRecord.model_validate(
        {
            "modeled_entity_type": "logical_entity",
            "modeled_entity_schema_name": "silver",
            "modeled_entity_name": "order",
            "modeled_attribute_name": "customer_id",
            "source_system_code": system["system_code"],
            "output_template_code": None,
            "attribute_mapping_transformation_document": {"transformation": "customer_id"},
            "attribute_mapping_status": "active",
            "attribute_mapping_is_locked": False,
        }
    )
    with pytest.raises(MappingBranchUnavailableError, match="mapping_object record 1"):
        await _apply_change_set(web_postgres_database, project_id, {"mapping_object": (gold,)})
    # The same Change Set completes the Logical Mapping, so the Gold branch exists.
    await _apply_change_set(
        web_postgres_database,
        project_id,
        {"mapping_object": (gold,), "mapping_attribute": (rule,)},
    )
    with web_postgres_database.connect_owner() as connection:
        assert _branches(connection, project_id, "dimensional_entity") == {
            (scope.plan.pair.modeled_entity_id, scope.source_system_id)
        }


async def test_dimensional_mapping_uses_logical_entities_without_registered_targets(
    web_postgres_database: DisposablePostgres,
) -> None:
    scope = _seed_mapping_scope(web_postgres_database)
    with web_postgres_database.connect_owner() as connection:
        connection.execute(
            "UPDATE project.project SET logical_entity_scd_type='type_1', "
            "dimensional_entity_scd_type='type_2' WHERE project_id=%s",
            (scope.plan.project_id,),
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


async def test_logical_mapping_keeps_source_and_ingested_bronze_inputs(
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


async def test_mapping_target_requires_owning_project_tenant(
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
    scope = _seed_mapping_scope(web_postgres_database, dimensional=dimensional)
    with web_postgres_database.connect_owner() as connection:
        pairs = _generation_targets(connection, scope, scope.plan.modeled_entity_type)
        assert {
            (row["entity_id"], row["source_system"]["system_id"]) for row in pairs
        } == {(scope.plan.pair.modeled_entity_id, scope.source_system_id)}
    context = await _load(web_postgres_database, scope)
    assert assess_mapping_readiness(plan=scope.plan, context=context).ready
