from __future__ import annotations

import ast
import json
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace
from uuid import UUID

import pytest
from gds_etl_workbench.domain.authorization import ActorKind
from gds_workbench_api.features.workflows.authoring.change_set_apply import (
    ApplyWorkflowDraftRequest,
)

import gds_workbench_notebooks.drafts as drafts
from gds_workbench_notebooks.drafts import (
    WorkflowDraftApplyRequest,
    WorkflowDraftApplyResult,
    WorkflowDraftReviewRequest,
    WorkflowDraftReviewResult,
    apply_workflow_draft,
    build_draft_apply_request,
    build_draft_review_request,
    draft_apply_widget_specs,
    draft_review_widget_specs,
    review_workflow_draft,
)
from gds_workbench_notebooks.errors import NotebookConfigurationError
from gds_workbench_notebooks.workflow_control import NotebookPrincipal

_ROOT = Path(__file__).parents[1]
_ENTRA_TENANT_ID = UUID("11111111-1111-4111-8111-111111111111")
_ENTRA_OBJECT_ID = UUID("22222222-2222-4222-8222-222222222222")
_CHANGE_SET_ID = UUID("33333333-3333-4333-8333-333333333333")
_IDEMPOTENCY_KEY = UUID("44444444-4444-4444-8444-444444444444")
_APPLIED_AT = datetime(2026, 8, 27, 12, 0, tzinfo=UTC)


def _principal() -> NotebookPrincipal:
    return NotebookPrincipal(
        display_name="Databricks Notebook Runtime",
        principal_type="service_principal",
        databricks_environment_code="prod-east",
        entra_tenant_id=_ENTRA_TENANT_ID,
        entra_object_id=_ENTRA_OBJECT_ID,
    )


def _review_request(dataset: str | None = None) -> WorkflowDraftReviewRequest:
    return WorkflowDraftReviewRequest(
        tenant_id=7,
        model_id=18,
        workflow_run_id=1047,
        dataset=dataset,
    )


def _apply_request() -> WorkflowDraftApplyRequest:
    return WorkflowDraftApplyRequest(
        tenant_id=7,
        model_id=18,
        workflow_run_id=1047,
        expected_model_revision=9,
        expected_draft_revision=2,
        expected_candidate_digest="d" * 64,
        idempotency_key=_IDEMPOTENCY_KEY,
    )


class _RunReader:
    def __init__(self) -> None:
        self.calls: list[tuple[object, dict[str, int]]] = []

    async def read_run(self, principal, **values):
        self.calls.append((principal, values))
        return SimpleNamespace(
            model_workflow="logical",
            workflow_run_state="completed",
            model_change_set_id=_CHANGE_SET_ID,
        )


class _ChangeSetReader:
    def __init__(self, records: list[dict[str, object]] | None) -> None:
        self.records = records
        self.calls: list[tuple[object, dict[str, object]]] = []

    async def get(self, principal, **values):
        self.calls.append((principal, values))
        return SimpleNamespace(
            model_id=18,
            model_change_set_id=_CHANGE_SET_ID,
            status="validated",
            draft_revision=2,
            candidate_digest="d" * 64,
            dataset_counts=(
                SimpleNamespace(dataset="logical_entity", record_count=len(self.records or [])),
                SimpleNamespace(dataset="logical_attribute", record_count=3),
            ),
            records=self.records,
        )


class _DraftApplier:
    def __init__(self) -> None:
        self.calls: list[tuple[object, dict[str, object]]] = []

    async def apply(self, principal, **values):
        self.calls.append((principal, values))
        return SimpleNamespace(
            model_id=18,
            workflow_run_id=1047,
            model_change_set_id=_CHANGE_SET_ID,
            replayed=False,
            draft_revision=2,
            candidate_digest="d" * 64,
            action_count=11,
            model_revision=10,
            applied_at=_APPLIED_AT,
        )


def test_widget_contracts_are_complete_and_stable() -> None:
    assert [spec.name for spec in draft_review_widget_specs()] == [
        "TenantID",
        "ModelID",
        "WorkflowRunID",
        "Dataset",
    ]
    assert draft_review_widget_specs()[-1].default == ""
    assert "logical_entity" in draft_review_widget_specs()[-1].choices
    assert [spec.name for spec in draft_apply_widget_specs()] == [
        "TenantID",
        "ModelID",
        "WorkflowRunID",
        "ExpectedModelRevision",
        "ExpectedDraftRevision",
        "ExpectedCandidateDigest",
        "IdempotencyKey",
        "Confirmation",
    ]


def test_review_widget_values_are_strictly_validated() -> None:
    assert build_draft_review_request(
        {
            "TenantID": "7",
            "ModelID": "18",
            "WorkflowRunID": "1047",
            "Dataset": "logical_entity",
        }
    ) == _review_request("logical_entity")
    assert (
        build_draft_review_request(
            {
                "TenantID": "7",
                "ModelID": "18",
                "WorkflowRunID": "1047",
                "Dataset": "",
            }
        )
        == _review_request()
    )

    for field, value in (
        ("TenantID", "0"),
        ("ModelID", " 18"),
        ("WorkflowRunID", "1047.0"),
        ("Dataset", "model_scope"),
    ):
        values = {
            "TenantID": "7",
            "ModelID": "18",
            "WorkflowRunID": "1047",
            "Dataset": "",
        }
        values[field] = value
        with pytest.raises(NotebookConfigurationError):
            build_draft_review_request(values)


def test_apply_requires_exact_confirmation_and_all_fences() -> None:
    values = {
        "TenantID": "7",
        "ModelID": "18",
        "WorkflowRunID": "1047",
        "ExpectedModelRevision": "9",
        "ExpectedDraftRevision": "2",
        "ExpectedCandidateDigest": "d" * 64,
        "IdempotencyKey": str(_IDEMPOTENCY_KEY),
        "Confirmation": "APPLY",
    }
    assert build_draft_apply_request(values) == _apply_request()

    for invalid_confirmation in ("", "apply", " APPLY", "APPLY "):
        with pytest.raises(NotebookConfigurationError, match="exactly APPLY"):
            build_draft_apply_request({**values, "Confirmation": invalid_confirmation})
    with pytest.raises(NotebookConfigurationError, match="lowercase hexadecimal"):
        build_draft_apply_request({**values, "ExpectedCandidateDigest": "D" * 64})
    with pytest.raises(NotebookConfigurationError, match="UUID"):
        build_draft_apply_request({**values, "IdempotencyKey": "retry-me"})
    with pytest.raises(NotebookConfigurationError, match="zero UUID"):
        build_draft_apply_request(
            {**values, "IdempotencyKey": "00000000-0000-0000-0000-000000000000"}
        )


@pytest.mark.asyncio
async def test_review_uses_run_then_change_set_service_with_workload_identity() -> None:
    runs = _RunReader()
    change_sets = _ChangeSetReader(records=None)

    result = await review_workflow_draft(
        _review_request(),
        principal=_principal(),
        database=object(),
        run_service=runs,
        change_set_service=change_sets,
    )

    assert result.as_dict() == {
        "tenant_id": 7,
        "model_id": 18,
        "workflow_run_id": 1047,
        "workflow": "logical",
        "workflow_state": "completed",
        "model_change_set_id": str(_CHANGE_SET_ID),
        "status": "validated",
        "draft_revision": 2,
        "candidate_digest": "d" * 64,
        "dataset_counts": [
            {"dataset": "logical_entity", "record_count": 0},
            {"dataset": "logical_attribute", "record_count": 3},
        ],
    }
    assert len(runs.calls) == len(change_sets.calls) == 1
    run_principal, run_values = runs.calls[0]
    change_principal, change_values = change_sets.calls[0]
    for request_principal in (run_principal, change_principal):
        assert request_principal.actor_kind is ActorKind.WORKLOAD
        assert request_principal.entra_tenant_id == _ENTRA_TENANT_ID
        assert request_principal.entra_object_id == _ENTRA_OBJECT_ID
    assert run_values == {"tenant_id": 7, "model_id": 18, "workflow_run_id": 1047}
    assert change_values == {
        "tenant_id": 7,
        "model_id": 18,
        "change_set_id": _CHANGE_SET_ID,
        "dataset": None,
    }


@pytest.mark.asyncio
async def test_selected_dataset_output_is_capped_at_fifty_rendered_records() -> None:
    records = [{"entity_name": f"Entity {index}", "ordinal": index} for index in range(55)]

    result = await review_workflow_draft(
        _review_request("logical_entity"),
        principal=_principal(),
        database=object(),
        run_service=_RunReader(),
        change_set_service=_ChangeSetReader(records=records),
    )

    assert result.selected_dataset_record_count == 55
    assert len(result.rendered_records) == 50
    assert result.records_truncated is True
    assert json.loads(result.rendered_records[0]) == {
        "entity_name": "Entity 0",
        "ordinal": 0,
    }
    assert json.loads(result.rendered_records[-1])["ordinal"] == 49
    assert result.as_dict()["displayed_record_count"] == 50


@pytest.mark.asyncio
async def test_oversized_record_is_replaced_with_a_bounded_marker() -> None:
    result = await review_workflow_draft(
        _review_request("logical_entity"),
        principal=_principal(),
        database=object(),
        run_service=_RunReader(),
        change_set_service=_ChangeSetReader(records=[{"value": "x" * 9000}]),
    )

    marker = json.loads(result.rendered_records[0])
    assert marker["record_omitted"] is True
    assert result.records_truncated is True
    assert len(result.rendered_records[0].encode()) < 500


@pytest.mark.asyncio
async def test_apply_uses_only_dedicated_workflow_draft_request_and_service() -> None:
    service = _DraftApplier()

    result = await apply_workflow_draft(
        _apply_request(),
        principal=_principal(),
        database=object(),
        apply_service=service,
    )

    assert result.as_dict() == {
        "tenant_id": 7,
        "model_id": 18,
        "workflow_run_id": 1047,
        "model_change_set_id": str(_CHANGE_SET_ID),
        "replayed": False,
        "draft_revision": 2,
        "candidate_digest": "d" * 64,
        "action_count": 11,
        "model_revision": 10,
        "applied_at": _APPLIED_AT.isoformat(),
    }
    assert len(service.calls) == 1
    request_principal, values = service.calls[0]
    assert request_principal.actor_kind is ActorKind.WORKLOAD
    assert request_principal.entra_tenant_id == _ENTRA_TENANT_ID
    assert request_principal.entra_object_id == _ENTRA_OBJECT_ID
    assert values["tenant_id"] == 7
    assert values["model_id"] == 18
    assert values["workflow_run_id"] == 1047
    assert values["idempotency_key"] == _IDEMPOTENCY_KEY
    assert isinstance(values["command"], ApplyWorkflowDraftRequest)
    assert values["command"].model_dump() == {
        "expected_model_revision": 9,
        "expected_draft_revision": 2,
        "expected_candidate_digest": "d" * 64,
    }


class _Widgets:
    def __init__(self, values: dict[str, str]) -> None:
        self.values = values
        self.created: list[tuple[str, str]] = []

    def text(self, name: str, _default: str, _label: str) -> None:
        self.created.append(("text", name))

    def dropdown(
        self,
        name: str,
        _default: str,
        _choices: list[str],
        _label: str,
    ) -> None:
        self.created.append(("dropdown", name))

    def get(self, name: str) -> str:
        return self.values[name]


def test_review_notebook_installs_widgets_and_prints_bounded_lines(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    widgets = _Widgets({"TenantID": "7", "ModelID": "18", "WorkflowRunID": "1047", "Dataset": ""})
    expected = WorkflowDraftReviewResult(
        tenant_id=7,
        model_id=18,
        workflow_run_id=1047,
        workflow="logical",
        workflow_state="completed",
        model_change_set_id=_CHANGE_SET_ID,
        status="validated",
        draft_revision=2,
        candidate_digest="d" * 64,
        dataset_counts=(),
        dataset=None,
        selected_dataset_record_count=0,
        rendered_records=(),
        records_truncated=False,
    )
    monkeypatch.setattr(drafts, "load_notebook_runtime_settings", lambda _root: object())
    monkeypatch.setattr(drafts, "execute_workflow_draft_review", lambda *_args, **_kw: expected)

    drafts.create_workflow_draft_review_widgets(dbutils=SimpleNamespace(widgets=widgets))
    result = drafts.run_workflow_draft_review_notebook(
        dbutils=SimpleNamespace(widgets=widgets),
        uploaded_root=tmp_path,
    )

    assert result is expected
    assert widgets.created == [
        ("text", "TenantID"),
        ("text", "ModelID"),
        ("text", "WorkflowRunID"),
        ("dropdown", "Dataset"),
    ]
    output = capsys.readouterr().out.splitlines()
    assert len(output) == 1
    assert json.loads(output[0])["workflow_run_id"] == 1047


def test_apply_notebook_installs_all_gates_before_calling_service(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    widgets = _Widgets(
        {
            "TenantID": "7",
            "ModelID": "18",
            "WorkflowRunID": "1047",
            "ExpectedModelRevision": "9",
            "ExpectedDraftRevision": "2",
            "ExpectedCandidateDigest": "d" * 64,
            "IdempotencyKey": str(_IDEMPOTENCY_KEY),
            "Confirmation": "APPLY",
        }
    )
    expected = WorkflowDraftApplyResult(
        tenant_id=7,
        model_id=18,
        workflow_run_id=1047,
        model_change_set_id=_CHANGE_SET_ID,
        replayed=False,
        draft_revision=2,
        candidate_digest="d" * 64,
        action_count=11,
        model_revision=10,
        applied_at=_APPLIED_AT,
    )
    received: list[WorkflowDraftApplyRequest] = []
    monkeypatch.setattr(drafts, "load_notebook_runtime_settings", lambda _root: object())
    monkeypatch.setattr(
        drafts,
        "execute_workflow_draft_apply",
        lambda request, **_kwargs: received.append(request) or expected,
    )

    drafts.create_workflow_draft_apply_widgets(dbutils=SimpleNamespace(widgets=widgets))
    result = drafts.run_workflow_draft_apply_notebook(
        dbutils=SimpleNamespace(widgets=widgets),
        uploaded_root=tmp_path,
    )

    assert result is expected
    assert received == [_apply_request()]
    assert [name for _kind, name in widgets.created] == [
        spec.name for spec in draft_apply_widget_specs()
    ]


def test_notebook_sources_are_thin_source_imports_and_start_no_server() -> None:
    notebook_expectations = {
        "90_review_workflow_draft.py": (
            "create_workflow_draft_review_widgets",
            "run_workflow_draft_review_notebook",
        ),
        "91_apply_workflow_draft.py": (
            "create_workflow_draft_apply_widgets",
            "run_workflow_draft_apply_notebook",
        ),
    }
    combined = (_ROOT / "src" / "gds_workbench_notebooks" / "drafts.py").read_text()
    for name, (setup, entry_point) in notebook_expectations.items():
        source = (_ROOT / "notebooks" / name).read_text()
        ast.parse(source, feature_version=(3, 12))
        assert source.startswith("# Databricks notebook source\n")
        assert 'str(_UPLOAD_ROOT / "src")' in source
        assert "sys.path.insert(0, _SOURCE_ROOT)" in source
        assert source.count("# COMMAND ----------") == 1
        assert (
            source.index(f"{setup}(dbutils=dbutils)")
            < source.index("# COMMAND ----------")
            < source.index(f"{entry_point}(dbutils=dbutils, uploaded_root=_UPLOAD_ROOT)")
        )
        assert source.count(f"{entry_point}(") == 1
        combined += source

    for forbidden in (
        "FastAPI(",
        "MCPServer(",
        "create_runtime_app(",
        "uvicorn.run",
        "run_mcp",
        "AppName",
        "GDS_WEB_",
        "dbutils.secrets",
        "DATABRICKS_TOKEN",
    ):
        assert forbidden not in combined
