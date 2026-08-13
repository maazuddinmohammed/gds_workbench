"""Application composition for local execution and Azure App Service."""

from __future__ import annotations

from collections.abc import Mapping

from mcp.server.transport_security import TransportSecuritySettings
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import JSONResponse, Response
from starlette.routing import Route

from gds_etl_workbench.adapters.auth.identity import IdentityProvider
from gds_etl_workbench.adapters.auth.middleware import ProtectedMCPMiddleware
from gds_etl_workbench.adapters.mcp.server import create_mcp_server
from gds_etl_workbench.configuration import (
    ConfigurationError,
    Environment,
    RuntimeSettings,
)
from gds_etl_workbench.infrastructure.postgres import Database, PostgresDatabase
from gds_etl_workbench.tools.snapshots.metadata.storage import MetadataSnapshotStore


def create_application(
    settings: RuntimeSettings,
    database: Database | None = None,
    metadata_snapshot_store: MetadataSnapshotStore | None = None,
) -> Starlette:
    runtime_database = database or PostgresDatabase(
        dsn=settings.database_dsn,
        pool_min=settings.pool_min,
        pool_max=settings.pool_max,
        pool_timeout_seconds=settings.pool_timeout_seconds,
        require_runtime_role=settings.environment is Environment.PRODUCTION,
        expected_schema_version=settings.schema_version,
    )
    identity_provider = IdentityProvider(settings.auth_mode)
    server = create_mcp_server(
        settings,
        runtime_database,
        identity_provider,
        metadata_snapshot_store,
    )
    transport_security = TransportSecuritySettings(
        allowed_hosts=list(settings.allowed_hosts),
        allowed_origins=[],
    )
    application = server.streamable_http_app(
        json_response=True,
        stateless_http=True,
        max_request_body_size=1024 * 1024,
        transport_security=transport_security,
    )
    application.add_middleware(
        ProtectedMCPMiddleware,
        identity_provider=identity_provider,
        require_https=settings.require_https,
    )
    return application


def create_application_from_environment(values: Mapping[str, str] | None = None) -> Starlette:
    try:
        settings = RuntimeSettings.from_environment(values)
    except ConfigurationError:
        return _configuration_error_application()
    return create_application(settings)


def _configuration_error_application() -> Starlette:
    async def live(_request: Request) -> Response:
        return JSONResponse(
            {"status": "live"},
            headers={"Cache-Control": "no-store"},
        )

    async def unavailable(_request: Request) -> Response:
        return JSONResponse(
            {
                "status": "not_ready",
                "error": {
                    "code": "dependency_unavailable",
                    "message": "Runtime configuration is unavailable.",
                    "retryable": False,
                },
            },
            status_code=503,
            headers={"Cache-Control": "no-store"},
        )

    return Starlette(
        routes=[
            Route("/health/live", live, methods=["GET"]),
            Route("/health/ready", unavailable, methods=["GET"]),
            Route("/mcp", unavailable, methods=["GET", "POST", "DELETE"]),
        ]
    )
