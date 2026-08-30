"""Thin Databricks widget entry points for Workbench Workflow Runs."""

from __future__ import annotations

import json
import re
from collections.abc import Collection, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any, cast
from uuid import UUID

from gds_etl_workbench.domain.errors import InvalidRequestError
from gds_workbench_api.capabilities import (
    CODE_GENERATION_AGENT_EXECUTION_MODE,
    AgentCapabilityRegistry,
    AgentExecutionModeCode,
    AgentRunSelection,
    load_default_agent_capabilities,
    select_agent_runtime_capabilities,
)

from .errors import NotebookConfigurationError

_WORKFLOWS = {
    "profiling",
    "analysis_inference",
    "analysis_validation",
    "conceptual",
    "logical",
    "dimensional",
    "mapping",
    "code_generation",
}
_AGENT_WORKFLOWS = {
    "analysis_inference",
    "conceptual",
    "logical",
    "dimensional",
    "mapping",
    "code_generation",
}
_CONFIGURABLE_MODE_WORKFLOWS = {
    "analysis_inference",
    "conceptual",
    "logical",
    "dimensional",
    "mapping",
}


@dataclass(frozen=True)
class WidgetSpec:
    name: str
    default: str
    label: str
    choices: tuple[str, ...] = ()


@dataclass(frozen=True)
class NotebookWorkflowRequest:
    tenant_id: int
    model_id: int
    workflow: str
    analysis_operation: str | None
    expected_model_revision: int
    idempotency_key: UUID
    create_payload: dict[str, object]


@dataclass(frozen=True)
class _NotebookAgentCapabilities:
    registry: AgentCapabilityRegistry
    default_sdk: str
    default_model: str
    default_mode: str
    default_reasoning_effort: str
    sdk_codes: tuple[str, ...]
    model_codes: tuple[str, ...]
    mode_codes: tuple[str, ...]
    reasoning_effort_codes: tuple[str, ...]


_COMMON_WIDGETS = (
    WidgetSpec("TenantID", "", "Tenant ID"),
    WidgetSpec("ModelID", "", "Model ID"),
    WidgetSpec("ExpectedModelRevision", "", "Expected Model revision"),
    WidgetSpec("SelectedObjectIDsJSON", "[]", "Selected Object IDs (JSON array)"),
    WidgetSpec("IdempotencyKey", "", "Idempotency key (UUID; reuse on retry)"),
)


def widget_specs(
    workflow: str,
    *,
    configured_model_codes: Collection[str] | None = None,
) -> tuple[WidgetSpec, ...]:
    """Return the complete, stable widget contract for one notebook."""
    _validate_workflow(workflow)
    agent_capabilities = (
        _load_notebook_agent_capabilities(
            workflow,
            configured_model_codes=configured_model_codes,
        )
        if workflow in _AGENT_WORKFLOWS
        else None
    )
    specs = list(_COMMON_WIDGETS)
    if workflow in {"profiling", "analysis_inference", "analysis_validation"}:
        specs.append(WidgetSpec("RequestedBatchID", "", "Requested batch ID (optional)"))
    if workflow in _CONFIGURABLE_MODE_WORKFLOWS:
        assert agent_capabilities is not None
        specs.append(
            WidgetSpec(
                "ExecutionMode",
                agent_capabilities.default_mode,
                "Execution mode",
                agent_capabilities.mode_codes,
            )
        )
    if workflow == "mapping":
        specs.extend(
            (
                WidgetSpec(
                    "MappingOperation",
                    "build",
                    "Mapping operation",
                    ("build", "extend"),
                ),
                WidgetSpec(
                    "MappingArtifactType",
                    "sql_file",
                    "Mapping artifact type",
                    ("sql_file", "python_file", "python_notebook"),
                ),
                WidgetSpec("MappingSourceSystemID", "", "Mapping source System ID"),
                WidgetSpec(
                    "MappingObjectOutputTemplateID",
                    "",
                    "Mapping Object output template ID (optional)",
                ),
                WidgetSpec(
                    "MappingAttributeOutputTemplateID",
                    "",
                    "Mapping Attribute output template ID (optional)",
                ),
            )
        )
    if workflow == "code_generation":
        specs.extend(
            (
                WidgetSpec(
                    "ModeledEntityType",
                    "logical_entity",
                    "Modeled Entity type",
                    ("logical_entity", "dimensional_entity"),
                ),
                WidgetSpec(
                    "CodeGenerationCoverage",
                    "selected_targets",
                    "Code Generation coverage",
                    ("selected_targets", "all_eligible_targets"),
                ),
                WidgetSpec(
                    "SqlGenerationGuideVersionID",
                    "",
                    "SQL Generation Guide Version ID (optional; blank uses active)",
                ),
            )
        )
    if workflow in _AGENT_WORKFLOWS:
        assert agent_capabilities is not None
        specs.extend(
            (
                WidgetSpec(
                    "AgentSDK",
                    agent_capabilities.default_sdk,
                    "Agent SDK",
                    agent_capabilities.sdk_codes,
                ),
                WidgetSpec(
                    "AgentProvider",
                    "databricks",
                    "Agent provider",
                    ("databricks",),
                ),
                WidgetSpec(
                    "AgentModel",
                    agent_capabilities.default_model,
                    "Agent model code",
                    agent_capabilities.model_codes,
                ),
                WidgetSpec(
                    "ReasoningEffort",
                    agent_capabilities.default_reasoning_effort,
                    "Reasoning effort (`default` omits the setting)",
                    agent_capabilities.reasoning_effort_codes,
                ),
                WidgetSpec(
                    "MaxTurns",
                    str(agent_capabilities.registry.max_turns.default),
                    "Maximum agent turns",
                ),
                WidgetSpec(
                    "ValidationRetryCount",
                    str(agent_capabilities.registry.validation_retries.default),
                    "Validation retry count",
                ),
                WidgetSpec(
                    "PromptOverridesJSON",
                    "{}",
                    "Prompt overrides (Stage ID to Version ID JSON)",
                ),
            )
        )
    return tuple(specs)


def _load_notebook_agent_capabilities(
    workflow: str,
    *,
    configured_model_codes: Collection[str] | None = None,
) -> _NotebookAgentCapabilities:
    complete_registry = load_default_agent_capabilities()
    available_model_codes = (
        None if configured_model_codes is None else frozenset(configured_model_codes)
    )
    configured_models = tuple(
        (model.provider_code, model.code)
        for model in complete_registry.models
        if model.provider_code == "databricks"
        and (available_model_codes is None or model.code in available_model_codes)
    )
    if not configured_models:
        raise NotebookConfigurationError(
            "The Agent registry has no Databricks model deployment for this notebook."
        )
    try:
        registry = select_agent_runtime_capabilities(
            complete_registry,
            configured_models=configured_models,
        )
    except ValueError:
        raise NotebookConfigurationError(
            "The selected Databricks model deployment does not match the Agent registry."
        ) from None
    profiles = [
        (model, profile)
        for model in registry.models
        for profile in model.execution_profiles
        if workflow != "code_generation"
        or profile.execution_mode == CODE_GENERATION_AGENT_EXECUTION_MODE
    ]
    if not profiles:
        raise NotebookConfigurationError(
            "The Databricks Agent registry has no compatible profile for this notebook."
        )

    default_model, default_profile = next(
        (
            item
            for item in profiles
            if workflow != "code_generation" and item[1].execution_mode == "tool_assisted"
        ),
        profiles[0],
    )
    sdk_codes = tuple(
        sdk.code
        for sdk in registry.sdks
        if any(profile.sdk_code == sdk.code for _, profile in profiles)
    )
    model_codes = tuple(
        model.code
        for model in registry.models
        if any(candidate.code == model.code for candidate, _ in profiles)
    )
    mode_codes = tuple(
        mode
        for mode in ("one_shot", "tool_assisted", "detailed_coverage")
        if any(profile.execution_mode == mode for _, profile in profiles)
    )
    reasoning_effort_codes = tuple(
        effort.code
        for effort in registry.reasoning_efforts
        if any(effort.code in profile.reasoning_effort_codes for _, profile in profiles)
    )
    return _NotebookAgentCapabilities(
        registry=registry,
        default_sdk=default_profile.sdk_code,
        default_model=default_model.code,
        default_mode=default_profile.execution_mode,
        default_reasoning_effort=default_profile.reasoning_effort_codes[0],
        sdk_codes=sdk_codes,
        model_codes=model_codes,
        mode_codes=mode_codes,
        reasoning_effort_codes=reasoning_effort_codes,
    )


def build_notebook_request(
    workflow: str,
    values: Mapping[str, str],
    *,
    configured_model_codes: Collection[str] | None = None,
) -> NotebookWorkflowRequest:
    """Validate widgets locally and construct the backend-owned command shape."""
    _validate_workflow(workflow)
    tenant_id = _positive_int(values, "TenantID")
    model_id = _positive_int(values, "ModelID")
    expected_revision = _positive_int(values, "ExpectedModelRevision")
    selected_ids = _positive_int_array(values, "SelectedObjectIDsJSON")
    idempotency_key = _uuid(values, "IdempotencyKey")

    model_workflow = "analysis" if workflow.startswith("analysis_") else workflow
    analysis_operation = (
        workflow.removeprefix("analysis_") if workflow.startswith("analysis_") else None
    )
    agent_capabilities = (
        _load_notebook_agent_capabilities(
            workflow,
            configured_model_codes=configured_model_codes,
        )
        if workflow in _AGENT_WORKFLOWS
        else None
    )
    execution_mode: str | None = None
    if workflow in _CONFIGURABLE_MODE_WORKFLOWS:
        assert agent_capabilities is not None
        execution_mode = _choice(
            values,
            "ExecutionMode",
            set(agent_capabilities.mode_codes),
        )

    payload: dict[str, object] = {
        "expected_model_revision": expected_revision,
        "model_workflow": model_workflow,
        "workflow_execution_mode": execution_mode,
        "selected_object_ids": selected_ids,
        "modeled_entity_type": None,
        "requested_batch_id": None,
        "mapping_operation": None,
        "mapping_coverage_mode": None,
        "mapping_artifact_type": None,
        "mapping_source_system_id": None,
        "mapping_object_output_template_id": None,
        "mapping_attribute_output_template_id": None,
        "code_generation_coverage_mode": None,
        "sql_generation_guide_version_id": None,
        "agent": None,
        "prompt_overrides": {},
    }

    if workflow in {"profiling", "analysis_inference", "analysis_validation"}:
        payload["requested_batch_id"] = _optional(values, "RequestedBatchID", maximum=500)
    if workflow == "mapping":
        if len(selected_ids) != 1:
            raise NotebookConfigurationError(
                "SelectedObjectIDsJSON must contain exactly one Mapping target Object ID."
            )
        payload.update(
            {
                "mapping_operation": _choice(values, "MappingOperation", {"build", "extend"}),
                "mapping_coverage_mode": "selected_targets",
                "mapping_artifact_type": _choice(
                    values,
                    "MappingArtifactType",
                    {"sql_file", "python_file", "python_notebook"},
                ),
                "mapping_source_system_id": _positive_int(values, "MappingSourceSystemID"),
                "mapping_object_output_template_id": _optional_positive_int(
                    values, "MappingObjectOutputTemplateID"
                ),
                "mapping_attribute_output_template_id": _optional_positive_int(
                    values, "MappingAttributeOutputTemplateID"
                ),
            }
        )
    elif workflow == "code_generation":
        coverage = _choice(
            values,
            "CodeGenerationCoverage",
            {"selected_targets", "all_eligible_targets"},
        )
        if coverage == "selected_targets" and not selected_ids:
            raise NotebookConfigurationError(
                "SelectedObjectIDsJSON is required for selected Code Generation coverage."
            )
        if coverage == "all_eligible_targets" and selected_ids:
            raise NotebookConfigurationError(
                "SelectedObjectIDsJSON must be [] for all-eligible Code Generation coverage."
            )
        payload.update(
            {
                "modeled_entity_type": _choice(
                    values,
                    "ModeledEntityType",
                    {"logical_entity", "dimensional_entity"},
                ),
                "code_generation_coverage_mode": coverage,
                "sql_generation_guide_version_id": _optional_positive_int(
                    values, "SqlGenerationGuideVersionID"
                ),
            }
        )
    elif not selected_ids:
        raise NotebookConfigurationError("SelectedObjectIDsJSON must contain at least one ID.")

    if workflow in _AGENT_WORKFLOWS:
        assert agent_capabilities is not None
        selection = AgentRunSelection(
            sdk_code=_choice(
                values,
                "AgentSDK",
                set(agent_capabilities.sdk_codes),
            ),
            provider_code=_choice(values, "AgentProvider", {"databricks"}),
            model_code=_choice(
                values,
                "AgentModel",
                set(agent_capabilities.model_codes),
            ),
            reasoning_effort_code=_choice(
                values,
                "ReasoningEffort",
                set(agent_capabilities.reasoning_effort_codes),
            ),
            max_turns=_bounded_int(
                values,
                "MaxTurns",
                minimum=agent_capabilities.registry.max_turns.minimum,
                maximum=agent_capabilities.registry.max_turns.maximum,
            ),
            validation_retry_count=_bounded_int(
                values,
                "ValidationRetryCount",
                minimum=agent_capabilities.registry.validation_retries.minimum,
                maximum=agent_capabilities.registry.validation_retries.maximum,
            ),
        )
        effective_execution_mode = (
            CODE_GENERATION_AGENT_EXECUTION_MODE
            if workflow == "code_generation"
            else execution_mode or "one_shot"
        )
        try:
            agent_capabilities.registry.validate_selection(
                selection,
                execution_mode=cast(
                    AgentExecutionModeCode,
                    effective_execution_mode,
                ),
            )
        except InvalidRequestError:
            raise NotebookConfigurationError(
                "The selected Agent SDK, model, execution mode, and reasoning effort "
                "combination is unavailable."
            ) from None
        payload["agent"] = selection.model_dump(mode="python")
        payload["prompt_overrides"] = _prompt_overrides(values, "PromptOverridesJSON")

    return NotebookWorkflowRequest(
        tenant_id=tenant_id,
        model_id=model_id,
        workflow=model_workflow,
        analysis_operation=analysis_operation,
        expected_model_revision=expected_revision,
        idempotency_key=idempotency_key,
        create_payload=payload,
    )


def create_workflow_widgets(
    workflow: str,
    *,
    dbutils: Any,
    uploaded_root: Path | None = None,
) -> None:
    """Create the visible widget bar for one workflow notebook."""
    _validate_workflow(workflow)
    del uploaded_root
    for spec in widget_specs(workflow):
        if spec.choices:
            dbutils.widgets.dropdown(spec.name, spec.default, list(spec.choices), spec.label)
        else:
            dbutils.widgets.text(spec.name, spec.default, spec.label)


def run_notebook(
    workflow: str,
    *,
    dbutils: Any,
    uploaded_root: Path | None = None,
) -> Any:
    """Read existing widgets and execute one independent imported Workflow."""
    from .runtime import load_notebook_runtime_settings, locate_uploaded_root
    from .workflow_execution import execute_notebook_workflow

    root = uploaded_root or locate_uploaded_root(Path.cwd())
    settings = load_notebook_runtime_settings(root)
    specs = widget_specs(workflow)
    values = {spec.name: dbutils.widgets.get(spec.name) for spec in specs}
    request = build_notebook_request(
        workflow,
        values,
    )
    result = execute_notebook_workflow(
        request,
        settings=settings,
    )
    print(json.dumps(result.as_dict(), ensure_ascii=False, separators=(",", ":"), sort_keys=True))
    return result


def _validate_workflow(workflow: str) -> None:
    if workflow not in _WORKFLOWS:
        raise NotebookConfigurationError("The requested notebook Workflow is unavailable.")


def _optional(values: Mapping[str, str], key: str, *, maximum: int) -> str | None:
    value = values.get(key, "").strip()
    if not value:
        return None
    if len(value.encode("utf-8")) > maximum or re.search(r"[\x00-\x1f\x7f]", value):
        raise NotebookConfigurationError(f"{key} must be valid text.")
    return value


def _bounded_int(values: Mapping[str, str], key: str, *, minimum: int, maximum: int) -> int:
    raw = values.get(key, "").strip()
    if re.fullmatch(r"0|[1-9][0-9]*", raw) is None:
        raise NotebookConfigurationError(
            f"{key} must be an integer from {minimum} through {maximum}."
        )
    value = int(raw)
    if not minimum <= value <= maximum:
        raise NotebookConfigurationError(
            f"{key} must be an integer from {minimum} through {maximum}."
        )
    return value


def _positive_int(values: Mapping[str, str], key: str) -> int:
    return _bounded_int(values, key, minimum=1, maximum=9_223_372_036_854_775_807)


def _optional_positive_int(values: Mapping[str, str], key: str) -> int | None:
    if not values.get(key, "").strip():
        return None
    return _positive_int(values, key)


def _uuid(values: Mapping[str, str], key: str) -> UUID:
    raw = values.get(key, "").strip()
    try:
        value = UUID(raw)
    except ValueError:
        raise NotebookConfigurationError(f"{key} must be a UUID.") from None
    if value.int == 0:
        raise NotebookConfigurationError(f"{key} must not be the zero UUID.")
    return value


def _choice(values: Mapping[str, str], key: str, choices: set[str]) -> str:
    value = values.get(key, "").strip()
    if value not in choices:
        raise NotebookConfigurationError(f"{key} has an unavailable value.")
    return value


def _positive_int_array(values: Mapping[str, str], key: str) -> list[int]:
    raw = values.get(key, "").strip()
    if len(raw.encode("utf-8")) > 1024 * 1024:
        raise NotebookConfigurationError(f"{key} is too large.")
    try:
        decoded: object = json.loads(raw)
    except json.JSONDecodeError:
        raise NotebookConfigurationError(
            f"{key} must be a JSON array of positive integers."
        ) from None
    if not isinstance(decoded, list):
        raise NotebookConfigurationError(
            f"{key} must contain at most 50000 unique positive integers."
        )
    parsed = cast(list[object], decoded)
    if (
        len(parsed) > 50_000
        or any(type(value) is not int or value <= 0 for value in parsed)
        or len(parsed) != len(set(cast(list[int], parsed)))
    ):
        raise NotebookConfigurationError(
            f"{key} must contain at most 50000 unique positive integers."
        )
    return cast(list[int], parsed)


def _prompt_overrides(values: Mapping[str, str], key: str) -> dict[str, int]:
    raw = values.get(key, "").strip()
    if len(raw.encode("utf-8")) > 32 * 1024:
        raise NotebookConfigurationError(f"{key} is too large.")
    try:
        decoded: object = json.loads(raw)
    except json.JSONDecodeError:
        raise NotebookConfigurationError(
            f"{key} must be a JSON object from Workflow Stage IDs to Prompt Version IDs."
        ) from None
    if not isinstance(decoded, dict):
        raise NotebookConfigurationError(f"{key} must contain at most 200 entries.")
    parsed = cast(dict[object, object], decoded)
    if len(parsed) > 200:
        raise NotebookConfigurationError(f"{key} must contain at most 200 entries.")
    if any(
        not isinstance(stage_id, str)
        or re.fullmatch(r"[1-9][0-9]*", stage_id) is None
        or type(version_id) is not int
        or version_id <= 0
        for stage_id, version_id in parsed.items()
    ):
        raise NotebookConfigurationError(
            f"{key} must map positive Workflow Stage IDs to positive Prompt Version IDs."
        )
    return cast(dict[str, int], parsed)


__all__ = [
    "NotebookWorkflowRequest",
    "WidgetSpec",
    "build_notebook_request",
    "run_notebook",
    "widget_specs",
]
