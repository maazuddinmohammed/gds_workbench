"""Mapping preserves useful transformations without inventing missing ones."""

from typing import cast

import pytest
from gds_workbench_api.features.mapping.complete_candidate import (
    CompleteMappingCandidateValidator,
)
from gds_workbench_api.features.mapping.preparation_contracts import ModeledEntityType
from gds_workbench_api.features.mapping.readiness import assess_mapping_readiness
from mapping_fixtures import mapping_candidate, mapping_preparation
from pydantic import JsonValue


@pytest.mark.parametrize("layer", ["logical_entity", "dimensional_entity"])
@pytest.mark.parametrize("with_object", [False, True])
@pytest.mark.parametrize("mapped_count", [0, 1, 5, 10])
async def test_mapping_keeps_any_available_transformation(
    layer: ModeledEntityType, with_object: bool, mapped_count: int
) -> None:
    preparation = mapping_preparation(modeled_entity_type=layer, attribute_count=10)
    candidate = mapping_candidate()
    if not with_object:
        candidate["object_mapping"] = None
    candidate["attribute_mappings"] = cast(
        list[JsonValue],
        [
            {
                "modeled_attribute_name": attribute.attribute_name,
                "attribute_mapping_transformation_document": {
                    "transformation": "source_value"
                },
            }
            for attribute in preparation.context.target.attributes[:mapped_count]
        ],
    )
    validator = CompleteMappingCandidateValidator(preparation=preparation)

    assert not (await validator.validate(candidate)).issues
    result = validator.parse_validated(candidate)
    records = {change.dataset: change.records for change in result.changes}
    if not with_object and not mapped_count:
        assert records == {}
        return
    assert len(records["mapping_object"]) == 1
    assert (
        records["mapping_object"][0]["mapping_transformation_document"] is not None
    ) == with_object
    assert len(records.get("mapping_attribute", [])) == mapped_count


async def test_mapping_evidence_gap_keeps_other_attribute_output() -> None:
    preparation = mapping_preparation(attribute_count=10)
    candidate = mapping_candidate()
    cast(list[dict[str, JsonValue]], candidate["attribute_mappings"])[0][
        "modeled_attribute_name"
    ] = preparation.context.target.attributes[0].attribute_name
    candidate["issues"] = [
        {
            "code": "missing_transformation_rule",
            "modeled_attribute_name": preparation.context.target.attributes[
                1
            ].attribute_name,
        }
    ]
    validator = CompleteMappingCandidateValidator(preparation=preparation)
    assert not (await validator.validate(candidate)).issues
    assert len(validator.parse_validated(candidate).changes) == 2


async def test_missing_selected_output_clears_saved_transformations() -> None:
    preparation = mapping_preparation(existing=True, attribute_count=10)
    candidate = mapping_candidate()
    candidate["object_mapping"] = None
    candidate["attribute_mappings"] = []
    validator = CompleteMappingCandidateValidator(preparation=preparation)
    assert not (await validator.validate(candidate)).issues
    result = validator.parse_validated(candidate)
    assert not result.has_transformations
    records = {change.dataset: change.records for change in result.changes}
    assert records["mapping_object"][0]["mapping_transformation_document"] is None
    assert len(records["mapping_attribute"]) == 10
    assert all(
        record["attribute_mapping_transformation_document"] is None
        for record in records["mapping_attribute"]
    )


@pytest.mark.parametrize("layer", ["logical_entity", "dimensional_entity"])
@pytest.mark.parametrize("protected_by", ["selection", "attribute_lock", "object_lock"])
async def test_missing_output_preserves_protected_saved_transformations(
    layer: ModeledEntityType, protected_by: str
) -> None:
    preparation = mapping_preparation(
        existing=True, attribute_count=10, modeled_entity_type=layer
    )
    header = preparation.context.headers[0]
    plan = preparation.plan
    if protected_by == "selection":
        plan = plan.model_copy(
            update={
                "selected_attribute_ids": tuple(
                    item.modeled_attribute_id for item in header.attribute_mappings[:5]
                )
            }
        )
    elif protected_by == "attribute_lock":
        header = header.model_copy(
            update={
                "attribute_mappings": tuple(
                    item.model_copy(update={"is_locked": index >= 5})
                    for index, item in enumerate(header.attribute_mappings)
                )
            }
        )
    else:
        header = header.model_copy(update={"is_locked": True})
    context = preparation.context.model_copy(update={"headers": (header,)})
    preparation = preparation.model_copy(
        update={
            "plan": plan,
            "context": context,
            "readiness": assess_mapping_readiness(plan=plan, context=context),
        }
    )
    candidate = mapping_candidate()
    candidate["object_mapping"] = None
    candidate["attribute_mappings"] = []
    validator = CompleteMappingCandidateValidator(preparation=preparation)
    assert not (await validator.validate(candidate)).issues
    result = validator.parse_validated(candidate)
    assert result.has_object_transformation
    if protected_by == "object_lock":
        assert result.changes == ()
        assert result.mapped_attribute_count == 10
    else:
        assert len(result.changes) == 1
        assert result.changes[0].dataset == "mapping_attribute"
        assert len(result.changes[0].records) == 5
        assert all(
            record["attribute_mapping_transformation_document"] is None
            for record in result.changes[0].records
        )
        assert result.mapped_attribute_count == 5


@pytest.mark.parametrize("layer", ["logical_entity", "dimensional_entity"])
async def test_generated_key_note_alone_cannot_create_a_mapping_pair(layer: ModeledEntityType) -> None:
    preparation = mapping_preparation(modeled_entity_type=layer, attribute_count=3)
    header = preparation.context.headers[0]
    attributes = tuple(item.model_copy(update={"is_surrogate_key": index == 0})
                       for index, item in enumerate(preparation.context.target.attributes))
    context = preparation.context.model_copy(update={
        "target": preparation.context.target.model_copy(update={"attributes": attributes}),
        "headers": (header.model_copy(update={"modeled_entity": header.modeled_entity.model_copy(
            update={"attributes": attributes})}),),
    })
    preparation = preparation.model_copy(update={"context": context})
    candidate = mapping_candidate()
    candidate["object_mapping"] = None
    candidate["attribute_mappings"] = [{
        "modeled_attribute_name": attributes[0].attribute_name,
        "attribute_mapping_transformation_document": {"transformation_logic": "Generated; omit from load SELECT."},
    }]
    validator = CompleteMappingCandidateValidator(preparation=preparation)
    assert not (await validator.validate(candidate)).issues
    result = validator.parse_validated(candidate)
    assert result.changes == ()
    assert result.normalized.outcome == "no_applicable_source"
    assert not result.has_transformations
