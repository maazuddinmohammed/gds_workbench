"""Agent output schemas publish the same semantics as canonical Model datasets."""

# pyright: reportPrivateUsage=false

from __future__ import annotations

from copy import deepcopy
from typing import cast

import pytest
from gds_etl_workbench.domain.snapshots.model import (
    CHANGE_SET_DATASETS,
    ModelingDatasetDefinition,
)
from pydantic import BaseModel, JsonValue

from gds_workbench_api.features.conceptual.candidate import _ConceptualCandidate
from gds_workbench_api.features.dimensional.candidate import _DimensionalCandidate
from gds_workbench_api.features.logical.candidate import _LogicalCandidate
from gds_workbench_api.features.workflows.authoring.repair import (
    enrich_agent_output_model_definitions,
)


@pytest.mark.parametrize(
    ("model", "record_definitions"),
    [
        (
            _ConceptualCandidate,
            {"ConceptualObjectRecord", "ConceptualRelationshipRecord"},
        ),
        (
            _LogicalCandidate,
            {
                "LogicalSubmodelRecord",
                "LogicalEntityRecord",
                "LogicalAttributeRecord",
                "LogicalRelationshipRecord",
            },
        ),
        (
            _DimensionalCandidate,
            {
                "DimensionalSubmodelRecord",
                "DimensionalEntityRecord",
                "DimensionalAttributeRecord",
                "DimensionalRelationshipRecord",
            },
        ),
    ],
)
def test_authorable_model_records_and_nested_fields_have_semantic_guidance(
    model: type[BaseModel],
    record_definitions: set[str],
) -> None:
    schema = cast(dict[str, JsonValue], model.model_json_schema())
    constraints_before = _without_semantic_guidance(schema)

    enrich_agent_output_model_definitions(schema)

    assert _without_semantic_guidance(schema) == constraints_before
    definitions = cast(dict[str, dict[str, object]], schema["$defs"])
    assert record_definitions <= definitions.keys()
    for name in record_definitions:
        definition = definitions[name]
        assert _nonblank(definition.get("description")), name
        rules = definition.get("x-gds-population-rules")
        assert isinstance(rules, list) and rules
        assert all(_nonblank(rule) for rule in cast(list[object], rules))
    for name, definition in definitions.items():
        properties = definition.get("properties")
        if not isinstance(properties, dict):
            continue
        typed_properties = cast(dict[str, object], properties)
        for field, raw_property in typed_properties.items():
            assert isinstance(raw_property, dict), (name, field)
            property_schema = cast(dict[str, object], raw_property)
            assert _nonblank(property_schema.get("description")), (name, field)
            assert _nonblank(property_schema.get("x-gds-population-guidance")), (
                name,
                field,
            )


@pytest.mark.parametrize("definition", CHANGE_SET_DATASETS, ids=lambda item: item.name)
def test_every_change_set_record_definition_can_publish_canonical_field_guidance(
    definition: ModelingDatasetDefinition,
) -> None:
    generated = cast(dict[str, JsonValue], definition.row_model.model_json_schema())
    raw_nested = generated.pop("$defs", {})
    assert isinstance(raw_nested, dict)
    nested = cast(dict[str, JsonValue], raw_nested)
    schema: dict[str, JsonValue] = {
        "$defs": {
            **nested,
            definition.row_model.__name__: generated,
        }
    }

    enrich_agent_output_model_definitions(schema)

    raw_definitions = schema["$defs"]
    assert isinstance(raw_definitions, dict)
    definitions = cast(dict[str, object], raw_definitions)
    raw_record = definitions[definition.row_model.__name__]
    assert isinstance(raw_record, dict)
    record = cast(dict[str, object], raw_record)
    assert _nonblank(record.get("description"))
    assert record.get("x-gds-population-rules")
    raw_properties = record["properties"]
    assert isinstance(raw_properties, dict)
    for field, raw_property in cast(dict[str, object], raw_properties).items():
        assert isinstance(raw_property, dict), field
        property_schema = cast(dict[str, object], raw_property)
        assert _nonblank(property_schema.get("description")), field
        assert _nonblank(property_schema.get("x-gds-population-guidance")), field


def _nonblank(value: object) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _without_semantic_guidance(value: object) -> object:
    document = deepcopy(value)
    if isinstance(document, dict):
        typed_document = cast(dict[str, object], document)
        for key in (
            "description",
            "x-gds-population-guidance",
            "x-gds-population-rules",
            "examples",
        ):
            typed_document.pop(key, None)
        return {
            key: _without_semantic_guidance(item) for key, item in typed_document.items()
        }
    if isinstance(document, list):
        return [_without_semantic_guidance(item) for item in cast(list[object], document)]
    return document
