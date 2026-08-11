from __future__ import annotations

import json
from dataclasses import replace

import pytest

from gds_etl_workbench.tools.snapshots.metadata.archive import (
    EncodedDataset,
    SnapshotContractError,
    build_root_documents,
    encode_dataset,
)
from gds_etl_workbench.tools.snapshots.metadata.contracts import DATASETS


def empty_datasets() -> tuple[EncodedDataset, ...]:
    return tuple(encode_dataset(definition, []) for definition in DATASETS)


def test_root_documents_are_complete_deterministic_and_row_free() -> None:
    encoded = empty_datasets()
    first = build_root_documents(encoded)
    second = build_root_documents(tuple(reversed(encoded)))

    assert first == second
    assert first.schema_json.endswith(b"\n")
    assert first.index_json.endswith(b"\n")
    schema = json.loads(first.schema_json)
    index = json.loads(first.index_json)
    assert len(schema["datasets"]) == 29
    assert [section["name"] for section in index["sections"]] == [
        "foundation",
        "metadata",
    ]
    assert [len(section["datasets"]) for section in index["sections"]] == [13, 16]
    assert all(
        dataset["row_count"] == 0
        for section in index["sections"]
        for dataset in section["datasets"]
    )
    assert b'"rows"' not in first.schema_json
    assert b'"rows"' not in first.index_json
    assert b'"sha256"' not in first.schema_json
    assert b'"sha256"' not in first.index_json


def test_root_index_contains_agent_navigation_paths() -> None:
    index = json.loads(build_root_documents(empty_datasets()).index_json)
    source_objects = next(
        dataset
        for section in index["sections"]
        for dataset in section["datasets"]
        if dataset["name"] == "source_object"
    )

    assert source_objects == {
        "name": "source_object",
        "label": "Source Objects",
        "row_count": 0,
        "data_path": "metadata/core/source_object/rows.jsonl",
        "table_index_path": "metadata/core/source_object/index.jsonl",
        "primary_key": ["object_id"],
        "display_columns": ["object_schema", "object_name"],
    }
    assert index["instructions"] == [
        "Read manifest.json and index.json first.",
        "Do not recursively load the snapshot into context.",
        "Search a dataset's index.jsonl, then read only the located line from rows.jsonl.",
    ]


def test_root_documents_reject_missing_duplicate_or_changed_datasets() -> None:
    encoded = empty_datasets()

    with pytest.raises(SnapshotContractError, match="fixed snapshot registry"):
        build_root_documents(encoded[:-1])
    with pytest.raises(SnapshotContractError, match="duplicate encoded dataset"):
        build_root_documents((*encoded, encoded[0]))
    with pytest.raises(SnapshotContractError, match="does not match the registry"):
        build_root_documents(
            (
                replace(
                    encoded[0],
                    definition=replace(encoded[0].definition, label="Changed"),
                ),
                *encoded[1:],
            )
        )
