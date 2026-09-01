from __future__ import annotations

from copy import deepcopy
from typing import cast

import pytest
from gds_etl_workbench.domain.mapping_profiles import (
    InvalidMappingPackageError,
    UnknownMappingProfileError,
    canonical_mapping_json_bytes,
    mapping_package_digest,
    resolve_mapping_profile_schema_digest,
    validate_mapping_package_profile,
)
from gds_etl_workbench.domain.modeling_records import MappingObjectRecord
from gds_etl_workbench.tools.change_sets.model_validation import validate_staged_records


def test_mapping_standard_profile_resolves_to_the_frozen_schema_digest() -> None:
    assert resolve_mapping_profile_schema_digest("mapping.standard", "1.0.0") == (
        "b3b324170019b51d2b812c3735fa6215e463209ea39e4099b44c786b956da8fa"
    )

    with pytest.raises(UnknownMappingProfileError, match="Unsupported Mapping profile"):
        resolve_mapping_profile_schema_digest("mapping.unknown", "1.0.0")

    with pytest.raises(UnknownMappingProfileError, match="Unsupported Mapping profile"):
        resolve_mapping_profile_schema_digest("mapping.standard", "2.0.0")


def test_mapping_package_digest_uses_one_canonical_json_encoding() -> None:
    package = {
        "schema_version": "1.0",
        "pydantic_profile": {
            "key": "mapping.standard",
            "version": "1.0.0",
            "schema_digest": (
                "b3b324170019b51d2b812c3735fa6215e463209ea39e4099b44c786b956da8fa"
            ),
        },
        "values": [2, 1],
    }

    assert canonical_mapping_json_bytes(package) == (
        b'{"pydantic_profile":{"key":"mapping.standard","schema_digest":'
        b'"b3b324170019b51d2b812c3735fa6215e463209ea39e4099b44c786b956da8fa",'
        b'"version":"1.0.0"},"schema_version":"1.0","values":[2,1]}'
    )
    assert mapping_package_digest(package) == (
        "a1e73730c86a724188e0cd1ae2e75f959df6a0d7502789c709b271f684eb3023"
    )


@pytest.mark.parametrize("value", [1.5, float("nan"), float("inf"), float("-inf")])
def test_mapping_canonical_json_rejects_all_floating_point_values(value: float) -> None:
    with pytest.raises(ValueError, match="Floating-point"):
        canonical_mapping_json_bytes({"nested": [value]})


def test_mapping_canonical_json_rejects_non_string_object_keys() -> None:
    with pytest.raises(ValueError, match="keys must be strings"):
        canonical_mapping_json_bytes({"nested": {1: "not JSON"}})


def test_mapping_package_profile_must_match_the_resolved_record_identity() -> None:
    package = {
        "schema_version": "1.0",
        "pydantic_profile": {
            "key": "mapping.standard",
            "version": "1.0.0",
            "schema_digest": (
                "b3b324170019b51d2b812c3735fa6215e463209ea39e4099b44c786b956da8fa"
            ),
        },
    }

    validate_mapping_package_profile(package, "mapping.standard", "1.0.0")

    package["pydantic_profile"] = {
        "key": "mapping.standard",
        "version": "1.0.0",
        "schema_digest": "0" * 64,
    }
    with pytest.raises(InvalidMappingPackageError, match="does not match"):
        validate_mapping_package_profile(package, "mapping.standard", "1.0.0")

    with pytest.raises(InvalidMappingPackageError, match="pydantic_profile"):
        validate_mapping_package_profile(
            {"schema_version": "1.0"},
            "mapping.standard",
            "1.0.0",
        )


def test_mapping_change_set_rejects_an_unknown_authored_profile() -> None:
    record = _authored_mapping_record()
    record["mapping_profile_key"] = "mapping.unknown"

    records, issues = validate_staged_records("mapping_object", [record])

    assert records == ()
    assert len(issues) == 1
    assert issues[0].code == "record_schema_invalid"


def test_mapping_change_set_rejects_noncanonical_or_mismatched_packages() -> None:
    floating = _authored_mapping_record()
    package = deepcopy(floating["mapping_package_document"])
    assert isinstance(package, dict)
    package["runtime_parameters"] = [
        {
            "name": "ratio",
            "data_type": "decimal",
            "purpose": "Invalid floating default.",
            "default_value": 1.5,
        }
    ]
    floating["mapping_package_document"] = package

    mismatched = _authored_mapping_record()
    package = deepcopy(mismatched["mapping_package_document"])
    assert isinstance(package, dict)
    profile = cast(dict[str, object], package["pydantic_profile"])
    profile["schema_digest"] = "0" * 64
    mismatched["mapping_package_document"] = package

    for record in (floating, mismatched):
        records, issues = validate_staged_records("mapping_object", [record])
        assert records == ()
        assert issues
        assert all(issue.code == "record_schema_invalid" for issue in issues)
        assert all(issue.dataset == "mapping_object" for issue in issues)
        assert all(issue.record_number == 1 for issue in issues)
        assert all(issue.fields for issue in issues)


def test_mapping_change_set_rejects_a_package_missing_exact_v1_fields() -> None:
    record = _authored_mapping_record()
    package = deepcopy(record["mapping_package_document"])
    assert isinstance(package, dict)
    del package["package_ref"]
    record["mapping_package_document"] = package

    records, issues = validate_staged_records("mapping_object", [record])

    assert records == ()
    assert len(issues) == 1
    assert issues[0].code == "record_schema_invalid"


def test_mapping_change_set_accepts_and_normalizes_one_exact_v1_package() -> None:
    record = _authored_mapping_record()
    package = deepcopy(record["mapping_package_document"])
    assert isinstance(package, dict)
    sources = cast(list[dict[str, object]], package["executable_sources"])
    sources[0]["batch_rule"] = {"attribute_id": 402, "values": [2, 1]}
    record["mapping_package_document"] = package

    records, issues = validate_staged_records("mapping_object", [record])

    assert issues == ()
    assert len(records) == 1
    normalized = cast(MappingObjectRecord, records[0]).mapping_package_document
    assert normalized is not None
    normalized_sources = cast(list[dict[str, object]], normalized["executable_sources"])
    batch_rule = cast(dict[str, object], normalized_sources[0]["batch_rule"])
    assert batch_rule["values"] == [1, 2]


def _authored_mapping_record() -> dict[str, object]:
    return {
        "tenant_code": "DEMO",
        "system_code": "ERP",
        "connection_code": "SOURCE",
        "object_schema": "silver",
        "object_name": "customer",
        "source_system_code": "CRM",
        "modeled_entity_type": "logical_entity",
        "modeled_entity_name": "Customer",
        "object_dependency_order": 0,
        "artifact_type": "sql_file",
        "artifact_generation_instructions": "Generate deterministic SQL.",
        "mapping_profile_key": "mapping.standard",
        "mapping_profile_version": "1.0.0",
        "mapping_package_document": _valid_mapping_package(),
        "object_mapping_transformation_document": {
            "schema_version": "1.0",
            "transformation_kind": "direct",
        },
        "object_mapping_status": "active",
        "object_mapping_is_locked": False,
    }


def _valid_mapping_package() -> dict[str, object]:
    return {
        "schema_version": "1.0",
        "package_ref": "customer_crm",
        "route": "logical_to_silver",
        "target_object_id": 101,
        "source_system_id": 201,
        "artifact_type": "sql_file",
        "artifact_generation_instructions": "Generate deterministic SQL.",
        "pydantic_profile": {
            "key": "mapping.standard",
            "version": "1.0.0",
            "schema_digest": (
                "b3b324170019b51d2b812c3735fa6215e463209ea39e4099b44c786b956da8fa"
            ),
        },
        "executable_sources": [
            {
                "object_id": 401,
                "alias": "customer_source",
                "role": "Customer source",
                "batch_rule": None,
            }
        ],
        "non_executable_provenance": [],
        "runtime_parameters": [],
        "source_system_dependencies": [],
        "target_dependencies": [],
        "steps": [
            {
                "name": "load_customer",
                "depends_on": [],
                "inputs": ["customer_source"],
                "output": "customer_rows",
                "logic": "Load the governed Customer rows.",
            }
        ],
        "grain_and_deduplication": "One row per Customer.",
        "load": {
            "write_mode": "merge",
            "merge_keys": [301],
            "partition_basis": None,
            "concurrent_system_write_mode": "idempotent_merge",
            "concurrent_write_basis": "Customer key.",
        },
    }
