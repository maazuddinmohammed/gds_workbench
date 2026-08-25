from __future__ import annotations

from typing import cast

import pytest
from pydantic import JsonValue
from test_mapping_attribute_candidate import (
    _preparation,  # pyright: ignore[reportPrivateUsage]
)

from gds_workbench_api.features.mapping.execution_context import (
    InMemoryMappingContextToolCatalog,
    MappingExecutionContextLimits,
    build_mapping_execution_context,
)
from gds_workbench_api.features.workflows.authoring.context import (
    AgentContextToolRequestError,
    AgentContextToolResultTooLargeError,
    AgentContextUnavailableError,
)
from gds_workbench_api.features.workflows.authoring.plan import WorkflowExecutionMode


def _limits(**updates: int) -> MappingExecutionContextLimits:
    return MappingExecutionContextLimits(
        max_tool_result_bytes=updates.get("max_tool_result_bytes", 128 * 1024),
        max_tool_catalog_bytes=updates.get("max_tool_catalog_bytes", 512 * 1024),
        max_tool_page_records=updates.get("max_tool_page_records", 20),
    )


def test_embedded_mapping_context_is_complete_but_never_contains_prompts() -> None:
    preparation = _preparation()

    result = build_mapping_execution_context(
        preparation=preparation,
        execution_mode="one_shot",
        limits=_limits(),
    )

    assert result.tool_catalog is None
    context = cast(dict[str, JsonValue], result.embedded_context)
    assert context["schema_version"] == "1.0"
    run = cast(dict[str, JsonValue], context["run"])
    assert run["workflow_run_id"] == 1048
    assert run["pair"] == {"target_object_id": 501, "source_system_id": 31}
    assert context["target"] == preparation.context.target.model_dump(mode="json")
    assert context["headers"] == [
        item.model_dump(mode="json") for item in preparation.context.headers
    ]
    serialized = str(context)
    assert "agent_plan" not in serialized
    assert "system_prompt_template" not in serialized
    assert "instruction_prompt_template" not in serialized


def test_tool_assisted_mapping_context_is_manifest_plus_bounded_local_pages() -> None:
    result = build_mapping_execution_context(
        preparation=_preparation(),
        execution_mode="tool_assisted",
        limits=_limits(max_tool_page_records=1),
    )

    catalog = result.tool_catalog
    assert isinstance(catalog, InMemoryMappingContextToolCatalog)
    assert result.embedded_context == catalog.manifest
    assert catalog.allowed_tool_names == (
        "get_mapping_context_manifest",
        "get_mapping_context_dataset",
    )
    manifest = cast(dict[str, JsonValue], catalog.manifest)
    assert manifest["workflow"] == "mapping"
    datasets = cast(list[dict[str, JsonValue]], manifest["datasets"])
    assert {cast(str, item["name"]) for item in datasets} >= {
        "target",
        "source",
        "header",
        "target_attribute",
        "modeled_attribute",
    }

    page = cast(
        dict[str, JsonValue],
        catalog.invoke(
            "get_mapping_context_dataset",
            {"dataset": "target_attribute", "offset": 0, "limit": 1},
        ),
    )
    assert page["offset"] == 0
    assert len(cast(list[JsonValue], page["items"])) == 1
    assert "raw prompt" not in repr(catalog).lower()


def test_mapping_tool_catalog_rejects_unbounded_or_unknown_requests() -> None:
    catalog = build_mapping_execution_context(
        preparation=_preparation(),
        execution_mode="tool_assisted",
        limits=_limits(max_tool_page_records=1),
    ).tool_catalog
    assert isinstance(catalog, InMemoryMappingContextToolCatalog)

    with pytest.raises(AgentContextToolRequestError):
        catalog.invoke(
            "get_mapping_context_dataset",
            {"dataset": "target_attribute", "offset": 0, "limit": 2},
        )
    with pytest.raises(AgentContextToolRequestError):
        catalog.invoke("read_database", {})

    tiny = build_mapping_execution_context(
        preparation=_preparation(),
        execution_mode="tool_assisted",
        limits=_limits(max_tool_result_bytes=1),
    ).tool_catalog
    assert isinstance(tiny, InMemoryMappingContextToolCatalog)
    with pytest.raises(AgentContextToolResultTooLargeError):
        tiny.invoke("get_mapping_context_manifest", {})


def test_detailed_mapping_context_is_embedded_without_local_tools() -> None:
    result = build_mapping_execution_context(
        preparation=_preparation(),
        execution_mode="detailed_coverage",
        limits=_limits(),
    )

    assert result.tool_catalog is None
    assert cast(dict[str, JsonValue], result.embedded_context)["workflow"] == "mapping"


@pytest.mark.parametrize(
    "execution_mode",
    ["one_shot", "tool_assisted", "detailed_coverage"],
)
@pytest.mark.parametrize(
    "unsafe_document",
    [
        {"api_key": "must-never-reach-provider"},
        {"notes": "Bearer must-never-reach-provider"},
        {"notes": "raw tool output from a prior run"},
    ],
)
def test_mapping_context_rejects_nested_sensitive_keys_and_values(
    execution_mode: WorkflowExecutionMode,
    unsafe_document: dict[str, JsonValue],
) -> None:
    preparation = _preparation()
    authoring = preparation.context.authoring.model_copy(
        update={"audit_columns_template": unsafe_document}
    )
    context = preparation.context.model_copy(update={"authoring": authoring})
    preparation = preparation.model_copy(update={"context": context})

    with pytest.raises(AgentContextUnavailableError):
        build_mapping_execution_context(
            preparation=preparation,
            execution_mode=execution_mode,
            limits=_limits(),
        )
