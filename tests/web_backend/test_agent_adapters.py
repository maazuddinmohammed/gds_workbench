import json
from collections.abc import Mapping
from types import SimpleNamespace
from typing import Any, cast

import pytest
from gds_etl_workbench.domain.errors import WorkbenchError
from gds_workbench_api.capabilities import AgentRunSelection
from gds_workbench_api.features.workflows.authoring.agent_execution import (
    AGENT_OUTPUT_CONTRACT_INSTRUCTION,
    AgentExecutionRequest,
    LocalAgentToolDefinition,
)
from gds_workbench_api.features.workflows.authoring.repair import (
    AgentCandidateValidation,
    ValidationRepairRunner,
    load_default_agent_context_policy,
)
from gds_workbench_api.integrations.agents import adapters as agent_adapters
from gds_workbench_api.integrations.agents.adapters import (
    FoundryApiKeyAuthentication,
    FoundryModelAuthentication,
    OpenAIAgentsSdkAdapter,
    OpenAIProviderCredentials,
)
from gds_workbench_api.integrations.agents.configuration import (
    AgentProviderConnection,
)
from pydantic import JsonValue, SecretStr, ValidationError


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
            api_key=SecretStr("short-lived-foundry-token"),
            base_url="https://fixture.openai.azure.com/openai/v1/",
        )


def test_agent_connection_rejects_removed_provider() -> None:
    with pytest.raises(ValidationError):
        AgentProviderConnection.model_validate(
            {
                "provider_code": "databricks",
                "model_code": "removed-model",
                "model_endpoint": "removed-endpoint",
                "timeout_seconds": 90,
            }
        )


@pytest.mark.asyncio
async def test_openai_adapter_rejects_removed_sdk_before_provider_io() -> None:
    connection = AgentProviderConnection(
        provider_code="microsoft_foundry",
        model_code="foundry-primary",
        model_endpoint="fixture-endpoint",
        timeout_seconds=90,
    )
    with pytest.raises(ValueError, match="requires one authentication adapter"):
        OpenAIAgentsSdkAdapter(connections=(connection,))
    adapter = OpenAIAgentsSdkAdapter(
        connections=(connection,),
        model_authentications={"microsoft_foundry": FakeModelAuthentication()},
    )
    with pytest.raises(WorkbenchError) as caught:
        await adapter.execute(
            _request(
                sdk_code="langchain_create_agent",
                provider_code="microsoft_foundry",
                model_code="foundry-primary",
            )
        )
    assert caught.value.code == "invalid_request"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "malformed",
    (
        '```json\n{"entities":[]}\n```',
        '{"entities":[',
        '{"entities":[1],"entities":[]}',
        '{"descriptions":{"target":"first","target":"second"}}',
    ),
    ids=("fenced", "incomplete", "duplicate-field", "duplicate-description-target"),
)
async def test_provider_json_format_errors_reach_bounded_validation_repair(
    monkeypatch: pytest.MonkeyPatch,
    malformed: str,
) -> None:
    outputs = iter((malformed, '{"entities":[]}'))
    contexts: list[dict[str, Any]] = []

    class FakeClient:
        def __init__(self, **_: Any) -> None:
            pass

        async def close(self) -> None:
            pass

    class FakeRunner:
        @staticmethod
        async def run(_: object, payload: str, **__: Any) -> SimpleNamespace:
            contexts.append(json.loads(payload)["context"])
            return SimpleNamespace(
                final_output=next(outputs), raw_responses=[object()], new_items=[]
            )

    class Validator:
        async def validate(self, candidate: JsonValue) -> AgentCandidateValidation:
            assert candidate == {"entities": []}
            return AgentCandidateValidation(issues=())

    monkeypatch.setattr(agent_adapters, "AsyncOpenAI", FakeClient)
    monkeypatch.setattr(agent_adapters, "OpenAIChatCompletionsModel", FakeClient)
    monkeypatch.setattr(agent_adapters, "Agent", FakeClient)
    monkeypatch.setattr(agent_adapters, "Runner", FakeRunner)
    adapter = OpenAIAgentsSdkAdapter(
        connections=(
            AgentProviderConnection(
                provider_code="microsoft_foundry",
                model_code="foundry-primary",
                model_endpoint="fixture-endpoint",
                timeout_seconds=90,
            ),
        ),
        model_authentications={"microsoft_foundry": FakeModelAuthentication()},
    )
    result = await ValidationRepairRunner(
        executor=adapter,
        policy=load_default_agent_context_policy(),
    ).run(
        request=_request(
            sdk_code="openai_agents_sdk",
            provider_code="microsoft_foundry",
            model_code="foundry-primary",
        ),
        validator=Validator(),
    )

    assert result.candidate == {"entities": []}
    assert result.attempt_count == 2
    assert "original_context" not in contexts[0]
    assert "original_context" not in contexts[1]
    assert contexts[1]["repair"]["previous_candidate"] == malformed
    assert contexts[1]["repair"]["validation_issues"][0]["code"] == "candidate.output_schema_type"
    assert malformed not in repr(result)


@pytest.mark.asyncio
async def test_openai_adapter_routes_exact_model_with_shared_provider_authentication(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, Any] = {}

    class FakeClient:
        def __init__(self, **_: Any) -> None: ...

        async def close(self) -> None: ...

    class FakeRunner:
        @staticmethod
        async def run(*_: Any, **__: Any) -> SimpleNamespace:
            return SimpleNamespace(
                final_output='{"entities":[]}', raw_responses=[object()], new_items=[]
            )

    def fake_model(**kwargs: Any) -> str:
        captured["model"] = kwargs
        return "model"

    monkeypatch.setattr(agent_adapters, "AsyncOpenAI", FakeClient)
    monkeypatch.setattr(agent_adapters, "OpenAIChatCompletionsModel", fake_model)
    monkeypatch.setattr(agent_adapters, "Agent", FakeClient)
    monkeypatch.setattr(agent_adapters, "Runner", FakeRunner)
    adapter = OpenAIAgentsSdkAdapter(
        connections=(
            AgentProviderConnection(
                provider_code="microsoft_foundry",
                model_code="foundry-primary",
                model_endpoint="primary-endpoint",
                timeout_seconds=90,
            ),
            AgentProviderConnection(
                provider_code="microsoft_foundry",
                model_code="foundry-secondary",
                model_endpoint="secondary-endpoint",
                timeout_seconds=90,
            ),
        ),
        model_authentications={"microsoft_foundry": FakeModelAuthentication()},
    )

    await adapter.execute(
        _request(
            sdk_code="openai_agents_sdk",
            provider_code="microsoft_foundry",
            model_code="foundry-secondary",
        )
    )

    assert captured["model"]["model"] == "secondary-endpoint"


@pytest.mark.asyncio
@pytest.mark.parametrize("empty_tool_selection", (False, True), ids=("one-shot", "zero-tools"))
async def test_openai_agents_adapter_disables_tracing_and_parses_json(
    monkeypatch: pytest.MonkeyPatch,
    empty_tool_selection: bool,
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

    class EmptyToolCatalog:
        definitions: tuple[LocalAgentToolDefinition, ...] = ()
        max_cumulative_result_bytes = 1024

        def invoke(self, tool_name: str, arguments: Mapping[str, JsonValue]) -> JsonValue:
            raise AssertionError("No tools are enabled")

    class FakeRunner:
        @staticmethod
        async def run(*args: Any, **kwargs: Any) -> SimpleNamespace:
            captured["run"] = (args, kwargs)
            return SimpleNamespace(
                final_output='{"relationships":[]}',
                raw_responses=[object(), object(), object()],
                new_items=[] if empty_tool_selection else [FakeToolCall(), object()],
            )

    monkeypatch.setattr(agent_adapters, "AsyncOpenAI", FakeClient)
    monkeypatch.setattr(agent_adapters, "OpenAIChatCompletionsModel", FakeModel)
    monkeypatch.setattr(agent_adapters, "Agent", FakeAgent)
    monkeypatch.setattr(agent_adapters, "Runner", FakeRunner)
    monkeypatch.setattr(agent_adapters, "ToolCallItem", FakeToolCall)
    adapter = OpenAIAgentsSdkAdapter(
        connections=(
            AgentProviderConnection(
                provider_code="microsoft_foundry",
                model_code="foundry-primary",
                model_endpoint="production-agent-endpoint",
                timeout_seconds=80,
            ),
        ),
        model_authentications={"microsoft_foundry": FakeModelAuthentication()},
    )

    request = _request(
        sdk_code="openai_agents_sdk",
        provider_code="microsoft_foundry",
        model_code="foundry-primary",
    )
    if empty_tool_selection:
        request = AgentExecutionRequest.model_validate(
            {
                **request.model_dump(),
                "execution_mode": "tool_assisted",
                "local_tool_catalog": EmptyToolCatalog(),
                "allowed_tool_names": (),
            }
        )

    result = await adapter.execute(request)

    assert result.candidate == {"relationships": []}
    assert result.turn_count == 3
    assert result.tool_call_count == (0 if empty_tool_selection else 1)
    run_args, run_kwargs = cast(tuple[tuple[Any, ...], dict[str, Any]], captured["run"])
    assert run_kwargs["max_turns"] == 6
    assert run_kwargs["run_config"].tracing_disabled is True
    assert run_kwargs["run_config"].trace_include_sensitive_data is False
    assert captured["closed"] is True
    assert captured["model"]["model"] == "production-agent-endpoint"
    assert captured["agent"]["model_settings"].store is None
    assert captured["agent"]["tools"] == []
    assert captured["agent"]["model_settings"].tool_choice is None
    assert json.loads(run_args[1]) == {
        "instruction": request.instruction_prompt,
        "context": {"repair": None},
        "required_output_schema": request.output_schema,
    }
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
                provider_code="microsoft_foundry",
                model_code="foundry-primary",
                model_endpoint="primary-endpoint",
                timeout_seconds=90,
            ),
        ),
        model_authentications={"microsoft_foundry": FakeModelAuthentication()},
    )
    request = _request(
        sdk_code="openai_agents_sdk",
        provider_code="microsoft_foundry",
        model_code="foundry-primary",
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
    adapter = OpenAIAgentsSdkAdapter(connections=())

    with pytest.raises(WorkbenchError) as caught:
        await adapter.execute(
            _request(
                sdk_code="openai_agents_sdk",
                provider_code="microsoft_foundry",
                model_code="foundry-primary",
            )
        )

    assert caught.value.code == "invalid_request"


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
    adapter = OpenAIAgentsSdkAdapter(
        connections=(
            AgentProviderConnection(
                provider_code="microsoft_foundry",
                model_code="foundry-primary",
                model_endpoint="production-agent-endpoint",
                timeout_seconds=90,
            ),
        ),
        model_authentications={"microsoft_foundry": FakeModelAuthentication()},
    )

    with pytest.raises(WorkbenchError) as caught:
        await adapter.execute(
            _request(
                sdk_code="openai_agents_sdk",
                provider_code="microsoft_foundry",
                model_code="different-model",
            )
        )

    assert caught.value.code == "invalid_request"
