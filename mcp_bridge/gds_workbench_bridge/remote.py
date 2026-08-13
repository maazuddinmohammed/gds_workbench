"""Authenticated client boundary for the remote MCP server."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, cast
from urllib.parse import urlsplit, urlunsplit
from uuid import UUID

import httpx2
import mcp.types as types
from mcp import Client
from mcp.client.streamable_http import streamable_http_client

from .configuration import BridgeConfigurationError, BridgeSettings


@dataclass(frozen=True, slots=True)
class OAuthMetadata:
    tenant_id: UUID
    scope: str


class AccessTokenProvider(Protocol):
    async def get_token(self, metadata: OAuthMetadata) -> str: ...

    async def close(self) -> None: ...


class AuthenticatedRemoteMcpGateway:
    """Discover remote authorization, obtain a token, and forward MCP tools."""

    def __init__(
        self,
        settings: BridgeSettings,
        token_provider: AccessTokenProvider,
        *,
        http_transport: httpx2.AsyncBaseTransport | None = None,
    ) -> None:
        self._settings = settings
        self._token_provider = token_provider
        self._http_transport = http_transport
        self._oauth_metadata: OAuthMetadata | None = None

    async def list_tools(
        self,
        params: types.PaginatedRequestParams | None,
    ) -> types.ListToolsResult:
        metadata = await self._get_oauth_metadata()
        token = await self._token_provider.get_token(metadata)
        async with httpx2.AsyncClient(
            headers={"Authorization": f"Bearer {token}"},
            timeout=120,
            follow_redirects=False,
            transport=self._http_transport,
        ) as http_client:
            transport = streamable_http_client(
                self._settings.remote_url,
                http_client=http_client,
                terminate_on_close=False,
            )
            async with Client(transport, read_timeout_seconds=120) as client:
                return await client.session.list_tools(params=params)

    async def call_tool(
        self,
        params: types.CallToolRequestParams,
    ) -> types.CallToolResult | types.InputRequiredResult:
        metadata = await self._get_oauth_metadata()
        token = await self._token_provider.get_token(metadata)
        async with httpx2.AsyncClient(
            headers={"Authorization": f"Bearer {token}"},
            timeout=120,
            follow_redirects=False,
            transport=self._http_transport,
        ) as http_client:
            transport = streamable_http_client(
                self._settings.remote_url,
                http_client=http_client,
                terminate_on_close=False,
            )
            async with Client(transport, read_timeout_seconds=120) as client:
                return await client.session.call_tool(
                    params.name,
                    params.arguments,
                    input_responses=params.input_responses,
                    request_state=params.request_state,
                    meta=params.meta,
                    allow_input_required=True,
                )

    async def close(self) -> None:
        await self._token_provider.close()

    async def _get_oauth_metadata(self) -> OAuthMetadata:
        if self._oauth_metadata is not None:
            return self._oauth_metadata

        remote = urlsplit(self._settings.remote_url)
        metadata_url = urlunsplit(
            (
                remote.scheme,
                remote.netloc,
                "/.well-known/oauth-protected-resource/mcp",
                "",
                "",
            )
        )
        async with httpx2.AsyncClient(
            timeout=10,
            follow_redirects=False,
            transport=self._http_transport,
        ) as http_client:
            response = await http_client.get(metadata_url)
            response.raise_for_status()
            raw_payload = cast(object, response.json())

        if not isinstance(raw_payload, dict):
            raise BridgeConfigurationError("remote OAuth metadata is invalid")
        payload = cast(dict[str, object], raw_payload)
        resource = payload.get("resource")
        authorization_servers = payload.get("authorization_servers")
        scopes = payload.get("scopes_supported")
        bearer_methods = payload.get("bearer_methods_supported")
        expected_scope = f"{self._settings.remote_url}/workbench.access"
        if (
            resource != self._settings.remote_url
            or not isinstance(authorization_servers, list)
            or not isinstance(scopes, list)
            or not isinstance(bearer_methods, list)
        ):
            raise BridgeConfigurationError("remote OAuth metadata is incompatible")
        authorization_server_items = cast(list[object], authorization_servers)
        scope_items = cast(list[object], scopes)
        bearer_method_items = cast(list[object], bearer_methods)
        authorization_server_values = [
            item for item in authorization_server_items if isinstance(item, str)
        ]
        scope_values = [item for item in scope_items if isinstance(item, str)]
        bearer_method_values = [
            item for item in bearer_method_items if isinstance(item, str)
        ]
        if (
            len(authorization_server_values) != 1
            or len(authorization_server_values) != len(authorization_server_items)
            or len(scope_values) != len(scope_items)
            or expected_scope not in scope_values
            or len(bearer_method_values) != len(bearer_method_items)
            or "header" not in bearer_method_values
        ):
            raise BridgeConfigurationError("remote OAuth metadata is incompatible")

        authority = urlsplit(authorization_server_values[0])
        authority_parts = authority.path.strip("/").split("/")
        if (
            authority.scheme != "https"
            or authority.hostname != "login.microsoftonline.com"
            or authority.username is not None
            or authority.password is not None
            or authority.query
            or authority.fragment
            or len(authority_parts) != 2
            or authority_parts[1] != "v2.0"
        ):
            raise BridgeConfigurationError("remote OAuth authority is invalid")
        try:
            tenant_id = UUID(authority_parts[0])
        except ValueError as exc:
            raise BridgeConfigurationError("remote OAuth tenant is invalid") from exc
        if tenant_id.int == 0:
            raise BridgeConfigurationError("remote OAuth tenant is invalid")

        self._oauth_metadata = OAuthMetadata(tenant_id=tenant_id, scope=expected_scope)
        return self._oauth_metadata
