import json
from uuid import UUID

import pytest
from gds_workbench_api.capabilities import load_default_agent_capabilities
from gds_workbench_api.features.workflows.commands.contracts import CreateWorkflowRunRequest

from gds_workbench_notebooks.errors import NotebookConfigurationError
from gds_workbench_notebooks.notebook import (
    build_notebook_request,
    create_workflow_widgets,
    run_notebook,
    widget_specs,
)
from gds_workbench_notebooks.workflow_execution import NotebookWorkflowExecutionResult

_WORKFLOWS = (
    "profiling",
    "analysis_inference",
    "analysis_validation",
    "conceptual",
    "logical",
    "dimensional",
    "mapping",
    "code_generation",
    "validation",
)
_COMMON_NAMES = (
    "TenantID",
    "ModelID",
    "ExpectedModelRevision",
    "SelectedObjectIDsJSON",
    "IdempotencyKey",
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
            "TenantID": "2",
            "ModelID": "3",
            "ExpectedModelRevision": "4",
            "SelectedObjectIDsJSON": "[11,12]",
            "IdempotencyKey": "12345678-1234-4234-8234-123456789abc",
        }
    )
    if workflow == "mapping":
        values.update({"SelectedObjectIDsJSON": "[11]", "MappingSourceSystemID": "20"})
    elif workflow == "validation":
        values.update(
            {
                "SelectedObjectIDsJSON": "[]",
                "SelectedSystemCodesJSON": '["ERP","CRM"]',
            }
        )
    return values


def _databricks_registry_with_default_reasoning():
    registry = load_default_agent_capabilities()
    model = next(model for model in registry.models if model.provider_code == "databricks")
    profile = next(
        profile
        for profile in model.execution_profiles
        if profile.sdk_code == "openai_agents_sdk" and profile.execution_mode == "tool_assisted"
    )
    return registry.model_copy(
        update={
            "models": (
                model.model_copy(
                    update={
                        "code": "registered-databricks-model",
                        "deployment_name": "registered-serving-endpoint",
                        "execution_profiles": (
                            profile.model_copy(update={"reasoning_effort_codes": ("default",)}),
                        ),
                    }
                ),
            ),
            "reasoning_efforts": (
                next(effort for effort in registry.reasoning_efforts if effort.code == "default"),
            ),
        }
    )


def _databricks_registry_with_disjoint_profiles():
    registry = _databricks_registry_with_default_reasoning()
    model = registry.models[0]
    tool_profile = model.execution_profiles[0]
    one_shot_profile = tool_profile.model_copy(
        update={
            "sdk_code": "langchain_create_agent",
            "execution_mode": "one_shot",
            "reasoning_effort_codes": ("low",),
        }
    )
    detailed_profile = tool_profile.model_copy(update={"execution_mode": "detailed_coverage"})
    return registry.model_copy(
        update={
            "models": (
                model.model_copy(
                    update={
                        "execution_profiles": (
                            one_shot_profile,
                            tool_profile,
                            detailed_profile,
                        )
                    }
                ),
            ),
            "reasoning_efforts": (
                next(
                    effort
                    for effort in load_default_agent_capabilities().reasoning_efforts
                    if effort.code == "low"
                ),
                registry.reasoning_efforts[0],
            ),
        }
    )


def _databricks_registry_with_secondary_model():
    registry = load_default_agent_capabilities()
    primary = next(model for model in registry.models if model.code == "databricks-primary")
    secondary = primary.model_copy(
        update={
            "code": "databricks-secondary",
            "name": "Operator-verified secondary Databricks deployment",
            "deployment_name": "databricks-secondary",
        }
    )
    return registry.model_copy(update={"models": (*registry.models, secondary)})


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
        "selected_system_codes",
        "modeled_entity_type",
        "requested_batch_id",
        "mapping_operation",
        "mapping_coverage_mode",
        "mapping_source_system_id",
        "mapping_object_output_template_id",
        "mapping_attribute_output_template_id",
        "code_generation_coverage_mode",
        "sql_generation_guide_version_id",
        "agent",
        "prompt_overrides",
    }
    if workflow in {"profiling", "analysis_validation", "validation"}:
        assert command.create_payload["workflow_execution_mode"] is None
    if workflow in {"profiling", "analysis_validation"}:
        assert command.create_payload["agent"] is None
    if workflow == "analysis_inference":
        assert command.create_payload["workflow_execution_mode"] == "tool_assisted"
    if workflow in {"conceptual", "logical", "dimensional", "mapping"}:
        assert command.create_payload["workflow_execution_mode"] == "tool_assisted"
    if workflow in {
        "analysis_inference",
        "conceptual",
        "logical",
        "dimensional",
        "mapping",
        "code_generation",
        "validation",
    }:
        assert command.create_payload["agent"] == {
            "sdk_code": "langchain_create_agent",
            "provider_code": "databricks",
            "model_code": "databricks-primary",
            "reasoning_effort_code": "default",
            "max_turns": 10,
            "validation_retry_count": 2,
        }


@pytest.mark.parametrize("workflow", _WORKFLOWS)
def test_each_notebook_payload_passes_the_shared_backend_contract(workflow: str) -> None:
    command = build_notebook_request(workflow, _values(workflow))

    validated = CreateWorkflowRunRequest.model_validate(command.create_payload, strict=True)

    assert validated.model_workflow == command.workflow
    assert validated.expected_model_revision == command.expected_model_revision


def test_widget_contract_is_exact_and_contains_no_secret_input() -> None:
    expected_extras = {
        "profiling": ("RequestedBatchID",),
        "analysis_inference": ("RequestedBatchID", "ExecutionMode", *_AGENT_NAMES),
        "analysis_validation": ("RequestedBatchID",),
        "conceptual": ("ExecutionMode", *_AGENT_NAMES),
        "logical": ("ExecutionMode", *_AGENT_NAMES),
        "dimensional": ("ExecutionMode", *_AGENT_NAMES),
        "mapping": (
            "ExecutionMode",
            "MappingOperation",
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
        "validation": ("SelectedSystemCodesJSON", *_AGENT_NAMES),
    }
    for workflow in _WORKFLOWS:
        names = tuple(spec.name for spec in widget_specs(workflow))
        assert names == (*_COMMON_NAMES, *expected_extras[workflow])
        assert not any("token" in name.lower() or "secret" in name.lower() for name in names)

    inference_mode = next(
        spec for spec in widget_specs("analysis_inference") if spec.name == "ExecutionMode"
    )
    assert inference_mode.default == "tool_assisted"
    assert inference_mode.choices == (
        "one_shot",
        "tool_assisted",
        "detailed_coverage",
    )
    inference_reasoning = next(
        spec for spec in widget_specs("analysis_inference") if spec.name == "ReasoningEffort"
    )
    assert inference_reasoning.default == "default"
    assert inference_reasoning.choices == ("default", "low", "medium", "high")


def test_agent_widget_choices_and_defaults_follow_the_databricks_registry(
    monkeypatch,
) -> None:
    monkeypatch.setattr(
        "gds_workbench_notebooks.notebook.load_default_agent_capabilities",
        _databricks_registry_with_default_reasoning,
    )

    specs = {spec.name: spec for spec in widget_specs("analysis_inference")}

    assert specs["AgentProvider"].choices == ("databricks",)
    assert specs["AgentSDK"].choices == ("openai_agents_sdk",)
    assert specs["AgentSDK"].default == "openai_agents_sdk"
    assert specs["AgentModel"].choices == ("registered-databricks-model",)
    assert specs["AgentModel"].default == "registered-databricks-model"
    assert specs["ExecutionMode"].choices == ("tool_assisted",)
    assert specs["ExecutionMode"].default == "tool_assisted"
    assert specs["ReasoningEffort"].choices == ("default",)
    assert specs["ReasoningEffort"].default == "default"


def test_agent_widgets_offer_all_databricks_models_registered_in_json(
    monkeypatch,
    tmp_path,
) -> None:
    registry = _databricks_registry_with_secondary_model()
    monkeypatch.setattr(
        "gds_workbench_notebooks.notebook.load_default_agent_capabilities",
        lambda: registry,
    )

    class FakeWidgets:
        def __init__(self) -> None:
            self.created: dict[str, tuple[str, tuple[str, ...]]] = {}

        def text(self, name: str, default: str, label: str) -> None:
            self.created[name] = (default, ())

        def dropdown(
            self,
            name: str,
            default: str,
            choices: list[str],
            label: str,
        ) -> None:
            self.created[name] = (default, tuple(choices))

    widgets = FakeWidgets()
    dbutils = type("Dbutils", (), {"widgets": widgets})()

    create_workflow_widgets(
        "analysis_inference",
        dbutils=dbutils,
        uploaded_root=tmp_path,
    )

    assert widgets.created["AgentModel"] == (
        "databricks-primary",
        (
            "databricks-primary",
            "databricks-claude-opus-5",
            "databricks-secondary",
        ),
    )


def test_request_only_accepts_models_configured_in_the_uploaded_env(monkeypatch) -> None:
    registry = _databricks_registry_with_secondary_model()
    monkeypatch.setattr(
        "gds_workbench_notebooks.notebook.load_default_agent_capabilities",
        lambda: registry,
    )
    values = _values("analysis_inference")

    with pytest.raises(NotebookConfigurationError, match="AgentModel"):
        build_notebook_request(
            "analysis_inference",
            values,
            configured_model_codes={"databricks-secondary"},
        )

    values["AgentModel"] = "databricks-secondary"
    command = build_notebook_request(
        "analysis_inference",
        values,
        configured_model_codes={"databricks-secondary"},
    )

    assert command.create_payload["agent"]["model_code"] == "databricks-secondary"


def test_build_notebook_request_accepts_an_exact_registered_agent_profile(
    monkeypatch,
) -> None:
    monkeypatch.setattr(
        "gds_workbench_notebooks.notebook.load_default_agent_capabilities",
        _databricks_registry_with_default_reasoning,
    )
    values = _values("analysis_inference")

    command = build_notebook_request("analysis_inference", values)

    assert command.create_payload["agent"] == {
        "sdk_code": "openai_agents_sdk",
        "provider_code": "databricks",
        "model_code": "registered-databricks-model",
        "reasoning_effort_code": "default",
        "max_turns": 10,
        "validation_retry_count": 2,
    }


def test_build_notebook_request_rejects_a_union_choice_outside_an_exact_profile(
    monkeypatch,
) -> None:
    monkeypatch.setattr(
        "gds_workbench_notebooks.notebook.load_default_agent_capabilities",
        _databricks_registry_with_disjoint_profiles,
    )
    values = _values("analysis_inference")
    values["ExecutionMode"] = "one_shot"

    with pytest.raises(NotebookConfigurationError, match="combination"):
        build_notebook_request("analysis_inference", values)


@pytest.mark.parametrize("workflow", ("code_generation", "validation"))
def test_fixed_mode_widgets_and_validation_use_the_internal_detailed_profile(
    workflow: str,
    monkeypatch,
) -> None:
    monkeypatch.setattr(
        "gds_workbench_notebooks.notebook.load_default_agent_capabilities",
        _databricks_registry_with_disjoint_profiles,
    )

    specs = {spec.name: spec for spec in widget_specs(workflow)}
    values = _values(workflow)
    command = build_notebook_request(workflow, values)

    assert "ExecutionMode" not in specs
    assert specs["AgentSDK"].choices == ("openai_agents_sdk",)
    assert specs["ReasoningEffort"].choices == ("default",)
    assert command.create_payload["workflow_execution_mode"] is None
    assert command.create_payload["agent"]["sdk_code"] == "openai_agents_sdk"
    assert command.create_payload["agent"]["reasoning_effort_code"] == "default"


def test_validation_requires_exact_system_selection_and_empty_object_selection() -> None:
    command = build_notebook_request("validation", _values("validation"))

    assert command.workflow == "validation"
    assert command.create_payload["selected_object_ids"] == []
    assert command.create_payload["selected_system_codes"] == ["ERP", "CRM"]
    assert command.create_payload["workflow_execution_mode"] is None

    values = _values("validation")
    values["SelectedObjectIDsJSON"] = "[11]"
    with pytest.raises(NotebookConfigurationError, match=r"must be \[\]"):
        build_notebook_request("validation", values)


@pytest.mark.parametrize(
    "selected_system_codes",
    ("[]", '["ERP","erp"]', '["ERP",""]', "[11]"),
)
def test_validation_rejects_missing_or_invalid_system_selection(
    selected_system_codes: str,
) -> None:
    values = _values("validation")
    values["SelectedSystemCodesJSON"] = selected_system_codes

    with pytest.raises(NotebookConfigurationError, match="SelectedSystemCodesJSON"):
        build_notebook_request("validation", values)


def test_validation_rejects_more_than_1000_systems() -> None:
    values = _values("validation")
    values["SelectedSystemCodesJSON"] = json.dumps([f"SYSTEM_{index}" for index in range(1_001)])

    with pytest.raises(NotebookConfigurationError, match="at most 1000"):
        build_notebook_request("validation", values)


@pytest.mark.parametrize(
    "execution_mode",
    ("one_shot", "tool_assisted", "detailed_coverage"),
)
def test_analysis_inference_accepts_each_supported_execution_mode(
    execution_mode: str,
) -> None:
    values = _values("analysis_inference")
    values["ExecutionMode"] = execution_mode

    command = build_notebook_request("analysis_inference", values)

    assert command.create_payload["workflow_execution_mode"] == execution_mode


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
        ("PromptOverridesJSON", '{"0": 5}'),
        ("AgentProvider", "microsoft_foundry"),
        ("AgentModel", "unregistered-model"),
    ),
)
def test_rejects_invalid_widget_values(key: str, value: str) -> None:
    values = _values("conceptual")
    values[key] = value
    with pytest.raises(NotebookConfigurationError):
        build_notebook_request("conceptual", values)


@pytest.mark.parametrize("workflow", _WORKFLOWS)
def test_each_notebook_creates_reads_and_executes_its_complete_widget_contract(
    workflow, tmp_path, capsys, monkeypatch
) -> None:
    class FakeWidgets:
        def __init__(self) -> None:
            self.values = _values(workflow)
            self.created: list[tuple[str, str, str, tuple[str, ...]]] = []
            self.read: list[str] = []

        def text(self, name: str, default: str, label: str) -> None:
            self.created.append(("text", name, default, ()))

        def dropdown(self, name: str, default: str, choices: list[str], label: str) -> None:
            self.created.append(("dropdown", name, default, tuple(choices)))

        def get(self, name: str) -> str:
            self.read.append(name)
            return self.values[name]

    widgets = FakeWidgets()
    dbutils = type("Dbutils", (), {"widgets": widgets})()
    (tmp_path / ".env").write_text(
        """\
GDS_NOTEBOOK_POSTGRES_HOST=workbench.postgres.database.azure.com
GDS_NOTEBOOK_POSTGRES_PORT=5432
GDS_NOTEBOOK_POSTGRES_DATABASE=gds_workbench
GDS_NOTEBOOK_POSTGRES_USER=gds_notebook_runtime
GDS_NOTEBOOK_POSTGRES_PASSWORD=fixture-password
"""
    )
    calls = []

    def execute(request, *, settings):
        calls.append((request, settings))
        return NotebookWorkflowExecutionResult(
            workflow_run_id=71,
            workflow=request.workflow,
            state="completed",
            created=True,
            model_revision=4,
        )

    monkeypatch.setattr(
        "gds_workbench_notebooks.workflow_execution.execute_notebook_workflow",
        execute,
    )

    create_workflow_widgets(workflow, dbutils=dbutils, uploaded_root=tmp_path)
    result = run_notebook(workflow, dbutils=dbutils, uploaded_root=tmp_path)

    specs = widget_specs(workflow)
    assert widgets.created == [
        (
            "dropdown" if spec.choices else "text",
            spec.name,
            spec.default,
            spec.choices,
        )
        for spec in specs
    ]
    assert widgets.read == [spec.name for spec in specs]
    assert result.workflow_run_id == 71
    assert calls[0][0].workflow == ("analysis" if workflow.startswith("analysis_") else workflow)
    assert calls[0][0].analysis_operation == (
        workflow.removeprefix("analysis_") if workflow.startswith("analysis_") else None
    )
    assert calls[0][1].database.user == "gds_notebook_runtime"
    assert f'"workflow":"{calls[0][0].workflow}"' in capsys.readouterr().out
