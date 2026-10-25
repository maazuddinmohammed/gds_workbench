from gds_workbench_api.features.workflows.authoring.naming import (
    effective_naming_instructions,
)


def test_default_project_authoring_naming_is_pascal_case_with_layer_suffixes() -> None:
    logical = effective_naming_instructions("logical", None)
    dimensional = effective_naming_instructions("dimensional", None)

    assert "PascalCase" in logical
    assert "end with ID" in logical
    assert "PascalCase" in dimensional
    assert "end with Key" in dimensional


def test_project_naming_policy_replaces_the_default() -> None:
    assert (
        effective_naming_instructions("logical", "Use snake_case.") == "Use snake_case."
    )
