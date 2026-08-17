"""Governed Model Change Set drafting and future-graph validation."""

# Pyright cannot see that @server.tool registers these nested handlers.
# pyright: reportUnusedFunction=false

from __future__ import annotations

import json
from collections.abc import Mapping
from datetime import datetime
from typing import Annotated, Any, Literal, LiteralString, cast
from uuid import UUID, uuid4

from mcp.server.mcpserver import Context, MCPServer
from psycopg.types.json import Jsonb
from pydantic import Field

from gds_etl_workbench.adapters.auth.identity import AuthenticationError, IdentityProvider
from gds_etl_workbench.adapters.mcp.tool_audit import ToolCallAuditMiddleware
from gds_etl_workbench.application.authorization import AuthorizationService, ResolvedPrincipal
from gds_etl_workbench.domain.authorization import RequestPrincipal, ToolPolicy
from gds_etl_workbench.domain.errors import (
    AuthorizationDeniedError,
    CandidateDigestConflictError,
    DraftRevisionConflictError,
    InvalidRequestError,
    ModelChangeSetNotActiveError,
    ModelChangeSetNotFoundError,
    ModelChangeSetNotValidatedError,
    WorkbenchError,
)
from gds_etl_workbench.domain.modeling_records import normalize_model_key_value
from gds_etl_workbench.infrastructure.postgres import WriteDatabase, WriteTransaction
from gds_etl_workbench.tools.catalog.visibility import VISIBLE_OBJECTS_CTE
from gds_etl_workbench.tools.modeling.common import ModelReadContext
from gds_etl_workbench.tools.snapshots.model.contracts import (
    DATASETS_BY_NAME,
    ModelDataset,
)
from gds_etl_workbench.tools.snapshots.model.selection import build_model_snapshot

from .action_review import DatasetActionReview
from .common import ChangeSetContractModel as ContractModel
from .common import change_set_annotations as _annotations
from .model_apply import ModelMaterializer
from .model_validation import (
    ModelValidationIssue,
    PhysicalModelScope,
    ValidatedModelChangeSet,
    validate_future_graph,
    validate_staged_records,
)

POLICY = ToolPolicy.TENANT_MODEL_WRITE
READ_POLICY = ToolPolicy.TENANT_READ

SECTION_COLUMN_BY_DATASET: dict[str, str] = {
    name: f"{definition.section}_document" for name, definition in DATASETS_BY_NAME.items()
}
SECTION_COLUMNS = (
    "model_scope_document",
    "profiling_document",
    "analysis_document",
    "assertion_document",
    "conceptual_document",
    "logical_document",
    "dimensional_document",
    "mapping_document",
)

_MODEL_CONTEXT_FOR_UPDATE_SQL: LiteralString = """
SELECT model_id,
       tenant_id,
       model_name,
       model_revision
  FROM model.model
 WHERE model_id = %s
   AND is_active
 FOR SHARE
"""

_MODEL_PHYSICAL_SCOPE_SQL: LiteralString = f"""
{VISIBLE_OBJECTS_CTE}
SELECT model_tenant.tenant_code AS model_tenant_code,
       scoped_tenant.tenant_code,
       system.system_code,
       connection.connection_code,
       object.object_schema,
       object.object_name,
       attribute.attribute_name
  FROM requested_tenant
  JOIN core.tenant AS model_tenant
    ON model_tenant.tenant_id = requested_tenant.tenant_id
   AND model_tenant.is_active
  LEFT JOIN visible_objects
    ON TRUE
  LEFT JOIN core.object AS object
    ON object.object_id = visible_objects.object_id
   AND object.is_active
  LEFT JOIN core.connection AS connection
    ON connection.connection_id = object.connection_id
   AND connection.is_active
  LEFT JOIN core.tenant AS scoped_tenant
    ON scoped_tenant.tenant_id = connection.tenant_id
   AND scoped_tenant.is_active
  LEFT JOIN core.system AS system
    ON system.system_id = connection.system_id
   AND system.is_active
  LEFT JOIN core.attribute AS attribute
    ON attribute.object_id = object.object_id
   AND attribute.is_active
"""

_OTHER_MODEL_NAMES_SQL: LiteralString = """
SELECT model_name
  FROM model.model
 WHERE tenant_id = %s
   AND model_id <> %s
   AND is_active
"""

_ACTIVE_SYSTEM_CODES_SQL: LiteralString = """
SELECT system_code
  FROM core.system
 WHERE is_active
"""

_FIND_ONGOING_SQL: LiteralString = """
SELECT model_change_set_id,
       model_change_set_status,
       draft_revision,
       created_time,
       expires_time
  FROM mcp.model_change_set
 WHERE model_id = %s
   AND created_by_principal_id = %s
   AND model_change_set_status IN ('active', 'validated')
   AND expires_time > CURRENT_TIMESTAMP
 ORDER BY created_time DESC
 LIMIT 1
 FOR UPDATE
"""

_EXPIRE_OWNED_SQL: LiteralString = """
UPDATE mcp.model_change_set
   SET model_change_set_status = 'expired',
       terminal_time = CURRENT_TIMESTAMP,
       last_activity_time = CURRENT_TIMESTAMP
 WHERE model_id = %s
   AND created_by_principal_id = %s
   AND model_change_set_status IN ('active', 'validated')
   AND expires_time <= CURRENT_TIMESTAMP
RETURNING model_change_set_id, draft_revision
"""

_CREATE_SQL: LiteralString = """
INSERT INTO mcp.model_change_set (
    model_change_set_id,
    model_id,
    model_change_set_status,
    base_model_revision,
    base_source_context_digest,
    base_assertion_digest,
    base_policy_digest,
    created_by_principal_id,
    correlation_id
)
SELECT %s,
       model.model_id,
       'active',
       model.model_revision,
       repeat(md5('scope:' || model.model_id::TEXT || ':' || model.model_revision::TEXT), 2),
       repeat(md5('assertion:' || model.model_id::TEXT || ':' || model.model_revision::TEXT), 2),
       repeat(md5(
           'policy:' || model.model_id::TEXT || ':' ||
           coalesce(model.silver_model_naming_template::TEXT, '') || ':' ||
           coalesce(model.gold_model_naming_template::TEXT, '')
       ), 2),
       %s,
       %s
  FROM model.model
 WHERE model.model_id = %s
RETURNING model_change_set_id,
          model_change_set_status,
          draft_revision,
          created_time,
          expires_time
"""

_INSERT_EVENT_SQL: LiteralString = """
INSERT INTO mcp.model_change_set_event (
    model_change_set_id,
    model_id,
    event_sequence,
    event_type,
    draft_revision,
    section_name,
    action_count,
    outcome,
    event_metadata,
    correlation_id
)
SELECT %s,
       %s,
       coalesce(max(event.event_sequence), 0) + 1,
       %s,
       %s,
       %s,
       %s,
       %s,
       %s,
       %s
  FROM mcp.model_change_set_event AS event
 WHERE event.model_change_set_id = %s
RETURNING model_change_set_event_id
"""

_GET_FOR_UPDATE_SQL: LiteralString = """
SELECT model_change_set.*
  FROM mcp.model_change_set AS model_change_set
 WHERE model_change_set.model_change_set_id = %s
   AND model_change_set.model_id = %s
 FOR UPDATE
"""

_GET_SQL: LiteralString = """
SELECT model_change_set.*
  FROM mcp.model_change_set AS model_change_set
 WHERE model_change_set.model_change_set_id = %s
   AND model_change_set.model_id = %s
"""

_STAGE_SQL: LiteralString = """
UPDATE mcp.model_change_set
   SET model_scope_document = %s,
       profiling_document = %s,
       analysis_document = %s,
       assertion_document = %s,
       conceptual_document = %s,
       logical_document = %s,
       dimensional_document = %s,
       mapping_document = %s,
       model_change_set_status = 'active',
       draft_revision = draft_revision + 1,
       candidate_digest = NULL,
       validation_outcome = NULL,
       validated_time = NULL,
       last_activity_time = CURRENT_TIMESTAMP,
       expires_time = CURRENT_TIMESTAMP + INTERVAL '4 hours'
 WHERE model_change_set_id = %s
RETURNING draft_revision, model_change_set_status, expires_time
"""

_RECORD_VALIDATION_SQL: LiteralString = """
UPDATE mcp.model_change_set
   SET model_change_set_status = %s,
       candidate_digest = %s,
       validation_outcome = %s,
       validated_time = CASE WHEN %s THEN CURRENT_TIMESTAMP ELSE NULL END,
       last_activity_time = CURRENT_TIMESTAMP,
       expires_time = CURRENT_TIMESTAMP + INTERVAL '4 hours'
 WHERE model_change_set_id = %s
RETURNING model_change_set_status,
          draft_revision,
          candidate_digest,
          validated_time,
          expires_time
"""

_ADVANCE_MODEL_REVISION_SQL: LiteralString = """
UPDATE model.model
   SET model_revision = model_revision + %s,
       updated_time = CURRENT_TIMESTAMP,
       updated_by = CURRENT_USER
 WHERE model_id = %s
   AND model_revision = %s
RETURNING model_revision
"""

_MARK_APPLIED_SQL: LiteralString = """
UPDATE mcp.model_change_set
   SET model_change_set_status = 'applied',
       applied_time = CURRENT_TIMESTAMP,
       terminal_time = CURRENT_TIMESTAMP,
       last_activity_time = CURRENT_TIMESTAMP
 WHERE model_change_set_id = %s
RETURNING model_change_set_status, applied_time
"""

_ARCHIVE_SQL: LiteralString = """
UPDATE mcp.model_change_set
   SET model_change_set_status = 'discarded',
       terminal_time = CURRENT_TIMESTAMP,
       last_activity_time = CURRENT_TIMESTAMP
 WHERE model_change_set_id = %s
   AND model_id = %s
   AND model_change_set_status IN ('active', 'validated')
RETURNING draft_revision, terminal_time
"""


class StageModelChange(ContractModel):
    dataset: ModelDataset
    records: Annotated[list[dict[str, object]], Field(max_length=20_000)]


class ModelDatasetCount(ContractModel):
    dataset: ModelDataset
    record_count: int = Field(ge=0)


class ModelValidationError(ContractModel):
    code: str
    dataset: str
    record_number: int | None
    fields: tuple[str, ...]
    message: str


class ModelChangeSetActionKey(ContractModel):
    action: Literal["insert", "update", "deactivate", "reactivate", "no_change"]
    natural_key: dict[str, str | int | bool | None]


class ModelChangeSetActionReview(ContractModel):
    dataset: ModelDataset
    insert_count: int = Field(ge=0)
    update_count: int = Field(ge=0)
    deactivate_count: int = Field(ge=0)
    reactivate_count: int = Field(ge=0)
    no_change_count: int = Field(ge=0)
    keys: tuple[ModelChangeSetActionKey, ...] = Field(max_length=100)
    keys_truncated: bool


class CreateModelChangeSetResult(ContractModel):
    schema_version: Literal["1.0"] = "1.0"
    model_id: int = Field(gt=0)
    model_change_set_id: UUID
    created: bool
    status: Literal["active", "validated"]
    draft_revision: int = Field(gt=0)
    created_at: datetime
    expires_at: datetime


class StageModelChangeSetResult(ContractModel):
    schema_version: Literal["1.0"] = "1.0"
    model_id: int = Field(gt=0)
    model_change_set_id: UUID
    staged: Literal[True] = True
    datasets: tuple[ModelDatasetCount, ...] = Field(min_length=1, max_length=19)
    draft_revision: int = Field(gt=0)
    status: Literal["active"] = "active"
    expires_at: datetime


class GetModelChangeSetResult(ContractModel):
    schema_version: Literal["1.0"] = "1.0"
    model_id: int = Field(gt=0)
    model_change_set_id: UUID
    status: Literal["active", "validated", "applied", "expired", "discarded", "superseded"]
    draft_revision: int = Field(gt=0)
    candidate_digest: str | None
    validation_outcome: dict[str, object] | None
    dataset_counts: tuple[ModelDatasetCount, ...]
    dataset: ModelDataset | None
    records: Annotated[list[dict[str, object]], Field(max_length=20_000)] | None
    created_at: datetime
    last_activity_at: datetime
    expires_at: datetime
    validated_at: datetime | None
    applied_at: datetime | None
    terminal_at: datetime | None


class ValidateModelChangeSetResult(ContractModel):
    schema_version: Literal["1.0"] = "1.0"
    model_id: int = Field(gt=0)
    model_change_set_id: UUID
    valid: bool
    phase: str
    status: Literal["active", "validated"]
    draft_revision: int = Field(gt=0)
    candidate_digest: str | None
    staged_record_count: int = Field(ge=0)
    error_count: int = Field(ge=0)
    errors: tuple[ModelValidationError, ...]
    action_review: tuple[ModelChangeSetActionReview, ...]
    validated_at: datetime | None
    expires_at: datetime


class ApplyModelChangeSetResult(ContractModel):
    schema_version: Literal["1.0"] = "1.0"
    model_id: int = Field(gt=0)
    model_change_set_id: UUID
    applied: Literal[True] = True
    status: Literal["applied"] = "applied"
    draft_revision: int = Field(gt=0)
    candidate_digest: str
    action_count: int = Field(ge=0)
    model_revision: int = Field(gt=0)
    applied_at: datetime


class ArchiveModelChangeSetResult(ContractModel):
    schema_version: Literal["1.0"] = "1.0"
    model_id: int = Field(gt=0)
    model_change_set_id: UUID
    archived: Literal[True] = True
    status: Literal["archived"] = "archived"
    draft_revision: int = Field(gt=0)
    archived_at: datetime


class ModelChangeSetToolError(Exception):
    """A bounded Change Set failure safe for MCP serialization."""


def register_model_change_set_tools(
    server: MCPServer[None],
    *,
    database: WriteDatabase,
    identity_provider: IdentityProvider,
    authorizer: AuthorizationService,
    audit: ToolCallAuditMiddleware,
) -> None:
    @server.tool(
        description=(
            "Create or resume the current Principal's governed Model Change Set. A "
            "caller-owned Tenant Lock is required."
        ),
        annotations=_annotations(read_only=False, idempotent=True),
        meta={"gds/toolPolicy": POLICY.value},
        structured_output=True,
    )
    async def create_model_change_set(
        ctx: Context[None],
        model_id: Annotated[int, Field(gt=0)],
        schema_version: Literal["1.0"] = "1.0",
    ) -> CreateModelChangeSetResult:
        del schema_version
        try:
            request_principal = identity_provider.request_principal(ctx.request_context.request)
            async with database.write_transaction() as transaction:
                model, principal = await _authorize_model(
                    transaction,
                    authorizer=authorizer,
                    request_principal=request_principal,
                    model_id=model_id,
                    policy=POLICY,
                )
                if principal.principal_id is None:
                    raise AuthorizationDeniedError()
                expired = await transaction.fetch_all(
                    _EXPIRE_OWNED_SQL,
                    (model.model_id, principal.principal_id),
                )
                for expired_row in expired:
                    expired_correlation_id = uuid4()
                    await _insert_event(
                        transaction,
                        change_set_id=expired_row["model_change_set_id"],
                        model_id=model.model_id,
                        event_type="expired",
                        draft_revision=expired_row["draft_revision"],
                        section=None,
                        action_count=0,
                        outcome="expired",
                        metadata={},
                        correlation_id=expired_correlation_id,
                    )
                row = await transaction.fetch_one(
                    _FIND_ONGOING_SQL,
                    (model.model_id, principal.principal_id),
                )
                created = row is None
                if row is None:
                    change_set_id = uuid4()
                    correlation_id = uuid4()
                    row = await transaction.fetch_one(
                        _CREATE_SQL,
                        (
                            change_set_id,
                            principal.principal_id,
                            correlation_id,
                            model.model_id,
                        ),
                    )
                    assert row is not None
                    await _insert_event(
                        transaction,
                        change_set_id=change_set_id,
                        model_id=model.model_id,
                        event_type="created",
                        draft_revision=row["draft_revision"],
                        section=None,
                        action_count=0,
                        outcome="created",
                        metadata={},
                        correlation_id=correlation_id,
                    )
            assert row is not None
            return CreateModelChangeSetResult(
                model_id=model_id,
                model_change_set_id=row["model_change_set_id"],
                created=created,
                status=row["model_change_set_status"],
                draft_revision=row["draft_revision"],
                created_at=row["created_time"],
                expires_at=row["expires_time"],
            )
        except AuthenticationError as error:
            raise ModelChangeSetToolError(f"{error.public_code}: {error.message}") from None
        except WorkbenchError as error:
            raise ModelChangeSetToolError(f"{error.code}: {error.message}") from None
        except Exception:
            raise ModelChangeSetToolError(
                "internal_error: The operation could not be completed."
            ) from None

    audit.register_tool(
        "create_model_change_set",
        policy=POLICY,
        summarize_input=_audit_model_input,
        retain_arguments={"model_id", "schema_version"},
    )

    @server.tool(
        description=(
            "Replace one or more complete pending Model datasets. Records use the exact "
            "ID-free schemas returned by describe_model_dataset."
        ),
        annotations=_annotations(read_only=False, idempotent=False),
        meta={"gds/toolPolicy": POLICY.value},
        structured_output=True,
    )
    async def stage_model_change_set(
        ctx: Context[None],
        model_id: Annotated[int, Field(gt=0)],
        model_change_set_id: UUID,
        expected_draft_revision: Annotated[int, Field(gt=0)],
        changes: Annotated[list[StageModelChange], Field(min_length=1, max_length=19)],
        schema_version: Literal["1.0"] = "1.0",
    ) -> StageModelChangeSetResult:
        del schema_version
        try:
            staged = _validate_stage_changes(changes)
            request_principal = identity_provider.request_principal(ctx.request_context.request)
            correlation_id = uuid4()
            async with database.write_transaction() as transaction:
                model, principal = await _authorize_model(
                    transaction,
                    authorizer=authorizer,
                    request_principal=request_principal,
                    model_id=model_id,
                    policy=POLICY,
                )
                row = await _owned_change_set(
                    transaction,
                    change_set_id=model_change_set_id,
                    model_id=model.model_id,
                    principal=principal,
                    for_update=True,
                )
                _require_mutable(row)
                if row["draft_revision"] != expected_draft_revision:
                    raise DraftRevisionConflictError(row["draft_revision"])
                documents = _documents(row)
                for dataset, records in staged.items():
                    section = DATASETS_BY_NAME[dataset].section
                    documents[section][dataset] = records
                _validate_document_bounds(documents)
                updated = await transaction.fetch_one(
                    _STAGE_SQL,
                    (
                        *(
                            Jsonb(documents[column.removesuffix("_document")])
                            for column in SECTION_COLUMNS
                        ),
                        model_change_set_id,
                    ),
                )
                assert updated is not None
                sections = sorted({DATASETS_BY_NAME[dataset].section for dataset in staged})
                await _insert_event(
                    transaction,
                    change_set_id=model_change_set_id,
                    model_id=model.model_id,
                    event_type="section_put",
                    draft_revision=updated["draft_revision"],
                    section=sections[0] if len(sections) == 1 else None,
                    action_count=sum(len(records) for records in staged.values()),
                    outcome="staged",
                    metadata={"datasets": sorted(staged)},
                    correlation_id=correlation_id,
                )
            return StageModelChangeSetResult(
                model_id=model_id,
                model_change_set_id=model_change_set_id,
                datasets=tuple(
                    ModelDatasetCount(
                        dataset=cast(ModelDataset, dataset), record_count=len(records)
                    )
                    for dataset, records in staged.items()
                ),
                draft_revision=updated["draft_revision"],
                expires_at=updated["expires_time"],
            )
        except AuthenticationError as error:
            raise ModelChangeSetToolError(f"{error.public_code}: {error.message}") from None
        except WorkbenchError as error:
            raise ModelChangeSetToolError(f"{error.code}: {error.message}") from None
        except Exception:
            raise ModelChangeSetToolError(
                "internal_error: The operation could not be completed."
            ) from None

    audit.register_tool(
        "stage_model_change_set",
        policy=POLICY,
        summarize_input=_audit_stage_input,
        retain_arguments={
            "model_id",
            "model_change_set_id",
            "expected_draft_revision",
            "schema_version",
        },
    )

    @server.tool(
        description=("Get Model Change Set counts, or one selected pending ID-free dataset."),
        annotations=_annotations(read_only=True, idempotent=True),
        meta={"gds/toolPolicy": READ_POLICY.value},
        structured_output=True,
    )
    async def get_model_change_set(
        ctx: Context[None],
        model_id: Annotated[int, Field(gt=0)],
        model_change_set_id: UUID,
        dataset: ModelDataset | None = None,
        schema_version: Literal["1.0"] = "1.0",
    ) -> GetModelChangeSetResult:
        del schema_version
        try:
            request_principal = identity_provider.request_principal(ctx.request_context.request)
            async with database.write_transaction() as transaction:
                model, principal = await _authorize_model(
                    transaction,
                    authorizer=authorizer,
                    request_principal=request_principal,
                    model_id=model_id,
                    policy=READ_POLICY,
                )
                row = await _owned_change_set(
                    transaction,
                    change_set_id=model_change_set_id,
                    model_id=model.model_id,
                    principal=principal,
                    for_update=False,
                )
            pending = _pending_datasets(row)
            return GetModelChangeSetResult(
                model_id=model_id,
                model_change_set_id=model_change_set_id,
                status=row["model_change_set_status"],
                draft_revision=row["draft_revision"],
                candidate_digest=row["candidate_digest"],
                validation_outcome=row["validation_outcome"],
                dataset_counts=tuple(
                    ModelDatasetCount(dataset=cast(ModelDataset, name), record_count=len(records))
                    for name, records in sorted(pending.items())
                ),
                dataset=dataset,
                records=None if dataset is None else pending.get(dataset, []),
                created_at=row["created_time"],
                last_activity_at=row["last_activity_time"],
                expires_at=row["expires_time"],
                validated_at=row["validated_time"],
                applied_at=row["applied_time"],
                terminal_at=row["terminal_time"],
            )
        except AuthenticationError as error:
            raise ModelChangeSetToolError(f"{error.public_code}: {error.message}") from None
        except WorkbenchError as error:
            raise ModelChangeSetToolError(f"{error.code}: {error.message}") from None
        except Exception:
            raise ModelChangeSetToolError(
                "internal_error: The operation could not be completed."
            ) from None

    audit.register_tool(
        "get_model_change_set",
        policy=READ_POLICY,
        summarize_input=_audit_get_input,
        retain_arguments={"model_id", "model_change_set_id", "dataset", "schema_version"},
    )

    @server.tool(
        description=("Validate one exact Model Change Set draft against the applied future graph."),
        annotations=_annotations(read_only=False, idempotent=False),
        meta={"gds/toolPolicy": POLICY.value},
        structured_output=True,
    )
    async def validate_model_change_set(
        ctx: Context[None],
        model_id: Annotated[int, Field(gt=0)],
        model_change_set_id: UUID,
        expected_draft_revision: Annotated[int, Field(gt=0)],
        schema_version: Literal["1.0"] = "1.0",
    ) -> ValidateModelChangeSetResult:
        del schema_version
        try:
            request_principal = identity_provider.request_principal(ctx.request_context.request)
            correlation_id = uuid4()
            async with database.write_transaction() as transaction:
                model, principal = await _authorize_model(
                    transaction,
                    authorizer=authorizer,
                    request_principal=request_principal,
                    model_id=model_id,
                    policy=POLICY,
                )
                row = await _owned_change_set(
                    transaction,
                    change_set_id=model_change_set_id,
                    model_id=model.model_id,
                    principal=principal,
                    for_update=True,
                )
                _require_mutable(row)
                if row["draft_revision"] != expected_draft_revision:
                    raise DraftRevisionConflictError(row["draft_revision"])
                validation = await _validate_locked_change_set(transaction, model, row)
                outcome = _validation_outcome(validation)
                updated = await transaction.fetch_one(
                    _RECORD_VALIDATION_SQL,
                    (
                        "validated" if validation.valid else "active",
                        validation.candidate_digest if validation.valid else None,
                        Jsonb(outcome),
                        validation.valid,
                        model_change_set_id,
                    ),
                )
                assert updated is not None
                await _insert_event(
                    transaction,
                    change_set_id=model_change_set_id,
                    model_id=model.model_id,
                    event_type=("validated" if validation.valid else "validation_failed"),
                    draft_revision=row["draft_revision"],
                    section=None,
                    action_count=sum(len(records) for records in validation.records.values()),
                    outcome="valid" if validation.valid else "invalid",
                    metadata={
                        "phase": validation.phase,
                        "error_count": len(validation.issues),
                    },
                    correlation_id=correlation_id,
                )
            return ValidateModelChangeSetResult(
                model_id=model_id,
                model_change_set_id=model_change_set_id,
                valid=validation.valid,
                phase=validation.phase,
                status=updated["model_change_set_status"],
                draft_revision=updated["draft_revision"],
                candidate_digest=updated["candidate_digest"],
                staged_record_count=sum(len(records) for records in validation.records.values()),
                error_count=len(validation.issues),
                errors=tuple(_error(issue) for issue in validation.issues),
                action_review=_model_action_review(validation.action_review),
                validated_at=updated["validated_time"],
                expires_at=updated["expires_time"],
            )
        except AuthenticationError as error:
            raise ModelChangeSetToolError(f"{error.public_code}: {error.message}") from None
        except WorkbenchError as error:
            raise ModelChangeSetToolError(f"{error.code}: {error.message}") from None
        except Exception:
            raise ModelChangeSetToolError(
                "internal_error: The operation could not be completed."
            ) from None

    audit.register_tool(
        "validate_model_change_set",
        policy=POLICY,
        summarize_input=_audit_revision_input,
        retain_arguments={
            "model_id",
            "model_change_set_id",
            "expected_draft_revision",
            "schema_version",
        },
    )

    @server.tool(
        description=(
            "Atomically revalidate and apply one sealed Model Change Set to normalized "
            "Model tables, advancing the Model revision once when records are written."
        ),
        annotations=_annotations(read_only=False, destructive=True, idempotent=False),
        meta={"gds/toolPolicy": POLICY.value},
        structured_output=True,
    )
    async def apply_model_change_set(
        ctx: Context[None],
        model_id: Annotated[int, Field(gt=0)],
        model_change_set_id: UUID,
        expected_draft_revision: Annotated[int, Field(gt=0)],
        schema_version: Literal["1.0"] = "1.0",
    ) -> ApplyModelChangeSetResult:
        del schema_version
        try:
            request_principal = identity_provider.request_principal(ctx.request_context.request)
            correlation_id = uuid4()
            async with database.write_transaction() as transaction:
                model, principal = await _authorize_model(
                    transaction,
                    authorizer=authorizer,
                    request_principal=request_principal,
                    model_id=model_id,
                    policy=POLICY,
                )
                row = await _owned_change_set(
                    transaction,
                    change_set_id=model_change_set_id,
                    model_id=model.model_id,
                    principal=principal,
                    for_update=True,
                )
                if row["model_change_set_status"] != "validated":
                    raise ModelChangeSetNotValidatedError()
                if row["draft_revision"] != expected_draft_revision:
                    raise DraftRevisionConflictError(row["draft_revision"])
                validation = await _validate_locked_change_set(transaction, model, row)
                if not validation.valid:
                    raise CandidateDigestConflictError()
                assert validation.candidate_digest is not None
                if validation.candidate_digest != row["candidate_digest"]:
                    raise CandidateDigestConflictError()
                materializer = ModelMaterializer(
                    transaction=transaction,
                    model_id=model.model_id,
                    source_context_digest=row["base_source_context_digest"],
                )
                action_count = await materializer.apply(validation.records)
                revision = await transaction.fetch_one(
                    _ADVANCE_MODEL_REVISION_SQL,
                    (
                        1 if action_count > 0 else 0,
                        model.model_id,
                        model.model_revision,
                    ),
                )
                if revision is None:
                    raise InvalidRequestError("Model revision changed during apply.")
                applied = await transaction.fetch_one(
                    _MARK_APPLIED_SQL,
                    (model_change_set_id,),
                )
                assert applied is not None
                await _insert_event(
                    transaction,
                    change_set_id=model_change_set_id,
                    model_id=model.model_id,
                    event_type="applied",
                    draft_revision=row["draft_revision"],
                    section=None,
                    action_count=action_count,
                    outcome="applied",
                    metadata={"model_revision": revision["model_revision"]},
                    correlation_id=correlation_id,
                )
            return ApplyModelChangeSetResult(
                model_id=model_id,
                model_change_set_id=model_change_set_id,
                draft_revision=row["draft_revision"],
                candidate_digest=validation.candidate_digest,
                action_count=action_count,
                model_revision=revision["model_revision"],
                applied_at=applied["applied_time"],
            )
        except AuthenticationError as error:
            raise ModelChangeSetToolError(f"{error.public_code}: {error.message}") from None
        except WorkbenchError as error:
            raise ModelChangeSetToolError(f"{error.code}: {error.message}") from None
        except Exception:
            raise ModelChangeSetToolError(
                "internal_error: The operation could not be completed."
            ) from None

    audit.register_tool(
        "apply_model_change_set",
        policy=POLICY,
        summarize_input=_audit_revision_input,
        retain_arguments={
            "model_id",
            "model_change_set_id",
            "expected_draft_revision",
            "schema_version",
        },
    )

    @server.tool(
        description=(
            "End and retain your active or validated Model Change Set. A current "
            "Tenant Lock is not required; the Change Set is not deleted."
        ),
        annotations=_annotations(read_only=False, destructive=True, idempotent=False),
        meta={"gds/toolPolicy": READ_POLICY.value},
        structured_output=True,
    )
    async def archive_model_change_set(
        ctx: Context[None],
        model_id: Annotated[int, Field(gt=0)],
        model_change_set_id: UUID,
        expected_draft_revision: Annotated[int, Field(gt=0)],
        schema_version: Literal["1.0"] = "1.0",
    ) -> ArchiveModelChangeSetResult:
        del schema_version
        try:
            request_principal = identity_provider.request_principal(ctx.request_context.request)
            correlation_id = uuid4()
            async with database.write_transaction() as transaction:
                model, principal = await _authorize_model(
                    transaction,
                    authorizer=authorizer,
                    request_principal=request_principal,
                    model_id=model_id,
                    policy=READ_POLICY,
                )
                row = await _owned_change_set(
                    transaction,
                    change_set_id=model_change_set_id,
                    model_id=model.model_id,
                    principal=principal,
                    for_update=True,
                )
                _require_mutable(row)
                if row["draft_revision"] != expected_draft_revision:
                    raise DraftRevisionConflictError(row["draft_revision"])
                archived = await transaction.fetch_one(
                    _ARCHIVE_SQL,
                    (model_change_set_id, model.model_id),
                )
                assert archived is not None
                await _insert_event(
                    transaction,
                    change_set_id=model_change_set_id,
                    model_id=model.model_id,
                    event_type="discarded",
                    draft_revision=archived["draft_revision"],
                    section=None,
                    action_count=0,
                    outcome="archived",
                    metadata={},
                    correlation_id=correlation_id,
                )
            return ArchiveModelChangeSetResult(
                model_id=model_id,
                model_change_set_id=model_change_set_id,
                draft_revision=archived["draft_revision"],
                archived_at=archived["terminal_time"],
            )
        except AuthenticationError as error:
            raise ModelChangeSetToolError(f"{error.public_code}: {error.message}") from None
        except WorkbenchError as error:
            raise ModelChangeSetToolError(f"{error.code}: {error.message}") from None
        except Exception:
            raise ModelChangeSetToolError(
                "internal_error: The operation could not be completed."
            ) from None

    audit.register_tool(
        "archive_model_change_set",
        policy=READ_POLICY,
        summarize_input=_audit_revision_input,
        retain_arguments={
            "model_id",
            "model_change_set_id",
            "expected_draft_revision",
            "schema_version",
        },
    )

    @server.prompt(
        name="work_with_model_change_set",
        title="Work with a GDS Model",
        description="Intent-bounded workflow for one complete Model Change Set.",
    )
    def work_with_model_change_set(model_id: int) -> str:
        return (
            f"Work with Model ID {model_id} only to the user's requested boundary. "
            "Never advance beyond it. Read-only inspection: use get_model, focused "
            "layer/evidence reads, or get_model_change_set and stop without a lock. "
            "Local drafting: keep the Model Snapshot immutable, author only affected "
            "datasets and direct dependencies, and do not call MCP mutation tools. "
            "Before Create, Stage, Validate, or Apply, call check_tenant_lock and ask "
            "before acquire_tenant_lock. Call create_model_change_set only for explicit "
            "create/resume or when an approved Stage has no draft. If resumed, fetch "
            "the summary and every dataset with a nonzero count before replacing "
            "anything. Use describe_model_dataset only for datasets being authored. "
            "Show complete affected lists and ask before stage_model_change_set. "
            "Validate the latest revision and repair only the first failed phase. Show "
            "the authoritative action_review, then obtain fresh approval immediately "
            "before apply_model_change_set. Archive only when requested; archive needs "
            "no current lock. Release any lock this workflow acquired when it stops."
        )


async def _authorize_model(
    transaction: WriteTransaction,
    *,
    authorizer: AuthorizationService,
    request_principal: RequestPrincipal,
    model_id: int,
    policy: ToolPolicy,
) -> tuple[ModelReadContext, ResolvedPrincipal]:
    row = await transaction.fetch_one(_MODEL_CONTEXT_FOR_UPDATE_SQL, (model_id,))
    if row is None:
        raise InvalidRequestError("Model was not found.")
    authorization = await authorizer.authorize_tenant(
        transaction,
        request_principal,
        tenant_id=row["tenant_id"],
        policy=policy,
    )
    return (
        ModelReadContext(
            model_id=row["model_id"],
            tenant_id=row["tenant_id"],
            model_name=row["model_name"],
            model_revision=row["model_revision"],
        ),
        authorization.principal,
    )


async def _owned_change_set(
    transaction: WriteTransaction,
    *,
    change_set_id: UUID,
    model_id: int,
    principal: ResolvedPrincipal,
    for_update: bool,
) -> dict[str, Any]:
    row = await transaction.fetch_one(
        _GET_FOR_UPDATE_SQL if for_update else _GET_SQL,
        (change_set_id, model_id),
    )
    if row is None or row["created_by_principal_id"] != principal.principal_id:
        raise ModelChangeSetNotFoundError()
    return row


def _require_mutable(row: Mapping[str, Any]) -> None:
    if row["model_change_set_status"] not in ("active", "validated"):
        raise ModelChangeSetNotActiveError()
    if row["expires_time"] <= datetime.now(row["expires_time"].tzinfo):
        raise ModelChangeSetNotActiveError()


def _validate_stage_changes(
    changes: list[StageModelChange],
) -> dict[str, list[dict[str, object]]]:
    staged: dict[str, list[dict[str, object]]] = {}
    for change in changes:
        if change.dataset in staged:
            raise InvalidRequestError("Each Model dataset may be staged only once per call.")
        records, issues = validate_staged_records(change.dataset, change.records)
        if issues:
            raise InvalidRequestError(issues[0].message)
        staged[change.dataset] = [record.model_dump(mode="json") for record in records]
    if sum(len(records) for records in staged.values()) > 50_000:
        raise InvalidRequestError("A Model Change Set stage is limited to 50,000 records.")
    return staged


def _validate_document_bounds(
    documents: dict[str, dict[str, list[dict[str, object]]]],
) -> None:
    if sum(len(records) for section in documents.values() for records in section.values()) > 50_000:
        raise InvalidRequestError("A Model Change Set is limited to 50,000 pending records.")
    if any(
        len(
            json.dumps(
                section,
                ensure_ascii=False,
                separators=(",", ":"),
            ).encode("utf-8")
        )
        > 16 * 1024 * 1024
        for section in documents.values()
    ):
        raise InvalidRequestError("A Model Change Set section exceeds 16 MiB.")


def _documents(row: Mapping[str, Any]) -> dict[str, dict[str, list[dict[str, object]]]]:
    return {column.removesuffix("_document"): dict(row[column] or {}) for column in SECTION_COLUMNS}


def _pending_datasets(row: Mapping[str, Any]) -> dict[str, list[dict[str, object]]]:
    return {
        dataset: records
        for section in _documents(row).values()
        for dataset, records in section.items()
    }


async def _validate_locked_change_set(
    transaction: WriteTransaction,
    model: ModelReadContext,
    row: Mapping[str, Any],
) -> ValidatedModelChangeSet:
    if row["base_model_revision"] != model.model_revision:
        issue = ModelValidationIssue(
            code="stale_model_revision",
            dataset="model",
            record_number=None,
            fields=("model_revision",),
            message="Applied Model revision changed after this Change Set was created.",
        )
        return ValidatedModelChangeSet(
            records={},
            phase="model_revision",
            candidate_digest=None,
            issues=(issue,),
            action_review=(),
        )
    snapshot = await build_model_snapshot(transaction, model)
    physical_scope = await _load_physical_scope(transaction, model)
    return validate_future_graph(
        snapshot=snapshot,
        staged_documents=_pending_datasets(row),
        physical_scope=physical_scope,
    )


async def _load_physical_scope(
    transaction: WriteTransaction,
    model: ModelReadContext,
) -> PhysicalModelScope:
    rows = await transaction.fetch_all(_MODEL_PHYSICAL_SCOPE_SQL, (model.tenant_id,))
    if not rows:
        raise InvalidRequestError("Model physical Scope could not be resolved.")
    system_rows = await transaction.fetch_all(_ACTIVE_SYSTEM_CODES_SQL)
    other_model_rows = await transaction.fetch_all(
        _OTHER_MODEL_NAMES_SQL,
        (model.tenant_id, model.model_id),
    )
    objects: set[tuple[str, str, str, str, str]] = set()
    attributes: set[tuple[str, str, str, str, str, str]] = set()
    for physical in rows:
        object_values = tuple(
            physical[field]
            for field in (
                "tenant_code",
                "system_code",
                "connection_code",
                "object_schema",
                "object_name",
            )
        )
        if all(isinstance(value, str) for value in object_values):
            object_key = cast(
                tuple[str, str, str, str, str],
                tuple(normalize_model_key_value(value) for value in object_values),
            )
            objects.add(object_key)
            attribute_name = physical["attribute_name"]
            if isinstance(attribute_name, str):
                attributes.add((*object_key, normalize_model_key_value(attribute_name)))
    return PhysicalModelScope(
        model_tenant_code=rows[0]["model_tenant_code"],
        active_system_codes=frozenset(
            normalize_model_key_value(system["system_code"]) for system in system_rows
        ),
        objects=frozenset(objects),
        attributes=frozenset(attributes),
        other_model_names=frozenset(
            normalize_model_key_value(other_model["model_name"])
            for other_model in other_model_rows
        ),
    )


def _validation_outcome(validation: ValidatedModelChangeSet) -> dict[str, object]:
    return {
        "schema_version": "1.0",
        "valid": validation.valid,
        "phase": validation.phase,
        "staged_record_count": sum(len(records) for records in validation.records.values()),
        "error_count": len(validation.issues),
        "errors": [
            {
                "code": issue.code,
                "dataset": issue.dataset,
                "record_number": issue.record_number,
                "fields": list(issue.fields),
                "message": issue.message,
            }
            for issue in validation.issues
        ],
        "action_review": [summary.as_document() for summary in validation.action_review],
    }


def _error(issue: ModelValidationIssue) -> ModelValidationError:
    return ModelValidationError(
        code=issue.code,
        dataset=issue.dataset,
        record_number=issue.record_number,
        fields=issue.fields,
        message=issue.message,
    )


def _model_action_review(
    action_review: tuple[DatasetActionReview, ...],
) -> tuple[ModelChangeSetActionReview, ...]:
    return tuple(
        ModelChangeSetActionReview(
            dataset=cast(ModelDataset, summary.dataset),
            insert_count=summary.insert_count,
            update_count=summary.update_count,
            deactivate_count=summary.deactivate_count,
            reactivate_count=summary.reactivate_count,
            no_change_count=summary.no_change_count,
            keys=tuple(
                ModelChangeSetActionKey(
                    action=key.action,
                    natural_key=cast(dict[str, str | int | bool | None], key.natural_key),
                )
                for key in summary.keys
            ),
            keys_truncated=summary.keys_truncated,
        )
        for summary in action_review
    )


async def _insert_event(
    transaction: WriteTransaction,
    *,
    change_set_id: UUID,
    model_id: int,
    event_type: str,
    draft_revision: int,
    section: str | None,
    action_count: int,
    outcome: str,
    metadata: dict[str, object],
    correlation_id: UUID,
) -> None:
    await transaction.fetch_one(
        _INSERT_EVENT_SQL,
        (
            change_set_id,
            model_id,
            event_type,
            draft_revision,
            section,
            action_count,
            outcome,
            Jsonb(metadata),
            correlation_id,
            change_set_id,
        ),
    )


def _audit_model_input(arguments: Mapping[str, Any]) -> dict[str, str | int]:
    model_id = arguments.get("model_id")
    return {
        "schema_version": ("1.0" if arguments.get("schema_version", "1.0") == "1.0" else "invalid"),
        "model_id": model_id if type(model_id) is int and model_id > 0 else "invalid",
    }


def _audit_revision_input(arguments: Mapping[str, Any]) -> dict[str, str | int]:
    result = _audit_model_input(arguments)
    revision = arguments.get("expected_draft_revision")
    return {
        **result,
        "expected_draft_revision": (
            revision if type(revision) is int and revision > 0 else "invalid"
        ),
    }


def _audit_stage_input(arguments: Mapping[str, Any]) -> dict[str, str | int]:
    result = _audit_revision_input(arguments)
    changes = arguments.get("changes", [])
    return {
        **result,
        "dataset_count": (
            len(cast(list[object], changes)) if isinstance(changes, list) else "invalid"
        ),
    }


def _audit_get_input(arguments: Mapping[str, Any]) -> dict[str, str | int]:
    result = _audit_model_input(arguments)
    dataset = arguments.get("dataset")
    return {
        **result,
        "dataset": (
            dataset
            if dataset is None or isinstance(dataset, str) and dataset in DATASETS_BY_NAME
            else "invalid"
        )
        or "counts_only",
    }
