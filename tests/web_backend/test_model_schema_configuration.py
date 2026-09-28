"""Schema lists are validated by the backend before model commands reach SQL."""

import pytest
from pydantic import ValidationError
from gds_workbench_api.features.models.command_contracts import CompleteModelRequest
from gds_workbench_api.features.model_targets.contracts import ExportModelTargetsRequest


def test_model_schema_configuration_rejects_normalized_duplicates() -> None:
    with pytest.raises(ValidationError):
        CompleteModelRequest.model_validate({"model_name": "Sales", "logical_schemas": [
            {"schema_name": "Silver", "description": None},
            {"schema_name": " silver ", "description": None},
        ]})


def test_model_allows_empty_schema_configuration_before_generation() -> None:
    model = CompleteModelRequest(model_name="Sales")
    assert model.logical_schemas == model.dimensional_schemas == []


def test_export_uses_saved_schema_and_rejects_request_override() -> None:
    with pytest.raises(ValidationError):
        ExportModelTargetsRequest.model_validate({"layer": "logical", "expected_model_revision": 1,
                                                 "object_schema": "override"})
