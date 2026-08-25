from __future__ import annotations

from typing import TYPE_CHECKING
from uuid import uuid4

import pytest
from gds_etl_workbench.application.authorization import AuthorizationService
from gds_etl_workbench.domain.authorization import ActorKind, RequestPrincipal
from gds_etl_workbench.tools.change_sets.model import StageModelChange
from tests.mcp.database_test_support import require_row
from tests.mcp.test_database_mapping_workflow_run import (
    CREATE_MAPPING_RUN_SQL,
    MappingRunContext,
    create_mapping_run_parameters,
    seed_mapping_output_template,
    seed_mapping_run_context,
)

from gds_workbench_api.database import WebPostgresDatabase
from gds_workbench_api.features.workflows.authoring.change_set_apply import (
    ApplyWorkflowDraftRequest,
    DatabaseWorkflowDraftApplyService,
)
from gds_workbench_api.features.workflows.authoring.change_set_handoff import (
    WorkflowChangeSetHandoff,
)
from gds_workbench_api.features.workflows.execution.repository import (
    DatabaseWorkflowClaimRepository,
)

if TYPE_CHECKING:
    from tests.mcp.conftest import DisposablePostgres


_PROFILE_DIGEST = "b3b324170019b51d2b812c3735fa6215e463209ea39e4099b44c786b956da8fa"


def _package(
    context: MappingRunContext,
    *,
    source_object_id: int,
    target_attribute_id: int,
) -> dict[str, object]:
    return {
        "schema_version": "1.0",
        "package_ref": "customer_crm",
        "route": "logical_to_silver",
        "target_object_id": context.target_object_id,
        "source_system_id": context.source_system_id,
        "artifact_type": "sql_file",
        "artifact_generation_instructions": "Generate deterministic SQL.",
        "pydantic_profile": {
            "key": "mapping.standard",
            "version": "1.0.0",
            "schema_digest": _PROFILE_DIGEST,
        },
        "executable_sources": [
            {
                "object_id": source_object_id,
                "alias": "customer_source",
                "role": "Customer source",
                "batch_rule": None,
            }
        ],
        "non_executable_provenance": [],
        "runtime_parameters": [],
        "source_system_dependencies": [],
        "target_dependencies": [],
        "steps": [
            {
                "name": "load_customer",
                "depends_on": [],
                "inputs": ["customer_source"],
                "output": "customer_rows",
                "logic": "Load the governed Customer rows.",
            }
        ],
        "grain_and_deduplication": "One row per Customer.",
        "load": {
            "write_mode": "merge",
            "merge_keys": [target_attribute_id],
            "partition_basis": None,
            "concurrent_system_write_mode": "idempotent_merge",
            "concurrent_write_basis": "Customer key.",
        },
    }


def _seed_mapping_apply_inputs(
    database: DisposablePostgres,
    context: MappingRunContext,
) -> tuple[int, int, tuple[StageModelChange, ...]]:
    workflow = context.workflow
    with database.connect_owner() as connection:
        object_template_id, _ = seed_mapping_output_template(
            connection,
            context,
            target_type="mapping_object",
        )
        attribute_template_id, _ = seed_mapping_output_template(
            connection,
            context,
            target_type="mapping_attribute",
        )
        header = require_row(
            connection.execute(
                """
                SELECT mapping.mapping_object_id,
                       mapping.logical_entity_id,
                       target_tenant.tenant_code,
                       target_system.system_code,
                       target_connection.connection_code,
                       target_object.object_schema,
                       target_object.object_name,
                       modeled.logical_entity_name,
                       source_system.system_code AS source_system_code
                  FROM workflow.mapping_object AS mapping
                  JOIN core.object AS target_object
                    ON target_object.object_id = mapping.object_id
                  JOIN core.connection AS target_connection
                    ON target_connection.connection_id = target_object.connection_id
                  JOIN core.system AS target_system
                    ON target_system.system_id = target_connection.system_id
                  JOIN core.tenant AS target_tenant
                    ON target_tenant.tenant_id = target_connection.tenant_id
                  JOIN core.system AS source_system
                    ON source_system.system_id = mapping.source_system_id
                  JOIN workflow.logical_entity AS modeled
                    ON modeled.logical_entity_id = mapping.logical_entity_id
                 WHERE mapping.model_id = %s
                   AND mapping.object_id = %s
                   AND mapping.source_system_id = %s
                """,
                (
                    workflow.model_id,
                    context.target_object_id,
                    context.source_system_id,
                ),
            ).fetchone()
        )
        target_attribute_id = require_row(
            connection.execute(
                """
                INSERT INTO core.attribute (
                    object_id,
                    attribute_name,
                    attribute_ordinal_position,
                    attribute_data_type,
                    attribute_nullability
                ) VALUES (%s, 'customer_id', 1, 'bigint', FALSE)
                RETURNING attribute_id
                """,
                (context.target_object_id,),
            ).fetchone()
        )["attribute_id"]
        logical_attribute_name = f"Customer Id {uuid4().hex}"
        connection.execute(
            """
            INSERT INTO workflow.logical_attribute (
                model_id,
                logical_entity_id,
                logical_attribute_name,
                logical_attribute_definition,
                logical_attribute_data_type,
                logical_attribute_is_nullable,
                logical_attribute_is_primary_key,
                logical_attribute_is_natural_key,
                logical_attribute_is_surrogate_key,
                logical_attribute_ordinal_position,
                logical_attribute_is_audit_column
            ) VALUES (
                %s, %s, %s, 'Customer identifier.', 'bigint',
                FALSE, TRUE, FALSE, TRUE, 1, FALSE
            )
            """,
            (
                workflow.model_id,
                header["logical_entity_id"],
                logical_attribute_name,
            ),
        )

    object_record: dict[str, object] = {
        "tenant_code": header["tenant_code"],
        "system_code": header["system_code"],
        "connection_code": header["connection_code"],
        "object_schema": header["object_schema"],
        "object_name": header["object_name"],
        "source_system_code": header["source_system_code"],
        "modeled_entity_type": "logical_entity",
        "modeled_entity_name": header["logical_entity_name"],
        "object_dependency_order": 0,
        "artifact_type": "sql_file",
        "artifact_generation_instructions": "Generate deterministic SQL.",
        "mapping_profile_key": "mapping.standard",
        "mapping_profile_version": "1.0.0",
        "mapping_package_document": _package(
            context,
            source_object_id=workflow.selected_object_ids[0],
            target_attribute_id=target_attribute_id,
        ),
        "object_mapping_transformation_document": {
            "schema_version": "1.0",
            "transformation_kind": "direct",
            "logic": "Load Customer rows.",
        },
        "object_mapping_status": "active",
        "object_mapping_is_locked": False,
    }
    attribute_record: dict[str, object] = {
        "tenant_code": header["tenant_code"],
        "system_code": header["system_code"],
        "connection_code": header["connection_code"],
        "object_schema": header["object_schema"],
        "object_name": header["object_name"],
        "attribute_name": "customer_id",
        "source_system_code": header["source_system_code"],
        "modeled_entity_type": "logical_entity",
        "modeled_entity_name": header["logical_entity_name"],
        "modeled_attribute_name": logical_attribute_name,
        "attribute_mapping_transformation_document": {
            "schema_version": "1.0",
            "transformation_kind": "direct",
            "logic": "Map Customer ID.",
        },
        "attribute_mapping_status": "active",
        "attribute_mapping_is_locked": False,
    }
    dependency_record: dict[str, object] = {
        "modeled_entity_type": "logical_entity",
        "source_system_code": header["source_system_code"],
        "source_system_dependency_order": 0,
        "mapping_source_system_dependency_status": "active",
        "mapping_source_system_dependency_is_locked": False,
    }
    return (
        object_template_id,
        attribute_template_id,
        (
            StageModelChange(dataset="mapping_dependency", records=[dependency_record]),
            StageModelChange(dataset="mapping_object", records=[object_record]),
            StageModelChange(dataset="mapping_attribute", records=[attribute_record]),
        ),
    )


@pytest.mark.asyncio
async def test_completed_mapping_draft_applies_frozen_templates_and_replays(
    web_postgres_database: DisposablePostgres,
) -> None:
    context = seed_mapping_run_context(web_postgres_database)
    workflow = context.workflow
    object_template_id, attribute_template_id, changes = _seed_mapping_apply_inputs(
        web_postgres_database,
        context,
    )
    correlation_id = uuid4()
    with web_postgres_database.connect_owner() as connection:
        created = require_row(
            connection.execute(
                CREATE_MAPPING_RUN_SQL,
                create_mapping_run_parameters(
                    context,
                    correlation_id=correlation_id,
                    object_output_template_id=object_template_id,
                    attribute_output_template_id=attribute_template_id,
                ),
            ).fetchone()
        )
        workflow_run_id = created["workflow_run_id"]
        started = require_row(
            connection.execute(
                """
                SELECT *
                  FROM application.start_workflow_run(
                      %s, %s, 'user', %s, %s
                  )
                """,
                (
                    workflow.entra_tenant_id,
                    workflow.entra_object_id,
                    workflow_run_id,
                    workflow.model_revision,
                ),
            ).fetchone()
        )
    assert started["workflow_run_state"] == "running"

    principal = RequestPrincipal(
        actor_kind=ActorKind.HUMAN,
        entra_tenant_id=workflow.entra_tenant_id,
        entra_object_id=workflow.entra_object_id,
    )
    database = WebPostgresDatabase(
        dsn=web_postgres_database.web_runtime_dsn(),
        pool_min=1,
        pool_max=1,
        pool_timeout_seconds=5,
    )
    authorizer = AuthorizationService()
    handoff = WorkflowChangeSetHandoff(database=database, authorizer=authorizer)
    apply_service = DatabaseWorkflowDraftApplyService(
        database=database,
        authorizer=authorizer,
    )
    idempotency_key = uuid4()

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
        ) == (
            workflow_run_id,
            workflow.tenant_id,
            workflow.model_id,
            workflow.model_revision,
            "mapping",
            "one_shot",
        )
        draft = await handoff.handoff(
            principal,
            tenant_id=workflow.tenant_id,
            model_id=workflow.model_id,
            workflow_run_id=workflow_run_id,
            expected_workflow="mapping",
            expected_model_revision=workflow.model_revision,
            workflow_run_claim_token=claim.workflow_run_claim_token,
            changes=changes,
        )
        with web_postgres_database.connect_owner() as connection:
            connection.execute(
                """
                SELECT *
                  FROM application.complete_workflow_run(
                      %s, %s, 'user', %s, %s, %s
                  )
                """,
                (
                    workflow.entra_tenant_id,
                    workflow.entra_object_id,
                    workflow_run_id,
                    workflow.model_revision,
                    draft.staged_record_count,
                ),
            )
        command = ApplyWorkflowDraftRequest(
            expected_model_revision=workflow.model_revision,
            expected_draft_revision=draft.draft_revision,
            expected_candidate_digest=draft.candidate_digest,
        )
        applied = await apply_service.apply(
            principal,
            tenant_id=workflow.tenant_id,
            model_id=workflow.model_id,
            workflow_run_id=workflow_run_id,
            command=command,
            idempotency_key=idempotency_key,
        )
        replayed = await apply_service.apply(
            principal,
            tenant_id=workflow.tenant_id,
            model_id=workflow.model_id,
            workflow_run_id=workflow_run_id,
            command=command,
            idempotency_key=idempotency_key,
        )
    finally:
        await database.close()

    with web_postgres_database.connect_owner() as connection:
        materialized = require_row(
            connection.execute(
                """
                SELECT dependency.workflow_run_id AS dependency_run_id,
                       mapping.workflow_run_id AS object_run_id,
                       mapping.output_template_id AS object_template_id,
                       child.workflow_run_id AS attribute_run_id,
                       child.output_template_id AS attribute_template_id
                  FROM workflow.mapping_source_system_dependency AS dependency
                  JOIN workflow.mapping_object AS mapping
                    ON mapping.model_id = dependency.model_id
                   AND mapping.modeled_entity_type = dependency.modeled_entity_type
                   AND mapping.source_system_id = dependency.source_system_id
                  JOIN workflow.mapping_attribute AS child
                    ON child.mapping_object_id = mapping.mapping_object_id
                 WHERE mapping.model_id = %s
                   AND mapping.object_id = %s
                   AND mapping.source_system_id = %s
                """,
                (
                    workflow.model_id,
                    context.target_object_id,
                    context.source_system_id,
                ),
            ).fetchone()
        )

    assert applied.replayed is False
    assert applied.action_count == 3
    assert replayed.replayed is True
    assert replayed.action_count == 3
    assert materialized == {
        "dependency_run_id": workflow_run_id,
        "object_run_id": workflow_run_id,
        "object_template_id": object_template_id,
        "attribute_run_id": workflow_run_id,
        "attribute_template_id": attribute_template_id,
    }
