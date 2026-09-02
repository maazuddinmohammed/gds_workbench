"""Governed Model Change Set drafting and future-graph validation."""

# Pyright cannot see that @server.tool registers these nested handlers.
# pyright: reportUnusedFunction=false

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from datetime import datetime
from typing import TYPE_CHECKING, Annotated, Any, Literal, LiteralString, cast
from uuid import UUID, uuid4

from psycopg.types.json import Jsonb
from pydantic import Field

from gds_etl_workbench.adapters.auth.identity import AuthenticationError, IdentityProvider
from gds_etl_workbench.application.authorization import AuthorizationService, ResolvedPrincipal
from gds_etl_workbench.domain.assertion_safety import ASSERTION_SECTION_MAX_BYTES
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
    StageBatchNotActiveError,
    StageBatchNotFoundError,
    StageChunkConflictError,
    WorkbenchError,
)
from gds_etl_workbench.domain.modeling_records import normalize_model_key_value
from gds_etl_workbench.infrastructure.postgres import WriteDatabase, WriteTransaction
from gds_etl_workbench.tools.catalog.visibility import VISIBLE_OBJECTS_CTE
from gds_etl_workbench.tools.modeling.common import ModelReadContext
from gds_etl_workbench.tools.snapshots.model.contracts import (
    CHANGE_SET_DATASETS_BY_NAME,
    DATASETS_BY_NAME,
    ModelChangeSetDataset,
    ModelDataset,
)
from gds_etl_workbench.tools.snapshots.model.selection import build_model_snapshot

from .action_review import DatasetActionReview
from .common import (
    MAX_MODEL_STAGE_CHUNK_BYTES,
    MAX_MODEL_STAGE_FRAGMENT_BASE64_CHARACTERS,
    MAX_MODEL_STAGE_PAYLOAD_BYTES,
    MAX_STAGE_CHUNK_RECORDS,
    MAX_STAGE_CHUNKS,
    SHA256_PATTERN,
    ChangeSetContractModel,
    canonical_records_bytes,
    canonical_records_sha256,
    change_set_annotations,
    decode_canonical_base64_fragment,
    stage_batch_sha256,
)
from .model_apply import ModelMaterializer
from .model_validation import (
    ModelValidationIssue,
    PhysicalModelCatalog,
    ValidatedModelChangeSet,
    validate_future_graph,
    validate_staged_records,
)

if TYPE_CHECKING:
    from mcp.server.mcpserver import Context, MCPServer

    from gds_etl_workbench.adapters.mcp.tool_audit import ToolCallAuditMiddleware

POLICY = ToolPolicy.TENANT_MODEL_WRITE
READ_POLICY = ToolPolicy.TENANT_READ
ContractModel = ChangeSetContractModel
_annotations = change_set_annotations
ModelStagePayloadMode = Literal["records", "json_fragments"]

READ_SECTION_COLUMNS = (
    "model_input_scope_document",
    "profiling_document",
    "analysis_document",
    "assertion_document",
    "conceptual_document",
    "logical_document",
    "dimensional_document",
    "model_binding_document",
    "mapping_document",
    "code_generation_document",
    "validation_document",
)
WRITE_SECTION_COLUMNS = READ_SECTION_COLUMNS

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
       object.object_id,
       placement_tenant.tenant_code,
       system.system_code,
       connection.connection_code,
       object.object_schema,
       object.object_name,
       attribute.attribute_id,
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
  LEFT JOIN core.tenant AS placement_tenant
    ON placement_tenant.tenant_id = connection.tenant_id
   AND placement_tenant.is_active
  LEFT JOIN core.system AS system
    ON system.system_id = connection.system_id
   AND system.is_active
  LEFT JOIN core.attribute AS attribute
    ON attribute.object_id = object.object_id
   AND attribute.is_active
"""

_MODEL_OBJECT_ELIGIBILITY_SQL: LiteralString = """
SELECT object_id,
       is_model_input_eligible,
       is_dimensional_source_eligible,
       is_logical_mapping_target_eligible,
       is_dimensional_mapping_target_eligible
  FROM workflow.list_model_object_eligibility(%s)
"""

_MODEL_ATTRIBUTE_ELIGIBILITY_SQL: LiteralString = """
SELECT attribute_id,
       is_model_input_eligible,
       is_dimensional_source_eligible,
       is_logical_mapping_target_eligible,
       is_dimensional_mapping_target_eligible
  FROM workflow.list_model_attribute_eligibility(%s)
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

_SERIALIZE_CREATE_SQL: LiteralString = """
SELECT pg_advisory_xact_lock(
    hashtextextended(
        'mcp.model_change_set:' || %s::TEXT || ':' || %s::TEXT,
        0
    )
)
"""

_DATABASE_TIME_SQL: LiteralString = """
SELECT clock_timestamp() AS current_time
"""

_LOCK_OWNED_CHANGE_SETS_SQL: LiteralString = """
SELECT change_set.model_change_set_id
  FROM mcp.model_change_set AS change_set
 WHERE change_set.model_id = %s
   AND change_set.created_by_principal_id = %s
   AND change_set.workflow_run_id IS NULL
   AND change_set.model_change_set_status IN ('active', 'validated')
 ORDER BY change_set.model_change_set_id
 FOR UPDATE
"""

_FIND_ONGOING_SQL: LiteralString = """
WITH operation_time AS MATERIALIZED (
    SELECT %s::TIMESTAMPTZ AS current_time
)
SELECT model_change_set_id,
       model_change_set_status,
       draft_revision,
       created_time,
       expires_time
  FROM mcp.model_change_set
 CROSS JOIN operation_time
 WHERE model_id = %s
   AND created_by_principal_id = %s
   AND workflow_run_id IS NULL
   AND model_change_set_status IN ('active', 'validated')
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
    UPDATE mcp.model_change_set AS change_set
       SET model_change_set_status = 'expired',
           terminal_time = operation_time.current_time
      FROM operation_time
     WHERE change_set.model_id = %s
       AND change_set.created_by_principal_id = %s
       AND change_set.workflow_run_id IS NULL
       AND change_set.model_change_set_status IN ('active', 'validated')
       AND change_set.expires_time <= operation_time.current_time
    RETURNING change_set.model_change_set_id,
              change_set.draft_revision,
              change_set.terminal_time
),
expired_batches AS (
    UPDATE mcp.model_stage_batch AS batch
       SET stage_batch_status = 'expired',
           terminal_time = expired_change_set.terminal_time
      FROM expired_change_set
     WHERE batch.model_change_set_id = expired_change_set.model_change_set_id
       AND batch.stage_batch_status = 'active'
    RETURNING batch.stage_batch_id
)
SELECT expired_change_set.model_change_set_id,
       expired_change_set.draft_revision
  FROM expired_change_set
"""

_EXPIRE_CHANGE_SET_SQL: LiteralString = """
WITH operation_time AS MATERIALIZED (
    SELECT %s::TIMESTAMPTZ AS current_time
),
expired_change_set AS (
    UPDATE mcp.model_change_set AS change_set
       SET model_change_set_status = 'expired',
           terminal_time = operation_time.current_time
      FROM operation_time
     WHERE change_set.model_change_set_id = %s
       AND change_set.model_id = %s
       AND change_set.created_by_principal_id = %s
       AND change_set.workflow_run_id IS NULL
       AND change_set.model_change_set_status IN ('active', 'validated')
       AND change_set.expires_time <= operation_time.current_time
    RETURNING change_set.*
),
expired_batches AS (
    UPDATE mcp.model_stage_batch AS batch
       SET stage_batch_status = 'expired',
           terminal_time = expired_change_set.terminal_time
      FROM expired_change_set
     WHERE batch.model_change_set_id = expired_change_set.model_change_set_id
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
INSERT INTO mcp.model_change_set (
    model_change_set_id,
    model_id,
    model_change_set_status,
    base_model_revision,
    base_source_context_digest,
    base_assertion_digest,
    base_policy_digest,
    created_by_principal_id,
    correlation_id,
    created_time,
    last_activity_time,
    expires_time
)
SELECT %s,
       model.model_id,
       'active',
       model.model_revision,
       repeat(md5('scope:' || model.model_id::TEXT || ':' || model.model_revision::TEXT), 2),
       repeat(md5('assertion:' || model.model_id::TEXT || ':' || model.model_revision::TEXT), 2),
       repeat(md5(
           'policy:' || jsonb_build_object(
               'model_id', model.model_id,
               'silver_model_naming_instructions',
                   model.silver_model_naming_instructions,
               'silver_model_audit_columns_template',
                   model.silver_model_audit_columns_template,
               'gold_model_naming_instructions',
                   model.gold_model_naming_instructions,
               'gold_model_technical_columns_template',
                   model.gold_model_technical_columns_template,
               'gold_model_audit_columns_template',
                   model.gold_model_audit_columns_template
           )::TEXT
       ), 2),
       %s,
       %s,
       operation_time.current_time,
       operation_time.current_time,
       operation_time.current_time + INTERVAL '4 hours'
  FROM model.model
 CROSS JOIN operation_time
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
SELECT model_change_set.*,
       model_change_set.expires_time <= clock_timestamp() AS is_expired
  FROM mcp.model_change_set AS model_change_set
 WHERE model_change_set.model_change_set_id = %s
   AND model_change_set.model_id = %s
 FOR UPDATE
"""

_GET_SQL: LiteralString = """
SELECT model_change_set.*,
       model_change_set.expires_time <= clock_timestamp() AS is_expired
  FROM mcp.model_change_set AS model_change_set
 WHERE model_change_set.model_change_set_id = %s
   AND model_change_set.model_id = %s
"""

_STAGE_SQL: LiteralString = """
WITH operation_time AS MATERIALIZED (
    SELECT clock_timestamp() AS current_time
)
UPDATE mcp.model_change_set AS change_set
   SET model_input_scope_document = %s,
       profiling_document = %s,
       analysis_document = %s,
       assertion_document = %s,
       conceptual_document = %s,
       logical_document = %s,
       dimensional_document = %s,
       model_binding_document = %s,
       mapping_document = %s,
       code_generation_document = %s,
       validation_document = %s,
       model_change_set_status = 'active',
       draft_revision = draft_revision + 1,
       candidate_digest = NULL,
       validation_outcome = NULL,
       validated_time = NULL,
       last_activity_time = operation_time.current_time,
       expires_time = operation_time.current_time + INTERVAL '4 hours'
  FROM operation_time
 WHERE change_set.model_change_set_id = %s
   AND change_set.model_id = %s
   AND change_set.created_by_principal_id = %s
   AND change_set.workflow_run_id IS NULL
   AND change_set.model_change_set_status IN ('active', 'validated')
   AND change_set.expires_time > operation_time.current_time
   AND change_set.draft_revision IS NOT DISTINCT FROM %s
RETURNING change_set.draft_revision,
          change_set.model_change_set_status,
          change_set.expires_time
"""

_LOCK_ACTIVE_MODEL_STAGE_BATCHES_SQL: LiteralString = """
SELECT batch.stage_batch_id
  FROM mcp.model_stage_batch AS batch
 WHERE batch.model_change_set_id = %s
   AND batch.dataset_name = %s
   AND batch.stage_batch_status = 'active'
 ORDER BY batch.stage_batch_id
 FOR UPDATE
"""

_EXPIRE_MODEL_STAGE_BATCH_SQL: LiteralString = """
WITH operation_time AS MATERIALIZED (
    SELECT %s::TIMESTAMPTZ AS current_time
)
UPDATE mcp.model_stage_batch AS batch
   SET stage_batch_status = 'expired',
       terminal_time = operation_time.current_time
  FROM operation_time
 WHERE batch.model_change_set_id = %s
   AND batch.dataset_name = %s
   AND batch.stage_batch_status = 'active'
   AND batch.expires_time <= operation_time.current_time
RETURNING batch.stage_batch_id
"""

_LOCK_ACTIVE_MODEL_STAGE_BATCH_BY_ID_SQL: LiteralString = """
SELECT batch.stage_batch_id
  FROM mcp.model_stage_batch AS batch
 WHERE batch.stage_batch_id = %s
   AND batch.model_change_set_id = %s
   AND batch.model_id = %s
   AND batch.stage_batch_status = 'active'
 FOR UPDATE
"""

_EXPIRE_MODEL_STAGE_BATCH_BY_ID_SQL: LiteralString = """
WITH operation_time AS MATERIALIZED (
    SELECT %s::TIMESTAMPTZ AS current_time
)
UPDATE mcp.model_stage_batch AS batch
   SET stage_batch_status = 'expired',
       terminal_time = operation_time.current_time
  FROM operation_time
 WHERE batch.stage_batch_id = %s
   AND batch.model_change_set_id = %s
   AND batch.model_id = %s
   AND batch.stage_batch_status = 'active'
   AND batch.expires_time <= operation_time.current_time
RETURNING batch.stage_batch_id
"""

_FIND_MODEL_STAGE_BATCH_SQL: LiteralString = """
SELECT batch.*,
       batch.expires_time <= clock_timestamp() AS is_expired,
       CASE batch.payload_mode
           WHEN 'json_fragments' THEN (
               SELECT count(*)
                 FROM mcp.model_stage_payload_chunk AS chunk
                WHERE chunk.stage_batch_id = batch.stage_batch_id
           )
           ELSE (
               SELECT count(*)
                 FROM mcp.model_stage_chunk AS chunk
                WHERE chunk.stage_batch_id = batch.stage_batch_id
           )
       END AS received_chunk_count
  FROM mcp.model_stage_batch AS batch
 WHERE batch.model_change_set_id = %s
   AND batch.dataset_name = %s
   AND batch.stage_batch_status = 'active'
 FOR UPDATE
"""

_CREATE_MODEL_STAGE_BATCH_SQL: LiteralString = """
WITH operation_time AS MATERIALIZED (
    SELECT %s::TIMESTAMPTZ AS current_time
)
INSERT INTO mcp.model_stage_batch (
    stage_batch_id,
    model_change_set_id,
    model_id,
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
  FROM mcp.model_change_set AS change_set
 CROSS JOIN operation_time
 WHERE change_set.model_change_set_id = %s
   AND change_set.model_id = %s
   AND change_set.created_by_principal_id = %s
   AND change_set.workflow_run_id IS NULL
   AND change_set.model_change_set_status IN ('active', 'validated')
   AND change_set.expires_time > operation_time.current_time
   AND change_set.draft_revision IS NOT DISTINCT FROM %s
RETURNING *, 0::BIGINT AS received_chunk_count
"""

_GET_MODEL_STAGE_BATCH_FOR_UPDATE_SQL: LiteralString = """
SELECT batch.*,
       batch.expires_time <= clock_timestamp() AS is_expired
  FROM mcp.model_stage_batch AS batch
 WHERE stage_batch_id = %s
   AND model_change_set_id = %s
   AND model_id = %s
 FOR UPDATE
"""

_GET_MODEL_STAGE_CHUNK_SQL: LiteralString = """
SELECT chunk_sha256, records_document, record_count
  FROM mcp.model_stage_chunk
 WHERE stage_batch_id = %s
   AND chunk_index = %s
"""

_MODEL_STAGE_CHUNK_TOTALS_SQL: LiteralString = """
SELECT count(*) AS chunk_count,
       coalesce(sum(record_count), 0) AS record_count
  FROM mcp.model_stage_chunk
 WHERE stage_batch_id = %s
"""

_INSERT_MODEL_STAGE_CHUNK_SQL: LiteralString = """
INSERT INTO mcp.model_stage_chunk (
    stage_batch_id, chunk_index, record_count, chunk_sha256, records_document
)
VALUES (%s, %s, %s, %s, %s)
RETURNING record_count
"""

_TOUCH_MODEL_STAGE_BATCH_SQL: LiteralString = """
WITH operation_time AS MATERIALIZED (
    SELECT clock_timestamp() AS current_time
)
UPDATE mcp.model_stage_batch AS batch
   SET last_activity_time = operation_time.current_time
  FROM operation_time
 WHERE stage_batch_id = %s
   AND batch.stage_batch_status = 'active'
   AND batch.expires_time > operation_time.current_time
RETURNING batch.expires_time
"""

_GET_MODEL_STAGE_CHUNKS_SQL: LiteralString = """
SELECT chunk_index, record_count, chunk_sha256, records_document
  FROM mcp.model_stage_chunk
 WHERE stage_batch_id = %s
 ORDER BY chunk_index
"""

_GET_MODEL_STAGE_PAYLOAD_CHUNK_SQL: LiteralString = """
SELECT chunk_sha256, chunk_byte_count, payload_fragment
  FROM mcp.model_stage_payload_chunk
 WHERE stage_batch_id = %s
   AND chunk_index = %s
"""

_MODEL_STAGE_PAYLOAD_CHUNK_TOTALS_SQL: LiteralString = """
SELECT count(*) AS chunk_count,
       coalesce(sum(chunk_byte_count), 0) AS payload_byte_count
  FROM mcp.model_stage_payload_chunk
 WHERE stage_batch_id = %s
"""

_INSERT_MODEL_STAGE_PAYLOAD_CHUNK_SQL: LiteralString = """
INSERT INTO mcp.model_stage_payload_chunk (
    stage_batch_id, chunk_index, chunk_byte_count, chunk_sha256, payload_fragment
)
VALUES (%s, %s, %s, %s, %s)
RETURNING chunk_byte_count
"""

_GET_MODEL_STAGE_PAYLOAD_CHUNKS_SQL: LiteralString = """
SELECT chunk_index, chunk_byte_count, chunk_sha256, payload_fragment
  FROM mcp.model_stage_payload_chunk
 WHERE stage_batch_id = %s
 ORDER BY chunk_index
"""

_MARK_MODEL_STAGE_BATCH_COMMITTED_SQL: LiteralString = """
WITH operation AS MATERIALIZED (
    SELECT clock_timestamp() AS current_time,
           %s::BIGINT AS committed_revision,
           %s::TIMESTAMPTZ AS committed_expires_time,
           %s::BIGINT AS expected_draft_revision
)
UPDATE mcp.model_stage_batch AS batch
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
UPDATE mcp.model_change_set AS change_set
   SET model_change_set_status = CASE
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
 WHERE change_set.model_change_set_id = %s
   AND change_set.model_id = %s
   AND change_set.created_by_principal_id = %s
   AND change_set.workflow_run_id IS NULL
   AND change_set.model_change_set_status IN ('active', 'validated')
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
RETURNING change_set.model_change_set_status,
          change_set.draft_revision,
          change_set.candidate_digest,
          change_set.validated_time,
          change_set.expires_time
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
WITH operation AS MATERIALIZED (
    SELECT clock_timestamp() AS current_time,
           %s::BIGINT AS expected_draft_revision,
           %s::TEXT AS expected_candidate_digest
)
UPDATE mcp.model_change_set AS change_set
   SET model_change_set_status = 'applied',
       applied_time = operation.current_time,
       terminal_time = operation.current_time,
       last_activity_time = operation.current_time
  FROM operation
 WHERE change_set.model_change_set_id = %s
   AND change_set.model_id = %s
   AND change_set.created_by_principal_id = %s
   AND change_set.workflow_run_id IS NULL
   AND change_set.model_change_set_status = 'validated'
   AND change_set.expires_time > operation.current_time
   AND change_set.draft_revision IS NOT DISTINCT FROM
       operation.expected_draft_revision
   AND change_set.candidate_digest IS NOT DISTINCT FROM
       operation.expected_candidate_digest
   AND operation.expected_candidate_digest IS NOT NULL
RETURNING change_set.model_change_set_status, change_set.applied_time
"""

_ARCHIVE_SQL: LiteralString = """
WITH operation AS MATERIALIZED (
    SELECT clock_timestamp() AS current_time,
           %s::BIGINT AS expected_draft_revision
)
UPDATE mcp.model_change_set AS change_set
   SET model_change_set_status = 'discarded',
       terminal_time = operation.current_time,
       last_activity_time = operation.current_time
  FROM operation
 WHERE change_set.model_change_set_id = %s
   AND change_set.model_id = %s
   AND change_set.created_by_principal_id = %s
   AND change_set.workflow_run_id IS NULL
   AND change_set.model_change_set_status IN ('active', 'validated')
   AND change_set.expires_time > operation.current_time
   AND change_set.draft_revision IS NOT DISTINCT FROM
       operation.expected_draft_revision
RETURNING change_set.draft_revision, change_set.terminal_time
"""


class StageModelChange(ContractModel):
    dataset: ModelChangeSetDataset = Field(
        description="Model dataset whose complete pending replacement is supplied."
    )
    records: Annotated[
        list[dict[str, object]],
        Field(
            max_length=20_000,
            description=(
                "Complete pending record list for this dataset; an empty list clears only "
                "this pending dataset and omitted datasets remain unchanged."
            ),
        ),
    ]


class ModelDatasetCount(ContractModel):
    dataset: ModelDataset
    record_count: int = Field(ge=0)


class ModelChangeSetDatasetCount(ContractModel):
    dataset: ModelChangeSetDataset
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
    dataset: ModelChangeSetDataset
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
    datasets: tuple[ModelChangeSetDatasetCount, ...] = Field(
        min_length=1,
        max_length=25,
    )
    draft_revision: int = Field(gt=0)
    status: Literal["active"] = "active"
    expires_at: datetime


class BeginModelStageBatchResult(ContractModel):
    schema_version: Literal["1.0"] = "1.0"
    model_id: int = Field(gt=0)
    model_change_set_id: UUID
    stage_batch_id: UUID
    dataset: ModelChangeSetDataset
    created: bool
    total_record_count: int = Field(gt=0, le=20_000)
    total_chunk_count: int = Field(gt=0, le=MAX_STAGE_CHUNKS)
    received_chunk_count: int = Field(ge=0, le=MAX_STAGE_CHUNKS)
    expected_draft_revision: int = Field(gt=0)
    expires_at: datetime
    payload_mode: ModelStagePayloadMode = "records"
    total_payload_bytes: int | None = Field(
        default=None,
        gt=0,
        le=MAX_MODEL_STAGE_PAYLOAD_BYTES,
    )


class PutModelStageChunkResult(ContractModel):
    schema_version: Literal["1.0"] = "1.0"
    model_id: int = Field(gt=0)
    model_change_set_id: UUID
    stage_batch_id: UUID
    dataset: ModelChangeSetDataset
    accepted: Literal[True] = True
    duplicate: bool
    chunk_index: int = Field(gt=0, le=MAX_STAGE_CHUNKS)
    record_count: int = Field(ge=0, le=MAX_STAGE_CHUNK_RECORDS)
    received_chunk_count: int = Field(gt=0, le=MAX_STAGE_CHUNKS)
    total_chunk_count: int = Field(gt=0, le=MAX_STAGE_CHUNKS)
    expires_at: datetime
    payload_mode: ModelStagePayloadMode = "records"
    payload_byte_count: int | None = Field(
        default=None,
        gt=0,
        le=MAX_MODEL_STAGE_CHUNK_BYTES,
    )


class CommitModelStageBatchResult(ContractModel):
    schema_version: Literal["1.0"] = "1.0"
    model_id: int = Field(gt=0)
    model_change_set_id: UUID
    stage_batch_id: UUID
    dataset: ModelChangeSetDataset
    committed: Literal[True] = True
    replayed: bool
    record_count: int = Field(gt=0, le=20_000)
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
    from mcp.server.mcpserver import Context as McpContext

    globals()["Context"] = McpContext

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
            row: dict[str, Any] | None = None
            created = False
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
                await transaction.fetch_one(
                    _SERIALIZE_CREATE_SQL,
                    (model.model_id, principal.principal_id),
                )
                await transaction.fetch_all(
                    _LOCK_OWNED_CHANGE_SETS_SQL,
                    (model.model_id, principal.principal_id),
                )
                operation_time = await transaction.fetch_one(_DATABASE_TIME_SQL, ())
                assert operation_time is not None
                expired_rows = await transaction.fetch_all(
                    _EXPIRE_OWNED_SQL,
                    (
                        operation_time["current_time"],
                        model.model_id,
                        principal.principal_id,
                    ),
                )
                for expired_row in expired_rows:
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
                    (
                        operation_time["current_time"],
                        model.model_id,
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
            "Replace one or more complete pending Model datasets in one transaction. Omitted "
            "datasets remain unchanged. Records must use describe_model_dataset's ID-free "
            "schemas; related replacements are checked against the complete future Model graph."
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
        changes: Annotated[
            list[StageModelChange],
            Field(
                min_length=1,
                max_length=25,
                description="One complete pending replacement per affected Model dataset.",
            ),
        ],
        schema_version: Literal["1.0"] = "1.0",
    ) -> StageModelChangeSetResult:
        del schema_version
        try:
            staged = _validate_stage_changes(changes)
            request_principal = identity_provider.request_principal(ctx.request_context.request)
            correlation_id = uuid4()
            expired: dict[str, Any] | None = None
            updated: dict[str, Any] | None = None
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
                expired = await _expire_change_set_if_due(
                    transaction,
                    row=row,
                    model_id=model.model_id,
                    principal=principal,
                    correlation_id=correlation_id,
                )
                if expired is None:
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
                                for column in WRITE_SECTION_COLUMNS
                            ),
                            model_change_set_id,
                            model.model_id,
                            principal.principal_id,
                            expected_draft_revision,
                        ),
                    )
                    if updated is None:
                        raise ModelChangeSetNotActiveError()
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
            if expired is not None:
                raise ModelChangeSetNotActiveError()
            assert updated is not None
            return StageModelChangeSetResult(
                model_id=model_id,
                model_change_set_id=model_change_set_id,
                datasets=tuple(
                    ModelChangeSetDatasetCount(
                        dataset=cast(ModelChangeSetDataset, dataset),
                        record_count=len(records),
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
        description=(
            "Begin or resume an oversized upload for one complete Model dataset replacement. "
            "Use records mode normally; only generated_code may use json_fragments. Beginning "
            "a batch is idempotent and does not change the draft revision."
        ),
        annotations=_annotations(read_only=False, idempotent=True),
        meta={"gds/toolPolicy": POLICY.value},
        structured_output=True,
    )
    async def begin_model_stage_batch(
        ctx: Context[None],
        model_id: Annotated[int, Field(gt=0)],
        model_change_set_id: UUID,
        expected_draft_revision: Annotated[int, Field(gt=0)],
        dataset: Annotated[
            ModelChangeSetDataset,
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
            ModelStagePayloadMode,
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
                le=MAX_MODEL_STAGE_PAYLOAD_BYTES,
                description=(
                    "Required decoded JSON byte count for generated_code json_fragments; "
                    "omit in records mode."
                ),
            ),
        ] = None,
        schema_version: Literal["1.0"] = "1.0",
    ) -> BeginModelStageBatchResult:
        del schema_version
        try:
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
                model, principal = await _authorize_model(
                    transaction,
                    authorizer=authorizer,
                    request_principal=request_principal,
                    model_id=model_id,
                    policy=POLICY,
                )
                if principal.principal_id is None:
                    raise AuthorizationDeniedError()
                change_set = await _owned_change_set(
                    transaction,
                    change_set_id=model_change_set_id,
                    model_id=model.model_id,
                    principal=principal,
                    for_update=True,
                )
                expired = await _expire_change_set_if_due(
                    transaction,
                    row=change_set,
                    model_id=model.model_id,
                    principal=principal,
                    correlation_id=correlation_id,
                )
                if expired is None:
                    _require_mutable(change_set)
                    if change_set["draft_revision"] != expected_draft_revision:
                        raise DraftRevisionConflictError(change_set["draft_revision"])
                    await transaction.fetch_all(
                        _LOCK_ACTIVE_MODEL_STAGE_BATCHES_SQL,
                        (model_change_set_id, dataset),
                    )
                    operation_time = await transaction.fetch_one(_DATABASE_TIME_SQL, ())
                    assert operation_time is not None
                    await transaction.fetch_all(
                        _EXPIRE_MODEL_STAGE_BATCH_SQL,
                        (
                            operation_time["current_time"],
                            model_change_set_id,
                            dataset,
                        ),
                    )
                    row = await transaction.fetch_one(
                        _FIND_MODEL_STAGE_BATCH_SQL,
                        (model_change_set_id, dataset),
                    )
                    created = row is None
                    if row is not None:
                        _require_model_stage_batch(row, principal, dataset)
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
                            _CREATE_MODEL_STAGE_BATCH_SQL,
                            (
                                operation_time["current_time"],
                                stage_batch_id,
                                model_change_set_id,
                                model.model_id,
                                dataset,
                                expected_draft_revision,
                                total_record_count,
                                total_chunk_count,
                                payload_mode,
                                total_payload_bytes,
                                batch_sha256,
                                principal.principal_id,
                                correlation_id,
                                model_change_set_id,
                                model.model_id,
                                principal.principal_id,
                                expected_draft_revision,
                            ),
                        )
                        if row is None:
                            raise ModelChangeSetNotActiveError()
            if expired is not None:
                raise ModelChangeSetNotActiveError()
            assert row is not None
            return BeginModelStageBatchResult(
                model_id=model_id,
                model_change_set_id=model_change_set_id,
                stage_batch_id=row["stage_batch_id"],
                dataset=cast(ModelChangeSetDataset, row["dataset_name"]),
                created=created,
                total_record_count=row["total_record_count"],
                total_chunk_count=row["total_chunk_count"],
                received_chunk_count=row["received_chunk_count"],
                expected_draft_revision=expected_draft_revision,
                expires_at=row["expires_time"],
                payload_mode=cast(ModelStagePayloadMode, row["payload_mode"]),
                total_payload_bytes=row["total_payload_bytes"],
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
        "begin_model_stage_batch",
        policy=POLICY,
        summarize_input=_audit_begin_stage_batch,
        retain_arguments={
            "model_id",
            "model_change_set_id",
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
            "Store one ordered chunk for an active Model Stage Batch. Supply records in records "
            "mode, or a base64 JSON fragment only for generated_code json_fragments mode. "
            "Repeated identical chunks are safe and do not change the Change Set."
        ),
        annotations=_annotations(read_only=False, idempotent=True),
        meta={"gds/toolPolicy": POLICY.value},
        structured_output=True,
    )
    async def put_model_stage_chunk(
        ctx: Context[None],
        model_id: Annotated[int, Field(gt=0)],
        model_change_set_id: UUID,
        stage_batch_id: UUID,
        dataset: Annotated[
            ModelChangeSetDataset,
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
                    "SHA-256 of normalized records, or decoded fragment bytes in "
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
            ModelStagePayloadMode,
            Field(description="Must match the Stage Batch manifest."),
        ] = "records",
        payload_fragment_base64: Annotated[
            str | None,
            Field(
                max_length=MAX_MODEL_STAGE_FRAGMENT_BASE64_CHARACTERS,
                description=(
                    "Required canonical base64 fragment in generated_code json_fragments "
                    "mode; otherwise omit."
                ),
            ),
        ] = None,
        schema_version: Literal["1.0"] = "1.0",
    ) -> PutModelStageChunkResult:
        del schema_version
        try:
            normalized: list[dict[str, object]] = []
            payload_fragment: bytes | None = None
            if payload_mode == "records":
                if not records or payload_fragment_base64 is not None:
                    raise InvalidRequestError("The Stage chunk payload mode is invalid.")
                normalized = _validate_stage_changes(
                    [StageModelChange(dataset=dataset, records=records)]
                )[dataset]
                encoded = canonical_records_bytes(normalized)
                if len(encoded) > MAX_MODEL_STAGE_CHUNK_BYTES:
                    raise InvalidRequestError("The Stage chunk exceeds the bounded byte limit.")
                if canonical_records_sha256(normalized) != chunk_sha256:
                    raise InvalidRequestError(
                        "The Stage chunk SHA-256 does not match its normalized records."
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
                model, principal = await _authorize_model(
                    transaction,
                    authorizer=authorizer,
                    request_principal=request_principal,
                    model_id=model_id,
                    policy=POLICY,
                )
                change_set = await _owned_change_set(
                    transaction,
                    change_set_id=model_change_set_id,
                    model_id=model.model_id,
                    principal=principal,
                    for_update=True,
                )
                expired = await _expire_change_set_if_due(
                    transaction,
                    row=change_set,
                    model_id=model.model_id,
                    principal=principal,
                    correlation_id=change_set["correlation_id"],
                )
                if expired is None:
                    _require_mutable(change_set)
                    await transaction.fetch_all(
                        _LOCK_ACTIVE_MODEL_STAGE_BATCH_BY_ID_SQL,
                        (stage_batch_id, model_change_set_id, model.model_id),
                    )
                    operation_time = await transaction.fetch_one(_DATABASE_TIME_SQL, ())
                    assert operation_time is not None
                    expired_batch = await transaction.fetch_one(
                        _EXPIRE_MODEL_STAGE_BATCH_BY_ID_SQL,
                        (
                            operation_time["current_time"],
                            stage_batch_id,
                            model_change_set_id,
                            model.model_id,
                        ),
                    )
                    if expired_batch is None:
                        batch = await transaction.fetch_one(
                            _GET_MODEL_STAGE_BATCH_FOR_UPDATE_SQL,
                            (stage_batch_id, model_change_set_id, model.model_id),
                        )
                        _require_model_stage_batch(batch, principal, dataset)
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
                            _GET_MODEL_STAGE_PAYLOAD_CHUNK_SQL
                            if payload_mode == "json_fragments"
                            else _GET_MODEL_STAGE_CHUNK_SQL
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
                                _MODEL_STAGE_PAYLOAD_CHUNK_TOTALS_SQL
                                if payload_mode == "json_fragments"
                                else _MODEL_STAGE_CHUNK_TOTALS_SQL
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
                                    _INSERT_MODEL_STAGE_PAYLOAD_CHUNK_SQL,
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
                                    _INSERT_MODEL_STAGE_CHUNK_SQL,
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
                                _TOUCH_MODEL_STAGE_BATCH_SQL,
                                (stage_batch_id,),
                            )
                            if touched is None:
                                raise StageBatchNotActiveError()
                        totals = await transaction.fetch_one(
                            (
                                _MODEL_STAGE_PAYLOAD_CHUNK_TOTALS_SQL
                                if payload_mode == "json_fragments"
                                else _MODEL_STAGE_CHUNK_TOTALS_SQL
                            ),
                            (stage_batch_id,),
                        )
                        assert totals is not None
            if expired is not None:
                raise ModelChangeSetNotActiveError()
            if expired_batch is not None:
                raise StageBatchNotActiveError()
            assert batch is not None
            assert totals is not None
            return PutModelStageChunkResult(
                model_id=model_id,
                model_change_set_id=model_change_set_id,
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
            raise ModelChangeSetToolError(f"{error.public_code}: {error.message}") from None
        except WorkbenchError as error:
            raise ModelChangeSetToolError(f"{error.code}: {error.message}") from None
        except Exception:
            raise ModelChangeSetToolError(
                "internal_error: The operation could not be completed."
            ) from None

    audit.register_tool(
        "put_model_stage_chunk",
        policy=POLICY,
        summarize_input=_audit_put_stage_chunk,
        retain_arguments={
            "model_id",
            "model_change_set_id",
            "stage_batch_id",
            "dataset",
            "chunk_index",
            "payload_mode",
            "schema_version",
        },
    )

    @server.tool(
        description=(
            "Verify and atomically commit one complete Model Stage Batch as that dataset's "
            "pending replacement. The response returns the new draft_revision; use it for "
            "the next batch or validation."
        ),
        annotations=_annotations(read_only=False, idempotent=True),
        meta={"gds/toolPolicy": POLICY.value},
        structured_output=True,
    )
    async def commit_model_stage_batch(
        ctx: Context[None],
        model_id: Annotated[int, Field(gt=0)],
        model_change_set_id: UUID,
        stage_batch_id: UUID,
        expected_draft_revision: Annotated[int, Field(gt=0)],
        schema_version: Literal["1.0"] = "1.0",
    ) -> CommitModelStageBatchResult:
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
                model, principal = await _authorize_model(
                    transaction,
                    authorizer=authorizer,
                    request_principal=request_principal,
                    model_id=model_id,
                    policy=POLICY,
                )
                change_set = await _owned_change_set(
                    transaction,
                    change_set_id=model_change_set_id,
                    model_id=model.model_id,
                    principal=principal,
                    for_update=True,
                )
                expired = await _expire_change_set_if_due(
                    transaction,
                    row=change_set,
                    model_id=model.model_id,
                    principal=principal,
                    correlation_id=correlation_id,
                )
                if expired is None:
                    _require_mutable(change_set)
                    await transaction.fetch_all(
                        _LOCK_ACTIVE_MODEL_STAGE_BATCH_BY_ID_SQL,
                        (stage_batch_id, model_change_set_id, model.model_id),
                    )
                    operation_time = await transaction.fetch_one(_DATABASE_TIME_SQL, ())
                    assert operation_time is not None
                    expired_batch = await transaction.fetch_one(
                        _EXPIRE_MODEL_STAGE_BATCH_BY_ID_SQL,
                        (
                            operation_time["current_time"],
                            stage_batch_id,
                            model_change_set_id,
                            model.model_id,
                        ),
                    )
                    if expired_batch is None:
                        batch = await transaction.fetch_one(
                            _GET_MODEL_STAGE_BATCH_FOR_UPDATE_SQL,
                            (stage_batch_id, model_change_set_id, model.model_id),
                        )
                        if (
                            batch is None
                            or batch["created_by_principal_id"] != principal.principal_id
                        ):
                            raise StageBatchNotFoundError()
                        if batch["expected_draft_revision"] != expected_draft_revision:
                            raise InvalidRequestError(
                                "Expected revision does not match the Stage Batch manifest."
                            )
                        if batch["stage_batch_status"] == "committed":
                            replayed = True
                            committed_revision = batch["committed_revision"]
                            committed_expires_time = batch["committed_expires_time"]
                        else:
                            _require_model_stage_batch(batch, principal, None)
                            if change_set["draft_revision"] != expected_draft_revision:
                                raise DraftRevisionConflictError(change_set["draft_revision"])
                            payload_mode = cast(ModelStagePayloadMode, batch["payload_mode"])
                            chunks = await transaction.fetch_all(
                                (
                                    _GET_MODEL_STAGE_PAYLOAD_CHUNKS_SQL
                                    if payload_mode == "json_fragments"
                                    else _GET_MODEL_STAGE_CHUNKS_SQL
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
                                assembled = _decode_canonical_stage_payload(
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
                            staged = _validate_stage_changes(
                                [
                                    StageModelChange(
                                        dataset=cast(
                                            ModelChangeSetDataset,
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
                            documents = _documents(change_set)
                            dataset_name = batch["dataset_name"]
                            section = DATASETS_BY_NAME[dataset_name].section
                            documents[section][dataset_name] = staged[dataset_name]
                            _validate_document_bounds(documents)
                            updated = await transaction.fetch_one(
                                _STAGE_SQL,
                                (
                                    *(
                                        Jsonb(documents[column.removesuffix("_document")])
                                        for column in WRITE_SECTION_COLUMNS
                                    ),
                                    model_change_set_id,
                                    model.model_id,
                                    principal.principal_id,
                                    expected_draft_revision,
                                ),
                            )
                            if updated is None:
                                raise ModelChangeSetNotActiveError()
                            await _insert_event(
                                transaction,
                                change_set_id=model_change_set_id,
                                model_id=model.model_id,
                                event_type="section_put",
                                draft_revision=updated["draft_revision"],
                                section=section,
                                action_count=len(assembled),
                                outcome="staged",
                                metadata={"datasets": [dataset_name]},
                                correlation_id=correlation_id,
                            )
                            marked = await transaction.fetch_one(
                                _MARK_MODEL_STAGE_BATCH_COMMITTED_SQL,
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
                raise ModelChangeSetNotActiveError()
            if expired_batch is not None:
                raise StageBatchNotActiveError()
            assert batch is not None
            assert committed_revision is not None
            assert committed_expires_time is not None
            return CommitModelStageBatchResult(
                model_id=model_id,
                model_change_set_id=model_change_set_id,
                stage_batch_id=stage_batch_id,
                dataset=cast(ModelChangeSetDataset, batch["dataset_name"]),
                replayed=replayed,
                record_count=batch["total_record_count"],
                draft_revision=committed_revision,
                expires_at=committed_expires_time,
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
        "commit_model_stage_batch",
        policy=POLICY,
        summarize_input=_audit_revision_input,
        retain_arguments={
            "model_id",
            "model_change_set_id",
            "stage_batch_id",
            "expected_draft_revision",
            "schema_version",
        },
    )

    @server.tool(
        description=(
            "Read the caller's Model Change Set without requiring a current Tenant Lock. "
            "Omit dataset for counts only; provide dataset to return only that pending "
            "ID-free dataset."
        ),
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
                    for_update=True,
                )
                expired = await _expire_change_set_if_due(
                    transaction,
                    row=row,
                    model_id=model.model_id,
                    principal=principal,
                    correlation_id=row["correlation_id"],
                )
                if expired is not None:
                    row = expired
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
        description=(
            "Validate one exact Model Change Set revision against the complete future graph "
            "and seal it for Apply. This does not execute generated Code or Validation Checks."
        ),
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
            expired: dict[str, Any] | None = None
            validation: ValidatedModelChangeSet | None = None
            updated: dict[str, Any] | None = None
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
                expired = await _expire_change_set_if_due(
                    transaction,
                    row=row,
                    model_id=model.model_id,
                    principal=principal,
                    correlation_id=correlation_id,
                )
                if expired is None:
                    _require_mutable(row)
                    if row["draft_revision"] != expected_draft_revision:
                        raise DraftRevisionConflictError(row["draft_revision"])
                    _require_mcp_writable_pending(row)
                    validation = await _validate_locked_change_set(transaction, model, row)
                    if validation.valid:
                        assert validation.candidate_digest is not None
                    outcome = _validation_outcome(validation)
                    updated = await transaction.fetch_one(
                        _RECORD_VALIDATION_SQL,
                        (
                            validation.valid,
                            validation.candidate_digest if validation.valid else None,
                            Jsonb(outcome),
                            model_change_set_id,
                            model.model_id,
                            principal.principal_id,
                            expected_draft_revision,
                        ),
                    )
                    if updated is None:
                        raise ModelChangeSetNotActiveError()
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
            if expired is not None:
                raise ModelChangeSetNotActiveError()
            assert validation is not None
            assert updated is not None
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
            expired: dict[str, Any] | None = None
            validation: ValidatedModelChangeSet | None = None
            revision: dict[str, Any] | None = None
            applied: dict[str, Any] | None = None
            action_count = 0
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
                expired = await _expire_change_set_if_due(
                    transaction,
                    row=row,
                    model_id=model.model_id,
                    principal=principal,
                    correlation_id=correlation_id,
                )
                if expired is None:
                    _require_mutable(row)
                    if row["model_change_set_status"] != "validated":
                        raise ModelChangeSetNotValidatedError()
                    if row["draft_revision"] != expected_draft_revision:
                        raise DraftRevisionConflictError(row["draft_revision"])
                    _require_mcp_writable_pending(row)
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
                        (
                            expected_draft_revision,
                            validation.candidate_digest,
                            model_change_set_id,
                            model.model_id,
                            principal.principal_id,
                        ),
                    )
                    if applied is None:
                        raise ModelChangeSetNotActiveError()
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
            if expired is not None:
                raise ModelChangeSetNotActiveError()
            assert validation is not None
            assert validation.candidate_digest is not None
            assert revision is not None
            assert applied is not None
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
            expired: dict[str, Any] | None = None
            archived: dict[str, Any] | None = None
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
                expired = await _expire_change_set_if_due(
                    transaction,
                    row=row,
                    model_id=model.model_id,
                    principal=principal,
                    correlation_id=correlation_id,
                )
                if expired is None:
                    _require_mutable(row)
                    if row["draft_revision"] != expected_draft_revision:
                        raise DraftRevisionConflictError(row["draft_revision"])
                    archived = await transaction.fetch_one(
                        _ARCHIVE_SQL,
                        (
                            expected_draft_revision,
                            model_change_set_id,
                            model.model_id,
                            principal.principal_id,
                        ),
                    )
                    if archived is None:
                        raise ModelChangeSetNotActiveError()
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
            if expired is not None:
                raise ModelChangeSetNotActiveError()
            assert archived is not None
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


async def _expire_change_set_if_due(
    transaction: WriteTransaction,
    *,
    row: Mapping[str, Any],
    model_id: int,
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
            row["model_change_set_id"],
            model_id,
            principal.principal_id,
        ),
    )
    if expired is None:
        return None
    await _insert_event(
        transaction,
        change_set_id=expired["model_change_set_id"],
        model_id=model_id,
        event_type="expired",
        draft_revision=expired["draft_revision"],
        section=None,
        action_count=0,
        outcome="expired",
        metadata={},
        correlation_id=correlation_id,
    )
    return expired


def _require_mutable(row: Mapping[str, Any]) -> None:
    _require_generic_change_set(row)
    if row["model_change_set_status"] not in ("active", "validated"):
        raise ModelChangeSetNotActiveError()
    if row.get("is_expired") is True:
        raise ModelChangeSetNotActiveError()


def _require_model_stage_batch(
    row: Mapping[str, Any] | None,
    principal: ResolvedPrincipal,
    dataset: ModelChangeSetDataset | None,
) -> None:
    if row is None or row["created_by_principal_id"] != principal.principal_id:
        raise StageBatchNotFoundError()
    if dataset is not None and row["dataset_name"] != dataset:
        raise InvalidRequestError("Dataset does not match the Stage Batch manifest.")
    if row["dataset_name"] not in CHANGE_SET_DATASETS_BY_NAME:
        raise InvalidRequestError("The Stage Batch dataset is not writable through MCP.")
    if row["stage_batch_status"] != "active":
        raise StageBatchNotActiveError()
    if row.get("is_expired") is True:
        raise StageBatchNotActiveError()


def _validate_stage_changes(
    changes: list[StageModelChange],
) -> dict[str, list[dict[str, object]]]:
    staged: dict[str, list[dict[str, object]]] = {}
    for change in changes:
        if change.dataset in staged:
            raise InvalidRequestError("Each Model dataset may be staged only once per call.")
        records, issues = validate_staged_records(change.dataset, change.records)
        if issues:
            issue = issues[0]
            field_path = ".".join(issue.fields) or "<record>"
            raise InvalidRequestError(
                f"Record {issue.record_number or 1} at {field_path}: {issue.message}"
            )
        staged[change.dataset] = [record.model_dump(mode="json") for record in records]
    if sum(len(records) for records in staged.values()) > 50_000:
        raise InvalidRequestError("A Model Change Set stage is limited to 50,000 records.")
    return staged


def _validate_stage_payload_manifest(
    *,
    dataset: ModelChangeSetDataset,
    payload_mode: ModelStagePayloadMode,
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


def _decode_canonical_stage_payload(
    payload: bytes,
    *,
    expected_record_count: int,
) -> list[dict[str, object]]:
    try:
        parsed = cast(object, json.loads(payload.decode("utf-8")))
    except (UnicodeDecodeError, json.JSONDecodeError):
        raise InvalidRequestError("The Stage payload is not valid UTF-8 JSON.") from None
    records = cast(list[object], parsed) if isinstance(parsed, list) else None
    if (
        records is None
        or len(records) != expected_record_count
        or any(not isinstance(record, dict) for record in records)
    ):
        raise InvalidRequestError("The Stage payload must contain the declared JSON record array.")
    return cast(list[dict[str, object]], records)


def _validate_document_bounds(
    documents: dict[str, dict[str, list[dict[str, object]]]],
) -> None:
    if sum(len(records) for section in documents.values() for records in section.values()) > 50_000:
        raise InvalidRequestError("A Model Change Set is limited to 50,000 pending records.")
    for section_name, section in documents.items():
        encoded_size = len(
            json.dumps(
                section,
                ensure_ascii=False,
                separators=(",", ":"),
            ).encode("utf-8")
        )
        if section_name == "assertion" and encoded_size > ASSERTION_SECTION_MAX_BYTES:
            raise InvalidRequestError("The Assertion Section exceeds 4 MiB.")
        if section_name not in {"assertion", "code_generation"} and encoded_size > 16 * 1024 * 1024:
            raise InvalidRequestError("A Model Change Set section exceeds 16 MiB.")


def _documents(row: Mapping[str, Any]) -> dict[str, dict[str, list[dict[str, object]]]]:
    return {
        column.removesuffix("_document"): dict(row[column] or {}) for column in READ_SECTION_COLUMNS
    }


def _pending_datasets(row: Mapping[str, Any]) -> dict[str, list[dict[str, object]]]:
    return {
        dataset: records
        for section in _documents(row).values()
        for dataset, records in section.items()
    }


def _require_mcp_writable_pending(row: Mapping[str, Any]) -> None:
    _require_generic_change_set(row)
    if any(dataset not in CHANGE_SET_DATASETS_BY_NAME for dataset in _pending_datasets(row)):
        raise InvalidRequestError(
            "The Model Change Set contains a dataset that is not writable through MCP."
        )


def _require_generic_change_set(row: Mapping[str, Any]) -> None:
    if row.get("workflow_run_id") is not None:
        raise InvalidRequestError(
            "Workflow-bound Model Change Sets are managed only by their Workflow Run."
        )


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
    staged_documents = cast(
        dict[ModelChangeSetDataset, list[dict[str, object]]],
        _pending_datasets(row),
    )
    snapshot = await build_model_snapshot(transaction, model)
    physical_scope = await _load_physical_scope(transaction, model)
    return validate_future_graph(
        snapshot=snapshot,
        staged_documents=staged_documents,
        physical_scope=physical_scope,
    )


async def _load_physical_scope(
    transaction: WriteTransaction,
    model: ModelReadContext,
) -> PhysicalModelCatalog:
    rows = await transaction.fetch_all(_MODEL_PHYSICAL_SCOPE_SQL, (model.tenant_id,))
    if not rows:
        raise InvalidRequestError("Model physical Scope could not be resolved.")
    system_rows = await transaction.fetch_all(_ACTIVE_SYSTEM_CODES_SQL)
    other_model_rows = await transaction.fetch_all(
        _OTHER_MODEL_NAMES_SQL,
        (model.tenant_id, model.model_id),
    )
    object_eligibility_rows = await transaction.fetch_all(
        _MODEL_OBJECT_ELIGIBILITY_SQL,
        (model.model_id,),
    )
    attribute_eligibility_rows = await transaction.fetch_all(
        _MODEL_ATTRIBUTE_ELIGIBILITY_SQL,
        (model.model_id,),
    )
    objects: set[tuple[str, str, str, str, str]] = set()
    attributes: set[tuple[str, str, str, str, str, str]] = set()
    object_keys_by_id: dict[int, tuple[str, str, str, str, str]] = {}
    attribute_keys_by_id: dict[int, tuple[str, str, str, str, str, str]] = {}
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
            object_id = physical["object_id"]
            if isinstance(object_id, int):
                object_keys_by_id[object_id] = object_key
            attribute_name = physical["attribute_name"]
            if isinstance(attribute_name, str):
                attribute_key = (*object_key, normalize_model_key_value(attribute_name))
                attributes.add(attribute_key)
                attribute_id = physical["attribute_id"]
                if isinstance(attribute_id, int):
                    attribute_keys_by_id[attribute_id] = attribute_key

    eligibility_flags = (
        "is_model_input_eligible",
        "is_dimensional_source_eligible",
        "is_logical_mapping_target_eligible",
        "is_dimensional_mapping_target_eligible",
    )
    eligible_objects: dict[str, set[tuple[str, str, str, str, str]]] = {
        flag: set() for flag in eligibility_flags
    }
    eligible_attributes: dict[str, set[tuple[str, str, str, str, str, str]]] = {
        flag: set() for flag in eligibility_flags
    }
    for eligibility in object_eligibility_rows:
        key = object_keys_by_id.get(eligibility["object_id"])
        if key is not None:
            for flag in eligibility_flags:
                if eligibility[flag] is True:
                    eligible_objects[flag].add(key)
    for eligibility in attribute_eligibility_rows:
        key = attribute_keys_by_id.get(eligibility["attribute_id"])
        if key is not None:
            for flag in eligibility_flags:
                if eligibility[flag] is True:
                    eligible_attributes[flag].add(key)
    return PhysicalModelCatalog(
        model_tenant_code=rows[0]["model_tenant_code"],
        active_system_codes=frozenset(
            normalize_model_key_value(system["system_code"]) for system in system_rows
        ),
        objects=frozenset(objects),
        attributes=frozenset(attributes),
        model_input_objects=frozenset(eligible_objects["is_model_input_eligible"]),
        model_input_attributes=frozenset(eligible_attributes["is_model_input_eligible"]),
        dimensional_source_objects=frozenset(eligible_objects["is_dimensional_source_eligible"]),
        dimensional_source_attributes=frozenset(
            eligible_attributes["is_dimensional_source_eligible"]
        ),
        logical_mapping_target_objects=frozenset(
            eligible_objects["is_logical_mapping_target_eligible"]
        ),
        logical_mapping_target_attributes=frozenset(
            eligible_attributes["is_logical_mapping_target_eligible"]
        ),
        dimensional_mapping_target_objects=frozenset(
            eligible_objects["is_dimensional_mapping_target_eligible"]
        ),
        dimensional_mapping_target_attributes=frozenset(
            eligible_attributes["is_dimensional_mapping_target_eligible"]
        ),
        other_model_names=frozenset(
            normalize_model_key_value(other_model["model_name"]) for other_model in other_model_rows
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
            dataset=cast(ModelChangeSetDataset, summary.dataset),
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
    result = _audit_model_input(arguments)
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


# Shared application-service boundary. MCP handlers keep their existing local
# names; the web adapter imports only these explicit public contracts.
decode_canonical_model_stage_payload = _decode_canonical_stage_payload
model_change_set_documents = _documents
model_validation_error = _error
model_action_review = _model_action_review
pending_model_change_set_datasets = _pending_datasets
require_mcp_writable_pending = _require_mcp_writable_pending
require_model_stage_batch = _require_model_stage_batch
require_mutable_model_change_set = _require_mutable
validate_model_change_set_document_bounds = _validate_document_bounds
validate_locked_model_change_set = _validate_locked_change_set
validate_model_stage_changes = _validate_stage_changes
model_validation_outcome = _validation_outcome


__all__ = [
    "ModelStagePayloadMode",
    "ModelChangeSetDatasetCount",
    "ModelDatasetCount",
    "StageModelChange",
    "decode_canonical_model_stage_payload",
    "model_action_review",
    "model_change_set_documents",
    "model_validation_error",
    "model_validation_outcome",
    "pending_model_change_set_datasets",
    "require_mcp_writable_pending",
    "require_model_stage_batch",
    "require_mutable_model_change_set",
    "validate_locked_model_change_set",
    "validate_model_change_set_document_bounds",
    "validate_model_stage_changes",
]
