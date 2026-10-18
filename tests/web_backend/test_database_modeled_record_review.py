"""Owned lifecycle writes for every result table on fixture-created PostgreSQL."""

# pyright: reportPrivateUsage=false
from dataclasses import replace
from uuid import uuid4

import pytest
from gds_etl_workbench.application.authorization import AuthorizationService
from gds_etl_workbench.application.change_sets.project import (
    load_project_physical_scope,
)
from gds_etl_workbench.application.change_sets.project_apply import ProjectMaterializer
from gds_etl_workbench.application.change_sets.project_validation import (
    validate_future_graph,
)
from gds_etl_workbench.application.project_read import ProjectReadContext
from gds_etl_workbench.application.project_snapshot import (
    build_project_snapshot,
    read_project_review_snapshot,
)
from gds_workbench_api.database import WebPostgresDatabase
from gds_workbench_api.features.project_change_sets.contracts import (
    PreviewProjectRecordsRequest,
    ReviewProjectRecordsRequest,
)
from gds_workbench_api.features.project_change_sets.review import (
    REVIEW_FIELDS,
    ProjectReviewDataset,
    review_lifecycle,
)
from gds_workbench_api.features.project_change_sets.service import (
    DatabaseProjectChangeSetService,
)

from tests.mcp.conftest import DisposablePostgres
from tests.mcp.project_test_fixtures import complete_project_graph
from tests.mcp.test_database_project_change_set_round_trip import (
    StaticIdentityProvider,
    _acquire_tenant_lock,
    _replace_codes,
    _seed_project_foundation,
)


@pytest.mark.parametrize("dataset", list(REVIEW_FIELDS))
async def test_owned_result_lifecycle_round_trip_preserves_authored_content(
    web_postgres_database: DisposablePostgres,
    dataset: ProjectReviewDataset,
) -> None:
    fixture = web_postgres_database
    prefix = "RESULT_REVIEW_" + uuid4().hex
    project_id, tenant_id = _seed_project_foundation(fixture, code_prefix=prefix)
    _acquire_tenant_lock(fixture, tenant_id)
    project = ProjectReadContext(
        project_id=project_id,
        tenant_id=tenant_id,
        project_name="Project Tool Round Trip",
        project_revision=1,
    )
    runtime = fixture.create_runtime_adapter()
    await runtime.open()
    try:
        async with runtime.write_transaction() as transaction:
            snapshot = await build_project_snapshot(transaction, project)
            physical = await load_project_physical_scope(transaction, project)
            validation = validate_future_graph(
                snapshot=snapshot,
                physical_scope=physical,
                staged_documents=_replace_codes(
                    complete_project_graph(), code_prefix=prefix
                ),
            )
            assert validation.valid
            await ProjectMaterializer(transaction, project_id, "a" * 64).apply(
                validation.records
            )
    finally:
        await runtime.close()
    database = WebPostgresDatabase(
        dsn=fixture.web_runtime_dsn(), pool_min=1, pool_max=1, pool_timeout_seconds=5
    )
    service = DatabaseProjectChangeSetService(
        database=database, authorizer=AuthorizationService()
    )
    principal = StaticIdentityProvider().request_principal(None)
    await database.open()
    try:
        async with database.read_transaction() as transaction:
            before = await read_project_review_snapshot(transaction, project)
        record_id = next(iter(before.records_by_id[dataset]))
        revision = 1
        for action in ("lock", "unlock", "deactivate", "reactivate"):
            preview = await service.preview_record_review(
                principal,
                tenant_id=tenant_id,
                project_id=project_id,
                command=PreviewProjectRecordsRequest(
                    dataset=dataset,
                    record_ids=[record_id],
                    action=action,
                    expected_project_revision=revision,
                ),
            )
            assert preview.can_apply
            command = ReviewProjectRecordsRequest(
                dataset=dataset,
                record_ids=[record_id],
                action=action,
                expected_project_revision=revision,
                expected_plan_digest=preview.plan_digest,
            )
            request_key = uuid4()
            receipt = await service.review_records(
                principal,
                tenant_id=tenant_id,
                project_id=project_id,
                command=command,
                idempotency_key=request_key,
            )
            revision = receipt.project_revision
            assert receipt.action_count == preview.action_count
            assert (
                await service.review_records(
                    principal,
                    tenant_id=tenant_id,
                    project_id=project_id,
                    command=command,
                    idempotency_key=request_key,
                )
                == receipt
            )
            async with database.read_transaction() as transaction:
                after = await read_project_review_snapshot(
                    transaction, replace(project, project_revision=revision)
                )
            history = await service.list_review_records(
                principal,
                tenant_id=tenant_id,
                project_id=project_id,
                dataset=dataset,
                expected_project_revision=revision,
            )
            assert history.project_revision == revision and history.dataset == dataset
            listed = next(row for row in history.items if row.record_id == record_id)
            assert listed.status == ("inactive" if action == "deactivate" else "active")
            locked, status = review_lifecycle(
                after.records_by_id[dataset][record_id], dataset
            )
            assert locked is (action == "lock")
            assert status == ("inactive" if action == "deactivate" else "active")
            for name in REVIEW_FIELDS:
                for identity, original in before.records_by_id[name].items():
                    old, new = (
                        original.model_dump(mode="json"),
                        after.records_by_id[name][identity].model_dump(mode="json"),
                    )
                    assert {field for field in old if old[field] != new[field]} <= set(
                        REVIEW_FIELDS[name][:2]
                    )
    finally:
        await database.close()
