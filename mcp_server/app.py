"""Azure App Service ASGI entrypoint."""

from atlas_mcp.runtime import create_application_from_environment

app = create_application_from_environment()
