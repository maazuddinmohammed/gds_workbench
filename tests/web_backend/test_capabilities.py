import json
from pathlib import Path
from uuid import UUID

import pytest
from fastapi.testclient import TestClient
from gds_etl_workbench.adapters.auth.identity import IdentityProvider
from gds_etl_workbench.configuration import AuthMode
from gds_etl_workbench.domain.errors import InvalidRequestError
from pydantic import ValidationError

from gds_workbench_api.capabilities import (
    AgentCapabilityRegistry,
    AgentModelExecutionProfile,
    AgentRunSelection,
    load_default_agent_capabilities,
    select_agent_runtime_capabilities,
)
from gds_workbench_api.main import create_app


def test_default_agent_capability_registry_is_valid_and_selection_is_bounded() -> None:
    registry = load_default_agent_capabilities()

    assert registry.schema_version == "3.0"
    assert {sdk.code for sdk in registry.sdks} == {
        "langchain_create_agent",
        "openai_agents_sdk",
    }
    assert (
        next(sdk.name for sdk in registry.sdks if sdk.code == "langchain_create_agent")
        == "LangChain create_agent"
    )
    assert {provider.code for provider in registry.providers} == {
        "databricks",
        "microsoft_foundry",
    }
    assert {effort.code for effort in registry.reasoning_efforts} == {
        "default",
        "none",
        "minimal",
        "low",
        "medium",
        "high",
        "xhigh",
        "max",
    }
    assert {
        (model.code, model.name, model.provider_code, model.deployment_name)
        for model in registry.models
    } == {
        (
            "databricks-primary",
            "OpenAI GPT OSS 120B",
            "databricks",
            "databricks-gpt-oss-120b",
        ),
        (
            "databricks-claude-opus-5",
            "Anthropic Claude Opus 5",
            "databricks",
            "databricks-claude-opus-5",
        ),
        (
            "foundry-primary",
            "OpenAI GPT-5.6 Sol",
            "microsoft_foundry",
            "gpt-5.6-sol",
        ),
        (
            "foundry-gpt-5.6-luna",
            "OpenAI GPT-5.6 Luna",
            "microsoft_foundry",
            "gpt-5.6-luna",
        ),
    }
    selection = AgentRunSelection(
        sdk_code="langchain_create_agent",
        provider_code="databricks",
        model_code="databricks-primary",
        reasoning_effort_code="default",
        max_turns=10,
        validation_retry_count=2,
    )
    databricks_model = next(
        model for model in registry.models if model.code == "databricks-primary"
    )
    assert databricks_model.deployment_name == "databricks-gpt-oss-120b"
    assert not hasattr(databricks_model, "deployment_binding")
    assert {
        (profile.sdk_code, profile.execution_mode)
        for profile in databricks_model.execution_profiles
    } == {
        (sdk_code, execution_mode)
        for sdk_code in ("langchain_create_agent", "openai_agents_sdk")
        for execution_mode in ("one_shot", "tool_assisted", "detailed_coverage")
    }
    assert not hasattr(databricks_model, "reasoning_effort_codes")

    registry.validate_selection(selection, execution_mode="one_shot")
    registry.validate_selection(selection)
    registry.validate_selection(
        selection.model_copy(update={"sdk_code": "openai_agents_sdk"}),
        execution_mode="tool_assisted",
    )
    registry.validate_selection(
        selection.model_copy(
            update={
                "reasoning_effort_code": "high",
            }
        ),
        execution_mode="tool_assisted",
    )
    with pytest.raises(InvalidRequestError):
        registry.validate_selection(
            selection.model_copy(
                update={
                    "model_code": "databricks-claude-opus-5",
                    "reasoning_effort_code": "high",
                }
            ),
            execution_mode="tool_assisted",
        )
    registry.validate_selection(
        selection.model_copy(
            update={
                "model_code": "databricks-claude-opus-5",
                "reasoning_effort_code": "default",
            }
        ),
        execution_mode="one_shot",
    )
    registry.validate_selection(
        selection.model_copy(
            update={
                "provider_code": "microsoft_foundry",
                "model_code": "foundry-primary",
                "reasoning_effort_code": "xhigh",
            }
        ),
        execution_mode="detailed_coverage",
    )
    registry.validate_selection(
        selection.model_copy(
            update={
                "provider_code": "microsoft_foundry",
                "model_code": "foundry-primary",
                "reasoning_effort_code": "none",
            }
        ),
        execution_mode="tool_assisted",
    )
    with pytest.raises(InvalidRequestError):
        registry.validate_selection(
            selection.model_copy(
                update={
                    "provider_code": "microsoft_foundry",
                    "model_code": "foundry-primary",
                    "reasoning_effort_code": "default",
                }
            ),
            execution_mode="tool_assisted",
        )


def test_selection_validation_uses_the_exact_sdk_and_execution_mode_profile() -> None:
    registry = load_default_agent_capabilities()
    databricks_model = next(
        model for model in registry.models if model.code == "databricks-primary"
    )
    restricted_model = databricks_model.model_copy(
        update={
            "execution_profiles": (
                AgentModelExecutionProfile(
                    sdk_code="langchain_create_agent",
                    execution_mode="one_shot",
                    reasoning_effort_codes=("low",),
                ),
                AgentModelExecutionProfile(
                    sdk_code="langchain_create_agent",
                    execution_mode="detailed_coverage",
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
        sdk_code="langchain_create_agent",
        provider_code="databricks",
        model_code="databricks-primary",
        reasoning_effort_code="high",
        max_turns=10,
        validation_retry_count=2,
    )

    restricted_registry.validate_selection(
        selection,
        execution_mode="detailed_coverage",
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
    duplicate["code"] = "databricks-duplicate-deployment"
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
    primary = next(
        model for model in registry.models if model.code == "databricks-primary"
    )
    secondary = primary.model_copy(
        update={
            "code": "databricks-secondary",
            "name": "Operator-verified secondary Databricks deployment",
            "deployment_name": "secondary-serving-endpoint",
        }
    )

    selected = select_agent_runtime_capabilities(
        registry.model_copy(update={"models": (*registry.models, secondary)}),
        configured_models={("databricks", "databricks-secondary")},
    )

    assert [provider.code for provider in selected.providers] == ["databricks"]
    assert [model.code for model in selected.models] == ["databricks-secondary"]
    assert all(sdk.provider_codes == ("databricks",) for sdk in selected.sdks)


@pytest.mark.parametrize(
    "configured_models",
    (
        set[tuple[str, str]](),
        {("databricks", "missing-model")},
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
    assert payload["models"][0]["provider_code"] == "databricks"
    assert payload["models"][0]["deployment_name"] == "databricks-gpt-oss-120b"
    assert "openai_base_url" not in response.text
    assert "environment_variable" not in response.text
    assert "secret" not in response.text.lower()
