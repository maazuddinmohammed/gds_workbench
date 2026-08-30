from pathlib import Path
from uuid import UUID

import certifi
import pytest
from gds_etl_workbench.configuration import ConfigurationError
from psycopg.conninfo import conninfo_to_dict

from gds_workbench_api.capabilities import load_default_agent_capabilities
from gds_workbench_api.configuration import Environment, RuntimeSettings
from gds_workbench_api.integrations.agents.configuration import (
    AgentRuntimeConfiguration,
)


def test_local_settings_are_explicit_and_hide_the_database_dsn() -> None:
    settings = RuntimeSettings.from_environment(
        {
            "GDS_WEB_ENVIRONMENT": "local",
            "GDS_WEB_DATABASE_DSN": (
                "postgresql://fixture_user:fixture_password@fixture.invalid/workbench"
            ),
            "GDS_WEB_CURSOR_SIGNING_KEY": "development-only-key-32-bytes-long",
            "GDS_WEB_DATABRICKS_ENVIRONMENT_CODE": "TEST",
            "GDS_WEB_LOCAL_ENTRA_TENANT_ID": "11111111-1111-1111-1111-111111111111",
            "GDS_WEB_LOCAL_PRINCIPAL_OBJECT_ID": "22222222-2222-2222-2222-222222222222",
        }
    )

    assert settings.environment is Environment.LOCAL
    assert settings.entra_tenant_id == UUID("11111111-1111-1111-1111-111111111111")
    assert settings.local_principal_object_id == UUID(
        "22222222-2222-2222-2222-222222222222"
    )
    assert settings.databricks_environment_code == "TEST"
    assert settings.databricks_execution_mode == "fake"
    assert settings.static_directory is None
    assert settings.cursor_signing_key == b"development-only-key-32-bytes-long"
    assert settings.agent_runtime.mode == "fake"
    assert settings.agent_runtime.connections == ()
    assert settings.workflow_execution.lease_duration_seconds == 30
    assert "fixture_password" not in repr(settings)
    assert "development-only-key" not in repr(settings)


def test_runtime_settings_accepts_worker_timing_overrides() -> None:
    settings = RuntimeSettings.from_environment(
        {
            "GDS_WEB_ENVIRONMENT": "local",
            "GDS_WEB_DATABASE_DSN": "postgresql://fixture.invalid/workbench",
            "GDS_WEB_CURSOR_SIGNING_KEY": "development-only-key-32-bytes-long",
            "GDS_WEB_DATABRICKS_ENVIRONMENT_CODE": "TEST",
            "GDS_WEB_LOCAL_ENTRA_TENANT_ID": "11111111-1111-1111-1111-111111111111",
            "GDS_WEB_LOCAL_PRINCIPAL_OBJECT_ID": "22222222-2222-2222-2222-222222222222",
            "GDS_WEB_WORKFLOW_LEASE_SECONDS": "45",
            "GDS_WEB_WORKFLOW_HEARTBEAT_SECONDS": "12",
        }
    )

    assert settings.workflow_execution.lease_duration_seconds == 45
    assert settings.workflow_execution.heartbeat_interval_seconds == 12


def test_complete_databricks_app_environment_builds_production_settings() -> None:
    settings = RuntimeSettings.from_environment(
        {
            "GDS_WEB_ENVIRONMENT": "production",
            "GDS_WEB_DATABASE_DSN": (
                "postgresql://gds_web_runtime:fixture_password@db.example/workbench"
                "?sslmode=verify-full&sslrootcert=system"
            ),
            "GDS_WEB_CURSOR_SIGNING_KEY": "production-only-key-32-bytes-long",
            "GDS_WEB_DATABRICKS_ENVIRONMENT_CODE": "PRODUCTION",
            "GDS_WEB_DATABRICKS_EXECUTION_MODE": "remote",
            "GDS_WEB_AGENT_EXECUTION_MODE": "remote",
            "GDS_WEB_ENTRA_TENANT_ID": "11111111-1111-1111-1111-111111111111",
            "GDS_WEB_STATIC_DIR": "web_app/frontend/dist",
            "DATABRICKS_HOST": "https://fixture.azuredatabricks.net",
            "DATABRICKS_APP_NAME": "gds-workbench",
            "DATABRICKS_WORKSPACE_ID": "123456789",
        }
    )

    assert settings.environment is Environment.PRODUCTION
    assert settings.databricks_execution_mode == "remote"
    assert settings.agent_runtime.mode == "remote"
    assert settings.agent_runtime.connections[0].model_endpoint == "databricks-gpt-oss-120b"
    assert settings.static_directory == Path("web_app/frontend/dist")
    assert settings.databricks_host == "https://fixture.azuredatabricks.net"
    assert settings.databricks_app_name == "gds-workbench"
    assert settings.databricks_workspace_id == 123456789
    assert conninfo_to_dict(settings.database_dsn)["sslrootcert"] == certifi.where()


def test_remote_agent_configuration_binds_multiple_registered_deployments() -> None:
    registry = load_default_agent_capabilities()
    primary = next(
        model for model in registry.models if model.code == "databricks-primary"
    )
    secondary = primary.model_copy(
        update={
            "code": "databricks-secondary",
            "name": "Operator-verified secondary Databricks deployment",
            "deployment_name": "secondary-endpoint",
        }
    )

    configuration = AgentRuntimeConfiguration.from_environment(
        {
            "GDS_WEB_AGENT_EXECUTION_MODE": "remote",
        },
        production=True,
        capabilities=registry.model_copy(
            update={"models": (*registry.models, secondary)}
        ),
    )

    assert [
        (connection.provider_code, connection.model_code, connection.model_endpoint)
        for connection in configuration.connections
    ] == [
        ("databricks", "databricks-primary", "databricks-gpt-oss-120b"),
        ("databricks", "databricks-claude-opus-5", "databricks-claude-opus-5"),
        ("databricks", "databricks-secondary", "secondary-endpoint"),
    ]


@pytest.mark.parametrize(
    ("legacy_key", "legacy_value"),
    (
        ("GDS_WEB_DATABRICKS_MODEL_ENDPOINT", "legacy-endpoint"),
        ("GDS_WEB_FOUNDRY_MODEL_DEPLOYMENT", "legacy-deployment"),
        ("GDS_WEB_AGENT_PROVIDER", "databricks"),
    ),
)
def test_runtime_settings_reject_legacy_model_routing_variables(
    legacy_key: str,
    legacy_value: str,
) -> None:
    values = {
        "GDS_WEB_ENVIRONMENT": "local",
        "GDS_WEB_DATABASE_DSN": "postgresql://fixture.invalid/workbench",
        "GDS_WEB_CURSOR_SIGNING_KEY": "development-only-key-32-bytes-long",
        "GDS_WEB_DATABRICKS_ENVIRONMENT_CODE": "TEST",
        "GDS_WEB_LOCAL_ENTRA_TENANT_ID": "11111111-1111-1111-1111-111111111111",
        "GDS_WEB_LOCAL_PRINCIPAL_OBJECT_ID": "22222222-2222-2222-2222-222222222222",
        "GDS_WEB_AGENT_EXECUTION_MODE": "remote",
    }

    settings = RuntimeSettings.from_environment(values)

    assert settings.agent_runtime.connections[0].model_code == "databricks-primary"
    with pytest.raises(ConfigurationError, match="unsupported GDS web setting"):
        RuntimeSettings.from_environment(
            {
                **values,
                legacy_key: legacy_value,
            }
        )


def test_databricks_app_environment_normalizes_a_bare_workspace_host() -> None:
    settings = RuntimeSettings.from_environment(
        {
            "GDS_WEB_ENVIRONMENT": "production",
            "GDS_WEB_DATABASE_DSN": (
                "postgresql://gds_web_runtime:fixture_password@db.example/workbench"
                "?sslmode=verify-full"
            ),
            "GDS_WEB_CURSOR_SIGNING_KEY": "production-only-key-32-bytes-long",
            "GDS_WEB_DATABRICKS_ENVIRONMENT_CODE": "PRODUCTION",
            "GDS_WEB_DATABRICKS_EXECUTION_MODE": "remote",
            "GDS_WEB_AGENT_EXECUTION_MODE": "remote",
            "GDS_WEB_ENTRA_TENANT_ID": "11111111-1111-1111-1111-111111111111",
            "GDS_WEB_STATIC_DIR": "web_app/frontend/dist",
            "DATABRICKS_HOST": "fixture.azuredatabricks.net",
            "DATABRICKS_APP_NAME": "gds-workbench",
            "DATABRICKS_WORKSPACE_ID": "123456789",
        }
    )

    assert settings.databricks_host == "https://fixture.azuredatabricks.net"


def test_production_accepts_require_tls_fallback_without_a_root_certificate() -> None:
    settings = RuntimeSettings.from_environment(
        {
            "GDS_WEB_ENVIRONMENT": "production",
            "GDS_WEB_DATABASE_DSN": (
                "postgresql://gds_web_runtime:fixture_password@db.example/workbench"
                "?sslmode=require&sslrootcert=system"
            ),
            "GDS_WEB_CURSOR_SIGNING_KEY": "production-only-key-32-bytes-long",
            "GDS_WEB_DATABRICKS_ENVIRONMENT_CODE": "DEVELOPMENT",
            "GDS_WEB_DATABRICKS_EXECUTION_MODE": "remote",
            "GDS_WEB_AGENT_EXECUTION_MODE": "remote",
            "GDS_WEB_ENTRA_TENANT_ID": "11111111-1111-1111-1111-111111111111",
            "GDS_WEB_STATIC_DIR": "web_app/frontend/dist",
            "DATABRICKS_HOST": "https://fixture.azuredatabricks.net",
            "DATABRICKS_APP_NAME": "gds-workbench",
            "DATABRICKS_WORKSPACE_ID": "123456789",
        }
    )

    dsn = conninfo_to_dict(settings.database_dsn)
    assert dsn["sslmode"] == "require"
    assert "sslrootcert" not in dsn


def test_production_requires_a_verified_postgres_connection() -> None:
    with pytest.raises(ConfigurationError) as captured:
        RuntimeSettings.from_environment(
            {
                "GDS_WEB_ENVIRONMENT": "production",
                "GDS_WEB_DATABASE_DSN": (
                    "postgresql://fixture_user:top-secret@db.example/workbench"
                ),
                "GDS_WEB_CURSOR_SIGNING_KEY": "production-only-key-32-bytes-long",
                "GDS_WEB_DATABRICKS_ENVIRONMENT_CODE": "PRODUCTION",
                "GDS_WEB_ENTRA_TENANT_ID": "11111111-1111-1111-1111-111111111111",
                "GDS_WEB_STATIC_DIR": "web_app/frontend/dist",
            }
        )

    assert str(captured.value) == (
        "production database DSN requires sslmode=require or verify-full"
    )
    assert "top-secret" not in str(captured.value)


def test_production_requires_the_exact_web_runtime_database_login() -> None:
    with pytest.raises(ConfigurationError) as captured:
        RuntimeSettings.from_environment(
            {
                "GDS_WEB_ENVIRONMENT": "production",
                "GDS_WEB_DATABASE_DSN": (
                    "postgresql://gds_app_write:top-secret@db.example/workbench"
                    "?sslmode=verify-full"
                ),
                "GDS_WEB_CURSOR_SIGNING_KEY": "production-only-key-32-bytes-long",
                "GDS_WEB_DATABRICKS_ENVIRONMENT_CODE": "PRODUCTION",
                "GDS_WEB_ENTRA_TENANT_ID": ("11111111-1111-1111-1111-111111111111"),
                "GDS_WEB_STATIC_DIR": "web_app/frontend/dist",
            }
        )

    assert str(captured.value) == (
        "production database DSN requires user=gds_web_runtime"
    )
    assert "top-secret" not in str(captured.value)


def test_remote_agent_settings_use_registered_databricks_model_deployment() -> None:
    settings = RuntimeSettings.from_environment(
        {
            "GDS_WEB_ENVIRONMENT": "local",
            "GDS_WEB_DATABASE_DSN": (
                "postgresql://fixture_user:fixture_password@fixture.invalid/workbench"
            ),
            "GDS_WEB_CURSOR_SIGNING_KEY": "development-only-key-32-bytes-long",
            "GDS_WEB_DATABRICKS_ENVIRONMENT_CODE": "TEST",
            "GDS_WEB_LOCAL_ENTRA_TENANT_ID": "11111111-1111-1111-1111-111111111111",
            "GDS_WEB_LOCAL_PRINCIPAL_OBJECT_ID": "22222222-2222-2222-2222-222222222222",
            "GDS_WEB_AGENT_EXECUTION_MODE": "remote",
            "GDS_WEB_AGENT_TIMEOUT_SECONDS": "90",
        }
    )

    assert settings.agent_runtime.mode == "remote"
    assert settings.agent_runtime.timeout_seconds == 90
    assert settings.agent_runtime.connections[0].provider_code == "databricks"
    assert settings.agent_runtime.connections[0].model_code == "databricks-primary"
    assert settings.agent_runtime.connections[0].model_endpoint == "databricks-gpt-oss-120b"


def test_remote_agent_settings_support_direct_foundry_authentication() -> None:
    settings = RuntimeSettings.from_environment(
        {
            "GDS_WEB_ENVIRONMENT": "local",
            "GDS_WEB_DATABASE_DSN": "postgresql://fixture.invalid/workbench",
            "GDS_WEB_CURSOR_SIGNING_KEY": "development-only-key-32-bytes-long",
            "GDS_WEB_DATABRICKS_ENVIRONMENT_CODE": "TEST",
            "GDS_WEB_LOCAL_ENTRA_TENANT_ID": "11111111-1111-1111-1111-111111111111",
            "GDS_WEB_LOCAL_PRINCIPAL_OBJECT_ID": "22222222-2222-2222-2222-222222222222",
            "GDS_WEB_AGENT_EXECUTION_MODE": "remote",
            "GDS_WEB_FOUNDRY_OPENAI_BASE_URL": (
                "https://fixture.openai.azure.com/openai/v1/"
            ),
            "GDS_WEB_FOUNDRY_ENTRA_TENANT_ID": ("33333333-3333-3333-3333-333333333333"),
            "GDS_WEB_FOUNDRY_CLIENT_ID": ("44444444-4444-4444-4444-444444444444"),
            "GDS_WEB_FOUNDRY_CLIENT_SECRET": "never-log-this-foundry-secret",
        }
    )

    connection = next(
        item
        for item in settings.agent_runtime.connections
        if item.provider_code == "microsoft_foundry"
    )
    assert {item.provider_code for item in settings.agent_runtime.connections} == {
        "databricks",
        "microsoft_foundry",
    }
    assert connection.provider_code == "microsoft_foundry"
    assert connection.model_code == "foundry-primary"
    assert connection.model_endpoint == "gpt-5.6-sol"
    assert connection.openai_base_url == "https://fixture.openai.azure.com/openai/v1/"
    assert connection.token_scope == "https://cognitiveservices.azure.com/.default"
    assert connection.foundry_client_credentials is not None
    assert connection.foundry_client_credentials.tenant_id == UUID(
        "33333333-3333-3333-3333-333333333333"
    )
    assert connection.foundry_client_credentials.client_id == UUID(
        "44444444-4444-4444-4444-444444444444"
    )
    assert (
        connection.foundry_client_credentials.client_secret.get_secret_value()
        == "never-log-this-foundry-secret"
    )
    assert "never-log-this-foundry-secret" not in repr(connection)
    assert "never-log-this-foundry-secret" not in connection.model_dump_json()
    assert "never-log-this-foundry-secret" not in repr(settings)


def test_remote_agent_settings_support_foundry_api_key_authentication() -> None:
    settings = RuntimeSettings.from_environment(
        {
            "GDS_WEB_ENVIRONMENT": "local",
            "GDS_WEB_DATABASE_DSN": "postgresql://fixture.invalid/workbench",
            "GDS_WEB_CURSOR_SIGNING_KEY": "development-only-key-32-bytes-long",
            "GDS_WEB_DATABRICKS_ENVIRONMENT_CODE": "TEST",
            "GDS_WEB_LOCAL_ENTRA_TENANT_ID": "11111111-1111-1111-1111-111111111111",
            "GDS_WEB_LOCAL_PRINCIPAL_OBJECT_ID": "22222222-2222-2222-2222-222222222222",
            "GDS_WEB_AGENT_EXECUTION_MODE": "remote",
            "GDS_WEB_FOUNDRY_OPENAI_BASE_URL": (
                "https://fixture.openai.azure.com/openai/v1/"
            ),
            "GDS_WEB_FOUNDRY_API_KEY": "never-log-this-foundry-api-key",
        }
    )

    connection = next(
        item
        for item in settings.agent_runtime.connections
        if item.provider_code == "microsoft_foundry"
    )
    assert connection.token_scope is None
    assert connection.foundry_client_credentials is None
    assert connection.foundry_api_key is not None
    assert (
        connection.foundry_api_key.get_secret_value()
        == "never-log-this-foundry-api-key"
    )
    assert "never-log-this-foundry-api-key" not in repr(connection)
    assert "never-log-this-foundry-api-key" not in connection.model_dump_json()
    assert "never-log-this-foundry-api-key" not in repr(settings)


def test_remote_foundry_rejects_mixed_authentication_methods() -> None:
    with pytest.raises(ConfigurationError) as captured:
        RuntimeSettings.from_environment(
            {
                "GDS_WEB_ENVIRONMENT": "local",
                "GDS_WEB_DATABASE_DSN": "postgresql://fixture.invalid/workbench",
                "GDS_WEB_CURSOR_SIGNING_KEY": "development-only-key-32-bytes-long",
                "GDS_WEB_DATABRICKS_ENVIRONMENT_CODE": "TEST",
                "GDS_WEB_LOCAL_ENTRA_TENANT_ID": (
                    "11111111-1111-1111-1111-111111111111"
                ),
                "GDS_WEB_LOCAL_PRINCIPAL_OBJECT_ID": (
                    "22222222-2222-2222-2222-222222222222"
                ),
                "GDS_WEB_AGENT_EXECUTION_MODE": "remote",
                "GDS_WEB_FOUNDRY_OPENAI_BASE_URL": (
                    "https://fixture.openai.azure.com/openai/v1/"
                ),
                "GDS_WEB_FOUNDRY_API_KEY": "never-log-this-foundry-api-key",
                "GDS_WEB_FOUNDRY_ENTRA_TENANT_ID": (
                    "33333333-3333-3333-3333-333333333333"
                ),
                "GDS_WEB_FOUNDRY_CLIENT_ID": ("44444444-4444-4444-4444-444444444444"),
                "GDS_WEB_FOUNDRY_CLIENT_SECRET": "never-log-this-foundry-secret",
            }
        )

    assert str(captured.value) == (
        "Foundry agent execution accepts exactly one authentication method: "
        "API key or complete Entra client credentials"
    )
    assert "never-log-this-foundry-api-key" not in repr(captured.value)
    assert "never-log-this-foundry-secret" not in repr(captured.value)


@pytest.mark.parametrize(
    ("foundry_values", "expected_message"),
    (
        (
            {
                "GDS_WEB_FOUNDRY_OPENAI_BASE_URL": (
                    "https://fixture.openai.azure.com/openai/v1/"
                ),
            },
            "requires either an API key or complete Entra tenant, client ID, "
            "and client secret",
        ),
        (
            {"GDS_WEB_FOUNDRY_API_KEY": "fixture-foundry-api-key"},
            "requires its OpenAI base URL",
        ),
        (
            {
                "GDS_WEB_FOUNDRY_OPENAI_BASE_URL": (
                    "https://fixture.openai.azure.com/openai/v1/"
                ),
                "GDS_WEB_FOUNDRY_ENTRA_TENANT_ID": (
                    "33333333-3333-3333-3333-333333333333"
                ),
            },
            "requires either an API key or complete Entra tenant, client ID, "
            "and client secret",
        ),
        (
            {
                "GDS_WEB_FOUNDRY_OPENAI_BASE_URL": (
                    "https://fixture.openai.azure.com/openai/v1/"
                ),
                "GDS_WEB_FOUNDRY_CLIENT_ID": ("44444444-4444-4444-4444-444444444444"),
            },
            "requires either an API key or complete Entra tenant, client ID, "
            "and client secret",
        ),
        (
            {
                "GDS_WEB_FOUNDRY_OPENAI_BASE_URL": (
                    "https://fixture.openai.azure.com/openai/v1/"
                ),
                "GDS_WEB_FOUNDRY_CLIENT_SECRET": "fixture-foundry-secret",
            },
            "requires either an API key or complete Entra tenant, client ID, "
            "and client secret",
        ),
        (
            {
                "GDS_WEB_FOUNDRY_OPENAI_BASE_URL": (
                    "https://fixture.openai.azure.com/openai/v1/"
                ),
                "GDS_WEB_FOUNDRY_ENTRA_TENANT_ID": (
                    "33333333-3333-3333-3333-333333333333"
                ),
                "GDS_WEB_FOUNDRY_CLIENT_ID": ("44444444-4444-4444-4444-444444444444"),
            },
            "requires either an API key or complete Entra tenant, client ID, "
            "and client secret",
        ),
        (
            {
                "GDS_WEB_FOUNDRY_OPENAI_BASE_URL": (
                    "https://fixture.openai.azure.com/openai/v1/"
                ),
                "GDS_WEB_FOUNDRY_ENTRA_TENANT_ID": (
                    "33333333-3333-3333-3333-333333333333"
                ),
                "GDS_WEB_FOUNDRY_CLIENT_SECRET": "fixture-foundry-secret",
            },
            "requires either an API key or complete Entra tenant, client ID, "
            "and client secret",
        ),
        (
            {
                "GDS_WEB_FOUNDRY_OPENAI_BASE_URL": (
                    "https://fixture.openai.azure.com/openai/v1/"
                ),
                "GDS_WEB_FOUNDRY_CLIENT_ID": ("44444444-4444-4444-4444-444444444444"),
                "GDS_WEB_FOUNDRY_CLIENT_SECRET": "fixture-foundry-secret",
            },
            "requires either an API key or complete Entra tenant, client ID, "
            "and client secret",
        ),
    ),
)
def test_remote_foundry_rejects_every_partial_configuration(
    foundry_values: dict[str, str],
    expected_message: str,
) -> None:
    with pytest.raises(ConfigurationError) as captured:
        RuntimeSettings.from_environment(
            {
                "GDS_WEB_ENVIRONMENT": "local",
                "GDS_WEB_DATABASE_DSN": "postgresql://fixture.invalid/workbench",
                "GDS_WEB_CURSOR_SIGNING_KEY": "development-only-key-32-bytes-long",
                "GDS_WEB_DATABRICKS_ENVIRONMENT_CODE": "TEST",
                "GDS_WEB_LOCAL_ENTRA_TENANT_ID": (
                    "11111111-1111-1111-1111-111111111111"
                ),
                "GDS_WEB_LOCAL_PRINCIPAL_OBJECT_ID": (
                    "22222222-2222-2222-2222-222222222222"
                ),
                "GDS_WEB_AGENT_EXECUTION_MODE": "remote",
                **foundry_values,
            }
        )

    assert expected_message in str(captured.value)


@pytest.mark.parametrize(
    "base_url",
    (
        "https://fixture.services.ai.azure.com/api/projects/production/openai/v1/",
        "https://fixture.services.ai.azure.com/openai/v1/",
        "https://fixture.openai.azure.com:444/openai/v1/",
        "https://fixture.openai.azure.com:invalid/openai/v1/",
    ),
)
def test_remote_foundry_rejects_non_resource_chat_completion_routes(
    base_url: str,
) -> None:
    with pytest.raises(ConfigurationError, match="resource HTTPS /openai/v1"):
        RuntimeSettings.from_environment(
            {
                "GDS_WEB_ENVIRONMENT": "local",
                "GDS_WEB_DATABASE_DSN": "postgresql://fixture.invalid/workbench",
                "GDS_WEB_CURSOR_SIGNING_KEY": "development-only-key-32-bytes-long",
                "GDS_WEB_DATABRICKS_ENVIRONMENT_CODE": "TEST",
                "GDS_WEB_LOCAL_ENTRA_TENANT_ID": "11111111-1111-1111-1111-111111111111",
                "GDS_WEB_LOCAL_PRINCIPAL_OBJECT_ID": "22222222-2222-2222-2222-222222222222",
                "GDS_WEB_AGENT_EXECUTION_MODE": "remote",
                "GDS_WEB_FOUNDRY_OPENAI_BASE_URL": base_url,
                "GDS_WEB_FOUNDRY_ENTRA_TENANT_ID": (
                    "33333333-3333-3333-3333-333333333333"
                ),
                "GDS_WEB_FOUNDRY_CLIENT_ID": "44444444-4444-4444-4444-444444444444",
                "GDS_WEB_FOUNDRY_CLIENT_SECRET": "never-log-this-foundry-secret",
            }
        )


def test_remote_foundry_accepts_the_services_resource_openai_route() -> None:
    settings = RuntimeSettings.from_environment(
        {
            "GDS_WEB_ENVIRONMENT": "local",
            "GDS_WEB_DATABASE_DSN": "postgresql://fixture.invalid/workbench",
            "GDS_WEB_CURSOR_SIGNING_KEY": "development-only-key-32-bytes-long",
            "GDS_WEB_DATABRICKS_ENVIRONMENT_CODE": "TEST",
            "GDS_WEB_LOCAL_ENTRA_TENANT_ID": "11111111-1111-1111-1111-111111111111",
            "GDS_WEB_LOCAL_PRINCIPAL_OBJECT_ID": "22222222-2222-2222-2222-222222222222",
            "GDS_WEB_AGENT_EXECUTION_MODE": "remote",
            "GDS_WEB_FOUNDRY_OPENAI_BASE_URL": (
                "https://fixture.services.ai.azure.com/openai/v1/"
            ),
            "GDS_WEB_FOUNDRY_API_KEY": "never-log-this-foundry-api-key",
        }
    )

    foundry_connection = next(
        item
        for item in settings.agent_runtime.connections
        if item.provider_code == "microsoft_foundry"
    )
    assert foundry_connection.openai_base_url == (
        "https://fixture.services.ai.azure.com/openai/v1/"
    )


def test_remote_agent_provider_rejects_legacy_model_endpoint_settings() -> None:
    with pytest.raises(ConfigurationError, match="unsupported GDS web setting"):
        RuntimeSettings.from_environment(
            {
                "GDS_WEB_ENVIRONMENT": "local",
                "GDS_WEB_DATABASE_DSN": "postgresql://fixture.invalid/workbench",
                "GDS_WEB_CURSOR_SIGNING_KEY": "development-only-key-32-bytes-long",
                "GDS_WEB_DATABRICKS_ENVIRONMENT_CODE": "TEST",
                "GDS_WEB_LOCAL_ENTRA_TENANT_ID": (
                    "11111111-1111-1111-1111-111111111111"
                ),
                "GDS_WEB_LOCAL_PRINCIPAL_OBJECT_ID": (
                    "22222222-2222-2222-2222-222222222222"
                ),
                "GDS_WEB_AGENT_EXECUTION_MODE": "remote",
                "GDS_WEB_DATABRICKS_MODEL_ENDPOINT": "must-not-route-through-databricks",
                "GDS_WEB_FOUNDRY_OPENAI_BASE_URL": (
                    "https://fixture.openai.azure.com/openai/v1/"
                ),
            }
        )


def test_production_rejects_fake_agent_execution() -> None:
    with pytest.raises(ConfigurationError) as captured:
        RuntimeSettings.from_environment(
            {
                "GDS_WEB_ENVIRONMENT": "production",
                "GDS_WEB_DATABASE_DSN": (
                    "postgresql://gds_web_runtime:top-secret@db.example/workbench"
                    "?sslmode=verify-full"
                ),
                "GDS_WEB_CURSOR_SIGNING_KEY": "production-only-key-32-bytes-long",
                "GDS_WEB_DATABRICKS_ENVIRONMENT_CODE": "PRODUCTION",
                "GDS_WEB_ENTRA_TENANT_ID": "11111111-1111-1111-1111-111111111111",
                "GDS_WEB_STATIC_DIR": "web_app/frontend/dist",
                "GDS_WEB_AGENT_EXECUTION_MODE": "fake",
                "DATABRICKS_HOST": "https://fixture.azuredatabricks.net",
                "DATABRICKS_APP_NAME": "gds-workbench",
                "DATABRICKS_WORKSPACE_ID": "123456789",
            }
        )

    assert str(captured.value) == "fake agent execution is available only locally"


def test_databricks_execution_mode_is_explicit_and_production_safe() -> None:
    local_values = {
        "GDS_WEB_ENVIRONMENT": "local",
        "GDS_WEB_DATABASE_DSN": "postgresql://fixture.invalid/workbench",
        "GDS_WEB_CURSOR_SIGNING_KEY": "development-only-key-32-bytes-long",
        "GDS_WEB_DATABRICKS_ENVIRONMENT_CODE": "TEST",
        "GDS_WEB_LOCAL_ENTRA_TENANT_ID": "11111111-1111-1111-1111-111111111111",
        "GDS_WEB_LOCAL_PRINCIPAL_OBJECT_ID": "22222222-2222-2222-2222-222222222222",
    }
    remote = RuntimeSettings.from_environment(
        {**local_values, "GDS_WEB_DATABRICKS_EXECUTION_MODE": "remote"}
    )
    assert remote.databricks_execution_mode == "remote"

    with pytest.raises(ConfigurationError, match="must be fake or remote"):
        RuntimeSettings.from_environment(
            {**local_values, "GDS_WEB_DATABRICKS_EXECUTION_MODE": "automatic"}
        )

    production_values = {
        **local_values,
        "GDS_WEB_ENVIRONMENT": "production",
        "GDS_WEB_DATABASE_DSN": (
            "postgresql://gds_web_runtime@fixture.invalid/workbench?sslmode=verify-full"
        ),
        "GDS_WEB_STATIC_DIR": "web_app/frontend/dist",
        "GDS_WEB_DATABRICKS_EXECUTION_MODE": "fake",
        "GDS_WEB_ENTRA_TENANT_ID": "11111111-1111-1111-1111-111111111111",
    }
    production_values.pop("GDS_WEB_LOCAL_ENTRA_TENANT_ID")
    production_values.pop("GDS_WEB_LOCAL_PRINCIPAL_OBJECT_ID")
    with pytest.raises(ConfigurationError, match="available only locally"):
        RuntimeSettings.from_environment(production_values)
