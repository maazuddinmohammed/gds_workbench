"""Permanent deletion uses a disposable database and the restricted web role."""

# pyright: reportPrivateUsage=false
from dataclasses import replace
from typing import cast
from uuid import uuid4

import pytest
from gds_etl_workbench.application.authorization import AuthorizationService
from gds_etl_workbench.application.change_sets.model import load_model_physical_scope
from gds_etl_workbench.application.change_sets.model_apply import ModelMaterializer
from gds_etl_workbench.application.change_sets.model_validation import validate_future_graph
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
)
from gds_workbench_api.features.model_change_sets.review import ModelLayer, ModelReviewDataset
from gds_workbench_api.features.model_change_sets.service import DatabaseModelChangeSetService
from psycopg import sql

from tests.mcp.conftest import DisposablePostgres
from tests.mcp.model_test_fixtures import complete_model_graph
from tests.mcp.test_database_model_change_set_round_trip import (
    StaticIdentityProvider,
    _acquire_tenant_lock,
    _replace_codes,
    _seed_model_foundation,
)


@pytest.mark.parametrize(
    ("layer", "selection"),
    [
        ("conceptual", "clear"),
        ("logical", "clear"),
        ("dimensional", "clear"),
        ("conceptual", "object"),
        ("logical", "entity"),
        ("logical", "attribute"),
        ("logical", "submodel"),
        ("dimensional", "entity"),
    ],
)
async def test_permanent_clear_includes_supports_and_replays_without_restoring_rows(
    web_postgres_database: DisposablePostgres,
    layer: ModelLayer,
    selection: str,
) -> None:
    fixture = web_postgres_database
    prefix = "DELETE_LAYER_" + uuid4().hex
    model_id, tenant_id = _seed_model_foundation(fixture, code_prefix=prefix)
    model = ModelReadContext(
        model_id=model_id, tenant_id=tenant_id, model_name="Model Tool Round Trip", model_revision=1
    )
    runtime = fixture.create_runtime_adapter()
    await runtime.open()
    try:
        async with runtime.write_transaction() as transaction:
            graph = complete_model_graph()
            # Inactive records must be deleted too, not left to block parent FKs.
            graph["conceptual_relationship"][0]["conceptual_relationship_status"] = "inactive"
            validation = validate_future_graph(
                snapshot=await build_model_snapshot(transaction, model),
                physical_scope=await load_model_physical_scope(transaction, model),
                staged_documents=_replace_codes(graph, code_prefix=prefix),
            )
            assert validation.valid
            await ModelMaterializer(transaction, model_id, "a" * 64).apply(validation.records)
    finally:
        await runtime.close()
    _acquire_tenant_lock(fixture, tenant_id)
    database = WebPostgresDatabase(
        dsn=fixture.web_runtime_dsn(), pool_min=1, pool_max=1, pool_timeout_seconds=5
    )
    service = DatabaseModelChangeSetService(database=database, authorizer=AuthorizationService())
    principal = StaticIdentityProvider().request_principal(None)
    dataset = cast(
        ModelReviewDataset,
        "conceptual_object"
        if layer == "conceptual"
        else f"{layer}_{'entity' if selection == 'clear' else selection}",
    )
    await database.open()
    try:
        async with database.read_transaction() as transaction:
            before = await read_model_review_snapshot(transaction, model)
        selected_id = min(before.records_by_id[dataset])
        preview_command = PreviewModelRecordsRequest(
            dataset=dataset,
            record_ids=[] if selection == "clear" else [selected_id],
            layer=layer if selection == "clear" else None,
            action="delete",
            expected_model_revision=1,
        )
        with pytest.raises(WorkbenchError) as forbidden:
            await service.preview_record_review(
                principal, tenant_id=tenant_id, model_id=model_id, command=preview_command
            )
        assert forbidden.value.code == "authorization_denied"
        with fixture.connect_owner() as connection:
            connection.execute(
                "UPDATE security.tenant_principal_access SET tenant_role = 'tenant_admin' "
                "WHERE tenant_id = %s",
                (tenant_id,),
            )
            actor = connection.execute(
                "SELECT principal_id, entra_principal_identity_id "
                "FROM security.entra_principal_identity "
                "WHERE entra_tenant_id = %s AND entra_object_id = %s",
                (principal.entra_tenant_id, principal.entra_object_id),
            ).fetchone()
            assert actor is not None
            run = connection.execute(
                """
                INSERT INTO application.workflow_run (
                    tenant_id, model_id, model_revision, model_workflow,
                    workflow_execution_mode, actor_principal_id,
                    actor_entra_principal_identity_id, agent_sdk_code, agent_provider_code,
                    agent_model_code, reasoning_effort_code, max_turns,
                    validation_retry_count, selected_scope_digest, selected_scope_count,
                    workflow_run_state, correlation_id, started_time, completed_time,
                    modeled_entity_type, mapping_operation, mapping_coverage_mode, mapping_route
                ) VALUES (%s, %s, 1, 'mapping', 'one_shot', %s, %s,
                    'openai_agents_sdk', 'databricks', 'test-model', 'medium', 8, 1,
                    %s, 1, 'completed', %s, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP,
                    'logical_entity', 'generate', 'selected_targets', 'logical_to_silver')
                RETURNING workflow_run_id
                """,
                (
                    tenant_id,
                    model_id,
                    actor["principal_id"],
                    actor["entra_principal_identity_id"],
                    "a" * 64,
                    uuid4(),
                ),
            ).fetchone()
            assert run is not None
            connection.execute(
                """
                INSERT INTO application.workflow_run_mapping_target_selection (
                    workflow_run_id, model_id, object_id, source_system_id, selection_order
                ) SELECT %s, mapping.model_id, binding.object_id, mapping.source_system_id, 1
                    FROM workflow.mapping_object AS mapping
                    JOIN workflow.model_object_binding AS binding USING (model_object_binding_id)
                    WHERE mapping.model_id = %s
                    ORDER BY mapping_object_id LIMIT 1
                """,
                (run["workflow_run_id"], model_id),
            )
        preview = await service.preview_record_review(
            principal, tenant_id=tenant_id, model_id=model_id, command=preview_command
        )
        assert preview.can_apply and preview.action_count > 0
        assert all(item.desired_status == "deleted" for item in preview.items)
        assert any(
            name.endswith(("_support", "_source_mapping", "_entity_submodel"))
            for name in preview.changes_by_dataset
        )
        if layer == "logical" and selection != "submodel":
            assert all(
                preview.changes_by_dataset.get(kind, 0) > 0
                for kind in (
                    "model_object_binding",
                    "model_attribute_binding",
                    "mapping_object",
                    "mapping_attribute",
                    "generated_code",
                    "generated_code_source_system",
                )
            )
        support = next(
            item
            for item in preview.items
            if item.dataset.endswith(("_support", "_source_mapping", "_entity_submodel"))
        )
        with fixture.connect_owner() as connection:
            connection.execute(
                sql.SQL("UPDATE workflow.{} SET {} = TRUE WHERE {} = %s").format(
                    sql.Identifier(support.dataset),
                    sql.Identifier(support.dataset + "_is_locked"),
                    sql.Identifier(support.dataset + "_id"),
                ),
                (support.record_id,),
            )
        blocked = await service.preview_record_review(
            principal, tenant_id=tenant_id, model_id=model_id, command=preview_command
        )
        assert not blocked.can_apply and blocked.issue_count == 1
        with pytest.raises(WorkbenchError) as locked:
            await service.review_records(
                principal,
                tenant_id=tenant_id,
                model_id=model_id,
                command=ReviewModelRecordsRequest.model_validate(
                    {**preview_command.model_dump(), "expected_plan_digest": blocked.plan_digest}
                ),
                idempotency_key=uuid4(),
            )
        assert locked.value.code == "record_locked"
        with fixture.connect_owner() as connection:
            connection.execute(
                sql.SQL("UPDATE workflow.{} SET {} = FALSE WHERE {} = %s").format(
                    sql.Identifier(support.dataset),
                    sql.Identifier(support.dataset + "_is_locked"),
                    sql.Identifier(support.dataset + "_id"),
                ),
                (support.record_id,),
            )
            permissions = connection.execute("""SELECT
                has_function_privilege('gds_web_write',
                    'application.delete_model_records(uuid,uuid,bigint,bigint,bigint,uuid,jsonb)',
                    'EXECUTE') AS web,
                has_function_privilege('gds_app_write',
                    'application.delete_model_records(uuid,uuid,bigint,bigint,bigint,uuid,jsonb)',
                    'EXECUTE') AS mcp,
                has_table_privilege('gds_web_write', 'workflow.logical_entity', 'DELETE') AS direct
            """).fetchone()
            assert permissions == {"web": True, "mcp": False, "direct": False}
        preview = await service.preview_record_review(
            principal, tenant_id=tenant_id, model_id=model_id, command=preview_command
        )
        with pytest.raises(WorkbenchError) as unconfirmed:
            await service.review_records(
                principal,
                tenant_id=tenant_id,
                model_id=model_id,
                command=ReviewModelRecordsRequest(**preview_command.model_dump()),
                idempotency_key=uuid4(),
            )
        assert unconfirmed.value.code == "review_confirmation_required"
        command = ReviewModelRecordsRequest.model_validate(
            {**preview_command.model_dump(), "expected_plan_digest": preview.plan_digest}
        )
        key = uuid4()
        result = await service.review_records(
            principal, tenant_id=tenant_id, model_id=model_id, command=command, idempotency_key=key
        )
        assert result.action_count == preview.action_count and result.model_revision == 2
        assert (
            await service.review_records(
                principal,
                tenant_id=tenant_id,
                model_id=model_id,
                command=command,
                idempotency_key=key,
            )
            == result
        )
        async with database.read_transaction() as transaction:
            remaining = await read_model_review_snapshot(
                transaction, replace(model, model_revision=2)
            )
        if selection == "clear":
            assert not remaining.records_by_id.get(dataset)
        else:
            assert selected_id not in remaining.records_by_id.get(dataset, {})
            assert set(before.records_by_id[dataset]) - {selected_id} == set(
                remaining.records_by_id.get(dataset, {})
            )
        if selection == "submodel":
            assert remaining.snapshot.logical.entities
            assert remaining.snapshot.model_binding.objects
            assert remaining.snapshot.code_generation.artifacts
        assert remaining.snapshot.assertion.records
        if layer == "conceptual":
            assert remaining.snapshot.logical.entities and remaining.snapshot.dimensional.entities
        else:
            assert remaining.snapshot.conceptual.objects
        with fixture.connect_owner() as connection:
            for item in preview.items:
                row = connection.execute(
                    sql.SQL("SELECT count(*) AS count FROM workflow.{} WHERE {} = %s").format(
                        sql.Identifier(item.dataset), sql.Identifier(item.dataset + "_id")
                    ),
                    (item.record_id,),
                ).fetchone()
                assert row is not None and row["count"] == 0
            physical = connection.execute("SELECT count(*) AS count FROM core.object").fetchone()
            assert physical is not None and physical["count"] > 0
            history = connection.execute(
                "SELECT count(*) AS count FROM application.workflow_run AS run "
                "JOIN application.workflow_run_mapping_target_selection USING (workflow_run_id) "
                "WHERE run.workflow_run_id = %s AND run.workflow_run_state = 'completed'",
                (run["workflow_run_id"],),
            ).fetchone()
            assert history is not None and history["count"] == 1
        with pytest.raises(WorkbenchError) as missing:
            await service.preview_record_review(
                principal,
                tenant_id=tenant_id,
                model_id=model_id,
                command=PreviewModelRecordsRequest(
                    dataset=dataset,
                    record_ids=[
                        next(item.record_id for item in preview.items if item.dataset == dataset)
                    ],
                    action="reactivate",
                    expected_model_revision=2,
                ),
            )
        assert missing.value.code == "model_record_not_found"
    finally:
        await database.close()
