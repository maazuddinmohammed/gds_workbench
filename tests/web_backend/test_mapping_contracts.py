"""Frozen Release-1 Mapping profile contract."""

from __future__ import annotations

import json
from typing import Any, cast

import pytest
from gds_etl_workbench.domain.mapping_contracts import (
    MappingPackageDocumentV1 as SharedMappingPackageDocumentV1,
)
from gds_etl_workbench.domain.mapping_contracts import (
    validate_mapping_package_document,
)
from gds_etl_workbench.domain.mapping_profiles import (
    canonical_mapping_json_bytes,
    resolve_mapping_profile_schema_digest,
)
from gds_etl_workbench.domain.mapping_profiles import (
    mapping_package_digest as shared_mapping_package_digest,
)
from pydantic import ValidationError

from gds_workbench_api.features.mapping.contracts import (
    MAX_ATTRIBUTE_MAPPER_ITEMS,
    MAX_GENERATOR_DOCUMENT_BYTES,
    MAX_MAPPING_PACKAGES_PER_RUN,
    MAX_MAPPING_SECTION_BYTES,
    AttributeMapperBatchOutputV1,
    GeneratorDocumentV1,
    HeaderMapperOutputV1,
    canonical_json_bytes,
    mapping_package_digest,
    mapping_schema_bundle,
    mapping_schema_bundle_digest,
    parse_contract_json,
)
from gds_workbench_api.features.mapping.profile_registry import (
    MappingProfileConfigurationError,
    load_mapping_profile_registry,
)


def test_mapping_profile_bundle_and_registry_are_one_canonical_contract() -> None:
    bundle = mapping_schema_bundle()
    bundle_bytes = canonical_json_bytes(bundle)

    assert bundle["schema_bundle_version"] == "1.0"
    schema_entries = cast(list[dict[str, object]], bundle["schemas"])
    assert [item["class_name"] for item in schema_entries] == [
        "AttributeMapperBatchOutputV1",
        "GeneratorDocumentV1",
        "HeaderMapperOutputV1",
    ]
    assert mapping_schema_bundle_digest() == (
        "b3b324170019b51d2b812c3735fa6215e463209ea39e4099b44c786b956da8fa"
    )
    assert len(bundle_bytes) == 37_279
    assert bundle_bytes.startswith(
        b'{"json_schema_mode":"validation","schema_bundle_version":"1.0","schemas":['
    )
    assert mapping_schema_bundle_digest() == load_mapping_profile_registry().schema_digest
    assert mapping_schema_bundle_digest() == resolve_mapping_profile_schema_digest(
        "mapping.standard",
        "1.0.0",
    )


def test_mapping_contract_json_rejects_duplicate_keys_floats_and_nonfinite_numbers() -> None:
    with pytest.raises(ValueError, match="duplicate JSON object key"):
        parse_contract_json('{"schema_version":"1.0","schema_version":"1.0"}')
    with pytest.raises(ValueError, match="floating-point"):
        parse_contract_json('{"value":1.5}')
    with pytest.raises(ValueError, match="non-finite"):
        parse_contract_json('{"value":NaN}')
    with pytest.raises(ValueError, match="object root"):
        parse_contract_json("[]")
    with pytest.raises(ValueError, match="invalid contract JSON"):
        parse_contract_json("{} {}")


def test_mapping_profile_registry_rejects_digest_or_runtime_drift() -> None:
    registered = load_mapping_profile_registry()
    payload = registered.model_dump(mode="json")
    payload["schema_digest"] = "0" * 64
    with pytest.raises(MappingProfileConfigurationError, match="schema digest"):
        load_mapping_profile_registry(json.dumps(payload))

    payload = registered.model_dump(mode="json")
    payload["pydantic_version"] = "0.0.0"
    with pytest.raises(MappingProfileConfigurationError, match="Pydantic"):
        load_mapping_profile_registry(json.dumps(payload))


def test_root_contracts_are_strict_and_nullable_fields_are_required() -> None:
    for model in (
        HeaderMapperOutputV1,
        AttributeMapperBatchOutputV1,
        GeneratorDocumentV1,
    ):
        assert model.model_config.get("extra") == "forbid"
        assert model.model_config.get("frozen") is True
        assert model.model_config.get("strict") is True
        assert model.model_json_schema()["additionalProperties"] is False

    with pytest.raises(ValidationError, match="partition_basis"):
        HeaderMapperOutputV1.model_validate(_header_candidate(omit_partition_basis=True))
    invalid = _header_candidate()
    invalid["unexpected"] = True
    with pytest.raises(ValidationError, match="extra_forbidden"):
        HeaderMapperOutputV1.model_validate(invalid)


def test_web_header_uses_the_shared_exact_mapping_package_contract() -> None:
    candidate = _header_candidate()
    shared = validate_mapping_package_document(candidate["package"])
    web = HeaderMapperOutputV1.model_validate(candidate).package

    assert isinstance(web, SharedMappingPackageDocumentV1)
    assert web == shared

    del candidate["package"]["package_ref"]
    with pytest.raises(ValidationError, match="package_ref"):
        validate_mapping_package_document(candidate["package"])
    with pytest.raises(ValidationError, match="package_ref"):
        HeaderMapperOutputV1.model_validate(candidate)

    candidate = _header_candidate()
    candidate["package"]["pydantic_profile"]["schema_digest"] = "0" * 64
    with pytest.raises(ValidationError, match="profile digest is not deployed"):
        validate_mapping_package_document(candidate["package"])
    with pytest.raises(ValidationError, match="profile digest is not deployed"):
        HeaderMapperOutputV1.model_validate(candidate)


def test_header_contract_enforces_provenance_uniqueness_and_direct_shape() -> None:
    candidate = _header_candidate()
    parsed = HeaderMapperOutputV1.model_validate(candidate)
    assert parsed.package.non_executable_provenance[0].lineage_kind == "original_ingestion"

    invalid = _header_candidate()
    invalid["package"]["non_executable_provenance"][0]["prior_object_mapping_ids"] = [99]
    with pytest.raises(ValidationError, match="Original-ingestion provenance"):
        HeaderMapperOutputV1.model_validate(invalid)

    invalid = _header_candidate()
    invalid["package"]["executable_sources"].append(invalid["package"]["executable_sources"][0])
    with pytest.raises(ValidationError, match="aliases must be unique"):
        HeaderMapperOutputV1.model_validate(invalid)


def test_attribute_contract_enforces_typed_identity_disposition_and_coverage() -> None:
    candidate = _attribute_candidate()
    parsed = AttributeMapperBatchOutputV1.model_validate(candidate)
    assert parsed.attribute_mappings[0].logical_attribute_id == 501

    invalid = _attribute_candidate()
    invalid["attribute_mappings"][0]["dimensional_attribute_id"] = 601
    with pytest.raises(ValidationError, match="typed modeled Attribute"):
        AttributeMapperBatchOutputV1.model_validate(invalid)

    invalid = _attribute_candidate()
    invalid["target_attribute_dispositions"][0]["reason"] = "not allowed"
    with pytest.raises(ValidationError, match="reason"):
        AttributeMapperBatchOutputV1.model_validate(invalid)


def test_generator_contract_has_no_database_ids_and_enforces_name_only_safety() -> None:
    schema = GeneratorDocumentV1.model_json_schema()
    property_names = _property_names(schema)
    assert not any(
        name == "id" or name.endswith("_id") or name.endswith("_ids") for name in property_names
    )
    assert not property_names & {
        "api_key",
        "credential",
        "password",
        "secret",
        "token",
    }

    candidate = _generator_candidate()
    parsed = GeneratorDocumentV1.model_validate(candidate)
    assert parsed.target.zone == "silver"

    invalid = _generator_candidate()
    invalid["target"]["columns"][0]["ordinal"] = 2
    with pytest.raises(ValidationError, match="complete and unique"):
        GeneratorDocumentV1.model_validate(invalid)

    invalid = _generator_candidate()
    invalid["target_columns"][0]["expression"] = "source.customer_id"
    with pytest.raises(ValidationError, match="Direct target-column"):
        GeneratorDocumentV1.model_validate(invalid)

    invalid = _generator_candidate()
    invalid["artifact"]["generation_instructions"] = (
        "Authorization: Bearer abcdefghijklmnopqrstuvwxyz"
    )
    with pytest.raises(ValidationError, match="secret-shaped"):
        GeneratorDocumentV1.model_validate(invalid)

    invalid = _generator_candidate()
    invalid["runtime_parameters"] = [
        {
            "name": "ratio",
            "data_type": "decimal",
            "purpose": "Invalid floating default",
            "default_value": 1.5,
        }
    ]
    with pytest.raises(ValidationError):
        GeneratorDocumentV1.model_validate(invalid)


def test_contract_text_and_collection_limits_are_enforced() -> None:
    assert MAX_MAPPING_SECTION_BYTES == 16 * 1_024 * 1_024
    assert MAX_GENERATOR_DOCUMENT_BYTES == 4 * 1_024 * 1_024
    assert MAX_MAPPING_PACKAGES_PER_RUN == 1_000
    assert MAX_ATTRIBUTE_MAPPER_ITEMS == 500

    invalid = _header_candidate()
    invalid["package"]["artifact_generation_instructions"] = "x" * 32_769
    with pytest.raises(ValidationError, match="string_too_long"):
        HeaderMapperOutputV1.model_validate(invalid)

    invalid = _attribute_candidate()
    invalid["chunk_count"] = 101
    with pytest.raises(ValidationError, match="less than or equal to 100"):
        AttributeMapperBatchOutputV1.model_validate(invalid)

    invalid = _generator_candidate()
    invalid["executable_sources"][0]["fqn"] = "x" * 1_025
    with pytest.raises(ValidationError, match="string_too_long"):
        GeneratorDocumentV1.model_validate(invalid)


def test_contract_canonical_json_has_a_stable_golden_vector() -> None:
    value = {"z": [3, 2, 1], "unicode": "café", "a": {"b": True}}
    assert canonical_json_bytes(value) == (b'{"a":{"b":true},"unicode":"caf\xc3\xa9","z":[3,2,1]}')
    assert canonical_json_bytes(value) == canonical_mapping_json_bytes(value)


def test_package_canonicalization_and_digest_have_a_golden_vector() -> None:
    first = HeaderMapperOutputV1.model_validate(_header_candidate()).package
    reordered = _header_candidate()
    reordered["package"]["executable_sources"][0]["batch_rule"]["values"] = [2, 1]
    second = HeaderMapperOutputV1.model_validate(reordered).package

    assert first == second
    assert mapping_package_digest(first) == (
        "2ccf021dfc893ce35b64b71fda1658c24917425085941797bf38d096996e7148"
    )
    assert mapping_package_digest(first) == shared_mapping_package_digest(
        first.model_dump(mode="json")
    )


def test_mapping_schema_has_no_unbounded_string_leaf() -> None:
    leaves = _string_schema_leaves(mapping_schema_bundle())

    assert leaves
    for leaf in leaves:
        assert (
            "maxLength" in leaf
            or "const" in leaf
            or "enum" in leaf
            or leaf.get("pattern") == "^[0-9a-f]{64}$"
        )


def _header_candidate(*, omit_partition_basis: bool = False) -> dict[str, Any]:
    load: dict[str, Any] = {
        "write_mode": "merge",
        "merge_keys": [301],
        "partition_basis": None,
        "concurrent_system_write_mode": "idempotent_merge",
        "concurrent_write_basis": "customer key",
    }
    if omit_partition_basis:
        del load["partition_basis"]
    return {
        "schema_version": "1.0",
        "package": {
            "schema_version": "1.0",
            "package_ref": "customer_crm",
            "route": "logical_to_silver",
            "target_object_id": 101,
            "source_system_id": 201,
            "artifact_type": "sql_file",
            "artifact_generation_instructions": "Generate one idempotent SQL file.",
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
                    "batch_rule": {"attribute_id": 402, "values": [1, 2]},
                }
            ],
            "non_executable_provenance": [
                {
                    "lineage_kind": "original_ingestion",
                    "source_system_id": 201,
                    "source_object_id": 403,
                    "ingestion_object_mapping_ids": [404],
                    "prior_object_mapping_ids": [],
                    "executable_source_aliases": ["customer_source"],
                }
            ],
            "runtime_parameters": [
                {
                    "name": "run_date",
                    "data_type": "date",
                    "purpose": "Load date",
                    "default_value": None,
                }
            ],
            "source_system_dependencies": [],
            "target_dependencies": [],
            "steps": [
                {
                    "name": "project_customer",
                    "depends_on": [],
                    "inputs": ["customer_source"],
                    "output": "customer_projected",
                    "logic": "Project customer fields.",
                }
            ],
            "grain_and_deduplication": "One row per customer.",
            "load": load,
        },
        "headers": [
            {
                "mapping_object_id": 701,
                "transformation": {
                    "schema_version": "1.0",
                    "transformation_kind": "direct",
                    "source_aliases": ["customer_source"],
                    "joins": [],
                    "unions": [],
                    "filters": [],
                    "aggregations": [],
                    "entity_contribution_logic": "Customer source contributes directly.",
                    "rationale": "Authoritative customer feed.",
                },
            }
        ],
        "coverage": {
            "expected_mapping_object_ids": [701],
            "returned_mapping_object_ids": [701],
        },
    }


def _attribute_candidate() -> dict[str, Any]:
    return {
        "schema_version": "1.0",
        "package_ref": "customer_crm",
        "target_object_id": 101,
        "source_system_id": 201,
        "chunk_index": 1,
        "chunk_count": 1,
        "package_digest": "b" * 64,
        "coverage_manifest_digest": "c" * 64,
        "attribute_mappings": [
            {
                "mapping_object_id": 701,
                "mapping_attribute_id": 801,
                "local_ref": None,
                "modeled_entity_type": "logical_entity",
                "logical_attribute_id": 501,
                "dimensional_attribute_id": None,
                "target_attribute_id": 301,
                "disposition": "update",
                "transformation": {
                    "schema_version": "1.0",
                    "transformation_kind": "direct",
                    "source_columns": [
                        {
                            "source_alias": "customer_source",
                            "source_attribute_id": 402,
                        }
                    ],
                    "step_output": None,
                    "expression": None,
                    "logic": "Copy customer ID.",
                },
            }
        ],
        "target_attribute_dispositions": [
            {"target_attribute_id": 301, "disposition": "mapped", "reason": None}
        ],
        "coverage": {
            "expected_target_attribute_ids": [301],
            "returned_target_attribute_ids": [301],
            "expected_existing_mapping_attribute_ids": [801],
            "returned_existing_mapping_attribute_ids": [801],
        },
    }


def _generator_candidate() -> dict[str, Any]:
    return {
        "schema": {
            "document_version": "1.0",
            "profile_key": "mapping.standard",
            "profile_version": "1.0.0",
            "profile_schema_digest": "a" * 64,
        },
        "applied_model": {
            "model_name": "Customer 360",
            "model_revision": 4,
            "source_context_digest": "b" * 64,
        },
        "route": "logical_to_silver",
        "source_system": {
            "code": "crm",
            "name": "CRM",
            "dependency_order": 0,
            "predecessors": [],
        },
        "artifact": {
            "type": "sql_file",
            "generation_instructions": "Generate one idempotent SQL file.",
        },
        "dependency_waves": {"target_order": 0, "target_predecessors": []},
        "target": {
            "catalog": "silver",
            "schema": "customer",
            "object_name": "customer",
            "fqn": "silver.customer.customer",
            "zone": "silver",
            "description": None,
            "grain_and_deduplication": "One row per customer.",
            "columns": [
                {
                    "name": "customer_id",
                    "data_type": "bigint",
                    "nullable": False,
                    "ordinal": 1,
                    "definition": None,
                }
            ],
        },
        "executable_sources": [
            {
                "alias": "customer_source",
                "zone": "bronze",
                "catalog": "bronze",
                "schema": "crm",
                "object_name": "customer_raw",
                "fqn": "bronze.crm.customer_raw",
                "used_columns": [
                    {
                        "name": "customer_id",
                        "data_type": "bigint",
                        "nullable": False,
                        "definition": None,
                        "meaning": None,
                    }
                ],
                "batch_rule": None,
            }
        ],
        "original_source_provenance": [
            {
                "source_system_code": "crm",
                "source_system_name": "CRM",
                "connection_code": "crm_prod",
                "source_object_name": "customer",
                "lineage_kind": "original_ingestion",
                "lineage_path": ["customer -> customer_raw"],
                "executable_source_aliases": ["customer_source"],
            }
        ],
        "runtime_parameters": [],
        "named_steps": [
            {
                "name": "project_customer",
                "depends_on": [],
                "inputs": ["customer_source"],
                "output": "customer_projected",
                "logic": "Project customer fields.",
            }
        ],
        "load": {
            "write_mode": "merge",
            "merge_keys": ["customer_id"],
            "partition_basis": None,
            "concurrent_system_write_mode": "idempotent_merge",
            "concurrent_write_basis": "customer key",
            "grain_and_deduplication": "One row per customer.",
        },
        "entity_contributions": [
            {
                "layer": "logical",
                "entity_name": "Customer",
                "definition": "A customer.",
                "transformation_kind": "direct",
                "source_aliases": ["customer_source"],
                "joins": [],
                "unions": [],
                "filters": [],
                "aggregations": [],
                "entity_contribution_logic": "Customer source contributes directly.",
                "rationale": "Authoritative customer feed.",
            }
        ],
        "target_columns": [
            {
                "target_column_name": "customer_id",
                "disposition": "mapped",
                "reason": None,
                "contributors": [
                    {
                        "entity_name": "Customer",
                        "attribute_name": "Customer ID",
                        "source_alias": "customer_source",
                        "source_column_name": "customer_id",
                    }
                ],
                "kind": "direct",
                "step_output": None,
                "expression": None,
                "logic": "Copy customer ID.",
                "rationale": "Stable business key.",
            }
        ],
    }


def _property_names(value: object) -> set[str]:
    names: set[str] = set()
    if isinstance(value, dict):
        mapping = cast(dict[object, object], value)
        properties = mapping.get("properties")
        if isinstance(properties, dict):
            names.update(
                key for key in cast(dict[object, object], properties) if isinstance(key, str)
            )
        for nested in mapping.values():
            names.update(_property_names(nested))
    elif isinstance(value, list):
        for nested in cast(list[object], value):
            names.update(_property_names(nested))
    return names


def _string_schema_leaves(value: object) -> list[dict[str, object]]:
    leaves: list[dict[str, object]] = []
    if isinstance(value, dict):
        mapping = cast(dict[object, object], value)
        if mapping.get("type") == "string":
            leaves.append({key: nested for key, nested in mapping.items() if isinstance(key, str)})
        for nested in mapping.values():
            leaves.extend(_string_schema_leaves(nested))
    elif isinstance(value, list):
        for nested in cast(list[object], value):
            leaves.extend(_string_schema_leaves(nested))
    return leaves
