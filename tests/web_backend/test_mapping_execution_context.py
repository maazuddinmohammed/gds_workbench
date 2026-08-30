from __future__ import annotations

import json
from hashlib import sha256
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
from gds_workbench_api.features.mapping.preparation_contracts import (
    ExistingMappingAttribute,
    MappingPreparation,
)
from gds_workbench_api.features.workflows.authoring.agent_execution import (
    AgentContextToolResultTooLargeError,
)
from gds_workbench_api.features.workflows.authoring.context import (
    AgentContextToolRequestError,
    AgentContextUnavailableError,
)
from gds_workbench_api.features.workflows.authoring.plan import WorkflowExecutionMode


def _limits(**updates: int) -> MappingExecutionContextLimits:
    return MappingExecutionContextLimits(
        max_tool_result_bytes=updates.get("max_tool_result_bytes", 128 * 1024),
        max_tool_transcript_bytes=updates.get(
            "max_tool_transcript_bytes",
            256 * 1024,
        ),
        max_tool_catalog_bytes=updates.get("max_tool_catalog_bytes", 512 * 1024),
        max_tool_page_records=updates.get("max_tool_page_records", 20),
    )


def _five_thousand_attribute_preparation() -> MappingPreparation:
    preparation = _preparation()
    target_seed = preparation.context.target.attributes[0]
    source_seed = preparation.context.sources[0].object.attributes[0]
    modeled_seed = preparation.context.headers[0].modeled_entity.attributes[0]
    target_attributes = tuple(
        target_seed.model_copy(
            update={
                "attribute_id": 10_000 + index,
                "attribute_name": f"target_{index:04d}",
                "attribute_ordinal_position": index + 1,
                "attribute_description": "t" * 600,
            }
        )
        for index in range(5_000)
    )
    source_attributes = tuple(
        source_seed.model_copy(
            update={
                "attribute_id": 20_000 + index,
                "attribute_name": f"source_{index:04d}",
                "attribute_ordinal_position": index + 1,
                "attribute_description": "s" * 600,
            }
        )
        for index in range(5_000)
    )
    modeled_attributes = tuple(
        modeled_seed.model_copy(
            update={
                "attribute_id": 30_000 + index,
                "attribute_name": f"modeled_{index:04d}",
                "ordinal_position": index + 1,
                "attribute_definition": "m" * 600,
            }
        )
        for index in range(5_000)
    )
    source = preparation.context.sources[0]
    header = preparation.context.headers[0]
    context = preparation.context.model_copy(
        update={
            "target": preparation.context.target.model_copy(
                update={"attributes": target_attributes}
            ),
            "sources": (
                source.model_copy(
                    update={
                        "object": source.object.model_copy(
                            update={"attributes": source_attributes}
                        )
                    }
                ),
            ),
            "headers": (
                header.model_copy(
                    update={
                        "modeled_entity": header.modeled_entity.model_copy(
                            update={"attributes": modeled_attributes}
                        )
                    }
                ),
            ),
        }
    )
    return preparation.model_copy(update={"context": context})


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

    target_page = cast(
        dict[str, JsonValue],
        catalog.invoke(
            "get_mapping_context_dataset",
            {"dataset": "target", "offset": 0, "limit": 1},
        ),
    )
    target = cast(list[dict[str, JsonValue]], target_page["items"])[0]
    assert target["attributes"] == []

    source_page = cast(
        dict[str, JsonValue],
        catalog.invoke(
            "get_mapping_context_dataset",
            {"dataset": "source", "offset": 0, "limit": 1},
        ),
    )
    source = cast(list[dict[str, JsonValue]], source_page["items"])[0]
    source_object = cast(dict[str, JsonValue], source["object"])
    assert source_object["attributes"] == []

    header_page = cast(
        dict[str, JsonValue],
        catalog.invoke(
            "get_mapping_context_dataset",
            {"dataset": "header", "offset": 0, "limit": 1},
        ),
    )
    header = cast(list[dict[str, JsonValue]], header_page["items"])[0]
    header_entity = cast(dict[str, JsonValue], header["modeled_entity"])
    assert header_entity["attributes"] == []
    assert header["attribute_mappings"] == []

    modeled_entity_page = cast(
        dict[str, JsonValue],
        catalog.invoke(
            "get_mapping_context_dataset",
            {"dataset": "modeled_entity", "offset": 0, "limit": 1},
        ),
    )
    modeled_entity = cast(list[dict[str, JsonValue]], modeled_entity_page["items"])[0]
    assert modeled_entity["attributes"] == []


def test_mapping_tool_pages_shrink_by_bytes_without_skipping_records() -> None:
    preparation = _preparation()
    target_attribute = preparation.context.target.attributes[0]
    attributes = tuple(
        target_attribute.model_copy(
            update={
                "attribute_id": 901 + index,
                "attribute_name": f"attribute_{index}",
                "attribute_ordinal_position": index + 1,
                "attribute_description": "x" * 900,
            }
        )
        for index in range(3)
    )
    context = preparation.context.model_copy(
        update={
            "target": preparation.context.target.model_copy(
                update={"attributes": attributes}
            )
        }
    )
    preparation = preparation.model_copy(update={"context": context})
    catalog = build_mapping_execution_context(
        preparation=preparation,
        execution_mode="tool_assisted",
        limits=_limits(max_tool_result_bytes=1_500, max_tool_page_records=3),
    ).tool_catalog
    assert isinstance(catalog, InMemoryMappingContextToolCatalog)

    seen_ids: list[int] = []
    offset = 0
    while True:
        page = cast(
            dict[str, JsonValue],
            catalog.invoke(
                "get_mapping_context_dataset",
                {"dataset": "target_attribute", "offset": offset, "limit": 3},
            ),
        )
        items = cast(list[dict[str, JsonValue]], page["items"])
        assert len(items) == 1
        seen_ids.extend(cast(int, item["attribute_id"]) for item in items)
        next_offset = page["next_offset"]
        if next_offset is None:
            break
        assert next_offset == offset + len(items)
        offset = cast(int, next_offset)

    assert seen_ids == [901, 902, 903]


def test_mapping_tool_catalog_fragments_and_reconstructs_one_oversized_record() -> None:
    existing = ExistingMappingAttribute(
        mapping_attribute_id=990,
        modeled_attribute_id=701,
        target_attribute_id=901,
        transformation_document={"expression": "é" * 20_000},
        status="active",
        is_locked=False,
        agent_run_id=None,
        workflow_run_id=None,
        output_template_id=None,
    )
    catalog = build_mapping_execution_context(
        preparation=_preparation(existing=existing),
        execution_mode="tool_assisted",
        limits=_limits(
            max_tool_result_bytes=2_000,
            max_tool_catalog_bytes=512 * 1024,
            max_tool_page_records=20,
        ),
    ).tool_catalog
    assert isinstance(catalog, InMemoryMappingContextToolCatalog)

    fragments: list[dict[str, JsonValue]] = []
    offset = 0
    while True:
        page = cast(
            dict[str, JsonValue],
            catalog.invoke(
                "get_mapping_context_dataset",
                {
                    "dataset": "existing_mapping_attribute",
                    "offset": offset,
                    "limit": 20,
                },
            ),
        )
        fragments.extend(cast(list[dict[str, JsonValue]], page["items"]))
        next_offset = page["next_offset"]
        if next_offset is None:
            break
        offset = cast(int, next_offset)

    metadata = [
        cast(dict[str, JsonValue], item["__gds_context_fragment__"])
        for item in fragments
    ]
    assert [item["fragment_index"] for item in metadata] == list(range(len(fragments)))
    assert all(item["fragment_count"] == len(fragments) for item in metadata)
    text = "".join(cast(str, item["json_text"]) for item in fragments)
    digest = sha256(text.encode("utf-8")).hexdigest()
    assert all(item["record_sha256"] == digest for item in metadata)
    assert json.loads(text)["transformation_document"] == {"expression": "é" * 20_000}


def test_mapping_tool_catalog_exposes_conservative_per_execution_allowance() -> None:
    preparation = _preparation()
    catalog = build_mapping_execution_context(
        preparation=preparation,
        execution_mode="tool_assisted",
        limits=_limits(max_tool_result_bytes=1_500),
    ).tool_catalog
    assert isinstance(catalog, InMemoryMappingContextToolCatalog)

    assert catalog.max_result_bytes == 1_500
    assert catalog.max_cumulative_result_bytes == 256 * 1024


def test_default_mapping_tool_catalog_accepts_legal_five_thousand_attribute_input() -> (
    None
):
    result = build_mapping_execution_context(
        preparation=_five_thousand_attribute_preparation(),
        execution_mode="tool_assisted",
    )

    catalog = result.tool_catalog
    assert isinstance(catalog, InMemoryMappingContextToolCatalog)
    assert catalog.serialized_size_bytes > 10 * 1024 * 1024
    assert catalog.serialized_size_bytes <= 128 * 1024 * 1024
    assert cast(dict[str, JsonValue], result.embedded_context)["workflow"] == "mapping"


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


def test_detailed_mapping_context_defers_to_bounded_stage_slices() -> None:
    result = build_mapping_execution_context(
        preparation=_preparation(),
        execution_mode="detailed_coverage",
        limits=_limits(),
    )

    assert result.tool_catalog is None
    assert result.embedded_context is None


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
