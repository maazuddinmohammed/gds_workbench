from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path
from threading import Barrier
from typing import TYPE_CHECKING, LiteralString, cast
from uuid import UUID, uuid4

import psycopg
import pytest
from psycopg.errors import InsufficientPrivilege, RaiseException
from psycopg.rows import dict_row

from tests.mcp.database_test_support import require_row
from tests.mcp.test_database_workflow_run_lifecycle import (
    WorkflowContext,
    _seed_code_generation_target,
    _seed_published_sql_generation_guide,
    seed_workflow_context,
)

if TYPE_CHECKING:
    from conftest import DisposablePostgres


VERIFY_INSTALL_SQL = Path(__file__).parents[2] / "database" / "13_verify_install.sql"

CREATE_NOTEBOOK_PROFILING_SQL = """
SELECT *
  FROM application.create_notebook_workflow_run(
      %s::BIGINT,
      %s::BIGINT,
      %s::BIGINT,
      'profiling'::VARCHAR,
      NULL::VARCHAR,
      NULL::VARCHAR,
      NULL::VARCHAR,
      NULL::VARCHAR,
      NULL::VARCHAR,
      NULL::INTEGER,
      NULL::INTEGER,
      %s::BIGINT[],
      NULL::VARCHAR,
      %s::VARCHAR,
      %s::UUID,
      '{}'::JSONB
  )
"""

START_AND_CLAIM_SQL = """
SELECT *
  FROM application.start_and_claim_notebook_workflow_run(
      %s::BIGINT,
      %s::BIGINT,
      %s::BIGINT,
      %s::BIGINT,
      'profiling'::VARCHAR,
      30::INTEGER
  )
"""

CREATE_NOTEBOOK_WORKFLOW_SQL = """
SELECT *
  FROM application.create_notebook_workflow_run(
      %s::BIGINT,
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
      %s::JSONB,
      %s::VARCHAR,
      %s::VARCHAR,
      %s::VARCHAR,
      %s::BIGINT,
      %s::BIGINT,
      %s::BIGINT,
      %s::VARCHAR,
      %s::BIGINT
  )
"""

START_AND_CLAIM_WORKFLOW_SQL = """
SELECT *
  FROM application.start_and_claim_notebook_workflow_run(
      %s::BIGINT,
      %s::BIGINT,
      %s::BIGINT,
      %s::BIGINT,
      %s::VARCHAR,
      30::INTEGER
  )
"""


@dataclass(frozen=True, slots=True)
class NotebookActor:
    database: DisposablePostgres
    principal_id: int
    entra_principal_identity_id: int
    entra_tenant_id: UUID
    entra_object_id: UUID


@dataclass(frozen=True, slots=True)
class NotebookWorkflowShape:
    entrypoint: str
    workflow: str
    execution_mode: str | None
    scope: str
    is_agentic: bool


NOTEBOOK_WORKFLOW_SHAPES = (
    NotebookWorkflowShape("profiling", "profiling", None, "bronze", False),
    NotebookWorkflowShape("analysis_validation", "analysis", None, "bronze", False),
    NotebookWorkflowShape("analysis_inference", "analysis", "one_shot", "bronze", True),
    NotebookWorkflowShape("conceptual", "conceptual", "one_shot", "bronze", True),
    NotebookWorkflowShape("logical", "logical", "one_shot", "bronze", True),
    NotebookWorkflowShape("dimensional", "dimensional", "one_shot", "mapped_silver", True),
    NotebookWorkflowShape("mapping", "mapping", "one_shot", "mapped_silver", True),
    NotebookWorkflowShape("code_generation", "code_generation", None, "mapped_silver", True),
)

ONE_SHOT_STAGE_CODES = {
    "analysis": "relationship_inference",
    "logical": "candidate_authoring",
    "dimensional": "candidate_authoring",
    "mapping": "mapping_authoring",
}


@pytest.fixture(scope="module")
def notebook_actor(
    bootstrap_postgres_database: DisposablePostgres,
) -> NotebookActor:
    entra_tenant_id = uuid4()
    entra_object_id = uuid4()
    with bootstrap_postgres_database.connect_owner() as connection:
        principal_id = require_row(
            connection.execute(
                """
                INSERT INTO security.principal (
                    principal_type,
                    principal_display_name,
                    service_principal_application_id,
                    service_principal_type,
                    is_super_admin
                ) VALUES (
                    'service_principal',
                    'Notebook Workflow Runtime',
                    %s,
                    'application',
                    TRUE
                )
                RETURNING principal_id
                """,
                (uuid4(),),
            ).fetchone()
        )["principal_id"]
        identity_id = require_row(
            connection.execute(
                """
                INSERT INTO security.entra_principal_identity (
                    principal_id,
                    principal_type,
                    entra_tenant_id,
                    entra_object_id
                ) VALUES (%s, 'service_principal', %s, %s)
                RETURNING entra_principal_identity_id
                """,
                (principal_id, entra_tenant_id, entra_object_id),
            ).fetchone()
        )["entra_principal_identity_id"]
        runtime_role = require_row(
            connection.execute(
                """
                SELECT oid, rolname
                  FROM pg_catalog.pg_roles
                 WHERE rolname = 'gds_notebook_runtime'
                """
            ).fetchone()
        )
        connection.execute(
            """
            INSERT INTO security.notebook_runtime_principal (
                database_role_oid,
                database_role_name,
                entra_principal_identity_id,
                principal_id,
                principal_type,
                databricks_environment_code
            ) VALUES (%s, %s, %s, %s, 'service_principal', 'TEST')
            """,
            (
                runtime_role["oid"],
                runtime_role["rolname"],
                identity_id,
                principal_id,
            ),
        )
    return NotebookActor(
        database=bootstrap_postgres_database,
        principal_id=principal_id,
        entra_principal_identity_id=identity_id,
        entra_tenant_id=entra_tenant_id,
        entra_object_id=entra_object_id,
    )


def _bind_notebook_tenant_lock(
    actor: NotebookActor,
    context: WorkflowContext,
) -> None:
    with actor.database.connect_owner() as connection:
        connection.execute(
            """
            UPDATE security.tenant_lock
               SET locked_by_principal_id = %s,
                   tenant_lock_purpose = 'Notebook Workflow test',
                   tenant_lock_expires_time =
                       clock_timestamp() + INTERVAL '30 minutes'
             WHERE tenant_id = %s
            """,
            (actor.principal_id, context.tenant_id),
        )


def _seed_notebook_tenant(actor: NotebookActor) -> WorkflowContext:
    context = seed_workflow_context(actor.database)
    _bind_notebook_tenant_lock(actor, context)
    return context


def _seed_missing_model_prompt_assignments(
    actor: NotebookActor,
    context: WorkflowContext,
    *,
    workflow: str,
    execution_mode: str | None,
) -> None:
    suffix = uuid4().hex
    with actor.database.connect_owner() as connection:
        stages = connection.execute(
            """
            SELECT stage.workflow_stage_id
              FROM application.workflow_stage AS stage
             WHERE stage.model_workflow = %s
               AND stage.workflow_execution_mode IS NOT DISTINCT FROM %s
               AND stage.workflow_stage_is_agentic
               AND stage.is_active
               AND NOT EXISTS (
                   SELECT 1
                     FROM application.prompt_assignment AS assignment
                    WHERE assignment.workflow_stage_id = stage.workflow_stage_id
                      AND assignment.prompt_assignment_scope = 'model_default'
                      AND assignment.model_id = %s
                      AND assignment.is_active
               )
             ORDER BY stage.workflow_stage_order
            """,
            (workflow, execution_mode, context.model_id),
        ).fetchall()
        if not stages:
            existing_stage = connection.execute(
                """
                SELECT 1
                  FROM application.workflow_stage AS stage
                 WHERE stage.model_workflow = %s
                   AND stage.workflow_execution_mode IS NOT DISTINCT FROM %s
                   AND stage.workflow_stage_is_agentic
                   AND stage.is_active
                 LIMIT 1
                """,
                (workflow, execution_mode),
            ).fetchone()
            if existing_stage is not None:
                return
            stage_code = ONE_SHOT_STAGE_CODES[workflow]
            stages = [
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
                        ) VALUES (%s, %s, %s, %s, 10, TRUE)
                        RETURNING workflow_stage_id
                        """,
                        (
                            workflow,
                            execution_mode,
                            stage_code,
                            f"Notebook {workflow} fixture",
                        ),
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
        for stage_number, stage in enumerate(stages, start=1):
            stage_id = stage["workflow_stage_id"]
            template_id = require_row(
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
                        stage_id,
                        context.tenant_id,
                        f"notebook_{workflow}_{stage_number}_{suffix}",
                        f"Notebook {workflow} fixture {stage_number} {suffix}",
                        context.principal_id,
                        context.principal_id,
                    ),
                ).fetchone()
            )["prompt_template_id"]
            version_id = require_row(
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
                        template_id,
                        stage_id,
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
                (stage_id, version_id, context.model_id, context.principal_id),
            )


def _create_notebook_profiling_run(
    actor: NotebookActor,
    context: WorkflowContext,
    *,
    correlation_id: UUID | None = None,
) -> dict[str, object]:
    with actor.database.connect_notebook_runtime() as connection:
        return require_row(
            connection.execute(
                CREATE_NOTEBOOK_PROFILING_SQL,
                (
                    context.tenant_id,
                    context.model_id,
                    context.model_revision,
                    list(context.selected_object_ids),
                    None,
                    correlation_id or uuid4(),
                ),
            ).fetchone()
        )


def _start_and_claim(
    actor: NotebookActor,
    context: WorkflowContext,
    workflow_run_id: int,
) -> dict[str, object] | None:
    with actor.database.connect_notebook_runtime() as connection:
        row = connection.execute(
            START_AND_CLAIM_SQL,
            (
                context.tenant_id,
                context.model_id,
                workflow_run_id,
                context.model_revision,
            ),
        ).fetchone()
    return None if row is None else dict(row)


def _start_without_claim(
    actor: NotebookActor,
    context: WorkflowContext,
    workflow_run_id: int,
) -> None:
    with actor.database.connect_owner() as connection:
        require_row(
            connection.execute(
                """
                SELECT *
                  FROM application.start_workflow_run(
                      %s::UUID,
                      %s::UUID,
                      'service_principal'::VARCHAR,
                      %s::BIGINT,
                      %s::BIGINT
                  )
                """,
                (
                    actor.entra_tenant_id,
                    actor.entra_object_id,
                    workflow_run_id,
                    context.model_revision,
                ),
            ).fetchone()
        )


def _expire_claim(
    actor: NotebookActor,
    workflow_run_id: int,
) -> None:
    with actor.database.connect_owner() as connection:
        connection.execute(
            """
            UPDATE application.workflow_run
               SET workflow_run_claimed_time =
                       clock_timestamp() - INTERVAL '3 minutes',
                   workflow_run_claim_heartbeat_time =
                       clock_timestamp() - INTERVAL '2 minutes',
                   workflow_run_claim_expires_time =
                       clock_timestamp() - INTERVAL '1 minute',
                   updated_time = clock_timestamp(),
                   updated_by = CURRENT_USER
             WHERE workflow_run_id = %s
            """,
            (workflow_run_id,),
        )


def test_notebook_create_is_idempotent_and_tenant_bound(
    notebook_actor: NotebookActor,
) -> None:
    context = _seed_notebook_tenant(notebook_actor)
    correlation_id = uuid4()

    created = _create_notebook_profiling_run(
        notebook_actor,
        context,
        correlation_id=correlation_id,
    )
    replayed = _create_notebook_profiling_run(
        notebook_actor,
        context,
        correlation_id=correlation_id,
    )

    assert created["created"] is True
    assert created["workflow_run_state"] == "queued"
    assert replayed["created"] is False
    assert replayed["workflow_run_id"] == created["workflow_run_id"]

    with notebook_actor.database.connect_notebook_runtime() as connection:
        wrong_workflow = connection.execute(
            """
            SELECT *
              FROM application.start_and_claim_notebook_workflow_run(
                  %s::BIGINT,
                  %s::BIGINT,
                  %s::BIGINT,
                  %s::BIGINT,
                  'analysis'::VARCHAR,
                  30::INTEGER
              )
            """,
            (
                context.tenant_id,
                context.model_id,
                created["workflow_run_id"],
                context.model_revision,
            ),
        ).fetchone()
        assert wrong_workflow is None

        with (
            pytest.raises(
                RaiseException,
                match="Workflow Run Tenant/Model binding is unavailable",
            ),
            connection.transaction(),
        ):
            connection.execute(
                CREATE_NOTEBOOK_PROFILING_SQL,
                (
                    9_223_372_036_854_775_000,
                    context.model_id,
                    context.model_revision,
                    list(context.selected_object_ids),
                    None,
                    uuid4(),
                ),
            ).fetchone()


def test_notebook_start_and_exact_claim_is_atomic_against_web_worker(
    notebook_actor: NotebookActor,
) -> None:
    context = _seed_notebook_tenant(notebook_actor)
    created = _create_notebook_profiling_run(notebook_actor, context)
    workflow_run_id = int(created["workflow_run_id"])
    barrier = Barrier(2)

    def notebook_claim() -> dict[str, object] | None:
        with notebook_actor.database.connect_notebook_runtime() as connection:
            barrier.wait(timeout=5)
            row = connection.execute(
                START_AND_CLAIM_SQL,
                (
                    context.tenant_id,
                    context.model_id,
                    workflow_run_id,
                    context.model_revision,
                ),
            ).fetchone()
        return None if row is None else dict(row)

    def web_claim() -> dict[str, object] | None:
        with psycopg.Connection[dict[str, object]].connect(
            notebook_actor.database.web_runtime_dsn(),
            row_factory=dict_row,
        ) as connection:
            connection.execute("SET ROLE gds_web_write")
            barrier.wait(timeout=5)
            row = connection.execute(
                "SELECT * FROM application.claim_next_workflow_run(30)"
            ).fetchone()
        return None if row is None else dict(row)

    with ThreadPoolExecutor(max_workers=2) as executor:
        notebook_future = executor.submit(notebook_claim)
        web_future = executor.submit(web_claim)
        claim = notebook_future.result(timeout=10)
        web_result = web_future.result(timeout=10)

    assert claim is not None
    assert claim["workflow_run_id"] == workflow_run_id
    assert claim["workflow_run_recovery_count"] == 0
    assert isinstance(claim["workflow_run_claim_token"], UUID)
    assert web_result is None or web_result["workflow_run_id"] != workflow_run_id

    with notebook_actor.database.connect_owner() as connection:
        stored = require_row(
            connection.execute(
                """
                SELECT workflow_run_state,
                       workflow_run_claim_token_digest,
                       workflow_run_claimed_time,
                       workflow_run_claim_expires_time
                  FROM application.workflow_run
                 WHERE workflow_run_id = %s
                """,
                (workflow_run_id,),
            ).fetchone()
        )
    assert stored["workflow_run_state"] == "running"
    assert isinstance(stored["workflow_run_claim_token_digest"], str)
    assert len(stored["workflow_run_claim_token_digest"]) == 64
    assert str(claim["workflow_run_claim_token"]) not in str(stored)


def test_notebook_exact_claim_recovers_only_its_requested_run_and_leases_are_bound(
    notebook_actor: NotebookActor,
) -> None:
    context = _seed_notebook_tenant(notebook_actor)
    created = _create_notebook_profiling_run(notebook_actor, context)
    workflow_run_id = int(created["workflow_run_id"])
    first = require_row(_start_and_claim(notebook_actor, context, workflow_run_id))
    first_token = first["workflow_run_claim_token"]
    assert isinstance(first_token, UUID)

    other_context = _seed_notebook_tenant(notebook_actor)
    other_created = _create_notebook_profiling_run(notebook_actor, other_context)
    other_run_id = int(other_created["workflow_run_id"])
    _start_without_claim(notebook_actor, other_context, other_run_id)

    assert _start_and_claim(notebook_actor, context, workflow_run_id) is None
    with notebook_actor.database.connect_owner() as connection:
        other_claim = require_row(
            connection.execute(
                """
                SELECT workflow_run_claim_token_digest
                  FROM application.workflow_run
                 WHERE workflow_run_id = %s
                """,
                (other_run_id,),
            ).fetchone()
        )
    assert other_claim == {"workflow_run_claim_token_digest": None}

    _expire_claim(notebook_actor, workflow_run_id)
    recovered = require_row(_start_and_claim(notebook_actor, context, workflow_run_id))
    recovered_token = recovered["workflow_run_claim_token"]
    assert isinstance(recovered_token, UUID)
    assert recovered_token != first_token
    assert recovered["workflow_run_recovery_count"] == 1

    with notebook_actor.database.connect_notebook_runtime() as connection:
        with (
            pytest.raises(RaiseException, match="claim is unavailable"),
            connection.transaction(),
        ):
            connection.execute(
                """
                SELECT application.assert_notebook_workflow_run_claim(
                    %s::BIGINT, %s::UUID
                )
                """,
                (workflow_run_id, first_token),
            ).fetchone()
        renewed = require_row(
            connection.execute(
                """
                SELECT *
                  FROM application.renew_notebook_workflow_run_claim(
                      %s::BIGINT, %s::UUID, 60::INTEGER
                  )
                """,
                (workflow_run_id, recovered_token),
            ).fetchone()
        )
        connection.execute(
            """
            SELECT application.assert_notebook_workflow_run_claim(
                %s::BIGINT, %s::UUID
            )
            """,
            (workflow_run_id, recovered_token),
        ).fetchone()
        released = require_row(
            connection.execute(
                """
                SELECT application.release_notebook_workflow_run_claim(
                    %s::BIGINT, %s::UUID
                ) AS released
                """,
                (workflow_run_id, recovered_token),
            ).fetchone()
        )
    assert renewed["workflow_run_id"] == workflow_run_id
    assert released == {"released": True}
    reclaimed = require_row(_start_and_claim(notebook_actor, context, workflow_run_id))
    assert reclaimed["workflow_run_claim_token"] != recovered_token
    assert reclaimed["workflow_run_recovery_count"] == 1

    user_context = seed_workflow_context(notebook_actor.database)
    with notebook_actor.database.connect_owner() as connection:
        user_created = require_row(
            connection.execute(
                """
                SELECT *
                  FROM application.create_workflow_run(
                      %s::UUID, %s::UUID, 'user'::VARCHAR,
                      %s::BIGINT, %s::BIGINT, 'profiling'::VARCHAR,
                      NULL::VARCHAR, NULL::VARCHAR, NULL::VARCHAR,
                      NULL::VARCHAR, NULL::VARCHAR, NULL::INTEGER,
                      NULL::INTEGER, %s::BIGINT[], NULL::VARCHAR,
                      NULL::VARCHAR, %s::UUID, '{}'::JSONB
                  )
                """,
                (
                    user_context.entra_tenant_id,
                    user_context.entra_object_id,
                    user_context.model_id,
                    user_context.model_revision,
                    list(user_context.selected_object_ids),
                    uuid4(),
                ),
            ).fetchone()
        )
        user_run_id = int(user_created["workflow_run_id"])
        connection.execute(
            """
            SELECT *
              FROM application.start_workflow_run(
                  %s::UUID, %s::UUID, 'user'::VARCHAR,
                  %s::BIGINT, %s::BIGINT
              )
            """,
            (
                user_context.entra_tenant_id,
                user_context.entra_object_id,
                user_run_id,
                user_context.model_revision,
            ),
        ).fetchone()
        user_token = uuid4()
        connection.execute(
            """
            UPDATE application.workflow_run
               SET workflow_run_claim_token_digest = encode(
                       sha256(convert_to(%s::UUID::TEXT, 'UTF8')),
                       'hex'
                   ),
                   workflow_run_claimed_time = clock_timestamp(),
                   workflow_run_claim_heartbeat_time = clock_timestamp(),
                   workflow_run_claim_expires_time =
                       clock_timestamp() + INTERVAL '5 minutes'
             WHERE workflow_run_id = %s
            """,
            (user_token, user_run_id),
        )

    with notebook_actor.database.connect_notebook_runtime() as connection:
        owner_mismatch = connection.execute(
            START_AND_CLAIM_SQL,
            (
                user_context.tenant_id,
                user_context.model_id,
                user_run_id,
                user_context.model_revision,
            ),
        ).fetchone()
        assert owner_mismatch is None
        with (
            pytest.raises(RaiseException, match="claim is unavailable"),
            connection.transaction(),
        ):
            connection.execute(
                """
                SELECT *
                  FROM application.renew_notebook_workflow_run_claim(
                      %s::BIGINT, %s::UUID, 30::INTEGER
                  )
                """,
                (user_run_id, user_token),
            ).fetchone()


@pytest.mark.parametrize(
    ("terminal_kind", "failure_code", "failure_message"),
    (
        (
            "invalid",
            "workflow_run_context_unavailable",
            "Workflow Run execution context is unavailable.",
        ),
        (
            "exhausted",
            "workflow_run_recovery_exhausted",
            "Workflow Run recovery limit exhausted.",
        ),
    ),
)
def test_notebook_exact_claim_terminalizes_only_its_invalid_or_exhausted_target_once(
    notebook_actor: NotebookActor,
    terminal_kind: str,
    failure_code: str,
    failure_message: str,
) -> None:
    context = _seed_notebook_tenant(notebook_actor)
    created = _create_notebook_profiling_run(notebook_actor, context)
    workflow_run_id = int(created["workflow_run_id"])

    if terminal_kind == "invalid":
        _start_without_claim(notebook_actor, context, workflow_run_id)
        with notebook_actor.database.connect_owner() as connection:
            connection.execute(
                """
                UPDATE model.model
                   SET is_active = FALSE
                 WHERE model_id = %s
                """,
                (context.model_id,),
            )
    else:
        claim = require_row(_start_and_claim(notebook_actor, context, workflow_run_id))
        assert claim["workflow_run_recovery_count"] == 0
        for expected_recovery_count in range(1, 6):
            _expire_claim(notebook_actor, workflow_run_id)
            claim = require_row(_start_and_claim(notebook_actor, context, workflow_run_id))
            assert claim["workflow_run_recovery_count"] == expected_recovery_count
        _expire_claim(notebook_actor, workflow_run_id)

    assert _start_and_claim(notebook_actor, context, workflow_run_id) is None
    assert _start_and_claim(notebook_actor, context, workflow_run_id) is None

    with notebook_actor.database.connect_owner() as connection:
        terminal = require_row(
            connection.execute(
                """
                SELECT run.workflow_run_state,
                       run.failure_code,
                       run.failure_message,
                       count(event.model_event_log_id)::INTEGER AS failed_events
                  FROM application.workflow_run AS run
                  LEFT JOIN model.model_event_log AS event
                    ON event.workflow_run_id = run.workflow_run_id
                   AND event.model_event_log_status = 'failed'
                 WHERE run.workflow_run_id = %s
                 GROUP BY run.workflow_run_id
                """,
                (workflow_run_id,),
            ).fetchone()
        )
    assert terminal == {
        "workflow_run_state": "failed",
        "failure_code": failure_code,
        "failure_message": failure_message,
        "failed_events": 1,
    }


@pytest.mark.parametrize(
    "shape",
    NOTEBOOK_WORKFLOW_SHAPES,
    ids=[shape.entrypoint for shape in NOTEBOOK_WORKFLOW_SHAPES],
)
def test_notebook_create_and_exact_claim_accept_every_entrypoint_shape(
    notebook_actor: NotebookActor,
    shape: NotebookWorkflowShape,
) -> None:
    context = seed_workflow_context(notebook_actor.database)
    selected_object_ids = list(context.selected_object_ids)
    modeled_entity_type = None
    requested_batch_id = (
        f"{shape.entrypoint}-batch" if shape.workflow in {"profiling", "analysis"} else None
    )
    mapping_operation = None
    mapping_coverage_mode = None
    mapping_artifact_type = None
    mapping_source_system_id = None
    code_generation_coverage_mode = None
    sql_generation_guide_version_id = None

    if shape.scope == "mapped_silver":
        target_id = _seed_code_generation_target(notebook_actor.database, context)
        selected_object_ids = [target_id]
        if shape.workflow == "mapping":
            with notebook_actor.database.connect_owner() as connection:
                mapping_source_system_id = require_row(
                    connection.execute(
                        """
                        SELECT source_connection.system_id
                          FROM core.object AS target_object
                          JOIN core.connection AS source_connection
                            ON source_connection.connection_id =
                               target_object.connection_id
                         WHERE target_object.object_id = %s
                        """,
                        (target_id,),
                    ).fetchone()
                )["system_id"]
            mapping_operation = "build"
            mapping_coverage_mode = "selected_targets"
            mapping_artifact_type = "sql_file"
        elif shape.workflow == "code_generation":
            modeled_entity_type = "logical_entity"
            code_generation_coverage_mode = "selected_targets"
            (
                _guide_id,
                sql_generation_guide_version_id,
                _guide_digest,
            ) = _seed_published_sql_generation_guide(
                notebook_actor.database,
                context,
                is_default=False,
            )

    if shape.is_agentic:
        _seed_missing_model_prompt_assignments(
            notebook_actor,
            context,
            workflow=shape.workflow,
            execution_mode=shape.execution_mode,
        )
        agent_configuration: tuple[object, ...] = (
            "langchain_create_agent",
            "databricks",
            "databricks-primary",
            "medium",
            10,
            2,
        )
    else:
        agent_configuration = (None, None, None, None, None, None)

    _bind_notebook_tenant_lock(notebook_actor, context)
    correlation_id = uuid4()
    with notebook_actor.database.connect_notebook_runtime() as connection:
        created = require_row(
            connection.execute(
                CREATE_NOTEBOOK_WORKFLOW_SQL,
                (
                    context.tenant_id,
                    context.model_id,
                    context.model_revision,
                    shape.workflow,
                    shape.execution_mode,
                    *agent_configuration,
                    selected_object_ids,
                    modeled_entity_type,
                    requested_batch_id,
                    correlation_id,
                    "{}",
                    mapping_operation,
                    mapping_coverage_mode,
                    mapping_artifact_type,
                    mapping_source_system_id,
                    None,
                    None,
                    code_generation_coverage_mode,
                    sql_generation_guide_version_id,
                ),
            ).fetchone()
        )
        claim = require_row(
            connection.execute(
                START_AND_CLAIM_WORKFLOW_SQL,
                (
                    context.tenant_id,
                    context.model_id,
                    created["workflow_run_id"],
                    context.model_revision,
                    shape.workflow,
                ),
            ).fetchone()
        )

    assert created["created"] is True
    assert created["workflow_run_state"] == "queued"
    assert created["correlation_id"] == correlation_id
    assert created["selected_scope_count"] == len(selected_object_ids)
    assert (created["prompt_snapshot_count"] > 0) is shape.is_agentic
    assert claim["workflow_run_id"] == created["workflow_run_id"]
    assert claim["tenant_id"] == context.tenant_id
    assert claim["model_id"] == context.model_id
    assert claim["model_revision"] == context.model_revision
    assert claim["model_workflow"] == shape.workflow
    assert claim["workflow_execution_mode"] == shape.execution_mode
    assert claim["correlation_id"] == correlation_id
    assert claim["actor_principal_type"] == "service_principal"
    assert claim["actor_entra_tenant_id"] == notebook_actor.entra_tenant_id
    assert claim["actor_entra_object_id"] == notebook_actor.entra_object_id
    assert isinstance(claim["workflow_run_claim_token"], UUID)
    assert claim["workflow_run_recovery_count"] == 0

    with notebook_actor.database.connect_owner() as connection:
        stored = require_row(
            connection.execute(
                """
                SELECT workflow_run_state,
                       agent_sdk_code,
                       agent_provider_code,
                       agent_model_code,
                       reasoning_effort_code,
                       max_turns,
                       validation_retry_count,
                       modeled_entity_type,
                       mapping_operation,
                       mapping_coverage_mode,
                       mapping_artifact_type,
                       code_generation_coverage_mode,
                       sql_generation_guide_version_id
                  FROM application.workflow_run
                 WHERE workflow_run_id = %s
                """,
                (created["workflow_run_id"],),
            ).fetchone()
        )
    assert stored["workflow_run_state"] == "running"
    assert (
        stored["agent_sdk_code"],
        stored["agent_provider_code"],
        stored["agent_model_code"],
        stored["reasoning_effort_code"],
        stored["max_turns"],
        stored["validation_retry_count"],
    ) == agent_configuration
    expected_modeled_entity_type = (
        "logical_entity" if shape.workflow == "mapping" else modeled_entity_type
    )
    assert stored["modeled_entity_type"] == expected_modeled_entity_type
    assert stored["mapping_operation"] == mapping_operation
    assert stored["mapping_coverage_mode"] == mapping_coverage_mode
    assert stored["mapping_artifact_type"] == mapping_artifact_type
    assert stored["code_generation_coverage_mode"] == code_generation_coverage_mode
    assert stored["sql_generation_guide_version_id"] == sql_generation_guide_version_id


def test_notebook_workflow_acl_is_wrapper_only_and_verified(
    notebook_actor: NotebookActor,
) -> None:
    allowed = (
        "application.create_notebook_workflow_run("
        "bigint,bigint,bigint,character varying,character varying,character varying,"
        "character varying,character varying,character varying,integer,integer,bigint[],"
        "character varying,character varying,uuid,jsonb,character varying,character varying,"
        "character varying,bigint,bigint,bigint,character varying,bigint)",
        "application.start_and_claim_notebook_workflow_run("
        "bigint,bigint,bigint,bigint,character varying,integer)",
        "application.renew_notebook_workflow_run_claim(bigint,uuid,integer)",
        "application.release_notebook_workflow_run_claim(bigint,uuid)",
        "application.assert_notebook_workflow_run_claim(bigint,uuid)",
    )
    forbidden = (
        "application.create_workflow_run("
        "uuid,uuid,character varying,bigint,bigint,character varying,character varying,"
        "character varying,character varying,character varying,character varying,integer,"
        "integer,bigint[],character varying,character varying,uuid,jsonb,character varying,"
        "character varying,character varying,bigint,bigint,bigint,character varying,bigint)",
        "application.start_workflow_run(uuid,uuid,character varying,bigint,bigint)",
        "application.claim_next_workflow_run(integer)",
        "application.claim_workflow_run_exact(bigint,character varying,integer)",
        "application.renew_workflow_run_claim(bigint,uuid,integer)",
        "application.release_workflow_run_claim(bigint,uuid)",
        "application.assert_workflow_run_claim(bigint,uuid)",
    )
    with notebook_actor.database.connect_owner() as connection:
        rows = connection.execute(
            """
            SELECT signature,
                   has_function_privilege(
                       'gds_notebook_runtime', signature, 'EXECUTE'
                   ) AS notebook_can_execute,
                   has_function_privilege(
                       'gds_web_write', signature, 'EXECUTE'
                   ) AS web_can_execute,
                   has_function_privilege(
                       'gds_app_write', signature, 'EXECUTE'
                   ) AS app_can_execute,
                   has_function_privilege(
                       'public', signature, 'EXECUTE'
                   ) AS public_can_execute
              FROM unnest(%s::TEXT[]) AS allowed_function(signature)
             ORDER BY signature
            """,
            (list(allowed),),
        ).fetchall()
        forbidden_rows = connection.execute(
            """
            SELECT signature,
                   has_function_privilege(
                       'gds_notebook_runtime', signature, 'EXECUTE'
                   ) AS notebook_can_execute
              FROM unnest(%s::TEXT[]) AS forbidden_function(signature)
             ORDER BY signature
            """,
            (list(forbidden),),
        ).fetchall()
        connection.execute(
            cast(
                LiteralString,
                VERIFY_INSTALL_SQL.read_text(encoding="utf-8"),
            )
        )

    assert rows == [
        {
            "signature": signature,
            "notebook_can_execute": True,
            "web_can_execute": False,
            "app_can_execute": False,
            "public_can_execute": False,
        }
        for signature in sorted(allowed)
    ]
    assert forbidden_rows == [
        {
            "signature": signature,
            "notebook_can_execute": False,
        }
        for signature in sorted(forbidden)
    ]

    with (
        notebook_actor.database.connect_notebook_runtime() as connection,
        pytest.raises(InsufficientPrivilege),
    ):
        connection.execute("SELECT workflow_run_id FROM application.workflow_run")

    with (
        notebook_actor.database.connect_notebook_runtime() as connection,
        pytest.raises(InsufficientPrivilege),
    ):
        connection.execute(
            """
            SELECT *
              FROM application.claim_workflow_run_exact(
                  1::BIGINT, 'profiling'::VARCHAR, 30::INTEGER
              )
            """
        ).fetchone()
