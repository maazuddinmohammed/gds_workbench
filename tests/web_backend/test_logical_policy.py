from __future__ import annotations

import pytest
from gds_etl_workbench.application.change_sets.model import StageModelChange
from gds_etl_workbench.domain.errors import InvalidRequestError
from gds_etl_workbench.domain.modeling_records import (
    LogicalAttributeRecord,
    LogicalEntityRecord,
)
from gds_etl_workbench.domain.snapshots.model import LogicalSection
from gds_workbench_api.features.logical.policy import project_logical_audit_policy


def _entity(name: str) -> LogicalEntityRecord:
    return LogicalEntityRecord(
        logical_entity_name=name,
        logical_entity_definition=f"One {name}.",
        logical_entity_type="core",
        logical_entity_type_detail=None,
        logical_entity_grain=f"One row per {name}.",
        logical_entity_dependency_order=0,
        logical_entity_confidence="high",
        logical_entity_status="active",
        logical_entity_is_locked=False,
        submodels=(),
        sources=(),
    )


def _business_attribute(entity: str) -> LogicalAttributeRecord:
    return LogicalAttributeRecord(
        logical_entity_name=entity,
        logical_attribute_name=f"{entity} ID",
        logical_attribute_definition=f"{entity} identifier.",
        logical_attribute_data_type="bigint",
        logical_attribute_is_nullable=False,
        logical_attribute_is_primary_key=True,
        logical_attribute_is_natural_key=True,
        logical_attribute_is_surrogate_key=False,
        logical_attribute_ordinal_position=1,
        logical_attribute_is_audit_column=False,
        logical_attribute_status="active",
        logical_attribute_is_locked=False,
        sources=(),
    )


def _template() -> dict[str, object]:
    return {
        "schema_version": "1.0",
        "columns": [
            {
                "semantic_name": "Created At",
                "data_type": "timestamp",
                "nullable": False,
                "definition": "Creation time.",
            },
            {
                "semantic_name": "Updated At",
                "data_type": "timestamp",
                "nullable": True,
                "definition": None,
            },
        ],
    }


def _attribute_records(
    changes: tuple[StageModelChange, ...],
) -> list[dict[str, object]]:
    change = next(item for item in changes if item.dataset == "logical_attribute")
    return change.records


def test_projection_adds_policy_columns_to_new_and_applied_active_entities() -> None:
    applied_entity = _entity("Account")
    applied_attribute = _business_attribute("Account")
    new_entity = _entity("Customer")
    new_attribute = _business_attribute("Customer")
    applied = LogicalSection(
        submodels=(),
        entities=(applied_entity,),
        attributes=(applied_attribute,),
        relationships=(),
    )
    changes = (
        StageModelChange(
            dataset="logical_entity",
            records=[new_entity.model_dump(mode="json")],
        ),
        StageModelChange(
            dataset="logical_attribute",
            records=[new_attribute.model_dump(mode="json")],
        ),
    )

    projected = project_logical_audit_policy(
        changes=changes,
        applied=applied,
        raw_template=_template(),
    )
    attributes = _attribute_records(projected)

    assert len(attributes) == 6
    audit = [item for item in attributes if item["logical_attribute_is_audit_column"]]
    assert {
        (item["logical_entity_name"], item["logical_attribute_name"]) for item in audit
    } == {
        ("Account", "Created At"),
        ("Account", "Updated At"),
        ("Customer", "Created At"),
        ("Customer", "Updated At"),
    }
    assert {item["logical_attribute_ordinal_position"] for item in audit} == {2, 3, 4}
    assert all(item["sources"] == [] for item in audit)


def test_missing_policy_is_an_exact_no_op() -> None:
    changes = (
        StageModelChange(
            dataset="logical_entity",
            records=[_entity("Customer").model_dump(mode="json")],
        ),
    )

    assert (
        project_logical_audit_policy(
            changes=changes,
            applied=None,
            raw_template=None,
        )
        is changes
    )


def test_projection_rejects_non_audit_name_collision() -> None:
    entity = _entity("Customer")
    collision = _business_attribute("Customer").model_copy(
        update={"logical_attribute_name": "Created At"}
    )
    applied = LogicalSection(
        submodels=(),
        entities=(entity,),
        attributes=(collision,),
        relationships=(),
    )

    with pytest.raises(InvalidRequestError):
        project_logical_audit_policy(
            changes=(),
            applied=applied,
            raw_template=_template(),
        )


def test_projection_rejects_invalid_template_without_partial_output() -> None:
    with pytest.raises(InvalidRequestError):
        project_logical_audit_policy(
            changes=(),
            applied=None,
            raw_template={"schema_version": "1.0", "columns": [], "extra": True},
        )


def test_source_system_provenance_retains_sources_and_natural_key_membership() -> None:
    from gds_etl_workbench.domain.modeling_records import (
        AttributePhysicalSourceRecord,
        PhysicalAttributeKey,
    )

    provenance = _business_attribute("Customer").model_copy(
        update={
            "logical_attribute_name": "SourceSystemID",
            "logical_attribute_is_audit_column": True,
            "sources": (
                AttributePhysicalSourceRecord(
                    support_source_type="attribute",
                    source_attribute=PhysicalAttributeKey(
                        tenant_code="GDS",
                        system_code="GDS",
                        connection_code="Lake",
                        object_schema="bronze",
                        object_name="Customer",
                        attribute_name="SourceSystemID",
                    ),
                    source_order=1,
                    rationale="Registered originating System.",
                    status="active",
                    is_locked=False,
                ),
            ),
        }
    )
    result = project_logical_audit_policy(
        changes=(
            StageModelChange(
                dataset="logical_attribute",
                records=[provenance.model_dump(mode="json")],
            ),
        ),
        applied=LogicalSection(
            submodels=(),
            entities=(_entity("Customer"),),
            attributes=(),
            relationships=(),
        ),
        raw_template={
            "schema_version": "1.0",
            "columns": [
                {
                    "semantic_name": "SourceSystemID",
                    "data_type": "bigint",
                    "nullable": False,
                    "definition": None,
                }
            ],
        },
    )
    record = _attribute_records(result)[0]
    assert record["logical_attribute_is_natural_key"] is True
    assert record["sources"] == provenance.model_dump(mode="json")["sources"]
