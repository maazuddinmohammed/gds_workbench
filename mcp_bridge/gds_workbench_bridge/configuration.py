"""Validated configuration for the local bridge process."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from os import environ
from urllib.parse import urlsplit
from uuid import UUID


class BridgeConfigurationError(ValueError):
    """A configuration failure that does not expose sensitive values."""


@dataclass(frozen=True, slots=True)
class BridgeSettings:
    remote_url: str
    entra_client_id: UUID
    redirect_uri: str

    @classmethod
    def from_environment(cls, values: Mapping[str, str] | None = None) -> BridgeSettings:
        source = environ if values is None else values
        remote_url = source.get("GDS_BRIDGE_MCP_URL", "").strip().rstrip("/")
        parsed_remote = urlsplit(remote_url)
        if (
            parsed_remote.scheme != "https"
            or not parsed_remote.hostname
            or parsed_remote.username is not None
            or parsed_remote.password is not None
            or parsed_remote.path != "/mcp"
            or parsed_remote.query
            or parsed_remote.fragment
        ):
            raise BridgeConfigurationError(
                "GDS_BRIDGE_MCP_URL must be an absolute HTTPS /mcp endpoint"
            )

        try:
            entra_client_id = UUID(source.get("GDS_BRIDGE_ENTRA_CLIENT_ID", ""))
        except ValueError as exc:
            raise BridgeConfigurationError(
                "GDS_BRIDGE_ENTRA_CLIENT_ID must be a UUID"
            ) from exc
        if entra_client_id.int == 0:
            raise BridgeConfigurationError(
                "GDS_BRIDGE_ENTRA_CLIENT_ID must be a nonzero UUID"
            )

        redirect_uri = source.get(
            "GDS_BRIDGE_REDIRECT_URI",
            "http://localhost:8400",
        ).strip()
        parsed_redirect = urlsplit(redirect_uri)
        try:
            redirect_port = parsed_redirect.port
        except ValueError as exc:
            raise BridgeConfigurationError("GDS_BRIDGE_REDIRECT_URI is invalid") from exc
        if (
            parsed_redirect.scheme != "http"
            or parsed_redirect.hostname not in {"localhost", "127.0.0.1", "::1"}
            or redirect_port is None
            or parsed_redirect.username is not None
            or parsed_redirect.password is not None
            or parsed_redirect.path not in {"", "/"}
            or parsed_redirect.query
            or parsed_redirect.fragment
        ):
            raise BridgeConfigurationError(
                "GDS_BRIDGE_REDIRECT_URI must be an HTTP loopback URL with a port"
            )

        return cls(
            remote_url=remote_url,
            entra_client_id=entra_client_id,
            redirect_uri=redirect_uri,
        )
