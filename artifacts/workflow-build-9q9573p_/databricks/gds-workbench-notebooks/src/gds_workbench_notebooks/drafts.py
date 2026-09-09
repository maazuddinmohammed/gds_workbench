"""Explicit apply for a Workflow draft already presented at completion."""

from __future__ import annotations

import json
import re
from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Protocol
from uuid import UUID

from .errors import (
    NotebookAuthorizationError,
    NotebookConfigurationError,
    NotebookDatabaseError,
)
from .notebook import WidgetSpec
from .runtime import (
    NotebookDatabaseSettings,
    NotebookRuntimeSettings,
    load_notebook_runtime_settings,
    locate_uploaded_root,
    notebook_database_connection,
)
from .shared_runtime import create_notebook_workflow_database, run_coroutine_in_thread
from .workflow_control import NotebookPrincipal, NotebookWorkflowControlClient


@dataclass(frozen=True, slots=True)
class WorkflowDraftApplyRequest:
    tenant_id: int
    model_id: int
    workflow_run_id: int
    expected_model_revision: int
    expected_draft_revision: int
    expected_candidate_digest: str
    idempotency_key: UUID


@dataclass(frozen=True, slots=True)
class WorkflowDraftApplyResult:
    tenant_id: int
    model_id: int
    workflow_run_id: int
    model_change_set_id: UUID
    replayed: bool
    draft_revision: int
    candidate_digest: str
    action_count: int
    model_revision: int
    applied_at: datetime

    def as_dict(self) -> dict[str, object]:
        return {
            "tenant_id": self.tenant_id,
            "model_id": self.model_id,
            "workflow_run_id": self.workflow_run_id,
            "model_change_set_id": str(self.model_change_set_id),
            "replayed": self.replayed,
            "draft_revision": self.draft_revision,
            "candidate_digest": self.candidate_digest,
            "action_count": self.action_count,
            "model_revision": self.model_revision,
            "applied_at": self.applied_at.isoformat(),
        }


class _WorkflowDraftApplier(Protocol):
    async def apply(
        self,
        principal: Any,
        *,
        tenant_id: int,
        model_id: int,
        workflow_run_id: int,
        command: Any,
        idempotency_key: UUID,
    ) -> Any: ...


def draft_apply_widget_specs() -> tuple[WidgetSpec, ...]:
    return (
        WidgetSpec("TenantID", "", "Tenant ID"),
        WidgetSpec("ModelID", "", "Model ID"),
        WidgetSpec("WorkflowRunID", "", "Workflow Run ID"),
        WidgetSpec("ExpectedModelRevision", "", "Expected Model revision"),
        WidgetSpec("ExpectedDraftRevision", "", "Expected draft revision"),
        WidgetSpec("ExpectedCandidateDigest", "", "Expected candidate digest"),
        WidgetSpec("IdempotencyKey", "", "Idempotency key (UUID; reuse on retry)"),
        WidgetSpec("Confirmation", "", "Type APPLY exactly to apply the draft"),
    )


def create_workflow_draft_apply_widgets(*, dbutils: Any) -> None:
    for spec in draft_apply_widget_specs():
        if spec.choices:
            dbutils.widgets.dropdown(spec.name, spec.default, list(spec.choices), spec.label)
        else:
            dbutils.widgets.text(spec.name, spec.default, spec.label)


def build_draft_apply_request(values: Mapping[str, str]) -> WorkflowDraftApplyRequest:
    if values.get("Confirmation", "") != "APPLY":
        raise NotebookConfigurationError("Confirmation must be exactly APPLY.")
    digest = values.get("ExpectedCandidateDigest", "")
    if re.fullmatch(r"[0-9a-f]{64}", digest) is None:
        raise NotebookConfigurationError(
            "ExpectedCandidateDigest must be exactly 64 lowercase hexadecimal characters."
        )
    return WorkflowDraftApplyRequest(
        tenant_id=_positive_int(values, "TenantID"),
        model_id=_positive_int(values, "ModelID"),
        workflow_run_id=_positive_int(values, "WorkflowRunID"),
        expected_model_revision=_positive_int(values, "ExpectedModelRevision"),
        expected_draft_revision=_positive_int(values, "ExpectedDraftRevision"),
        expected_candidate_digest=digest,
        idempotency_key=_uuid(values, "IdempotencyKey"),
    )


async def apply_workflow_draft(
    request: WorkflowDraftApplyRequest,
    *,
    principal: NotebookPrincipal,
    database: Any,
    apply_service: _WorkflowDraftApplier | None = None,
) -> WorkflowDraftApplyResult:
    from gds_workbench_api.features.workflows.authoring.change_set_apply import (
        ApplyWorkflowDraftRequest,
        DatabaseWorkflowDraftApplyService,
    )

    if apply_service is None:
        from gds_etl_workbench.application.authorization import AuthorizationService

        apply_service = DatabaseWorkflowDraftApplyService(
            database=database,
            authorizer=AuthorizationService(),
        )
    result = await apply_service.apply(
        _request_principal(principal),
        tenant_id=request.tenant_id,
        model_id=request.model_id,
        workflow_run_id=request.workflow_run_id,
        command=ApplyWorkflowDraftRequest(
            expected_model_revision=request.expected_model_revision,
            expected_draft_revision=request.expected_draft_revision,
            expected_candidate_digest=request.expected_candidate_digest,
        ),
        idempotency_key=request.idempotency_key,
    )
    return _apply_result(request, result)


def execute_workflow_draft_apply(
    request: WorkflowDraftApplyRequest,
    *,
    settings: NotebookRuntimeSettings,
) -> WorkflowDraftApplyResult:
    principal = _current_notebook_principal(settings.database)
    try:
        return run_coroutine_in_thread(
            lambda: _with_runtime_database(
                settings,
                lambda database: apply_workflow_draft(
                    request,
                    principal=principal,
                    database=database,
                ),
            )
        )
    except (NotebookAuthorizationError, NotebookConfigurationError, NotebookDatabaseError):
        raise
    except Exception:
        raise NotebookDatabaseError(
            "Notebook draft apply failed without exposing runtime details."
        ) from None


def run_workflow_draft_apply_notebook(
    *,
    dbutils: Any,
    uploaded_root: Path | None = None,
) -> WorkflowDraftApplyResult:
    values = {spec.name: dbutils.widgets.get(spec.name) for spec in draft_apply_widget_specs()}
    request = build_draft_apply_request(values)
    root = uploaded_root or locate_uploaded_root(Path.cwd())
    result = execute_workflow_draft_apply(
        request,
        settings=load_notebook_runtime_settings(root),
    )
    print(json.dumps(result.as_dict(), ensure_ascii=False, separators=(",", ":"), sort_keys=True))
    return result


async def _with_runtime_database[T](
    settings: NotebookRuntimeSettings,
    operation: Callable[[Any], Awaitable[T]],
) -> T:
    database = create_notebook_workflow_database(settings.database)
    await database.open()
    try:
        readiness = await database.readiness()
        if not readiness.ready:
            raise NotebookDatabaseError(
                "Notebook database execution provisioning is incomplete or unavailable."
            )
        return await operation(database)
    finally:
        await database.close()


def _current_notebook_principal(settings: NotebookDatabaseSettings) -> NotebookPrincipal:
    with notebook_database_connection(settings) as connection:
        return NotebookWorkflowControlClient(connection).current_principal()


def _request_principal(principal: NotebookPrincipal) -> Any:
    from gds_etl_workbench.domain.authorization import ActorKind, RequestPrincipal

    return RequestPrincipal(
        actor_kind=ActorKind.WORKLOAD,
        entra_tenant_id=principal.entra_tenant_id,
        entra_object_id=principal.entra_object_id,
    )


def _apply_result(request: WorkflowDraftApplyRequest, result: Any) -> WorkflowDraftApplyResult:
    model_id = getattr(result, "model_id", None)
    workflow_run_id = getattr(result, "workflow_run_id", None)
    change_set_id = getattr(result, "model_change_set_id", None)
    replayed = getattr(result, "replayed", None)
    draft_revision = getattr(result, "draft_revision", None)
    candidate_digest = getattr(result, "candidate_digest", None)
    action_count = getattr(result, "action_count", None)
    model_revision = getattr(result, "model_revision", None)
    applied_at = getattr(result, "applied_at", None)
    if model_id != request.model_id or workflow_run_id != request.workflow_run_id:
        raise NotebookDatabaseError("The draft apply returned an invalid Workflow Run.")
    if not isinstance(change_set_id, UUID):
        raise NotebookDatabaseError("The draft apply returned an invalid Change Set.")
    if not isinstance(replayed, bool):
        raise NotebookDatabaseError("The draft apply returned an invalid replay state.")
    if type(draft_revision) is not int or draft_revision <= 0:
        raise NotebookDatabaseError("The draft apply returned an invalid revision.")
    if type(model_revision) is not int or model_revision <= 0:
        raise NotebookDatabaseError("The draft apply returned an invalid revision.")
    if type(action_count) is not int or action_count < 0:
        raise NotebookDatabaseError("The draft apply returned an invalid action count.")
    if (
        not isinstance(candidate_digest, str)
        or re.fullmatch(r"[0-9a-f]{64}", candidate_digest) is None
    ):
        raise NotebookDatabaseError("The draft apply returned an invalid candidate digest.")
    if not isinstance(applied_at, datetime):
        raise NotebookDatabaseError("The draft apply returned an invalid applied time.")
    return WorkflowDraftApplyResult(
        tenant_id=request.tenant_id,
        model_id=request.model_id,
        workflow_run_id=request.workflow_run_id,
        model_change_set_id=change_set_id,
        replayed=replayed,
        draft_revision=draft_revision,
        candidate_digest=candidate_digest,
        action_count=action_count,
        model_revision=model_revision,
        applied_at=applied_at,
    )


def _positive_int(values: Mapping[str, str], key: str) -> int:
    raw = values.get(key, "")
    if re.fullmatch(r"[1-9][0-9]*", raw) is None:
        raise NotebookConfigurationError(f"{key} must be a positive integer.")
    value = int(raw)
    if value > 9_223_372_036_854_775_807:
        raise NotebookConfigurationError(f"{key} must fit a PostgreSQL BIGINT.")
    return value


def _uuid(values: Mapping[str, str], key: str) -> UUID:
    raw = values.get(key, "")
    try:
        value = UUID(raw)
    except (AttributeError, ValueError):
        raise NotebookConfigurationError(f"{key} must be a UUID.") from None
    if value.int == 0:
        raise NotebookConfigurationError(f"{key} must not be the zero UUID.")
    return value


__all__ = [
    "WorkflowDraftApplyRequest",
    "WorkflowDraftApplyResult",
    "apply_workflow_draft",
    "build_draft_apply_request",
    "create_workflow_draft_apply_widgets",
    "draft_apply_widget_specs",
    "execute_workflow_draft_apply",
    "run_workflow_draft_apply_notebook",
]
