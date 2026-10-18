"""Governed Project Change Set application service."""

import hashlib
import json
from collections import Counter
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
    MAX_PROJECT_STAGE_CHUNK_BYTES,
    bounded_validation_outcome,
    canonical_records_bytes,
    canonical_records_sha256,
    decode_canonical_base64_fragment,
    stage_batch_sha256,
)
from gds_etl_workbench.application.change_sets.project import (
    ProjectChangeSetDatasetCount,
    ProjectDatasetCount,
    StageProjectChange,
    decode_canonical_project_stage_payload,
    load_project_physical_scope,
    pending_project_change_set_datasets,
    project_action_review,
    project_change_set_documents,
    project_validation_error,
    project_validation_error_groups,
    project_validation_outcome,
    require_mcp_writable_pending,
    require_mutable_project_change_set,
    require_project_stage_batch,
    validate_locked_project_change_set,
    validate_project_change_set_document_bounds,
    validate_project_stage_changes,
)
from gds_etl_workbench.application.change_sets.project_apply import ProjectMaterializer
from gds_etl_workbench.application.change_sets.project_validation import (
    ValidatedProjectChangeSet,
    build_project_action_review,
    validate_future_graph,
)
from gds_etl_workbench.application.project_read import (
    ProjectReadContext,
    authorize_project_read,
)
from gds_etl_workbench.application.project_snapshot import (
    build_project_snapshot,
    read_project_review_snapshot,
)
from gds_etl_workbench.domain.authorization import (
    ActorKind,
    RequestPrincipal,
    TenantRole,
    ToolPolicy,
)
from gds_etl_workbench.domain.errors import (
    AuthorizationDeniedError,
    CandidateDigestConflictError,
    DependencyUnavailableError,
    DraftRevisionConflictError,
    InvalidRequestError,
    ProjectChangeSetNotActiveError,
    ProjectChangeSetNotFoundError,
    ProjectChangeSetNotValidatedError,
    StageBatchConflictError,
    StageBatchIncompleteError,
    StageBatchNotFoundError,
    StageChunkConflictError,
    TenantLockRequiredError,
    TenantWorkflowConflictError,
    WorkbenchError,
)
from gds_etl_workbench.domain.modeling_records import AnalysisResultRecord, MappingObjectRecord
from gds_etl_workbench.domain.snapshots.project import (
    DATASETS_BY_NAME,
    ProjectChangeSetDataset,
    ProjectDataset,
    project_snapshot_records,
)
from gds_etl_workbench.infrastructure.postgres import WriteTransaction
from psycopg.types.json import Jsonb

from gds_workbench_api.features.context.authoring import (
    SaveContextGroupRequest,
    SaveContextRecordRequest,
    prepare_context_group,
    prepare_context_record,
)
from gds_workbench_api.features.mapping.editor import (
    MAPPING_INPUT_SCOPE_SQL,
    NEW_MAPPING_TARGET_SQL,
    mapping_record_editor,
    prepare_mapping_edit,
)
from gds_workbench_api.features.mapping.preparation_repository import MAPPING_SOURCE_CONTEXT_SQL
from gds_workbench_api.features.project_change_sets.input_scope import (
    AddInputScopeRequest,
    prepare_input_scope_addition,
)
from gds_workbench_api.features.projects import ProjectNotFoundError, ProjectRevisionConflictError

from .contracts import (
    ApplyProjectChangeSetResult,
    ArchiveProjectChangeSetResult,
    BeginProjectStageBatchRequest,
    BeginProjectStageBatchResult,
    CommitProjectStageBatchResult,
    CreateProjectChangeSetRequest,
    CreateProjectChangeSetResult,
    ExpectedDraftRevisionRequest,
    GetProjectChangeSetResult,
    PreviewProjectRecordsRequest,
    PreviewProjectRecordsResult,
    ProjectRecordHistoryItem,
    ProjectRecordHistoryPage,
    ProjectRecordReviewIssue,
    ProjectRecordReviewItem,
    PutProjectStageChunkRequest,
    PutProjectStageChunkResult,
    ReviewProjectRecordsRequest,
    ReviewProjectRecordsResult,
    StageProjectChangeSetRequest,
    StageProjectChangeSetResult,
    ValidateProjectChangeSetResult,
)
from .deletion import plan_project_deletion
from .editor import (
    ProjectRecordEditor,
    ProjectRecordEditorRequest,
    SaveProjectRecordRequest,
    prepare_project_record_edit,
    project_record_editor,
)
from .repository import PostgresProjectChangeSetRepository, require_datetime
from .review import (
    REVIEW_FIELDS,
    ProjectReviewDataset,
    prepare_project_record_review,
    review_lifecycle,
)


class ProjectChangeSetDatabase(Protocol):
    def write_transaction(self) -> AbstractAsyncContextManager[WriteTransaction]: ...


class DatabaseProjectChangeSetService:
    def __init__(
        self,
        *,
        database: ProjectChangeSetDatabase,
        authorizer: AuthorizationService,
    ) -> None:
        self._database = database
        self._authorizer = authorizer

    async def list_review_records(
        self,
        principal: RequestPrincipal,
        *,
        tenant_id: int,
        project_id: int,
        dataset: ProjectReviewDataset,
        expected_project_revision: int,
        page: int = 1,
        entity_type: str | None = None,
    ) -> ProjectRecordHistoryPage:
        # Project SHARE fence keeps numeric identity pages stable. Include inactive
        # owned history even when a Entity Mapping is no longer eligible to run.
        async with self._database.write_transaction() as transaction:
            _, project, _ = await self._authorize_project(
                transaction,
                principal,
                tenant_id=tenant_id,
                project_id=project_id,
                policy=ToolPolicy.TENANT_READ,
            )
            if project.project_revision != expected_project_revision:
                raise ProjectRevisionConflictError()
            review = await read_project_review_snapshot(
                transaction, project, enforce_row_limits=False
            )
            if entity_type is not None and (
                dataset != "generated_code"
                or entity_type not in {"logical_entity", "dimensional_entity"}
            ):
                raise InvalidRequestError("Layer filtering is available only for Generated Code.")
            rows = sorted(
                (record_id, row)
                for record_id, row in review.records_by_id.get(dataset, {}).items()
                if entity_type is None or getattr(row, "modeled_entity_type", None) == entity_type
            )
            if page < 1 or (page > 1 and (page - 1) * 200 >= len(rows)):
                raise InvalidRequestError("The record page is unavailable.")
            items: list[ProjectRecordHistoryItem] = []
            for record_id, row in rows[(page - 1) * 200 : page * 200]:
                locked, status = review_lifecycle(row, dataset)
                items.append(
                    ProjectRecordHistoryItem(
                        record_id=record_id,
                        label=" · ".join(
                            str(getattr(row, field))
                            for field in DATASETS_BY_NAME[dataset].canonical_key
                        ),
                        is_locked=locked,
                        status=cast(Any, status),
                    )
                )
        return ProjectRecordHistoryPage(
            project_id=project_id,
            project_revision=project.project_revision,
            dataset=dataset,
            items=tuple(items),
            next_page=page + 1 if page * 200 < len(rows) else None,
        )

    async def add_input_scope(
        self,
        principal: RequestPrincipal,
        *,
        tenant_id: int,
        project_id: int,
        command: AddInputScopeRequest,
        idempotency_key: UUID,
    ) -> ReviewProjectRecordsResult:
        request_digest = hashlib.sha256(
            json.dumps(
                {"operation": "add_input_scope", **command.model_dump()},
                sort_keys=True,
                separators=(",", ":"),
            ).encode()
        ).hexdigest()
        async with self._database.write_transaction() as transaction:
            repository, project, principal_id = await self._authorize_record_review(
                transaction, principal, tenant_id=tenant_id, project_id=project_id
            )
            replay = await repository.replay_review(
                project_id=project_id, principal_id=principal_id, correlation_id=idempotency_key
            )
            if replay is not None:
                metadata = replay["event_metadata"]
                if metadata.get("request_digest") != request_digest:
                    raise WorkbenchError("review_conflict", "This review key was already used.")
                return ReviewProjectRecordsResult(
                    project_id=project_id,
                    project_change_set_id=replay["project_change_set_id"],
                    project_revision=metadata["project_revision"],
                    action_count=replay["action_count"],
                )
            if project["project_revision"] != command.expected_project_revision:
                raise ProjectRevisionConflictError()
            if await repository.has_running_tenant_workflow(tenant_id=tenant_id):
                raise TenantWorkflowConflictError()
            context = ProjectReadContext(
                project_id=project_id,
                tenant_id=tenant_id,
                project_name=project["project_name"],
                project_revision=project["project_revision"],
                readable_source_tenant_ids=project["readable_source_tenant_ids"],
            )
            validation = await prepare_input_scope_addition(
                transaction, context, command.object_ids
            )
            await self._authorizer.authorize_tenant(
                transaction,
                principal,
                tenant_id=tenant_id,
                policy=ToolPolicy.TENANT_PROJECT_WRITE,
                project_id=project_id,
            )
            return await self._apply_validated_review(
                transaction,
                repository,
                validation,
                project_id=project_id,
                principal_id=principal_id,
                idempotency_key=idempotency_key,
                expected_project_revision=command.expected_project_revision,
                request_digest=request_digest,
                section="project_input_scope",
                outcome="scope_added",
                scope_addition=(principal, tenant_id, command.object_ids),
            )

    async def save_context(
        self,
        principal: RequestPrincipal,
        *,
        tenant_id: int,
        project_id: int,
        command: SaveContextGroupRequest | SaveContextRecordRequest,
        idempotency_key: UUID,
    ) -> ReviewProjectRecordsResult:
        request_digest = hashlib.sha256(
            json.dumps(
                {"operation": "save_context", **command.model_dump(mode="json")},
                sort_keys=True,
                separators=(",", ":"),
            ).encode()
        ).hexdigest()
        async with self._database.write_transaction() as transaction:
            repository, project, principal_id = await self._authorize_record_review(
                transaction, principal, tenant_id=tenant_id, project_id=project_id
            )
            replay = await repository.replay_review(
                project_id=project_id, principal_id=principal_id, correlation_id=idempotency_key
            )
            if replay is not None:
                metadata = replay["event_metadata"]
                if metadata.get("request_digest") != request_digest:
                    raise WorkbenchError("review_conflict", "This review key was already used.")
                return ReviewProjectRecordsResult(
                    project_id=project_id,
                    project_change_set_id=replay["project_change_set_id"],
                    project_revision=metadata["project_revision"],
                    action_count=replay["action_count"],
                )
            if project["project_revision"] != command.expected_project_revision:
                raise ProjectRevisionConflictError()
            if await repository.has_running_tenant_workflow(tenant_id=tenant_id):
                raise TenantWorkflowConflictError()
            context = ProjectReadContext(
                project_id=project_id,
                tenant_id=tenant_id,
                project_name=project["project_name"],
                project_revision=project["project_revision"],
                readable_source_tenant_ids=project["readable_source_tenant_ids"],
            )
            validation = await (
                prepare_context_group(transaction, context, command)
                if isinstance(command, SaveContextGroupRequest)
                else prepare_context_record(transaction, context, command)
            )
            await self._authorizer.authorize_tenant(
                transaction,
                principal,
                tenant_id=tenant_id,
                policy=ToolPolicy.TENANT_PROJECT_WRITE,
                project_id=project_id,
            )
            return await self._apply_validated_review(
                transaction,
                repository,
                validation,
                project_id=project_id,
                principal_id=principal_id,
                idempotency_key=idempotency_key,
                expected_project_revision=command.expected_project_revision,
                request_digest=request_digest,
                section="context",
                outcome="context_saved",
            )

    async def edit_record(
        self,
        principal: RequestPrincipal,
        *,
        tenant_id: int,
        project_id: int,
        command: ProjectRecordEditorRequest | SaveProjectRecordRequest,
        idempotency_key: UUID | None = None,
    ) -> ProjectRecordEditor | ReviewProjectRecordsResult:
        saving = isinstance(command, SaveProjectRecordRequest)
        if saving and idempotency_key is None:
            raise InvalidRequestError("An idempotency key is required to save.")
        request_digest = hashlib.sha256(
            json.dumps(
                {"operation": "edit_project_record", **command.model_dump()},
                sort_keys=True,
                separators=(",", ":"),
            ).encode()
        ).hexdigest()
        async with self._database.write_transaction() as transaction:
            repository, project, principal_id = await self._authorize_record_review(
                transaction,
                principal,
                tenant_id=tenant_id,
                project_id=project_id,
            )
            if saving and idempotency_key is not None:
                replay = await repository.replay_review(
                    project_id=project_id,
                    principal_id=principal_id,
                    correlation_id=idempotency_key,
                )
                if replay is not None:
                    metadata = replay["event_metadata"]
                    if metadata.get("request_digest") != request_digest:
                        raise WorkbenchError("review_conflict", "This review key was already used.")
                    return ReviewProjectRecordsResult(
                        project_id=project_id,
                        project_change_set_id=replay["project_change_set_id"],
                        project_revision=metadata["project_revision"],
                        action_count=replay["action_count"],
                    )
            if project["project_revision"] != command.expected_project_revision:
                raise ProjectRevisionConflictError()
            if await repository.has_running_tenant_workflow(tenant_id=tenant_id):
                raise TenantWorkflowConflictError()
            context = ProjectReadContext(
                project_id=project_id,
                tenant_id=tenant_id,
                project_name=project["project_name"],
                project_revision=project["project_revision"],
                readable_source_tenant_ids=project["readable_source_tenant_ids"],
            )
            review = await read_project_review_snapshot(
                transaction, context, enforce_row_limits=False
            )
            if command.dataset == "mapping_object":
                if command.mapping_target is not None:
                    target = command.mapping_target
                    selected = await transaction.fetch_one(
                        NEW_MAPPING_TARGET_SQL,
                        (
                            target.source_system_id,
                            project_id,
                            target.entity_id,
                            target.entity_type,
                        ),
                    )
                    if selected is None:
                        raise InvalidRequestError("Choose an eligible unmapped Entity and System.")
                    # Draft-only identity. The materializer generates the persisted ID.
                    review.records_by_id.setdefault("mapping_object", {})[0] = MappingObjectRecord(
                        modeled_entity_type=target.entity_type,
                        modeled_entity_schema_name=selected["modeled_entity_schema_name"],
                        modeled_entity_name=selected["modeled_entity_name"],
                        source_system_code=selected["system_code"],
                        object_dependency_order=selected["dependency_order"],
                        mapping_transformation_document=None,
                        output_template_code=None,
                        object_mapping_status="active",
                        object_mapping_is_locked=False,
                    )
                    anchor = {
                        "entity_id": target.entity_id,
                        "modeled_entity_type": target.entity_type,
                        "source_system_id": target.source_system_id,
                    }
                else:
                    anchor = await transaction.fetch_one(
                        "SELECT source_system_id, modeled_entity_type, "
                        "coalesce(logical_entity_id, dimensional_entity_id) AS entity_id "
                        "FROM workflow.mapping_object WHERE project_id = %s "
                        "AND mapping_object_id = %s",
                        (project_id, command.record_id),
                    )
                    if anchor is None:
                        raise WorkbenchError(
                            "project_record_not_found", "This Mapping is unavailable."
                        )
                sources = await transaction.fetch_all(
                    MAPPING_INPUT_SCOPE_SQL
                    if anchor["modeled_entity_type"] == "logical_entity"
                    else MAPPING_SOURCE_CONTEXT_SQL,
                    (project_id, anchor["source_system_id"])
                    if anchor["modeled_entity_type"] == "logical_entity"
                    else (
                        project_id,
                        anchor["entity_id"],
                        anchor["modeled_entity_type"],
                        anchor["source_system_id"],
                    ),
                )
                if (
                    len(sources) > 200
                    or sum(len(row["source"]["object"]["attributes"]) for row in sources) > 5000
                ):
                    raise InvalidRequestError(
                        "Mapping editing supports up to 200 source tables and 5,000 source columns."
                    )
                editor = mapping_record_editor(review, command, sources)
                if not isinstance(command, SaveProjectRecordRequest):
                    return editor
                validation = prepare_mapping_edit(
                    review, command, editor, await load_project_physical_scope(transaction, context)
                )
            else:
                if not isinstance(command, SaveProjectRecordRequest):
                    return project_record_editor(review, command)
                validation = prepare_project_record_edit(
                    review, command, await load_project_physical_scope(transaction, context)
                )
            await self._authorizer.authorize_tenant(
                transaction,
                principal,
                tenant_id=tenant_id,
                policy=ToolPolicy.TENANT_PROJECT_WRITE,
                project_id=project_id,
            )
            assert idempotency_key is not None
            return await self._apply_validated_review(
                transaction,
                repository,
                validation,
                project_id=project_id,
                principal_id=principal_id,
                idempotency_key=idempotency_key,
                expected_project_revision=command.expected_project_revision,
                request_digest=request_digest,
                section=DATASETS_BY_NAME[command.dataset].section,
                outcome="record_edited",
            )

    async def _apply_validated_review(
        self,
        transaction: WriteTransaction,
        repository: PostgresProjectChangeSetRepository,
        validation: ValidatedProjectChangeSet,
        *,
        project_id: int,
        principal_id: int,
        idempotency_key: UUID,
        expected_project_revision: int,
        request_digest: str,
        section: str,
        outcome: str,
        scope_addition: tuple[RequestPrincipal, int, list[int]] | None = None,
        layer: str | None = None,
    ) -> ReviewProjectRecordsResult:
        """Persist a validated Scope command within its authorization transaction."""
        change_set_id = uuid4()
        row = await repository.create(
            change_set_id=change_set_id,
            project_id=project_id,
            workflow_run_id=None,
            principal_id=principal_id,
            correlation_id=idempotency_key,
        )
        if row is None:
            raise ProjectNotFoundError()
        documents = project_change_set_documents(row)
        for dataset, records in validation.records.items():
            documents[DATASETS_BY_NAME[dataset].section][dataset] = [
                record.model_dump(mode="json") for record in records
            ]
        validate_project_change_set_document_bounds(documents)
        staged = await repository.stage_documents(documents=documents, change_set_id=change_set_id)
        if staged is None:
            raise ProjectChangeSetNotFoundError()
        await repository.record_validation(
            change_set_id=change_set_id,
            status="validated",
            valid=True,
            candidate_digest=validation.candidate_digest,
            outcome=project_validation_outcome(validation),
        )
        if scope_addition is None:
            action_count = await ProjectMaterializer(
                transaction=transaction,
                project_id=project_id,
                source_context_digest=row["base_source_context_digest"],
            ).apply(validation.records)
        else:
            actor, tenant_id, object_ids = scope_addition
            result = await transaction.fetch_one(
                "SELECT application.add_project_input_scope_objects(%s,%s,%s,%s,%s,%s) AS count",
                (
                    actor.entra_tenant_id,
                    actor.entra_object_id,
                    tenant_id,
                    project_id,
                    expected_project_revision,
                    object_ids,
                ),
            )
            if result is None:
                raise DependencyUnavailableError()
            action_count = result["count"]
        revision = await repository.advance_project_revision(
            project_id=project_id,
            expected_project_revision=expected_project_revision,
            changed=action_count > 0,
        )
        if revision is None:
            raise ProjectRevisionConflictError()
        await repository.mark_applied(change_set_id=change_set_id)
        for event_type in ("created", "section_put", "validated", "applied"):
            await repository.insert_event(
                change_set_id=change_set_id,
                project_id=project_id,
                event_type=event_type,
                draft_revision=1 if event_type == "created" else staged["draft_revision"],
                section=section,
                action_count=action_count,
                outcome=outcome if event_type == "applied" else section,
                metadata={
                    "request_digest": request_digest,
                    "project_revision": revision["project_revision"],
                    **({"layer": layer} if layer is not None else {}),
                },
                correlation_id=idempotency_key,
            )
        return ReviewProjectRecordsResult(
            project_id=project_id,
            project_change_set_id=change_set_id,
            project_revision=revision["project_revision"],
            action_count=action_count,
        )

    async def review_records(
        self,
        principal: RequestPrincipal,
        *,
        tenant_id: int,
        project_id: int,
        command: ReviewProjectRecordsRequest,
        idempotency_key: UUID,
    ) -> ReviewProjectRecordsResult:
        """Apply a human's exact lifecycle decision, preserving authored content."""
        if command.action == "delete":
            result = await self.delete_records(
                principal,
                tenant_id=tenant_id,
                project_id=project_id,
                command=command,
                idempotency_key=idempotency_key,
            )
            assert isinstance(result, ReviewProjectRecordsResult)
            return result
        request_digest = hashlib.sha256(
            json.dumps(
                {**command.model_dump(exclude_none=True), "record_ids": sorted(command.record_ids)},
                sort_keys=True,
                separators=(",", ":"),
            ).encode()
        ).hexdigest()
        async with self._database.write_transaction() as transaction:
            repository, project, principal_id = await self._authorize_record_review(
                transaction, principal, tenant_id=tenant_id, project_id=project_id
            )
            replay = await repository.replay_review(
                project_id=project_id, principal_id=principal_id, correlation_id=idempotency_key
            )
            if replay is not None:
                metadata = replay["event_metadata"]
                if metadata.get("request_digest") != request_digest:
                    raise WorkbenchError("review_conflict", "This review key was already used.")
                return ReviewProjectRecordsResult(
                    project_id=project_id,
                    project_change_set_id=replay["project_change_set_id"],
                    project_revision=metadata["project_revision"],
                    action_count=replay["action_count"],
                )
            if project["project_revision"] != command.expected_project_revision:
                raise ProjectRevisionConflictError()
            if await repository.has_running_tenant_workflow(tenant_id=tenant_id):
                raise TenantWorkflowConflictError()
            project_context = ProjectReadContext(
                project_id=project_id,
                tenant_id=tenant_id,
                project_name=project["project_name"],
                project_revision=project["project_revision"],
                readable_source_tenant_ids=project["readable_source_tenant_ids"],
            )
            changed_rows: list[tuple[str, int | str, bool, str]] = []
            if command.dataset != "analysis_result":
                review = await read_project_review_snapshot(
                    transaction, project_context, enforce_row_limits=False
                )
                snapshot = review.snapshot
                prepared = prepare_project_record_review(
                    review,
                    physical_scope=await load_project_physical_scope(transaction, project_context),
                    dataset=command.dataset,
                    record_ids=command.record_ids,
                    action=command.action,
                    layer=command.layer,
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
                if command.expected_plan_digest is None and (
                    command.layer is not None
                    or any(
                        not item.selected and item.original != item.reviewed
                        for item in prepared.decisions
                    )
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
                    project_id=project_id, record_ids=cast(list[int], command.record_ids)
                )
                if len(rows) != len(command.record_ids):
                    raise WorkbenchError(
                        "project_record_not_found", "A selected record is unavailable."
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
                snapshot = await build_project_snapshot(
                    transaction, project_context, enforce_row_limits=False
                )
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
                    physical_scope=await load_project_physical_scope(transaction, project_context),
                )
            if not validation.valid or validation.candidate_digest is None:
                raise WorkbenchError(
                    "review_conflict",
                    "The review conflicts with the current Project. Refresh and retry.",
                )
            validation = replace(
                validation,
                action_review=build_project_action_review(
                    project_snapshot_records(snapshot), validation.records
                ),
            )
            # Row locks cannot stop a lease expiring during complete-graph validation.
            authorization = await self._authorizer.authorize_tenant(
                transaction,
                principal,
                tenant_id=tenant_id,
                policy=ToolPolicy.TENANT_PROJECT_WRITE,
                project_id=project_id,
            )
            if authorization.principal.principal_id != principal_id:
                raise AuthorizationDeniedError()
            change_set_id = uuid4()
            row = await repository.create(
                change_set_id=change_set_id,
                project_id=project_id,
                workflow_run_id=None,
                principal_id=principal_id,
                correlation_id=idempotency_key,
            )
            if row is None:
                raise ProjectNotFoundError()
            documents = project_change_set_documents(row)
            for dataset, reviewed_records in validation.records.items():
                documents[DATASETS_BY_NAME[dataset].section][dataset] = [
                    record.model_dump(mode="json") for record in reviewed_records
                ]
            validate_project_change_set_document_bounds(documents)
            staged = await repository.stage_documents(
                documents=documents, change_set_id=change_set_id
            )
            if staged is None:
                raise ProjectChangeSetNotFoundError()
            await repository.record_validation(
                change_set_id=change_set_id,
                status="validated",
                candidate_digest=validation.candidate_digest,
                valid=True,
                outcome=project_validation_outcome(validation),
            )
            for dataset, record_id, locked, status in changed_rows:
                updated = await repository.apply_record_review(
                    dataset=dataset,
                    project_id=project_id,
                    record_id=record_id,
                    locked=locked,
                    status=status,
                    actor=f"principal:{principal_id}",
                )
                if updated is None:
                    raise WorkbenchError(
                        "project_record_not_found", "A selected record is unavailable."
                    )
            revision = await repository.advance_project_revision(
                project_id=project_id,
                expected_project_revision=command.expected_project_revision,
                changed=bool(changed_rows),
            )
            if revision is None:
                raise ProjectRevisionConflictError()
            await repository.mark_applied(change_set_id=change_set_id)
            for event_type in ("created", "section_put", "validated", "applied"):
                await repository.insert_event(
                    change_set_id=change_set_id,
                    project_id=project_id,
                    event_type=event_type,
                    draft_revision=1 if event_type == "created" else staged["draft_revision"],
                    section=DATASETS_BY_NAME[command.dataset].section,
                    action_count=len(changed_rows),
                    outcome="review_applied" if event_type == "applied" else "review",
                    metadata={
                        "action": command.action,
                        "dataset": command.dataset,
                        "request_digest": request_digest,
                        "project_revision": revision["project_revision"],
                    },
                    correlation_id=idempotency_key,
                )
        return ReviewProjectRecordsResult(
            project_id=project_id,
            project_change_set_id=change_set_id,
            project_revision=revision["project_revision"],
            action_count=len(changed_rows),
        )

    async def preview_record_review(
        self,
        principal: RequestPrincipal,
        *,
        tenant_id: int,
        project_id: int,
        command: PreviewProjectRecordsRequest,
        page: int = 1,
    ) -> PreviewProjectRecordsResult:
        if command.action == "delete":
            result = await self.delete_records(
                principal, tenant_id=tenant_id, project_id=project_id, command=command, page=page
            )
            assert isinstance(result, PreviewProjectRecordsResult)
            return result
        async with self._database.write_transaction() as transaction:
            repository, project, _ = await self._authorize_record_review(
                transaction, principal, tenant_id=tenant_id, project_id=project_id
            )
            if project["project_revision"] != command.expected_project_revision:
                raise ProjectRevisionConflictError()
            if await repository.has_running_tenant_workflow(tenant_id=tenant_id):
                raise TenantWorkflowConflictError()
            project_context = ProjectReadContext(
                project_id=project_id,
                tenant_id=tenant_id,
                project_name=project["project_name"],
                project_revision=project["project_revision"],
                readable_source_tenant_ids=project["readable_source_tenant_ids"],
            )
            review = await read_project_review_snapshot(
                transaction, project_context, enforce_row_limits=False
            )
            prepared = prepare_project_record_review(
                review,
                physical_scope=await load_project_physical_scope(transaction, project_context),
                dataset=command.dataset,
                record_ids=command.record_ids,
                action=command.action,
                layer=command.layer,
            )
            if (
                command.expected_plan_digest is not None
                and command.expected_plan_digest != prepared.plan_digest
            ):
                raise WorkbenchError("review_conflict", "The review changed. Refresh its preview.")
            count = len(prepared.decisions)
            if page < 1 or (page > 1 and (page - 1) * 200 >= count):
                raise InvalidRequestError("The review page is unavailable.")
            items: list[ProjectRecordReviewItem] = []
            for decision in prepared.decisions[(page - 1) * 200 : page * 200]:
                original = decision.original.model_dump()
                items.append(
                    ProjectRecordReviewItem(
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
            return PreviewProjectRecordsResult(
                project_id=project_id,
                project_revision=project["project_revision"],
                plan_digest=prepared.plan_digest,
                can_apply=prepared.validation.valid,
                action_count=sum(item.original != item.reviewed for item in prepared.decisions),
                additional_change_count=sum(
                    not item.selected and item.original != item.reviewed
                    for item in prepared.decisions
                ),
                total_record_count=count,
                changes_by_dataset=dict(
                    Counter(
                        item.dataset
                        for item in prepared.decisions
                        if item.original != item.reviewed
                    )
                ),
                warnings=(
                    (
                        "Conceptual records have no stored ownership link to Logical or "
                        "Dimensional entities; those layers remain unchanged.",
                    )
                    if command.dataset.startswith("conceptual_") and command.action == "deactivate"
                    else (
                        "Physical tables and registered metadata remain unchanged.",
                        "Validation checks are grouped by System, without target-object links. "
                        "A group is removed only when its System loses its last active mapping; "
                        "remaining checks need review after this change.",
                    )
                    if command.action == "deactivate"
                    else ()
                ),
                items=tuple(items),
                issues=tuple(
                    ProjectRecordReviewIssue(
                        code=issue.code, dataset=issue.dataset, message=issue.message
                    )
                    for issue in prepared.validation.issues[:20]
                ),
                issue_count=len(prepared.validation.issues),
                page=page,
                next_page=page + 1 if page * 200 < count else None,
            )

    async def delete_records(
        self,
        principal: RequestPrincipal,
        *,
        tenant_id: int,
        project_id: int,
        command: PreviewProjectRecordsRequest | ReviewProjectRecordsRequest,
        idempotency_key: UUID | None = None,
        page: int = 1,
    ) -> PreviewProjectRecordsResult | ReviewProjectRecordsResult:
        """Preview or atomically apply an administrator's confirmed deletion."""
        if command.action != "delete":
            raise InvalidRequestError("A delete action is required.")
        request_digest = hashlib.sha256(
            json.dumps(
                {**command.model_dump(exclude_none=True), "record_ids": sorted(command.record_ids)},
                sort_keys=True,
                separators=(",", ":"),
            ).encode()
        ).hexdigest()
        async with self._database.write_transaction() as transaction:
            repository, project, principal_id = await self._authorize_record_review(
                transaction, principal, tenant_id=tenant_id, project_id=project_id
            )
            authorization = await self._authorizer.authorize_tenant(
                transaction,
                principal,
                tenant_id=tenant_id,
                policy=ToolPolicy.TENANT_PROJECT_WRITE,
                project_id=project_id,
            )
            if authorization.effective_role not in {
                TenantRole.SUPER_ADMIN,
                TenantRole.TENANT_ADMIN,
            }:
                raise AuthorizationDeniedError()
            if idempotency_key is not None:
                replay = await repository.replay_review(
                    project_id=project_id, principal_id=principal_id, correlation_id=idempotency_key
                )
                if replay is not None:
                    metadata = replay["event_metadata"]
                    if metadata.get("request_digest") != request_digest:
                        raise WorkbenchError(
                            "review_conflict", "This deletion key was already used."
                        )
                    return ReviewProjectRecordsResult(
                        project_id=project_id,
                        project_change_set_id=replay["project_change_set_id"],
                        project_revision=metadata["project_revision"],
                        action_count=replay["action_count"],
                    )
            if project["project_revision"] != command.expected_project_revision:
                raise ProjectRevisionConflictError()
            if await repository.has_running_tenant_workflow(tenant_id=tenant_id):
                raise TenantWorkflowConflictError()
            context = ProjectReadContext(
                project_id=project_id,
                tenant_id=tenant_id,
                project_name=project["project_name"],
                project_revision=project["project_revision"],
                readable_source_tenant_ids=project["readable_source_tenant_ids"],
            )
            plan = await plan_project_deletion(
                transaction,
                await read_project_review_snapshot(transaction, context, enforce_row_limits=False),
                dataset=cast(ProjectReviewDataset, command.dataset),
                record_ids=cast(list[int], command.record_ids),
                layer=command.layer,
            )
            if (
                command.expected_plan_digest is not None
                and command.expected_plan_digest != plan.digest
            ):
                raise WorkbenchError(
                    "review_conflict", "The deletion plan changed. Preview it again."
                )
            locked = [item for item in plan.items if item.is_locked]
            if idempotency_key is None:
                count = len(plan.items)
                if page < 1 or (page > 1 and (page - 1) * 200 >= count):
                    raise InvalidRequestError("The deletion page is unavailable.")
                return PreviewProjectRecordsResult(
                    project_id=project_id,
                    project_revision=project["project_revision"],
                    plan_digest=plan.digest,
                    can_apply=not locked,
                    action_count=count,
                    additional_change_count=sum(not item.selected for item in plan.items),
                    total_record_count=count,
                    changes_by_dataset={name: len(ids) for name, ids in plan.records.items()},
                    warnings=(
                        "Physical tables, registered metadata, context records, "
                        "and workflow history are retained.",
                        *(
                            ("Conceptual deletion does not delete Logical or Dimensional records.",)
                            if command.dataset.startswith("conceptual_")
                            else (
                                "System-level validations are deleted only when their System loses "
                                "its last Mapping. Review remaining checks manually.",
                            )
                        ),
                    ),
                    items=tuple(
                        ProjectRecordReviewItem(
                            dataset=item.dataset,
                            record_id=item.record_id,
                            label=item.label,
                            selected=item.selected,
                            reason=item.reason,
                            is_locked=item.is_locked,
                            desired_locked=False,
                            status=cast(Any, item.status),
                            desired_status="deleted",
                            can_unlock=item.dataset in REVIEW_FIELDS,
                            changed=True,
                        )
                        for item in plan.items[(page - 1) * 200 : page * 200]
                    ),
                    issues=tuple(
                        ProjectRecordReviewIssue(
                            code="record_locked",
                            dataset=item.dataset,
                            message=f"Unlock {item.label} before deleting it.",
                        )
                        for item in locked[:20]
                    ),
                    issue_count=len(locked),
                    page=page,
                    next_page=page + 1 if page * 200 < count else None,
                )
            if command.expected_plan_digest is None:
                raise WorkbenchError(
                    "review_confirmation_required",
                    "Preview and confirm all affected records before deletion.",
                )
            if locked:
                raise WorkbenchError(
                    "record_locked", "Unlock selected and dependent records before deletion."
                )
            if not plan.items:
                raise WorkbenchError("review_conflict", "There are no records to delete.")
            change_set_id = uuid4()
            row = await repository.create(
                change_set_id=change_set_id,
                project_id=project_id,
                workflow_run_id=None,
                principal_id=principal_id,
                correlation_id=idempotency_key,
            )
            if row is None:
                raise ProjectNotFoundError()
            await repository.record_validation(
                change_set_id=change_set_id,
                status="validated",
                candidate_digest=plan.digest,
                valid=True,
                outcome={"valid": True, "delete_records": plan.records},
            )
            result = await transaction.fetch_one(
                "SELECT application.delete_project_records(%s, %s, %s, %s, %s, %s, %s) AS count",
                (
                    principal.entra_tenant_id,
                    principal.entra_object_id,
                    tenant_id,
                    project_id,
                    command.expected_project_revision,
                    change_set_id,
                    Jsonb(plan.records),
                ),
            )
            if result is None:
                raise DependencyUnavailableError()
            count = result["count"]
            if count != len(plan.items):
                raise WorkbenchError("review_conflict", "Deletion counts changed. Preview again.")
            revision = await repository.advance_project_revision(
                project_id=project_id,
                expected_project_revision=command.expected_project_revision,
                changed=True,
            )
            if revision is None:
                raise ProjectRevisionConflictError()
            await repository.mark_applied(change_set_id=change_set_id)
            for event_type in ("created", "validated", "applied"):
                await repository.insert_event(
                    change_set_id=change_set_id,
                    project_id=project_id,
                    event_type=event_type,
                    draft_revision=row["draft_revision"],
                    section=DATASETS_BY_NAME[command.dataset].section,
                    action_count=count,
                    outcome="records_deleted" if event_type == "applied" else "deletion",
                    metadata={
                        "action": "delete",
                        "dataset": command.dataset,
                        "request_digest": request_digest,
                        "plan_digest": plan.digest,
                        "project_revision": revision["project_revision"],
                        "changes_by_dataset": {
                            name: len(ids) for name, ids in plan.records.items()
                        },
                    },
                    correlation_id=idempotency_key,
                )
            return ReviewProjectRecordsResult(
                project_id=project_id,
                project_change_set_id=change_set_id,
                project_revision=revision["project_revision"],
                action_count=count,
            )

    async def _authorize_record_review(
        self,
        transaction: WriteTransaction,
        principal: RequestPrincipal,
        *,
        tenant_id: int,
        project_id: int,
    ) -> tuple[PostgresProjectChangeSetRepository, dict[str, Any], int]:
        if (
            principal.actor_kind is not ActorKind.HUMAN
            or principal.entra_tenant_id is None
            or principal.entra_object_id is None
        ):
            raise AuthorizationDeniedError()
        repository = PostgresProjectChangeSetRepository(transaction)
        # The governed helper locks Project then Tenant before write authorization.
        # Taking authorization's SHARE fence first would require a deadlocking upgrade.
        project = await repository.authorize_record_review(
            entra_tenant_id=principal.entra_tenant_id,
            entra_object_id=principal.entra_object_id,
            tenant_id=tenant_id,
            project_id=project_id,
        )
        if project is None:
            raise DependencyUnavailableError()
        denial = project["denial_code"]
        if denial is not None:
            errors: dict[str, WorkbenchError] = {
                "invalid_request": InvalidRequestError("The Project review request is invalid."),
                "authorization_denied": AuthorizationDeniedError(),
                "project_not_found": ProjectNotFoundError(),
                "tenant_not_found": ProjectNotFoundError(),
                "tenant_lock_required": TenantLockRequiredError(),
                "tenant_locked": TenantLockRequiredError(),
            }
            raise errors.get(denial, DependencyUnavailableError())
        principal_id = project["principal_id"]
        if (
            not isinstance(principal_id, int)
            or isinstance(principal_id, bool)
            or principal_id < 1
            or project["project_id"] != project_id
            or project["tenant_id"] != tenant_id
        ):
            raise DependencyUnavailableError()
        context = await authorize_project_read(
            transaction, authorizer=self._authorizer, principal=principal, project_id=project_id
        )
        project["readable_source_tenant_ids"] = context.readable_source_tenant_ids
        return repository, project, principal_id

    async def create_or_resume(
        self,
        principal: RequestPrincipal,
        *,
        tenant_id: int,
        project_id: int,
        command: CreateProjectChangeSetRequest,
        idempotency_key: UUID,
    ) -> CreateProjectChangeSetResult:
        async with self._database.write_transaction() as transaction:
            repository = PostgresProjectChangeSetRepository(transaction)
            project = await repository.get_project(tenant_id=tenant_id, project_id=project_id)
            if project is None:
                raise ProjectNotFoundError()
            if project["project_revision"] != command.expected_project_revision:
                raise ProjectRevisionConflictError()
            authorization = await self._authorizer.authorize_tenant(
                transaction,
                principal,
                tenant_id=tenant_id,
                policy=ToolPolicy.TENANT_PROJECT_WRITE,
                project_id=project_id,
            )
            principal_id = authorization.principal.principal_id
            if principal_id is None:
                raise AuthorizationDeniedError()

            expired = await repository.expire_owned(
                project_id=project_id,
                principal_id=principal_id,
            )
            for expired_row in expired:
                await repository.insert_event(
                    change_set_id=expired_row["project_change_set_id"],
                    project_id=project_id,
                    event_type="expired",
                    draft_revision=expired_row["draft_revision"],
                    section=None,
                    action_count=0,
                    outcome="expired",
                    metadata={},
                    correlation_id=uuid4(),
                )

            row = await repository.find_ongoing(
                project_id=project_id,
                principal_id=principal_id,
            )
            created = row is None
            if row is None:
                change_set_id = uuid4()
                row = await repository.create(
                    change_set_id=change_set_id,
                    project_id=project_id,
                    workflow_run_id=None,
                    principal_id=principal_id,
                    correlation_id=idempotency_key,
                )
                if row is None:
                    raise ProjectNotFoundError()
                await repository.insert_event(
                    change_set_id=row["project_change_set_id"],
                    project_id=project_id,
                    event_type="created",
                    draft_revision=row["draft_revision"],
                    section=None,
                    action_count=0,
                    outcome="created",
                    metadata={},
                    correlation_id=idempotency_key,
                )

        return CreateProjectChangeSetResult(
            project_id=project_id,
            project_change_set_id=row["project_change_set_id"],
            created=created,
            status=row["project_change_set_status"],
            draft_revision=row["draft_revision"],
            created_at=require_datetime(row, "created_time"),
            expires_at=require_datetime(row, "expires_time"),
        )

    async def stage(
        self,
        principal: RequestPrincipal,
        *,
        tenant_id: int,
        project_id: int,
        change_set_id: UUID,
        command: StageProjectChangeSetRequest,
        idempotency_key: UUID,
    ) -> StageProjectChangeSetResult:
        self._require_web_stage_datasets(change.dataset for change in command.changes)
        staged = validate_project_stage_changes(command.changes)
        async with self._database.write_transaction() as transaction:
            repository, _project, authorization = await self._authorize_project(
                transaction,
                principal,
                tenant_id=tenant_id,
                project_id=project_id,
                policy=ToolPolicy.TENANT_PROJECT_WRITE,
            )
            row = await self._owned_change_set(
                repository,
                change_set_id=change_set_id,
                project_id=project_id,
                principal_id=authorization.principal.principal_id,
                for_update=True,
            )
            require_mutable_project_change_set(row)
            self._require_draft_revision(row, command.expected_draft_revision)
            documents = project_change_set_documents(row)
            for dataset, records in staged.items():
                section = DATASETS_BY_NAME[dataset].section
                documents[section][dataset] = records
            validate_project_change_set_document_bounds(documents)
            updated = await repository.stage_documents(
                documents=documents,
                change_set_id=change_set_id,
            )
            if updated is None:
                raise ProjectChangeSetNotFoundError()
            sections = sorted({DATASETS_BY_NAME[name].section for name in staged})
            await repository.insert_event(
                change_set_id=change_set_id,
                project_id=project_id,
                event_type="section_put",
                draft_revision=updated["draft_revision"],
                section=sections[0] if len(sections) == 1 else None,
                action_count=sum(len(records) for records in staged.values()),
                outcome="staged",
                metadata={"datasets": sorted(staged)},
                correlation_id=idempotency_key,
            )
        return StageProjectChangeSetResult(
            project_id=project_id,
            project_change_set_id=change_set_id,
            datasets=tuple(
                ProjectChangeSetDatasetCount(
                    dataset=cast(ProjectChangeSetDataset, dataset),
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
        project_id: int,
        change_set_id: UUID,
        command: BeginProjectStageBatchRequest,
        idempotency_key: UUID,
    ) -> BeginProjectStageBatchResult:
        self._require_web_stage_datasets((command.dataset,))
        async with self._database.write_transaction() as transaction:
            repository, _project, authorization = await self._authorize_project(
                transaction,
                principal,
                tenant_id=tenant_id,
                project_id=project_id,
                policy=ToolPolicy.TENANT_PROJECT_WRITE,
            )
            principal_id = authorization.principal.principal_id
            if principal_id is None:
                raise AuthorizationDeniedError()
            change_set = await self._owned_change_set(
                repository,
                change_set_id=change_set_id,
                project_id=project_id,
                principal_id=principal_id,
                for_update=True,
            )
            require_mutable_project_change_set(change_set)
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
                        project_id,
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
                    raise ProjectChangeSetNotFoundError()
        return BeginProjectStageBatchResult(
            project_id=project_id,
            project_change_set_id=change_set_id,
            stage_batch_id=row["stage_batch_id"],
            dataset=cast(ProjectChangeSetDataset, row["dataset_name"]),
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
        project_id: int,
        change_set_id: UUID,
        stage_batch_id: UUID,
        chunk_index: int,
        command: PutProjectStageChunkRequest,
        idempotency_key: UUID,
    ) -> PutProjectStageChunkResult:
        del idempotency_key
        self._require_web_stage_datasets((command.dataset,))
        normalized: list[dict[str, object]] = []
        payload_fragment: bytes | None = None
        if command.payload_mode == "records":
            assert command.records is not None
            normalized = validate_project_stage_changes(
                [StageProjectChange(dataset=command.dataset, records=command.records)]
            )[command.dataset]
            if len(canonical_records_bytes(normalized)) > MAX_PROJECT_STAGE_CHUNK_BYTES:
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
            repository, _project, authorization = await self._authorize_project(
                transaction,
                principal,
                tenant_id=tenant_id,
                project_id=project_id,
                policy=ToolPolicy.TENANT_PROJECT_WRITE,
            )
            change_set = await self._owned_change_set(
                repository,
                change_set_id=change_set_id,
                project_id=project_id,
                principal_id=authorization.principal.principal_id,
                for_update=True,
            )
            require_mutable_project_change_set(change_set)
            batch = await repository.get_stage_batch(
                stage_batch_id=stage_batch_id,
                change_set_id=change_set_id,
                project_id=project_id,
            )
            require_project_stage_batch(batch, authorization.principal, command.dataset)
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
        return PutProjectStageChunkResult(
            project_id=project_id,
            project_change_set_id=change_set_id,
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
        project_id: int,
        change_set_id: UUID,
        stage_batch_id: UUID,
        command: ExpectedDraftRevisionRequest,
        idempotency_key: UUID,
    ) -> CommitProjectStageBatchResult:
        async with self._database.write_transaction() as transaction:
            repository, _project, authorization = await self._authorize_project(
                transaction,
                principal,
                tenant_id=tenant_id,
                project_id=project_id,
                policy=ToolPolicy.TENANT_PROJECT_WRITE,
            )
            change_set = await self._owned_change_set(
                repository,
                change_set_id=change_set_id,
                project_id=project_id,
                principal_id=authorization.principal.principal_id,
                for_update=True,
            )
            batch = await repository.get_stage_batch(
                stage_batch_id=stage_batch_id,
                change_set_id=change_set_id,
                project_id=project_id,
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
                require_project_stage_batch(batch, authorization.principal, None)
                require_mutable_project_change_set(change_set)
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
                    assembled = decode_canonical_project_stage_payload(
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
                dataset = cast(ProjectChangeSetDataset, batch["dataset_name"])
                staged = validate_project_stage_changes(
                    [StageProjectChange(dataset=dataset, records=assembled)]
                )
                if (
                    payload_mode == "json_fragments"
                    and payload is not None
                    and canonical_records_bytes(staged[dataset]) != payload
                ):
                    raise InvalidRequestError("The Stage payload is not canonical normalized JSON.")
                documents = project_change_set_documents(change_set)
                section = DATASETS_BY_NAME[dataset].section
                documents[section][dataset] = staged[dataset]
                validate_project_change_set_document_bounds(documents)
                updated = await repository.stage_documents(
                    documents=documents,
                    change_set_id=change_set_id,
                )
                if updated is None:
                    raise ProjectChangeSetNotFoundError()
                await repository.insert_event(
                    change_set_id=change_set_id,
                    project_id=project_id,
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
        return CommitProjectStageBatchResult(
            project_id=project_id,
            project_change_set_id=change_set_id,
            stage_batch_id=stage_batch_id,
            dataset=cast(ProjectChangeSetDataset, batch["dataset_name"]),
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
        project_id: int,
        change_set_id: UUID,
        dataset: ProjectDataset | None,
    ) -> GetProjectChangeSetResult:
        async with self._database.write_transaction() as transaction:
            repository, _project, authorization = await self._authorize_project(
                transaction,
                principal,
                tenant_id=tenant_id,
                project_id=project_id,
                policy=ToolPolicy.TENANT_READ,
            )
            row = await self._owned_change_set(
                repository,
                change_set_id=change_set_id,
                project_id=project_id,
                principal_id=authorization.principal.principal_id,
                for_update=False,
            )
        pending = pending_project_change_set_datasets(row)
        return GetProjectChangeSetResult(
            project_id=project_id,
            project_change_set_id=change_set_id,
            status=row["project_change_set_status"],
            draft_revision=row["draft_revision"],
            candidate_digest=row["candidate_digest"],
            validation_outcome=bounded_validation_outcome(row["validation_outcome"]),
            dataset_counts=tuple(
                ProjectDatasetCount(
                    dataset=cast(ProjectDataset, name),
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
        project_id: int,
        change_set_id: UUID,
        command: ExpectedDraftRevisionRequest,
        idempotency_key: UUID,
    ) -> ValidateProjectChangeSetResult:
        async with self._database.write_transaction() as transaction:
            repository, project, authorization = await self._authorize_project(
                transaction,
                principal,
                tenant_id=tenant_id,
                project_id=project_id,
                policy=ToolPolicy.TENANT_PROJECT_WRITE,
            )
            row = await self._owned_change_set(
                repository,
                change_set_id=change_set_id,
                project_id=project_id,
                principal_id=authorization.principal.principal_id,
                for_update=True,
            )
            require_mutable_project_change_set(row)
            self._require_draft_revision(row, command.expected_draft_revision)
            self._require_web_writable_pending(row)
            validation = await validate_locked_project_change_set(
                transaction, project, row, enforce_row_limits=False
            )
            updated = await repository.record_validation(
                change_set_id=change_set_id,
                status="validated" if validation.valid else "active",
                candidate_digest=(validation.candidate_digest if validation.valid else None),
                outcome=project_validation_outcome(validation),
                valid=validation.valid,
            )
            if updated is None:
                raise ProjectChangeSetNotFoundError()
            await repository.insert_event(
                change_set_id=change_set_id,
                project_id=project_id,
                event_type="validated" if validation.valid else "validation_failed",
                draft_revision=row["draft_revision"],
                section=None,
                action_count=sum(len(records) for records in validation.records.values()),
                outcome="valid" if validation.valid else "invalid",
                metadata={"phase": validation.phase, "error_count": len(validation.issues)},
                correlation_id=idempotency_key,
            )
        return ValidateProjectChangeSetResult(
            project_id=project_id,
            project_change_set_id=change_set_id,
            valid=validation.valid,
            phase=validation.phase,
            status=updated["project_change_set_status"],
            draft_revision=updated["draft_revision"],
            candidate_digest=updated["candidate_digest"],
            staged_record_count=sum(len(records) for records in validation.records.values()),
            error_count=len(validation.issues),
            error_groups=project_validation_error_groups(validation),
            errors=tuple(
                project_validation_error(issue)
                for issue in validation.issues[:MAX_AGENT_VALIDATION_ERROR_EXAMPLES]
            ),
            errors_truncated=(len(validation.issues) > MAX_AGENT_VALIDATION_ERROR_EXAMPLES),
            action_review=project_action_review(validation.action_review),
            validated_at=self._optional_datetime(updated, "validated_time"),
            expires_at=require_datetime(updated, "expires_time"),
        )

    async def apply(
        self,
        principal: RequestPrincipal,
        *,
        tenant_id: int,
        project_id: int,
        change_set_id: UUID,
        command: ExpectedDraftRevisionRequest,
        idempotency_key: UUID,
    ) -> ApplyProjectChangeSetResult:
        async with self._database.write_transaction() as transaction:
            repository, project, authorization = await self._authorize_project(
                transaction,
                principal,
                tenant_id=tenant_id,
                project_id=project_id,
                policy=ToolPolicy.TENANT_PROJECT_WRITE,
            )
            row = await self._owned_change_set(
                repository,
                change_set_id=change_set_id,
                project_id=project_id,
                principal_id=authorization.principal.principal_id,
                for_update=True,
            )
            if row["project_change_set_status"] != "validated":
                raise ProjectChangeSetNotValidatedError()
            self._require_draft_revision(row, command.expected_draft_revision)
            self._require_web_writable_pending(row)
            validation = await validate_locked_project_change_set(
                transaction, project, row, enforce_row_limits=False
            )
            if not validation.valid or validation.candidate_digest is None:
                raise CandidateDigestConflictError()
            if validation.candidate_digest != row["candidate_digest"]:
                raise CandidateDigestConflictError()
            materializer = ProjectMaterializer(
                transaction=transaction,
                project_id=project_id,
                source_context_digest=row["base_source_context_digest"],
                readable_source_tenant_ids=project.readable_source_tenant_ids,
                change_set_id=change_set_id,
                request_principal=principal,
                draft_revision=command.expected_draft_revision,
                candidate_digest=validation.candidate_digest,
            )
            action_count = await materializer.apply(validation.records)
            revision = await repository.advance_project_revision(
                project_id=project_id,
                expected_project_revision=project.project_revision,
                changed=action_count > 0,
            )
            if revision is None:
                raise InvalidRequestError("Project revision changed during apply.")
            applied = await repository.mark_applied(change_set_id=change_set_id)
            if applied is None:
                raise ProjectChangeSetNotFoundError()
            await repository.insert_event(
                change_set_id=change_set_id,
                project_id=project_id,
                event_type="applied",
                draft_revision=row["draft_revision"],
                section=None,
                action_count=action_count,
                outcome="applied",
                metadata={"project_revision": revision["project_revision"]},
                correlation_id=idempotency_key,
            )
        return ApplyProjectChangeSetResult(
            project_id=project_id,
            project_change_set_id=change_set_id,
            draft_revision=row["draft_revision"],
            candidate_digest=validation.candidate_digest,
            action_count=action_count,
            project_revision=revision["project_revision"],
            applied_at=require_datetime(applied, "applied_time"),
        )

    async def archive(
        self,
        principal: RequestPrincipal,
        *,
        tenant_id: int,
        project_id: int,
        change_set_id: UUID,
        command: ExpectedDraftRevisionRequest,
        idempotency_key: UUID,
    ) -> ArchiveProjectChangeSetResult:
        async with self._database.write_transaction() as transaction:
            repository, _project, authorization = await self._authorize_project(
                transaction,
                principal,
                tenant_id=tenant_id,
                project_id=project_id,
                policy=ToolPolicy.TENANT_READ,
            )
            row = await self._owned_change_set(
                repository,
                change_set_id=change_set_id,
                project_id=project_id,
                principal_id=authorization.principal.principal_id,
                for_update=True,
            )
            require_mutable_project_change_set(row)
            self._require_draft_revision(row, command.expected_draft_revision)
            archived = await repository.archive(
                change_set_id=change_set_id,
                project_id=project_id,
            )
            if archived is None:
                raise ProjectChangeSetNotActiveError()
            await repository.insert_event(
                change_set_id=change_set_id,
                project_id=project_id,
                event_type="discarded",
                draft_revision=archived["draft_revision"],
                section=None,
                action_count=0,
                outcome="archived",
                metadata={},
                correlation_id=idempotency_key,
            )
        return ArchiveProjectChangeSetResult(
            project_id=project_id,
            project_change_set_id=change_set_id,
            draft_revision=archived["draft_revision"],
            archived_at=require_datetime(archived, "terminal_time"),
        )

    async def _authorize_project(
        self,
        transaction: WriteTransaction,
        principal: RequestPrincipal,
        *,
        tenant_id: int,
        project_id: int,
        policy: ToolPolicy,
    ) -> tuple[
        PostgresProjectChangeSetRepository,
        ProjectReadContext,
        TenantAuthorization,
    ]:
        repository = PostgresProjectChangeSetRepository(transaction)
        row = await repository.get_project(tenant_id=tenant_id, project_id=project_id)
        if row is None:
            raise ProjectNotFoundError()
        authorization = await self._authorizer.authorize_tenant(
            transaction,
            principal,
            tenant_id=tenant_id,
            policy=policy,
            project_id=project_id,
        )
        source_tenants = authorization.readable_source_tenant_ids
        return (
            repository,
            ProjectReadContext(
                project_id=row["project_id"],
                tenant_id=row["tenant_id"],
                project_name=row["project_name"],
                project_revision=row["project_revision"],
                readable_source_tenant_ids=source_tenants,
            ),
            authorization,
        )

    @staticmethod
    async def _owned_change_set(
        repository: PostgresProjectChangeSetRepository,
        *,
        change_set_id: UUID,
        project_id: int,
        principal_id: int | None,
        for_update: bool,
    ) -> dict[str, Any]:
        row = await repository.get_change_set(
            change_set_id=change_set_id,
            project_id=project_id,
            for_update=for_update,
        )
        if row is None or row["created_by_principal_id"] != principal_id:
            raise ProjectChangeSetNotFoundError()
        return row

    @staticmethod
    def _require_draft_revision(row: Mapping[str, object], expected: int) -> None:
        current = row["draft_revision"]
        if current != expected:
            if not isinstance(current, int):
                raise ProjectChangeSetNotFoundError()
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
            if dataset == "project_input_scope":
                raise InvalidRequestError(
                    "Project Input Scope must use the governed Project Input Scope command."
                )
            if dataset == "profiling_profile":
                raise InvalidRequestError(
                    "Profiling results must use the governed Profiling persistence command."
                )

    @classmethod
    def _require_web_writable_pending(cls, row: Mapping[str, object]) -> None:
        require_mcp_writable_pending(row)
        cls._require_web_stage_datasets(pending_project_change_set_datasets(row))
