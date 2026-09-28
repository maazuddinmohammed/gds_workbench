"""Partial Mapping preserves protected logic and recognizes content-free templates."""

from typing import cast

import pytest
from gds_workbench_api.features.mapping.complete_candidate import CompleteMappingCandidateValidator
from gds_workbench_api.features.mapping.contracts import (
    MappingAttributeCandidate,
    MappingObjectCandidate,
)
from gds_workbench_api.features.mapping.readiness import assess_mapping_readiness
from pydantic import JsonValue, ValidationError

from tests.web_backend.mapping_fixtures import mapping_preparation

EMPTY_DOCUMENTS: list[JsonValue] = [
    None,
    {},
    {"steps": [], "source_objects": []},
    {"rule": {"expression": " \t\n", "inputs": [None, {}, [], {"empty": []}]}},
]


@pytest.mark.parametrize("protection", ("locked", "unselected"))
@pytest.mark.parametrize("saved_logic", (False, True))
async def test_new_object_logic_cannot_change_a_protected_authored_attribute(
    protection: str,
    saved_logic: bool,
) -> None:
    preparation = mapping_preparation(existing=True, attribute_count=2)
    header = preparation.context.headers[0]
    protected, selected = header.attribute_mappings
    protected = protected.model_copy(
        update={
            "is_locked": protection == "locked",
            "transformation_document": protected.transformation_document if saved_logic else None,
        }
    )
    header = header.model_copy(
        update={
            "transformation_document": None,
            "attribute_mappings": (protected, selected),
        }
    )
    context = preparation.context.model_copy(update={"headers": (header,)})
    plan = preparation.plan.model_copy(
        update={
            "selected_attribute_ids": (selected.modeled_attribute_id,),
        }
    )
    preparation = preparation.model_copy(
        update={
            "context": context,
            "plan": plan,
            "readiness": assess_mapping_readiness(plan=plan, context=context),
        }
    )
    assert preparation.readiness.ready
    candidate: JsonValue = {
        "schema_version": "1.0",
        "object_mapping": {
            "object_dependency_order": 0,
            "mapping_transformation_document": {"steps": ["Synthetic new Object grain."]},
        },
        "attribute_mappings": [],
    }
    validator = CompleteMappingCandidateValidator(preparation=preparation)
    validation = await validator.validate(candidate)
    assert bool(validation.issues) == saved_logic
    if saved_logic:
        assert "Keep existing Object logic unchanged" in validation.issues[0].message
        candidate["object_mapping"] = None
        assert not (await validator.validate(candidate)).issues
    result = validator.parse_validated(candidate)
    protected_name = next(
        attribute.attribute_name
        for attribute in header.modeled_entity.attributes
        if attribute.attribute_id == protected.modeled_attribute_id
    )
    assert all(
        record["modeled_attribute_name"] != protected_name
        for change in result.changes
        if change.dataset == "mapping_attribute"
        for record in change.records
    )


async def test_virtual_unselected_attributes_allow_initial_object_authoring() -> None:
    preparation = mapping_preparation(attribute_count=2)
    plan = preparation.plan.model_copy(update={"selected_attribute_ids": (701,)})
    preparation = preparation.model_copy(
        update={
            "plan": plan,
            "readiness": assess_mapping_readiness(plan=plan, context=preparation.context),
        }
    )
    candidate: JsonValue = {
        "schema_version": "1.0",
        "attribute_mappings": [],
        "object_mapping": {
            "object_dependency_order": 0,
            "mapping_transformation_document": {"steps": ["Read source."]},
        },
    }
    validator = CompleteMappingCandidateValidator(preparation=preparation)
    assert not (await validator.validate(candidate)).issues
    result = validator.parse_validated(candidate)
    assert result.has_object_transformation and result.is_partial
    assert [change.dataset for change in result.changes] == ["mapping_object"]


@pytest.mark.parametrize(
    "document",
    EMPTY_DOCUMENTS,
)
def test_recursively_empty_mapping_documents_become_null(document: JsonValue) -> None:
    assert (
        MappingObjectCandidate.model_validate(
            {
                "object_dependency_order": 0,
                "mapping_transformation_document": document,
            }
        ).mapping_transformation_document
        is None
    )
    assert (
        MappingAttributeCandidate.model_validate(
            {
                "modeled_attribute_name": "CustomerID",
                "attribute_mapping_transformation_document": document,
            }
        ).attribute_mapping_transformation_document
        is None
    )


@pytest.mark.parametrize("value", [False, 0, 0.0, " 0 ", "  custom rule  "])
def test_meaningful_custom_mapping_values_are_preserved_exactly(value: JsonValue) -> None:
    document: JsonValue = {"custom": {"value": [None, value], "empty": []}}
    assert (
        MappingObjectCandidate.model_validate(
            {
                "object_dependency_order": 0,
                "mapping_transformation_document": document,
            }
        ).mapping_transformation_document
        == document
    )
    assert (
        MappingAttributeCandidate.model_validate(
            {
                "modeled_attribute_name": "CustomerID",
                "attribute_mapping_transformation_document": document,
            }
        ).attribute_mapping_transformation_document
        == document
    )


@pytest.mark.parametrize("kind,maximum", [("object", 524_288), ("attribute", 65_536)])
def test_blank_normalization_cannot_bypass_mapping_document_byte_limit(
    kind: str,
    maximum: int,
) -> None:
    document = {"blank": " " * maximum}
    with pytest.raises(ValidationError, match="exceeds"):
        if kind == "object":
            MappingObjectCandidate.model_validate(
                {
                    "object_dependency_order": 0,
                    "mapping_transformation_document": document,
                }
            )
        else:
            MappingAttributeCandidate.model_validate(
                {
                    "modeled_attribute_name": "CustomerID",
                    "attribute_mapping_transformation_document": document,
                }
            )


async def test_empty_template_containers_do_not_create_a_new_mapping_pair() -> None:
    candidate: JsonValue = {
        "schema_version": "1.0",
        "object_mapping": {
            "object_dependency_order": 0,
            "mapping_transformation_document": {"steps": [], "sources": []},
        },
        "attribute_mappings": [
            {
                "modeled_attribute_name": "CustomerID",
                "attribute_mapping_transformation_document": {"rule": " "},
            }
        ],
    }
    validator = CompleteMappingCandidateValidator(preparation=mapping_preparation())
    assert not (await validator.validate(candidate)).issues
    result = validator.parse_validated(cast(JsonValue, candidate))
    assert not result.has_transformations and not result.changes
