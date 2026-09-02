from __future__ import annotations

import json
from collections.abc import Mapping
from typing import cast
from uuid import UUID

import pytest
from gds_etl_workbench.domain.errors import WorkbenchError
from gds_etl_workbench.domain.modeling_records import (
    LogicalEntityRecord,
    PhysicalAttributeKey,
    PhysicalObjectKey,
)
from pydantic import JsonValue, SecretStr
from mapping_fixtures import mapping_preparation as _mapping_preparation

from gds_workbench_api.capabilities import (
    AgentModelExecutionProfile,
    AgentRunSelection,
    load_default_agent_capabilities,
)
from gds_workbench_api.features.dimensional.candidate import (
    DimensionalCandidateValidator,
)
from gds_workbench_api.features.dimensional.detailed import (
    DetailedDimensionalEntityDetail,
    DetailedDimensionalEntityDetailValidator,
    DetailedDimensionalReconciliationReceiptValidator,
    DetailedDimensionalReconciliationValidator,
    DetailedDimensionalTopologyContribution,
    DetailedDimensionalTopologyContributionValidator,
    DetailedDimensionalTopologyReconciliationValidator,
    DetailedDimensionalValidationLeadValidator,
    DetailedDimensionalValidationWorkerResult,
    DetailedDimensionalValidationWorkerValidator,
    build_dimensional_draft_manifest,
    build_dimensional_relationship_signal_ledger,
    build_dimensional_validation_packages,
    materialize_dimensional_reviewed_candidate,
)
from gds_workbench_api.features.logical.candidate import LogicalCandidateValidator
from gds_workbench_api.features.logical.detailed import (
    DetailedLogicalEntityDetailValidator,
    DetailedLogicalReconciliationValidator,
    DetailedLogicalTopologyContributionValidator,
    DetailedLogicalTopologyReconciliationValidator,
    DetailedLogicalValidationFinding,
    DetailedLogicalValidationLeadValidator,
    DetailedLogicalValidationPackage,
    DetailedLogicalValidationRecord,
    DetailedLogicalValidationWorkerResult,
    DetailedLogicalValidationWorkerValidator,
    build_logical_relationship_signal_ledger,
)
from gds_workbench_api.features.mapping.complete_candidate import (
    CompleteMappingCandidateValidator,
)
from gds_workbench_api.features.mapping.execution_context import (
    build_mapping_execution_context,
)
from gds_workbench_api.features.workflows.authoring.agent_execution import (
    AgentExecutionRequest,
    LocalAgentToolCatalog,
    LocalAgentToolDefinition,
)
from gds_workbench_api.integrations.agents.configuration import (
    AgentProviderConnection,
    AgentRuntimeConfiguration,
    FoundryClientCredentials,
)
from gds_workbench_api.integrations.agents import (
    create_agent_execution_router,
)


def _selection(*, sdk_code: str) -> AgentRunSelection:
    return AgentRunSelection(
        sdk_code=sdk_code,
        provider_code="databricks",
        model_code="databricks-primary",
        reasoning_effort_code="medium",
        max_turns=8,
        validation_retry_count=2,
    )


def _request(*, sdk_code: str) -> AgentExecutionRequest:
    return AgentExecutionRequest(
        workflow_run_id=1048,
        workflow="code_generation",
        stage="sql_generation",
        execution_mode="one_shot",
        selection=_selection(sdk_code=sdk_code),
        system_prompt="private system prompt",
        instruction_prompt="private instruction prompt",
        context={
            "original_context": {
                "targets": [
                    {"target_ref": "target_1", "context": {"private": "value"}},
                    {"target_ref": "target_2", "context": {"private": "value"}},
                ]
            },
            "repair": None,
        },
        output_schema={"type": "object"},
        allowed_tool_names=(),
    )


@pytest.mark.asyncio
async def test_agent_router_rejects_a_model_profile_for_the_wrong_execution_mode() -> (
    None
):
    registry = load_default_agent_capabilities()
    databricks_model = next(
        model for model in registry.models if model.code == "databricks-primary"
    )
    restricted = databricks_model.model_copy(
        update={
            "execution_profiles": (
                AgentModelExecutionProfile(
                    sdk_code="langchain_create_agent",
                    execution_mode="detailed_coverage",
                    reasoning_effort_codes=("medium",),
                ),
            )
        }
    )
    registry = registry.model_copy(
        update={
            "models": tuple(
                restricted if model.code == restricted.code else model
                for model in registry.models
            )
        }
    )
    router = create_agent_execution_router(
        configuration=AgentRuntimeConfiguration(
            mode="fake",
            timeout_seconds=120,
            connections=(),
        ),
        capabilities=registry,
    )

    with pytest.raises(WorkbenchError, match="incompatible"):
        await router.execute(_request(sdk_code="langchain_create_agent"))


def _mapping_request(
    *, sdk_code: str
) -> tuple[AgentExecutionRequest, CompleteMappingCandidateValidator]:
    preparation = _mapping_preparation()
    context = build_mapping_execution_context(
        preparation=preparation,
        execution_mode="one_shot",
    )
    validator = CompleteMappingCandidateValidator(preparation=preparation)
    return (
        AgentExecutionRequest(
            workflow_run_id=1048,
            workflow="mapping",
            stage="mapping_authoring",
            execution_mode="one_shot",
            selection=_selection(sdk_code=sdk_code),
            system_prompt="private system prompt",
            instruction_prompt="private instruction prompt",
            context={"original_context": context.embedded_context, "repair": None},
            output_schema=validator.output_schema(),
            allowed_tool_names=(),
        ),
        validator,
    )


class _RecordingMappingCatalog:
    def __init__(self, delegate: LocalAgentToolCatalog) -> None:
        self.delegate = delegate
        self.calls: list[tuple[str, dict[str, JsonValue]]] = []

    @property
    def definitions(self) -> tuple[LocalAgentToolDefinition, ...]:
        return self.delegate.definitions

    @property
    def max_cumulative_result_bytes(self) -> int:
        return self.delegate.max_cumulative_result_bytes

    def invoke(
        self,
        tool_name: str,
        arguments: Mapping[str, JsonValue],
    ) -> JsonValue:
        self.calls.append((tool_name, dict(arguments)))
        return self.delegate.invoke(tool_name, arguments)


def _tool_assisted_mapping_request(
    *,
    sdk_code: str,
) -> tuple[
    AgentExecutionRequest,
    CompleteMappingCandidateValidator,
    _RecordingMappingCatalog,
]:
    preparation = _mapping_preparation(execution_mode="tool_assisted")
    context = build_mapping_execution_context(
        preparation=preparation,
        execution_mode="tool_assisted",
    )
    catalog = context.tool_catalog
    assert catalog is not None
    recording_catalog = _RecordingMappingCatalog(catalog)
    validator = CompleteMappingCandidateValidator(preparation=preparation)
    return (
        AgentExecutionRequest(
            workflow_run_id=1048,
            workflow="mapping",
            stage="mapping_authoring",
            execution_mode="tool_assisted",
            selection=_selection(sdk_code=sdk_code),
            system_prompt="private system prompt",
            instruction_prompt="private instruction prompt",
            tool_instruction="Use only the immutable local Mapping tools.",
            context={"original_context": context.embedded_context, "repair": None},
            output_schema=validator.output_schema(),
            allowed_tool_names=tuple(
                definition.name for definition in recording_catalog.definitions
            ),
            local_tool_catalog=recording_catalog,
        ),
        validator,
        recording_catalog,
    )


def _conceptual_request(*, sdk_code: str) -> AgentExecutionRequest:
    return AgentExecutionRequest(
        workflow_run_id=1048,
        workflow="conceptual",
        stage="candidate_authoring",
        execution_mode="one_shot",
        selection=_selection(sdk_code=sdk_code),
        system_prompt="private system prompt",
        instruction_prompt="private instruction prompt",
        context={
            "original_context": {
                "selected_objects": [
                    {
                        "selection_order": 1,
                        "object": {
                            "tenant_code": "NWA",
                            "system_code": "CRM",
                            "connection_code": "SOURCE",
                            "object_schema": "bronze",
                            "object_name": "customer_raw",
                        },
                        "attributes": [],
                    }
                ]
            },
            "repair": None,
        },
        output_schema={"type": "object"},
        allowed_tool_names=(),
    )


class _ConceptualCatalog:
    max_cumulative_result_bytes = 64 * 1024
    definitions = (
        LocalAgentToolDefinition(
            name="get_agent_context_manifest",
            description="Return the local context manifest.",
            input_schema={
                "type": "object",
                "properties": {},
                "additionalProperties": False,
            },
        ),
        LocalAgentToolDefinition(
            name="get_agent_context_dataset",
            description="Return one bounded local context page.",
            input_schema={
                "type": "object",
                "properties": {
                    "dataset": {"type": "string"},
                    "offset": {"type": "integer", "minimum": 0},
                    "limit": {"type": "integer", "minimum": 1, "maximum": 200},
                },
                "required": ["dataset", "offset", "limit"],
                "additionalProperties": False,
            },
        ),
    )

    def invoke(
        self,
        tool_name: str,
        arguments: Mapping[str, JsonValue],
    ) -> JsonValue:
        if tool_name == "get_agent_context_manifest":
            assert arguments == {}
            return {"dataset_counts": {"selected_object": 1}}
        assert tool_name == "get_agent_context_dataset"
        assert arguments == {"dataset": "selected_object", "offset": 0, "limit": 1}
        return {
            "dataset": "selected_object",
            "total_count": 1,
            "offset": 0,
            "items": [
                {
                    "selection_order": 1,
                    "tenant_code": "NWA",
                    "system_code": "CRM",
                    "connection_code": "SOURCE",
                    "object_schema": "bronze",
                    "object_name": "customer_raw",
                    "attribute_count": 0,
                }
            ],
            "next_offset": None,
        }


class _LogicalCatalog:
    max_cumulative_result_bytes = 64 * 1024
    definitions = _ConceptualCatalog.definitions

    def invoke(
        self,
        tool_name: str,
        arguments: Mapping[str, JsonValue],
    ) -> JsonValue:
        if tool_name == "get_agent_context_manifest":
            assert arguments == {}
            return {
                "dataset_counts": {
                    "selected_object": 1,
                    "selected_attribute": 1,
                }
            }
        assert tool_name == "get_agent_context_dataset"
        dataset = arguments.get("dataset")
        assert arguments == {"dataset": dataset, "offset": 0, "limit": 1}
        if dataset == "selected_object":
            item: JsonValue = {
                "selection_order": 1,
                "tenant_code": "NWA",
                "system_code": "CRM",
                "connection_code": "SOURCE",
                "object_schema": "bronze",
                "object_name": "customer_raw",
                "object_description": "private object context",
                "attribute_count": 1,
            }
        else:
            assert dataset == "selected_attribute"
            item = {
                "selection_order": 1,
                "tenant_code": "NWA",
                "system_code": "CRM",
                "connection_code": "SOURCE",
                "object_schema": "bronze",
                "object_name": "customer_raw",
                "attribute_name": "customer_id",
                "attribute_description": "private attribute context",
            }
        return {
            "dataset": dataset,
            "total_count": 1,
            "offset": 0,
            "items": [item],
            "next_offset": None,
        }


class _PaginatedDimensionalCatalog:
    max_cumulative_result_bytes = 64 * 1024
    definitions = (
        _ConceptualCatalog.definitions[0],
        LocalAgentToolDefinition(
            name="get_agent_context_dataset",
            description="Return one bounded local context page.",
            input_schema={
                "type": "object",
                "properties": {
                    "dataset": {"type": "string"},
                    "offset": {"type": "integer", "minimum": 0},
                    "limit": {"type": "integer", "minimum": 1, "maximum": 1},
                },
                "required": ["dataset", "offset", "limit"],
                "additionalProperties": False,
            },
        ),
    )

    def __init__(self) -> None:
        self.calls: list[tuple[str, int]] = []

    def invoke(
        self,
        tool_name: str,
        arguments: Mapping[str, JsonValue],
    ) -> JsonValue:
        if tool_name == "get_agent_context_manifest":
            assert arguments == {}
            return {
                "dataset_counts": {
                    "selected_object": 2,
                    "selected_attribute": 2,
                }
            }
        assert tool_name == "get_agent_context_dataset"
        dataset = arguments.get("dataset")
        offset = arguments.get("offset")
        assert dataset in ("selected_object", "selected_attribute")
        assert isinstance(offset, int) and not isinstance(offset, bool)
        assert arguments == {"dataset": dataset, "offset": offset, "limit": 1}
        assert offset in (0, 1)
        self.calls.append((cast(str, dataset), offset))
        object_name = ("customer_curated", "order_curated")[offset]
        item: dict[str, JsonValue] = {
            "selection_order": offset + 1,
            "tenant_code": "NWA",
            "system_code": "CRM",
            "connection_code": "CURATED",
            "object_schema": "silver",
            "object_name": object_name,
            "private_description": "must not appear",
        }
        if dataset == "selected_object":
            item["attribute_count"] = 1
        else:
            item["attribute_name"] = "customer_id"
        return {
            "dataset": dataset,
            "total_count": 2,
            "offset": offset,
            "items": [item],
            "next_offset": offset + 1 if offset == 0 else None,
        }


def _tool_assisted_conceptual_request(*, sdk_code: str) -> AgentExecutionRequest:
    catalog = _ConceptualCatalog()
    return AgentExecutionRequest(
        workflow_run_id=1048,
        workflow="conceptual",
        stage="candidate_authoring",
        execution_mode="tool_assisted",
        selection=_selection(sdk_code=sdk_code),
        system_prompt="private system prompt",
        instruction_prompt="private instruction prompt",
        tool_instruction="Use the local tools.",
        context={
            "original_context": {"dataset_counts": {"selected_object": 1}},
            "repair": None,
        },
        output_schema={"type": "object"},
        allowed_tool_names=tuple(item.name for item in catalog.definitions),
        local_tool_catalog=catalog,
    )


def _tool_assisted_logical_request(*, sdk_code: str) -> AgentExecutionRequest:
    catalog = _LogicalCatalog()
    return AgentExecutionRequest(
        workflow_run_id=1048,
        workflow="logical",
        stage="candidate_authoring",
        execution_mode="tool_assisted",
        selection=_selection(sdk_code=sdk_code),
        system_prompt="private system prompt",
        instruction_prompt="private instruction prompt",
        tool_instruction="Use the local tools.",
        context={
            "original_context": {
                "dataset_counts": {
                    "selected_object": 1,
                    "selected_attribute": 1,
                }
            },
            "repair": None,
        },
        output_schema={"type": "object"},
        allowed_tool_names=tuple(item.name for item in catalog.definitions),
        local_tool_catalog=catalog,
    )


def _tool_assisted_dimensional_request(
    *,
    sdk_code: str,
    catalog: _PaginatedDimensionalCatalog,
) -> AgentExecutionRequest:
    manifest = cast(
        JsonValue,
        {
            "dataset_counts": {
                "selected_object": 2,
                "selected_attribute": 2,
            }
        },
    )
    return AgentExecutionRequest(
        workflow_run_id=1048,
        workflow="dimensional",
        stage="candidate_authoring",
        execution_mode="tool_assisted",
        selection=_selection(sdk_code=sdk_code),
        system_prompt="private system prompt",
        instruction_prompt="private instruction prompt",
        tool_instruction="Use the local tools.",
        context=cast(JsonValue, {"original_context": manifest, "repair": None}),
        output_schema={"type": "object"},
        allowed_tool_names=tuple(item.name for item in catalog.definitions),
        local_tool_catalog=catalog,
    )


def _analysis_request(*, sdk_code: str) -> AgentExecutionRequest:
    selected_objects: list[dict[str, JsonValue]] = []
    for position, object_name in enumerate(("order_raw", "customer_raw"), start=1):
        selected_objects.append(
            {
                "selection_order": position,
                "object": {
                    "tenant_code": "NWA",
                    "system_code": "CRM",
                    "connection_code": "SOURCE",
                    "object_schema": "bronze",
                    "object_name": object_name,
                },
                "attributes": [
                    {
                        "tenant_code": "NWA",
                        "system_code": "CRM",
                        "connection_code": "SOURCE",
                        "object_schema": "bronze",
                        "object_name": object_name,
                        "attribute_name": "customer_id",
                    }
                ],
            }
        )
    return AgentExecutionRequest(
        workflow_run_id=1048,
        workflow="analysis_inference",
        stage="relationship_inference",
        execution_mode="one_shot",
        selection=_selection(sdk_code=sdk_code),
        system_prompt="private system prompt",
        instruction_prompt="private instruction prompt",
        context=cast(
            JsonValue,
            {
                "original_context": {"selected_objects": selected_objects},
                "repair": None,
            },
        ),
        output_schema={"type": "object"},
        allowed_tool_names=(),
    )


def _tool_assisted_analysis_request(
    *,
    sdk_code: str,
    catalog: _PaginatedDimensionalCatalog,
) -> AgentExecutionRequest:
    manifest = cast(
        JsonValue,
        {
            "dataset_counts": {
                "selected_object": 2,
                "selected_attribute": 2,
            }
        },
    )
    return AgentExecutionRequest(
        workflow_run_id=1048,
        workflow="analysis_inference",
        stage="relationship_inference",
        execution_mode="tool_assisted",
        selection=_selection(sdk_code=sdk_code),
        system_prompt="private system prompt",
        instruction_prompt="private instruction prompt",
        tool_instruction="Use the local tools.",
        context=cast(JsonValue, {"original_context": manifest, "repair": None}),
        output_schema={"type": "object"},
        allowed_tool_names=tuple(item.name for item in catalog.definitions),
        local_tool_catalog=catalog,
    )


def _logical_request(*, sdk_code: str) -> AgentExecutionRequest:
    return AgentExecutionRequest(
        workflow_run_id=1048,
        workflow="logical",
        stage="candidate_authoring",
        execution_mode="one_shot",
        selection=_selection(sdk_code=sdk_code),
        system_prompt="private system prompt",
        instruction_prompt="private instruction prompt",
        context={
            "original_context": {
                "selected_objects": [
                    {
                        "selection_order": 1,
                        "object": {
                            "tenant_code": "NWA",
                            "system_code": "CRM",
                            "connection_code": "SOURCE",
                            "object_schema": "bronze",
                            "object_name": "customer_raw",
                            "object_description": "private object context",
                        },
                        "attributes": [
                            {
                                "tenant_code": "NWA",
                                "system_code": "CRM",
                                "connection_code": "SOURCE",
                                "object_schema": "bronze",
                                "object_name": "customer_raw",
                                "attribute_name": "customer_id",
                                "attribute_description": "private attribute context",
                            }
                        ],
                    }
                ]
            },
            "repair": None,
        },
        output_schema={"type": "object"},
        allowed_tool_names=(),
    )


def _logical_validator() -> LogicalCandidateValidator:
    source_object = PhysicalObjectKey(
        tenant_code="NWA",
        system_code="CRM",
        connection_code="SOURCE",
        object_schema="bronze",
        object_name="customer_raw",
    )
    return LogicalCandidateValidator(
        selected_object_keys=(source_object,),
        selected_attribute_keys=(
            PhysicalAttributeKey(
                **source_object.model_dump(),
                attribute_name="customer_id",
            ),
        ),
        assertion_record_keys=(),
        applied=None,
    )


def _dimensional_request(*, sdk_code: str) -> AgentExecutionRequest:
    return AgentExecutionRequest(
        workflow_run_id=1048,
        workflow="dimensional",
        stage="candidate_authoring",
        execution_mode="one_shot",
        selection=_selection(sdk_code=sdk_code),
        system_prompt="private system prompt",
        instruction_prompt="private instruction prompt",
        context={
            "original_context": {
                "selected_objects": [
                    {
                        "selection_order": 1,
                        "object": {
                            "tenant_code": "NWA",
                            "system_code": "CRM",
                            "connection_code": "CURATED",
                            "object_schema": "silver",
                            "object_name": "customer_curated",
                            "object_description": "private object context",
                        },
                        "attributes": [
                            {
                                "tenant_code": "NWA",
                                "system_code": "CRM",
                                "connection_code": "CURATED",
                                "object_schema": "silver",
                                "object_name": "customer_curated",
                                "attribute_name": "customer_id",
                                "attribute_description": "private attribute context",
                            }
                        ],
                    }
                ]
            },
            "repair": None,
        },
        output_schema={"type": "object"},
        allowed_tool_names=(),
    )


def _dimensional_validator(
    *,
    source_objects: tuple[PhysicalObjectKey, ...] | None = None,
    source_attributes: tuple[PhysicalAttributeKey, ...] | None = None,
) -> DimensionalCandidateValidator:
    default_object = PhysicalObjectKey(
        tenant_code="NWA",
        system_code="CRM",
        connection_code="CURATED",
        object_schema="silver",
        object_name="customer_curated",
    )
    return DimensionalCandidateValidator(
        selected_object_keys=source_objects or (default_object,),
        selected_attribute_keys=source_attributes
        or (
            PhysicalAttributeKey(
                **default_object.model_dump(),
                attribute_name="customer_id",
            ),
        ),
        assertion_record_keys=(),
        applied=None,
    )


def _detailed_conceptual_request(
    *,
    sdk_code: str,
    stage: str,
    context: JsonValue,
) -> AgentExecutionRequest:
    return AgentExecutionRequest(
        workflow_run_id=1048,
        workflow="conceptual",
        stage=stage,
        execution_mode="detailed_coverage",
        selection=_selection(sdk_code=sdk_code),
        system_prompt="private system prompt",
        instruction_prompt="private instruction prompt",
        context={"original_context": context, "repair": None},
        output_schema={"type": "object"},
        allowed_tool_names=(),
    )


def _detailed_logical_request(
    *,
    sdk_code: str,
    stage: str,
    context: JsonValue,
) -> AgentExecutionRequest:
    return AgentExecutionRequest(
        workflow_run_id=1048,
        workflow="logical",
        stage=stage,
        execution_mode="detailed_coverage",
        selection=_selection(sdk_code=sdk_code),
        system_prompt="private system prompt",
        instruction_prompt="private instruction prompt",
        context={"original_context": context, "repair": None},
        output_schema={"type": "object"},
        allowed_tool_names=(),
    )


def _detailed_dimensional_request(
    *,
    sdk_code: str,
    stage: str,
    context: JsonValue,
) -> AgentExecutionRequest:
    return AgentExecutionRequest(
        workflow_run_id=1048,
        workflow="dimensional",
        stage=stage,
        execution_mode="detailed_coverage",
        selection=_selection(sdk_code=sdk_code),
        system_prompt="private system prompt",
        instruction_prompt="private instruction prompt",
        context={"original_context": context, "repair": None},
        output_schema={"type": "object"},
        allowed_tool_names=(),
    )


@pytest.mark.parametrize(
    "sdk_code",
    ("langchain_create_agent", "openai_agents_sdk"),
)
async def test_local_fake_returns_one_complete_valid_mapping_candidate(
    sdk_code: str,
) -> None:
    router = create_agent_execution_router(
        configuration=AgentRuntimeConfiguration(
            mode="fake",
            timeout_seconds=120,
            connections=(),
        ),
        capabilities=load_default_agent_capabilities(),
    )
    request, validator = _mapping_request(sdk_code=sdk_code)

    result = await router.execute(request)
    repeated = await router.execute(request)

    assert result.candidate == repeated.candidate
    assert (await validator.validate(result.candidate)).issues == ()
    assert "private system prompt" not in repr(result.candidate)
    assert result.turn_count == 1
    assert result.tool_call_count == 0


@pytest.mark.parametrize(
    "sdk_code",
    ("langchain_create_agent", "openai_agents_sdk"),
)
async def test_local_fake_uses_local_tools_for_one_complete_mapping_candidate(
    sdk_code: str,
) -> None:
    router = create_agent_execution_router(
        configuration=AgentRuntimeConfiguration(
            mode="fake",
            timeout_seconds=120,
            connections=(),
        ),
        capabilities=load_default_agent_capabilities(),
    )
    request, validator, catalog = _tool_assisted_mapping_request(sdk_code=sdk_code)

    result = await router.execute(request)

    assert (await validator.validate(result.candidate)).issues == ()
    assert result.tool_call_count > 0
    assert "private system prompt" not in repr(result.candidate)
    retrieved_datasets = {
        cast(str, arguments["dataset"])
        for tool_name, arguments in catalog.calls
        if tool_name == "get_mapping_context_dataset"
    }
    assert retrieved_datasets >= {
        "target_attribute",
        "source_attribute",
        "modeled_attribute",
        "existing_mapping_attribute",
    }
    for dataset, nested_field in (
        ("target", "attributes"),
        ("header", "attribute_mappings"),
    ):
        page = cast(
            dict[str, JsonValue],
            catalog.delegate.invoke(
                "get_mapping_context_dataset",
                {"dataset": dataset, "offset": 0, "limit": 1},
            ),
        )
        parent = cast(list[dict[str, JsonValue]], page["items"])[0]
        assert parent[nested_field] == []
    source_page = cast(
        dict[str, JsonValue],
        catalog.delegate.invoke(
            "get_mapping_context_dataset",
            {"dataset": "source", "offset": 0, "limit": 1},
        ),
    )
    source_parent = cast(list[dict[str, JsonValue]], source_page["items"])[0]
    assert cast(dict[str, JsonValue], source_parent["object"])["attributes"] == []


@pytest.mark.parametrize(
    "sdk_code",
    ("langchain_create_agent", "openai_agents_sdk"),
)
async def test_local_fake_supports_complete_detailed_mapping_sequence(
    sdk_code: str,
) -> None:
    router = create_agent_execution_router(
        configuration=AgentRuntimeConfiguration(
            mode="fake",
            timeout_seconds=120,
            connections=(),
        ),
        capabilities=load_default_agent_capabilities(),
    )
    preparation = _mapping_preparation(execution_mode="detailed_coverage")
    context = build_mapping_execution_context(
        preparation=preparation,
        execution_mode="detailed_coverage",
    )
    validator = CompleteMappingCandidateValidator(preparation=preparation)
    result = await router.execute(
        AgentExecutionRequest(
            workflow_run_id=1048,
            workflow="mapping",
            stage="mapping_authoring",
            execution_mode="detailed_coverage",
            selection=_selection(sdk_code=sdk_code),
            system_prompt="private system prompt",
            instruction_prompt="private instruction prompt",
            context={"original_context": context.embedded_context, "repair": None},
            output_schema=validator.output_schema(),
            allowed_tool_names=(),
        )
    )

    assert (await validator.validate(result.candidate)).issues == ()
    assert result.tool_call_count == 0
    assert "private system prompt" not in repr(result.candidate)


@pytest.mark.parametrize(
    "sdk_code",
    ("langchain_create_agent", "openai_agents_sdk"),
)
async def test_local_fake_returns_exact_code_generation_target_coverage(
    sdk_code: str,
) -> None:
    router = create_agent_execution_router(
        configuration=AgentRuntimeConfiguration(
            mode="fake",
            timeout_seconds=120,
            connections=(),
        ),
        capabilities=load_default_agent_capabilities(),
    )

    result = await router.execute(_request(sdk_code=sdk_code))

    assert result.candidate == {
        "artifacts": [
            {"target_ref": "target_1", "generated_sql": "SELECT 1;\n"},
            {"target_ref": "target_2", "generated_sql": "SELECT 2;\n"},
        ]
    }
    rendered = repr(result)
    assert "private" not in rendered
    assert result.turn_count == 1
    assert result.tool_call_count == 0


@pytest.mark.parametrize(
    "sdk_code",
    ("langchain_create_agent", "openai_agents_sdk"),
)
async def test_local_fake_supports_detailed_conceptual_stage_contracts(
    sdk_code: str,
) -> None:
    router = create_agent_execution_router(
        configuration=AgentRuntimeConfiguration(
            mode="fake",
            timeout_seconds=120,
            connections=(),
        ),
        capabilities=load_default_agent_capabilities(),
    )
    selected_object: dict[str, JsonValue] = {
        "selection_order": 1,
        "object": {
            "tenant_code": "NWA",
            "source_tenant_code": "NWA",
            "system_code": "CRM",
            "connection_code": "SOURCE",
            "object_schema": "bronze",
            "object_name": "customer_raw",
            "fc_object_schema": None,
            "fc_object_name": None,
            "object_transformation": None,
            "object_description": "Customer metadata.",
            "batch_attribute_name": "batch_id",
            "object_type_code": "table",
            "zone_code": "bronze",
            "is_locked": False,
            "is_active": True,
        },
        "attributes": [],
    }
    contribution = await router.execute(
        _detailed_conceptual_request(
            sdk_code=sdk_code,
            stage="object_contribution",
            context=cast(
                JsonValue,
                {
                    "schema_version": "1.0",
                    "model": {"model_name": "Customer 360"},
                    "contribution_ref": "object_1",
                    "selected_object": selected_object,
                    "profiles": [],
                    "analysis_relationships": [],
                    "assertions": {"documents": [], "records": []},
                    "applied_conceptual": None,
                },
            ),
        )
    )
    consolidation = await router.execute(
        _detailed_conceptual_request(
            sdk_code=sdk_code,
            stage="entity_consolidation",
            context=cast(
                JsonValue,
                {
                    "schema_version": "1.0",
                    "model": {"model_name": "Customer 360"},
                    "contributions": [contribution.candidate],
                },
            ),
        )
    )
    consolidation_candidate = cast(
        dict[str, JsonValue],
        consolidation.candidate,
    )
    consolidated_entities = cast(
        list[dict[str, JsonValue]],
        consolidation_candidate["entities"],
    )
    detail = await router.execute(
        _detailed_conceptual_request(
            sdk_code=sdk_code,
            stage="entity_attribute_detail",
            context=cast(
                JsonValue,
                {
                    "schema_version": "1.0",
                    "model": {"model_name": "Customer 360"},
                    "entity": consolidated_entities[0],
                    "contributions": [contribution.candidate],
                    "selected_objects": [selected_object],
                },
            ),
        )
    )
    reconciled = await router.execute(
        _detailed_conceptual_request(
            sdk_code=sdk_code,
            stage="whole_model_reconciliation",
            context=cast(
                JsonValue,
                {
                    "schema_version": "1.0",
                    "model": {"model_name": "Customer 360"},
                    "consolidation": consolidation.candidate,
                    "entity_details": [detail.candidate],
                    "relationship_packages": [],
                    "relationship_refinements": [],
                    "applied_conceptual": None,
                    "required_applied_record_refs": [],
                    "required_input_contribution_refs": ["object_1"],
                },
            ),
        )
    )

    assert cast(dict[str, JsonValue], contribution.candidate)["contribution_ref"] == (
        "object_1"
    )
    assert len(consolidated_entities) == 1
    assert cast(dict[str, JsonValue], detail.candidate)["canonical_entity_ref"] == (
        "business_concept"
    )
    assert (
        cast(dict[str, JsonValue], reconciled.candidate)[
            "reviewed_relationship_package_refs"
        ]
        == []
    )


@pytest.mark.parametrize(
    "sdk_code",
    ("langchain_create_agent", "openai_agents_sdk"),
)
async def test_local_fake_returns_bounded_conceptual_candidate(
    sdk_code: str,
) -> None:
    router = create_agent_execution_router(
        configuration=AgentRuntimeConfiguration(
            mode="fake",
            timeout_seconds=120,
            connections=(),
        ),
        capabilities=load_default_agent_capabilities(),
    )

    result = await router.execute(_conceptual_request(sdk_code=sdk_code))

    candidate = result.candidate
    assert isinstance(candidate, dict)
    assert candidate["relationships"] == []
    objects = cast(list[dict[str, JsonValue]], candidate["objects"])
    supports = cast(list[dict[str, JsonValue]], objects[0]["supports"])
    assert supports[0]["source_object"] == {
        "tenant_code": "NWA",
        "system_code": "CRM",
        "connection_code": "SOURCE",
        "object_schema": "bronze",
        "object_name": "customer_raw",
    }
    assert "private" not in repr(result)
    assert result.tool_call_count == 0


@pytest.mark.parametrize(
    "sdk_code",
    ("langchain_create_agent", "openai_agents_sdk"),
)
async def test_local_fake_returns_deterministic_valid_logical_candidate(
    sdk_code: str,
) -> None:
    router = create_agent_execution_router(
        configuration=AgentRuntimeConfiguration(
            mode="fake",
            timeout_seconds=120,
            connections=(),
        ),
        capabilities=load_default_agent_capabilities(),
    )
    request = _logical_request(sdk_code=sdk_code)

    result = await router.execute(request)
    repeated = await router.execute(request)

    assert result.candidate == repeated.candidate
    assert (await _logical_validator().validate(result.candidate)).issues == ()
    candidate = cast(dict[str, JsonValue], result.candidate)
    assert len(cast(list[JsonValue], candidate["entities"])) == 1
    assert len(cast(list[JsonValue], candidate["attributes"])) == 1
    assert "private" not in repr(candidate)
    assert result.turn_count == 1
    assert result.tool_call_count == 0


@pytest.mark.parametrize(
    "sdk_code",
    ("langchain_create_agent", "openai_agents_sdk"),
)
async def test_local_fake_returns_deterministic_valid_dimensional_business_candidate(
    sdk_code: str,
) -> None:
    router = create_agent_execution_router(
        configuration=AgentRuntimeConfiguration(
            mode="fake",
            timeout_seconds=120,
            connections=(),
        ),
        capabilities=load_default_agent_capabilities(),
    )
    request = _dimensional_request(sdk_code=sdk_code)

    result = await router.execute(request)
    repeated = await router.execute(request)

    assert result.candidate == repeated.candidate
    assert (await _dimensional_validator().validate(result.candidate)).issues == ()
    candidate = cast(dict[str, JsonValue], result.candidate)
    attributes = cast(list[dict[str, JsonValue]], candidate["attributes"])
    attribute_sources = cast(list[dict[str, JsonValue]], attributes[0]["sources"])
    assert attribute_sources[0]["source_attribute"] == {
        "tenant_code": "NWA",
        "system_code": "CRM",
        "connection_code": "CURATED",
        "object_schema": "silver",
        "object_name": "customer_curated",
        "attribute_name": "customer_id",
    }
    assert all(
        item["dimensional_attribute_role"] not in ("technical", "audit")
        and item["dimensional_attribute_key_role"] not in ("surrogate", "foreign")
        and item["dimensional_attribute_is_audit_column"] is False
        for item in attributes
    )
    assert "private" not in repr(candidate)
    assert result.turn_count == 1
    assert result.tool_call_count == 0


@pytest.mark.parametrize(
    "sdk_code",
    ("langchain_create_agent", "openai_agents_sdk"),
)
async def test_local_fake_builds_valid_logical_topology_contribution(
    sdk_code: str,
) -> None:
    router = create_agent_execution_router(
        configuration=AgentRuntimeConfiguration(
            mode="fake",
            timeout_seconds=120,
            connections=(),
        ),
        capabilities=load_default_agent_capabilities(),
    )
    source_object = PhysicalObjectKey(
        tenant_code="NWA",
        system_code="CRM",
        connection_code="SOURCE",
        object_schema="bronze",
        object_name="customer_raw",
    )
    source_attribute = PhysicalAttributeKey(
        **source_object.model_dump(),
        attribute_name="customer_id",
    )
    result = await router.execute(
        _detailed_logical_request(
            sdk_code=sdk_code,
            stage="topology_builder",
            context=cast(
                JsonValue,
                {
                    "schema_version": "1.0",
                    "model": {"model_name": "private model context"},
                    "contribution_ref": "object_00001",
                    "selected_object": {
                        "selection_order": 1,
                        "object": {
                            **source_object.model_dump(mode="json"),
                            "object_description": "private object context",
                        },
                        "attributes": [
                            {
                                **source_attribute.model_dump(mode="json"),
                                "attribute_description": "private attribute context",
                            }
                        ],
                    },
                    "profiles": [],
                    "analysis_relationships": [],
                    "assertions": {"documents": [], "records": []},
                    "applied_logical": None,
                },
            ),
        )
    )
    validator = DetailedLogicalTopologyContributionValidator(
        contribution_ref="object_00001",
        source_object=source_object,
        source_attributes=(source_attribute,),
    )

    assert (await validator.validate(result.candidate)).issues == ()
    assert "private" not in repr(result.candidate)
    assert result.tool_call_count == 0


@pytest.mark.parametrize(
    "sdk_code",
    ("langchain_create_agent", "openai_agents_sdk"),
)
async def test_local_fake_reconciles_complete_logical_topology(
    sdk_code: str,
) -> None:
    router = create_agent_execution_router(
        configuration=AgentRuntimeConfiguration(
            mode="fake",
            timeout_seconds=120,
            connections=(),
        ),
        capabilities=load_default_agent_capabilities(),
    )
    source_object = PhysicalObjectKey(
        tenant_code="NWA",
        system_code="CRM",
        connection_code="SOURCE",
        object_schema="bronze",
        object_name="customer_raw",
    )
    source_attribute = PhysicalAttributeKey(
        **source_object.model_dump(),
        attribute_name="customer_id",
    )
    contribution_validator = DetailedLogicalTopologyContributionValidator(
        contribution_ref="object_00001",
        source_object=source_object,
        source_attributes=(source_attribute,),
    )
    contribution = contribution_validator.parse_validated(
        (
            await router.execute(
                _detailed_logical_request(
                    sdk_code=sdk_code,
                    stage="topology_builder",
                    context=cast(
                        JsonValue,
                        {
                            "contribution_ref": "object_00001",
                            "selected_object": {
                                "object": source_object.model_dump(mode="json"),
                                "attributes": [
                                    source_attribute.model_dump(mode="json")
                                ],
                            },
                        },
                    ),
                )
            )
        ).candidate
    )
    result = await router.execute(
        _detailed_logical_request(
            sdk_code=sdk_code,
            stage="topology_reconciler",
            context=cast(
                JsonValue,
                {
                    "schema_version": "1.0",
                    "model": {"model_name": "private model context"},
                    "contributions": [contribution.model_dump(mode="json")],
                    "applied_logical": None,
                },
            ),
        )
    )
    validator = DetailedLogicalTopologyReconciliationValidator(
        contributions=(contribution,)
    )

    assert (await validator.validate(result.candidate)).issues == ()
    assert "private" not in repr(result.candidate)


@pytest.mark.parametrize(
    "sdk_code",
    ("langchain_create_agent", "openai_agents_sdk"),
)
async def test_local_fake_builds_valid_logical_entity_detail(
    sdk_code: str,
) -> None:
    router = create_agent_execution_router(
        configuration=AgentRuntimeConfiguration(
            mode="fake",
            timeout_seconds=120,
            connections=(),
        ),
        capabilities=load_default_agent_capabilities(),
    )
    source_object = PhysicalObjectKey(
        tenant_code="NWA",
        system_code="CRM",
        connection_code="SOURCE",
        object_schema="bronze",
        object_name="customer_raw",
    )
    source_attribute = PhysicalAttributeKey(
        **source_object.model_dump(),
        attribute_name="customer_id",
    )
    contribution_validator = DetailedLogicalTopologyContributionValidator(
        contribution_ref="object_00001",
        source_object=source_object,
        source_attributes=(source_attribute,),
    )
    contribution = contribution_validator.parse_validated(
        (
            await router.execute(
                _detailed_logical_request(
                    sdk_code=sdk_code,
                    stage="topology_builder",
                    context=cast(
                        JsonValue,
                        {
                            "contribution_ref": "object_00001",
                            "selected_object": {
                                "object": source_object.model_dump(mode="json"),
                                "attributes": [
                                    source_attribute.model_dump(mode="json")
                                ],
                            },
                        },
                    ),
                )
            )
        ).candidate
    )
    topology_validator = DetailedLogicalTopologyReconciliationValidator(
        contributions=(contribution,)
    )
    topology = topology_validator.parse_validated(
        (
            await router.execute(
                _detailed_logical_request(
                    sdk_code=sdk_code,
                    stage="topology_reconciler",
                    context=cast(
                        JsonValue,
                        {"contributions": [contribution.model_dump(mode="json")]},
                    ),
                )
            )
        ).candidate
    )
    entity = topology.entities[0]
    result = await router.execute(
        _detailed_logical_request(
            sdk_code=sdk_code,
            stage="entity_detail_builder",
            context=cast(
                JsonValue,
                {
                    "schema_version": "1.0",
                    "model": {"model_name": "private model context"},
                    "topology": topology.model_dump(mode="json"),
                    "entity": entity.model_dump(mode="json"),
                    "contributions": [contribution.model_dump(mode="json")],
                    "selected_objects": [
                        {
                            "object": {
                                **source_object.model_dump(mode="json"),
                                "object_description": "private object context",
                            },
                            "attributes": [
                                {
                                    **source_attribute.model_dump(mode="json"),
                                    "attribute_description": "private attribute context",
                                }
                            ],
                        }
                    ],
                },
            ),
        )
    )
    validator = DetailedLogicalEntityDetailValidator(
        entity=entity,
        topology=topology,
        contributions=(contribution,),
    )

    assert (await validator.validate(result.candidate)).issues == ()
    assert "private" not in repr(result.candidate)


@pytest.mark.parametrize(
    "sdk_code",
    ("langchain_create_agent", "openai_agents_sdk"),
)
async def test_local_fake_reconciles_valid_complete_logical_model(
    sdk_code: str,
) -> None:
    router = create_agent_execution_router(
        configuration=AgentRuntimeConfiguration(
            mode="fake",
            timeout_seconds=120,
            connections=(),
        ),
        capabilities=load_default_agent_capabilities(),
    )
    source_object = PhysicalObjectKey(
        tenant_code="NWA",
        system_code="CRM",
        connection_code="SOURCE",
        object_schema="bronze",
        object_name="customer_raw",
    )
    source_attribute = PhysicalAttributeKey(
        **source_object.model_dump(),
        attribute_name="customer_id",
    )
    contribution_validator = DetailedLogicalTopologyContributionValidator(
        contribution_ref="object_00001",
        source_object=source_object,
        source_attributes=(source_attribute,),
    )
    contribution = contribution_validator.parse_validated(
        (
            await router.execute(
                _detailed_logical_request(
                    sdk_code=sdk_code,
                    stage="topology_builder",
                    context=cast(
                        JsonValue,
                        {
                            "contribution_ref": "object_00001",
                            "selected_object": {
                                "object": source_object.model_dump(mode="json"),
                                "attributes": [
                                    source_attribute.model_dump(mode="json")
                                ],
                            },
                        },
                    ),
                )
            )
        ).candidate
    )
    topology_validator = DetailedLogicalTopologyReconciliationValidator(
        contributions=(contribution,)
    )
    topology = topology_validator.parse_validated(
        (
            await router.execute(
                _detailed_logical_request(
                    sdk_code=sdk_code,
                    stage="topology_reconciler",
                    context=cast(
                        JsonValue,
                        {"contributions": [contribution.model_dump(mode="json")]},
                    ),
                )
            )
        ).candidate
    )
    detail_validator = DetailedLogicalEntityDetailValidator(
        entity=topology.entities[0],
        topology=topology,
        contributions=(contribution,),
    )
    detail = detail_validator.parse_validated(
        (
            await router.execute(
                _detailed_logical_request(
                    sdk_code=sdk_code,
                    stage="entity_detail_builder",
                    context=cast(
                        JsonValue,
                        {
                            "topology": topology.model_dump(mode="json"),
                            "entity": topology.entities[0].model_dump(mode="json"),
                            "contributions": [contribution.model_dump(mode="json")],
                        },
                    ),
                )
            )
        ).candidate
    )
    relationship_ledger = build_logical_relationship_signal_ledger(
        entity_details=(detail,),
        max_signals=100,
    )
    final_validator = LogicalCandidateValidator(
        selected_object_keys=(source_object,),
        selected_attribute_keys=(source_attribute,),
        assertion_record_keys=(),
        applied=None,
    )
    validator = DetailedLogicalReconciliationValidator(
        topology=topology,
        entity_details=(detail,),
        relationship_signal_refs=relationship_ledger.signal_refs,
        applied_record_refs=(),
        final_validator=final_validator,
    )
    result = await router.execute(
        _detailed_logical_request(
            sdk_code=sdk_code,
            stage="whole_model_reconciliation",
            context=cast(
                JsonValue,
                {
                    "schema_version": "1.0",
                    "model": {"model_name": "private model context"},
                    "topology": topology.model_dump(mode="json"),
                    "entity_details": [detail.model_dump(mode="json")],
                    "relationship_signal_ledger": relationship_ledger.model_dump(
                        mode="json"
                    ),
                    "applied_logical": None,
                    "required_applied_record_refs": [],
                },
            ),
        )
    )

    assert (await validator.validate(result.candidate)).issues == ()
    materialized = validator.materialize_validated(result.candidate)
    assert (await final_validator.validate(materialized)).issues == ()
    assert "private" not in repr(result.candidate)


@pytest.mark.parametrize(
    "sdk_code",
    ("langchain_create_agent", "openai_agents_sdk"),
)
async def test_local_fake_supports_all_dimensional_detailed_stage_contracts(
    sdk_code: str,
) -> None:
    router = create_agent_execution_router(
        configuration=AgentRuntimeConfiguration(
            mode="fake",
            timeout_seconds=120,
            connections=(),
        ),
        capabilities=load_default_agent_capabilities(),
    )
    source_objects = tuple(
        PhysicalObjectKey(
            tenant_code="NWA",
            system_code="CRM",
            connection_code="CURATED",
            object_schema="silver",
            object_name=object_name,
        )
        for object_name in ("customer_curated", "order_curated")
    )
    source_attributes = tuple(
        PhysicalAttributeKey(
            **source_object.model_dump(),
            attribute_name="customer_id",
        )
        for source_object in source_objects
    )

    contributions: list[DetailedDimensionalTopologyContribution] = []
    for position, (source_object, source_attribute) in enumerate(
        zip(source_objects, source_attributes, strict=True),
        start=1,
    ):
        validator = DetailedDimensionalTopologyContributionValidator(
            contribution_ref=f"object_{position:05d}",
            source_object=source_object,
            source_attributes=(source_attribute,),
        )
        outcome = await router.execute(
            _detailed_dimensional_request(
                sdk_code=sdk_code,
                stage="topology_builder",
                context=cast(
                    JsonValue,
                    {
                        "schema_version": "1.0",
                        "model": {"model_name": "private model context"},
                        "contribution_ref": f"object_{position:05d}",
                        "selected_object": {
                            "selection_order": position,
                            "object": {
                                **source_object.model_dump(mode="json"),
                                "object_description": "private object context",
                            },
                            "attributes": [
                                {
                                    **source_attribute.model_dump(mode="json"),
                                    "attribute_description": "private attribute context",
                                }
                            ],
                        },
                    },
                ),
            )
        )
        assert (await validator.validate(outcome.candidate)).issues == ()
        contributions.append(validator.parse_validated(outcome.candidate))

    topology_validator = DetailedDimensionalTopologyReconciliationValidator(
        contributions=tuple(contributions)
    )
    topology_outcome = await router.execute(
        _detailed_dimensional_request(
            sdk_code=sdk_code,
            stage="topology_reconciler",
            context=cast(
                JsonValue,
                {
                    "schema_version": "1.0",
                    "model": {"model_name": "private model context"},
                    "contributions": [
                        item.model_dump(mode="json") for item in contributions
                    ],
                    "applied_dimensional": None,
                },
            ),
        )
    )
    assert (await topology_validator.validate(topology_outcome.candidate)).issues == ()
    topology = topology_validator.parse_validated(topology_outcome.candidate)

    details: list[DetailedDimensionalEntityDetail] = []
    contribution_by_ref = {item.contribution_ref: item for item in contributions}
    for entity in topology.entities:
        relevant = tuple(
            contribution_by_ref[reference.split(".", maxsplit=1)[0]]
            for reference in entity.contribution_refs
        )
        detail_validator = DetailedDimensionalEntityDetailValidator(
            entity=entity,
            topology=topology,
            contributions=tuple(contributions),
        )
        detail_outcome = await router.execute(
            _detailed_dimensional_request(
                sdk_code=sdk_code,
                stage="entity_detail_builder",
                context=cast(
                    JsonValue,
                    {
                        "schema_version": "1.0",
                        "model": {"model_name": "private model context"},
                        "topology": topology.model_dump(mode="json"),
                        "entity": entity.model_dump(mode="json"),
                        "contributions": [
                            item.model_dump(mode="json") for item in relevant
                        ],
                        "selected_objects": [],
                        "assertions": {"records": []},
                    },
                ),
            )
        )
        assert (await detail_validator.validate(detail_outcome.candidate)).issues == ()
        details.append(detail_validator.parse_validated(detail_outcome.candidate))

    relationship_ledger = build_dimensional_relationship_signal_ledger(
        entity_details=tuple(details),
        max_signals=100,
    )
    assert len(relationship_ledger.signals) == 1
    final_validator = _dimensional_validator(
        source_objects=source_objects,
        source_attributes=source_attributes,
    )
    manifest = build_dimensional_draft_manifest(
        topology=topology,
        entity_details=tuple(details),
        relationship_ledger=relationship_ledger,
        applied_record_refs=(),
    )
    receipt_validator = DetailedDimensionalReconciliationReceiptValidator(
        partition_ref="reconciliation_00001",
        manifest=manifest,
        relationship_signals=relationship_ledger.signals,
    )
    receipt_outcome = await router.execute(
        _detailed_dimensional_request(
            sdk_code=sdk_code,
            stage="whole_model_reconciliation",
            context=cast(
                JsonValue,
                {
                    "schema_version": "1.0",
                    "model": {"model_name": "private model context"},
                    "partition_ref": "reconciliation_00001",
                    "review_manifest": manifest.model_dump(mode="json"),
                    "relationship_signals": [
                        item.model_dump(mode="json")
                        for item in relationship_ledger.signals
                    ],
                    "validation_failure_summary": {
                        "finding_count": 0,
                        "findings_digest": "0" * 64,
                        "included_finding_count": 0,
                        "included_findings": [],
                        "is_complete": True,
                    },
                },
            ),
        )
    )
    assert (await receipt_validator.validate(receipt_outcome.candidate)).issues == ()
    receipt = receipt_validator.parse_validated(receipt_outcome.candidate)
    receipt_materialized = materialize_dimensional_reviewed_candidate(
        topology=topology,
        entity_details=tuple(details),
        relationship_ledger=relationship_ledger,
        manifest=manifest,
        receipts=(receipt,),
        applied_record_refs=(),
    )
    assert (await final_validator.validate(receipt_materialized)).issues == ()

    reconciliation_validator = DetailedDimensionalReconciliationValidator(
        topology=topology,
        entity_details=tuple(details),
        relationship_signal_refs=relationship_ledger.signal_refs,
        applied_record_refs=(),
        final_validator=final_validator,
    )
    reconciliation_outcome = await router.execute(
        _detailed_dimensional_request(
            sdk_code=sdk_code,
            stage="whole_model_reconciliation",
            context=cast(
                JsonValue,
                {
                    "schema_version": "1.0",
                    "model": {"model_name": "private model context"},
                    "topology": topology.model_dump(mode="json"),
                    "entity_details": [
                        item.model_dump(mode="json") for item in details
                    ],
                    "relationship_signal_ledger": relationship_ledger.model_dump(
                        mode="json"
                    ),
                    "applied_dimensional": None,
                    "required_applied_record_refs": [],
                },
            ),
        )
    )
    assert (
        await reconciliation_validator.validate(reconciliation_outcome.candidate)
    ).issues == ()
    reconciliation = reconciliation_validator.parse_validated(
        reconciliation_outcome.candidate
    )
    materialized = reconciliation_validator.materialize_validated(
        reconciliation_outcome.candidate
    )
    assert (await final_validator.validate(materialized)).issues == ()
    candidate = cast(dict[str, JsonValue], materialized)
    relationships = cast(list[dict[str, JsonValue]], candidate["relationships"])
    assert relationships[0]["dimensional_relationship_is_optional"] is True
    for attribute in cast(list[dict[str, JsonValue]], candidate["attributes"]):
        assert attribute["dimensional_attribute_role"] not in ("technical", "audit")
        assert attribute["dimensional_attribute_key_role"] not in (
            "surrogate",
            "foreign",
        )

    packages = build_dimensional_validation_packages(
        candidate=reconciliation,
        package_size=100,
        max_packages=100,
    )
    worker_results: list[DetailedDimensionalValidationWorkerResult] = []
    for package in packages:
        worker_validator = DetailedDimensionalValidationWorkerValidator(package=package)
        worker_outcome = await router.execute(
            _detailed_dimensional_request(
                sdk_code=sdk_code,
                stage="validator_worker",
                context=cast(
                    JsonValue,
                    {
                        "schema_version": "1.0",
                        "model": {"model_name": "private model context"},
                        "validation_package": package.model_dump(mode="json"),
                    },
                ),
            )
        )
        assert (await worker_validator.validate(worker_outcome.candidate)).issues == ()
        worker_results.append(
            worker_validator.parse_validated(worker_outcome.candidate)
        )

    lead_validator = DetailedDimensionalValidationLeadValidator(
        worker_results=tuple(worker_results)
    )
    lead_outcome = await router.execute(
        _detailed_dimensional_request(
            sdk_code=sdk_code,
            stage="validator_lead",
            context=cast(
                JsonValue,
                {
                    "schema_version": "1.0",
                    "model": {"model_name": "private model context"},
                    "worker_results": [
                        item.model_dump(mode="json") for item in worker_results
                    ],
                },
            ),
        )
    )
    assert (await lead_validator.validate(lead_outcome.candidate)).issues == ()
    assert "private" not in repr(
        (
            topology_outcome.candidate,
            reconciliation_outcome.candidate,
            lead_outcome.candidate,
        )
    )


@pytest.mark.parametrize(
    "sdk_code",
    ("langchain_create_agent", "openai_agents_sdk"),
)
async def test_local_fake_logical_validator_worker_covers_package(
    sdk_code: str,
) -> None:
    router = create_agent_execution_router(
        configuration=AgentRuntimeConfiguration(
            mode="fake",
            timeout_seconds=120,
            connections=(),
        ),
        capabilities=load_default_agent_capabilities(),
    )
    authored = cast(
        dict[str, JsonValue],
        (await router.execute(_logical_request(sdk_code=sdk_code))).candidate,
    )
    raw_entity = cast(list[JsonValue], authored["entities"])[0]
    entity = LogicalEntityRecord.model_validate_json(
        json.dumps(raw_entity), strict=True
    )
    package = DetailedLogicalValidationPackage(
        package_ref="validation_00001",
        records=(
            DetailedLogicalValidationRecord(
                record_ref="entity:logical entity 1",
                dataset="logical_entity",
                record=entity,
            ),
        ),
    )
    result = await router.execute(
        _detailed_logical_request(
            sdk_code=sdk_code,
            stage="validator_worker",
            context=cast(
                JsonValue,
                {
                    "schema_version": "1.0",
                    "model": {"model_name": "private model context"},
                    "validation_package": package.model_dump(mode="json"),
                },
            ),
        )
    )
    validator = DetailedLogicalValidationWorkerValidator(package=package)

    assert (await validator.validate(result.candidate)).issues == ()
    candidate = cast(dict[str, JsonValue], result.candidate)
    assert candidate["findings"] == []
    assert "private" not in repr(candidate)


@pytest.mark.parametrize(
    "sdk_code",
    ("langchain_create_agent", "openai_agents_sdk"),
)
async def test_local_fake_logical_validator_lead_reconciles_findings(
    sdk_code: str,
) -> None:
    router = create_agent_execution_router(
        configuration=AgentRuntimeConfiguration(
            mode="fake",
            timeout_seconds=120,
            connections=(),
        ),
        capabilities=load_default_agent_capabilities(),
    )
    worker_result = DetailedLogicalValidationWorkerResult(
        package_ref="validation_00001",
        reviewed_record_refs=("entity:logical entity 1",),
        findings=(
            DetailedLogicalValidationFinding(
                finding_ref="validation_00001.finding_00001",
                severity="error",
                code="logical.private_finding",
                message="private worker finding context",
                record_refs=("entity:logical entity 1",),
            ),
        ),
    )
    result = await router.execute(
        _detailed_logical_request(
            sdk_code=sdk_code,
            stage="validator_lead",
            context=cast(
                JsonValue,
                {
                    "schema_version": "1.0",
                    "model": {"model_name": "private model context"},
                    "worker_results": [worker_result.model_dump(mode="json")],
                },
            ),
        )
    )
    validator = DetailedLogicalValidationLeadValidator(worker_results=(worker_result,))

    assert (await validator.validate(result.candidate)).issues == ()
    candidate = cast(dict[str, JsonValue], result.candidate)
    assert candidate["blocking_finding_refs"] == ["validation_00001.finding_00001"]
    assert "private" not in repr(candidate)


@pytest.mark.parametrize(
    "sdk_code",
    ("langchain_create_agent", "openai_agents_sdk"),
)
async def test_local_fake_uses_only_the_tool_assisted_catalog(
    sdk_code: str,
) -> None:
    router = create_agent_execution_router(
        configuration=AgentRuntimeConfiguration(
            mode="fake",
            timeout_seconds=120,
            connections=(),
        ),
        capabilities=load_default_agent_capabilities(),
    )

    result = await router.execute(_tool_assisted_conceptual_request(sdk_code=sdk_code))

    candidate = cast(dict[str, JsonValue], result.candidate)
    objects = cast(list[dict[str, JsonValue]], candidate["objects"])
    supports = cast(list[dict[str, JsonValue]], objects[0]["supports"])
    assert cast(dict[str, JsonValue], supports[0]["source_object"])["object_name"] == (
        "customer_raw"
    )
    assert result.tool_call_count == 2


@pytest.mark.parametrize(
    "sdk_code",
    ("langchain_create_agent", "openai_agents_sdk"),
)
async def test_local_fake_uses_logical_tool_catalog_without_context_echo(
    sdk_code: str,
) -> None:
    router = create_agent_execution_router(
        configuration=AgentRuntimeConfiguration(
            mode="fake",
            timeout_seconds=120,
            connections=(),
        ),
        capabilities=load_default_agent_capabilities(),
    )

    result = await router.execute(_tool_assisted_logical_request(sdk_code=sdk_code))

    assert (await _logical_validator().validate(result.candidate)).issues == ()
    assert "private" not in repr(result.candidate)
    assert result.tool_call_count == 3


@pytest.mark.parametrize(
    "sdk_code",
    ("langchain_create_agent", "openai_agents_sdk"),
)
async def test_local_fake_pages_dimensional_tool_catalog_and_preserves_sources(
    sdk_code: str,
) -> None:
    catalog = _PaginatedDimensionalCatalog()
    router = create_agent_execution_router(
        configuration=AgentRuntimeConfiguration(
            mode="fake",
            timeout_seconds=120,
            connections=(),
        ),
        capabilities=load_default_agent_capabilities(),
    )

    result = await router.execute(
        _tool_assisted_dimensional_request(
            sdk_code=sdk_code,
            catalog=catalog,
        )
    )

    source_objects = tuple(
        PhysicalObjectKey(
            tenant_code="NWA",
            system_code="CRM",
            connection_code="CURATED",
            object_schema="silver",
            object_name=object_name,
        )
        for object_name in ("customer_curated", "order_curated")
    )
    source_attributes = tuple(
        PhysicalAttributeKey(
            **source_object.model_dump(),
            attribute_name="customer_id",
        )
        for source_object in source_objects
    )
    assert (
        await _dimensional_validator(
            source_objects=source_objects,
            source_attributes=source_attributes,
        ).validate(result.candidate)
    ).issues == ()
    assert catalog.calls == [
        ("selected_object", 0),
        ("selected_object", 1),
        ("selected_attribute", 0),
        ("selected_attribute", 1),
    ]
    assert result.tool_call_count == 5
    assert "private" not in repr(result.candidate)


@pytest.mark.parametrize(
    "sdk_code",
    ("langchain_create_agent", "openai_agents_sdk"),
)
async def test_local_fake_returns_bounded_analysis_inference_candidate(
    sdk_code: str,
) -> None:
    router = create_agent_execution_router(
        configuration=AgentRuntimeConfiguration(
            mode="fake",
            timeout_seconds=120,
            connections=(),
        ),
        capabilities=load_default_agent_capabilities(),
    )

    result = await router.execute(_analysis_request(sdk_code=sdk_code))

    assert result.candidate == {
        "relationships": [
            {
                "from_tenant_code": "NWA",
                "from_system_code": "CRM",
                "from_connection_code": "SOURCE",
                "from_object_schema": "bronze",
                "from_object_name": "order_raw",
                "from_attribute_name": "customer_id",
                "to_tenant_code": "NWA",
                "to_system_code": "CRM",
                "to_connection_code": "SOURCE",
                "to_object_schema": "bronze",
                "to_object_name": "customer_raw",
                "to_attribute_name": "customer_id",
                "relationship_kind": "reference",
                "relationship_confidence": "medium",
                "relationship_basis": (
                    "Selected Attribute metadata supports this candidate."
                ),
            }
        ]
    }
    assert "private" not in repr(result)


@pytest.mark.parametrize(
    "sdk_code",
    ("langchain_create_agent", "openai_agents_sdk"),
)
async def test_local_fake_pages_tool_assisted_analysis_context(
    sdk_code: str,
) -> None:
    catalog = _PaginatedDimensionalCatalog()
    router = create_agent_execution_router(
        configuration=AgentRuntimeConfiguration(
            mode="fake",
            timeout_seconds=120,
            connections=(),
        ),
        capabilities=load_default_agent_capabilities(),
    )

    result = await router.execute(
        _tool_assisted_analysis_request(sdk_code=sdk_code, catalog=catalog)
    )

    assert result.candidate == {
        "relationships": [
            {
                "from_tenant_code": "NWA",
                "from_system_code": "CRM",
                "from_connection_code": "CURATED",
                "from_object_schema": "silver",
                "from_object_name": "customer_curated",
                "from_attribute_name": "customer_id",
                "to_tenant_code": "NWA",
                "to_system_code": "CRM",
                "to_connection_code": "CURATED",
                "to_object_schema": "silver",
                "to_object_name": "order_curated",
                "to_attribute_name": "customer_id",
                "relationship_kind": "reference",
                "relationship_confidence": "medium",
                "relationship_basis": (
                    "Selected Attribute metadata supports this candidate."
                ),
            }
        ]
    }
    assert catalog.calls == [
        ("selected_object", 0),
        ("selected_object", 1),
        ("selected_attribute", 0),
        ("selected_attribute", 1),
    ]
    assert result.tool_call_count == 5
    assert "private" not in repr(result)


async def test_local_fake_rejects_unsupported_path_or_malformed_context() -> None:
    router = create_agent_execution_router(
        configuration=AgentRuntimeConfiguration(
            mode="fake",
            timeout_seconds=120,
            connections=(),
        ),
        capabilities=load_default_agent_capabilities(),
    )
    unsupported = _request(sdk_code="langchain_create_agent").model_copy(
        update={"workflow": "logical"}
    )
    malformed = _request(sdk_code="langchain_create_agent").model_copy(
        update={"context": {"original_context": {}, "repair": None}}
    )
    unsupported_dimensional = _detailed_dimensional_request(
        sdk_code="langchain_create_agent",
        stage="unsupported_stage",
        context={},
    )
    malformed_dimensional = _detailed_dimensional_request(
        sdk_code="langchain_create_agent",
        stage="entity_detail_builder",
        context=cast(
            JsonValue,
            {
                "topology": {"submodels": []},
                "entity": {
                    "canonical_entity_ref": "entity_00001",
                    "dimensional_entity_name": "Dimensional Entity 1",
                    "contribution_refs": [[]],
                    "submodel_refs": [],
                },
                "contributions": [{}],
            },
        ),
    )

    for request in (
        unsupported,
        malformed,
        unsupported_dimensional,
        malformed_dimensional,
    ):
        with pytest.raises(WorkbenchError) as captured:
            await router.execute(request)
        assert captured.value.code == "invalid_request"


async def test_remote_runtime_constructs_without_contacting_a_provider() -> None:
    connection = AgentProviderConnection(
        provider_code="databricks",
        model_code="databricks-primary",
        model_endpoint="databricks-gpt-oss-120b",
        timeout_seconds=90,
    )

    router = create_agent_execution_router(
        configuration=AgentRuntimeConfiguration(
            mode="remote",
            timeout_seconds=90,
            connections=(connection,),
        ),
        capabilities=load_default_agent_capabilities(),
    )

    request = _request(sdk_code="langchain_create_agent").model_copy(
        update={
            "selection": AgentRunSelection(
                sdk_code="langchain_create_agent",
                provider_code="openai",
                model_code="databricks-primary",
                reasoning_effort_code="medium",
                max_turns=8,
                validation_retry_count=2,
            )
        }
    )
    with pytest.raises(WorkbenchError) as captured:
        await router.execute(request)

    assert captured.value.code == "invalid_request"


async def test_remote_foundry_runtime_constructs_without_provider_io() -> None:
    connection = AgentProviderConnection(
        provider_code="microsoft_foundry",
        model_code="foundry-primary",
        model_endpoint="gpt-5.6-sol",
        timeout_seconds=90,
        openai_base_url="https://fixture.openai.azure.com/openai/v1/",
        token_scope="https://cognitiveservices.azure.com/.default",
        foundry_client_credentials=FoundryClientCredentials(
            tenant_id=UUID("11111111-1111-1111-1111-111111111111"),
            client_id=UUID("22222222-2222-2222-2222-222222222222"),
            client_secret=SecretStr("never-log-this-foundry-client-secret"),
        ),
    )

    router = create_agent_execution_router(
        configuration=AgentRuntimeConfiguration(
            mode="remote",
            timeout_seconds=90,
            connections=(connection,),
        ),
        capabilities=load_default_agent_capabilities(),
    )

    with pytest.raises(WorkbenchError) as captured:
        await router.execute(_request(sdk_code="langchain_create_agent"))

    assert captured.value.code == "invalid_request"
    assert "never-log-this-foundry-client-secret" not in repr(router)


async def test_remote_foundry_api_key_runtime_constructs_without_provider_io() -> None:
    connection = AgentProviderConnection(
        provider_code="microsoft_foundry",
        model_code="foundry-primary",
        model_endpoint="gpt-5.6-sol",
        timeout_seconds=90,
        openai_base_url="https://fixture.services.ai.azure.com/openai/v1/",
        foundry_api_key=SecretStr("never-log-this-foundry-api-key"),
    )

    router = create_agent_execution_router(
        configuration=AgentRuntimeConfiguration(
            mode="remote",
            timeout_seconds=90,
            connections=(connection,),
        ),
        capabilities=load_default_agent_capabilities(),
    )

    with pytest.raises(WorkbenchError) as captured:
        await router.execute(_request(sdk_code="langchain_create_agent"))

    assert captured.value.code == "invalid_request"
    assert "never-log-this-foundry-api-key" not in repr(router)
