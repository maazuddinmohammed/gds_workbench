"""Definition editing and whole-layer removal through the governed web database role."""

# pyright: reportPrivateUsage=false
from dataclasses import replace
from typing import cast
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
from gds_etl_workbench.domain.errors import WorkbenchError
from gds_workbench_api.database import WebPostgresDatabase
from gds_workbench_api.features.project_change_sets.contracts import (
    PreviewProjectRecordsRequest,
    ReviewProjectRecordsRequest,
    ReviewProjectRecordsResult,
)
from gds_workbench_api.features.project_change_sets.editor import (
    EditableDataset,
    ProjectRecordEditor,
    ProjectRecordEditorRequest,
    SaveProjectRecordRequest,
)
from gds_workbench_api.features.project_change_sets.review import (
    ProjectLayer,
    review_lifecycle,
)
from gds_workbench_api.features.project_change_sets.service import (
    DatabaseProjectChangeSetService,
)
from gds_workbench_api.features.project_targets.contracts import ExportProjectDdlRequest
from gds_workbench_api.features.project_targets.service import (
    DatabaseProjectTargetsService,
)
from gds_workbench_api.features.projects import ProjectRevisionConflictError

from tests.mcp.conftest import DisposablePostgres
from tests.mcp.project_test_fixtures import complete_project_graph
from tests.mcp.test_database_project_change_set_round_trip import (
    StaticIdentityProvider,
    _acquire_tenant_lock,
    _replace_codes,
    _seed_project_foundation,
)


@pytest.mark.parametrize("layer", ["conceptual", "logical", "dimensional"])
async def test_edit_then_clear_layer_is_atomic_replayable_and_recoverable(
    web_postgres_database: DisposablePostgres,
    layer: ProjectLayer,
) -> None:
    fixture = web_postgres_database
    prefix = "EDIT_LAYER_" + uuid4().hex
    project_id, tenant_id = _seed_project_foundation(fixture, code_prefix=prefix)
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
            validation = validate_future_graph(
                snapshot=await build_project_snapshot(transaction, project),
                physical_scope=await load_project_physical_scope(transaction, project),
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
    dataset = cast(
        EditableDataset,
        "conceptual_object" if layer == "conceptual" else f"{layer}_entity",
    )
    await database.open()
    try:
        async with database.read_transaction() as transaction:
            before = await read_project_review_snapshot(transaction, project)
        record_id = next(iter(before.records_by_id[dataset]))
        assert isinstance(record_id, int)
        load = ProjectRecordEditorRequest(
            dataset=dataset, record_id=record_id, expected_project_revision=1
        )
        with pytest.raises(WorkbenchError) as denied:
            await service.edit_record(
                principal, tenant_id=tenant_id, project_id=project_id, command=load
            )
        assert denied.value.code == "tenant_lock_required"
        _acquire_tenant_lock(fixture, tenant_id)
        editor = await service.edit_record(
            principal, tenant_id=tenant_id, project_id=project_id, command=load
        )
        assert isinstance(editor, ProjectRecordEditor) and editor.project_revision == 1
        field = f"{dataset}_definition"
        command = SaveProjectRecordRequest(
            **load.model_dump(), changes={field: "Updated business definition."}
        )
        key = uuid4()
        receipt = await service.edit_record(
            principal,
            tenant_id=tenant_id,
            project_id=project_id,
            command=command,
            idempotency_key=key,
        )
        assert (
            isinstance(receipt, ReviewProjectRecordsResult)
            and receipt.project_revision == 2
        )
        assert (
            await service.edit_record(
                principal,
                tenant_id=tenant_id,
                project_id=project_id,
                command=command,
                idempotency_key=key,
            )
            == receipt
        )
        with pytest.raises(ProjectRevisionConflictError):
            await service.edit_record(
                principal,
                tenant_id=tenant_id,
                project_id=project_id,
                command=command,
                idempotency_key=uuid4(),
            )
        async with database.read_transaction() as transaction:
            after = await read_project_review_snapshot(
                transaction, replace(project, project_revision=2)
            )
        assert (
            after.records_by_id[dataset].keys() == before.records_by_id[dataset].keys()
        )
        original = before.records_by_id[dataset][record_id].model_dump()
        updated = after.records_by_id[dataset][record_id].model_dump()
        assert {name for name in original if original[name] != updated[name]} == {field}

        clear = PreviewProjectRecordsRequest(
            dataset=dataset,
            record_ids=[],
            layer=layer,
            action="deactivate",
            expected_project_revision=2,
        )
        preview = await service.preview_record_review(
            principal, tenant_id=tenant_id, project_id=project_id, command=clear
        )
        assert preview.can_apply and preview.action_count > 1
        with pytest.raises(WorkbenchError) as unconfirmed:
            await service.review_records(
                principal,
                tenant_id=tenant_id,
                project_id=project_id,
                command=ReviewProjectRecordsRequest(**clear.model_dump()),
                idempotency_key=uuid4(),
            )
        assert unconfirmed.value.code == "review_confirmation_required"
        clear_command = ReviewProjectRecordsRequest.model_validate(
            {**clear.model_dump(), "expected_plan_digest": preview.plan_digest}
        )
        clear_key = uuid4()
        cleared = await service.review_records(
            principal,
            tenant_id=tenant_id,
            project_id=project_id,
            command=clear_command,
            idempotency_key=clear_key,
        )
        assert (
            cleared.project_revision == 3
            and cleared.action_count == preview.action_count
        )
        assert (
            await service.review_records(
                principal,
                tenant_id=tenant_id,
                project_id=project_id,
                command=clear_command,
                idempotency_key=clear_key,
            )
            == cleared
        )
        async with database.read_transaction() as transaction:
            final = await read_project_review_snapshot(
                transaction, replace(project, project_revision=3)
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
            project_id=project_id,
            dataset=dataset,
            expected_project_revision=3,
        )
        assert all(item.status == "inactive" for item in history.items)
        restore = PreviewProjectRecordsRequest(
            dataset=dataset,
            record_ids=[record_id],
            action="reactivate",
            expected_project_revision=3,
        )
        restore_preview = await service.preview_record_review(
            principal, tenant_id=tenant_id, project_id=project_id, command=restore
        )
        assert restore_preview.can_apply
        restored = await service.review_records(
            principal,
            tenant_id=tenant_id,
            project_id=project_id,
            command=ReviewProjectRecordsRequest.model_validate(
                {
                    **restore.model_dump(),
                    "expected_plan_digest": restore_preview.plan_digest,
                }
            ),
            idempotency_key=uuid4(),
        )
        assert restored.project_revision == 4
    finally:
        await database.close()


@pytest.mark.parametrize("creating", [False, True])
async def test_mapping_edit_uses_scope_and_revision_fenced_replay(
    web_postgres_database: DisposablePostgres,
    creating: bool,
) -> None:
    fixture = web_postgres_database
    prefix = "MAP_EDIT_" + uuid4().hex
    project_id, tenant_id = _seed_project_foundation(fixture, code_prefix=prefix)
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
            validation = validate_future_graph(
                snapshot=await build_project_snapshot(transaction, project),
                physical_scope=await load_project_physical_scope(transaction, project),
                staged_documents=_replace_codes(
                    {
                        key: rows
                        for key, rows in complete_project_graph().items()
                        if not creating
                        or not key.startswith(("mapping_", "generated_", "validation_"))
                    },
                    code_prefix=prefix,
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
        targets = DatabaseProjectTargetsService(
            database=database, authorizer=AuthorizationService()
        )
        ddl = await targets.export_ddl(
            principal,
            tenant_id=tenant_id,
            project_id=project_id,
            command=ExportProjectDdlRequest(
                layer="conceptual", expected_project_revision=1
            ),
        )
        assert "`conceptual`." in ddl and "`ConceptID` BIGINT" in ddl
        async with database.read_transaction() as transaction:
            before = await read_project_review_snapshot(transaction, project)
        record_id = (
            0 if creating else next(iter(before.records_by_id["mapping_object"]))
        )
        assert isinstance(record_id, int)
        target = None
        if creating:
            async with database.read_transaction() as transaction:
                anchor = await transaction.fetch_one(
                    "SELECT entity.modeled_entity_id, system.system_id "
                    "FROM workflow.modeled_entity entity CROSS JOIN core.system system "
                    "WHERE entity.project_id = %s "
                    "AND entity.modeled_entity_type = 'logical_entity' "
                    "AND entity.modeled_entity_name = 'Order' AND system.system_code = %s",
                    (project_id, prefix + "_ERP"),
                )
            assert anchor is not None
            from gds_workbench_api.features.project_change_sets.editor import (
                NewMappingTarget,
            )

            target = NewMappingTarget(
                entity_type="logical_entity",
                entity_id=anchor["modeled_entity_id"],
                source_system_id=anchor["system_id"],
            )
        load = ProjectRecordEditorRequest(
            dataset="mapping_object",
            record_id=record_id,
            expected_project_revision=1,
            mapping_target=target,
        )
        with pytest.raises(WorkbenchError) as denied:
            await service.edit_record(
                principal, tenant_id=tenant_id, project_id=project_id, command=load
            )
        assert denied.value.code == "tenant_lock_required"
        _acquire_tenant_lock(fixture, tenant_id)
        editor = await service.edit_record(
            principal, tenant_id=tenant_id, project_id=project_id, command=load
        )
        assert isinstance(editor, ProjectRecordEditor) and editor.mapping is not None
        assert {
            table["reference"]["object_name"]
            for table in editor.mapping["source_tables"]
        } >= {
            "orders",
            "customers",
        }
        selected_source = editor.mapping["source_tables"][0]["reference"]
        command = SaveProjectRecordRequest(
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
            project_id=project_id,
            command=command,
            idempotency_key=key,
        )
        assert (
            isinstance(receipt, ReviewProjectRecordsResult)
            and receipt.project_revision == 2
        )
        assert (
            await service.edit_record(
                principal,
                tenant_id=tenant_id,
                project_id=project_id,
                command=command,
                idempotency_key=key,
            )
            == receipt
        )
        with pytest.raises(ProjectRevisionConflictError):
            await service.edit_record(
                principal,
                tenant_id=tenant_id,
                project_id=project_id,
                command=command,
                idempotency_key=uuid4(),
            )
        async with database.read_transaction() as transaction:
            after = await read_project_review_snapshot(
                transaction, replace(project, project_revision=2)
            )
        if creating:
            record_id = next(iter(after.records_by_id["mapping_object"]))
            assert isinstance(record_id, int)
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
            project_id=project_id,
            command=ProjectRecordEditorRequest(
                dataset="mapping_object",
                record_id=record_id,
                expected_project_revision=2,
            ),
        )
        assert (
            isinstance(attribute_editor, ProjectRecordEditor)
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
        bad_command = SaveProjectRecordRequest(
            dataset="mapping_object",
            record_id=record_id,
            expected_project_revision=2,
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
                project_id=project_id,
                command=bad_command,
                idempotency_key=uuid4(),
            )
        assert outside.value.code == "invalid_request"
        good_command = SaveProjectRecordRequest(
            dataset="mapping_object",
            record_id=record_id,
            expected_project_revision=2,
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
            project_id=project_id,
            command=good_command,
            idempotency_key=uuid4(),
        )
        assert (
            isinstance(saved, ReviewProjectRecordsResult)
            and saved.project_revision == 3
        )
        async with database.read_transaction() as transaction:
            final = await read_project_review_snapshot(
                transaction, replace(project, project_revision=3)
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
