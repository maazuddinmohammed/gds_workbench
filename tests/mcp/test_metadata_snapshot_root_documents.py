from __future__ import annotations

import json
from dataclasses import replace
from typing import Any, cast

import pytest

from gds_etl_workbench.tools.snapshots.metadata.archive import (
    EncodedDataset,
    SnapshotContractError,
    build_root_documents,
    encode_dataset,
)
from gds_etl_workbench.domain.snapshots.metadata import DATASETS


def empty_datasets() -> tuple[EncodedDataset, ...]:
    return tuple(encode_dataset(definition, []) for definition in DATASETS)


def test_root_documents_are_complete_deterministic_and_row_free() -> None:
    encoded = empty_datasets()
    first = build_root_documents(encoded)
    second = build_root_documents(tuple(reversed(encoded)))

    assert first == second
    assert first.catalog_json.endswith(b"\n")
    assert len(first.schemas) == 28
    assert all(content.endswith(b"\n") for _path, content in first.schemas)
    catalog = json.loads(first.catalog_json)
    assert [section["name"] for section in catalog["sections"]] == [
        "foundational",
        "reference",
        "operational",
    ]
    assert [len(section["datasets"]) for section in catalog["sections"]] == [4, 8, 16]
    assert all(
        dataset["row_count"] == 0
        for section in catalog["sections"]
        for dataset in section["datasets"]
    )
    assert b'"rows"' not in first.catalog_json
    assert b'"sha256"' not in first.catalog_json


def test_catalog_contains_agent_navigation_without_duplicate_rows() -> None:
    catalog = cast(
        dict[str, Any], json.loads(build_root_documents(empty_datasets()).catalog_json)
    )
    source_objects = next(
        dataset
        for section in catalog["sections"]
        for dataset in section["datasets"]
        if dataset["name"] == "source_object"
    )
    projects = next(
        dataset
        for section in catalog["sections"]
        for dataset in section["datasets"]
        if dataset["name"] == "project"
    )

    assert source_objects == {
        "name": "source_object",
        "label": "Source Objects",
        "record_type": "object",
        "row_count": 0,
        "canonical_key": [
            "tenant_code",
            "system_code",
            "connection_code",
            "object_schema",
            "object_name",
        ],
        "search_fields": [
            "tenant_code",
            "system_code",
            "connection_code",
            "object_schema",
            "object_name",
            "source_tenant_code",
            "object_type_code",
            "zone_code",
            "is_locked",
            "is_active",
        ],
        "schema_file": "schemas/source_object.schema.json",
        "search_file": "data/operational/source_object/lookup.jsonl",
        "rows_file": "data/operational/source_object/rows.jsonl",
        "search_result_complete": False,
    }
    assert projects["search_file"] == projects["rows_file"]
    assert projects["search_result_complete"] is True
    assert catalog["record_groups"] == [
        {
            "name": "objects",
            "datasets": [
                "source_object",
                "bronze_object",
                "silver_object",
                "gold_object",
            ],
        },
        {
            "name": "attributes",
            "datasets": [
                "source_attribute",
                "bronze_attribute",
                "silver_attribute",
                "gold_attribute",
            ],
        },
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


def test_root_documents_reject_an_unresolved_natural_key_reference() -> None:
    encoded = list(empty_datasets())
    connection_index = next(
        index
        for index, definition in enumerate(DATASETS)
        if definition.name == "connection"
    )
    encoded[connection_index] = encode_dataset(
        DATASETS[connection_index],
        [
            {
                "tenant_code": "MISSING",
                "system_code": "MISSING",
                "connection_code": "SOURCE",
                "connection_name": "Source",
                "connection_type_code": "MISSING",
                "has_foreign_catalog": False,
                "foreign_catalog": None,
                "is_global_data_store": False,
                "is_active": True,
            }
        ],
    )

    with pytest.raises(SnapshotContractError, match="unresolved natural-key reference"):
        build_root_documents(encoded)
