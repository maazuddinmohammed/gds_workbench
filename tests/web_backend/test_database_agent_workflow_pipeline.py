"""Installed defaults -> real repositories/stages -> governed draft/apply; synthetic agents only."""

# Existing builders create only fixture-owned disposable database contents.
# pyright: reportPrivateUsage=false
from hashlib import sha256
from typing import Literal
from uuid import uuid4

import pytest
from gds_etl_workbench.application.authorization import AuthorizationService
from gds_etl_workbench.domain.authorization import ActorKind, RequestPrincipal
from gds_workbench_api.capabilities import (
    AgentRunSelection,
    load_default_agent_capabilities,
)
from gds_workbench_api.database import WebPostgresDatabase
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
from tests.web_backend.test_database_mapping_source_context import _seed_mapping_scope


@pytest.fixture(scope="module")
def pipeline_database(
    bootstrap_postgres_database: DisposablePostgres,
) -> DisposablePostgres:
    database = bootstrap_postgres_database
    _apply_sql(database, REFERENCE_SEED.read_text(encoding="utf-8"))
    actor_id = _seed_super_admin(database)
    _apply_sql(database, _render_seed())
    seed_mapping_output_templates(database)
    content = "Generate Databricks SQL from the frozen Mapping definitions."
    with database.connect_owner() as connection:
        guide_id = require_row(
            connection.execute(
                "INSERT INTO application.sql_generation_guide "
                "(sql_generation_guide_code, sql_generation_guide_name, is_default, "
                "created_by_principal_id, updated_by_principal_id) "
                "VALUES ('fixture_pipeline', 'Fixture pipeline guide', TRUE, %s, %s) "
                "RETURNING sql_generation_guide_id",
                (actor_id, actor_id),
            ).fetchone()
        )["sql_generation_guide_id"]
        connection.execute(
            "INSERT INTO application.sql_generation_guide_version "
            "(sql_generation_guide_id, sql_generation_guide_version_number, "
            "sql_generation_guide_content, sql_generation_guide_digest, "
            "sql_generation_guide_version_status, created_by_principal_id, "
            "updated_by_principal_id, published_time, published_by_principal_id) "
            "VALUES (%s, 1, %s, %s, 'published', %s, %s, CURRENT_TIMESTAMP, %s)",
            (
                guide_id,
                content,
                sha256(content.encode()).hexdigest(),
                actor_id,
                actor_id,
                actor_id,
            ),
        )
    return database


@pytest.mark.parametrize("mapping_mode", ["one_shot", "tool_assisted"])
async def test_mapping_code_validation_pipeline_uses_real_persistence_and_apply(
    pipeline_database: DisposablePostgres,
    monkeypatch: pytest.MonkeyPatch,
    mapping_mode: Literal["one_shot", "tool_assisted"],
) -> None:
    fixture = pipeline_database
    scope = _seed_mapping_scope(fixture, dimensional=False, create_run=False)
    model_id = scope.plan.model_id
    with fixture.connect_owner() as connection:
        actor = require_row(
            connection.execute(
                "SELECT entra_tenant_id, entra_object_id FROM security.entra_principal_identity "
                "WHERE principal_id = %s",
                (scope.plan.actor_principal_id,),
            ).fetchone()
        )
        source = require_row(
            connection.execute(
                "SELECT system_code FROM core.system WHERE system_id = %s",
                (scope.source_system_id,),
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
    calls: list[tuple[str, str, int]] = []
    original_execute = LocalFakeAgentAdapter.execute

    async def recording_execute(
        self: LocalFakeAgentAdapter, request: AgentExecutionRequest
    ) -> AgentExecutionResult:
        result = await original_execute(self, request)
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
    selection = AgentRunSelection(
        sdk_code="openai_agents_sdk",
        provider_code="microsoft_foundry",
        model_code="foundry-primary",
        reasoning_effort_code="none",
        max_turns=8,
        validation_retry_count=1,
    )
    run_ids: list[int] = []
    await database.open()
    try:
        for revision, workflow in enumerate(("mapping", "code_generation", "validation"), 1):
            if workflow == "mapping":
                command = CreateWorkflowRunRequest(
                    expected_model_revision=revision,
                    model_workflow="mapping",
                    workflow_execution_mode=mapping_mode,
                    selected_object_ids=[scope.silver_object_id],
                    mapping_operation="extend",
                    mapping_coverage_mode="selected_targets",
                    mapping_source_system_id=scope.source_system_id,
                    agent=selection,
                )
            elif workflow == "code_generation":
                command = CreateWorkflowRunRequest(
                    expected_model_revision=revision,
                    model_workflow="code_generation",
                    selected_object_ids=[scope.silver_object_id],
                    modeled_entity_type="logical_entity",
                    code_generation_coverage_mode="selected_targets",
                    agent=selection,
                )
            else:
                command = CreateWorkflowRunRequest(
                    expected_model_revision=revision,
                    model_workflow="validation",
                    selected_object_ids=[],
                    selected_system_codes=[source["system_code"]],
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
    finally:
        await services.close()
        await database.close()
    assert [workflow for workflow, _, _ in calls] == [
        "mapping",
        "code_generation",
        "validation",
    ]
    assert calls[0][1] == mapping_mode
    assert (calls[0][2] > 0) == (mapping_mode == "tool_assisted")
    assert all(mode == "tool_assisted" and count > 0 for _, mode, count in calls[1:])
    with fixture.connect_owner() as connection:
        states = connection.execute(
            "SELECT run.workflow_run_state, changes.model_change_set_status, "
            "(SELECT count(*) FROM mcp.model_change_set_event AS event "
            "WHERE event.model_change_set_id=changes.model_change_set_id "
            "AND event.event_type='applied') AS applied_event_count "
            "FROM application.workflow_run AS run JOIN mcp.model_change_set AS changes "
            "USING(workflow_run_id) WHERE run.workflow_run_id=ANY(%s)",
            (run_ids,),
        ).fetchall()
    assert len(states) == 3
    assert all(row["model_change_set_status"] == "applied" for row in states)
    assert all(row["applied_event_count"] == 1 for row in states)
