import json
from pathlib import Path
from uuid import UUID

import pytest
from fastapi.testclient import TestClient
from gds_etl_workbench.adapters.auth.identity import IdentityProvider
from gds_etl_workbench.configuration import AuthMode
from gds_etl_workbench.domain.errors import InvalidRequestError
from gds_workbench_api.capabilities import (
    AgentCapabilityRegistry,
    AgentExecutionModeCode,
    AgentModelExecutionProfile,
    AgentRunSelection,
    load_default_agent_capabilities,
    select_agent_runtime_capabilities,
)
from gds_workbench_api.main import create_app
from pydantic import ValidationError


def test_default_agent_capability_registry_is_valid_and_selection_is_bounded() -> None:
    registry = load_default_agent_capabilities()
    assert registry.schema_version == "3.0"
    assert {sdk.code for sdk in registry.sdks} == {"openai_agents_sdk"}
    assert {provider.code for provider in registry.providers} == {"microsoft_foundry"}
    assert {model.code for model in registry.models} == {"foundry-primary", "foundry-gpt-5.6-luna"}
    for model in registry.models:
        for profile in model.execution_profiles:
            for effort in profile.reasoning_effort_codes:
                registry.validate_selection(
                    AgentRunSelection(
                        sdk_code="openai_agents_sdk",
                        provider_code="microsoft_foundry",
                        model_code=model.code,
                        reasoning_effort_code=effort,
                        max_turns=10,
                        validation_retry_count=2,
                    ),
                    execution_mode=profile.execution_mode,
                )
    selection = registry.resolve_default_selection(execution_mode="one_shot")
    for changed in (
        {"sdk_code": "langchain_create_agent"},
        {"provider_code": "databricks"},
        {"model_code": "databricks-primary"},
        {"reasoning_effort_code": "missing"},
    ):
        with pytest.raises(InvalidRequestError):
            registry.validate_selection(selection.model_copy(update=changed))
    with pytest.raises(InvalidRequestError):
        registry.validate_selection(selection, execution_mode="tool_assisted")


@pytest.mark.parametrize("mode", ["one_shot", "tool_assisted"])
def test_new_run_defaults_recover_retired_models_and_incompatible_efforts(
    mode: AgentExecutionModeCode,
) -> None:
    registry = load_default_agent_capabilities()
    selected = registry.resolve_default_selection(
        execution_mode=mode,
        model_code="retired-model",
        reasoning_effort_code="unsupported",
        max_turns=99,
        validation_retry_count=-1,
    )
    assert selected.model_code == "foundry-primary"
    assert selected.max_turns == registry.max_turns.default
    assert selected.validation_retry_count == registry.validation_retries.default
    assert selected.reasoning_effort_code == ("none" if mode == "tool_assisted" else "default")
    preserved = registry.resolve_default_selection(
        execution_mode=mode,
        model_code="foundry-gpt-5.6-luna",
        reasoning_effort_code="none",
        max_turns=12,
        validation_retry_count=3,
    )
    assert preserved.model_code == "foundry-gpt-5.6-luna"
    assert (preserved.max_turns, preserved.validation_retry_count) == (12, 3)


def test_selection_validation_uses_the_exact_sdk_and_execution_mode_profile() -> None:
    registry = load_default_agent_capabilities()
    foundry_model = next(model for model in registry.models if model.code == "foundry-primary")
    restricted_model = foundry_model.model_copy(
        update={
            "execution_profiles": (
                AgentModelExecutionProfile(
                    sdk_code="openai_agents_sdk",
                    execution_mode="one_shot",
                    reasoning_effort_codes=("low",),
                ),
                AgentModelExecutionProfile(
                    sdk_code="openai_agents_sdk",
                    execution_mode="tool_assisted",
                    reasoning_effort_codes=("high",),
                ),
            )
        }
    )
    restricted_registry = registry.model_copy(
        update={
            "models": tuple(
                restricted_model if model.code == restricted_model.code else model
                for model in registry.models
            )
        }
    )
    selection = AgentRunSelection(
        sdk_code="openai_agents_sdk",
        provider_code="microsoft_foundry",
        model_code="foundry-primary",
        reasoning_effort_code="high",
        max_turns=10,
        validation_retry_count=2,
    )

    restricted_registry.validate_selection(
        selection,
        execution_mode="tool_assisted",
    )
    with pytest.raises(InvalidRequestError):
        restricted_registry.validate_selection(selection, execution_mode="one_shot")
    with pytest.raises(InvalidRequestError):
        restricted_registry.validate_selection(
            selection.model_copy(update={"reasoning_effort_code": "low"}),
            execution_mode="tool_assisted",
        )


def test_duplicate_model_execution_profiles_fail_registry_validation() -> None:
    payload = load_default_agent_capabilities().model_dump(mode="json")
    profile = payload["models"][0]["execution_profiles"][0]
    payload["models"][0]["execution_profiles"].append(profile)

    with pytest.raises(ValidationError, match="repeats an execution profile"):
        AgentCapabilityRegistry.model_validate_json(json.dumps(payload), strict=True)


def test_model_deployment_names_are_unique_within_a_provider() -> None:
    payload = load_default_agent_capabilities().model_dump(mode="json")
    duplicate = dict(payload["models"][0])
    duplicate["code"] = "foundry-duplicate-deployment"
    payload["models"].append(duplicate)

    with pytest.raises(ValidationError, match="deployment names must be unique"):
        AgentCapabilityRegistry.model_validate_json(json.dumps(payload), strict=True)


def test_invalid_capability_cross_references_fail_before_startup(
    tmp_path: Path,
) -> None:
    invalid_path = tmp_path / "agent_capabilities.json"
    invalid_path.write_text(
        json.dumps(
            {
                "schema_version": "3.0",
                "sdks": [
                    {
                        "code": "openai_agents_sdk",
                        "name": "OpenAI Agents SDK",
                        "provider_codes": ["missing_provider"],
                    }
                ],
                "providers": [],
                "models": [],
                "reasoning_efforts": [],
                "max_turns": {"minimum": 1, "default": 10, "maximum": 50},
                "validation_retries": {"minimum": 0, "default": 2, "maximum": 5},
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(ValidationError):
        AgentCapabilityRegistry.from_path(invalid_path)


def test_runtime_capabilities_include_only_exact_configured_registry_models() -> None:
    registry = load_default_agent_capabilities()
    primary = next(model for model in registry.models if model.code == "foundry-primary")
    secondary = primary.model_copy(
        update={
            "code": "foundry-secondary",
            "name": "Operator-verified secondary Foundry deployment",
            "deployment_name": "secondary-serving-endpoint",
        }
    )

    selected = select_agent_runtime_capabilities(
        registry.model_copy(update={"models": (*registry.models, secondary)}),
        configured_models={("microsoft_foundry", "foundry-secondary")},
    )

    assert [provider.code for provider in selected.providers] == ["microsoft_foundry"]
    assert [model.code for model in selected.models] == ["foundry-secondary"]
    assert all(sdk.provider_codes == ("microsoft_foundry",) for sdk in selected.sdks)


@pytest.mark.parametrize(
    "configured_models",
    (
        set[tuple[str, str]](),
        {("microsoft_foundry", "missing-model")},
        {("databricks", "foundry-primary")},
    ),
)
def test_runtime_capabilities_reject_zero_unknown_or_mismatched_bindings(
    configured_models: set[tuple[str, str]],
) -> None:
    with pytest.raises(ValueError):
        select_agent_runtime_capabilities(
            load_default_agent_capabilities(),
            configured_models=configured_models,
        )


def test_agent_capabilities_are_authenticated_and_exposed_read_only() -> None:
    app = create_app(
        identity_provider=IdentityProvider(
            AuthMode.DEV,
            local_tenant_id=UUID("11111111-1111-1111-1111-111111111111"),
            local_principal_object_id=UUID("22222222-2222-2222-2222-222222222222"),
        ),
        agent_capability_registry=load_default_agent_capabilities(),
    )

    with TestClient(app) as client:
        response = client.get("/api/v1/config/agent-capabilities")

    assert response.status_code == 200
    payload = response.json()
    assert payload["schema_version"] == "3.0"
    assert payload["models"][0]["provider_code"] == "microsoft_foundry"
    assert payload["models"][0]["deployment_name"] == "gpt-5.6-sol"
    assert "openai_base_url" not in response.text
    assert "environment_variable" not in response.text
    assert "secret" not in response.text.lower()
