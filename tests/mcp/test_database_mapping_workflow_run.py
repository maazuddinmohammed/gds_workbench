from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any
from uuid import UUID, uuid4

import pytest
from psycopg.errors import (
    CheckViolation,
    ForeignKeyViolation,
    ObjectNotInPrerequisiteState,
    RaiseException,
)

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


CREATE_MAPPING_RUN_SQL = """
    SELECT *
      FROM application.create_workflow_run(
          %s::UUID, %s::UUID, 'user'::VARCHAR,
          %s::BIGINT, %s::BIGINT, 'mapping'::VARCHAR,
          'one_shot'::VARCHAR,
          NULL::VARCHAR, NULL::VARCHAR, NULL::VARCHAR, NULL::VARCHAR,
          NULL::INTEGER, NULL::INTEGER,
          %s::BIGINT[], NULL::VARCHAR, NULL::VARCHAR, %s::UUID, '{}'::JSONB,
          %s::VARCHAR, %s::VARCHAR, %s::VARCHAR, %s::BIGINT,
          %s::BIGINT, %s::BIGINT
      )
"""

CREATE_PROFILING_RUN_WITH_MAPPING_TEMPLATE_SQL = """
    SELECT *
      FROM application.create_workflow_run(
          %s::UUID, %s::UUID, 'user'::VARCHAR,
          %s::BIGINT, %s::BIGINT, 'profiling'::VARCHAR,
          NULL::VARCHAR,
          NULL::VARCHAR, NULL::VARCHAR, NULL::VARCHAR, NULL::VARCHAR,
          NULL::INTEGER, NULL::INTEGER,
          %s::BIGINT[], NULL::VARCHAR, NULL::VARCHAR, %s::UUID, '{}'::JSONB,
          NULL::VARCHAR, NULL::VARCHAR, NULL::VARCHAR, NULL::BIGINT,
          %s::BIGINT, %s::BIGINT
      )
"""


def create_mapping_run_parameters(
    context: MappingRunContext,
    *,
    correlation_id: UUID,
    operation: str = "build",
    artifact_type: str = "sql_file",
    object_output_template_id: int | None = None,
    attribute_output_template_id: int | None = None,
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
        "selected_targets",
        artifact_type,
        context.source_system_id,
        object_output_template_id,
        attribute_output_template_id,
    )


def seed_mapping_output_template(
    connection: Connection[dict[str, Any]],
    context: MappingRunContext,
    *,
    target_type: str,
    is_active: bool = True,
    has_fields: bool = True,
) -> tuple[int, str]:
    suffix = uuid4().hex
    schema_digest = ("a" if target_type == "mapping_object" else "b") * 64
    template = require_row(
        connection.execute(
            """
            INSERT INTO application.output_template (
                output_template_code,
                output_template_name,
                output_template_target_type,
                output_template_schema_digest,
                created_by_principal_id,
                updated_by_principal_id,
                is_active
            ) VALUES (%s, %s, %s, %s, %s, %s, %s)
            RETURNING output_template_id, output_template_schema_digest
            """,
            (
                f"mapping_run_{target_type}_{suffix}",
                f"Mapping Run {target_type} {suffix}",
                target_type,
                schema_digest,
                context.workflow.principal_id,
                context.workflow.principal_id,
                is_active,
            ),
        ).fetchone()
    )
    template_id = template["output_template_id"]
    if has_fields:
        connection.execute(
            """
            INSERT INTO application.output_template_field (
                output_template_id,
                output_template_field_name,
                output_template_field_description,
                output_template_field_data_type,
                output_template_field_order
            ) VALUES (%s, 'logic', 'Mapping transformation logic.', 'string', 1)
            """,
            (template_id,),
        )
    return template_id, template["output_template_schema_digest"]


def seed_mapping_run_context(
    postgres_database: DisposablePostgres,
) -> MappingRunContext:
    workflow = seed_workflow_context(postgres_database)
    suffix = uuid4().hex
    with postgres_database.connect_owner() as connection:
        physical = require_row(
            connection.execute(
                """
                SELECT object.connection_id,
                       object.object_type_id,
                       connection.system_id
                  FROM core.object AS object
                  JOIN core.connection AS connection
                    ON connection.connection_id = object.connection_id
                 WHERE object.object_id = %s
                """,
                (workflow.selected_object_ids[0],),
            ).fetchone()
        )
        zone = connection.execute(
            """
            SELECT zone_id
              FROM reference.zone
             WHERE lower(btrim(zone_code)) = 'silver'
               AND is_active
            """
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
                    connection_id,
                    object_schema,
                    object_name,
                    object_type_id,
                    zone_id
                ) VALUES (%s, %s, %s, %s, %s)
                RETURNING object_id
                """,
                (
                    physical["connection_id"],
                    f"silver_{suffix}",
                    f"mapping_target_{suffix}",
                    physical["object_type_id"],
                    zone["zone_id"],
                ),
            ).fetchone()
        )["object_id"]
        connection.execute(
            """
            INSERT INTO model.model_scope (model_id, object_id)
            VALUES (%s, %s)
            """,
            (workflow.model_id, target_object_id),
        )
        logical_entity_id = require_row(
            connection.execute(
                """
                INSERT INTO workflow.logical_entity (
                    model_id,
                    logical_entity_name,
                    logical_entity_definition,
                    logical_entity_type,
                    logical_entity_grain
                ) VALUES (%s, %s, 'Mapping test Entity', 'core', 'One row')
                RETURNING logical_entity_id
                """,
                (workflow.model_id, f"Mapping Entity {suffix}"),
            ).fetchone()
        )["logical_entity_id"]
        connection.execute(
            """
            INSERT INTO workflow.mapping_source_system_dependency (
                model_id,
                modeled_entity_type,
                source_system_id
            ) VALUES (%s, 'logical_entity', %s)
            """,
            (workflow.model_id, physical["system_id"]),
        )
        connection.execute(
            """
            INSERT INTO workflow.mapping_object (
                model_id,
                object_id,
                source_system_id,
                modeled_entity_type,
                logical_entity_id
            ) VALUES (%s, %s, %s, 'logical_entity', %s)
            """,
            (
                workflow.model_id,
                target_object_id,
                physical["system_id"],
                logical_entity_id,
            ),
        )

        stage = connection.execute(
            """
            SELECT workflow_stage_id
              FROM application.workflow_stage
             WHERE model_workflow = 'mapping'
               AND workflow_execution_mode = 'one_shot'
               AND workflow_stage_is_agentic
               AND is_active
            """
        ).fetchone()
        if stage is None:
            stage = require_row(
                connection.execute(
                    """
                    INSERT INTO application.workflow_stage (
                        model_workflow,
                        workflow_execution_mode,
                        workflow_stage_code,
                        workflow_stage_name,
                        workflow_stage_order,
                        workflow_stage_is_agentic
                    ) VALUES (
                        'mapping', 'one_shot', %s,
                        'Mapping Authoring', 1000, TRUE
                    )
                    RETURNING workflow_stage_id
                    """,
                    (f"mapping_authoring_{suffix}",),
                ).fetchone()
            )
        digest = require_row(
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
                                       'tool_instruction_prompt_template',
                                           NULL::TEXT
                                   )::TEXT,
                                   'UTF8'
                               )
                           ),
                           'hex'
                       ) AS digest
                """
            ).fetchone()
        )["digest"]
        prompt_template_id = require_row(
            connection.execute(
                """
                INSERT INTO application.prompt_template (
                    workflow_stage_id,
                    prompt_template_ownership_scope,
                    owner_tenant_id,
                    prompt_template_code,
                    prompt_template_name,
                    created_by_principal_id,
                    updated_by_principal_id
                ) VALUES (%s, 'tenant', %s, %s, %s, %s, %s)
                RETURNING prompt_template_id
                """,
                (
                    stage["workflow_stage_id"],
                    workflow.tenant_id,
                    f"mapping_prompt_{suffix}",
                    f"Mapping Prompt {suffix}",
                    workflow.principal_id,
                    workflow.principal_id,
                ),
            ).fetchone()
        )["prompt_template_id"]
        prompt_version_id = require_row(
            connection.execute(
                """
                INSERT INTO application.prompt_template_version (
                    prompt_template_id,
                    workflow_stage_id,
                    prompt_template_version_number,
                    system_prompt_template,
                    instruction_prompt_template,
                    prompt_template_digest,
                    prompt_template_version_status,
                    published_time,
                    published_by_principal_id,
                    created_by_principal_id,
                    updated_by_principal_id
                ) VALUES (
                    %s, %s, 1, '{{ stage_context }}', '{{ stage_context }}',
                    %s, 'published', CURRENT_TIMESTAMP, %s, %s, %s
                )
                RETURNING prompt_template_version_id
                """,
                (
                    prompt_template_id,
                    stage["workflow_stage_id"],
                    digest,
                    workflow.principal_id,
                    workflow.principal_id,
                    workflow.principal_id,
                ),
            ).fetchone()
        )["prompt_template_version_id"]
        connection.execute(
            """
            INSERT INTO application.prompt_assignment (
                workflow_stage_id,
                prompt_template_version_id,
                prompt_assignment_scope,
                model_id,
                assigned_by_principal_id
            ) VALUES (%s, %s, 'model_default', %s, %s)
            """,
            (
                stage["workflow_stage_id"],
                prompt_version_id,
                workflow.model_id,
                workflow.principal_id,
            ),
        )

    return MappingRunContext(
        workflow=workflow,
        target_object_id=target_object_id,
        source_system_id=physical["system_id"],
    )


def test_mapping_run_freezes_one_inferred_logical_to_silver_pair(
    postgres_database: DisposablePostgres,
) -> None:
    context = seed_mapping_run_context(postgres_database)

    with postgres_database.connect_owner() as connection:
        created = require_row(
            connection.execute(
                CREATE_MAPPING_RUN_SQL,
                create_mapping_run_parameters(context, correlation_id=uuid4()),
            ).fetchone()
        )
        run = require_row(
            connection.execute(
                """
                SELECT modeled_entity_type,
                       mapping_operation,
                       mapping_coverage_mode,
                       mapping_artifact_type,
                       mapping_route,
                       mapping_profile_key,
                       mapping_profile_version,
                       mapping_profile_schema_digest,
                       mapping_object_output_template_id,
                       mapping_object_output_template_schema_digest,
                       mapping_attribute_output_template_id,
                       mapping_attribute_output_template_schema_digest
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

    assert run["modeled_entity_type"] == "logical_entity"
    assert run["mapping_operation"] == "build"
    assert run["mapping_coverage_mode"] == "selected_targets"
    assert run["mapping_artifact_type"] == "sql_file"
    assert run["mapping_route"] == "logical_to_silver"
    assert run["mapping_profile_key"] == "mapping.standard"
    assert run["mapping_profile_version"] == "1.0.0"
    assert run["mapping_profile_schema_digest"] == (
        "b3b324170019b51d2b812c3735fa6215e463209ea39e4099b44c786b956da8fa"
    )
    assert run["mapping_object_output_template_id"] is None
    assert run["mapping_object_output_template_schema_digest"] is None
    assert run["mapping_attribute_output_template_id"] is None
    assert run["mapping_attribute_output_template_schema_digest"] is None
    assert pair == {
        "object_id": context.target_object_id,
        "source_system_id": context.source_system_id,
        "selection_order": 1,
    }


@pytest.mark.parametrize(
    ("select_object", "select_attribute"),
    ((True, False), (False, True), (True, True)),
)
def test_mapping_run_freezes_independent_output_template_selections(
    postgres_database: DisposablePostgres,
    select_object: bool,
    select_attribute: bool,
) -> None:
    context = seed_mapping_run_context(postgres_database)

    with postgres_database.connect_owner() as connection:
        object_template_id, object_schema_digest = seed_mapping_output_template(
            connection,
            context,
            target_type="mapping_object",
        )
        attribute_template_id, attribute_schema_digest = seed_mapping_output_template(
            connection,
            context,
            target_type="mapping_attribute",
        )
        created = require_row(
            connection.execute(
                CREATE_MAPPING_RUN_SQL,
                create_mapping_run_parameters(
                    context,
                    correlation_id=uuid4(),
                    object_output_template_id=(
                        object_template_id if select_object else None
                    ),
                    attribute_output_template_id=(
                        attribute_template_id if select_attribute else None
                    ),
                ),
            ).fetchone()
        )
        run = require_row(
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

    assert run == {
        "mapping_object_output_template_id": (
            object_template_id if select_object else None
        ),
        "mapping_object_output_template_schema_digest": (
            object_schema_digest if select_object else None
        ),
        "mapping_attribute_output_template_id": (
            attribute_template_id if select_attribute else None
        ),
        "mapping_attribute_output_template_schema_digest": (
            attribute_schema_digest if select_attribute else None
        ),
    }


@pytest.mark.parametrize(
    ("invalid_pair", "expected_error"),
    (
        ("missing_digest", CheckViolation),
        ("wrong_digest", ForeignKeyViolation),
    ),
)
def test_mapping_run_template_id_digest_pair_is_authoritative(
    postgres_database: DisposablePostgres,
    invalid_pair: str,
    expected_error: type[Exception],
) -> None:
    context = seed_mapping_run_context(postgres_database)
    invalid_correlation_id = uuid4()
    with postgres_database.connect_owner() as connection:
        template_id, _ = seed_mapping_output_template(
            connection,
            context,
            target_type="mapping_object",
        )
        created = require_row(
            connection.execute(
                CREATE_MAPPING_RUN_SQL,
                create_mapping_run_parameters(
                    context,
                    correlation_id=uuid4(),
                    object_output_template_id=template_id,
                ),
            ).fetchone()
        )

    invalid_digest = None if invalid_pair == "missing_digest" else "f" * 64
    with (
        postgres_database.connect_owner() as connection,
        pytest.raises(expected_error),
    ):
        connection.execute(
            """
            INSERT INTO application.workflow_run (
                model_id,
                model_revision,
                model_workflow,
                workflow_execution_mode,
                actor_principal_id,
                actor_entra_principal_identity_id,
                agent_sdk_code,
                agent_provider_code,
                agent_model_code,
                reasoning_effort_code,
                max_turns,
                validation_retry_count,
                modeled_entity_type,
                requested_batch_id,
                mapping_operation,
                mapping_coverage_mode,
                mapping_artifact_type,
                mapping_route,
                mapping_profile_key,
                mapping_profile_version,
                mapping_profile_schema_digest,
                mapping_object_output_template_id,
                mapping_object_output_template_schema_digest,
                mapping_attribute_output_template_id,
                mapping_attribute_output_template_schema_digest,
                selected_scope_digest,
                selected_scope_count,
                correlation_id,
                workflow_run_request_digest
            )
            SELECT model_id,
                   model_revision,
                   model_workflow,
                   workflow_execution_mode,
                   actor_principal_id,
                   actor_entra_principal_identity_id,
                   agent_sdk_code,
                   agent_provider_code,
                   agent_model_code,
                   reasoning_effort_code,
                   max_turns,
                   validation_retry_count,
                   modeled_entity_type,
                   requested_batch_id,
                   mapping_operation,
                   mapping_coverage_mode,
                   mapping_artifact_type,
                   mapping_route,
                   mapping_profile_key,
                   mapping_profile_version,
                   mapping_profile_schema_digest,
                   mapping_object_output_template_id,
                   %s,
                   mapping_attribute_output_template_id,
                   mapping_attribute_output_template_schema_digest,
                   selected_scope_digest,
                   selected_scope_count,
                   %s,
                   workflow_run_request_digest
              FROM application.workflow_run
             WHERE workflow_run_id = %s
            """,
            (
                invalid_digest,
                invalid_correlation_id,
                created["workflow_run_id"],
            ),
        )

    with postgres_database.connect_owner() as connection:
        run_count = require_row(
            connection.execute(
                """
                SELECT count(*) AS run_count
                  FROM application.workflow_run
                 WHERE correlation_id = %s
                """,
                (invalid_correlation_id,),
            ).fetchone()
        )["run_count"]

    assert run_count == 0


def test_mapping_run_output_template_selection_is_immutable(
    postgres_database: DisposablePostgres,
) -> None:
    context = seed_mapping_run_context(postgres_database)
    with postgres_database.connect_owner() as connection:
        template_id, schema_digest = seed_mapping_output_template(
            connection,
            context,
            target_type="mapping_object",
        )
        created = require_row(
            connection.execute(
                CREATE_MAPPING_RUN_SQL,
                create_mapping_run_parameters(
                    context,
                    correlation_id=uuid4(),
                    object_output_template_id=template_id,
                ),
            ).fetchone()
        )

    with (
        postgres_database.connect_owner() as connection,
        pytest.raises(
            ObjectNotInPrerequisiteState,
            match="workflow run identity is immutable",
        ),
    ):
        connection.execute(
            """
            UPDATE application.workflow_run
               SET mapping_object_output_template_id = NULL,
                   mapping_object_output_template_schema_digest = NULL
             WHERE workflow_run_id = %s
            """,
            (created["workflow_run_id"],),
        )

    with postgres_database.connect_owner() as connection:
        stored = require_row(
            connection.execute(
                """
                SELECT mapping_object_output_template_id,
                       mapping_object_output_template_schema_digest
                  FROM application.workflow_run
                 WHERE workflow_run_id = %s
                """,
                (created["workflow_run_id"],),
            ).fetchone()
        )

    assert stored == {
        "mapping_object_output_template_id": template_id,
        "mapping_object_output_template_schema_digest": schema_digest,
    }


@pytest.mark.parametrize("selection_level", ("object", "attribute"))
@pytest.mark.parametrize(
    "invalid_case",
    ("missing", "inactive", "no_fields", "wrong_type"),
)
def test_mapping_run_rejects_unavailable_output_template_atomically(
    postgres_database: DisposablePostgres,
    selection_level: str,
    invalid_case: str,
) -> None:
    context = seed_mapping_run_context(postgres_database)
    correlation_id = uuid4()
    expected_target_type = f"mapping_{selection_level}"

    if invalid_case == "missing":
        template_id = 9_000_000_000
    else:
        actual_target_type = expected_target_type
        if invalid_case == "wrong_type":
            actual_target_type = (
                "mapping_attribute" if selection_level == "object" else "mapping_object"
            )
        with postgres_database.connect_owner() as connection:
            template_id, _ = seed_mapping_output_template(
                connection,
                context,
                target_type=actual_target_type,
                is_active=invalid_case != "inactive",
                has_fields=invalid_case != "no_fields",
            )

    with (
        postgres_database.connect_owner() as connection,
        pytest.raises(
            RaiseException,
            match=(
                f"Selected Mapping {selection_level.title()} output template is unavailable"
            ),
        ),
    ):
        connection.execute(
            CREATE_MAPPING_RUN_SQL,
            create_mapping_run_parameters(
                context,
                correlation_id=correlation_id,
                object_output_template_id=(
                    template_id if selection_level == "object" else None
                ),
                attribute_output_template_id=(
                    template_id if selection_level == "attribute" else None
                ),
            ),
        )

    with postgres_database.connect_owner() as connection:
        persisted = require_row(
            connection.execute(
                """
                SELECT count(*) AS run_count,
                       count(selection.workflow_run_mapping_target_selection_id)
                           AS selection_count
                  FROM application.workflow_run AS run
                  LEFT JOIN application.workflow_run_mapping_target_selection
                            AS selection
                    ON selection.workflow_run_id = run.workflow_run_id
                 WHERE run.correlation_id = %s
                """,
                (correlation_id,),
            ).fetchone()
        )

    assert persisted == {"run_count": 0, "selection_count": 0}


@pytest.mark.parametrize("selection_level", ("object", "attribute"))
def test_non_mapping_run_rejects_output_template_selection_atomically(
    postgres_database: DisposablePostgres,
    selection_level: str,
) -> None:
    context = seed_mapping_run_context(postgres_database)
    correlation_id = uuid4()
    with postgres_database.connect_owner() as connection:
        template_id, _ = seed_mapping_output_template(
            connection,
            context,
            target_type=f"mapping_{selection_level}",
        )

    workflow = context.workflow
    parameters = (
        workflow.entra_tenant_id,
        workflow.entra_object_id,
        workflow.model_id,
        workflow.model_revision,
        [workflow.selected_object_ids[0]],
        correlation_id,
        template_id if selection_level == "object" else None,
        template_id if selection_level == "attribute" else None,
    )
    with (
        postgres_database.connect_owner() as connection,
        pytest.raises(
            RaiseException,
            match="Mapping inputs are unavailable for this Workflow Run",
        ),
    ):
        connection.execute(
            CREATE_PROFILING_RUN_WITH_MAPPING_TEMPLATE_SQL,
            parameters,
        )

    with postgres_database.connect_owner() as connection:
        persisted = require_row(
            connection.execute(
                """
                SELECT count(*) AS run_count,
                       count(selection.workflow_run_object_selection_id)
                           AS selection_count
                  FROM application.workflow_run AS run
                  LEFT JOIN application.workflow_run_object_selection AS selection
                    ON selection.workflow_run_id = run.workflow_run_id
                 WHERE run.correlation_id = %s
                """,
                (correlation_id,),
            ).fetchone()
        )

    assert persisted == {"run_count": 0, "selection_count": 0}


def test_mapping_run_correlation_replay_is_exact(
    postgres_database: DisposablePostgres,
) -> None:
    context = seed_mapping_run_context(postgres_database)
    correlation_id = uuid4()

    with postgres_database.connect_owner() as connection:
        created = require_row(
            connection.execute(
                CREATE_MAPPING_RUN_SQL,
                create_mapping_run_parameters(context, correlation_id=correlation_id),
            ).fetchone()
        )
        replayed = require_row(
            connection.execute(
                CREATE_MAPPING_RUN_SQL,
                create_mapping_run_parameters(context, correlation_id=correlation_id),
            ).fetchone()
        )
        pair_count = require_row(
            connection.execute(
                """
                SELECT count(*) AS pair_count
                  FROM application.workflow_run_mapping_target_selection
                 WHERE workflow_run_id = %s
                """,
                (created["workflow_run_id"],),
            ).fetchone()
        )["pair_count"]

    with (
        postgres_database.connect_owner() as connection,
        pytest.raises(RaiseException, match="correlation conflict"),
    ):
        connection.execute(
            CREATE_MAPPING_RUN_SQL,
            create_mapping_run_parameters(
                context,
                correlation_id=correlation_id,
                operation="extend",
            ),
        )

    assert created["created"] is True
    assert replayed["created"] is False
    assert replayed["workflow_run_id"] == created["workflow_run_id"]
    assert pair_count == 1


@pytest.mark.parametrize("changed_selection", ("object", "attribute"))
def test_mapping_run_correlation_replay_freezes_output_template_choices(
    postgres_database: DisposablePostgres,
    changed_selection: str,
) -> None:
    context = seed_mapping_run_context(postgres_database)
    correlation_id = uuid4()
    with postgres_database.connect_owner() as connection:
        object_template_id, _ = seed_mapping_output_template(
            connection,
            context,
            target_type="mapping_object",
        )
        replacement_object_template_id, _ = seed_mapping_output_template(
            connection,
            context,
            target_type="mapping_object",
        )
        attribute_template_id, _ = seed_mapping_output_template(
            connection,
            context,
            target_type="mapping_attribute",
        )
        replacement_attribute_template_id, _ = seed_mapping_output_template(
            connection,
            context,
            target_type="mapping_attribute",
        )

        parameters = create_mapping_run_parameters(
            context,
            correlation_id=correlation_id,
            object_output_template_id=object_template_id,
            attribute_output_template_id=attribute_template_id,
        )
        created = require_row(
            connection.execute(CREATE_MAPPING_RUN_SQL, parameters).fetchone()
        )
        replayed = require_row(
            connection.execute(CREATE_MAPPING_RUN_SQL, parameters).fetchone()
        )

    changed_parameters = create_mapping_run_parameters(
        context,
        correlation_id=correlation_id,
        object_output_template_id=(
            replacement_object_template_id
            if changed_selection == "object"
            else object_template_id
        ),
        attribute_output_template_id=(
            replacement_attribute_template_id
            if changed_selection == "attribute"
            else attribute_template_id
        ),
    )
    with (
        postgres_database.connect_owner() as connection,
        pytest.raises(RaiseException, match="correlation conflict"),
    ):
        connection.execute(CREATE_MAPPING_RUN_SQL, changed_parameters)

    assert created["created"] is True
    assert replayed["created"] is False
    assert replayed["workflow_run_id"] == created["workflow_run_id"]


@pytest.mark.parametrize(
    ("operation", "rows_are_locked"),
    (("build", True), ("extend", True), ("build", False), ("extend", False)),
)
def test_mapping_run_allows_complete_package_when_rows_are_preserved(
    postgres_database: DisposablePostgres,
    operation: str,
    rows_are_locked: bool,
) -> None:
    context = seed_mapping_run_context(postgres_database)

    with postgres_database.connect_owner() as connection:
        header = require_row(
            connection.execute(
                """
                UPDATE workflow.mapping_object
                   SET artifact_type = 'python_file',
                       artifact_generation_instructions =
                           'Generate Databricks SQL.',
                       mapping_profile_key = 'mapping.legacy',
                       mapping_profile_version = '0.9.0',
                       mapping_profile_schema_digest =
                           repeat('c', 64),
                       mapping_package_document =
                           '{"schema_version":"1.0"}'::JSONB,
                       mapping_package_digest = repeat('a', 64),
                       object_mapping_transformation_document =
                           '{"schema_version":"1.0","transformation_kind":"direct"}'::JSONB,
                       object_mapping_is_locked = %s
                 WHERE model_id = %s
                   AND object_id = %s
                   AND source_system_id = %s
                RETURNING mapping_object_id, logical_entity_id
                """,
                (
                    rows_are_locked,
                    context.workflow.model_id,
                    context.target_object_id,
                    context.source_system_id,
                ),
            ).fetchone()
        )
        connection.execute(
            """
            UPDATE workflow.mapping_source_system_dependency
               SET mapping_source_system_dependency_is_locked = %s
             WHERE model_id = %s
               AND modeled_entity_type = 'logical_entity'
               AND source_system_id = %s
            """,
            (
                rows_are_locked,
                context.workflow.model_id,
                context.source_system_id,
            ),
        )
        target_attribute_id = require_row(
            connection.execute(
                """
                INSERT INTO core.attribute (
                    object_id,
                    attribute_name,
                    attribute_ordinal_position,
                    attribute_data_type,
                    attribute_nullability
                ) VALUES (%s, 'customer_id', 1, 'bigint', FALSE)
                RETURNING attribute_id
                """,
                (context.target_object_id,),
            ).fetchone()
        )["attribute_id"]
        logical_attribute_id = require_row(
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
                ) VALUES (
                    %s, %s, 'Customer ID', 'Customer identifier.',
                    'bigint', FALSE, 1
                )
                RETURNING logical_attribute_id
                """,
                (context.workflow.model_id, header["logical_entity_id"]),
            ).fetchone()
        )["logical_attribute_id"]
        connection.execute(
            """
            INSERT INTO workflow.mapping_attribute (
                model_id,
                object_id,
                attribute_id,
                mapping_object_id,
                modeled_entity_type,
                logical_attribute_id,
                attribute_mapping_transformation_document,
                attribute_mapping_is_locked
            ) VALUES (
                %s, %s, %s, %s, 'logical_entity', %s,
                '{"schema_version":"1.0","transformation_kind":"direct"}'::JSONB,
                %s
            )
            """,
            (
                context.workflow.model_id,
                context.target_object_id,
                target_attribute_id,
                header["mapping_object_id"],
                logical_attribute_id,
                rows_are_locked,
            ),
        )

        created = require_row(
            connection.execute(
                CREATE_MAPPING_RUN_SQL,
                create_mapping_run_parameters(
                    context,
                    correlation_id=uuid4(),
                    operation=operation,
                ),
            ).fetchone()
        )
        run = require_row(
            connection.execute(
                """
                SELECT mapping_artifact_type,
                       mapping_profile_key,
                       mapping_profile_version,
                       mapping_profile_schema_digest
                  FROM application.workflow_run
                 WHERE workflow_run_id = %s
                """,
                (created["workflow_run_id"],),
            ).fetchone()
        )

    assert created["created"] is True
    assert run == {
        "mapping_artifact_type": "sql_file",
        "mapping_profile_key": "mapping.standard",
        "mapping_profile_version": "1.0.0",
        "mapping_profile_schema_digest": (
            "b3b324170019b51d2b812c3735fa6215e463209ea39e4099b44c786b956da8fa"
        ),
    }


@pytest.mark.parametrize(
    ("header_is_locked", "child_is_locked"),
    ((False, True), (True, False)),
)
def test_mapping_run_rejects_incomplete_child_under_a_lock_atomically(
    postgres_database: DisposablePostgres,
    header_is_locked: bool,
    child_is_locked: bool,
) -> None:
    context = seed_mapping_run_context(postgres_database)
    correlation_id = uuid4()

    with postgres_database.connect_owner() as connection:
        header = require_row(
            connection.execute(
                """
                UPDATE workflow.mapping_object
                   SET artifact_type = 'sql_file',
                       artifact_generation_instructions =
                           'Generate Databricks SQL.',
                       mapping_profile_key = 'mapping.standard',
                       mapping_profile_version = '1.0.0',
                       mapping_profile_schema_digest =
                           'b3b324170019b51d2b812c3735fa6215e463209ea39e4099b44c786b956da8fa',
                       mapping_package_document =
                           '{"schema_version":"1.0"}'::JSONB,
                       mapping_package_digest = repeat('b', 64),
                       object_mapping_transformation_document =
                           '{"schema_version":"1.0","transformation_kind":"direct"}'::JSONB,
                       object_mapping_is_locked = %s
                 WHERE model_id = %s
                   AND object_id = %s
                   AND source_system_id = %s
                RETURNING mapping_object_id, logical_entity_id
                """,
                (
                    header_is_locked,
                    context.workflow.model_id,
                    context.target_object_id,
                    context.source_system_id,
                ),
            ).fetchone()
        )
        target_attribute_id = require_row(
            connection.execute(
                """
                INSERT INTO core.attribute (
                    object_id,
                    attribute_name,
                    attribute_ordinal_position,
                    attribute_data_type,
                    attribute_nullability
                ) VALUES (%s, 'customer_id', 1, 'bigint', FALSE)
                RETURNING attribute_id
                """,
                (context.target_object_id,),
            ).fetchone()
        )["attribute_id"]
        logical_attribute_id = require_row(
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
                ) VALUES (
                    %s, %s, 'Customer ID', 'Customer identifier.',
                    'bigint', FALSE, 1
                )
                RETURNING logical_attribute_id
                """,
                (context.workflow.model_id, header["logical_entity_id"]),
            ).fetchone()
        )["logical_attribute_id"]
        connection.execute(
            """
            INSERT INTO workflow.mapping_attribute (
                model_id,
                object_id,
                attribute_id,
                mapping_object_id,
                modeled_entity_type,
                logical_attribute_id,
                attribute_mapping_is_locked
            ) VALUES (%s, %s, %s, %s, 'logical_entity', %s, %s)
            """,
            (
                context.workflow.model_id,
                context.target_object_id,
                target_attribute_id,
                header["mapping_object_id"],
                logical_attribute_id,
                child_is_locked,
            ),
        )

    with (
        postgres_database.connect_owner() as connection,
        pytest.raises(RaiseException, match="unavailable or locked header"),
    ):
        connection.execute(
            CREATE_MAPPING_RUN_SQL,
            create_mapping_run_parameters(context, correlation_id=correlation_id),
        )

    with postgres_database.connect_owner() as connection:
        persisted = require_row(
            connection.execute(
                """
                SELECT count(*) AS run_count,
                       count(selection.workflow_run_mapping_target_selection_id)
                           AS selection_count
                  FROM application.workflow_run AS run
                  LEFT JOIN application.workflow_run_mapping_target_selection
                            AS selection
                    ON selection.workflow_run_id = run.workflow_run_id
                 WHERE run.correlation_id = %s
                """,
                (correlation_id,),
            ).fetchone()
        )

    assert persisted == {"run_count": 0, "selection_count": 0}


@pytest.mark.parametrize(
    ("invalid_case", "expected_error"),
    (
        ("missing", "no preregistered header"),
        ("inactive", "unavailable or locked header"),
        ("locked", "unavailable or locked header"),
        ("unavailable_entity", "unavailable or locked header"),
        ("mixed", "mixed modeled layers"),
        ("wrong_zone", "mixed or wrong-zone route"),
    ),
)
def test_mapping_run_rejects_invalid_preregistered_target_atomically(
    postgres_database: DisposablePostgres,
    invalid_case: str,
    expected_error: str,
) -> None:
    context = seed_mapping_run_context(postgres_database)
    correlation_id = uuid4()

    with postgres_database.connect_owner() as connection:
        if invalid_case == "inactive":
            connection.execute(
                """
                UPDATE workflow.mapping_object
                   SET object_mapping_status = 'inactive'
                 WHERE model_id = %s
                   AND object_id = %s
                   AND source_system_id = %s
                """,
                (
                    context.workflow.model_id,
                    context.target_object_id,
                    context.source_system_id,
                ),
            )
        elif invalid_case == "locked":
            connection.execute(
                """
                UPDATE workflow.mapping_object
                   SET object_mapping_is_locked = TRUE
                 WHERE model_id = %s
                   AND object_id = %s
                   AND source_system_id = %s
                """,
                (
                    context.workflow.model_id,
                    context.target_object_id,
                    context.source_system_id,
                ),
            )
        elif invalid_case == "unavailable_entity":
            connection.execute(
                """
                UPDATE workflow.logical_entity AS entity
                   SET logical_entity_status = 'inactive'
                  FROM workflow.mapping_object AS mapping
                 WHERE mapping.model_id = %s
                   AND mapping.object_id = %s
                   AND mapping.source_system_id = %s
                   AND mapping.logical_entity_id = entity.logical_entity_id
                   AND mapping.model_id = entity.model_id
                """,
                (
                    context.workflow.model_id,
                    context.target_object_id,
                    context.source_system_id,
                ),
            )
        elif invalid_case == "mixed":
            dimensional_entity_id = require_row(
                connection.execute(
                    """
                    INSERT INTO workflow.dimensional_entity (
                        model_id,
                        dimensional_entity_name,
                        dimensional_entity_definition,
                        dimensional_entity_type
                    ) VALUES (%s, %s, 'Mixed Mapping test', 'dimension')
                    RETURNING dimensional_entity_id
                    """,
                    (
                        context.workflow.model_id,
                        f"Mixed Dimension {uuid4().hex}",
                    ),
                ).fetchone()
            )["dimensional_entity_id"]
            connection.execute(
                """
                INSERT INTO workflow.mapping_source_system_dependency (
                    model_id,
                    modeled_entity_type,
                    source_system_id
                ) VALUES (%s, 'dimensional_entity', %s)
                """,
                (context.workflow.model_id, context.source_system_id),
            )
            connection.execute(
                """
                INSERT INTO workflow.mapping_object (
                    model_id,
                    object_id,
                    source_system_id,
                    modeled_entity_type,
                    dimensional_entity_id
                ) VALUES (%s, %s, %s, 'dimensional_entity', %s)
                """,
                (
                    context.workflow.model_id,
                    context.target_object_id,
                    context.source_system_id,
                    dimensional_entity_id,
                ),
            )
        elif invalid_case == "wrong_zone":
            connection.execute(
                """
                UPDATE core.object
                   SET zone_id = (
                       SELECT zone_id
                         FROM reference.zone
                        WHERE lower(btrim(zone_code)) = 'bronze'
                          AND is_active
                   )
                 WHERE object_id = %s
                """,
                (context.target_object_id,),
            )

    attempted_context = context
    if invalid_case == "missing":
        attempted_context = MappingRunContext(
            workflow=context.workflow,
            target_object_id=context.target_object_id,
            source_system_id=context.source_system_id + 1_000_000,
        )

    with (
        postgres_database.connect_owner() as connection,
        pytest.raises(RaiseException, match=expected_error),
    ):
        connection.execute(
            CREATE_MAPPING_RUN_SQL,
            create_mapping_run_parameters(
                attempted_context,
                correlation_id=correlation_id,
            ),
        )

    with postgres_database.connect_owner() as connection:
        persisted = require_row(
            connection.execute(
                """
                SELECT count(*) AS run_count,
                       count(selection.workflow_run_mapping_target_selection_id)
                           AS selection_count
                  FROM application.workflow_run AS run
                  LEFT JOIN application.workflow_run_mapping_target_selection
                            AS selection
                    ON selection.workflow_run_id = run.workflow_run_id
                 WHERE run.correlation_id = %s
                """,
                (correlation_id,),
            ).fetchone()
        )

    assert persisted == {"run_count": 0, "selection_count": 0}
