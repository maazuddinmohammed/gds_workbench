from __future__ import annotations

# pyright: reportPrivateUsage=false
from typing import TYPE_CHECKING
from uuid import uuid4

import pytest
from database_test_support import require_row
from psycopg.errors import RaiseException
from test_database_workflow_run_lifecycle import (
    CREATE_WORKFLOW_RUN_SQL,
    create_workflow_run_parameters,
    seed_workflow_context,
)

if TYPE_CHECKING:
    from conftest import DisposablePostgres


COMPLETE_AUTHORING_NO_OP_SQL = """
    SELECT *
      FROM application.complete_authoring_workflow_run_no_op(
          %s::UUID,
          %s::UUID,
          'user'::VARCHAR,
          %s::BIGINT,
          %s::BIGINT,
          %s::BIGINT,
          %s::VARCHAR,
          %s::VARCHAR,
          %s::UUID,
          %s::BIGINT,
          %s::CHAR(64),
          %s::BIGINT,
          %s::INTEGER,
          %s::VARCHAR,
          %s::VARCHAR,
          %s::VARCHAR,
          %s::INTEGER,
          %s::INTEGER,
          %s::INTEGER
      )
"""


def test_authoring_no_op_is_atomic_revision_stable_and_exactly_replayable(
    postgres_database: DisposablePostgres,
) -> None:
    context = seed_workflow_context(postgres_database)
    correlation_id = uuid4()
    candidate_digest = "c" * 64

    with postgres_database.connect_owner() as connection:
        created = require_row(
            connection.execute(
                CREATE_WORKFLOW_RUN_SQL,
                create_workflow_run_parameters(context, correlation_id=correlation_id),
            ).fetchone()
        )
        workflow_run_id = created["workflow_run_id"]
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
        )
        connection.execute(
            """
            SELECT *
              FROM application.append_workflow_run_event(
                  %s::UUID, %s::UUID, 'user'::VARCHAR,
                  %s::BIGINT, %s::BIGINT, 2::BIGINT, 1::INTEGER,
                  'conceptual.candidate_authoring'::VARCHAR,
                  'running'::VARCHAR, 'Conceptual authoring started.'::VARCHAR,
                  0::INTEGER, 1::INTEGER, 0::INTEGER
              )
            """,
            (
                context.entra_tenant_id,
                context.entra_object_id,
                workflow_run_id,
                context.model_revision,
            ),
        )
        parameters = (
            context.entra_tenant_id,
            context.entra_object_id,
            context.tenant_id,
            context.model_id,
            workflow_run_id,
            "conceptual",
            "one_shot",
            correlation_id,
            context.model_revision,
            candidate_digest,
            3,
            1,
            "conceptual.backend_validation",
            "running",
            "Conceptual authoring completed with no effective change.",
            1,
            1,
            0,
        )
        other_entra_tenant_id = uuid4()
        other_entra_object_id = uuid4()
        other_principal_id = require_row(
            connection.execute(
                """
                INSERT INTO security.principal (
                    principal_type, principal_display_name, principal_email
                ) VALUES ('user', 'Other no-op actor', %s)
                RETURNING principal_id
                """,
                (f"other-no-op-{uuid4().hex}@example.test",),
            ).fetchone()
        )["principal_id"]
        connection.execute(
            """
            INSERT INTO security.entra_principal_identity (
                principal_id, principal_type, entra_tenant_id, entra_object_id
            ) VALUES (%s, 'user', %s, %s)
            """,
            (other_principal_id, other_entra_tenant_id, other_entra_object_id),
        )
        connection.execute(
            """
            INSERT INTO security.tenant_principal_access (
                tenant_id, principal_id, tenant_role, granted_by_principal_id
            ) VALUES (%s, %s, 'architect', %s)
            """,
            (context.tenant_id, other_principal_id, context.principal_id),
        )
        connection.execute(
            """
            UPDATE security.tenant_lock
               SET locked_by_principal_id = %s
             WHERE tenant_id = %s
            """,
            (other_principal_id, context.tenant_id),
        )
        with (
            pytest.raises(RaiseException, match="another Principal"),
            connection.transaction(),
        ):
            connection.execute(
                COMPLETE_AUTHORING_NO_OP_SQL,
                (other_entra_tenant_id, other_entra_object_id, *parameters[2:]),
            )
        connection.execute(
            """
            UPDATE security.tenant_lock
               SET locked_by_principal_id = %s
             WHERE tenant_id = %s
            """,
            (context.principal_id, context.tenant_id),
        )
        receipt = require_row(
            connection.execute(COMPLETE_AUTHORING_NO_OP_SQL, parameters).fetchone()
        )
        replay = require_row(
            connection.execute(COMPLETE_AUTHORING_NO_OP_SQL, parameters).fetchone()
        )

        mismatches: list[tuple[object, ...]] = []
        for index, value in (
            (2, context.tenant_id + 10_000),
            (3, context.model_id + 10_000),
            (5, "logical"),
            (6, "tool_assisted"),
            (7, uuid4()),
            (8, context.model_revision + 1),
            (9, "d" * 64),
            (10, 4),
            (11, 2),
            (12, "conceptual.other_validation"),
            (13, "warning"),
            (14, "Different safe final message."),
            (15, 0),
        ):
            mismatch_values: list[object] = list(parameters)
            mismatch_values[index] = value
            mismatches.append(tuple(mismatch_values))
        for mismatch_parameters in mismatches:
            with (
                pytest.raises(RaiseException, match="conflict"),
                connection.transaction(),
            ):
                connection.execute(
                    COMPLETE_AUTHORING_NO_OP_SQL,
                    mismatch_parameters,
                )

        missing_run = list(parameters)
        missing_run[4] = workflow_run_id + 10_000
        with (
            pytest.raises(RaiseException, match="unavailable"),
            connection.transaction(),
        ):
            connection.execute(COMPLETE_AUTHORING_NO_OP_SQL, tuple(missing_run))

        with (
            pytest.raises(RaiseException, match="durable authoring outcome"),
            connection.transaction(),
        ):
            connection.execute(
                """
                SELECT *
                  FROM application.fail_workflow_run(
                      %s::UUID, %s::UUID, 'user'::VARCHAR,
                      %s::BIGINT, %s::BIGINT,
                      'unexpected_failure'::VARCHAR,
                      'Safe failure.'::VARCHAR
                  )
                """,
                (
                    context.entra_tenant_id,
                    context.entra_object_id,
                    workflow_run_id,
                    context.model_revision,
                ),
            )

        stored = require_row(
            connection.execute(
                """
                SELECT run.workflow_run_state,
                       run.authoring_no_op_base_model_revision,
                       run.authoring_no_op_candidate_digest,
                       run.authoring_no_op_model_event_log_id,
                       target_model.model_revision,
                       count(change_set.model_change_set_id) AS change_set_count
                  FROM application.workflow_run AS run
                  JOIN model.model AS target_model
                    ON target_model.model_id = run.model_id
                  LEFT JOIN mcp.model_change_set AS change_set
                    ON change_set.workflow_run_id = run.workflow_run_id
                 WHERE run.workflow_run_id = %s
                 GROUP BY run.workflow_run_state,
                          run.authoring_no_op_base_model_revision,
                          run.authoring_no_op_candidate_digest,
                          run.authoring_no_op_model_event_log_id,
                          target_model.model_revision
                """,
                (workflow_run_id,),
            ).fetchone()
        )
        final_event = require_row(
            connection.execute(
                """
                SELECT model_event_log_sequence AS final_event_sequence,
                       model_event_log_attempt AS final_event_attempt,
                       model_event_log_stage AS final_event_stage,
                       model_event_log_status AS final_event_status,
                       model_event_log_message AS final_event_message,
                       model_event_log_current AS final_event_current,
                       model_event_log_total AS final_event_total,
                       model_event_log_percent AS final_event_percent,
                       finding_count AS final_finding_count
                  FROM model.model_event_log
                 WHERE model_event_log_id = %s
                """,
                (stored["authoring_no_op_model_event_log_id"],),
            ).fetchone()
        )

    assert receipt["changed"] is True
    assert replay["changed"] is False
    assert replay == receipt | {"changed": False}
    assert receipt["workflow_run_state"] == "completed"
    assert receipt["model_revision"] == context.model_revision
    assert receipt["candidate_digest"] == candidate_digest
    assert stored == {
        "workflow_run_state": "completed",
        "authoring_no_op_base_model_revision": context.model_revision,
        "authoring_no_op_candidate_digest": candidate_digest,
        "authoring_no_op_model_event_log_id": stored[
            "authoring_no_op_model_event_log_id"
        ],
        "model_revision": context.model_revision,
        "change_set_count": 0,
    }
    assert isinstance(stored["authoring_no_op_model_event_log_id"], int)
    assert final_event == {
        "final_event_sequence": 3,
        "final_event_attempt": 1,
        "final_event_stage": "conceptual.backend_validation",
        "final_event_status": "running",
        "final_event_message": (
            "Conceptual authoring completed with no effective change."
        ),
        "final_event_current": 1,
        "final_event_total": 1,
        "final_event_percent": 100,
        "final_finding_count": 0,
    }


def test_authoring_no_op_persists_repaired_backend_event_and_derives_state(
    postgres_database: DisposablePostgres,
) -> None:
    context = seed_workflow_context(postgres_database)
    correlation_id = uuid4()

    with postgres_database.connect_owner() as connection:
        workflow_run_id = require_row(
            connection.execute(
                CREATE_WORKFLOW_RUN_SQL,
                create_workflow_run_parameters(context, correlation_id=correlation_id),
            ).fetchone()
        )["workflow_run_id"]
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
        )
        connection.execute(
            """
            SELECT *
              FROM application.append_workflow_run_event(
                  %s::UUID, %s::UUID, 'user'::VARCHAR,
                  %s::BIGINT, %s::BIGINT, 2::BIGINT, 1::INTEGER,
                  'conceptual.candidate_authoring'::VARCHAR,
                  'running'::VARCHAR, 'Conceptual authoring started.'::VARCHAR,
                  0::INTEGER, 1::INTEGER, 0::INTEGER
              )
            """,
            (
                context.entra_tenant_id,
                context.entra_object_id,
                workflow_run_id,
                context.model_revision,
            ),
        )
        receipt = require_row(
            connection.execute(
                COMPLETE_AUTHORING_NO_OP_SQL,
                (
                    context.entra_tenant_id,
                    context.entra_object_id,
                    context.tenant_id,
                    context.model_id,
                    workflow_run_id,
                    "conceptual",
                    "one_shot",
                    correlation_id,
                    context.model_revision,
                    "e" * 64,
                    3,
                    2,
                    "conceptual.backend_validation",
                    "warning",
                    "Conceptual repair completed with no effective change.",
                    1,
                    1,
                    0,
                ),
            ).fetchone()
        )
        stored_event = require_row(
            connection.execute(
                """
                SELECT event.model_event_log_sequence,
                       event.model_event_log_attempt,
                       event.model_event_log_stage,
                       event.model_event_log_status,
                       event.model_event_log_message,
                       event.model_event_log_current,
                       event.model_event_log_total,
                       event.finding_count
                  FROM application.workflow_run AS run
                  JOIN model.model_event_log AS event
                    ON event.model_event_log_id =
                       run.authoring_no_op_model_event_log_id
                 WHERE run.workflow_run_id = %s
                """,
                (workflow_run_id,),
            ).fetchone()
        )

    assert receipt["workflow_run_state"] == "completed_with_repair"
    assert receipt["final_event_attempt"] == 2
    assert receipt["final_event_status"] == "warning"
    assert stored_event == {
        "model_event_log_sequence": 3,
        "model_event_log_attempt": 2,
        "model_event_log_stage": "conceptual.backend_validation",
        "model_event_log_status": "warning",
        "model_event_log_message": (
            "Conceptual repair completed with no effective change."
        ),
        "model_event_log_current": 1,
        "model_event_log_total": 1,
        "finding_count": 0,
    }


def test_existing_draft_blocks_no_op_and_durable_draft_blocks_failure(
    postgres_database: DisposablePostgres,
) -> None:
    context = seed_workflow_context(postgres_database)
    correlation_id = uuid4()

    with postgres_database.connect_owner() as connection:
        workflow_run_id = require_row(
            connection.execute(
                CREATE_WORKFLOW_RUN_SQL,
                create_workflow_run_parameters(context, correlation_id=correlation_id),
            ).fetchone()
        )["workflow_run_id"]
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
        )
        change_set_id = uuid4()
        connection.execute(
            """
            INSERT INTO mcp.model_change_set (
                model_change_set_id,
                model_id,
                workflow_run_id,
                base_model_revision,
                base_source_context_digest,
                base_assertion_digest,
                base_policy_digest,
                created_by_principal_id,
                correlation_id
            ) VALUES (
                %s, %s, %s, %s, %s, %s, %s, %s, %s
            )
            """,
            (
                change_set_id,
                context.model_id,
                workflow_run_id,
                context.model_revision,
                "1" * 64,
                "2" * 64,
                "3" * 64,
                context.principal_id,
                correlation_id,
            ),
        )
        no_op_parameters = (
            context.entra_tenant_id,
            context.entra_object_id,
            context.tenant_id,
            context.model_id,
            workflow_run_id,
            "conceptual",
            "one_shot",
            correlation_id,
            context.model_revision,
            "f" * 64,
            2,
            1,
            "conceptual.backend_validation",
            "running",
            "Conceptual authoring completed with no effective change.",
            1,
            1,
            0,
        )
        with (
            pytest.raises(RaiseException, match="requires no Model Change Set"),
            connection.transaction(),
        ):
            connection.execute(COMPLETE_AUTHORING_NO_OP_SQL, no_op_parameters)

        connection.execute(
            """
            UPDATE mcp.model_change_set
               SET model_change_set_status = 'validated',
                   candidate_digest = %s,
                   validation_outcome = '{}'::JSONB,
                   validated_time = CURRENT_TIMESTAMP
             WHERE model_change_set_id = %s
            """,
            ("a" * 64, change_set_id),
        )
        failure_sql = """
            SELECT *
              FROM application.fail_workflow_run(
                  %s::UUID, %s::UUID, 'user'::VARCHAR,
                  %s::BIGINT, %s::BIGINT,
                  'unexpected_failure'::VARCHAR, 'Safe failure.'::VARCHAR
              )
        """
        failure_parameters = (
            context.entra_tenant_id,
            context.entra_object_id,
            workflow_run_id,
            context.model_revision,
        )
        for status in ("validated", "applied"):
            if status == "applied":
                connection.execute(
                    """
                    UPDATE mcp.model_change_set
                       SET model_change_set_status = 'applied',
                           applied_time = CURRENT_TIMESTAMP,
                           terminal_time = CURRENT_TIMESTAMP
                     WHERE model_change_set_id = %s
                    """,
                    (change_set_id,),
                )
            with (
                pytest.raises(RaiseException, match="durable authoring outcome"),
                connection.transaction(),
            ):
                connection.execute(failure_sql, failure_parameters)

        stored = require_row(
            connection.execute(
                """
                SELECT run.workflow_run_state,
                       run.failure_code,
                       run.authoring_no_op_candidate_digest,
                       target_model.model_revision,
                       count(event.model_event_log_id) AS event_count
                  FROM application.workflow_run AS run
                  JOIN model.model AS target_model
                    ON target_model.model_id = run.model_id
                  JOIN model.model_event_log AS event
                    ON event.workflow_run_id = run.workflow_run_id
                 WHERE run.workflow_run_id = %s
                 GROUP BY run.workflow_run_state,
                          run.failure_code,
                          run.authoring_no_op_candidate_digest,
                          target_model.model_revision
                """,
                (workflow_run_id,),
            ).fetchone()
        )

    assert stored == {
        "workflow_run_state": "running",
        "failure_code": None,
        "authoring_no_op_candidate_digest": None,
        "model_revision": context.model_revision,
        "event_count": 1,
    }
