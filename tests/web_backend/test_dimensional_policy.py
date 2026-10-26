from __future__ import annotations

import json
from copy import deepcopy
from typing import Literal

import pytest
from gds_etl_workbench.application.change_sets.project import StageProjectChange
from gds_etl_workbench.domain.errors import InvalidRequestError
from gds_etl_workbench.domain.modeling_records import (
    DimensionalAttributeRecord,
    DimensionalEntityRecord,
    DimensionalRelationshipRecord,
)
from gds_etl_workbench.domain.snapshots.project import DimensionalSection

from gds_workbench_api.features.dimensional.policy import (
    DimensionalProjectionConflictError,
    project_dimensional_foreign_key_policy,
    project_dimensional_gold_policy,
    validate_dimensional_gold_policy,
)


def _entity(name: str = "Customer Dimension") -> DimensionalEntityRecord:
    return DimensionalEntityRecord(
        dimensional_entity_schema_name="gold",
        dimensional_entity_name=name,
        dimensional_entity_definition=f"One {name}.",
        dimensional_entity_type="dimension",
        dimensional_fact_type=None,
        dimensional_entity_grain_definition=None,
        dimensional_entity_dependency_order=0,
        dimensional_entity_is_active=True,
        dimensional_entity_is_locked=False,
        sources=(),
    )


def _business_attribute(
    entity: str = "Customer Dimension",
) -> DimensionalAttributeRecord:
    return DimensionalAttributeRecord(
        dimensional_entity_schema_name="gold",
        dimensional_entity_name=entity,
        dimensional_attribute_name="Customer Name",
        dimensional_attribute_definition="Customer name.",
        dimensional_attribute_data_type="string",
        dimensional_attribute_is_nullable=True,
        dimensional_attribute_ordinal_position=1,
        dimensional_attribute_is_natural_key=False,
        dimensional_attribute_is_surrogate_key=False,
        dimensional_attribute_is_audit_column=False,
        dimensional_attribute_is_active=True,
        dimensional_attribute_is_locked=False,
        sources=(),
    )


def _fact(name: str = "Sales Fact") -> DimensionalEntityRecord:
    return DimensionalEntityRecord(
        dimensional_entity_schema_name="gold",
        dimensional_entity_name=name,
        dimensional_entity_definition="One row per sale.",
        dimensional_entity_type="fact",
        dimensional_fact_type="transaction",
        dimensional_entity_grain_definition="One row per sale and customer.",
        dimensional_entity_dependency_order=1,
        dimensional_entity_is_active=True,
        dimensional_entity_is_locked=False,
        sources=(),
    )


def _fact_business_attribute(*, nullable: bool = False) -> DimensionalAttributeRecord:
    """The Fact's business customer reference; a nullable one is not a natural key."""
    return _business_attribute("Sales Fact").model_copy(
        update={
            "dimensional_attribute_name": "Source Customer ID",
            "dimensional_attribute_definition": "Source customer identifier.",
            "dimensional_attribute_is_natural_key": not nullable,
            "dimensional_attribute_is_surrogate_key": False,
            "dimensional_attribute_is_nullable": nullable,
        }
    )


def _relationship(*, role_name: str | None = "Bill To Customer") -> DimensionalRelationshipRecord:
    return DimensionalRelationshipRecord(
        from_dimensional_entity_schema_name="gold",
        from_dimensional_entity_name="Sales Fact",
        from_dimensional_attribute_name="Source Customer ID",
        to_dimensional_entity_schema_name="gold",
        to_dimensional_entity_name="Customer Dimension",
        to_dimensional_attribute_name="Customer Name",
        dimensional_relationship_role_name=role_name,
        dimensional_relationship_basis="Sales customer evidence.",
        dimensional_relationship_is_active=True,
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
    changes: tuple[StageProjectChange, ...],
) -> list[dict[str, object]]:
    return next(change.records for change in changes if change.dataset == "dimensional_attribute")


def test_projection_adds_dimension_surrogate_before_business_and_audit() -> None:
    entity = _entity()
    business = _business_attribute()
    changes = (
        StageProjectChange(
            dataset="dimensional_entity",
            records=[entity.model_dump(mode="json")],
        ),
        StageProjectChange(
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
        "Customer Dimension key",
        "Customer Name",
        "Loaded At",
    ]
    assert [item["dimensional_attribute_is_audit_column"] for item in attributes] == [
        False,
        False,
        True,
    ]
    assert [item["dimensional_attribute_ordinal_position"] for item in attributes] == [
        1,
        2,
        3,
    ]
    assert attributes[0]["dimensional_attribute_is_surrogate_key"] is True
    assert all(item["sources"] == [] for item in attributes[1:])


def test_projection_adds_type_2_columns_from_project_policy() -> None:
    entity = _entity()
    historized = _business_attribute()
    projected = project_dimensional_gold_policy(
        changes=(
            StageProjectChange(
                dataset="dimensional_entity",
                records=[entity.model_dump(mode="json")],
            ),
            StageProjectChange(
                dataset="dimensional_attribute",
                records=[historized.model_dump(mode="json")],
            ),
        ),
        applied=None,
        scd_type="type_2",
        raw_technical_template=_technical_template(),
        raw_audit_template=_audit_template(),
    )

    attributes = _attribute_records(projected)
    assert [item["dimensional_attribute_name"] for item in attributes] == [
        "Customer Dimension key",
        "Customer Name",
        "Is Current",
        "Effective From",
        "Effective To",
        "Loaded At",
    ]
    assert all(item["dimensional_attribute_is_audit_column"] for item in attributes[2:])


def test_projection_covers_applied_active_and_new_active_entities() -> None:
    applied_entity = _entity("Account Dimension")
    inactive_entity = _entity("Inactive Dimension").model_copy(
        update={"dimensional_entity_is_active": False}
    )
    fact = DimensionalEntityRecord(
        dimensional_entity_schema_name="gold",
        dimensional_entity_name="Sales Fact",
        dimensional_entity_definition="One sales event.",
        dimensional_entity_type="fact",
        dimensional_fact_type="transaction",
        dimensional_entity_grain_definition="One row per sale.",
        dimensional_entity_dependency_order=1,
        dimensional_entity_is_active=True,
        dimensional_entity_is_locked=False,
        sources=(),
    )
    applied = DimensionalSection(
        entities=(applied_entity, inactive_entity),
        attributes=(),
        relationships=(),
    )

    projected = project_dimensional_gold_policy(
        changes=(
            StageProjectChange(
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
        (item["dimensional_entity_name"], item["dimensional_attribute_name"]) for item in attributes
    } == {
        ("Account Dimension", "Account Dimension key"),
        ("Account Dimension", "Loaded At"),
        ("Sales Fact", "Loaded At"),
        ("Sales Fact", "Sales Fact key"),
    }


def test_missing_policy_group_is_an_exact_no_op() -> None:
    changes = (
        StageProjectChange(
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
        dimensional_entity_schema_name="gold",
        dimensional_entity_name=entity.dimensional_entity_name,
        dimensional_attribute_name="Customer Dimension key",
        dimensional_attribute_definition="Old but structurally compatible definition.",
        dimensional_attribute_data_type="bigint",
        dimensional_attribute_is_nullable=False,
        dimensional_attribute_ordinal_position=1,
        dimensional_attribute_is_natural_key=False,
        dimensional_attribute_is_surrogate_key=True,
        dimensional_attribute_is_audit_column=False,
        dimensional_attribute_is_active=True,
        dimensional_attribute_is_locked=True,
        sources=(),
    )
    applied = DimensionalSection(
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
        dimensional_entity_schema_name="gold",
        dimensional_entity_name=entity.dimensional_entity_name,
        dimensional_attribute_name="Loaded At",
        dimensional_attribute_definition="Wrong type.",
        dimensional_attribute_data_type="string",
        dimensional_attribute_is_nullable=False,
        dimensional_attribute_ordinal_position=1,
        dimensional_attribute_is_natural_key=False,
        dimensional_attribute_is_surrogate_key=False,
        dimensional_attribute_is_audit_column=True,
        dimensional_attribute_is_active=True,
        dimensional_attribute_is_locked=False,
        sources=(),
    )
    applied = DimensionalSection(
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
            raw_audit_template={"schema_version": "1.0", "columns": [{}]},
        )


@pytest.mark.parametrize("nullable", [False, True])
def test_foreign_key_projection_binds_role_aware_endpoints_and_nullability(
    nullable: bool,
) -> None:
    dimension = _entity()
    fact = _fact()
    dimension_attribute = _business_attribute()
    # The foreign key may be null exactly when the business customer reference may be.
    fact_attribute = _fact_business_attribute(nullable=nullable)
    first = project_dimensional_gold_policy(
        changes=(
            StageProjectChange(
                dataset="dimensional_entity",
                records=[
                    dimension.model_dump(mode="json"),
                    fact.model_dump(mode="json"),
                ],
            ),
            StageProjectChange(
                dataset="dimensional_attribute",
                records=[
                    dimension_attribute.model_dump(mode="json"),
                    fact_attribute.model_dump(mode="json"),
                ],
            ),
            StageProjectChange(
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
        if item["dimensional_attribute_name"] in {"Bill To Customer key", "Customer Dimension key"}
        and not item["dimensional_attribute_is_surrogate_key"]
    )
    relationship = next(
        change.records[0] for change in projected if change.dataset == "dimensional_relationship"
    )

    assert foreign_key["dimensional_entity_name"] == "Sales Fact"
    assert foreign_key["dimensional_attribute_name"] == "Bill To Customer key"
    assert foreign_key["dimensional_attribute_data_type"] == "bigint"
    assert foreign_key["dimensional_attribute_is_nullable"] is nullable
    assert not foreign_key["dimensional_attribute_is_natural_key"]
    assert not foreign_key["dimensional_attribute_is_surrogate_key"]
    assert foreign_key["sources"] == []
    fact_attributes = [
        item for item in attributes if item["dimensional_entity_name"] == "Sales Fact"
    ]
    assert [item["dimensional_attribute_name"] for item in fact_attributes] == [
        "Sales Fact key",
        "Source Customer ID",
        "Bill To Customer key",
        "Loaded At",
    ]
    assert [item["dimensional_attribute_ordinal_position"] for item in fact_attributes] == [
        1,
        2,
        3,
        4,
    ]
    assert relationship["from_dimensional_attribute_name"] == "Bill To Customer key"
    assert relationship["to_dimensional_attribute_name"] == "Customer Dimension key"
    assert relationship["dimensional_relationship_role_name"] == "Bill To Customer"


def test_complete_gold_projection_is_idempotent_with_existing_fact_foreign_key() -> None:
    first = project_dimensional_gold_policy(
        changes=(
            StageProjectChange(
                dataset="dimensional_entity",
                records=[
                    _entity().model_dump(mode="json"),
                    _fact().model_dump(mode="json"),
                ],
            ),
            StageProjectChange(
                dataset="dimensional_attribute",
                records=[
                    _business_attribute().model_dump(mode="json"),
                    _fact_business_attribute().model_dump(mode="json"),
                ],
            ),
            StageProjectChange(
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
            StageProjectChange(
                dataset="dimensional_entity",
                records=[
                    _entity().model_dump(mode="json"),
                    _fact().model_dump(mode="json"),
                ],
            ),
            StageProjectChange(
                dataset="dimensional_attribute",
                records=[
                    _business_attribute().model_dump(mode="json"),
                    _fact_business_attribute().model_dump(mode="json"),
                ],
            ),
            StageProjectChange(
                dataset="dimensional_relationship",
                records=[_relationship(role_name=None).model_dump(mode="json")],
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
        if item["dimensional_attribute_name"] in {"Bill To Customer key", "Customer Dimension key"}
        and not item["dimensional_attribute_is_surrogate_key"]
    )

    assert foreign_key["dimensional_attribute_name"] == "Customer Dimension key"
    assert foreign_key["dimensional_attribute_is_nullable"] is False


def test_foreign_key_projection_rejects_reversed_fact_dimension_orientation() -> None:
    relationship = _relationship().model_copy(
        update={
            "from_dimensional_entity_schema_name": "gold",
            "from_dimensional_entity_name": "Customer Dimension",
            "from_dimensional_attribute_name": "Customer Name",
            "to_dimensional_entity_schema_name": "gold",
            "to_dimensional_entity_name": "Sales Fact",
            "to_dimensional_attribute_name": "Source Customer ID",
        }
    )
    changes = (
        StageProjectChange(
            dataset="dimensional_entity",
            records=[
                _entity().model_dump(mode="json"),
                _fact().model_dump(mode="json"),
            ],
        ),
        StageProjectChange(
            dataset="dimensional_attribute",
            records=[
                _business_attribute().model_dump(mode="json"),
                _fact_business_attribute().model_dump(mode="json"),
            ],
        ),
        StageProjectChange(
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


@pytest.mark.parametrize("scd_type", ["type_1", "type_2"])
def test_dimension_scd_policy_preserves_business_columns_and_excludes_fact_history(
    scd_type: Literal["type_1", "type_2"],
) -> None:
    projected = project_dimensional_gold_policy(
        changes=(
            StageProjectChange(
                dataset="dimensional_entity",
                records=[
                    _entity().model_dump(mode="json"),
                    _fact().model_dump(mode="json"),
                ],
            ),
            StageProjectChange(
                dataset="dimensional_attribute",
                records=[
                    _business_attribute().model_dump(mode="json"),
                    _fact_business_attribute().model_dump(mode="json"),
                ],
            ),
        ),
        applied=None,
        raw_technical_template=_technical_template(),
        raw_audit_template=_audit_template(),
        scd_type=scd_type,
    )
    rows = _attribute_records(projected)
    business = next(row for row in rows if row["dimensional_attribute_name"] == "Customer Name")
    assert not business["dimensional_attribute_is_surrogate_key"]
    history = [row for row in rows if row["dimensional_attribute_name"] == "Effective From"]
    assert len(history) == (1 if scd_type == "type_2" else 0)
    assert all(row["dimensional_entity_name"] == "Customer Dimension" for row in history)


def test_combined_audit_template_projects_history_in_audit_order() -> None:
    from gds_workbench_api.features.projects.templates import default_project_templates
    from gds_workbench_api.features.workflows.authoring.gold_policy import (
        effective_gold_templates,
    )

    combined = default_project_templates()["gold_model_audit_columns_template"]
    assert isinstance(combined, dict)
    technical, audit = effective_gold_templates(None, combined)
    projected = project_dimensional_gold_policy(
        changes=(
            StageProjectChange(
                dataset="dimensional_entity",
                records=[_entity().model_dump(mode="json")],
            ),
        ),
        applied=None,
        raw_technical_template=technical,
        raw_audit_template=audit,
        scd_type="type_2",
    )
    attributes = _attribute_records(projected)
    names = [item["dimensional_attribute_name"] for item in attributes]
    source_index = names.index("SourceSystemID")
    assert names[source_index + 1 : source_index + 4] == [
        "IsCurrentRecord",
        "RecordStartTime",
        "RecordEndTime",
    ]
    assert names.index("RecordEndTime") < names.index("GDSBatchID")
    for item in attributes[source_index + 1 : source_index + 4]:
        assert item["dimensional_attribute_is_audit_column"] is True


@pytest.mark.parametrize("locked", [False, True])
def test_existing_non_audit_column_cannot_be_reclassified_as_history(
    locked: bool,
) -> None:
    entity = _entity()
    projected = project_dimensional_gold_policy(
        changes=(
            StageProjectChange(
                dataset="dimensional_entity", records=[entity.model_dump(mode="json")]
            ),
        ),
        applied=None,
        raw_technical_template=_technical_template(),
        raw_audit_template=_audit_template(),
        scd_type="type_2",
    )
    attributes = [
        DimensionalAttributeRecord.model_validate_json(json.dumps(row))
        for row in _attribute_records(projected)
    ]
    old = tuple(
        row.model_copy(
            update={
                "dimensional_attribute_is_audit_column": False,
                "dimensional_attribute_is_locked": locked,
            }
        )
        if row.dimensional_attribute_name in {"Is Current", "Effective From", "Effective To"}
        else row
        for row in attributes
    )
    baseline = DimensionalSection(entities=(entity,), attributes=old, relationships=())
    with pytest.raises(DimensionalProjectionConflictError):
        project_dimensional_gold_policy(
            changes=(),
            applied=baseline,
            raw_technical_template=_technical_template(),
            raw_audit_template=_audit_template(),
            scd_type="type_2",
        )


def _projected_baseline(*, with_relationship: bool = True) -> DimensionalSection:
    changes = (
        StageProjectChange(
            dataset="dimensional_entity",
            records=[
                _entity().model_dump(mode="json"),
                _fact().model_dump(mode="json"),
            ],
        ),
        StageProjectChange(
            dataset="dimensional_attribute",
            records=[
                _business_attribute().model_dump(mode="json"),
                _fact_business_attribute().model_dump(mode="json"),
            ],
        ),
        *(
            (
                StageProjectChange(
                    dataset="dimensional_relationship",
                    records=[
                        _relationship().model_dump(mode="json"),
                    ],
                ),
            )
            if with_relationship
            else ()
        ),
    )
    projected = project_dimensional_gold_policy(
        changes=changes,
        applied=None,
        raw_technical_template=_technical_template(),
        raw_audit_template=_audit_template(),
    )
    projected = project_dimensional_foreign_key_policy(
        changes=projected,
        applied=None,
        raw_technical_template=_technical_template(),
    )
    return DimensionalSection(
        entities=(_entity(), _fact()),
        attributes=tuple(
            DimensionalAttributeRecord.model_validate_json(json.dumps(row))
            for row in _attribute_records(projected)
        ),
        relationships=tuple(
            DimensionalRelationshipRecord.model_validate_json(json.dumps(row))
            for change in projected
            if change.dataset == "dimensional_relationship"
            for row in change.records
        ),
    )


def test_foreign_key_projection_keeps_each_role_playing_edge_on_its_own_key() -> None:
    baseline = _projected_baseline()
    added = _relationship(role_name="Alpha Customer")
    changes = project_dimensional_gold_policy(
        changes=(
            StageProjectChange(
                dataset="dimensional_relationship",
                records=[added.model_dump(mode="json")],
            ),
        ),
        applied=baseline,
        raw_technical_template=_technical_template(),
        raw_audit_template=_audit_template(),
    )
    projected = project_dimensional_foreign_key_policy(
        changes=changes,
        applied=baseline,
        raw_technical_template=_technical_template(),
    )
    fact_columns: dict[str, object] = {
        row.dimensional_attribute_name: row.dimensional_attribute_ordinal_position
        for row in baseline.attributes
        if row.dimensional_entity_name == "Sales Fact"
    }
    fact_columns.update(
        {
            str(row["dimensional_attribute_name"]): row["dimensional_attribute_ordinal_position"]
            for row in _attribute_records(projected)
            if row["dimensional_entity_name"] == "Sales Fact"
        }
    )
    assert fact_columns["Alpha Customer key"] == 3
    assert fact_columns["Bill To Customer key"] == 4
    assert fact_columns["Loaded At"] == 5


def test_foreign_key_projection_cannot_take_over_a_business_column() -> None:
    baseline = _projected_baseline(with_relationship=False)
    collision = _fact_business_attribute().model_copy(
        update={
            "dimensional_attribute_name": "Bill To Customer key",
            "dimensional_attribute_is_natural_key": False,
            "dimensional_attribute_is_nullable": True,
            "dimensional_attribute_data_type": "bigint",
            "dimensional_attribute_definition": "An independently maintained business value.",
        }
    )
    baseline = baseline.model_copy(update={"attributes": (*baseline.attributes, collision)})
    with pytest.raises(DimensionalProjectionConflictError, match="existing business Attribute"):
        project_dimensional_foreign_key_policy(
            changes=(
                StageProjectChange(
                    dataset="dimensional_relationship",
                    records=[_relationship().model_dump(mode="json")],
                ),
            ),
            applied=baseline,
            raw_technical_template=_technical_template(),
        )


def test_inactive_relationship_does_not_create_an_active_foreign_key() -> None:
    baseline = _projected_baseline(with_relationship=False)
    inactive = _relationship().model_copy(update={"dimensional_relationship_is_active": False})
    changes = (
        StageProjectChange(
            dataset="dimensional_relationship",
            records=[inactive.model_dump(mode="json")],
        ),
    )
    projected = project_dimensional_foreign_key_policy(
        changes=changes,
        applied=baseline,
        raw_technical_template=_technical_template(),
    )
    assert projected == changes


def test_inactive_proposal_does_not_reclassify_business_attribute_during_gold_projection() -> None:
    baseline = _projected_baseline(with_relationship=False)
    baseline = baseline.model_copy(
        update={
            "attributes": tuple(
                row.model_copy(
                    update={
                        "dimensional_attribute_name": "Bill To Customer key",
                        "dimensional_attribute_is_natural_key": False,
                    }
                )
                if row.dimensional_entity_name == "Sales Fact"
                and row.dimensional_attribute_name == "Source Customer ID"
                else row
                for row in baseline.attributes
            ),
        }
    )
    inactive = _relationship().model_copy(
        update={
            "from_dimensional_attribute_name": "Bill To Customer key",
            "dimensional_relationship_is_active": False,
        }
    )
    changes = project_dimensional_gold_policy(
        changes=(
            StageProjectChange(
                dataset="dimensional_relationship",
                records=[inactive.model_dump(mode="json")],
            ),
        ),
        applied=baseline,
        raw_technical_template=_technical_template(),
        raw_audit_template=_audit_template(),
    )
    projected = project_dimensional_foreign_key_policy(
        changes=changes,
        applied=baseline,
        raw_technical_template=_technical_template(),
    )
    effective = {
        row.dimensional_attribute_name: row.model_dump(mode="json")
        for row in baseline.attributes
        if row.dimensional_entity_name == "Sales Fact"
    }
    effective.update(
        {
            str(row["dimensional_attribute_name"]): row
            for change in projected
            if change.dataset == "dimensional_attribute"
            for row in change.records
            if row["dimensional_entity_name"] == "Sales Fact"
        }
    )
    assert {
        name: row["dimensional_attribute_ordinal_position"] for name, row in effective.items()
    } == {
        "Sales Fact key": 1,
        "Bill To Customer key": 2,
        "Loaded At": 3,
    }
