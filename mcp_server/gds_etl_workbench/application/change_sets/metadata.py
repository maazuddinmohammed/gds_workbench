"""Governed Metadata Change Set operations shared by web and MCP adapters."""

# Pyright cannot see that @server.tool registers these nested handlers.
# pyright: reportUnusedFunction=false

from __future__ import annotations

import json
from collections.abc import Mapping
from datetime import datetime
from typing import TYPE_CHECKING, Annotated, Any, Literal, LiteralString, cast
from uuid import UUID, uuid4

from psycopg.types.json import Jsonb
from pydantic import Field, ValidationError

from gds_etl_workbench.application.authorization import AuthorizationService
from gds_etl_workbench.application.change_sets.contracts import (
    MAX_STAGE_CHUNK_BYTES,
    MAX_STAGE_CHUNK_RECORDS,
    MAX_STAGE_CHUNKS,
    SHA256_PATTERN,
    ChangeSetContractModel,
    canonical_records_sha256,
)
from gds_etl_workbench.application.change_sets.metadata_validation import (
    MetadataChangeSetValidation,
    rows_from_snapshot,
    validate_metadata_documents,
)
from gds_etl_workbench.domain.authorization import ActorKind, RequestPrincipal, ToolPolicy
from gds_etl_workbench.domain.errors import (
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
    WorkbenchError,
)
from gds_etl_workbench.domain.snapshots.metadata import DATASETS_BY_NAME
from gds_etl_workbench.infrastructure.postgres import WriteDatabase, WriteTransaction
from gds_etl_workbench.tools.snapshots.metadata.get_metadata_snapshot import (
    select_snapshot_datasets,
)

if TYPE_CHECKING:
    from mcp.server.mcpserver import Context, MCPServer

    from gds_etl_workbench.adapters.auth.identity import IdentityProvider
    from gds_etl_workbench.adapters.mcp.tool_audit import ToolCallAuditMiddleware

POLICY = ToolPolicy.TENANT_METADATA_WRITE
READ_POLICY = ToolPolicy.TENANT_LOCK_MANAGE
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

_CREATE_SQL: LiteralString = """
SELECT created,
       denial_code,
       metadata_change_set_id,
       metadata_change_set_status,
       draft_revision,
       created_time,
       expires_time
  FROM mcp.create_metadata_change_set(%s, %s, %s, %s, %s, %s)
"""

_STAGE_SQL: LiteralString = """
SELECT staged,
       denial_code,
       draft_revision,
       dataset_counts,
       expires_time
  FROM mcp.stage_metadata_change_set(%s, %s, %s, %s, %s, %s, %s, %s)
"""

_BEGIN_STAGE_BATCH_SQL: LiteralString = """
SELECT started,
       denial_code,
       stage_batch_id,
       created,
       dataset_name,
       total_record_count,
       total_chunk_count,
       received_chunk_count,
       expires_time
  FROM mcp.begin_metadata_stage_batch(
      %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s
  )
"""

_PUT_STAGE_CHUNK_SQL: LiteralString = """
SELECT accepted,
       denial_code,
       duplicate,
       received_chunk_count,
       total_chunk_count,
       record_count,
       expires_time
  FROM mcp.put_metadata_stage_chunk(
      %s, %s, %s, %s, %s, %s, %s, %s, %s, %s
  )
"""

_COMMIT_STAGE_BATCH_SQL: LiteralString = """
SELECT committed,
       denial_code,
       replayed,
       dataset_name,
       record_count,
       draft_revision,
       expires_time
  FROM mcp.commit_metadata_stage_batch(
      %s, %s, %s, %s, %s, %s, %s, %s
  )
"""

_GET_SQL: LiteralString = """
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

_APPLY_SQL: LiteralString = """
SELECT applied,
       denial_code,
       metadata_change_set_status,
       draft_revision,
       applied_time,
       action_count
  FROM mcp.apply_metadata_change_set(%s, %s, %s, %s, %s, %s, %s, %s)
"""

_ARCHIVE_SQL: LiteralString = """
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
    errors: list[MetadataChangeSetValidationError]
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
    errors: list[MetadataChangeSetValidationError]
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


class MetadataChangeSetToolError(Exception):
    """A bounded tool failure safe for MCP serialization."""


def register_metadata_change_set_tools(
    server: MCPServer[None],
    *,
    database: WriteDatabase,
    identity_provider: IdentityProvider,
    authorizer: AuthorizationService,
    audit: ToolCallAuditMiddleware,
) -> None:
    from mcp.server.mcpserver import Context as McpContext

    from gds_etl_workbench.adapters.auth.identity import AuthenticationError
    from gds_etl_workbench.adapters.mcp.annotations import change_set_annotations

    _annotations = change_set_annotations
    globals()["Context"] = McpContext

    @server.tool(
        description=(
            "Create one Metadata Change Set for a locked Tenant, or return the current "
            "Principal's existing active or validated Change Set for that Tenant."
        ),
        annotations=_annotations(read_only=False, destructive=False, idempotent=True),
        meta={"gds/toolPolicy": POLICY.value},
        structured_output=True,
    )
    async def create_metadata_change_set(
        ctx: Context[None],
        tenant_id: Annotated[int, Field(gt=0, le=9_223_372_036_854_775_807)],
        schema_version: Literal["1.0"] = "1.0",
    ) -> CreateMetadataChangeSetResult:
        del schema_version
        try:
            principal = identity_provider.request_principal(ctx.request_context.request)
            identity_arguments = _identity_arguments(principal)
            async with database.write_transaction() as transaction:
                row = await transaction.fetch_one(
                    _CREATE_SQL,
                    (*identity_arguments, tenant_id, uuid4(), uuid4()),
                )
            _raise_governed_denial(row)
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
        except AuthenticationError as error:
            raise MetadataChangeSetToolError(f"{error.public_code}: {error.message}") from None
        except WorkbenchError as error:
            raise MetadataChangeSetToolError(f"{error.code}: {error.message}") from None
        except Exception:
            raise MetadataChangeSetToolError(
                "internal_error: The operation could not be completed."
            ) from None

    audit.register_tool(
        "create_metadata_change_set",
        policy=POLICY,
        summarize_input=_tenant_audit,
        retain_arguments={"tenant_id", "schema_version"},
        tenant_argument="tenant_id",
    )

    @server.tool(
        description=(
            "Replace the complete pending record lists for one or more Metadata datasets in "
            "one transaction; this never appends. Omitted datasets stay unchanged and empty "
            "lists clear only that pending dataset. Use the direct operation only when every "
            "included dataset fits in one request; otherwise use ordered Begin, Put, and Commit "
            "operations. The draft revision increments once."
        ),
        annotations=_annotations(read_only=False, destructive=False, idempotent=False),
        meta={"gds/toolPolicy": POLICY.value},
        structured_output=True,
    )
    async def stage_metadata_change_set(
        ctx: Context[None],
        tenant_id: Annotated[int, Field(gt=0, le=9_223_372_036_854_775_807)],
        metadata_change_set_id: UUID,
        expected_draft_revision: Annotated[int, Field(gt=0)],
        changes: Annotated[
            list[StageChange],
            Field(
                min_length=1,
                max_length=16,
                description="One complete pending replacement per affected Metadata dataset.",
            ),
        ],
        schema_version: Literal["1.0"] = "1.0",
    ) -> StageMetadataChangeSetResult:
        del schema_version
        try:
            documents = _stage_documents(changes)
            principal = identity_provider.request_principal(ctx.request_context.request)
            identity_arguments = _identity_arguments(principal)
            async with database.write_transaction() as transaction:
                row = await transaction.fetch_one(
                    _STAGE_SQL,
                    (
                        *identity_arguments,
                        tenant_id,
                        metadata_change_set_id,
                        expected_draft_revision,
                        Jsonb(documents),
                        uuid4(),
                    ),
                )
            _raise_governed_denial(row)
            assert row is not None
            raw_counts = row["dataset_counts"]
            if not isinstance(raw_counts, Mapping):
                raise InvalidRequestError("Stored dataset counts are invalid.")
            dataset_counts = cast(Mapping[object, object], raw_counts)
            return StageMetadataChangeSetResult(
                tenant_id=tenant_id,
                metadata_change_set_id=metadata_change_set_id,
                datasets=[
                    StagedMetadataChangeSetDataset(
                        dataset=cast(ChangeSetDataset, dataset),
                        record_count=_staged_record_count(dataset_counts, dataset),
                    )
                    for dataset in documents
                ],
                draft_revision=row["draft_revision"],
                expires_at=row["expires_time"],
            )
        except AuthenticationError as error:
            raise MetadataChangeSetToolError(f"{error.public_code}: {error.message}") from None
        except WorkbenchError as error:
            raise MetadataChangeSetToolError(f"{error.code}: {error.message}") from None
        except Exception:
            raise MetadataChangeSetToolError(
                "internal_error: The operation could not be completed."
            ) from None

    audit.register_tool(
        "stage_metadata_change_set",
        policy=POLICY,
        summarize_input=_stage_audit,
        retain_arguments={
            "tenant_id",
            "metadata_change_set_id",
            "expected_draft_revision",
            "schema_version",
        },
        tenant_argument="tenant_id",
    )

    @server.tool(
        description=(
            "Begin or resume the nonempty Metadata dataset replacement selected by the client "
            "Stage plan. Use at most 64 ordered chunks; each Put accepts at most 5,000 records "
            "and 450 KiB of canonical JSON. Begin is idempotent and does not change the draft "
            "revision."
        ),
        annotations=_annotations(read_only=False, destructive=False, idempotent=True),
        meta={"gds/toolPolicy": POLICY.value},
        structured_output=True,
    )
    async def begin_metadata_stage_batch(
        ctx: Context[None],
        tenant_id: Annotated[int, Field(gt=0, le=9_223_372_036_854_775_807)],
        metadata_change_set_id: UUID,
        expected_draft_revision: Annotated[int, Field(gt=0)],
        dataset: Annotated[
            ChangeSetDataset,
            Field(description="Single dataset replaced when this batch is committed."),
        ],
        total_record_count: Annotated[
            int,
            Field(gt=0, le=50_000, description="Records in the complete replacement list."),
        ],
        total_chunk_count: Annotated[
            int,
            Field(gt=0, le=MAX_STAGE_CHUNKS, description="Ordered chunks numbered from 1."),
        ],
        batch_sha256: Annotated[
            str,
            Field(
                pattern=SHA256_PATTERN,
                description=(
                    "SHA-256 of the lowercase chunk SHA-256 strings concatenated in chunk order."
                ),
            ),
        ],
        schema_version: Literal["1.0"] = "1.0",
    ) -> BeginMetadataStageBatchResult:
        del schema_version
        try:
            principal = identity_provider.request_principal(ctx.request_context.request)
            async with database.write_transaction() as transaction:
                row = await transaction.fetch_one(
                    _BEGIN_STAGE_BATCH_SQL,
                    (
                        *_identity_arguments(principal),
                        tenant_id,
                        metadata_change_set_id,
                        expected_draft_revision,
                        uuid4(),
                        dataset,
                        total_record_count,
                        total_chunk_count,
                        batch_sha256,
                        uuid4(),
                    ),
                )
            _raise_governed_denial(row)
            assert row is not None and row["started"]
            return BeginMetadataStageBatchResult(
                tenant_id=tenant_id,
                metadata_change_set_id=metadata_change_set_id,
                stage_batch_id=row["stage_batch_id"],
                dataset=cast(ChangeSetDataset, row["dataset_name"]),
                created=row["created"],
                total_record_count=row["total_record_count"],
                total_chunk_count=row["total_chunk_count"],
                received_chunk_count=row["received_chunk_count"],
                expected_draft_revision=expected_draft_revision,
                expires_at=row["expires_time"],
            )
        except AuthenticationError as error:
            raise MetadataChangeSetToolError(f"{error.public_code}: {error.message}") from None
        except WorkbenchError as error:
            raise MetadataChangeSetToolError(f"{error.code}: {error.message}") from None
        except Exception:
            raise MetadataChangeSetToolError(
                "internal_error: The operation could not be completed."
            ) from None

    audit.register_tool(
        "begin_metadata_stage_batch",
        policy=POLICY,
        summarize_input=_begin_stage_batch_audit,
        retain_arguments={
            "tenant_id",
            "metadata_change_set_id",
            "expected_draft_revision",
            "dataset",
            "total_record_count",
            "total_chunk_count",
            "schema_version",
        },
        tenant_argument="tenant_id",
    )

    @server.tool(
        description=(
            "Store one ordered Metadata batch chunk: 1-5,000 complete records and at most 450 "
            "KiB after schema normalization. chunk_sha256 covers the canonical normalized list. "
            "An identical retry is safe; Put does not change the draft revision."
        ),
        annotations=_annotations(read_only=False, destructive=False, idempotent=True),
        meta={"gds/toolPolicy": POLICY.value},
        structured_output=True,
    )
    async def put_metadata_stage_chunk(
        ctx: Context[None],
        tenant_id: Annotated[int, Field(gt=0, le=9_223_372_036_854_775_807)],
        metadata_change_set_id: UUID,
        stage_batch_id: UUID,
        dataset: Annotated[
            ChangeSetDataset,
            Field(description="Must match the dataset declared by the Stage Batch."),
        ],
        chunk_index: Annotated[
            int,
            Field(gt=0, le=MAX_STAGE_CHUNKS, description="One-based chunk position."),
        ],
        records: Annotated[
            list[dict[str, object]],
            Field(
                min_length=1,
                max_length=MAX_STAGE_CHUNK_RECORDS,
                description=(
                    "Whole records for this chunk; never partial records or JSON fragments."
                ),
            ),
        ],
        chunk_sha256: Annotated[
            str,
            Field(
                pattern=SHA256_PATTERN,
                description="SHA-256 of this chunk's normalized record list.",
            ),
        ],
        schema_version: Literal["1.0"] = "1.0",
    ) -> PutMetadataStageChunkResult:
        del schema_version
        try:
            normalized = _stage_document(StageChange(dataset=dataset, records=records))
            encoded = json.dumps(
                normalized,
                ensure_ascii=False,
                separators=(",", ":"),
                sort_keys=True,
            ).encode("utf-8")
            if len(encoded) > MAX_STAGE_CHUNK_BYTES:
                raise InvalidRequestError("The Stage chunk exceeds the bounded byte limit.")
            if canonical_records_sha256(normalized) != chunk_sha256:
                raise InvalidRequestError(
                    "The Stage chunk SHA-256 does not match its normalized records."
                )
            principal = identity_provider.request_principal(ctx.request_context.request)
            async with database.write_transaction() as transaction:
                row = await transaction.fetch_one(
                    _PUT_STAGE_CHUNK_SQL,
                    (
                        *_identity_arguments(principal),
                        tenant_id,
                        metadata_change_set_id,
                        stage_batch_id,
                        dataset,
                        chunk_index,
                        chunk_sha256,
                        Jsonb(normalized),
                    ),
                )
            _raise_governed_denial(row)
            assert row is not None and row["accepted"]
            return PutMetadataStageChunkResult(
                tenant_id=tenant_id,
                metadata_change_set_id=metadata_change_set_id,
                stage_batch_id=stage_batch_id,
                dataset=dataset,
                duplicate=row["duplicate"],
                chunk_index=chunk_index,
                record_count=row["record_count"],
                received_chunk_count=row["received_chunk_count"],
                total_chunk_count=row["total_chunk_count"],
                expires_at=row["expires_time"],
            )
        except AuthenticationError as error:
            raise MetadataChangeSetToolError(f"{error.public_code}: {error.message}") from None
        except WorkbenchError as error:
            raise MetadataChangeSetToolError(f"{error.code}: {error.message}") from None
        except Exception:
            raise MetadataChangeSetToolError(
                "internal_error: The operation could not be completed."
            ) from None

    audit.register_tool(
        "put_metadata_stage_chunk",
        policy=POLICY,
        summarize_input=_put_stage_chunk_audit,
        retain_arguments={
            "tenant_id",
            "metadata_change_set_id",
            "stage_batch_id",
            "dataset",
            "chunk_index",
            "schema_version",
        },
        tenant_argument="tenant_id",
    )

    @server.tool(
        description=(
            "Verify and atomically commit one complete Metadata Stage Batch as that dataset's "
            "pending replacement. The response returns the new draft_revision; use it for "
            "the next batch or validation."
        ),
        annotations=_annotations(read_only=False, destructive=False, idempotent=True),
        meta={"gds/toolPolicy": POLICY.value},
        structured_output=True,
    )
    async def commit_metadata_stage_batch(
        ctx: Context[None],
        tenant_id: Annotated[int, Field(gt=0, le=9_223_372_036_854_775_807)],
        metadata_change_set_id: UUID,
        stage_batch_id: UUID,
        expected_draft_revision: Annotated[int, Field(gt=0)],
        schema_version: Literal["1.0"] = "1.0",
    ) -> CommitMetadataStageBatchResult:
        del schema_version
        try:
            principal = identity_provider.request_principal(ctx.request_context.request)
            async with database.write_transaction() as transaction:
                row = await transaction.fetch_one(
                    _COMMIT_STAGE_BATCH_SQL,
                    (
                        *_identity_arguments(principal),
                        tenant_id,
                        metadata_change_set_id,
                        stage_batch_id,
                        expected_draft_revision,
                        uuid4(),
                    ),
                )
            _raise_governed_denial(row)
            assert row is not None and row["committed"]
            return CommitMetadataStageBatchResult(
                tenant_id=tenant_id,
                metadata_change_set_id=metadata_change_set_id,
                stage_batch_id=stage_batch_id,
                dataset=cast(ChangeSetDataset, row["dataset_name"]),
                replayed=row["replayed"],
                record_count=row["record_count"],
                draft_revision=row["draft_revision"],
                expires_at=row["expires_time"],
            )
        except AuthenticationError as error:
            raise MetadataChangeSetToolError(f"{error.public_code}: {error.message}") from None
        except WorkbenchError as error:
            raise MetadataChangeSetToolError(f"{error.code}: {error.message}") from None
        except Exception:
            raise MetadataChangeSetToolError(
                "internal_error: The operation could not be completed."
            ) from None

    audit.register_tool(
        "commit_metadata_stage_batch",
        policy=POLICY,
        summarize_input=_revision_audit,
        retain_arguments={
            "tenant_id",
            "metadata_change_set_id",
            "stage_batch_id",
            "expected_draft_revision",
            "schema_version",
        },
        tenant_argument="tenant_id",
    )

    @server.tool(
        description=(
            "Read your Metadata Change Set without requiring a current Tenant Lock. "
            "Omit dataset for counts only; provide dataset to return only that dataset."
        ),
        annotations=_annotations(read_only=True, destructive=False, idempotent=True),
        meta={"gds/toolPolicy": READ_POLICY.value},
        structured_output=True,
    )
    async def get_metadata_change_set(
        ctx: Context[None],
        tenant_id: Annotated[int, Field(gt=0, le=9_223_372_036_854_775_807)],
        metadata_change_set_id: UUID,
        dataset: ChangeSetDataset | None = None,
        schema_version: Literal["1.0"] = "1.0",
    ) -> GetMetadataChangeSetResult:
        del schema_version
        try:
            principal = identity_provider.request_principal(ctx.request_context.request)
            # The governed ownership function calls the centralized
            # authorization function, which takes row-share locks. It remains
            # logically read-only but requires a read-write PostgreSQL transaction.
            async with database.write_transaction() as transaction:
                row = await transaction.fetch_one(
                    _GET_SQL,
                    (
                        *_identity_arguments(principal),
                        tenant_id,
                        metadata_change_set_id,
                    ),
                )
            _raise_governed_denial(row)
            assert row is not None
            counts = [
                MetadataChangeSetDatasetCount(
                    dataset=name,
                    record_count=len(row[DOCUMENT_COLUMN_BY_DATASET[name]]),
                )
                for name in CHANGE_SET_DATASETS
            ]
            records = _read_document(row, dataset) if dataset is not None else None
            return GetMetadataChangeSetResult(
                tenant_id=tenant_id,
                metadata_change_set_id=metadata_change_set_id,
                status=row["metadata_change_set_status"],
                draft_revision=row["draft_revision"],
                candidate_digest=row["candidate_digest"],
                validation_outcome=row["validation_outcome"],
                dataset_counts=counts,
                dataset=dataset,
                records=records,
                created_at=row["created_time"],
                last_activity_at=row["last_activity_time"],
                expires_at=row["expires_time"],
                validated_at=row["validated_time"],
                applied_at=row["applied_time"],
                terminal_at=row["terminal_time"],
            )
        except AuthenticationError as error:
            raise MetadataChangeSetToolError(f"{error.public_code}: {error.message}") from None
        except WorkbenchError as error:
            raise MetadataChangeSetToolError(f"{error.code}: {error.message}") from None
        except Exception:
            raise MetadataChangeSetToolError(
                "internal_error: The operation could not be completed."
            ) from None

    audit.register_tool(
        "get_metadata_change_set",
        policy=READ_POLICY,
        summarize_input=_get_audit,
        retain_arguments={
            "tenant_id",
            "metadata_change_set_id",
            "dataset",
            "schema_version",
        },
        tenant_argument="tenant_id",
    )

    @server.tool(
        description=(
            "Validate your complete pending Metadata Change Set against the shared Snapshot "
            "schemas, natural keys, uniqueness rules, references, and current database state. "
            "An invalid draft remains active so its exact revision can be corrected and staged "
            "again; validation never applies it."
        ),
        annotations=_annotations(read_only=False, destructive=False, idempotent=False),
        meta={"gds/toolPolicy": POLICY.value},
        structured_output=True,
    )
    async def validate_metadata_change_set(
        ctx: Context[None],
        tenant_id: Annotated[int, Field(gt=0, le=9_223_372_036_854_775_807)],
        metadata_change_set_id: UUID,
        expected_draft_revision: Annotated[int, Field(gt=0)],
        schema_version: Literal["1.0"] = "1.0",
    ) -> ValidateMetadataChangeSetResult:
        del schema_version
        try:
            principal = identity_provider.request_principal(ctx.request_context.request)
            async with database.write_transaction() as transaction:
                validation, persisted = await _validate_and_persist(
                    transaction,
                    tenant_id=tenant_id,
                    metadata_change_set_id=metadata_change_set_id,
                    expected_draft_revision=expected_draft_revision,
                    principal=principal,
                    authorizer=authorizer,
                )
            return ValidateMetadataChangeSetResult(
                tenant_id=tenant_id,
                metadata_change_set_id=metadata_change_set_id,
                valid=validation.valid,
                phase=validation.phase,
                status=persisted["metadata_change_set_status"],
                draft_revision=persisted["draft_revision"],
                candidate_digest=persisted["candidate_digest"],
                staged_record_count=validation.staged_record_count,
                error_count=len(validation.issues),
                errors=[
                    MetadataChangeSetValidationError(
                        code=issue.code,
                        dataset=issue.dataset,
                        record_number=issue.record_number,
                        fields=list(issue.fields),
                        message=issue.message,
                    )
                    for issue in validation.issues
                ],
                action_review=_action_review(validation),
                validated_at=persisted["validated_time"],
                expires_at=persisted["expires_time"],
            )
        except AuthenticationError as error:
            raise MetadataChangeSetToolError(f"{error.public_code}: {error.message}") from None
        except WorkbenchError as error:
            raise MetadataChangeSetToolError(f"{error.code}: {error.message}") from None
        except Exception:
            raise MetadataChangeSetToolError(
                "internal_error: The operation could not be completed."
            ) from None

    audit.register_tool(
        "validate_metadata_change_set",
        policy=POLICY,
        summarize_input=_revision_audit,
        retain_arguments={
            "tenant_id",
            "metadata_change_set_id",
            "expected_draft_revision",
            "schema_version",
        },
        tenant_argument="tenant_id",
    )

    @server.tool(
        description=(
            "Revalidate and atomically apply your complete Metadata Change Set to "
            "PostgreSQL by resolving every relationship from natural keys."
        ),
        annotations=_annotations(read_only=False, destructive=True, idempotent=False),
        meta={"gds/toolPolicy": POLICY.value},
        structured_output=True,
    )
    async def apply_metadata_change_set(
        ctx: Context[None],
        tenant_id: Annotated[int, Field(gt=0, le=9_223_372_036_854_775_807)],
        metadata_change_set_id: UUID,
        expected_draft_revision: Annotated[int, Field(gt=0)],
        schema_version: Literal["1.0"] = "1.0",
    ) -> ApplyMetadataChangeSetResult:
        del schema_version
        try:
            principal = identity_provider.request_principal(ctx.request_context.request)
            identity_arguments = _identity_arguments(principal)
            async with database.write_transaction() as transaction:
                validation, persisted = await _validate_and_persist(
                    transaction,
                    tenant_id=tenant_id,
                    metadata_change_set_id=metadata_change_set_id,
                    expected_draft_revision=expected_draft_revision,
                    principal=principal,
                    authorizer=authorizer,
                )
                applied_row: Mapping[str, Any] | None = None
                if validation.valid:
                    assert validation.candidate_digest is not None
                    applied_row = await transaction.fetch_one(
                        _APPLY_SQL,
                        (
                            *identity_arguments,
                            tenant_id,
                            metadata_change_set_id,
                            expected_draft_revision,
                            validation.candidate_digest,
                            uuid4(),
                        ),
                    )
                    _raise_governed_denial(applied_row)
                    assert applied_row is not None
            row = applied_row or persisted
            return ApplyMetadataChangeSetResult(
                tenant_id=tenant_id,
                metadata_change_set_id=metadata_change_set_id,
                valid=validation.valid,
                applied=bool(applied_row and applied_row["applied"]),
                phase=validation.phase,
                status=row["metadata_change_set_status"],
                draft_revision=row["draft_revision"],
                candidate_digest=(validation.candidate_digest if validation.valid else None),
                staged_record_count=validation.staged_record_count,
                action_count=int(applied_row["action_count"]) if applied_row else 0,
                error_count=len(validation.issues),
                errors=[
                    MetadataChangeSetValidationError(
                        code=issue.code,
                        dataset=issue.dataset,
                        record_number=issue.record_number,
                        fields=list(issue.fields),
                        message=issue.message,
                    )
                    for issue in validation.issues
                ],
                action_review=_action_review(validation),
                applied_at=applied_row["applied_time"] if applied_row else None,
            )
        except AuthenticationError as error:
            raise MetadataChangeSetToolError(f"{error.public_code}: {error.message}") from None
        except WorkbenchError as error:
            raise MetadataChangeSetToolError(f"{error.code}: {error.message}") from None
        except Exception:
            raise MetadataChangeSetToolError(
                "internal_error: The operation could not be completed."
            ) from None

    audit.register_tool(
        "apply_metadata_change_set",
        policy=POLICY,
        summarize_input=_revision_audit,
        retain_arguments={
            "tenant_id",
            "metadata_change_set_id",
            "expected_draft_revision",
            "schema_version",
        },
        tenant_argument="tenant_id",
    )

    @server.tool(
        description=(
            "End and retain your active or validated Metadata Change Set. A current "
            "Tenant Lock is not required; the Change Set is not deleted."
        ),
        annotations=_annotations(read_only=False, destructive=True, idempotent=False),
        meta={"gds/toolPolicy": READ_POLICY.value},
        structured_output=True,
    )
    async def archive_metadata_change_set(
        ctx: Context[None],
        tenant_id: Annotated[int, Field(gt=0, le=9_223_372_036_854_775_807)],
        metadata_change_set_id: UUID,
        expected_draft_revision: Annotated[int, Field(gt=0)],
        schema_version: Literal["1.0"] = "1.0",
    ) -> ArchiveMetadataChangeSetResult:
        del schema_version
        try:
            principal = identity_provider.request_principal(ctx.request_context.request)
            async with database.write_transaction() as transaction:
                row = await transaction.fetch_one(
                    _ARCHIVE_SQL,
                    (
                        *_identity_arguments(principal),
                        tenant_id,
                        metadata_change_set_id,
                        expected_draft_revision,
                        uuid4(),
                    ),
                )
            _raise_governed_denial(row)
            assert row is not None
            return ArchiveMetadataChangeSetResult(
                tenant_id=tenant_id,
                metadata_change_set_id=metadata_change_set_id,
                draft_revision=row["draft_revision"],
                archived_at=row["terminal_time"],
            )
        except AuthenticationError as error:
            raise MetadataChangeSetToolError(f"{error.public_code}: {error.message}") from None
        except WorkbenchError as error:
            raise MetadataChangeSetToolError(f"{error.code}: {error.message}") from None
        except Exception:
            raise MetadataChangeSetToolError(
                "internal_error: The operation could not be completed."
            ) from None

    audit.register_tool(
        "archive_metadata_change_set",
        policy=READ_POLICY,
        summarize_input=_revision_audit,
        retain_arguments={
            "tenant_id",
            "metadata_change_set_id",
            "expected_draft_revision",
            "schema_version",
        },
        tenant_argument="tenant_id",
    )


def _identity_arguments(principal: RequestPrincipal) -> tuple[UUID, UUID, str]:
    if principal.entra_tenant_id is None or principal.entra_object_id is None:
        raise AuthorizationDeniedError()
    expected_type = "user" if principal.actor_kind is ActorKind.HUMAN else "service_principal"
    return principal.entra_tenant_id, principal.entra_object_id, expected_type


def _action_review(
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


async def _validate_and_persist(
    transaction: WriteTransaction,
    *,
    tenant_id: int,
    metadata_change_set_id: UUID,
    expected_draft_revision: int,
    principal: RequestPrincipal,
    authorizer: AuthorizationService,
) -> tuple[MetadataChangeSetValidation, Mapping[str, Any]]:
    identity_arguments = _identity_arguments(principal)
    authorization = await transaction.fetch_one(
        _AUTHORIZE_WRITE_SQL,
        (*identity_arguments, tenant_id),
    )
    _raise_governed_denial(authorization)
    change_set = await transaction.fetch_one(
        _GET_SQL,
        (*identity_arguments, tenant_id, metadata_change_set_id),
    )
    _raise_governed_denial(change_set)
    assert change_set is not None
    _require_editable_revision(change_set, expected_draft_revision)
    selected = await select_snapshot_datasets(
        transaction,
        tenant_id=tenant_id,
        request_principal=principal,
        authorizer=authorizer,
    )
    validation = validate_metadata_documents(
        tenant_code=selected.tenant_code,
        current_rows_by_dataset=rows_from_snapshot(selected.datasets),
        staged_rows_by_dataset=_all_documents(change_set),
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
    _raise_governed_denial(persisted)
    assert persisted is not None
    return validation, persisted


def _raise_governed_denial(row: Mapping[str, Any] | None) -> None:
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


def _stage_document(change: StageChange) -> list[dict[str, object]]:
    definition = DATASETS_BY_NAME[change.dataset]
    records: list[dict[str, object]] = []
    for record_number, raw_record in enumerate(change.records, start=1):
        try:
            encoded_record = json.dumps(
                raw_record,
                ensure_ascii=False,
                separators=(",", ":"),
            )
        except (TypeError, ValueError):
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


def _stage_documents(
    changes: list[StageChange],
) -> dict[str, list[dict[str, object]]]:
    documents: dict[str, list[dict[str, object]]] = {}
    for change in changes:
        if change.dataset in documents:
            raise InvalidRequestError("A dataset can appear only once in a Stage request.")
        documents[change.dataset] = _stage_document(change)
    encoded = json.dumps(
        documents,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    if len(encoded) > 16_777_216:
        raise InvalidRequestError("The Stage request exceeds 16 MiB.")
    return documents


def _staged_record_count(counts: Mapping[object, object], dataset: str) -> int:
    value = counts.get(dataset)
    if type(value) is not int or value < 0:
        raise InvalidRequestError("Stored dataset counts are invalid.")
    return value


def _read_document(
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


def _all_documents(row: Mapping[str, Any]) -> dict[str, list[Mapping[str, object]]]:
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


def _require_editable_revision(row: Mapping[str, Any], expected_revision: int) -> None:
    if row["metadata_change_set_status"] not in ("active", "validated"):
        raise MetadataChangeSetNotActiveError()
    if row["draft_revision"] != expected_revision:
        raise DraftRevisionConflictError(int(row["draft_revision"]))


def _tenant_audit(arguments: Mapping[str, Any]) -> dict[str, str | int]:
    raw_tenant_id = arguments.get("tenant_id")
    tenant_id: int | str = (
        raw_tenant_id
        if type(raw_tenant_id) is int and 0 < raw_tenant_id <= 9_223_372_036_854_775_807
        else "invalid"
    )
    return {
        "schema_version": "1.0" if arguments.get("schema_version", "1.0") == "1.0" else "invalid",
        "tenant_id": tenant_id,
    }


def _stage_audit(arguments: Mapping[str, Any]) -> dict[str, str | int]:
    summary = _tenant_audit(arguments)
    raw_revision = arguments.get("expected_draft_revision")
    summary["expected_draft_revision"] = (
        raw_revision if type(raw_revision) is int and raw_revision > 0 else "invalid"
    )
    raw_changes = arguments.get("changes")
    if not isinstance(raw_changes, list):
        summary["dataset_count"] = "invalid"
        summary["record_count"] = "invalid"
        return summary
    datasets: set[str] = set()
    record_count = 0
    valid = True
    for raw_change in cast(list[object], raw_changes):
        if not isinstance(raw_change, Mapping):
            valid = False
            continue
        change = cast(Mapping[object, object], raw_change)
        dataset = change.get("dataset")
        records = change.get("records")
        if (
            not isinstance(dataset, str)
            or dataset not in DATASETS_BY_NAME
            or dataset in datasets
            or not isinstance(records, list)
        ):
            valid = False
            continue
        datasets.add(dataset)
        record_count += len(cast(list[object], records))
    summary["dataset_count"] = len(datasets) if valid else "invalid"
    summary["record_count"] = record_count if valid else "invalid"
    return summary


def _begin_stage_batch_audit(arguments: Mapping[str, Any]) -> dict[str, str | int]:
    summary = _revision_audit(arguments)
    raw_dataset = arguments.get("dataset")
    summary["dataset"] = (
        raw_dataset
        if isinstance(raw_dataset, str) and raw_dataset in DATASETS_BY_NAME
        else "invalid"
    )
    for name in ("total_record_count", "total_chunk_count"):
        value = arguments.get(name)
        summary[name] = value if type(value) is int and value > 0 else "invalid"
    return summary


def _put_stage_chunk_audit(arguments: Mapping[str, Any]) -> dict[str, str | int]:
    summary = _tenant_audit(arguments)
    raw_dataset = arguments.get("dataset")
    summary["dataset"] = (
        raw_dataset
        if isinstance(raw_dataset, str) and raw_dataset in DATASETS_BY_NAME
        else "invalid"
    )
    raw_index = arguments.get("chunk_index")
    summary["chunk_index"] = raw_index if type(raw_index) is int and raw_index > 0 else "invalid"
    raw_records = arguments.get("records")
    summary["record_count"] = (
        len(cast(list[object], raw_records)) if isinstance(raw_records, list) else "invalid"
    )
    return summary


def _get_audit(arguments: Mapping[str, Any]) -> dict[str, str | int]:
    summary = _tenant_audit(arguments)
    raw_dataset = arguments.get("dataset")
    summary["dataset"] = (
        raw_dataset
        if isinstance(raw_dataset, str) and raw_dataset in DOCUMENT_COLUMN_BY_DATASET
        else "summary"
        if raw_dataset is None
        else "invalid"
    )
    return summary


def _revision_audit(arguments: Mapping[str, Any]) -> dict[str, str | int]:
    summary = _tenant_audit(arguments)
    raw_revision = arguments.get("expected_draft_revision")
    summary["expected_draft_revision"] = (
        raw_revision if type(raw_revision) is int and raw_revision > 0 else "invalid"
    )
    return summary
