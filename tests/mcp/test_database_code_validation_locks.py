"""Stored Code/Validation locks survive materialization, snapshots and validation."""

# pyright: reportPrivateUsage=false
from copy import deepcopy
from uuid import uuid4

from gds_etl_workbench.application.change_sets.project import (
    load_project_physical_scope,
)
from gds_etl_workbench.application.change_sets.project_apply import ProjectMaterializer
from gds_etl_workbench.application.change_sets.project_validation import (
    validate_future_graph,
)
from gds_etl_workbench.application.project_read import ProjectReadContext
from gds_etl_workbench.application.project_snapshot import build_project_snapshot
from gds_etl_workbench.domain.snapshots.project import (
    ProjectChangeSetDataset,
    project_snapshot_records,
)

from tests.mcp.conftest import DisposablePostgres
from tests.mcp.project_test_fixtures import complete_project_graph
from tests.mcp.test_database_project_change_set_round_trip import (
    _replace_codes,
    _seed_project_foundation,
)


async def test_code_validation_lock_round_trip_and_authoring_barrier(
    postgres_database: DisposablePostgres,
) -> None:
    prefix = "CODE_LOCKS_" + uuid4().hex
    project_id, tenant_id = _seed_project_foundation(
        postgres_database, code_prefix=prefix
    )
    graph = _replace_codes(complete_project_graph(), code_prefix=prefix)
    locked: dict[ProjectChangeSetDataset, str] = {
        "generated_code": "generated_code_is_locked",
        "generated_code_source_system": "generated_code_source_system_is_locked",
        "validation_group": "is_locked",
        "validation_check": "is_locked",
    }
    for dataset, field in locked.items():
        graph[dataset][0][field] = True
    project = ProjectReadContext(
        project_id=project_id,
        tenant_id=tenant_id,
        project_name="Project Tool Round Trip",
        project_revision=1,
    )
    runtime = postgres_database.create_runtime_adapter()
    await runtime.open()
    try:
        async with runtime.write_transaction() as transaction:
            snapshot = await build_project_snapshot(transaction, project)
            physical = await load_project_physical_scope(transaction, project)
            authored = validate_future_graph(
                snapshot=snapshot, staged_documents=graph, physical_scope=physical
            )
            assert authored.valid
            await ProjectMaterializer(transaction, project_id, "a" * 64).apply(
                authored.records
            )
        async with runtime.read_transaction() as transaction:
            snapshot = await build_project_snapshot(transaction, project)
            records = project_snapshot_records(snapshot)
            physical = await load_project_physical_scope(transaction, project)
            for dataset, field in locked.items():
                original = records[dataset][0].model_dump(mode="json")
                assert original[field] is True
                assert original == graph[dataset][0]
                changes = (
                    field,
                    "is_active"
                    if dataset.startswith("validation")
                    else dataset + "_status",
                )
                if dataset == "generated_code":
                    changes += (
                        "code_storage_type",
                        "code_repository_url",
                        "code_commit_path",
                        "code_entry_point",
                        "code_parameters",
                    )
                for change in changes:
                    attempted = deepcopy(original)
                    attempted[change] = (
                        "git"
                        if change == "code_storage_type"
                        else False
                        if isinstance(original[change], bool)
                        else "inactive"
                    )
                    rejected = validate_future_graph(
                        snapshot=snapshot,
                        staged_documents={dataset: [attempted]},
                        physical_scope=physical,
                    )
                    assert not rejected.valid
                    assert any(
                        issue.code == "record_locked" and issue.dataset == dataset
                        for issue in rejected.issues
                    )
    finally:
        await runtime.close()
