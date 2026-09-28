"""Public Mapping schemas retain metadata boundaries and natural-key projections."""

# pyright: reportPrivateUsage=false
from copy import deepcopy
from typing import Any, cast

import pytest
from gds_etl_workbench.application.mapping_context import (
    OPAQUE_CONTEXT_DOCUMENT_FIELDS,
    without_internal_fields,
)
from jsonschema import Draft202012Validator
from tests.web_backend.mapping_fixtures import mapping_preparation

from gds_workbench_api.features.mapping.execution_context import build_mapping_execution_context
from gds_workbench_api.features.workflows.authoring.downstream_inputs import (
    project_downstream_inputs,
)
from gds_workbench_api.features.workflows.authoring.mapping_input_schemas import (
    _project_schema,
    mapping_input_schemas,
)


def test_schema_and_payload_share_exact_metadata_filter_and_opaque_boundaries() -> None:
    business: dict[str, Any] = {
        "object_id": "business identifier",
        "ids": [3],
        "schema_digest": "business digest",
        "nested": {"customer_id": 4},
    }
    raw = {
        "entity_id": 1,
        "ids": [1],
        "schema_digest": "internal digest",
        "schema_digest_is_valid": True,
        "selected_entity_ids": [1],
        "nested": {"attribute_id": 2, "attribute_name": "CustomerID"},
        **{name: deepcopy(business) for name in OPAQUE_CONTEXT_DOCUMENT_FIELDS},
    }
    schema: dict[str, Any] = {
        "type": "object",
        "additionalProperties": False,
        "properties": {name: {} for name in raw},
        "required": list(raw),
    }
    schema["properties"]["nested"] = {
        "type": "object",
        "additionalProperties": False,
        "properties": {"attribute_id": {"type": "integer"}, "attribute_name": {"type": "string"}},
        "required": ["attribute_id", "attribute_name"],
    }
    for name in OPAQUE_CONTEXT_DOCUMENT_FIELDS:
        schema["properties"][name] = {
            "type": "object",
            "properties": {key: {} for key in business},
            "required": list(business),
            "additionalProperties": False,
        }
    before_schema = deepcopy(schema)
    before_raw = deepcopy(raw)
    public_schema = _project_schema(schema)
    public_value = without_internal_fields(raw)
    validator = cast(Any, Draft202012Validator(public_schema))
    validator.validate(public_value)
    expected = {"selected_entity_ids", "nested", *OPAQUE_CONTEXT_DOCUMENT_FIELDS}
    assert set(public_value) == set(public_schema["properties"]) == expected
    assert set(public_schema["required"]) == expected
    assert public_value["nested"] == {"attribute_name": "CustomerID"}
    for name in OPAQUE_CONTEXT_DOCUMENT_FIELDS:
        assert public_value[name] == business
        assert public_schema["properties"][name] == schema["properties"][name]
    public_value["transformation_document"]["nested"]["customer_id"] = 99
    assert raw == before_raw and schema == before_schema


@pytest.mark.parametrize("layer", ["logical_entity", "dimensional_entity"])
def test_derived_schemas_accept_real_mapping_projection_and_reject_metadata_ids(layer: Any) -> None:
    preparation = mapping_preparation(existing=True, modeled_entity_type=layer)
    context = build_mapping_execution_context(preparation=preparation, execution_mode="one_shot")
    values = project_downstream_inputs("mapping", cast(dict[str, Any], context.embedded_context))
    schemas = mapping_input_schemas()
    for name, schema in schemas.items():
        Draft202012Validator.check_schema(schema)
        cast(Any, Draft202012Validator(schema)).validate(values[name])
    assert not cast(Any, Draft202012Validator(schemas["target_metadata"])).is_valid(
        {**values["target_metadata"], "entity_id": 201}
    )
    assert not cast(Any, Draft202012Validator(schemas["source_system"])).is_valid(
        {**values["source_system"], "system_id": 31}
    )
    for name, child in (
        ("existing_mapping", values["existing_mapping"][0]["attribute_mappings"][0]),
        ("readiness", values["readiness"]["headers"][0]["attribute_actions"][0]),
    ):
        validator = cast(Any, Draft202012Validator(schemas[name]))
        original_name = child.pop("modeled_attribute_name")
        assert not validator.is_valid(values[name])
        child["modeled_attribute_name"] = "A" * 400
        validator.validate(values[name])
        child["modeled_attribute_name"] = "A" * 401
        assert not validator.is_valid(values[name])
        child["modeled_attribute_name"] = original_name


def test_modeled_source_schema_keeps_logical_and_dimensional_identities_distinct() -> None:
    preparation = mapping_preparation(modeled_entity_type="dimensional_entity")
    source = preparation.context.sources[0].model_dump(mode="json")
    schema = mapping_input_schemas()["source_evidence"]
    validator = cast(Any, Draft202012Validator(schema))
    for entity_type in ("logical_entity", "dimensional_entity"):
        source["object"]["entity_type"] = entity_type
        public = without_internal_fields(source)
        validator.validate([public])
        public["object"].pop("entity_schema_name")
        assert not validator.is_valid([public])
    public = without_internal_fields(source)
    public["object"]["entity_type"] = "registered_object"
    assert not validator.is_valid([public])
