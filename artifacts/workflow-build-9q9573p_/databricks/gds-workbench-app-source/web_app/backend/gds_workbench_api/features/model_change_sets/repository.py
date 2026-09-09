"""PostgreSQL persistence for governed Model Change Sets."""

from collections.abc import Mapping
from datetime import datetime
from typing import Any, LiteralString
from uuid import UUID

from gds_etl_workbench.infrastructure.postgres import WriteTransaction
from psycopg.types.json import Jsonb

_AUTHORIZE_RECORD_REVIEW_SQL: LiteralString = """
SELECT denial_code, principal_id, model_id, tenant_id, model_name, model_revision
  FROM application.authorize_model_record_review(%s, %s, 'user', %s, %s)
"""

_REVIEW_ANALYSIS_SQL: LiteralString = """
SELECT result.*,
       from_tenant.tenant_code AS from_tenant_code,
       from_system.system_code AS from_system_code,
       from_connection.connection_code AS from_connection_code,
       from_object.object_schema AS from_object_schema,
       from_object.object_name AS from_object_name,
       from_attribute.attribute_name AS from_attribute_name,
       to_tenant.tenant_code AS to_tenant_code,
       to_system.system_code AS to_system_code,
       to_connection.connection_code AS to_connection_code,
       to_object.object_schema AS to_object_schema,
       to_object.object_name AS to_object_name,
       to_attribute.attribute_name AS to_attribute_name
  FROM workflow.analysis_result AS result
  JOIN core.object AS from_object ON from_object.object_id = result.from_object_id
  JOIN core.connection AS from_connection
    ON from_connection.connection_id = from_object.connection_id
  JOIN core.tenant AS from_tenant ON from_tenant.tenant_id = from_connection.tenant_id
  JOIN core.system AS from_system ON from_system.system_id = from_connection.system_id
  JOIN core.attribute AS from_attribute
    ON from_attribute.attribute_id = result.from_attribute_id
   AND from_attribute.object_id = result.from_object_id
  JOIN core.object AS to_object ON to_object.object_id = result.to_object_id
  JOIN core.connection AS to_connection
    ON to_connection.connection_id = to_object.connection_id
  JOIN core.tenant AS to_tenant ON to_tenant.tenant_id = to_connection.tenant_id
  JOIN core.system AS to_system ON to_system.system_id = to_connection.system_id
  JOIN core.attribute AS to_attribute
    ON to_attribute.attribute_id = result.to_attribute_id
   AND to_attribute.object_id = result.to_object_id
 WHERE result.model_id = %s AND result.analysis_result_id = ANY(%s::BIGINT[])
 ORDER BY result.analysis_result_id
 FOR UPDATE OF result
"""

_APPLY_ANALYSIS_REVIEW_SQL: LiteralString = """
UPDATE workflow.analysis_result
   SET analysis_result_is_locked = %s,
       analysis_result_status = %s,
       updated_time = CURRENT_TIMESTAMP,
       updated_by = %s
 WHERE model_id = %s AND analysis_result_id = %s
RETURNING analysis_result_id
"""

_APPLY_CONCEPTUAL_OBJECT_REVIEW_SQL: LiteralString = """
UPDATE workflow.conceptual_object
   SET conceptual_object_is_locked = %s, conceptual_object_status = %s,
       updated_time = CURRENT_TIMESTAMP, updated_by = %s
 WHERE model_id = %s AND conceptual_object_id = %s
RETURNING conceptual_object_id
"""

_APPLY_CONCEPTUAL_RELATIONSHIP_REVIEW_SQL: LiteralString = """
UPDATE workflow.conceptual_relationship
   SET conceptual_relationship_is_locked = %s, conceptual_relationship_status = %s,
       updated_time = CURRENT_TIMESTAMP, updated_by = %s
 WHERE model_id = %s AND conceptual_relationship_id = %s
RETURNING conceptual_relationship_id
"""

_APPLY_OTHER_REVIEWS_SQL: dict[str, LiteralString] = {
    "logical_submodel": """
UPDATE workflow.logical_submodel AS target
   SET logical_submodel_is_locked = %s, logical_submodel_status = %s,
       updated_time = CURRENT_TIMESTAMP, updated_by = %s
 WHERE target.model_id = %s
   AND target.logical_submodel_id = %s
RETURNING target.logical_submodel_id
""",
    "logical_entity": """
UPDATE workflow.logical_entity AS target
   SET logical_entity_is_locked = %s, logical_entity_status = %s,
       updated_time = CURRENT_TIMESTAMP, updated_by = %s
 WHERE target.model_id = %s
   AND target.logical_entity_id = %s
RETURNING target.logical_entity_id
""",
    "logical_attribute": """
UPDATE workflow.logical_attribute AS target
   SET logical_attribute_is_locked = %s, logical_attribute_status = %s,
       updated_time = CURRENT_TIMESTAMP, updated_by = %s
 WHERE target.model_id = %s
   AND target.logical_attribute_id = %s
RETURNING target.logical_attribute_id
""",
    "logical_relationship": """
UPDATE workflow.logical_relationship AS target
   SET logical_relationship_is_locked = %s, logical_relationship_status = %s,
       updated_time = CURRENT_TIMESTAMP, updated_by = %s
 WHERE target.model_id = %s
   AND target.logical_relationship_id = %s
RETURNING target.logical_relationship_id
""",
    "dimensional_submodel": """
UPDATE workflow.dimensional_submodel AS target
   SET dimensional_submodel_is_locked = %s, dimensional_submodel_status = %s,
       updated_time = CURRENT_TIMESTAMP, updated_by = %s
 WHERE target.model_id = %s
   AND target.dimensional_submodel_id = %s
RETURNING target.dimensional_submodel_id
""",
    "dimensional_entity": """
UPDATE workflow.dimensional_entity AS target
   SET dimensional_entity_is_locked = %s, dimensional_entity_status = %s,
       updated_time = CURRENT_TIMESTAMP, updated_by = %s
 WHERE target.model_id = %s
   AND target.dimensional_entity_id = %s
RETURNING target.dimensional_entity_id
""",
    "dimensional_attribute": """
UPDATE workflow.dimensional_attribute AS target
   SET dimensional_attribute_is_locked = %s, dimensional_attribute_status = %s,
       updated_time = CURRENT_TIMESTAMP, updated_by = %s
 WHERE target.model_id = %s
   AND target.dimensional_attribute_id = %s
RETURNING target.dimensional_attribute_id
""",
    "dimensional_relationship": """
UPDATE workflow.dimensional_relationship AS target
   SET dimensional_relationship_is_locked = %s, dimensional_relationship_status = %s,
       updated_time = CURRENT_TIMESTAMP, updated_by = %s
 WHERE target.model_id = %s
   AND target.dimensional_relationship_id = %s
RETURNING target.dimensional_relationship_id
""",
    "model_object_binding": """
UPDATE workflow.model_object_binding AS target
   SET model_object_binding_is_locked = %s, model_object_binding_status = %s,
       updated_time = CURRENT_TIMESTAMP, updated_by = %s
 WHERE target.model_id = %s
   AND target.model_object_binding_id = %s
RETURNING target.model_object_binding_id
""",
    "model_attribute_binding": """
UPDATE workflow.model_attribute_binding AS target
   SET model_attribute_binding_is_locked = %s, model_attribute_binding_status = %s,
       updated_time = CURRENT_TIMESTAMP, updated_by = %s
 WHERE EXISTS (SELECT 1 FROM workflow.model_object_binding b
       WHERE b.model_object_binding_id = target.model_object_binding_id
         AND b.model_id = %s)
   AND target.model_attribute_binding_id = %s
RETURNING target.model_attribute_binding_id
""",
    "mapping_dependency": """
UPDATE workflow.mapping_source_system_dependency AS target
   SET mapping_source_system_dependency_is_locked = %s,
       mapping_source_system_dependency_status = %s,
       updated_time = CURRENT_TIMESTAMP, updated_by = %s
 WHERE target.model_id = %s
   AND target.mapping_source_system_dependency_id = %s
RETURNING target.mapping_source_system_dependency_id
""",
    "mapping_object": """
UPDATE workflow.mapping_object AS target
   SET object_mapping_is_locked = %s, object_mapping_status = %s,
       updated_time = CURRENT_TIMESTAMP, updated_by = %s
 WHERE target.model_id = %s
   AND target.mapping_object_id = %s
RETURNING target.mapping_object_id
""",
    "mapping_attribute": """
UPDATE workflow.mapping_attribute AS target
   SET attribute_mapping_is_locked = %s, attribute_mapping_status = %s,
       updated_time = CURRENT_TIMESTAMP, updated_by = %s
 WHERE EXISTS (SELECT 1 FROM workflow.mapping_object m
       WHERE m.mapping_object_id = target.mapping_object_id
         AND m.model_id = %s)
   AND target.mapping_attribute_id = %s
RETURNING target.mapping_attribute_id
""",
    "generated_code": """
UPDATE workflow.generated_code AS target
   SET generated_code_is_locked = %s, generated_code_status = %s,
       updated_time = CURRENT_TIMESTAMP, updated_by = %s
 WHERE EXISTS (SELECT 1 FROM workflow.model_object_binding b
       WHERE b.model_object_binding_id = target.model_object_binding_id
         AND b.model_id = %s)
   AND target.generated_code_id = %s
RETURNING target.generated_code_id
""",
    "generated_code_source_system": """
UPDATE workflow.generated_code_source_system AS target
   SET generated_code_source_system_is_locked = %s, generated_code_source_system_status = %s,
       updated_time = CURRENT_TIMESTAMP, updated_by = %s
 WHERE EXISTS (SELECT 1 FROM workflow.generated_code c
        JOIN workflow.model_object_binding b
          ON b.model_object_binding_id = c.model_object_binding_id
       WHERE c.generated_code_id = target.generated_code_id
         AND b.model_id = %s)
   AND target.generated_code_source_system_id = %s
RETURNING target.generated_code_source_system_id
""",
    "validation_group": """
UPDATE workflow.validation_group AS target
   SET is_locked = %s, is_active = %s,
       updated_time = CURRENT_TIMESTAMP, updated_by = %s
 WHERE target.model_id = %s
   AND target.validation_group_id = %s
RETURNING target.validation_group_id
""",
    "validation_check": """
UPDATE workflow.validation_check AS target
   SET is_locked = %s, is_active = %s,
       updated_time = CURRENT_TIMESTAMP, updated_by = %s
 WHERE EXISTS (SELECT 1 FROM workflow.validation_group g
       WHERE g.validation_group_id = target.validation_group_id
         AND g.model_id = %s)
   AND target.validation_check_id = %s
RETURNING target.validation_check_id
""",
}

_REPLAY_REVIEW_SQL: LiteralString = """
SELECT change_set.model_change_set_id, event.action_count, event.event_metadata
  FROM mcp.model_change_set AS change_set
  JOIN mcp.model_change_set_event AS event
    ON event.model_change_set_id = change_set.model_change_set_id
   AND event.event_type = 'applied'
   AND event.outcome IN ('review_applied', 'bindings_applied', 'scope_added')
 WHERE change_set.model_id = %s
   AND change_set.created_by_principal_id = %s
   AND change_set.correlation_id = %s
   AND change_set.model_change_set_status = 'applied'
"""

_RUNNING_TENANT_WORKFLOW_SQL: LiteralString = """
SELECT workflow_run_id FROM application.workflow_run
 WHERE tenant_id = %s AND workflow_run_state = 'running'
 LIMIT 1
"""

_MODEL_CONTEXT_SQL: LiteralString = """
SELECT target_model.model_id,
       target_model.tenant_id,
       target_model.model_name,
       target_model.model_revision
  FROM model.model AS target_model
 WHERE target_model.tenant_id = %s
   AND target_model.model_id = %s
   AND target_model.is_active
 FOR SHARE
"""

_MODEL_CONTEXT_FOR_UPDATE_SQL: LiteralString = """
SELECT target_model.model_id,
       target_model.tenant_id,
       target_model.model_name,
       target_model.model_revision
  FROM model.model AS target_model
 WHERE target_model.tenant_id = %s
   AND target_model.model_id = %s
   AND target_model.is_active
 FOR UPDATE
"""

_EXPIRE_OWNED_SQL: LiteralString = """
UPDATE mcp.model_change_set
   SET model_change_set_status = 'expired',
       terminal_time = CURRENT_TIMESTAMP,
       last_activity_time = CURRENT_TIMESTAMP
 WHERE model_id = %s
   AND created_by_principal_id = %s
   AND workflow_run_id IS NULL
   AND model_change_set_status IN ('active', 'validated')
   AND expires_time <= CURRENT_TIMESTAMP
RETURNING model_change_set_id, draft_revision
"""

_FIND_ONGOING_SQL: LiteralString = """
SELECT model_change_set_id,
       model_change_set_status,
       base_model_revision,
       draft_revision,
       created_time,
       expires_time
  FROM mcp.model_change_set
 WHERE model_id = %s
   AND created_by_principal_id = %s
   AND workflow_run_id IS NULL
   AND model_change_set_status IN ('active', 'validated')
   AND expires_time > CURRENT_TIMESTAMP
 ORDER BY created_time DESC
 LIMIT 1
 FOR UPDATE
"""

_GET_WORKFLOW_RUN_FOR_UPDATE_SQL: LiteralString = """
SELECT locked.workflow_run_id,
       locked.model_id,
       locked.model_workflow,
       locked.workflow_execution_mode,
       locked.actor_principal_id,
       locked.workflow_run_state,
       locked.correlation_id,
       run.mapping_object_output_template_id,
       run.mapping_attribute_output_template_id
  FROM application.lock_authoring_workflow_run(%s, %s) AS locked
  JOIN application.workflow_run AS run
    ON run.workflow_run_id = locked.workflow_run_id
   AND run.model_id = locked.model_id
"""

_GET_BY_WORKFLOW_RUN_SQL: LiteralString = """
SELECT model_change_set.*,
       CURRENT_TIMESTAMP AS database_time
  FROM mcp.model_change_set AS model_change_set
 WHERE model_change_set.workflow_run_id = %s
   AND model_change_set.model_id = %s
 FOR UPDATE OF model_change_set
"""

_CREATE_SQL: LiteralString = """
INSERT INTO mcp.model_change_set (
    model_change_set_id,
    model_id,
    workflow_run_id,
    model_change_set_status,
    base_model_revision,
    base_source_context_digest,
    base_assertion_digest,
    base_policy_digest,
    created_by_principal_id,
    correlation_id
)
SELECT %s,
       target_model.model_id,
       %s,
       'active',
       target_model.model_revision,
       repeat(md5('scope:' || target_model.model_id::TEXT || ':' ||
                   target_model.model_revision::TEXT), 2),
       repeat(md5('assertion:' || target_model.model_id::TEXT || ':' ||
                   target_model.model_revision::TEXT), 2),
       repeat(md5(
           'policy:' || jsonb_build_object(
               'model_id', target_model.model_id,
               'silver_model_naming_instructions',
                   target_model.silver_model_naming_instructions,
               'silver_model_audit_columns_template',
                   target_model.silver_model_audit_columns_template,
               'gold_model_naming_instructions',
                   target_model.gold_model_naming_instructions,
               'gold_model_technical_columns_template',
                   target_model.gold_model_technical_columns_template,
               'gold_model_audit_columns_template',
                   target_model.gold_model_audit_columns_template
           )::TEXT
       ), 2),
       %s,
       %s
  FROM model.model AS target_model
 WHERE target_model.model_id = %s
RETURNING *
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

_GET_CHANGE_SET_SQL: LiteralString = """
SELECT model_change_set.*
  FROM mcp.model_change_set AS model_change_set
 WHERE model_change_set.model_change_set_id = %s
   AND model_change_set.model_id = %s
"""

_GET_CHANGE_SET_FOR_UPDATE_SQL: LiteralString = _GET_CHANGE_SET_SQL + " FOR UPDATE"

_STAGE_SQL: LiteralString = """
UPDATE mcp.model_change_set
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
       last_activity_time = CURRENT_TIMESTAMP,
       expires_time = CURRENT_TIMESTAMP + INTERVAL '4 hours'
 WHERE model_change_set_id = %s
RETURNING draft_revision, model_change_set_status, expires_time
"""

_EXPIRE_STAGE_BATCH_SQL: LiteralString = """
UPDATE mcp.model_stage_batch
   SET stage_batch_status = 'expired',
       terminal_time = CURRENT_TIMESTAMP
 WHERE model_change_set_id = %s
   AND dataset_name = %s
   AND stage_batch_status = 'active'
   AND expires_time <= CURRENT_TIMESTAMP
RETURNING stage_batch_id
"""

_FIND_STAGE_BATCH_SQL: LiteralString = """
SELECT batch.*,
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

_CREATE_STAGE_BATCH_SQL: LiteralString = """
INSERT INTO mcp.model_stage_batch (
    stage_batch_id, model_change_set_id, model_id, dataset_name,
    expected_draft_revision, total_record_count, total_chunk_count,
    payload_mode, total_payload_bytes, batch_sha256,
    created_by_principal_id, correlation_id, expires_time
)
VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
        least(%s, CURRENT_TIMESTAMP + INTERVAL '4 hours'))
RETURNING *, 0::BIGINT AS received_chunk_count
"""

_GET_STAGE_BATCH_FOR_UPDATE_SQL: LiteralString = """
SELECT *
  FROM mcp.model_stage_batch
 WHERE stage_batch_id = %s
   AND model_change_set_id = %s
   AND model_id = %s
 FOR UPDATE
"""

_GET_STAGE_CHUNK_SQL: LiteralString = """
SELECT chunk_sha256, records_document, record_count
  FROM mcp.model_stage_chunk
 WHERE stage_batch_id = %s
   AND chunk_index = %s
"""

_STAGE_CHUNK_TOTALS_SQL: LiteralString = """
SELECT count(*) AS chunk_count,
       coalesce(sum(record_count), 0) AS record_count
  FROM mcp.model_stage_chunk
 WHERE stage_batch_id = %s
"""

_INSERT_STAGE_CHUNK_SQL: LiteralString = """
INSERT INTO mcp.model_stage_chunk (
    stage_batch_id, chunk_index, record_count, chunk_sha256, records_document
)
VALUES (%s, %s, %s, %s, %s)
RETURNING record_count
"""

_TOUCH_STAGE_BATCH_SQL: LiteralString = """
UPDATE mcp.model_stage_batch
   SET last_activity_time = CURRENT_TIMESTAMP
 WHERE stage_batch_id = %s
RETURNING expires_time
"""

_GET_STAGE_CHUNKS_SQL: LiteralString = """
SELECT chunk_index, record_count, chunk_sha256, records_document
  FROM mcp.model_stage_chunk
 WHERE stage_batch_id = %s
 ORDER BY chunk_index
"""

_GET_STAGE_PAYLOAD_CHUNK_SQL: LiteralString = """
SELECT chunk_sha256, chunk_byte_count, payload_fragment
  FROM mcp.model_stage_payload_chunk
 WHERE stage_batch_id = %s
   AND chunk_index = %s
"""

_STAGE_PAYLOAD_CHUNK_TOTALS_SQL: LiteralString = """
SELECT count(*) AS chunk_count,
       coalesce(sum(chunk_byte_count), 0) AS payload_byte_count
  FROM mcp.model_stage_payload_chunk
 WHERE stage_batch_id = %s
"""

_INSERT_STAGE_PAYLOAD_CHUNK_SQL: LiteralString = """
INSERT INTO mcp.model_stage_payload_chunk (
    stage_batch_id, chunk_index, chunk_byte_count, chunk_sha256, payload_fragment
)
VALUES (%s, %s, %s, %s, %s)
RETURNING chunk_byte_count
"""

_GET_STAGE_PAYLOAD_CHUNKS_SQL: LiteralString = """
SELECT chunk_index, chunk_byte_count, chunk_sha256, payload_fragment
  FROM mcp.model_stage_payload_chunk
 WHERE stage_batch_id = %s
 ORDER BY chunk_index
"""

_MARK_STAGE_BATCH_COMMITTED_SQL: LiteralString = """
UPDATE mcp.model_stage_batch
   SET stage_batch_status = 'committed',
       last_activity_time = CURRENT_TIMESTAMP,
       committed_revision = %s,
       committed_expires_time = %s,
       terminal_time = CURRENT_TIMESTAMP
 WHERE stage_batch_id = %s
   AND stage_batch_status = 'active'
RETURNING committed_revision, committed_expires_time
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
RETURNING model_change_set_status, draft_revision, candidate_digest,
          validated_time, expires_time
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

_MARK_WORKFLOW_APPLIED_SQL: LiteralString = """
UPDATE mcp.model_change_set
   SET model_change_set_status = 'applied',
       applied_time = CURRENT_TIMESTAMP,
       terminal_time = CURRENT_TIMESTAMP,
       last_activity_time = CURRENT_TIMESTAMP
 WHERE model_change_set_id = %s
   AND model_id = %s
   AND workflow_run_id = %s
   AND model_change_set_status = 'validated'
   AND draft_revision = %s
   AND candidate_digest = %s
RETURNING model_change_set_status, applied_time
"""

_GET_APPLIED_EVENT_SQL: LiteralString = """
SELECT event.draft_revision,
       event.action_count,
       event.event_metadata,
       event.correlation_id
  FROM mcp.model_change_set_event AS event
 WHERE event.model_change_set_id = %s
   AND event.model_id = %s
   AND event.event_type = 'applied'
 ORDER BY event.event_sequence DESC
 LIMIT 1
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


class PostgresModelChangeSetRepository:
    """One transaction-bound repository; service owns the transaction boundary."""

    def __init__(self, transaction: WriteTransaction) -> None:
        self._transaction = transaction

    async def get_model(self, *, tenant_id: int, model_id: int) -> dict[str, Any] | None:
        return await self._transaction.fetch_one(_MODEL_CONTEXT_SQL, (tenant_id, model_id))

    async def authorize_record_review(
        self,
        *,
        entra_tenant_id: UUID,
        entra_object_id: UUID,
        tenant_id: int,
        model_id: int,
    ) -> dict[str, Any] | None:
        return await self._transaction.fetch_one(
            _AUTHORIZE_RECORD_REVIEW_SQL,
            (entra_tenant_id, entra_object_id, tenant_id, model_id),
        )

    async def read_analysis_review_records(
        self, *, model_id: int, record_ids: list[int]
    ) -> list[dict[str, Any]]:
        return await self._transaction.fetch_all(_REVIEW_ANALYSIS_SQL, (model_id, record_ids))

    async def apply_record_review(
        self, *, dataset: str, model_id: int, record_id: int, locked: bool, status: str, actor: str
    ) -> dict[str, Any] | None:
        queries: dict[str, LiteralString] = {
            **_APPLY_OTHER_REVIEWS_SQL,
            "analysis_result": _APPLY_ANALYSIS_REVIEW_SQL,
            "conceptual_object": _APPLY_CONCEPTUAL_OBJECT_REVIEW_SQL,
            "conceptual_relationship": _APPLY_CONCEPTUAL_RELATIONSHIP_REVIEW_SQL,
        }
        return await self._transaction.fetch_one(
            queries[dataset],
            (
                locked,
                status == "active"
                if dataset in {"validation_group", "validation_check"}
                else status,
                actor,
                model_id,
                record_id,
            ),
        )

    async def replay_review(
        self, *, model_id: int, principal_id: int, correlation_id: UUID
    ) -> dict[str, Any] | None:
        return await self._transaction.fetch_one(
            _REPLAY_REVIEW_SQL, (model_id, principal_id, correlation_id)
        )

    async def has_running_tenant_workflow(self, *, tenant_id: int) -> bool:
        return (
            await self._transaction.fetch_one(_RUNNING_TENANT_WORKFLOW_SQL, (tenant_id,))
            is not None
        )

    async def get_model_for_update(
        self,
        *,
        tenant_id: int,
        model_id: int,
    ) -> dict[str, Any] | None:
        return await self._transaction.fetch_one(
            _MODEL_CONTEXT_FOR_UPDATE_SQL,
            (tenant_id, model_id),
        )

    async def expire_owned(self, *, model_id: int, principal_id: int) -> list[dict[str, Any]]:
        return await self._transaction.fetch_all(
            _EXPIRE_OWNED_SQL,
            (model_id, principal_id),
        )

    async def find_ongoing(
        self,
        *,
        model_id: int,
        principal_id: int,
    ) -> dict[str, Any] | None:
        return await self._transaction.fetch_one(
            _FIND_ONGOING_SQL,
            (model_id, principal_id),
        )

    async def get_workflow_run_for_update(
        self,
        *,
        workflow_run_id: int,
        model_id: int,
    ) -> dict[str, Any] | None:
        return await self._transaction.fetch_one(
            _GET_WORKFLOW_RUN_FOR_UPDATE_SQL,
            (workflow_run_id, model_id),
        )

    async def get_by_workflow_run(
        self,
        *,
        workflow_run_id: int,
        model_id: int,
    ) -> dict[str, Any] | None:
        return await self._transaction.fetch_one(
            _GET_BY_WORKFLOW_RUN_SQL,
            (workflow_run_id, model_id),
        )

    async def create(
        self,
        *,
        change_set_id: UUID,
        model_id: int,
        workflow_run_id: int | None,
        principal_id: int,
        correlation_id: UUID,
    ) -> dict[str, Any] | None:
        return await self._transaction.fetch_one(
            _CREATE_SQL,
            (
                change_set_id,
                workflow_run_id,
                principal_id,
                correlation_id,
                model_id,
            ),
        )

    async def insert_event(
        self,
        *,
        change_set_id: UUID,
        model_id: int,
        event_type: str,
        draft_revision: int,
        section: str | None,
        action_count: int,
        outcome: str,
        metadata: Mapping[str, object],
        correlation_id: UUID,
    ) -> None:
        await self._transaction.fetch_one(
            _INSERT_EVENT_SQL,
            (
                change_set_id,
                model_id,
                event_type,
                draft_revision,
                section,
                action_count,
                outcome,
                Jsonb(dict(metadata)),
                correlation_id,
                change_set_id,
            ),
        )

    async def get_change_set(
        self,
        *,
        change_set_id: UUID,
        model_id: int,
        for_update: bool,
    ) -> dict[str, Any] | None:
        return await self._transaction.fetch_one(
            _GET_CHANGE_SET_FOR_UPDATE_SQL if for_update else _GET_CHANGE_SET_SQL,
            (change_set_id, model_id),
        )

    async def stage_documents(
        self,
        *,
        documents: Mapping[str, Mapping[str, list[dict[str, object]]]],
        change_set_id: UUID,
    ) -> dict[str, Any] | None:
        return await self._transaction.fetch_one(
            _STAGE_SQL,
            (
                *(
                    Jsonb(dict(documents[section]))
                    for section in (
                        "model_input_scope",
                        "profiling",
                        "analysis",
                        "assertion",
                        "conceptual",
                        "logical",
                        "dimensional",
                        "model_binding",
                        "mapping",
                        "code_generation",
                        "validation",
                    )
                ),
                change_set_id,
            ),
        )

    async def expire_stage_batches(self, *, change_set_id: UUID, dataset: str) -> None:
        await self._transaction.fetch_all(_EXPIRE_STAGE_BATCH_SQL, (change_set_id, dataset))

    async def find_stage_batch(
        self,
        *,
        change_set_id: UUID,
        dataset: str,
    ) -> dict[str, Any] | None:
        return await self._transaction.fetch_one(
            _FIND_STAGE_BATCH_SQL,
            (change_set_id, dataset),
        )

    async def create_stage_batch(self, parameters: tuple[object, ...]) -> dict[str, Any] | None:
        return await self._transaction.fetch_one(_CREATE_STAGE_BATCH_SQL, parameters)

    async def get_stage_batch(
        self,
        *,
        stage_batch_id: UUID,
        change_set_id: UUID,
        model_id: int,
    ) -> dict[str, Any] | None:
        return await self._transaction.fetch_one(
            _GET_STAGE_BATCH_FOR_UPDATE_SQL,
            (stage_batch_id, change_set_id, model_id),
        )

    async def get_stage_chunk(
        self,
        *,
        stage_batch_id: UUID,
        chunk_index: int,
    ) -> dict[str, Any] | None:
        return await self._transaction.fetch_one(
            _GET_STAGE_CHUNK_SQL,
            (stage_batch_id, chunk_index),
        )

    async def stage_chunk_totals(self, *, stage_batch_id: UUID) -> dict[str, Any]:
        row = await self._transaction.fetch_one(_STAGE_CHUNK_TOTALS_SQL, (stage_batch_id,))
        if row is None:
            raise RuntimeError("Database did not return Stage Batch totals")
        return row

    async def insert_stage_chunk(
        self,
        *,
        stage_batch_id: UUID,
        chunk_index: int,
        records: list[dict[str, object]],
        chunk_sha256: str,
    ) -> None:
        await self._transaction.fetch_one(
            _INSERT_STAGE_CHUNK_SQL,
            (stage_batch_id, chunk_index, len(records), chunk_sha256, Jsonb(records)),
        )
        await self._transaction.fetch_one(_TOUCH_STAGE_BATCH_SQL, (stage_batch_id,))

    async def get_stage_chunks(self, *, stage_batch_id: UUID) -> list[dict[str, Any]]:
        return await self._transaction.fetch_all(_GET_STAGE_CHUNKS_SQL, (stage_batch_id,))

    async def get_stage_payload_chunk(
        self,
        *,
        stage_batch_id: UUID,
        chunk_index: int,
    ) -> dict[str, Any] | None:
        return await self._transaction.fetch_one(
            _GET_STAGE_PAYLOAD_CHUNK_SQL,
            (stage_batch_id, chunk_index),
        )

    async def stage_payload_chunk_totals(self, *, stage_batch_id: UUID) -> dict[str, Any]:
        row = await self._transaction.fetch_one(
            _STAGE_PAYLOAD_CHUNK_TOTALS_SQL,
            (stage_batch_id,),
        )
        if row is None:
            raise RuntimeError("Database did not return Stage payload totals")
        return row

    async def insert_stage_payload_chunk(
        self,
        *,
        stage_batch_id: UUID,
        chunk_index: int,
        payload_fragment: bytes,
        chunk_sha256: str,
    ) -> None:
        await self._transaction.fetch_one(
            _INSERT_STAGE_PAYLOAD_CHUNK_SQL,
            (
                stage_batch_id,
                chunk_index,
                len(payload_fragment),
                chunk_sha256,
                payload_fragment,
            ),
        )
        await self._transaction.fetch_one(_TOUCH_STAGE_BATCH_SQL, (stage_batch_id,))

    async def get_stage_payload_chunks(
        self,
        *,
        stage_batch_id: UUID,
    ) -> list[dict[str, Any]]:
        return await self._transaction.fetch_all(
            _GET_STAGE_PAYLOAD_CHUNKS_SQL,
            (stage_batch_id,),
        )

    async def mark_stage_batch_committed(
        self,
        *,
        stage_batch_id: UUID,
        draft_revision: int,
        expires_at: datetime,
    ) -> dict[str, Any] | None:
        return await self._transaction.fetch_one(
            _MARK_STAGE_BATCH_COMMITTED_SQL,
            (draft_revision, expires_at, stage_batch_id),
        )

    async def record_validation(
        self,
        *,
        change_set_id: UUID,
        status: str,
        candidate_digest: str | None,
        outcome: Mapping[str, object],
        valid: bool,
    ) -> dict[str, Any] | None:
        return await self._transaction.fetch_one(
            _RECORD_VALIDATION_SQL,
            (status, candidate_digest, Jsonb(dict(outcome)), valid, change_set_id),
        )

    async def advance_model_revision(
        self,
        *,
        model_id: int,
        expected_model_revision: int,
        changed: bool,
    ) -> dict[str, Any] | None:
        return await self._transaction.fetch_one(
            _ADVANCE_MODEL_REVISION_SQL,
            (1 if changed else 0, model_id, expected_model_revision),
        )

    async def mark_applied(self, *, change_set_id: UUID) -> dict[str, Any] | None:
        return await self._transaction.fetch_one(_MARK_APPLIED_SQL, (change_set_id,))

    async def mark_workflow_applied(
        self,
        *,
        change_set_id: UUID,
        model_id: int,
        workflow_run_id: int,
        draft_revision: int,
        candidate_digest: str,
    ) -> dict[str, Any] | None:
        return await self._transaction.fetch_one(
            _MARK_WORKFLOW_APPLIED_SQL,
            (
                change_set_id,
                model_id,
                workflow_run_id,
                draft_revision,
                candidate_digest,
            ),
        )

    async def get_applied_event(
        self,
        *,
        change_set_id: UUID,
        model_id: int,
    ) -> dict[str, Any] | None:
        return await self._transaction.fetch_one(
            _GET_APPLIED_EVENT_SQL,
            (change_set_id, model_id),
        )

    async def archive(
        self,
        *,
        change_set_id: UUID,
        model_id: int,
    ) -> dict[str, Any] | None:
        return await self._transaction.fetch_one(_ARCHIVE_SQL, (change_set_id, model_id))


def require_datetime(row: Mapping[str, Any], field: str) -> datetime:
    value = row[field]
    if not isinstance(value, datetime):
        raise RuntimeError(f"Database returned an invalid {field}")
    return value
