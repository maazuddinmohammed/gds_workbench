"""Installed defaults -> real repositories/stages -> governed draft/apply; synthetic agents only."""

# Existing builders create only fixture-owned disposable database contents.
# pyright: reportPrivateUsage=false
from typing import Literal, cast
from uuid import uuid4

import pytest
from gds_etl_workbench.application.authorization import AuthorizationService
from gds_etl_workbench.domain.authorization import ActorKind, RequestPrincipal
from gds_etl_workbench.domain.errors import WorkbenchError
from gds_workbench_api.capabilities import (
    AgentRunSelection,
    load_default_agent_capabilities,
)
from gds_workbench_api.database import WebPostgresDatabase
from gds_workbench_api.features.mapping.contracts import MappingTargetSelection
from gds_workbench_api.features.mapping.read_contracts import (
    MappingAttributeFilters,
    MappingFilters,
)
from gds_workbench_api.features.mapping.read_service import DatabaseMappingReviewService
from gds_workbench_api.features.workflows.authoring.agent_execution import (
    AgentExecutionRequest,
    AgentExecutionResult,
)
from gds_workbench_api.features.workflows.authoring.change_set_apply import (
    ApplyWorkflowDraftRequest,
    DatabaseWorkflowDraftApplyService,
)
from gds_workbench_api.features.workflows.authoring.change_set_handoff import (
    WorkflowChangeSetHandoffResult,
)
from gds_workbench_api.features.workflows.authoring.lifecycle import (
    DatabaseAgentWorkflowLifecycle,
)
from gds_workbench_api.features.workflows.commands import (
    CreateWorkflowRunRequest,
    DatabaseWorkflowCommandService,
)
from gds_workbench_api.features.workflows.execution.assembly import (
    create_workflow_runtime_services,
)
from gds_workbench_api.features.workflows.execution.dispatcher import (
    WorkflowExecutionDispatcher,
)
from gds_workbench_api.features.workflows.execution.repository import (
    DatabaseWorkflowClaimRepository,
)
from gds_workbench_api.features.workflows.runs import DatabaseWorkflowRunService
from gds_workbench_api.integrations.agents import LocalFakeAgentAdapter
from gds_workbench_api.integrations.agents.configuration import (
    AgentRuntimeConfiguration,
)
from gds_workbench_api.integrations.databricks.runtime import (
    create_databricks_execution_adapters,
)
from psycopg import sql
from pydantic import JsonValue

from tests.mcp.conftest import DisposablePostgres
from tests.mcp.conftest import (
    bootstrap_postgres_database as bootstrap_postgres_database,
)
from tests.mcp.database_test_support import require_row
from tests.mcp.test_database_global_prompt_seed import (
    REFERENCE_SEED,
    _apply_sql,
    _render_seed,
    _seed_super_admin,
)
from tests.mcp.test_database_mapping_output_template_seed import (
    seed_mapping_output_templates,
)
from tests.web_backend.test_database_mapping_source_context import (
    MappingScope,
    _seed_assertion_mapping_target,
    _seed_mapping_scope,
)


@pytest.fixture(scope="module")
def pipeline_database(
    bootstrap_postgres_database: DisposablePostgres,
) -> DisposablePostgres:
    database = bootstrap_postgres_database
    _apply_sql(database, REFERENCE_SEED.read_text(encoding="utf-8"))
    _seed_super_admin(database)
    _apply_sql(database, _render_seed())
    seed_mapping_output_templates(database)
    return database


@pytest.mark.parametrize("mapping_mode", ["one_shot", "tool_assisted"])
@pytest.mark.parametrize(
    "bulk,dimensional",
    [
        ("single", False),
        ("complete", False),
        ("partial", False),
        ("partial", True),
        ("single", True),
        ("complete", True),
        ("multi_system", False),
        ("multi_system", True),
        ("assertion", False),
        ("assertion", True),
        ("object_only", False),
        ("object_only", True),
        ("attribute_only", False),
        ("attribute_only", True),
        ("partial_attributes", False),
        ("partial_attributes", True),
        ("empty", False),
        ("empty", True),
    ],
)
async def test_mapping_code_validation_pipeline_uses_real_persistence_and_apply(
    pipeline_database: DisposablePostgres,
    monkeypatch: pytest.MonkeyPatch,
    mapping_mode: Literal["one_shot", "tool_assisted"],
    bulk: str,
    dimensional: bool,
) -> None:
    fixture = pipeline_database
    scope = _seed_mapping_scope(fixture, dimensional=dimensional, create_run=False)
    model_id = scope.plan.model_id
    entity_type = "dimensional_entity" if dimensional else "logical_entity"
    partial_shape = bulk in {
        "object_only",
        "attribute_only",
        "partial_attributes",
        "empty",
    }
    if bulk == "assertion":
        _seed_assertion_mapping_target(fixture, scope, dimensional=dimensional)
    elif bulk != "single":
        _add_mapping_target(
            fixture,
            model_id,
            scope.plan.pair.modeled_entity_id,
            dimensional=dimensional,
        )
    if partial_shape:
        layer = "dimensional" if dimensional else "logical"
        with fixture.connect_owner() as connection:
            columns = [
                "model_id",
                f"{layer}_entity_id",
                f"{layer}_attribute_name",
                f"{layer}_attribute_definition",
                f"{layer}_attribute_data_type",
                f"{layer}_attribute_ordinal_position",
            ]
            values = "entity.model_id, entity.modeled_entity_id, 'fixture_' || position, "
            values += "'Synthetic test Attribute.', 'bigint', position"
            if dimensional:
                columns.append("dimensional_attribute_role")
                values += ", 'descriptor'"
            connection.execute(
                sql.SQL(
                    "INSERT INTO workflow.{} ({}) SELECT {} "
                    "FROM workflow.modeled_entity entity CROSS JOIN generate_series(2,10) position "
                    "WHERE entity.model_id=%s AND entity.modeled_entity_type=%s "
                    "AND entity.modeled_entity_name='SecondCustomer'"
                ).format(
                    sql.Identifier(f"{layer}_attribute"),
                    sql.SQL(",").join(map(sql.Identifier, columns)),
                    sql.SQL(values),
                ),
                (model_id, entity_type),
            )
    if bulk == "multi_system" or partial_shape:
        _add_mapping_system(fixture, scope)
    with fixture.connect_owner() as connection:
        actor = require_row(
            connection.execute(
                "SELECT entra_tenant_id, entra_object_id FROM security.entra_principal_identity "
                "WHERE principal_id = %s",
                (scope.plan.actor_principal_id,),
            ).fetchone()
        )
        acquired = require_row(
            connection.execute(
                "SELECT acquired FROM security.acquire_tenant_lock(%s, %s, 'user', %s, 60, "
                "'Fixture agent pipeline verification')",
                (actor["entra_tenant_id"], actor["entra_object_id"], scope.tenant_id),
            ).fetchone()
        )
    assert acquired["acquired"]
    principal = RequestPrincipal(
        actor_kind=ActorKind.HUMAN,
        entra_tenant_id=actor["entra_tenant_id"],
        entra_object_id=actor["entra_object_id"],
    )
    with fixture.connect_owner() as connection:
        preserved_objects = connection.execute(
            "SELECT to_jsonb(mapping) AS record FROM workflow.mapping_object mapping "
            "WHERE model_id=%s AND modeled_entity_type=%s "
            "AND coalesce(logical_entity_id, dimensional_entity_id)=%s "
            "ORDER BY mapping_object_id",
            (model_id, entity_type, scope.plan.pair.modeled_entity_id),
        ).fetchall()
        preserved_attributes = connection.execute(
            "SELECT to_jsonb(attribute) AS record "
            "FROM workflow.mapping_attribute attribute "
            "JOIN workflow.mapping_object mapping USING(mapping_object_id, model_id) "
            "WHERE mapping.model_id=%s AND mapping.modeled_entity_type=%s "
            "AND coalesce(mapping.logical_entity_id, mapping.dimensional_entity_id)=%s "
            "ORDER BY mapping_attribute_id",
            (model_id, entity_type, scope.plan.pair.modeled_entity_id),
        ).fetchall()
    calls: list[tuple[str, str, int]] = []
    mapping_calls = 0
    original_execute = LocalFakeAgentAdapter.execute

    async def recording_execute(
        self: LocalFakeAgentAdapter, request: AgentExecutionRequest
    ) -> AgentExecutionResult:
        nonlocal mapping_calls
        if partial_shape and request.workflow in {"code_generation", "validation"}:
            outer = cast(dict[str, JsonValue], request.context)
            original = cast(dict[str, JsonValue], outer["original_context"])
            values = cast(dict[str, JsonValue], original["values"])
            if request.workflow == "code_generation":
                target = cast(dict[str, JsonValue], values["target_metadata"])
                if bulk == "empty":
                    assert target["object_name"] != "SecondCustomer"
                elif target["object_name"] == "SecondCustomer":
                    attributes = cast(
                        list[dict[str, JsonValue]], values["attribute_transformations"]
                    )
                    assert len(attributes) == 20
                    expected_blank_count = {
                        "object_only": 20,
                        "attribute_only": 0,
                        "partial_attributes": 10,
                    }[bulk]
                    assert (
                        sum(row["transformation"] is None for row in attributes)
                        == expected_blank_count
                    )
            else:
                evidence = cast(list[dict[str, JsonValue]], values["mapping_evidence"])
                assert evidence
                assert all(row["modeled_entity_name"] != "SecondCustomer" for row in evidence)
        if request.workflow == "mapping":
            mapping_calls += 1
            if bulk == "partial" and mapping_calls == 1:
                calls.append((request.workflow, request.execution_mode, 0))
                raise TimeoutError("Synthetic provider timeout")
        result = await original_execute(self, request)
        if partial_shape and bulk != "empty" and request.workflow == "code_generation":
            outer = cast(dict[str, JsonValue], request.context)
            original = cast(dict[str, JsonValue], outer["original_context"])
            values = cast(dict[str, JsonValue], original["values"])
            target = cast(dict[str, JsonValue], values["target_metadata"])
            if target["object_name"] == "SecondCustomer":
                # Synthetic provider output exercises the real SQL validation/draft/Apply path.
                transforms = cast(list[dict[str, JsonValue]], values["attribute_transformations"])
                systems = cast(list[dict[str, JsonValue]], values["source_systems"])
                fields = cast(list[dict[str, JsonValue]], target["attributes"])
                selects: list[str] = []
                for system in systems:
                    missing = {
                        cast(str, row["modeled_attribute_name"])
                        for row in transforms
                        if row["source_system_code"] == system["system_code"]
                        and row["transformation"] is None
                    }
                    expressions = [
                        f"CAST({'NULL' if field['attribute_name'] in missing else '1'} "
                        f"AS {field['attribute_data_type']}) AS `{field['attribute_name']}`"
                        for field in fields
                        if field.get("is_active", True)
                        and field.get("population") not in {"database", "framework"}
                    ]
                    selects.append("SELECT " + ", ".join(expressions))
                candidate = cast(dict[str, JsonValue], result.candidate)
                artifacts = cast(list[dict[str, JsonValue]], candidate["artifacts"])
                result = result.model_copy(
                    update={
                        "candidate": {
                            **candidate,
                            "artifacts": [
                                {**artifact, "generated_sql": "\nUNION ALL\n".join(selects) + ";\n"}
                                for artifact in artifacts
                            ],
                        }
                    }
                )
        if request.workflow == "mapping" and partial_shape:
            candidate = cast(dict[str, JsonValue], result.candidate)
            attributes = cast(list[JsonValue], candidate["attribute_mappings"])
            if len(attributes) == 10:
                candidate = {
                    **candidate,
                    "object_mapping": None
                    if bulk in {"attribute_only", "empty"}
                    else candidate["object_mapping"],
                    "attribute_mappings": []
                    if bulk in {"object_only", "empty"}
                    else attributes[:5]
                    if bulk == "partial_attributes"
                    else attributes,
                }
                result = result.model_copy(update={"candidate": candidate})
        calls.append((request.workflow, request.execution_mode, result.tool_call_count))
        return result

    monkeypatch.setattr(LocalFakeAgentAdapter, "execute", recording_execute)
    database = WebPostgresDatabase(
        dsn=fixture.web_runtime_dsn(), pool_min=1, pool_max=2, pool_timeout_seconds=5
    )
    authorizer = AuthorizationService()
    capabilities = load_default_agent_capabilities()
    services = create_workflow_runtime_services(
        database=database,
        authorizer=authorizer,
        agent_runtime=AgentRuntimeConfiguration(mode="fake", timeout_seconds=120, connections=()),
        agent_capability_registry=capabilities,
        databricks_environment_code="fixture",
        databricks_execution=create_databricks_execution_adapters("fake"),
    )
    dispatcher = WorkflowExecutionDispatcher(services.execution_services())
    commands = DatabaseWorkflowCommandService(
        database=database, authorizer=authorizer, agent_capability_registry=capabilities
    )
    lifecycle = DatabaseAgentWorkflowLifecycle(database=database)
    claims = DatabaseWorkflowClaimRepository(database=database)
    apply_service = DatabaseWorkflowDraftApplyService(database=database, authorizer=authorizer)
    runs = DatabaseWorkflowRunService(
        database=database,
        authorizer=authorizer,
        cursor_signing_key=b"fixture-signing-key" * 2,
    )
    mapping_review = DatabaseMappingReviewService(
        database=database,
        authorizer=authorizer,
        cursor_signing_key=b"fixture-key" * 4,
    )
    selection = AgentRunSelection(
        sdk_code="openai_agents_sdk",
        provider_code="microsoft_foundry",
        model_code="foundry-primary",
        reasoning_effort_code="low",
        max_turns=8,
        validation_retry_count=1,
    )
    run_ids: list[int] = []
    await database.open()
    try:
        targets = await mapping_review.list_generation_targets(
            principal,
            tenant_id=scope.tenant_id,
            model_id=model_id,
            entity_type=entity_type,
            page_size=200,
            cursor=None,
        )
        eligible = [row for row in targets.items if row.has_sources]
        expected_pair_count = (
            1 if bulk == "single" else 4 if bulk == "multi_system" or partial_shape else 2
        )
        assert len(eligible) == expected_pair_count
        assert all(row.attributes and not row.is_locked for row in eligible)
        selected_entity_ids = sorted({row.entity_id for row in eligible})
        selected_system_codes = sorted({row.source_system.system_code for row in eligible})
        expected_pairs = {(row.entity_id, row.source_system.system_id) for row in eligible}
        successful_entity_ids = (
            [scope.plan.pair.modeled_entity_id]
            if partial_shape
            else [
                entity
                for entity in selected_entity_ids
                if entity != scope.plan.pair.modeled_entity_id
            ]
            if bulk == "partial"
            else selected_entity_ids
        )
        successful_pairs = {pair for pair in expected_pairs if pair[0] in successful_entity_ids}
        code_entity_ids = (
            selected_entity_ids if partial_shape and bulk != "empty" else successful_entity_ids
        )
        code_pairs_expected = {pair for pair in expected_pairs if pair[0] in code_entity_ids}
        selections = [
            MappingTargetSelection(
                modeled_entity_id=row.entity_id,
                source_system_id=row.source_system.system_id,
                selected_attribute_ids=[attribute.attribute_id for attribute in row.attributes],
            )
            for row in eligible
        ]
        if bulk == "partial":
            # Frozen selection and dependency execution deliberately have different orders.
            selections.sort(
                key=lambda target: target.modeled_entity_id == scope.plan.pair.modeled_entity_id
            )
        for revision, workflow in enumerate(("mapping", "code_generation", "validation"), 1):
            if workflow == "mapping":
                command = CreateWorkflowRunRequest(
                    expected_model_revision=revision,
                    model_workflow="mapping",
                    workflow_execution_mode=mapping_mode,
                    selected_entity_ids=selected_entity_ids,
                    modeled_entity_type=entity_type,
                    mapping_operation=("build" if dimensional else "extend")
                    if bulk == "single"
                    else "generate",
                    mapping_targets=selections if bulk != "single" else None,
                    mapping_coverage_mode="selected_targets",
                    mapping_source_system_id=scope.source_system_id if bulk == "single" else None,
                    agent=selection,
                )
            elif workflow == "code_generation":
                command = CreateWorkflowRunRequest(
                    expected_model_revision=revision,
                    model_workflow="code_generation",
                    selected_entity_ids=code_entity_ids,
                    modeled_entity_type=entity_type,
                    code_generation_coverage_mode="selected_targets",
                    agent=selection,
                )
            else:
                command = CreateWorkflowRunRequest(
                    expected_model_revision=revision,
                    model_workflow="validation",
                    selected_object_ids=[],
                    selected_system_codes=selected_system_codes,
                    agent=selection,
                )
            created = await commands.create_run(
                principal,
                tenant_id=scope.tenant_id,
                model_id=model_id,
                correlation_id=uuid4(),
                command=command,
            )
            assert created.created and created.prompt_snapshot_count == 1
            if workflow == "mapping" and bulk != "single":
                with fixture.connect_owner() as connection:
                    frozen = connection.execute(
                        "SELECT entity.modeled_entity_id, target.source_system_id, "
                        "target.selected_attribute_ids "
                        "FROM application.workflow_run_mapping_target_selection target "
                        "JOIN application.workflow_run_entity_selection entity "
                        "USING (workflow_run_entity_selection_id, workflow_run_id, model_id) "
                        "WHERE target.workflow_run_id=%s ORDER BY target.selection_order",
                        (created.workflow_run_id,),
                    ).fetchall()
                assert len(frozen) == expected_pair_count
                assert {
                    (row["modeled_entity_id"], row["source_system_id"]) for row in frozen
                } == expected_pairs
                assert {row["modeled_entity_id"] for row in frozen} == set(
                    command.selected_entity_ids
                )
                assert all(row["selected_attribute_ids"] for row in frozen)
                if bulk == "partial":
                    assert frozen[0]["modeled_entity_id"] != scope.plan.pair.modeled_entity_id
                    assert frozen[-1]["modeled_entity_id"] == scope.plan.pair.modeled_entity_id
            run_ids.append(created.workflow_run_id)
            await lifecycle.start(
                principal,
                tenant_id=scope.tenant_id,
                model_id=model_id,
                workflow_run_id=created.workflow_run_id,
                expected_workflow=workflow,
                expected_execution_mode=command.workflow_execution_mode,
                expected_model_revision=revision,
            )
            claim = await claims.claim_next(lease_duration_seconds=300)
            assert claim is not None and claim.workflow_run_id == created.workflow_run_id
            draft = await dispatcher.execute(claim)
            assert isinstance(draft, WorkflowChangeSetHandoffResult)
            assert draft.staged_record_count > 0
            detail = await runs.read_run(
                principal,
                tenant_id=scope.tenant_id,
                model_id=model_id,
                workflow_run_id=created.workflow_run_id,
            )
            assert detail.workflow_run_state in {"completed", "completed_with_repair"}
            assert detail.failure_code is None
            assert detail.model_change_set_status == "validated"
            if workflow == "mapping":
                assert detail.mapping_outcome is not None
                assert detail.mapping_outcome.completed_pair_count == len(successful_pairs)
                assert detail.mapping_outcome.partial_pair_count == (
                    2 if partial_shape and bulk != "empty" else 0
                )
                assert detail.mapping_outcome.empty_pair_count == (2 if bulk == "empty" else 0)
                assert detail.mapping_outcome.failed_pair_count == int(bulk == "partial")
                assert detail.mapping_outcome.preserved_pair_count == 0
                assert detail.mapping_outcome.no_source_pair_count == 0
                assert not detail.mapping_failures_truncated
                if bulk == "partial":
                    assert len(detail.mapping_failures) == 1
                    failed_pair = detail.mapping_failures[0]
                    assert failed_pair.modeled_entity_id == scope.plan.pair.modeled_entity_id
                    assert failed_pair.source_system_id == scope.source_system_id
                    assert "agent" in failed_pair.message.lower()
                else:
                    assert not detail.mapping_failures
                ledger = await runs.list_runs(
                    principal,
                    tenant_id=scope.tenant_id,
                    model_id=model_id,
                    workflow="mapping",
                    run_state=None,
                    page_size=200,
                    cursor=None,
                )
                assert ledger.items[0].mapping_outcome == detail.mapping_outcome
            with fixture.connect_owner() as connection:
                before = require_row(
                    connection.execute(
                        "SELECT model_revision FROM model.model WHERE model_id=%s",
                        (model_id,),
                    ).fetchone()
                )
            assert before["model_revision"] == revision
            apply = ApplyWorkflowDraftRequest(
                expected_model_revision=revision,
                expected_draft_revision=draft.draft_revision,
                expected_candidate_digest=draft.candidate_digest,
            )
            key = uuid4()
            applied = await apply_service.apply(
                principal,
                tenant_id=scope.tenant_id,
                model_id=model_id,
                workflow_run_id=created.workflow_run_id,
                command=apply,
                idempotency_key=key,
            )
            replayed = await apply_service.apply(
                principal,
                tenant_id=scope.tenant_id,
                model_id=model_id,
                workflow_run_id=created.workflow_run_id,
                command=apply,
                idempotency_key=key,
            )
            assert applied.model_revision == revision + 1 and not applied.replayed
            assert replayed == applied.model_copy(update={"replayed": True})
            if workflow == "mapping" and partial_shape:
                objects = await mapping_review.list_objects(
                    principal,
                    tenant_id=scope.tenant_id,
                    model_id=model_id,
                    filters=MappingFilters(entity_type=entity_type),
                    page_size=200,
                    cursor=None,
                )
                partial_objects = [
                    row for row in objects.items if row.target.entity_name == "SecondCustomer"
                ]
                assert len(partial_objects) == (0 if bulk == "empty" else 2)
                for mapping in partial_objects:
                    object_detail = await mapping_review.read_object(
                        principal,
                        tenant_id=scope.tenant_id,
                        model_id=model_id,
                        mapping_object_id=mapping.mapping_object_id,
                    )
                    assert (object_detail.mapping_document is None) == (bulk == "attribute_only")
                    attributes = await mapping_review.list_attributes(
                        principal,
                        tenant_id=scope.tenant_id,
                        model_id=model_id,
                        filters=MappingAttributeFilters(
                            mapping_object_id=mapping.mapping_object_id
                        ),
                        page_size=200,
                        cursor=None,
                    )
                    assert len(attributes.items) == 10 and attributes.next_cursor is None
                    assert len({row.target.attribute_name for row in attributes.items}) == 10
                    documents = 0
                    for attribute in attributes.items:
                        if attribute.mapping_attribute_id is None:
                            assert attribute.status is None and attribute.updated_at is None
                            assert not attribute.is_locked
                            continue
                        attribute_detail = await mapping_review.read_attribute(
                            principal,
                            tenant_id=scope.tenant_id,
                            model_id=model_id,
                            mapping_attribute_id=attribute.mapping_attribute_id,
                        )
                        documents += int(attribute_detail.mapping_document is not None)
                    assert (
                        documents
                        == {
                            "object_only": 0,
                            "attribute_only": 10,
                            "partial_attributes": 5,
                        }[bulk]
                    )
                incomplete = [
                    entity for entity in selected_entity_ids if entity not in successful_entity_ids
                ]
                partial_code_command = CreateWorkflowRunRequest(
                    expected_model_revision=revision + 1,
                    model_workflow="code_generation",
                    selected_entity_ids=incomplete,
                    modeled_entity_type=entity_type,
                    code_generation_coverage_mode="selected_targets",
                    agent=selection,
                )
                if bulk == "empty":
                    with pytest.raises(WorkbenchError) as incomplete_mapping_error:
                        await commands.create_run(
                            principal,
                            tenant_id=scope.tenant_id,
                            model_id=model_id,
                            correlation_id=uuid4(),
                            command=partial_code_command,
                        )
                    assert incomplete_mapping_error.value.code == "code_mapping_incomplete"
                with fixture.connect_owner() as connection:
                    eligible_code = connection.execute(
                        "SELECT modeled_entity_id FROM "
                        "workflow.list_code_generation_target_context(%s,%s,NULL)",
                        (model_id, entity_type),
                    ).fetchall()
                assert {row["modeled_entity_id"] for row in eligible_code} == set(
                    successful_entity_ids
                )
    finally:
        await services.close()
        await database.close()
    expected_mapping_calls = expected_pair_count
    expected_downstream_calls = ["code_generation"] * len(code_entity_ids) + ["validation"] * len(
        selected_system_codes
    )
    assert [workflow for workflow, _, _ in calls] == (
        ["mapping"] * expected_mapping_calls + expected_downstream_calls
    )
    assert calls[0][1] == mapping_mode
    if bulk != "partial":
        assert (calls[0][2] > 0) == (mapping_mode == "tool_assisted")
    assert all(
        mode == "tool_assisted" and count > 0 for _, mode, count in calls[expected_mapping_calls:]
    )
    with fixture.connect_owner() as connection:
        states = connection.execute(
            "SELECT run.workflow_run_state, changes.model_change_set_status, "
            "(SELECT count(*) FROM mcp.model_change_set_event AS event "
            "WHERE event.model_change_set_id=changes.model_change_set_id "
            "AND event.event_type='applied') AS applied_event_count "
            "FROM application.workflow_run AS run LEFT JOIN mcp.model_change_set AS changes "
            "USING(workflow_run_id) WHERE run.workflow_run_id=ANY(%s)",
            (run_ids,),
        ).fetchall()
        mapping_pairs = connection.execute(
            "SELECT coalesce(logical_entity_id, dimensional_entity_id) AS entity_id, "
            "source_system_id FROM workflow.mapping_object "
            "WHERE model_id=%s AND modeled_entity_type=%s AND object_mapping_status='active'",
            (model_id, entity_type),
        ).fetchall()
        code_pairs = connection.execute(
            "SELECT coalesce(code.logical_entity_id, code.dimensional_entity_id) AS entity_id, "
            "assigned.source_system_id, code.generated_code_content, "
            "code.code_input_digest=live.code_input_digest AS current "
            "FROM workflow.generated_code code "
            "JOIN workflow.generated_code_source_system assigned USING(generated_code_id) "
            "JOIN workflow.list_code_generation_target_context(%s,%s) live "
            "ON live.modeled_entity_id=coalesce(code.logical_entity_id, "
            "code.dimensional_entity_id) "
            "WHERE code.model_id=%s AND code.modeled_entity_type=%s "
            "AND code.generated_code_status='active' "
            "AND assigned.generated_code_source_system_status='active'",
            (model_id, entity_type, model_id, entity_type),
        ).fetchall()
        existing_pairs: set[tuple[int, int]] = (
            {(scope.plan.pair.modeled_entity_id, scope.source_system_id)}
            if bulk == "partial" and preserved_objects
            else set()
        )
        assert {(row["entity_id"], row["source_system_id"]) for row in mapping_pairs} == (
            expected_pairs
            if partial_shape and bulk != "empty"
            else successful_pairs | existing_pairs
        )
        assert {
            (row["entity_id"], row["source_system_id"]) for row in code_pairs
        } == code_pairs_expected
        assert len(code_pairs) == len(code_pairs_expected)
        assert all(row["generated_code_content"] and row["current"] for row in code_pairs)
        if partial_shape and bulk != "empty":
            partial_code = [
                row for row in code_pairs if row["entity_id"] != scope.plan.pair.modeled_entity_id
            ]
            assert len(partial_code) == 2
            for row in partial_code:
                assert all(
                    f"AS `fixture_{position}`" in row["generated_code_content"]
                    for position in range(2, 11)
                )
                assert (
                    "CAST(NULL AS bigint)" in row["generated_code_content"]
                ) == (bulk in {"object_only", "partial_attributes"})
        if bulk == "partial":
            assert (
                connection.execute(
                    "SELECT to_jsonb(mapping) AS record FROM workflow.mapping_object mapping "
                    "WHERE model_id=%s AND modeled_entity_type=%s "
                    "AND coalesce(logical_entity_id, dimensional_entity_id)=%s "
                    "ORDER BY mapping_object_id",
                    (model_id, entity_type, scope.plan.pair.modeled_entity_id),
                ).fetchall()
                == preserved_objects
            )
            assert (
                connection.execute(
                    "SELECT to_jsonb(attribute) AS record "
                    "FROM workflow.mapping_attribute attribute "
                    "JOIN workflow.mapping_object mapping USING(mapping_object_id, model_id) "
                    "WHERE mapping.model_id=%s AND mapping.modeled_entity_type=%s "
                    "AND coalesce(mapping.logical_entity_id, mapping.dimensional_entity_id)=%s "
                    "ORDER BY mapping_attribute_id",
                    (model_id, entity_type, scope.plan.pair.modeled_entity_id),
                ).fetchall()
                == preserved_attributes
            )
    assert len(states) == 3
    assert all(row["model_change_set_status"] == "applied" for row in states)
    assert all(row["applied_event_count"] == 1 for row in states)


def _add_mapping_target(
    fixture: DisposablePostgres,
    model_id: int,
    entity_id: int,
    *,
    dimensional: bool = False,
) -> None:
    """Create another modeled target without registering a physical table."""
    if dimensional:
        with fixture.connect_owner() as connection:
            entity = require_row(
                connection.execute(
                    "INSERT INTO workflow.dimensional_entity "
                    "(model_id, dimensional_entity_schema_name, dimensional_entity_name, "
                    "dimensional_entity_definition, dimensional_entity_type, "
                    "dimensional_entity_grain_definition) "
                    "VALUES (%s, 'gold', 'SecondCustomer', 'Second customer projection.', "
                    "'dimension', 'One customer.') RETURNING dimensional_entity_id",
                    (model_id,),
                ).fetchone()
            )["dimensional_entity_id"]
            connection.execute(
                "INSERT INTO workflow.dimensional_attribute "
                "(model_id, dimensional_entity_id, dimensional_attribute_name, "
                "dimensional_attribute_definition, dimensional_attribute_data_type, "
                "dimensional_attribute_ordinal_position, dimensional_attribute_role) "
                "VALUES (%s,%s,'customer_id','Customer key.','bigint',1,'key')",
                (model_id, entity),
            )
            connection.execute(
                "INSERT INTO workflow.dimensional_entity_source_mapping "
                "(model_id, dimensional_entity_id, support_source_type, source_logical_entity_id, "
                "dimensional_entity_source_role, dimensional_entity_source_mapping_rationale) "
                "SELECT %s,%s,'logical_entity',source_logical_entity_id, "
                "'support','Synthetic source.' "
                "FROM workflow.dimensional_entity_source_mapping "
                "WHERE model_id=%s AND dimensional_entity_id=%s "
                "AND support_source_type='logical_entity'",
                (model_id, entity, model_id, entity_id),
            )
        return
    with fixture.connect_owner() as connection:
        entity = require_row(
            connection.execute(
                "INSERT INTO workflow.logical_entity (model_id, logical_entity_schema_name, "
                "logical_entity_name, logical_entity_definition, logical_entity_type, "
                "logical_entity_grain, logical_entity_dependency_order) "
                "VALUES (%s, 'silver', 'SecondCustomer', 'Second customer projection.', "
                "'core', 'One customer.', 1) RETURNING logical_entity_id",
                (model_id,),
            ).fetchone()
        )["logical_entity_id"]
        connection.execute(
            "INSERT INTO workflow.logical_attribute (model_id, logical_entity_id, "
            "logical_attribute_name, logical_attribute_definition, logical_attribute_data_type, "
            "logical_attribute_ordinal_position) "
            "VALUES (%s, %s, 'customer_id', 'Customer key.', 'bigint', 1)",
            (model_id, entity),
        )
        connection.execute(
            "INSERT INTO workflow.logical_entity_source_mapping (model_id, logical_entity_id, "
            "support_source_type, source_object_id, logical_entity_source_mapping_order, "
            "logical_entity_source_mapping_rationale) "
            "SELECT %s, %s, 'object', sources.source_object_id, "
            "sources.logical_entity_source_mapping_order, 'Synthetic source.' "
            "FROM workflow.logical_entity_source_mapping sources "
            "WHERE sources.model_id=%s AND sources.logical_entity_id=%s "
            "AND sources.support_source_type='object'",
            (model_id, entity, model_id, entity_id),
        )


def _add_mapping_system(fixture: DisposablePostgres, scope: MappingScope) -> None:
    """Add a second System and its support, including applied upstream Logical Mapping."""
    with fixture.connect_owner() as connection:
        source = require_row(
            connection.execute(
                "SELECT object.connection_id, connection.connection_type_id, system.system_type_id "
                "FROM core.object object JOIN core.connection connection USING(connection_id) "
                "JOIN core.system system USING(system_id) WHERE object.object_id=%s",
                (scope.source_object_id,),
            ).fetchone()
        )
        system_id = require_row(
            connection.execute(
                "INSERT INTO core.system(system_code,system_name,system_type_id) "
                "VALUES (%s,'Second business System',%s) RETURNING system_id",
                (f"SECOND_{scope.plan.model_id}", source["system_type_id"]),
            ).fetchone()
        )["system_id"]
        connection_id = require_row(
            connection.execute(
                "INSERT INTO core.connection(tenant_id,system_id,connection_code, "
                "connection_name,connection_type_id) "
                "VALUES (%s,%s,%s,'Second source',%s) RETURNING connection_id",
                (
                    scope.tenant_id,
                    system_id,
                    f"SECOND_{scope.plan.model_id}",
                    source["connection_type_id"],
                ),
            ).fetchone()
        )["connection_id"]
        object_id = require_row(
            connection.execute(
                "INSERT INTO core.object(connection_id,source_tenant_id,object_schema, "
                "object_name,object_type_id,zone_id) "
                "SELECT %s,source_tenant_id,object_schema,object_name,object_type_id,zone_id "
                "FROM core.object WHERE object_id=%s RETURNING object_id",
                (connection_id, scope.source_object_id),
            ).fetchone()
        )["object_id"]
        connection.execute(
            "INSERT INTO core.attribute(object_id,attribute_name,attribute_ordinal_position, "
            "attribute_data_type,attribute_nullability) "
            "SELECT %s,attribute_name,attribute_ordinal_position, "
            "attribute_data_type,attribute_nullability "
            "FROM core.attribute WHERE object_id=%s",
            (object_id, scope.source_object_id),
        )
        connection.execute(
            "INSERT INTO model.model_input_scope(model_id,object_id) VALUES (%s,%s)",
            (scope.plan.model_id, object_id),
        )
        connection.execute(
            "INSERT INTO workflow.logical_entity_source_mapping "
            "(model_id,logical_entity_id,support_source_type,source_object_id, "
            "logical_entity_source_mapping_rationale) "
            "SELECT model_id,logical_entity_id,'object',%s, "
            "'Second System contributes customer data.' "
            "FROM workflow.logical_entity WHERE model_id=%s",
            (object_id, scope.plan.model_id),
        )
        if scope.plan.modeled_entity_type == "dimensional_entity":
            mapping_id = require_row(
                connection.execute(
                    "INSERT INTO workflow.mapping_object "
                    "(model_id,modeled_entity_type,logical_entity_id,source_system_id, "
                    "mapping_transformation_document) "
                    "SELECT model_id,modeled_entity_type,logical_entity_id,%s, "
                    "mapping_transformation_document "
                    "FROM workflow.mapping_object WHERE model_id=%s AND logical_entity_id=%s "
                    "AND source_system_id=%s RETURNING mapping_object_id",
                    (
                        system_id,
                        scope.plan.model_id,
                        scope.logical_entity_id,
                        scope.source_system_id,
                    ),
                ).fetchone()
            )["mapping_object_id"]
            connection.execute(
                "INSERT INTO workflow.mapping_attribute "
                "(model_id,modeled_entity_type,logical_entity_id,logical_attribute_id, "
                "mapping_object_id,attribute_mapping_transformation_document) "
                "SELECT model_id,'logical_entity',logical_entity_id, "
                "logical_attribute_id,%s,'{}'::JSONB "
                "FROM workflow.logical_attribute WHERE model_id=%s AND logical_entity_id=%s",
                (mapping_id, scope.plan.model_id, scope.logical_entity_id),
            )
