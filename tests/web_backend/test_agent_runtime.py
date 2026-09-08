from __future__ import annotations

from collections.abc import Mapping
from typing import cast
from uuid import UUID

import pytest
from gds_etl_workbench.domain.errors import WorkbenchError
from gds_etl_workbench.domain.modeling_records import (
    PhysicalAttributeKey,
    PhysicalObjectKey,
)
from gds_workbench_api.capabilities import (
    AgentModelExecutionProfile,
    AgentRunSelection,
    load_default_agent_capabilities,
)
from gds_workbench_api.features.dimensional.candidate import (
    DimensionalCandidateValidator,
)
from gds_workbench_api.features.logical.candidate import LogicalCandidateValidator
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
from gds_workbench_api.integrations.agents import (
    create_agent_execution_router,
)
from gds_workbench_api.integrations.agents.configuration import (
    AgentProviderConnection,
    AgentRuntimeConfiguration,
    FoundryClientCredentials,
)
from mapping_fixtures import mapping_preparation as _mapping_preparation
from pydantic import JsonValue, SecretStr


def _selection(*, sdk_code: str) -> AgentRunSelection:
    return AgentRunSelection(
        sdk_code=sdk_code,
        provider_code="microsoft_foundry",
        model_code="foundry-primary",
        reasoning_effort_code="none",
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
        model for model in registry.models if model.code == "foundry-primary"
    )
    restricted = databricks_model.model_copy(
        update={
            "execution_profiles": (
                AgentModelExecutionProfile(
                    sdk_code="openai_agents_sdk",
                    execution_mode="tool_assisted",
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
        await router.execute(_request(sdk_code="openai_agents_sdk"))


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


@pytest.mark.parametrize(
    "sdk_code",
    ("openai_agents_sdk",),
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
    ("openai_agents_sdk",),
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
    assert "get_existing_mapping" in {name for name, _ in catalog.calls}
    for tool, nested_field in (
        ("get_mapping_target", "attributes"),
        ("get_existing_mapping", "attribute_mappings"),
    ):
        page = cast(dict[str, JsonValue], catalog.delegate.invoke(tool, {}))
        parent = cast(list[dict[str, JsonValue]], page["items"])[0]
        assert parent[nested_field]
        assert "object_id" not in parent
    page = cast(
        dict[str, JsonValue], catalog.delegate.invoke("get_mapping_sources", {})
    )
    source = cast(list[dict[str, JsonValue]], page["items"])[0]
    assert cast(dict[str, JsonValue], source["object"])["attributes"]


@pytest.mark.parametrize(
    "sdk_code",
    ("openai_agents_sdk",),
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
    ("openai_agents_sdk",),
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
    ("openai_agents_sdk",),
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
    ("openai_agents_sdk",),
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
    ("openai_agents_sdk",),
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
    ("openai_agents_sdk",),
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
    ("openai_agents_sdk",),
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
    ("openai_agents_sdk",),
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
    ("openai_agents_sdk",),
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
    unsupported = _request(sdk_code="openai_agents_sdk").model_copy(
        update={"workflow": "logical"}
    )
    malformed = _request(sdk_code="openai_agents_sdk").model_copy(
        update={"context": {"original_context": {}, "repair": None}}
    )

    for request in (
        unsupported,
        malformed,
    ):
        with pytest.raises(WorkbenchError) as captured:
            await router.execute(request)
        assert captured.value.code == "invalid_request"


async def test_remote_runtime_constructs_without_contacting_a_provider() -> None:
    connection = AgentProviderConnection(
        provider_code="microsoft_foundry",
        model_code="foundry-primary",
        model_endpoint="gpt-5.6-sol",
        openai_base_url="https://fixture.services.ai.azure.com/openai/v1/",
        foundry_api_key=SecretStr("fixture-key"),
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

    request = _request(sdk_code="openai_agents_sdk").model_copy(
        update={
            "selection": AgentRunSelection(
                sdk_code="openai_agents_sdk",
                provider_code="openai",
                model_code="foundry-primary",
                reasoning_effort_code="none",
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
        await router.execute(_request(sdk_code="unsupported_sdk"))

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
        await router.execute(_request(sdk_code="unsupported_sdk"))

    assert captured.value.code == "invalid_request"
    assert "never-log-this-foundry-api-key" not in repr(router)
