"""MCP transport for governed Metadata Change Sets."""

# Pyright cannot see that @server.tool registers these nested handlers.
# pyright: reportUnusedFunction=false

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from typing import Annotated, Any, Literal, LiteralString, cast
from uuid import UUID, uuid4

from mcp.server.mcpserver import Context, MCPServer
from psycopg.types.json import Jsonb
from pydantic import Field

from gds_etl_workbench.adapters.auth.identity import AuthenticationError, IdentityProvider
from gds_etl_workbench.adapters.mcp.annotations import closed_world_annotations as _annotations
from gds_etl_workbench.adapters.mcp.tool_audit import ToolCallAuditMiddleware
from gds_etl_workbench.application.authorization import AuthorizationService
from gds_etl_workbench.application.change_sets.contracts import (
    MAX_AGENT_VALIDATION_ERROR_EXAMPLES,
    MAX_STAGE_CHUNK_BYTES,
    MAX_STAGE_CHUNK_RECORDS,
    MAX_STAGE_CHUNKS,
    SHA256_PATTERN,
    bounded_validation_outcome,
    canonical_records_sha256,
)
from gds_etl_workbench.application.change_sets.metadata import (
    APPLY_SQL,
    ARCHIVE_SQL,
    CHANGE_SET_DATASETS,
    CREATE_SQL,
    DOCUMENT_COLUMN_BY_DATASET,
    GET_SQL,
    STAGE_SQL,
    ApplyMetadataChangeSetResult,
    ArchiveMetadataChangeSetResult,
    BeginMetadataStageBatchResult,
    ChangeSetDataset,
    CommitMetadataStageBatchResult,
    CreateMetadataChangeSetResult,
    GetMetadataChangeSetFingerprintResult,
    GetMetadataChangeSetResult,
    MetadataChangeSetDatasetCount,
    MetadataChangeSetDatasetFingerprint,
    PutMetadataStageChunkResult,
    StageChange,
    StagedMetadataChangeSetDataset,
    StageMetadataChangeSetResult,
    ValidateMetadataChangeSetResult,
    action_review,
    metadata_error_examples,
    metadata_error_groups,
    metadata_identity_arguments,
    raise_governed_denial,
    read_document,
    stage_document,
    stage_documents,
    staged_record_count,
    validate_and_persist,
)
from gds_etl_workbench.domain.authorization import ToolPolicy
from gds_etl_workbench.domain.errors import (
    InvalidRequestError,
    WorkbenchError,
)
from gds_etl_workbench.domain.snapshots.metadata import DATASETS_BY_NAME
from gds_etl_workbench.infrastructure.postgres import WriteDatabase

POLICY = ToolPolicy.TENANT_METADATA_WRITE

READ_POLICY = ToolPolicy.TENANT_LOCK_MANAGE

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
            identity_arguments = metadata_identity_arguments(principal)
            async with database.write_transaction() as transaction:
                row = await transaction.fetch_one(
                    CREATE_SQL,
                    (*identity_arguments, tenant_id, uuid4(), uuid4()),
                )
            raise_governed_denial(row)
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
            documents = stage_documents(changes)
            principal = identity_provider.request_principal(ctx.request_context.request)
            identity_arguments = metadata_identity_arguments(principal)
            async with database.write_transaction() as transaction:
                row = await transaction.fetch_one(
                    STAGE_SQL,
                    (
                        *identity_arguments,
                        tenant_id,
                        metadata_change_set_id,
                        expected_draft_revision,
                        Jsonb(documents),
                        uuid4(),
                    ),
                )
            raise_governed_denial(row)
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
                        record_count=staged_record_count(dataset_counts, dataset),
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
                        *metadata_identity_arguments(principal),
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
            raise_governed_denial(row)
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
            "KiB after schema normalization. chunk_sha256 covers the exact canonical request list. "
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
                description="SHA-256 of this chunk's exact canonical request record list.",
            ),
        ],
        schema_version: Literal["1.0"] = "1.0",
    ) -> PutMetadataStageChunkResult:
        del schema_version
        try:
            normalized = stage_document(StageChange(dataset=dataset, records=records))
            encoded = json.dumps(
                normalized,
                ensure_ascii=False,
                separators=(",", ":"),
                sort_keys=True,
            ).encode("utf-8")
            if len(encoded) > MAX_STAGE_CHUNK_BYTES:
                raise InvalidRequestError("The Stage chunk exceeds the bounded byte limit.")
            if canonical_records_sha256(records) != chunk_sha256:
                raise InvalidRequestError(
                    "The Stage chunk SHA-256 does not match its request records."
                )
            principal = identity_provider.request_principal(ctx.request_context.request)
            async with database.write_transaction() as transaction:
                row = await transaction.fetch_one(
                    _PUT_STAGE_CHUNK_SQL,
                    (
                        *metadata_identity_arguments(principal),
                        tenant_id,
                        metadata_change_set_id,
                        stage_batch_id,
                        dataset,
                        chunk_index,
                        chunk_sha256,
                        Jsonb(normalized),
                    ),
                )
            raise_governed_denial(row)
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
                        *metadata_identity_arguments(principal),
                        tenant_id,
                        metadata_change_set_id,
                        stage_batch_id,
                        expected_draft_revision,
                        uuid4(),
                    ),
                )
            raise_governed_denial(row)
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
                    GET_SQL,
                    (
                        *metadata_identity_arguments(principal),
                        tenant_id,
                        metadata_change_set_id,
                    ),
                )
            raise_governed_denial(row)
            assert row is not None
            counts = [
                MetadataChangeSetDatasetCount(
                    dataset=name,
                    record_count=len(row[DOCUMENT_COLUMN_BY_DATASET[name]]),
                )
                for name in CHANGE_SET_DATASETS
            ]
            records = read_document(row, dataset) if dataset is not None else None
            return GetMetadataChangeSetResult(
                tenant_id=tenant_id,
                metadata_change_set_id=metadata_change_set_id,
                status=row["metadata_change_set_status"],
                draft_revision=row["draft_revision"],
                candidate_digest=row["candidate_digest"],
                validation_outcome=bounded_validation_outcome(row["validation_outcome"]),
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
            "Return bounded counts and SHA-256 fingerprints for the caller's exact Metadata "
            "Change Set revision without returning pending records. Use this to verify Stage "
            "transport, including active drafts that failed validation."
        ),
        annotations=_annotations(read_only=True, destructive=False, idempotent=True),
        meta={"gds/toolPolicy": READ_POLICY.value},
        structured_output=True,
    )
    async def get_metadata_change_set_fingerprint(
        ctx: Context[None],
        tenant_id: Annotated[int, Field(gt=0, le=9_223_372_036_854_775_807)],
        metadata_change_set_id: UUID,
        schema_version: Literal["1.0"] = "1.0",
    ) -> GetMetadataChangeSetFingerprintResult:
        del schema_version
        try:
            principal = identity_provider.request_principal(ctx.request_context.request)
            async with database.write_transaction() as transaction:
                row = await transaction.fetch_one(
                    GET_SQL,
                    (
                        *metadata_identity_arguments(principal),
                        tenant_id,
                        metadata_change_set_id,
                    ),
                )
            raise_governed_denial(row)
            assert row is not None
            datasets = [
                MetadataChangeSetDatasetFingerprint(
                    dataset=name,
                    record_count=len(records),
                    sha256=canonical_records_sha256(records),
                )
                for name in CHANGE_SET_DATASETS
                for records in [read_document(row, name)]
            ]
            fingerprint_document = {
                "area": "metadata",
                "datasets": [item.model_dump(mode="json") for item in datasets],
                "fingerprint_version": "1.0",
            }
            fingerprint = hashlib.sha256(
                json.dumps(
                    fingerprint_document,
                    ensure_ascii=False,
                    separators=(",", ":"),
                    sort_keys=True,
                ).encode("utf-8")
            ).hexdigest()
            return GetMetadataChangeSetFingerprintResult(
                tenant_id=tenant_id,
                metadata_change_set_id=metadata_change_set_id,
                status=row["metadata_change_set_status"],
                draft_revision=row["draft_revision"],
                dataset_count=len(datasets),
                record_count=sum(item.record_count for item in datasets),
                datasets=datasets,
                fingerprint=fingerprint,
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
        "get_metadata_change_set_fingerprint",
        policy=READ_POLICY,
        summarize_input=_tenant_audit,
        retain_arguments={
            "tenant_id",
            "metadata_change_set_id",
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
                validation, persisted = await validate_and_persist(
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
                error_groups=metadata_error_groups(validation),
                errors=metadata_error_examples(validation),
                errors_truncated=(len(validation.issues) > MAX_AGENT_VALIDATION_ERROR_EXAMPLES),
                action_review=action_review(validation),
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
            identity_arguments = metadata_identity_arguments(principal)
            async with database.write_transaction() as transaction:
                validation, persisted = await validate_and_persist(
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
                        APPLY_SQL,
                        (
                            *identity_arguments,
                            tenant_id,
                            metadata_change_set_id,
                            expected_draft_revision,
                            validation.candidate_digest,
                            uuid4(),
                        ),
                    )
                    raise_governed_denial(applied_row)
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
                error_groups=metadata_error_groups(validation),
                errors=metadata_error_examples(validation),
                errors_truncated=(len(validation.issues) > MAX_AGENT_VALIDATION_ERROR_EXAMPLES),
                action_review=action_review(validation),
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
                    ARCHIVE_SQL,
                    (
                        *metadata_identity_arguments(principal),
                        tenant_id,
                        metadata_change_set_id,
                        expected_draft_revision,
                        uuid4(),
                    ),
                )
            raise_governed_denial(row)
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
