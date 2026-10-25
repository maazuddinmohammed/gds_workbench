"""Manual Subject Area saves and Subject Area run selection on a disposable database."""

# Fixture imports reuse only disposable databases and synthetic identities.
# pyright: reportPrivateUsage=false
from uuid import UUID, uuid4

import pytest
from gds_etl_workbench.application.authorization import AuthorizationService
from gds_etl_workbench.domain.authorization import ActorKind, RequestPrincipal
from gds_etl_workbench.domain.errors import InvalidRequestError, WorkbenchError
from gds_workbench_api.capabilities import load_default_agent_capabilities
from gds_workbench_api.database import WebPostgresDatabase
from gds_workbench_api.features.project_change_sets.contracts import (
    ReviewProjectRecordsResult,
    SaveSubjectAreaRequest,
)
from gds_workbench_api.features.project_change_sets.service import (
    DatabaseProjectChangeSetService,
)
from gds_workbench_api.features.projects import ProjectRevisionConflictError
from gds_workbench_api.features.workflows.commands import (
    CreateWorkflowRunRequest,
    DatabaseWorkflowCommandService,
)

from tests.mcp.conftest import DisposablePostgres
from tests.mcp.database_test_support import require_row
from tests.mcp.test_database_workflow_run_lifecycle import (
    WorkflowContext,
    _seed_project_input_scope_object_in_zone,
    seed_workflow_context,
)

_DEFINITION = "Orders and the customers who place them."


async def _save(
    runtime: WebPostgresDatabase,
    context: WorkflowContext,
    command: SaveSubjectAreaRequest,
    key: UUID | None = None,
) -> ReviewProjectRecordsResult:
    """Save as the seeded architect, who holds the Tenant Lock."""
    return await DatabaseProjectChangeSetService(
        database=runtime, authorizer=AuthorizationService()
    ).save_subject_area(
        RequestPrincipal(
            actor_kind=ActorKind.HUMAN,
            entra_tenant_id=context.entra_tenant_id,
            entra_object_id=context.entra_object_id,
        ),
        tenant_id=context.tenant_id,
        project_id=context.project_id,
        command=command,
        idempotency_key=key or uuid4(),
    )


async def _rejected(
    runtime: WebPostgresDatabase,
    context: WorkflowContext,
    command: SaveSubjectAreaRequest,
    key: UUID | None = None,
) -> str:
    with pytest.raises(WorkbenchError) as error:
        await _save(runtime, context, command, key)
    return error.value.code


async def test_subject_area_saves_create_regroup_and_rename_without_deleting(
    web_postgres_database: DisposablePostgres,
) -> None:
    database = web_postgres_database
    # Three active Bronze Scope tables and a held Tenant Lock.
    context = seed_workflow_context(database)
    orders, customers, payments = context.selected_object_ids
    source_table = _seed_project_input_scope_object_in_zone(database, context, zone_code="source")
    with database.connect_owner() as connection:
        outside_scope = require_row(
            connection.execute(
                "INSERT INTO core.object (connection_id, source_tenant_id, object_schema, "
                "object_name, object_type_id, zone_id) "
                "SELECT connection_id, source_tenant_id, object_schema, 'outside_scope', "
                "object_type_id, zone_id FROM core.object WHERE object_id = %s "
                "RETURNING object_id",
                (orders,),
            ).fetchone()
        )["object_id"]

    def area_id(name: str) -> int:
        with database.connect_owner() as connection:
            return require_row(
                connection.execute(
                    "SELECT subject_area_id FROM workflow.subject_area "
                    "WHERE project_id = %s AND subject_area_name = %s",
                    (context.project_id, name),
                ).fetchone()
            )["subject_area_id"]

    runtime = WebPostgresDatabase(
        dsn=database.web_runtime_dsn(), pool_min=1, pool_max=1, pool_timeout_seconds=5
    )
    await runtime.open()
    try:
        created = await _save(
            runtime,
            context,
            SaveSubjectAreaRequest(
                expected_project_revision=1,
                subject_area_name="Sales",
                subject_area_definition=_DEFINITION,
                add_object_ids=[orders, customers],
            ),
        )
        with pytest.raises(ProjectRevisionConflictError):
            await _save(
                runtime,
                context,
                SaveSubjectAreaRequest(
                    expected_project_revision=1,
                    subject_area_name="Support",
                    subject_area_definition="Customer support cases.",
                ),
            )
        assert (
            await _rejected(
                runtime,
                context,
                SaveSubjectAreaRequest(
                    expected_project_revision=2,
                    subject_area_name="SALES",
                    subject_area_definition="A second sales area.",
                ),
            )
            == "subject_area_name_conflict"
        )
        sales_id = area_id("Sales")
        # Only active Bronze Input Scope tables can join an area.
        for unavailable in (source_table, outside_scope):
            assert (
                await _rejected(
                    runtime,
                    context,
                    SaveSubjectAreaRequest(
                        expected_project_revision=2,
                        subject_area_id=sales_id,
                        add_object_ids=[unavailable],
                    ),
                )
                == "subject_area_table_unavailable"
            )
        removed = await _save(
            runtime,
            context,
            SaveSubjectAreaRequest(
                expected_project_revision=2,
                subject_area_id=sales_id,
                remove_object_ids=[customers],
            ),
        )
        with database.connect_owner() as connection:
            after_removal = connection.execute(
                "SELECT object_id, subject_area_table_status FROM workflow.subject_area_table "
                "WHERE subject_area_id = %s ORDER BY object_id",
                (sales_id,),
            ).fetchall()
        added = await _save(
            runtime,
            context,
            SaveSubjectAreaRequest(
                expected_project_revision=3,
                subject_area_id=sales_id,
                add_object_ids=[customers, payments],
            ),
        )
        # A rename keeps the old area and its memberships as inactive history.
        renamed = await _save(
            runtime,
            context,
            SaveSubjectAreaRequest(
                expected_project_revision=4,
                subject_area_id=sales_id,
                subject_area_name="Commerce",
            ),
        )
        assert (
            await _rejected(
                runtime,
                context,
                SaveSubjectAreaRequest(
                    expected_project_revision=5,
                    subject_area_name="sales",
                    subject_area_definition="Reuses a retired name.",
                ),
            )
            == "subject_area_name_conflict"
        )
        commerce_id = area_id("Commerce")
        with database.connect_owner() as connection:
            connection.execute(
                "UPDATE workflow.subject_area SET subject_area_is_locked = TRUE "
                "WHERE subject_area_id = %s",
                (commerce_id,),
            )
        assert (
            await _rejected(
                runtime,
                context,
                SaveSubjectAreaRequest(
                    expected_project_revision=5,
                    subject_area_id=commerce_id,
                    subject_area_definition="Edits a locked area.",
                ),
            )
            == "record_locked"
        )
    finally:
        await runtime.close()

    assert (created.project_revision, created.action_count) == (2, 3)
    assert [result.project_revision for result in (removed, added, renamed)] == [3, 4, 5]
    assert after_removal == [
        {"object_id": orders, "subject_area_table_status": "active"},
        {"object_id": customers, "subject_area_table_status": "inactive"},
    ]
    with database.connect_owner() as connection:
        areas = connection.execute(
            "SELECT subject_area_id, subject_area_name, subject_area_definition, "
            "subject_area_status, workflow_run_id FROM workflow.subject_area "
            "WHERE project_id = %s ORDER BY subject_area_id",
            (context.project_id,),
        ).fetchall()
        memberships = connection.execute(
            "SELECT area.subject_area_name, membership.object_id, "
            "membership.subject_area_table_status "
            "FROM workflow.subject_area_table AS membership "
            "JOIN workflow.subject_area AS area USING (subject_area_id) "
            "WHERE membership.project_id = %s "
            "ORDER BY area.subject_area_id, membership.object_id",
            (context.project_id,),
        ).fetchall()
    assert areas == [
        {
            "subject_area_id": sales_id,
            "subject_area_name": "Sales",
            "subject_area_definition": _DEFINITION,
            "subject_area_status": "inactive",
            "workflow_run_id": None,
        },
        {
            "subject_area_id": commerce_id,
            "subject_area_name": "Commerce",
            "subject_area_definition": _DEFINITION,
            "subject_area_status": "active",
            "workflow_run_id": None,
        },
    ]
    # Re-adding customers reactivated its one Sales membership row before the rename.
    assert memberships == [
        {"subject_area_name": name, "object_id": table, "subject_area_table_status": status}
        for name, status in (("Sales", "inactive"), ("Commerce", "active"))
        for table in (orders, customers, payments)
    ]


async def test_subject_area_save_replays_its_key_and_rejects_a_different_body(
    web_postgres_database: DisposablePostgres,
) -> None:
    database = web_postgres_database
    context = seed_workflow_context(database)
    command = SaveSubjectAreaRequest(
        expected_project_revision=1,
        subject_area_name="Sales",
        subject_area_definition=_DEFINITION,
        add_object_ids=list(context.selected_object_ids),
    )
    key = uuid4()
    runtime = WebPostgresDatabase(
        dsn=database.web_runtime_dsn(), pool_min=1, pool_max=1, pool_timeout_seconds=5
    )
    await runtime.open()
    try:
        created = await _save(runtime, context, command, key)
        replayed = await _save(runtime, context, command, key)
        conflict = await _rejected(
            runtime,
            context,
            command.model_copy(update={"subject_area_definition": "Another body."}),
            key,
        )
    finally:
        await runtime.close()

    assert created.project_revision == 2
    assert replayed == created
    assert conflict == "review_conflict"


async def test_subject_area_run_must_select_the_whole_active_bronze_scope(
    web_postgres_database: DisposablePostgres,
) -> None:
    database = web_postgres_database
    # Three active Bronze Scope tables, Subject Area prompts and a held Tenant Lock.
    context = seed_workflow_context(database)
    source_table = _seed_project_input_scope_object_in_zone(database, context, zone_code="source")
    principal = RequestPrincipal(
        actor_kind=ActorKind.HUMAN,
        entra_tenant_id=context.entra_tenant_id,
        entra_object_id=context.entra_object_id,
    )
    runtime = WebPostgresDatabase(
        dsn=database.web_runtime_dsn(), pool_min=1, pool_max=1, pool_timeout_seconds=5
    )
    commands = DatabaseWorkflowCommandService(
        database=runtime,
        authorizer=AuthorizationService(),
        agent_capability_registry=load_default_agent_capabilities(),
    )

    def selecting(object_ids: list[int]) -> CreateWorkflowRunRequest:
        return CreateWorkflowRunRequest(
            expected_project_revision=context.project_revision,
            project_workflow="subject_area",
            workflow_execution_mode="one_shot",
            selected_object_ids=object_ids,
        )

    await runtime.open()
    try:
        for selection in (
            list(context.selected_object_ids[:2]),
            [*context.selected_object_ids, source_table],
        ):
            with pytest.raises(InvalidRequestError):
                await commands.create_run(
                    principal,
                    tenant_id=context.tenant_id,
                    project_id=context.project_id,
                    correlation_id=uuid4(),
                    command=selecting(selection),
                )
        created = await commands.create_run(
            principal,
            tenant_id=context.tenant_id,
            project_id=context.project_id,
            correlation_id=uuid4(),
            command=selecting(list(reversed(context.selected_object_ids))),
        )
    finally:
        await runtime.close()

    assert created.created and created.workflow_run_state == "queued"
    assert created.selected_scope_count == len(context.selected_object_ids)
    with database.connect_owner() as connection:
        runs = connection.execute(
            "SELECT workflow_run_id FROM application.workflow_run WHERE project_id = %s",
            (context.project_id,),
        ).fetchall()
    assert runs == [{"workflow_run_id": created.workflow_run_id}]
