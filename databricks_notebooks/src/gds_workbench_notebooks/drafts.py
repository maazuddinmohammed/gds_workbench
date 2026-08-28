"""Independent notebook review and explicit apply for Workflow-owned drafts."""

from __future__ import annotations

import json
import re
from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any, Protocol, cast
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
from .shared_runtime import (
    create_notebook_workflow_database,
    run_coroutine_in_thread,
)
from .workflow_control import NotebookPrincipal, NotebookWorkflowControlClient

_MAX_DISPLAY_RECORDS = 50
_MAX_RENDERED_RECORD_BYTES = 8 * 1024
_NOTEBOOK_DRAFT_CURSOR_KEY = b"gds-notebook-draft-reader-key-v1"
_MODEL_CHANGE_SET_DATASETS = (
    "model_details",
    "profiling_profile",
    "analysis_result",
    "modeling_assertion_document",
    "modeling_assertion_record",
    "conceptual_object",
    "conceptual_relationship",
    "logical_submodel",
    "logical_entity",
    "logical_attribute",
    "logical_relationship",
    "dimensional_submodel",
    "dimensional_entity",
    "dimensional_attribute",
    "dimensional_relationship",
    "mapping_dependency",
    "mapping_object",
    "mapping_attribute",
)
_MODEL_CHANGE_SET_DATASET_SET = frozenset(_MODEL_CHANGE_SET_DATASETS)
_WORKFLOWS = frozenset({"profiling", "analysis", "conceptual", "logical", "dimensional", "mapping"})
_WORKFLOW_STATES = frozenset({"queued", "running", "completed", "completed_with_repair", "failed"})
_DRAFT_STATUSES = frozenset(
    {"active", "validated", "applied", "expired", "discarded", "superseded"}
)


@dataclass(frozen=True, slots=True)
class WorkflowDraftReviewRequest:
    tenant_id: int
    model_id: int
    workflow_run_id: int
    dataset: str | None


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
class WorkflowDraftDatasetCount:
    dataset: str
    record_count: int

    def as_dict(self) -> dict[str, object]:
        return {"dataset": self.dataset, "record_count": self.record_count}


@dataclass(frozen=True, slots=True)
class WorkflowDraftReviewResult:
    tenant_id: int
    model_id: int
    workflow_run_id: int
    workflow: str
    workflow_state: str
    model_change_set_id: UUID
    status: str
    draft_revision: int
    candidate_digest: str | None
    dataset_counts: tuple[WorkflowDraftDatasetCount, ...]
    dataset: str | None
    selected_dataset_record_count: int
    rendered_records: tuple[str, ...]
    records_truncated: bool

    def as_dict(self) -> dict[str, object]:
        result: dict[str, object] = {
            "tenant_id": self.tenant_id,
            "model_id": self.model_id,
            "workflow_run_id": self.workflow_run_id,
            "workflow": self.workflow,
            "workflow_state": self.workflow_state,
            "model_change_set_id": str(self.model_change_set_id),
            "status": self.status,
            "draft_revision": self.draft_revision,
            "dataset_counts": [count.as_dict() for count in self.dataset_counts],
        }
        if self.candidate_digest is not None:
            result["candidate_digest"] = self.candidate_digest
        if self.dataset is not None:
            result.update(
                {
                    "dataset": self.dataset,
                    "selected_dataset_record_count": self.selected_dataset_record_count,
                    "displayed_record_count": len(self.rendered_records),
                    "records_truncated": self.records_truncated,
                }
            )
        return result


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


class _WorkflowRunReader(Protocol):
    async def read_run(
        self,
        principal: Any,
        *,
        tenant_id: int,
        model_id: int,
        workflow_run_id: int,
    ) -> Any: ...


class _ModelChangeSetReader(Protocol):
    async def get(
        self,
        principal: Any,
        *,
        tenant_id: int,
        model_id: int,
        change_set_id: UUID,
        dataset: Any,
    ) -> Any: ...


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


def draft_review_widget_specs() -> tuple[WidgetSpec, ...]:
    return (
        WidgetSpec("TenantID", "", "Tenant ID"),
        WidgetSpec("ModelID", "", "Model ID"),
        WidgetSpec("WorkflowRunID", "", "Workflow Run ID"),
        WidgetSpec(
            "Dataset",
            "",
            "Dataset (optional; blank returns summary only)",
            ("", *_MODEL_CHANGE_SET_DATASETS),
        ),
    )


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


def create_workflow_draft_review_widgets(*, dbutils: Any) -> None:
    """Create the visible widget bar for the draft review notebook."""
    _create_widgets(dbutils, draft_review_widget_specs())


def create_workflow_draft_apply_widgets(*, dbutils: Any) -> None:
    """Create the visible widget bar for the draft apply notebook."""
    _create_widgets(dbutils, draft_apply_widget_specs())


def build_draft_review_request(values: Mapping[str, str]) -> WorkflowDraftReviewRequest:
    dataset = values.get("Dataset", "")
    if dataset and dataset not in _MODEL_CHANGE_SET_DATASET_SET:
        raise NotebookConfigurationError("Dataset must be a supported draft dataset or blank.")
    return WorkflowDraftReviewRequest(
        tenant_id=_positive_int(values, "TenantID"),
        model_id=_positive_int(values, "ModelID"),
        workflow_run_id=_positive_int(values, "WorkflowRunID"),
        dataset=dataset or None,
    )


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


async def review_workflow_draft(
    request: WorkflowDraftReviewRequest,
    *,
    principal: NotebookPrincipal,
    database: Any,
    run_service: _WorkflowRunReader | None = None,
    change_set_service: _ModelChangeSetReader | None = None,
) -> WorkflowDraftReviewResult:
    """Read one run, then its actor-owned draft through shared governed services."""
    request_principal = _request_principal(principal)
    if run_service is None or change_set_service is None:
        from gds_etl_workbench.application.authorization import AuthorizationService
        from gds_workbench_api.features.model_change_sets.service import (
            DatabaseModelChangeSetService,
        )
        from gds_workbench_api.features.workflows.runs import DatabaseWorkflowRunService

        authorizer = AuthorizationService()
        if run_service is None:
            run_service = DatabaseWorkflowRunService(
                database=database,
                authorizer=authorizer,
                cursor_signing_key=_NOTEBOOK_DRAFT_CURSOR_KEY,
            )
        if change_set_service is None:
            change_set_service = DatabaseModelChangeSetService(
                database=database,
                authorizer=authorizer,
            )

    assert run_service is not None
    assert change_set_service is not None
    run = await run_service.read_run(
        request_principal,
        tenant_id=request.tenant_id,
        model_id=request.model_id,
        workflow_run_id=request.workflow_run_id,
    )
    change_set_id = getattr(run, "model_change_set_id", None)
    if not isinstance(change_set_id, UUID):
        raise NotebookDatabaseError("The Workflow Run has no reviewable draft.")
    draft = await change_set_service.get(
        request_principal,
        tenant_id=request.tenant_id,
        model_id=request.model_id,
        change_set_id=change_set_id,
        dataset=cast(Any, request.dataset),
    )
    return _review_result(request, run, draft, change_set_id)


async def apply_workflow_draft(
    request: WorkflowDraftApplyRequest,
    *,
    principal: NotebookPrincipal,
    database: Any,
    apply_service: _WorkflowDraftApplier | None = None,
) -> WorkflowDraftApplyResult:
    """Apply only through the dedicated Workflow draft fences and materializer."""
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
    assert apply_service is not None
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


def execute_workflow_draft_review(
    request: WorkflowDraftReviewRequest,
    *,
    settings: NotebookRuntimeSettings,
) -> WorkflowDraftReviewResult:
    principal = _current_notebook_principal(settings.database)
    try:
        return run_coroutine_in_thread(
            lambda: _with_runtime_database(
                settings,
                lambda database: review_workflow_draft(
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
            "Notebook draft review failed without exposing runtime details."
        ) from None


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


def run_workflow_draft_review_notebook(
    *,
    dbutils: Any,
    uploaded_root: Path | None = None,
) -> WorkflowDraftReviewResult:
    values = _read_widgets(dbutils, draft_review_widget_specs())
    request = build_draft_review_request(values)
    root = uploaded_root or locate_uploaded_root(Path.cwd())
    result = execute_workflow_draft_review(
        request,
        settings=load_notebook_runtime_settings(root),
    )
    print(_compact_json(result.as_dict()))
    for record in result.rendered_records:
        print(record)
    return result


def run_workflow_draft_apply_notebook(
    *,
    dbutils: Any,
    uploaded_root: Path | None = None,
) -> WorkflowDraftApplyResult:
    values = _read_widgets(dbutils, draft_apply_widget_specs())
    request = build_draft_apply_request(values)
    root = uploaded_root or locate_uploaded_root(Path.cwd())
    result = execute_workflow_draft_apply(
        request,
        settings=load_notebook_runtime_settings(root),
    )
    print(_compact_json(result.as_dict()))
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


def _review_result(
    request: WorkflowDraftReviewRequest,
    run: Any,
    draft: Any,
    change_set_id: UUID,
) -> WorkflowDraftReviewResult:
    if getattr(draft, "model_id", None) != request.model_id:
        raise NotebookDatabaseError("The draft review returned an invalid Model.")
    if getattr(draft, "model_change_set_id", None) != change_set_id:
        raise NotebookDatabaseError("The draft review returned an invalid Change Set.")
    counts = _dataset_counts(getattr(draft, "dataset_counts", ()))
    records = cast(object, getattr(draft, "records", None))
    if request.dataset is None:
        if records is not None:
            raise NotebookDatabaseError("The summary-only draft review returned records.")
        rendered_records: tuple[str, ...] = ()
        record_count = 0
        records_truncated = False
    else:
        if not isinstance(records, list):
            raise NotebookDatabaseError("The selected draft dataset returned invalid records.")
        record_values = cast(list[object], records)
        if not all(isinstance(record, Mapping) for record in record_values):
            raise NotebookDatabaseError("The selected draft dataset returned invalid records.")
        display_records = cast(list[Mapping[object, object]], record_values)
        rendered_records, oversized = _render_records(display_records)
        record_count = len(display_records)
        records_truncated = len(display_records) > _MAX_DISPLAY_RECORDS or oversized

    workflow = getattr(run, "model_workflow", None)
    workflow_state = getattr(run, "workflow_run_state", None)
    status = getattr(draft, "status", None)
    draft_revision = getattr(draft, "draft_revision", None)
    candidate_digest = getattr(draft, "candidate_digest", None)
    if workflow not in _WORKFLOWS or workflow_state not in _WORKFLOW_STATES:
        raise NotebookDatabaseError("The Workflow Run returned invalid review metadata.")
    if status not in _DRAFT_STATUSES or type(draft_revision) is not int or draft_revision <= 0:
        raise NotebookDatabaseError("The draft returned invalid review metadata.")
    if candidate_digest is not None and (
        not isinstance(candidate_digest, str)
        or re.fullmatch(r"[0-9a-f]{64}", candidate_digest) is None
    ):
        raise NotebookDatabaseError("The draft returned an invalid candidate digest.")
    return WorkflowDraftReviewResult(
        tenant_id=request.tenant_id,
        model_id=request.model_id,
        workflow_run_id=request.workflow_run_id,
        workflow=workflow,
        workflow_state=workflow_state,
        model_change_set_id=change_set_id,
        status=status,
        draft_revision=draft_revision,
        candidate_digest=candidate_digest,
        dataset_counts=counts,
        dataset=request.dataset,
        selected_dataset_record_count=record_count,
        rendered_records=rendered_records,
        records_truncated=records_truncated,
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


def _dataset_counts(raw_counts: Any) -> tuple[WorkflowDraftDatasetCount, ...]:
    try:
        counts = tuple(raw_counts)
    except TypeError:
        raise NotebookDatabaseError("The draft returned invalid dataset counts.") from None
    if len(counts) > len(_MODEL_CHANGE_SET_DATASETS):
        raise NotebookDatabaseError("The draft returned too many dataset counts.")
    result: list[WorkflowDraftDatasetCount] = []
    seen: set[str] = set()
    for raw_count in counts:
        dataset = getattr(raw_count, "dataset", None)
        record_count = getattr(raw_count, "record_count", None)
        if (
            not isinstance(dataset, str)
            or dataset not in _MODEL_CHANGE_SET_DATASET_SET
            or dataset in seen
            or type(record_count) is not int
            or record_count < 0
        ):
            raise NotebookDatabaseError("The draft returned invalid dataset counts.")
        seen.add(dataset)
        result.append(WorkflowDraftDatasetCount(dataset=dataset, record_count=record_count))
    return tuple(result)


def _render_records(
    records: list[Mapping[object, object]],
) -> tuple[tuple[str, ...], bool]:
    rendered: list[str] = []
    oversized = False
    for index, record in enumerate(records[:_MAX_DISPLAY_RECORDS], start=1):
        try:
            document = _compact_json(dict(record))
        except (TypeError, ValueError):
            raise NotebookDatabaseError(
                "The selected draft dataset contains a record that cannot be displayed safely."
            ) from None
        if len(document.encode("utf-8")) > _MAX_RENDERED_RECORD_BYTES:
            oversized = True
            document = _compact_json(
                {
                    "display_record_number": index,
                    "record_omitted": True,
                    "reason": "record exceeds the notebook display limit",
                }
            )
        rendered.append(document)
    return tuple(rendered), oversized


def _compact_json(value: object) -> str:
    return json.dumps(
        value,
        default=_json_default,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    )


def _json_default(value: object) -> object:
    if isinstance(value, UUID):
        return str(value)
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    if isinstance(value, Decimal):
        return str(value)
    raise TypeError("unsupported notebook display value")


def _create_widgets(
    dbutils: Any,
    specs: tuple[WidgetSpec, ...],
) -> None:
    for spec in specs:
        if spec.choices:
            dbutils.widgets.dropdown(spec.name, spec.default, list(spec.choices), spec.label)
        else:
            dbutils.widgets.text(spec.name, spec.default, spec.label)


def _read_widgets(
    dbutils: Any,
    specs: tuple[WidgetSpec, ...],
) -> dict[str, str]:
    return {spec.name: dbutils.widgets.get(spec.name) for spec in specs}


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
    "WorkflowDraftDatasetCount",
    "WorkflowDraftReviewRequest",
    "WorkflowDraftReviewResult",
    "apply_workflow_draft",
    "build_draft_apply_request",
    "build_draft_review_request",
    "create_workflow_draft_apply_widgets",
    "create_workflow_draft_review_widgets",
    "draft_apply_widget_specs",
    "draft_review_widget_specs",
    "execute_workflow_draft_apply",
    "execute_workflow_draft_review",
    "review_workflow_draft",
    "run_workflow_draft_apply_notebook",
    "run_workflow_draft_review_notebook",
]
