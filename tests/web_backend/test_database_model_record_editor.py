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
from gds_workbench_api.features.model_targets.contracts import ExportModelDdlRequest
from gds_workbench_api.features.model_targets.service import DatabaseModelTargetsService

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


@pytest.mark.parametrize("creating", [False, True])
async def test_mapping_edit_uses_scope_and_revision_fenced_replay(
    web_postgres_database: DisposablePostgres,
    creating: bool,
) -> None:
    fixture = web_postgres_database
    prefix = "MAP_EDIT_" + uuid4().hex
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
                    {
                        key: rows
                        for key, rows in complete_model_graph().items()
                        if not creating
                        or not key.startswith(("mapping_", "generated_", "validation_"))
                    },
                    code_prefix=prefix,
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
    await database.open()
    try:
        targets = DatabaseModelTargetsService(
            database=database, authorizer=AuthorizationService()
        )
        ddl = await targets.export_ddl(
            principal,
            tenant_id=tenant_id,
            model_id=model_id,
            command=ExportModelDdlRequest(
                layer="conceptual", expected_model_revision=1
            ),
        )
        assert "`conceptual`." in ddl and "`ConceptID` BIGINT" in ddl
        async with database.read_transaction() as transaction:
            before = await read_model_review_snapshot(transaction, model)
        record_id = (
            0 if creating else next(iter(before.records_by_id["mapping_object"]))
        )
        target = None
        if creating:
            async with database.read_transaction() as transaction:
                anchor = await transaction.fetch_one(
                    "SELECT entity.modeled_entity_id, system.system_id "
                    "FROM workflow.modeled_entity entity CROSS JOIN core.system system "
                    "WHERE entity.model_id = %s AND entity.modeled_entity_type = 'logical_entity' "
                    "AND entity.modeled_entity_name = 'Order' AND system.system_code = %s",
                    (model_id, prefix + "_ERP"),
                )
            assert anchor is not None
            from gds_workbench_api.features.model_change_sets.editor import (
                NewMappingTarget,
            )

            target = NewMappingTarget(
                entity_type="logical_entity",
                entity_id=anchor["modeled_entity_id"],
                source_system_id=anchor["system_id"],
            )
        load = ModelRecordEditorRequest(
            dataset="mapping_object",
            record_id=record_id,
            expected_model_revision=1,
            mapping_target=target,
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
        assert isinstance(editor, ModelRecordEditor) and editor.mapping is not None
        assert {
            table["reference"]["object_name"]
            for table in editor.mapping["source_tables"]
        } >= {"orders", "customers"}
        selected_source = editor.mapping["source_tables"][0]["reference"]
        command = SaveModelRecordRequest(
            **load.model_dump(),
            changes={
                "object_mapping": {
                    "object_dependency_order": editor.mapping["dependency_order"],
                    "mapping_transformation_document": {
                        "source_tables": [selected_source],
                        "filter_criteria": "Active orders only.",
                    },
                },
                "attribute_mappings": [],
            },
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
        if creating:
            record_id = next(iter(after.records_by_id["mapping_object"]))
        assert (
            after.records_by_id["mapping_object"][record_id].model_dump()[
                "mapping_transformation_document"
            ]
            == command.changes["object_mapping"]["mapping_transformation_document"]
        )
        assert (
            after.records_by_id["mapping_attribute"]
            == before.records_by_id["mapping_attribute"]
        )
        attribute_editor = await service.edit_record(
            principal,
            tenant_id=tenant_id,
            model_id=model_id,
            command=ModelRecordEditorRequest(
                dataset="mapping_object", record_id=record_id, expected_model_revision=2
            ),
        )
        assert (
            isinstance(attribute_editor, ModelRecordEditor)
            and attribute_editor.mapping is not None
        )
        data = attribute_editor.mapping
        assert data["object_document"]["source_tables"] == [selected_source]
        selected_table = next(
            table
            for table in data["source_tables"]
            if table["reference"] == selected_source
        )
        other_table = next(
            table
            for table in data["source_tables"]
            if table["reference"] != selected_source
        )
        target_name = data["attributes"][0]["name"]
        bad_command = SaveModelRecordRequest(
            dataset="mapping_object",
            record_id=record_id,
            expected_model_revision=2,
            changes={
                "attribute_mappings": [
                    {
                        "modeled_attribute_name": target_name,
                        "attribute_mapping_transformation_document": {
                            "source_columns": [other_table["columns"][0]["reference"]],
                            "transformation_logic": "Read the source column.",
                        },
                    }
                ]
            },
        )
        with pytest.raises(WorkbenchError) as outside:
            await service.edit_record(
                principal,
                tenant_id=tenant_id,
                model_id=model_id,
                command=bad_command,
                idempotency_key=uuid4(),
            )
        assert outside.value.code == "invalid_request"
        good_command = SaveModelRecordRequest(
            dataset="mapping_object",
            record_id=record_id,
            expected_model_revision=2,
            changes={
                "attribute_mappings": [
                    {
                        "modeled_attribute_name": target_name,
                        "attribute_mapping_transformation_document": {
                            "source_columns": [
                                selected_table["columns"][0]["reference"]
                            ],
                            "transformation_logic": "Read the selected source column.",
                            "default_record": "Unknown",
                        },
                    }
                ]
            },
        )
        saved = await service.edit_record(
            principal,
            tenant_id=tenant_id,
            model_id=model_id,
            command=good_command,
            idempotency_key=uuid4(),
        )
        assert isinstance(saved, ReviewModelRecordsResult) and saved.model_revision == 3
        async with database.read_transaction() as transaction:
            final = await read_model_review_snapshot(
                transaction, replace(model, model_revision=3)
            )
        assert (
            final.records_by_id["mapping_object"]
            == after.records_by_id["mapping_object"]
        )
        child = next(
            row
            for row in final.records_by_id["mapping_attribute"].values()
            if row.model_dump()["modeled_attribute_name"] == target_name
            and row.model_dump()["modeled_entity_type"] == "logical_entity"
        )
        assert (
            child.model_dump()["attribute_mapping_transformation_document"]
            == good_command.changes["attribute_mappings"][0][
                "attribute_mapping_transformation_document"
            ]
        )

    finally:
        await database.close()
