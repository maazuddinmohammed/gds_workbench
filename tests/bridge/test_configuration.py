from __future__ import annotations

from uuid import UUID

import pytest

from gds_workbench_bridge.configuration import (
    BridgeConfigurationError,
    BridgeSettings,
)


def valid_environment() -> dict[str, str]:
    return {
        "GDS_BRIDGE_MCP_URL": "https://example.azurewebsites.net/mcp",
        "GDS_BRIDGE_ENTRA_CLIENT_ID": "22222222-2222-2222-2222-222222222222",
    }


def test_settings_accept_remote_endpoint_and_public_client() -> None:
    settings = BridgeSettings.from_environment(valid_environment())

    assert settings.remote_url == "https://example.azurewebsites.net/mcp"
    assert settings.entra_client_id == UUID("22222222-2222-2222-2222-222222222222")
    assert settings.redirect_uri == "http://localhost:8400"


@pytest.mark.parametrize(
    "url",
    [
        "http://example.azurewebsites.net/mcp",
        "https://example.azurewebsites.net/not-mcp",
        "https://user@example.azurewebsites.net/mcp",
    ],
)
def test_settings_reject_unsafe_remote_endpoint(url: str) -> None:
    values = valid_environment()
    values["GDS_BRIDGE_MCP_URL"] = url

    with pytest.raises(BridgeConfigurationError):
        BridgeSettings.from_environment(values)


def test_settings_reject_non_loopback_redirect() -> None:
    values = valid_environment()
    values["GDS_BRIDGE_REDIRECT_URI"] = "https://example.com/callback"

    with pytest.raises(BridgeConfigurationError):
        BridgeSettings.from_environment(values)
