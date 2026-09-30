"""Layer-specific defaults retain source eligibility and selected-template checks."""

from copy import deepcopy
from typing import Any

import pytest
from gds_workbench_api.features.mapping.complete_candidate import (
    CompleteMappingCandidateValidator,
)
from gds_workbench_api.features.mapping.preparation_contracts import ModeledEntityType
from gds_workbench_api.features.mapping.readiness import assess_mapping_readiness
from gds_workbench_api.features.workflows.authoring.context_inputs import OBJECT_FIELDS
from mapping_fixtures import mapping_candidate, mapping_preparation


@pytest.mark.parametrize("layer", ("logical_entity", "dimensional_entity"))
@pytest.mark.parametrize(
    "case",
    (
        "valid",
        "empty",
        "null_columns",
        "wrong_source",
        "wrong_attribute",
        "missing_table",
        "null_tables",
    ),
)
async def test_default_source_fields_preserve_integrity(
    layer: ModeledEntityType, case: str
) -> None:
    preparation = mapping_preparation(modeled_entity_type=layer)
    source = preparation.context.sources[0].object.model_dump(mode="json")
    keys = (
        OBJECT_FIELDS
        if layer == "logical_entity"
        else (
            "entity_type",
            "entity_schema_name",
            "entity_name",
        )
    )
    table = {key: source[key] for key in keys}
    column = {**table, "attribute_name": "customer_id"}
    object_document: dict[str, Any] = {
        "source_tables": [table],
        "filter_criteria": None,
        "sample_query": "SELECT customer_id FROM the supported source",
    }
    attribute_document: dict[str, Any] = {
        "transformation_logic": "Copy customer_id",
        "default_record": None,
        "source_columns": [column],
    }
    if case == "empty":
        object_document["source_tables"] = []
        attribute_document["source_columns"] = []
    elif case == "null_columns":
        attribute_document["source_columns"] = None
    elif case == "wrong_source":
        field = "object_name" if layer == "logical_entity" else "entity_name"
        table[field] = "UnavailableSource"
    elif case == "wrong_attribute":
        column["attribute_name"] = "UnavailableAttribute"
    elif case == "missing_table":
        object_document["source_tables"] = []
    elif case == "null_tables":
        object_document["source_tables"] = None
    candidate = deepcopy(mapping_candidate())
    candidate["object_mapping"] = {
        "object_dependency_order": 0,
        "mapping_transformation_document": object_document,
    }
    candidate["attribute_mappings"] = [
        {
            "modeled_attribute_name": "CustomerID",
            "attribute_mapping_transformation_document": attribute_document,
        }
    ]
    result = await CompleteMappingCandidateValidator(preparation=preparation).validate(
        candidate
    )
    assert bool(result.issues) == (case not in {"valid", "empty", "null_columns"})


def test_preparation_rejects_a_template_for_the_opposite_layer() -> None:
    preparation = mapping_preparation()
    document = preparation.model_dump(mode="json")
    template = {
        "output_template_id": 901,
        "code": "mapping_dimensional_object_default",
        "name": "Dimensional Object",
        "target_type": "mapping_object",
        "modeled_entity_type": "dimensional_entity",
        "schema_digest": "a" * 64,
        "schema_digest_is_valid": True,
        "is_active": True,
        "fields": [
            {
                "name": "source_tables",
                "description": "Sources",
                "data_type": "array",
                "array_item_type": "object",
                "is_required": True,
                "order": 1,
            }
        ],
    }
    for scope in ("plan", "context"):
        document[scope]["output_template_selections"]["mapping_object"] = {
            "output_template_id": 901,
            "schema_digest": "a" * 64,
        }
    document["context"]["output_templates"] = {"ids": [901], "definitions": [template]}
    preparation = type(preparation).model_validate(document, strict=False)
    readiness = assess_mapping_readiness(
        plan=preparation.plan, context=preparation.context
    )
    assert not readiness.ready
    assert "template.unavailable" in {issue.code for issue in readiness.issues}


@pytest.mark.parametrize("legacy_names", [False, True])
@pytest.mark.parametrize("template_kind", ["custom", "default"])
async def test_selected_template_owns_same_named_field_semantics(
    legacy_names: bool, template_kind: str
) -> None:
    preparation = mapping_preparation()
    document = preparation.model_dump(mode="json")
    templates: list[dict[str, Any]] = []
    object_field = "source_objects" if legacy_names else "source_tables"
    attribute_field = "source_attributes" if legacy_names else "source_columns"
    for index, (kind, field) in enumerate(
        (("mapping_object", object_field), ("mapping_attribute", attribute_field)),
        start=901,
    ):
        code = (
            f"custom.{kind}_labels"
            if template_kind == "custom"
            else f"mapping_logical_{kind.removeprefix('mapping_')}_default"
        )
        templates.append(
            {
                "output_template_id": index,
                "code": code,
                "name": "Named labels",
                "target_type": kind,
                "modeled_entity_type": "logical_entity",
                "schema_digest": "a" * 64,
                "schema_digest_is_valid": True,
                "is_active": True,
                "fields": [
                    {
                        "name": field,
                        "description": "External source labels, not natural-key references.",
                        "data_type": "array",
                        "array_item_type": "string"
                        if template_kind == "custom"
                        else "object",
                        "is_required": True,
                        "order": 1,
                    }
                ],
            }
        )
        for scope in ("plan", "context"):
            document[scope]["output_template_selections"][kind] = {
                "output_template_id": index,
                "schema_digest": "a" * 64,
            }
    document["context"]["output_templates"] = {
        "ids": [901, 902],
        "definitions": templates,
    }
    preparation = type(preparation).model_validate(document, strict=False)
    candidate = deepcopy(mapping_candidate())
    candidate["object_mapping"] = {
        "object_dependency_order": 0,
        "mapping_transformation_document": {object_field: ["customer_source"]},
    }
    candidate["attribute_mappings"] = [
        {
            "modeled_attribute_name": "CustomerID",
            "attribute_mapping_transformation_document": {
                attribute_field: ["customer_name"]
            },
        }
    ]
    result = await CompleteMappingCandidateValidator(preparation=preparation).validate(
        candidate
    )
    assert bool(result.issues) is (template_kind == "default")
    if template_kind == "custom":
        parsed = CompleteMappingCandidateValidator(
            preparation=preparation
        ).parse_validated(candidate)
        assert parsed.normalized.object_mapping is not None
        assert parsed.normalized.object_mapping.mapping_transformation_document == {
            object_field: ["customer_source"]
        }


@pytest.mark.parametrize("invalid", [None, "table", "column"])
async def test_historical_default_templates_validate_legacy_references(
    invalid: str | None,
) -> None:
    preparation = mapping_preparation()
    document = preparation.model_dump(mode="json")
    templates: list[dict[str, Any]] = []
    for index, (kind, field) in enumerate(
        (
            ("mapping_object", "source_objects"),
            ("mapping_attribute", "source_attributes"),
        ),
        start=901,
    ):
        templates.append(
            {
                "output_template_id": index,
                "code": kind + "_default",
                "name": "Historical default",
                "target_type": kind,
                "modeled_entity_type": None,
                "schema_digest": "a" * 64,
                "schema_digest_is_valid": True,
                "is_active": True,
                "fields": [
                    {
                        "name": field,
                        "description": "Complete source natural keys.",
                        "data_type": "array",
                        "array_item_type": "object",
                        "is_required": True,
                        "order": 1,
                    }
                ],
            }
        )
        for scope in ("plan", "context"):
            document[scope]["output_template_selections"][kind] = {
                "output_template_id": index,
                "schema_digest": "a" * 64,
            }
    document["context"]["output_templates"] = {
        "ids": [901, 902],
        "definitions": templates,
    }
    preparation = type(preparation).model_validate(document, strict=False)
    source = preparation.context.sources[0].object.model_dump(mode="json")
    reference = {key: source[key] for key in OBJECT_FIELDS}
    table = {**reference, "alias": "c"}
    column = {**reference, "attribute_name": "customer_id"}
    if invalid == "table":
        table["object_name"] = "Missing"
    elif invalid == "column":
        column["attribute_name"] = "Missing"
    candidate = deepcopy(mapping_candidate())
    candidate["object_mapping"] = {
        "object_dependency_order": 0,
        "mapping_transformation_document": {"source_objects": [table]},
    }
    candidate["attribute_mappings"] = [
        {
            "modeled_attribute_name": "CustomerID",
            "attribute_mapping_transformation_document": {
                "source_attributes": [column]
            },
        }
    ]
    result = await CompleteMappingCandidateValidator(preparation=preparation).validate(
        candidate
    )
    assert bool(result.issues) is (invalid is not None)
