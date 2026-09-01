from types import SimpleNamespace
from typing import Any, cast

import pytest
from gds_etl_workbench.domain.errors import WorkbenchError
from pydantic import SecretStr

from gds_workbench_api.capabilities import AgentRunSelection
from gds_workbench_api.features.workflows.authoring.agent_execution import (
    AGENT_OUTPUT_CONTRACT_INSTRUCTION,
    AgentExecutionRequest,
)
from gds_workbench_api.integrations.agents import adapters as agent_adapters
from gds_workbench_api.integrations.agents.adapters import (
    DatabricksModelAuthentication,
    FoundryApiKeyAuthentication,
    FoundryModelAuthentication,
    LangChainCreateAgentAdapter,
    OpenAIAgentsSdkAdapter,
    OpenAIProviderCredentials,
)
from gds_workbench_api.integrations.agents.configuration import (
    AgentProviderConnection,
)


def _request(
    *,
    sdk_code: str,
    provider_code: str,
    model_code: str,
) -> AgentExecutionRequest:
    return AgentExecutionRequest(
        workflow_run_id=1048,
        workflow="logical",
        stage="entity_consolidation",
        execution_mode="one_shot",
        selection=AgentRunSelection(
            sdk_code=sdk_code,
            provider_code=provider_code,
            model_code=model_code,
            reasoning_effort_code="high",
            max_turns=6,
            validation_retry_count=2,
        ),
        system_prompt="sensitive system",
        instruction_prompt="sensitive instruction",
        tool_instruction=None,
        context={"scope": [1, 2]},
        output_schema={"type": "object"},
    )


class FakeModelAuthentication:
    async def authenticate(self) -> OpenAIProviderCredentials:
        return OpenAIProviderCredentials(
            api_key=SecretStr("short-lived-databricks-token"),
            base_url="https://fixture.azuredatabricks.net/serving-endpoints",
        )


@pytest.mark.asyncio
async def test_langchain_adapter_uses_prompt_json_and_bounded_turns(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, Any] = {}

    class FakeGraph:
        async def ainvoke(
            self,
            values: dict[str, Any],
            config: dict[str, Any],
        ) -> dict[str, Any]:
            captured["values"] = values
            captured["config"] = config
            return {
                "messages": [
                    SimpleNamespace(type="ai", tool_calls=[], content="intermediate"),
                    SimpleNamespace(
                        type="ai",
                        tool_calls=[{"name": "local"}],
                        content=[
                            {"type": "reasoning", "reasoning": "not an answer"},
                            {"type": "text", "text": '{"entities":[]}'},
                        ],
                    ),
                ],
            }

    def fake_model(**kwargs: Any) -> str:
        captured["model"] = kwargs
        return "model"

    def fake_create_agent(**kwargs: Any) -> FakeGraph:
        captured["agent"] = kwargs
        return FakeGraph()

    monkeypatch.setattr(agent_adapters, "ChatOpenAI", fake_model)
    monkeypatch.setattr(agent_adapters, "create_agent", fake_create_agent)
    adapter = LangChainCreateAgentAdapter(
        connections=(
            AgentProviderConnection(
                provider_code="databricks",
                model_code="databricks-primary",
                model_endpoint="production-agent-endpoint",
                timeout_seconds=90,
            ),
        ),
        model_authentications={"databricks": FakeModelAuthentication()},
    )

    result = await adapter.execute(
        _request(
            sdk_code="langchain_create_agent",
            provider_code="databricks",
            model_code="databricks-primary",
        )
    )

    assert result.candidate == {"entities": []}
    assert result.turn_count == 2
    assert result.tool_call_count == 1
    assert "response_format" not in captured["agent"]
    assert captured["agent"]["system_prompt"].endswith(AGENT_OUTPUT_CONTRACT_INSTRUCTION)
    assert captured["config"] == {"recursion_limit": 13}
    assert captured["model"]["model"] == "production-agent-endpoint"
    assert "store" not in captured["model"]
    assert "short-lived-databricks-token" not in repr(adapter)


@pytest.mark.asyncio
async def test_langchain_adapter_routes_exact_model_with_shared_provider_authentication(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, Any] = {}

    class FakeGraph:
        async def ainvoke(self, *_: Any, **__: Any) -> dict[str, Any]:
            return {
                "messages": [SimpleNamespace(type="ai", tool_calls=[], content='{"entities":[]}')]
            }

    def fake_model(**kwargs: Any) -> str:
        captured["model"] = kwargs
        return "model"

    def fake_create_agent(**_: Any) -> FakeGraph:
        return FakeGraph()

    monkeypatch.setattr(agent_adapters, "ChatOpenAI", fake_model)
    monkeypatch.setattr(agent_adapters, "create_agent", fake_create_agent)
    adapter = LangChainCreateAgentAdapter(
        connections=(
            AgentProviderConnection(
                provider_code="databricks",
                model_code="databricks-primary",
                model_endpoint="primary-endpoint",
                timeout_seconds=90,
            ),
            AgentProviderConnection(
                provider_code="databricks",
                model_code="databricks-secondary",
                model_endpoint="secondary-endpoint",
                timeout_seconds=90,
            ),
        ),
        model_authentications={"databricks": FakeModelAuthentication()},
    )

    await adapter.execute(
        _request(
            sdk_code="langchain_create_agent",
            provider_code="databricks",
            model_code="databricks-secondary",
        )
    )

    assert captured["model"]["model"] == "secondary-endpoint"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("reasoning_effort_code", "expected_reasoning_effort"),
    (("default", None), ("none", "none")),
)
async def test_langchain_adapter_distinguishes_provider_default_and_explicit_none(
    monkeypatch: pytest.MonkeyPatch,
    reasoning_effort_code: str,
    expected_reasoning_effort: str | None,
) -> None:
    captured: dict[str, Any] = {}

    class FakeGraph:
        async def ainvoke(self, *_: Any, **__: Any) -> dict[str, Any]:
            return {
                "messages": [SimpleNamespace(type="ai", tool_calls=[], content='{"entities":[]}')]
            }

    def fake_model(**kwargs: Any) -> dict[str, Any]:
        return captured.setdefault("model", kwargs)

    def fake_create_agent(**_: Any) -> FakeGraph:
        return FakeGraph()

    monkeypatch.setattr(
        agent_adapters,
        "ChatOpenAI",
        fake_model,
    )
    monkeypatch.setattr(agent_adapters, "create_agent", fake_create_agent)
    adapter = LangChainCreateAgentAdapter(
        connections=(
            AgentProviderConnection(
                provider_code="databricks",
                model_code="databricks-primary",
                model_endpoint="primary-endpoint",
                timeout_seconds=90,
            ),
        ),
        model_authentications={"databricks": FakeModelAuthentication()},
    )
    request = _request(
        sdk_code="langchain_create_agent",
        provider_code="databricks",
        model_code="databricks-primary",
    )

    await adapter.execute(
        request.model_copy(
            update={
                "selection": request.selection.model_copy(
                    update={"reasoning_effort_code": reasoning_effort_code}
                )
            }
        )
    )

    if expected_reasoning_effort is None:
        assert "reasoning_effort" not in captured["model"]
    else:
        assert captured["model"]["reasoning_effort"] == expected_reasoning_effort


@pytest.mark.asyncio
async def test_openai_agents_adapter_disables_tracing_and_parses_json(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, Any] = {}

    class FakeClient:
        def __init__(self, **kwargs: Any) -> None:
            captured["client"] = kwargs

        async def close(self) -> None:
            captured["closed"] = True

    class FakeModel:
        def __init__(self, **kwargs: Any) -> None:
            captured["model"] = kwargs

    class FakeAgent:
        def __init__(self, **kwargs: Any) -> None:
            captured["agent"] = kwargs

    class FakeToolCall:
        pass

    class FakeRunner:
        @staticmethod
        async def run(*args: Any, **kwargs: Any) -> SimpleNamespace:
            captured["run"] = (args, kwargs)
            return SimpleNamespace(
                final_output='{"relationships":[]}',
                raw_responses=[object(), object(), object()],
                new_items=[FakeToolCall(), object()],
            )

    monkeypatch.setattr(agent_adapters, "AsyncOpenAI", FakeClient)
    monkeypatch.setattr(agent_adapters, "OpenAIChatCompletionsModel", FakeModel)
    monkeypatch.setattr(agent_adapters, "Agent", FakeAgent)
    monkeypatch.setattr(agent_adapters, "Runner", FakeRunner)
    monkeypatch.setattr(agent_adapters, "ToolCallItem", FakeToolCall)
    adapter = OpenAIAgentsSdkAdapter(
        connections=(
            AgentProviderConnection(
                provider_code="databricks",
                model_code="databricks-primary",
                model_endpoint="production-agent-endpoint",
                timeout_seconds=80,
            ),
        ),
        model_authentications={"databricks": FakeModelAuthentication()},
    )

    result = await adapter.execute(
        _request(
            sdk_code="openai_agents_sdk",
            provider_code="databricks",
            model_code="databricks-primary",
        )
    )

    assert result.candidate == {"relationships": []}
    assert result.turn_count == 3
    assert result.tool_call_count == 1
    _, run_kwargs = cast(tuple[tuple[Any, ...], dict[str, Any]], captured["run"])
    assert run_kwargs["max_turns"] == 6
    assert run_kwargs["run_config"].tracing_disabled is True
    assert run_kwargs["run_config"].trace_include_sensitive_data is False
    assert captured["closed"] is True
    assert captured["model"]["model"] == "production-agent-endpoint"
    assert captured["agent"]["model_settings"].store is None
    assert captured["agent"]["instructions"].endswith(AGENT_OUTPUT_CONTRACT_INSTRUCTION)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("reasoning_effort_code", "expected_reasoning_effort"),
    (("default", None), ("none", "none")),
)
async def test_openai_agents_adapter_distinguishes_provider_default_and_explicit_none(
    monkeypatch: pytest.MonkeyPatch,
    reasoning_effort_code: str,
    expected_reasoning_effort: str | None,
) -> None:
    captured: dict[str, Any] = {}

    class FakeClient:
        def __init__(self, **_: Any) -> None: ...

        async def close(self) -> None: ...

    class FakeAgent:
        def __init__(self, **kwargs: Any) -> None:
            captured["settings"] = kwargs["model_settings"]

    class FakeRunner:
        @staticmethod
        async def run(*_: Any, **__: Any) -> SimpleNamespace:
            return SimpleNamespace(
                final_output='{"relationships":[]}',
                raw_responses=[object()],
                new_items=[],
            )

    def fake_model(**_: Any) -> str:
        return "model"

    monkeypatch.setattr(agent_adapters, "AsyncOpenAI", FakeClient)
    monkeypatch.setattr(
        agent_adapters,
        "OpenAIChatCompletionsModel",
        fake_model,
    )
    monkeypatch.setattr(agent_adapters, "Agent", FakeAgent)
    monkeypatch.setattr(agent_adapters, "Runner", FakeRunner)
    adapter = OpenAIAgentsSdkAdapter(
        connections=(
            AgentProviderConnection(
                provider_code="databricks",
                model_code="databricks-primary",
                model_endpoint="primary-endpoint",
                timeout_seconds=90,
            ),
        ),
        model_authentications={"databricks": FakeModelAuthentication()},
    )
    request = _request(
        sdk_code="openai_agents_sdk",
        provider_code="databricks",
        model_code="databricks-primary",
    )

    await adapter.execute(
        request.model_copy(
            update={
                "selection": request.selection.model_copy(
                    update={"reasoning_effort_code": reasoning_effort_code}
                )
            }
        )
    )

    if expected_reasoning_effort is None:
        assert captured["settings"].reasoning is None
    else:
        assert captured["settings"].reasoning.effort == expected_reasoning_effort


@pytest.mark.asyncio
async def test_adapter_rejects_provider_without_configured_connection() -> None:
    adapter = LangChainCreateAgentAdapter(connections=())

    with pytest.raises(WorkbenchError) as caught:
        await adapter.execute(
            _request(
                sdk_code="langchain_create_agent",
                provider_code="databricks",
                model_code="databricks-primary",
            )
        )

    assert caught.value.code == "invalid_request"


@pytest.mark.asyncio
async def test_databricks_model_authentication_uses_unified_oauth(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class FakeConfig:
        host = "https://fixture.azuredatabricks.net"

        @staticmethod
        def authenticate() -> dict[str, str]:
            return {"Authorization": "Bearer never-log-this-token"}

    class FakeWorkspace:
        def __init__(self, **kwargs: object) -> None:
            assert kwargs["product"] == "gds-workbench-web"
            assert kwargs["auth_type"] == "oauth-m2m"
            assert kwargs["debug_headers"] is False
            self.config = FakeConfig()

    monkeypatch.setattr(agent_adapters, "WorkspaceClient", FakeWorkspace)

    credentials = await DatabricksModelAuthentication().authenticate()

    assert credentials.base_url == ("https://fixture.azuredatabricks.net/serving-endpoints")
    assert credentials.api_key.get_secret_value() == "never-log-this-token"
    assert "never-log-this-token" not in repr(credentials)


@pytest.mark.asyncio
async def test_databricks_notebook_authentication_uses_default_unified_auth(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, object] = {}

    class FakeConfig:
        host = "https://fixture.azuredatabricks.net"

        @staticmethod
        def authenticate() -> dict[str, str]:
            return {"Authorization": "Bearer never-log-this-notebook-token"}

    class FakeWorkspace:
        def __init__(self, **kwargs: object) -> None:
            captured.update(kwargs)
            self.config = FakeConfig()

    monkeypatch.setattr(agent_adapters, "WorkspaceClient", FakeWorkspace)

    authentication = DatabricksModelAuthentication(mode="notebook")
    credentials = await authentication.authenticate()

    assert captured == {
        "debug_headers": False,
        "product": "gds-workbench-notebook",
        "product_version": "0.1.0",
    }
    assert "auth_type" not in captured
    assert credentials.api_key.get_secret_value() == "never-log-this-notebook-token"
    assert "never-log-this-notebook-token" not in repr(credentials)
    assert "never-log-this-notebook-token" not in repr(authentication)


@pytest.mark.asyncio
async def test_foundry_api_key_authentication_returns_redacted_credentials() -> None:
    authentication = FoundryApiKeyAuthentication(
        base_url="https://fixture.services.ai.azure.com/openai/v1",
        api_key=SecretStr("never-log-this-foundry-api-key"),
    )

    credentials = await authentication.authenticate()
    await authentication.close()
    await authentication.close()

    with pytest.raises(RuntimeError, match="authentication is closed"):
        await authentication.authenticate()

    assert credentials.base_url == "https://fixture.services.ai.azure.com/openai/v1/"
    assert credentials.api_key.get_secret_value() == "never-log-this-foundry-api-key"
    assert "never-log-this-foundry-api-key" not in repr(credentials)
    assert "never-log-this-foundry-api-key" not in repr(authentication)


@pytest.mark.asyncio
async def test_foundry_authentication_uses_direct_entra_token(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, object] = {}

    class FakeCredential:
        def __init__(self, **kwargs: object) -> None:
            captured["created"] = cast(int, captured.get("created", 0)) + 1
            captured["credential"] = kwargs

        async def get_token(self, scope: str) -> SimpleNamespace:
            scopes = cast(list[str], captured.setdefault("scopes", []))
            scopes.append(scope)
            return SimpleNamespace(token="never-log-this-foundry-token")

        async def close(self) -> None:
            captured["closed"] = cast(int, captured.get("closed", 0)) + 1

    monkeypatch.setattr(
        agent_adapters,
        "AsyncClientSecretCredential",
        FakeCredential,
    )
    authentication = FoundryModelAuthentication(
        base_url="https://fixture.openai.azure.com/openai/v1/",
        token_scope="https://cognitiveservices.azure.com/.default",
        tenant_id="11111111-1111-1111-1111-111111111111",
        client_id="22222222-2222-2222-2222-222222222222",
        client_secret=SecretStr("never-log-this-foundry-client-secret"),
    )

    credentials = await authentication.authenticate()
    second_credentials = await authentication.authenticate()
    await authentication.close()
    await authentication.close()

    with pytest.raises(RuntimeError, match="authentication is closed"):
        await authentication.authenticate()

    assert credentials.base_url == "https://fixture.openai.azure.com/openai/v1/"
    assert credentials.api_key.get_secret_value() == "never-log-this-foundry-token"
    assert second_credentials.api_key.get_secret_value() == "never-log-this-foundry-token"
    assert captured == {
        "created": 1,
        "credential": {
            "tenant_id": "11111111-1111-1111-1111-111111111111",
            "client_id": "22222222-2222-2222-2222-222222222222",
            "client_secret": "never-log-this-foundry-client-secret",
        },
        "scopes": [
            "https://cognitiveservices.azure.com/.default",
            "https://cognitiveservices.azure.com/.default",
        ],
        "closed": 1,
    }
    assert "never-log-this-foundry-token" not in repr(authentication)
    assert "never-log-this-foundry-client-secret" not in repr(authentication)


@pytest.mark.asyncio
async def test_adapter_requires_selected_model_mapping() -> None:
    adapter = LangChainCreateAgentAdapter(
        connections=(
            AgentProviderConnection(
                provider_code="databricks",
                model_code="databricks-primary",
                model_endpoint="production-agent-endpoint",
                timeout_seconds=90,
            ),
        ),
        model_authentications={"databricks": FakeModelAuthentication()},
    )

    with pytest.raises(WorkbenchError) as caught:
        await adapter.execute(
            _request(
                sdk_code="langchain_create_agent",
                provider_code="databricks",
                model_code="different-model",
            )
        )

    assert caught.value.code == "invalid_request"
