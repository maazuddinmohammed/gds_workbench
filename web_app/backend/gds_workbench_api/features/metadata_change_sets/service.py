"""Governed Metadata Change Set web application service."""

# This web adapter deliberately reuses the canonical MCP staging and validation
# implementation until that shared boundary is promoted to a public module.
# pyright: reportPrivateUsage=false

from collections.abc import Mapping
from contextlib import AbstractAsyncContextManager
from typing import Any, Protocol, cast
from uuid import UUID, uuid4

from gds_etl_workbench.application.authorization import AuthorizationService
from gds_etl_workbench.domain.authorization import RequestPrincipal
from gds_etl_workbench.domain.errors import InvalidRequestError
from gds_etl_workbench.infrastructure.postgres import WriteTransaction
from gds_etl_workbench.tools.change_sets import metadata as canonical_metadata
from gds_etl_workbench.tools.change_sets.validation import MetadataChangeSetValidation
from psycopg.types.json import Jsonb

from gds_workbench_api.features.metadata.workbook import (
    MetadataWorkbookParseError,
    parse_metadata_workbook,
)

from .contracts import (
    ApplyMetadataChangeSetResult,
    ArchiveMetadataChangeSetResult,
    CreateMetadataChangeSetRequest,
    CreateMetadataChangeSetResult,
    ExpectedDraftRevisionRequest,
    GetMetadataChangeSetResult,
    ImportMetadataWorkbookResult,
    MetadataChangeSetActionKey,
    MetadataChangeSetActionReview,
    MetadataChangeSetDatasetCount,
    MetadataChangeSetValidationError,
    StageMetadataChangeSetRequest,
    StageMetadataChangeSetResult,
    ValidateMetadataChangeSetResult,
)


class MetadataChangeSetDatabase(Protocol):
    def write_transaction(self) -> AbstractAsyncContextManager[WriteTransaction]: ...


class DatabaseMetadataChangeSetService:
    """Expose the existing governed database operations to authenticated web users."""

    def __init__(
        self,
        *,
        database: MetadataChangeSetDatabase,
        authorizer: AuthorizationService,
    ) -> None:
        self._database = database
        self._authorizer = authorizer

    async def create_or_resume(
        self,
        principal: RequestPrincipal,
        *,
        tenant_id: int,
        command: CreateMetadataChangeSetRequest,
        idempotency_key: UUID,
    ) -> CreateMetadataChangeSetResult:
        del command
        identity = canonical_metadata._identity_arguments(principal)
        async with self._database.write_transaction() as transaction:
            row = await transaction.fetch_one(
                canonical_metadata._CREATE_SQL,
                (*identity, tenant_id, uuid4(), idempotency_key),
            )
        canonical_metadata._raise_governed_denial(row)
        assert row is not None
        return CreateMetadataChangeSetResult(
            tenant_id=tenant_id,
            metadata_change_set_id=row["metadata_change_set_id"],
            created=row["created"],
            status=row["metadata_change_set_status"],
            draft_revision=row["draft_revision"],
            created_at=row["created_time"],
            expires_at=row["expires_time"],
        )

    async def stage(
        self,
        principal: RequestPrincipal,
        *,
        tenant_id: int,
        change_set_id: UUID,
        command: StageMetadataChangeSetRequest,
        idempotency_key: UUID,
    ) -> StageMetadataChangeSetResult:
        documents = canonical_metadata._stage_documents(
            [
                canonical_metadata.StageChange(
                    dataset=change.dataset,
                    records=change.records,
                )
                for change in command.changes
            ]
        )
        identity = canonical_metadata._identity_arguments(principal)
        async with self._database.write_transaction() as transaction:
            row = await self._stage_in_transaction(
                transaction,
                identity=identity,
                tenant_id=tenant_id,
                change_set_id=change_set_id,
                expected_draft_revision=command.expected_draft_revision,
                documents=documents,
                correlation_id=idempotency_key,
            )
        return self._stage_result(
            tenant_id=tenant_id,
            change_set_id=change_set_id,
            datasets=tuple(documents),
            row=row,
        )

    async def get(
        self,
        principal: RequestPrincipal,
        *,
        tenant_id: int,
        change_set_id: UUID,
        dataset: canonical_metadata.ChangeSetDataset | None,
    ) -> GetMetadataChangeSetResult:
        identity = canonical_metadata._identity_arguments(principal)
        # The ownership function takes row-share locks, so this logically read-only
        # operation intentionally uses the write-capable transaction boundary.
        async with self._database.write_transaction() as transaction:
            row = await transaction.fetch_one(
                canonical_metadata._GET_SQL,
                (*identity, tenant_id, change_set_id),
            )
        canonical_metadata._raise_governed_denial(row)
        assert row is not None
        documents = canonical_metadata._all_documents(row)
        records = (
            tuple(canonical_metadata._read_document(row, dataset)) if dataset is not None else None
        )
        validation_outcome = row["validation_outcome"]
        if validation_outcome is not None and not isinstance(validation_outcome, dict):
            raise InvalidRequestError("Stored Metadata Change Set validation is invalid.")
        return GetMetadataChangeSetResult(
            tenant_id=tenant_id,
            metadata_change_set_id=change_set_id,
            status=row["metadata_change_set_status"],
            draft_revision=row["draft_revision"],
            candidate_digest=row["candidate_digest"],
            validation_outcome=cast(dict[str, object] | None, validation_outcome),
            dataset_counts=tuple(
                MetadataChangeSetDatasetCount(
                    dataset=name,
                    record_count=len(documents[name]),
                )
                for name in canonical_metadata.CHANGE_SET_DATASETS
            ),
            dataset=dataset,
            records=records,
            created_at=row["created_time"],
            last_activity_at=row["last_activity_time"],
            expires_at=row["expires_time"],
            validated_at=row["validated_time"],
            applied_at=row["applied_time"],
            terminal_at=row["terminal_time"],
        )

    async def validate(
        self,
        principal: RequestPrincipal,
        *,
        tenant_id: int,
        change_set_id: UUID,
        command: ExpectedDraftRevisionRequest,
    ) -> ValidateMetadataChangeSetResult:
        async with self._database.write_transaction() as transaction:
            validation, persisted = await canonical_metadata._validate_and_persist(
                transaction,
                tenant_id=tenant_id,
                metadata_change_set_id=change_set_id,
                expected_draft_revision=command.expected_draft_revision,
                principal=principal,
                authorizer=self._authorizer,
            )
        return self._validation_result(
            tenant_id=tenant_id,
            change_set_id=change_set_id,
            validation=validation,
            persisted=persisted,
        )

    async def apply(
        self,
        principal: RequestPrincipal,
        *,
        tenant_id: int,
        change_set_id: UUID,
        command: ExpectedDraftRevisionRequest,
        idempotency_key: UUID,
    ) -> ApplyMetadataChangeSetResult:
        identity = canonical_metadata._identity_arguments(principal)
        async with self._database.write_transaction() as transaction:
            validation, persisted = await canonical_metadata._validate_and_persist(
                transaction,
                tenant_id=tenant_id,
                metadata_change_set_id=change_set_id,
                expected_draft_revision=command.expected_draft_revision,
                principal=principal,
                authorizer=self._authorizer,
            )
            applied: Mapping[str, Any] | None = None
            if validation.valid:
                assert validation.candidate_digest is not None
                applied = await transaction.fetch_one(
                    canonical_metadata._APPLY_SQL,
                    (
                        *identity,
                        tenant_id,
                        change_set_id,
                        command.expected_draft_revision,
                        validation.candidate_digest,
                        idempotency_key,
                    ),
                )
                canonical_metadata._raise_governed_denial(applied)
                assert applied is not None
        row = applied or persisted
        return ApplyMetadataChangeSetResult(
            tenant_id=tenant_id,
            metadata_change_set_id=change_set_id,
            valid=validation.valid,
            applied=bool(applied and applied["applied"]),
            phase=validation.phase,
            status=row["metadata_change_set_status"],
            draft_revision=row["draft_revision"],
            candidate_digest=(validation.candidate_digest if validation.valid else None),
            staged_record_count=validation.staged_record_count,
            action_count=int(applied["action_count"]) if applied is not None else 0,
            error_count=len(validation.issues),
            errors=self._validation_errors(validation),
            action_review=self._action_review(validation),
            applied_at=applied["applied_time"] if applied is not None else None,
        )

    async def archive(
        self,
        principal: RequestPrincipal,
        *,
        tenant_id: int,
        change_set_id: UUID,
        command: ExpectedDraftRevisionRequest,
        idempotency_key: UUID,
    ) -> ArchiveMetadataChangeSetResult:
        identity = canonical_metadata._identity_arguments(principal)
        async with self._database.write_transaction() as transaction:
            row = await transaction.fetch_one(
                canonical_metadata._ARCHIVE_SQL,
                (
                    *identity,
                    tenant_id,
                    change_set_id,
                    command.expected_draft_revision,
                    idempotency_key,
                ),
            )
        canonical_metadata._raise_governed_denial(row)
        assert row is not None
        return ArchiveMetadataChangeSetResult(
            tenant_id=tenant_id,
            metadata_change_set_id=change_set_id,
            draft_revision=row["draft_revision"],
            archived_at=row["terminal_time"],
        )

    async def import_workbook(
        self,
        principal: RequestPrincipal,
        *,
        tenant_id: int,
        change_set_id: UUID,
        expected_draft_revision: int,
        content: bytes,
        idempotency_key: UUID,
    ) -> ImportMetadataWorkbookResult:
        try:
            sheets = parse_metadata_workbook(content, tenant_id=tenant_id)
        except MetadataWorkbookParseError as error:
            raise InvalidRequestError(str(error)) from None

        # Parsing and canonical row normalization both finish before opening a
        # transaction. The original workbook bytes never cross this boundary.
        documents = canonical_metadata._stage_documents(
            [
                canonical_metadata.StageChange(
                    dataset=cast(canonical_metadata.ChangeSetDataset, sheet.code),
                    records=[dict(record) for record in sheet.rows],
                )
                for sheet in sheets
            ]
        )
        identity = canonical_metadata._identity_arguments(principal)
        async with self._database.write_transaction() as transaction:
            staged_row = await self._stage_in_transaction(
                transaction,
                identity=identity,
                tenant_id=tenant_id,
                change_set_id=change_set_id,
                expected_draft_revision=expected_draft_revision,
                documents=documents,
                correlation_id=idempotency_key,
            )
            staged_revision = staged_row["draft_revision"]
            if type(staged_revision) is not int:
                raise InvalidRequestError("Stored Metadata Change Set revision is invalid.")
            validation, persisted = await canonical_metadata._validate_and_persist(
                transaction,
                tenant_id=tenant_id,
                metadata_change_set_id=change_set_id,
                expected_draft_revision=staged_revision,
                principal=principal,
                authorizer=self._authorizer,
            )

        staged = self._stage_result(
            tenant_id=tenant_id,
            change_set_id=change_set_id,
            datasets=tuple(documents),
            row=staged_row,
        )
        reviewed = self._validation_result(
            tenant_id=tenant_id,
            change_set_id=change_set_id,
            validation=validation,
            persisted=persisted,
        )
        return ImportMetadataWorkbookResult(
            tenant_id=tenant_id,
            metadata_change_set_id=change_set_id,
            imported_sheet_count=len(sheets),
            staged=staged,
            validation=reviewed,
        )

    async def _stage_in_transaction(
        self,
        transaction: WriteTransaction,
        *,
        identity: tuple[UUID, UUID, str],
        tenant_id: int,
        change_set_id: UUID,
        expected_draft_revision: int,
        documents: dict[str, list[dict[str, object]]],
        correlation_id: UUID,
    ) -> Mapping[str, Any]:
        row = await transaction.fetch_one(
            canonical_metadata._STAGE_SQL,
            (
                *identity,
                tenant_id,
                change_set_id,
                expected_draft_revision,
                Jsonb(documents),
                correlation_id,
            ),
        )
        canonical_metadata._raise_governed_denial(row)
        assert row is not None
        return row

    @staticmethod
    def _stage_result(
        *,
        tenant_id: int,
        change_set_id: UUID,
        datasets: tuple[str, ...],
        row: Mapping[str, Any],
    ) -> StageMetadataChangeSetResult:
        raw_counts = row["dataset_counts"]
        if not isinstance(raw_counts, Mapping):
            raise InvalidRequestError("Stored dataset counts are invalid.")
        counts = cast(Mapping[object, object], raw_counts)
        return StageMetadataChangeSetResult(
            tenant_id=tenant_id,
            metadata_change_set_id=change_set_id,
            datasets=tuple(
                MetadataChangeSetDatasetCount(
                    dataset=cast(canonical_metadata.ChangeSetDataset, dataset),
                    record_count=canonical_metadata._staged_record_count(counts, dataset),
                )
                for dataset in datasets
            ),
            draft_revision=row["draft_revision"],
            expires_at=row["expires_time"],
        )

    @classmethod
    def _validation_result(
        cls,
        *,
        tenant_id: int,
        change_set_id: UUID,
        validation: MetadataChangeSetValidation,
        persisted: Mapping[str, Any],
    ) -> ValidateMetadataChangeSetResult:
        return ValidateMetadataChangeSetResult(
            tenant_id=tenant_id,
            metadata_change_set_id=change_set_id,
            valid=validation.valid,
            phase=validation.phase,
            status=persisted["metadata_change_set_status"],
            draft_revision=persisted["draft_revision"],
            candidate_digest=persisted["candidate_digest"],
            staged_record_count=validation.staged_record_count,
            error_count=len(validation.issues),
            errors=cls._validation_errors(validation),
            action_review=cls._action_review(validation),
            validated_at=persisted["validated_time"],
            expires_at=persisted["expires_time"],
        )

    @staticmethod
    def _validation_errors(
        validation: MetadataChangeSetValidation,
    ) -> tuple[MetadataChangeSetValidationError, ...]:
        return tuple(
            MetadataChangeSetValidationError(
                code=issue.code,
                dataset=issue.dataset,
                record_number=issue.record_number,
                fields=issue.fields,
                message=issue.message,
            )
            for issue in validation.issues
        )

    @staticmethod
    def _action_review(
        validation: MetadataChangeSetValidation,
    ) -> tuple[MetadataChangeSetActionReview, ...]:
        return tuple(
            MetadataChangeSetActionReview(
                dataset=cast(canonical_metadata.ChangeSetDataset, summary.dataset),
                insert_count=summary.insert_count,
                update_count=summary.update_count,
                deactivate_count=summary.deactivate_count,
                reactivate_count=summary.reactivate_count,
                no_change_count=summary.no_change_count,
                keys=tuple(
                    MetadataChangeSetActionKey(
                        action=key.action,
                        natural_key=cast(
                            dict[str, str | int | bool | None],
                            key.natural_key,
                        ),
                    )
                    for key in summary.keys
                ),
                keys_truncated=summary.keys_truncated,
            )
            for summary in validation.action_review
        )


__all__ = ["DatabaseMetadataChangeSetService", "MetadataChangeSetDatabase"]
