from __future__ import annotations

from collections.abc import AsyncGenerator
from contextlib import AbstractAsyncContextManager, asynccontextmanager
from typing import Any, LiteralString
from uuid import UUID

import pytest
from gds_etl_workbench.application.authorization import (
    ResolvedPrincipal,
    TenantAuthorization,
)
from gds_etl_workbench.domain.authorization import (
    ActorKind,
    RequestPrincipal,
    TenantRole,
    ToolPolicy,
)
from gds_etl_workbench.infrastructure.postgres import (
    ReadIsolation,
    ReadTransaction,
    WriteTransaction,
)
from pydantic import ValidationError
from pydantic.version import VERSION as PYDANTIC_VERSION

from gds_workbench_api.capabilities import AgentRunSelection
from gds_workbench_api.features.mapping import (
    MappingDependencyEdge,
    MappingDependencyGraph,
    MappingDependencyNode,
    MappingOutputTemplate,
    MappingPairIdentity,
    MappingProfileRegistration,
    MappingReadinessService,
    MappingRunContext,
    MappingRunPlan,
    MappingTargetDependencyEdge,
    MappingTargetDependencyGraph,
    MappingTargetDependencyNode,
    PostgresMappingRunContextRepository,
    PostgresMappingRunPlanRepository,
    assess_mapping_readiness,
)
from gds_workbench_api.features.workflows.authoring.plan import (
    AgentRunPlan,
    FrozenAgentStage,
)
from gds_workbench_api.prompt_rendering import PromptComponentTemplates


def _agent_plan() -> AgentRunPlan:
    return AgentRunPlan(
        workflow_run_id=1048,
        model_id=18,
        correlation_id=UUID("33333333-3333-3333-3333-333333333333"),
        model_revision=7,
        model_workflow="mapping",
        workflow_execution_mode="one_shot",
        modeled_entity_type="logical_entity",
        selected_scope_digest="a" * 64,
        selected_object_ids=(501,),
        selection=AgentRunSelection(
            sdk_code="langchain_create_agent",
            provider_code="microsoft_foundry",
            model_code="gpt-5.6",
            reasoning_effort_code="medium",
            max_turns=8,
            validation_retry_count=1,
        ),
        stages=(
            FrozenAgentStage(
                workflow_stage_id=31,
                stage_code="header_mapper",
                stage_order=10,
                prompt_template_version_id=81,
                prompt_template_digest="b" * 64,
                templates=PromptComponentTemplates(
                    system="Sensitive Mapping system prompt.",
                    instruction="Sensitive Mapping instruction prompt.",
                ),
                variables=(),
            ),
        ),
    )


def _plan(
    *,
    operation: str = "build",
    object_template: tuple[int, str] | None = None,
    attribute_template: tuple[int, str] | None = None,
) -> MappingRunPlan:
    return MappingRunPlan.model_validate(
        {
            "agent_plan": _agent_plan(),
            "actor_principal_id": 77,
            "pair": {"target_object_id": 501, "source_system_id": 31},
            "operation": operation,
            "coverage_mode": "selected_targets",
            "artifact_type": "sql_file",
            "route": "logical_to_silver",
            "profile": {
                "key": "mapping.standard",
                "version": "1.0.0",
                "schema_digest": "c" * 64,
            },
            "output_template_selections": {
                "mapping_object": (
                    None
                    if object_template is None
                    else {
                        "output_template_id": object_template[0],
                        "schema_digest": object_template[1],
                    }
                ),
                "mapping_attribute": (
                    None
                    if attribute_template is None
                    else {
                        "output_template_id": attribute_template[0],
                        "schema_digest": attribute_template[1],
                    }
                ),
            },
        }
    )


def _profile() -> MappingProfileRegistration:
    return MappingProfileRegistration(
        schema_version="1.0",
        key="mapping.standard",
        version="1.0.0",
        schema_digest="c" * 64,
        schema_bundle_version="1.0",
        json_schema_mode="validation",
        pydantic_version=PYDANTIC_VERSION,
        root_models=[
            "AttributeMapperBatchOutputV1",
            "GeneratorDocumentV1",
            "HeaderMapperOutputV1",
        ],
    )


def _context() -> MappingRunContext:
    return MappingRunContext.model_validate(
        {
            "workflow_run_id": 1048,
            "model_id": 18,
            "model_revision": 7,
            "correlation_id": "33333333-3333-3333-3333-333333333333",
            "pair": {"target_object_id": 501, "source_system_id": 31},
            "modeled_entity_type": "logical_entity",
            "route": "logical_to_silver",
            "output_template_selections": {
                "mapping_object": None,
                "mapping_attribute": None,
            },
            "source_system": {
                "system_id": 31,
                "system_code": "CRM",
                "system_name": "Customer Relationship Management",
                "system_description": None,
                "is_active": True,
            },
            "dependency": {
                "mapping_source_system_dependency_id": 71,
                "dependency_order": 0,
                "status": "active",
                "is_locked": True,
            },
            "dependency_graph": {
                "nodes": [
                    {
                        "mapping_source_system_dependency_id": 71,
                        "source_system_id": 31,
                        "dependency_order": 0,
                        "status": "active",
                        "is_locked": True,
                    }
                ],
                "edges": [],
                "malformed_reference_count": 0,
            },
            "target_dependency_graph": {
                "nodes": [
                    {
                        "target_object_id": 501,
                        "dependency_order": 0,
                        "status": "active",
                        "has_locked_headers": True,
                        "has_unlocked_headers": True,
                    }
                ],
                "edges": [],
                "malformed_reference_count": 0,
                "mixed_order_target_count": 0,
            },
            "output_templates": {
                "ids": [801, 802],
                "definitions": [
                    {
                        "output_template_id": 801,
                        "code": "standard_mapping_object",
                        "name": "Standard Mapping Object",
                        "description": "Registered header authoring shape.",
                        "target_type": "mapping_object",
                        "schema_digest": "d" * 64,
                        "schema_digest_is_valid": True,
                        "is_active": True,
                        "fields": [
                            {
                                "name": "transformation_kind",
                                "description": "Direct or derived transformation.",
                                "data_type": "string",
                                "array_item_type": None,
                                "example": "direct",
                                "is_required": True,
                                "order": 10,
                            }
                        ],
                    },
                    {
                        "output_template_id": 802,
                        "code": "standard_mapping_attribute",
                        "name": "Standard Mapping Attribute",
                        "description": "Registered Attribute authoring shape.",
                        "target_type": "mapping_attribute",
                        "schema_digest": "e" * 64,
                        "schema_digest_is_valid": True,
                        "is_active": True,
                        "fields": [
                            {
                                "name": "expression",
                                "description": "Attribute expression.",
                                "data_type": "string",
                                "array_item_type": None,
                                "example": None,
                                "is_required": False,
                                "order": 20,
                            }
                        ],
                    },
                ],
            },
            "target": {
                "object_id": 501,
                "tenant_id": 7,
                "tenant_code": "NWA",
                "tenant_catalog": "northwind",
                "tenant_is_active": True,
                "system_id": 41,
                "system_code": "GDS",
                "system_is_active": True,
                "connection_id": 61,
                "connection_code": "lakehouse",
                "connection_is_active": True,
                "is_global_data_store": True,
                "object_schema": "silver_crm",
                "object_name": "customer",
                "object_description": "Customer target.",
                "batch_attribute_name": None,
                "zone_code": "silver",
                "scope_is_locked": False,
                "scope_is_active": True,
                "is_locked": False,
                "is_active": True,
                "attributes": [
                    {
                        "attribute_id": 901,
                        "attribute_name": "CustomerID",
                        "attribute_data_type": "BIGINT",
                        "attribute_nullability": False,
                        "attribute_ordinal_position": 1,
                        "attribute_description": "Stable customer key.",
                        "is_active": True,
                    }
                ],
            },
            "sources": [
                {
                    "source_mapping_id": 301,
                    "modeled_entity_id": 201,
                    "role": "customer source",
                    "rationale": "Authoritative CRM feed.",
                    "mapping_order": 1,
                    "is_locked": False,
                    "object": {
                        "object_id": 401,
                        "tenant_id": 7,
                        "tenant_code": "NWA",
                        "tenant_catalog": "northwind",
                        "tenant_is_active": True,
                        "system_id": 31,
                        "system_code": "CRM",
                        "system_is_active": True,
                        "connection_id": 51,
                        "connection_code": "crm_bronze",
                        "connection_is_active": True,
                        "is_global_data_store": False,
                        "object_schema": "bronze_crm",
                        "object_name": "customer",
                        "object_description": None,
                        "batch_attribute_name": None,
                        "zone_code": "bronze",
                        "scope_is_locked": False,
                        "scope_is_active": True,
                        "is_locked": False,
                        "is_active": True,
                        "attributes": [
                            {
                                "attribute_id": 801,
                                "attribute_name": "customer_id",
                                "attribute_data_type": "BIGINT",
                                "attribute_nullability": False,
                                "attribute_ordinal_position": 1,
                                "attribute_description": None,
                                "is_active": True,
                            }
                        ],
                    },
                }
            ],
            "headers": [
                {
                    "mapping_object_id": 101,
                    "modeled_entity": {
                        "entity_id": 201,
                        "entity_name": "Customer",
                        "entity_definition": "A customer.",
                        "entity_kind": "core",
                        "grain": "One row per customer.",
                        "dependency_order": 0,
                        "status": "active",
                        "is_locked": False,
                        "attributes": [
                            {
                                "attribute_id": 701,
                                "attribute_name": "CustomerID",
                                "attribute_definition": "Stable customer key.",
                                "attribute_data_type": "BIGINT",
                                "is_nullable": False,
                                "ordinal_position": 1,
                                "is_audit_column": False,
                                "status": "active",
                                "is_locked": False,
                            }
                        ],
                    },
                    "object_dependency_order": 0,
                    "artifact_type": "sql_file",
                    "artifact_generation_instructions": "Generate idempotent SQL.",
                    "profile": {
                        "key": "mapping.standard",
                        "version": "1.0.0",
                        "schema_digest": "c" * 64,
                    },
                    "mapping_package_document": {"schema_version": "1.0"},
                    "mapping_package_digest": "f" * 64,
                    "transformation_document": {
                        "schema_version": "1.0",
                        "transformation_kind": "direct",
                    },
                    "status": "active",
                    "is_locked": True,
                    "agent_run_id": None,
                    "workflow_run_id": None,
                    "output_template_id": 801,
                    "attribute_mappings": [
                        {
                            "mapping_attribute_id": 601,
                            "modeled_attribute_id": 701,
                            "target_attribute_id": 901,
                            "transformation_document": {
                                "schema_version": "1.0",
                                "transformation_kind": "direct",
                            },
                            "status": "active",
                            "is_locked": True,
                            "agent_run_id": None,
                            "workflow_run_id": None,
                            "output_template_id": 802,
                        }
                    ],
                },
                {
                    "mapping_object_id": 102,
                    "modeled_entity": {
                        "entity_id": 202,
                        "entity_name": "CustomerStatus",
                        "entity_definition": "Customer status contribution.",
                        "entity_kind": "reference",
                        "grain": "One row per customer status.",
                        "dependency_order": 0,
                        "status": "active",
                        "is_locked": False,
                        "attributes": [],
                    },
                    "object_dependency_order": 0,
                    "artifact_type": None,
                    "artifact_generation_instructions": None,
                    "profile": None,
                    "mapping_package_document": None,
                    "mapping_package_digest": None,
                    "transformation_document": None,
                    "status": "active",
                    "is_locked": False,
                    "agent_run_id": None,
                    "workflow_run_id": None,
                    "output_template_id": 801,
                    "attribute_mappings": [],
                },
            ],
            "authoring": {
                "model_name": "Customer Model",
                "naming_instructions": "Use PascalCase names.",
                "audit_columns_template": {
                    "schema_version": "1.0",
                    "columns": [{"semantic_name": "created time"}],
                },
                "technical_columns_template": None,
            },
        },
        strict=False,
    )


def _context_for_plan(
    plan: MappingRunPlan,
    *,
    extra_definitions: tuple[MappingOutputTemplate, ...] = (),
) -> MappingRunContext:
    context = _context()
    selected_ids = {
        selection.output_template_id
        for selection in (
            plan.output_template_selections.mapping_object,
            plan.output_template_selections.mapping_attribute,
        )
        if selection is not None
    }
    payload = context.model_dump(mode="python")
    payload["output_template_selections"] = plan.output_template_selections.model_dump(
        mode="python"
    )
    payload["output_templates"] = {
        "ids": sorted(set(context.output_templates.ids) | selected_ids),
        "definitions": [
            item.model_dump(mode="python")
            for item in sorted(
                (*context.output_templates.definitions, *extra_definitions),
                key=lambda item: item.output_template_id,
            )
        ],
    }
    return MappingRunContext.model_validate(payload, strict=False)


def test_build_preserves_locked_complete_rows_and_authors_unlocked_headers() -> None:
    readiness = assess_mapping_readiness(
        plan=_plan(),
        context=_context(),
        registration=_profile(),
    )

    assert readiness.ready is True
    assert readiness.package_action == "author"
    assert [(item.mapping_object_id, item.action) for item in readiness.headers] == [
        (101, "preserve"),
        (102, "author"),
    ]
    assert readiness.headers[0].attribute_actions[0].action == "preserve"
    assert readiness.issues == ()
    assert "Sensitive Mapping" not in repr(_plan())


@pytest.mark.parametrize("operation", ("build", "extend"))
def test_complete_locked_no_change_package_is_preserveable(
    operation: str,
) -> None:
    context = _context()
    legacy_profile = context.headers[0].profile
    assert legacy_profile is not None
    locked_complete = context.headers[0].model_copy(
        update={
            "artifact_type": "python_file",
            "profile": legacy_profile.model_copy(
                update={
                    "key": "mapping.legacy",
                    "version": "0.9.0",
                    "schema_digest": "8" * 64,
                }
            ),
        }
    )
    context = context.model_copy(
        update={
            "headers": (locked_complete,),
            "target_dependency_graph": context.target_dependency_graph.model_copy(
                update={
                    "nodes": (
                        context.target_dependency_graph.nodes[0].model_copy(
                            update={"has_unlocked_headers": False}
                        ),
                    )
                }
            ),
        }
    )

    readiness = assess_mapping_readiness(
        plan=_plan(operation=operation),
        context=context,
        registration=_profile(),
    )

    assert readiness.ready is True
    assert readiness.package_action == "preserve"
    assert readiness.headers[0].action == "preserve"
    assert readiness.issues == ()


def test_build_blocks_only_locked_header_that_still_requires_authoring() -> None:
    context = _context()
    locked_incomplete = context.headers[1].model_copy(update={"is_locked": True})
    context = context.model_copy(
        update={
            "headers": (context.headers[0], locked_incomplete),
            "target_dependency_graph": context.target_dependency_graph.model_copy(
                update={
                    "nodes": (
                        context.target_dependency_graph.nodes[0].model_copy(
                            update={"has_unlocked_headers": False}
                        ),
                    )
                }
            ),
        }
    )

    readiness = assess_mapping_readiness(
        plan=_plan(),
        context=context,
        registration=_profile(),
    )

    assert readiness.ready is False
    assert readiness.package_action == "blocked"
    assert [(item.mapping_object_id, item.action) for item in readiness.headers] == [
        (101, "preserve"),
        (102, "blocked"),
    ]
    assert [issue.code for issue in readiness.issues] == [
        "header.locked_change_required"
    ]


def test_mapping_authoring_policy_documents_are_optional_context() -> None:
    context = _context().model_copy(
        update={
            "authoring": _context().authoring.model_copy(
                update={
                    "naming_instructions": None,
                    "audit_columns_template": None,
                    "technical_columns_template": None,
                }
            )
        }
    )

    readiness = assess_mapping_readiness(
        plan=_plan(),
        context=context,
        registration=_profile(),
    )

    assert readiness.ready is True
    assert readiness.issues == ()


class _Transaction:
    async def fetch_one(
        self,
        query: LiteralString,
        parameters: tuple[Any, ...] = (),
    ) -> dict[str, Any] | None:
        del query, parameters
        raise AssertionError("The fake repositories own this service test")

    async def fetch_all(
        self,
        query: LiteralString,
        parameters: tuple[Any, ...] = (),
    ) -> list[dict[str, Any]]:
        del query, parameters
        raise AssertionError("The fake repositories own this service test")


class _Database:
    def __init__(self) -> None:
        self.transaction = _Transaction()
        self.isolation: ReadIsolation | None = None

    @asynccontextmanager
    async def _write(
        self,
        isolation: ReadIsolation,
    ) -> AsyncGenerator[WriteTransaction]:
        self.isolation = isolation
        yield self.transaction

    def write_transaction(
        self,
        *,
        isolation: ReadIsolation = ReadIsolation.READ_COMMITTED,
    ) -> AbstractAsyncContextManager[WriteTransaction]:
        return self._write(isolation)


class _Authorizer:
    async def authorize_tenant(
        self,
        transaction: ReadTransaction,
        request_principal: RequestPrincipal,
        *,
        tenant_id: int,
        policy: ToolPolicy,
    ) -> TenantAuthorization:
        assert isinstance(transaction, _Transaction)
        assert request_principal == _principal()
        assert tenant_id == 7
        assert policy is ToolPolicy.TENANT_MODEL_WRITE
        return TenantAuthorization(
            principal=ResolvedPrincipal(
                principal_id=77,
                actor_kind=ActorKind.HUMAN,
                display_name="Mapping Architect",
                is_super_admin=False,
            ),
            effective_role=TenantRole.ARCHITECT,
            lock_expires_time=None,
        )


class _PlanRepository:
    async def load(
        self,
        transaction: ReadTransaction,
        *,
        actor_principal_id: int,
        tenant_id: int,
        model_id: int,
        workflow_run_id: int,
        expected_model_revision: int,
    ) -> MappingRunPlan:
        assert isinstance(transaction, _Transaction)
        assert (
            actor_principal_id,
            tenant_id,
            model_id,
            workflow_run_id,
            expected_model_revision,
        ) == (77, 7, 18, 1048, 7)
        return _plan()


class _ContextRepository:
    async def load(
        self,
        transaction: ReadTransaction,
        *,
        tenant_id: int,
        plan: MappingRunPlan,
    ) -> MappingRunContext:
        assert isinstance(transaction, _Transaction)
        assert tenant_id == 7
        assert plan == _plan()
        return _context()


class _ProfileResolver:
    def __init__(self) -> None:
        self.call: tuple[str, str, str] | None = None

    def resolve(
        self,
        *,
        key: str,
        version: str,
        schema_digest: str,
    ) -> MappingProfileRegistration | None:
        self.call = (key, version, schema_digest)
        return _profile()


def _principal() -> RequestPrincipal:
    return RequestPrincipal(
        actor_kind=ActorKind.HUMAN,
        entra_tenant_id=UUID("11111111-1111-1111-1111-111111111111"),
        entra_object_id=UUID("22222222-2222-2222-2222-222222222222"),
    )


@pytest.mark.asyncio
async def test_service_authorizes_and_revision_fences_the_exact_pair() -> None:
    database = _Database()
    resolver = _ProfileResolver()
    service = MappingReadinessService(
        database=database,
        authorizer=_Authorizer(),
        plan_repository=_PlanRepository(),
        context_repository=_ContextRepository(),
        profile_resolver=resolver,
    )

    prepared = await service.prepare(
        _principal(),
        tenant_id=7,
        model_id=18,
        workflow_run_id=1048,
        expected_model_revision=7,
    )

    assert database.isolation is ReadIsolation.REPEATABLE_READ
    assert prepared.plan.pair == MappingPairIdentity(
        target_object_id=501,
        source_system_id=31,
    )
    assert prepared.context.target.object_name == "customer"
    assert prepared.registration == _profile()
    assert prepared.readiness.ready is True
    assert resolver.call == ("mapping.standard", "1.0.0", "c" * 64)


class _AgentPlanRepository:
    async def load(
        self,
        transaction: ReadTransaction,
        *,
        tenant_id: int,
        model_id: int,
        workflow_run_id: int,
    ) -> AgentRunPlan:
        assert isinstance(transaction, _PlanTransaction)
        assert (tenant_id, model_id, workflow_run_id) == (7, 18, 1048)
        return _agent_plan()


class _PlanTransaction:
    def __init__(self, row: dict[str, Any]) -> None:
        self.row = row

    async def fetch_one(
        self,
        query: LiteralString,
        parameters: tuple[Any, ...] = (),
    ) -> dict[str, Any] | None:
        assert "workflow_run_mapping_target_selection" in query
        assert "run.actor_principal_id = %s" in query
        assert "target_model.tenant_id = %s" in query
        assert "target_model.model_revision = %s" in query
        assert "run.workflow_run_state = 'running'" in query
        assert parameters == (7, 18, 1048, 7, 77)
        return self.row

    async def fetch_all(
        self,
        query: LiteralString,
        parameters: tuple[Any, ...] = (),
    ) -> list[dict[str, Any]]:
        del query, parameters
        raise AssertionError("The injected common plan repository owns fetch_all")


@pytest.mark.asyncio
async def test_postgres_plan_loads_only_server_frozen_mapping_fields() -> None:
    transaction = _PlanTransaction(
        {
            "workflow_run_id": 1048,
            "model_id": 18,
            "correlation_id": UUID("33333333-3333-3333-3333-333333333333"),
            "actor_principal_id": 77,
            "model_revision": 7,
            "modeled_entity_type": "logical_entity",
            "mapping_operation": "build",
            "mapping_coverage_mode": "selected_targets",
            "mapping_artifact_type": "sql_file",
            "mapping_route": "logical_to_silver",
            "mapping_profile_key": "mapping.standard",
            "mapping_profile_version": "1.0.0",
            "mapping_profile_schema_digest": "c" * 64,
            "mapping_object_output_template_id": None,
            "mapping_object_output_template_schema_digest": None,
            "mapping_attribute_output_template_id": None,
            "mapping_attribute_output_template_schema_digest": None,
            "target_object_id": 501,
            "source_system_id": 31,
            "selection_order": 1,
        }
    )

    repository = PostgresMappingRunPlanRepository(
        agent_plan_repository=_AgentPlanRepository()
    )
    plan = await repository.load(
        transaction,
        actor_principal_id=77,
        tenant_id=7,
        model_id=18,
        workflow_run_id=1048,
        expected_model_revision=7,
    )

    assert plan.pair == MappingPairIdentity(
        target_object_id=501,
        source_system_id=31,
    )
    assert plan.operation == "build"
    assert plan.route == "logical_to_silver"
    assert plan.profile.schema_digest == "c" * 64
    assert plan.output_template_selections.mapping_object is None
    assert plan.output_template_selections.mapping_attribute is None

    transaction.row["mapping_object_output_template_id"] = 801
    transaction.row["mapping_object_output_template_schema_digest"] = "d" * 64
    selected = await repository.load(
        transaction,
        actor_principal_id=77,
        tenant_id=7,
        model_id=18,
        workflow_run_id=1048,
        expected_model_revision=7,
    )

    assert selected.output_template_selections.mapping_object is not None
    assert selected.output_template_selections.mapping_object.output_template_id == 801
    assert selected.output_template_selections.mapping_attribute is None


def test_readiness_blocks_a_missing_referenced_template_definition() -> None:
    context = _context()
    mismatched = context.headers[1].model_copy(update={"output_template_id": 999})
    context = context.model_copy(
        update={
            "headers": (context.headers[0], mismatched),
            "output_templates": context.output_templates.model_copy(
                update={"ids": (801, 802, 999)}
            ),
        }
    )

    readiness = assess_mapping_readiness(
        plan=_plan(),
        context=context,
        registration=_profile(),
    )

    assert readiness.ready is False
    assert readiness.package_action == "blocked"
    assert [issue.code for issue in readiness.issues] == ["template.header_missing"]


@pytest.mark.parametrize(
    ("object_template", "attribute_template"),
    (
        (None, None),
        ((801, "d" * 64), None),
        (None, (802, "e" * 64)),
        ((801, "d" * 64), (802, "e" * 64)),
    ),
)
def test_run_template_selections_are_independently_nullable(
    object_template: tuple[int, str] | None,
    attribute_template: tuple[int, str] | None,
) -> None:
    plan = _plan(
        object_template=object_template,
        attribute_template=attribute_template,
    )

    readiness = assess_mapping_readiness(
        plan=plan,
        context=_context_for_plan(plan),
        registration=_profile(),
    )

    assert readiness.ready is True
    assert readiness.issues == ()


def test_selected_output_template_must_resolve_exact_active_definition() -> None:
    missing_plan = _plan(object_template=(899, "f" * 64))
    drift_plan = _plan(object_template=(801, "0" * 64))
    type_plan = _plan(object_template=(802, "e" * 64))
    inactive_plan = _plan(object_template=(801, "d" * 64))
    inactive_context = _context_for_plan(inactive_plan)
    inactive_context = inactive_context.model_copy(
        update={
            "output_templates": inactive_context.output_templates.model_copy(
                update={
                    "definitions": (
                        inactive_context.output_templates.definitions[0].model_copy(
                            update={"is_active": False}
                        ),
                        inactive_context.output_templates.definitions[1],
                    )
                }
            )
        }
    )

    results = (
        assess_mapping_readiness(
            plan=missing_plan,
            context=_context_for_plan(missing_plan),
            registration=_profile(),
        ),
        assess_mapping_readiness(
            plan=drift_plan,
            context=_context_for_plan(drift_plan),
            registration=_profile(),
        ),
        assess_mapping_readiness(
            plan=type_plan,
            context=_context_for_plan(type_plan),
            registration=_profile(),
        ),
        assess_mapping_readiness(
            plan=inactive_plan,
            context=inactive_context,
            registration=_profile(),
        ),
    )

    assert [[issue.code for issue in result.issues] for result in results] == [
        ["template.selected_object_missing"],
        ["template.selected_object_digest_drift"],
        ["template.selected_object_type_mismatch"],
        ["template.selected_object_inactive"],
    ]


def test_row_template_selections_are_independent_and_may_differ() -> None:
    context = _context()
    alternate_header_template = context.output_templates.definitions[0].model_copy(
        update={
            "output_template_id": 803,
            "code": "alternate_mapping_object",
            "schema_digest": "9" * 64,
        }
    )
    first_header = context.headers[0].model_copy(update={"output_template_id": None})
    second_header = context.headers[1].model_copy(update={"output_template_id": 803})
    context = context.model_copy(
        update={
            "output_templates": context.output_templates.model_copy(
                update={
                    "ids": (802, 803),
                    "definitions": (
                        context.output_templates.definitions[1],
                        alternate_header_template,
                    ),
                }
            ),
            "headers": (first_header, second_header),
        }
    )

    readiness = assess_mapping_readiness(
        plan=_plan(),
        context=context,
        registration=_profile(),
    )

    assert readiness.ready is True
    assert readiness.issues == ()


def test_historical_inactive_output_template_remains_preserveable() -> None:
    context = _context()
    context = context.model_copy(
        update={
            "output_templates": context.output_templates.model_copy(
                update={
                    "definitions": (
                        context.output_templates.definitions[0].model_copy(
                            update={"is_active": False}
                        ),
                        context.output_templates.definitions[1],
                    )
                }
            )
        }
    )

    readiness = assess_mapping_readiness(
        plan=_plan(),
        context=context,
        registration=_profile(),
    )

    assert readiness.ready is True
    assert readiness.headers[0].action == "preserve"


def test_output_template_digest_corruption_blocks_referenced_rows() -> None:
    context = _context()
    context = context.model_copy(
        update={
            "output_templates": context.output_templates.model_copy(
                update={
                    "definitions": (
                        context.output_templates.definitions[0].model_copy(
                            update={"schema_digest_is_valid": False}
                        ),
                        context.output_templates.definitions[1],
                    )
                }
            )
        }
    )

    readiness = assess_mapping_readiness(
        plan=_plan(),
        context=context,
        registration=_profile(),
    )

    assert readiness.ready is False
    assert [issue.code for issue in readiness.issues] == [
        "template.header_digest_drift",
        "template.header_digest_drift",
    ]


def test_output_template_fields_allow_sorted_noncontiguous_orders() -> None:
    template = _context().output_templates.definitions[0]
    second_field = template.fields[0].model_copy(update={"name": "logic", "order": 20})

    payload = template.model_dump(mode="python")
    payload["fields"] = (
        template.fields[0].model_dump(mode="python"),
        second_field.model_dump(mode="python"),
    )
    validated = MappingOutputTemplate.model_validate(
        payload,
        strict=False,
    )

    assert [field.order for field in validated.fields] == [10, 20]


def test_extend_preserves_locked_complete_rows_and_extends_unlocked_rows() -> None:
    readiness = assess_mapping_readiness(
        plan=_plan(operation="extend"),
        context=_context(),
        registration=_profile(),
    )

    assert readiness.ready is True
    assert readiness.package_action == "extend"
    assert [(item.mapping_object_id, item.action) for item in readiness.headers] == [
        (101, "preserve"),
        (102, "extend"),
    ]
    assert readiness.headers[0].attribute_actions[0].action == "preserve"


class _ContextTransaction:
    def __init__(self, expected: MappingRunContext) -> None:
        self.expected = expected

    async def fetch_one(
        self,
        query: LiteralString,
        parameters: tuple[Any, ...] = (),
    ) -> dict[str, Any] | None:
        if "application.workflow_run AS run" in query:
            object_selection = self.expected.output_template_selections.mapping_object
            attribute_selection = (
                self.expected.output_template_selections.mapping_attribute
            )
            assert "workflow_run_mapping_target_selection" in query
            assert "run.actor_principal_id = %s" in query
            assert "target_model.tenant_id = %s" in query
            assert "target_model.model_revision = %s" in query
            assert "run.correlation_id = %s" in query
            assert "workflow.mapping_source_system_dependency" in query
            assert parameters == (
                7,
                18,
                1048,
                7,
                77,
                UUID("33333333-3333-3333-3333-333333333333"),
                501,
                31,
                "logical_entity",
                "logical_to_silver",
                "build",
                "sql_file",
                "mapping.standard",
                "1.0.0",
                "c" * 64,
                object_selection.output_template_id
                if object_selection is not None
                else None,
                object_selection.schema_digest
                if object_selection is not None
                else None,
                attribute_selection.output_template_id
                if attribute_selection is not None
                else None,
                attribute_selection.schema_digest
                if attribute_selection is not None
                else None,
            )
            return {
                "workflow_run_id": self.expected.workflow_run_id,
                "model_id": self.expected.model_id,
                "model_revision": self.expected.model_revision,
                "correlation_id": self.expected.correlation_id,
                "actor_principal_id": 77,
                "target_object_id": self.expected.pair.target_object_id,
                "source_system_id": self.expected.pair.source_system_id,
                "modeled_entity_type": self.expected.modeled_entity_type,
                "mapping_route": self.expected.route,
                "mapping_operation": "build",
                "mapping_artifact_type": "sql_file",
                "mapping_profile_key": "mapping.standard",
                "mapping_profile_version": "1.0.0",
                "mapping_profile_schema_digest": "c" * 64,
                "mapping_object_output_template_id": (
                    object_selection.output_template_id
                    if object_selection is not None
                    else None
                ),
                "mapping_object_output_template_schema_digest": (
                    object_selection.schema_digest
                    if object_selection is not None
                    else None
                ),
                "mapping_attribute_output_template_id": (
                    attribute_selection.output_template_id
                    if attribute_selection is not None
                    else None
                ),
                "mapping_attribute_output_template_schema_digest": (
                    attribute_selection.schema_digest
                    if attribute_selection is not None
                    else None
                ),
                "source_system": self.expected.source_system.model_dump(mode="python"),
                "dependency": self.expected.dependency.model_dump(mode="python"),
                "authoring": self.expected.authoring.model_dump(mode="python"),
            }
        if "dependency_node AS MATERIALIZED" in query:
            assert "mapping_package_document" in query
            assert "source_system_dependencies" in query
            assert "LIMIT 1001" in query
            assert "LIMIT 10001" in query
            assert parameters == (
                7,
                18,
                7,
                "logical_entity",
                "logical_entity",
            )
            return {
                "dependency_graph": self.expected.dependency_graph.model_dump(
                    mode="python"
                )
            }
        if "target_summary AS MATERIALIZED" in query:
            assert "target_dependencies" in query
            assert "mixed_order_target_count" in query
            assert "LIMIT 1001" in query
            assert "LIMIT 10001" in query
            assert parameters == (
                7,
                18,
                7,
                "logical_entity",
                "logical_entity",
            )
            return {
                "target_dependency_graph": (
                    self.expected.target_dependency_graph.model_dump(mode="python")
                )
            }
        assert "core.attribute AS attribute" in query
        assert "LIMIT 5001" in query
        assert parameters == (7, 18, 7, 501)
        return {"target": self.expected.target.model_dump(mode="python")}

    async def fetch_all(
        self,
        query: LiteralString,
        parameters: tuple[Any, ...] = (),
    ) -> list[dict[str, Any]]:
        if "mapping_attribute_document" in query:
            assert "LIMIT 65" in query
            assert "LIMIT 20001" in query
            assert parameters == (7, 18, 7, 501, 31, "logical_entity")
            return [
                {"header": item.model_dump(mode="python")}
                for item in self.expected.headers
            ]
        if "source_binding AS MATERIALIZED" in query:
            assert "workflow.logical_entity_source_mapping" in query
            assert "workflow.dimensional_entity_source_mapping" in query
            assert "core.ingestion_object_mapping" in query
            assert "prior_mapping.mapping_package_document IS NOT NULL" in query
            assert parameters == (
                7,
                18,
                7,
                501,
                31,
                "logical_entity",
                18,
                7,
                7,
            )
            return [
                {"source": item.model_dump(mode="python")}
                for item in self.expected.sources
            ]
        assert "application.output_template_field" in query
        assert "sha256" in query
        assert "LIMIT 501" in query
        assert parameters == (list(self.expected.output_templates.ids),)
        return [
            {"output_template": item.model_dump(mode="python")}
            for item in self.expected.output_templates.definitions
        ]


@pytest.mark.asyncio
async def test_postgres_context_loads_complete_typed_pair_with_optional_provenance() -> (
    None
):
    expected = _context()

    context = await PostgresMappingRunContextRepository().load(
        _ContextTransaction(expected),
        tenant_id=7,
        plan=_plan(),
    )

    assert context == expected
    assert context.headers[0].workflow_run_id is None
    assert context.headers[0].attribute_mappings[0].workflow_run_id is None
    assert [field.name for field in context.output_templates.definitions[0].fields] == [
        "transformation_kind"
    ]


@pytest.mark.asyncio
async def test_postgres_context_loads_selected_template_without_row_reference() -> None:
    plan = _plan(object_template=(803, "9" * 64))
    alternate = (
        _context()
        .output_templates.definitions[0]
        .model_copy(
            update={
                "output_template_id": 803,
                "code": "future_mapping_object",
                "schema_digest": "9" * 64,
            }
        )
    )
    expected = _context_for_plan(plan, extra_definitions=(alternate,))

    loaded = await PostgresMappingRunContextRepository().load(
        _ContextTransaction(expected),
        tenant_id=7,
        plan=plan,
    )

    assert loaded == expected
    assert loaded.output_templates.ids == (801, 802, 803)
    assert loaded.output_templates.definitions[-1] == alternate


@pytest.mark.asyncio
async def test_postgres_context_loads_cycle_for_deterministic_readiness_rejection() -> (
    None
):
    context = _context()
    graph = MappingDependencyGraph(
        nodes=(
            context.dependency_graph.nodes[0],
            MappingDependencyNode(
                mapping_source_system_dependency_id=72,
                source_system_id=42,
                dependency_order=1,
                status="active",
                is_locked=False,
            ),
        ),
        edges=(
            MappingDependencyEdge(
                predecessor_source_system_id=42,
                successor_source_system_id=31,
            ),
            MappingDependencyEdge(
                predecessor_source_system_id=31,
                successor_source_system_id=42,
            ),
        ),
        malformed_reference_count=0,
    )
    expected = context.model_copy(update={"dependency_graph": graph})

    loaded = await PostgresMappingRunContextRepository().load(
        _ContextTransaction(expected),
        tenant_id=7,
        plan=_plan(),
    )
    readiness = assess_mapping_readiness(
        plan=_plan(),
        context=loaded,
        registration=_profile(),
    )

    assert loaded.dependency_graph == graph
    assert [issue.code for issue in readiness.issues] == [
        "dependency.graph_order_invalid",
        "dependency.graph_cycle",
    ]


@pytest.mark.asyncio
async def test_postgres_context_loads_malformed_dependency_count_for_blocking() -> None:
    context = _context()
    expected = context.model_copy(
        update={
            "dependency_graph": context.dependency_graph.model_copy(
                update={"malformed_reference_count": 1}
            )
        }
    )

    loaded = await PostgresMappingRunContextRepository().load(
        _ContextTransaction(expected),
        tenant_id=7,
        plan=_plan(),
    )
    readiness = assess_mapping_readiness(
        plan=_plan(),
        context=loaded,
        registration=_profile(),
    )

    assert loaded.dependency_graph.malformed_reference_count == 1
    assert [issue.code for issue in readiness.issues] == ["dependency.graph_malformed"]


def test_dependency_graph_rejects_more_than_one_thousand_nodes() -> None:
    with pytest.raises(ValidationError):
        MappingDependencyGraph(
            nodes=tuple(
                MappingDependencyNode(
                    mapping_source_system_dependency_id=index,
                    source_system_id=index,
                    dependency_order=index - 1,
                    status="active",
                    is_locked=False,
                )
                for index in range(1, 1_002)
            ),
            edges=(),
            malformed_reference_count=0,
        )


@pytest.mark.asyncio
async def test_postgres_context_loads_target_cycle_for_readiness_rejection() -> None:
    context = _context()
    graph = MappingTargetDependencyGraph(
        nodes=(
            context.target_dependency_graph.nodes[0],
            MappingTargetDependencyNode(
                target_object_id=502,
                dependency_order=1,
                status="active",
                has_locked_headers=False,
                has_unlocked_headers=True,
            ),
        ),
        edges=(
            MappingTargetDependencyEdge(
                predecessor_target_object_id=502,
                successor_target_object_id=501,
            ),
            MappingTargetDependencyEdge(
                predecessor_target_object_id=501,
                successor_target_object_id=502,
            ),
        ),
        malformed_reference_count=0,
        mixed_order_target_count=0,
    )
    expected = context.model_copy(update={"target_dependency_graph": graph})

    loaded = await PostgresMappingRunContextRepository().load(
        _ContextTransaction(expected),
        tenant_id=7,
        plan=_plan(),
    )
    readiness = assess_mapping_readiness(
        plan=_plan(),
        context=loaded,
        registration=_profile(),
    )

    assert loaded.target_dependency_graph == graph
    assert [issue.code for issue in readiness.issues] == [
        "target_dependency.graph_order_invalid",
        "target_dependency.graph_cycle",
    ]


def test_target_graph_reports_malformed_missing_and_mixed_order() -> None:
    context = _context()
    graph = context.target_dependency_graph.model_copy(
        update={
            "edges": (
                MappingTargetDependencyEdge(
                    predecessor_target_object_id=999,
                    successor_target_object_id=501,
                ),
            ),
            "malformed_reference_count": 1,
            "mixed_order_target_count": 1,
        }
    )
    context = context.model_copy(update={"target_dependency_graph": graph})

    readiness = assess_mapping_readiness(
        plan=_plan(),
        context=context,
        registration=_profile(),
    )

    assert [issue.code for issue in readiness.issues] == [
        "target_dependency.graph_malformed",
        "target_dependency.graph_mixed_order",
        "target_dependency.graph_node_missing",
    ]


def test_target_graph_selected_node_must_match_current_header_order() -> None:
    context = _context()
    context = context.model_copy(
        update={
            "target_dependency_graph": context.target_dependency_graph.model_copy(
                update={
                    "nodes": (
                        context.target_dependency_graph.nodes[0].model_copy(
                            update={"dependency_order": 1}
                        ),
                    )
                }
            )
        }
    )

    readiness = assess_mapping_readiness(
        plan=_plan(),
        context=context,
        registration=_profile(),
    )

    assert [issue.code for issue in readiness.issues] == [
        "target_dependency.graph_selected_drift"
    ]


def test_target_dependency_graph_rejects_more_than_one_thousand_nodes() -> None:
    with pytest.raises(ValidationError):
        MappingTargetDependencyGraph(
            nodes=tuple(
                MappingTargetDependencyNode(
                    target_object_id=index,
                    dependency_order=index - 1,
                    status="active",
                    has_locked_headers=False,
                    has_unlocked_headers=True,
                )
                for index in range(1, 1_002)
            ),
            edges=(),
            malformed_reference_count=0,
            mixed_order_target_count=0,
        )
