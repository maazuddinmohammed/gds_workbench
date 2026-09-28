"""Real web Entity export and independent registration transactions on a disposable fixture database."""

# pyright: reportPrivateUsage=false
from uuid import uuid4

import pytest
from gds_etl_workbench.application.authorization import AuthorizationService
from gds_etl_workbench.application.change_sets.model import StageModelChange
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
    StageModelChangeSetRequest,
)
from gds_workbench_api.features.model_change_sets.service import (
    DatabaseModelChangeSetService,
)
from gds_workbench_api.features.model_targets.contracts import ExportModelTargetsRequest
from gds_workbench_api.features.model_targets.service import DatabaseModelTargetsService
from gds_workbench_api.features.models import ModelRevisionConflictError

from tests.mcp.conftest import DisposablePostgres
from tests.mcp.test_database_model_entity_order import entity_layer_graph
from tests.mcp.test_database_model_change_set_round_trip import (
    StaticIdentityProvider,
    _acquire_tenant_lock,
    _seed_model_foundation,
)


async def test_both_layers_export_saved_schemas_and_register_independently(
    web_postgres_database: DisposablePostgres,
) -> None:
    fixture = web_postgres_database
    prefix = f"TARGETS_{uuid4().hex}"
    model_id, tenant_id = _seed_model_foundation(fixture, code_prefix=prefix)
    _acquire_tenant_lock(fixture, tenant_id)
    graph = entity_layer_graph(prefix)
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
                columns = connection.execute(
                    f"SELECT * FROM workflow.{layer}_attribute WHERE model_id=%s "
                    f"ORDER BY {layer}_attribute_id",
                    (model_id,),
                ).fetchall()
            options = await targets.options(principal, tenant_id=tenant_id, model_id=model_id)
            assert options.placement is not None
            assert options.model_revision == revision
            command = ExportModelTargetsRequest(
                layer=layer,
                expected_model_revision=revision,
                object_type_code=f"{prefix}_TABLE",
            )
            workbook = await targets.export(
                principal, tenant_id=tenant_id, model_id=model_id, command=command
            )
            sheets = parse_metadata_workbook(workbook.content, tenant_id=tenant_id)
            assert sheets[0].rows[0]["object_type_code"] == f"{prefix}_TABLE"
            assert sheets[0].rows[0]["object_name"] == graph["logical_entity" if layer == "logical" else "dimensional_entity"][0][layer + "_entity_name"]
            assert sheets[0].rows[0]["object_schema"] == ("silver" if layer == "logical" else "gold")
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

            # Export remains read-only and independent from registration.
            existing_export = await targets.export(
                principal, tenant_id=tenant_id, model_id=model_id, command=command,
            )
            assert existing_export.content
            with pytest.raises(ModelRevisionConflictError):
                await targets.export(principal, tenant_id=tenant_id, model_id=model_id,
                    command=command.model_copy(update={"expected_model_revision": revision - 1}))
    finally:
        await database.close()
