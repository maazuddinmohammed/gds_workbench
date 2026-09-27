"""Definition editing and whole-layer removal through the governed web database role."""

# pyright: reportPrivateUsage=false
from dataclasses import replace
from typing import cast
from uuid import uuid4

import pytest
from gds_etl_workbench.application.authorization import AuthorizationService
from gds_etl_workbench.application.change_sets.model import load_model_physical_scope
from gds_etl_workbench.application.change_sets.model_apply import ModelMaterializer
from gds_etl_workbench.application.change_sets.model_validation import (
    validate_future_graph,
)
from gds_etl_workbench.application.model_read import ModelReadContext
from gds_etl_workbench.application.model_snapshot import (
    build_model_snapshot,
    read_model_review_snapshot,
)
from gds_etl_workbench.domain.errors import WorkbenchError
from gds_workbench_api.database import WebPostgresDatabase
from gds_workbench_api.features.model_change_sets.contracts import (
    PreviewModelRecordsRequest,
    ReviewModelRecordsRequest,
    ReviewModelRecordsResult,
)
from gds_workbench_api.features.model_change_sets.editor import (
    EditableDataset,
    ModelRecordEditor,
    ModelRecordEditorRequest,
    SaveModelRecordRequest,
)
from gds_workbench_api.features.model_change_sets.review import (
    ModelLayer,
    review_lifecycle,
)
from gds_workbench_api.features.model_change_sets.service import (
    DatabaseModelChangeSetService,
)
from gds_workbench_api.features.models import ModelRevisionConflictError

from tests.mcp.conftest import DisposablePostgres
from tests.mcp.model_test_fixtures import complete_model_graph
from tests.mcp.test_database_model_change_set_round_trip import (
    StaticIdentityProvider,
    _acquire_tenant_lock,
    _replace_codes,
    _seed_model_foundation,
)


@pytest.mark.parametrize("layer", ["conceptual", "logical", "dimensional"])
async def test_edit_then_clear_layer_is_atomic_replayable_and_recoverable(
    web_postgres_database: DisposablePostgres,
    layer: ModelLayer,
) -> None:
    fixture = web_postgres_database
    prefix = "EDIT_LAYER_" + uuid4().hex
    model_id, tenant_id = _seed_model_foundation(fixture, code_prefix=prefix)
    model = ModelReadContext(
        model_id=model_id,
        tenant_id=tenant_id,
        model_name="Model Tool Round Trip",
        model_revision=1,
    )
    runtime = fixture.create_runtime_adapter()
    await runtime.open()
    try:
        async with runtime.write_transaction() as transaction:
            validation = validate_future_graph(
                snapshot=await build_model_snapshot(transaction, model),
                physical_scope=await load_model_physical_scope(transaction, model),
                staged_documents=_replace_codes(
                    complete_model_graph(), code_prefix=prefix
                ),
            )
            assert validation.valid
            await ModelMaterializer(transaction, model_id, "a" * 64).apply(
                validation.records
            )
    finally:
        await runtime.close()
    database = WebPostgresDatabase(
        dsn=fixture.web_runtime_dsn(), pool_min=1, pool_max=1, pool_timeout_seconds=5
    )
    service = DatabaseModelChangeSetService(
        database=database, authorizer=AuthorizationService()
    )
    principal = StaticIdentityProvider().request_principal(None)
    dataset = cast(
        EditableDataset,
        "conceptual_object" if layer == "conceptual" else f"{layer}_entity",
    )
    await database.open()
    try:
        async with database.read_transaction() as transaction:
            before = await read_model_review_snapshot(transaction, model)
        record_id = next(iter(before.records_by_id[dataset]))
        load = ModelRecordEditorRequest(
            dataset=dataset, record_id=record_id, expected_model_revision=1
        )
        with pytest.raises(WorkbenchError) as denied:
            await service.edit_record(
                principal, tenant_id=tenant_id, model_id=model_id, command=load
            )
        assert denied.value.code == "tenant_lock_required"
        _acquire_tenant_lock(fixture, tenant_id)
        editor = await service.edit_record(
            principal, tenant_id=tenant_id, model_id=model_id, command=load
        )
        assert isinstance(editor, ModelRecordEditor) and editor.model_revision == 1
        field = f"{dataset}_definition"
        command = SaveModelRecordRequest(
            **load.model_dump(), changes={field: "Updated business definition."}
        )
        key = uuid4()
        receipt = await service.edit_record(
            principal,
            tenant_id=tenant_id,
            model_id=model_id,
            command=command,
            idempotency_key=key,
        )
        assert (
            isinstance(receipt, ReviewModelRecordsResult)
            and receipt.model_revision == 2
        )
        assert (
            await service.edit_record(
                principal,
                tenant_id=tenant_id,
                model_id=model_id,
                command=command,
                idempotency_key=key,
            )
            == receipt
        )
        with pytest.raises(ModelRevisionConflictError):
            await service.edit_record(
                principal,
                tenant_id=tenant_id,
                model_id=model_id,
                command=command,
                idempotency_key=uuid4(),
            )
        async with database.read_transaction() as transaction:
            after = await read_model_review_snapshot(
                transaction, replace(model, model_revision=2)
            )
        assert (
            after.records_by_id[dataset].keys() == before.records_by_id[dataset].keys()
        )
        original = before.records_by_id[dataset][record_id].model_dump()
        updated = after.records_by_id[dataset][record_id].model_dump()
        assert {name for name in original if original[name] != updated[name]} == {field}

        clear = PreviewModelRecordsRequest(
            dataset=dataset,
            record_ids=[],
            layer=layer,
            action="deactivate",
            expected_model_revision=2,
        )
        preview = await service.preview_record_review(
            principal, tenant_id=tenant_id, model_id=model_id, command=clear
        )
        assert preview.can_apply and preview.action_count > 1
        with pytest.raises(WorkbenchError) as unconfirmed:
            await service.review_records(
                principal,
                tenant_id=tenant_id,
                model_id=model_id,
                command=ReviewModelRecordsRequest(**clear.model_dump()),
                idempotency_key=uuid4(),
            )
        assert unconfirmed.value.code == "review_confirmation_required"
        clear_command = ReviewModelRecordsRequest.model_validate(
            {**clear.model_dump(), "expected_plan_digest": preview.plan_digest}
        )
        clear_key = uuid4()
        cleared = await service.review_records(
            principal,
            tenant_id=tenant_id,
            model_id=model_id,
            command=clear_command,
            idempotency_key=clear_key,
        )
        assert (
            cleared.model_revision == 3 and cleared.action_count == preview.action_count
        )
        assert (
            await service.review_records(
                principal,
                tenant_id=tenant_id,
                model_id=model_id,
                command=clear_command,
                idempotency_key=clear_key,
            )
            == cleared
        )
        async with database.read_transaction() as transaction:
            final = await read_model_review_snapshot(
                transaction, replace(model, model_revision=3)
            )
        for name, rows in final.records_by_id.items():
            assert rows.keys() == before.records_by_id[name].keys()
            if name.startswith(layer + "_"):
                assert all(
                    review_lifecycle(row, cast(EditableDataset, name))[1] == "inactive"
                    for row in rows.values()
                )
        history = await service.list_review_records(
            principal,
            tenant_id=tenant_id,
            model_id=model_id,
            dataset=dataset,
            expected_model_revision=3,
        )
        assert all(item.status == "inactive" for item in history.items)
        restore = PreviewModelRecordsRequest(
            dataset=dataset,
            record_ids=[record_id],
            action="reactivate",
            expected_model_revision=3,
        )
        restore_preview = await service.preview_record_review(
            principal, tenant_id=tenant_id, model_id=model_id, command=restore
        )
        assert restore_preview.can_apply
        restored = await service.review_records(
            principal,
            tenant_id=tenant_id,
            model_id=model_id,
            command=ReviewModelRecordsRequest.model_validate(
                {
                    **restore.model_dump(),
                    "expected_plan_digest": restore_preview.plan_digest,
                }
            ),
            idempotency_key=uuid4(),
        )
        assert restored.model_revision == 4
    finally:
        await database.close()
