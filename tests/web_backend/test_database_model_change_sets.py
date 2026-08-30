import hashlib
import json
from collections.abc import Mapping
from typing import Literal, Protocol, cast
from uuid import UUID, uuid4

import pytest
from gds_etl_workbench.application.authorization import AuthorizationService
from gds_etl_workbench.domain.authorization import ActorKind, RequestPrincipal
from gds_etl_workbench.domain.errors import (
    CandidateDigestConflictError,
    DependencyUnavailableError,
    InvalidRequestError,
    TenantLockRequiredError,
)
from gds_etl_workbench.tools.change_sets.common import (
    canonical_records_sha256,
    stage_batch_sha256,
)
from gds_etl_workbench.tools.change_sets.model import StageModelChange
from psycopg import Connection
from psycopg.types.json import Jsonb

from gds_workbench_api.database import WebPostgresDatabase
from gds_workbench_api.features.analysis.service import (
    AnalysisInferenceWorkflow,
    DatabaseAnalysisInferenceExecutor,
)
from gds_workbench_api.features.conceptual.service import (
    ConceptualWorkflow,
    DatabaseConceptualExecutor,
)
from gds_workbench_api.features.dimensional import (
    DatabaseDimensionalExecutor,
    DimensionalWorkflow,
)
from gds_workbench_api.features.logical.service import (
    DatabaseLogicalExecutor,
    LogicalWorkflow,
)
from gds_workbench_api.features.model_change_sets.contracts import (
    BeginModelStageBatchRequest,
    CreateModelChangeSetRequest,
    ExpectedDraftRevisionRequest,
    PutModelStageChunkRequest,
    StageModelChangeSetRequest,
)
from gds_workbench_api.features.model_change_sets.service import (
    DatabaseModelChangeSetService,
)
from gds_workbench_api.features.workflows.authoring.change_set_apply import (
    ApplyWorkflowDraftRequest,
    DatabaseWorkflowDraftApplyService,
)
from gds_workbench_api.features.workflows.authoring.change_set_handoff import (
    WorkflowChangeSetHandoff,
    WorkflowChangeSetHandoffResult,
    WorkflowChangeSetValidationError,
)
from gds_workbench_api.features.workflows.authoring.lifecycle import (
    AgentWorkflowEvent,
    DatabaseAgentWorkflowLifecycle,
)
from gds_workbench_api.features.workflows.authoring.no_op import (
    DatabaseAuthoringNoOpService,
)
from gds_workbench_api.features.workflows.execution.repository import (
    DatabaseWorkflowClaimRepository,
)
from gds_workbench_api.integrations.agents import LocalFakeAgentAdapter
from gds_workbench_api.features.models import ModelRevisionConflictError
from gds_workbench_api.features.workflows.runs import DatabaseWorkflowRunService


class DisposablePostgresFixture(Protocol):
    def connect_owner(self) -> Connection[dict[str, object]]: ...

    def web_runtime_dsn(self) -> str: ...


_MATERIALIZED_TABLES = (
    "model.modeling_assertion_document",
    "model.modeling_assertion_record",
    "workflow.analysis_result",
    "workflow.mapping_attribute",
    "workflow.conceptual_object",
    "workflow.conceptual_relationship",
    "workflow.conceptual_support",
    "workflow.dimensional_attribute",
    "workflow.dimensional_attribute_source_mapping",
    "workflow.dimensional_entity",
    "workflow.dimensional_entity_source_mapping",
    "workflow.dimensional_entity_submodel",
    "workflow.dimensional_relationship",
    "workflow.dimensional_submodel",
    "workflow.logical_attribute",
    "workflow.logical_attribute_source_mapping",
    "workflow.logical_entity",
    "workflow.logical_entity_source_mapping",
    "workflow.logical_entity_submodel",
    "workflow.logical_relationship",
    "workflow.logical_submodel",
    "workflow.mapping_source_system_dependency",
    "workflow.mapping_object",
)


def _bool(row: Mapping[str, object] | None, field: str) -> bool:
    if row is None or not isinstance(row.get(field), bool):
        raise AssertionError(f"expected boolean {field}")
    return row[field] is True


def test_web_change_set_role_has_only_the_required_materialization_surface(
    web_postgres_database: DisposablePostgresFixture,
) -> None:
    with web_postgres_database.connect_owner() as connection:
        for table in _MATERIALIZED_TABLES:
            row = connection.execute(
                """
                SELECT has_table_privilege('gds_web_write', %s, 'SELECT') AS can_read,
                       has_table_privilege('gds_web_write', %s, 'INSERT') AS can_insert,
                       has_table_privilege('gds_web_write', %s, 'UPDATE') AS can_update,
                       has_table_privilege('gds_web_write', %s, 'DELETE') AS can_delete,
                       has_table_privilege('gds_web_write', %s, 'TRUNCATE') AS can_truncate
                """,
                (table, table, table, table, table),
            ).fetchone()
            assert _bool(row, "can_read")
            assert _bool(row, "can_insert")
            assert _bool(row, "can_update")
            assert not _bool(row, "can_delete")
            assert not _bool(row, "can_truncate")

        change_set = connection.execute(
            """
            SELECT has_table_privilege(
                       'gds_web_write', 'mcp.model_change_set', 'SELECT,INSERT,UPDATE'
                   ) AS change_set_ok,
                   has_table_privilege(
                       'gds_web_write', 'mcp.model_stage_batch', 'SELECT,INSERT,UPDATE'
                   ) AS batch_ok,
                   has_table_privilege(
                       'gds_web_write', 'mcp.model_stage_chunk', 'SELECT,INSERT'
                   ) AS chunk_ok,
                   has_table_privilege(
                       'gds_web_write', 'mcp.model_change_set_event', 'SELECT,INSERT'
                   ) AS event_ok,
                   (
                       has_table_privilege(
                           'gds_web_write', 'mcp.model_stage_chunk', 'UPDATE'
                       ) OR has_table_privilege(
                           'gds_web_write', 'mcp.model_stage_chunk', 'DELETE'
                       ) OR has_table_privilege(
                           'gds_web_write', 'mcp.model_stage_chunk', 'TRUNCATE'
                       )
                   ) AS chunk_too_broad,
                   (
                       has_table_privilege(
                           'gds_web_write', 'mcp.tool_call_log', 'SELECT'
                       ) OR has_table_privilege(
                           'gds_web_write', 'mcp.tool_call_log', 'INSERT'
                       ) OR has_table_privilege(
                           'gds_web_write', 'mcp.tool_call_log', 'UPDATE'
                       ) OR has_table_privilege(
                           'gds_web_write', 'mcp.tool_call_log', 'DELETE'
                       )
                   ) AS audit_exposed,
                   (
                       has_any_column_privilege(
                           'gds_web_write', 'model.model_scope', 'INSERT'
                       ) OR has_any_column_privilege(
                           'gds_web_write', 'model.model_scope', 'UPDATE'
                       )
                   ) AS scope_mutable
            """
        ).fetchone()

    assert _bool(change_set, "change_set_ok")
    assert _bool(change_set, "batch_ok")
    assert _bool(change_set, "chunk_ok")
    assert _bool(change_set, "event_ok")
    assert not _bool(change_set, "chunk_too_broad")
    assert not _bool(change_set, "audit_exposed")
    assert not _bool(change_set, "scope_mutable")


def _required_id(row: Mapping[str, object] | None, field: str) -> int:
    value = None if row is None else row.get(field)
    if not isinstance(value, int) or isinstance(value, bool) or value <= 0:
        raise AssertionError(f"expected positive database ID {field}")
    return value


def _seed_profile_model(
    database: DisposablePostgresFixture,
) -> tuple[int, int, int, UUID, UUID, dict[str, object]]:
    suffix = uuid4().hex
    entra_tenant_id = uuid4()
    entra_object_id = uuid4()
    with database.connect_owner() as connection:
        system_type_id = _required_id(
            connection.execute(
                """
                INSERT INTO reference.system_type (system_type_code, system_type_name)
                VALUES (%s, %s)
                RETURNING system_type_id
                """,
                (f"changeset_db_{suffix}", f"Change Set DB {suffix}"),
            ).fetchone(),
            "system_type_id",
        )
        connection_type_id = _required_id(
            connection.execute(
                """
                INSERT INTO reference.connection_type (
                    connection_type_code, connection_type_name
                ) VALUES (%s, %s)
                RETURNING connection_type_id
                """,
                (f"changeset_pg_{suffix}", f"Change Set PG {suffix}"),
            ).fetchone(),
            "connection_type_id",
        )
        object_type_id = _required_id(
            connection.execute(
                """
                INSERT INTO reference.object_type (object_type_code, object_type_name)
                VALUES (%s, %s)
                RETURNING object_type_id
                """,
                (f"changeset_table_{suffix}", f"Change Set Table {suffix}"),
            ).fetchone(),
            "object_type_id",
        )
        bronze_zone = connection.execute(
            """
                SELECT zone_id
                  FROM reference.zone
                 WHERE lower(btrim(zone_code)) = 'bronze'
                """
        ).fetchone()
        if bronze_zone is None:
            bronze_zone = connection.execute(
                """
                INSERT INTO reference.zone (zone_code, zone_name)
                VALUES ('bronze', 'Bronze')
                RETURNING zone_id
                """
            ).fetchone()
        bronze_zone_id = _required_id(bronze_zone, "zone_id")
        project_id = _required_id(
            connection.execute(
                """
                INSERT INTO core.project (project_code, project_name)
                VALUES (%s, %s)
                RETURNING project_id
                """,
                (f"changeset_{suffix}", f"Change Set Project {suffix}"),
            ).fetchone(),
            "project_id",
        )
        tenant_code = f"CHANGESET_{suffix}"
        tenant_id = _required_id(
            connection.execute(
                """
                INSERT INTO core.tenant (
                    project_id, tenant_code, tenant_name,
                    tenant_catalog, gds_admin_catalog
                ) VALUES (%s, %s, %s, %s, %s)
                RETURNING tenant_id
                """,
                (
                    project_id,
                    tenant_code,
                    f"Change Set Tenant {suffix}",
                    f"changeset_{suffix}",
                    f"changeset_admin_{suffix}",
                ),
            ).fetchone(),
            "tenant_id",
        )
        system_code = f"ERP_{suffix}"
        system_id = _required_id(
            connection.execute(
                """
                INSERT INTO core.system (system_code, system_name, system_type_id)
                VALUES (%s, %s, %s)
                RETURNING system_id
                """,
                (system_code, f"ERP {suffix}", system_type_id),
            ).fetchone(),
            "system_id",
        )
        connection_code = f"SOURCE_{suffix}"
        connection_id = _required_id(
            connection.execute(
                """
                INSERT INTO core.connection (
                    tenant_id, system_id, connection_code,
                    connection_name, connection_type_id
                ) VALUES (%s, %s, %s, %s, %s)
                RETURNING connection_id
                """,
                (
                    tenant_id,
                    system_id,
                    connection_code,
                    f"Source {suffix}",
                    connection_type_id,
                ),
            ).fetchone(),
            "connection_id",
        )
        object_id = _required_id(
            connection.execute(
                """
                INSERT INTO core.object (
                    connection_id, object_schema, object_name, object_type_id, zone_id
                ) VALUES (%s, 'sales', 'orders', %s, %s)
                RETURNING object_id
                """,
                (connection_id, object_type_id, bronze_zone_id),
            ).fetchone(),
            "object_id",
        )
        attribute_id = _required_id(
            connection.execute(
                """
                INSERT INTO core.attribute (
                    object_id, attribute_name, attribute_ordinal_position,
                    attribute_data_type, attribute_nullability
                ) VALUES (%s, 'customer_id', 1, 'bigint', FALSE)
                RETURNING attribute_id
                """,
                (object_id,),
            ).fetchone(),
            "attribute_id",
        )
        model_id = _required_id(
            connection.execute(
                """
                INSERT INTO model.model (tenant_id, model_name)
                VALUES (%s, %s)
                RETURNING model_id
                """,
                (tenant_id, f"Change Set Model {suffix}"),
            ).fetchone(),
            "model_id",
        )
        connection.execute(
            "INSERT INTO model.model_scope (model_id, object_id) VALUES (%s, %s)",
            (model_id, object_id),
        )
        principal_id = _required_id(
            connection.execute(
                """
                INSERT INTO security.principal (
                    principal_type, principal_display_name, principal_email
                ) VALUES ('user', %s, %s)
                RETURNING principal_id
                """,
                (f"Change Set Author {suffix}", f"changeset_{suffix}@example.test"),
            ).fetchone(),
            "principal_id",
        )
        connection.execute(
            """
            INSERT INTO security.entra_principal_identity (
                principal_id, principal_type, entra_tenant_id, entra_object_id
            ) VALUES (%s, 'user', %s, %s)
            """,
            (principal_id, entra_tenant_id, entra_object_id),
        )
        connection.execute(
            """
            INSERT INTO security.tenant_principal_access (
                tenant_id, principal_id, tenant_role, granted_by_principal_id
            ) VALUES (%s, %s, 'architect', %s)
            """,
            (tenant_id, principal_id, principal_id),
        )
    profile: dict[str, object] = {
        "tenant_code": tenant_code,
        "system_code": system_code,
        "connection_code": connection_code,
        "object_schema": "sales",
        "object_name": "orders",
        "attribute_name": "customer_id",
        "row_count": 10,
        "non_null_count": 9,
        "null_count": 1,
        "blank_count": 0,
        "distinct_count": 5,
        "min_data_length": 1,
        "max_data_length": 5,
        "avg_data_length": 2,
        "percent_populated": 90,
        "percent_duplicates": 44.4444,
        "percent_null": 10,
        "percent_blank": 0,
        "percent_distinct": 55.5556,
    }
    return model_id, tenant_id, attribute_id, entra_tenant_id, entra_object_id, profile


def _make_scope_object_dimensional_eligible(
    database: DisposablePostgresFixture,
    *,
    model_id: int,
) -> int:
    technical_template = {
        "schema_version": "1.0",
        "dimension_surrogate_key": {
            "semantic_name_template": "{entity_name} key",
            "data_type": "bigint",
            "nullable": False,
            "definition_template": "Surrogate key for {entity_name}.",
        },
        "fact_bridge_foreign_key": {
            "with_role_semantic_name_template": "{role_name} key",
            "without_role_semantic_name_template": "{entity_name} key",
            "definition_template": "Foreign key to {entity_name}.",
        },
        "type_2": {
            "effective_from": {
                "semantic_name": "Effective From",
                "data_type": "TIMESTAMPTZ",
                "nullable": False,
                "definition": "Type 2 effective start.",
            },
            "effective_to": {
                "semantic_name": "Effective To",
                "data_type": "TIMESTAMPTZ",
                "nullable": True,
                "definition": "Type 2 effective end.",
            },
            "is_current": {
                "semantic_name": "Is Current",
                "data_type": "BOOLEAN",
                "nullable": False,
                "definition": "Current Type 2 row.",
            },
        },
    }
    audit_template = {
        "schema_version": "1.0",
        "columns": [
            {
                "semantic_name": "Loaded At",
                "data_type": "TIMESTAMPTZ",
                "nullable": False,
                "definition": "Warehouse load time.",
            }
        ],
    }
    with database.connect_owner() as connection:
        scoped = connection.execute(
            """
            SELECT object.object_id,
                   object.connection_id,
                   connection.system_id,
                   attribute.attribute_id
              FROM model.model_scope AS scope
              JOIN core.object AS object
                ON object.object_id = scope.object_id
              JOIN core.connection AS connection
                ON connection.connection_id = object.connection_id
              JOIN core.attribute AS attribute
                ON attribute.object_id = object.object_id
             WHERE scope.model_id = %s
               AND scope.is_active
             ORDER BY attribute.attribute_ordinal_position
             LIMIT 1
            """,
            (model_id,),
        ).fetchone()
        if scoped is None:
            raise AssertionError("expected one seeded scoped Object")
        object_id = _required_id(scoped, "object_id")
        system_id = _required_id(scoped, "system_id")
        attribute_id = _required_id(scoped, "attribute_id")
        silver_zone = connection.execute(
            """
            SELECT zone_id
              FROM reference.zone
             WHERE lower(btrim(zone_code)) = 'silver'
            """
        ).fetchone()
        if silver_zone is None:
            silver_zone = connection.execute(
                """
                INSERT INTO reference.zone (zone_code, zone_name)
                VALUES ('silver', 'Silver')
                RETURNING zone_id
                """
            ).fetchone()
        silver_zone_id = _required_id(silver_zone, "zone_id")
        connection.execute(
            "UPDATE core.object SET zone_id = %s WHERE object_id = %s",
            (silver_zone_id, object_id),
        )
        logical_entity_id = _required_id(
            connection.execute(
                """
                INSERT INTO workflow.logical_entity (
                    model_id,
                    logical_entity_name,
                    logical_entity_definition,
                    logical_entity_type,
                    logical_entity_grain,
                    logical_entity_status
                ) VALUES (
                    %s,
                    'order',
                    'One source order.',
                    'transaction',
                    'One row per source order.',
                    'active'
                )
                RETURNING logical_entity_id
                """,
                (model_id,),
            ).fetchone(),
            "logical_entity_id",
        )
        logical_attribute_id = _required_id(
            connection.execute(
                """
                INSERT INTO workflow.logical_attribute (
                    model_id,
                    logical_entity_id,
                    logical_attribute_name,
                    logical_attribute_definition,
                    logical_attribute_data_type,
                    logical_attribute_is_nullable,
                    logical_attribute_is_natural_key,
                    logical_attribute_ordinal_position,
                    logical_attribute_status
                ) VALUES (
                    %s,
                    %s,
                    'customer_id',
                    'Source customer identifier.',
                    'bigint',
                    FALSE,
                    TRUE,
                    1,
                    'active'
                )
                RETURNING logical_attribute_id
                """,
                (model_id, logical_entity_id),
            ).fetchone(),
            "logical_attribute_id",
        )
        connection.execute(
            """
            INSERT INTO workflow.mapping_source_system_dependency (
                model_id,
                modeled_entity_type,
                source_system_id,
                mapping_source_system_dependency_status
            ) VALUES (%s, 'logical_entity', %s, 'active')
            """,
            (model_id, system_id),
        )
        mapping_object_id = _required_id(
            connection.execute(
                """
                INSERT INTO workflow.mapping_object (
                    model_id,
                    object_id,
                    source_system_id,
                    modeled_entity_type,
                    logical_entity_id,
                    object_mapping_status
                ) VALUES (%s, %s, %s, 'logical_entity', %s, 'active')
                RETURNING mapping_object_id
                """,
                (model_id, object_id, system_id, logical_entity_id),
            ).fetchone(),
            "mapping_object_id",
        )
        connection.execute(
            """
            INSERT INTO workflow.mapping_attribute (
                model_id,
                object_id,
                attribute_id,
                mapping_object_id,
                modeled_entity_type,
                logical_attribute_id,
                attribute_mapping_status
            ) VALUES (%s, %s, %s, %s, 'logical_entity', %s, 'active')
            """,
            (
                model_id,
                object_id,
                attribute_id,
                mapping_object_id,
                logical_attribute_id,
            ),
        )
        connection.execute(
            """
            UPDATE model.model
               SET gold_model_naming_instructions =
                       'Use concise business names for Gold artifacts.',
                   gold_model_technical_columns_template = %s,
                   gold_model_audit_columns_template = %s
             WHERE model_id = %s
            """,
            (Jsonb(technical_template), Jsonb(audit_template), model_id),
        )
        eligibility = connection.execute(
            """
            SELECT is_dimensional_source_eligible
              FROM workflow.list_model_object_eligibility(%s)
             WHERE object_id = %s
            """,
            (model_id, object_id),
        ).fetchone()
        if eligibility != {"is_dimensional_source_eligible": True}:
            raise AssertionError("expected an eligible Silver Dimensional source")
    return object_id


def _create_running_conceptual_run(
    database: DisposablePostgresFixture,
    *,
    tenant_id: int,
    model_id: int,
    entra_tenant_id: UUID,
    entra_object_id: UUID,
) -> int:
    with database.connect_owner() as connection:
        actor = connection.execute(
            """
            SELECT identity.principal_id,
                   identity.entra_principal_identity_id
              FROM security.entra_principal_identity AS identity
             WHERE identity.entra_tenant_id = %s
               AND identity.entra_object_id = %s
            """,
            (entra_tenant_id, entra_object_id),
        ).fetchone()
        if actor is None:
            raise AssertionError("expected seeded actor identity")
        selected = connection.execute(
            """
            SELECT scope.object_id
              FROM model.model_scope AS scope
             WHERE scope.model_id = %s
               AND scope.is_active
             ORDER BY scope.object_id
             LIMIT 1
            """,
            (model_id,),
        ).fetchone()
        if selected is None:
            raise AssertionError("expected seeded Model Scope Object")
        workflow_run_id = _required_id(
            connection.execute(
                """
                INSERT INTO application.workflow_run (
                    tenant_id,
                    model_id,
                    model_revision,
                    model_workflow,
                    workflow_execution_mode,
                    actor_principal_id,
                    actor_entra_principal_identity_id,
                    agent_sdk_code,
                    agent_provider_code,
                    agent_model_code,
                    reasoning_effort_code,
                    max_turns,
                    validation_retry_count,
                    selected_scope_digest,
                    selected_scope_count,
                    workflow_run_state,
                    correlation_id,
                    started_time
                ) VALUES (
                    %s, %s, 1, 'conceptual', 'one_shot', %s, %s,
                    'openai_agents_sdk', 'databricks', 'test-model',
                    'medium', 8, 1, %s, 1, 'running', %s, CURRENT_TIMESTAMP
                )
                RETURNING workflow_run_id
                """,
                (
                    tenant_id,
                    model_id,
                    actor["principal_id"],
                    actor["entra_principal_identity_id"],
                    "e" * 64,
                    uuid4(),
                ),
            ).fetchone(),
            "workflow_run_id",
        )
        connection.execute(
            """
            INSERT INTO application.workflow_run_object_selection (
                workflow_run_id,
                model_id,
                object_id,
                selection_order
            ) VALUES (%s, %s, %s, 1)
            """,
            (workflow_run_id, model_id, selected["object_id"]),
        )
    return workflow_run_id


def _create_queued_authoring_run_with_prompt(
    database: DisposablePostgresFixture,
    *,
    model_id: int,
    tenant_id: int,
    entra_tenant_id: UUID,
    entra_object_id: UUID,
    workflow: Literal["conceptual", "logical", "dimensional"],
    selected_object_id: int | None = None,
) -> int:
    suffix = uuid4().hex
    with database.connect_owner() as connection:
        actor = connection.execute(
            """
            SELECT identity.principal_id
              FROM security.entra_principal_identity AS identity
             WHERE identity.entra_tenant_id = %s
               AND identity.entra_object_id = %s
            """,
            (entra_tenant_id, entra_object_id),
        ).fetchone()
        if selected_object_id is None:
            selected = connection.execute(
                """
                SELECT scope.object_id
                  FROM model.model_scope AS scope
                 WHERE scope.model_id = %s
                   AND scope.is_active
                 ORDER BY scope.object_id
                 LIMIT 1
                """,
                (model_id,),
            ).fetchone()
        else:
            selected = connection.execute(
                """
                SELECT scope.object_id
                  FROM model.model_scope AS scope
                 WHERE scope.model_id = %s
                   AND scope.object_id = %s
                   AND scope.is_active
                """,
                (model_id, selected_object_id),
            ).fetchone()
        if actor is None or selected is None:
            raise AssertionError("expected seeded authoring run inputs")
        principal_id = _required_id(actor, "principal_id")
        object_id = _required_id(selected, "object_id")

        stage = connection.execute(
            """
            SELECT workflow_stage_id
              FROM application.workflow_stage
             WHERE model_workflow = %s
               AND workflow_execution_mode = 'one_shot'
               AND workflow_stage_code = 'candidate_authoring'
            """,
            (workflow,),
        ).fetchone()
        if stage is None:
            stage = connection.execute(
                """
                INSERT INTO application.workflow_stage (
                    model_workflow,
                    workflow_execution_mode,
                    workflow_stage_code,
                    workflow_stage_name,
                    workflow_stage_order,
                    workflow_stage_is_agentic
                ) VALUES (
                    %s, 'one_shot', 'candidate_authoring',
                    'Candidate authoring', 10, TRUE
                )
                RETURNING workflow_stage_id
                """,
                (workflow,),
            ).fetchone()
        system_prompt = f"Author one complete {workflow.title()} candidate."
        instruction_prompt = "Use the immutable context: {{stage_context}}."
        digest_row = connection.execute(
            """
            SELECT encode(
                       sha256(
                           convert_to(
                               jsonb_build_object(
                                   'system_prompt_template', %s::TEXT,
                                   'instruction_prompt_template', %s::TEXT,
                                   'tool_instruction_prompt_template', NULL::TEXT
                               )::TEXT,
                               'UTF8'
                           )
                       ),
                       'hex'
                   ) AS prompt_digest
            """,
            (system_prompt, instruction_prompt),
        ).fetchone()
        if digest_row is None or not isinstance(digest_row.get("prompt_digest"), str):
            raise AssertionError("expected Prompt digest")
        prompt_digest = digest_row["prompt_digest"]
        stages = connection.execute(
            """
            SELECT workflow_stage_id, workflow_stage_code
              FROM application.workflow_stage
             WHERE model_workflow = %s
               AND workflow_execution_mode = 'one_shot'
               AND workflow_stage_is_agentic
               AND is_active
             ORDER BY workflow_stage_order, workflow_stage_id
            """,
            (workflow,),
        ).fetchall()
        prompt_overrides: dict[str, int] = {}
        for prompt_number, prompt_stage in enumerate(stages, start=1):
            workflow_stage_id = _required_id(prompt_stage, "workflow_stage_id")
            workflow_stage_code = prompt_stage.get("workflow_stage_code")
            if not isinstance(workflow_stage_code, str):
                raise AssertionError("expected Workflow Stage code")
            variables = (
                (
                    "stage_context",
                    f"workflow.{workflow}.one_shot.{workflow_stage_code}.context",
                    "json",
                    True,
                    "Immutable bounded context for this authoring run.",
                    10,
                ),
                (
                    "naming_instructions",
                    "model.naming_instructions",
                    "text",
                    False,
                    "Optional Model naming instructions.",
                    20,
                ),
                (
                    "validation_failures",
                    "workflow.validation_failures",
                    "json",
                    False,
                    "Bounded validation failures for a repair attempt.",
                    30,
                ),
            )
            for variable in variables:
                connection.execute(
                    """
                    INSERT INTO application.workflow_stage_variable (
                        workflow_stage_id,
                        workflow_stage_variable_name,
                        workflow_stage_variable_resolver_key,
                        workflow_stage_variable_data_type,
                        workflow_stage_variable_is_required,
                        workflow_stage_variable_description,
                        workflow_stage_variable_order
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT (
                        workflow_stage_id,
                        workflow_stage_variable_name
                    ) DO NOTHING
                    """,
                    (workflow_stage_id,) + variable,
                )
            prompt_template_id = _required_id(
                connection.execute(
                    """
                    INSERT INTO application.prompt_template (
                        workflow_stage_id,
                        prompt_template_ownership_scope,
                        owner_tenant_id,
                        prompt_template_code,
                        prompt_template_name,
                        created_by_principal_id,
                        updated_by_principal_id
                    ) VALUES (%s, 'tenant', %s, %s, %s, %s, %s)
                    RETURNING prompt_template_id
                    """,
                    (
                        workflow_stage_id,
                        tenant_id,
                        f"{workflow}_execution_{prompt_number}_{suffix}",
                        f"{workflow.title()} Execution {prompt_number} {suffix}",
                        principal_id,
                        principal_id,
                    ),
                ).fetchone(),
                "prompt_template_id",
            )
            prompt_version_id = _required_id(
                connection.execute(
                    """
                    INSERT INTO application.prompt_template_version (
                        prompt_template_id,
                        workflow_stage_id,
                        prompt_template_version_number,
                        system_prompt_template,
                        instruction_prompt_template,
                        prompt_template_digest,
                        created_by_principal_id,
                        updated_by_principal_id
                    ) VALUES (%s, %s, 1, %s, %s, %s, %s, %s)
                    RETURNING prompt_template_version_id
                    """,
                    (
                        prompt_template_id,
                        workflow_stage_id,
                        system_prompt,
                        instruction_prompt,
                        prompt_digest,
                        principal_id,
                        principal_id,
                    ),
                ).fetchone(),
                "prompt_template_version_id",
            )
            connection.execute(
                """
                UPDATE application.prompt_template_version
                   SET prompt_template_version_status = 'published',
                       published_time = CURRENT_TIMESTAMP,
                       published_by_principal_id = %s,
                       updated_by_principal_id = %s,
                       updated_time = CURRENT_TIMESTAMP
                 WHERE prompt_template_version_id = %s
                """,
                (principal_id, principal_id, prompt_version_id),
            )
            prompt_overrides[str(workflow_stage_id)] = prompt_version_id

        created = connection.execute(
            """
            SELECT *
              FROM application.create_workflow_run(
                  %s::UUID,
                  %s::UUID,
                  'user'::VARCHAR,
                  %s::BIGINT,
                  1::BIGINT,
                  %s::VARCHAR,
                  'one_shot'::VARCHAR,
                  'openai_agents_sdk'::VARCHAR,
                  'databricks'::VARCHAR,
                  'test-model'::VARCHAR,
                  'medium'::VARCHAR,
                  8::INTEGER,
                  1::INTEGER,
                  %s::BIGINT[],
                  NULL::VARCHAR,
                  NULL::VARCHAR,
                  %s::UUID,
                  %s::JSONB
              )
            """,
            (
                entra_tenant_id,
                entra_object_id,
                model_id,
                workflow,
                [object_id],
                uuid4(),
                Jsonb(prompt_overrides),
            ),
        ).fetchone()
        if (
            created is None
            or created.get("created") is not True
            or created.get("workflow_run_state") != "queued"
            or created.get("prompt_snapshot_count") != len(prompt_overrides)
        ):
            raise AssertionError("expected governed queued authoring run")
        workflow_run_id = _required_id(created, "workflow_run_id")
    return workflow_run_id


def _create_queued_conceptual_run_with_prompt(
    database: DisposablePostgresFixture,
    *,
    model_id: int,
    tenant_id: int,
    entra_tenant_id: UUID,
    entra_object_id: UUID,
) -> int:
    return _create_queued_authoring_run_with_prompt(
        database,
        model_id=model_id,
        tenant_id=tenant_id,
        entra_tenant_id=entra_tenant_id,
        entra_object_id=entra_object_id,
        workflow="conceptual",
    )


def _create_queued_logical_run_with_prompt(
    database: DisposablePostgresFixture,
    *,
    model_id: int,
    tenant_id: int,
    entra_tenant_id: UUID,
    entra_object_id: UUID,
) -> int:
    return _create_queued_authoring_run_with_prompt(
        database,
        model_id=model_id,
        tenant_id=tenant_id,
        entra_tenant_id=entra_tenant_id,
        entra_object_id=entra_object_id,
        workflow="logical",
    )


def _create_queued_dimensional_run_with_prompt(
    database: DisposablePostgresFixture,
    *,
    model_id: int,
    tenant_id: int,
    entra_tenant_id: UUID,
    entra_object_id: UUID,
    selected_object_id: int,
) -> int:
    return _create_queued_authoring_run_with_prompt(
        database,
        model_id=model_id,
        tenant_id=tenant_id,
        entra_tenant_id=entra_tenant_id,
        entra_object_id=entra_object_id,
        workflow="dimensional",
        selected_object_id=selected_object_id,
    )


def _create_queued_analysis_run_with_prompt(
    database: DisposablePostgresFixture,
    *,
    model_id: int,
    tenant_id: int,
    entra_tenant_id: UUID,
    entra_object_id: UUID,
) -> int:
    suffix = uuid4().hex
    with database.connect_owner() as connection:
        actor = connection.execute(
            """
            SELECT identity.principal_id
              FROM security.entra_principal_identity AS identity
             WHERE identity.entra_tenant_id = %s
               AND identity.entra_object_id = %s
            """,
            (entra_tenant_id, entra_object_id),
        ).fetchone()
        selected = connection.execute(
            """
            SELECT scope.object_id
              FROM model.model_scope AS scope
             WHERE scope.model_id = %s
               AND scope.is_active
             ORDER BY scope.object_id
             LIMIT 1
            """,
            (model_id,),
        ).fetchone()
        if actor is None or selected is None:
            raise AssertionError("expected seeded Analysis run inputs")
        principal_id = _required_id(actor, "principal_id")
        object_id = _required_id(selected, "object_id")

        stage = connection.execute(
            """
            SELECT workflow_stage_id
              FROM application.workflow_stage
             WHERE model_workflow = 'analysis'
               AND workflow_execution_mode = 'one_shot'
               AND workflow_stage_code = 'relationship_inference'
            """
        ).fetchone()
        if stage is None:
            stage = connection.execute(
                """
                INSERT INTO application.workflow_stage (
                    model_workflow,
                    workflow_execution_mode,
                    workflow_stage_code,
                    workflow_stage_name,
                    workflow_stage_order,
                    workflow_stage_is_agentic
                ) VALUES (
                    'analysis', 'one_shot', 'relationship_inference',
                    'Relationship inference', 10, TRUE
                )
                RETURNING workflow_stage_id
                """
            ).fetchone()
        workflow_stage_id = _required_id(stage, "workflow_stage_id")
        variables = (
            (
                "stage_context",
                "workflow.analysis.one_shot.relationship_inference.context",
                "json",
                True,
                "Immutable bounded context for this Analysis run.",
                10,
            ),
            (
                "validation_failures",
                "workflow.validation_failures",
                "json",
                False,
                "Bounded validation failures for a repair attempt.",
                20,
            ),
        )
        for variable in variables:
            connection.execute(
                """
                INSERT INTO application.workflow_stage_variable (
                    workflow_stage_id,
                    workflow_stage_variable_name,
                    workflow_stage_variable_resolver_key,
                    workflow_stage_variable_data_type,
                    workflow_stage_variable_is_required,
                    workflow_stage_variable_description,
                    workflow_stage_variable_order
                ) VALUES (%s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (
                    workflow_stage_id,
                    workflow_stage_variable_name
                ) DO NOTHING
                """,
                (workflow_stage_id,) + variable,
            )

        system_prompt = "Infer the complete Analysis relationship candidate."
        instruction_prompt = "Use the immutable context: {{stage_context}}."
        digest_row = connection.execute(
            """
            SELECT encode(
                       sha256(
                           convert_to(
                               jsonb_build_object(
                                   'system_prompt_template', %s::TEXT,
                                   'instruction_prompt_template', %s::TEXT,
                                   'tool_instruction_prompt_template', NULL::TEXT
                               )::TEXT,
                               'UTF8'
                           )
                       ),
                       'hex'
                   ) AS prompt_digest
            """,
            (system_prompt, instruction_prompt),
        ).fetchone()
        if digest_row is None or not isinstance(digest_row.get("prompt_digest"), str):
            raise AssertionError("expected Prompt digest")
        prompt_digest = digest_row["prompt_digest"]
        prompt_template_id = _required_id(
            connection.execute(
                """
                INSERT INTO application.prompt_template (
                    workflow_stage_id,
                    prompt_template_ownership_scope,
                    owner_tenant_id,
                    prompt_template_code,
                    prompt_template_name,
                    created_by_principal_id,
                    updated_by_principal_id
                ) VALUES (%s, 'tenant', %s, %s, %s, %s, %s)
                RETURNING prompt_template_id
                """,
                (
                    workflow_stage_id,
                    tenant_id,
                    f"analysis_execution_{suffix}",
                    f"Analysis Execution {suffix}",
                    principal_id,
                    principal_id,
                ),
            ).fetchone(),
            "prompt_template_id",
        )
        prompt_version_id = _required_id(
            connection.execute(
                """
                INSERT INTO application.prompt_template_version (
                    prompt_template_id,
                    workflow_stage_id,
                    prompt_template_version_number,
                    system_prompt_template,
                    instruction_prompt_template,
                    prompt_template_digest,
                    created_by_principal_id,
                    updated_by_principal_id
                ) VALUES (%s, %s, 1, %s, %s, %s, %s, %s)
                RETURNING prompt_template_version_id
                """,
                (
                    prompt_template_id,
                    workflow_stage_id,
                    system_prompt,
                    instruction_prompt,
                    prompt_digest,
                    principal_id,
                    principal_id,
                ),
            ).fetchone(),
            "prompt_template_version_id",
        )
        connection.execute(
            """
            UPDATE application.prompt_template_version
               SET prompt_template_version_status = 'published',
                   published_time = CURRENT_TIMESTAMP,
                   published_by_principal_id = %s,
                   updated_by_principal_id = %s,
                   updated_time = CURRENT_TIMESTAMP
             WHERE prompt_template_version_id = %s
            """,
            (principal_id, principal_id, prompt_version_id),
        )

        created = connection.execute(
            """
            SELECT *
              FROM application.create_workflow_run(
                  %s::UUID,
                  %s::UUID,
                  'user'::VARCHAR,
                  %s::BIGINT,
                  1::BIGINT,
                  'analysis'::VARCHAR,
                  'one_shot'::VARCHAR,
                  'openai_agents_sdk'::VARCHAR,
                  'databricks'::VARCHAR,
                  'test-model'::VARCHAR,
                  'medium'::VARCHAR,
                  8::INTEGER,
                  1::INTEGER,
                  %s::BIGINT[],
                  NULL::VARCHAR,
                  NULL::VARCHAR,
                  %s::UUID,
                  %s::JSONB
              )
            """,
            (
                entra_tenant_id,
                entra_object_id,
                model_id,
                [object_id],
                uuid4(),
                Jsonb({str(workflow_stage_id): prompt_version_id}),
            ),
        ).fetchone()
        if (
            created is None
            or created.get("created") is not True
            or created.get("workflow_run_state") != "queued"
            or created.get("prompt_snapshot_count") != 1
        ):
            raise AssertionError("expected governed queued Analysis run")
        workflow_run_id = _required_id(created, "workflow_run_id")
    return workflow_run_id


@pytest.mark.asyncio
async def test_web_change_set_requires_lock_and_applies_with_null_provenance(
    web_postgres_database: DisposablePostgresFixture,
) -> None:
    (
        model_id,
        tenant_id,
        _attribute_id,
        entra_tenant_id,
        entra_object_id,
        profile,
    ) = _seed_profile_model(web_postgres_database)
    principal = RequestPrincipal(
        actor_kind=ActorKind.HUMAN,
        entra_tenant_id=entra_tenant_id,
        entra_object_id=entra_object_id,
    )
    database = WebPostgresDatabase(
        dsn=web_postgres_database.web_runtime_dsn(),
        pool_min=1,
        pool_max=1,
        pool_timeout_seconds=5,
    )
    service = DatabaseModelChangeSetService(
        database=database,
        authorizer=AuthorizationService(),
    )
    await database.open()
    try:
        with pytest.raises(TenantLockRequiredError):
            await service.create_or_resume(
                principal,
                tenant_id=tenant_id,
                model_id=model_id,
                command=CreateModelChangeSetRequest(expected_model_revision=1),
                idempotency_key=uuid4(),
            )

        with web_postgres_database.connect_owner() as connection:
            acquired = connection.execute(
                """
                SELECT acquired
                  FROM security.acquire_tenant_lock(
                      %s, %s, 'user', %s, 60, 'Web Model authoring test'
                  )
                """,
                (entra_tenant_id, entra_object_id, tenant_id),
            ).fetchone()
        assert acquired == {"acquired": True}

        created = await service.create_or_resume(
            principal,
            tenant_id=tenant_id,
            model_id=model_id,
            command=CreateModelChangeSetRequest(expected_model_revision=1),
            idempotency_key=uuid4(),
        )
        resumed = await service.create_or_resume(
            principal,
            tenant_id=tenant_id,
            model_id=model_id,
            command=CreateModelChangeSetRequest(expected_model_revision=1),
            idempotency_key=uuid4(),
        )
        assert created.created is True
        assert resumed.created is False
        assert resumed.model_change_set_id == created.model_change_set_id

        with pytest.raises(InvalidRequestError):
            await service.stage(
                principal,
                tenant_id=tenant_id,
                model_id=model_id,
                change_set_id=created.model_change_set_id,
                command=StageModelChangeSetRequest(
                    expected_draft_revision=1,
                    changes=[
                        StageModelChange(dataset="profiling_profile", records=[profile])
                    ],
                ),
                idempotency_key=uuid4(),
            )

        conceptual_records: list[dict[str, object]] = [
            {
                "conceptual_object_name": name,
                "conceptual_object_definition": f"A governed {name.lower()}.",
                "conceptual_object_type": object_type,
                "conceptual_object_grain": f"One {name.lower()}.",
                "conceptual_object_aliases": [],
                "conceptual_object_confidence": "high",
                "conceptual_object_status": "active",
                "conceptual_object_is_locked": False,
                "supports": [],
            }
            for name, object_type in (("Customer", "party"), ("Order", "transaction"))
        ]
        chunks = [[conceptual_records[0]], [conceptual_records[1]]]
        chunk_hashes = [canonical_records_sha256(chunk) for chunk in chunks]
        batch_command = BeginModelStageBatchRequest(
            expected_draft_revision=1,
            dataset="conceptual_object",
            total_record_count=2,
            total_chunk_count=2,
            batch_sha256=stage_batch_sha256(chunk_hashes),
        )
        begun = await service.begin_stage_batch(
            principal,
            tenant_id=tenant_id,
            model_id=model_id,
            change_set_id=created.model_change_set_id,
            command=batch_command,
            idempotency_key=uuid4(),
        )
        resumed_batch = await service.begin_stage_batch(
            principal,
            tenant_id=tenant_id,
            model_id=model_id,
            change_set_id=created.model_change_set_id,
            command=batch_command,
            idempotency_key=uuid4(),
        )
        assert begun.created is True
        assert resumed_batch.created is False
        assert resumed_batch.stage_batch_id == begun.stage_batch_id
        for chunk_index, (chunk, chunk_hash) in enumerate(
            zip(chunks, chunk_hashes, strict=True),
            start=1,
        ):
            put = await service.put_stage_chunk(
                principal,
                tenant_id=tenant_id,
                model_id=model_id,
                change_set_id=created.model_change_set_id,
                stage_batch_id=begun.stage_batch_id,
                chunk_index=chunk_index,
                command=PutModelStageChunkRequest(
                    dataset="conceptual_object",
                    records=chunk,
                    chunk_sha256=chunk_hash,
                ),
                idempotency_key=uuid4(),
            )
            assert put.received_chunk_count == chunk_index
        duplicate = await service.put_stage_chunk(
            principal,
            tenant_id=tenant_id,
            model_id=model_id,
            change_set_id=created.model_change_set_id,
            stage_batch_id=begun.stage_batch_id,
            chunk_index=1,
            command=PutModelStageChunkRequest(
                dataset="conceptual_object",
                records=chunks[0],
                chunk_sha256=chunk_hashes[0],
            ),
            idempotency_key=uuid4(),
        )
        assert duplicate.duplicate is True
        committed = await service.commit_stage_batch(
            principal,
            tenant_id=tenant_id,
            model_id=model_id,
            change_set_id=created.model_change_set_id,
            stage_batch_id=begun.stage_batch_id,
            command=ExpectedDraftRevisionRequest(expected_draft_revision=1),
            idempotency_key=uuid4(),
        )
        replayed = await service.commit_stage_batch(
            principal,
            tenant_id=tenant_id,
            model_id=model_id,
            change_set_id=created.model_change_set_id,
            stage_batch_id=begun.stage_batch_id,
            command=ExpectedDraftRevisionRequest(expected_draft_revision=1),
            idempotency_key=uuid4(),
        )
        assert committed.draft_revision == 2
        assert replayed.replayed is True
        validated = await service.validate(
            principal,
            tenant_id=tenant_id,
            model_id=model_id,
            change_set_id=created.model_change_set_id,
            command=ExpectedDraftRevisionRequest(
                expected_draft_revision=committed.draft_revision
            ),
            idempotency_key=uuid4(),
        )
        assert validated.valid is True
        applied = await service.apply(
            principal,
            tenant_id=tenant_id,
            model_id=model_id,
            change_set_id=created.model_change_set_id,
            command=ExpectedDraftRevisionRequest(
                expected_draft_revision=committed.draft_revision
            ),
            idempotency_key=uuid4(),
        )
    finally:
        await database.close()

    with web_postgres_database.connect_owner() as connection:
        stored = connection.execute(
            """
            SELECT agent_run_id, workflow_run_id, conceptual_object_name
              FROM workflow.conceptual_object
             WHERE model_id = %s
             ORDER BY conceptual_object_name
            """,
            (model_id,),
        ).fetchall()
        model = connection.execute(
            "SELECT model_revision FROM model.model WHERE model_id = %s",
            (model_id,),
        ).fetchone()

    assert applied.action_count == 2
    assert stored == [
        {
            "agent_run_id": None,
            "workflow_run_id": None,
            "conceptual_object_name": "Customer",
        },
        {
            "agent_run_id": None,
            "workflow_run_id": None,
            "conceptual_object_name": "Order",
        },
    ]
    assert model == {"model_revision": 2}


@pytest.mark.asyncio
async def test_workflow_handoff_rolls_back_invalid_output_then_replays_one_bound_draft(
    web_postgres_database: DisposablePostgresFixture,
) -> None:
    (
        model_id,
        tenant_id,
        _attribute_id,
        entra_tenant_id,
        entra_object_id,
        _profile,
    ) = _seed_profile_model(web_postgres_database)
    workflow_run_id = _create_running_conceptual_run(
        web_postgres_database,
        tenant_id=tenant_id,
        model_id=model_id,
        entra_tenant_id=entra_tenant_id,
        entra_object_id=entra_object_id,
    )
    with web_postgres_database.connect_owner() as connection:
        acquired = connection.execute(
            """
            SELECT acquired
              FROM security.acquire_tenant_lock(
                  %s, %s, 'user', %s, 60, 'Workflow handoff test'
              )
            """,
            (entra_tenant_id, entra_object_id, tenant_id),
        ).fetchone()
    assert acquired == {"acquired": True}

    principal = RequestPrincipal(
        actor_kind=ActorKind.HUMAN,
        entra_tenant_id=entra_tenant_id,
        entra_object_id=entra_object_id,
    )
    database = WebPostgresDatabase(
        dsn=web_postgres_database.web_runtime_dsn(),
        pool_min=1,
        pool_max=1,
        pool_timeout_seconds=5,
    )
    handoff = WorkflowChangeSetHandoff(
        database=database,
        authorizer=AuthorizationService(),
    )
    apply_service = DatabaseWorkflowDraftApplyService(
        database=database,
        authorizer=AuthorizationService(),
    )
    invalid_relationship = StageModelChange(
        dataset="conceptual_relationship",
        records=[
            {
                "from_conceptual_object_name": "Missing Order",
                "to_conceptual_object_name": "Missing Customer",
                "conceptual_relationship_name": "belongs to",
                "conceptual_relationship_type": "association",
                "conceptual_relationship_definition": "Order belongs to customer.",
                "conceptual_relationship_cardinality": "many_to_one",
                "conceptual_relationship_basis": "Business rule.",
                "conceptual_relationship_cardinality_basis": "Many orders per customer.",
                "conceptual_relationship_confidence": "high",
                "conceptual_relationship_status": "active",
                "conceptual_relationship_is_locked": False,
                "supports": [],
            }
        ],
    )
    valid_object = StageModelChange(
        dataset="conceptual_object",
        records=[
            {
                "conceptual_object_name": "Customer",
                "conceptual_object_definition": "A governed customer.",
                "conceptual_object_type": "party",
                "conceptual_object_grain": "One customer.",
                "conceptual_object_aliases": [],
                "conceptual_object_confidence": "high",
                "conceptual_object_status": "active",
                "conceptual_object_is_locked": False,
                "supports": [],
            }
        ],
    )

    await database.open()
    try:
        claim = await DatabaseWorkflowClaimRepository(database=database).claim_next(
            lease_duration_seconds=300
        )
        assert claim is not None
        assert (
            claim.workflow_run_id,
            claim.tenant_id,
            claim.model_id,
            claim.model_revision,
            claim.model_workflow,
            claim.workflow_execution_mode,
        ) == (workflow_run_id, tenant_id, model_id, 1, "conceptual", "one_shot")
        with pytest.raises(WorkflowChangeSetValidationError):
            await handoff.handoff(
                principal,
                tenant_id=tenant_id,
                model_id=model_id,
                workflow_run_id=workflow_run_id,
                expected_workflow="conceptual",
                expected_model_revision=1,
                workflow_run_claim_token=claim.workflow_run_claim_token,
                changes=(invalid_relationship,),
            )

        with web_postgres_database.connect_owner() as connection:
            rolled_back = connection.execute(
                """
                SELECT count(*) AS change_set_count
                  FROM mcp.model_change_set
                 WHERE workflow_run_id = %s
                """,
                (workflow_run_id,),
            ).fetchone()
        assert rolled_back == {"change_set_count": 0}

        created = await handoff.handoff(
            principal,
            tenant_id=tenant_id,
            model_id=model_id,
            workflow_run_id=workflow_run_id,
            expected_workflow="conceptual",
            expected_model_revision=1,
            workflow_run_claim_token=claim.workflow_run_claim_token,
            changes=(valid_object,),
        )
        replayed = await handoff.handoff(
            principal,
            tenant_id=tenant_id,
            model_id=model_id,
            workflow_run_id=workflow_run_id,
            expected_workflow="conceptual",
            expected_model_revision=1,
            workflow_run_claim_token=claim.workflow_run_claim_token,
            changes=(valid_object,),
        )
        with pytest.raises(InvalidRequestError):
            await apply_service.apply(
                principal,
                tenant_id=tenant_id,
                model_id=model_id,
                workflow_run_id=workflow_run_id,
                command=ApplyWorkflowDraftRequest(
                    expected_model_revision=1,
                    expected_draft_revision=created.draft_revision,
                    expected_candidate_digest=created.candidate_digest,
                ),
                idempotency_key=uuid4(),
            )
        changed_record = dict(valid_object.records[0])
        changed_record["conceptual_object_definition"] = "A different candidate."
        with pytest.raises(InvalidRequestError):
            await handoff.handoff(
                principal,
                tenant_id=tenant_id,
                model_id=model_id,
                workflow_run_id=workflow_run_id,
                expected_workflow="conceptual",
                expected_model_revision=1,
                workflow_run_claim_token=claim.workflow_run_claim_token,
                changes=(
                    StageModelChange(
                        dataset="conceptual_object",
                        records=[changed_record],
                    ),
                ),
            )
    finally:
        await database.close()

    with web_postgres_database.connect_owner() as connection:
        stored = connection.execute(
            """
            SELECT model_change_set_id,
                   workflow_run_id,
                   model_change_set_status,
                   conceptual_document,
                   candidate_digest
              FROM mcp.model_change_set
             WHERE workflow_run_id = %s
            """,
            (workflow_run_id,),
        ).fetchone()
        events = connection.execute(
            """
            SELECT event_type
              FROM mcp.model_change_set_event
             WHERE model_change_set_id = %s
             ORDER BY event_sequence
            """,
            (created.model_change_set_id,),
        ).fetchall()
        model = connection.execute(
            "SELECT model_revision FROM model.model WHERE model_id = %s",
            (model_id,),
        ).fetchone()
        materialized = connection.execute(
            """
            SELECT count(*) AS conceptual_object_count
              FROM workflow.conceptual_object
             WHERE model_id = %s
            """,
            (model_id,),
        ).fetchone()

    assert created.replayed is False
    assert replayed.replayed is True
    assert replayed.model_change_set_id == created.model_change_set_id
    assert stored is not None
    assert stored["workflow_run_id"] == workflow_run_id
    assert stored["model_change_set_status"] == "validated"
    assert stored["candidate_digest"] == created.candidate_digest
    conceptual_document_value = stored["conceptual_document"]
    assert isinstance(conceptual_document_value, dict)
    conceptual_document = cast(dict[str, object], conceptual_document_value)
    conceptual_objects_value = conceptual_document.get("conceptual_object")
    assert isinstance(conceptual_objects_value, list)
    conceptual_objects = cast(list[object], conceptual_objects_value)
    assert len(conceptual_objects) == 1
    assert events == [
        {"event_type": "created"},
        {"event_type": "section_put"},
        {"event_type": "validated"},
    ]
    assert model == {"model_revision": 1}
    assert materialized == {"conceptual_object_count": 0}


@pytest.mark.asyncio
async def test_workflow_finalization_is_atomic_and_rejects_completed_claim_reuse(
    web_postgres_database: DisposablePostgresFixture,
) -> None:
    (
        model_id,
        tenant_id,
        _attribute_id,
        entra_tenant_id,
        entra_object_id,
        _profile,
    ) = _seed_profile_model(web_postgres_database)
    with web_postgres_database.connect_owner() as connection:
        acquired = connection.execute(
            """
            SELECT acquired
              FROM security.acquire_tenant_lock(
                  %s, %s, 'user', %s, 60, 'Atomic finalization test'
              )
            """,
            (entra_tenant_id, entra_object_id, tenant_id),
        ).fetchone()
    assert acquired == {"acquired": True}
    workflow_run_id = _create_queued_conceptual_run_with_prompt(
        web_postgres_database,
        model_id=model_id,
        tenant_id=tenant_id,
        entra_tenant_id=entra_tenant_id,
        entra_object_id=entra_object_id,
    )
    principal = RequestPrincipal(
        actor_kind=ActorKind.HUMAN,
        entra_tenant_id=entra_tenant_id,
        entra_object_id=entra_object_id,
    )
    change = StageModelChange(
        dataset="conceptual_object",
        records=[
            {
                "conceptual_object_name": "Customer",
                "conceptual_object_definition": "A governed customer.",
                "conceptual_object_type": "party",
                "conceptual_object_grain": "One customer.",
                "conceptual_object_aliases": [],
                "conceptual_object_confidence": "high",
                "conceptual_object_status": "active",
                "conceptual_object_is_locked": False,
                "supports": [],
            }
        ],
    )
    database = WebPostgresDatabase(
        dsn=web_postgres_database.web_runtime_dsn(),
        pool_min=1,
        pool_max=1,
        pool_timeout_seconds=5,
    )
    lifecycle = DatabaseAgentWorkflowLifecycle(database=database)
    finalizer = WorkflowChangeSetHandoff(
        database=database,
        authorizer=AuthorizationService(),
    )
    final_event = AgentWorkflowEvent(
        sequence=2,
        attempt=1,
        stage="conceptual.backend_validation",
        status="running",
        message="Conceptual candidate is ready in a validated draft.",
        current=1,
        total=1,
        finding_count=1,
    )

    await database.open()
    try:
        await lifecycle.start(
            principal,
            tenant_id=tenant_id,
            model_id=model_id,
            workflow_run_id=workflow_run_id,
            expected_workflow="conceptual",
            expected_execution_mode="one_shot",
            expected_model_revision=1,
        )
        claim = await DatabaseWorkflowClaimRepository(database=database).claim_next(
            lease_duration_seconds=300
        )
        assert claim is not None
        assert (
            claim.workflow_run_id,
            claim.tenant_id,
            claim.model_id,
            claim.model_revision,
            claim.model_workflow,
            claim.workflow_execution_mode,
        ) == (workflow_run_id, tenant_id, model_id, 1, "conceptual", "one_shot")
        with pytest.raises(InvalidRequestError):
            await finalizer.finalize(
                principal,
                tenant_id=tenant_id,
                model_id=model_id,
                workflow_run_id=workflow_run_id,
                expected_workflow="conceptual",
                expected_model_revision=1,
                workflow_run_claim_token=claim.workflow_run_claim_token,
                changes=(change,),
                final_event=final_event.model_copy(update={"sequence": 3}),
            )

        with web_postgres_database.connect_owner() as connection:
            rolled_back = connection.execute(
                """
                SELECT run.workflow_run_state,
                       (SELECT count(*)
                          FROM mcp.model_change_set AS change_set
                         WHERE change_set.workflow_run_id = run.workflow_run_id
                       ) AS change_set_count,
                       (SELECT count(*)
                          FROM model.model_event_log AS event
                         WHERE event.workflow_run_id = run.workflow_run_id
                       ) AS event_count
                  FROM application.workflow_run AS run
                 WHERE run.workflow_run_id = %s
                """,
                (workflow_run_id,),
            ).fetchone()
        assert rolled_back == {
            "workflow_run_state": "running",
            "change_set_count": 0,
            "event_count": 1,
        }

        committed = await finalizer.finalize(
            principal,
            tenant_id=tenant_id,
            model_id=model_id,
            workflow_run_id=workflow_run_id,
            expected_workflow="conceptual",
            expected_model_revision=1,
            workflow_run_claim_token=claim.workflow_run_claim_token,
            changes=(change,),
            final_event=final_event,
        )
        with pytest.raises(DependencyUnavailableError):
            await finalizer.finalize(
                principal,
                tenant_id=tenant_id,
                model_id=model_id,
                workflow_run_id=workflow_run_id,
                expected_workflow="conceptual",
                expected_model_revision=1,
                workflow_run_claim_token=claim.workflow_run_claim_token,
                changes=(change,),
                final_event=final_event.model_copy(
                    update={"message": "A different terminal payload."}
                ),
            )
        with pytest.raises(DependencyUnavailableError):
            await finalizer.finalize(
                principal,
                tenant_id=tenant_id,
                model_id=model_id,
                workflow_run_id=workflow_run_id,
                expected_workflow="conceptual",
                expected_model_revision=1,
                workflow_run_claim_token=claim.workflow_run_claim_token,
                changes=(change,),
                final_event=final_event,
            )
    finally:
        await database.close()

    with web_postgres_database.connect_owner() as connection:
        stored = connection.execute(
            """
            SELECT run.workflow_run_state,
                   target_model.model_revision,
                   change_set.model_change_set_status,
                   count(*) OVER () AS change_set_count
              FROM application.workflow_run AS run
              JOIN model.model AS target_model
                ON target_model.model_id = run.model_id
              JOIN mcp.model_change_set AS change_set
                ON change_set.workflow_run_id = run.workflow_run_id
             WHERE run.workflow_run_id = %s
            """,
            (workflow_run_id,),
        ).fetchone()
        events = connection.execute(
            """
            SELECT model_event_log_sequence AS sequence,
                   model_event_log_stage AS stage,
                   model_event_log_status AS status,
                   finding_count
              FROM model.model_event_log
             WHERE workflow_run_id = %s
             ORDER BY model_event_log_sequence
            """,
            (workflow_run_id,),
        ).fetchall()

    assert committed.handoff.replayed is False
    assert committed.completion.changed is True
    assert committed.completion.workflow_run_state == "completed"
    assert stored == {
        "workflow_run_state": "completed",
        "model_revision": 1,
        "model_change_set_status": "validated",
        "change_set_count": 1,
    }
    assert events == [
        {
            "sequence": 1,
            "stage": "workflow_run",
            "status": "started",
            "finding_count": 0,
        },
        {
            "sequence": 2,
            "stage": "conceptual.backend_validation",
            "status": "running",
            "finding_count": 1,
        },
        {
            "sequence": 3,
            "stage": "workflow_run",
            "status": "completed",
            "finding_count": 1,
        },
    ]


@pytest.mark.asyncio
async def test_conceptual_executor_completes_with_one_validated_unapplied_draft(
    web_postgres_database: DisposablePostgresFixture,
) -> None:
    (
        model_id,
        tenant_id,
        _attribute_id,
        entra_tenant_id,
        entra_object_id,
        _profile,
    ) = _seed_profile_model(web_postgres_database)
    with web_postgres_database.connect_owner() as connection:
        acquired = connection.execute(
            """
            SELECT acquired
              FROM security.acquire_tenant_lock(
                  %s, %s, 'user', %s, 60, 'Conceptual execution test'
              )
            """,
            (entra_tenant_id, entra_object_id, tenant_id),
        ).fetchone()
    assert acquired == {"acquired": True}
    workflow_run_id = _create_queued_conceptual_run_with_prompt(
        web_postgres_database,
        model_id=model_id,
        tenant_id=tenant_id,
        entra_tenant_id=entra_tenant_id,
        entra_object_id=entra_object_id,
    )

    principal = RequestPrincipal(
        actor_kind=ActorKind.HUMAN,
        entra_tenant_id=entra_tenant_id,
        entra_object_id=entra_object_id,
    )
    database = WebPostgresDatabase(
        dsn=web_postgres_database.web_runtime_dsn(),
        pool_min=1,
        pool_max=1,
        pool_timeout_seconds=5,
    )
    authorizer = AuthorizationService()
    lifecycle = DatabaseAgentWorkflowLifecycle(database=database)
    workflow = ConceptualWorkflow(
        lifecycle=lifecycle,
        executor=DatabaseConceptualExecutor(
            database=database,
            authorizer=authorizer,
            agent_executor=LocalFakeAgentAdapter(sdk_code="openai_agents_sdk"),
            handoff=WorkflowChangeSetHandoff(
                database=database,
                authorizer=authorizer,
            ),
            no_op=DatabaseAuthoringNoOpService(database=database),
            lifecycle=lifecycle,
        ),
    )
    runs = DatabaseWorkflowRunService(
        database=database,
        authorizer=authorizer,
        cursor_signing_key=b"conceptual-test-cursor-key-32-bytes",
    )

    await database.open()
    try:
        started = await workflow.start(
            principal,
            tenant_id=tenant_id,
            model_id=model_id,
            workflow_run_id=workflow_run_id,
            expected_execution_mode="one_shot",
            expected_model_revision=1,
        )
        claim = await DatabaseWorkflowClaimRepository(database=database).claim_next(
            lease_duration_seconds=30
        )
        assert claim is not None
        assert (
            claim.workflow_run_id,
            claim.tenant_id,
            claim.model_id,
            claim.model_revision,
            claim.model_workflow,
            claim.workflow_execution_mode,
        ) == (workflow_run_id, tenant_id, model_id, 1, "conceptual", "one_shot")
        result = await workflow.execute_started(
            principal,
            tenant_id=tenant_id,
            model_id=model_id,
            workflow_run_id=workflow_run_id,
            expected_model_revision=1,
            workflow_run_claim_token=claim.workflow_run_claim_token,
        )
        assert isinstance(result, WorkflowChangeSetHandoffResult)
        detail = await runs.read_run(
            principal,
            tenant_id=tenant_id,
            model_id=model_id,
            workflow_run_id=workflow_run_id,
        )
        events = await runs.list_events(
            principal,
            tenant_id=tenant_id,
            model_id=model_id,
            workflow_run_id=workflow_run_id,
            after_sequence=0,
            page_size=20,
        )
    finally:
        await database.close()

    with web_postgres_database.connect_owner() as connection:
        persisted = connection.execute(
            """
            SELECT count(*) AS change_set_count,
                   min(model_change_set_status) AS model_change_set_status,
                   min(candidate_digest) AS candidate_digest
              FROM mcp.model_change_set
             WHERE workflow_run_id = %s
               AND model_id = %s
            """,
            (workflow_run_id, model_id),
        ).fetchone()
        model = connection.execute(
            "SELECT model_revision FROM model.model WHERE model_id = %s",
            (model_id,),
        ).fetchone()
        materialized = connection.execute(
            """
            SELECT (
                       SELECT count(*)
                         FROM workflow.conceptual_object
                        WHERE model_id = %s
                   ) AS conceptual_object_count,
                   (
                       SELECT count(*)
                         FROM workflow.conceptual_relationship
                        WHERE model_id = %s
                   ) AS conceptual_relationship_count,
                   (
                       SELECT count(*)
                         FROM workflow.conceptual_support
                        WHERE model_id = %s
                   ) AS conceptual_support_count
            """,
            (model_id, model_id, model_id),
        ).fetchone()

    assert started.changed is True
    assert started.workflow_run_state == "running"
    assert result.replayed is False
    assert result.workflow_run_id == workflow_run_id
    assert result.staged_record_count == 1
    assert detail.workflow_run_state == "completed"
    assert detail.model_change_set_id == result.model_change_set_id
    assert detail.model_change_set_status == "validated"
    assert detail.draft_revision == result.draft_revision
    assert detail.candidate_digest == result.candidate_digest
    assert detail.validated_at == result.validated_at
    assert detail.failure_code is None
    assert [event.sequence for event in events.items] == [1, 2, 3, 4]
    assert [event.stage for event in events.items] == [
        "workflow_run",
        "conceptual.candidate_authoring",
        "conceptual.backend_validation",
        "workflow_run",
    ]
    assert [event.status for event in events.items] == [
        "started",
        "running",
        "running",
        "completed",
    ]
    assert [event.finding_count for event in events.items] == [0, 0, 1, 1]
    assert persisted == {
        "change_set_count": 1,
        "model_change_set_status": "validated",
        "candidate_digest": result.candidate_digest,
    }
    assert model == {"model_revision": 1}
    assert materialized == {
        "conceptual_object_count": 0,
        "conceptual_relationship_count": 0,
        "conceptual_support_count": 0,
    }


@pytest.mark.asyncio
async def test_completed_conceptual_draft_applies_once_with_run_provenance(
    web_postgres_database: DisposablePostgresFixture,
) -> None:
    (
        model_id,
        tenant_id,
        _attribute_id,
        entra_tenant_id,
        entra_object_id,
        _profile,
    ) = _seed_profile_model(web_postgres_database)
    with web_postgres_database.connect_owner() as connection:
        acquired = connection.execute(
            """
            SELECT acquired
              FROM security.acquire_tenant_lock(
                  %s, %s, 'user', %s, 60, 'Conceptual apply test'
              )
            """,
            (entra_tenant_id, entra_object_id, tenant_id),
        ).fetchone()
    assert acquired == {"acquired": True}
    workflow_run_id = _create_queued_conceptual_run_with_prompt(
        web_postgres_database,
        model_id=model_id,
        tenant_id=tenant_id,
        entra_tenant_id=entra_tenant_id,
        entra_object_id=entra_object_id,
    )

    principal = RequestPrincipal(
        actor_kind=ActorKind.HUMAN,
        entra_tenant_id=entra_tenant_id,
        entra_object_id=entra_object_id,
    )
    database = WebPostgresDatabase(
        dsn=web_postgres_database.web_runtime_dsn(),
        pool_min=1,
        pool_max=1,
        pool_timeout_seconds=5,
    )
    authorizer = AuthorizationService()
    lifecycle = DatabaseAgentWorkflowLifecycle(database=database)
    workflow = ConceptualWorkflow(
        lifecycle=lifecycle,
        executor=DatabaseConceptualExecutor(
            database=database,
            authorizer=authorizer,
            agent_executor=LocalFakeAgentAdapter(sdk_code="openai_agents_sdk"),
            handoff=WorkflowChangeSetHandoff(
                database=database,
                authorizer=authorizer,
            ),
            no_op=DatabaseAuthoringNoOpService(database=database),
            lifecycle=lifecycle,
        ),
    )
    apply_service = DatabaseWorkflowDraftApplyService(
        database=database,
        authorizer=authorizer,
    )
    idempotency_key = uuid4()

    await database.open()
    try:
        await workflow.start(
            principal,
            tenant_id=tenant_id,
            model_id=model_id,
            workflow_run_id=workflow_run_id,
            expected_execution_mode="one_shot",
            expected_model_revision=1,
        )
        claim = await DatabaseWorkflowClaimRepository(database=database).claim_next(
            lease_duration_seconds=30
        )
        assert claim is not None
        assert (
            claim.workflow_run_id,
            claim.tenant_id,
            claim.model_id,
            claim.model_revision,
            claim.model_workflow,
            claim.workflow_execution_mode,
        ) == (workflow_run_id, tenant_id, model_id, 1, "conceptual", "one_shot")
        draft = await workflow.execute_started(
            principal,
            tenant_id=tenant_id,
            model_id=model_id,
            workflow_run_id=workflow_run_id,
            expected_model_revision=1,
            workflow_run_claim_token=claim.workflow_run_claim_token,
        )
        assert isinstance(draft, WorkflowChangeSetHandoffResult)
        command = ApplyWorkflowDraftRequest(
            expected_model_revision=1,
            expected_draft_revision=draft.draft_revision,
            expected_candidate_digest=draft.candidate_digest,
        )

        with pytest.raises(CandidateDigestConflictError):
            await apply_service.apply(
                principal,
                tenant_id=tenant_id,
                model_id=model_id,
                workflow_run_id=workflow_run_id,
                command=command.model_copy(
                    update={"expected_candidate_digest": "e" * 64}
                ),
                idempotency_key=uuid4(),
            )
        with pytest.raises(ModelRevisionConflictError):
            await apply_service.apply(
                principal,
                tenant_id=tenant_id,
                model_id=model_id,
                workflow_run_id=workflow_run_id,
                command=command.model_copy(update={"expected_model_revision": 2}),
                idempotency_key=uuid4(),
            )

        with web_postgres_database.connect_owner() as connection:
            released = connection.execute(
                """
                SELECT released
                  FROM security.release_tenant_lock(%s, %s, 'user', %s)
                """,
                (entra_tenant_id, entra_object_id, tenant_id),
            ).fetchone()
        assert released == {"released": True}
        with pytest.raises(TenantLockRequiredError):
            await apply_service.apply(
                principal,
                tenant_id=tenant_id,
                model_id=model_id,
                workflow_run_id=workflow_run_id,
                command=command,
                idempotency_key=idempotency_key,
            )

        with web_postgres_database.connect_owner() as connection:
            reacquired = connection.execute(
                """
                SELECT acquired
                  FROM security.acquire_tenant_lock(
                      %s, %s, 'user', %s, 60, 'Conceptual apply retry'
                  )
                """,
                (entra_tenant_id, entra_object_id, tenant_id),
            ).fetchone()
        assert reacquired == {"acquired": True}
        applied = await apply_service.apply(
            principal,
            tenant_id=tenant_id,
            model_id=model_id,
            workflow_run_id=workflow_run_id,
            command=command,
            idempotency_key=idempotency_key,
        )
        with web_postgres_database.connect_owner() as connection:
            released_after_apply = connection.execute(
                """
                SELECT released
                  FROM security.release_tenant_lock(%s, %s, 'user', %s)
                """,
                (entra_tenant_id, entra_object_id, tenant_id),
            ).fetchone()
        assert released_after_apply == {"released": True}
        replayed = await apply_service.apply(
            principal,
            tenant_id=tenant_id,
            model_id=model_id,
            workflow_run_id=workflow_run_id,
            command=command,
            idempotency_key=idempotency_key,
        )
        with pytest.raises(InvalidRequestError):
            await apply_service.apply(
                principal,
                tenant_id=tenant_id,
                model_id=model_id,
                workflow_run_id=workflow_run_id,
                command=command,
                idempotency_key=uuid4(),
            )
    finally:
        await database.close()

    with web_postgres_database.connect_owner() as connection:
        model = connection.execute(
            "SELECT model_revision FROM model.model WHERE model_id = %s",
            (model_id,),
        ).fetchone()
        change_set = connection.execute(
            """
            SELECT model_change_set_status, applied_time
              FROM mcp.model_change_set
             WHERE workflow_run_id = %s
            """,
            (workflow_run_id,),
        ).fetchone()
        objects = connection.execute(
            """
            SELECT workflow_run_id
              FROM workflow.conceptual_object
             WHERE model_id = %s
             ORDER BY conceptual_object_name
            """,
            (model_id,),
        ).fetchall()
        supports = connection.execute(
            """
            SELECT workflow_run_id, supported_artifact_type, support_source_type
              FROM workflow.conceptual_support
             WHERE model_id = %s
             ORDER BY conceptual_support_id
            """,
            (model_id,),
        ).fetchall()
        applied_events = connection.execute(
            """
            SELECT correlation_id
              FROM mcp.model_change_set_event
             WHERE model_change_set_id = %s
               AND event_type = 'applied'
             ORDER BY event_sequence
            """,
            (draft.model_change_set_id,),
        ).fetchall()

    assert applied.replayed is False
    assert applied.workflow_run_id == workflow_run_id
    assert applied.model_change_set_id == draft.model_change_set_id
    assert applied.action_count == 2
    assert applied.model_revision == 2
    assert replayed == applied.model_copy(update={"replayed": True})
    assert model == {"model_revision": 2}
    assert change_set is not None
    assert change_set["model_change_set_status"] == "applied"
    assert change_set["applied_time"] == applied.applied_at
    assert objects == [{"workflow_run_id": workflow_run_id}]
    assert supports == [
        {
            "workflow_run_id": workflow_run_id,
            "supported_artifact_type": "conceptual_object",
            "support_source_type": "object",
        }
    ]
    assert applied_events == [{"correlation_id": idempotency_key}]


@pytest.mark.asyncio
async def test_completed_logical_draft_applies_once_with_run_provenance(
    web_postgres_database: DisposablePostgresFixture,
) -> None:
    (
        model_id,
        tenant_id,
        _attribute_id,
        entra_tenant_id,
        entra_object_id,
        _profile,
    ) = _seed_profile_model(web_postgres_database)
    with web_postgres_database.connect_owner() as connection:
        acquired = connection.execute(
            """
            SELECT acquired
              FROM security.acquire_tenant_lock(
                  %s, %s, 'user', %s, 60, 'Logical execution and apply test'
              )
            """,
            (entra_tenant_id, entra_object_id, tenant_id),
        ).fetchone()
    assert acquired == {"acquired": True}
    workflow_run_id = _create_queued_logical_run_with_prompt(
        web_postgres_database,
        model_id=model_id,
        tenant_id=tenant_id,
        entra_tenant_id=entra_tenant_id,
        entra_object_id=entra_object_id,
    )

    principal = RequestPrincipal(
        actor_kind=ActorKind.HUMAN,
        entra_tenant_id=entra_tenant_id,
        entra_object_id=entra_object_id,
    )
    database = WebPostgresDatabase(
        dsn=web_postgres_database.web_runtime_dsn(),
        pool_min=1,
        pool_max=1,
        pool_timeout_seconds=5,
    )
    authorizer = AuthorizationService()
    lifecycle = DatabaseAgentWorkflowLifecycle(database=database)
    workflow = LogicalWorkflow(
        lifecycle=lifecycle,
        executor=DatabaseLogicalExecutor(
            database=database,
            authorizer=authorizer,
            agent_executor=LocalFakeAgentAdapter(sdk_code="openai_agents_sdk"),
            handoff=WorkflowChangeSetHandoff(
                database=database,
                authorizer=authorizer,
            ),
            no_op=DatabaseAuthoringNoOpService(database=database),
            lifecycle=lifecycle,
        ),
    )
    apply_service = DatabaseWorkflowDraftApplyService(
        database=database,
        authorizer=authorizer,
    )
    idempotency_key = uuid4()

    await database.open()
    try:
        started = await workflow.start(
            principal,
            tenant_id=tenant_id,
            model_id=model_id,
            workflow_run_id=workflow_run_id,
            expected_execution_mode="one_shot",
            expected_model_revision=1,
        )
        claim = await DatabaseWorkflowClaimRepository(database=database).claim_next(
            lease_duration_seconds=30
        )
        assert claim is not None
        assert (
            claim.workflow_run_id,
            claim.tenant_id,
            claim.model_id,
            claim.model_revision,
            claim.model_workflow,
            claim.workflow_execution_mode,
        ) == (workflow_run_id, tenant_id, model_id, 1, "logical", "one_shot")
        draft = await workflow.execute_started(
            principal,
            tenant_id=tenant_id,
            model_id=model_id,
            workflow_run_id=workflow_run_id,
            expected_model_revision=1,
            workflow_run_claim_token=claim.workflow_run_claim_token,
        )
        assert isinstance(draft, WorkflowChangeSetHandoffResult)
        command = ApplyWorkflowDraftRequest(
            expected_model_revision=1,
            expected_draft_revision=draft.draft_revision,
            expected_candidate_digest=draft.candidate_digest,
        )
        applied = await apply_service.apply(
            principal,
            tenant_id=tenant_id,
            model_id=model_id,
            workflow_run_id=workflow_run_id,
            command=command,
            idempotency_key=idempotency_key,
        )
        replayed = await apply_service.apply(
            principal,
            tenant_id=tenant_id,
            model_id=model_id,
            workflow_run_id=workflow_run_id,
            command=command,
            idempotency_key=idempotency_key,
        )
    finally:
        await database.close()

    with web_postgres_database.connect_owner() as connection:
        model = connection.execute(
            "SELECT model_revision FROM model.model WHERE model_id = %s",
            (model_id,),
        ).fetchone()
        change_set = connection.execute(
            """
            SELECT model_change_set_status, logical_document
              FROM mcp.model_change_set
             WHERE workflow_run_id = %s
            """,
            (workflow_run_id,),
        ).fetchone()
        materialized = connection.execute(
            """
            SELECT (
                       SELECT count(*)
                         FROM workflow.logical_entity
                        WHERE model_id = %s AND workflow_run_id = %s
                   ) AS entity_count,
                   (
                       SELECT count(*)
                         FROM workflow.logical_entity_source_mapping
                        WHERE model_id = %s AND workflow_run_id = %s
                   ) AS entity_source_count,
                   (
                       SELECT count(*)
                         FROM workflow.logical_attribute
                        WHERE model_id = %s AND workflow_run_id = %s
                   ) AS attribute_count,
                   (
                       SELECT count(*)
                         FROM workflow.logical_attribute_source_mapping
                        WHERE model_id = %s AND workflow_run_id = %s
                   ) AS attribute_source_count
            """,
            (
                model_id,
                workflow_run_id,
                model_id,
                workflow_run_id,
                model_id,
                workflow_run_id,
                model_id,
                workflow_run_id,
            ),
        ).fetchone()

    assert started.changed is True
    assert started.workflow_run_state == "running"
    assert draft.replayed is False
    assert draft.workflow_run_id == workflow_run_id
    assert draft.staged_record_count == 2
    assert applied.replayed is False
    assert applied.action_count == 4
    assert applied.model_revision == 2
    assert replayed == applied.model_copy(update={"replayed": True})
    assert model == {"model_revision": 2}
    assert change_set is not None
    assert change_set["model_change_set_status"] == "applied"
    logical_document_value = change_set["logical_document"]
    assert isinstance(logical_document_value, dict)
    logical_document = cast(dict[str, object], logical_document_value)
    logical_entities_value = logical_document.get("logical_entity")
    logical_attributes_value = logical_document.get("logical_attribute")
    assert isinstance(logical_entities_value, list)
    assert isinstance(logical_attributes_value, list)
    logical_entities = cast(list[object], logical_entities_value)
    logical_attributes = cast(list[object], logical_attributes_value)
    assert len(logical_entities) == 1
    assert len(logical_attributes) == 1
    assert materialized == {
        "entity_count": 1,
        "entity_source_count": 1,
        "attribute_count": 1,
        "attribute_source_count": 1,
    }


@pytest.mark.asyncio
async def test_completed_dimensional_draft_applies_once_with_run_provenance(
    web_postgres_database: DisposablePostgresFixture,
) -> None:
    (
        model_id,
        tenant_id,
        _attribute_id,
        entra_tenant_id,
        entra_object_id,
        _profile,
    ) = _seed_profile_model(web_postgres_database)
    silver_object_id = _make_scope_object_dimensional_eligible(
        web_postgres_database,
        model_id=model_id,
    )
    with web_postgres_database.connect_owner() as connection:
        acquired = connection.execute(
            """
            SELECT acquired
              FROM security.acquire_tenant_lock(
                  %s, %s, 'user', %s, 60, 'Dimensional execution and apply test'
              )
            """,
            (entra_tenant_id, entra_object_id, tenant_id),
        ).fetchone()
    assert acquired == {"acquired": True}
    workflow_run_id = _create_queued_dimensional_run_with_prompt(
        web_postgres_database,
        model_id=model_id,
        tenant_id=tenant_id,
        entra_tenant_id=entra_tenant_id,
        entra_object_id=entra_object_id,
        selected_object_id=silver_object_id,
    )

    principal = RequestPrincipal(
        actor_kind=ActorKind.HUMAN,
        entra_tenant_id=entra_tenant_id,
        entra_object_id=entra_object_id,
    )
    database = WebPostgresDatabase(
        dsn=web_postgres_database.web_runtime_dsn(),
        pool_min=1,
        pool_max=1,
        pool_timeout_seconds=5,
    )
    authorizer = AuthorizationService()
    lifecycle = DatabaseAgentWorkflowLifecycle(database=database)
    workflow = DimensionalWorkflow(
        lifecycle=lifecycle,
        executor=DatabaseDimensionalExecutor(
            database=database,
            authorizer=authorizer,
            agent_executor=LocalFakeAgentAdapter(sdk_code="openai_agents_sdk"),
            handoff=WorkflowChangeSetHandoff(
                database=database,
                authorizer=authorizer,
            ),
            no_op=DatabaseAuthoringNoOpService(database=database),
            lifecycle=lifecycle,
        ),
    )
    apply_service = DatabaseWorkflowDraftApplyService(
        database=database,
        authorizer=authorizer,
    )
    idempotency_key = uuid4()

    await database.open()
    try:
        started = await workflow.start(
            principal,
            tenant_id=tenant_id,
            model_id=model_id,
            workflow_run_id=workflow_run_id,
            expected_execution_mode="one_shot",
            expected_model_revision=1,
        )
        claim = await DatabaseWorkflowClaimRepository(database=database).claim_next(
            lease_duration_seconds=300
        )
        assert claim is not None
        assert (
            claim.workflow_run_id,
            claim.tenant_id,
            claim.model_id,
            claim.model_revision,
            claim.model_workflow,
            claim.workflow_execution_mode,
        ) == (workflow_run_id, tenant_id, model_id, 1, "dimensional", "one_shot")
        draft = await workflow.execute_started(
            principal,
            tenant_id=tenant_id,
            model_id=model_id,
            workflow_run_id=workflow_run_id,
            expected_model_revision=1,
            workflow_run_claim_token=claim.workflow_run_claim_token,
        )
        assert isinstance(draft, WorkflowChangeSetHandoffResult)
        command = ApplyWorkflowDraftRequest(
            expected_model_revision=1,
            expected_draft_revision=draft.draft_revision,
            expected_candidate_digest=draft.candidate_digest,
        )
        applied = await apply_service.apply(
            principal,
            tenant_id=tenant_id,
            model_id=model_id,
            workflow_run_id=workflow_run_id,
            command=command,
            idempotency_key=idempotency_key,
        )
        replayed = await apply_service.apply(
            principal,
            tenant_id=tenant_id,
            model_id=model_id,
            workflow_run_id=workflow_run_id,
            command=command,
            idempotency_key=idempotency_key,
        )
    finally:
        await database.close()

    with web_postgres_database.connect_owner() as connection:
        model = connection.execute(
            "SELECT model_revision FROM model.model WHERE model_id = %s",
            (model_id,),
        ).fetchone()
        change_set = connection.execute(
            """
            SELECT model_change_set_status, dimensional_document
              FROM mcp.model_change_set
             WHERE workflow_run_id = %s
            """,
            (workflow_run_id,),
        ).fetchone()
        materialized = connection.execute(
            """
            SELECT (
                       SELECT count(*)
                         FROM workflow.dimensional_entity
                        WHERE model_id = %s AND workflow_run_id = %s
                   ) AS entity_count,
                   (
                       SELECT count(*)
                         FROM workflow.dimensional_entity_source_mapping
                        WHERE model_id = %s AND workflow_run_id = %s
                   ) AS entity_source_count,
                   (
                       SELECT count(*)
                         FROM workflow.dimensional_attribute
                        WHERE model_id = %s AND workflow_run_id = %s
                   ) AS attribute_count,
                   (
                       SELECT count(*)
                         FROM workflow.dimensional_attribute_source_mapping
                        WHERE model_id = %s AND workflow_run_id = %s
                   ) AS attribute_source_count
            """,
            (
                model_id,
                workflow_run_id,
                model_id,
                workflow_run_id,
                model_id,
                workflow_run_id,
                model_id,
                workflow_run_id,
            ),
        ).fetchone()

    assert started.changed is True
    assert started.workflow_run_state == "running"
    assert draft.replayed is False
    assert draft.workflow_run_id == workflow_run_id
    assert draft.staged_record_count == 4
    assert applied.replayed is False
    assert applied.action_count == 6
    assert applied.model_revision == 2
    assert replayed == applied.model_copy(update={"replayed": True})
    assert model == {"model_revision": 2}
    assert change_set is not None
    assert change_set["model_change_set_status"] == "applied"
    dimensional_document_value = change_set["dimensional_document"]
    assert isinstance(dimensional_document_value, dict)
    dimensional_document = cast(dict[str, object], dimensional_document_value)
    dimensional_entities_value = dimensional_document.get("dimensional_entity")
    dimensional_attributes_value = dimensional_document.get("dimensional_attribute")
    assert isinstance(dimensional_entities_value, list)
    assert isinstance(dimensional_attributes_value, list)
    dimensional_entities = cast(list[object], dimensional_entities_value)
    dimensional_attributes = cast(list[object], dimensional_attributes_value)
    assert len(dimensional_entities) == 1
    assert len(dimensional_attributes) == 3
    assert materialized == {
        "entity_count": 1,
        "entity_source_count": 1,
        "attribute_count": 3,
        "attribute_source_count": 1,
    }


@pytest.mark.asyncio
async def test_completed_analysis_draft_applies_once_and_preserves_validation(
    web_postgres_database: DisposablePostgresFixture,
) -> None:
    (
        model_id,
        tenant_id,
        from_attribute_id,
        entra_tenant_id,
        entra_object_id,
        _profile,
    ) = _seed_profile_model(web_postgres_database)
    validation_policy_version = "1.0.0"
    validation_source_context_digest = "b" * 64
    validation_policy_digest = hashlib.sha256(
        json.dumps(
            {
                "version": validation_policy_version,
                "result": "supported",
                "kind": "reference",
            },
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()
    with web_postgres_database.connect_owner() as connection:
        seeded = connection.execute(
            """
            SELECT attribute.object_id,
                   identity.principal_id,
                   identity.entra_principal_identity_id
              FROM core.attribute AS attribute
              JOIN security.entra_principal_identity AS identity
                ON identity.entra_tenant_id = %s
               AND identity.entra_object_id = %s
             WHERE attribute.attribute_id = %s
            """,
            (entra_tenant_id, entra_object_id, from_attribute_id),
        ).fetchone()
        if seeded is None:
            raise AssertionError("expected seeded Analysis inputs")
        object_id = _required_id(seeded, "object_id")
        principal_id = _required_id(seeded, "principal_id")
        principal_identity_id = _required_id(
            seeded,
            "entra_principal_identity_id",
        )
        to_attribute_id = _required_id(
            connection.execute(
                """
                INSERT INTO core.attribute (
                    object_id,
                    attribute_name,
                    attribute_ordinal_position,
                    attribute_data_type,
                    attribute_nullability
                ) VALUES (%s, 'order_id', 2, 'bigint', FALSE)
                RETURNING attribute_id
                """,
                (object_id,),
            ).fetchone(),
            "attribute_id",
        )
        validation_workflow_run_id = _required_id(
            connection.execute(
                """
                INSERT INTO application.workflow_run (
                    tenant_id,
                    model_id,
                    model_revision,
                    model_workflow,
                    workflow_execution_mode,
                    actor_principal_id,
                    actor_entra_principal_identity_id,
                    selected_scope_digest,
                    selected_scope_count,
                    workflow_run_state,
                    correlation_id,
                    started_time,
                    completed_time
                ) VALUES (
                    %s, %s, 1, 'analysis', NULL, %s, %s, %s, 1,
                    'completed', %s, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP
                )
                RETURNING workflow_run_id
                """,
                (
                    tenant_id,
                    model_id,
                    principal_id,
                    principal_identity_id,
                    "a" * 64,
                    uuid4(),
                ),
            ).fetchone(),
            "workflow_run_id",
        )
        connection.execute(
            """
            INSERT INTO application.workflow_run_object_selection (
                workflow_run_id,
                model_id,
                object_id,
                selection_order
            ) VALUES (%s, %s, %s, 1)
            """,
            (validation_workflow_run_id, model_id, object_id),
        )
        connection.execute(
            """
            INSERT INTO workflow.analysis_result (
                model_id,
                agent_run_id,
                inference_workflow_run_id,
                validation_workflow_run_id,
                validation_source_context_digest,
                from_object_id,
                from_attribute_id,
                to_object_id,
                to_attribute_id,
                relationship_kind,
                relationship_confidence,
                relationship_basis,
                validation_policy_version,
                validation_policy_digest,
                validation_result,
                validation_source_non_null_count,
                validation_source_distinct_count,
                validation_target_non_null_count,
                validation_target_distinct_count,
                validation_source_missing_target_count,
                validation_unused_target_count,
                validation_duplicate_target_key_count,
                analysis_result_status,
                analysis_result_is_locked
            ) VALUES (
                %s, 'legacy-agent-run', NULL, %s, %s, %s, %s, %s, %s,
                'reference', 'high', 'Prior inference basis.',
                %s, %s, 'supported', 9, 5, 10, 10, 1, 2, 0,
                'needs_review', FALSE
            )
            """,
            (
                model_id,
                validation_workflow_run_id,
                validation_source_context_digest,
                object_id,
                from_attribute_id,
                object_id,
                to_attribute_id,
                validation_policy_version,
                validation_policy_digest,
            ),
        )
        acquired = connection.execute(
            """
            SELECT acquired
              FROM security.acquire_tenant_lock(
                  %s, %s, 'user', %s, 60, 'Analysis apply test'
              )
            """,
            (entra_tenant_id, entra_object_id, tenant_id),
        ).fetchone()
    assert acquired == {"acquired": True}

    workflow_run_id = _create_queued_analysis_run_with_prompt(
        web_postgres_database,
        model_id=model_id,
        tenant_id=tenant_id,
        entra_tenant_id=entra_tenant_id,
        entra_object_id=entra_object_id,
    )
    principal = RequestPrincipal(
        actor_kind=ActorKind.HUMAN,
        entra_tenant_id=entra_tenant_id,
        entra_object_id=entra_object_id,
    )
    database = WebPostgresDatabase(
        dsn=web_postgres_database.web_runtime_dsn(),
        pool_min=1,
        pool_max=1,
        pool_timeout_seconds=5,
    )
    authorizer = AuthorizationService()
    lifecycle = DatabaseAgentWorkflowLifecycle(database=database)
    workflow = AnalysisInferenceWorkflow(
        lifecycle=lifecycle,
        executor=DatabaseAnalysisInferenceExecutor(
            database=database,
            authorizer=authorizer,
            agent_executor=LocalFakeAgentAdapter(sdk_code="openai_agents_sdk"),
            handoff=WorkflowChangeSetHandoff(
                database=database,
                authorizer=authorizer,
            ),
            no_op=DatabaseAuthoringNoOpService(database=database),
            lifecycle=lifecycle,
        ),
    )
    apply_service = DatabaseWorkflowDraftApplyService(
        database=database,
        authorizer=authorizer,
    )
    idempotency_key = uuid4()

    await database.open()
    try:
        await workflow.start(
            principal,
            tenant_id=tenant_id,
            model_id=model_id,
            workflow_run_id=workflow_run_id,
            expected_execution_mode="one_shot",
            expected_model_revision=1,
        )
        claim = await DatabaseWorkflowClaimRepository(database=database).claim_next(
            lease_duration_seconds=300
        )
        assert claim is not None
        assert (
            claim.workflow_run_id,
            claim.tenant_id,
            claim.model_id,
            claim.model_revision,
            claim.model_workflow,
            claim.workflow_execution_mode,
        ) == (workflow_run_id, tenant_id, model_id, 1, "analysis", "one_shot")
        draft = await workflow.execute_started(
            principal,
            tenant_id=tenant_id,
            model_id=model_id,
            workflow_run_id=workflow_run_id,
            expected_model_revision=1,
            workflow_run_claim_token=claim.workflow_run_claim_token,
        )
        assert draft is not None
        with web_postgres_database.connect_owner() as connection:
            before_apply = connection.execute(
                """
                SELECT change_set.model_change_set_status,
                       target_model.model_revision,
                       result.agent_run_id,
                       result.inference_workflow_run_id,
                       result.relationship_confidence,
                       result.relationship_basis
                  FROM mcp.model_change_set AS change_set
                  JOIN model.model AS target_model
                    ON target_model.model_id = change_set.model_id
                  JOIN workflow.analysis_result AS result
                    ON result.model_id = change_set.model_id
                 WHERE change_set.workflow_run_id = %s
                """,
                (workflow_run_id,),
            ).fetchone()
        assert before_apply == {
            "model_change_set_status": "validated",
            "model_revision": 1,
            "agent_run_id": "legacy-agent-run",
            "inference_workflow_run_id": None,
            "relationship_confidence": "high",
            "relationship_basis": "Prior inference basis.",
        }

        command = ApplyWorkflowDraftRequest(
            expected_model_revision=1,
            expected_draft_revision=draft.draft_revision,
            expected_candidate_digest=draft.candidate_digest,
        )
        applied = await apply_service.apply(
            principal,
            tenant_id=tenant_id,
            model_id=model_id,
            workflow_run_id=workflow_run_id,
            command=command,
            idempotency_key=idempotency_key,
        )
        replayed = await apply_service.apply(
            principal,
            tenant_id=tenant_id,
            model_id=model_id,
            workflow_run_id=workflow_run_id,
            command=command,
            idempotency_key=idempotency_key,
        )
    finally:
        await database.close()

    with web_postgres_database.connect_owner() as connection:
        persisted = connection.execute(
            """
            SELECT result.agent_run_id,
                   result.inference_workflow_run_id,
                   result.validation_workflow_run_id,
                   result.validation_source_context_digest,
                   result.relationship_confidence,
                   result.relationship_basis,
                   result.validation_policy_version,
                   result.validation_policy_digest,
                   result.validation_result,
                   result.validation_source_non_null_count,
                   result.validation_source_distinct_count,
                   result.validation_target_non_null_count,
                   result.validation_target_distinct_count,
                   result.validation_source_missing_target_count,
                   result.validation_unused_target_count,
                   result.validation_duplicate_target_key_count,
                   target_model.model_revision,
                   change_set.model_change_set_status,
                   (
                       SELECT count(*)
                         FROM mcp.model_change_set_event AS event
                        WHERE event.model_change_set_id = change_set.model_change_set_id
                          AND event.event_type = 'applied'
                   ) AS applied_event_count
              FROM workflow.analysis_result AS result
              JOIN model.model AS target_model
                ON target_model.model_id = result.model_id
              JOIN mcp.model_change_set AS change_set
                ON change_set.model_id = result.model_id
               AND change_set.workflow_run_id = %s
             WHERE result.model_id = %s
               AND result.from_attribute_id = %s
               AND result.to_attribute_id = %s
               AND result.relationship_kind = 'reference'
            """,
            (
                workflow_run_id,
                model_id,
                from_attribute_id,
                to_attribute_id,
            ),
        ).fetchone()

    assert draft.staged_record_count == 1
    assert applied.replayed is False
    assert applied.workflow_run_id == workflow_run_id
    assert applied.model_change_set_id == draft.model_change_set_id
    assert applied.action_count == 1
    assert applied.model_revision == 2
    assert replayed == applied.model_copy(update={"replayed": True})
    assert persisted == {
        "agent_run_id": None,
        "inference_workflow_run_id": workflow_run_id,
        "validation_workflow_run_id": validation_workflow_run_id,
        "validation_source_context_digest": validation_source_context_digest,
        "relationship_confidence": "medium",
        "relationship_basis": ("Selected Attribute metadata supports this candidate."),
        "validation_policy_version": validation_policy_version,
        "validation_policy_digest": validation_policy_digest,
        "validation_result": "supported",
        "validation_source_non_null_count": 9,
        "validation_source_distinct_count": 5,
        "validation_target_non_null_count": 10,
        "validation_target_distinct_count": 10,
        "validation_source_missing_target_count": 1,
        "validation_unused_target_count": 2,
        "validation_duplicate_target_key_count": 0,
        "model_revision": 2,
        "model_change_set_status": "applied",
        "applied_event_count": 1,
    }
