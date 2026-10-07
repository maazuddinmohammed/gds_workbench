from datetime import UTC, datetime
from io import BytesIO

import pytest
from gds_workbench_api.features.metadata_enrichment.workbook import (
    build_enrichment_workbook,
)
from gds_workbench_api.features.model_input_scope.contracts import (
    ModelInputScopeAttribute,
    ModelInputScopeObject,
)
from openpyxl import load_workbook


@pytest.fixture
def dictionary_rows() -> list[tuple[ModelInputScopeObject, ModelInputScopeAttribute]]:
    obj = ModelInputScopeObject(
        model_input_scope_id=1,
        object_id=1,
        connection_id=1,
        system_id=1,
        system_code="CRM",
        system_name="CRM",
        source_tenant_id=1,
        source_tenant_code="TEST",
        source_tenant_name="Test",
        object_schema="crm",
        object_name="Customer",
        zone_code="source",
        attribute_count=1,
        is_model_input_eligible=True,
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )
    attr = ModelInputScopeAttribute(
        attribute_id=1,
        review_revision="a" * 64,
        attribute_name="Id",
        attribute_ordinal_position=1,
        attribute_data_type="STRING",
        attribute_inferred_data_type=None,
        attribute_nullability=False,
        is_surrogate_key=False,
        is_natural_key=False,
        is_meta_data=False,
        is_masking_required=False,
        is_mapped=False,
        is_purge=False,
        is_locked=False,
        is_active=True,
    )
    return [(obj, attr)]


@pytest.mark.parametrize("value", ["x" * 32768, "😀" * 16384, "invalid\x01text", "bad\ud800"])
def test_export_rejects_unsupported_cells_before_writer_truncation(
    dictionary_rows: list[tuple[ModelInputScopeObject, ModelInputScopeAttribute]],
    value: str,
) -> None:
    obj, attr = dictionary_rows[0]
    with pytest.raises(ValueError, match="unsupported cell text") as error:
        build_enrichment_workbook([(obj.model_copy(update={"object_description": value}), attr)])
    assert value not in str(error.value)


def test_unknowns_remain_blank_and_large_counts_remain_exact(
    dictionary_rows: list[tuple[ModelInputScopeObject, ModelInputScopeAttribute]],
) -> None:
    obj, attr = dictionary_rows[0]
    content = build_enrichment_workbook(
        [
            (
                obj,
                attr.model_copy(
                    update={
                        "profile": {
                            "row_count": 1234567890123456789,
                            "null_count": 0,
                            "blank_count": None,
                            "percent_blank": None,
                            "avg_data_length": None,
                        }
                    }
                ),
            ),
            (obj, None),
        ]
    )
    workbook = load_workbook(BytesIO(content))
    try:
        assert all(cell.value is None for cell in workbook.worksheets[0][2][8:12])
        assert workbook.worksheets[1]["F2"].value == "1234567890123456789"
        assert workbook.worksheets[1]["H2"].value == 0
        assert workbook.worksheets[1]["I2"].value is None
        assert workbook.worksheets[1]["M2"].value is None
        assert workbook.worksheets[1]["R2"].value is None
        assert workbook.worksheets[0]["D3"].value is None
    finally:
        workbook.close()
