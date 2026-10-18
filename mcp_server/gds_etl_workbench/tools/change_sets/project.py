"""MCP transport for governed Project Change Sets."""

# Pyright cannot see that @server.tool registers these nested handlers.
# pyright: reportUnusedFunction=false

from __future__ import annotations

import hashlib
from collections.abc import Mapping
from datetime import datetime
from typing import Annotated, Any, Literal, LiteralString, cast
from uuid import UUID, uuid4

from mcp.server.mcpserver import Context, MCPServer
from psycopg.types.json import Jsonb
from pydantic import Field

from gds_etl_workbench.adapters.auth.identity import AuthenticationError, IdentityProvider
from gds_etl_workbench.adapters.mcp.annotations import closed_world_annotations as _annotations
from gds_etl_workbench.adapters.mcp.tool_audit import ToolCallAuditMiddleware
from gds_etl_workbench.application.authorization import (
    AuthorizationService,
    ResolvedPrincipal,
)
from gds_etl_workbench.application.change_sets.contracts import (
    MAX_AGENT_VALIDATION_ERROR_EXAMPLES,
    MAX_PROJECT_STAGE_CHUNK_BYTES,
    MAX_PROJECT_STAGE_FRAGMENT_BASE64_CHARACTERS,
    MAX_PROJECT_STAGE_PAYLOAD_BYTES,
    MAX_STAGE_CHUNK_RECORDS,
    MAX_STAGE_CHUNKS,
    SHA256_PATTERN,
    bounded_validation_outcome,
    canonical_records_bytes,
    canonical_records_sha256,
    decode_canonical_base64_fragment,
    stage_batch_sha256,
    stage_fingerprint_sha256,
)
from gds_etl_workbench.application.change_sets.project import (
    READ_SECTION_COLUMNS,
    ApplyProjectChangeSetResult,
    ArchiveProjectChangeSetResult,
    BeginProjectStageBatchResult,
    CommitProjectStageBatchResult,
    CreateProjectChangeSetResult,
    GetProjectChangeSetFingerprintResult,
    GetProjectChangeSetResult,
    ProjectChangeSetDatasetCount,
    ProjectChangeSetDatasetFingerprint,
    ProjectDatasetCount,
    ProjectStagePayloadMode,
    PutProjectStageChunkResult,
    StageProjectChange,
    StageProjectChangeSetResult,
    ValidateProjectChangeSetResult,
    decode_canonical_project_stage_payload,
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
)
from gds_etl_workbench.application.project_read import ProjectReadContext
from gds_etl_workbench.domain.authorization import RequestPrincipal, ToolPolicy
from gds_etl_workbench.domain.errors import (
    AuthorizationDeniedError,
    CandidateDigestConflictError,
    DraftRevisionConflictError,
    InvalidRequestError,
    ProjectChangeSetNotActiveError,
    ProjectChangeSetNotFoundError,
    ProjectChangeSetNotValidatedError,
    ProjectLockedError,
    StageBatchConflictError,
    StageBatchIncompleteError,
    StageBatchNotActiveError,
    StageBatchNotFoundError,
    StageChunkConflictError,
    WebManagedDatasetError,
    WorkbenchError,
)
from gds_etl_workbench.domain.snapshots.project import (
    CHANGE_SET_DATASETS_BY_NAME,
    DATASETS_BY_NAME,
    WEB_MANAGED_PROJECT_DATASETS,
    ProjectChangeSetDataset,
    ProjectDataset,
)
from gds_etl_workbench.infrastructure.postgres import (
    WriteDatabase,
    WriteTransaction,
)

POLICY = ToolPolicy.TENANT_PROJECT_WRITE

READ_POLICY = ToolPolicy.TENANT_READ

WRITE_SECTION_COLUMNS = READ_SECTION_COLUMNS

_PROJECT_CONTEXT_FOR_UPDATE_SQL: LiteralString = """
SELECT project_id,
       tenant_id,
       project_name,
       project_revision,
       is_locked
  FROM project.project
 WHERE project_id = %s
   AND is_active
 FOR SHARE
"""

_SERIALIZE_CREATE_SQL: LiteralString = """
SELECT pg_advisory_xact_lock(
    hashtextextended(
        'mcp.project_change_set:' || %s::TEXT || ':' || %s::TEXT,
        0
    )
)
"""

_DATABASE_TIME_SQL: LiteralString = """
SELECT clock_timestamp() AS current_time
"""

_LOCK_OWNED_CHANGE_SETS_SQL: LiteralString = """
SELECT change_set.project_change_set_id
  FROM mcp.project_change_set AS change_set
 WHERE change_set.project_id = %s
   AND change_set.created_by_principal_id = %s
   AND change_set.workflow_run_id IS NULL
   AND change_set.project_change_set_status IN ('active', 'validated')
 ORDER BY change_set.project_change_set_id
 FOR UPDATE
"""

_FIND_ONGOING_SQL: LiteralString = """
WITH operation_time AS MATERIALIZED (
    SELECT %s::TIMESTAMPTZ AS current_time
)
SELECT project_change_set_id,
       project_change_set_status,
       draft_revision,
       created_time,
       expires_time
  FROM mcp.project_change_set
 CROSS JOIN operation_time
 WHERE project_id = %s
   AND created_by_principal_id = %s
   AND workflow_run_id IS NULL
   AND project_change_set_status IN ('active', 'validated')
   AND expires_time > operation_time.current_time
 ORDER BY created_time DESC
 LIMIT 1
 FOR UPDATE
"""

_EXPIRE_OWNED_SQL: LiteralString = """
WITH operation_time AS MATERIALIZED (
    SELECT %s::TIMESTAMPTZ AS current_time
),
expired_change_set AS (
    UPDATE mcp.project_change_set AS change_set
       SET project_change_set_status = 'expired',
           terminal_time = operation_time.current_time
      FROM operation_time
     WHERE change_set.project_id = %s
       AND change_set.created_by_principal_id = %s
       AND change_set.workflow_run_id IS NULL
       AND change_set.project_change_set_status IN ('active', 'validated')
       AND change_set.expires_time <= operation_time.current_time
    RETURNING change_set.project_change_set_id,
              change_set.draft_revision,
              change_set.terminal_time
),
expired_batches AS (
    UPDATE mcp.project_stage_batch AS batch
       SET stage_batch_status = 'expired',
           terminal_time = expired_change_set.terminal_time
      FROM expired_change_set
     WHERE batch.project_change_set_id = expired_change_set.project_change_set_id
       AND batch.stage_batch_status = 'active'
    RETURNING batch.stage_batch_id
)
SELECT expired_change_set.project_change_set_id,
       expired_change_set.draft_revision
  FROM expired_change_set
"""

_EXPIRE_CHANGE_SET_SQL: LiteralString = """
WITH operation_time AS MATERIALIZED (
    SELECT %s::TIMESTAMPTZ AS current_time
),
expired_change_set AS (
    UPDATE mcp.project_change_set AS change_set
       SET project_change_set_status = 'expired',
           terminal_time = operation_time.current_time
      FROM operation_time
     WHERE change_set.project_change_set_id = %s
       AND change_set.project_id = %s
       AND change_set.created_by_principal_id = %s
       AND change_set.workflow_run_id IS NULL
       AND change_set.project_change_set_status IN ('active', 'validated')
       AND change_set.expires_time <= operation_time.current_time
       AND NOT EXISTS (SELECT 1 FROM project.project AS owner
                       WHERE owner.project_id = change_set.project_id AND owner.is_locked)
    RETURNING change_set.*
),
expired_batches AS (
    UPDATE mcp.project_stage_batch AS batch
       SET stage_batch_status = 'expired',
           terminal_time = expired_change_set.terminal_time
      FROM expired_change_set
     WHERE batch.project_change_set_id = expired_change_set.project_change_set_id
       AND batch.stage_batch_status = 'active'
    RETURNING batch.stage_batch_id
)
SELECT expired_change_set.*,
       (SELECT count(*) FROM expired_batches) AS expired_batch_count
  FROM expired_change_set
"""

_CREATE_SQL: LiteralString = """
WITH operation_time AS MATERIALIZED (
    SELECT %s::TIMESTAMPTZ AS current_time
)
INSERT INTO mcp.project_change_set (
    project_change_set_id,
    project_id,
    project_change_set_status,
    base_project_revision,
    base_source_context_digest,
    base_context_digest,
    base_policy_digest,
    created_by_principal_id,
    correlation_id,
    created_time,
    last_activity_time,
    expires_time
)
SELECT %s,
       project.project_id,
       'active',
       project.project_revision,
       repeat(md5('scope:' || project.project_id::TEXT || ':' ||
           project.project_revision::TEXT), 2),
       repeat(md5('context:' || project.project_id::TEXT || ':' ||
           project.project_revision::TEXT), 2),
       repeat(md5(
           'policy:' || jsonb_build_object(
               'project_id', project.project_id,
               'logical_entity_scd_type', project.logical_entity_scd_type,
               'dimensional_entity_scd_type', project.dimensional_entity_scd_type,
               'logical_coverage_threshold_percent', project.logical_coverage_threshold_percent,
               'dimensional_coverage_threshold_percent',
                   project.dimensional_coverage_threshold_percent,
               'logical_enforce_coverage_threshold', project.logical_enforce_coverage_threshold,
               'dimensional_enforce_coverage_threshold',
                   project.dimensional_enforce_coverage_threshold,
               'silver_model_naming_instructions',
                   project.silver_model_naming_instructions,
               'silver_model_audit_columns_template',
                   project.silver_model_audit_columns_template,
               'gold_model_naming_instructions',
                   project.gold_model_naming_instructions,
               'gold_model_technical_columns_template',
                   project.gold_model_technical_columns_template,
               'gold_model_audit_columns_template',
                   project.gold_model_audit_columns_template
           )::TEXT
       ), 2),
       %s,
       %s,
       operation_time.current_time,
       operation_time.current_time,
       operation_time.current_time + INTERVAL '4 hours'
  FROM project.project
 CROSS JOIN operation_time
 WHERE project.project_id = %s
RETURNING project_change_set_id,
          project_change_set_status,
          draft_revision,
          created_time,
          expires_time
"""

_INSERT_EVENT_SQL: LiteralString = """
INSERT INTO mcp.project_change_set_event (
    project_change_set_id,
    project_id,
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
  FROM mcp.project_change_set_event AS event
 WHERE event.project_change_set_id = %s
RETURNING project_change_set_event_id
"""

_GET_FOR_UPDATE_SQL: LiteralString = """
SELECT project_change_set.*,
       project_change_set.expires_time <= clock_timestamp() AS is_expired
  FROM mcp.project_change_set AS project_change_set
 WHERE project_change_set.project_change_set_id = %s
   AND project_change_set.project_id = %s
 FOR UPDATE
"""

_GET_SQL: LiteralString = """
SELECT project_change_set.*,
       project_change_set.expires_time <= clock_timestamp() AS is_expired
  FROM mcp.project_change_set AS project_change_set
 WHERE project_change_set.project_change_set_id = %s
   AND project_change_set.project_id = %s
"""

_STAGE_SQL: LiteralString = """
WITH operation_time AS MATERIALIZED (
    SELECT clock_timestamp() AS current_time
)
UPDATE mcp.project_change_set AS change_set
   SET project_input_scope_document = %s,
       profiling_document = %s,
       enrichment_document = %s,
       analysis_document = %s,
       context_document = %s,
       conceptual_document = %s,
       logical_document = %s,
       dimensional_document = %s,
       mapping_document = %s,
       code_generation_document = %s,
       validation_document = %s,
       project_change_set_status = 'active',
       draft_revision = draft_revision + 1,
       candidate_digest = NULL,
       validation_outcome = NULL,
       validated_time = NULL,
       last_activity_time = operation_time.current_time,
       expires_time = operation_time.current_time + INTERVAL '4 hours'
  FROM operation_time
 WHERE change_set.project_change_set_id = %s
   AND change_set.project_id = %s
   AND change_set.created_by_principal_id = %s
   AND change_set.workflow_run_id IS NULL
   AND change_set.project_change_set_status IN ('active', 'validated')
   AND change_set.expires_time > operation_time.current_time
   AND change_set.draft_revision IS NOT DISTINCT FROM %s
RETURNING change_set.draft_revision,
          change_set.project_change_set_status,
          change_set.expires_time
"""

_LOCK_ACTIVE_PROJECT_STAGE_BATCHES_SQL: LiteralString = """
SELECT batch.stage_batch_id
  FROM mcp.project_stage_batch AS batch
 WHERE batch.project_change_set_id = %s
   AND batch.dataset_name = %s
   AND batch.stage_batch_status = 'active'
 ORDER BY batch.stage_batch_id
 FOR UPDATE
"""

_EXPIRE_PROJECT_STAGE_BATCH_SQL: LiteralString = """
WITH operation_time AS MATERIALIZED (
    SELECT %s::TIMESTAMPTZ AS current_time
)
UPDATE mcp.project_stage_batch AS batch
   SET stage_batch_status = 'expired',
       terminal_time = operation_time.current_time
  FROM operation_time
 WHERE batch.project_change_set_id = %s
   AND batch.dataset_name = %s
   AND batch.stage_batch_status = 'active'
   AND batch.expires_time <= operation_time.current_time
RETURNING batch.stage_batch_id
"""

_LOCK_ACTIVE_PROJECT_STAGE_BATCH_BY_ID_SQL: LiteralString = """
SELECT batch.stage_batch_id
  FROM mcp.project_stage_batch AS batch
 WHERE batch.stage_batch_id = %s
   AND batch.project_change_set_id = %s
   AND batch.project_id = %s
   AND batch.stage_batch_status = 'active'
 FOR UPDATE
"""

_EXPIRE_PROJECT_STAGE_BATCH_BY_ID_SQL: LiteralString = """
WITH operation_time AS MATERIALIZED (
    SELECT %s::TIMESTAMPTZ AS current_time
)
UPDATE mcp.project_stage_batch AS batch
   SET stage_batch_status = 'expired',
       terminal_time = operation_time.current_time
  FROM operation_time
 WHERE batch.stage_batch_id = %s
   AND batch.project_change_set_id = %s
   AND batch.project_id = %s
   AND batch.stage_batch_status = 'active'
   AND batch.expires_time <= operation_time.current_time
RETURNING batch.stage_batch_id
"""

_FIND_PROJECT_STAGE_BATCH_SQL: LiteralString = """
SELECT batch.*,
       batch.expires_time <= clock_timestamp() AS is_expired,
       CASE batch.payload_mode
           WHEN 'json_fragments' THEN (
               SELECT count(*)
                 FROM mcp.project_stage_payload_chunk AS chunk
                WHERE chunk.stage_batch_id = batch.stage_batch_id
           )
           ELSE (
               SELECT count(*)
                 FROM mcp.project_stage_chunk AS chunk
                WHERE chunk.stage_batch_id = batch.stage_batch_id
           )
       END AS received_chunk_count
  FROM mcp.project_stage_batch AS batch
 WHERE batch.project_change_set_id = %s
   AND batch.dataset_name = %s
   AND batch.stage_batch_status = 'active'
 FOR UPDATE
"""

_CREATE_PROJECT_STAGE_BATCH_SQL: LiteralString = """
WITH operation_time AS MATERIALIZED (
    SELECT %s::TIMESTAMPTZ AS current_time
)
INSERT INTO mcp.project_stage_batch (
    stage_batch_id,
    project_change_set_id,
    project_id,
    dataset_name,
    expected_draft_revision,
    total_record_count,
    total_chunk_count,
    payload_mode,
    total_payload_bytes,
    batch_sha256,
    created_by_principal_id,
    correlation_id,
    created_time,
    last_activity_time,
    expires_time
)
SELECT %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
       operation_time.current_time,
       operation_time.current_time,
       least(change_set.expires_time, operation_time.current_time + INTERVAL '4 hours')
  FROM mcp.project_change_set AS change_set
 CROSS JOIN operation_time
 WHERE change_set.project_change_set_id = %s
   AND change_set.project_id = %s
   AND change_set.created_by_principal_id = %s
   AND change_set.workflow_run_id IS NULL
   AND change_set.project_change_set_status IN ('active', 'validated')
   AND change_set.expires_time > operation_time.current_time
   AND change_set.draft_revision IS NOT DISTINCT FROM %s
RETURNING *, 0::BIGINT AS received_chunk_count
"""

_GET_PROJECT_STAGE_BATCH_FOR_UPDATE_SQL: LiteralString = """
SELECT batch.*,
       batch.expires_time <= clock_timestamp() AS is_expired
  FROM mcp.project_stage_batch AS batch
 WHERE stage_batch_id = %s
   AND project_change_set_id = %s
   AND project_id = %s
 FOR UPDATE
"""

_GET_PROJECT_STAGE_CHUNK_SQL: LiteralString = """
SELECT chunk_sha256, records_document, record_count
  FROM mcp.project_stage_chunk
 WHERE stage_batch_id = %s
   AND chunk_index = %s
"""

_PROJECT_STAGE_CHUNK_TOTALS_SQL: LiteralString = """
SELECT count(*) AS chunk_count,
       coalesce(sum(record_count), 0) AS record_count
  FROM mcp.project_stage_chunk
 WHERE stage_batch_id = %s
"""

_INSERT_PROJECT_STAGE_CHUNK_SQL: LiteralString = """
INSERT INTO mcp.project_stage_chunk (
    stage_batch_id, chunk_index, record_count, chunk_sha256, records_document
)
VALUES (%s, %s, %s, %s, %s)
RETURNING record_count
"""

_TOUCH_PROJECT_STAGE_BATCH_SQL: LiteralString = """
WITH operation_time AS MATERIALIZED (
    SELECT clock_timestamp() AS current_time
)
UPDATE mcp.project_stage_batch AS batch
   SET last_activity_time = operation_time.current_time
  FROM operation_time
 WHERE stage_batch_id = %s
   AND batch.stage_batch_status = 'active'
   AND batch.expires_time > operation_time.current_time
RETURNING batch.expires_time
"""

_GET_PROJECT_STAGE_CHUNKS_SQL: LiteralString = """
SELECT chunk_index, record_count, chunk_sha256, records_document
  FROM mcp.project_stage_chunk
 WHERE stage_batch_id = %s
 ORDER BY chunk_index
"""

_GET_PROJECT_STAGE_PAYLOAD_CHUNK_SQL: LiteralString = """
SELECT chunk_sha256, chunk_byte_count, payload_fragment
  FROM mcp.project_stage_payload_chunk
 WHERE stage_batch_id = %s
   AND chunk_index = %s
"""

_PROJECT_STAGE_PAYLOAD_CHUNK_TOTALS_SQL: LiteralString = """
SELECT count(*) AS chunk_count,
       coalesce(sum(chunk_byte_count), 0) AS payload_byte_count
  FROM mcp.project_stage_payload_chunk
 WHERE stage_batch_id = %s
"""

_INSERT_PROJECT_STAGE_PAYLOAD_CHUNK_SQL: LiteralString = """
INSERT INTO mcp.project_stage_payload_chunk (
    stage_batch_id, chunk_index, chunk_byte_count, chunk_sha256, payload_fragment
)
VALUES (%s, %s, %s, %s, %s)
RETURNING chunk_byte_count
"""

_GET_PROJECT_STAGE_PAYLOAD_CHUNKS_SQL: LiteralString = """
SELECT chunk_index, chunk_byte_count, chunk_sha256, payload_fragment
  FROM mcp.project_stage_payload_chunk
 WHERE stage_batch_id = %s
 ORDER BY chunk_index
"""

_MARK_PROJECT_STAGE_BATCH_COMMITTED_SQL: LiteralString = """
WITH operation AS MATERIALIZED (
    SELECT clock_timestamp() AS current_time,
           %s::BIGINT AS committed_revision,
           %s::TIMESTAMPTZ AS committed_expires_time,
           %s::BIGINT AS expected_draft_revision
)
UPDATE mcp.project_stage_batch AS batch
   SET stage_batch_status = 'committed',
       last_activity_time = operation.current_time,
       committed_revision = operation.committed_revision,
       committed_expires_time = operation.committed_expires_time,
       terminal_time = operation.current_time
  FROM operation
 WHERE stage_batch_id = %s
   AND batch.stage_batch_status = 'active'
   AND batch.expires_time > operation.current_time
   AND batch.expected_draft_revision IS NOT DISTINCT FROM
       operation.expected_draft_revision
   AND operation.committed_revision IS NOT DISTINCT FROM
       operation.expected_draft_revision + 1
   AND operation.committed_expires_time > operation.current_time
RETURNING batch.committed_revision, batch.committed_expires_time
"""

_RECORD_VALIDATION_SQL: LiteralString = """
WITH operation AS MATERIALIZED (
    SELECT clock_timestamp() AS current_time,
           %s::BOOLEAN AS validation_succeeded,
           %s::TEXT AS candidate_digest,
           %s::JSONB AS validation_outcome
)
UPDATE mcp.project_change_set AS change_set
   SET project_change_set_status = CASE
           WHEN operation.validation_succeeded THEN 'validated'
           ELSE 'active'
       END,
       candidate_digest = CASE
           WHEN operation.validation_succeeded THEN operation.candidate_digest
           ELSE NULL
       END,
       validation_outcome = operation.validation_outcome,
       validated_time = CASE
           WHEN operation.validation_succeeded THEN operation.current_time
           ELSE NULL
       END,
       last_activity_time = operation.current_time,
       expires_time = operation.current_time + INTERVAL '4 hours'
  FROM operation
 WHERE change_set.project_change_set_id = %s
   AND change_set.project_id = %s
   AND change_set.created_by_principal_id = %s
   AND change_set.workflow_run_id IS NULL
   AND change_set.project_change_set_status IN ('active', 'validated')
   AND change_set.expires_time > operation.current_time
   AND change_set.draft_revision IS NOT DISTINCT FROM %s
   AND jsonb_typeof(operation.validation_outcome) = 'object'
   AND (
       (
           operation.validation_succeeded
           AND operation.candidate_digest ~ '^[0-9a-f]{64}$'
       ) OR (
           operation.validation_succeeded = FALSE
           AND operation.candidate_digest IS NULL
       )
   )
RETURNING change_set.project_change_set_status,
          change_set.draft_revision,
          change_set.candidate_digest,
          change_set.validated_time,
          change_set.expires_time
"""

_ADVANCE_PROJECT_REVISION_SQL: LiteralString = """
UPDATE project.project
   SET project_revision = project_revision + %s,
       updated_time = CURRENT_TIMESTAMP,
       updated_by = CURRENT_USER
 WHERE project_id = %s
   AND project_revision = %s
RETURNING project_revision
"""

_MARK_APPLIED_SQL: LiteralString = """
WITH operation AS MATERIALIZED (
    SELECT clock_timestamp() AS current_time,
           %s::BIGINT AS expected_draft_revision,
           %s::TEXT AS expected_candidate_digest
)
UPDATE mcp.project_change_set AS change_set
   SET project_change_set_status = 'applied',
       applied_time = operation.current_time,
       terminal_time = operation.current_time,
       last_activity_time = operation.current_time
  FROM operation
 WHERE change_set.project_change_set_id = %s
   AND change_set.project_id = %s
   AND change_set.created_by_principal_id = %s
   AND change_set.workflow_run_id IS NULL
   AND change_set.project_change_set_status = 'validated'
   AND change_set.expires_time > operation.current_time
   AND change_set.draft_revision IS NOT DISTINCT FROM
       operation.expected_draft_revision
   AND change_set.candidate_digest IS NOT DISTINCT FROM
       operation.expected_candidate_digest
   AND operation.expected_candidate_digest IS NOT NULL
RETURNING change_set.project_change_set_status, change_set.applied_time
"""

_ARCHIVE_SQL: LiteralString = """
WITH operation AS MATERIALIZED (
    SELECT clock_timestamp() AS current_time,
           %s::BIGINT AS expected_draft_revision
)
UPDATE mcp.project_change_set AS change_set
   SET project_change_set_status = 'discarded',
       terminal_time = operation.current_time,
       last_activity_time = operation.current_time
  FROM operation
 WHERE change_set.project_change_set_id = %s
   AND change_set.project_id = %s
   AND change_set.created_by_principal_id = %s
   AND change_set.workflow_run_id IS NULL
   AND change_set.project_change_set_status IN ('active', 'validated')
   AND change_set.expires_time > operation.current_time
   AND change_set.draft_revision IS NOT DISTINCT FROM
       operation.expected_draft_revision
RETURNING change_set.draft_revision, change_set.terminal_time
"""


class ProjectChangeSetToolError(Exception):
    """A bounded Change Set failure safe for MCP serialization."""


def register_project_change_set_tools(
    server: MCPServer[None],
    *,
    database: WriteDatabase,
    identity_provider: IdentityProvider,
    authorizer: AuthorizationService,
    audit: ToolCallAuditMiddleware,
) -> None:
    @server.tool(
        description=(
            "Create or resume the current Principal's governed Project Change Set. A "
            "caller-owned Tenant Lock is required."
        ),
        annotations=_annotations(read_only=False, idempotent=True),
        meta={"gds/toolPolicy": POLICY.value},
        structured_output=True,
    )
    async def create_project_change_set(
        ctx: Context[None],
        project_id: Annotated[int, Field(gt=0)],
        schema_version: Literal["2.0"] = "2.0",
    ) -> CreateProjectChangeSetResult:
        del schema_version
        try:
            request_principal = identity_provider.request_principal(ctx.request_context.request)
            row: dict[str, Any] | None = None
            created = False
            async with database.write_transaction() as transaction:
                project, principal = await _authorize_project(
                    transaction,
                    authorizer=authorizer,
                    request_principal=request_principal,
                    project_id=project_id,
                    policy=POLICY,
                )
                if principal.principal_id is None:
                    raise AuthorizationDeniedError()
                await transaction.fetch_one(
                    _SERIALIZE_CREATE_SQL,
                    (project.project_id, principal.principal_id),
                )
                await transaction.fetch_all(
                    _LOCK_OWNED_CHANGE_SETS_SQL,
                    (project.project_id, principal.principal_id),
                )
                operation_time = await transaction.fetch_one(_DATABASE_TIME_SQL, ())
                assert operation_time is not None
                expired_rows = await transaction.fetch_all(
                    _EXPIRE_OWNED_SQL,
                    (
                        operation_time["current_time"],
                        project.project_id,
                        principal.principal_id,
                    ),
                )
                for expired_row in expired_rows:
                    expired_correlation_id = uuid4()
                    await _insert_event(
                        transaction,
                        change_set_id=expired_row["project_change_set_id"],
                        project_id=project.project_id,
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
                    (
                        operation_time["current_time"],
                        project.project_id,
                        principal.principal_id,
                    ),
                )
                created = row is None
                if row is None:
                    change_set_id = uuid4()
                    correlation_id = uuid4()
                    row = await transaction.fetch_one(
                        _CREATE_SQL,
                        (
                            operation_time["current_time"],
                            change_set_id,
                            principal.principal_id,
                            correlation_id,
                            project.project_id,
                        ),
                    )
                    assert row is not None
                    await _insert_event(
                        transaction,
                        change_set_id=change_set_id,
                        project_id=project.project_id,
                        event_type="created",
                        draft_revision=row["draft_revision"],
                        section=None,
                        action_count=0,
                        outcome="created",
                        metadata={},
                        correlation_id=correlation_id,
                    )
            assert row is not None
            return CreateProjectChangeSetResult(
                project_id=project_id,
                project_change_set_id=row["project_change_set_id"],
                created=created,
                status=row["project_change_set_status"],
                draft_revision=row["draft_revision"],
                created_at=row["created_time"],
                expires_at=row["expires_time"],
            )
        except AuthenticationError as error:
            raise ProjectChangeSetToolError(f"{error.public_code}: {error.message}") from None
        except WorkbenchError as error:
            raise ProjectChangeSetToolError(f"{error.code}: {error.message}") from None
        except Exception:
            raise ProjectChangeSetToolError(
                "internal_error: The operation could not be completed."
            ) from None

    audit.register_tool(
        "create_project_change_set",
        policy=POLICY,
        summarize_input=_audit_project_input,
        retain_arguments={"project_id", "schema_version"},
    )

    @server.tool(
        description=(
            "Replace the complete pending record lists for one or more Project datasets in one "
            "transaction; this never appends. Omitted datasets stay unchanged and empty lists "
            "clear only that pending dataset. Use the direct operation only when every included "
            "dataset fits in one request; otherwise use ordered Begin, Put, and Commit operations. "
            "The draft revision increments once."
        ),
        annotations=_annotations(read_only=False, idempotent=False),
        meta={"gds/toolPolicy": POLICY.value},
        structured_output=True,
    )
    async def stage_project_change_set(
        ctx: Context[None],
        project_id: Annotated[int, Field(gt=0)],
        project_change_set_id: UUID,
        expected_draft_revision: Annotated[int, Field(gt=0)],
        changes: Annotated[
            list[StageProjectChange],
            Field(
                min_length=1,
                max_length=25,
                description="One complete pending replacement per affected Project dataset.",
            ),
        ],
        schema_version: Literal["2.0"] = "2.0",
    ) -> StageProjectChangeSetResult:
        del schema_version
        try:
            for change in changes:
                if change.dataset in WEB_MANAGED_PROJECT_DATASETS:
                    raise WebManagedDatasetError(change.dataset)
            staged = validate_project_stage_changes(changes)
            request_principal = identity_provider.request_principal(ctx.request_context.request)
            correlation_id = uuid4()
            expired: dict[str, Any] | None = None
            updated: dict[str, Any] | None = None
            async with database.write_transaction() as transaction:
                project, principal = await _authorize_project(
                    transaction,
                    authorizer=authorizer,
                    request_principal=request_principal,
                    project_id=project_id,
                    policy=POLICY,
                )
                row = await _owned_change_set(
                    transaction,
                    change_set_id=project_change_set_id,
                    project_id=project.project_id,
                    principal=principal,
                    for_update=True,
                )
                expired = await _expire_change_set_if_due(
                    transaction,
                    row=row,
                    project_id=project.project_id,
                    principal=principal,
                    correlation_id=correlation_id,
                )
                if expired is None:
                    require_mutable_project_change_set(row)
                    if row["draft_revision"] != expected_draft_revision:
                        raise DraftRevisionConflictError(row["draft_revision"])
                    documents = project_change_set_documents(row)
                    for dataset, records in staged.items():
                        section = DATASETS_BY_NAME[dataset].section
                        documents[section][dataset] = records
                    validate_project_change_set_document_bounds(documents)
                    updated = await transaction.fetch_one(
                        _STAGE_SQL,
                        (
                            *(
                                Jsonb(documents[column.removesuffix("_document")])
                                for column in WRITE_SECTION_COLUMNS
                            ),
                            project_change_set_id,
                            project.project_id,
                            principal.principal_id,
                            expected_draft_revision,
                        ),
                    )
                    if updated is None:
                        raise ProjectChangeSetNotActiveError()
                    sections = sorted({DATASETS_BY_NAME[dataset].section for dataset in staged})
                    await _insert_event(
                        transaction,
                        change_set_id=project_change_set_id,
                        project_id=project.project_id,
                        event_type="section_put",
                        draft_revision=updated["draft_revision"],
                        section=sections[0] if len(sections) == 1 else None,
                        action_count=sum(len(records) for records in staged.values()),
                        outcome="staged",
                        metadata={"datasets": sorted(staged)},
                        correlation_id=correlation_id,
                    )
            if expired is not None:
                raise ProjectChangeSetNotActiveError()
            assert updated is not None
            return StageProjectChangeSetResult(
                project_id=project_id,
                project_change_set_id=project_change_set_id,
                datasets=tuple(
                    ProjectChangeSetDatasetCount(
                        dataset=cast(ProjectChangeSetDataset, dataset),
                        record_count=len(records),
                    )
                    for dataset, records in staged.items()
                ),
                draft_revision=updated["draft_revision"],
                expires_at=updated["expires_time"],
            )
        except AuthenticationError as error:
            raise ProjectChangeSetToolError(f"{error.public_code}: {error.message}") from None
        except WorkbenchError as error:
            raise ProjectChangeSetToolError(f"{error.code}: {error.message}") from None
        except Exception:
            raise ProjectChangeSetToolError(
                "internal_error: The operation could not be completed."
            ) from None

    audit.register_tool(
        "stage_project_change_set",
        policy=POLICY,
        summarize_input=_audit_stage_input,
        retain_arguments={
            "project_id",
            "project_change_set_id",
            "expected_draft_revision",
            "schema_version",
        },
    )

    @server.tool(
        description=(
            "Begin or resume the nonempty Project dataset replacement selected by the client "
            "Stage plan, with at most 64 ordered chunks. Use records mode for chunks of at most "
            "5,000 records and 1 MiB. Only generated_code may use 1 MiB decoded json_fragments. "
            "Begin is idempotent and does not change the draft revision."
        ),
        annotations=_annotations(read_only=False, idempotent=True),
        meta={"gds/toolPolicy": POLICY.value},
        structured_output=True,
    )
    async def begin_project_stage_batch(
        ctx: Context[None],
        project_id: Annotated[int, Field(gt=0)],
        project_change_set_id: UUID,
        expected_draft_revision: Annotated[int, Field(gt=0)],
        dataset: Annotated[
            ProjectChangeSetDataset,
            Field(description="Single dataset replaced when this batch is committed."),
        ],
        total_record_count: Annotated[
            int,
            Field(gt=0, le=20_000, description="Records in the complete replacement list."),
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
        payload_mode: Annotated[
            ProjectStagePayloadMode,
            Field(
                description=(
                    "Use records for whole records. json_fragments is allowed only for "
                    "generated_code and requires total_payload_bytes."
                )
            ),
        ] = "records",
        total_payload_bytes: Annotated[
            int | None,
            Field(
                gt=0,
                le=MAX_PROJECT_STAGE_PAYLOAD_BYTES,
                description=(
                    "Required decoded JSON byte count for generated_code json_fragments; "
                    "omit in records mode."
                ),
            ),
        ] = None,
        schema_version: Literal["2.0"] = "2.0",
    ) -> BeginProjectStageBatchResult:
        del schema_version
        try:
            if dataset in WEB_MANAGED_PROJECT_DATASETS:
                raise WebManagedDatasetError(dataset)
            _validate_stage_payload_manifest(
                dataset=dataset,
                payload_mode=payload_mode,
                total_payload_bytes=total_payload_bytes,
            )
            request_principal = identity_provider.request_principal(ctx.request_context.request)
            correlation_id = uuid4()
            expired: dict[str, Any] | None = None
            row: dict[str, Any] | None = None
            created = False
            async with database.write_transaction() as transaction:
                project, principal = await _authorize_project(
                    transaction,
                    authorizer=authorizer,
                    request_principal=request_principal,
                    project_id=project_id,
                    policy=POLICY,
                )
                if principal.principal_id is None:
                    raise AuthorizationDeniedError()
                change_set = await _owned_change_set(
                    transaction,
                    change_set_id=project_change_set_id,
                    project_id=project.project_id,
                    principal=principal,
                    for_update=True,
                )
                expired = await _expire_change_set_if_due(
                    transaction,
                    row=change_set,
                    project_id=project.project_id,
                    principal=principal,
                    correlation_id=correlation_id,
                )
                if expired is None:
                    require_mutable_project_change_set(change_set)
                    if change_set["draft_revision"] != expected_draft_revision:
                        raise DraftRevisionConflictError(change_set["draft_revision"])
                    await transaction.fetch_all(
                        _LOCK_ACTIVE_PROJECT_STAGE_BATCHES_SQL,
                        (project_change_set_id, dataset),
                    )
                    operation_time = await transaction.fetch_one(_DATABASE_TIME_SQL, ())
                    assert operation_time is not None
                    await transaction.fetch_all(
                        _EXPIRE_PROJECT_STAGE_BATCH_SQL,
                        (
                            operation_time["current_time"],
                            project_change_set_id,
                            dataset,
                        ),
                    )
                    row = await transaction.fetch_one(
                        _FIND_PROJECT_STAGE_BATCH_SQL,
                        (project_change_set_id, dataset),
                    )
                    created = row is None
                    if row is not None:
                        require_project_stage_batch(row, principal, dataset)
                        if (
                            row["expected_draft_revision"] != expected_draft_revision
                            or row["total_record_count"] != total_record_count
                            or row["total_chunk_count"] != total_chunk_count
                            or row["payload_mode"] != payload_mode
                            or row["total_payload_bytes"] != total_payload_bytes
                            or row["batch_sha256"] != batch_sha256
                        ):
                            raise StageBatchConflictError()
                    else:
                        stage_batch_id = uuid4()
                        row = await transaction.fetch_one(
                            _CREATE_PROJECT_STAGE_BATCH_SQL,
                            (
                                operation_time["current_time"],
                                stage_batch_id,
                                project_change_set_id,
                                project.project_id,
                                dataset,
                                expected_draft_revision,
                                total_record_count,
                                total_chunk_count,
                                payload_mode,
                                total_payload_bytes,
                                batch_sha256,
                                principal.principal_id,
                                correlation_id,
                                project_change_set_id,
                                project.project_id,
                                principal.principal_id,
                                expected_draft_revision,
                            ),
                        )
                        if row is None:
                            raise ProjectChangeSetNotActiveError()
            if expired is not None:
                raise ProjectChangeSetNotActiveError()
            assert row is not None
            return BeginProjectStageBatchResult(
                project_id=project_id,
                project_change_set_id=project_change_set_id,
                stage_batch_id=row["stage_batch_id"],
                dataset=cast(ProjectChangeSetDataset, row["dataset_name"]),
                created=created,
                total_record_count=row["total_record_count"],
                total_chunk_count=row["total_chunk_count"],
                received_chunk_count=row["received_chunk_count"],
                expected_draft_revision=expected_draft_revision,
                expires_at=row["expires_time"],
                payload_mode=cast(ProjectStagePayloadMode, row["payload_mode"]),
                total_payload_bytes=row["total_payload_bytes"],
            )
        except AuthenticationError as error:
            raise ProjectChangeSetToolError(f"{error.public_code}: {error.message}") from None
        except WorkbenchError as error:
            raise ProjectChangeSetToolError(f"{error.code}: {error.message}") from None
        except Exception:
            raise ProjectChangeSetToolError(
                "internal_error: The operation could not be completed."
            ) from None

    audit.register_tool(
        "begin_project_stage_batch",
        policy=POLICY,
        summarize_input=_audit_begin_stage_batch,
        retain_arguments={
            "project_id",
            "project_change_set_id",
            "expected_draft_revision",
            "dataset",
            "total_record_count",
            "total_chunk_count",
            "payload_mode",
            "total_payload_bytes",
            "schema_version",
        },
    )

    @server.tool(
        description=(
            "Store one ordered Project batch chunk. In records mode supply 1-5,000 whole records "
            "whose canonical JSON is at most 1 MiB. Only generated_code json_fragments mode may "
            "instead supply one base64 fragment of at most 1 MiB decoded. An identical retry is "
            "safe; Put does not change the draft revision."
        ),
        annotations=_annotations(read_only=False, idempotent=True),
        meta={"gds/toolPolicy": POLICY.value},
        structured_output=True,
    )
    async def put_project_stage_chunk(
        ctx: Context[None],
        project_id: Annotated[int, Field(gt=0)],
        project_change_set_id: UUID,
        stage_batch_id: UUID,
        dataset: Annotated[
            ProjectChangeSetDataset,
            Field(description="Must match the dataset declared by the Stage Batch."),
        ],
        chunk_index: Annotated[
            int,
            Field(gt=0, le=MAX_STAGE_CHUNKS, description="One-based chunk position."),
        ],
        chunk_sha256: Annotated[
            str,
            Field(
                pattern=SHA256_PATTERN,
                description=(
                    "SHA-256 of exact canonical request records, or decoded fragment bytes in "
                    "json_fragments mode."
                ),
            ),
        ],
        records: Annotated[
            list[dict[str, object]] | None,
            Field(
                max_length=MAX_STAGE_CHUNK_RECORDS,
                description="Required nonempty record list in records mode; otherwise omit.",
            ),
        ] = None,
        payload_mode: Annotated[
            ProjectStagePayloadMode,
            Field(description="Must match the Stage Batch manifest."),
        ] = "records",
        payload_fragment_base64: Annotated[
            str | None,
            Field(
                max_length=MAX_PROJECT_STAGE_FRAGMENT_BASE64_CHARACTERS,
                description=(
                    "Required canonical base64 fragment in generated_code json_fragments "
                    "mode; otherwise omit."
                ),
            ),
        ] = None,
        schema_version: Literal["2.0"] = "2.0",
    ) -> PutProjectStageChunkResult:
        del schema_version
        try:
            if dataset in WEB_MANAGED_PROJECT_DATASETS:
                raise WebManagedDatasetError(dataset)
            normalized: list[dict[str, object]] = []
            payload_fragment: bytes | None = None
            if payload_mode == "records":
                if not records or payload_fragment_base64 is not None:
                    raise InvalidRequestError("The Stage chunk payload mode is invalid.")
                normalized = validate_project_stage_changes(
                    [StageProjectChange(dataset=dataset, records=records)]
                )[dataset]
                encoded = canonical_records_bytes(normalized)
                if len(encoded) > MAX_PROJECT_STAGE_CHUNK_BYTES:
                    raise InvalidRequestError("The Stage chunk exceeds the bounded byte limit.")
                if canonical_records_sha256(records) != chunk_sha256:
                    raise InvalidRequestError(
                        "The Stage chunk SHA-256 does not match its request records."
                    )
            else:
                if (
                    dataset != "generated_code"
                    or records is not None
                    or payload_fragment_base64 is None
                ):
                    raise InvalidRequestError("The Stage chunk payload mode is invalid.")
                try:
                    payload_fragment = decode_canonical_base64_fragment(payload_fragment_base64)
                except ValueError:
                    raise InvalidRequestError("The Stage payload fragment is invalid.") from None
                if hashlib.sha256(payload_fragment).hexdigest() != chunk_sha256:
                    raise InvalidRequestError(
                        "The Stage chunk SHA-256 does not match its decoded payload bytes."
                    )
            request_principal = identity_provider.request_principal(ctx.request_context.request)
            expired: dict[str, Any] | None = None
            expired_batch: dict[str, Any] | None = None
            batch: dict[str, Any] | None = None
            totals: dict[str, Any] | None = None
            duplicate = False
            async with database.write_transaction() as transaction:
                project, principal = await _authorize_project(
                    transaction,
                    authorizer=authorizer,
                    request_principal=request_principal,
                    project_id=project_id,
                    policy=POLICY,
                )
                change_set = await _owned_change_set(
                    transaction,
                    change_set_id=project_change_set_id,
                    project_id=project.project_id,
                    principal=principal,
                    for_update=True,
                )
                expired = await _expire_change_set_if_due(
                    transaction,
                    row=change_set,
                    project_id=project.project_id,
                    principal=principal,
                    correlation_id=change_set["correlation_id"],
                )
                if expired is None:
                    require_mutable_project_change_set(change_set)
                    await transaction.fetch_all(
                        _LOCK_ACTIVE_PROJECT_STAGE_BATCH_BY_ID_SQL,
                        (stage_batch_id, project_change_set_id, project.project_id),
                    )
                    operation_time = await transaction.fetch_one(_DATABASE_TIME_SQL, ())
                    assert operation_time is not None
                    expired_batch = await transaction.fetch_one(
                        _EXPIRE_PROJECT_STAGE_BATCH_BY_ID_SQL,
                        (
                            operation_time["current_time"],
                            stage_batch_id,
                            project_change_set_id,
                            project.project_id,
                        ),
                    )
                    if expired_batch is None:
                        batch = await transaction.fetch_one(
                            _GET_PROJECT_STAGE_BATCH_FOR_UPDATE_SQL,
                            (stage_batch_id, project_change_set_id, project.project_id),
                        )
                        require_project_stage_batch(batch, principal, dataset)
                        assert batch is not None
                        if batch["payload_mode"] != payload_mode:
                            raise InvalidRequestError(
                                "Payload mode does not match the Stage Batch manifest."
                            )
                        if change_set["draft_revision"] != batch["expected_draft_revision"]:
                            raise DraftRevisionConflictError(change_set["draft_revision"])
                        if chunk_index > batch["total_chunk_count"]:
                            raise InvalidRequestError(
                                "Chunk index exceeds the Stage Batch manifest."
                            )
                        chunk_query = (
                            _GET_PROJECT_STAGE_PAYLOAD_CHUNK_SQL
                            if payload_mode == "json_fragments"
                            else _GET_PROJECT_STAGE_CHUNK_SQL
                        )
                        existing = await transaction.fetch_one(
                            chunk_query, (stage_batch_id, chunk_index)
                        )
                        duplicate = existing is not None
                        if existing is not None:
                            same_payload = (
                                bytes(existing["payload_fragment"]) == payload_fragment
                                if payload_mode == "json_fragments"
                                else existing["records_document"] == normalized
                            )
                            if existing["chunk_sha256"] != chunk_sha256 or not same_payload:
                                raise StageChunkConflictError()
                        else:
                            totals_query = (
                                _PROJECT_STAGE_PAYLOAD_CHUNK_TOTALS_SQL
                                if payload_mode == "json_fragments"
                                else _PROJECT_STAGE_CHUNK_TOTALS_SQL
                            )
                            totals = await transaction.fetch_one(totals_query, (stage_batch_id,))
                            assert totals is not None
                            if payload_mode == "json_fragments":
                                assert payload_fragment is not None
                                if (
                                    totals["payload_byte_count"] + len(payload_fragment)
                                    > batch["total_payload_bytes"]
                                ):
                                    raise InvalidRequestError(
                                        "Stage fragments exceed the approved payload bytes."
                                    )
                                inserted = await transaction.fetch_one(
                                    _INSERT_PROJECT_STAGE_PAYLOAD_CHUNK_SQL,
                                    (
                                        stage_batch_id,
                                        chunk_index,
                                        len(payload_fragment),
                                        chunk_sha256,
                                        payload_fragment,
                                    ),
                                )
                            else:
                                if (
                                    totals["record_count"] + len(normalized)
                                    > batch["total_record_count"]
                                ):
                                    raise InvalidRequestError(
                                        "Stage chunks exceed the approved record count."
                                    )
                                inserted = await transaction.fetch_one(
                                    _INSERT_PROJECT_STAGE_CHUNK_SQL,
                                    (
                                        stage_batch_id,
                                        chunk_index,
                                        len(normalized),
                                        chunk_sha256,
                                        Jsonb(normalized),
                                    ),
                                )
                            assert inserted is not None
                            touched = await transaction.fetch_one(
                                _TOUCH_PROJECT_STAGE_BATCH_SQL,
                                (stage_batch_id,),
                            )
                            if touched is None:
                                raise StageBatchNotActiveError()
                        totals = await transaction.fetch_one(
                            (
                                _PROJECT_STAGE_PAYLOAD_CHUNK_TOTALS_SQL
                                if payload_mode == "json_fragments"
                                else _PROJECT_STAGE_CHUNK_TOTALS_SQL
                            ),
                            (stage_batch_id,),
                        )
                        assert totals is not None
            if expired is not None:
                raise ProjectChangeSetNotActiveError()
            if expired_batch is not None:
                raise StageBatchNotActiveError()
            assert batch is not None
            assert totals is not None
            return PutProjectStageChunkResult(
                project_id=project_id,
                project_change_set_id=project_change_set_id,
                stage_batch_id=stage_batch_id,
                dataset=dataset,
                duplicate=duplicate,
                chunk_index=chunk_index,
                record_count=len(normalized),
                received_chunk_count=totals["chunk_count"],
                total_chunk_count=batch["total_chunk_count"],
                expires_at=batch["expires_time"],
                payload_mode=payload_mode,
                payload_byte_count=(
                    len(payload_fragment) if payload_fragment is not None else None
                ),
            )
        except AuthenticationError as error:
            raise ProjectChangeSetToolError(f"{error.public_code}: {error.message}") from None
        except WorkbenchError as error:
            raise ProjectChangeSetToolError(f"{error.code}: {error.message}") from None
        except Exception:
            raise ProjectChangeSetToolError(
                "internal_error: The operation could not be completed."
            ) from None

    audit.register_tool(
        "put_project_stage_chunk",
        policy=POLICY,
        summarize_input=_audit_put_stage_chunk,
        retain_arguments={
            "project_id",
            "project_change_set_id",
            "stage_batch_id",
            "dataset",
            "chunk_index",
            "payload_mode",
            "schema_version",
        },
    )

    @server.tool(
        description=(
            "Verify and atomically commit one complete Project Stage Batch as that dataset's "
            "pending replacement. The response returns the new draft_revision; use it for "
            "the next batch or validation."
        ),
        annotations=_annotations(read_only=False, idempotent=True),
        meta={"gds/toolPolicy": POLICY.value},
        structured_output=True,
    )
    async def commit_project_stage_batch(
        ctx: Context[None],
        project_id: Annotated[int, Field(gt=0)],
        project_change_set_id: UUID,
        stage_batch_id: UUID,
        expected_draft_revision: Annotated[int, Field(gt=0)],
        schema_version: Literal["2.0"] = "2.0",
    ) -> CommitProjectStageBatchResult:
        del schema_version
        try:
            request_principal = identity_provider.request_principal(ctx.request_context.request)
            correlation_id = uuid4()
            expired: dict[str, Any] | None = None
            expired_batch: dict[str, Any] | None = None
            batch: dict[str, Any] | None = None
            committed_revision: int | None = None
            committed_expires_time: datetime | None = None
            replayed = False
            async with database.write_transaction() as transaction:
                project, principal = await _authorize_project(
                    transaction,
                    authorizer=authorizer,
                    request_principal=request_principal,
                    project_id=project_id,
                    policy=POLICY,
                )
                change_set = await _owned_change_set(
                    transaction,
                    change_set_id=project_change_set_id,
                    project_id=project.project_id,
                    principal=principal,
                    for_update=True,
                )
                expired = await _expire_change_set_if_due(
                    transaction,
                    row=change_set,
                    project_id=project.project_id,
                    principal=principal,
                    correlation_id=correlation_id,
                )
                if expired is None:
                    require_mutable_project_change_set(change_set)
                    await transaction.fetch_all(
                        _LOCK_ACTIVE_PROJECT_STAGE_BATCH_BY_ID_SQL,
                        (stage_batch_id, project_change_set_id, project.project_id),
                    )
                    operation_time = await transaction.fetch_one(_DATABASE_TIME_SQL, ())
                    assert operation_time is not None
                    expired_batch = await transaction.fetch_one(
                        _EXPIRE_PROJECT_STAGE_BATCH_BY_ID_SQL,
                        (
                            operation_time["current_time"],
                            stage_batch_id,
                            project_change_set_id,
                            project.project_id,
                        ),
                    )
                    if expired_batch is None:
                        batch = await transaction.fetch_one(
                            _GET_PROJECT_STAGE_BATCH_FOR_UPDATE_SQL,
                            (stage_batch_id, project_change_set_id, project.project_id),
                        )
                        if (
                            batch is None
                            or batch["created_by_principal_id"] != principal.principal_id
                        ):
                            raise StageBatchNotFoundError()
                        # Begin refuses these datasets; this covers batches begun before that.
                        if batch["dataset_name"] in WEB_MANAGED_PROJECT_DATASETS:
                            raise WebManagedDatasetError(batch["dataset_name"])
                        if batch["expected_draft_revision"] != expected_draft_revision:
                            raise InvalidRequestError(
                                "Expected revision does not match the Stage Batch manifest."
                            )
                        if batch["stage_batch_status"] == "committed":
                            replayed = True
                            committed_revision = batch["committed_revision"]
                            committed_expires_time = batch["committed_expires_time"]
                        else:
                            require_project_stage_batch(batch, principal, None)
                            if change_set["draft_revision"] != expected_draft_revision:
                                raise DraftRevisionConflictError(change_set["draft_revision"])
                            payload_mode = cast(ProjectStagePayloadMode, batch["payload_mode"])
                            chunks = await transaction.fetch_all(
                                (
                                    _GET_PROJECT_STAGE_PAYLOAD_CHUNKS_SQL
                                    if payload_mode == "json_fragments"
                                    else _GET_PROJECT_STAGE_CHUNKS_SQL
                                ),
                                (stage_batch_id,),
                            )
                            if (
                                len(chunks) != batch["total_chunk_count"]
                                or stage_batch_sha256([row["chunk_sha256"] for row in chunks])
                                != batch["batch_sha256"]
                            ):
                                raise StageBatchIncompleteError()
                            payload: bytes | None = None
                            if payload_mode == "json_fragments":
                                if (
                                    sum(row["chunk_byte_count"] for row in chunks)
                                    != batch["total_payload_bytes"]
                                ):
                                    raise StageBatchIncompleteError()
                                payload = b"".join(bytes(row["payload_fragment"]) for row in chunks)
                                assembled = decode_canonical_project_stage_payload(
                                    payload,
                                    expected_record_count=batch["total_record_count"],
                                )
                            else:
                                if (
                                    sum(row["record_count"] for row in chunks)
                                    != batch["total_record_count"]
                                ):
                                    raise StageBatchIncompleteError()
                                assembled = [
                                    cast(dict[str, object], record)
                                    for chunk in chunks
                                    for record in chunk["records_document"]
                                ]
                            staged = validate_project_stage_changes(
                                [
                                    StageProjectChange(
                                        dataset=cast(
                                            ProjectChangeSetDataset,
                                            batch["dataset_name"],
                                        ),
                                        records=assembled,
                                    )
                                ]
                            )
                            if (
                                payload_mode == "json_fragments"
                                and payload is not None
                                and canonical_records_bytes(staged[batch["dataset_name"]])
                                != payload
                            ):
                                raise InvalidRequestError(
                                    "The Stage payload is not canonical normalized JSON."
                                )
                            documents = project_change_set_documents(change_set)
                            dataset_name = batch["dataset_name"]
                            section = DATASETS_BY_NAME[dataset_name].section
                            documents[section][dataset_name] = staged[dataset_name]
                            validate_project_change_set_document_bounds(documents)
                            updated = await transaction.fetch_one(
                                _STAGE_SQL,
                                (
                                    *(
                                        Jsonb(documents[column.removesuffix("_document")])
                                        for column in WRITE_SECTION_COLUMNS
                                    ),
                                    project_change_set_id,
                                    project.project_id,
                                    principal.principal_id,
                                    expected_draft_revision,
                                ),
                            )
                            if updated is None:
                                raise ProjectChangeSetNotActiveError()
                            await _insert_event(
                                transaction,
                                change_set_id=project_change_set_id,
                                project_id=project.project_id,
                                event_type="section_put",
                                draft_revision=updated["draft_revision"],
                                section=section,
                                action_count=len(assembled),
                                outcome="staged",
                                metadata={"datasets": [dataset_name]},
                                correlation_id=correlation_id,
                            )
                            marked = await transaction.fetch_one(
                                _MARK_PROJECT_STAGE_BATCH_COMMITTED_SQL,
                                (
                                    updated["draft_revision"],
                                    updated["expires_time"],
                                    expected_draft_revision,
                                    stage_batch_id,
                                ),
                            )
                            if marked is None:
                                raise StageBatchNotActiveError()
                            committed_revision = marked["committed_revision"]
                            committed_expires_time = marked["committed_expires_time"]
            if expired is not None:
                raise ProjectChangeSetNotActiveError()
            if expired_batch is not None:
                raise StageBatchNotActiveError()
            assert batch is not None
            assert committed_revision is not None
            assert committed_expires_time is not None
            return CommitProjectStageBatchResult(
                project_id=project_id,
                project_change_set_id=project_change_set_id,
                stage_batch_id=stage_batch_id,
                dataset=cast(ProjectChangeSetDataset, batch["dataset_name"]),
                replayed=replayed,
                record_count=batch["total_record_count"],
                draft_revision=committed_revision,
                expires_at=committed_expires_time,
            )
        except AuthenticationError as error:
            raise ProjectChangeSetToolError(f"{error.public_code}: {error.message}") from None
        except WorkbenchError as error:
            raise ProjectChangeSetToolError(f"{error.code}: {error.message}") from None
        except Exception:
            raise ProjectChangeSetToolError(
                "internal_error: The operation could not be completed."
            ) from None

    audit.register_tool(
        "commit_project_stage_batch",
        policy=POLICY,
        summarize_input=_audit_revision_input,
        retain_arguments={
            "project_id",
            "project_change_set_id",
            "stage_batch_id",
            "expected_draft_revision",
            "schema_version",
        },
    )

    @server.tool(
        description=(
            "Read the caller's Project Change Set without requiring a current Tenant Lock. "
            "Omit dataset for counts only; provide dataset to return only that pending "
            "ID-free dataset."
        ),
        annotations=_annotations(read_only=True, idempotent=True),
        meta={"gds/toolPolicy": READ_POLICY.value},
        structured_output=True,
    )
    async def get_project_change_set(
        ctx: Context[None],
        project_id: Annotated[int, Field(gt=0)],
        project_change_set_id: UUID,
        dataset: ProjectDataset | None = None,
        schema_version: Literal["2.0"] = "2.0",
    ) -> GetProjectChangeSetResult:
        del schema_version
        try:
            request_principal = identity_provider.request_principal(ctx.request_context.request)
            async with database.write_transaction() as transaction:
                project, principal = await _authorize_project(
                    transaction,
                    authorizer=authorizer,
                    request_principal=request_principal,
                    project_id=project_id,
                    policy=READ_POLICY,
                )
                row = await _owned_change_set(
                    transaction,
                    change_set_id=project_change_set_id,
                    project_id=project.project_id,
                    principal=principal,
                    for_update=True,
                )
                expired = await _expire_change_set_if_due(
                    transaction,
                    row=row,
                    project_id=project.project_id,
                    principal=principal,
                    correlation_id=row["correlation_id"],
                )
                if expired is not None:
                    row = expired
            pending = pending_project_change_set_datasets(row)
            return GetProjectChangeSetResult(
                project_id=project_id,
                project_change_set_id=project_change_set_id,
                status=row["project_change_set_status"],
                draft_revision=row["draft_revision"],
                candidate_digest=row["candidate_digest"],
                validation_outcome=bounded_validation_outcome(row["validation_outcome"]),
                dataset_counts=tuple(
                    ProjectDatasetCount(
                        dataset=cast(ProjectDataset, name), record_count=len(records)
                    )
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
            raise ProjectChangeSetToolError(f"{error.public_code}: {error.message}") from None
        except WorkbenchError as error:
            raise ProjectChangeSetToolError(f"{error.code}: {error.message}") from None
        except Exception:
            raise ProjectChangeSetToolError(
                "internal_error: The operation could not be completed."
            ) from None

    audit.register_tool(
        "get_project_change_set",
        policy=READ_POLICY,
        summarize_input=_audit_get_input,
        retain_arguments={"project_id", "project_change_set_id", "dataset", "schema_version"},
    )

    @server.tool(
        description=(
            "Return bounded counts and SHA-256 fingerprints for the caller's exact Project "
            "Change Set revision without returning pending records. Use this to verify Stage "
            "transport, including active drafts that failed validation."
        ),
        annotations=_annotations(read_only=True, idempotent=True),
        meta={"gds/toolPolicy": READ_POLICY.value},
        structured_output=True,
    )
    async def get_project_change_set_fingerprint(
        ctx: Context[None],
        project_id: Annotated[int, Field(gt=0)],
        project_change_set_id: UUID,
        schema_version: Literal["2.0"] = "2.0",
    ) -> GetProjectChangeSetFingerprintResult:
        del schema_version
        try:
            request_principal = identity_provider.request_principal(ctx.request_context.request)
            async with database.write_transaction() as transaction:
                project, principal = await _authorize_project(
                    transaction,
                    authorizer=authorizer,
                    request_principal=request_principal,
                    project_id=project_id,
                    policy=READ_POLICY,
                )
                row = await _owned_change_set(
                    transaction,
                    change_set_id=project_change_set_id,
                    project_id=project.project_id,
                    principal=principal,
                    for_update=True,
                )
                expired = await _expire_change_set_if_due(
                    transaction,
                    row=row,
                    project_id=project.project_id,
                    principal=principal,
                    correlation_id=row["correlation_id"],
                )
                if expired is not None:
                    row = expired
            require_mcp_writable_pending(row)
            pending = pending_project_change_set_datasets(row)
            datasets = tuple(
                ProjectChangeSetDatasetFingerprint(
                    dataset=cast(ProjectChangeSetDataset, name),
                    record_count=len(records),
                    sha256=canonical_records_sha256(records),
                )
                for name in sorted(CHANGE_SET_DATASETS_BY_NAME)
                for records in [pending.get(name, [])]
            )
            fingerprint = stage_fingerprint_sha256(
                "project", [item.model_dump(mode="json") for item in datasets]
            )
            return GetProjectChangeSetFingerprintResult(
                project_id=project_id,
                project_change_set_id=project_change_set_id,
                status=row["project_change_set_status"],
                draft_revision=row["draft_revision"],
                dataset_count=len(datasets),
                record_count=sum(item.record_count for item in datasets),
                datasets=datasets,
                fingerprint=fingerprint,
                expires_at=row["expires_time"],
            )
        except AuthenticationError as error:
            raise ProjectChangeSetToolError(f"{error.public_code}: {error.message}") from None
        except WorkbenchError as error:
            raise ProjectChangeSetToolError(f"{error.code}: {error.message}") from None
        except Exception:
            raise ProjectChangeSetToolError(
                "internal_error: The operation could not be completed."
            ) from None

    audit.register_tool(
        "get_project_change_set_fingerprint",
        policy=READ_POLICY,
        summarize_input=_audit_project_input,
        retain_arguments={"project_id", "project_change_set_id", "schema_version"},
    )

    @server.tool(
        description=(
            "Validate one exact Project Change Set revision against the complete future graph "
            "and seal it for Apply. An invalid draft remains active so its exact revision can "
            "be corrected and staged again. This does not execute generated Code or Validation "
            "Checks or apply the draft."
        ),
        annotations=_annotations(read_only=False, idempotent=False),
        meta={"gds/toolPolicy": POLICY.value},
        structured_output=True,
    )
    async def validate_project_change_set(
        ctx: Context[None],
        project_id: Annotated[int, Field(gt=0)],
        project_change_set_id: UUID,
        expected_draft_revision: Annotated[int, Field(gt=0)],
        schema_version: Literal["2.0"] = "2.0",
    ) -> ValidateProjectChangeSetResult:
        del schema_version
        try:
            request_principal = identity_provider.request_principal(ctx.request_context.request)
            correlation_id = uuid4()
            expired: dict[str, Any] | None = None
            validation: ValidatedProjectChangeSet | None = None
            updated: dict[str, Any] | None = None
            async with database.write_transaction() as transaction:
                project, principal = await _authorize_project(
                    transaction,
                    authorizer=authorizer,
                    request_principal=request_principal,
                    project_id=project_id,
                    policy=POLICY,
                )
                row = await _owned_change_set(
                    transaction,
                    change_set_id=project_change_set_id,
                    project_id=project.project_id,
                    principal=principal,
                    for_update=True,
                )
                expired = await _expire_change_set_if_due(
                    transaction,
                    row=row,
                    project_id=project.project_id,
                    principal=principal,
                    correlation_id=correlation_id,
                )
                if expired is None:
                    require_mutable_project_change_set(row)
                    if row["draft_revision"] != expected_draft_revision:
                        raise DraftRevisionConflictError(row["draft_revision"])
                    require_mcp_writable_pending(row)
                    validation = await validate_locked_project_change_set(transaction, project, row)
                    if validation.valid:
                        assert validation.candidate_digest is not None
                    outcome = project_validation_outcome(validation)
                    updated = await transaction.fetch_one(
                        _RECORD_VALIDATION_SQL,
                        (
                            validation.valid,
                            validation.candidate_digest if validation.valid else None,
                            Jsonb(outcome),
                            project_change_set_id,
                            project.project_id,
                            principal.principal_id,
                            expected_draft_revision,
                        ),
                    )
                    if updated is None:
                        raise ProjectChangeSetNotActiveError()
                    await _insert_event(
                        transaction,
                        change_set_id=project_change_set_id,
                        project_id=project.project_id,
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
            if expired is not None:
                raise ProjectChangeSetNotActiveError()
            assert validation is not None
            assert updated is not None
            return ValidateProjectChangeSetResult(
                project_id=project_id,
                project_change_set_id=project_change_set_id,
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
                validated_at=updated["validated_time"],
                expires_at=updated["expires_time"],
            )
        except AuthenticationError as error:
            raise ProjectChangeSetToolError(f"{error.public_code}: {error.message}") from None
        except WorkbenchError as error:
            raise ProjectChangeSetToolError(f"{error.code}: {error.message}") from None
        except Exception:
            raise ProjectChangeSetToolError(
                "internal_error: The operation could not be completed."
            ) from None

    audit.register_tool(
        "validate_project_change_set",
        policy=POLICY,
        summarize_input=_audit_revision_input,
        retain_arguments={
            "project_id",
            "project_change_set_id",
            "expected_draft_revision",
            "schema_version",
        },
    )

    @server.tool(
        description=(
            "Atomically revalidate and apply one sealed Project Change Set to normalized "
            "Project tables, advancing the Project revision once when records are written."
        ),
        annotations=_annotations(read_only=False, destructive=True, idempotent=False),
        meta={"gds/toolPolicy": POLICY.value},
        structured_output=True,
    )
    async def apply_project_change_set(
        ctx: Context[None],
        project_id: Annotated[int, Field(gt=0)],
        project_change_set_id: UUID,
        expected_draft_revision: Annotated[int, Field(gt=0)],
        expected_candidate_digest: Annotated[
            str,
            Field(
                pattern=r"^[0-9a-f]{64}$",
                description="candidate_digest of the validation the user approved for Apply.",
            ),
        ],
        schema_version: Literal["2.0"] = "2.0",
    ) -> ApplyProjectChangeSetResult:
        del schema_version
        try:
            request_principal = identity_provider.request_principal(ctx.request_context.request)
            correlation_id = uuid4()
            expired: dict[str, Any] | None = None
            validation: ValidatedProjectChangeSet | None = None
            revision: dict[str, Any] | None = None
            applied: dict[str, Any] | None = None
            action_count = 0
            async with database.write_transaction() as transaction:
                project, principal = await _authorize_project(
                    transaction,
                    authorizer=authorizer,
                    request_principal=request_principal,
                    project_id=project_id,
                    policy=POLICY,
                )
                row = await _owned_change_set(
                    transaction,
                    change_set_id=project_change_set_id,
                    project_id=project.project_id,
                    principal=principal,
                    for_update=True,
                )
                expired = await _expire_change_set_if_due(
                    transaction,
                    row=row,
                    project_id=project.project_id,
                    principal=principal,
                    correlation_id=correlation_id,
                )
                if expired is None:
                    require_mutable_project_change_set(row)
                    if row["project_change_set_status"] != "validated":
                        raise ProjectChangeSetNotValidatedError()
                    if row["draft_revision"] != expected_draft_revision:
                        raise DraftRevisionConflictError(row["draft_revision"])
                    if row["candidate_digest"] != expected_candidate_digest:
                        raise CandidateDigestConflictError()
                    require_mcp_writable_pending(row)
                    validation = await validate_locked_project_change_set(transaction, project, row)
                    if not validation.valid:
                        raise CandidateDigestConflictError()
                    assert validation.candidate_digest is not None
                    if validation.candidate_digest != row["candidate_digest"]:
                        raise CandidateDigestConflictError()
                    materializer = ProjectMaterializer(
                        transaction=transaction,
                        project_id=project.project_id,
                        source_context_digest=row["base_source_context_digest"],
                        readable_source_tenant_ids=project.readable_source_tenant_ids,
                        change_set_id=project_change_set_id,
                        request_principal=request_principal,
                        draft_revision=expected_draft_revision,
                        candidate_digest=validation.candidate_digest,
                    )
                    action_count = await materializer.apply(validation.records)
                    revision = await transaction.fetch_one(
                        _ADVANCE_PROJECT_REVISION_SQL,
                        (
                            1 if action_count > 0 else 0,
                            project.project_id,
                            project.project_revision,
                        ),
                    )
                    if revision is None:
                        raise InvalidRequestError("Project revision changed during apply.")
                    applied = await transaction.fetch_one(
                        _MARK_APPLIED_SQL,
                        (
                            expected_draft_revision,
                            validation.candidate_digest,
                            project_change_set_id,
                            project.project_id,
                            principal.principal_id,
                        ),
                    )
                    if applied is None:
                        raise ProjectChangeSetNotActiveError()
                    await _insert_event(
                        transaction,
                        change_set_id=project_change_set_id,
                        project_id=project.project_id,
                        event_type="applied",
                        draft_revision=row["draft_revision"],
                        section=None,
                        action_count=action_count,
                        outcome="applied",
                        metadata={"project_revision": revision["project_revision"]},
                        correlation_id=correlation_id,
                    )
            if expired is not None:
                raise ProjectChangeSetNotActiveError()
            assert validation is not None
            assert validation.candidate_digest is not None
            assert revision is not None
            assert applied is not None
            return ApplyProjectChangeSetResult(
                project_id=project_id,
                project_change_set_id=project_change_set_id,
                draft_revision=row["draft_revision"],
                candidate_digest=validation.candidate_digest,
                action_count=action_count,
                project_revision=revision["project_revision"],
                applied_at=applied["applied_time"],
            )
        except AuthenticationError as error:
            raise ProjectChangeSetToolError(f"{error.public_code}: {error.message}") from None
        except WorkbenchError as error:
            raise ProjectChangeSetToolError(f"{error.code}: {error.message}") from None
        except Exception:
            raise ProjectChangeSetToolError(
                "internal_error: The operation could not be completed."
            ) from None

    audit.register_tool(
        "apply_project_change_set",
        policy=POLICY,
        summarize_input=_audit_revision_input,
        retain_arguments={
            "project_id",
            "project_change_set_id",
            "expected_draft_revision",
            "expected_candidate_digest",
            "schema_version",
        },
    )

    @server.tool(
        description=(
            "End and retain your active or validated Project Change Set. A current "
            "Tenant Lock is not required; the Change Set is not deleted."
        ),
        annotations=_annotations(read_only=False, destructive=True, idempotent=False),
        meta={"gds/toolPolicy": READ_POLICY.value},
        structured_output=True,
    )
    async def archive_project_change_set(
        ctx: Context[None],
        project_id: Annotated[int, Field(gt=0)],
        project_change_set_id: UUID,
        expected_draft_revision: Annotated[int, Field(gt=0)],
        schema_version: Literal["2.0"] = "2.0",
    ) -> ArchiveProjectChangeSetResult:
        del schema_version
        try:
            request_principal = identity_provider.request_principal(ctx.request_context.request)
            correlation_id = uuid4()
            expired: dict[str, Any] | None = None
            archived: dict[str, Any] | None = None
            async with database.write_transaction() as transaction:
                project, principal = await _authorize_project(
                    transaction,
                    authorizer=authorizer,
                    request_principal=request_principal,
                    project_id=project_id,
                    policy=READ_POLICY,
                )
                if project.is_locked:
                    raise ProjectLockedError()
                row = await _owned_change_set(
                    transaction,
                    change_set_id=project_change_set_id,
                    project_id=project.project_id,
                    principal=principal,
                    for_update=True,
                )
                expired = await _expire_change_set_if_due(
                    transaction,
                    row=row,
                    project_id=project.project_id,
                    principal=principal,
                    correlation_id=correlation_id,
                )
                if expired is None:
                    require_mutable_project_change_set(row)
                    if row["draft_revision"] != expected_draft_revision:
                        raise DraftRevisionConflictError(row["draft_revision"])
                    archived = await transaction.fetch_one(
                        _ARCHIVE_SQL,
                        (
                            expected_draft_revision,
                            project_change_set_id,
                            project.project_id,
                            principal.principal_id,
                        ),
                    )
                    if archived is None:
                        raise ProjectChangeSetNotActiveError()
                    await _insert_event(
                        transaction,
                        change_set_id=project_change_set_id,
                        project_id=project.project_id,
                        event_type="discarded",
                        draft_revision=archived["draft_revision"],
                        section=None,
                        action_count=0,
                        outcome="archived",
                        metadata={},
                        correlation_id=correlation_id,
                    )
            if expired is not None:
                raise ProjectChangeSetNotActiveError()
            assert archived is not None
            return ArchiveProjectChangeSetResult(
                project_id=project_id,
                project_change_set_id=project_change_set_id,
                draft_revision=archived["draft_revision"],
                archived_at=archived["terminal_time"],
            )
        except AuthenticationError as error:
            raise ProjectChangeSetToolError(f"{error.public_code}: {error.message}") from None
        except WorkbenchError as error:
            raise ProjectChangeSetToolError(f"{error.code}: {error.message}") from None
        except Exception:
            raise ProjectChangeSetToolError(
                "internal_error: The operation could not be completed."
            ) from None

    audit.register_tool(
        "archive_project_change_set",
        policy=READ_POLICY,
        summarize_input=_audit_revision_input,
        retain_arguments={
            "project_id",
            "project_change_set_id",
            "expected_draft_revision",
            "schema_version",
        },
    )


async def _authorize_project(
    transaction: WriteTransaction,
    *,
    authorizer: AuthorizationService,
    request_principal: RequestPrincipal,
    project_id: int,
    policy: ToolPolicy,
) -> tuple[ProjectReadContext, ResolvedPrincipal]:
    row = await transaction.fetch_one(_PROJECT_CONTEXT_FOR_UPDATE_SQL, (project_id,))
    if row is None:
        raise InvalidRequestError("Project was not found.")
    authorization = await authorizer.authorize_tenant(
        transaction,
        request_principal,
        tenant_id=row["tenant_id"],
        policy=policy,
        project_id=project_id,
    )
    readable = authorization.readable_source_tenant_ids
    return (
        ProjectReadContext(
            project_id=row["project_id"],
            tenant_id=row["tenant_id"],
            project_name=row["project_name"],
            project_revision=row["project_revision"],
            is_locked=bool(row.get("is_locked", False)),
            readable_source_tenant_ids=readable,
        ),
        authorization.principal,
    )


async def _owned_change_set(
    transaction: WriteTransaction,
    *,
    change_set_id: UUID,
    project_id: int,
    principal: ResolvedPrincipal,
    for_update: bool,
) -> dict[str, Any]:
    row = await transaction.fetch_one(
        _GET_FOR_UPDATE_SQL if for_update else _GET_SQL,
        (change_set_id, project_id),
    )
    if row is None or row["created_by_principal_id"] != principal.principal_id:
        raise ProjectChangeSetNotFoundError()
    return row


async def _expire_change_set_if_due(
    transaction: WriteTransaction,
    *,
    row: Mapping[str, Any],
    project_id: int,
    principal: ResolvedPrincipal,
    correlation_id: UUID,
) -> dict[str, Any] | None:
    if principal.principal_id is None:
        return None
    operation_time = await transaction.fetch_one(_DATABASE_TIME_SQL, ())
    assert operation_time is not None
    expired = await transaction.fetch_one(
        _EXPIRE_CHANGE_SET_SQL,
        (
            operation_time["current_time"],
            row["project_change_set_id"],
            project_id,
            principal.principal_id,
        ),
    )
    if expired is None:
        return None
    await _insert_event(
        transaction,
        change_set_id=expired["project_change_set_id"],
        project_id=project_id,
        event_type="expired",
        draft_revision=expired["draft_revision"],
        section=None,
        action_count=0,
        outcome="expired",
        metadata={},
        correlation_id=correlation_id,
    )
    return expired


def _validate_stage_payload_manifest(
    *,
    dataset: ProjectChangeSetDataset,
    payload_mode: ProjectStagePayloadMode,
    total_payload_bytes: int | None,
) -> None:
    if payload_mode == "records":
        if total_payload_bytes is not None:
            raise InvalidRequestError("Record Stage Batches cannot declare payload fragment bytes.")
        return
    if dataset != "generated_code" or total_payload_bytes is None:
        raise InvalidRequestError(
            "JSON fragment Stage Batches are available only for generated_code."
        )


async def _insert_event(
    transaction: WriteTransaction,
    *,
    change_set_id: UUID,
    project_id: int,
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
            project_id,
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


def _audit_project_input(arguments: Mapping[str, Any]) -> dict[str, str | int]:
    project_id = arguments.get("project_id")
    return {
        "schema_version": ("2.0" if arguments.get("schema_version", "2.0") == "2.0" else "invalid"),
        "project_id": project_id if type(project_id) is int and project_id > 0 else "invalid",
    }


def _audit_revision_input(arguments: Mapping[str, Any]) -> dict[str, str | int]:
    result = _audit_project_input(arguments)
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


def _audit_begin_stage_batch(arguments: Mapping[str, Any]) -> dict[str, str | int]:
    result = _audit_revision_input(arguments)
    dataset = arguments.get("dataset")
    for name in ("total_record_count", "total_chunk_count", "total_payload_bytes"):
        value = arguments.get(name)
        result[name] = (
            value
            if type(value) is int and value > 0
            else "none"
            if name == "total_payload_bytes" and value is None
            else "invalid"
        )
    payload_mode = arguments.get("payload_mode", "records")
    result["payload_mode"] = (
        payload_mode if payload_mode in {"records", "json_fragments"} else "invalid"
    )
    result["dataset"] = (
        dataset
        if isinstance(dataset, str) and dataset in CHANGE_SET_DATASETS_BY_NAME
        else "invalid"
    )
    return result


def _audit_put_stage_chunk(arguments: Mapping[str, Any]) -> dict[str, str | int]:
    result = _audit_project_input(arguments)
    dataset = arguments.get("dataset")
    result["dataset"] = (
        dataset
        if isinstance(dataset, str) and dataset in CHANGE_SET_DATASETS_BY_NAME
        else "invalid"
    )
    chunk_index = arguments.get("chunk_index")
    result["chunk_index"] = (
        chunk_index if type(chunk_index) is int and chunk_index > 0 else "invalid"
    )
    records = arguments.get("records")
    result["record_count"] = len(cast(list[object], records)) if isinstance(records, list) else 0
    payload_mode = arguments.get("payload_mode", "records")
    result["payload_mode"] = (
        payload_mode if payload_mode in {"records", "json_fragments"} else "invalid"
    )
    fragment = arguments.get("payload_fragment_base64")
    result["payload_fragment_base64_characters"] = len(fragment) if isinstance(fragment, str) else 0
    return result


def _audit_get_input(arguments: Mapping[str, Any]) -> dict[str, str | int]:
    result = _audit_project_input(arguments)
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
