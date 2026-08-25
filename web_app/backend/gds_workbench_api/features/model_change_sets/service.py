"""Governed Model Change Set application service."""

import json
from collections.abc import Iterable, Mapping
from contextlib import AbstractAsyncContextManager
from datetime import datetime
from typing import Any, Protocol, cast
from uuid import UUID, uuid4

from gds_etl_workbench.application.authorization import (
    AuthorizationService,
    TenantAuthorization,
)
from gds_etl_workbench.domain.authorization import RequestPrincipal, ToolPolicy
from gds_etl_workbench.domain.errors import (
    AuthorizationDeniedError,
    CandidateDigestConflictError,
    DraftRevisionConflictError,
    InvalidRequestError,
    ModelChangeSetNotActiveError,
    ModelChangeSetNotFoundError,
    ModelChangeSetNotValidatedError,
    StageBatchConflictError,
    StageBatchIncompleteError,
    StageBatchNotFoundError,
    StageChunkConflictError,
)
from gds_etl_workbench.infrastructure.postgres import WriteTransaction
from gds_etl_workbench.tools.change_sets.common import (
    MAX_STAGE_CHUNK_BYTES,
    canonical_records_sha256,
    stage_batch_sha256,
)
from gds_etl_workbench.tools.change_sets.model import (
    ModelChangeSetDatasetCount,
    ModelDatasetCount,
    StageModelChange,
    model_action_review,
    model_change_set_documents,
    model_validation_error,
    model_validation_outcome,
    pending_model_change_set_datasets,
    require_mcp_writable_pending,
    require_model_stage_batch,
    require_mutable_model_change_set,
    validate_locked_model_change_set,
    validate_model_change_set_document_bounds,
    validate_model_stage_changes,
)
from gds_etl_workbench.tools.change_sets.model_apply import ModelMaterializer
from gds_etl_workbench.tools.modeling.common import ModelReadContext
from gds_etl_workbench.tools.snapshots.model.contracts import (
    DATASETS_BY_NAME,
    ModelChangeSetDataset,
    ModelDataset,
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
    PutModelStageChunkRequest,
    PutModelStageChunkResult,
    StageModelChangeSetRequest,
    StageModelChangeSetResult,
    ValidateModelChangeSetResult,
)
from .repository import PostgresModelChangeSetRepository, require_datetime


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
        normalized = validate_model_stage_changes(
            [StageModelChange(dataset=command.dataset, records=command.records)]
        )[command.dataset]
        encoded = json.dumps(
            normalized,
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        ).encode()
        if len(encoded) > MAX_STAGE_CHUNK_BYTES:
            raise InvalidRequestError("The Stage chunk exceeds the bounded byte limit.")
        if canonical_records_sha256(normalized) != command.chunk_sha256:
            raise InvalidRequestError(
                "The Stage chunk SHA-256 does not match its normalized records."
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
            if chunk_index > batch["total_chunk_count"]:
                raise InvalidRequestError("Chunk index exceeds the Stage Batch manifest.")
            existing = await repository.get_stage_chunk(
                stage_batch_id=stage_batch_id,
                chunk_index=chunk_index,
            )
            duplicate = existing is not None
            if existing is not None:
                if (
                    existing["chunk_sha256"] != command.chunk_sha256
                    or existing["records_document"] != normalized
                ):
                    raise StageChunkConflictError()
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
            totals = await repository.stage_chunk_totals(stage_batch_id=stage_batch_id)
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
                chunks = await repository.get_stage_chunks(stage_batch_id=stage_batch_id)
                if (
                    len(chunks) != batch["total_chunk_count"]
                    or sum(chunk["record_count"] for chunk in chunks) != batch["total_record_count"]
                    or stage_batch_sha256([chunk["chunk_sha256"] for chunk in chunks])
                    != batch["batch_sha256"]
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
            validation_outcome=row["validation_outcome"],
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
            errors=tuple(model_validation_error(issue) for issue in validation.issues),
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
            if dataset == "profiling_profile":
                raise InvalidRequestError(
                    "Profiling results must use the governed Profiling persistence command."
                )

    @classmethod
    def _require_web_writable_pending(cls, row: Mapping[str, object]) -> None:
        require_mcp_writable_pending(row)
        cls._require_web_stage_datasets(pending_model_change_set_datasets(row))
