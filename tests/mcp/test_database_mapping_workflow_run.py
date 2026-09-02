from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any
from uuid import UUID, uuid4

import pytest
from psycopg.errors import RaiseException

from tests.mcp.database_test_support import require_row
from tests.mcp.test_database_workflow_run_lifecycle import (
    WorkflowContext,
    seed_workflow_context,
)

if TYPE_CHECKING:
    from conftest import DisposablePostgres
    from psycopg import Connection


@dataclass(frozen=True, slots=True)
class MappingRunContext:
    workflow: WorkflowContext
    target_object_id: int
    source_system_id: int
    model_object_binding_id: int


CREATE_MAPPING_RUN_SQL = """
    SELECT *
      FROM application.create_workflow_run(
          %s::UUID, %s::UUID, 'user'::VARCHAR,
          %s::BIGINT, %s::BIGINT, 'mapping'::VARCHAR,
          'one_shot'::VARCHAR,
          NULL::VARCHAR, NULL::VARCHAR, NULL::VARCHAR, NULL::VARCHAR,
          NULL::INTEGER, NULL::INTEGER,
          %s::BIGINT[], ARRAY[]::VARCHAR[], NULL::VARCHAR, NULL::VARCHAR,
          %s::UUID, '{}'::JSONB,
          %s::VARCHAR, 'selected_targets'::VARCHAR,
          %s::BIGINT, %s::BIGINT, %s::BIGINT
      )
"""


def _parameters(
    context: MappingRunContext,
    *,
    correlation_id: UUID,
    operation: str = "build",
    object_template_id: int | None = None,
    attribute_template_id: int | None = None,
) -> tuple[object, ...]:
    workflow = context.workflow
    return (
        workflow.entra_tenant_id,
        workflow.entra_object_id,
        workflow.model_id,
        workflow.model_revision,
        [context.target_object_id],
        correlation_id,
        operation,
        context.source_system_id,
        object_template_id,
        attribute_template_id,
    )


def _seed_mapping_prompt(
    connection: Connection[dict[str, Any]],
    context: WorkflowContext,
) -> None:
    suffix = uuid4().hex
    stage = connection.execute(
        """
        SELECT workflow_stage_id
          FROM application.workflow_stage
         WHERE model_workflow = 'mapping'
           AND workflow_execution_mode = 'one_shot'
           AND workflow_stage_is_agentic
           AND is_active
         ORDER BY workflow_stage_order
         LIMIT 1
        """
    ).fetchone()
    if stage is None:
        stage = require_row(
            connection.execute(
                """
                INSERT INTO application.workflow_stage (
                    model_workflow, workflow_execution_mode,
                    workflow_stage_code, workflow_stage_name,
                    workflow_stage_order, workflow_stage_is_agentic
                ) VALUES (
                    'mapping', 'one_shot', %s, 'Mapping Authoring', 1000, TRUE
                )
                RETURNING workflow_stage_id
                """,
                (f"mapping_authoring_{suffix}",),
            ).fetchone()
        )
    prompt_digest = require_row(
        connection.execute(
            """
            SELECT encode(
                       sha256(
                           convert_to(
                               jsonb_build_object(
                                   'system_prompt_template',
                                       '{{ stage_context }}'::TEXT,
                                   'instruction_prompt_template',
                                       '{{ stage_context }}'::TEXT,
                                   'tool_instruction_prompt_template', NULL::TEXT
                               )::TEXT,
                               'UTF8'
                           )
                       ),
                       'hex'
                   ) AS digest
            """
        ).fetchone()
    )["digest"]
    template_id = require_row(
        connection.execute(
            """
            INSERT INTO application.prompt_template (
                workflow_stage_id, prompt_template_ownership_scope,
                owner_tenant_id, prompt_template_code, prompt_template_name,
                created_by_principal_id, updated_by_principal_id
            ) VALUES (%s, 'tenant', %s, %s, %s, %s, %s)
            RETURNING prompt_template_id
            """,
            (
                stage["workflow_stage_id"],
                context.tenant_id,
                f"mapping_prompt_{suffix}",
                f"Mapping Prompt {suffix}",
                context.principal_id,
                context.principal_id,
            ),
        ).fetchone()
    )["prompt_template_id"]
    version_id = require_row(
        connection.execute(
            """
            INSERT INTO application.prompt_template_version (
                prompt_template_id, workflow_stage_id,
                prompt_template_version_number, system_prompt_template,
                instruction_prompt_template, prompt_template_digest,
                created_by_principal_id, updated_by_principal_id
            ) VALUES (
                %s, %s, 1, '{{ stage_context }}', '{{ stage_context }}',
                %s, %s, %s
            )
            RETURNING prompt_template_version_id
            """,
            (
                template_id,
                stage["workflow_stage_id"],
                prompt_digest,
                context.principal_id,
                context.principal_id,
            ),
        ).fetchone()
    )["prompt_template_version_id"]
    connection.execute(
        """
        UPDATE application.prompt_template_version
           SET prompt_template_version_status = 'published',
               published_time = CURRENT_TIMESTAMP,
               published_by_principal_id = %s,
               updated_by_principal_id = %s,
               updated_time = CURRENT_TIMESTAMP
         WHERE prompt_template_version_id = %s
        """,
        (context.principal_id, context.principal_id, version_id),
    )
    connection.execute(
        """
        INSERT INTO application.prompt_assignment (
            workflow_stage_id, prompt_template_version_id,
            prompt_assignment_scope, model_id, assigned_by_principal_id
        ) VALUES (%s, %s, 'model_default', %s, %s)
        """,
        (
            stage["workflow_stage_id"],
            version_id,
            context.model_id,
            context.principal_id,
        ),
    )


def _seed_mapping_context(
    postgres_database: DisposablePostgres,
) -> MappingRunContext:
    workflow = seed_workflow_context(postgres_database)
    suffix = uuid4().hex
    with postgres_database.connect_owner() as connection:
        physical = require_row(
            connection.execute(
                """
                SELECT object_record.connection_id,
                       object_record.source_tenant_id,
                       object_record.object_type_id,
                       connection.system_id
                  FROM core.object AS object_record
                  JOIN core.connection AS connection
                    ON connection.connection_id = object_record.connection_id
                 WHERE object_record.object_id = %s
                """,
                (workflow.selected_object_ids[0],),
            ).fetchone()
        )
        zone = connection.execute(
            "SELECT zone_id FROM reference.zone WHERE lower(btrim(zone_code)) = 'silver'"
        ).fetchone()
        if zone is None:
            zone = require_row(
                connection.execute(
                    """
                    INSERT INTO reference.zone (zone_code, zone_name)
                    VALUES ('silver', 'Silver')
                    RETURNING zone_id
                    """
                ).fetchone()
            )
        target_object_id = require_row(
            connection.execute(
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
                    f"silver_{suffix}",
                    f"mapping_target_{suffix}",
                    physical["object_type_id"],
                    zone["zone_id"],
                ),
            ).fetchone()
        )["object_id"]
        entity_id = require_row(
            connection.execute(
                """
                INSERT INTO workflow.logical_entity (
                    model_id, logical_entity_name, logical_entity_definition,
                    logical_entity_type, logical_entity_grain
                ) VALUES (%s, %s, 'Mapping Entity.', 'core', 'One row')
                RETURNING logical_entity_id
                """,
                (workflow.model_id, f"MappingEntity{suffix}"),
            ).fetchone()
        )["logical_entity_id"]
        binding_id = require_row(
            connection.execute(
                """
                INSERT INTO workflow.model_object_binding (
                    model_id, object_id, modeled_entity_type, logical_entity_id
                ) VALUES (%s, %s, 'logical_entity', %s)
                RETURNING model_object_binding_id
                """,
                (workflow.model_id, target_object_id, entity_id),
            ).fetchone()
        )["model_object_binding_id"]
        connection.execute(
            """
            INSERT INTO workflow.mapping_source_system_dependency (
                model_id, modeled_entity_type, source_system_id
            ) VALUES (%s, 'logical_entity', %s)
            """,
            (workflow.model_id, physical["system_id"]),
        )
        _seed_mapping_prompt(connection, workflow)

    return MappingRunContext(
        workflow=workflow,
        target_object_id=target_object_id,
        source_system_id=physical["system_id"],
        model_object_binding_id=binding_id,
    )


def _seed_output_template(
    connection: Connection[dict[str, Any]],
    context: MappingRunContext,
    target_type: str,
) -> tuple[int, str]:
    suffix = uuid4().hex
    digest = ("a" if target_type == "mapping_object" else "b") * 64
    template = require_row(
        connection.execute(
            """
            INSERT INTO application.output_template (
                output_template_code, output_template_name,
                output_template_target_type, output_template_schema_digest,
                created_by_principal_id, updated_by_principal_id
            ) VALUES (%s, %s, %s, %s, %s, %s)
            RETURNING output_template_id
            """,
            (
                f"mapping_{target_type}_{suffix}",
                f"Mapping {target_type} {suffix}",
                target_type,
                digest,
                context.workflow.principal_id,
                context.workflow.principal_id,
            ),
        ).fetchone()
    )
    connection.execute(
        """
        INSERT INTO application.output_template_field (
            output_template_id, output_template_field_name,
            output_template_field_description, output_template_field_data_type,
            output_template_field_order
        ) VALUES (%s, 'logic', 'Transformation logic.', 'string', 1)
        """,
        (template["output_template_id"],),
    )
    return template["output_template_id"], digest


def test_mapping_run_freezes_binding_route_and_target_pair(
    postgres_database: DisposablePostgres,
) -> None:
    context = _seed_mapping_context(postgres_database)
    with postgres_database.connect_owner() as connection:
        created = require_row(
            connection.execute(
                CREATE_MAPPING_RUN_SQL,
                _parameters(context, correlation_id=uuid4()),
            ).fetchone()
        )
        run = require_row(
            connection.execute(
                """
                SELECT modeled_entity_type, mapping_operation,
                       mapping_coverage_mode, mapping_route
                  FROM application.workflow_run
                 WHERE workflow_run_id = %s
                """,
                (created["workflow_run_id"],),
            ).fetchone()
        )
        pair = require_row(
            connection.execute(
                """
                SELECT object_id, source_system_id, selection_order
                  FROM application.workflow_run_mapping_target_selection
                 WHERE workflow_run_id = %s
                """,
                (created["workflow_run_id"],),
            ).fetchone()
        )

    assert run == {
        "modeled_entity_type": "logical_entity",
        "mapping_operation": "build",
        "mapping_coverage_mode": "selected_targets",
        "mapping_route": "logical_to_silver",
    }
    assert pair == {
        "object_id": context.target_object_id,
        "source_system_id": context.source_system_id,
        "selection_order": 1,
    }


def test_mapping_run_freezes_independent_advisory_templates(
    postgres_database: DisposablePostgres,
) -> None:
    context = _seed_mapping_context(postgres_database)
    with postgres_database.connect_owner() as connection:
        object_template = _seed_output_template(connection, context, "mapping_object")
        attribute_template = _seed_output_template(
            connection, context, "mapping_attribute"
        )
        created = require_row(
            connection.execute(
                CREATE_MAPPING_RUN_SQL,
                _parameters(
                    context,
                    correlation_id=uuid4(),
                    object_template_id=object_template[0],
                    attribute_template_id=attribute_template[0],
                ),
            ).fetchone()
        )
        frozen = require_row(
            connection.execute(
                """
                SELECT mapping_object_output_template_id,
                       mapping_object_output_template_schema_digest,
                       mapping_attribute_output_template_id,
                       mapping_attribute_output_template_schema_digest
                  FROM application.workflow_run
                 WHERE workflow_run_id = %s
                """,
                (created["workflow_run_id"],),
            ).fetchone()
        )

    assert frozen == {
        "mapping_object_output_template_id": object_template[0],
        "mapping_object_output_template_schema_digest": object_template[1],
        "mapping_attribute_output_template_id": attribute_template[0],
        "mapping_attribute_output_template_schema_digest": attribute_template[1],
    }


def test_mapping_run_replay_is_exact(
    postgres_database: DisposablePostgres,
) -> None:
    context = _seed_mapping_context(postgres_database)
    correlation_id = uuid4()
    with postgres_database.connect_owner() as connection:
        created = require_row(
            connection.execute(
                CREATE_MAPPING_RUN_SQL,
                _parameters(context, correlation_id=correlation_id),
            ).fetchone()
        )
        replayed = require_row(
            connection.execute(
                CREATE_MAPPING_RUN_SQL,
                _parameters(context, correlation_id=correlation_id),
            ).fetchone()
        )
    assert created["created"] is True
    assert replayed["created"] is False
    assert replayed["workflow_run_id"] == created["workflow_run_id"]

    with (
        postgres_database.connect_owner() as connection,
        pytest.raises(RaiseException, match="correlation conflict"),
    ):
        connection.execute(
            CREATE_MAPPING_RUN_SQL,
            _parameters(context, correlation_id=correlation_id, operation="extend"),
        )


@pytest.mark.parametrize("invalid_state", ("inactive", "locked", "wrong_zone"))
def test_mapping_run_rejects_invalid_binding_atomically(
    postgres_database: DisposablePostgres,
    invalid_state: str,
) -> None:
    context = _seed_mapping_context(postgres_database)
    with postgres_database.connect_owner() as connection:
        if invalid_state == "inactive":
            connection.execute(
                """
                UPDATE workflow.model_object_binding
                   SET model_object_binding_status = 'inactive'
                 WHERE model_object_binding_id = %s
                """,
                (context.model_object_binding_id,),
            )
            message = "unavailable or locked header"
        elif invalid_state == "locked":
            connection.execute(
                """
                UPDATE workflow.model_object_binding
                   SET model_object_binding_is_locked = TRUE
                 WHERE model_object_binding_id = %s
                """,
                (context.model_object_binding_id,),
            )
            message = "unavailable or locked header"
        else:
            gold_zone = connection.execute(
                "SELECT zone_id FROM reference.zone WHERE lower(btrim(zone_code)) = 'gold'"
            ).fetchone()
            if gold_zone is None:
                gold_zone = require_row(
                    connection.execute(
                        """
                        INSERT INTO reference.zone (zone_code, zone_name)
                        VALUES ('gold', 'Gold')
                        RETURNING zone_id
                        """
                    ).fetchone()
                )
            connection.execute(
                "UPDATE core.object SET zone_id = %s WHERE object_id = %s",
                (gold_zone["zone_id"], context.target_object_id),
            )
            message = "mixed or wrong-zone route"

    correlation_id = uuid4()
    with (
        postgres_database.connect_owner() as connection,
        pytest.raises(RaiseException, match=message),
    ):
        connection.execute(
            CREATE_MAPPING_RUN_SQL,
            _parameters(context, correlation_id=correlation_id),
        )
    with postgres_database.connect_owner() as connection:
        count = require_row(
            connection.execute(
                "SELECT count(*)::INTEGER AS count FROM application.workflow_run WHERE correlation_id = %s",
                (correlation_id,),
            ).fetchone()
        )["count"]
    assert count == 0
