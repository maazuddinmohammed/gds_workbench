"""Real Conceptual graph repair and draft Apply using a disposable database."""

# pyright: reportPrivateUsage=false
from copy import deepcopy
from typing import Any
from uuid import uuid4

import pytest
from gds_etl_workbench.application.authorization import AuthorizationService
from gds_etl_workbench.domain.authorization import ActorKind, RequestPrincipal
from gds_workbench_api.database import WebPostgresDatabase
from gds_workbench_api.features.conceptual.service import DatabaseConceptualExecutor
from gds_workbench_api.features.workflows.authoring.agent_execution import (
    AgentExecutionRequest,
    AgentExecutionResult,
)
from gds_workbench_api.features.workflows.authoring.change_set_apply import (
    ApplyWorkflowDraftRequest,
    DatabaseWorkflowDraftApplyService,
)
from gds_workbench_api.features.workflows.authoring.change_set_handoff import (
    WorkflowChangeSetHandoff,
    WorkflowChangeSetHandoffResult,
)
from gds_workbench_api.features.workflows.authoring.lifecycle import DatabaseAgentWorkflowLifecycle
from gds_workbench_api.features.workflows.authoring.no_op import DatabaseAuthoringNoOpService
from gds_workbench_api.features.workflows.authoring.repair import AgentCandidateValidationError
from gds_workbench_api.features.workflows.execution.repository import (
    DatabaseWorkflowClaimRepository,
)

from tests.mcp.conftest import DisposablePostgres
from tests.web_backend.test_conceptual_candidate import _object
from tests.web_backend.test_database_model_change_sets import (
    _create_queued_conceptual_run_with_prompt,
    _seed_profile_model,
)


@pytest.mark.parametrize("repair_succeeds", [True, False])
async def test_conceptual_graph_failure_repairs_or_retains_complete_rejected_draft(
    web_postgres_database: DisposablePostgres,
    repair_succeeds: bool,
) -> None:
    model_id, tenant_id, _, entra_tenant_id, entra_object_id, _ = _seed_profile_model(
        web_postgres_database
    )
    with web_postgres_database.connect_owner() as connection:
        object_ids: dict[str, int] = {}
        for name in ("Customer", "Order"):
            record = _object(name=name)
            row = connection.execute(
                """
                INSERT INTO workflow.conceptual_object (
                    model_id, conceptual_object_name, conceptual_object_definition,
                    conceptual_object_type, conceptual_object_grain,
                    conceptual_object_confidence
                ) VALUES (%s, %s, %s, %s, %s, %s)
                RETURNING conceptual_object_id
                """,
                (
                    model_id,
                    name,
                    record["conceptual_object_definition"],
                    record["conceptual_object_type"],
                    record["conceptual_object_grain"],
                    record["conceptual_object_confidence"],
                ),
            ).fetchone()
            assert row is not None
            object_ids[name] = row["conceptual_object_id"]
        connection.execute(
            """
            INSERT INTO workflow.conceptual_relationship (
                model_id, from_conceptual_object_id, to_conceptual_object_id,
                conceptual_relationship_name, conceptual_relationship_type,
                conceptual_relationship_definition, conceptual_relationship_cardinality,
                conceptual_relationship_basis, conceptual_relationship_cardinality_basis
            ) VALUES (%s, %s, %s, 'belongs to', 'association',
                      'Order belongs to customer.', 'many_to_one',
                      'Declared business rule.', 'Many orders per customer.')
            """,
            (model_id, object_ids["Order"], object_ids["Customer"]),
        )
        acquired = connection.execute(
            "SELECT acquired FROM security.acquire_tenant_lock(%s, %s, 'user', %s, 60, %s)",
            (entra_tenant_id, entra_object_id, tenant_id, "Conceptual graph repair fixture"),
        ).fetchone()
        assert acquired == {"acquired": True}
    run_id = _create_queued_conceptual_run_with_prompt(
        web_postgres_database,
        tenant_id=tenant_id,
        model_id=model_id,
        entra_tenant_id=entra_tenant_id,
        entra_object_id=entra_object_id,
    )
    principal = RequestPrincipal(
        actor_kind=ActorKind.HUMAN,
        entra_tenant_id=entra_tenant_id,
        entra_object_id=entra_object_id,
    )
    requests: list[AgentExecutionRequest] = []

    class Agent:
        async def execute(self, request: AgentExecutionRequest) -> AgentExecutionResult:
            requests.append(request)
            candidate = _object()
            if len(requests) == 1 or not repair_succeeds:
                candidate["conceptual_object_status"] = "inactive"
            else:
                candidate["conceptual_object_definition"] = "Customer identified by a business key."
            return AgentExecutionResult(
                candidate={"objects": [candidate], "relationships": []},
                turn_count=1,
                tool_call_count=0,
            )

    database = WebPostgresDatabase(
        dsn=web_postgres_database.web_runtime_dsn(),
        pool_min=1,
        pool_max=1,
        pool_timeout_seconds=5,
    )
    authorizer = AuthorizationService()
    lifecycle = DatabaseAgentWorkflowLifecycle(database=database)
    executor = DatabaseConceptualExecutor(
        database=database,
        authorizer=authorizer,
        agent_executor=Agent(),
        handoff=WorkflowChangeSetHandoff(database=database, authorizer=authorizer),
        no_op=DatabaseAuthoringNoOpService(database=database),
        lifecycle=lifecycle,
    )
    await database.open()
    try:
        await lifecycle.start(
            principal,
            tenant_id=tenant_id,
            model_id=model_id,
            workflow_run_id=run_id,
            expected_workflow="conceptual",
            expected_execution_mode="one_shot",
            expected_model_revision=1,
        )
        claim = await DatabaseWorkflowClaimRepository(database=database).claim_next(
            lease_duration_seconds=300
        )
        assert claim is not None and claim.workflow_run_id == run_id
        arguments: dict[str, Any] = {
            "tenant_id": tenant_id,
            "model_id": model_id,
            "workflow_run_id": run_id,
            "expected_model_revision": 1,
            "workflow_run_claim_token": claim.workflow_run_claim_token,
        }
        if repair_succeeds:
            draft = await executor.execute_started(principal, **arguments)
            assert isinstance(draft, WorkflowChangeSetHandoffResult)
            assert len(requests) == 2
            await DatabaseWorkflowDraftApplyService(database=database, authorizer=authorizer).apply(
                principal,
                tenant_id=tenant_id,
                model_id=model_id,
                workflow_run_id=run_id,
                command=ApplyWorkflowDraftRequest(
                    expected_model_revision=1,
                    expected_draft_revision=draft.draft_revision,
                    expected_candidate_digest=draft.candidate_digest,
                ),
                idempotency_key=uuid4(),
            )
        else:
            with pytest.raises(AgentCandidateValidationError):
                await executor.execute_started(principal, **arguments)
            assert 2 <= len(requests) <= 6
        original = deepcopy(requests[0].context)
        assert isinstance(original, dict)
        for request in requests[1:]:
            context = request.context
            assert isinstance(context, dict)
            assert context["original_context"] == original["original_context"]
            feedback = context["repair"]
            assert isinstance(feedback, dict)
            issues = feedback["validation_issues"]
            assert isinstance(issues, list)
            assert any(
                isinstance(issue, dict)
                and issue.get("code") == "candidate.active_dependency_invalid"
                for issue in issues
            )
        with web_postgres_database.connect_owner() as connection:
            state = connection.execute(
                """
                SELECT run.workflow_run_state, model.model_revision,
                       draft.model_change_set_status, draft.applied_time IS NOT NULL AS applied,
                       object.conceptual_object_status, object.conceptual_object_definition,
                       relationship.conceptual_relationship_status,
                       relationship.workflow_run_id AS relationship_run_id,
                       draft.conceptual_document
                  FROM application.workflow_run AS run
                  JOIN model.model AS model ON model.model_id = run.model_id
                  JOIN mcp.model_change_set AS draft ON draft.workflow_run_id = run.workflow_run_id
                  JOIN workflow.conceptual_object AS object
                    ON object.model_id = model.model_id
                   AND object.conceptual_object_name = 'Customer'
                  JOIN workflow.conceptual_relationship AS relationship
                    ON relationship.model_id = model.model_id
                 WHERE run.workflow_run_id = %s
                """,
                (run_id,),
            ).fetchone()
        assert state is not None
        assert state["model_revision"] == (2 if repair_succeeds else 1)
        assert state["applied"] is repair_succeeds
        assert state["model_change_set_status"] == ("applied" if repair_succeeds else "active")
        assert state["workflow_run_state"] == (
            "completed_with_repair" if repair_succeeds else "failed"
        )
        assert state["conceptual_object_status"] == "active"
        assert state["conceptual_relationship_status"] == "active"
        assert state["relationship_run_id"] is None
        if repair_succeeds:
            assert state["conceptual_object_definition"] == "Customer identified by a business key."
        else:
            assert (
                state["conceptual_object_definition"] == _object()["conceptual_object_definition"]
            )
            assert (
                state["conceptual_document"]["conceptual_object"][0]["conceptual_object_status"]
                == "inactive"
            )
    finally:
        await database.close()
