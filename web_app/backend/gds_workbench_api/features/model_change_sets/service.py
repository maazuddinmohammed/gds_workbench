"""Governed Model Change Set application service."""

import hashlib
import json
from collections.abc import Iterable, Mapping
from contextlib import AbstractAsyncContextManager
from dataclasses import replace
from datetime import datetime
from typing import Any, Protocol, cast
from uuid import UUID, uuid4

from gds_etl_workbench.application.authorization import (
    AuthorizationService,
    TenantAuthorization,
)
from gds_etl_workbench.application.change_sets.contracts import (
    MAX_AGENT_VALIDATION_ERROR_EXAMPLES,
    MAX_MODEL_STAGE_CHUNK_BYTES,
    bounded_validation_outcome,
    canonical_records_bytes,
    canonical_records_sha256,
    decode_canonical_base64_fragment,
    stage_batch_sha256,
)
from gds_etl_workbench.application.change_sets.model import (
    ModelChangeSetDatasetCount,
    ModelDatasetCount,
    StageModelChange,
    decode_canonical_model_stage_payload,
    load_model_physical_scope,
    model_action_review,
    model_change_set_documents,
    model_validation_error,
    model_validation_error_groups,
    model_validation_outcome,
    pending_model_change_set_datasets,
    require_mcp_writable_pending,
    require_model_stage_batch,
    require_mutable_model_change_set,
    validate_locked_model_change_set,
    validate_model_change_set_document_bounds,
    validate_model_stage_changes,
)
from gds_etl_workbench.application.change_sets.model_apply import ModelMaterializer
from gds_etl_workbench.application.change_sets.model_validation import (
    ValidatedModelChangeSet,
    build_model_action_review,
    validate_future_graph,
)
from gds_etl_workbench.application.model_read import ModelReadContext
from gds_etl_workbench.application.model_snapshot import (
    build_model_snapshot,
    read_model_review_snapshot,
)
from gds_etl_workbench.domain.authorization import ActorKind, RequestPrincipal, ToolPolicy
from gds_etl_workbench.domain.errors import (
    AuthorizationDeniedError,
    CandidateDigestConflictError,
    DependencyUnavailableError,
    DraftRevisionConflictError,
    InvalidRequestError,
    ModelChangeSetNotActiveError,
    ModelChangeSetNotFoundError,
    ModelChangeSetNotValidatedError,
    StageBatchConflictError,
    StageBatchIncompleteError,
    StageBatchNotFoundError,
    StageChunkConflictError,
    TenantLockRequiredError,
    TenantWorkflowConflictError,
    WorkbenchError,
)
from gds_etl_workbench.domain.modeling_records import AnalysisResultRecord
from gds_etl_workbench.domain.snapshots.model import (
    DATASETS_BY_NAME,
    ModelChangeSetDataset,
    ModelDataset,
    model_snapshot_records,
)
from gds_etl_workbench.infrastructure.postgres import WriteTransaction

from gds_workbench_api.features.model_change_sets.input_scope import (
    AddInputScopeRequest,
    prepare_input_scope_addition,
)
from gds_workbench_api.features.model_targets.binding import (
    load_generated_bindings,
    load_model_binding,
)
from gds_workbench_api.features.model_targets.contracts import (
    ApplyModelBindingRequest,
    GeneratedBindingsPreview,
    GenerateModelBindingsRequest,
    ModelBindingPreview,
    PreviewModelBindingRequest,
)
from gds_workbench_api.features.models import ModelNotFoundError, ModelRevisionConflictError

from .contracts import (
    ApplyModelChangeSetResult,
    ArchiveModelChangeSetResult,
    BeginModelStageBatchRequest,
    BeginModelStageBatchResult,
    CommitModelStageBatchResult,
    CreateModelChangeSetRequest,
    CreateModelChangeSetResult,
    ExpectedDraftRevisionRequest,
    GetModelChangeSetResult,
    ModelRecordHistoryItem,
    ModelRecordHistoryPage,
    ModelRecordReviewIssue,
    ModelRecordReviewItem,
    PreviewModelRecordsRequest,
    PreviewModelRecordsResult,
    PutModelStageChunkRequest,
    PutModelStageChunkResult,
    ReviewModelRecordsRequest,
    ReviewModelRecordsResult,
    StageModelChangeSetRequest,
    StageModelChangeSetResult,
    ValidateModelChangeSetResult,
)
from .repository import PostgresModelChangeSetRepository, require_datetime
from .review import ModelReviewDataset, prepare_model_record_review, review_lifecycle


class ModelChangeSetDatabase(Protocol):
    def write_transaction(self) -> AbstractAsyncContextManager[WriteTransaction]: ...


class DatabaseModelChangeSetService:
    def __init__(
        self,
        *,
        database: ModelChangeSetDatabase,
        authorizer: AuthorizationService,
    ) -> None:
        self._database = database
        self._authorizer = authorizer

    async def list_review_records(
        self,
        principal: RequestPrincipal,
        *,
        tenant_id: int,
        model_id: int,
        dataset: ModelReviewDataset,
        expected_model_revision: int,
        page: int = 1,
    ) -> ModelRecordHistoryPage:
        # Model SHARE fence keeps numeric identity pages stable. Include inactive
        # owned history even when a Binding/Mapping is no longer eligible to run.
        async with self._database.write_transaction() as transaction:
            _, model, _ = await self._authorize_model(
                transaction,
                principal,
                tenant_id=tenant_id,
                model_id=model_id,
                policy=ToolPolicy.TENANT_READ,
            )
            if model.model_revision != expected_model_revision:
                raise ModelRevisionConflictError()
            review = await read_model_review_snapshot(transaction, model)
            rows = sorted(review.records_by_id.get(dataset, {}).items())
            if page < 1 or (page > 1 and (page - 1) * 200 >= len(rows)):
                raise InvalidRequestError("The record page is unavailable.")
            items: list[ModelRecordHistoryItem] = []
            for record_id, row in rows[(page - 1) * 200 : page * 200]:
                locked, status = review_lifecycle(row, dataset)
                items.append(
                    ModelRecordHistoryItem(
                        record_id=record_id,
                        label=" · ".join(
                            str(getattr(row, field))
                            for field in DATASETS_BY_NAME[dataset].canonical_key
                        ),
                        is_locked=locked,
                        status=cast(Any, status),
                    )
                )
        return ModelRecordHistoryPage(
            model_id=model_id,
            model_revision=model.model_revision,
            dataset=dataset,
            items=tuple(items),
            next_page=page + 1 if page * 200 < len(rows) else None,
        )

    async def bind_registered_target(
        self,
        principal: RequestPrincipal,
        *,
        tenant_id: int,
        model_id: int,
        command: PreviewModelBindingRequest
        | ApplyModelBindingRequest
        | GenerateModelBindingsRequest,
        idempotency_key: UUID | None = None,
    ) -> ModelBindingPreview | GeneratedBindingsPreview | ReviewModelRecordsResult:
        """Preview or atomically apply only the explicitly approved Object/Attribute Bindings."""
        applying = isinstance(command, ApplyModelBindingRequest) or (
            isinstance(command, GenerateModelBindingsRequest) and idempotency_key is not None
        )
        if applying and idempotency_key is None:
            raise InvalidRequestError("An idempotency key is required to apply Bindings.")
        request_digest = hashlib.sha256(
            json.dumps(
                {"operation": "bind_registered_target", **command.model_dump(mode="json")},
                sort_keys=True,
                separators=(",", ":"),
            ).encode()
        ).hexdigest()
        async with self._database.write_transaction() as transaction:
            repository, model, principal_id = await self._authorize_record_review(
                transaction, principal, tenant_id=tenant_id, model_id=model_id
            )
            if applying and idempotency_key is not None:
                replay = await repository.replay_review(
                    model_id=model_id, principal_id=principal_id, correlation_id=idempotency_key
                )
                if replay is not None:
                    metadata = replay["event_metadata"]
                    if metadata.get("request_digest") != request_digest:
                        raise WorkbenchError("review_conflict", "This review key was already used.")
                    return ReviewModelRecordsResult(
                        model_id=model_id,
                        model_change_set_id=replay["model_change_set_id"],
                        model_revision=metadata["model_revision"],
                        action_count=replay["action_count"],
                    )
            if model["model_revision"] != command.expected_model_revision:
                raise ModelRevisionConflictError()
            if await repository.has_running_tenant_workflow(tenant_id=tenant_id):
                raise TenantWorkflowConflictError()
            context = ModelReadContext(
                model_id=model_id,
                tenant_id=tenant_id,
                model_name=model["model_name"],
                model_revision=model["model_revision"],
            )
            prepared = (
                await load_generated_bindings(transaction, context, command)
                if isinstance(command, GenerateModelBindingsRequest)
                else await load_model_binding(transaction, context, command)
            )
            if not applying:
                return prepared.preview
            if (
                not isinstance(command, (ApplyModelBindingRequest, GenerateModelBindingsRequest))
                or command.expected_plan_digest != prepared.preview.plan_digest
            ):
                raise WorkbenchError("review_conflict", "The Binding changed. Refresh its preview.")
            if not prepared.preview.can_apply or prepared.validation.candidate_digest is None:
                raise WorkbenchError(
                    "review_conflict", "Correct the Binding issues before applying."
                )
            authorization = await self._authorizer.authorize_tenant(
                transaction, principal, tenant_id=tenant_id, policy=ToolPolicy.TENANT_MODEL_WRITE
            )
            if authorization.principal.principal_id != principal_id:
                raise AuthorizationDeniedError()
            assert idempotency_key is not None
            return await self._apply_validated_review(
                transaction,
                repository,
                prepared.validation,
                model_id=model_id,
                principal_id=principal_id,
                idempotency_key=idempotency_key,
                expected_model_revision=command.expected_model_revision,
                request_digest=request_digest,
                section="model_binding",
                outcome="bindings_applied",
                layer=command.layer,
            )

    async def add_input_scope(
        self,
        principal: RequestPrincipal,
        *,
        tenant_id: int,
        model_id: int,
        command: AddInputScopeRequest,
        idempotency_key: UUID,
    ) -> ReviewModelRecordsResult:
        request_digest = hashlib.sha256(
            json.dumps(
                {"operation": "add_input_scope", **command.model_dump()},
                sort_keys=True,
                separators=(",", ":"),
            ).encode()
        ).hexdigest()
        async with self._database.write_transaction() as transaction:
            repository, model, principal_id = await self._authorize_record_review(
                transaction, principal, tenant_id=tenant_id, model_id=model_id
            )
            replay = await repository.replay_review(
                model_id=model_id, principal_id=principal_id, correlation_id=idempotency_key
            )
            if replay is not None:
                metadata = replay["event_metadata"]
                if metadata.get("request_digest") != request_digest:
                    raise WorkbenchError("review_conflict", "This review key was already used.")
                return ReviewModelRecordsResult(
                    model_id=model_id,
                    model_change_set_id=replay["model_change_set_id"],
                    model_revision=metadata["model_revision"],
                    action_count=replay["action_count"],
                )
            if model["model_revision"] != command.expected_model_revision:
                raise ModelRevisionConflictError()
            if await repository.has_running_tenant_workflow(tenant_id=tenant_id):
                raise TenantWorkflowConflictError()
            context = ModelReadContext(
                model_id=model_id,
                tenant_id=tenant_id,
                model_name=model["model_name"],
                model_revision=model["model_revision"],
            )
            validation = await prepare_input_scope_addition(
                transaction, context, command.object_ids
            )
            await self._authorizer.authorize_tenant(
                transaction, principal, tenant_id=tenant_id, policy=ToolPolicy.TENANT_MODEL_WRITE
            )
            return await self._apply_validated_review(
                transaction,
                repository,
                validation,
                model_id=model_id,
                principal_id=principal_id,
                idempotency_key=idempotency_key,
                expected_model_revision=command.expected_model_revision,
                request_digest=request_digest,
                section="model_input_scope",
                outcome="scope_added",
                scope_addition=(principal, tenant_id, command.object_ids),
            )

    async def _apply_validated_review(
        self,
        transaction: WriteTransaction,
        repository: PostgresModelChangeSetRepository,
        validation: ValidatedModelChangeSet,
        *,
        model_id: int,
        principal_id: int,
        idempotency_key: UUID,
        expected_model_revision: int,
        request_digest: str,
        section: str,
        outcome: str,
        scope_addition: tuple[RequestPrincipal, int, list[int]] | None = None,
        layer: str | None = None,
    ) -> ReviewModelRecordsResult:
        """Persist a validated Binding or Scope command within its authorization transaction."""
        change_set_id = uuid4()
        row = await repository.create(
            change_set_id=change_set_id,
            model_id=model_id,
            workflow_run_id=None,
            principal_id=principal_id,
            correlation_id=idempotency_key,
        )
        if row is None:
            raise ModelNotFoundError()
        documents = model_change_set_documents(row)
        for dataset, records in validation.records.items():
            documents[DATASETS_BY_NAME[dataset].section][dataset] = [
                record.model_dump(mode="json") for record in records
            ]
        validate_model_change_set_document_bounds(documents)
        staged = await repository.stage_documents(documents=documents, change_set_id=change_set_id)
        if staged is None:
            raise ModelChangeSetNotFoundError()
        await repository.record_validation(
            change_set_id=change_set_id,
            status="validated",
            valid=True,
            candidate_digest=validation.candidate_digest,
            outcome=model_validation_outcome(validation),
        )
        if scope_addition is None:
            action_count = await ModelMaterializer(
                transaction=transaction,
                model_id=model_id,
                source_context_digest=row["base_source_context_digest"],
            ).apply(validation.records)
        else:
            actor, tenant_id, object_ids = scope_addition
            result = await transaction.fetch_one(
                "SELECT application.add_model_input_scope_objects(%s,%s,%s,%s,%s,%s) AS count",
                (
                    actor.entra_tenant_id,
                    actor.entra_object_id,
                    tenant_id,
                    model_id,
                    expected_model_revision,
                    object_ids,
                ),
            )
            if result is None:
                raise DependencyUnavailableError()
            action_count = result["count"]
        revision = await repository.advance_model_revision(
            model_id=model_id,
            expected_model_revision=expected_model_revision,
            changed=action_count > 0,
        )
        if revision is None:
            raise ModelRevisionConflictError()
        await repository.mark_applied(change_set_id=change_set_id)
        for event_type in ("created", "section_put", "validated", "applied"):
            await repository.insert_event(
                change_set_id=change_set_id,
                model_id=model_id,
                event_type=event_type,
                draft_revision=1 if event_type == "created" else staged["draft_revision"],
                section=section,
                action_count=action_count,
                outcome=outcome if event_type == "applied" else section,
                metadata={
                    "request_digest": request_digest,
                    "model_revision": revision["model_revision"],
                    **({"layer": layer} if layer is not None else {}),
                },
                correlation_id=idempotency_key,
            )
        return ReviewModelRecordsResult(
            model_id=model_id,
            model_change_set_id=change_set_id,
            model_revision=revision["model_revision"],
            action_count=action_count,
        )

    async def review_records(
        self,
        principal: RequestPrincipal,
        *,
        tenant_id: int,
        model_id: int,
        command: ReviewModelRecordsRequest,
        idempotency_key: UUID,
    ) -> ReviewModelRecordsResult:
        """Apply a human's exact lifecycle decision, preserving authored content."""
        request_digest = hashlib.sha256(
            json.dumps(
                {**command.model_dump(exclude_none=True), "record_ids": sorted(command.record_ids)},
                sort_keys=True,
                separators=(",", ":"),
            ).encode()
        ).hexdigest()
        async with self._database.write_transaction() as transaction:
            repository, model, principal_id = await self._authorize_record_review(
                transaction, principal, tenant_id=tenant_id, model_id=model_id
            )
            replay = await repository.replay_review(
                model_id=model_id, principal_id=principal_id, correlation_id=idempotency_key
            )
            if replay is not None:
                metadata = replay["event_metadata"]
                if metadata.get("request_digest") != request_digest:
                    raise WorkbenchError("review_conflict", "This review key was already used.")
                return ReviewModelRecordsResult(
                    model_id=model_id,
                    model_change_set_id=replay["model_change_set_id"],
                    model_revision=metadata["model_revision"],
                    action_count=replay["action_count"],
                )
            if model["model_revision"] != command.expected_model_revision:
                raise ModelRevisionConflictError()
            if await repository.has_running_tenant_workflow(tenant_id=tenant_id):
                raise TenantWorkflowConflictError()
            model_context = ModelReadContext(
                model_id=model_id,
                tenant_id=tenant_id,
                model_name=model["model_name"],
                model_revision=model["model_revision"],
            )
            changed_rows: list[tuple[str, int, bool, str]] = []
            if command.dataset != "analysis_result":
                review = await read_model_review_snapshot(transaction, model_context)
                snapshot = review.snapshot
                prepared = prepare_model_record_review(
                    review,
                    physical_scope=await load_model_physical_scope(transaction, model_context),
                    dataset=command.dataset,
                    record_ids=command.record_ids,
                    action=command.action,
                )
                validation = prepared.validation
                if any(issue.code == "record_locked" for issue in validation.issues):
                    raise WorkbenchError(
                        "record_locked",
                        "Unlock selected and required records before changing their status.",
                    )
                if (
                    command.expected_plan_digest is not None
                    and command.expected_plan_digest != prepared.plan_digest
                ):
                    raise WorkbenchError(
                        "review_conflict", "The review changed. Refresh its preview."
                    )
                if command.expected_plan_digest is None and any(
                    not item.selected and item.original != item.reviewed
                    for item in prepared.decisions
                ):
                    raise WorkbenchError(
                        "review_confirmation_required",
                        "Review and confirm the required dependent changes before applying.",
                    )
                for decision in prepared.decisions:
                    if decision.original != decision.reviewed:
                        changed_rows.append(
                            (
                                decision.dataset,
                                decision.record_id,
                                *review_lifecycle(decision.reviewed, decision.dataset),
                            )
                        )
            else:
                rows = await repository.read_analysis_review_records(
                    model_id=model_id, record_ids=command.record_ids
                )
                if len(rows) != len(command.record_ids):
                    raise WorkbenchError(
                        "model_record_not_found", "A selected record is unavailable."
                    )
                records: list[dict[str, object]] = []
                originals: list[AnalysisResultRecord] = []
                for row in rows:
                    original = AnalysisResultRecord.model_validate(
                        {field: row[field] for field in AnalysisResultRecord.model_fields}
                    )
                    originals.append(original)
                    values = original.model_dump(mode="json")
                    if command.action in {"lock", "unlock"}:
                        values["analysis_result_is_locked"] = command.action == "lock"
                    else:
                        values["analysis_result_status"] = (
                            "inactive" if command.action == "deactivate" else "active"
                        )
                        if original.analysis_result_is_locked and values != original.model_dump(
                            mode="json"
                        ):
                            raise WorkbenchError(
                                "record_locked",
                                "Unlock selected records before changing their status.",
                            )
                    reviewed = AnalysisResultRecord.model_validate(values)
                    records.append(values)
                    if reviewed != original:
                        changed_rows.append(
                            (
                                "analysis_result",
                                row["analysis_result_id"],
                                reviewed.analysis_result_is_locked,
                                reviewed.analysis_result_status,
                            )
                        )

                # Review changes only these two lifecycle fields. Generic authoring
                # validation and its prohibition on changing locked content remain intact.
                snapshot = await build_model_snapshot(transaction, model_context)
                validation_snapshot = snapshot
                if command.action == "unlock":
                    validation_snapshot = snapshot.model_copy(
                        update={
                            "analysis": snapshot.analysis.model_copy(
                                update={
                                    "relationships": tuple(
                                        record.model_copy(
                                            update={"analysis_result_is_locked": False}
                                        )
                                        if record in originals
                                        else record
                                        for record in snapshot.analysis.relationships
                                    ),
                                }
                            ),
                        }
                    )
                validation = validate_future_graph(
                    snapshot=validation_snapshot,
                    staged_documents={"analysis_result": records},
                    physical_scope=await load_model_physical_scope(transaction, model_context),
                )
            if not validation.valid or validation.candidate_digest is None:
                raise WorkbenchError(
                    "review_conflict",
                    "The review conflicts with the current Model. Refresh and retry.",
                )
            validation = replace(
                validation,
                action_review=build_model_action_review(
                    model_snapshot_records(snapshot), validation.records
                ),
            )
            # Row locks cannot stop a lease expiring during complete-graph validation.
            authorization = await self._authorizer.authorize_tenant(
                transaction, principal, tenant_id=tenant_id, policy=ToolPolicy.TENANT_MODEL_WRITE
            )
            if authorization.principal.principal_id != principal_id:
                raise AuthorizationDeniedError()
            change_set_id = uuid4()
            row = await repository.create(
                change_set_id=change_set_id,
                model_id=model_id,
                workflow_run_id=None,
                principal_id=principal_id,
                correlation_id=idempotency_key,
            )
            if row is None:
                raise ModelNotFoundError()
            documents = model_change_set_documents(row)
            for dataset, reviewed_records in validation.records.items():
                documents[DATASETS_BY_NAME[dataset].section][dataset] = [
                    record.model_dump(mode="json") for record in reviewed_records
                ]
            validate_model_change_set_document_bounds(documents)
            staged = await repository.stage_documents(
                documents=documents, change_set_id=change_set_id
            )
            if staged is None:
                raise ModelChangeSetNotFoundError()
            await repository.record_validation(
                change_set_id=change_set_id,
                status="validated",
                candidate_digest=validation.candidate_digest,
                valid=True,
                outcome=model_validation_outcome(validation),
            )
            for dataset, record_id, locked, status in changed_rows:
                updated = await repository.apply_record_review(
                    dataset=dataset,
                    model_id=model_id,
                    record_id=record_id,
                    locked=locked,
                    status=status,
                    actor=f"principal:{principal_id}",
                )
                if updated is None:
                    raise WorkbenchError(
                        "model_record_not_found", "A selected record is unavailable."
                    )
            revision = await repository.advance_model_revision(
                model_id=model_id,
                expected_model_revision=command.expected_model_revision,
                changed=bool(changed_rows),
            )
            if revision is None:
                raise ModelRevisionConflictError()
            await repository.mark_applied(change_set_id=change_set_id)
            for event_type in ("created", "section_put", "validated", "applied"):
                await repository.insert_event(
                    change_set_id=change_set_id,
                    model_id=model_id,
                    event_type=event_type,
                    draft_revision=1 if event_type == "created" else staged["draft_revision"],
                    section=DATASETS_BY_NAME[command.dataset].section,
                    action_count=len(changed_rows),
                    outcome="review_applied" if event_type == "applied" else "review",
                    metadata={
                        "action": command.action,
                        "dataset": command.dataset,
                        "request_digest": request_digest,
                        "model_revision": revision["model_revision"],
                    },
                    correlation_id=idempotency_key,
                )
        return ReviewModelRecordsResult(
            model_id=model_id,
            model_change_set_id=change_set_id,
            model_revision=revision["model_revision"],
            action_count=len(changed_rows),
        )

    async def preview_record_review(
        self,
        principal: RequestPrincipal,
        *,
        tenant_id: int,
        model_id: int,
        command: PreviewModelRecordsRequest,
        page: int = 1,
    ) -> PreviewModelRecordsResult:
        async with self._database.write_transaction() as transaction:
            repository, model, _ = await self._authorize_record_review(
                transaction, principal, tenant_id=tenant_id, model_id=model_id
            )
            if model["model_revision"] != command.expected_model_revision:
                raise ModelRevisionConflictError()
            if await repository.has_running_tenant_workflow(tenant_id=tenant_id):
                raise TenantWorkflowConflictError()
            model_context = ModelReadContext(
                model_id=model_id,
                tenant_id=tenant_id,
                model_name=model["model_name"],
                model_revision=model["model_revision"],
            )
            review = await read_model_review_snapshot(transaction, model_context)
            prepared = prepare_model_record_review(
                review,
                physical_scope=await load_model_physical_scope(transaction, model_context),
                dataset=command.dataset,
                record_ids=command.record_ids,
                action=command.action,
            )
            if (
                command.expected_plan_digest is not None
                and command.expected_plan_digest != prepared.plan_digest
            ):
                raise WorkbenchError("review_conflict", "The review changed. Refresh its preview.")
            count = len(prepared.decisions)
            if page < 1 or (page - 1) * 200 >= count:
                raise InvalidRequestError("The review page is unavailable.")
            items: list[ModelRecordReviewItem] = []
            for decision in prepared.decisions[(page - 1) * 200 : page * 200]:
                original = decision.original.model_dump()
                items.append(
                    ModelRecordReviewItem(
                        dataset=decision.dataset,
                        record_id=decision.record_id,
                        selected=decision.selected,
                        reason=decision.reason,
                        label=" · ".join(
                            str(original[name])
                            for name in DATASETS_BY_NAME[decision.dataset].canonical_key
                        ),
                        is_locked=review_lifecycle(decision.original, decision.dataset)[0],
                        desired_locked=review_lifecycle(decision.reviewed, decision.dataset)[0],
                        status=cast(Any, review_lifecycle(decision.original, decision.dataset)[1]),
                        desired_status=cast(
                            Any, review_lifecycle(decision.reviewed, decision.dataset)[1]
                        ),
                        changed=decision.original != decision.reviewed,
                    )
                )
            return PreviewModelRecordsResult(
                model_id=model_id,
                model_revision=model["model_revision"],
                plan_digest=prepared.plan_digest,
                can_apply=prepared.validation.valid,
                action_count=sum(item.original != item.reviewed for item in prepared.decisions),
                additional_change_count=sum(
                    not item.selected and item.original != item.reviewed
                    for item in prepared.decisions
                ),
                total_record_count=count,
                items=tuple(items),
                issues=tuple(
                    ModelRecordReviewIssue(
                        code=issue.code, dataset=issue.dataset, message=issue.message
                    )
                    for issue in prepared.validation.issues[:20]
                ),
                issue_count=len(prepared.validation.issues),
                page=page,
                next_page=page + 1 if page * 200 < count else None,
            )

    async def _authorize_record_review(
        self,
        transaction: WriteTransaction,
        principal: RequestPrincipal,
        *,
        tenant_id: int,
        model_id: int,
    ) -> tuple[PostgresModelChangeSetRepository, dict[str, Any], int]:
        if (
            principal.actor_kind is not ActorKind.HUMAN
            or principal.entra_tenant_id is None
            or principal.entra_object_id is None
        ):
            raise AuthorizationDeniedError()
        repository = PostgresModelChangeSetRepository(transaction)
        # The governed helper locks Model then Tenant before write authorization.
        # Taking authorization's SHARE fence first would require a deadlocking upgrade.
        model = await repository.authorize_record_review(
            entra_tenant_id=principal.entra_tenant_id,
            entra_object_id=principal.entra_object_id,
            tenant_id=tenant_id,
            model_id=model_id,
        )
        if model is None:
            raise DependencyUnavailableError()
        denial = model["denial_code"]
        if denial is not None:
            errors: dict[str, WorkbenchError] = {
                "invalid_request": InvalidRequestError("The Model review request is invalid."),
                "authorization_denied": AuthorizationDeniedError(),
                "model_not_found": ModelNotFoundError(),
                "tenant_not_found": ModelNotFoundError(),
                "tenant_lock_required": TenantLockRequiredError(),
                "tenant_locked": TenantLockRequiredError(),
            }
            raise errors.get(denial, DependencyUnavailableError())
        principal_id = model["principal_id"]
        if (
            not isinstance(principal_id, int)
            or isinstance(principal_id, bool)
            or principal_id < 1
            or model["model_id"] != model_id
            or model["tenant_id"] != tenant_id
        ):
            raise DependencyUnavailableError()
        return repository, model, principal_id

    async def create_or_resume(
        self,
        principal: RequestPrincipal,
        *,
        tenant_id: int,
        model_id: int,
        command: CreateModelChangeSetRequest,
        idempotency_key: UUID,
    ) -> CreateModelChangeSetResult:
        async with self._database.write_transaction() as transaction:
            repository = PostgresModelChangeSetRepository(transaction)
            model = await repository.get_model(tenant_id=tenant_id, model_id=model_id)
            if model is None:
                raise ModelNotFoundError()
            if model["model_revision"] != command.expected_model_revision:
                raise ModelRevisionConflictError()
            authorization = await self._authorizer.authorize_tenant(
                transaction,
                principal,
                tenant_id=tenant_id,
                policy=ToolPolicy.TENANT_MODEL_WRITE,
            )
            principal_id = authorization.principal.principal_id
            if principal_id is None:
                raise AuthorizationDeniedError()

            expired = await repository.expire_owned(
                model_id=model_id,
                principal_id=principal_id,
            )
            for expired_row in expired:
                await repository.insert_event(
                    change_set_id=expired_row["model_change_set_id"],
                    model_id=model_id,
                    event_type="expired",
                    draft_revision=expired_row["draft_revision"],
                    section=None,
                    action_count=0,
                    outcome="expired",
                    metadata={},
                    correlation_id=uuid4(),
                )

            row = await repository.find_ongoing(
                model_id=model_id,
                principal_id=principal_id,
            )
            created = row is None
            if row is None:
                change_set_id = uuid4()
                row = await repository.create(
                    change_set_id=change_set_id,
                    model_id=model_id,
                    workflow_run_id=None,
                    principal_id=principal_id,
                    correlation_id=idempotency_key,
                )
                if row is None:
                    raise ModelNotFoundError()
                await repository.insert_event(
                    change_set_id=row["model_change_set_id"],
                    model_id=model_id,
                    event_type="created",
                    draft_revision=row["draft_revision"],
                    section=None,
                    action_count=0,
                    outcome="created",
                    metadata={},
                    correlation_id=idempotency_key,
                )

        return CreateModelChangeSetResult(
            model_id=model_id,
            model_change_set_id=row["model_change_set_id"],
            created=created,
            status=row["model_change_set_status"],
            draft_revision=row["draft_revision"],
            created_at=require_datetime(row, "created_time"),
            expires_at=require_datetime(row, "expires_time"),
        )

    async def stage(
        self,
        principal: RequestPrincipal,
        *,
        tenant_id: int,
        model_id: int,
        change_set_id: UUID,
        command: StageModelChangeSetRequest,
        idempotency_key: UUID,
    ) -> StageModelChangeSetResult:
        self._require_web_stage_datasets(change.dataset for change in command.changes)
        staged = validate_model_stage_changes(command.changes)
        async with self._database.write_transaction() as transaction:
            repository, _model, authorization = await self._authorize_model(
                transaction,
                principal,
                tenant_id=tenant_id,
                model_id=model_id,
                policy=ToolPolicy.TENANT_MODEL_WRITE,
            )
            row = await self._owned_change_set(
                repository,
                change_set_id=change_set_id,
                model_id=model_id,
                principal_id=authorization.principal.principal_id,
                for_update=True,
            )
            require_mutable_model_change_set(row)
            self._require_draft_revision(row, command.expected_draft_revision)
            documents = model_change_set_documents(row)
            for dataset, records in staged.items():
                section = DATASETS_BY_NAME[dataset].section
                documents[section][dataset] = records
            validate_model_change_set_document_bounds(documents)
            updated = await repository.stage_documents(
                documents=documents,
                change_set_id=change_set_id,
            )
            if updated is None:
                raise ModelChangeSetNotFoundError()
            sections = sorted({DATASETS_BY_NAME[name].section for name in staged})
            await repository.insert_event(
                change_set_id=change_set_id,
                model_id=model_id,
                event_type="section_put",
                draft_revision=updated["draft_revision"],
                section=sections[0] if len(sections) == 1 else None,
                action_count=sum(len(records) for records in staged.values()),
                outcome="staged",
                metadata={"datasets": sorted(staged)},
                correlation_id=idempotency_key,
            )
        return StageModelChangeSetResult(
            model_id=model_id,
            model_change_set_id=change_set_id,
            datasets=tuple(
                ModelChangeSetDatasetCount(
                    dataset=cast(ModelChangeSetDataset, dataset),
                    record_count=len(records),
                )
                for dataset, records in staged.items()
            ),
            draft_revision=updated["draft_revision"],
            expires_at=require_datetime(updated, "expires_time"),
        )

    async def begin_stage_batch(
        self,
        principal: RequestPrincipal,
        *,
        tenant_id: int,
        model_id: int,
        change_set_id: UUID,
        command: BeginModelStageBatchRequest,
        idempotency_key: UUID,
    ) -> BeginModelStageBatchResult:
        self._require_web_stage_datasets((command.dataset,))
        async with self._database.write_transaction() as transaction:
            repository, _model, authorization = await self._authorize_model(
                transaction,
                principal,
                tenant_id=tenant_id,
                model_id=model_id,
                policy=ToolPolicy.TENANT_MODEL_WRITE,
            )
            principal_id = authorization.principal.principal_id
            if principal_id is None:
                raise AuthorizationDeniedError()
            change_set = await self._owned_change_set(
                repository,
                change_set_id=change_set_id,
                model_id=model_id,
                principal_id=principal_id,
                for_update=True,
            )
            require_mutable_model_change_set(change_set)
            self._require_draft_revision(change_set, command.expected_draft_revision)
            await repository.expire_stage_batches(
                change_set_id=change_set_id,
                dataset=command.dataset,
            )
            row = await repository.find_stage_batch(
                change_set_id=change_set_id,
                dataset=command.dataset,
            )
            created = row is None
            if row is not None:
                if (
                    row["created_by_principal_id"] != principal_id
                    or row["expected_draft_revision"] != command.expected_draft_revision
                    or row["total_record_count"] != command.total_record_count
                    or row["total_chunk_count"] != command.total_chunk_count
                    or row["payload_mode"] != command.payload_mode
                    or row["total_payload_bytes"] != command.total_payload_bytes
                    or row["batch_sha256"] != command.batch_sha256
                ):
                    raise StageBatchConflictError()
            else:
                row = await repository.create_stage_batch(
                    (
                        uuid4(),
                        change_set_id,
                        model_id,
                        command.dataset,
                        command.expected_draft_revision,
                        command.total_record_count,
                        command.total_chunk_count,
                        command.payload_mode,
                        command.total_payload_bytes,
                        command.batch_sha256,
                        principal_id,
                        idempotency_key,
                        change_set["expires_time"],
                    )
                )
                if row is None:
                    raise ModelChangeSetNotFoundError()
        return BeginModelStageBatchResult(
            model_id=model_id,
            model_change_set_id=change_set_id,
            stage_batch_id=row["stage_batch_id"],
            dataset=cast(ModelChangeSetDataset, row["dataset_name"]),
            created=created,
            total_record_count=row["total_record_count"],
            total_chunk_count=row["total_chunk_count"],
            received_chunk_count=row["received_chunk_count"],
            expected_draft_revision=command.expected_draft_revision,
            expires_at=require_datetime(row, "expires_time"),
            payload_mode=row["payload_mode"],
            total_payload_bytes=row["total_payload_bytes"],
        )

    async def put_stage_chunk(
        self,
        principal: RequestPrincipal,
        *,
        tenant_id: int,
        model_id: int,
        change_set_id: UUID,
        stage_batch_id: UUID,
        chunk_index: int,
        command: PutModelStageChunkRequest,
        idempotency_key: UUID,
    ) -> PutModelStageChunkResult:
        del idempotency_key
        self._require_web_stage_datasets((command.dataset,))
        normalized: list[dict[str, object]] = []
        payload_fragment: bytes | None = None
        if command.payload_mode == "records":
            assert command.records is not None
            normalized = validate_model_stage_changes(
                [StageModelChange(dataset=command.dataset, records=command.records)]
            )[command.dataset]
            if len(canonical_records_bytes(normalized)) > MAX_MODEL_STAGE_CHUNK_BYTES:
                raise InvalidRequestError("The Stage chunk exceeds the bounded byte limit.")
            actual_sha256 = canonical_records_sha256(normalized)
        else:
            assert command.payload_fragment_base64 is not None
            try:
                payload_fragment = decode_canonical_base64_fragment(command.payload_fragment_base64)
            except ValueError:
                raise InvalidRequestError("Stage payload fragment is invalid.") from None
            actual_sha256 = hashlib.sha256(payload_fragment).hexdigest()
        if actual_sha256 != command.chunk_sha256:
            raise InvalidRequestError(
                "The Stage chunk SHA-256 does not match its canonical payload."
            )
        async with self._database.write_transaction() as transaction:
            repository, _model, authorization = await self._authorize_model(
                transaction,
                principal,
                tenant_id=tenant_id,
                model_id=model_id,
                policy=ToolPolicy.TENANT_MODEL_WRITE,
            )
            change_set = await self._owned_change_set(
                repository,
                change_set_id=change_set_id,
                model_id=model_id,
                principal_id=authorization.principal.principal_id,
                for_update=True,
            )
            require_mutable_model_change_set(change_set)
            batch = await repository.get_stage_batch(
                stage_batch_id=stage_batch_id,
                change_set_id=change_set_id,
                model_id=model_id,
            )
            require_model_stage_batch(batch, authorization.principal, command.dataset)
            assert batch is not None
            self._require_draft_revision(change_set, batch["expected_draft_revision"])
            if batch["payload_mode"] != command.payload_mode:
                raise InvalidRequestError("Payload mode does not match the Stage Batch manifest.")
            if chunk_index > batch["total_chunk_count"]:
                raise InvalidRequestError("Chunk index exceeds the Stage Batch manifest.")
            existing = (
                await repository.get_stage_payload_chunk(
                    stage_batch_id=stage_batch_id,
                    chunk_index=chunk_index,
                )
                if command.payload_mode == "json_fragments"
                else await repository.get_stage_chunk(
                    stage_batch_id=stage_batch_id,
                    chunk_index=chunk_index,
                )
            )
            duplicate = existing is not None
            if existing is not None:
                fragment_conflict = command.payload_mode == "json_fragments" and (
                    payload_fragment is None
                    or bytes(existing["payload_fragment"]) != payload_fragment
                )
                record_conflict = (
                    command.payload_mode == "records" and existing["records_document"] != normalized
                )
                if (
                    existing["chunk_sha256"] != command.chunk_sha256
                    or fragment_conflict
                    or record_conflict
                ):
                    raise StageChunkConflictError()
            else:
                if command.payload_mode == "json_fragments":
                    assert payload_fragment is not None
                    totals = await repository.stage_payload_chunk_totals(
                        stage_batch_id=stage_batch_id
                    )
                    if (
                        totals["payload_byte_count"] + len(payload_fragment)
                        > batch["total_payload_bytes"]
                    ):
                        raise InvalidRequestError("Stage chunks exceed the approved payload bytes.")
                    await repository.insert_stage_payload_chunk(
                        stage_batch_id=stage_batch_id,
                        chunk_index=chunk_index,
                        payload_fragment=payload_fragment,
                        chunk_sha256=command.chunk_sha256,
                    )
                else:
                    totals = await repository.stage_chunk_totals(stage_batch_id=stage_batch_id)
                    if totals["record_count"] + len(normalized) > batch["total_record_count"]:
                        raise InvalidRequestError("Stage chunks exceed the approved record count.")
                    await repository.insert_stage_chunk(
                        stage_batch_id=stage_batch_id,
                        chunk_index=chunk_index,
                        records=normalized,
                        chunk_sha256=command.chunk_sha256,
                    )
            totals = (
                await repository.stage_payload_chunk_totals(stage_batch_id=stage_batch_id)
                if command.payload_mode == "json_fragments"
                else await repository.stage_chunk_totals(stage_batch_id=stage_batch_id)
            )
        return PutModelStageChunkResult(
            model_id=model_id,
            model_change_set_id=change_set_id,
            stage_batch_id=stage_batch_id,
            dataset=command.dataset,
            duplicate=duplicate,
            chunk_index=chunk_index,
            record_count=len(normalized),
            received_chunk_count=totals["chunk_count"],
            total_chunk_count=batch["total_chunk_count"],
            expires_at=require_datetime(batch, "expires_time"),
            payload_mode=command.payload_mode,
            payload_byte_count=(len(payload_fragment) if payload_fragment is not None else None),
        )

    async def commit_stage_batch(
        self,
        principal: RequestPrincipal,
        *,
        tenant_id: int,
        model_id: int,
        change_set_id: UUID,
        stage_batch_id: UUID,
        command: ExpectedDraftRevisionRequest,
        idempotency_key: UUID,
    ) -> CommitModelStageBatchResult:
        async with self._database.write_transaction() as transaction:
            repository, _model, authorization = await self._authorize_model(
                transaction,
                principal,
                tenant_id=tenant_id,
                model_id=model_id,
                policy=ToolPolicy.TENANT_MODEL_WRITE,
            )
            change_set = await self._owned_change_set(
                repository,
                change_set_id=change_set_id,
                model_id=model_id,
                principal_id=authorization.principal.principal_id,
                for_update=True,
            )
            batch = await repository.get_stage_batch(
                stage_batch_id=stage_batch_id,
                change_set_id=change_set_id,
                model_id=model_id,
            )
            if (
                batch is None
                or batch["created_by_principal_id"] != authorization.principal.principal_id
            ):
                raise StageBatchNotFoundError()
            self._require_web_stage_datasets((batch["dataset_name"],))
            if batch["expected_draft_revision"] != command.expected_draft_revision:
                raise InvalidRequestError(
                    "Expected revision does not match the Stage Batch manifest."
                )
            if batch["stage_batch_status"] == "committed":
                replayed = True
                committed_revision = batch["committed_revision"]
                committed_expires_at = require_datetime(batch, "committed_expires_time")
            else:
                require_model_stage_batch(batch, authorization.principal, None)
                require_mutable_model_change_set(change_set)
                self._require_draft_revision(change_set, command.expected_draft_revision)
                payload_mode = batch["payload_mode"]
                chunks = (
                    await repository.get_stage_payload_chunks(stage_batch_id=stage_batch_id)
                    if payload_mode == "json_fragments"
                    else await repository.get_stage_chunks(stage_batch_id=stage_batch_id)
                )
                if (
                    len(chunks) != batch["total_chunk_count"]
                    or stage_batch_sha256([chunk["chunk_sha256"] for chunk in chunks])
                    != batch["batch_sha256"]
                ):
                    raise StageBatchIncompleteError()
                payload: bytes | None = None
                if payload_mode == "json_fragments":
                    if (
                        sum(chunk["chunk_byte_count"] for chunk in chunks)
                        != batch["total_payload_bytes"]
                    ):
                        raise StageBatchIncompleteError()
                    payload = b"".join(bytes(chunk["payload_fragment"]) for chunk in chunks)
                    assembled = decode_canonical_model_stage_payload(
                        payload,
                        expected_record_count=batch["total_record_count"],
                    )
                else:
                    if (
                        sum(chunk["record_count"] for chunk in chunks)
                        != batch["total_record_count"]
                    ):
                        raise StageBatchIncompleteError()
                    assembled = [
                        cast(dict[str, object], record)
                        for chunk in chunks
                        for record in chunk["records_document"]
                    ]
                dataset = cast(ModelChangeSetDataset, batch["dataset_name"])
                staged = validate_model_stage_changes(
                    [StageModelChange(dataset=dataset, records=assembled)]
                )
                if (
                    payload_mode == "json_fragments"
                    and payload is not None
                    and canonical_records_bytes(staged[dataset]) != payload
                ):
                    raise InvalidRequestError("The Stage payload is not canonical normalized JSON.")
                documents = model_change_set_documents(change_set)
                section = DATASETS_BY_NAME[dataset].section
                documents[section][dataset] = staged[dataset]
                validate_model_change_set_document_bounds(documents)
                updated = await repository.stage_documents(
                    documents=documents,
                    change_set_id=change_set_id,
                )
                if updated is None:
                    raise ModelChangeSetNotFoundError()
                await repository.insert_event(
                    change_set_id=change_set_id,
                    model_id=model_id,
                    event_type="section_put",
                    draft_revision=updated["draft_revision"],
                    section=section,
                    action_count=len(assembled),
                    outcome="staged",
                    metadata={"datasets": [dataset]},
                    correlation_id=idempotency_key,
                )
                marked = await repository.mark_stage_batch_committed(
                    stage_batch_id=stage_batch_id,
                    draft_revision=updated["draft_revision"],
                    expires_at=require_datetime(updated, "expires_time"),
                )
                if marked is None:
                    raise StageBatchNotFoundError()
                replayed = False
                committed_revision = marked["committed_revision"]
                committed_expires_at = require_datetime(marked, "committed_expires_time")
        return CommitModelStageBatchResult(
            model_id=model_id,
            model_change_set_id=change_set_id,
            stage_batch_id=stage_batch_id,
            dataset=cast(ModelChangeSetDataset, batch["dataset_name"]),
            replayed=replayed,
            record_count=batch["total_record_count"],
            draft_revision=committed_revision,
            expires_at=committed_expires_at,
        )

    async def get(
        self,
        principal: RequestPrincipal,
        *,
        tenant_id: int,
        model_id: int,
        change_set_id: UUID,
        dataset: ModelDataset | None,
    ) -> GetModelChangeSetResult:
        async with self._database.write_transaction() as transaction:
            repository, _model, authorization = await self._authorize_model(
                transaction,
                principal,
                tenant_id=tenant_id,
                model_id=model_id,
                policy=ToolPolicy.TENANT_READ,
            )
            row = await self._owned_change_set(
                repository,
                change_set_id=change_set_id,
                model_id=model_id,
                principal_id=authorization.principal.principal_id,
                for_update=False,
            )
        pending = pending_model_change_set_datasets(row)
        return GetModelChangeSetResult(
            model_id=model_id,
            model_change_set_id=change_set_id,
            status=row["model_change_set_status"],
            draft_revision=row["draft_revision"],
            candidate_digest=row["candidate_digest"],
            validation_outcome=bounded_validation_outcome(row["validation_outcome"]),
            dataset_counts=tuple(
                ModelDatasetCount(
                    dataset=cast(ModelDataset, name),
                    record_count=len(records),
                )
                for name, records in sorted(pending.items())
            ),
            dataset=dataset,
            records=None if dataset is None else pending.get(dataset, []),
            created_at=require_datetime(row, "created_time"),
            last_activity_at=require_datetime(row, "last_activity_time"),
            expires_at=require_datetime(row, "expires_time"),
            validated_at=self._optional_datetime(row, "validated_time"),
            applied_at=self._optional_datetime(row, "applied_time"),
            terminal_at=self._optional_datetime(row, "terminal_time"),
        )

    async def validate(
        self,
        principal: RequestPrincipal,
        *,
        tenant_id: int,
        model_id: int,
        change_set_id: UUID,
        command: ExpectedDraftRevisionRequest,
        idempotency_key: UUID,
    ) -> ValidateModelChangeSetResult:
        async with self._database.write_transaction() as transaction:
            repository, model, authorization = await self._authorize_model(
                transaction,
                principal,
                tenant_id=tenant_id,
                model_id=model_id,
                policy=ToolPolicy.TENANT_MODEL_WRITE,
            )
            row = await self._owned_change_set(
                repository,
                change_set_id=change_set_id,
                model_id=model_id,
                principal_id=authorization.principal.principal_id,
                for_update=True,
            )
            require_mutable_model_change_set(row)
            self._require_draft_revision(row, command.expected_draft_revision)
            self._require_web_writable_pending(row)
            validation = await validate_locked_model_change_set(transaction, model, row)
            updated = await repository.record_validation(
                change_set_id=change_set_id,
                status="validated" if validation.valid else "active",
                candidate_digest=(validation.candidate_digest if validation.valid else None),
                outcome=model_validation_outcome(validation),
                valid=validation.valid,
            )
            if updated is None:
                raise ModelChangeSetNotFoundError()
            await repository.insert_event(
                change_set_id=change_set_id,
                model_id=model_id,
                event_type="validated" if validation.valid else "validation_failed",
                draft_revision=row["draft_revision"],
                section=None,
                action_count=sum(len(records) for records in validation.records.values()),
                outcome="valid" if validation.valid else "invalid",
                metadata={"phase": validation.phase, "error_count": len(validation.issues)},
                correlation_id=idempotency_key,
            )
        return ValidateModelChangeSetResult(
            model_id=model_id,
            model_change_set_id=change_set_id,
            valid=validation.valid,
            phase=validation.phase,
            status=updated["model_change_set_status"],
            draft_revision=updated["draft_revision"],
            candidate_digest=updated["candidate_digest"],
            staged_record_count=sum(len(records) for records in validation.records.values()),
            error_count=len(validation.issues),
            error_groups=model_validation_error_groups(validation),
            errors=tuple(
                model_validation_error(issue)
                for issue in validation.issues[:MAX_AGENT_VALIDATION_ERROR_EXAMPLES]
            ),
            errors_truncated=(len(validation.issues) > MAX_AGENT_VALIDATION_ERROR_EXAMPLES),
            action_review=model_action_review(validation.action_review),
            validated_at=self._optional_datetime(updated, "validated_time"),
            expires_at=require_datetime(updated, "expires_time"),
        )

    async def apply(
        self,
        principal: RequestPrincipal,
        *,
        tenant_id: int,
        model_id: int,
        change_set_id: UUID,
        command: ExpectedDraftRevisionRequest,
        idempotency_key: UUID,
    ) -> ApplyModelChangeSetResult:
        async with self._database.write_transaction() as transaction:
            repository, model, authorization = await self._authorize_model(
                transaction,
                principal,
                tenant_id=tenant_id,
                model_id=model_id,
                policy=ToolPolicy.TENANT_MODEL_WRITE,
            )
            row = await self._owned_change_set(
                repository,
                change_set_id=change_set_id,
                model_id=model_id,
                principal_id=authorization.principal.principal_id,
                for_update=True,
            )
            if row["model_change_set_status"] != "validated":
                raise ModelChangeSetNotValidatedError()
            self._require_draft_revision(row, command.expected_draft_revision)
            self._require_web_writable_pending(row)
            validation = await validate_locked_model_change_set(transaction, model, row)
            if not validation.valid or validation.candidate_digest is None:
                raise CandidateDigestConflictError()
            if validation.candidate_digest != row["candidate_digest"]:
                raise CandidateDigestConflictError()
            materializer = ModelMaterializer(
                transaction=transaction,
                model_id=model_id,
                source_context_digest=row["base_source_context_digest"],
            )
            action_count = await materializer.apply(validation.records)
            revision = await repository.advance_model_revision(
                model_id=model_id,
                expected_model_revision=model.model_revision,
                changed=action_count > 0,
            )
            if revision is None:
                raise InvalidRequestError("Model revision changed during apply.")
            applied = await repository.mark_applied(change_set_id=change_set_id)
            if applied is None:
                raise ModelChangeSetNotFoundError()
            await repository.insert_event(
                change_set_id=change_set_id,
                model_id=model_id,
                event_type="applied",
                draft_revision=row["draft_revision"],
                section=None,
                action_count=action_count,
                outcome="applied",
                metadata={"model_revision": revision["model_revision"]},
                correlation_id=idempotency_key,
            )
        return ApplyModelChangeSetResult(
            model_id=model_id,
            model_change_set_id=change_set_id,
            draft_revision=row["draft_revision"],
            candidate_digest=validation.candidate_digest,
            action_count=action_count,
            model_revision=revision["model_revision"],
            applied_at=require_datetime(applied, "applied_time"),
        )

    async def archive(
        self,
        principal: RequestPrincipal,
        *,
        tenant_id: int,
        model_id: int,
        change_set_id: UUID,
        command: ExpectedDraftRevisionRequest,
        idempotency_key: UUID,
    ) -> ArchiveModelChangeSetResult:
        async with self._database.write_transaction() as transaction:
            repository, _model, authorization = await self._authorize_model(
                transaction,
                principal,
                tenant_id=tenant_id,
                model_id=model_id,
                policy=ToolPolicy.TENANT_READ,
            )
            row = await self._owned_change_set(
                repository,
                change_set_id=change_set_id,
                model_id=model_id,
                principal_id=authorization.principal.principal_id,
                for_update=True,
            )
            require_mutable_model_change_set(row)
            self._require_draft_revision(row, command.expected_draft_revision)
            archived = await repository.archive(
                change_set_id=change_set_id,
                model_id=model_id,
            )
            if archived is None:
                raise ModelChangeSetNotActiveError()
            await repository.insert_event(
                change_set_id=change_set_id,
                model_id=model_id,
                event_type="discarded",
                draft_revision=archived["draft_revision"],
                section=None,
                action_count=0,
                outcome="archived",
                metadata={},
                correlation_id=idempotency_key,
            )
        return ArchiveModelChangeSetResult(
            model_id=model_id,
            model_change_set_id=change_set_id,
            draft_revision=archived["draft_revision"],
            archived_at=require_datetime(archived, "terminal_time"),
        )

    async def _authorize_model(
        self,
        transaction: WriteTransaction,
        principal: RequestPrincipal,
        *,
        tenant_id: int,
        model_id: int,
        policy: ToolPolicy,
    ) -> tuple[
        PostgresModelChangeSetRepository,
        ModelReadContext,
        TenantAuthorization,
    ]:
        repository = PostgresModelChangeSetRepository(transaction)
        row = await repository.get_model(tenant_id=tenant_id, model_id=model_id)
        if row is None:
            raise ModelNotFoundError()
        authorization = await self._authorizer.authorize_tenant(
            transaction,
            principal,
            tenant_id=tenant_id,
            policy=policy,
        )
        return (
            repository,
            ModelReadContext(
                model_id=row["model_id"],
                tenant_id=row["tenant_id"],
                model_name=row["model_name"],
                model_revision=row["model_revision"],
            ),
            authorization,
        )

    @staticmethod
    async def _owned_change_set(
        repository: PostgresModelChangeSetRepository,
        *,
        change_set_id: UUID,
        model_id: int,
        principal_id: int | None,
        for_update: bool,
    ) -> dict[str, Any]:
        row = await repository.get_change_set(
            change_set_id=change_set_id,
            model_id=model_id,
            for_update=for_update,
        )
        if row is None or row["created_by_principal_id"] != principal_id:
            raise ModelChangeSetNotFoundError()
        return row

    @staticmethod
    def _require_draft_revision(row: Mapping[str, object], expected: int) -> None:
        current = row["draft_revision"]
        if current != expected:
            if not isinstance(current, int):
                raise ModelChangeSetNotFoundError()
            raise DraftRevisionConflictError(current)

    @staticmethod
    def _optional_datetime(row: Mapping[str, object], field: str) -> datetime | None:
        value = row[field]
        if value is None or isinstance(value, datetime):
            return value
        raise RuntimeError(f"Database returned an invalid {field}")

    @staticmethod
    def _require_web_stage_datasets(datasets: Iterable[object]) -> None:
        for dataset in datasets:
            if dataset == "model_input_scope":
                raise InvalidRequestError(
                    "Model Input Scope must use the governed Model Input Scope command."
                )
            if dataset == "profiling_profile":
                raise InvalidRequestError(
                    "Profiling results must use the governed Profiling persistence command."
                )

    @classmethod
    def _require_web_writable_pending(cls, row: Mapping[str, object]) -> None:
        require_mcp_writable_pending(row)
        cls._require_web_stage_datasets(pending_model_change_set_datasets(row))
