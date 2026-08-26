from datetime import UTC, datetime
from decimal import Decimal
from uuid import UUID

from fastapi.testclient import TestClient
from gds_etl_workbench.adapters.auth.identity import IdentityProvider
from gds_etl_workbench.configuration import AuthMode
from gds_etl_workbench.domain.authorization import ActorKind, RequestPrincipal

from gds_workbench_api.main import create_app
from gds_workbench_api.features.workflows.runs import (
    ModelWorkflow,
    RunEventCollection,
    RunEventRecord,
    RunState,
    WorkflowRunCollection,
    WorkflowRunDetail,
    WorkflowRunLedgerRecord,
)


class StaticWorkflowRunService:
    async def list_runs(
        self,
        principal: RequestPrincipal,
        *,
        tenant_id: int,
        model_id: int,
        workflow: ModelWorkflow | None,
        run_state: RunState | None,
        page_size: int,
        cursor: str | None,
    ) -> WorkflowRunCollection:
        assert principal.actor_kind is ActorKind.HUMAN
        assert (tenant_id, model_id, workflow, run_state, page_size, cursor) == (
            7,
            18,
            "profiling",
            None,
            25,
            None,
        )
        return WorkflowRunCollection(
            items=(
                WorkflowRunLedgerRecord(
                    workflow_run_id=1048,
                    model_workflow="profiling",
                    workflow_execution_mode=None,
                    modeled_entity_type=None,
                    selected_scope_count=8,
                    requested_batch_id="10428",
                    workflow_run_state="completed",
                    actor_display_name="Maaz",
                    created_at=datetime(2026, 8, 24, 14, 0, tzinfo=UTC),
                    started_at=datetime(2026, 8, 24, 14, 0, 1, tzinfo=UTC),
                    completed_at=datetime(2026, 8, 24, 14, 1, tzinfo=UTC),
                ),
            ),
            next_cursor=None,
        )

    async def read_run(
        self,
        principal: RequestPrincipal,
        *,
        tenant_id: int,
        model_id: int,
        workflow_run_id: int,
    ) -> WorkflowRunDetail:
        assert principal.actor_kind is ActorKind.HUMAN
        assert (tenant_id, model_id, workflow_run_id) == (7, 18, 1048)
        return WorkflowRunDetail(
            workflow_run_id=1048,
            model_workflow="profiling",
            workflow_execution_mode=None,
            modeled_entity_type=None,
            selected_scope_count=8,
            requested_batch_id="10428",
            workflow_run_state="completed",
            actor_display_name="Maaz",
            created_at=datetime(2026, 8, 24, 14, 0, tzinfo=UTC),
            started_at=datetime(2026, 8, 24, 14, 0, 1, tzinfo=UTC),
            completed_at=datetime(2026, 8, 24, 14, 1, tzinfo=UTC),
            correlation_id=UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"),
            agent_sdk_code=None,
            agent_provider_code=None,
            agent_model_code=None,
            reasoning_effort_code=None,
            max_turns=None,
            validation_retry_count=None,
            failure_code=None,
            failure_message=None,
            model_change_set_id=UUID("bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb"),
            model_change_set_status="validated",
            draft_revision=2,
            candidate_digest="c" * 64,
            validated_at=datetime(2026, 8, 24, 14, 0, 30, tzinfo=UTC),
        )

    async def list_events(
        self,
        principal: RequestPrincipal,
        *,
        tenant_id: int,
        model_id: int,
        workflow_run_id: int,
        after_sequence: int,
        page_size: int,
    ) -> RunEventCollection:
        assert principal.actor_kind is ActorKind.HUMAN
        assert (tenant_id, model_id, workflow_run_id, after_sequence, page_size) == (
            7,
            18,
            1048,
            0,
            200,
        )
        return RunEventCollection(
            items=(
                RunEventRecord(
                    sequence=1,
                    attempt=1,
                    stage="prepare",
                    status="started",
                    message="Profiling preparation started.",
                    current=0,
                    total=8,
                    percent=Decimal("0"),
                    finding_count=0,
                    created_at=datetime(2026, 8, 24, 14, 0, tzinfo=UTC),
                ),
            ),
            next_after_sequence=1,
        )


def _app() -> TestClient:
    app = create_app(
        identity_provider=IdentityProvider(
            AuthMode.DEV,
            local_tenant_id=UUID("11111111-1111-1111-1111-111111111111"),
            local_principal_object_id=UUID("22222222-2222-2222-2222-222222222222"),
        ),
        workflow_run_service=StaticWorkflowRunService(),
    )
    return TestClient(app)


def test_run_ledger_is_filtered_by_workflow() -> None:
    with _app() as client:
        response = client.get(
            "/api/v1/tenants/7/models/18/runs?workflow=profiling&page_size=25"
        )

    assert response.status_code == 200
    assert response.json()["items"][0]["workflow_run_id"] == 1048
    assert "correlation_id" not in response.json()["items"][0]


def test_run_detail_and_incremental_events_are_separate_bounded_reads() -> None:
    with _app() as client:
        detail = client.get("/api/v1/tenants/7/models/18/runs/1048")
        events = client.get(
            "/api/v1/tenants/7/models/18/runs/1048/events?after_sequence=0&page_size=200"
        )

    assert detail.status_code == 200
    assert detail.json()["correlation_id"] == "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"
    assert detail.json()["model_change_set_id"] == (
        "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb"
    )
    assert detail.json()["model_change_set_status"] == "validated"
    assert detail.json()["draft_revision"] == 2
    assert events.status_code == 200
    assert events.json() == {
        "items": [
            {
                "sequence": 1,
                "attempt": 1,
                "stage": "prepare",
                "status": "started",
                "message": "Profiling preparation started.",
                "current": 0,
                "total": 8,
                "percent": "0",
                "finding_count": 0,
                "created_at": "2026-08-24T14:00:00Z",
            }
        ],
        "next_after_sequence": 1,
    }


def test_event_stream_supports_ordered_reconnect_and_stops_for_terminal_run() -> None:
    with (
        _app() as client,
        client.stream(
            "GET",
            "/api/v1/tenants/7/models/18/runs/1048/events/stream",
            headers={"Last-Event-ID": "0"},
        ) as response,
    ):
        body = "".join(response.iter_text())

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")
    assert "id: 1\n" in body
    assert "event: run_event\n" in body
    assert '"stage":"prepare"' in body
    assert "retry: 2000\n" in body
