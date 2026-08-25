from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, cast
from uuid import uuid4

import pytest
from gds_etl_workbench.application.authorization import AuthorizationService
from gds_etl_workbench.domain.authorization import ActorKind, RequestPrincipal
from pydantic import JsonValue
from tests.mcp.database_test_support import require_row
from tests.mcp.test_database_mapping_workflow_run import (
    CREATE_MAPPING_RUN_SQL,
    MappingRunContext,
    create_mapping_run_parameters,
    seed_mapping_run_context,
)

from gds_workbench_api.database import WebPostgresDatabase
from gds_workbench_api.features.mapping.attribute_candidate import (
    build_mapping_attribute_batch_plans,
)
from gds_workbench_api.features.mapping.candidate import (
    MappingHeaderCandidateValidator,
)
from gds_workbench_api.features.mapping import (
    MappingPreparation,
    MappingReadinessService,
    PostgresMappingRunContextRepository,
    PostgresMappingRunPlanRepository,
)
from gds_workbench_api.features.mapping.profile_registry import (
    MappingProfileRegistration,
    load_mapping_profile_registry,
)
from gds_workbench_api.features.mapping.service import (
    DatabaseMappingExecutor,
    MappingWorkflow,
)
from gds_workbench_api.features.workflows.authoring.agent_execution import (
    AgentExecutionRequest,
    AgentExecutionResult,
)
from gds_workbench_api.features.workflows.authoring.change_set_handoff import (
    WorkflowChangeSetHandoff,
    WorkflowChangeSetHandoffResult,
)
from gds_workbench_api.features.workflows.authoring.lifecycle import (
    DatabaseAgentWorkflowLifecycle,
)
from gds_workbench_api.features.workflows.authoring.no_op import (
    DatabaseAuthoringNoOpService,
)
from gds_workbench_api.features.workflows.authoring.repair import (
    AgentCandidateValidationError,
)
from gds_workbench_api.features.workflows.execution.repository import (
    DatabaseWorkflowClaimRepository,
)

if TYPE_CHECKING:
    from tests.mcp.conftest import DisposablePostgres


class _ProfileResolver:
    def __init__(self, registration: MappingProfileRegistration) -> None:
        self._registration = registration

    def resolve(
        self,
        *,
        key: str,
        version: str,
        schema_digest: str,
    ) -> MappingProfileRegistration | None:
        registration = self._registration
        if (key, version, schema_digest) != (
            registration.key,
            registration.version,
            registration.schema_digest,
        ):
            return None
        return registration


class _CapturingPreparationService:
    def __init__(self, delegate: MappingReadinessService) -> None:
        self._delegate = delegate
        self.latest: MappingPreparation | None = None

    async def prepare(
        self,
        principal: RequestPrincipal,
        *,
        tenant_id: int,
        model_id: int,
        workflow_run_id: int,
        expected_model_revision: int,
    ) -> MappingPreparation:
        result = await self._delegate.prepare(
            principal,
            tenant_id=tenant_id,
            model_id=model_id,
            workflow_run_id=workflow_run_id,
            expected_model_revision=expected_model_revision,
        )
        self.latest = result
        return result


class _MappingAgent:
    def __init__(
        self,
        preparation: _CapturingPreparationService,
        *,
        invalid: bool = False,
    ) -> None:
        self._preparation = preparation
        self._invalid = invalid
        self.request_count = 0

    async def execute(self, request: AgentExecutionRequest) -> AgentExecutionResult:
        self.request_count += 1
        if self._invalid:
            candidate: JsonValue = {"schema_version": "1.0"}
        else:
            preparation = self._preparation.latest
            if preparation is None:
                raise AssertionError("Mapping preparation must precede agent execution")
            candidate = _complete_candidate(preparation)
        return AgentExecutionResult(
            candidate=candidate,
            turn_count=1,
            tool_call_count=0,
        )


def _required_int(row: Mapping[str, object], field: str) -> int:
    value = row.get(field)
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise AssertionError(f"expected positive database ID {field}")
    return value


def _seed_authorable_mapping(
    database: DisposablePostgres,
) -> tuple[MappingRunContext, int]:
    context = seed_mapping_run_context(database)
    workflow = context.workflow
    source_object_id = workflow.selected_object_ids[0]
    with database.connect_owner() as connection:
        connection.execute(
            """
            UPDATE application.workflow_stage
               SET workflow_stage_code = 'mapping_authoring'
             WHERE model_workflow = 'mapping'
               AND workflow_execution_mode = 'one_shot'
               AND workflow_stage_is_agentic
               AND is_active
            """
        )
        header = require_row(
            connection.execute(
                """
                SELECT mapping_object_id, logical_entity_id
                  FROM workflow.mapping_object
                 WHERE model_id = %s
                   AND object_id = %s
                   AND source_system_id = %s
                """,
                (
                    workflow.model_id,
                    context.target_object_id,
                    context.source_system_id,
                ),
            ).fetchone()
        )
        mapping_object_id = _required_int(header, "mapping_object_id")
        logical_entity_id = _required_int(header, "logical_entity_id")
        source_attribute_id = _required_int(
            require_row(
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
                    (source_object_id,),
                ).fetchone()
            ),
            "attribute_id",
        )
        _required_int(
            require_row(
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
            ),
            "attribute_id",
        )
        logical_attribute_id = _required_int(
            require_row(
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
                        logical_attribute_ordinal_position
                    ) VALUES (
                        %s, %s, 'Customer ID', 'Stable customer identifier.',
                        'bigint', FALSE, TRUE, 1
                    )
                    RETURNING logical_attribute_id
                    """,
                    (workflow.model_id, logical_entity_id),
                ).fetchone()
            ),
            "logical_attribute_id",
        )
        source_mapping_id = _required_int(
            require_row(
                connection.execute(
                    """
                    INSERT INTO workflow.logical_entity_source_mapping (
                        model_id,
                        logical_entity_id,
                        support_source_type,
                        source_object_id,
                        logical_entity_source_mapping_order,
                        logical_entity_source_mapping_rationale
                    ) VALUES (%s, %s, 'object', %s, 1, 'Authoritative source.')
                    RETURNING logical_entity_source_mapping_id
                    """,
                    (workflow.model_id, logical_entity_id, source_object_id),
                ).fetchone()
            ),
            "logical_entity_source_mapping_id",
        )
        connection.execute(
            """
            INSERT INTO workflow.logical_attribute_source_mapping (
                model_id,
                logical_entity_source_mapping_id,
                logical_entity_id,
                logical_attribute_id,
                support_source_type,
                source_object_id,
                source_attribute_id,
                logical_attribute_source_mapping_order,
                logical_attribute_source_mapping_rationale
            ) VALUES (%s, %s, %s, %s, 'attribute', %s, %s, 1, 'Direct source.')
            """,
            (
                workflow.model_id,
                source_mapping_id,
                logical_entity_id,
                logical_attribute_id,
                source_object_id,
                source_attribute_id,
            ),
        )

    return context, mapping_object_id


def _header_candidate(preparation: MappingPreparation) -> dict[str, object]:
    plan = preparation.plan
    context = preparation.context
    aliases = {
        source.object.object_id: f"source_{position}"
        for position, source in enumerate(context.sources, 1)
    }
    actionable_ids = sorted(
        item.mapping_object_id
        for item in preparation.readiness.headers
        if item.action in {"author", "extend"}
    )
    package: dict[str, object] = {
        "schema_version": "1.0",
        "package_ref": "customer_mapping",
        "route": plan.route,
        "target_object_id": plan.pair.target_object_id,
        "source_system_id": plan.pair.source_system_id,
        "artifact_type": plan.artifact_type,
        "artifact_generation_instructions": "Generate deterministic SQL.",
        "pydantic_profile": plan.profile.model_dump(mode="json"),
        "executable_sources": [
            {
                "object_id": object_id,
                "alias": alias,
                "role": "Authoritative source",
                "batch_rule": None,
            }
            for object_id, alias in sorted(aliases.items())
        ],
        "non_executable_provenance": [],
        "runtime_parameters": [],
        "source_system_dependencies": [
            {
                "predecessor_source_system_id": edge.predecessor_source_system_id,
                "reason": "Frozen source-System dependency.",
            }
            for edge in context.dependency_graph.edges
            if edge.successor_source_system_id == plan.pair.source_system_id
        ],
        "target_dependencies": [
            {
                "predecessor_target_object_id": edge.predecessor_target_object_id,
                "reason": "Frozen target dependency.",
            }
            for edge in context.target_dependency_graph.edges
            if edge.successor_target_object_id == plan.pair.target_object_id
        ],
        "steps": [
            {
                "name": "project_customer",
                "depends_on": [],
                "inputs": sorted(aliases.values()),
                "output": "customer_rows",
                "logic": "Project the governed customer source.",
            }
        ],
        "grain_and_deduplication": "One row per customer.",
        "load": {
            "write_mode": "append",
            "merge_keys": [],
            "partition_basis": None,
            "concurrent_system_write_mode": "serialized",
            "concurrent_write_basis": "One selected source System at a time.",
        },
    }
    header_by_id = {item.mapping_object_id: item for item in context.headers}
    return {
        "schema_version": "1.0",
        "package": package,
        "headers": [
            {
                "mapping_object_id": mapping_object_id,
                "transformation": {
                    "schema_version": "1.0",
                    "transformation_kind": "direct",
                    "source_aliases": sorted(
                        aliases[source.object.object_id]
                        for source in context.sources
                        if source.modeled_entity_id
                        == header_by_id[mapping_object_id].modeled_entity.entity_id
                    ),
                    "logic": "Use the governed source directly.",
                },
            }
            for mapping_object_id in actionable_ids
        ],
        "coverage": {
            "expected_mapping_object_ids": sorted(header_by_id),
            "returned_mapping_object_ids": actionable_ids,
        },
    }


def _complete_candidate(preparation: MappingPreparation) -> JsonValue:
    raw_header = cast(JsonValue, _header_candidate(preparation))
    header = MappingHeaderCandidateValidator(preparation=preparation).parse_validated(
        raw_header
    )
    plans = build_mapping_attribute_batch_plans(
        preparation=preparation,
        package=header.package,
    )
    headers = {item.mapping_object_id: item for item in preparation.context.headers}
    eligible_header = next(
        item
        for item in preparation.readiness.headers
        if item.action in {"author", "extend"}
    )
    modeled_attribute_id = (
        headers[eligible_header.mapping_object_id]
        .modeled_entity.attributes[0]
        .attribute_id
    )
    batches: list[JsonValue] = []
    for plan in plans:
        mappings = [
            {
                "mapping_object_id": eligible_header.mapping_object_id,
                "mapping_attribute_id": None,
                "local_ref": f"target_{target_id}",
                "modeled_entity_type": preparation.plan.modeled_entity_type,
                "logical_attribute_id": modeled_attribute_id,
                "dimensional_attribute_id": None,
                "target_attribute_id": target_id,
                "disposition": "create",
                "transformation": {
                    "schema_version": "1.0",
                    "transformation_kind": "direct",
                    "logic": "Map the governed source customer identifier.",
                },
            }
            for target_id in plan.expected_target_attribute_ids
        ]
        batches.append(
            cast(
                JsonValue,
                {
                    "schema_version": "1.0",
                    "package_ref": header.package.package_ref,
                    "target_object_id": plan.target_object_id,
                    "source_system_id": plan.source_system_id,
                    "chunk_index": plan.chunk_index,
                    "chunk_count": plan.chunk_count,
                    "package_digest": plan.package_digest,
                    "coverage_manifest_digest": plan.coverage_manifest_digest,
                    "attribute_mappings": mappings,
                    "target_attribute_dispositions": [
                        {
                            "target_attribute_id": target_id,
                            "disposition": "mapped",
                            "reason": None,
                        }
                        for target_id in plan.expected_target_attribute_ids
                    ],
                    "coverage": {
                        "expected_target_attribute_ids": list(
                            plan.expected_target_attribute_ids
                        ),
                        "returned_target_attribute_ids": list(
                            plan.expected_target_attribute_ids
                        ),
                        "expected_existing_mapping_attribute_ids": list(
                            plan.expected_existing_mapping_attribute_ids
                        ),
                        "returned_existing_mapping_attribute_ids": [],
                    },
                },
            )
        )
    return cast(
        JsonValue,
        {
            "schema_version": "1.0",
            "header": raw_header,
            "attribute_batches": batches,
        },
    )


def _create_workflow(
    database: WebPostgresDatabase,
    *,
    invalid_agent: bool,
) -> tuple[MappingWorkflow, _MappingAgent]:
    authorizer = AuthorizationService()
    lifecycle = DatabaseAgentWorkflowLifecycle(database=database)
    preparation = _CapturingPreparationService(
        MappingReadinessService(
            database=database,
            authorizer=authorizer,
            plan_repository=PostgresMappingRunPlanRepository(),
            context_repository=PostgresMappingRunContextRepository(),
            profile_resolver=_ProfileResolver(load_mapping_profile_registry()),
        )
    )
    agent = _MappingAgent(preparation, invalid=invalid_agent)
    return (
        MappingWorkflow(
            lifecycle=lifecycle,
            executor=DatabaseMappingExecutor(
                preparation_service=preparation,
                agent_executor=agent,
                handoff=WorkflowChangeSetHandoff(
                    database=database,
                    authorizer=authorizer,
                ),
                no_op=DatabaseAuthoringNoOpService(database=database),
                lifecycle=lifecycle,
            ),
        ),
        agent,
    )


def _create_queued_run(
    database: DisposablePostgres,
    context: MappingRunContext,
) -> int:
    with database.connect_owner() as connection:
        row = require_row(
            connection.execute(
                CREATE_MAPPING_RUN_SQL,
                create_mapping_run_parameters(context, correlation_id=uuid4()),
            ).fetchone()
        )
    return _required_int(row, "workflow_run_id")


@pytest.mark.asyncio
async def test_mapping_executor_commits_one_validated_unapplied_draft(
    web_postgres_database: DisposablePostgres,
) -> None:
    context, mapping_object_id = _seed_authorable_mapping(web_postgres_database)
    workflow_run_id = _create_queued_run(web_postgres_database, context)
    workflow_context = context.workflow
    principal = RequestPrincipal(
        actor_kind=ActorKind.HUMAN,
        entra_tenant_id=workflow_context.entra_tenant_id,
        entra_object_id=workflow_context.entra_object_id,
    )
    database = WebPostgresDatabase(
        dsn=web_postgres_database.web_runtime_dsn(),
        pool_min=1,
        pool_max=1,
        pool_timeout_seconds=5,
    )
    workflow, agent = _create_workflow(database, invalid_agent=False)

    await database.open()
    try:
        started = await workflow.start(
            principal,
            tenant_id=workflow_context.tenant_id,
            model_id=workflow_context.model_id,
            workflow_run_id=workflow_run_id,
            expected_execution_mode="one_shot",
            expected_model_revision=workflow_context.model_revision,
        )
        claim = await DatabaseWorkflowClaimRepository(database=database).claim_next(
            lease_duration_seconds=30
        )
        assert claim is not None
        assert claim.workflow_run_id == workflow_run_id
        result = await workflow.execute_started(
            principal,
            tenant_id=workflow_context.tenant_id,
            model_id=workflow_context.model_id,
            workflow_run_id=workflow_run_id,
            workflow_run_claim_token=claim.workflow_run_claim_token,
            expected_model_revision=workflow_context.model_revision,
        )
    finally:
        await database.close()

    with web_postgres_database.connect_owner() as connection:
        stored = require_row(
            connection.execute(
                """
                SELECT run.workflow_run_state,
                       target_model.model_revision,
                       change_set.model_change_set_status,
                       change_set.mapping_document,
                       (
                           SELECT count(*)
                             FROM mcp.model_change_set
                            WHERE workflow_run_id = run.workflow_run_id
                       ) AS change_set_count,
                       (
                           SELECT count(*)
                             FROM workflow.mapping_attribute
                            WHERE model_id = run.model_id
                       ) AS materialized_attribute_count
                  FROM application.workflow_run AS run
                  JOIN model.model AS target_model
                    ON target_model.model_id = run.model_id
                  JOIN mcp.model_change_set AS change_set
                    ON change_set.workflow_run_id = run.workflow_run_id
                 WHERE run.workflow_run_id = %s
                """,
                (workflow_run_id,),
            ).fetchone()
        )
        header = require_row(
            connection.execute(
                """
                SELECT mapping_package_document,
                       object_mapping_transformation_document
                  FROM workflow.mapping_object
                 WHERE mapping_object_id = %s
                """,
                (mapping_object_id,),
            ).fetchone()
        )
        events = connection.execute(
            """
            SELECT model_event_log_sequence AS sequence,
                   model_event_log_stage AS stage,
                   model_event_log_status AS status
              FROM model.model_event_log
             WHERE workflow_run_id = %s
             ORDER BY model_event_log_sequence
            """,
            (workflow_run_id,),
        ).fetchall()

    assert started.workflow_run_state == "running"
    assert isinstance(result, WorkflowChangeSetHandoffResult)
    assert result.staged_record_count == 2
    assert agent.request_count == 1
    assert stored["workflow_run_state"] == "completed"
    assert stored["model_revision"] == workflow_context.model_revision
    assert stored["model_change_set_status"] == "validated"
    assert stored["change_set_count"] == 1
    assert stored["materialized_attribute_count"] == 0
    raw_document = stored["mapping_document"]
    assert isinstance(raw_document, dict)
    document = cast(dict[str, object], raw_document)
    raw_mapping_objects = document.get("mapping_object")
    raw_mapping_attributes = document.get("mapping_attribute")
    assert isinstance(raw_mapping_objects, list)
    assert isinstance(raw_mapping_attributes, list)
    mapping_objects = cast(list[object], raw_mapping_objects)
    mapping_attributes = cast(list[object], raw_mapping_attributes)
    assert len(mapping_objects) == 1
    assert len(mapping_attributes) == 1
    raw_first_mapping_attribute = mapping_attributes[0]
    assert isinstance(raw_first_mapping_attribute, dict)
    first_mapping_attribute = cast(dict[str, object], raw_first_mapping_attribute)
    assert first_mapping_attribute["attribute_name"] == "customer_id"
    assert header == {
        "mapping_package_document": None,
        "object_mapping_transformation_document": None,
    }
    assert [(row["sequence"], row["stage"], row["status"]) for row in events] == [
        (1, "workflow_run", "started"),
        (2, "mapping.mapping_authoring", "running"),
        (3, "mapping.backend_validation", "warning"),
        (4, "workflow_run", "completed"),
    ]


@pytest.mark.asyncio
async def test_mapping_executor_failure_persists_no_partial_draft(
    web_postgres_database: DisposablePostgres,
) -> None:
    context, mapping_object_id = _seed_authorable_mapping(web_postgres_database)
    workflow_run_id = _create_queued_run(web_postgres_database, context)
    workflow_context = context.workflow
    principal = RequestPrincipal(
        actor_kind=ActorKind.HUMAN,
        entra_tenant_id=workflow_context.entra_tenant_id,
        entra_object_id=workflow_context.entra_object_id,
    )
    database = WebPostgresDatabase(
        dsn=web_postgres_database.web_runtime_dsn(),
        pool_min=1,
        pool_max=1,
        pool_timeout_seconds=5,
    )
    workflow, agent = _create_workflow(database, invalid_agent=True)

    await database.open()
    try:
        await workflow.start(
            principal,
            tenant_id=workflow_context.tenant_id,
            model_id=workflow_context.model_id,
            workflow_run_id=workflow_run_id,
            expected_execution_mode="one_shot",
            expected_model_revision=workflow_context.model_revision,
        )
        claim = await DatabaseWorkflowClaimRepository(database=database).claim_next(
            lease_duration_seconds=30
        )
        assert claim is not None
        assert claim.workflow_run_id == workflow_run_id
        with pytest.raises(AgentCandidateValidationError):
            await workflow.execute_started(
                principal,
                tenant_id=workflow_context.tenant_id,
                model_id=workflow_context.model_id,
                workflow_run_id=workflow_run_id,
                workflow_run_claim_token=claim.workflow_run_claim_token,
                expected_model_revision=workflow_context.model_revision,
            )
    finally:
        await database.close()

    with web_postgres_database.connect_owner() as connection:
        stored = require_row(
            connection.execute(
                """
                SELECT run.workflow_run_state,
                       run.failure_code,
                       target_model.model_revision,
                       (
                           SELECT count(*)
                             FROM mcp.model_change_set
                            WHERE workflow_run_id = run.workflow_run_id
                       ) AS change_set_count,
                       (
                           SELECT count(*)
                             FROM workflow.mapping_attribute
                            WHERE model_id = run.model_id
                       ) AS materialized_attribute_count
                  FROM application.workflow_run AS run
                  JOIN model.model AS target_model
                    ON target_model.model_id = run.model_id
                 WHERE run.workflow_run_id = %s
                """,
                (workflow_run_id,),
            ).fetchone()
        )
        header = require_row(
            connection.execute(
                """
                SELECT mapping_package_document,
                       object_mapping_transformation_document
                  FROM workflow.mapping_object
                 WHERE mapping_object_id = %s
                """,
                (mapping_object_id,),
            ).fetchone()
        )

    assert agent.request_count == 3
    assert stored == {
        "workflow_run_state": "failed",
        "failure_code": "agent_candidate_validation_failed",
        "model_revision": workflow_context.model_revision,
        "change_set_count": 0,
        "materialized_attribute_count": 0,
    }
    assert header == {
        "mapping_package_document": None,
        "object_mapping_transformation_document": None,
    }
