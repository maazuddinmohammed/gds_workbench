from uuid import UUID

import pytest
from gds_etl_workbench.configuration import AuthMode, ConfigurationError

from gds_workbench_api.configuration import Environment, RuntimeSettings


def test_local_settings_are_explicit_and_hide_the_database_dsn() -> None:
    settings = RuntimeSettings.from_environment(
        {
            "GDS_WEB_ENVIRONMENT": "local",
            "GDS_WEB_DATABASE_DSN": (
                "postgresql://fixture_user:fixture_password@fixture.invalid/workbench"
            ),
            "GDS_WEB_CURSOR_SIGNING_KEY": "development-only-key-32-bytes-long",
            "GDS_WEB_DATABRICKS_ENVIRONMENT_CODE": "TEST",
            "GDS_WEB_PUBLIC_URL": "http://localhost:8000",
            "GDS_WEB_FRONTEND_ORIGIN": "http://localhost:5173",
            "GDS_WEB_LOCAL_ENTRA_TENANT_ID": "11111111-1111-1111-1111-111111111111",
            "GDS_WEB_LOCAL_PRINCIPAL_OBJECT_ID": "22222222-2222-2222-2222-222222222222",
        }
    )

    assert settings.environment is Environment.LOCAL
    assert settings.auth_mode is AuthMode.DEV
    assert settings.local_entra_tenant_id == UUID("11111111-1111-1111-1111-111111111111")
    assert settings.local_principal_object_id == UUID("22222222-2222-2222-2222-222222222222")
    assert settings.frontend_origin == "http://localhost:5173"
    assert settings.databricks_environment_code == "TEST"
    assert settings.databricks_execution_mode == "fake"
    assert settings.require_https is False
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
            "GDS_WEB_PUBLIC_URL": "http://localhost:8000",
            "GDS_WEB_FRONTEND_ORIGIN": "http://localhost:5173",
            "GDS_WEB_LOCAL_ENTRA_TENANT_ID": "11111111-1111-1111-1111-111111111111",
            "GDS_WEB_LOCAL_PRINCIPAL_OBJECT_ID": "22222222-2222-2222-2222-222222222222",
            "GDS_WEB_WORKFLOW_LEASE_SECONDS": "45",
            "GDS_WEB_WORKFLOW_HEARTBEAT_SECONDS": "12",
        }
    )

    assert settings.workflow_execution.lease_duration_seconds == 45
    assert settings.workflow_execution.heartbeat_interval_seconds == 12


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
                "GDS_WEB_PUBLIC_URL": "https://api.example.test",
                "GDS_WEB_FRONTEND_ORIGIN": "https://workbench.example.test",
            }
        )

    assert str(captured.value) == "production database DSN requires sslmode=verify-full"
    assert "top-secret" not in str(captured.value)


def test_remote_agent_settings_require_complete_https_provider_pairs_and_hide_keys() -> None:
    settings = RuntimeSettings.from_environment(
        {
            "GDS_WEB_ENVIRONMENT": "local",
            "GDS_WEB_DATABASE_DSN": (
                "postgresql://fixture_user:fixture_password@fixture.invalid/workbench"
            ),
            "GDS_WEB_CURSOR_SIGNING_KEY": "development-only-key-32-bytes-long",
            "GDS_WEB_DATABRICKS_ENVIRONMENT_CODE": "TEST",
            "GDS_WEB_PUBLIC_URL": "http://localhost:8000",
            "GDS_WEB_FRONTEND_ORIGIN": "http://localhost:5173",
            "GDS_WEB_LOCAL_ENTRA_TENANT_ID": "11111111-1111-1111-1111-111111111111",
            "GDS_WEB_LOCAL_PRINCIPAL_OBJECT_ID": "22222222-2222-2222-2222-222222222222",
            "GDS_WEB_AGENT_EXECUTION_MODE": "remote",
            "GDS_WEB_FOUNDRY_BASE_URL": "https://foundry.example/openai/v1/",
            "GDS_WEB_FOUNDRY_API_KEY": "provider-key-must-stay-hidden",
            "GDS_WEB_AGENT_TIMEOUT_SECONDS": "90",
        }
    )

    assert settings.agent_runtime.mode == "remote"
    assert settings.agent_runtime.timeout_seconds == 90
    assert [item.provider_code for item in settings.agent_runtime.connections] == [
        "microsoft_foundry"
    ]
    assert "provider-key-must-stay-hidden" not in repr(settings)
    assert "foundry.example" not in repr(settings)


def test_agent_provider_connection_pair_must_be_complete() -> None:
    values = {
        "GDS_WEB_ENVIRONMENT": "local",
        "GDS_WEB_DATABASE_DSN": (
            "postgresql://fixture_user:fixture_password@fixture.invalid/workbench"
        ),
        "GDS_WEB_CURSOR_SIGNING_KEY": "development-only-key-32-bytes-long",
        "GDS_WEB_DATABRICKS_ENVIRONMENT_CODE": "TEST",
        "GDS_WEB_PUBLIC_URL": "http://localhost:8000",
        "GDS_WEB_FRONTEND_ORIGIN": "http://localhost:5173",
        "GDS_WEB_LOCAL_ENTRA_TENANT_ID": "11111111-1111-1111-1111-111111111111",
        "GDS_WEB_LOCAL_PRINCIPAL_OBJECT_ID": "22222222-2222-2222-2222-222222222222",
        "GDS_WEB_AGENT_EXECUTION_MODE": "remote",
        "GDS_WEB_FOUNDRY_BASE_URL": "https://foundry.example/openai/v1/",
    }

    with pytest.raises(ConfigurationError) as captured:
        RuntimeSettings.from_environment(values)

    assert str(captured.value) == ("microsoft_foundry agent provider requires both URL and API key")


def test_production_rejects_fake_agent_execution() -> None:
    with pytest.raises(ConfigurationError) as captured:
        RuntimeSettings.from_environment(
            {
                "GDS_WEB_ENVIRONMENT": "production",
                "GDS_WEB_DATABASE_DSN": (
                    "postgresql://fixture_user:top-secret@db.example/workbench?sslmode=verify-full"
                ),
                "GDS_WEB_CURSOR_SIGNING_KEY": "production-only-key-32-bytes-long",
                "GDS_WEB_DATABRICKS_ENVIRONMENT_CODE": "PRODUCTION",
                "GDS_WEB_PUBLIC_URL": "https://api.example.test",
                "GDS_WEB_FRONTEND_ORIGIN": "https://workbench.example.test",
                "GDS_WEB_AGENT_EXECUTION_MODE": "fake",
            }
        )

    assert str(captured.value) == "fake agent execution is available only locally"


def test_databricks_execution_mode_is_explicit_and_production_safe() -> None:
    local_values = {
        "GDS_WEB_ENVIRONMENT": "local",
        "GDS_WEB_DATABASE_DSN": "postgresql://fixture.invalid/workbench",
        "GDS_WEB_CURSOR_SIGNING_KEY": "development-only-key-32-bytes-long",
        "GDS_WEB_DATABRICKS_ENVIRONMENT_CODE": "TEST",
        "GDS_WEB_PUBLIC_URL": "http://localhost:8000",
        "GDS_WEB_FRONTEND_ORIGIN": "http://localhost:5173",
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
        "GDS_WEB_DATABASE_DSN": ("postgresql://fixture.invalid/workbench?sslmode=verify-full"),
        "GDS_WEB_PUBLIC_URL": "https://api.example.test",
        "GDS_WEB_FRONTEND_ORIGIN": "https://workbench.example.test",
        "GDS_WEB_DATABRICKS_EXECUTION_MODE": "fake",
    }
    production_values.pop("GDS_WEB_LOCAL_ENTRA_TENANT_ID")
    production_values.pop("GDS_WEB_LOCAL_PRINCIPAL_OBJECT_ID")
    with pytest.raises(ConfigurationError, match="available only locally"):
        RuntimeSettings.from_environment(production_values)
