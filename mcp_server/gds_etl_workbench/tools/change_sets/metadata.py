"""Governed Metadata Change Set MCP tools and fixed database calls."""

# Pyright cannot see that @server.tool registers these nested handlers.
# pyright: reportUnusedFunction=false

from __future__ import annotations

import json
from collections.abc import Mapping
from datetime import datetime
from typing import Annotated, Any, Literal, LiteralString, cast
from uuid import UUID, uuid4

from mcp.server.mcpserver import Context, MCPServer
from mcp.types import ToolAnnotations
from psycopg.types.json import Jsonb
from pydantic import BaseModel, ConfigDict, Field

from gds_etl_workbench.adapters.auth.identity import AuthenticationError, IdentityProvider
from gds_etl_workbench.adapters.mcp.tool_audit import ToolCallAuditMiddleware
from gds_etl_workbench.application.authorization import AuthorizationService
from gds_etl_workbench.domain.authorization import ActorKind, RequestPrincipal, ToolPolicy
from gds_etl_workbench.domain.errors import (
    AuthorizationDeniedError,
    CandidateDigestConflictError,
    DraftRevisionConflictError,
    InvalidRequestError,
    MetadataChangeSetNotActiveError,
    MetadataChangeSetNotFoundError,
    MetadataChangeSetNotValidatedError,
    TenantLockedError,
    TenantLockRequiredError,
    TenantNotFoundError,
    WorkbenchError,
)
from gds_etl_workbench.domain.metadata_records import (
    AttributeRecord,
    CopyGroupControlRecord,
    CopyGroupRecord,
    CopyRecord,
    IngestionAttributeMappingRecord,
    IngestionObjectMappingRecord,
    MemberGroupRecord,
    ObjectRecord,
    ProcessGroupRecord,
    ProcessRecord,
)
from gds_etl_workbench.infrastructure.postgres import WriteDatabase, WriteTransaction
from gds_etl_workbench.tools.snapshots.metadata.contracts import DATASETS_BY_NAME
from gds_etl_workbench.tools.snapshots.metadata.get_metadata_snapshot import (
    select_snapshot_datasets,
)

from .validation import (
    MetadataChangeSetValidation,
    rows_from_snapshot,
    validate_metadata_documents,
)

POLICY = ToolPolicy.TENANT_METADATA_WRITE
READ_POLICY = ToolPolicy.TENANT_LOCK_MANAGE

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
       record_count,
       expires_time
  FROM mcp.stage_metadata_change_set(%s, %s, %s, %s, %s, %s, %s, %s, %s)
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


class ContractModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class CreateMetadataChangeSetResult(ContractModel):
    schema_version: Literal["1.0"] = "1.0"
    tenant_id: int = Field(gt=0, le=9_223_372_036_854_775_807)
    metadata_change_set_id: UUID
    created: bool
    status: Literal["active", "validated"]
    draft_revision: int = Field(gt=0)
    created_at: datetime
    expires_at: datetime


class SourceObjectChange(ContractModel):
    dataset: Literal["source_object"]
    records: Annotated[list[ObjectRecord], Field(max_length=50_000)]


class SourceAttributeChange(ContractModel):
    dataset: Literal["source_attribute"]
    records: Annotated[list[AttributeRecord], Field(max_length=50_000)]


class BronzeObjectChange(ContractModel):
    dataset: Literal["bronze_object"]
    records: Annotated[list[ObjectRecord], Field(max_length=50_000)]


class BronzeAttributeChange(ContractModel):
    dataset: Literal["bronze_attribute"]
    records: Annotated[list[AttributeRecord], Field(max_length=50_000)]


class SilverObjectChange(ContractModel):
    dataset: Literal["silver_object"]
    records: Annotated[list[ObjectRecord], Field(max_length=50_000)]


class SilverAttributeChange(ContractModel):
    dataset: Literal["silver_attribute"]
    records: Annotated[list[AttributeRecord], Field(max_length=50_000)]


class GoldObjectChange(ContractModel):
    dataset: Literal["gold_object"]
    records: Annotated[list[ObjectRecord], Field(max_length=50_000)]


class GoldAttributeChange(ContractModel):
    dataset: Literal["gold_attribute"]
    records: Annotated[list[AttributeRecord], Field(max_length=50_000)]


class IngestionObjectMappingChange(ContractModel):
    dataset: Literal["ingestion_object_mapping"]
    records: Annotated[list[IngestionObjectMappingRecord], Field(max_length=50_000)]


class IngestionAttributeMappingChange(ContractModel):
    dataset: Literal["ingestion_attribute_mapping"]
    records: Annotated[list[IngestionAttributeMappingRecord], Field(max_length=50_000)]


class CopyGroupChange(ContractModel):
    dataset: Literal["copy_group"]
    records: Annotated[list[CopyGroupRecord], Field(max_length=50_000)]


class MemberGroupChange(ContractModel):
    dataset: Literal["member_group"]
    records: Annotated[list[MemberGroupRecord], Field(max_length=50_000)]


class CopyGroupControlChange(ContractModel):
    dataset: Literal["copy_group_control"]
    records: Annotated[list[CopyGroupControlRecord], Field(max_length=50_000)]


class CopyChange(ContractModel):
    dataset: Literal["copy"]
    records: Annotated[list[CopyRecord], Field(max_length=50_000)]


class ProcessGroupChange(ContractModel):
    dataset: Literal["process_group"]
    records: Annotated[list[ProcessGroupRecord], Field(max_length=50_000)]


class ProcessChange(ContractModel):
    dataset: Literal["process"]
    records: Annotated[list[ProcessRecord], Field(max_length=50_000)]


type StageChange = Annotated[
    SourceObjectChange
    | SourceAttributeChange
    | BronzeObjectChange
    | BronzeAttributeChange
    | SilverObjectChange
    | SilverAttributeChange
    | GoldObjectChange
    | GoldAttributeChange
    | IngestionObjectMappingChange
    | IngestionAttributeMappingChange
    | CopyGroupChange
    | MemberGroupChange
    | CopyGroupControlChange
    | CopyChange
    | ProcessGroupChange
    | ProcessChange,
    Field(discriminator="dataset"),
]


class StageMetadataChangeSetResult(ContractModel):
    schema_version: Literal["1.0"] = "1.0"
    tenant_id: int = Field(gt=0, le=9_223_372_036_854_775_807)
    metadata_change_set_id: UUID
    dataset: str
    staged: Literal[True] = True
    record_count: int = Field(ge=0)
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
        tenant_argument="tenant_id",
    )

    @server.tool(
        description=(
            "Replace one complete pending Metadata Change Set dataset. Every item must "
            "be a full ID-free record matching the selected Snapshot dataset schema."
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
        change: StageChange,
        schema_version: Literal["1.0"] = "1.0",
    ) -> StageMetadataChangeSetResult:
        del schema_version
        try:
            records = _stage_document(change)
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
                        change.dataset,
                        Jsonb(records),
                        uuid4(),
                    ),
                )
            _raise_governed_denial(row)
            assert row is not None
            return StageMetadataChangeSetResult(
                tenant_id=tenant_id,
                metadata_change_set_id=metadata_change_set_id,
                dataset=change.dataset,
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
        "stage_metadata_change_set",
        policy=POLICY,
        summarize_input=_stage_audit,
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
            async with database.read_transaction() as transaction:
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
        tenant_argument="tenant_id",
    )

    @server.tool(
        description=(
            "Validate your complete pending Metadata Change Set against the shared "
            "Snapshot schemas, natural keys, uniqueness rules, and references."
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
        tenant_argument="tenant_id",
    )

    @server.prompt(
        name="work_with_metadata_change_set",
        title="Work with Tenant metadata",
        description="Safe, context-bounded workflow for one Tenant Metadata Change Set.",
    )
    def work_with_metadata_change_set(tenant_id: int) -> str:
        return (
            f"Work with Tenant ID {tenant_id}. First check_tenant_lock, then acquire it "
            "if unlocked. Create a fresh get_metadata_snapshot and download the ZIP. Read "
            "catalog.json first; search only needed lookup/rows files and read a dataset "
            "schema only when needed. Never load the whole ZIP into chat. Then call "
            "create_metadata_change_set. stage_metadata_change_set accepts one complete "
            "ID-free dataset list whose record schema is published in that tool's input "
            "schema; sending an empty list clears that pending dataset. Always pass the "
            "latest draft_revision. Use get_metadata_change_set without a dataset for "
            "counts, or with one dataset for its records. Validate, fix the reported first "
            "failed phase, and repeat. Apply only after review; apply revalidates inside the "
            "same transaction. Archive an abandoned draft, then release the Tenant Lock."
        )


def _identity_arguments(principal: RequestPrincipal) -> tuple[UUID, UUID, str]:
    if principal.entra_tenant_id is None or principal.entra_object_id is None:
        raise AuthorizationDeniedError()
    expected_type = "user" if principal.actor_kind is ActorKind.HUMAN else "service_principal"
    return principal.entra_tenant_id, principal.entra_object_id, expected_type


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
    if denial_code == "candidate_digest_conflict":
        raise CandidateDigestConflictError()
    if denial_code == "draft_revision_conflict":
        raise DraftRevisionConflictError(int(row["draft_revision"]))
    if denial_code == "invalid_request":
        raise InvalidRequestError()
    raise AuthorizationDeniedError()


def _stage_document(change: StageChange) -> list[dict[str, object]]:
    definition = DATASETS_BY_NAME[change.dataset]
    records = [record.model_dump(mode="json") for record in change.records]
    for field_name, expected_value in definition.fixed_values:
        if any(record[field_name] != expected_value for record in records):
            raise InvalidRequestError(
                f"Every {change.dataset} record must have {field_name}={expected_value}."
            )
    encoded = json.dumps(records, ensure_ascii=False, separators=(",", ":")).encode()
    if len(encoded) > 16_777_216:
        raise InvalidRequestError("The staged dataset exceeds 16 MiB.")
    return records


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
    raw_change = arguments.get("change")
    change: Mapping[str, Any] = (
        cast(Mapping[str, Any], raw_change) if isinstance(raw_change, Mapping) else {}
    )
    raw_dataset = change.get("dataset")
    summary["dataset"] = (
        raw_dataset
        if isinstance(raw_dataset, str) and raw_dataset in DATASETS_BY_NAME
        else "invalid"
    )
    raw_records = change.get("records")
    summary["record_count"] = (
        len(cast(list[object], raw_records)) if isinstance(raw_records, list) else "invalid"
    )
    raw_revision = arguments.get("expected_draft_revision")
    summary["expected_draft_revision"] = (
        raw_revision if type(raw_revision) is int and raw_revision > 0 else "invalid"
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


def _annotations(
    *,
    read_only: bool,
    destructive: bool,
    idempotent: bool,
) -> ToolAnnotations:
    return ToolAnnotations(
        read_only_hint=read_only,
        destructive_hint=destructive,
        idempotent_hint=idempotent,
        open_world_hint=False,
    )
