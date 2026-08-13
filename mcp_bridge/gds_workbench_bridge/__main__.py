"""Run the local bridge over standard input/output."""

from __future__ import annotations

import asyncio
import sys

from mcp.server.stdio import stdio_server

from .authentication import EntraAccessTokenProvider
from .configuration import BridgeConfigurationError, BridgeSettings
from .remote import AuthenticatedRemoteMcpGateway
from .server import create_bridge_server


async def run() -> None:
    settings = BridgeSettings.from_environment()
    token_provider = EntraAccessTokenProvider(settings)
    remote = AuthenticatedRemoteMcpGateway(settings, token_provider)
    server = create_bridge_server(remote)

    async with stdio_server() as (read_stream, write_stream):
        await server.run(
            read_stream,
            write_stream,
            server.create_initialization_options(),
        )


def main() -> None:
    try:
        asyncio.run(run())
    except BridgeConfigurationError as exc:
        print(f"GDS bridge configuration error: {exc}", file=sys.stderr)
        raise SystemExit(2) from None


if __name__ == "__main__":
    main()
