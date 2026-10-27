"""Each layer's Subject Area list reports Build state and counts through the web role."""

# Fixture imports reuse only disposable databases and synthetic identities.
# pyright: reportPrivateUsage=false
from __future__ import annotations

from collections.abc import Mapping
from typing import Any
from uuid import uuid4

import psycopg
import pytest
from gds_etl_workbench.application.authorization import AuthorizationService
from gds_workbench_api.database import WebPostgresDatabase
from gds_workbench_api.features.dimensional import DatabaseDimensionalService
from gds_workbench_api.features.logical import DatabaseLogicalService, WaitingDraft

from tests.mcp.conftest import DisposablePostgres
from tests.mcp.test_database_project_change_set_round_trip import (
    ENTRA_OBJECT_ID,
    ENTRA_TENANT_ID,
    StaticIdentityProvider,
    _seed_project_foundation,
)


def _required_id(row: Mapping[str, object] | None, field: str) -> int:
    if row is None:
        raise AssertionError(f"expected database ID field {field}")
    value = row[field]
    if not isinstance(value, int) or isinstance(value, bool) or value <= 0:
        raise AssertionError(f"expected positive database ID field {field}")
    return value


def _insert_run(
    connection: psycopg.Connection[Any],
    *,
    tenant_id: int,
    project_id: int,
    actor: Mapping[str, object],
    workflow: str,
    operation: str,
    state: str,
    area_ids: tuple[int, ...] = (),
    draft: str | None = None,
) -> int:
    """Insert a Run in its final state, its area selection and, optionally, its draft."""
    terminal = state in ("completed", "failed", "cancelled")
    run_id = _required_id(
        connection.execute(
            """
            INSERT INTO application.workflow_run (
                tenant_id, project_id, project_revision, project_workflow,
                workflow_execution_mode, actor_principal_id, actor_entra_principal_identity_id,
                agent_sdk_code, agent_provider_code, agent_model_code, reasoning_effort_code,
                max_turns, validation_retry_count, selected_scope_digest, selected_scope_count,
                modeled_entity_type, workflow_operation, workflow_run_state, correlation_id,
                started_time, completed_time, failure_code, failure_message
            ) VALUES (
                %s, %s, 1, %s, 'one_shot', %s, %s, 'openai_agents_sdk', 'databricks',
                'test-project', 'medium', 8, 1, %s, 1, %s, %s, %s, %s,
                CURRENT_TIMESTAMP,
                CASE WHEN %s THEN CURRENT_TIMESTAMP END,
                CASE WHEN %s = 'failed' THEN 'agent_failed' END,
                CASE WHEN %s = 'failed' THEN 'The agent answer was invalid.' END
            )
            RETURNING workflow_run_id
            """,
            (
                tenant_id,
                project_id,
                workflow,
                actor["principal_id"],
                actor["entra_principal_identity_id"],
                "e" * 64,
                "logical_entity" if workflow == "dimensional" else None,
                operation,
                state,
                uuid4(),
                terminal,
                state,
                state,
            ),
        ).fetchone(),
        "workflow_run_id",
    )
    for order, area_id in enumerate(area_ids, start=1):
        connection.execute(
            "INSERT INTO application.workflow_run_subject_area_selection "
            "(workflow_run_id, project_id, subject_area_id, selection_order) "
            "VALUES (%s, %s, %s, %s)",
            (run_id, project_id, area_id, order),
        )
    if draft is not None:
        connection.execute(
            """
            INSERT INTO mcp.project_change_set (
                project_change_set_id, project_id, workflow_run_id, project_change_set_status,
                base_project_revision, base_source_context_digest, base_context_digest,
                base_policy_digest, candidate_digest, created_by_principal_id, correlation_id,
                validated_time, applied_time, terminal_time
            ) VALUES (
                %s, %s, %s, %s, 1, %s, %s, %s, %s, %s, %s,
                CURRENT_TIMESTAMP,
                CASE WHEN %s = 'applied' THEN CURRENT_TIMESTAMP END,
                CASE WHEN %s <> 'validated' THEN CURRENT_TIMESTAMP END
            )
            """,
            (
                uuid4(),
                project_id,
                run_id,
                draft,
                "1" * 64,
                "2" * 64,
                "3" * 64,
                "4" * 64,
                actor["principal_id"],
                uuid4(),
                draft,
                draft,
            ),
        )
    return run_id


@pytest.mark.asyncio
async def test_subject_area_lists_report_each_layers_build_state_and_counts(
    web_postgres_database: DisposablePostgres,
) -> None:
    fixture = web_postgres_database
    project_id, tenant_id = _seed_project_foundation(
        fixture, code_prefix=f"BUILD_STATUS_{uuid4().hex[:12]}"
    )
    with fixture.connect_owner() as connection:
        actor = connection.execute(
            """
            SELECT identity.principal_id, identity.entra_principal_identity_id
              FROM security.entra_principal_identity AS identity
             WHERE identity.entra_tenant_id = %s
               AND identity.entra_object_id = %s
            """,
            (ENTRA_TENANT_ID, ENTRA_OBJECT_ID),
        ).fetchone()
        assert actor is not None
        objects = {
            (row["object_schema"], row["object_name"]): row["object_id"]
            for row in connection.execute(
                "SELECT object_id, object_schema, object_name FROM core.object "
                "WHERE source_tenant_id = %s AND object_schema IN ('src', 'bronze')",
                (tenant_id,),
            ).fetchall()
        }
        customers, src_orders = objects[("src", "customers")], objects[("src", "orders")]
        bronze_orders = objects[("bronze", "orders")]
        for object_id in (customers, src_orders, bronze_orders):
            connection.execute(
                "INSERT INTO project.project_input_scope (project_id, object_id) VALUES (%s, %s)",
                (project_id, object_id),
            )

        def area(name: str, members: tuple[int, ...] = (), *, active: bool = True) -> int:
            area_id = _required_id(
                connection.execute(
                    "INSERT INTO workflow.subject_area (project_id, subject_area_name, "
                    "subject_area_definition, subject_area_is_active) VALUES (%s, %s, %s, %s) "
                    "RETURNING subject_area_id",
                    (project_id, name, f"{name} tables.", active),
                ).fetchone(),
                "subject_area_id",
            )
            for object_id in members:
                connection.execute(
                    "INSERT INTO workflow.subject_area_table (project_id, subject_area_id, "
                    "object_id) VALUES (%s, %s, %s)",
                    (project_id, area_id, object_id),
                )
            return area_id

        # Customers sit in Applied and Failed, so both share one Object; the inactive
        # Archive area holding Orders shares nothing.
        applied = area("Applied", (customers,))
        waiting = area("Waiting", (src_orders,))
        failed = area("Failed", (customers, bronze_orders))
        paused = area("Paused")
        discarded = area("Discarded")
        running = area("Running")
        area("Untouched")
        area("Archive", (src_orders,), active=False)

        # Only Customer is an active Logical Entity, sourced from customers; Dim Customer
        # reaches it through an active Logical source.
        customer = _required_id(
            connection.execute(
                "INSERT INTO workflow.logical_entity (project_id, logical_entity_schema_name, "
                "logical_entity_name, logical_entity_definition, logical_entity_type, "
                "logical_entity_grain) VALUES (%s, 'silver', 'Customer', 'A Customer.', "
                "'core', 'One Customer') RETURNING logical_entity_id",
                (project_id,),
            ).fetchone(),
            "logical_entity_id",
        )
        connection.execute(
            "INSERT INTO workflow.logical_entity_source_mapping (project_id, "
            "logical_entity_id, source_object_id) VALUES (%s, %s, %s)",
            (project_id, customer, customers),
        )
        dimension = _required_id(
            connection.execute(
                "INSERT INTO workflow.dimensional_entity (project_id, "
                "dimensional_entity_schema_name, dimensional_entity_name, "
                "dimensional_entity_definition, dimensional_entity_type) VALUES (%s, 'gold', "
                "'Dim Customer', 'Customer descriptors.', 'dimension') "
                "RETURNING dimensional_entity_id",
                (project_id,),
            ).fetchone(),
            "dimensional_entity_id",
        )
        connection.execute(
            "INSERT INTO workflow.dimensional_entity_source_mapping (project_id, "
            "dimensional_entity_id, source_logical_entity_id) VALUES (%s, %s, %s)",
            (project_id, dimension, customer),
        )

        def run(workflow: str, state: str, *areas: int, draft: str | None = None) -> int:
            return _insert_run(
                connection,
                tenant_id=tenant_id,
                project_id=project_id,
                actor=actor,
                workflow=workflow,
                operation="build",
                state=state,
                area_ids=areas,
                draft=draft,
            )

        applied_run = run("logical", "completed", applied, draft="applied")
        waiting_run = run("logical", "completed", waiting, draft="validated")
        # A newer failure decides even after an applied Build.
        run("logical", "completed", failed, draft="applied")
        failed_run = run("logical", "failed", failed)
        # A cancelled Build is skipped; the no-change Build before it decides.
        no_change_run = run("logical", "completed", paused)
        run("logical", "cancelled", paused)
        # A discarded draft is skipped, and nothing came before it.
        run("logical", "completed", discarded, draft="discarded")
        running_run = run("logical", "running", running)
        dimensional_run = run("dimensional", "completed", applied, draft="applied")

    database = WebPostgresDatabase(
        dsn=fixture.web_runtime_dsn(),
        pool_min=1,
        pool_max=1,
        pool_timeout_seconds=5,
    )
    authorizer = AuthorizationService()
    key = b"development-only-key-32-bytes-long"
    logical = DatabaseLogicalService(
        database=database, authorizer=authorizer, cursor_signing_key=key
    )
    dimensional = DatabaseDimensionalService(
        database=database, authorizer=authorizer, cursor_signing_key=key
    )
    principal = StaticIdentityProvider().request_principal(None)
    scope = {"tenant_id": tenant_id, "project_id": project_id}

    await database.open()
    try:
        logical_page = await logical.list_subject_areas(principal, **scope)
        dimensional_page = await dimensional.list_subject_areas(principal, **scope)
    finally:
        await database.close()

    assert [
        (
            item.subject_area_name,
            item.table_count,
            item.shared_table_count,
            item.build.state,
            item.build.workflow_run_id,
        )
        for item in logical_page.items
    ] == [
        ("Applied", 1, 1, "applied", applied_run),
        ("Discarded", 0, 0, "not_built", None),
        ("Failed", 2, 1, "failed", failed_run),
        ("Paused", 0, 0, "applied", no_change_run),
        ("Running", 0, 0, "running", running_run),
        ("Untouched", 0, 0, "not_built", None),
        ("Waiting", 1, 0, "draft_waiting", waiting_run),
    ]
    assert all(
        (item.build.at is None) == (item.build.state == "not_built") for item in logical_page.items
    )
    assert logical_page.waiting_draft == WaitingDraft(
        workflow_run_id=waiting_run, workflow_operation="build"
    )
    assert {item.subject_area_id for item in logical_page.items} >= {
        applied,
        waiting,
        failed,
        paused,
        discarded,
        running,
    }

    # Dimensional reads its own Builds.
    assert [
        (
            item.subject_area_name,
            item.build.state,
            item.build.workflow_run_id,
        )
        for item in dimensional_page.items
    ] == [
        ("Applied", "applied", dimensional_run),
        ("Discarded", "not_built", None),
        ("Failed", "not_built", None),
        ("Paused", "not_built", None),
        ("Running", "not_built", None),
        ("Untouched", "not_built", None),
        ("Waiting", "not_built", None),
    ]
    assert dimensional_page.waiting_draft is None
