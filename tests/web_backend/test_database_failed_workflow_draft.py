"""Failed authoring retains a reviewable draft without bypassing Apply fences."""

from collections.abc import AsyncGenerator
from typing import Any, cast
from uuid import uuid4

import pytest
from gds_etl_workbench.application.authorization import AuthorizationService
from gds_etl_workbench.application.change_sets.project import StageProjectChange
from gds_etl_workbench.application.change_sets.project_validation import (
    ProjectValidationIssue,
)
from gds_etl_workbench.domain.authorization import ActorKind, RequestPrincipal
from gds_etl_workbench.domain.errors import (
    AuthorizationDeniedError,
    DependencyUnavailableError,
    InvalidRequestError,
    ProjectChangeSetNotValidatedError,
    TenantLockRequiredError,
)
from tests.mcp.conftest import DisposablePostgres
from tests.web_backend.test_database_project_change_sets import (
    _create_queued_subject_area_run_with_prompt,  # pyright: ignore[reportPrivateUsage]
    _seed_profile_project,  # pyright: ignore[reportPrivateUsage]
)
from tests.web_backend.test_database_workflow_run_claims import (
    _expire_claim,  # pyright: ignore[reportPrivateUsage]
)

from gds_workbench_api.database import WebPostgresDatabase
from gds_workbench_api.features.project_change_sets.contracts import (
    ExpectedDraftRevisionRequest,
)
from gds_workbench_api.features.project_change_sets.service import (
    DatabaseProjectChangeSetService,
)
from gds_workbench_api.features.projects import ProjectRevisionConflictError
from gds_workbench_api.features.workflows.authoring import change_set_handoff
from gds_workbench_api.features.workflows.authoring.change_set_apply import (
    ApplyWorkflowDraftRequest,
    DatabaseWorkflowDraftApplyService,
)
from gds_workbench_api.features.workflows.authoring.change_set_handoff import (
    WorkflowChangeSetHandoff,
)
from gds_workbench_api.features.workflows.authoring.lifecycle import (
    DatabaseAgentWorkflowLifecycle,
)
from gds_workbench_api.features.workflows.execution.contracts import (
    WorkflowExecutionClaim,
)
from gds_workbench_api.features.workflows.execution.repository import (
    DatabaseWorkflowClaimRepository,
)

type ClaimedRun = tuple[WebPostgresDatabase, WorkflowExecutionClaim]


def _candidate() -> StageProjectChange:
    # A membership of an area that does not exist, for a table outside the Scope.
    return StageProjectChange(
        dataset="subject_area_table",
        records=[
            {
                "subject_area_name": "Missing Area",
                "tenant_code": "MISSING_TENANT",
                "system_code": "MISSING_SYSTEM",
                "connection_code": "MISSING_CONNECTION",
                "object_schema": "missing",
                "object_name": "missing_table",
                "subject_area_table_is_active": True,
                "subject_area_table_is_locked": False,
            }
        ],
    )


def _retention_arguments(claim: WorkflowExecutionClaim) -> dict[str, Any]:
    return {
        "tenant_id": claim.tenant_id,
        "project_id": claim.project_id,
        "workflow_run_id": claim.workflow_run_id,
        "expected_workflow": "subject_area",
        "expected_project_revision": claim.project_revision,
        "workflow_run_claim_token": claim.workflow_run_claim_token,
        "changes": (_candidate(),),
        "issues": (
            ProjectValidationIssue(
                code="reference_not_found",
                dataset="subject_area_table",
                record_number=1,
                fields=("subject_area_name",),
                message="Subject Area is unavailable.",
            ),
        ),
        "failure_code": "workflow_change_set_validation_failed",
        "safe_failure_message": "Candidate retained for review; validation failed.",
    }


@pytest.fixture
async def claimed_subject_area_run(
    web_postgres_database: DisposablePostgres,
) -> AsyncGenerator[ClaimedRun]:
    project_id, tenant_id, _, entra_tenant_id, entra_object_id, _ = _seed_profile_project(
        web_postgres_database
    )
    with web_postgres_database.connect_owner() as connection:
        acquired = connection.execute(
            """
            SELECT acquired FROM security.acquire_tenant_lock(
                %s, %s, 'user', %s, 60, 'Failed candidate fixture'
            )
            """,
            (entra_tenant_id, entra_object_id, tenant_id),
        ).fetchone()
    assert acquired == {"acquired": True}
    run_id = _create_queued_subject_area_run_with_prompt(
        web_postgres_database,
        tenant_id=tenant_id,
        project_id=project_id,
        entra_tenant_id=entra_tenant_id,
        entra_object_id=entra_object_id,
    )
    principal = RequestPrincipal(
        actor_kind=ActorKind.HUMAN,
        entra_tenant_id=entra_tenant_id,
        entra_object_id=entra_object_id,
    )
    database = WebPostgresDatabase(
        dsn=web_postgres_database.web_runtime_dsn(),
        pool_min=1,
        pool_max=1,
        pool_timeout_seconds=5,
    )
    await database.open()
    try:
        await DatabaseAgentWorkflowLifecycle(database=database).start(
            principal,
            tenant_id=tenant_id,
            project_id=project_id,
            workflow_run_id=run_id,
            expected_workflow="subject_area",
            expected_execution_mode="one_shot",
            expected_project_revision=1,
        )
        claim = await DatabaseWorkflowClaimRepository(database=database).claim_next(
            lease_duration_seconds=300
        )
        assert claim is not None
        assert claim.workflow_run_id == run_id
        yield database, claim
    finally:
        await database.close()


def _assert_retention_rolled_back(
    fixture: DisposablePostgres,
    claim: WorkflowExecutionClaim,
) -> None:
    with fixture.connect_owner() as connection:
        state = connection.execute(
            """
            SELECT run.workflow_run_state,
                   (SELECT count(*) FROM mcp.project_change_set AS draft
                     WHERE draft.workflow_run_id = run.workflow_run_id) AS draft_count,
                   (SELECT count(*) FROM project.project_event_log AS event
                     WHERE event.workflow_run_id = run.workflow_run_id
                       AND event.project_event_log_status = 'failed') AS failed_event_count
              FROM application.workflow_run AS run
             WHERE run.workflow_run_id = %s
            """,
            (claim.workflow_run_id,),
        ).fetchone()
    assert state == {
        "workflow_run_state": "running",
        "draft_count": 0,
        "failed_event_count": 0,
    }


async def test_failed_canonical_candidate_is_retained_for_review_but_cannot_apply(
    web_postgres_database: DisposablePostgres,
    claimed_subject_area_run: ClaimedRun,
) -> None:
    database, claim = claimed_subject_area_run
    result = await WorkflowChangeSetHandoff(
        database=database, authorizer=AuthorizationService()
    ).retain_failed_candidate(claim.principal, **_retention_arguments(claim))

    assert result.changed
    assert result.workflow_run_id == claim.workflow_run_id
    assert result.workflow_run_state == "failed"
    with web_postgres_database.connect_owner() as connection:
        stored = connection.execute(
            """
            SELECT run.workflow_run_state, run.failure_code,
                   run.workflow_run_claim_token_digest IS NULL AS claim_cleared,
                   target_project.project_revision,
                   draft.project_change_set_id, draft.project_change_set_status,
                   draft.draft_revision, draft.candidate_digest,
                   draft.validation_outcome, draft.validated_time,
                   draft.applied_time, draft.subject_area_document,
                   draft.created_by_principal_id = run.actor_principal_id AS owned,
                   draft.correlation_id = run.correlation_id AS correlation_matches,
                   (SELECT count(*) FROM workflow.subject_area_table AS result
                     WHERE result.project_id = run.project_id) AS applied_record_count
              FROM application.workflow_run AS run
              JOIN project.project AS target_project ON target_project.project_id = run.project_id
              JOIN mcp.project_change_set AS draft ON draft.workflow_run_id = run.workflow_run_id
             WHERE run.workflow_run_id = %s
            """,
            (claim.workflow_run_id,),
        ).fetchone()
        assert stored is not None
        events = connection.execute(
            """
            SELECT event_type FROM mcp.project_change_set_event
             WHERE project_change_set_id = %s ORDER BY event_sequence
            """,
            (stored["project_change_set_id"],),
        ).fetchall()

    assert stored["workflow_run_state"] == "failed"
    assert stored["failure_code"] == "workflow_change_set_validation_failed"
    assert stored["claim_cleared"] is True
    assert stored["project_revision"] == claim.project_revision
    assert stored["project_change_set_status"] == "active"
    assert stored["candidate_digest"] is None
    assert stored["validated_time"] is None
    assert stored["applied_time"] is None
    assert stored["owned"] is True
    assert stored["correlation_matches"] is True
    assert stored["applied_record_count"] == 0
    assert stored["subject_area_document"] == {"subject_area_table": _candidate().records}
    assert isinstance(stored["validation_outcome"], dict)
    outcome = cast(dict[str, Any], stored["validation_outcome"])
    assert outcome["valid"] is False
    assert outcome["error_count"] > 0
    assert 0 < len(outcome["errors"]) <= 25
    assert events == [
        {"event_type": "created"},
        {"event_type": "section_put"},
        {"event_type": "validation_failed"},
    ]

    change_set_service = DatabaseProjectChangeSetService(
        database=database, authorizer=AuthorizationService()
    )
    draft = await change_set_service.get(
        claim.principal,
        tenant_id=claim.tenant_id,
        project_id=claim.project_id,
        change_set_id=stored["project_change_set_id"],
        dataset="subject_area_table",
    )
    assert draft.status == "active"
    assert draft.candidate_digest is None
    assert draft.records == _candidate().records
    assert draft.validation_outcome is not None
    assert draft.validation_outcome["valid"] is False
    assert draft.validation_outcome["error_count"] == outcome["error_count"]
    assert draft.validation_outcome["errors"] == outcome["errors"]
    assert draft.validation_outcome["error_groups"] == outcome["error_groups"]
    assert draft.validation_outcome["error_groups"]
    with pytest.raises(InvalidRequestError):
        await DatabaseWorkflowDraftApplyService(
            database=database, authorizer=AuthorizationService()
        ).apply(
            claim.principal,
            tenant_id=claim.tenant_id,
            project_id=claim.project_id,
            workflow_run_id=claim.workflow_run_id,
            command=ApplyWorkflowDraftRequest(
                expected_project_revision=claim.project_revision,
                expected_draft_revision=draft.draft_revision,
                expected_candidate_digest="0" * 64,
            ),
            idempotency_key=uuid4(),
        )
    with pytest.raises(ProjectChangeSetNotValidatedError):
        await change_set_service.apply(
            claim.principal,
            tenant_id=claim.tenant_id,
            project_id=claim.project_id,
            change_set_id=draft.project_change_set_id,
            command=ExpectedDraftRevisionRequest(expected_draft_revision=draft.draft_revision),
            idempotency_key=uuid4(),
        )


@pytest.mark.parametrize("fence", ["project_revision", "claim", "reclaimed_claim", "tenant_lock"])
async def test_retained_draft_obeys_live_revision_claim_and_tenant_lock(
    web_postgres_database: DisposablePostgres,
    claimed_subject_area_run: ClaimedRun,
    fence: str,
) -> None:
    database, claim = claimed_subject_area_run
    arguments = _retention_arguments(claim)
    expected_error = DependencyUnavailableError
    if fence == "project_revision":
        with web_postgres_database.connect_owner() as connection:
            connection.execute(
                "UPDATE project.project SET project_revision = project_revision + 1 "
                "WHERE project_id = %s",
                (claim.project_id,),
            )
        expected_error = ProjectRevisionConflictError
    elif fence == "claim":
        arguments["workflow_run_claim_token"] = uuid4()
    elif fence == "reclaimed_claim":
        with web_postgres_database.connect_owner() as connection:
            _expire_claim(connection, claim.workflow_run_id)
        renewed = await DatabaseWorkflowClaimRepository(database=database).claim_next(
            lease_duration_seconds=300
        )
        assert renewed is not None
        assert renewed.workflow_run_id == claim.workflow_run_id
        assert renewed.workflow_run_claim_token != claim.workflow_run_claim_token
    else:
        with web_postgres_database.connect_owner() as connection:
            released = connection.execute(
                "SELECT released FROM security.release_tenant_lock(%s, %s, 'user', %s)",
                (
                    claim.actor_entra_tenant_id,
                    claim.actor_entra_object_id,
                    claim.tenant_id,
                ),
            ).fetchone()
        assert released == {"released": True}
        expected_error = TenantLockRequiredError

    with pytest.raises(expected_error):
        await WorkflowChangeSetHandoff(
            database=database, authorizer=AuthorizationService()
        ).retain_failed_candidate(claim.principal, **arguments)
    _assert_retention_rolled_back(web_postgres_database, claim)


async def test_another_authorized_lock_owner_cannot_retain_someone_elses_run(
    web_postgres_database: DisposablePostgres,
    claimed_subject_area_run: ClaimedRun,
) -> None:
    database, claim = claimed_subject_area_run
    _, _, _, other_tenant_identity, other_object_identity, _ = _seed_profile_project(
        web_postgres_database
    )
    with web_postgres_database.connect_owner() as connection:
        connection.execute(
            """
            INSERT INTO security.tenant_principal_access (
                tenant_id, principal_id, tenant_role, granted_by_principal_id
            ) SELECT %s, principal_id, 'architect', principal_id
                FROM security.entra_principal_identity
               WHERE entra_tenant_id = %s AND entra_object_id = %s
            """,
            (claim.tenant_id, other_tenant_identity, other_object_identity),
        )
        released = connection.execute(
            "SELECT released FROM security.release_tenant_lock(%s, %s, 'user', %s)",
            (claim.actor_entra_tenant_id, claim.actor_entra_object_id, claim.tenant_id),
        ).fetchone()
        assert released == {"released": True}
        acquired = connection.execute(
            """
            SELECT acquired FROM security.acquire_tenant_lock(
                %s, %s, 'user', %s, 60, 'Other authorized reviewer'
            )
            """,
            (other_tenant_identity, other_object_identity, claim.tenant_id),
        ).fetchone()
        assert acquired == {"acquired": True}
    other_principal = RequestPrincipal(
        actor_kind=ActorKind.HUMAN,
        entra_tenant_id=other_tenant_identity,
        entra_object_id=other_object_identity,
    )
    with pytest.raises(AuthorizationDeniedError):
        await WorkflowChangeSetHandoff(
            database=database, authorizer=AuthorizationService()
        ).retain_failed_candidate(other_principal, **_retention_arguments(claim))
    _assert_retention_rolled_back(web_postgres_database, claim)


async def test_failed_run_persistence_error_rolls_back_the_retained_draft(
    web_postgres_database: DisposablePostgres,
    claimed_subject_area_run: ClaimedRun,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    database, claim = claimed_subject_area_run

    async def fail_terminal_write(*args: object, **kwargs: object) -> None:
        del args, kwargs
        raise DependencyUnavailableError()

    monkeypatch.setattr(change_set_handoff, "fail_agent_workflow_run", fail_terminal_write)
    with pytest.raises(DependencyUnavailableError):
        await WorkflowChangeSetHandoff(
            database=database, authorizer=AuthorizationService()
        ).retain_failed_candidate(claim.principal, **_retention_arguments(claim))
    _assert_retention_rolled_back(web_postgres_database, claim)


async def test_retention_rejects_noncanonical_records_before_persisting(
    web_postgres_database: DisposablePostgres,
    claimed_subject_area_run: ClaimedRun,
) -> None:
    database, claim = claimed_subject_area_run
    arguments = _retention_arguments(claim)
    record = dict(_candidate().records[0])
    record.pop("subject_area_table_is_active")
    arguments["changes"] = (StageProjectChange(dataset="subject_area_table", records=[record]),)
    with pytest.raises(InvalidRequestError):
        await WorkflowChangeSetHandoff(
            database=database, authorizer=AuthorizationService()
        ).retain_failed_candidate(claim.principal, **arguments)
    _assert_retention_rolled_back(web_postgres_database, claim)


async def test_caller_issues_cannot_mark_a_freshly_valid_candidate_invalid(
    web_postgres_database: DisposablePostgres,
    claimed_subject_area_run: ClaimedRun,
) -> None:
    database, claim = claimed_subject_area_run
    arguments = _retention_arguments(claim)
    arguments["changes"] = (
        StageProjectChange(
            dataset="subject_area",
            records=[
                {
                    "subject_area_name": "Customer",
                    "subject_area_definition": "A governed customer.",
                    "subject_area_is_active": True,
                    "subject_area_is_locked": False,
                }
            ],
        ),
    )
    with pytest.raises(InvalidRequestError, match="no longer fails authoritative validation"):
        await WorkflowChangeSetHandoff(
            database=database, authorizer=AuthorizationService()
        ).retain_failed_candidate(claim.principal, **arguments)
    _assert_retention_rolled_back(web_postgres_database, claim)
