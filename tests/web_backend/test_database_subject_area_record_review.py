"""Subject Area review previews exact memberships without changing stored records."""

from typing import Any
from uuid import uuid4

import pytest
from gds_etl_workbench.application.authorization import AuthorizationService
from gds_etl_workbench.domain.authorization import ActorKind, RequestPrincipal
from gds_etl_workbench.domain.errors import WorkbenchError
from gds_workbench_api.database import WebPostgresDatabase
from gds_workbench_api.features.project_change_sets.contracts import (
    PreviewProjectRecordsRequest,
    ReviewProjectRecordsRequest,
)
from gds_workbench_api.features.project_change_sets.service import (
    DatabaseProjectChangeSetService,
)

from tests.mcp.conftest import DisposablePostgres
from tests.mcp.database_test_support import require_row
from tests.mcp.test_database_workflow_run_lifecycle import (
    WorkflowContext,
    seed_workflow_context,
)

type StoredAreas = tuple[list[dict[str, Any]], list[dict[str, Any]]]


def _seed_area(
    database: DisposablePostgres,
    context: WorkflowContext,
    *,
    name: str,
    table_count: int,
    locked: bool,
) -> tuple[int, list[int]]:
    """Add new Bronze Scope tables and one active area holding all of them."""
    with database.connect_owner() as connection:
        area_id = require_row(
            connection.execute(
                "INSERT INTO workflow.subject_area (project_id, subject_area_name, "
                "subject_area_definition) VALUES (%s, %s, %s) RETURNING subject_area_id",
                (context.project_id, name, f"Tables that describe {name.lower()}."),
            ).fetchone()
        )["subject_area_id"]
        memberships = connection.execute(
            """
            WITH placement AS (
                SELECT connection_id, source_tenant_id, object_type_id, zone_id
                  FROM core.object
                 WHERE object_id = %s
            ), created AS (
                INSERT INTO core.object (
                    connection_id, source_tenant_id, object_schema, object_name,
                    object_type_id, zone_id
                )
                SELECT connection_id, source_tenant_id, 'bronze_review',
                       %s || '_' || number, object_type_id, zone_id
                  FROM placement, generate_series(1, %s) AS number
                RETURNING object_id
            ), scoped AS (
                INSERT INTO project.project_input_scope (project_id, object_id)
                SELECT %s, object_id FROM created
                RETURNING object_id
            )
            INSERT INTO workflow.subject_area_table (
                project_id, subject_area_id, object_id, subject_area_table_is_locked
            )
            SELECT %s, %s, object_id, %s FROM scoped
            RETURNING subject_area_table_id
            """,
            (
                context.selected_object_ids[0],
                name.lower(),
                table_count,
                context.project_id,
                context.project_id,
                area_id,
                locked,
            ),
        ).fetchall()
    return area_id, sorted(row["subject_area_table_id"] for row in memberships)


def _stored(database: DisposablePostgres, project_id: int) -> StoredAreas:
    with database.connect_owner() as connection:
        return (
            connection.execute(
                "SELECT * FROM workflow.subject_area WHERE project_id = %s "
                "ORDER BY subject_area_id",
                (project_id,),
            ).fetchall(),
            connection.execute(
                "SELECT * FROM workflow.subject_area_table WHERE project_id = %s "
                "ORDER BY subject_area_table_id",
                (project_id,),
            ).fetchall(),
        )


@pytest.mark.parametrize(("table_count", "locked"), [(1, False), (1, True), (205, False)])
async def test_subject_area_preview_is_complete_paged_and_preserves_stored_state(
    web_postgres_database: DisposablePostgres,
    table_count: int,
    locked: bool,
) -> None:
    database = web_postgres_database
    context = seed_workflow_context(database)
    area_id, table_ids = _seed_area(
        database, context, name="Sales", table_count=table_count, locked=locked
    )
    with database.connect_owner() as connection:
        other = require_row(
            connection.execute(
                "INSERT INTO project.project (tenant_id, project_name) VALUES (%s, %s) "
                "RETURNING project_id, project_revision",
                (context.tenant_id, f"Other review {uuid4().hex}"),
            ).fetchone()
        )
    before = _stored(database, context.project_id)
    principal = RequestPrincipal(
        actor_kind=ActorKind.HUMAN,
        entra_tenant_id=context.entra_tenant_id,
        entra_object_id=context.entra_object_id,
    )
    runtime = WebPostgresDatabase(
        dsn=database.web_runtime_dsn(), pool_min=1, pool_max=1, pool_timeout_seconds=5
    )
    service = DatabaseProjectChangeSetService(database=runtime, authorizer=AuthorizationService())
    command = PreviewProjectRecordsRequest(
        dataset="subject_area",
        record_ids=[area_id],
        action="deactivate",
        expected_project_revision=context.project_revision,
    )
    await runtime.open()
    try:
        # Retiring an area retires every active membership with it.
        first = await service.preview_record_review(
            principal,
            tenant_id=context.tenant_id,
            project_id=context.project_id,
            command=command,
        )
        assert first.can_apply is not locked
        assert first.action_count == table_count + 1
        assert first.additional_change_count == table_count
        assert first.total_record_count == table_count + 1
        assert first.changes_by_dataset == {"subject_area": 1, "subject_area_table": table_count}
        assert first.warnings == (
            "Subject Areas only group Input Scope tables; Logical and "
            "Dimensional records remain unchanged.",
        )
        all_items = list(first.items)
        assert (first.next_page is not None) == (table_count + 1 > 200)
        if first.next_page is not None:
            second = await service.preview_record_review(
                principal,
                tenant_id=context.tenant_id,
                project_id=context.project_id,
                command=command.model_copy(update={"expected_plan_digest": first.plan_digest}),
                page=first.next_page,
            )
            assert second.plan_digest == first.plan_digest and second.next_page is None
            all_items.extend(second.items)
        assert {(item.dataset, item.record_id) for item in all_items} == {
            ("subject_area", area_id),
            *(("subject_area_table", table_id) for table_id in table_ids),
        }
        assert all(item.desired_status == "inactive" for item in all_items)
        assert _stored(database, context.project_id) == before
        assert bool(first.issues) == locked
        if locked:
            assert any(issue.code == "record_locked" for issue in first.issues)
        with pytest.raises(WorkbenchError) as missing:
            await service.preview_record_review(
                principal,
                tenant_id=context.tenant_id,
                project_id=other["project_id"],
                command=command.model_copy(
                    update={"expected_project_revision": other["project_revision"]}
                ),
            )
        assert missing.value.code == "project_record_not_found"
        with pytest.raises(WorkbenchError) as stale:
            await service.preview_record_review(
                principal,
                tenant_id=context.tenant_id,
                project_id=context.project_id,
                command=command.model_copy(update={"expected_plan_digest": "f" * 64}),
            )
        assert stale.value.code == "review_conflict"
        apply_command = ReviewProjectRecordsRequest.model_validate(
            command.model_dump(), strict=False
        )
        with pytest.raises(WorkbenchError) as denied:
            await service.review_records(
                principal,
                tenant_id=context.tenant_id,
                project_id=context.project_id,
                command=apply_command,
                idempotency_key=uuid4(),
            )
        assert denied.value.code == ("record_locked" if locked else "review_confirmation_required")
        assert _stored(database, context.project_id) == before
        if locked:
            return

        apply_command = apply_command.model_copy(update={"expected_plan_digest": first.plan_digest})
        request_key = uuid4()
        applied = await service.review_records(
            principal,
            tenant_id=context.tenant_id,
            project_id=context.project_id,
            command=apply_command,
            idempotency_key=request_key,
        )
        assert applied.action_count == first.action_count
        assert applied.project_revision == context.project_revision + 1
        after = _stored(database, context.project_id)
        assert [row["subject_area_status"] for row in after[0]] == ["inactive"]
        assert all(row["subject_area_table_status"] == "inactive" for row in after[1])
        for dataset_index, dataset in enumerate(("subject_area", "subject_area_table")):
            for original, reviewed in zip(before[dataset_index], after[dataset_index], strict=True):
                for field in original.keys() - {
                    f"{dataset}_status",
                    "updated_time",
                    "updated_by",
                }:
                    assert original[field] == reviewed[field]
        replay = await service.review_records(
            principal,
            tenant_id=context.tenant_id,
            project_id=context.project_id,
            command=apply_command,
            idempotency_key=request_key,
        )
        assert replay == applied and _stored(database, context.project_id) == after

        revision = applied.project_revision
        for action in ("lock", "unlock"):
            reviewed = await service.review_records(
                principal,
                tenant_id=context.tenant_id,
                project_id=context.project_id,
                command=ReviewProjectRecordsRequest(
                    dataset="subject_area",
                    record_ids=[area_id],
                    action=action,
                    expected_project_revision=revision,
                ),
                idempotency_key=uuid4(),
            )
            assert reviewed.action_count == 1
            revision = reviewed.project_revision
            if action == "lock":
                with pytest.raises(WorkbenchError) as locked_status:
                    await service.review_records(
                        principal,
                        tenant_id=context.tenant_id,
                        project_id=context.project_id,
                        command=ReviewProjectRecordsRequest(
                            dataset="subject_area",
                            record_ids=[area_id],
                            action="reactivate",
                            expected_project_revision=revision,
                        ),
                        idempotency_key=uuid4(),
                    )
                assert locked_status.value.code == "record_locked"

        # Reactivating one membership needs its area active again, and nothing else.
        reactivate = PreviewProjectRecordsRequest(
            dataset="subject_area_table",
            record_ids=[table_ids[0]],
            action="reactivate",
            expected_project_revision=revision,
        )
        reopen = await service.preview_record_review(
            principal,
            tenant_id=context.tenant_id,
            project_id=context.project_id,
            command=reactivate,
        )
        assert reopen.can_apply and reopen.additional_change_count == 1
        applied = await service.review_records(
            principal,
            tenant_id=context.tenant_id,
            project_id=context.project_id,
            command=ReviewProjectRecordsRequest.model_validate(
                {**reactivate.model_dump(), "expected_plan_digest": reopen.plan_digest},
                strict=False,
            ),
            idempotency_key=uuid4(),
        )
        assert applied.action_count == 2
        final_areas, final_tables = _stored(database, context.project_id)
        assert [row["subject_area_status"] for row in final_areas] == ["active"]
        assert [
            row["subject_area_table_id"]
            for row in final_tables
            if row["subject_area_table_status"] == "active"
        ] == [table_ids[0]]
    finally:
        await runtime.close()


async def test_subject_area_delete_removes_only_its_own_memberships(
    web_postgres_database: DisposablePostgres,
) -> None:
    database = web_postgres_database
    context = seed_workflow_context(database)
    sales_id, sales_tables = _seed_area(
        database, context, name="Sales", table_count=2, locked=False
    )
    support_id, support_tables = _seed_area(
        database, context, name="Support", table_count=1, locked=False
    )
    with database.connect_owner() as connection:
        # Permanent deletion is reserved for Tenant administrators.
        connection.execute(
            "UPDATE security.tenant_principal_access SET tenant_role = 'tenant_admin' "
            "WHERE tenant_id = %s AND principal_id = %s",
            (context.tenant_id, context.principal_id),
        )
        scope_count = require_row(
            connection.execute(
                "SELECT count(*) AS count FROM project.project_input_scope WHERE project_id = %s",
                (context.project_id,),
            ).fetchone()
        )["count"]
    before = _stored(database, context.project_id)
    principal = RequestPrincipal(
        actor_kind=ActorKind.HUMAN,
        entra_tenant_id=context.entra_tenant_id,
        entra_object_id=context.entra_object_id,
    )
    runtime = WebPostgresDatabase(
        dsn=database.web_runtime_dsn(), pool_min=1, pool_max=1, pool_timeout_seconds=5
    )
    service = DatabaseProjectChangeSetService(database=runtime, authorizer=AuthorizationService())
    command = PreviewProjectRecordsRequest(
        dataset="subject_area",
        record_ids=[sales_id],
        action="delete",
        expected_project_revision=context.project_revision,
    )
    await runtime.open()
    try:
        preview = await service.preview_record_review(
            principal,
            tenant_id=context.tenant_id,
            project_id=context.project_id,
            command=command,
        )
        assert _stored(database, context.project_id) == before
        with pytest.raises(WorkbenchError) as unconfirmed:
            await service.review_records(
                principal,
                tenant_id=context.tenant_id,
                project_id=context.project_id,
                command=ReviewProjectRecordsRequest.model_validate(
                    command.model_dump(), strict=False
                ),
                idempotency_key=uuid4(),
            )
        deleted = await service.review_records(
            principal,
            tenant_id=context.tenant_id,
            project_id=context.project_id,
            command=ReviewProjectRecordsRequest.model_validate(
                {**command.model_dump(), "expected_plan_digest": preview.plan_digest},
                strict=False,
            ),
            idempotency_key=uuid4(),
        )
    finally:
        await runtime.close()

    assert preview.can_apply
    assert {(item.dataset, item.record_id) for item in preview.items} == {
        ("subject_area", sales_id),
        *(("subject_area_table", table_id) for table_id in sales_tables),
    }
    assert all(item.desired_status == "deleted" for item in preview.items)
    assert preview.changes_by_dataset == {"subject_area": 1, "subject_area_table": 2}
    assert (
        "Deleting a Subject Area removes only its table memberships; "
        "Logical and Dimensional records remain."
    ) in preview.warnings
    assert unconfirmed.value.code == "review_confirmation_required"
    assert deleted.action_count == 3
    assert deleted.project_revision == context.project_revision + 1
    areas, tables = _stored(database, context.project_id)
    assert [row["subject_area_id"] for row in areas] == [support_id]
    assert [row["subject_area_table_id"] for row in tables] == support_tables
    with database.connect_owner() as connection:
        remaining_scope = require_row(
            connection.execute(
                "SELECT count(*) AS count FROM project.project_input_scope WHERE project_id = %s",
                (context.project_id,),
            ).fetchone()
        )["count"]
    assert remaining_scope == scope_count
