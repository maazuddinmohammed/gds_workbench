"""Governed Metadata Change Set operations shared by web and MCP adapters."""

from __future__ import annotations

import json
from collections import Counter
from collections.abc import Mapping
from datetime import datetime
from typing import Annotated, Any, Literal, LiteralString, cast
from uuid import UUID, uuid4

from psycopg.types.json import Jsonb
from pydantic import Field, ValidationError

from gds_etl_workbench.application.authorization import AuthorizationService
from gds_etl_workbench.application.change_sets.contracts import (
    MAX_AGENT_VALIDATION_ERROR_EXAMPLES,
    MAX_STAGE_CHUNK_RECORDS,
    MAX_STAGE_CHUNKS,
    SHA256_PATTERN,
    ChangeSetContractModel,
    ChangeSetValidationErrorGroup,
)
from gds_etl_workbench.application.change_sets.metadata_validation import (
    MetadataChangeSetValidation,
    rows_from_snapshot,
    validate_metadata_documents,
)
from gds_etl_workbench.application.metadata_snapshot.selection import (
    select_snapshot_datasets,
)
from gds_etl_workbench.domain.authorization import ActorKind, RequestPrincipal
from gds_etl_workbench.domain.errors import (
    AttributeLockedError,
    AuthorizationDeniedError,
    CandidateDigestConflictError,
    DraftRevisionConflictError,
    InvalidRequestError,
    MetadataChangeSetNotActiveError,
    MetadataChangeSetNotFoundError,
    MetadataChangeSetNotValidatedError,
    ObjectLockedError,
    StageBatchConflictError,
    StageBatchIncompleteError,
    StageBatchNotActiveError,
    StageBatchNotFoundError,
    StageChunkConflictError,
    TenantLockedError,
    TenantLockRequiredError,
    TenantNotFoundError,
)
from gds_etl_workbench.domain.snapshots.metadata import DATASETS_BY_NAME
from gds_etl_workbench.infrastructure.postgres import WriteTransaction

ContractModel = ChangeSetContractModel

type ChangeSetDataset = Literal[
    "source_object",
    "source_attribute",
    "bronze_object",
    "bronze_attribute",
    "silver_object",
    "silver_attribute",
    "gold_object",
    "gold_attribute",
    "ingestion_object_mapping",
    "ingestion_attribute_mapping",
    "copy_group",
    "member_group",
    "copy_group_control",
    "copy",
    "process_group",
    "process",
]

CHANGE_SET_DATASETS: tuple[ChangeSetDataset, ...] = (
    "source_object",
    "source_attribute",
    "bronze_object",
    "bronze_attribute",
    "silver_object",
    "silver_attribute",
    "gold_object",
    "gold_attribute",
    "ingestion_object_mapping",
    "ingestion_attribute_mapping",
    "copy_group",
    "member_group",
    "copy_group_control",
    "copy",
    "process_group",
    "process",
)

DOCUMENT_COLUMN_BY_DATASET = {dataset: f"{dataset}_document" for dataset in CHANGE_SET_DATASETS}

CREATE_SQL: LiteralString = """
SELECT created,
       denial_code,
       metadata_change_set_id,
       metadata_change_set_status,
       draft_revision,
       created_time,
       expires_time
  FROM mcp.create_metadata_change_set(%s, %s, %s, %s, %s, %s)
"""

STAGE_SQL: LiteralString = """
SELECT staged,
       denial_code,
       draft_revision,
       dataset_counts,
       expires_time
  FROM mcp.stage_metadata_change_set(%s, %s, %s, %s, %s, %s, %s, %s)
"""


GET_SQL: LiteralString = """
SELECT *
  FROM mcp.get_metadata_change_set(%s, %s, %s, %s, %s)
"""

_AUTHORIZE_WRITE_SQL: LiteralString = """
SELECT authorized,
       denial_code,
       lock_owner_display_name
  FROM security.authorize_tenant_operation(%s, %s, %s, %s, 'tenant_metadata_write')
"""

_RECORD_VALIDATION_SQL: LiteralString = """
SELECT recorded,
       denial_code,
       metadata_change_set_status,
       draft_revision,
       candidate_digest,
       validated_time,
       expires_time
  FROM mcp.record_metadata_change_set_validation(
      %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s
  )
"""

APPLY_SQL: LiteralString = """
SELECT applied,
       denial_code,
       metadata_change_set_status,
       draft_revision,
       applied_time,
       action_count
  FROM mcp.apply_metadata_change_set(%s, %s, %s, %s, %s, %s, %s, %s)
"""

ARCHIVE_SQL: LiteralString = """
SELECT archived,
       denial_code,
       metadata_change_set_status,
       draft_revision,
       terminal_time
  FROM mcp.archive_metadata_change_set(%s, %s, %s, %s, %s, %s, %s)
"""


class CreateMetadataChangeSetResult(ContractModel):
    schema_version: Literal["1.0"] = "1.0"
    tenant_id: int = Field(gt=0, le=9_223_372_036_854_775_807)
    metadata_change_set_id: UUID
    created: bool
    status: Literal["active", "validated"]
    draft_revision: int = Field(gt=0)
    created_at: datetime
    expires_at: datetime


class StageChange(ContractModel):
    dataset: ChangeSetDataset = Field(
        description="Metadata dataset whose complete pending replacement is supplied."
    )
    records: Annotated[
        list[dict[str, object]],
        Field(
            max_length=50_000,
            description=(
                "Complete pending record list for this dataset; an empty list clears only "
                "this pending dataset and omitted datasets remain unchanged."
            ),
        ),
    ]


class StagedMetadataChangeSetDataset(ContractModel):
    dataset: ChangeSetDataset
    record_count: int = Field(ge=0)


class StageMetadataChangeSetResult(ContractModel):
    schema_version: Literal["1.0"] = "1.0"
    tenant_id: int = Field(gt=0, le=9_223_372_036_854_775_807)
    metadata_change_set_id: UUID
    staged: Literal[True] = True
    datasets: list[StagedMetadataChangeSetDataset] = Field(min_length=1, max_length=16)
    draft_revision: int = Field(gt=0)
    status: Literal["active"] = "active"
    expires_at: datetime


class BeginMetadataStageBatchResult(ContractModel):
    schema_version: Literal["1.0"] = "1.0"
    tenant_id: int = Field(gt=0, le=9_223_372_036_854_775_807)
    metadata_change_set_id: UUID
    stage_batch_id: UUID
    dataset: ChangeSetDataset
    created: bool
    total_record_count: int = Field(gt=0, le=50_000)
    total_chunk_count: int = Field(gt=0, le=MAX_STAGE_CHUNKS)
    received_chunk_count: int = Field(ge=0, le=MAX_STAGE_CHUNKS)
    expected_draft_revision: int = Field(gt=0)
    expires_at: datetime


class PutMetadataStageChunkResult(ContractModel):
    schema_version: Literal["1.0"] = "1.0"
    tenant_id: int = Field(gt=0, le=9_223_372_036_854_775_807)
    metadata_change_set_id: UUID
    stage_batch_id: UUID
    dataset: ChangeSetDataset
    accepted: Literal[True] = True
    duplicate: bool
    chunk_index: int = Field(gt=0, le=MAX_STAGE_CHUNKS)
    record_count: int = Field(gt=0, le=MAX_STAGE_CHUNK_RECORDS)
    received_chunk_count: int = Field(gt=0, le=MAX_STAGE_CHUNKS)
    total_chunk_count: int = Field(gt=0, le=MAX_STAGE_CHUNKS)
    expires_at: datetime


class CommitMetadataStageBatchResult(ContractModel):
    schema_version: Literal["1.0"] = "1.0"
    tenant_id: int = Field(gt=0, le=9_223_372_036_854_775_807)
    metadata_change_set_id: UUID
    stage_batch_id: UUID
    dataset: ChangeSetDataset
    committed: Literal[True] = True
    replayed: bool
    record_count: int = Field(gt=0, le=50_000)
    draft_revision: int = Field(gt=0)
    status: Literal["active"] = "active"
    expires_at: datetime


class MetadataChangeSetDatasetCount(ContractModel):
    dataset: ChangeSetDataset
    record_count: int = Field(ge=0)


class GetMetadataChangeSetResult(ContractModel):
    schema_version: Literal["1.0"] = "1.0"
    tenant_id: int = Field(gt=0, le=9_223_372_036_854_775_807)
    metadata_change_set_id: UUID
    status: Literal["active", "validated", "applied", "expired", "archived", "superseded"]
    draft_revision: int = Field(gt=0)
    candidate_digest: str | None
    validation_outcome: dict[str, object] | None
    dataset_counts: list[MetadataChangeSetDatasetCount]
    dataset: ChangeSetDataset | None
    records: list[dict[str, object]] | None
    created_at: datetime
    last_activity_at: datetime
    expires_at: datetime
    validated_at: datetime | None
    applied_at: datetime | None
    terminal_at: datetime | None


class MetadataChangeSetDatasetFingerprint(ContractModel):
    dataset: ChangeSetDataset
    record_count: int = Field(ge=0)
    sha256: str = Field(pattern=SHA256_PATTERN)


class GetMetadataChangeSetFingerprintResult(ContractModel):
    schema_version: Literal["1.0"] = "1.0"
    fingerprint_version: Literal["1.0"] = "1.0"
    area: Literal["metadata"] = "metadata"
    tenant_id: int = Field(gt=0, le=9_223_372_036_854_775_807)
    metadata_change_set_id: UUID
    status: Literal["active", "validated", "applied", "expired", "archived", "superseded"]
    draft_revision: int = Field(gt=0)
    dataset_count: int = Field(ge=0)
    record_count: int = Field(ge=0)
    datasets: list[MetadataChangeSetDatasetFingerprint]
    fingerprint: str = Field(pattern=SHA256_PATTERN)
    expires_at: datetime


class MetadataChangeSetValidationError(ContractModel):
    code: str
    dataset: str
    record_number: int | None
    fields: list[str]
    message: str


class MetadataChangeSetActionKey(ContractModel):
    action: Literal["insert", "update", "deactivate", "reactivate", "no_change"]
    natural_key: dict[str, str | int | bool | None]


class MetadataChangeSetActionReview(ContractModel):
    dataset: ChangeSetDataset
    insert_count: int = Field(ge=0)
    update_count: int = Field(ge=0)
    deactivate_count: int = Field(ge=0)
    reactivate_count: int = Field(ge=0)
    no_change_count: int = Field(ge=0)
    keys: list[MetadataChangeSetActionKey] = Field(max_length=100)
    keys_truncated: bool


class ValidateMetadataChangeSetResult(ContractModel):
    schema_version: Literal["1.0"] = "1.0"
    tenant_id: int = Field(gt=0, le=9_223_372_036_854_775_807)
    metadata_change_set_id: UUID
    valid: bool
    phase: str
    status: Literal["active", "validated"]
    draft_revision: int = Field(gt=0)
    candidate_digest: str | None
    staged_record_count: int = Field(ge=0)
    error_count: int = Field(ge=0)
    error_groups: list[ChangeSetValidationErrorGroup]
    errors: list[MetadataChangeSetValidationError]
    errors_truncated: bool
    action_review: list[MetadataChangeSetActionReview]
    validated_at: datetime | None
    expires_at: datetime


class ApplyMetadataChangeSetResult(ContractModel):
    schema_version: Literal["1.0"] = "1.0"
    tenant_id: int = Field(gt=0, le=9_223_372_036_854_775_807)
    metadata_change_set_id: UUID
    valid: bool
    applied: bool
    phase: str
    status: Literal["active", "applied"]
    draft_revision: int = Field(gt=0)
    candidate_digest: str | None
    staged_record_count: int = Field(ge=0)
    action_count: int = Field(ge=0)
    error_count: int = Field(ge=0)
    error_groups: list[ChangeSetValidationErrorGroup]
    errors: list[MetadataChangeSetValidationError]
    errors_truncated: bool
    action_review: list[MetadataChangeSetActionReview]
    applied_at: datetime | None


class ArchiveMetadataChangeSetResult(ContractModel):
    schema_version: Literal["1.0"] = "1.0"
    tenant_id: int = Field(gt=0, le=9_223_372_036_854_775_807)
    metadata_change_set_id: UUID
    archived: Literal[True] = True
    status: Literal["archived"] = "archived"
    draft_revision: int = Field(gt=0)
    archived_at: datetime


def metadata_identity_arguments(principal: RequestPrincipal) -> tuple[UUID, UUID, str]:
    if principal.entra_tenant_id is None or principal.entra_object_id is None:
        raise AuthorizationDeniedError()
    expected_type = "user" if principal.actor_kind is ActorKind.HUMAN else "service_principal"
    return principal.entra_tenant_id, principal.entra_object_id, expected_type


def action_review(
    validation: MetadataChangeSetValidation,
) -> list[MetadataChangeSetActionReview]:
    return [
        MetadataChangeSetActionReview(
            dataset=cast(ChangeSetDataset, summary.dataset),
            insert_count=summary.insert_count,
            update_count=summary.update_count,
            deactivate_count=summary.deactivate_count,
            reactivate_count=summary.reactivate_count,
            no_change_count=summary.no_change_count,
            keys=[
                MetadataChangeSetActionKey(
                    action=key.action,
                    natural_key=cast(dict[str, str | int | bool | None], key.natural_key),
                )
                for key in summary.keys
            ],
            keys_truncated=summary.keys_truncated,
        )
        for summary in validation.action_review
    ]


def metadata_error_groups(
    validation: MetadataChangeSetValidation,
) -> list[ChangeSetValidationErrorGroup]:
    groups = Counter((issue.dataset, issue.code) for issue in validation.issues)
    return [
        ChangeSetValidationErrorGroup(dataset=dataset, code=code, count=count)
        for (dataset, code), count in sorted(groups.items())
    ]


def metadata_error_examples(
    validation: MetadataChangeSetValidation,
) -> list[MetadataChangeSetValidationError]:
    return [
        MetadataChangeSetValidationError(
            code=issue.code,
            dataset=issue.dataset,
            record_number=issue.record_number,
            fields=list(issue.fields),
            message=issue.message,
        )
        for issue in validation.issues[:MAX_AGENT_VALIDATION_ERROR_EXAMPLES]
    ]


async def validate_and_persist(
    transaction: WriteTransaction,
    *,
    tenant_id: int,
    metadata_change_set_id: UUID,
    expected_draft_revision: int,
    principal: RequestPrincipal,
    authorizer: AuthorizationService,
) -> tuple[MetadataChangeSetValidation, Mapping[str, Any]]:
    identity_arguments = metadata_identity_arguments(principal)
    authorization = await transaction.fetch_one(
        _AUTHORIZE_WRITE_SQL,
        (*identity_arguments, tenant_id),
    )
    raise_governed_denial(authorization)
    change_set = await transaction.fetch_one(
        GET_SQL,
        (*identity_arguments, tenant_id, metadata_change_set_id),
    )
    raise_governed_denial(change_set)
    assert change_set is not None
    require_editable_revision(change_set, expected_draft_revision)
    selected = await select_snapshot_datasets(
        transaction,
        tenant_id=tenant_id,
        request_principal=principal,
        authorizer=authorizer,
    )
    validation = validate_metadata_documents(
        tenant_code=selected.tenant_code,
        current_rows_by_dataset=rows_from_snapshot(selected.datasets),
        staged_rows_by_dataset=all_documents(change_set),
    )
    persisted = await transaction.fetch_one(
        _RECORD_VALIDATION_SQL,
        (
            *identity_arguments,
            tenant_id,
            metadata_change_set_id,
            expected_draft_revision,
            validation.valid,
            validation.candidate_digest if validation.valid else None,
            Jsonb(validation.outcome_document()),
            uuid4(),
            uuid4(),
        ),
    )
    raise_governed_denial(persisted)
    assert persisted is not None
    return validation, persisted


def raise_governed_denial(row: Mapping[str, Any] | None) -> None:
    if row is None:
        raise AuthorizationDeniedError()
    denial_code = row["denial_code"]
    if denial_code in (None, "metadata_change_set_exists"):
        return
    if denial_code == "tenant_not_found":
        raise TenantNotFoundError()
    if denial_code == "tenant_lock_required":
        raise TenantLockRequiredError()
    if denial_code == "tenant_locked":
        raise TenantLockedError("another Principal")
    if denial_code == "metadata_change_set_not_found":
        raise MetadataChangeSetNotFoundError()
    if denial_code == "metadata_change_set_not_active":
        raise MetadataChangeSetNotActiveError()
    if denial_code == "metadata_change_set_not_validated":
        raise MetadataChangeSetNotValidatedError()
    if denial_code == "object_locked":
        raise ObjectLockedError()
    if denial_code == "attribute_locked":
        raise AttributeLockedError()
    if denial_code == "candidate_digest_conflict":
        raise CandidateDigestConflictError()
    if denial_code == "stage_batch_conflict":
        raise StageBatchConflictError()
    if denial_code == "stage_batch_not_found":
        raise StageBatchNotFoundError()
    if denial_code == "stage_batch_not_active":
        raise StageBatchNotActiveError()
    if denial_code == "stage_batch_incomplete":
        raise StageBatchIncompleteError()
    if denial_code == "stage_chunk_conflict":
        raise StageChunkConflictError()
    if denial_code == "draft_revision_conflict":
        raw_revision = row.get("draft_revision")
        raise DraftRevisionConflictError(int(raw_revision) if type(raw_revision) is int else None)
    if denial_code == "invalid_request":
        raise InvalidRequestError()
    raise AuthorizationDeniedError()


def stage_document(change: StageChange) -> list[dict[str, object]]:
    definition = DATASETS_BY_NAME[change.dataset]
    records: list[dict[str, object]] = []
    for record_number, raw_record in enumerate(change.records, start=1):
        try:
            encoded_record = json.dumps(
                raw_record,
                ensure_ascii=False,
                separators=(",", ":"),
            )
        except TypeError, ValueError:
            raise InvalidRequestError(
                f"{change.dataset} record {record_number} field record "
                "does not match its published schema."
            ) from None
        try:
            record = definition.row_model.model_validate_json(encoded_record, strict=True)
        except ValidationError as error:
            first_error = error.errors(
                include_url=False,
                include_context=False,
                include_input=False,
            )[0]
            field = next(
                (
                    part
                    for part in first_error["loc"]
                    if isinstance(part, str) and part in definition.row_model.model_fields
                ),
                "unknown_field" if first_error["type"] == "extra_forbidden" else "record",
            )
            raise InvalidRequestError(
                f"{change.dataset} record {record_number} field {field} "
                "does not match its published schema."
            ) from None
        records.append(record.model_dump(mode="json"))
    for field_name, expected_value in definition.fixed_values:
        if any(record[field_name] != expected_value for record in records):
            raise InvalidRequestError(
                f"Every {change.dataset} record must have {field_name}={expected_value}."
            )
    encoded = json.dumps(records, ensure_ascii=False, separators=(",", ":")).encode()
    if len(encoded) > 16_777_216:
        raise InvalidRequestError("The staged dataset exceeds 16 MiB.")
    return records


def stage_documents(
    changes: list[StageChange],
) -> dict[str, list[dict[str, object]]]:
    documents: dict[str, list[dict[str, object]]] = {}
    for change in changes:
        if change.dataset in documents:
            raise InvalidRequestError("A dataset can appear only once in a Stage request.")
        documents[change.dataset] = stage_document(change)
    encoded = json.dumps(
        documents,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    if len(encoded) > 16_777_216:
        raise InvalidRequestError("The Stage request exceeds 16 MiB.")
    return documents


def staged_record_count(counts: Mapping[object, object], dataset: str) -> int:
    value = counts.get(dataset)
    if type(value) is not int or value < 0:
        raise InvalidRequestError("Stored dataset counts are invalid.")
    return value


def read_document(
    row: Mapping[str, Any],
    dataset: ChangeSetDataset,
) -> list[dict[str, object]]:
    definition = DATASETS_BY_NAME[dataset]
    document = row[DOCUMENT_COLUMN_BY_DATASET[dataset]]
    if not isinstance(document, list):
        raise InvalidRequestError("Stored Metadata Change Set document is invalid.")
    return [
        definition.row_model.model_validate(record).model_dump(mode="json")
        for record in cast(list[object], document)
    ]


def all_documents(row: Mapping[str, Any]) -> dict[str, list[Mapping[str, object]]]:
    documents: dict[str, list[Mapping[str, object]]] = {}
    for dataset in CHANGE_SET_DATASETS:
        raw = row[DOCUMENT_COLUMN_BY_DATASET[dataset]]
        if not isinstance(raw, list):
            raise InvalidRequestError("Stored Metadata Change Set document is invalid.")
        documents[dataset] = [
            cast(Mapping[str, object], record)
            for record in cast(list[object], raw)
            if isinstance(record, Mapping)
        ]
        if len(documents[dataset]) != len(cast(list[object], raw)):
            raise InvalidRequestError("Stored Metadata Change Set document is invalid.")
    return documents


def require_editable_revision(row: Mapping[str, Any], expected_revision: int) -> None:
    if row["metadata_change_set_status"] not in ("active", "validated"):
        raise MetadataChangeSetNotActiveError()
    if row["draft_revision"] != expected_revision:
        raise DraftRevisionConflictError(int(row["draft_revision"]))
