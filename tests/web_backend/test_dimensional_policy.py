from __future__ import annotations

from copy import deepcopy
from typing import Literal

import pytest
from gds_etl_workbench.domain.errors import InvalidRequestError
from gds_etl_workbench.domain.modeling_records import (
    DimensionalAttributeRecord,
    DimensionalEntityRecord,
    DimensionalRelationshipRecord,
)
from gds_etl_workbench.tools.change_sets.model import StageModelChange
from gds_etl_workbench.tools.snapshots.model.contracts import DimensionalSection

from gds_workbench_api.features.dimensional.policy import (
    project_dimensional_foreign_key_policy,
    project_dimensional_gold_policy,
    validate_dimensional_gold_policy,
)


def _entity(name: str = "Customer Dimension") -> DimensionalEntityRecord:
    return DimensionalEntityRecord(
        dimensional_entity_name=name,
        dimensional_entity_definition=f"One {name}.",
        dimensional_entity_type="dimension",
        dimensional_fact_type=None,
        dimensional_entity_grain_definition=None,
        dimensional_entity_dependency_order=0,
        dimensional_entity_confidence="high",
        dimensional_entity_status="active",
        dimensional_entity_is_locked=False,
        submodels=(),
        sources=(),
    )


def _business_attribute(
    entity: str = "Customer Dimension",
    *,
    change_behavior: Literal["fixed", "overwrite", "historize"] | None = "fixed",
) -> DimensionalAttributeRecord:
    return DimensionalAttributeRecord(
        dimensional_entity_name=entity,
        dimensional_attribute_name="Customer Name",
        dimensional_attribute_definition="Customer name.",
        dimensional_attribute_data_type="string",
        dimensional_attribute_is_nullable=True,
        dimensional_attribute_ordinal_position=1,
        dimensional_attribute_role="descriptor",
        dimensional_attribute_key_role="none",
        dimensional_attribute_is_grain_component=False,
        dimensional_attribute_additivity=None,
        dimensional_attribute_default_aggregation=None,
        dimensional_attribute_aggregation_basis=None,
        dimensional_attribute_change_behavior=change_behavior,
        dimensional_attribute_is_audit_column=False,
        dimensional_attribute_confidence="high",
        dimensional_attribute_status="active",
        dimensional_attribute_is_locked=False,
        sources=(),
    )


def _fact(name: str = "Sales Fact") -> DimensionalEntityRecord:
    return DimensionalEntityRecord(
        dimensional_entity_name=name,
        dimensional_entity_definition="One row per sale.",
        dimensional_entity_type="fact",
        dimensional_fact_type="transaction",
        dimensional_entity_grain_definition="One row per sale and customer.",
        dimensional_entity_dependency_order=1,
        dimensional_entity_confidence="high",
        dimensional_entity_status="active",
        dimensional_entity_is_locked=False,
        submodels=(),
        sources=(),
    )


def _fact_business_attribute() -> DimensionalAttributeRecord:
    return _business_attribute("Sales Fact").model_copy(
        update={
            "dimensional_attribute_name": "Source Customer ID",
            "dimensional_attribute_definition": "Source customer identifier.",
            "dimensional_attribute_role": "key",
            "dimensional_attribute_key_role": "business",
            "dimensional_attribute_is_nullable": True,
        }
    )


def _relationship(
    *,
    is_optional: bool = True,
    role_name: str | None = "Bill To Customer",
) -> DimensionalRelationshipRecord:
    return DimensionalRelationshipRecord(
        dimensional_relationship_name="Sales to customer",
        dimensional_relationship_definition="Each sale references its customer.",
        from_dimensional_entity_name="Sales Fact",
        from_dimensional_attribute_name="Source Customer ID",
        to_dimensional_entity_name="Customer Dimension",
        to_dimensional_attribute_name="Customer Name",
        dimensional_relationship_kind="foreign_key",
        dimensional_relationship_cardinality="many_to_one",
        dimensional_relationship_is_optional=is_optional,
        dimensional_relationship_role_name=role_name,
        dimensional_relationship_confidence="high",
        dimensional_relationship_basis="Sales customer evidence.",
        dimensional_relationship_cardinality_basis="Many sales reference one customer.",
        dimensional_relationship_status="active",
        dimensional_relationship_is_locked=False,
    )


def _technical_template() -> dict[str, object]:
    return {
        "schema_version": "1.0",
        "dimension_surrogate_key": {
            "semantic_name_template": "{entity_name} key",
            "data_type": "bigint",
            "nullable": False,
            "definition_template": "Surrogate key for {entity_name}.",
        },
        "fact_bridge_foreign_key": {
            "with_role_semantic_name_template": "{role_name} key",
            "without_role_semantic_name_template": "{entity_name} key",
            "definition_template": "Foreign key to {entity_name}.",
        },
        "type_2": {
            "effective_from": {
                "semantic_name": "Effective From",
                "data_type": "TIMESTAMPTZ",
                "nullable": False,
                "definition": "Type 2 effective start.",
            },
            "effective_to": {
                "semantic_name": "Effective To",
                "data_type": "TIMESTAMPTZ",
                "nullable": True,
                "definition": "Type 2 effective end.",
            },
            "is_current": {
                "semantic_name": "Is Current",
                "data_type": "BOOLEAN",
                "nullable": False,
                "definition": "Current Type 2 row.",
            },
        },
    }


def _audit_template() -> dict[str, object]:
    return {
        "schema_version": "1.0",
        "columns": [
            {
                "semantic_name": "Loaded At",
                "data_type": "TIMESTAMPTZ",
                "nullable": False,
                "definition": "Warehouse load time.",
            }
        ],
    }


def _attribute_records(
    changes: tuple[StageModelChange, ...],
) -> list[dict[str, object]]:
    return next(
        change.records
        for change in changes
        if change.dataset == "dimensional_attribute"
    )


def test_projection_adds_dimension_surrogate_and_audit_after_business_attributes() -> (
    None
):
    entity = _entity()
    business = _business_attribute()
    changes = (
        StageModelChange(
            dataset="dimensional_entity",
            records=[entity.model_dump(mode="json")],
        ),
        StageModelChange(
            dataset="dimensional_attribute",
            records=[business.model_dump(mode="json")],
        ),
    )

    projected = project_dimensional_gold_policy(
        changes=changes,
        applied=None,
        raw_technical_template=_technical_template(),
        raw_audit_template=_audit_template(),
    )
    attributes = _attribute_records(projected)

    assert [item["dimensional_attribute_name"] for item in attributes] == [
        "Customer Name",
        "Customer Dimension key",
        "Loaded At",
    ]
    assert [item["dimensional_attribute_role"] for item in attributes] == [
        "descriptor",
        "technical",
        "audit",
    ]
    assert [item["dimensional_attribute_ordinal_position"] for item in attributes] == [
        1,
        2,
        3,
    ]
    assert attributes[1]["dimensional_attribute_key_role"] == "surrogate"
    assert all(item["sources"] == [] for item in attributes[1:])


def test_projection_adds_type_2_columns_only_when_dimension_historizes() -> None:
    entity = _entity()
    historized = _business_attribute(change_behavior="historize")
    projected = project_dimensional_gold_policy(
        changes=(
            StageModelChange(
                dataset="dimensional_entity",
                records=[entity.model_dump(mode="json")],
            ),
            StageModelChange(
                dataset="dimensional_attribute",
                records=[historized.model_dump(mode="json")],
            ),
        ),
        applied=None,
        raw_technical_template=_technical_template(),
        raw_audit_template=_audit_template(),
    )

    attributes = _attribute_records(projected)
    assert [item["dimensional_attribute_name"] for item in attributes] == [
        "Customer Name",
        "Customer Dimension key",
        "Effective From",
        "Effective To",
        "Is Current",
        "Loaded At",
    ]
    assert [item["dimensional_attribute_role"] for item in attributes[1:5]] == [
        "technical",
        "technical",
        "technical",
        "technical",
    ]


def test_projection_covers_applied_active_and_new_needs_review_entities() -> None:
    applied_entity = _entity("Account Dimension")
    inactive_entity = _entity("Inactive Dimension").model_copy(
        update={"dimensional_entity_status": "inactive"}
    )
    fact = DimensionalEntityRecord(
        dimensional_entity_name="Sales Fact",
        dimensional_entity_definition="One sales event.",
        dimensional_entity_type="fact",
        dimensional_fact_type="transaction",
        dimensional_entity_grain_definition="One row per sale.",
        dimensional_entity_dependency_order=1,
        dimensional_entity_confidence="high",
        dimensional_entity_status="needs_review",
        dimensional_entity_is_locked=False,
        submodels=(),
        sources=(),
    )
    applied = DimensionalSection(
        submodels=(),
        entities=(applied_entity, inactive_entity),
        attributes=(),
        relationships=(),
    )

    projected = project_dimensional_gold_policy(
        changes=(
            StageModelChange(
                dataset="dimensional_entity",
                records=[fact.model_dump(mode="json")],
            ),
        ),
        applied=applied,
        raw_technical_template=_technical_template(),
        raw_audit_template=_audit_template(),
    )
    attributes = _attribute_records(projected)

    assert {
        (item["dimensional_entity_name"], item["dimensional_attribute_name"])
        for item in attributes
    } == {
        ("Account Dimension", "Account Dimension key"),
        ("Account Dimension", "Loaded At"),
        ("Sales Fact", "Loaded At"),
    }


def test_missing_policy_group_is_an_exact_no_op() -> None:
    changes = (
        StageModelChange(
            dataset="dimensional_entity",
            records=[_entity().model_dump(mode="json")],
        ),
    )

    assert (
        project_dimensional_gold_policy(
            changes=changes,
            applied=None,
            raw_technical_template=None,
            raw_audit_template=None,
        )
        is changes
    )


@pytest.mark.parametrize(
    ("naming", "technical", "audit"),
    [
        (None, _technical_template(), _audit_template()),
        ("Use Gold names.", None, _audit_template()),
        ("Use Gold names.", _technical_template(), None),
    ],
)
def test_dimensional_readiness_requires_complete_gold_policy_group(
    naming: str | None,
    technical: dict[str, object] | None,
    audit: dict[str, object] | None,
) -> None:
    with pytest.raises(InvalidRequestError):
        validate_dimensional_gold_policy(
            naming_instructions=naming,
            raw_technical_template=technical,
            raw_audit_template=audit,
        )


def test_dimensional_readiness_parses_the_complete_gold_policy_group() -> None:
    validate_dimensional_gold_policy(
        naming_instructions="Use Gold names.",
        raw_technical_template=_technical_template(),
        raw_audit_template=_audit_template(),
    )


def test_projection_rejects_business_name_collision() -> None:
    entity = _entity()
    collision = _business_attribute().model_copy(
        update={"dimensional_attribute_name": "Customer Dimension key"}
    )
    applied = DimensionalSection(
        submodels=(),
        entities=(entity,),
        attributes=(collision,),
        relationships=(),
    )

    with pytest.raises(InvalidRequestError):
        project_dimensional_gold_policy(
            changes=(),
            applied=applied,
            raw_technical_template=_technical_template(),
            raw_audit_template=_audit_template(),
        )


def test_projection_rejects_locked_policy_rewrite() -> None:
    entity = _entity()
    locked_surrogate = DimensionalAttributeRecord(
        dimensional_entity_name=entity.dimensional_entity_name,
        dimensional_attribute_name="Customer Dimension key",
        dimensional_attribute_definition="Old but structurally compatible definition.",
        dimensional_attribute_data_type="bigint",
        dimensional_attribute_is_nullable=False,
        dimensional_attribute_ordinal_position=1,
        dimensional_attribute_role="technical",
        dimensional_attribute_key_role="surrogate",
        dimensional_attribute_is_grain_component=True,
        dimensional_attribute_additivity=None,
        dimensional_attribute_default_aggregation=None,
        dimensional_attribute_aggregation_basis=None,
        dimensional_attribute_change_behavior="fixed",
        dimensional_attribute_is_audit_column=False,
        dimensional_attribute_confidence="high",
        dimensional_attribute_status="active",
        dimensional_attribute_is_locked=True,
        sources=(),
    )
    applied = DimensionalSection(
        submodels=(),
        entities=(entity,),
        attributes=(locked_surrogate,),
        relationships=(),
    )

    with pytest.raises(InvalidRequestError):
        project_dimensional_gold_policy(
            changes=(),
            applied=applied,
            raw_technical_template=_technical_template(),
            raw_audit_template=_audit_template(),
        )


def test_projection_rejects_incompatible_existing_policy_attribute() -> None:
    entity = _entity()
    incompatible = DimensionalAttributeRecord(
        dimensional_entity_name=entity.dimensional_entity_name,
        dimensional_attribute_name="Loaded At",
        dimensional_attribute_definition="Wrong type.",
        dimensional_attribute_data_type="string",
        dimensional_attribute_is_nullable=False,
        dimensional_attribute_ordinal_position=1,
        dimensional_attribute_role="audit",
        dimensional_attribute_key_role="none",
        dimensional_attribute_is_grain_component=False,
        dimensional_attribute_additivity=None,
        dimensional_attribute_default_aggregation=None,
        dimensional_attribute_aggregation_basis=None,
        dimensional_attribute_change_behavior="fixed",
        dimensional_attribute_is_audit_column=True,
        dimensional_attribute_confidence="high",
        dimensional_attribute_status="active",
        dimensional_attribute_is_locked=False,
        sources=(),
    )
    applied = DimensionalSection(
        submodels=(),
        entities=(entity,),
        attributes=(incompatible,),
        relationships=(),
    )

    with pytest.raises(InvalidRequestError):
        project_dimensional_gold_policy(
            changes=(),
            applied=applied,
            raw_technical_template=_technical_template(),
            raw_audit_template=_audit_template(),
        )


def test_projection_rejects_partial_or_invalid_v1_policy_group() -> None:
    technical = _technical_template()
    invalid_technical = deepcopy(technical)
    dimension_key = invalid_technical["dimension_surrogate_key"]
    assert isinstance(dimension_key, dict)
    dimension_key["semantic_name_template"] = "{unknown} key"

    with pytest.raises(InvalidRequestError):
        project_dimensional_gold_policy(
            changes=(),
            applied=None,
            raw_technical_template=technical,
            raw_audit_template=None,
        )
    with pytest.raises(InvalidRequestError):
        project_dimensional_gold_policy(
            changes=(),
            applied=None,
            raw_technical_template=invalid_technical,
            raw_audit_template=_audit_template(),
        )
    with pytest.raises(InvalidRequestError):
        project_dimensional_gold_policy(
            changes=(),
            applied=None,
            raw_technical_template=technical,
            raw_audit_template={"schema_version": "1.0", "columns": []},
        )


def test_foreign_key_projection_binds_role_aware_endpoints_and_nullability() -> None:
    dimension = _entity()
    fact = _fact()
    dimension_attribute = _business_attribute()
    fact_attribute = _fact_business_attribute()
    first = project_dimensional_gold_policy(
        changes=(
            StageModelChange(
                dataset="dimensional_entity",
                records=[
                    dimension.model_dump(mode="json"),
                    fact.model_dump(mode="json"),
                ],
            ),
            StageModelChange(
                dataset="dimensional_attribute",
                records=[
                    dimension_attribute.model_dump(mode="json"),
                    fact_attribute.model_dump(mode="json"),
                ],
            ),
            StageModelChange(
                dataset="dimensional_relationship",
                records=[_relationship().model_dump(mode="json")],
            ),
        ),
        applied=None,
        raw_technical_template=_technical_template(),
        raw_audit_template=_audit_template(),
    )

    projected = project_dimensional_foreign_key_policy(
        changes=first,
        applied=None,
        raw_technical_template=_technical_template(),
    )
    attributes = _attribute_records(projected)
    foreign_key = next(
        item
        for item in attributes
        if item["dimensional_attribute_key_role"] == "foreign"
    )
    relationship = next(
        change.records[0]
        for change in projected
        if change.dataset == "dimensional_relationship"
    )

    assert foreign_key["dimensional_entity_name"] == "Sales Fact"
    assert foreign_key["dimensional_attribute_name"] == "Bill To Customer key"
    assert foreign_key["dimensional_attribute_data_type"] == "bigint"
    assert foreign_key["dimensional_attribute_is_nullable"] is True
    assert foreign_key["dimensional_attribute_role"] == "technical"
    assert foreign_key["dimensional_attribute_is_grain_component"] is True
    assert foreign_key["sources"] == []
    fact_attributes = [
        item for item in attributes if item["dimensional_entity_name"] == "Sales Fact"
    ]
    assert [item["dimensional_attribute_name"] for item in fact_attributes] == [
        "Source Customer ID",
        "Bill To Customer key",
        "Loaded At",
    ]
    assert [
        item["dimensional_attribute_ordinal_position"] for item in fact_attributes
    ] == [1, 2, 3]
    assert relationship["from_dimensional_attribute_name"] == "Bill To Customer key"
    assert relationship["to_dimensional_attribute_name"] == "Customer Dimension key"
    assert relationship["dimensional_relationship_is_optional"] is True


def test_complete_gold_projection_is_idempotent_with_existing_fact_foreign_key() -> (
    None
):
    first = project_dimensional_gold_policy(
        changes=(
            StageModelChange(
                dataset="dimensional_entity",
                records=[
                    _entity().model_dump(mode="json"),
                    _fact().model_dump(mode="json"),
                ],
            ),
            StageModelChange(
                dataset="dimensional_attribute",
                records=[
                    _business_attribute().model_dump(mode="json"),
                    _fact_business_attribute().model_dump(mode="json"),
                ],
            ),
            StageModelChange(
                dataset="dimensional_relationship",
                records=[_relationship().model_dump(mode="json")],
            ),
        ),
        applied=None,
        raw_technical_template=_technical_template(),
        raw_audit_template=_audit_template(),
    )
    first = project_dimensional_foreign_key_policy(
        changes=first,
        applied=None,
        raw_technical_template=_technical_template(),
    )
    by_dataset = {change.dataset: tuple(change.records) for change in first}
    applied = DimensionalSection.model_validate(
        {
            "submodels": (),
            "entities": by_dataset["dimensional_entity"],
            "attributes": by_dataset["dimensional_attribute"],
            "relationships": by_dataset["dimensional_relationship"],
        },
        strict=False,
    )

    second = project_dimensional_gold_policy(
        changes=(),
        applied=applied,
        raw_technical_template=_technical_template(),
        raw_audit_template=_audit_template(),
    )
    second = project_dimensional_foreign_key_policy(
        changes=second,
        applied=applied,
        raw_technical_template=_technical_template(),
    )

    assert second == ()


def test_foreign_key_projection_uses_dimension_name_without_role() -> None:
    first = project_dimensional_gold_policy(
        changes=(
            StageModelChange(
                dataset="dimensional_entity",
                records=[
                    _entity().model_dump(mode="json"),
                    _fact().model_dump(mode="json"),
                ],
            ),
            StageModelChange(
                dataset="dimensional_attribute",
                records=[
                    _business_attribute().model_dump(mode="json"),
                    _fact_business_attribute().model_dump(mode="json"),
                ],
            ),
            StageModelChange(
                dataset="dimensional_relationship",
                records=[
                    _relationship(is_optional=False, role_name=None).model_dump(
                        mode="json"
                    )
                ],
            ),
        ),
        applied=None,
        raw_technical_template=_technical_template(),
        raw_audit_template=_audit_template(),
    )

    projected = project_dimensional_foreign_key_policy(
        changes=first,
        applied=None,
        raw_technical_template=_technical_template(),
    )
    foreign_key = next(
        item
        for item in _attribute_records(projected)
        if item["dimensional_attribute_key_role"] == "foreign"
    )

    assert foreign_key["dimensional_attribute_name"] == "Customer Dimension key"
    assert foreign_key["dimensional_attribute_is_nullable"] is False


def test_foreign_key_projection_rejects_reversed_fact_dimension_orientation() -> None:
    relationship = _relationship().model_copy(
        update={
            "from_dimensional_entity_name": "Customer Dimension",
            "from_dimensional_attribute_name": "Customer Name",
            "to_dimensional_entity_name": "Sales Fact",
            "to_dimensional_attribute_name": "Source Customer ID",
        }
    )
    changes = (
        StageModelChange(
            dataset="dimensional_entity",
            records=[
                _entity().model_dump(mode="json"),
                _fact().model_dump(mode="json"),
            ],
        ),
        StageModelChange(
            dataset="dimensional_attribute",
            records=[
                _business_attribute().model_dump(mode="json"),
                _fact_business_attribute().model_dump(mode="json"),
            ],
        ),
        StageModelChange(
            dataset="dimensional_relationship",
            records=[relationship.model_dump(mode="json")],
        ),
    )

    with pytest.raises(InvalidRequestError):
        project_dimensional_foreign_key_policy(
            changes=changes,
            applied=None,
            raw_technical_template=_technical_template(),
        )
