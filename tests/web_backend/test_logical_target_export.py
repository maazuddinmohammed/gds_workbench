"""Logical registration exports round-trip through the governed Metadata importer."""

import pytest
from gds_etl_workbench.domain.errors import InvalidRequestError
from gds_workbench_api.features.metadata.workbook import parse_metadata_workbook
from gds_workbench_api.features.model_targets.contracts import (
    ExportModelTargetsRequest,
    TargetLayer,
    TargetPlacement,
)
from gds_workbench_api.features.model_targets.service import registration_workbook


@pytest.mark.parametrize("layer,zone", [("logical", "silver"), ("dimensional", "gold")])
def test_logical_workbook_preserves_the_applied_design(
    layer: TargetLayer, zone: str
) -> None:
    command = ExportModelTargetsRequest(
        layer=layer,
        expected_model_revision=3,
        entity_ids=[10],
        object_schema="silver",
        object_type_code="table",
    )
    placement = TargetPlacement(
        tenant_code="platform",
        system_code="warehouse",
        connection_code="gds",
        source_tenant_code="sales",
    )
    entities = [
        {
            "entity_id": 10,
            "entity_name": "Customer",
            "definition": "=A literal business definition",
        }
    ]
    attributes = [
        {
            "entity_id": 10,
            "attribute_name": "CustomerId",
            "ordinal_position": 1,
            "definition": "Stable customer identifier.",
            "data_type": "DECIMAL(20,0)",
            "is_nullable": False,
            "is_natural_key": True,
            "is_surrogate_key": False,
            "is_audit_column": False,
            "is_masking_required": True,
        }
    ]
    content = registration_workbook(
        tenant_id=7,
        placement=placement,
        command=command,
        entities=entities,
        attributes=attributes,
    )
    sheets = parse_metadata_workbook(content, tenant_id=7)
    assert [sheet.code for sheet in sheets] == [f"{zone}_object", f"{zone}_attribute"]
    target = sheets[0].rows[0]
    column = sheets[1].rows[0]
    assert target["source_tenant_code"] == "sales"
    assert target["tenant_code"] == "platform"
    assert target["object_description"] == "=A literal business definition"
    assert target["zone_code"] == zone
    assert column["attribute_data_type"] == "DECIMAL(20,0)"
    assert column["attribute_inferred_data_type"] is None
    assert column["attribute_nullability"] is False
    assert column["is_natural_key"] is True
    assert column["is_masking_required"] is True
    assert column["is_locked"] is False
    tied = [
        {**attributes[0], "attribute_name": "First"},
        {**attributes[0], "attribute_name": "Second"},
    ]
    tied_sheets = parse_metadata_workbook(
        registration_workbook(
            tenant_id=7,
            placement=placement,
            command=command,
            entities=entities,
            attributes=tied,
        ),
        tenant_id=7,
    )
    assert [row["attribute_ordinal_position"] for row in tied_sheets[1].rows] == [1, 2]
    with pytest.raises(InvalidRequestError):
        registration_workbook(
            tenant_id=7,
            placement=placement,
            command=command,
            entities=entities,
            attributes=[],
        )
