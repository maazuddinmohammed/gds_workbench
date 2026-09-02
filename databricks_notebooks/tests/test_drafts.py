from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace
from uuid import UUID

import pytest
from gds_etl_workbench.domain.authorization import ActorKind

import gds_workbench_notebooks.drafts as drafts
from gds_workbench_notebooks.drafts import (
    WorkflowDraftApplyRequest,
    apply_workflow_draft,
    build_draft_apply_request,
    draft_apply_widget_specs,
)
from gds_workbench_notebooks.errors import NotebookConfigurationError
from gds_workbench_notebooks.workflow_control import NotebookPrincipal

_ROOT = Path(__file__).parents[1]
_IDEMPOTENCY_KEY = UUID("44444444-4444-4444-8444-444444444444")
_CHANGE_SET_ID = UUID("33333333-3333-4333-8333-333333333333")
_APPLIED_AT = datetime(2026, 8, 27, 12, 0, tzinfo=UTC)


def _request() -> WorkflowDraftApplyRequest:
    return WorkflowDraftApplyRequest(
        tenant_id=7,
        model_id=18,
        workflow_run_id=1047,
        expected_model_revision=9,
        expected_draft_revision=2,
        expected_candidate_digest="d" * 64,
        idempotency_key=_IDEMPOTENCY_KEY,
    )


def _principal() -> NotebookPrincipal:
    return NotebookPrincipal(
        display_name="Databricks Notebook Runtime",
        principal_type="service_principal",
        databricks_environment_code="prod-east",
        entra_tenant_id=UUID("11111111-1111-4111-8111-111111111111"),
        entra_object_id=UUID("22222222-2222-4222-8222-222222222222"),
    )


def test_only_explicit_apply_has_a_standalone_notebook_contract() -> None:
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
    assert (_ROOT / "notebooks" / "91_apply_workflow_draft.py").is_file()


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
    assert build_draft_apply_request(values) == _request()

    for confirmation in ("", "apply", " APPLY", "APPLY "):
        with pytest.raises(NotebookConfigurationError, match="exactly APPLY"):
            build_draft_apply_request({**values, "Confirmation": confirmation})


@pytest.mark.asyncio
async def test_apply_uses_workload_identity_and_exact_fences() -> None:
    calls: list[tuple[object, dict[str, object]]] = []

    class Applier:
        async def apply(self, principal, **values):
            calls.append((principal, values))
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

    result = await apply_workflow_draft(
        _request(),
        principal=_principal(),
        database=object(),
        apply_service=Applier(),
    )

    principal, values = calls[0]
    assert principal.actor_kind is ActorKind.WORKLOAD
    assert values["tenant_id"] == 7
    assert values["model_id"] == 18
    assert values["workflow_run_id"] == 1047
    assert values["idempotency_key"] == _IDEMPOTENCY_KEY
    assert result.model_revision == 10
    assert result.action_count == 11


def test_apply_notebook_source_uses_imported_runtime_only() -> None:
    source = (_ROOT / "notebooks" / "91_apply_workflow_draft.py").read_text()
    assert "create_workflow_draft_apply_widgets" in source
    assert "run_workflow_draft_apply_notebook" in source
    compile(source, "91_apply_workflow_draft.py", "exec")


def test_apply_notebook_runner_prints_only_bounded_result(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    expected = SimpleNamespace(
        as_dict=lambda: {
            "workflow_run_id": 1047,
            "model_change_set_id": str(_CHANGE_SET_ID),
            "model_revision": 10,
        }
    )
    monkeypatch.setattr(drafts, "execute_workflow_draft_apply", lambda *_args, **_kw: expected)
    monkeypatch.setattr(drafts, "load_notebook_runtime_settings", lambda _root: object())

    class Widgets:
        def get(self, name: str) -> str:
            return {
                "TenantID": "7",
                "ModelID": "18",
                "WorkflowRunID": "1047",
                "ExpectedModelRevision": "9",
                "ExpectedDraftRevision": "2",
                "ExpectedCandidateDigest": "d" * 64,
                "IdempotencyKey": str(_IDEMPOTENCY_KEY),
                "Confirmation": "APPLY",
            }[name]

    result = drafts.run_workflow_draft_apply_notebook(
        dbutils=SimpleNamespace(widgets=Widgets()),
        uploaded_root=_ROOT,
    )

    assert result is expected
    assert "workflow_run_id" in capsys.readouterr().out
