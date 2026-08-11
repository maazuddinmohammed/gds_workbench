from __future__ import annotations

from uuid import UUID

import pytest

from gds_etl_workbench.configuration import (
    AuthMode,
    ConfigurationError,
    DATABASE_CONNECTION_BUDGET,
    DATABASE_CONNECTION_HEADROOM,
    DATABASE_POOL_MAX,
    WEB_CONCURRENCY,
    RuntimeSettings,
)


def settings_values(**overrides: str) -> dict[str, str]:
    values = {
        "GDS_ENVIRONMENT": "local",
        "GDS_DATABASE_DSN": "postgresql://app@db.example.invalid/workbench",
        "GDS_CURSOR_SIGNING_KEY": "development-only-key-32-bytes-long",
        "GDS_ENTRA_API_CLIENT_ID": "22222222-2222-2222-2222-222222222222",
        "GDS_ENTRA_TENANT_ID": "11111111-1111-1111-1111-111111111111",
        "GDS_MCP_PUBLIC_URL": "https://workbench.example.test/mcp",
        "GDS_METADATA_SNAPSHOT_STORAGE_ACCOUNT_URL": (
            "https://snapshot.blob.core.windows.net"
        ),
        "GDS_METADATA_SNAPSHOT_STORAGE_CONTAINER": "snapshots",
    }
    values.update(overrides)
    return values


def test_development_mode_explicitly_disables_authentication() -> None:
    settings = RuntimeSettings.from_environment(settings_values())

    assert settings.auth_mode is AuthMode.DEV
    assert settings.require_https is False
    assert settings.allowed_hosts == (
        "workbench.example.test",
        "workbench.example.test:*",
        "localhost",
        "localhost:*",
        "127.0.0.1",
        "127.0.0.1:*",
        "[::1]",
        "[::1]:*",
    )


def test_production_derives_easy_auth_https_and_exact_public_host() -> None:
    settings = RuntimeSettings.from_environment(
        settings_values(
            GDS_ENVIRONMENT="production",
            GDS_DATABASE_DSN=(
                "postgresql://app@db.example.invalid/workbench?sslmode=verify-full"
            ),
        )
    )

    assert settings.auth_mode is AuthMode.AZURE_EASY_AUTH
    assert settings.require_https is True
    assert settings.allowed_hosts == (
        "workbench.example.test",
        "workbench.example.test:*",
    )


def test_oauth_discovery_settings_are_explicit_non_secret_configuration() -> None:
    settings = RuntimeSettings.from_environment(settings_values())

    assert settings.mcp_public_url == "https://workbench.example.test/mcp"
    assert settings.entra_tenant_id == UUID("11111111-1111-1111-1111-111111111111")
    assert settings.entra_api_client_id == UUID("22222222-2222-2222-2222-222222222222")


@pytest.mark.parametrize(
    "public_url",
    [
        "https://workbench.example.test",
        "https://workbench.example.test/mcp/extra",
        "https://user@workbench.example.test/mcp",
        "https://workbench.example.test/mcp?tenant=secret",
    ],
)
def test_mcp_public_url_requires_an_absolute_mcp_endpoint(public_url: str) -> None:
    with pytest.raises(ConfigurationError, match="GDS_MCP_PUBLIC_URL"):
        RuntimeSettings.from_environment(settings_values(GDS_MCP_PUBLIC_URL=public_url))


@pytest.mark.parametrize("key", ["GDS_ENTRA_TENANT_ID", "GDS_ENTRA_API_CLIENT_ID"])
def test_entra_identifiers_must_be_uuids(key: str) -> None:
    with pytest.raises(ConfigurationError, match=key):
        RuntimeSettings.from_environment(settings_values(**{key: "invalid"}))


def test_production_requires_verify_full_database_tls() -> None:
    with pytest.raises(ConfigurationError, match="sslmode=verify-full"):
        RuntimeSettings.from_environment(settings_values(GDS_ENVIRONMENT="production"))


def test_production_oauth_discovery_requires_https_public_url() -> None:
    with pytest.raises(ConfigurationError, match="GDS_MCP_PUBLIC_URL must use HTTPS"):
        RuntimeSettings.from_environment(
            settings_values(
                GDS_ENVIRONMENT="production",
                GDS_DATABASE_DSN=(
                    "postgresql://app@db.example.invalid/workbench?sslmode=verify-full"
                ),
                GDS_MCP_PUBLIC_URL="http://workbench.example.test/mcp",
            )
        )


def test_fixed_pool_policy_stays_within_connection_budget() -> None:
    settings = RuntimeSettings.from_environment(settings_values())

    assert settings.pool_min == 1
    assert settings.pool_max == 5
    assert settings.pool_timeout_seconds == 10
    assert WEB_CONCURRENCY * DATABASE_POOL_MAX <= (
        DATABASE_CONNECTION_BUDGET - DATABASE_CONNECTION_HEADROOM
    )


@pytest.mark.parametrize(
    "key",
    [
        "GDS_AUTH_MODE",
        "GDS_DATABASE_CONNECTION_BUDGET",
        "GDS_DATABASE_CONNECTION_HEADROOM",
        "GDS_DATABASE_POOL_MAX",
        "GDS_DATABASE_POOL_MIN",
        "GDS_DATABASE_POOL_TIMEOUT_SECONDS",
        "GDS_MCP_ALLOWED_HOSTS",
        "GDS_METADATA_SNAPSHOT_DOWNLOAD_TTL_SECONDS",
        "GDS_METADATA_SNAPSHOT_MAX_ARCHIVE_BYTES",
        "GDS_METADATA_SNAPSHOT_RETENTION_HOURS",
        "GDS_REQUEST_TIMEOUT_SECONDS",
        "GDS_REQUIRE_HTTPS",
        "GDS_SCHEMA_VERSION",
    ],
)
def test_fixed_policy_cannot_be_overridden_by_environment(key: str) -> None:
    with pytest.raises(ConfigurationError, match=f"unsupported GDS setting: {key}"):
        RuntimeSettings.from_environment(settings_values(**{key: "override"}))


def test_secret_values_are_not_in_settings_repr() -> None:
    settings = RuntimeSettings.from_environment(settings_values())

    rendered = repr(settings)
    assert "postgresql://" not in rendered
    assert "development-only-key" not in rendered


def test_metadata_snapshot_settings_use_bounded_defaults() -> None:
    settings = RuntimeSettings.from_environment(settings_values())

    assert (
        settings.metadata_snapshot_storage_account_url
        == "https://snapshot.blob.core.windows.net"
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


def test_metadata_snapshot_managed_identity_client_id_is_optional_and_validated() -> (
    None
):
    client_id = "11111111-1111-1111-1111-111111111111"
    settings = RuntimeSettings.from_environment(
        settings_values(
            GDS_METADATA_SNAPSHOT_MANAGED_IDENTITY_CLIENT_ID=client_id,
        )
    )

    assert settings.metadata_snapshot_managed_identity_client_id == UUID(client_id)

    with pytest.raises(ConfigurationError, match="must be a UUID"):
        RuntimeSettings.from_environment(
            settings_values(GDS_METADATA_SNAPSHOT_MANAGED_IDENTITY_CLIENT_ID="invalid")
        )
