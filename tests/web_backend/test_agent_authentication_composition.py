from __future__ import annotations

from collections.abc import Mapping
from uuid import UUID

import pytest
from pydantic import SecretStr

from gds_workbench_api.capabilities import (
    AgentCapabilityRegistry,
    load_default_agent_capabilities,
)
from gds_workbench_api.integrations.agents import composition as agent_composition
from gds_workbench_api.integrations.agents.adapters import (
    OpenAIProviderCredentials,
)
from gds_workbench_api.integrations.agents.configuration import (
    AgentProviderConnection,
    AgentRuntimeConfiguration,
    FoundryClientCredentials,
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
                model_endpoint="databricks-gpt-oss-120b",
                timeout_seconds=90,
            ),
        ),
    )


def _multi_remote_configuration() -> AgentRuntimeConfiguration:
    primary = _remote_configuration().connections[0]
    return AgentRuntimeConfiguration(
        mode="remote",
        timeout_seconds=90,
        connections=(
            primary,
            primary.model_copy(
                update={
                    "model_code": "databricks-secondary",
                    "model_endpoint": "databricks-secondary",
                }
            ),
        ),
    )


def _capabilities_with_secondary(provider_code: str) -> AgentCapabilityRegistry:
    registry = load_default_agent_capabilities()
    primary = next(
        model for model in registry.models if model.provider_code == provider_code
    )
    if provider_code == "databricks":
        model_code = "databricks-secondary"
    else:
        model_code = "foundry-secondary"
    secondary = primary.model_copy(
        update={
            "code": model_code,
            "name": f"Operator-verified {provider_code} secondary deployment",
            "deployment_name": model_code,
        }
    )
    return registry.model_copy(update={"models": (*registry.models, secondary)})


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


def test_remote_router_constructs_only_sdks_registered_for_the_bound_model(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    registry = load_default_agent_capabilities()
    primary = next(
        model for model in registry.models if model.code == "databricks-primary"
    )
    openai_only = primary.model_copy(
        update={
            "execution_profiles": tuple(
                profile
                for profile in primary.execution_profiles
                if profile.sdk_code == "openai_agents_sdk"
            )
        }
    )
    registry = registry.model_copy(
        update={
            "models": tuple(
                openai_only if model.code == openai_only.code else model
                for model in registry.models
            )
        }
    )
    constructed: list[str] = []

    class ForbiddenLangChainAdapter:
        sdk_code = "langchain_create_agent"

        def __init__(self, **_: object) -> None:
            raise AssertionError("An unregistered SDK adapter was constructed")

    class FakeOpenAIAdapter:
        sdk_code = "openai_agents_sdk"

        def __init__(self, **_: object) -> None:
            constructed.append(self.sdk_code)

    monkeypatch.setattr(
        agent_composition,
        "LangChainCreateAgentAdapter",
        ForbiddenLangChainAdapter,
    )
    monkeypatch.setattr(
        agent_composition,
        "OpenAIAgentsSdkAdapter",
        FakeOpenAIAdapter,
    )

    agent_composition.create_agent_execution_router(
        configuration=_remote_configuration(),
        capabilities=registry,
        provider_authentications={"databricks": InjectedAuthentication()},
    )

    assert constructed == ["openai_agents_sdk"]


@pytest.mark.asyncio
async def test_multiple_models_share_one_provider_authentication_and_cleanup(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured_connections: list[tuple[AgentProviderConnection, ...]] = []

    class FakeAdapter:
        def __init__(
            self,
            *,
            connections: tuple[AgentProviderConnection, ...],
            model_authentications: Mapping[str, object],
        ) -> None:
            captured_connections.append(connections)
            assert set(model_authentications) == {"databricks"}

    class FakeLangChainAdapter(FakeAdapter):
        sdk_code = "langchain_create_agent"

    class FakeOpenAIAdapter(FakeAdapter):
        sdk_code = "openai_agents_sdk"

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
        configuration=_multi_remote_configuration(),
        capabilities=_capabilities_with_secondary("databricks"),
        provider_authentications={"databricks": authentication},
    )

    assert len(captured_connections) == 2
    assert all(len(connections) == 2 for connections in captured_connections)
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


def test_remote_router_rejects_unregistered_model_binding_at_startup() -> None:
    primary = _remote_configuration().connections[0]
    configuration = AgentRuntimeConfiguration(
        mode="remote",
        timeout_seconds=90,
        connections=(
            primary.model_copy(
                update={
                    "model_code": "unregistered-model",
                    "model_endpoint": "unregistered-endpoint",
                }
            ),
        ),
    )

    with pytest.raises(ValueError, match="not registered"):
        agent_composition.create_agent_execution_router(
            configuration=configuration,
            capabilities=load_default_agent_capabilities(),
            provider_authentications={"databricks": InjectedAuthentication()},
        )


def test_remote_router_rejects_a_deployment_name_outside_the_registry() -> None:
    primary = _remote_configuration().connections[0]
    configuration = AgentRuntimeConfiguration(
        mode="remote",
        timeout_seconds=90,
        connections=(
            primary.model_copy(
                update={"model_endpoint": "environment-overridden-endpoint"}
            ),
        ),
    )

    with pytest.raises(ValueError, match="does not match the Agent registry"):
        agent_composition.create_agent_execution_router(
            configuration=configuration,
            capabilities=load_default_agent_capabilities(),
            provider_authentications={"databricks": InjectedAuthentication()},
        )


@pytest.mark.asyncio
async def test_multiple_foundry_models_create_and_close_one_shared_authentication(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    created: list[InjectedAuthentication] = []

    def fake_authentication(**_: object) -> InjectedAuthentication:
        authentication = InjectedAuthentication()
        created.append(authentication)
        return authentication

    class FakeAdapter:
        def __init__(self, **_: object) -> None: ...

    class FakeLangChainAdapter(FakeAdapter):
        sdk_code = "langchain_create_agent"

    class FakeOpenAIAdapter(FakeAdapter):
        sdk_code = "openai_agents_sdk"

    monkeypatch.setattr(
        agent_composition,
        "FoundryModelAuthentication",
        fake_authentication,
    )
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
    credentials = FoundryClientCredentials(
        tenant_id=UUID("11111111-1111-1111-1111-111111111111"),
        client_id=UUID("22222222-2222-2222-2222-222222222222"),
        client_secret=SecretStr("never-log-this-foundry-secret"),
    )
    primary = AgentProviderConnection(
        provider_code="microsoft_foundry",
        model_code="foundry-primary",
        model_endpoint="gpt-5.6-sol",
        timeout_seconds=90,
        openai_base_url="https://fixture.openai.azure.com/openai/v1/",
        token_scope="https://cognitiveservices.azure.com/.default",
        foundry_client_credentials=credentials,
    )

    router = agent_composition.create_agent_execution_router(
        configuration=AgentRuntimeConfiguration(
            mode="remote",
            timeout_seconds=90,
            connections=(
                primary,
                primary.model_copy(
                    update={
                        "model_code": "foundry-secondary",
                        "model_endpoint": "foundry-secondary",
                    }
                ),
            ),
        ),
        capabilities=_capabilities_with_secondary("microsoft_foundry"),
    )

    assert len(created) == 1
    await router.close()
    assert created[0].close_count == 1
