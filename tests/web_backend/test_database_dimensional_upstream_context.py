"""Physical Dimensional support loads through actual runtime-role PostgreSQL queries."""

# Existing fixture builders create only sentinel-verified disposable containers.
# pyright: reportPrivateUsage=false
from __future__ import annotations

from typing import Any, cast
from uuid import uuid4

import pytest
from gds_etl_workbench.infrastructure.postgres import ReadIsolation
from gds_workbench_api.database import WebPostgresDatabase
from gds_workbench_api.features.workflows.authoring.context import (
    _SUPPORTING_OBJECT_IDS_SQL,
    PostgresAgentContextRepository,
)
from gds_workbench_api.features.workflows.authoring.context_inputs import OBJECT_FIELDS
from psycopg.types.json import Jsonb

from tests.mcp.conftest import DisposablePostgres
from tests.mcp.enrichment_test_support import seed_model_enrichment
from tests.web_backend.test_database_mapping_source_context import _seed_mapping_scope
from tests.web_backend.test_database_model_change_sets import _required_id
from tests.web_backend.test_dimensional_executor import _plan


@pytest.mark.asyncio
@pytest.mark.parametrize("mode", ["one_shot", "tool_assisted"])
async def test_dimensional_repository_loads_only_authorized_active_selected_lineage(
    web_postgres_database: DisposablePostgres, mode: Any
) -> None:
    database = web_postgres_database
    scope = _seed_mapping_scope(database, dimensional=False)
    foreign = _seed_mapping_scope(database, dimensional=False)
    with database.connect_owner() as connection:
        connection.execute(
            "UPDATE model.model SET logical_entity_scd_type='type_1', "
            "dimensional_entity_scd_type='type_2' WHERE model_id=%s",
            (scope.plan.model_id,),
        )
        other_model_id = _required_id(
            connection.execute(
                """INSERT INTO model.model (tenant_id, model_name, logical_schemas)
               VALUES (%s,%s,'[{"schema_name":"silver","description":null}]')
               RETURNING model_id""",
                (scope.tenant_id, f"Other support model {uuid4().hex}"),
            ).fetchone(),
            "model_id",
        )
        extra_entity_ids: dict[str, int] = {}
        for name, model_id in (
            ("Unselected", scope.plan.model_id),
            ("OtherModel", other_model_id),
        ):
            extra_entity_ids[name] = _required_id(
                connection.execute(
                    """INSERT INTO workflow.logical_entity (
                    model_id,logical_entity_schema_name,logical_entity_name,
                    logical_entity_definition,logical_entity_type,logical_entity_grain)
                    VALUES (%s,'silver',%s,'Unselected contextual entity.','core','One row.')
                    RETURNING logical_entity_id""",
                    (model_id, name),
                ).fetchone(),
                "logical_entity_id",
            )
        for name, model_id, entity_id, physical_active, support_status in (
            (
                "inactive_support",
                scope.plan.model_id,
                scope.logical_entity_id,
                True,
                "inactive",
            ),
            (
                "inactive_object",
                scope.plan.model_id,
                scope.logical_entity_id,
                False,
                "active",
            ),
            (
                "unselected_entity",
                scope.plan.model_id,
                extra_entity_ids["Unselected"],
                True,
                "active",
            ),
            (
                "other_model",
                other_model_id,
                extra_entity_ids["OtherModel"],
                True,
                "active",
            ),
        ):
            object_id = _required_id(
                connection.execute(
                    """INSERT INTO core.object (
                    connection_id, source_tenant_id, object_schema, object_name,
                    object_type_id, zone_id, is_active)
                    SELECT connection_id, source_tenant_id, object_schema, %s,
                           object_type_id, zone_id, %s FROM core.object WHERE object_id=%s
                    RETURNING object_id""",
                    (name, physical_active, scope.bronze_object_id),
                ).fetchone(),
                "object_id",
            )
            connection.execute(
                """INSERT INTO core.attribute (
                    object_id, attribute_name, attribute_ordinal_position,
                    attribute_data_type, attribute_nullability)
                    VALUES (%s,'excluded_value',1,'bigint',FALSE)""",
                (object_id,),
            )
            connection.execute(
                "INSERT INTO model.model_input_scope (model_id, object_id) VALUES (%s,%s)",
                (model_id, object_id),
            )
            connection.execute(
                """INSERT INTO workflow.logical_entity_source_mapping (
                    model_id,logical_entity_id,support_source_type,source_object_id,
                    logical_entity_source_mapping_rationale,logical_entity_source_mapping_status)
                    VALUES (%s,%s,'object',%s,'Excluded support fixture.',%s)""",
                (model_id, entity_id, object_id, support_status),
            )
        connection.execute(
            """UPDATE core.object SET object_description='Enriched supported order source.'
               WHERE object_id=ANY(%s)""",
            ([scope.bronze_object_id, scope.source_object_id],),
        )
        connection.execute(
            """UPDATE core.attribute
               SET attribute_description='Enriched customer account identifier.',
                   attribute_inferred_data_type='BIGINT' WHERE object_id=ANY(%s)""",
            ([scope.bronze_object_id, scope.source_object_id],),
        )
        seed_model_enrichment(connection, scope.plan.model_id)
        connection.execute(
            """INSERT INTO workflow.attribute_profile (model_id, object_id, attribute_id,
                source_context_digest, row_count, non_null_count, null_count, distinct_count,
                percent_populated, percent_duplicates)
                SELECT %s,object_id,attribute_id,%s,10,10,0,8,100,20
                  FROM core.attribute WHERE object_id=%s""",
            (scope.plan.model_id, "a" * 64, scope.bronze_object_id),
        )
        connection.execute(
            """INSERT INTO workflow.analysis_result (
                model_id,from_object_id,from_attribute_id,to_object_id,to_attribute_id,
                relationship_kind,relationship_confidence,relationship_basis)
                SELECT %s,source.object_id,source.attribute_id,target.object_id,target.attribute_id,
                       'reference','high','Stored source-to-Bronze relationship.'
                  FROM core.attribute source CROSS JOIN core.attribute target
                 WHERE source.object_id=%s AND target.object_id=%s""",
            (scope.plan.model_id, scope.source_object_id, scope.bronze_object_id),
        )
        model_row = connection.execute(
            "SELECT model_revision FROM model.model WHERE model_id=%s",
            (scope.plan.model_id,),
        ).fetchone()
        assert model_row is not None
        revision = _required_id(model_row, "model_revision")
        connection.execute(
            """UPDATE application.workflow_run
               SET workflow_run_state='completed', completed_time=CURRENT_TIMESTAMP
               WHERE workflow_run_id=%s""",
            (scope.plan.workflow_run_id,),
        )
        run_id = _required_id(
            connection.execute(
                """INSERT INTO application.workflow_run (
                tenant_id,model_id,model_revision,model_workflow,workflow_execution_mode,
                actor_principal_id,actor_entra_principal_identity_id,
                agent_sdk_code,agent_provider_code,agent_model_code,reasoning_effort_code,
                max_turns,validation_retry_count,selected_scope_digest,selected_scope_count,
                workflow_run_state,correlation_id,started_time,modeled_entity_type)
                SELECT tenant_id,model_id,%s,'dimensional',%s,
                       actor_principal_id,actor_entra_principal_identity_id,
                       agent_sdk_code,agent_provider_code,agent_model_code,reasoning_effort_code,
                       max_turns,validation_retry_count,selected_scope_digest,1,
                       'running',%s,CURRENT_TIMESTAMP,'logical_entity'
                  FROM application.workflow_run WHERE workflow_run_id=%s
                RETURNING workflow_run_id""",
                (revision, mode, uuid4(), scope.plan.workflow_run_id),
            ).fetchone(),
            "workflow_run_id",
        )
        connection.execute(
            """INSERT INTO application.workflow_run_entity_selection (
                workflow_run_id,model_id,modeled_entity_type,modeled_entity_id,
                modeled_entity_schema_name,modeled_entity_name,selection_order)
                SELECT %s,model_id,modeled_entity_type,modeled_entity_id,
                       modeled_entity_schema_name,modeled_entity_name,selection_order
                  FROM application.workflow_run_entity_selection WHERE workflow_run_id=%s""",
            (run_id, scope.plan.workflow_run_id),
        )
        # Known natural keys deliberately include another Tenant to exercise the
        # SQL ownership predicate under the runtime role, independently of Python.
        probe_rows = connection.execute(
            """SELECT object.object_id,tenant.tenant_code,system.system_code,
                       connection.connection_code,object.object_schema,object.object_name
                  FROM core.object object JOIN core.connection connection USING(connection_id)
                  JOIN core.tenant tenant ON tenant.tenant_id=connection.tenant_id
                  JOIN core.system system USING(system_id)
                 WHERE object.object_id=ANY(%s)""",
            (
                [
                    scope.bronze_object_id,
                    scope.source_object_id,
                    foreign.bronze_object_id,
                ],
            ),
        ).fetchall()

    runtime = WebPostgresDatabase(
        dsn=database.web_runtime_dsn(), pool_min=1, pool_max=1, pool_timeout_seconds=5
    )
    await runtime.open()
    try:
        async with runtime.read_transaction(
            isolation=ReadIsolation.REPEATABLE_READ
        ) as transaction:
            probe = await transaction.fetch_all(
                _SUPPORTING_OBJECT_IDS_SQL,
                (
                    Jsonb(
                        [
                            {field: row[field] for field in OBJECT_FIELDS}
                            for row in probe_rows
                        ]
                    ),
                    scope.tenant_id,
                ),
            )
            assert {row["object_id"] for row in probe} == {
                scope.bronze_object_id,
                scope.source_object_id,
            }
            result = await PostgresAgentContextRepository().load(
                transaction,
                tenant_id=scope.tenant_id,
                plan=_plan(mode=mode).model_copy(
                    update={
                        "model_id": scope.plan.model_id,
                        "model_revision": revision,
                        "workflow_run_id": run_id,
                        "selected_entity_ids": (scope.logical_entity_id,),
                    }
                ),
            )
    finally:
        await runtime.close()
    assert result.context.model_details.logical_entity_scd_type == "type_1"
    assert result.context.model_details.dimensional_entity_scd_type == "type_2"
    assert result.context.selected_objects == ()
    assert len(result.context.selected_logical_entities) == 1
    assert len(result.context.supporting_objects) == 2
    actual_keys = {
        tuple(getattr(group.object, field) for field in OBJECT_FIELDS)
        for group in result.context.supporting_objects
    }
    expected_keys = {
        tuple(row[field] for field in OBJECT_FIELDS)
        for row in probe_rows
        if row["object_id"] != foreign.bronze_object_id
    }
    assert actual_keys == expected_keys
    assert {
        group.object.object_schema for group in result.context.supporting_objects
    } == {
        "sales",
        "source",
    }
    assert result.snapshot is not None
    assert all(
        group.object.source_tenant_code == result.snapshot.model_tenant_code
        for group in result.context.supporting_objects
    )
    values = (
        result.tool_catalog.prompt_values
        if result.tool_catalog
        else cast(dict[str, Any], result.embedded_context)["prompt_inputs"]
    )
    assert values["dimensional_entity_scd_type"] == "type_2"
    assert len(values["object_context"]) == len(values["object_attribute_context"]) == 2
    assert len(values["source_context"]) == len(values["ingestion_mapping"]) == 1
    attributes = [
        attribute
        for group in values["object_attribute_context"]
        for attribute in group["attributes"]
    ]
    assert all(
        attribute["attribute_description"] == "Enriched customer account identifier."
        for attribute in attributes
    )
    profiles = [
        attribute["profile"]
        for attribute in attributes
        if attribute["profile"] is not None
    ]
    assert len(profiles) == 1 and profiles[0]["distinct_count"] == 8
    assert profiles[0]["profiled_at"] is not None
    assert profiles[0]["row_scope"] is None
    assert (
        sum(
            len(group["outgoing_relationships"])
            for group in values["object_relationship_context"]
        )
        == 1
    )
    if result.tool_catalog:
        assert (
            len(
                cast(dict[str, Any], result.tool_catalog.invoke("get_objects", {}))[
                    "items"
                ]
            )
            == 2
        )
