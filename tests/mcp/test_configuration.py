from __future__ import annotations

import pytest

from gds_etl_workbench.configuration import (
    AuthMode,
    ConfigurationError,
    RuntimeSettings,
)


def settings_values(**overrides: str) -> dict[str, str]:
    values = {
        "GDS_ENVIRONMENT": "local",
        "GDS_AUTH_MODE": "dev",
        "GDS_DATABASE_DSN": "postgresql://app@db.example.invalid/workbench",
        "GDS_CURSOR_SIGNING_KEY": "development-only-key-32-bytes-long",
        "GDS_MCP_ALLOWED_HOSTS": "localhost,127.0.0.1",
        "GDS_REQUIRE_HTTPS": "false",
        "GDS_SCHEMA_VERSION": "1.0.0",
        "GDS_DATABASE_POOL_MIN": "1",
        "GDS_DATABASE_POOL_MAX": "5",
        "GDS_DATABASE_POOL_TIMEOUT_SECONDS": "10",
        "GDS_DATABASE_CONNECTION_BUDGET": "100",
        "GDS_DATABASE_CONNECTION_HEADROOM": "20",
        "GDS_REQUEST_TIMEOUT_SECONDS": "120",
        "WEB_CONCURRENCY": "2",
        "PORT": "8000",
    }
    values.update(overrides)
    return values


def test_development_mode_explicitly_disables_authentication() -> None:
    settings = RuntimeSettings.from_environment(settings_values())

    assert settings.auth_mode is AuthMode.DEV
    assert settings.require_https is False


def test_production_rejects_dev_authentication_mode() -> None:
    with pytest.raises(ConfigurationError, match="production requires"):
        RuntimeSettings.from_environment(settings_values(GDS_ENVIRONMENT="production"))


def test_production_requires_verify_full_database_tls() -> None:
    with pytest.raises(ConfigurationError, match="sslmode=verify-full"):
        RuntimeSettings.from_environment(
            settings_values(
                GDS_ENVIRONMENT="production",
                GDS_AUTH_MODE="azure_easy_auth",
                GDS_REQUIRE_HTTPS="true",
            )
        )


def test_pool_arithmetic_fails_closed() -> None:
    with pytest.raises(
        ConfigurationError, match="exceed the database connection budget"
    ):
        RuntimeSettings.from_environment(
            settings_values(
                GDS_DATABASE_POOL_MAX="50",
                GDS_DATABASE_CONNECTION_BUDGET="100",
                GDS_DATABASE_CONNECTION_HEADROOM="20",
            )
        )


def test_secret_values_are_not_in_settings_repr() -> None:
    settings = RuntimeSettings.from_environment(settings_values())

    rendered = repr(settings)
    assert "postgresql://" not in rendered
    assert "development-only-key" not in rendered
