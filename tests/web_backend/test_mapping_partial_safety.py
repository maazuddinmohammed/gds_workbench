"""Partial Mapping preserves protected logic and recognizes content-free templates."""

from typing import cast

import pytest
from atlas_platform.features.mapping.complete_candidate import (
    CompleteMappingCandidateValidator,
)
from atlas_platform.features.mapping.contracts import (
    MappingAttributeCandidate,
    MappingObjectCandidate,
)
from atlas_platform.features.mapping.preparation_contracts import (
    MappingModeledEntity,
    ModeledEntityType,
)
from atlas_platform.features.mapping.readiness import assess_mapping_readiness
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
def test_meaningful_custom_mapping_values_are_preserved_exactly(
    value: JsonValue,
) -> None:
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


async def test_unavailable_cyclic_lookup_does_not_discard_the_independent_mapping() -> None:
    prep = mapping_preparation(attribute_count=2)
    supported, cyclic = (a.attribute_name for a in prep.context.target.attributes)
    prep = prep.model_copy(
        update={
            "readiness": prep.readiness.model_copy(
                update={"deferred_dependency_attributes": (cyclic,)}
            )
        }
    )
    candidate: JsonValue = {
        "schema_version": "1.0",
        "object_mapping": {
            "object_dependency_order": 0,
            "mapping_transformation_document": {"sample_query": "FROM bronze.customer c"},
        },
        "attribute_mappings": [
            {
                "modeled_attribute_name": supported,
                "attribute_mapping_transformation_document": {"rule": "c.customer_id"},
            },
            {
                "modeled_attribute_name": cyclic,
                "attribute_mapping_transformation_document": {"rule": "unavailable.parent_id"},
            },
        ],
    }
    validator = CompleteMappingCandidateValidator(preparation=prep)
    assert not (await validator.validate(candidate)).issues
    result = validator.parse_validated(candidate)
    assert result.has_object_transformation and result.is_partial
    assert [row.modeled_attribute_name for row in result.normalized.attribute_mappings] == [
        supported
    ]
    assert result.mapped_attribute_count == 1 and result.attribute_count == 2


@pytest.mark.parametrize("layer", ("logical_entity", "dimensional_entity"))
@pytest.mark.parametrize("legacy", (False, True))
@pytest.mark.parametrize("prior", ("fresh", "replace", "omit", "null"))
async def test_circular_source_documents_leave_independent_rules_reviewable(
    layer: ModeledEntityType,
    legacy: bool,
    prior: str,
) -> None:
    saved = prior != "fresh"
    prep = mapping_preparation(attribute_count=3, modeled_entity_type=layer, existing=saved)
    target = prep.context.target
    driver = prep.context.sources[0].object
    # A Gold cyclic parent and a Silver driver can have the same numeric id.
    parent = (
        target.model_copy(update={"entity_id": driver.entity_id, "entity_name": "Parent"})
        if isinstance(driver, MappingModeledEntity)
        else target
    )
    lookup = prep.context.sources[0].model_copy(update={"role": "lookup", "object": parent})
    context = prep.context.model_copy(update={"sources": (*prep.context.sources, lookup)})
    readiness = prep.readiness.model_copy(
        update={
            "deferred_dependency_parent_ids": (parent.entity_id,),
            "deferred_dependency_attributes": ("CustomerID3",),
        }
    )
    family = layer.removesuffix("_entity")
    identity: dict[str, JsonValue] = {
        "entity_type": layer,
        "entity_schema_name": parent.entity_schema_name,
        "entity_name": parent.entity_name,
    }
    obj: dict[str, JsonValue] = {
        "source_tables": [identity],
        "sample_query": "FROM circular_parent AS p",
    }
    field: dict[str, JsonValue] = {
        "source_columns": [{**identity, "attribute_name": "CustomerID1"}],
        "transformation_logic": "p.CustomerID1",
    }
    if legacy:
        identity = {
            f"{family}_entity_schema_name": parent.entity_schema_name,
            f"{family}_entity_name": parent.entity_name,
        }
        obj = {f"source_{family}_entities": [{**identity, "alias": "p"}]}
        field = {
            f"source_{family}_attributes": [{**identity, f"{family}_attribute_name": "CustomerID1"}]
        }
    independent: dict[str, JsonValue] = {"transformation_logic": "driver.customer_id"}
    if isinstance(driver, MappingModeledEntity):
        independent["source_columns"] = [
            {
                "entity_type": driver.entity_type,
                "entity_schema_name": driver.entity_schema_name,
                "entity_name": driver.entity_name,
                "attribute_name": "customer_id",
            }
        ]
    answer: JsonValue = {
        "schema_version": "1.0",
        "object_mapping": {
            "object_dependency_order": 0,
            "mapping_transformation_document": obj,
        },
        "attribute_mappings": [
            {
                "modeled_attribute_name": name,
                "attribute_mapping_transformation_document": document,
            }
            for name, document in (
                ("CustomerID1", independent),
                ("CustomerID2", field),
                ("CustomerID3", field),
            )
        ],
    }
    if prior in ("omit", "null"):
        # A human already supplied the second-pass rowset and field rule.
        header = context.headers[0]
        first, second, third = header.attribute_mappings
        header = header.model_copy(
            update={
                "transformation_document": obj,
                "attribute_mappings": (
                    first,
                    second.model_copy(update={"transformation_document": field}),
                    third,
                ),
            }
        )
        context = context.model_copy(update={"headers": (header,)})
        answer["object_mapping"] = None
        fields = cast(list[JsonValue], answer["attribute_mappings"])
        fields[1:] = (
            []
            if prior == "omit"
            else [
                {
                    "modeled_attribute_name": "CustomerID2",
                    "attribute_mapping_transformation_document": None,
                }
            ]
        )
    prep = prep.model_copy(update={"context": context, "readiness": readiness})
    validator = CompleteMappingCandidateValidator(preparation=prep)
    assert not (await validator.validate(answer)).issues
    result = validator.parse_validated(answer)
    assert result.has_object_transformation is saved
    normalized = result.normalized
    assert normalized.object_mapping is None
    assert [item.modeled_attribute_name for item in normalized.attribute_mappings] == [
        "CustomerID1"
    ]
    if prior in ("fresh", "replace"):
        assert {item.modeled_attribute_name for item in normalized.issues} >= {None, "CustomerID2"}
    staged_attributes = [
        row
        for change in result.changes
        if change.dataset == "mapping_attribute"
        for row in change.records
    ]
    assert [row["modeled_attribute_name"] for row in staged_attributes] == ["CustomerID1"]
    assert result.mapped_attribute_count == (3 if saved else 1)
