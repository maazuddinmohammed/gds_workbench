from __future__ import annotations

import json
import re
from decimal import Decimal
from pathlib import Path

import pytest

from gds_workbench_notebooks.errors import (
    NotebookConfigurationError,
    NotebookDatabaseError,
)
from gds_workbench_notebooks.runtime import (
    load_notebook_database_settings,
    load_notebook_runtime_settings,
    locate_uploaded_root,
    notebook_database_connection,
)

_PASSWORD = "fixture-password-must-stay-hidden"


def _root(tmp_path: Path, *, env_document: str | None = None) -> Path:
    root = tmp_path / "uploaded"
    (root / "src" / "gds_workbench_notebooks").mkdir(parents=True)
    (root / "src" / "gds_workbench_notebooks" / "__init__.py").write_text("")
    (root / "notebooks" / "nested").mkdir(parents=True)
    (root / "requirements.txt").write_text("psycopg[binary]==3.3.4\n")
    if env_document is not None:
        (root / ".env").write_text(env_document)
    return root


def _valid_env() -> str:
    return f"""\
GDS_NOTEBOOK_POSTGRES_HOST=workbench.postgres.database.azure.com
GDS_NOTEBOOK_POSTGRES_PORT=5432
GDS_NOTEBOOK_POSTGRES_DATABASE=gds_workbench
GDS_NOTEBOOK_POSTGRES_USER=gds_notebook_runtime
GDS_NOTEBOOK_POSTGRES_PASSWORD={_PASSWORD}
GDS_NOTEBOOK_POSTGRES_SSLMODE=verify-full
GDS_NOTEBOOK_POSTGRES_CONNECT_TIMEOUT_SECONDS=12
GDS_NOTEBOOK_POSTGRES_STATEMENT_TIMEOUT_SECONDS=45
GDS_NOTEBOOK_WORKFLOW_LEASE_SECONDS=45
GDS_NOTEBOOK_WORKFLOW_HEARTBEAT_SECONDS=15
GDS_NOTEBOOK_AGENT_TIMEOUT_SECONDS=240
"""


def test_locates_uploaded_root_from_a_nested_notebook_directory(tmp_path: Path) -> None:
    root = _root(tmp_path)

    assert locate_uploaded_root(root / "notebooks" / "nested") == root


def test_loads_only_explicit_database_settings_and_conceals_password(tmp_path: Path) -> None:
    root = _root(tmp_path, env_document=_valid_env())

    settings = load_notebook_database_settings(root)

    assert settings.host == "workbench.postgres.database.azure.com"
    assert settings.port == 5432
    assert settings.database == "gds_workbench"
    assert settings.user == "gds_notebook_runtime"
    assert settings.password == _PASSWORD
    assert settings.sslmode == "verify-full"
    assert settings.connect_timeout_seconds == 12
    assert settings.statement_timeout_seconds == 45
    assert _PASSWORD not in repr(settings)


def test_loads_bounded_workflow_runtime_controls(tmp_path: Path) -> None:
    root = _root(tmp_path, env_document=_valid_env())

    settings = load_notebook_runtime_settings(root)

    assert settings.database.user == "gds_notebook_runtime"
    assert settings.workflow_lease_seconds == 45
    assert settings.workflow_heartbeat_seconds == 15
    assert settings.agent_timeout_seconds == 240
    assert _PASSWORD not in repr(settings)


def test_runtime_controls_use_validated_safe_defaults(tmp_path: Path) -> None:
    document = "\n".join(
        line
        for line in _valid_env().splitlines()
        if not line.startswith(
            (
                "GDS_NOTEBOOK_WORKFLOW_",
                "GDS_NOTEBOOK_AGENT_TIMEOUT_SECONDS=",
            )
        )
    )

    settings = load_notebook_runtime_settings(_root(tmp_path, env_document=f"{document}\n"))

    assert settings.workflow_lease_seconds == 30
    assert settings.workflow_heartbeat_seconds == 10
    assert settings.agent_timeout_seconds == 120


@pytest.mark.parametrize(
    ("document", "message"),
    (
        (_valid_env() + "GDS_NOTEBOOK_POSTGRES_DSN=postgresql://unsafe\n", "unsupported"),
        (_valid_env() + "GDS_NOTEBOOK_PRINCIPAL_ID=12\n", "unsupported"),
        (
            _valid_env() + "GDS_NOTEBOOK_DATABRICKS_MODEL_ENDPOINT=legacy-endpoint\n",
            "unsupported",
        ),
        (
            _valid_env().replace("gds_notebook_runtime", "gds_web_runtime"),
            "gds_notebook_runtime",
        ),
        (
            _valid_env().replace("workbench.postgres.database.azure.com", "<postgresql-hostname>"),
            "placeholder",
        ),
        (
            _valid_env().replace("GDS_NOTEBOOK_POSTGRES_PORT=5432", ""),
            "missing",
        ),
        (_valid_env() + "GDS_NOTEBOOK_POSTGRES_PORT=5433\n", "repeats"),
    ),
)
def test_rejects_unsafe_or_ambiguous_env_documents(
    tmp_path: Path,
    document: str,
    message: str,
) -> None:
    root = _root(tmp_path, env_document=document)

    with pytest.raises(NotebookConfigurationError, match=message):
        load_notebook_database_settings(root)


def test_connection_uses_only_explicit_validated_keywords(tmp_path: Path) -> None:
    settings = load_notebook_database_settings(_root(tmp_path, env_document=_valid_env()))
    calls: list[dict[str, object]] = []

    class FakeConnection:
        def __enter__(self) -> FakeConnection:
            return self

        def __exit__(self, *args: object) -> None:
            return None

    def connector(**kwargs: object) -> FakeConnection:
        calls.append(kwargs)
        return FakeConnection()

    with notebook_database_connection(settings, connector=connector) as connection:
        assert isinstance(connection, FakeConnection)

    assert len(calls) == 1
    assert calls[0] == {
        "host": "workbench.postgres.database.azure.com",
        "port": 5432,
        "dbname": "gds_workbench",
        "user": "gds_notebook_runtime",
        "password": _PASSWORD,
        "sslmode": "verify-full",
        "connect_timeout": 12,
        "application_name": "gds_workbench_databricks_notebook",
        "options": "-c statement_timeout=45000",
        "row_factory": calls[0]["row_factory"],
    }
    assert "dsn" not in calls[0]


@pytest.mark.parametrize(
    ("field", "value", "message"),
    (
        ("GDS_NOTEBOOK_WORKFLOW_LEASE_SECONDS", "301", "lease duration"),
        ("GDS_NOTEBOOK_WORKFLOW_HEARTBEAT_SECONDS", "45", "shorter"),
        ("GDS_NOTEBOOK_AGENT_TIMEOUT_SECONDS", "601", "Agent timeout"),
    ),
)
def test_rejects_invalid_runtime_controls(
    tmp_path: Path,
    field: str,
    value: str,
    message: str,
) -> None:
    document = re.sub(rf"^{field}=.*$", f"{field}={value}", _valid_env(), flags=re.MULTILINE)

    with pytest.raises(NotebookConfigurationError, match=message):
        load_notebook_runtime_settings(_root(tmp_path, env_document=document))


def test_connection_failure_never_discloses_driver_text_or_password(tmp_path: Path) -> None:
    settings = load_notebook_database_settings(_root(tmp_path, env_document=_valid_env()))

    def connector(**kwargs: object) -> None:
        raise RuntimeError(f"driver leaked {kwargs['password']}")

    with (
        pytest.raises(NotebookDatabaseError) as captured,
        notebook_database_connection(settings, connector=connector),
    ):
        pass

    assert _PASSWORD not in str(captured.value)
    assert "driver leaked" not in str(captured.value)


def test_checked_in_env_example_is_placeholder_only_and_real_env_is_ignored() -> None:
    root = Path(__file__).parents[1]
    example = (root / ".env.example").read_text()
    keys = {
        line.partition("=")[0] for line in example.splitlines() if line and not line.startswith("#")
    }

    assert keys == {
        "GDS_NOTEBOOK_POSTGRES_HOST",
        "GDS_NOTEBOOK_POSTGRES_PORT",
        "GDS_NOTEBOOK_POSTGRES_DATABASE",
        "GDS_NOTEBOOK_POSTGRES_USER",
        "GDS_NOTEBOOK_POSTGRES_PASSWORD",
        "GDS_NOTEBOOK_POSTGRES_SSLMODE",
        "GDS_NOTEBOOK_POSTGRES_CONNECT_TIMEOUT_SECONDS",
        "GDS_NOTEBOOK_POSTGRES_STATEMENT_TIMEOUT_SECONDS",
        "GDS_NOTEBOOK_WORKFLOW_LEASE_SECONDS",
        "GDS_NOTEBOOK_WORKFLOW_HEARTBEAT_SECONDS",
        "GDS_NOTEBOOK_AGENT_TIMEOUT_SECONDS",
        "GDS_NOTEBOOK_FOUNDRY_OPENAI_BASE_URL",
        "GDS_NOTEBOOK_FOUNDRY_API_KEY",
        "GDS_NOTEBOOK_FOUNDRY_PRICING_JSON",
    }
    assert "GDS_NOTEBOOK_POSTGRES_USER=gds_notebook_runtime" in example
    assert "<notebook-runtime-password>" in example
    assert not any(
        forbidden in example
        for forbidden in (
            "GDS_NOTEBOOK_TENANT_ID",
            "MODEL_ID",
            "PRINCIPAL_ID",
            "ROLE",
            "TOKEN",
            "DATABASE_URL",
            "POSTGRES_DSN",
        )
    )
    gitignore = (root.parent / ".gitignore").read_text()
    assert "**/.env" in gitignore
    assert "!**/.env.example" in gitignore
    assert not (root / ".env").exists()


@pytest.mark.parametrize("authentication", ["api_key", "entra"])
def test_foundry_configuration_uses_shared_validation_without_environment_or_repr_leaks(
    tmp_path: Path, monkeypatch, authentication: str
) -> None:
    import os

    from gds_workbench_api.integrations.agents.configuration import AgentRuntimeConfiguration

    secret = "fixture-provider-secret-kept-private"
    extra = "GDS_NOTEBOOK_FOUNDRY_OPENAI_BASE_URL=https://fixture.openai.azure.com/openai/v1/\n"
    if authentication == "api_key":
        extra += f"GDS_NOTEBOOK_FOUNDRY_API_KEY={secret}\n"
    else:
        extra += (
            "GDS_NOTEBOOK_FOUNDRY_ENTRA_TENANT_ID=22345678-1234-4234-8234-123456789abc\n"
            "GDS_NOTEBOOK_FOUNDRY_CLIENT_ID=32345678-1234-4234-8234-123456789abc\n"
            f"GDS_NOTEBOOK_FOUNDRY_CLIENT_SECRET={secret}\n"
        )
    monkeypatch.setenv("GDS_WEB_FOUNDRY_API_KEY", "unrelated-process-setting")
    before = dict(os.environ)
    settings = load_notebook_runtime_settings(_root(tmp_path, env_document=_valid_env() + extra))

    assert isinstance(settings.agent_runtime, AgentRuntimeConfiguration)
    assert settings.agent_runtime.mode == "remote"
    assert settings.agent_runtime.timeout_seconds == 240
    assert all(
        connection.provider_code == "microsoft_foundry"
        for connection in settings.agent_runtime.connections
    )
    connection = settings.agent_runtime.connections[0]
    if authentication == "api_key":
        assert connection.foundry_api_key.get_secret_value() == secret
        assert connection.foundry_client_credentials is None
    else:
        assert connection.foundry_client_credentials.client_secret.get_secret_value() == secret
        assert connection.foundry_api_key is None
    assert secret not in repr(settings)
    assert secret not in repr(settings.agent_runtime)
    assert dict(os.environ) == before


@pytest.mark.parametrize(
    "extra",
    [
        "GDS_NOTEBOOK_FOUNDRY_API_KEY=fixture-private-value\n",
        "GDS_NOTEBOOK_FOUNDRY_OPENAI_BASE_URL=https://fixture.openai.azure.com/openai/v1/\n",
        "GDS_NOTEBOOK_FOUNDRY_OPENAI_BASE_URL=https://invalid.example/openai/v1/\nGDS_NOTEBOOK_FOUNDRY_API_KEY=fixture-private-value\n",
        "GDS_NOTEBOOK_FOUNDRY_OPENAI_BASE_URL=https://fixture.openai.azure.com/openai/v1/\nGDS_NOTEBOOK_FOUNDRY_CLIENT_SECRET=fixture-private-value\n",
        "GDS_NOTEBOOK_FOUNDRY_OPENAI_BASE_URL=https://fixture.openai.azure.com/openai/v1/\nGDS_NOTEBOOK_FOUNDRY_API_KEY=fixture-private-value\nGDS_NOTEBOOK_FOUNDRY_CLIENT_ID=32345678-1234-4234-8234-123456789abc\n",
        "GDS_NOTEBOOK_FOUNDRY_OPENAI_BASE_URL=https://fixture.openai.azure.com/openai/v1/\nGDS_NOTEBOOK_FOUNDRY_API_KEY="
        + "é" * 2049
        + "\n",
    ],
)
def test_invalid_foundry_configuration_is_bounded_and_redacted(tmp_path: Path, extra: str) -> None:
    with pytest.raises(NotebookConfigurationError, match="Foundry configuration") as caught:
        load_notebook_runtime_settings(_root(tmp_path, env_document=_valid_env() + extra))
    assert "fixture-private-value" not in str(caught.value)
    assert "invalid.example" not in str(caught.value)
    assert "é" not in str(caught.value)


def test_foundry_is_optional_for_database_and_deterministic_commands(tmp_path: Path) -> None:
    settings = load_notebook_runtime_settings(_root(tmp_path, env_document=_valid_env()))
    assert settings.agent_runtime is None


def test_notebook_pricing_uses_shared_validation_without_process_environment(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import os

    pricing = {
        "foundry-primary": {
            "basis": "Fixture USD schedule",
            "input_usd_per_million": "1.23456789",
            "cached_input_usd_per_million": "0.25",
            "cache_write_input_usd_per_million": "2",
            "output_usd_per_million": "4",
            "valid_from": "2026-01-01T00:00:00Z",
            "valid_until": "2027-01-01T00:00:00Z",
            "max_input_tokens": 100000,
        }
    }
    monkeypatch.setenv("GDS_WEB_FOUNDRY_PRICING_JSON", "ignored invalid process configuration")
    before = dict(os.environ)
    document = (
        _valid_env()
        + "GDS_NOTEBOOK_FOUNDRY_OPENAI_BASE_URL=https://fixture.openai.azure.com/openai/v1/\n"
        + "GDS_NOTEBOOK_FOUNDRY_API_KEY=fixture-private-value\n"
        + "GDS_NOTEBOOK_FOUNDRY_PRICING_JSON="
        + json.dumps(pricing)
        + "\n"
    )
    settings = load_notebook_runtime_settings(_root(tmp_path, env_document=document))
    assert settings.agent_runtime is not None
    connection = next(
        item for item in settings.agent_runtime.connections if item.model_code == "foundry-primary"
    )
    assert connection.pricing is not None
    assert connection.pricing.input_usd_per_million == Decimal("1.23456789")
    assert connection.pricing.max_input_tokens == 100000
    assert connection.pricing.valid_until is not None
    assert connection.pricing.valid_until.utcoffset().total_seconds() == 0
    assert all(
        item.pricing is None
        for item in settings.agent_runtime.connections
        if item.model_code != "foundry-primary"
    )
    assert dict(os.environ) == before


@pytest.mark.parametrize("pricing", ["not valid JSON", '{"unregistered-model":{}}'])
def test_invalid_notebook_pricing_returns_safe_configuration_error(
    tmp_path: Path,
    pricing: str,
) -> None:
    document = (
        _valid_env()
        + "GDS_NOTEBOOK_FOUNDRY_OPENAI_BASE_URL=https://fixture.openai.azure.com/openai/v1/\n"
        + "GDS_NOTEBOOK_FOUNDRY_API_KEY=fixture-private-value\n"
        + "GDS_NOTEBOOK_FOUNDRY_PRICING_JSON="
        + pricing
        + "\n"
    )
    with pytest.raises(NotebookConfigurationError, match="Optional pricing") as caught:
        load_notebook_runtime_settings(_root(tmp_path, env_document=document))
    assert pricing not in str(caught.value)
    assert "fixture-private-value" not in str(caught.value)
