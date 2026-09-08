"""Metadata enrichment registration preserves governed scope and claim boundaries."""

# These tests reuse fixture-only workflow and notebook setup helpers.
# pyright: reportPrivateUsage=false

from dataclasses import replace
from typing import Any, LiteralString
from uuid import uuid4

import psycopg
import pytest
from psycopg.errors import RaiseException
from psycopg.rows import dict_row

from tests.mcp.database_test_support import require_row
from tests.mcp.test_database_notebook_workflows import (
    CREATE_NOTEBOOK_WORKFLOW_SQL,
    START_AND_CLAIM_WORKFLOW_SQL,
    NotebookActor,
    _bind_notebook_tenant_lock,
    _seed_missing_model_prompt_assignments,
    notebook_actor as notebook_actor,
)
from tests.mcp.test_database_workflow_run_lifecycle import (
    CREATE_WORKFLOW_RUN_SQL,
    WorkflowContext,
    _seed_model_input_scope_object_in_zone,
    create_workflow_run_parameters,
    seed_workflow_context,
)


def _context(actor: NotebookActor) -> WorkflowContext:
    context = seed_workflow_context(actor.database)
    # This disposable bootstrap fixture installs schema but not deployment seed files.
    with actor.database.connect_owner() as connection:
        connection.execute(
            """
            INSERT INTO application.workflow_stage (
                model_workflow, workflow_execution_mode, workflow_stage_code,
                workflow_stage_name, workflow_stage_order, workflow_stage_is_agentic
            ) SELECT workflow, 'one_shot', 'candidate_authoring',
                     'Metadata Enrichment', stage_order, TRUE
               FROM (VALUES ('metadata_enrichment_object', 10),
                            ('metadata_enrichment_attribute', 20)) AS stages(workflow, stage_order)
               WHERE NOT EXISTS (
                   SELECT 1 FROM application.workflow_stage
                    WHERE model_workflow = stages.workflow
                      AND workflow_execution_mode = 'one_shot'
               )
            """
        )
    for workflow in ("metadata_enrichment_object", "metadata_enrichment_attribute"):
        _seed_missing_model_prompt_assignments(
            actor, context, workflow=workflow, execution_mode="one_shot"
        )
    return context


def _create(
    actor: NotebookActor,
    context: WorkflowContext,
    **overrides: Any,
) -> dict[str, Any]:
    parameters = create_workflow_run_parameters(
        context, workflow="metadata_enrichment", **overrides
    )
    with psycopg.Connection[dict[str, Any]].connect(
        actor.database.web_runtime_dsn(), row_factory=dict_row
    ) as connection:
        connection.execute("SET LOCAL ROLE gds_web_write")
        return require_row(
            connection.execute(CREATE_WORKFLOW_RUN_SQL, parameters).fetchone()
        )


def _physical_snapshot(
    actor: NotebookActor, context: WorkflowContext
) -> dict[str, Any]:
    with actor.database.connect_owner() as connection:
        return require_row(
            connection.execute(
                """
                SELECT (SELECT jsonb_agg(to_jsonb(object) ORDER BY object.object_id)
                          FROM core.object AS object
                         WHERE object.source_tenant_id = %s) AS objects,
                       (SELECT jsonb_agg(to_jsonb(attribute) ORDER BY attribute.attribute_id)
                          FROM core.attribute AS attribute
                          JOIN core.object AS object USING (object_id)
                         WHERE object.source_tenant_id = %s) AS attributes
                """,
                (context.tenant_id, context.tenant_id),
            ).fetchone()
        )


@pytest.mark.parametrize("notebook", [False, True], ids=["web", "notebook_exact_claim"])
def test_enrichment_registers_locked_source_and_bronze_on_shared_placement_without_writes(
    notebook_actor: NotebookActor,
    notebook: bool,
) -> None:
    actor = notebook_actor
    context = _context(actor)
    source_id = _seed_model_input_scope_object_in_zone(
        actor.database, context, zone_code="source"
    )
    placement = seed_workflow_context(actor.database)
    with actor.database.connect_owner() as connection:
        connection.execute(
            """
            UPDATE core.connection SET tenant_id = %s, is_global_data_store = TRUE
             WHERE connection_id IN (
                 SELECT connection_id FROM core.object WHERE source_tenant_id = %s
             )
            """,
            (placement.tenant_id, context.tenant_id),
        )
        connection.execute(
            "UPDATE core.object SET is_locked = TRUE WHERE source_tenant_id = %s",
            (context.tenant_id,),
        )
        connection.execute(
            """
            INSERT INTO core.attribute (
                object_id, attribute_name, attribute_ordinal_position,
                attribute_data_type, attribute_inferred_data_type, is_locked
            ) SELECT object_id, 'identifier', 1, 'string', NULL, TRUE
                FROM core.object WHERE source_tenant_id = %s
            """,
            (context.tenant_id,),
        )
        connection.execute(
            "UPDATE model.model_input_scope SET model_input_scope_is_locked = TRUE WHERE model_id = %s",
            (context.model_id,),
        )
    selected = [source_id, *reversed(context.selected_object_ids)]
    before = _physical_snapshot(actor, context)
    correlation_id = uuid4()
    if notebook:
        _bind_notebook_tenant_lock(actor, context)
        with actor.database.connect_notebook_runtime() as connection:
            created = require_row(
                connection.execute(
                    CREATE_NOTEBOOK_WORKFLOW_SQL,
                    (
                        context.tenant_id,
                        context.model_id,
                        context.model_revision,
                        "metadata_enrichment",
                        "one_shot",
                        None,
                        None,
                        None,
                        None,
                        None,
                        None,
                        selected,
                        [],
                        None,
                        None,
                        correlation_id,
                        "{}",
                        None,
                        None,
                        None,
                        None,
                        None,
                        None,
                        None,
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
                        "metadata_enrichment",
                    ),
                ).fetchone()
            )
            assert claim["workflow_run_id"] == created["workflow_run_id"]
            assert claim["model_workflow"] == "metadata_enrichment"
            assert claim["workflow_execution_mode"] == "one_shot"
            assert claim["workflow_run_claim_token"] is not None
    else:
        created = _create(
            actor, context, correlation_id=correlation_id, selected_object_ids=selected
        )
        assert (
            _create(
                actor,
                context,
                correlation_id=correlation_id,
                selected_object_ids=selected,
            )["created"]
            is False
        )
    assert created["created"] is True
    assert created["selected_scope_count"] == len(selected)
    with actor.database.connect_owner() as connection:
        snapshot = connection.execute(
            """
            SELECT stage.workflow_stage_code
              FROM application.workflow_run_prompt_snapshot AS snapshot
              JOIN application.workflow_stage AS stage USING (workflow_stage_id)
             WHERE snapshot.workflow_run_id = %s
            """,
            (created["workflow_run_id"],),
        ).fetchall()
        assert snapshot == [{"workflow_stage_code": "candidate_authoring"}] * 2
        assert connection.execute(
            "SELECT object_id FROM application.workflow_run_object_selection WHERE workflow_run_id = %s ORDER BY selection_order",
            (created["workflow_run_id"],),
        ).fetchall() == [{"object_id": value} for value in sorted(selected)]
    assert _physical_snapshot(actor, context) == before


@pytest.mark.parametrize(
    "case",
    [
        "inactive_scope",
        "inactive_object",
        "outside_scope",
        "silver",
        "gold",
        "foreign_owner",
    ],
)
def test_enrichment_rejects_ineligible_scope_atomically(
    notebook_actor: NotebookActor,
    case: str,
) -> None:
    actor = notebook_actor
    context = _context(actor)
    object_id = context.selected_object_ids[0]
    if case in {"silver", "gold"}:
        object_id = _seed_model_input_scope_object_in_zone(
            actor.database, context, zone_code=case
        )
    elif case == "foreign_owner":
        foreign = seed_workflow_context(actor.database)
        with actor.database.connect_owner() as connection:
            connection.execute(
                "UPDATE core.object SET source_tenant_id = %s WHERE object_id = %s",
                (foreign.tenant_id, object_id),
            )
    else:
        statements: dict[str, LiteralString] = {
            "inactive_scope": "UPDATE model.model_input_scope SET is_active = FALSE WHERE model_id = %s AND object_id = %s",
            "inactive_object": "UPDATE core.object SET is_active = FALSE WHERE source_tenant_id = %s AND object_id = %s",
            "outside_scope": """INSERT INTO core.object (
                connection_id, source_tenant_id, object_schema, object_name, object_type_id, zone_id
            ) SELECT connection_id, source_tenant_id, object_schema, 'unscoped', object_type_id, zone_id
                FROM core.object WHERE source_tenant_id = %s AND object_id = %s RETURNING object_id""",
        }
        with actor.database.connect_owner() as connection:
            cursor = connection.execute(
                statements[case],
                (
                    context.model_id if case == "inactive_scope" else context.tenant_id,
                    object_id,
                ),
            )
            if case == "outside_scope":
                object_id = require_row(cursor.fetchone())["object_id"]
    correlation_id = uuid4()
    with pytest.raises(RaiseException):
        _create(
            actor,
            context,
            correlation_id=correlation_id,
            selected_object_ids=[object_id],
        )
    with actor.database.connect_owner() as connection:
        assert (
            connection.execute(
                "SELECT 1 FROM application.workflow_run WHERE correlation_id = %s",
                (correlation_id,),
            ).fetchone()
            is None
        )


@pytest.mark.parametrize("mode", [None, "tool_assisted"])
def test_enrichment_rejects_unsupported_execution_modes(
    notebook_actor: NotebookActor,
    mode: str | None,
) -> None:
    context = _context(notebook_actor)
    with pytest.raises(RaiseException):
        _create(notebook_actor, context, correlation_id=uuid4(), execution_mode=mode)


def test_enrichment_rejects_more_than_200_selected_objects(
    notebook_actor: NotebookActor,
) -> None:
    context = _context(notebook_actor)
    with pytest.raises(RaiseException, match="200"):
        _create(
            notebook_actor,
            context,
            correlation_id=uuid4(),
            selected_object_ids=list(range(1, 202)),
        )


@pytest.mark.parametrize("fence", ["revision", "identity", "role", "lock"])
def test_enrichment_registration_keeps_revision_identity_role_and_lock_fences(
    notebook_actor: NotebookActor,
    fence: str,
) -> None:
    actor = notebook_actor
    context = _context(actor)
    if fence == "revision":
        context = replace(context, model_revision=context.model_revision + 1)
    elif fence == "identity":
        context = replace(context, entra_object_id=uuid4())
    else:
        with actor.database.connect_owner() as connection:
            if fence == "role":
                connection.execute(
                    "UPDATE security.tenant_principal_access SET tenant_role = 'viewer' WHERE tenant_id = %s AND principal_id = %s",
                    (context.tenant_id, context.principal_id),
                )
            else:
                connection.execute(
                    "UPDATE security.tenant_lock SET tenant_lock_expires_time = clock_timestamp() - INTERVAL '1 second', tenant_lock_acquired_time = clock_timestamp() - INTERVAL '1 hour' WHERE tenant_id = %s",
                    (context.tenant_id,),
                )
    correlation_id = uuid4()
    with pytest.raises(RaiseException):
        _create(actor, context, correlation_id=correlation_id)
    with actor.database.connect_owner() as connection:
        assert (
            connection.execute(
                "SELECT 1 FROM application.workflow_run WHERE correlation_id = %s",
                (correlation_id,),
            ).fetchone()
            is None
        )
