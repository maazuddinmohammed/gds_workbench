from __future__ import annotations

from decimal import Decimal

import pytest
from pydantic import ValidationError

from gds_etl_workbench.domain.modeling_records import ProfilingProfileRecord
from gds_etl_workbench.tools.snapshots.model.contracts import (
    DATASETS_BY_NAME,
    build_model_dataset_schema,
)


def _profile() -> dict[str, object]:
    return {
        "tenant_code": "northwind",
        "system_code": "erp",
        "connection_code": "source",
        "object_schema": "sales",
        "object_name": "orders",
        "attribute_name": "customer_id",
        "row_count": 100,
        "non_null_count": 90,
        "null_count": 10,
        "blank_count": 0,
        "distinct_count": 45,
        "min_data_length": 1,
        "max_data_length": 10,
        "avg_data_length": Decimal("5.5"),
        "percent_populated": Decimal("90"),
        "percent_duplicates": Decimal("50"),
        "percent_null": Decimal("10"),
        "percent_blank": Decimal("0"),
        "percent_distinct": Decimal("50"),
    }


def test_modeling_records_are_strict_id_free_contracts() -> None:
    record = ProfilingProfileRecord.model_validate(_profile())
    assert record.object_name == "orders"

    for forbidden in (
        "object_id",
        "attribute_id",
        "agent_run_id",
        "created_by",
        "updated_time",
    ):
        invalid = {**_profile(), forbidden: 1}
        with pytest.raises(ValidationError):
            ProfilingProfileRecord.model_validate(invalid)


def test_all_model_datasets_share_one_registry() -> None:
    assert set(DATASETS_BY_NAME) == {
        "model_details",
        "model_scope",
        "profiling_profile",
        "analysis_result",
        "modeling_assertion_document",
        "modeling_assertion_record",
        "conceptual_object",
        "conceptual_relationship",
        "logical_submodel",
        "logical_entity",
        "logical_attribute",
        "logical_relationship",
        "dimensional_submodel",
        "dimensional_entity",
        "dimensional_attribute",
        "dimensional_relationship",
        "mapping_dependency",
        "mapping_object",
        "mapping_attribute",
    }
    assert DATASETS_BY_NAME["profiling_profile"].canonical_key[-1] == "attribute_name"


def test_described_schemas_explain_layer_specific_source_roles() -> None:
    logical = str(build_model_dataset_schema(DATASETS_BY_NAME["logical_entity"]))
    dimensional = str(
        build_model_dataset_schema(DATASETS_BY_NAME["dimensional_entity"])
    )

    assert "source_role" not in logical
    assert "source_role" in dimensional
