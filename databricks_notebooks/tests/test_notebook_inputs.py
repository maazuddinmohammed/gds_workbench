from uuid import UUID

import pytest
from gds_workbench_notebooks import (
    NotebookConfigurationError,
    WorkflowLaunchResult,
    build_notebook_request,
    run_notebook,
    widget_specs,
)

_WORKFLOWS = (
    "profiling",
    "analysis_inference",
    "analysis_validation",
    "conceptual",
    "logical",
    "dimensional",
    "mapping",
    "code_generation",
)
_COMMON_NAMES = (
    "AppName",
    "TenantID",
    "ModelID",
    "ExpectedModelRevision",
    "SelectedObjectIDsJSON",
    "IdempotencyKey",
    "WaitTimeoutSeconds",
)
_AGENT_NAMES = (
    "AgentSDK",
    "AgentProvider",
    "AgentModel",
    "ReasoningEffort",
    "MaxTurns",
    "ValidationRetryCount",
    "PromptOverridesJSON",
)


def _values(workflow: str) -> dict[str, str]:
    values = {spec.name: spec.default for spec in widget_specs(workflow)}
    values.update(
        {
            "AppName": "gds-workbench",
            "TenantID": "2",
            "ModelID": "3",
            "ExpectedModelRevision": "4",
            "SelectedObjectIDsJSON": "[11,12]",
            "IdempotencyKey": "12345678-1234-4234-8234-123456789abc",
        }
    )
    if workflow == "mapping":
        values.update({"SelectedObjectIDsJSON": "[11]", "MappingSourceSystemID": "20"})
    return values


@pytest.mark.parametrize("workflow", _WORKFLOWS)
def test_each_notebook_builds_the_existing_create_contract(workflow: str) -> None:
    command = build_notebook_request(workflow, _values(workflow))

    assert command.tenant_id == 2
    assert command.model_id == 3
    assert command.expected_model_revision == 4
    assert command.idempotency_key == UUID("12345678-1234-4234-8234-123456789abc")
    assert command.workflow == ("analysis" if workflow.startswith("analysis_") else workflow)
    assert command.analysis_operation == (
        workflow.removeprefix("analysis_") if workflow.startswith("analysis_") else None
    )
    assert set(command.create_payload) == {
        "expected_model_revision",
        "model_workflow",
        "workflow_execution_mode",
        "selected_object_ids",
        "modeled_entity_type",
        "requested_batch_id",
        "mapping_operation",
        "mapping_coverage_mode",
        "mapping_artifact_type",
        "mapping_source_system_id",
        "mapping_object_output_template_id",
        "mapping_attribute_output_template_id",
        "code_generation_coverage_mode",
        "sql_generation_guide_version_id",
        "agent",
        "prompt_overrides",
    }
    if workflow in {"profiling", "analysis_validation"}:
        assert command.create_payload["workflow_execution_mode"] is None
        assert command.create_payload["agent"] is None
    if workflow == "analysis_inference":
        assert command.create_payload["workflow_execution_mode"] == "one_shot"
    if workflow in {"conceptual", "logical", "dimensional", "mapping"}:
        assert command.create_payload["workflow_execution_mode"] == "one_shot"
    if workflow in {
        "analysis_inference",
        "conceptual",
        "logical",
        "dimensional",
        "mapping",
        "code_generation",
    }:
        assert command.create_payload["agent"] == {
            "sdk_code": "langchain_create_agent",
            "provider_code": "databricks",
            "model_code": "databricks-primary",
            "reasoning_effort_code": "medium",
            "max_turns": 10,
            "validation_retry_count": 2,
        }


def test_widget_contract_is_exact_and_contains_no_secret_input() -> None:
    expected_extras = {
        "profiling": ("RequestedBatchID",),
        "analysis_inference": ("RequestedBatchID", *_AGENT_NAMES),
        "analysis_validation": ("RequestedBatchID",),
        "conceptual": ("ExecutionMode", *_AGENT_NAMES),
        "logical": ("ExecutionMode", *_AGENT_NAMES),
        "dimensional": ("ExecutionMode", *_AGENT_NAMES),
        "mapping": (
            "ExecutionMode",
            "MappingOperation",
            "MappingArtifactType",
            "MappingSourceSystemID",
            "MappingObjectOutputTemplateID",
            "MappingAttributeOutputTemplateID",
            *_AGENT_NAMES,
        ),
        "code_generation": (
            "ModeledEntityType",
            "CodeGenerationCoverage",
            "SqlGenerationGuideVersionID",
            *_AGENT_NAMES,
        ),
    }
    for workflow in _WORKFLOWS:
        names = tuple(spec.name for spec in widget_specs(workflow))
        assert names == (*_COMMON_NAMES, *expected_extras[workflow])
        assert not any("token" in name.lower() or "secret" in name.lower() for name in names)


def test_mapping_requires_exactly_one_target() -> None:
    values = _values("mapping")
    values["SelectedObjectIDsJSON"] = "[11,12]"
    with pytest.raises(NotebookConfigurationError, match="exactly one"):
        build_notebook_request("mapping", values)


def test_all_eligible_code_generation_requires_empty_selection() -> None:
    values = _values("code_generation")
    values["CodeGenerationCoverage"] = "all_eligible_targets"
    with pytest.raises(NotebookConfigurationError, match=r"must be \[\]"):
        build_notebook_request("code_generation", values)

    values["SelectedObjectIDsJSON"] = "[]"
    command = build_notebook_request("code_generation", values)
    assert command.create_payload["code_generation_coverage_mode"] == "all_eligible_targets"
    assert command.create_payload["selected_object_ids"] == []


@pytest.mark.parametrize(
    ("key", "value"),
    (
        ("SelectedObjectIDsJSON", "[true]"),
        ("SelectedObjectIDsJSON", "[11,11]"),
        ("IdempotencyKey", "not-a-uuid"),
        ("WaitTimeoutSeconds", "86401"),
        ("PromptOverridesJSON", '{"0": 5}'),
    ),
)
def test_rejects_invalid_widget_values(key: str, value: str) -> None:
    values = _values("conceptual")
    values[key] = value
    with pytest.raises(NotebookConfigurationError):
        build_notebook_request("conceptual", values)


def test_run_notebook_registers_widgets_and_prints_only_safe_result(capsys) -> None:
    class FakeWidgets:
        def __init__(self) -> None:
            self.values = _values("profiling")
            self.created: list[str] = []

        def text(self, name: str, default: str, label: str) -> None:
            self.created.append(name)

        def dropdown(self, name: str, default: str, choices: list[str], label: str) -> None:
            self.created.append(name)

        def get(self, name: str) -> str:
            return self.values[name]

    class FakeClient:
        def launch_workflow(self, **kwargs: object) -> WorkflowLaunchResult:
            assert kwargs["workflow"] == "profiling"
            return WorkflowLaunchResult(71, "profiling", "running", True)

    widgets = FakeWidgets()
    dbutils = type("Dbutils", (), {"widgets": widgets})()
    factory_calls: list[dict[str, object]] = []

    def factory(**kwargs: object) -> FakeClient:
        factory_calls.append(kwargs)
        return FakeClient()

    result = run_notebook("profiling", dbutils=dbutils, client_factory=factory)

    assert widgets.created == [spec.name for spec in widget_specs("profiling")]
    assert factory_calls == [{"app_name": "gds-workbench", "dbutils": dbutils}]
    assert result.state == "running"
    assert capsys.readouterr().out == (
        '{"created":true,"state":"running","workflow":"profiling","workflow_run_id":71}\n'
    )
