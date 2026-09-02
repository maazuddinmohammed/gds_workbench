from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, LiteralString, cast
from uuid import uuid4

import psycopg
import pytest
from psycopg.types.json import Jsonb

if TYPE_CHECKING:
    from conftest import DisposablePostgres


SEED_ROOT = Path(__file__).parents[2] / "database" / "seed"
DEMO_SEED = SEED_ROOT / "01_metadata_snapshot_demo.sql"
CLEANUP_TEMPLATE = SEED_ROOT / "06_model_cleanup.template.sql"
MODEL_PLACEHOLDER = "__REPLACE_WITH_MODEL_ID__"


def test_model_cleanup_template_is_inert_until_rendered(
    bootstrap_postgres_database: DisposablePostgres,
) -> None:
    template = CLEANUP_TEMPLATE.read_text(encoding="utf-8")
    with bootstrap_postgres_database.connect_owner() as connection:
        with pytest.raises(
            psycopg.errors.RaiseException,
            match="replace the Model cleanup Model ID placeholder",
        ):
            connection.execute(cast(LiteralString, template))


def test_model_cleanup_removes_model_history_and_bound_physical_metadata(
    bootstrap_postgres_database: DisposablePostgres,
) -> None:
    template = CLEANUP_TEMPLATE.read_text(encoding="utf-8")
    with bootstrap_postgres_database.connect_owner() as connection:
        connection.execute(cast(LiteralString, DEMO_SEED.read_text(encoding="utf-8")))
        context = connection.execute(
            """
            SELECT tenant.tenant_id,
                   system.system_id,
                   bronze.object_id AS bronze_object_id,
                   silver.object_id AS silver_object_id,
                   gold.object_id AS gold_object_id,
                   silver_attribute.attribute_id AS silver_attribute_id,
                   gold_attribute.attribute_id AS gold_attribute_id
              FROM core.tenant AS tenant
              JOIN core.system AS system
                ON system.system_code = 'DEMO_CUSTOMER_SYSTEM'
              JOIN core.object AS bronze
                ON bronze.source_tenant_id = tenant.tenant_id
               AND bronze.object_schema = 'bronze_demo'
              JOIN core.object AS silver
                ON silver.source_tenant_id = tenant.tenant_id
               AND silver.object_schema = 'silver_demo'
              JOIN core.object AS gold
                ON gold.source_tenant_id = tenant.tenant_id
               AND gold.object_schema = 'gold_demo'
              JOIN core.attribute AS silver_attribute
                ON silver_attribute.object_id = silver.object_id
               AND silver_attribute.attribute_ordinal_position = 1
              JOIN core.attribute AS gold_attribute
                ON gold_attribute.object_id = gold.object_id
               AND gold_attribute.attribute_ordinal_position = 1
             WHERE tenant.tenant_code = 'DEMO_TENANT'
            """
        ).fetchone()
        assert context is not None

        principal = connection.execute(
            """
            INSERT INTO security.principal (
                principal_type, principal_display_name, principal_email
            ) VALUES ('user', 'Cleanup Tester', %s)
            RETURNING principal_id
            """,
            (f"cleanup-{uuid4().hex}@example.test",),
        ).fetchone()
        assert principal is not None
        model = connection.execute(
            """
            INSERT INTO model.model (tenant_id, model_name)
            VALUES (%s, %s)
            RETURNING model_id, model_revision
            """,
            (context["tenant_id"], f"Cleanup {uuid4().hex}"),
        ).fetchone()
        assert model is not None
        model_id = model["model_id"]

        connection.execute(
            """
            INSERT INTO model.model_input_scope (model_id, object_id)
            VALUES (%s, %s)
            """,
            (model_id, context["bronze_object_id"]),
        )
        logical = connection.execute(
            """
            INSERT INTO workflow.logical_entity (
                model_id, logical_entity_name, logical_entity_definition,
                logical_entity_type, logical_entity_grain
            ) VALUES (%s, 'CleanupCustomer', 'Customer.', 'core', 'One customer')
            RETURNING logical_entity_id
            """,
            (model_id,),
        ).fetchone()
        assert logical is not None
        logical_attribute = connection.execute(
            """
            INSERT INTO workflow.logical_attribute (
                model_id, logical_entity_id, logical_attribute_name,
                logical_attribute_definition, logical_attribute_data_type,
                logical_attribute_ordinal_position
            ) VALUES (%s, %s, 'CustomerID', 'Customer ID.', 'bigint', 1)
            RETURNING logical_attribute_id
            """,
            (model_id, logical["logical_entity_id"]),
        ).fetchone()
        assert logical_attribute is not None

        dimensional = connection.execute(
            """
            INSERT INTO workflow.dimensional_entity (
                model_id, dimensional_entity_name,
                dimensional_entity_definition, dimensional_entity_type
            ) VALUES (%s, 'DimCleanupCustomer', 'Customer dimension.', 'dimension')
            RETURNING dimensional_entity_id
            """,
            (model_id,),
        ).fetchone()
        assert dimensional is not None
        dimensional_attribute = connection.execute(
            """
            INSERT INTO workflow.dimensional_attribute (
                model_id, dimensional_entity_id, dimensional_attribute_name,
                dimensional_attribute_definition, dimensional_attribute_data_type,
                dimensional_attribute_ordinal_position,
                dimensional_attribute_role, dimensional_attribute_key_role
            ) VALUES (%s, %s, 'CustomerKey', 'Customer key.', 'bigint', 1,
                      'key', 'surrogate')
            RETURNING dimensional_attribute_id
            """,
            (model_id, dimensional["dimensional_entity_id"]),
        ).fetchone()
        assert dimensional_attribute is not None

        logical_binding = connection.execute(
            """
            INSERT INTO workflow.model_object_binding (
                model_id, object_id, modeled_entity_type, logical_entity_id
            ) VALUES (%s, %s, 'logical_entity', %s)
            RETURNING model_object_binding_id
            """,
            (
                model_id,
                context["silver_object_id"],
                logical["logical_entity_id"],
            ),
        ).fetchone()
        dimensional_binding = connection.execute(
            """
            INSERT INTO workflow.model_object_binding (
                model_id, object_id, modeled_entity_type, dimensional_entity_id
            ) VALUES (%s, %s, 'dimensional_entity', %s)
            RETURNING model_object_binding_id
            """,
            (
                model_id,
                context["gold_object_id"],
                dimensional["dimensional_entity_id"],
            ),
        ).fetchone()
        assert logical_binding is not None
        assert dimensional_binding is not None

        logical_attribute_binding = connection.execute(
            """
            INSERT INTO workflow.model_attribute_binding (
                model_object_binding_id, logical_attribute_id, attribute_id
            ) VALUES (%s, %s, %s)
            RETURNING model_attribute_binding_id
            """,
            (
                logical_binding["model_object_binding_id"],
                logical_attribute["logical_attribute_id"],
                context["silver_attribute_id"],
            ),
        ).fetchone()
        dimensional_attribute_binding = connection.execute(
            """
            INSERT INTO workflow.model_attribute_binding (
                model_object_binding_id, dimensional_attribute_id, attribute_id
            ) VALUES (%s, %s, %s)
            RETURNING model_attribute_binding_id
            """,
            (
                dimensional_binding["model_object_binding_id"],
                dimensional_attribute["dimensional_attribute_id"],
                context["gold_attribute_id"],
            ),
        ).fetchone()
        assert logical_attribute_binding is not None
        assert dimensional_attribute_binding is not None

        mapping = connection.execute(
            """
            INSERT INTO workflow.mapping_object (
                model_id, model_object_binding_id, source_system_id
            ) VALUES (%s, %s, %s)
            RETURNING mapping_object_id
            """,
            (
                model_id,
                logical_binding["model_object_binding_id"],
                context["system_id"],
            ),
        ).fetchone()
        assert mapping is not None
        connection.execute(
            """
            INSERT INTO workflow.mapping_attribute (
                mapping_object_id, model_attribute_binding_id
            ) VALUES (%s, %s)
            """,
            (
                mapping["mapping_object_id"],
                logical_attribute_binding["model_attribute_binding_id"],
            ),
        )
        generated_code = connection.execute(
            """
            INSERT INTO workflow.generated_code (
                model_object_binding_id, artifact_name, artifact_type,
                generated_code_content, code_input_digest
            ) VALUES (%s, 'CleanupCustomer.sql', 'sql_file', 'SELECT 1', %s)
            RETURNING generated_code_id
            """,
            (logical_binding["model_object_binding_id"], "a" * 64),
        ).fetchone()
        assert generated_code is not None
        connection.execute(
            """
            INSERT INTO workflow.generated_code_source_system (
                generated_code_id, source_system_id
            ) VALUES (%s, %s)
            """,
            (generated_code["generated_code_id"], context["system_id"]),
        )

        validation_group = connection.execute(
            """
            INSERT INTO workflow.validation_group (
                model_id, tenant_id, system_id, validation_group_name,
                mapping_context_digest
            ) VALUES (%s, %s, %s, 'Cleanup checks', %s)
            RETURNING validation_group_id
            """,
            (model_id, context["tenant_id"], context["system_id"], "b" * 64),
        ).fetchone()
        assert validation_group is not None
        connection.execute(
            """
            INSERT INTO workflow.validation_check (
                validation_group_id, validation_check_name,
                validation_category_code, validation_severity,
                validation_query_sql, validation_comparison_operator,
                validation_comparison_value_type
            ) VALUES (%s, 'Compiles', 'technical', 'blocking', 'SELECT 1',
                      'executes_successfully', 'none')
            """,
            (validation_group["validation_group_id"],),
        )

        workflow_run = connection.execute(
            """
            INSERT INTO application.workflow_run (
                tenant_id, model_id, model_revision, model_workflow,
                actor_principal_id, selected_scope_digest,
                selected_scope_count, correlation_id
            ) VALUES (%s, %s, %s, 'profiling', %s, %s, 1, %s)
            RETURNING workflow_run_id
            """,
            (
                context["tenant_id"],
                model_id,
                model["model_revision"],
                principal["principal_id"],
                "c" * 64,
                uuid4(),
            ),
        ).fetchone()
        assert workflow_run is not None
        connection.execute(
            """
            INSERT INTO application.workflow_run_object_selection (
                workflow_run_id, model_id, object_id, selection_order
            ) VALUES (%s, %s, %s, 1)
            """,
            (
                workflow_run["workflow_run_id"],
                model_id,
                context["bronze_object_id"],
            ),
        )
        connection.execute(
            """
            INSERT INTO model.model_event_log (
                model_id, correlation_id, workflow_run_id,
                model_event_log_sequence, model_event_log_attempt,
                model_workflow, model_event_log_stage,
                model_event_log_status, model_event_log_message
            ) VALUES (%s, %s, %s, 1, 1, 'profiling', 'cleanup-test',
                      'completed', 'Cleanup test event')
            """,
            (model_id, uuid4(), workflow_run["workflow_run_id"]),
        )

        change_set_id = uuid4()
        connection.execute(
            """
            INSERT INTO mcp.model_change_set (
                model_change_set_id, model_id, workflow_run_id,
                base_model_revision, base_source_context_digest,
                base_assertion_digest, base_policy_digest,
                created_by_principal_id, correlation_id
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
            """,
            (
                change_set_id,
                model_id,
                workflow_run["workflow_run_id"],
                model["model_revision"],
                "d" * 64,
                "e" * 64,
                "f" * 64,
                principal["principal_id"],
                uuid4(),
            ),
        )
        connection.execute(
            """
            INSERT INTO mcp.model_change_set_event (
                model_change_set_id, model_id, event_sequence, event_type,
                draft_revision, outcome, correlation_id
            ) VALUES (%s, %s, 1, 'created', 1, 'created', %s)
            """,
            (change_set_id, model_id, uuid4()),
        )
        audit_id = uuid4()
        connection.execute(
            """
            INSERT INTO mcp.tool_call_log (
                tool_call_id, principal_display_name, actor_kind, tool_name,
                tool_policy, tenant_id, input_metadata, tool_call_status
            ) VALUES (%s, 'Cleanup Tester', 'development',
                      'get_model_snapshot', 'tenant_model_write', %s, %s,
                      'succeeded')
            """,
            (
                audit_id,
                context["tenant_id"],
                Jsonb({"model_id": model_id}),
            ),
        )

        rendered = template.replace(MODEL_PLACEHOLDER, str(model_id))
        assert MODEL_PLACEHOLDER not in rendered
        connection.execute(cast(LiteralString, rendered))

        assert (
            connection.execute(
                "SELECT 1 FROM model.model WHERE model_id = %s", (model_id,)
            ).fetchone()
            is None
        )
        assert (
            connection.execute(
                "SELECT 1 FROM application.workflow_run WHERE model_id = %s",
                (model_id,),
            ).fetchone()
            is None
        )
        assert (
            connection.execute(
                "SELECT 1 FROM mcp.model_change_set WHERE model_id = %s", (model_id,)
            ).fetchone()
            is None
        )
        assert (
            connection.execute(
                "SELECT 1 FROM mcp.tool_call_log WHERE tool_call_id = %s", (audit_id,)
            ).fetchone()
            is None
        )
        assert (
            connection.execute(
                "SELECT 1 FROM core.object WHERE object_id = ANY(%s)",
                ([context["silver_object_id"], context["gold_object_id"]],),
            ).fetchone()
            is None
        )
        assert connection.execute(
            "SELECT 1 FROM core.object WHERE object_id = %s",
            (context["bronze_object_id"],),
        ).fetchone() == {"?column?": 1}

        trigger_states = connection.execute(
            """
            SELECT trigger.tgname, trigger.tgenabled
              FROM pg_catalog.pg_trigger AS trigger
             WHERE trigger.tgname IN (
                       'reject_tool_call_log_mutation',
                       'reject_model_event_log_mutation',
                       'guard_workflow_run',
                       'guard_workflow_run_object_selection',
                       'guard_workflow_run_system_selection',
                       'guard_workflow_run_mapping_target_selection',
                       'guard_workflow_run_prompt_snapshot'
                   )
            """
        ).fetchall()
        assert len(trigger_states) == 7
        assert all(row["tgenabled"] == "O" for row in trigger_states)


def test_model_cleanup_refuses_a_bound_object_used_by_another_model(
    bootstrap_postgres_database: DisposablePostgres,
) -> None:
    template = CLEANUP_TEMPLATE.read_text(encoding="utf-8")
    with bootstrap_postgres_database.connect_owner() as connection:
        physical = connection.execute(
            """
            SELECT object_record.connection_id,
                   object_record.source_tenant_id,
                   object_record.object_type_id,
                   zone_record.zone_id
              FROM core.object AS object_record
              CROSS JOIN reference.zone AS zone_record
             WHERE object_record.object_schema = 'bronze_demo'
               AND lower(btrim(zone_record.zone_code)) = 'silver'
            """
        ).fetchone()
        assert physical is not None
        target = connection.execute(
            """
            INSERT INTO core.object (
                connection_id, source_tenant_id, object_schema, object_name,
                object_type_id, zone_id
            ) VALUES (%s, %s, %s, %s, %s, %s)
            RETURNING object_id
            """,
            (
                physical["connection_id"],
                physical["source_tenant_id"],
                f"shared_cleanup_{uuid4().hex}",
                "customer",
                physical["object_type_id"],
                physical["zone_id"],
            ),
        ).fetchone()
        assert target is not None

        model_ids: list[int] = []
        for suffix in ("A", "B"):
            model = connection.execute(
                """
                INSERT INTO model.model (tenant_id, model_name)
                VALUES (%s, %s)
                RETURNING model_id
                """,
                (
                    physical["source_tenant_id"],
                    f"Shared cleanup {suffix} {uuid4().hex}",
                ),
            ).fetchone()
            assert model is not None
            model_ids.append(model["model_id"])
            entity = connection.execute(
                """
                INSERT INTO workflow.logical_entity (
                    model_id, logical_entity_name, logical_entity_definition,
                    logical_entity_type, logical_entity_grain
                ) VALUES (%s, %s, 'Shared customer.', 'core', 'One customer')
                RETURNING logical_entity_id
                """,
                (model["model_id"], f"SharedCustomer{suffix}"),
            ).fetchone()
            assert entity is not None
            connection.execute(
                """
                INSERT INTO workflow.model_object_binding (
                    model_id, object_id, modeled_entity_type, logical_entity_id
                ) VALUES (%s, %s, 'logical_entity', %s)
                """,
                (
                    model["model_id"],
                    target["object_id"],
                    entity["logical_entity_id"],
                ),
            )

        rendered = template.replace(MODEL_PLACEHOLDER, str(model_ids[0]))
        with (
            pytest.raises(
                psycopg.errors.RaiseException,
                match="bound Object used by another Model",
            ),
            connection.transaction(),
        ):
            connection.execute(cast(LiteralString, rendered))

        assert connection.execute(
            "SELECT count(*) AS count FROM model.model WHERE model_id = ANY(%s)",
            (model_ids,),
        ).fetchone() == {"count": 2}
        assert connection.execute(
            "SELECT 1 FROM core.object WHERE object_id = %s",
            (target["object_id"],),
        ).fetchone() == {"?column?": 1}
