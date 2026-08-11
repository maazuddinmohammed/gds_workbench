from __future__ import annotations

from uuid import UUID

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
        "GDS_METADATA_SNAPSHOT_STORAGE_ACCOUNT_URL": ("https://snapshot.blob.core.windows.net"),
        "GDS_METADATA_SNAPSHOT_STORAGE_CONTAINER": "snapshots",
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
    with pytest.raises(ConfigurationError, match="exceed the database connection budget"):
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


def test_metadata_snapshot_settings_use_bounded_defaults() -> None:
    settings = RuntimeSettings.from_environment(settings_values())

    assert (
        settings.metadata_snapshot_storage_account_url == "https://snapshot.blob.core.windows.net"
    )
    assert settings.metadata_snapshot_storage_container == "snapshots"
    assert settings.metadata_snapshot_download_ttl_seconds == 900
    assert settings.metadata_snapshot_retention_hours == 24
    assert settings.metadata_snapshot_max_archive_bytes == 268435456
    assert settings.metadata_snapshot_managed_identity_client_id is None


@pytest.mark.parametrize(
    "account_url",
    [
        "http://snapshot.blob.core.windows.net",
        "https://user@snapshot.blob.core.windows.net",
        "https://snapshot.blob.core.windows.net/container",
        "https://snapshot.blob.core.windows.net?sig=secret",
    ],
)
def test_metadata_snapshot_account_url_rejects_non_root_urls(account_url: str) -> None:
    with pytest.raises(ConfigurationError, match="HTTPS account root"):
        RuntimeSettings.from_environment(
            settings_values(GDS_METADATA_SNAPSHOT_STORAGE_ACCOUNT_URL=account_url)
        )


@pytest.mark.parametrize("container", ["AB", "Uppercase", "bad--name", "-bad-name"])
def test_metadata_snapshot_container_uses_azure_naming_rules(container: str) -> None:
    with pytest.raises(ConfigurationError, match="valid container name"):
        RuntimeSettings.from_environment(
            settings_values(GDS_METADATA_SNAPSHOT_STORAGE_CONTAINER=container)
        )


def test_metadata_snapshot_numeric_bounds_and_client_id() -> None:
    client_id = "11111111-1111-1111-1111-111111111111"
    settings = RuntimeSettings.from_environment(
        settings_values(
            GDS_METADATA_SNAPSHOT_DOWNLOAD_TTL_SECONDS="60",
            GDS_METADATA_SNAPSHOT_RETENTION_HOURS="168",
            GDS_METADATA_SNAPSHOT_MAX_ARCHIVE_BYTES="1073741824",
            GDS_METADATA_SNAPSHOT_MANAGED_IDENTITY_CLIENT_ID=client_id,
        )
    )

    assert settings.metadata_snapshot_download_ttl_seconds == 60
    assert settings.metadata_snapshot_retention_hours == 168
    assert settings.metadata_snapshot_max_archive_bytes == 1073741824
    assert settings.metadata_snapshot_managed_identity_client_id == UUID(client_id)

    with pytest.raises(ConfigurationError, match="between 60 and 3600"):
        RuntimeSettings.from_environment(
            settings_values(GDS_METADATA_SNAPSHOT_DOWNLOAD_TTL_SECONDS="59")
        )
    with pytest.raises(ConfigurationError, match="must be a UUID"):
        RuntimeSettings.from_environment(
            settings_values(GDS_METADATA_SNAPSHOT_MANAGED_IDENTITY_CLIENT_ID="invalid")
        )
