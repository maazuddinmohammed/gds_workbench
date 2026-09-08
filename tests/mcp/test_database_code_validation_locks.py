"""Stored Code/Validation locks survive materialization, snapshots and validation."""

# pyright: reportPrivateUsage=false
from copy import deepcopy
from uuid import uuid4

from gds_etl_workbench.application.change_sets.model import load_model_physical_scope
from gds_etl_workbench.application.change_sets.model_apply import ModelMaterializer
from gds_etl_workbench.application.change_sets.model_validation import validate_future_graph
from gds_etl_workbench.application.model_read import ModelReadContext
from gds_etl_workbench.application.model_snapshot import build_model_snapshot
from gds_etl_workbench.domain.snapshots.model import ModelChangeSetDataset, model_snapshot_records

from tests.mcp.conftest import DisposablePostgres
from tests.mcp.model_test_fixtures import complete_model_graph
from tests.mcp.test_database_model_change_set_round_trip import (
    _replace_codes,
    _seed_model_foundation,
)


async def test_code_validation_lock_round_trip_and_authoring_barrier(
    postgres_database: DisposablePostgres,
) -> None:
    prefix = "CODE_LOCKS_" + uuid4().hex
    model_id, tenant_id = _seed_model_foundation(postgres_database, code_prefix=prefix)
    graph = _replace_codes(complete_model_graph(), code_prefix=prefix)
    locked: dict[ModelChangeSetDataset, str] = {
        "generated_code": "generated_code_is_locked",
        "generated_code_source_system": "generated_code_source_system_is_locked",
        "validation_group": "is_locked",
        "validation_check": "is_locked",
    }
    for dataset, field in locked.items():
        graph[dataset][0][field] = True
    model = ModelReadContext(
        model_id=model_id, tenant_id=tenant_id, model_name="Model Tool Round Trip", model_revision=1
    )
    runtime = postgres_database.create_runtime_adapter()
    await runtime.open()
    try:
        async with runtime.write_transaction() as transaction:
            snapshot = await build_model_snapshot(transaction, model)
            physical = await load_model_physical_scope(transaction, model)
            authored = validate_future_graph(
                snapshot=snapshot, staged_documents=graph, physical_scope=physical
            )
            assert authored.valid
            await ModelMaterializer(transaction, model_id, "a" * 64).apply(authored.records)
        async with runtime.read_transaction() as transaction:
            snapshot = await build_model_snapshot(transaction, model)
            records = model_snapshot_records(snapshot)
            physical = await load_model_physical_scope(transaction, model)
            for dataset, field in locked.items():
                original = records[dataset][0].model_dump(mode="json")
                assert original[field] is True
                assert original == graph[dataset][0]
                for change in (
                    field,
                    "is_active" if dataset.startswith("validation") else dataset + "_status",
                ):
                    attempted = deepcopy(original)
                    attempted[change] = False if isinstance(original[change], bool) else "inactive"
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
