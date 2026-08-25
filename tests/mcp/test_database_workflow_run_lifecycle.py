from __future__ import annotations

from dataclasses import dataclass, replace
from hashlib import sha256
from typing import TYPE_CHECKING
from uuid import UUID, uuid4

import pytest
from psycopg.errors import CheckViolation, RaiseException

from tests.mcp.database_test_support import require_row

if TYPE_CHECKING:
    from conftest import DisposablePostgres


@dataclass(frozen=True, slots=True)
class WorkflowContext:
    entra_tenant_id: UUID
    entra_object_id: UUID
    tenant_id: int
    model_id: int
    model_revision: int
    principal_id: int
    prompt_snapshots: tuple[tuple[int, int], ...]
    selected_object_ids: tuple[int, ...]


CREATE_WORKFLOW_RUN_SQL = """
    SELECT *
      FROM application.create_workflow_run(
          %s::UUID,
          %s::UUID,
          'user'::VARCHAR,
          %s::BIGINT,
          %s::BIGINT,
          %s::VARCHAR,
          %s::VARCHAR,
          %s::VARCHAR,
          %s::VARCHAR,
          %s::VARCHAR,
          %s::VARCHAR,
          %s::INTEGER,
          %s::INTEGER,
          %s::BIGINT[],
          %s::VARCHAR,
          %s::VARCHAR,
          %s::UUID,
          %s::JSONB
      )
"""

CREATE_CODE_GENERATION_WORKFLOW_RUN_SQL = """
    SELECT *
      FROM application.create_workflow_run(
          %s::UUID,
          %s::UUID,
          'user'::VARCHAR,
          %s::BIGINT,
          %s::BIGINT,
          'code_generation'::VARCHAR,
          NULL::VARCHAR,
          NULL::VARCHAR,
          NULL::VARCHAR,
          NULL::VARCHAR,
          NULL::VARCHAR,
          NULL::INTEGER,
          NULL::INTEGER,
          %s::BIGINT[],
          'logical_entity'::VARCHAR,
          NULL::VARCHAR,
          %s::UUID,
          '{}'::JSONB,
          NULL::VARCHAR,
          NULL::VARCHAR,
          NULL::VARCHAR,
          NULL::BIGINT,
          NULL::BIGINT,
          NULL::BIGINT,
          %s::VARCHAR,
          %s::BIGINT
      )
"""


def seed_workflow_context(
    postgres_database: DisposablePostgres,
) -> WorkflowContext:
    suffix = uuid4().hex
    entra_tenant_id = uuid4()
    entra_object_id = uuid4()

    with postgres_database.connect_owner() as connection:
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
        project_id = require_row(
            connection.execute(
                """
            INSERT INTO core.project (project_code, project_name)
            VALUES (%s, %s)
            RETURNING project_id
            """,
                (f"workflow_project_{suffix}", f"Workflow Project {suffix}"),
            ).fetchone()
        )["project_id"]
        tenant_id = require_row(
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
                    f"workflow_tenant_{suffix}",
                    f"Workflow Tenant {suffix}",
                    f"workflow_catalog_{suffix}",
                    f"workflow_admin_{suffix}",
                ),
            ).fetchone()
        )["tenant_id"]
        model_row = require_row(
            connection.execute(
                """
            INSERT INTO model.model (
                tenant_id,
                model_name,
                default_agent_sdk_code,
                default_agent_provider_code,
                default_agent_model_code,
                default_reasoning_effort_code,
                default_max_turns,
                default_validation_retry_count
            ) VALUES (
                %s,
                %s,
                'openai_agents_sdk',
                'microsoft_foundry',
                'default-model',
                'medium',
                12,
                2
            )
            RETURNING model_id, model_revision
            """,
                (tenant_id, f"Workflow Model {suffix}"),
            ).fetchone()
        )
        principal_id = require_row(
            connection.execute(
                """
            INSERT INTO security.principal (
                principal_type,
                principal_display_name,
                principal_email
            ) VALUES ('user', %s, %s)
            RETURNING principal_id
            """,
                (f"Workflow Architect {suffix}", f"workflow_{suffix}@example.test"),
            ).fetchone()
        )["principal_id"]
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
            ) VALUES (%s, %s, 'architect', %s)
            """,
            (tenant_id, principal_id, principal_id),
        )
        connection.execute(
            """
            INSERT INTO security.tenant_lock (
                tenant_id,
                locked_by_principal_id,
                tenant_lock_purpose,
                tenant_lock_expires_time
            ) VALUES (
                %s,
                %s,
                'Workflow lifecycle test',
                CURRENT_TIMESTAMP + INTERVAL '30 minutes'
            )
            """,
            (tenant_id, principal_id),
        )
        workflow_stages = connection.execute(
            """
            SELECT workflow_stage_id
              FROM application.workflow_stage
             WHERE model_workflow = 'conceptual'
               AND workflow_execution_mode = 'one_shot'
               AND workflow_stage_is_agentic
               AND is_active
             ORDER BY workflow_stage_order
            """
        ).fetchall()
        if not workflow_stages:
            workflow_stages = [
                require_row(
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
                        'conceptual', 'one_shot', 'candidate_authoring',
                        'Candidate Authoring', 10, TRUE
                    )
                    RETURNING workflow_stage_id
                        """
                    ).fetchone()
                )
            ]

        prompt_snapshots: list[tuple[int, int]] = []
        for prompt_number, workflow_stage in enumerate(workflow_stages, start=1):
            workflow_stage_id = workflow_stage["workflow_stage_id"]
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
                        workflow_stage_id,
                        tenant_id,
                        f"conceptual_prompt_{prompt_number}_{suffix}",
                        f"Conceptual Prompt {prompt_number} {suffix}",
                        principal_id,
                        principal_id,
                    ),
                ).fetchone()
            )["prompt_template_id"]
            prompt_template_version_id = require_row(
                connection.execute(
                    """
                INSERT INTO application.prompt_template_version (
                    prompt_template_id,
                    workflow_stage_id,
                    prompt_template_version_number,
                    system_prompt_template,
                    instruction_prompt_template,
                    prompt_template_digest,
                    created_by_principal_id,
                    updated_by_principal_id
                ) VALUES (
                    %s, %s, 1, '{{ stage_context }}',
                    '{{ stage_context }}', %s, %s, %s
                )
                RETURNING prompt_template_version_id
                """,
                    (
                        prompt_template_id,
                        workflow_stage_id,
                        prompt_digest,
                        principal_id,
                        principal_id,
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
                (principal_id, principal_id, prompt_template_version_id),
            )
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
                    workflow_stage_id,
                    prompt_template_version_id,
                    model_row["model_id"],
                    principal_id,
                ),
            )
            prompt_snapshots.append((workflow_stage_id, prompt_template_version_id))

    context = WorkflowContext(
        entra_tenant_id=entra_tenant_id,
        entra_object_id=entra_object_id,
        tenant_id=tenant_id,
        model_id=model_row["model_id"],
        model_revision=model_row["model_revision"],
        principal_id=principal_id,
        prompt_snapshots=tuple(prompt_snapshots),
        selected_object_ids=(),
    )
    return replace(
        context,
        selected_object_ids=_seed_bronze_model_scope(
            postgres_database,
            context,
        ),
    )


def create_workflow_run_parameters(
    context: WorkflowContext,
    *,
    correlation_id: UUID,
    selected_object_ids: tuple[int, ...] | list[int] | None = None,
    modeled_entity_type: str | None = None,
    requested_batch_id: str | None = None,
    agent_configuration: tuple[
        str | None,
        str | None,
        str | None,
        str | None,
        int | None,
        int | None,
    ] = (None, None, None, None, None, None),
    workflow: str = "conceptual",
    execution_mode: str | None = "one_shot",
) -> tuple[object, ...]:
    return (
        context.entra_tenant_id,
        context.entra_object_id,
        context.model_id,
        context.model_revision,
        workflow,
        execution_mode,
        *agent_configuration,
        (
            list(context.selected_object_ids)
            if selected_object_ids is None
            else list(selected_object_ids)
        ),
        modeled_entity_type,
        requested_batch_id,
        correlation_id,
        "{}",
    )


def _seed_bronze_model_scope(
    postgres_database: DisposablePostgres,
    context: WorkflowContext,
    *,
    object_count: int = 3,
) -> tuple[int, ...]:
    suffix = uuid4().hex
    with postgres_database.connect_owner() as connection:
        reference_ids = require_row(
            connection.execute(
                """
            WITH inserted_system_type AS (
                INSERT INTO reference.system_type (
                    system_type_code,
                    system_type_name
                ) VALUES (%s, %s)
                RETURNING system_type_id
            ),
            inserted_connection_type AS (
                INSERT INTO reference.connection_type (
                    connection_type_code,
                    connection_type_name
                ) VALUES (%s, %s)
                RETURNING connection_type_id
            ),
            inserted_object_type AS (
                INSERT INTO reference.object_type (
                    object_type_code,
                    object_type_name
                ) VALUES (%s, %s)
                RETURNING object_type_id
            )
            SELECT system_type_id,
                   connection_type_id,
                   object_type_id
              FROM inserted_system_type,
                   inserted_connection_type,
                   inserted_object_type
            """,
                (
                    f"workflow_system_type_{suffix}",
                    f"Workflow System Type {suffix}",
                    f"workflow_connection_type_{suffix}",
                    f"Workflow Connection Type {suffix}",
                    f"workflow_object_type_{suffix}",
                    f"Workflow Object Type {suffix}",
                ),
            ).fetchone()
        )
        zone_row = connection.execute(
            """
            SELECT zone_id
              FROM reference.zone
             WHERE lower(btrim(zone_code)) = 'bronze'
               AND is_active
            """
        ).fetchone()
        if zone_row is None:
            zone_row = require_row(
                connection.execute(
                    """
                    INSERT INTO reference.zone (zone_code, zone_name)
                    VALUES ('bronze', 'Bronze')
                    RETURNING zone_id
                    """
                ).fetchone()
            )
        system_id = require_row(
            connection.execute(
                """
            INSERT INTO core.system (
                system_code,
                system_name,
                system_type_id
            ) VALUES (%s, %s, %s)
            RETURNING system_id
            """,
                (
                    f"workflow_system_{suffix}",
                    f"Workflow System {suffix}",
                    reference_ids["system_type_id"],
                ),
            ).fetchone()
        )["system_id"]
        connection_id = require_row(
            connection.execute(
                """
            INSERT INTO core.connection (
                tenant_id,
                system_id,
                connection_code,
                connection_name,
                connection_type_id
            ) VALUES (%s, %s, %s, %s, %s)
            RETURNING connection_id
            """,
                (
                    context.tenant_id,
                    system_id,
                    f"workflow_connection_{suffix}",
                    f"Workflow Connection {suffix}",
                    reference_ids["connection_type_id"],
                ),
            ).fetchone()
        )["connection_id"]
        object_ids: list[int] = []
        for object_number in range(1, object_count + 1):
            object_id = require_row(
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
                        connection_id,
                        f"bronze_{suffix}",
                        f"workflow_object_{object_number}_{suffix}",
                        reference_ids["object_type_id"],
                        zone_row["zone_id"],
                    ),
                ).fetchone()
            )["object_id"]
            connection.execute(
                """
                INSERT INTO model.model_scope (model_id, object_id)
                VALUES (%s, %s)
                """,
                (context.model_id, object_id),
            )
            object_ids.append(object_id)

    return tuple(object_ids)


def _seed_model_scope_object_in_zone(
    postgres_database: DisposablePostgres,
    context: WorkflowContext,
    *,
    zone_code: str,
) -> int:
    suffix = uuid4().hex
    with postgres_database.connect_owner() as connection:
        zone_row = connection.execute(
            """
            SELECT zone_id
              FROM reference.zone
             WHERE lower(btrim(zone_code)) = lower(btrim(%s))
               AND is_active
            """,
            (zone_code,),
        ).fetchone()
        if zone_row is None:
            zone_row = require_row(
                connection.execute(
                    """
                    INSERT INTO reference.zone (zone_code, zone_name)
                    VALUES (%s, %s)
                    RETURNING zone_id
                    """,
                    (zone_code, f"{zone_code.title()} {suffix}"),
                ).fetchone()
            )
        physical_context = require_row(
            connection.execute(
                """
            SELECT object.connection_id, object.object_type_id
              FROM core.object AS object
             WHERE object.object_id = %s
            """,
                (context.selected_object_ids[0],),
            ).fetchone()
        )
        object_id = require_row(
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
                    physical_context["connection_id"],
                    f"{zone_code}_{suffix}",
                    f"workflow_{zone_code}_object_{suffix}",
                    physical_context["object_type_id"],
                    zone_row["zone_id"],
                ),
            ).fetchone()
        )["object_id"]
        connection.execute(
            """
            INSERT INTO model.model_scope (model_id, object_id)
            VALUES (%s, %s)
            """,
            (context.model_id, object_id),
        )

    return object_id


def _move_object_to_second_system(
    postgres_database: DisposablePostgres,
    context: WorkflowContext,
    *,
    object_id: int,
) -> None:
    suffix = uuid4().hex
    with postgres_database.connect_owner() as connection:
        physical_context = require_row(
            connection.execute(
                """
                SELECT system.system_type_id,
                       source_connection.connection_type_id
                  FROM core.object AS object_record
                  JOIN core.connection AS source_connection
                    ON source_connection.connection_id = object_record.connection_id
                  JOIN core.system AS system
                    ON system.system_id = source_connection.system_id
                 WHERE object_record.object_id = %s
                """,
                (object_id,),
            ).fetchone()
        )
        target_connection_id = require_row(
            connection.execute(
                """
                WITH inserted_system AS (
                    INSERT INTO core.system (
                        system_code,
                        system_name,
                        system_type_id
                    ) VALUES (%s, %s, %s)
                    RETURNING system_id
                )
                INSERT INTO core.connection (
                    tenant_id,
                    system_id,
                    connection_code,
                    connection_name,
                    connection_type_id
                )
                SELECT %s, system_id, %s, %s, %s
                  FROM inserted_system
                RETURNING connection_id
                """,
                (
                    f"workflow_second_system_{suffix}",
                    f"Workflow Second System {suffix}",
                    physical_context["system_type_id"],
                    context.tenant_id,
                    f"workflow_second_connection_{suffix}",
                    f"Workflow Second Connection {suffix}",
                    physical_context["connection_type_id"],
                ),
            ).fetchone()
        )["connection_id"]
        connection.execute(
            """
            UPDATE core.object
               SET connection_id = %s
             WHERE object_id = %s
            """,
            (target_connection_id, object_id),
        )


def _seed_code_generation_target(
    postgres_database: DisposablePostgres,
    context: WorkflowContext,
) -> int:
    suffix = uuid4().hex
    object_id = _seed_model_scope_object_in_zone(
        postgres_database,
        context,
        zone_code="silver",
    )
    with postgres_database.connect_owner() as connection:
        source_system_id = require_row(
            connection.execute(
                """
                SELECT connection.system_id
                  FROM core.object AS object_record
                  JOIN core.connection AS connection
                    ON connection.connection_id = object_record.connection_id
                 WHERE object_record.object_id = %s
                """,
                (object_id,),
            ).fetchone()
        )["system_id"]
        logical_entity_id = require_row(
            connection.execute(
                """
            INSERT INTO workflow.logical_entity (
                model_id,
                logical_entity_name,
                logical_entity_definition,
                logical_entity_type,
                logical_entity_grain
            ) VALUES (%s, %s, %s, 'core', %s)
            RETURNING logical_entity_id
            """,
                (
                    context.model_id,
                    f"code_generation_entity_{suffix}",
                    "Complete logical entity for SQL generation.",
                    "One SQL target row",
                ),
            ).fetchone()
        )["logical_entity_id"]
        connection.execute(
            """
            INSERT INTO workflow.mapping_source_system_dependency (
                model_id,
                modeled_entity_type,
                source_system_id
            ) VALUES (%s, 'logical_entity', %s)
            ON CONFLICT (model_id, modeled_entity_type, source_system_id)
            DO NOTHING
            """,
            (context.model_id, source_system_id),
        )
        connection.execute(
            """
            INSERT INTO workflow.mapping_object (
                model_id,
                object_id,
                source_system_id,
                modeled_entity_type,
                logical_entity_id,
                artifact_type,
                artifact_generation_instructions,
                mapping_profile_key,
                mapping_profile_version,
                mapping_profile_schema_digest,
                mapping_package_document,
                mapping_package_digest,
                object_mapping_transformation_document
            ) VALUES (
                %s, %s, %s, 'logical_entity', %s,
                'sql_file', 'Generate SQL for this target.',
                'free_form', '1.0.0', repeat('c', 64),
                '{"schema_version":"1.0","mapping":"complete"}'::JSONB,
                %s,
                '{"schema_version":"1.0","transformation_kind":"direct"}'::JSONB
            )
            """,
            (
                context.model_id,
                object_id,
                source_system_id,
                logical_entity_id,
                sha256(f"mapping:{object_id}".encode()).hexdigest(),
            ),
        )
    return object_id


def _seed_published_sql_generation_guide(
    postgres_database: DisposablePostgres,
    context: WorkflowContext,
    *,
    is_default: bool = True,
) -> tuple[int, int, str]:
    suffix = uuid4().hex
    content = f"Generate Databricks SQL only. {suffix}"
    digest = sha256(content.encode()).hexdigest()
    with postgres_database.connect_owner() as connection:
        stage_rows = connection.execute(
            """
            SELECT workflow_stage_id
              FROM application.workflow_stage
             WHERE model_workflow = 'code_generation'
               AND workflow_execution_mode IS NULL
               AND workflow_stage_is_agentic
               AND is_active
             ORDER BY workflow_stage_order
            """
        ).fetchall()
        if not stage_rows:
            stage_rows = [
                require_row(
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
                        'code_generation', NULL, %s,
                        'SQL Generation', 10, TRUE
                    )
                    RETURNING workflow_stage_id
                    """,
                        (f"sql_generation_{suffix}",),
                    ).fetchone()
                )
            ]
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
        for prompt_number, stage in enumerate(stage_rows, start=1):
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
                        context.tenant_id,
                        f"sql_prompt_{prompt_number}_{suffix}",
                        f"SQL Prompt {prompt_number} {suffix}",
                        context.principal_id,
                        context.principal_id,
                    ),
                ).fetchone()
            )["prompt_template_id"]
            prompt_template_version_id = require_row(
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
                    created_by_principal_id,
                    updated_by_principal_id,
                    published_time,
                    published_by_principal_id
                ) VALUES (
                    %s, %s, 1, '{{ stage_context }}',
                    '{{ stage_context }}', %s, 'published', %s, %s,
                    CURRENT_TIMESTAMP, %s
                )
                RETURNING prompt_template_version_id
                """,
                    (
                        prompt_template_id,
                        stage["workflow_stage_id"],
                        prompt_digest,
                        context.principal_id,
                        context.principal_id,
                        context.principal_id,
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
                    prompt_template_version_id,
                    context.model_id,
                    context.principal_id,
                ),
            )
        existing_default = None
        if is_default:
            existing_default = connection.execute(
                """
                SELECT guide.sql_generation_guide_id,
                       version.sql_generation_guide_version_id,
                       version.sql_generation_guide_digest
                  FROM application.sql_generation_guide AS guide
                  LEFT JOIN LATERAL (
                      SELECT candidate.sql_generation_guide_version_id,
                             candidate.sql_generation_guide_digest
                        FROM application.sql_generation_guide_version AS candidate
                       WHERE candidate.sql_generation_guide_id =
                             guide.sql_generation_guide_id
                         AND candidate.sql_generation_guide_version_status =
                             'published'
                       ORDER BY candidate.sql_generation_guide_version_number DESC
                       LIMIT 1
                  ) AS version ON TRUE
                 WHERE guide.is_active
                   AND guide.is_default
                """
            ).fetchone()
            if (
                existing_default is not None
                and existing_default["sql_generation_guide_version_id"] is not None
            ):
                return (
                    existing_default["sql_generation_guide_id"],
                    existing_default["sql_generation_guide_version_id"],
                    existing_default["sql_generation_guide_digest"],
                )

        if existing_default is None:
            guide_id = require_row(
                connection.execute(
                    """
                INSERT INTO application.sql_generation_guide (
                    sql_generation_guide_code,
                    sql_generation_guide_name,
                    is_default,
                    created_by_principal_id,
                    updated_by_principal_id
                ) VALUES (%s, %s, %s, %s, %s)
                RETURNING sql_generation_guide_id
                """,
                    (
                        f"code_generation_{suffix}",
                        f"Code Generation {suffix}",
                        is_default,
                        context.principal_id,
                        context.principal_id,
                    ),
                ).fetchone()
            )["sql_generation_guide_id"]
        else:
            guide_id = existing_default["sql_generation_guide_id"]
        version_number = require_row(
            connection.execute(
                """
                SELECT coalesce(
                           max(sql_generation_guide_version_number),
                           0
                       ) + 1 AS version_number
                  FROM application.sql_generation_guide_version
                 WHERE sql_generation_guide_id = %s
                """,
                (guide_id,),
            ).fetchone()
        )["version_number"]
        version_id = require_row(
            connection.execute(
                """
            INSERT INTO application.sql_generation_guide_version (
                sql_generation_guide_id,
                sql_generation_guide_version_number,
                sql_generation_guide_content,
                sql_generation_guide_digest,
                sql_generation_guide_version_status,
                created_by_principal_id,
                updated_by_principal_id,
                published_time,
                published_by_principal_id
            ) VALUES (
                %s, %s, %s, %s, 'published', %s, %s,
                CURRENT_TIMESTAMP, %s
            )
            RETURNING sql_generation_guide_version_id
            """,
                (
                    guide_id,
                    version_number,
                    content,
                    digest,
                    context.principal_id,
                    context.principal_id,
                    context.principal_id,
                ),
            ).fetchone()
        )["sql_generation_guide_version_id"]
    return guide_id, version_id, digest


def _code_generation_parameters(
    context: WorkflowContext,
    *,
    object_ids: list[int],
    correlation_id: UUID,
    coverage_mode: str,
    guide_version_id: int | None,
) -> tuple[object, ...]:
    return (
        context.entra_tenant_id,
        context.entra_object_id,
        context.model_id,
        context.model_revision,
        object_ids,
        correlation_id,
        coverage_mode,
        guide_version_id,
    )


def test_create_workflow_run_freezes_server_derived_selected_scope(
    postgres_database: DisposablePostgres,
) -> None:
    context = seed_workflow_context(postgres_database)
    object_ids = context.selected_object_ids
    requested_order = [object_ids[2], object_ids[0], object_ids[1]]

    with postgres_database.connect_owner() as connection:
        created = require_row(
            connection.execute(
                CREATE_WORKFLOW_RUN_SQL,
                create_workflow_run_parameters(
                    context,
                    correlation_id=uuid4(),
                    selected_object_ids=requested_order,
                    requested_batch_id=" 10428 ",
                    workflow="profiling",
                    execution_mode=None,
                ),
            ).fetchone()
        )
        stored_run = require_row(
            connection.execute(
                """
            SELECT run.actor_principal_id,
                   run.actor_entra_principal_identity_id,
                   run.modeled_entity_type,
                   run.requested_batch_id,
                   run.selected_scope_digest,
                   run.selected_scope_count,
                   identity.principal_id AS identity_principal_id
              FROM application.workflow_run AS run
              JOIN security.entra_principal_identity AS identity
                ON identity.entra_principal_identity_id =
                   run.actor_entra_principal_identity_id
             WHERE run.workflow_run_id = %s
            """,
                (created["workflow_run_id"],),
            ).fetchone()
        )
        selections = connection.execute(
            """
            SELECT object_id, selection_order
              FROM application.workflow_run_object_selection
             WHERE workflow_run_id = %s
             ORDER BY selection_order
            """,
            (created["workflow_run_id"],),
        ).fetchall()

    canonical_ids = sorted(object_ids)
    expected_digest = sha256(
        ",".join(str(object_id) for object_id in canonical_ids).encode()
    ).hexdigest()
    assert stored_run == {
        "actor_principal_id": context.principal_id,
        "actor_entra_principal_identity_id": stored_run["actor_entra_principal_identity_id"],
        "modeled_entity_type": None,
        "requested_batch_id": "10428",
        "selected_scope_digest": expected_digest,
        "selected_scope_count": len(object_ids),
        "identity_principal_id": context.principal_id,
    }
    assert stored_run["actor_entra_principal_identity_id"] is not None
    assert selections == [
        {"object_id": object_id, "selection_order": index}
        for index, object_id in enumerate(canonical_ids, start=1)
    ]


def test_create_code_generation_run_freezes_selected_targets_revision_and_guide(
    postgres_database: DisposablePostgres,
) -> None:
    context = seed_workflow_context(postgres_database)
    target_id = _seed_code_generation_target(postgres_database, context)
    guide_id, guide_version_id, guide_digest = (
        _seed_published_sql_generation_guide(
            postgres_database,
            context,
            is_default=False,
        )
    )

    with postgres_database.connect_owner() as connection:
        created = require_row(
            connection.execute(
                CREATE_CODE_GENERATION_WORKFLOW_RUN_SQL,
                _code_generation_parameters(
                    context,
                    object_ids=[target_id],
                    correlation_id=uuid4(),
                    coverage_mode="selected_targets",
                    guide_version_id=guide_version_id,
                ),
            ).fetchone()
        )
        selection = connection.execute(
            """
            SELECT object_id, selection_order
              FROM application.workflow_run_object_selection
             WHERE workflow_run_id = %s
            """,
            (created["workflow_run_id"],),
        ).fetchall()

    assert created["model_revision"] == context.model_revision
    assert created["selected_scope_count"] == 1
    assert created["code_generation_coverage_mode"] == "selected_targets"
    assert created["sql_generation_guide_id"] == guide_id
    assert created["sql_generation_guide_version_id"] == guide_version_id
    assert created["sql_generation_guide_digest"] == guide_digest
    assert selection == [{"object_id": target_id, "selection_order": 1}]


def test_create_code_generation_run_derives_all_eligible_targets_only_from_empty_input(
    postgres_database: DisposablePostgres,
) -> None:
    context = seed_workflow_context(postgres_database)
    target_ids = sorted(
        [
            _seed_code_generation_target(postgres_database, context),
            _seed_code_generation_target(postgres_database, context),
        ]
    )
    _guide_id, guide_version_id, _guide_digest = (
        _seed_published_sql_generation_guide(
            postgres_database,
            context,
            is_default=False,
        )
    )

    with postgres_database.connect_owner() as connection:
        created = require_row(
            connection.execute(
                CREATE_CODE_GENERATION_WORKFLOW_RUN_SQL,
                _code_generation_parameters(
                    context,
                    object_ids=[],
                    correlation_id=uuid4(),
                    coverage_mode="all_eligible_targets",
                    guide_version_id=guide_version_id,
                ),
            ).fetchone()
        )
        selections = connection.execute(
            """
            SELECT object_id, selection_order
              FROM application.workflow_run_object_selection
             WHERE workflow_run_id = %s
             ORDER BY selection_order
            """,
            (created["workflow_run_id"],),
        ).fetchall()

    assert created["selected_scope_count"] == 2
    assert selections == [
        {"object_id": object_id, "selection_order": position}
        for position, object_id in enumerate(target_ids, start=1)
    ]

    with (
        postgres_database.connect_owner() as connection,
        pytest.raises(RaiseException, match="requires an empty"),
    ):
        connection.execute(
            CREATE_CODE_GENERATION_WORKFLOW_RUN_SQL,
            _code_generation_parameters(
                context,
                object_ids=[target_ids[0]],
                correlation_id=uuid4(),
                coverage_mode="all_eligible_targets",
                guide_version_id=guide_version_id,
            ),
        )


def test_code_generation_run_replay_keeps_frozen_default_guide_after_retirement(
    postgres_database: DisposablePostgres,
) -> None:
    context = seed_workflow_context(postgres_database)
    target_id = _seed_code_generation_target(postgres_database, context)
    guide_id, guide_version_id, guide_digest = (
        _seed_published_sql_generation_guide(postgres_database, context)
    )
    correlation_id = uuid4()
    parameters = _code_generation_parameters(
        context,
        object_ids=[target_id],
        correlation_id=correlation_id,
        coverage_mode="selected_targets",
        guide_version_id=None,
    )

    with postgres_database.connect_owner() as connection:
        created = require_row(
            connection.execute(
                CREATE_CODE_GENERATION_WORKFLOW_RUN_SQL,
                parameters,
            ).fetchone()
        )
        connection.execute(
            """
            UPDATE application.sql_generation_guide_version
               SET sql_generation_guide_version_status = 'retired',
                   retired_time = CURRENT_TIMESTAMP,
                   retired_by_principal_id = %s,
                   updated_by_principal_id = %s,
                   updated_time = CURRENT_TIMESTAMP
             WHERE sql_generation_guide_version_id = %s
            """,
            (context.principal_id, context.principal_id, guide_version_id),
        )

    with postgres_database.connect_owner() as connection:
        replay = require_row(
            connection.execute(
                CREATE_CODE_GENERATION_WORKFLOW_RUN_SQL,
                parameters,
            ).fetchone()
        )

    assert created["created"] is True
    assert replay["created"] is False
    assert replay["workflow_run_id"] == created["workflow_run_id"]
    assert replay["sql_generation_guide_id"] == guide_id
    assert replay["sql_generation_guide_version_id"] == guide_version_id
    assert replay["sql_generation_guide_digest"] == guide_digest


def test_code_generation_run_rejects_zone_only_target_without_complete_mapping(
    postgres_database: DisposablePostgres,
) -> None:
    context = seed_workflow_context(postgres_database)
    target_id = _seed_model_scope_object_in_zone(
        postgres_database,
        context,
        zone_code="silver",
    )
    _guide_id, guide_version_id, _guide_digest = (
        _seed_published_sql_generation_guide(
            postgres_database,
            context,
            is_default=False,
        )
    )

    with (
        postgres_database.connect_owner() as connection,
        pytest.raises(RaiseException, match="complete applied SQL Mapping"),
    ):
        connection.execute(
            CREATE_CODE_GENERATION_WORKFLOW_RUN_SQL,
            _code_generation_parameters(
                context,
                object_ids=[target_id],
                correlation_id=uuid4(),
                coverage_mode="selected_targets",
                guide_version_id=guide_version_id,
            ),
        )


@pytest.mark.parametrize("workflow", ("profiling", "analysis"))
def test_create_workflow_run_rejects_only_batch_across_multiple_systems(
    postgres_database: DisposablePostgres,
    workflow: str,
) -> None:
    context = seed_workflow_context(postgres_database)
    _move_object_to_second_system(
        postgres_database,
        context,
        object_id=context.selected_object_ids[-1],
    )

    with postgres_database.connect_owner() as connection:
        no_batch = require_row(
            connection.execute(
                CREATE_WORKFLOW_RUN_SQL,
                create_workflow_run_parameters(
                    context,
                    correlation_id=uuid4(),
                    workflow=workflow,
                    execution_mode=None,
                ),
            ).fetchone()
        )

    with (
        postgres_database.connect_owner() as connection,
        pytest.raises(RaiseException, match="batch ID.*one System"),
    ):
        connection.execute(
            CREATE_WORKFLOW_RUN_SQL,
            create_workflow_run_parameters(
                context,
                correlation_id=uuid4(),
                requested_batch_id="10428",
                workflow=workflow,
                execution_mode=None,
            ),
        )

    assert no_batch["created"] is True


def test_create_workflow_run_rejects_invalid_selected_scope_atomically(
    postgres_database: DisposablePostgres,
) -> None:
    context = seed_workflow_context(postgres_database)
    correlations = [uuid4(), uuid4(), uuid4()]
    invalid_selections: tuple[tuple[list[int], str], ...] = (
        ([], "between"),
        (
            [context.selected_object_ids[0], context.selected_object_ids[0]],
            "unique",
        ),
        ([max(context.selected_object_ids) + 1_000_000], "ineligible|unavailable"),
    )

    for correlation_id, (selected_object_ids, expected_error) in zip(
        correlations,
        invalid_selections,
        strict=True,
    ):
        with (
            postgres_database.connect_owner() as connection,
            pytest.raises(RaiseException, match=expected_error),
        ):
            connection.execute(
                CREATE_WORKFLOW_RUN_SQL,
                create_workflow_run_parameters(
                    context,
                    correlation_id=correlation_id,
                    selected_object_ids=selected_object_ids,
                ),
            )

    with postgres_database.connect_owner() as connection:
        rejected_rows = require_row(
            connection.execute(
                """
            SELECT count(*) AS run_count,
                   count(selection.workflow_run_object_selection_id)
                       AS selection_count
              FROM application.workflow_run AS run
              LEFT JOIN application.workflow_run_object_selection AS selection
                ON selection.workflow_run_id = run.workflow_run_id
             WHERE run.correlation_id = ANY(%s::UUID[])
            """,
                (correlations,),
            ).fetchone()
        )

    assert rejected_rows == {"run_count": 0, "selection_count": 0}


def test_create_workflow_run_enforces_workflow_eligibility_not_scope_zone(
    postgres_database: DisposablePostgres,
) -> None:
    context = seed_workflow_context(postgres_database)
    source_object_id = _seed_model_scope_object_in_zone(
        postgres_database,
        context,
        zone_code="source",
    )

    with (
        postgres_database.connect_owner() as connection,
        pytest.raises(RaiseException, match="ineligible"),
    ):
        connection.execute(
            CREATE_WORKFLOW_RUN_SQL,
            create_workflow_run_parameters(
                context,
                correlation_id=uuid4(),
                selected_object_ids=[source_object_id],
            ),
        )

    with postgres_database.connect_owner() as connection:
        scope_row = require_row(
            connection.execute(
                """
                SELECT is_active
                  FROM model.model_scope
                 WHERE model_id = %s
                   AND object_id = %s
                """,
                (context.model_id, source_object_id),
            ).fetchone()
        )

    assert scope_row["is_active"] is True


def test_create_workflow_run_rejects_workflow_incompatible_options(
    postgres_database: DisposablePostgres,
) -> None:
    context = seed_workflow_context(postgres_database)
    cases = (
        (
            create_workflow_run_parameters(
                context,
                correlation_id=uuid4(),
                workflow="mapping",
                modeled_entity_type=None,
            ),
            "complete selected target",
        ),
        (
            create_workflow_run_parameters(
                context,
                correlation_id=uuid4(),
                workflow="conceptual",
                requested_batch_id="10428",
            ),
            "batch ID",
        ),
        (
            create_workflow_run_parameters(
                context,
                correlation_id=uuid4(),
                workflow="profiling",
                execution_mode=None,
                modeled_entity_type="logical_entity",
            ),
            "Modeled Entity type",
        ),
    )

    for parameters, expected_error in cases:
        with (
            postgres_database.connect_owner() as connection,
            pytest.raises(RaiseException, match=expected_error),
        ):
            connection.execute(CREATE_WORKFLOW_RUN_SQL, parameters)


def test_workflow_run_constraint_requires_mapping_entity_type(
    postgres_database: DisposablePostgres,
) -> None:
    context = seed_workflow_context(postgres_database)

    with (
        postgres_database.connect_owner() as connection,
        pytest.raises(CheckViolation),
    ):
        connection.execute(
            """
            INSERT INTO application.workflow_run (
                model_id,
                model_revision,
                model_workflow,
                workflow_execution_mode,
                actor_principal_id,
                agent_sdk_code,
                agent_provider_code,
                agent_model_code,
                reasoning_effort_code,
                max_turns,
                validation_retry_count,
                modeled_entity_type,
                selected_scope_digest,
                selected_scope_count,
                correlation_id
            ) VALUES (
                %s,
                %s,
                'mapping',
                'one_shot',
                %s,
                'openai_agents_sdk',
                'microsoft_foundry',
                'default-model',
                'medium',
                12,
                2,
                NULL,
                repeat('0', 64),
                1,
                %s
            )
            """,
            (
                context.model_id,
                context.model_revision,
                context.principal_id,
                uuid4(),
            ),
        )


def test_workflow_run_object_selection_is_immutable(
    postgres_database: DisposablePostgres,
) -> None:
    context = seed_workflow_context(postgres_database)
    with postgres_database.connect_owner() as connection:
        created = require_row(
            connection.execute(
                CREATE_WORKFLOW_RUN_SQL,
                create_workflow_run_parameters(
                    context,
                    correlation_id=uuid4(),
                    workflow="profiling",
                    execution_mode=None,
                ),
            ).fetchone()
        )

    for statement in (
        """
        UPDATE application.workflow_run_object_selection
           SET selection_order = selection_order + 10
         WHERE workflow_run_id = %s
        """,
        """
        DELETE FROM application.workflow_run_object_selection
         WHERE workflow_run_id = %s
        """,
    ):
        with (
            postgres_database.connect_owner() as connection,
            pytest.raises(RaiseException, match="immutable"),
        ):
            connection.execute(statement, (created["workflow_run_id"],))

    with postgres_database.connect_owner() as connection:
        selected_count = require_row(
            connection.execute(
                """
                SELECT count(*) AS count
                  FROM application.workflow_run_object_selection
                 WHERE workflow_run_id = %s
                """,
                (created["workflow_run_id"],),
            ).fetchone()
        )["count"]

    assert selected_count == len(context.selected_object_ids)


def test_governed_workflow_run_happy_path_is_idempotent_ordered_and_repair_aware(
    postgres_database: DisposablePostgres,
) -> None:
    context = seed_workflow_context(postgres_database)
    correlation_id = uuid4()
    create_parameters = create_workflow_run_parameters(context, correlation_id=correlation_id)

    with postgres_database.connect_owner() as connection:
        created = require_row(
            connection.execute(
                CREATE_WORKFLOW_RUN_SQL,
                create_parameters,
            ).fetchone()
        )
        replayed = require_row(
            connection.execute(
                CREATE_WORKFLOW_RUN_SQL,
                create_parameters,
            ).fetchone()
        )
        reordered_replay = require_row(
            connection.execute(
                CREATE_WORKFLOW_RUN_SQL,
                create_workflow_run_parameters(
                    context,
                    correlation_id=correlation_id,
                    selected_object_ids=list(reversed(context.selected_object_ids)),
                ),
            ).fetchone()
        )
        stored_run = require_row(
            connection.execute(
                """
            SELECT actor_principal_id,
                   agent_sdk_code,
                   agent_provider_code,
                   agent_model_code,
                   reasoning_effort_code,
                   max_turns,
                   validation_retry_count
              FROM application.workflow_run
             WHERE workflow_run_id = %s
            """,
                (created["workflow_run_id"],),
            ).fetchone()
        )

    assert created["workflow_run_id"] == replayed["workflow_run_id"]
    assert created["workflow_run_id"] == reordered_replay["workflow_run_id"]
    assert created["created"] is True
    assert replayed["created"] is False
    assert reordered_replay["created"] is False
    assert created["prompt_snapshot_count"] == len(context.prompt_snapshots)
    assert created["workflow_run_state"] == "queued"
    assert stored_run == {
        "actor_principal_id": context.principal_id,
        "agent_sdk_code": "openai_agents_sdk",
        "agent_provider_code": "microsoft_foundry",
        "agent_model_code": "default-model",
        "reasoning_effort_code": "medium",
        "max_turns": 12,
        "validation_retry_count": 2,
    }

    with (
        postgres_database.connect_owner() as connection,
        pytest.raises(RaiseException, match="correlation|idempot"),
    ):
        connection.execute(
            CREATE_WORKFLOW_RUN_SQL,
            create_workflow_run_parameters(
                context,
                correlation_id=correlation_id,
                selected_object_ids=context.selected_object_ids[:2],
            ),
        )

    workflow_run_id = created["workflow_run_id"]
    with postgres_database.connect_owner() as connection:
        running = require_row(
            connection.execute(
                """
            SELECT *
              FROM application.start_workflow_run(
                  %s::UUID, %s::UUID, 'user'::VARCHAR,
                  %s::BIGINT, %s::BIGINT
              )
            """,
                (
                    context.entra_tenant_id,
                    context.entra_object_id,
                    workflow_run_id,
                    context.model_revision,
                ),
            ).fetchone()
        )
        first_event = require_row(
            connection.execute(
                """
            SELECT *
              FROM application.append_workflow_run_event(
                  %s::UUID, %s::UUID, 'user'::VARCHAR,
                  %s::BIGINT, %s::BIGINT, 2::BIGINT, 1::INTEGER,
                  'prepare'::VARCHAR, 'running'::VARCHAR,
                  'Preparing bounded workflow context.'::VARCHAR,
                  0::INTEGER, 3::INTEGER, 0::INTEGER
              )
            """,
                (
                    context.entra_tenant_id,
                    context.entra_object_id,
                    workflow_run_id,
                    context.model_revision,
                ),
            ).fetchone()
        )

    assert running["workflow_run_state"] == "running"
    assert first_event["model_event_log_sequence"] == 2
    assert first_event["model_event_log_attempt"] == 1
    assert first_event["model_id"] == context.model_id
    assert first_event["correlation_id"] == correlation_id

    with (
        postgres_database.connect_owner() as connection,
        pytest.raises(RaiseException, match="sequence|ordered"),
    ):
        connection.execute(
            """
            SELECT *
              FROM application.append_workflow_run_event(
                  %s::UUID, %s::UUID, 'user'::VARCHAR,
                  %s::BIGINT, %s::BIGINT, 4::BIGINT, 2::INTEGER,
                  'repair'::VARCHAR, 'running'::VARCHAR,
                  'Repairing one validation finding.'::VARCHAR,
                  2::INTEGER, 3::INTEGER, 1::INTEGER
              )
            """,
            (
                context.entra_tenant_id,
                context.entra_object_id,
                workflow_run_id,
                context.model_revision,
            ),
        )

    with postgres_database.connect_owner() as connection:
        second_event = require_row(
            connection.execute(
                """
            SELECT *
              FROM application.append_workflow_run_event(
                  %s::UUID, %s::UUID, 'user'::VARCHAR,
                  %s::BIGINT, %s::BIGINT, 3::BIGINT, 2::INTEGER,
                  'repair'::VARCHAR, 'running'::VARCHAR,
                  'Repairing one validation finding.'::VARCHAR,
                  2::INTEGER, 3::INTEGER, 1::INTEGER
              )
            """,
                (
                    context.entra_tenant_id,
                    context.entra_object_id,
                    workflow_run_id,
                    context.model_revision,
                ),
            ).fetchone()
        )
        completed = require_row(
            connection.execute(
                """
            SELECT *
              FROM application.complete_workflow_run(
                  %s::UUID, %s::UUID, 'user'::VARCHAR,
                  %s::BIGINT, %s::BIGINT, 1::INTEGER
              )
            """,
                (
                    context.entra_tenant_id,
                    context.entra_object_id,
                    workflow_run_id,
                    context.model_revision,
                ),
            ).fetchone()
        )
        snapshots = connection.execute(
            """
            SELECT workflow_stage_id,
                   prompt_template_version_id,
                   prompt_resolution_source
              FROM application.workflow_run_prompt_snapshot
             WHERE workflow_run_id = %s
             ORDER BY workflow_stage_id
            """,
            (workflow_run_id,),
        ).fetchall()
        events = connection.execute(
            """
            SELECT model_event_log_sequence, model_event_log_attempt
              FROM model.model_event_log
             WHERE workflow_run_id = %s
             ORDER BY model_event_log_sequence
            """,
            (workflow_run_id,),
        ).fetchall()
        stored_terminal_run = require_row(
            connection.execute(
                """
            SELECT failure_code, failure_message
              FROM application.workflow_run
             WHERE workflow_run_id = %s
            """,
                (workflow_run_id,),
            ).fetchone()
        )

    assert second_event["model_event_log_sequence"] == 3
    assert completed["workflow_run_state"] == "completed_with_repair"
    assert stored_terminal_run == {"failure_code": None, "failure_message": None}
    assert snapshots == [
        {
            "workflow_stage_id": stage_id,
            "prompt_template_version_id": version_id,
            "prompt_resolution_source": "model_default",
        }
        for stage_id, version_id in context.prompt_snapshots
    ]
    assert events == [
        {"model_event_log_sequence": 1, "model_event_log_attempt": 1},
        {"model_event_log_sequence": 2, "model_event_log_attempt": 1},
        {"model_event_log_sequence": 3, "model_event_log_attempt": 2},
        {"model_event_log_sequence": 4, "model_event_log_attempt": 2},
    ]


def test_create_workflow_run_validates_agent_overrides_and_snapshots_atomically(
    postgres_database: DisposablePostgres,
) -> None:
    context = seed_workflow_context(postgres_database)
    override_correlation = uuid4()
    override = (
        "pydantic_ai",
        "registered_provider",
        "registered-model-2",
        "high",
        20,
        4,
    )

    with postgres_database.connect_owner() as connection:
        created = require_row(
            connection.execute(
                CREATE_WORKFLOW_RUN_SQL,
                create_workflow_run_parameters(
                    context,
                    correlation_id=override_correlation,
                    agent_configuration=override,
                ),
            ).fetchone()
        )
        stored_run = require_row(
            connection.execute(
                """
            SELECT agent_sdk_code,
                   agent_provider_code,
                   agent_model_code,
                   reasoning_effort_code,
                   max_turns,
                   validation_retry_count
              FROM application.workflow_run
             WHERE workflow_run_id = %s
            """,
                (created["workflow_run_id"],),
            ).fetchone()
        )

    assert (
        stored_run["agent_sdk_code"],
        stored_run["agent_provider_code"],
        stored_run["agent_model_code"],
        stored_run["reasoning_effort_code"],
        stored_run["max_turns"],
        stored_run["validation_retry_count"],
    ) == override

    partial_correlation = uuid4()
    with (
        postgres_database.connect_owner() as connection,
        pytest.raises(RaiseException, match="[Aa]gent configuration|partial"),
    ):
        connection.execute(
            CREATE_WORKFLOW_RUN_SQL,
            create_workflow_run_parameters(
                context,
                correlation_id=partial_correlation,
                agent_configuration=(
                    "pydantic_ai",
                    None,
                    None,
                    None,
                    None,
                    None,
                ),
            ),
        )

    missing_prompt_correlation = uuid4()
    with postgres_database.connect_owner() as connection:
        logical_stage_count = require_row(
            connection.execute(
                """
            SELECT count(*) AS count
              FROM application.workflow_stage
             WHERE model_workflow = 'logical'
               AND workflow_execution_mode = 'one_shot'
               AND workflow_stage_is_agentic
               AND is_active
            """
            ).fetchone()
        )["count"]
        if logical_stage_count == 0:
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
                    'logical', 'one_shot', %s,
                    'Logical authoring', 1000, TRUE
                )
                """,
                (f"logical_authoring_{uuid4().hex}",),
            )

    with (
        postgres_database.connect_owner() as connection,
        pytest.raises(RaiseException, match="prompt|Prompt"),
    ):
        connection.execute(
            CREATE_WORKFLOW_RUN_SQL,
            create_workflow_run_parameters(
                context,
                correlation_id=missing_prompt_correlation,
                workflow="logical",
            ),
        )

    with postgres_database.connect_owner() as connection:
        rejected_runs = require_row(
            connection.execute(
                """
            SELECT count(*) AS count
              FROM application.workflow_run
             WHERE correlation_id IN (%s, %s)
            """,
                (partial_correlation, missing_prompt_correlation),
            ).fetchone()
        )["count"]
        rejected_snapshots = require_row(
            connection.execute(
                """
            SELECT count(*) AS count
              FROM application.workflow_run_prompt_snapshot AS snapshot
              JOIN application.workflow_run AS run
                ON run.workflow_run_id = snapshot.workflow_run_id
             WHERE run.correlation_id IN (%s, %s)
            """,
                (partial_correlation, missing_prompt_correlation),
            ).fetchone()
        )["count"]

    assert rejected_runs == 0
    assert rejected_snapshots == 0


def test_create_and_complete_require_identity_role_owned_lock_and_revision(
    postgres_database: DisposablePostgres,
) -> None:
    context = seed_workflow_context(postgres_database)
    viewer_tenant_id = uuid4()
    viewer_object_id = uuid4()
    viewer_correlation = uuid4()

    with postgres_database.connect_owner() as connection:
        viewer_id = require_row(
            connection.execute(
                """
            INSERT INTO security.principal (
                principal_type,
                principal_display_name,
                principal_email
            ) VALUES ('user', 'Workflow Viewer', %s)
            RETURNING principal_id
            """,
                (f"workflow_viewer_{uuid4().hex}@example.test",),
            ).fetchone()
        )["principal_id"]
        connection.execute(
            """
            INSERT INTO security.entra_principal_identity (
                principal_id,
                principal_type,
                entra_tenant_id,
                entra_object_id
            ) VALUES (%s, 'user', %s, %s)
            """,
            (viewer_id, viewer_tenant_id, viewer_object_id),
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
            (context.tenant_id, viewer_id, viewer_id),
        )

    viewer_parameters = list(
        create_workflow_run_parameters(
            context,
            correlation_id=viewer_correlation,
        )
    )
    viewer_parameters[0] = viewer_tenant_id
    viewer_parameters[1] = viewer_object_id
    with (
        postgres_database.connect_owner() as connection,
        pytest.raises(RaiseException, match="authoriz|denied"),
    ):
        connection.execute(CREATE_WORKFLOW_RUN_SQL, viewer_parameters)

    stale_correlation = uuid4()
    with (
        postgres_database.connect_owner() as connection,
        pytest.raises(RaiseException, match="revision"),
    ):
        stale_parameters = list(
            create_workflow_run_parameters(
                context,
                correlation_id=stale_correlation,
            )
        )
        stale_parameters[3] = context.model_revision + 1
        connection.execute(CREATE_WORKFLOW_RUN_SQL, stale_parameters)

    no_lock_correlation = uuid4()
    with postgres_database.connect_owner() as connection:
        connection.execute(
            """
            UPDATE security.tenant_lock
               SET tenant_lock_acquired_time = CURRENT_TIMESTAMP - INTERVAL '2 hours',
                   tenant_lock_expires_time = CURRENT_TIMESTAMP - INTERVAL '1 hour'
             WHERE tenant_id = %s
            """,
            (context.tenant_id,),
        )

    with (
        postgres_database.connect_owner() as connection,
        pytest.raises(RaiseException, match="lock"),
    ):
        connection.execute(
            CREATE_WORKFLOW_RUN_SQL,
            create_workflow_run_parameters(context, correlation_id=no_lock_correlation),
        )

    with postgres_database.connect_owner() as connection:
        rejected_count = require_row(
            connection.execute(
                """
            SELECT count(*) AS count
              FROM application.workflow_run
             WHERE correlation_id IN (%s, %s, %s)
            """,
                (viewer_correlation, stale_correlation, no_lock_correlation),
            ).fetchone()
        )["count"]

    assert rejected_count == 0


def test_fail_workflow_run_requires_the_owned_lock_and_records_safe_failure(
    postgres_database: DisposablePostgres,
) -> None:
    context = seed_workflow_context(postgres_database)
    correlation_id = uuid4()

    with postgres_database.connect_owner() as connection:
        created = require_row(
            connection.execute(
                CREATE_WORKFLOW_RUN_SQL,
                create_workflow_run_parameters(context, correlation_id=correlation_id),
            ).fetchone()
        )
        connection.execute(
            """
            SELECT *
              FROM application.start_workflow_run(
                  %s::UUID, %s::UUID, 'user'::VARCHAR,
                  %s::BIGINT, %s::BIGINT
              )
            """,
            (
                context.entra_tenant_id,
                context.entra_object_id,
                created["workflow_run_id"],
                context.model_revision,
            ),
        )
        connection.execute(
            """
            UPDATE security.tenant_lock
               SET tenant_lock_acquired_time = CURRENT_TIMESTAMP - INTERVAL '2 hours',
                   tenant_lock_expires_time = CURRENT_TIMESTAMP - INTERVAL '1 hour'
             WHERE tenant_id = %s
            """,
            (context.tenant_id,),
        )
    with (
        postgres_database.connect_owner() as connection,
        pytest.raises(RaiseException, match="lock"),
    ):
        connection.execute(
            """
            SELECT *
              FROM application.fail_workflow_run(
                  %s::UUID, %s::UUID, 'user'::VARCHAR,
                  %s::BIGINT, %s::BIGINT,
                  'provider_timeout'::VARCHAR,
                  'Registered provider timed out.'::VARCHAR
              )
            """,
            (
                context.entra_tenant_id,
                context.entra_object_id,
                created["workflow_run_id"],
                context.model_revision,
            ),
        )

    with postgres_database.connect_owner() as connection:
        still_running = require_row(
            connection.execute(
                """
            SELECT workflow_run_state
              FROM application.workflow_run
             WHERE workflow_run_id = %s
            """,
                (created["workflow_run_id"],),
            ).fetchone()
        )
        acquired = require_row(
            connection.execute(
                """
            SELECT acquired
              FROM security.acquire_tenant_lock(
                  %s::UUID, %s::UUID, 'user'::VARCHAR,
                  %s::BIGINT, 30::INTEGER, 'Finish failed Workflow Run'::VARCHAR
              )
            """,
                (
                    context.entra_tenant_id,
                    context.entra_object_id,
                    context.tenant_id,
                ),
            ).fetchone()
        )
        failed = require_row(
            connection.execute(
                """
            SELECT *
              FROM application.fail_workflow_run(
                  %s::UUID, %s::UUID, 'user'::VARCHAR,
                  %s::BIGINT, %s::BIGINT,
                  'provider_timeout'::VARCHAR,
                  'Registered provider timed out.'::VARCHAR
              )
            """,
                (
                    context.entra_tenant_id,
                    context.entra_object_id,
                    created["workflow_run_id"],
                    context.model_revision,
                ),
            ).fetchone()
        )
        stored_failure = require_row(
            connection.execute(
                """
            SELECT failure_code, failure_message
              FROM application.workflow_run
             WHERE workflow_run_id = %s
            """,
                (created["workflow_run_id"],),
            ).fetchone()
        )

    assert still_running["workflow_run_state"] == "running"
    assert acquired["acquired"] is True
    assert failed["workflow_run_state"] == "failed"
    assert stored_failure == {
        "failure_code": "provider_timeout",
        "failure_message": "Registered provider timed out.",
    }


def test_workflow_lifecycle_mutations_use_web_only_security_definer_functions(
    postgres_database: DisposablePostgres,
) -> None:
    expected_functions = {
        "append_workflow_run_event",
        "complete_workflow_run",
        "create_workflow_run",
        "fail_workflow_run",
        "start_workflow_run",
    }

    with postgres_database.connect_owner() as connection:
        rows = connection.execute(
            """
            SELECT procedure.proname AS function_name,
                   procedure.prosecdef AS is_security_definer,
                   procedure.proconfig AS settings,
                   has_function_privilege(
                       'gds_web_write', procedure.oid, 'EXECUTE'
                   ) AS web_can_execute,
                   has_function_privilege(
                       'gds_app_write', procedure.oid, 'EXECUTE'
                   ) AS mcp_can_execute,
                   has_function_privilege(
                       'public', procedure.oid, 'EXECUTE'
                   ) AS public_can_execute
              FROM pg_catalog.pg_proc AS procedure
              JOIN pg_catalog.pg_namespace AS namespace
                ON namespace.oid = procedure.pronamespace
             WHERE namespace.nspname = 'application'
               AND procedure.proname = ANY(%s)
             ORDER BY procedure.proname
            """,
            (list(expected_functions),),
        ).fetchall()
        direct_table_access = require_row(
            connection.execute(
                """
            SELECT has_table_privilege(
                       'gds_web_write',
                       'application.workflow_run',
                       'INSERT,UPDATE,DELETE'
                   ) AS web_can_mutate_run,
                   has_table_privilege(
                       'gds_web_write',
                       'application.workflow_run_prompt_snapshot',
                       'INSERT,UPDATE,DELETE'
                   ) AS web_can_mutate_snapshot,
                   has_table_privilege(
                       'gds_web_write',
                       'application.workflow_run_object_selection',
                       'INSERT,UPDATE,DELETE'
                   ) AS web_can_mutate_selection,
                   has_table_privilege(
                       'gds_web_write',
                       'model.model_event_log',
                       'INSERT,UPDATE,DELETE'
                   ) AS web_can_mutate_event
            """
            ).fetchone()
        )

    assert {row["function_name"] for row in rows} == expected_functions
    assert all(row["is_security_definer"] for row in rows)
    assert all(row["web_can_execute"] for row in rows)
    assert not any(row["mcp_can_execute"] for row in rows)
    assert not any(row["public_can_execute"] for row in rows)
    assert all(
        row["settings"] is not None
        and any(setting.startswith("search_path=") for setting in row["settings"])
        for row in rows
    )
    assert direct_table_access == {
        "web_can_mutate_run": False,
        "web_can_mutate_snapshot": False,
        "web_can_mutate_selection": False,
        "web_can_mutate_event": False,
    }
