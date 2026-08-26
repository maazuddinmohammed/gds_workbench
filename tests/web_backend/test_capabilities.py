import json
from pathlib import Path
from uuid import UUID

import pytest
from fastapi.testclient import TestClient
from gds_etl_workbench.adapters.auth.identity import IdentityProvider
from gds_etl_workbench.configuration import AuthMode
from pydantic import ValidationError

from gds_workbench_api.capabilities import (
    AgentCapabilityRegistry,
    AgentRunSelection,
    load_default_agent_capabilities,
    select_agent_provider_capabilities,
)
from gds_workbench_api.main import create_app


def test_default_agent_capability_registry_is_valid_and_selection_is_bounded() -> None:
    registry = load_default_agent_capabilities()

    assert registry.schema_version == "1.0"
    assert {sdk.code for sdk in registry.sdks} == {
        "langchain_create_agent",
        "openai_agents_sdk",
    }
    assert {provider.code for provider in registry.providers} == {
        "databricks",
        "microsoft_foundry",
    }
    selection = AgentRunSelection(
        sdk_code="langchain_create_agent",
        provider_code="databricks",
        model_code="databricks-primary",
        reasoning_effort_code="medium",
        max_turns=10,
        validation_retry_count=2,
    )
    registry.validate_selection(selection)
    registry.validate_selection(
        selection.model_copy(update={"sdk_code": "openai_agents_sdk"})
    )
    registry.validate_selection(
        selection.model_copy(
            update={
                "provider_code": "microsoft_foundry",
                "model_code": "foundry-primary",
            }
        )
    )


def test_invalid_capability_cross_references_fail_before_startup(
    tmp_path: Path,
) -> None:
    invalid_path = tmp_path / "agent_capabilities.json"
    invalid_path.write_text(
        json.dumps(
            {
                "schema_version": "1.0",
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


def test_runtime_capabilities_include_only_the_configured_provider() -> None:
    registry = select_agent_provider_capabilities(
        load_default_agent_capabilities(),
        provider_codes={"microsoft_foundry"},
    )

    assert [provider.code for provider in registry.providers] == ["microsoft_foundry"]
    assert [model.code for model in registry.models] == ["foundry-primary"]
    assert all(
        sdk.provider_codes == ("microsoft_foundry",)
        for sdk in registry.sdks
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
    assert payload["schema_version"] == "1.0"
    assert payload["models"][0]["provider_code"] == "databricks"
    assert "endpoint" not in response.text.lower()
    assert "secret" not in response.text.lower()
