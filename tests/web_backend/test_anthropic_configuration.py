"""Claude registry, endpoint isolation, and authentication; no provider or database I/O."""

from collections.abc import Mapping

import pytest
from gds_etl_workbench.configuration import ConfigurationError
from gds_etl_workbench.domain.errors import InvalidRequestError
from gds_workbench_api.capabilities import (
    AgentExecutionModeCode,
    AgentRunSelection,
    load_default_agent_capabilities,
    select_agent_runtime_capabilities,
)
from gds_workbench_api.features.workflows.authoring.agent_execution import AgentExecutionRequest
from gds_workbench_api.integrations.agents import composition
from gds_workbench_api.integrations.agents.adapters import (
    ManagedModelAuthentication,
    OpenAIProviderCredentials,
)
from gds_workbench_api.integrations.agents.configuration import (
    AgentProviderConnection,
    AgentRuntimeConfiguration,
)
from pydantic import SecretStr

CLAUDE_CODE = "foundry-claude-opus-5-5"
ANTHROPIC_URL = "https://fixture.services.ai.azure.com/anthropic"
OPENAI_URL = "https://fixture.openai.azure.com/openai/v1/"


def _environment(*, entra: bool = False) -> dict[str, str]:
    values = {
        "GDS_WEB_AGENT_EXECUTION_MODE": "remote",
        "GDS_WEB_FOUNDRY_OPENAI_BASE_URL": OPENAI_URL,
        "GDS_WEB_FOUNDRY_ANTHROPIC_BASE_URL": ANTHROPIC_URL,
    }
    if entra:
        values.update(
            {
                "GDS_WEB_FOUNDRY_ENTRA_TENANT_ID": "11111111-1111-1111-1111-111111111111",
                "GDS_WEB_FOUNDRY_CLIENT_ID": "22222222-2222-2222-2222-222222222222",
                "GDS_WEB_FOUNDRY_CLIENT_SECRET": "synthetic-fixture-credential",
            }
        )
    else:
        values["GDS_WEB_FOUNDRY_API_KEY"] = "synthetic-fixture-credential"
    return values


@pytest.mark.parametrize("mode", ["one_shot", "tool_assisted"])
def test_claude_registry_uses_native_protocol_and_documented_efforts(
    mode: AgentExecutionModeCode,
) -> None:
    registry = load_default_agent_capabilities()
    model = next(model for model in registry.models if model.code == CLAUDE_CODE)
    assert model.name == "Anthropic Claude Opus 5.5"
    assert model.deployment_name == "claude-opus-5-5"
    assert model.provider_code == "microsoft_foundry"
    assert model.api_protocol == "anthropic_messages"
    profile = next(
        profile for profile in model.execution_profiles if profile.execution_mode == mode
    )
    assert profile.sdk_code == "openai_agents_sdk"
    assert profile.reasoning_effort_codes == ("default", "low", "medium", "high", "xhigh", "max")
    for effort in profile.reasoning_effort_codes:
        registry.validate_selection(
            AgentRunSelection(
                sdk_code="openai_agents_sdk",
                provider_code="microsoft_foundry",
                model_code=CLAUDE_CODE,
                reasoning_effort_code=effort,
                max_turns=10,
                validation_retry_count=2,
            ),
            execution_mode=mode,
        )


@pytest.mark.parametrize("mode", ["one_shot", "tool_assisted"])
@pytest.mark.parametrize("effort", ["none", "minimal", "ultra"])
def test_claude_rejects_unsupported_explicit_efforts(
    mode: AgentExecutionModeCode,
    effort: str,
) -> None:
    registry = load_default_agent_capabilities()
    selection = registry.resolve_default_selection(execution_mode=mode, model_code=CLAUDE_CODE)
    with pytest.raises(InvalidRequestError):
        registry.validate_selection(
            selection.model_copy(update={"reasoning_effort_code": effort}), execution_mode=mode
        )


@pytest.mark.parametrize("configured", [False, True])
def test_remote_claude_is_exposed_only_with_its_endpoint(configured: bool) -> None:
    values = _environment()
    if not configured:
        del values["GDS_WEB_FOUNDRY_ANTHROPIC_BASE_URL"]
    runtime = AgentRuntimeConfiguration.from_environment(values, production=True)
    registry = select_agent_runtime_capabilities(
        load_default_agent_capabilities(),
        configured_models={(item.provider_code, item.model_code) for item in runtime.connections},
    )
    assert (CLAUDE_CODE in {model.code for model in registry.models}) is configured
    assert {item.model_code for item in runtime.connections if item.api_protocol == "openai"} == {
        "foundry-primary",
        "foundry-gpt-5.6-luna",
    }
    if configured:
        claude = next(item for item in runtime.connections if item.model_code == CLAUDE_CODE)
        assert claude.openai_base_url is None
        assert claude.anthropic_base_url == ANTHROPIC_URL
        assert claude.authentication_key == "microsoft_foundry.anthropic"


@pytest.mark.parametrize("entra", [False, True])
def test_auto_anthropic_endpoint_exposes_claude_from_existing_foundry_resource(entra: bool) -> None:
    values = _environment(entra=entra)
    values["GDS_WEB_FOUNDRY_ANTHROPIC_BASE_URL"] = "auto"
    runtime = AgentRuntimeConfiguration.from_environment(values, production=True)
    registry = select_agent_runtime_capabilities(
        load_default_agent_capabilities(),
        configured_models={(item.provider_code, item.model_code) for item in runtime.connections},
    )
    claude = next(item for item in runtime.connections if item.model_code == CLAUDE_CODE)
    assert claude.anthropic_base_url == ANTHROPIC_URL
    assert claude.openai_base_url is None
    assert claude.token_scope == ("https://ai.azure.com/.default" if entra else None)
    assert CLAUDE_CODE in {model.code for model in registry.models}


def test_auto_anthropic_endpoint_accepts_services_openai_route() -> None:
    values = _environment()
    values["GDS_WEB_FOUNDRY_OPENAI_BASE_URL"] = "https://fixture.services.ai.azure.com/openai/v1/"
    values["GDS_WEB_FOUNDRY_ANTHROPIC_BASE_URL"] = "auto"
    runtime = AgentRuntimeConfiguration.from_environment(values, production=True)
    claude = next(item for item in runtime.connections if item.model_code == CLAUDE_CODE)
    assert claude.anthropic_base_url == ANTHROPIC_URL


@pytest.mark.parametrize(
    "hostname",
    [
        "fixture.other.openai.azure.com",
        "fixture.other.services.ai.azure.com",
        ".openai.azure.com",
        ".services.ai.azure.com",
        "-fixture.openai.azure.com",
        "fixture-.openai.azure.com",
    ],
)
def test_auto_anthropic_endpoint_rejects_malformed_resource_hosts(hostname: str) -> None:
    values = _environment()
    values["GDS_WEB_FOUNDRY_OPENAI_BASE_URL"] = f"https://{hostname}/openai/v1/"
    values["GDS_WEB_FOUNDRY_ANTHROPIC_BASE_URL"] = "auto"
    with pytest.raises(ConfigurationError):
        AgentRuntimeConfiguration.from_environment(values, production=True)


@pytest.mark.parametrize("entra", [False, True])
def test_claude_and_openai_keep_separate_authentication_audiences(entra: bool) -> None:
    runtime = AgentRuntimeConfiguration.from_environment(_environment(entra=entra), production=True)
    claude = next(item for item in runtime.connections if item.model_code == CLAUDE_CODE)
    openai = next(item for item in runtime.connections if item.model_code == "foundry-primary")
    assert openai.api_protocol == "openai"
    assert openai.openai_base_url == OPENAI_URL
    assert openai.anthropic_base_url is None
    assert openai.authentication_key == "microsoft_foundry"
    assert claude.foundry_client_credentials == openai.foundry_client_credentials
    assert claude.foundry_api_key == openai.foundry_api_key
    if entra:
        assert claude.token_scope == "https://ai.azure.com/.default"
        assert openai.token_scope == "https://cognitiveservices.azure.com/.default"
        assert claude.foundry_api_key is None
    else:
        assert claude.token_scope is openai.token_scope is None
        assert claude.foundry_client_credentials is None


@pytest.mark.parametrize(
    "url",
    [
        "http://fixture.services.ai.azure.com/anthropic",
        "https://fixture.openai.azure.com/anthropic",
        "https://different.services.ai.azure.com/anthropic",
        "https://fixture.other.services.ai.azure.com/anthropic",
        "https://fixture.services.ai.azure.com/anthropic/v1/messages",
        "https://fixture.services.ai.azure.com/openai/v1",
        "https://fixture.services.ai.azure.com/anthropic?api-version=fixture",
        "https://fixture.services.ai.azure.com/anthropic#fragment",
        "https://user@fixture.services.ai.azure.com/anthropic",
        "https://fixture.services.ai.azure.com:8443/anthropic",
        "https://fixture.services.ai.azure.com:invalid/anthropic",
        "https://fixture.services.ai.azure.com.example.invalid/anthropic",
    ],
)
def test_anthropic_endpoint_rejects_invalid_or_different_resource_routes(url: str) -> None:
    values = _environment()
    values["GDS_WEB_FOUNDRY_ANTHROPIC_BASE_URL"] = url
    with pytest.raises(ConfigurationError):
        AgentRuntimeConfiguration.from_environment(values, production=True)


def test_anthropic_endpoint_accepts_same_resource_services_openai_route() -> None:
    values = _environment()
    values["GDS_WEB_FOUNDRY_OPENAI_BASE_URL"] = "https://fixture.services.ai.azure.com/openai/v1"
    values["GDS_WEB_FOUNDRY_ANTHROPIC_BASE_URL"] = ANTHROPIC_URL + "/"
    runtime = AgentRuntimeConfiguration.from_environment(values, production=True)
    assert any(item.model_code == CLAUDE_CODE for item in runtime.connections)


def test_fake_execution_rejects_anthropic_endpoint() -> None:
    with pytest.raises(ConfigurationError, match="fake agent execution"):
        AgentRuntimeConfiguration.from_environment(
            {"GDS_WEB_FOUNDRY_ANTHROPIC_BASE_URL": ANTHROPIC_URL},
            production=False,
        )


@pytest.mark.asyncio
async def test_fake_execution_exposes_claude_without_provider_configuration() -> None:
    registry = load_default_agent_capabilities()
    router = composition.create_agent_execution_router(
        configuration=AgentRuntimeConfiguration.from_environment({}, production=False),
        capabilities=registry,
    )
    try:
        result = await router.execute(
            AgentExecutionRequest(
                workflow_run_id=1,
                workflow="metadata_enrichment",
                stage="candidate_authoring",
                execution_mode="one_shot",
                selection=registry.resolve_default_selection(
                    execution_mode="one_shot",
                    model_code=CLAUDE_CODE,
                ),
                system_prompt="Synthetic fixture instructions.",
                instruction_prompt="Produce the synthetic fixture candidate.",
                tool_instruction=None,
                context={},
                output_schema={"properties": {"descriptions": {"required": ["fixture"]}}},
            )
        )
    finally:
        await router.close()
    assert result.candidate == {
        "descriptions": {"fixture": "Synthetic local description for fixture."}
    }
    assert result.turn_count == 1
    assert result.tool_call_count == 0


@pytest.mark.parametrize("entra", [False, True])
@pytest.mark.asyncio
async def test_composition_creates_and_closes_separate_protocol_authentication(
    monkeypatch: pytest.MonkeyPatch,
    entra: bool,
) -> None:
    constructed: list[dict[str, object]] = []
    created: list[RecordingAuthentication] = []
    captured: dict[str, ManagedModelAuthentication] = {}

    class RecordingAuthentication:
        def __init__(self, **values: object) -> None:
            constructed.append(values)
            created.append(self)
            self.close_count = 0

        async def authenticate(self) -> OpenAIProviderCredentials:
            raise AssertionError("Configuration must not contact a provider")

        async def close(self) -> None:
            self.close_count += 1

    class RecordingAdapter:
        sdk_code = "openai_agents_sdk"

        def __init__(
            self,
            *,
            connections: tuple[AgentProviderConnection, ...],
            model_authentications: Mapping[str, ManagedModelAuthentication],
        ) -> None:
            assert {item.authentication_key for item in connections} == {
                "microsoft_foundry",
                "microsoft_foundry.anthropic",
            }
            captured.update(model_authentications)

    monkeypatch.setattr(composition, "FoundryModelAuthentication", RecordingAuthentication)
    monkeypatch.setattr(composition, "FoundryApiKeyAuthentication", RecordingAuthentication)
    monkeypatch.setattr(composition, "OpenAIAgentsSdkAdapter", RecordingAdapter)
    router = composition.create_agent_execution_router(
        configuration=AgentRuntimeConfiguration.from_environment(
            _environment(entra=entra),
            production=True,
        ),
        capabilities=load_default_agent_capabilities(),
    )
    assert len(created) == 2
    assert set(captured) == {"microsoft_foundry", "microsoft_foundry.anthropic"}
    assert captured["microsoft_foundry"] is not captured["microsoft_foundry.anthropic"]
    by_endpoint = {str(values["base_url"]).rstrip("/"): values for values in constructed}
    assert set(by_endpoint) == {OPENAI_URL.rstrip("/"), ANTHROPIC_URL}
    if entra:
        assert by_endpoint[OPENAI_URL.rstrip("/")]["token_scope"] == (
            "https://cognitiveservices.azure.com/.default"
        )
        assert by_endpoint[ANTHROPIC_URL]["token_scope"] == "https://ai.azure.com/.default"
    else:
        assert all(isinstance(values["api_key"], SecretStr) for values in constructed)
    await router.close()
    await router.close()
    assert [authentication.close_count for authentication in created] == [1, 1]


def test_composition_rejects_protocol_that_disagrees_with_registered_deployment() -> None:
    runtime = AgentRuntimeConfiguration.from_environment(_environment(), production=True)
    claude = next(item for item in runtime.connections if item.model_code == CLAUDE_CODE)
    wrong = claude.model_copy(update={"api_protocol": "openai"})
    with pytest.raises(ValueError, match="registry|protocol"):
        composition.create_agent_execution_router(
            configuration=runtime.model_copy(update={"connections": (wrong,)}),
            capabilities=load_default_agent_capabilities(),
        )
