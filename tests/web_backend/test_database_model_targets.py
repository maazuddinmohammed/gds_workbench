"""Real web target export and Binding transactions on a disposable fixture database."""

# pyright: reportPrivateUsage=false
from uuid import uuid4

import pytest
from gds_etl_workbench.application.authorization import AuthorizationService
from gds_etl_workbench.application.change_sets.model import StageModelChange
from gds_etl_workbench.domain.errors import WorkbenchError
from gds_workbench_api.database import WebPostgresDatabase
from gds_workbench_api.features.metadata.workbook import parse_metadata_workbook
from gds_workbench_api.features.metadata_change_sets.contracts import (
    CreateMetadataChangeSetRequest,
)
from gds_workbench_api.features.metadata_change_sets.contracts import (
    ExpectedDraftRevisionRequest as MetadataRevisionRequest,
)
from gds_workbench_api.features.metadata_change_sets.service import (
    DatabaseMetadataChangeSetService,
)
from gds_workbench_api.features.model_change_sets.contracts import (
    CreateModelChangeSetRequest,
    ExpectedDraftRevisionRequest,
    ReviewModelRecordsResult,
    StageModelChangeSetRequest,
)
from gds_workbench_api.features.model_change_sets.service import (
    DatabaseModelChangeSetService,
)
from gds_workbench_api.features.model_targets.contracts import (
    ApplyModelBindingRequest,
    AttributeAssignment,
    ExportModelTargetsRequest,
    GeneratedBindingsPreview,
    GenerateModelBindingsRequest,
    ModelBindingPreview,
    PreviewModelBindingRequest,
)
from gds_workbench_api.features.model_targets.service import DatabaseModelTargetsService
from gds_workbench_api.features.models import ModelRevisionConflictError

from tests.mcp.conftest import DisposablePostgres
from tests.mcp.test_database_model_binding_order import bound_layer_graph
from tests.mcp.test_database_model_change_set_round_trip import (
    StaticIdentityProvider,
    _acquire_tenant_lock,
    _seed_model_foundation,
)


@pytest.mark.parametrize("generation", [False, True])
async def test_both_layers_export_and_bind_with_revision_fencing_and_replay(
    web_postgres_database: DisposablePostgres,
    generation: bool,
) -> None:
    fixture = web_postgres_database
    prefix = f"TARGETS_{uuid4().hex}"
    model_id, tenant_id = _seed_model_foundation(fixture, code_prefix=prefix)
    _acquire_tenant_lock(fixture, tenant_id)
    graph = bound_layer_graph(prefix)
    with fixture.connect_owner() as connection:
        connection.execute(
            "UPDATE core.tenant SET gds_connection_id = (SELECT connection_id "
            "FROM core.connection WHERE connection_code=%s) WHERE tenant_id=%s",
            (f"{prefix}_LAKEHOUSE", tenant_id),
        )
        connection.execute(
            "INSERT INTO model.model_input_scope(model_id,object_id) "
            "SELECT %s,object_id FROM core.object WHERE source_tenant_id=%s "
            "AND object_schema='src' AND object_name='orders'",
            (model_id, tenant_id),
        )
    database = WebPostgresDatabase(
        dsn=fixture.web_runtime_dsn(), pool_min=1, pool_max=1, pool_timeout_seconds=5
    )
    principal = StaticIdentityProvider().request_principal(None)
    authorizer = AuthorizationService()
    service = DatabaseModelChangeSetService(database=database, authorizer=authorizer)
    targets = DatabaseModelTargetsService(database=database, authorizer=authorizer)
    await database.open()
    revision = 1
    try:
        for layer in ("logical", "dimensional"):
            created = await service.create_or_resume(
                principal,
                tenant_id=tenant_id,
                model_id=model_id,
                command=CreateModelChangeSetRequest(expected_model_revision=revision),
                idempotency_key=uuid4(),
            )
            staged = await service.stage(
                principal,
                tenant_id=tenant_id,
                model_id=model_id,
                change_set_id=created.model_change_set_id,
                command=StageModelChangeSetRequest(
                    expected_draft_revision=created.draft_revision,
                    changes=[
                        StageModelChange(dataset=dataset, records=records)
                        for dataset, records in graph.items()
                        if dataset.startswith(layer)
                        or (layer == "dimensional" and dataset.startswith("mapping_"))
                    ],
                ),
                idempotency_key=uuid4(),
            )
            draft_command = ExpectedDraftRevisionRequest(
                expected_draft_revision=staged.draft_revision
            )
            validated = await service.validate(
                principal,
                tenant_id=tenant_id,
                model_id=model_id,
                change_set_id=created.model_change_set_id,
                command=draft_command,
                idempotency_key=uuid4(),
            )
            assert validated.valid, [
                (issue.dataset, issue.code, issue.fields) for issue in validated.errors
            ]
            applied = await service.apply(
                principal,
                tenant_id=tenant_id,
                model_id=model_id,
                change_set_id=created.model_change_set_id,
                command=draft_command,
                idempotency_key=uuid4(),
            )
            revision = applied.model_revision
            with fixture.connect_owner() as connection:
                # Identifiers are a fixed two-layer fixture vocabulary, never request input.
                entity = connection.execute(
                    f"SELECT {layer}_entity_id AS entity_id FROM workflow.{layer}_entity "
                    "WHERE model_id=%s",
                    (model_id,),
                ).fetchone()
                assert entity is not None
                entity_id = entity["entity_id"]
                columns = connection.execute(
                    f"SELECT * FROM workflow.{layer}_attribute WHERE model_id=%s "
                    f"ORDER BY {layer}_attribute_id",
                    (model_id,),
                ).fetchall()
                object_binding = next(
                    row
                    for row in graph["model_object_binding"]
                    if row["modeled_entity_type"] == f"{layer}_entity"
                )
                physical = connection.execute(
                    "SELECT object_id FROM core.object WHERE source_tenant_id=%s "
                    "AND object_schema=%s AND object_name=%s",
                    (
                        tenant_id,
                        object_binding["object_schema"],
                        object_binding["object_name"],
                    ),
                ).fetchone()
                assert physical is not None
                object_id = physical["object_id"]
                for column in columns:
                    binding = next(
                        row
                        for row in graph["model_attribute_binding"]
                        if row["modeled_entity_type"] == f"{layer}_entity"
                        and row["modeled_attribute_name"] == column[f"{layer}_attribute_name"]
                    )
                    connection.execute(
                        "UPDATE core.attribute SET is_natural_key=%s,is_surrogate_key=%s,"
                        "is_meta_data=%s WHERE object_id=%s AND attribute_name=%s",
                        (
                            column["logical_attribute_is_natural_key"]
                            if layer == "logical"
                            else column["dimensional_attribute_key_role"] == "business",
                            column["logical_attribute_is_surrogate_key"]
                            if layer == "logical"
                            else column["dimensional_attribute_key_role"] == "surrogate",
                            column[f"{layer}_attribute_is_audit_column"],
                            object_id,
                            binding["attribute_name"],
                        ),
                    )
            options = await targets.options(principal, tenant_id=tenant_id, model_id=model_id)
            assert options.placement is not None
            assert options.model_revision == revision
            command = ExportModelTargetsRequest(
                layer=layer,
                expected_model_revision=revision,
                object_schema=f"new_{layer}",
                object_type_code=f"{prefix}_TABLE",
            )
            workbook = await targets.export(
                principal, tenant_id=tenant_id, model_id=model_id, command=command
            )
            sheets = parse_metadata_workbook(workbook.content, tenant_id=tenant_id)
            assert sheets[0].rows[0]["object_name"] == object_binding["modeled_entity_name"]
            assert len(sheets[1].rows) == len(columns)
            metadata = DatabaseMetadataChangeSetService(database=database, authorizer=authorizer)
            draft = await metadata.create_or_resume(
                principal,
                tenant_id=tenant_id,
                command=CreateMetadataChangeSetRequest(),
                idempotency_key=uuid4(),
            )
            imported = await metadata.import_workbook(
                principal,
                tenant_id=tenant_id,
                change_set_id=draft.metadata_change_set_id,
                expected_draft_revision=draft.draft_revision,
                content=workbook.content,
                idempotency_key=uuid4(),
            )
            assert imported.validation.valid, [
                (issue.dataset, issue.code) for issue in imported.validation.errors
            ]
            registered = await metadata.apply(
                principal,
                tenant_id=tenant_id,
                change_set_id=draft.metadata_change_set_id,
                command=MetadataRevisionRequest(
                    expected_draft_revision=imported.staged.draft_revision
                ),
                idempotency_key=uuid4(),
            )
            assert registered.applied, [(issue.dataset, issue.code) for issue in registered.errors]
            assert registered.action_count == 3

            # Export is read-only and remains available after target registration.
            existing_export = await targets.export(
                principal,
                tenant_id=tenant_id,
                model_id=model_id,
                command=command.model_copy(
                    update={"object_schema": object_binding["object_schema"]}
                ),
            )
            existing_sheets = parse_metadata_workbook(existing_export.content, tenant_id=tenant_id)
            assert (
                existing_sheets[0].rows[0]["object_name"] == object_binding["modeled_entity_name"]
            )
            available = await targets.targets(
                principal,
                tenant_id=tenant_id,
                model_id=model_id,
                layer=layer,
                search="",
                after=0,
            )
            assert object_id in {item.object_id for item in available.items}
            recommended = next(item for item in available.items if item.object_id == object_id)
            assert entity_id in recommended.matching_entity_ids
            scoped = await targets.targets(
                principal,
                tenant_id=tenant_id,
                model_id=model_id,
                layer=layer,
                search="",
                after=0,
                object_schema=f"new_{layer}",
            )
            assert len(scoped.items) == 1
            assert scoped.items[0].object_schema == f"new_{layer}"
            assert scoped.items[0].matching_entity_ids == [entity_id]
            assert scoped.items[0].bound_entity_ids == []
            preview_command = PreviewModelBindingRequest(
                layer=layer,
                entity_id=entity_id,
                object_id=object_id,
                expected_model_revision=revision,
            )
            preview = await service.bind_registered_target(
                principal,
                tenant_id=tenant_id,
                model_id=model_id,
                command=preview_command,
            )
            assert isinstance(preview, ModelBindingPreview)
            assert preview.can_apply
            apply_command = ApplyModelBindingRequest(
                **preview_command.model_dump(exclude={"assignments"}),
                expected_plan_digest=preview.plan_digest,
                assignments=[
                    AttributeAssignment(
                        modeled_attribute_id=item.modeled_attribute_id,
                        attribute_id=item.attribute_id,
                    )
                    for item in preview.assignments
                    if item.attribute_id is not None
                ],
            )
            with pytest.raises(WorkbenchError, match="Binding changed"):
                await service.bind_registered_target(
                    principal,
                    tenant_id=tenant_id,
                    model_id=model_id,
                    command=apply_command.model_copy(update={"expected_plan_digest": "0" * 64}),
                    idempotency_key=uuid4(),
                )
            inventory = await targets.bindings(
                principal, tenant_id=tenant_id, model_id=model_id, layer=layer
            )
            assert inventory.items[0].object_id is None
            request = GenerateModelBindingsRequest(
                layer=layer,
                object_schema=object_binding["object_schema"],
                expected_model_revision=revision,
            )
            if generation:
                empty = await service.bind_registered_target(
                    principal,
                    tenant_id=tenant_id,
                    model_id=model_id,
                    command=request.model_copy(update={"object_schema": "missing_schema"}),
                )
                assert isinstance(empty, GeneratedBindingsPreview) and not empty.can_apply
                assert empty.matches[0].status == "unmatched"
                generated = await service.bind_registered_target(
                    principal, tenant_id=tenant_id, model_id=model_id, command=request
                )
                assert isinstance(generated, GeneratedBindingsPreview) and generated.can_apply
                assert generated.matches[0].status == "matched"
                apply_command = request.model_copy(
                    update={"expected_plan_digest": generated.plan_digest}
                )
            key = uuid4()
            result = await service.bind_registered_target(
                principal,
                tenant_id=tenant_id,
                model_id=model_id,
                command=apply_command,
                idempotency_key=key,
            )
            assert isinstance(result, ReviewModelRecordsResult)
            assert result.action_count == 3
            assert result.model_revision == revision + 1
            replay = await service.bind_registered_target(
                principal,
                tenant_id=tenant_id,
                model_id=model_id,
                command=apply_command,
                idempotency_key=key,
            )
            assert replay == result
            with pytest.raises(ModelRevisionConflictError):
                await service.bind_registered_target(
                    principal,
                    tenant_id=tenant_id,
                    model_id=model_id,
                    command=apply_command,
                    idempotency_key=uuid4(),
                )
            inventory = await targets.bindings(
                principal, tenant_id=tenant_id, model_id=model_id, layer=layer
            )
            assert (
                inventory.items[0].object_id == object_id
                and inventory.items[0].binding_id is not None
            )
            if generation:
                unchanged = await service.bind_registered_target(
                    principal,
                    tenant_id=tenant_id,
                    model_id=model_id,
                    command=request.model_copy(
                        update={"expected_model_revision": result.model_revision}
                    ),
                )
                assert isinstance(unchanged, GeneratedBindingsPreview) and not unchanged.can_apply
                assert unchanged.matches[0].status == "existing"
            revision = result.model_revision
            bound_targets = await targets.targets(
                principal,
                tenant_id=tenant_id,
                model_id=model_id,
                layer=layer,
                search="",
                after=0,
                object_schema=object_binding["object_schema"],
            )
            assert any(entity_id in item.bound_entity_ids for item in bound_targets.items)
        with fixture.connect_owner() as connection:
            counts = connection.execute(
                "SELECT (SELECT count(*) FROM workflow.model_object_binding "
                "WHERE model_id=%s) AS objects, "
                "(SELECT count(*) FROM workflow.model_attribute_binding a "
                "JOIN workflow.model_object_binding o USING(model_object_binding_id) "
                "WHERE o.model_id=%s) AS attributes",
                (model_id, model_id),
            ).fetchone()
            assert counts == {"objects": 2, "attributes": 4}
    finally:
        await database.close()
