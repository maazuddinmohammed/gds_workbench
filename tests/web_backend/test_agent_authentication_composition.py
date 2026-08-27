from __future__ import annotations

from collections.abc import Mapping

import pytest
from pydantic import SecretStr

from gds_workbench_api.capabilities import load_default_agent_capabilities
from gds_workbench_api.integrations.agents import composition as agent_composition
from gds_workbench_api.integrations.agents.adapters import (
    OpenAIProviderCredentials,
)
from gds_workbench_api.integrations.agents.configuration import (
    AgentProviderConnection,
    AgentRuntimeConfiguration,
)


class InjectedAuthentication:
    def __init__(self) -> None:
        self.close_count = 0

    async def authenticate(self) -> OpenAIProviderCredentials:
        return OpenAIProviderCredentials(
            api_key=SecretStr("never-log-this-injected-token"),
            base_url="https://fixture.azuredatabricks.net/serving-endpoints",
        )

    async def close(self) -> None:
        self.close_count += 1


def _remote_configuration() -> AgentRuntimeConfiguration:
    return AgentRuntimeConfiguration(
        mode="remote",
        timeout_seconds=90,
        connections=(
            AgentProviderConnection(
                provider_code="databricks",
                model_code="databricks-primary",
                model_endpoint="production-agent-endpoint",
                timeout_seconds=90,
            ),
        ),
    )


@pytest.mark.asyncio
async def test_injected_authentication_reaches_both_sdks_and_closes_once(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, Mapping[str, object]] = {}

    class FakeLangChainAdapter:
        sdk_code = "langchain_create_agent"

        def __init__(
            self,
            *,
            connections: tuple[AgentProviderConnection, ...],
            model_authentications: Mapping[str, object],
        ) -> None:
            assert len(connections) == 1
            captured[self.sdk_code] = model_authentications

    class FakeOpenAIAdapter:
        sdk_code = "openai_agents_sdk"

        def __init__(
            self,
            *,
            connections: tuple[AgentProviderConnection, ...],
            model_authentications: Mapping[str, object],
        ) -> None:
            assert len(connections) == 1
            captured[self.sdk_code] = model_authentications

    monkeypatch.setattr(
        agent_composition,
        "LangChainCreateAgentAdapter",
        FakeLangChainAdapter,
    )
    monkeypatch.setattr(
        agent_composition,
        "OpenAIAgentsSdkAdapter",
        FakeOpenAIAdapter,
    )
    authentication = InjectedAuthentication()

    router = agent_composition.create_agent_execution_router(
        configuration=_remote_configuration(),
        capabilities=load_default_agent_capabilities(),
        provider_authentications={"databricks": authentication},
    )

    assert set(captured) == {"langchain_create_agent", "openai_agents_sdk"}
    assert all(
        authentications["databricks"] is authentication
        for authentications in captured.values()
    )
    await router.close()
    await router.close()
    assert authentication.close_count == 1


@pytest.mark.parametrize(
    "provider_codes",
    ((), ("other",), ("databricks", "other")),
)
def test_injected_authentication_requires_exact_provider_coverage(
    provider_codes: tuple[str, ...],
) -> None:
    authentications = {
        provider_code: InjectedAuthentication() for provider_code in provider_codes
    }

    with pytest.raises(
        ValueError,
        match="Every configured Agent provider requires exactly one authentication adapter",
    ):
        agent_composition.create_agent_execution_router(
            configuration=_remote_configuration(),
            capabilities=load_default_agent_capabilities(),
            provider_authentications=authentications,
        )
