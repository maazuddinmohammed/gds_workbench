from pathlib import Path
from uuid import UUID

import pytest
from gds_etl_workbench.configuration import ConfigurationError

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
                "postgresql://fixture_user:fixture_password@db.example/workbench"
                "?sslmode=verify-full"
            ),
            "GDS_WEB_CURSOR_SIGNING_KEY": "production-only-key-32-bytes-long",
            "GDS_WEB_DATABRICKS_ENVIRONMENT_CODE": "PRODUCTION",
            "GDS_WEB_DATABRICKS_EXECUTION_MODE": "remote",
            "GDS_WEB_AGENT_EXECUTION_MODE": "remote",
            "GDS_WEB_DATABRICKS_MODEL_ENDPOINT": "production-agent-endpoint",
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
    assert settings.agent_runtime.connections[0].model_endpoint == (
        "production-agent-endpoint"
    )
    assert settings.static_directory == Path("web_app/frontend/dist")
    assert settings.databricks_host == "https://fixture.azuredatabricks.net"
    assert settings.databricks_app_name == "gds-workbench"
    assert settings.databricks_workspace_id == 123456789


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

    assert str(captured.value) == "production database DSN requires sslmode=verify-full"
    assert "top-secret" not in str(captured.value)


def test_remote_agent_settings_use_one_databricks_model_endpoint() -> None:
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
            "GDS_WEB_DATABRICKS_MODEL_ENDPOINT": "production-agent-endpoint",
            "GDS_WEB_AGENT_TIMEOUT_SECONDS": "90",
        }
    )

    assert settings.agent_runtime.mode == "remote"
    assert settings.agent_runtime.timeout_seconds == 90
    assert settings.agent_runtime.connections[0].provider_code == "databricks"
    assert settings.agent_runtime.connections[0].model_endpoint == (
        "production-agent-endpoint"
    )


def test_remote_agent_settings_require_a_databricks_model_endpoint() -> None:
    values = {
        "GDS_WEB_ENVIRONMENT": "local",
        "GDS_WEB_DATABASE_DSN": (
            "postgresql://fixture_user:fixture_password@fixture.invalid/workbench"
        ),
        "GDS_WEB_CURSOR_SIGNING_KEY": "development-only-key-32-bytes-long",
        "GDS_WEB_DATABRICKS_ENVIRONMENT_CODE": "TEST",
        "GDS_WEB_LOCAL_ENTRA_TENANT_ID": "11111111-1111-1111-1111-111111111111",
        "GDS_WEB_LOCAL_PRINCIPAL_OBJECT_ID": "22222222-2222-2222-2222-222222222222",
        "GDS_WEB_AGENT_EXECUTION_MODE": "remote",
    }

    with pytest.raises(ConfigurationError) as captured:
        RuntimeSettings.from_environment(values)

    assert str(captured.value) == (
        "remote agent execution requires GDS_WEB_DATABRICKS_MODEL_ENDPOINT"
    )


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
            "postgresql://fixture.invalid/workbench?sslmode=verify-full"
        ),
        "GDS_WEB_STATIC_DIR": "web_app/frontend/dist",
        "GDS_WEB_DATABRICKS_EXECUTION_MODE": "fake",
        "GDS_WEB_ENTRA_TENANT_ID": "11111111-1111-1111-1111-111111111111",
    }
    production_values.pop("GDS_WEB_LOCAL_ENTRA_TENANT_ID")
    production_values.pop("GDS_WEB_LOCAL_PRINCIPAL_OBJECT_ID")
    with pytest.raises(ConfigurationError, match="available only locally"):
        RuntimeSettings.from_environment(production_values)
