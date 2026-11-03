"""Validation's frozen System-wide evidence must not replay each candidate catalog per target."""

import json
from copy import deepcopy
from typing import Any

import pytest
from atlas_platform.features.workflows.authoring.agent_execution import (
    AgentContextToolResultTooLargeError,
)
from atlas_platform.features.workflows.authoring.context import (
    AgentContextToolRequestError,
)
from atlas_platform.features.workflows.authoring.downstream_inputs import (
    build_downstream_readers,
    project_downstream_inputs,
)

from tests.web_backend.test_downstream_prompt_inputs import FIXTURE


def test_wide_system_ledger_pages_shared_sources_once_and_retains_differing_values() -> (
    None
):
    values = project_downstream_inputs("validation", deepcopy(FIXTURE["validation"]))
    original = values["mapping_evidence"][0]
    sources: list[dict[str, Any]] = []
    for i in range(16):
        source = deepcopy(original["context"]["source_metadata"][0])
        source["role"] = "candidate"
        obj = source["object"]
        obj["object_name"] = f"catalog_{i}"
        obj["attributes"] = [
            {**obj["attributes"][0], "attribute_name": f"field_{j}"} for j in range(32)
        ]
        sources.append(source)
    targets: list[dict[str, Any]] = []
    for n in range(12):
        target = deepcopy(original)
        target["modeled_entity_name"] = f"Target{n}"
        ctx = target["context"]
        ctx["target_metadata"]["object_name"] = target["modeled_entity_name"]
        ctx["source_metadata"] = deepcopy(sources)
        for row in ctx["attribute_transformations"]:
            row["modeled_entity_name"] = target["modeled_entity_name"]
        targets.append(target)
    # Same physical coordinates can carry different frozen evidence. Never merge the versions.
    targets[-1]["context"]["source_metadata"][-1]["object"]["attributes"][-1][
        "attribute_description"
    ] = "different"
    values["mapping_evidence"] = targets
    first_artifact = values["current_code"][0]
    second_artifact = {
        **first_artifact,
        "modeled_entity_name": "OtherTarget",
        "generated_code_content": "SELECT 2",
    }
    values["current_code"].append(second_artifact)
    readers = build_downstream_readers(
        "validation",
        values,
        max_result_bytes=8_192,
        max_page_records=200,
        max_cumulative_result_bytes=None,
    )
    with pytest.raises(AgentContextToolResultTooLargeError):
        readers.invoke("get_mapping_evidence", {})

    def collect(args: dict[str, Any]) -> list[Any]:
        pages: list[Any] = []
        while True:
            page = readers.invoke("get_validation_basis", args)
            pages.extend(page["items"])
            if page["is_complete"]:
                return pages
            args = {"cursor": page["next_cursor"]}

    core = collect({})
    assert len([r for r in core if r["kind"] == "target"]) == 12
    assert len([r for r in core if r["kind"] == "source"]) == 17
    assert not any(r["kind"] == "source_attribute" for r in core)
    assert len(json.dumps(core)) < len(json.dumps(targets)) // 10
    target_rules = [
        r["record"]
        for r in collect({"detail_refs": ["t12"]})
        if r["kind"] == "attribute_transformation"
    ]
    assert target_rules == targets[-1]["context"]["attribute_transformations"]
    artifact_headers = [r["record"] for r in core if r["kind"] == "code_header"]
    assert artifact_headers == [
        {k: v for k, v in row.items() if k != "generated_code_content"}
        for row in values["current_code"]
    ]
    artifact_key = {
        key: second_artifact[key]
        for key in (
            "modeled_entity_type",
            "modeled_entity_schema_name",
            "modeled_entity_name",
            "artifact_name",
        )
    }
    assert readers.invoke("get_current_code", {"artifact_keys": [artifact_key]})[
        "items"
    ] == [second_artifact]
    assert [r["record"] for r in core if r["kind"] == "applied_group"] == values[
        "applied_groups"
    ]
    saved_header = next(r for r in core if r["kind"] == "applied_check")
    assert "validation_query_sql" not in saved_header["record"]
    assert (
        collect({"detail_refs": [saved_header["ref"]]})[0]["record"]
        == values["applied_checks"][0]
    )
    last_source = [r for r in core if r["kind"] == "source"][-1]["ref"]
    field_name = target_rules[0]["target_attribute_name"]
    selected = collect(
        {"detail_refs": [f"t12:{field_name}", f"{last_source}:field_31", "t12.o1"]}
    )
    assert [
        r["record"] for r in selected if r["kind"] == "attribute_transformation"
    ] == target_rules
    assert [r["record"] for r in selected if r["kind"] == "source_attribute"] == [
        targets[-1]["context"]["source_metadata"][-1]["object"]["attributes"][-1]
    ]
    assert [
        r["record"]["transformation"]
        for r in selected
        if r["kind"] == "object_transformation"
    ] == [targets[-1]["context"]["object_transformations"][0]["transformation"]]
    with pytest.raises(AgentContextToolRequestError):
        readers.invoke("get_validation_basis", {"detail_refs": ["t12:UnknownField"]})
    cols = collect({"detail_refs": [last_source]})
    assert [r["record"] for r in cols] == targets[-1]["context"]["source_metadata"][-1][
        "object"
    ]["attributes"]
    with pytest.raises(AgentContextToolRequestError):
        readers.invoke("get_validation_basis", {"detail_refs": ["unknown"]})
