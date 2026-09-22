"""Local review data must survive the same full-graph gate as agent-authored candidates."""

# Fixture imports reuse only disposable databases and synthetic identities.
# pyright: reportPrivateUsage=false
from pathlib import Path
from uuid import uuid4

from gds_etl_workbench.application.authorization import AuthorizationService
from gds_etl_workbench.domain.authorization import ActorKind, RequestPrincipal
from gds_etl_workbench.domain.databricks_sql import validate_databricks_sql
from gds_workbench_api.capabilities import AgentRunSelection, load_default_agent_capabilities
from gds_workbench_api.database import WebPostgresDatabase
from gds_workbench_api.features.conceptual.service import ConceptualWorkflow
from gds_workbench_api.features.workflows.authoring.change_set_handoff import (
    WorkflowChangeSetHandoff,
    WorkflowChangeSetHandoffResult,
)
from gds_workbench_api.features.workflows.authoring.lifecycle import DatabaseAgentWorkflowLifecycle
from gds_workbench_api.features.workflows.authoring.no_op import DatabaseAuthoringNoOpService
from gds_workbench_api.features.workflows.commands import (
    CreateWorkflowRunRequest,
    DatabaseWorkflowCommandService,
)
from gds_workbench_api.features.workflows.execution.repository import (
    DatabaseWorkflowClaimRepository,
)

from tests.mcp.conftest import DisposablePostgres
from tests.mcp.conftest import bootstrap_postgres_database as bootstrap_postgres_database
from tests.mcp.database_test_support import require_row
from tests.mcp.test_database_global_prompt_seed import ENTRA_OBJECT_ID, ENTRA_TENANT_ID, _apply_sql
from tests.web_backend.test_database_agent_workflow_pipeline import (
    pipeline_database as pipeline_database,
)
from tests.web_backend.test_database_model_change_sets import RecordingFakeAgentAdapter


async def test_local_review_validation_queries_do_not_poison_conceptual_authoring(
    pipeline_database: DisposablePostgres,
) -> None:
    fixture = pipeline_database
    seed_root = Path(__file__).parents[2] / "database" / "seed"
    _apply_sql(fixture, (seed_root / "01_metadata_snapshot_demo.sql").read_text())
    seed = (seed_root / "08_local_workbench_review.sql").read_text()
    local_guard = "current_database() !~ '^gds_local_[0-9a-f]{12}$'"
    assert seed.count(local_guard) == 1
    # Match this verified disposable fixture exactly; retain the production seed's local-only guard.
    seed = seed.replace(local_guard, f"current_database() <> '{fixture.database}'")
    _apply_sql(fixture, seed)
    with fixture.connect_owner() as connection:
        model = require_row(
            connection.execute(
                "SELECT model_id, tenant_id, model_revision FROM model.model "
                "WHERE model_name='Customer Orders 360'",
            ).fetchone()
        )
        scope = connection.execute(
            "SELECT object_id FROM model.model_input_scope WHERE model_id=%s AND is_active "
            "ORDER BY object_id",
            (model["model_id"],),
        ).fetchall()
        checks = connection.execute(
            "SELECT validation_query_sql FROM workflow.validation_check AS check_record "
            "JOIN workflow.validation_group AS group_record USING(validation_group_id) "
            "WHERE group_record.model_id=%s",
            (model["model_id"],),
        ).fetchall()
        acquired = require_row(
            connection.execute(
                "SELECT acquired FROM security.acquire_tenant_lock(%s,%s,'user',%s,60, "
                "'Fixture local review regression')",
                (ENTRA_TENANT_ID, ENTRA_OBJECT_ID, model["tenant_id"]),
            ).fetchone()
        )
    assert acquired["acquired"] and scope and len(checks) == 3
    principal = RequestPrincipal(
        actor_kind=ActorKind.HUMAN,
        entra_tenant_id=ENTRA_TENANT_ID,
        entra_object_id=ENTRA_OBJECT_ID,
    )
    database = WebPostgresDatabase(
        dsn=fixture.web_runtime_dsn(),
        pool_min=1,
        pool_max=1,
        pool_timeout_seconds=5,
    )
    authorizer = AuthorizationService()
    lifecycle = DatabaseAgentWorkflowLifecycle(database=database)
    agent = RecordingFakeAgentAdapter()
    workflow = ConceptualWorkflow(
        database=database,
        authorizer=authorizer,
        agent_executor=agent,
        handoff=WorkflowChangeSetHandoff(database=database, authorizer=authorizer),
        no_op=DatabaseAuthoringNoOpService(database=database),
        lifecycle=lifecycle,
    )
    commands = DatabaseWorkflowCommandService(
        database=database,
        authorizer=authorizer,
        agent_capability_registry=load_default_agent_capabilities(),
    )
    await database.open()
    try:
        created = await commands.create_run(
            principal,
            tenant_id=model["tenant_id"],
            model_id=model["model_id"],
            correlation_id=uuid4(),
            command=CreateWorkflowRunRequest(
                expected_model_revision=model["model_revision"],
                model_workflow="conceptual",
                workflow_execution_mode="tool_assisted",
                selected_object_ids=[row["object_id"] for row in scope],
                agent=AgentRunSelection(
                    sdk_code="openai_agents_sdk",
                    provider_code="microsoft_foundry",
                    model_code="foundry-primary",
                    reasoning_effort_code="none",
                    max_turns=8,
                    validation_retry_count=1,
                ),
            ),
        )
        await workflow.start(
            principal,
            tenant_id=model["tenant_id"],
            model_id=model["model_id"],
            workflow_run_id=created.workflow_run_id,
            expected_execution_mode="tool_assisted",
            expected_model_revision=model["model_revision"],
        )
        claim = await DatabaseWorkflowClaimRepository(database=database).claim_next(
            lease_duration_seconds=300,
        )
        assert claim is not None and claim.workflow_run_id == created.workflow_run_id
        draft = await workflow.execute_started(
            principal,
            tenant_id=model["tenant_id"],
            model_id=model["model_id"],
            workflow_run_id=created.workflow_run_id,
            expected_model_revision=model["model_revision"],
            workflow_run_claim_token=claim.workflow_run_claim_token,
        )
        assert isinstance(draft, WorkflowChangeSetHandoffResult)
        assert agent.tool_call_count > 0
    finally:
        await database.close()
    assert all(
        validate_databricks_sql(row["validation_query_sql"]).final_returns_rows for row in checks
    )
    with fixture.connect_owner() as connection:
        state = require_row(
            connection.execute(
                "SELECT workflow_run_state,failure_code FROM application.workflow_run "
                "WHERE workflow_run_id=%s",
                (created.workflow_run_id,),
            ).fetchone()
        )
    assert state == {"workflow_run_state": "completed", "failure_code": None}
