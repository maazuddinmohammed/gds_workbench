"""Schema lists are validated by the backend before project commands reach SQL."""

import pytest
from gds_workbench_api.features.project_targets.contracts import (
    ExportProjectTargetsRequest,
)
from gds_workbench_api.features.projects.command_contracts import CompleteProjectRequest
from pydantic import ValidationError


def test_project_schema_configuration_rejects_normalized_duplicates() -> None:
    with pytest.raises(ValidationError):
        CompleteProjectRequest.model_validate(
            {
                "project_name": "Sales",
                "logical_schemas": [
                    {"schema_name": "Silver", "description": None},
                    {"schema_name": " silver ", "description": None},
                ],
            }
        )


def test_project_allows_empty_schema_configuration_before_generation() -> None:
    project = CompleteProjectRequest(project_name="Sales")
    assert project.logical_schemas == project.dimensional_schemas == []


def test_export_uses_saved_schema_and_rejects_request_override() -> None:
    with pytest.raises(ValidationError):
        ExportProjectTargetsRequest.model_validate(
            {
                "layer": "logical",
                "expected_project_revision": 1,
                "object_schema": "override",
            }
        )
