"""Independent review regressions for the renamed Project contract."""

# The audit projection is intentionally tested without transport or database setup.
# pyright: reportPrivateUsage=false

import pytest
from gds_etl_workbench.tools.change_sets.project import _audit_project_input


@pytest.mark.parametrize(
    "arguments,expected_version",
    [
        ({"project_id": 41}, "2.0"),
        ({"project_id": 41, "schema_version": "2.0"}, "2.0"),
        ({"project_id": 41, "schema_version": "1.0"}, "invalid"),
    ],
)
def test_project_audit_uses_current_contract_version(
    arguments: dict[str, object], expected_version: str
) -> None:
    assert _audit_project_input(arguments) == {
        "project_id": 41,
        "schema_version": expected_version,
    }
