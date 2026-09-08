from copy import deepcopy

import pytest
from gds_etl_workbench.application.change_sets.metadata_validation import (
    validate_metadata_documents,
)
from gds_etl_workbench.domain.metadata_records import AttributeRecord
from pydantic import ValidationError

from tests.mcp.test_metadata_change_set_validation import (
    _attribute_record,
    _foundation,
    _object_record,
)


@pytest.mark.parametrize("field", ["attribute_inferred_data_type", "is_locked"])
def test_old_attribute_records_cannot_clear_new_metadata_by_omission(
    field: str,
) -> None:
    record = _attribute_record()
    del record[field]
    with pytest.raises(ValidationError):
        AttributeRecord.model_validate(record)


def test_inferred_type_is_separate_and_part_of_candidate_digest() -> None:
    current = _foundation()
    current["bronze_object"] = [_object_record(object_schema="public", tenant_code="DEMO")]
    record = _attribute_record()
    record["attribute_data_type"] = "STRING"
    record["attribute_inferred_data_type"] = "DECIMAL(18,2)"
    result = validate_metadata_documents(
        tenant_code="DEMO",
        current_rows_by_dataset=current,
        staged_rows_by_dataset={"bronze_attribute": [record]},
    )
    assert result.valid
    assert AttributeRecord.model_validate(record).attribute_data_type == "STRING"
    changed = {**record, "attribute_inferred_data_type": "BIGINT"}
    revised = validate_metadata_documents(
        tenant_code="DEMO",
        current_rows_by_dataset=current,
        staged_rows_by_dataset={"bronze_attribute": [changed]},
    )
    assert revised.valid
    assert result.candidate_digest != revised.candidate_digest


@pytest.mark.parametrize("change", [{"attribute_description": "Changed"}, {"is_locked": False}, {}])
def test_locked_physical_attribute_rejects_authoring_changes(
    change: dict[str, object],
) -> None:
    current = _foundation()
    current["bronze_object"] = [_object_record(object_schema="public", tenant_code="DEMO")]
    locked = {
        **_attribute_record(),
        "is_locked": True,
        "attribute_inferred_data_type": "BIGINT",
    }
    current["bronze_attribute"] = [locked]
    result = validate_metadata_documents(
        tenant_code="DEMO",
        current_rows_by_dataset=current,
        staged_rows_by_dataset={"bronze_attribute": [{**deepcopy(locked), **change}]},
    )
    assert not result.valid
    assert result.phase == "locks"
    assert [issue.code for issue in result.issues] == ["attribute_locked"]
