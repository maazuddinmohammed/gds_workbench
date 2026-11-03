"""SQL authoring reads only the source coordinates and columns its Mapping needs."""

from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path
from typing import Any, cast

import pytest
from atlas_platform.features.workflows.authoring.agent_execution import AgentContextToolRequestError
from atlas_platform.features.workflows.authoring.context_inputs import OBJECT_FIELDS
from atlas_platform.features.workflows.authoring.downstream_inputs import build_downstream_readers
from jsonschema import Draft202012Validator


def _source_inputs(count: int, width: int) -> dict[str, Any]:
    values = json.loads((Path(__file__).parent / "fixtures/code_review_example.json").read_text())[
        "inputs"
    ]
    original = values["source_metadata"][0]
    sources: list[dict[str, Any]] = []
    for i in range(count):
        row = deepcopy(original)
        row["role"] = "support" if i == 0 else "candidate"
        obj = row["object"]
        obj["object_name"] = f"feed_{i}"
        obj["attributes"] = [
            {**obj["attributes"][0], "attribute_name": f"field_{j:03d}"} for j in range(width)
        ]
        sources.append(row)
    values["source_metadata"] = sources
    return values


def test_mapped_sources_and_columns_can_be_read_without_unrelated_candidate_columns() -> None:
    values = _source_inputs(41, 80)
    reader = build_downstream_readers(
        "code_generation",
        values,
        max_result_bytes=None,
        max_page_records=200,
        max_cumulative_result_bytes=None,
    )
    directory = reader.invoke("get_code_sources", {"directory_only": True})
    rows = directory["items"]
    assert directory["is_complete"] and len(rows) == 41
    assert all(row["object"]["attributes"] == [] for row in rows)
    chosen = {key: rows[-1]["object"][key] for key in OBJECT_FIELDS}
    selected = reader.invoke(
        "get_code_sources",
        {"source_object_keys": [{**chosen, "attribute_names": ["field_077", "field_002"]}]},
    )
    assert selected["is_complete"]
    result = selected["items"][0]["object"]
    assert result["object_name"] == "feed_40"
    assert [a["attribute_name"] for a in result["attributes"]] == ["field_002", "field_077"]
    full_bytes = len(json.dumps(values["source_metadata"]))
    assert len(json.dumps([directory, selected])) < full_bytes // 10
    with pytest.raises(AgentContextToolRequestError):
        reader.invoke(
            "get_code_sources", {"source_object_keys": [{**chosen, "attribute_names": ["absent"]}]}
        )
    with pytest.raises(AgentContextToolRequestError):
        reader.invoke(
            "get_code_sources", {"source_object_keys": [{**chosen, "connection_code": "different"}]}
        )


@pytest.mark.parametrize("page_bytes", [None, 2200])
def test_wide_code_sources_are_paged_losslessly_for_existing_readers(
    page_bytes: int | None,
) -> None:
    values = _source_inputs(3, 40)
    reader = build_downstream_readers(
        "code_generation",
        values,
        max_result_bytes=page_bytes,
        max_page_records=7,
        max_cumulative_result_bytes=None,
    )
    page = reader.invoke("get_code_sources", {})
    expected = {
        row["object"]["object_name"]: row["object"]["attributes"]
        for row in values["source_metadata"]
    }
    collected: dict[str, list[Any]] = {name: [] for name in expected}
    assert page["next_cursor"] is not None
    definition = next(item for item in reader.definitions if item.name == "get_code_sources")
    assert definition.result_schema is not None
    result_schema = cast(Any, Draft202012Validator(definition.result_schema))
    with pytest.raises(AgentContextToolRequestError):
        reader.invoke("get_code_sources", {"directory_only": True, "cursor": page["next_cursor"]})
    while True:
        assert result_schema.is_valid(page)
        assert sum(len(row["object"]["attributes"]) for row in page["items"]) <= 7
        if page_bytes is not None:
            assert len(json.dumps(page, separators=(",", ":")).encode()) <= page_bytes
        for row in page["items"]:
            obj = row["object"]
            collected[obj["object_name"]].extend(obj["attributes"])
        if page["is_complete"]:
            break
        page = reader.invoke("get_code_sources", {"cursor": page["next_cursor"]})
    assert collected == expected
