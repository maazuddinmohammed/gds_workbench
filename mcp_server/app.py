"""Azure App Service ASGI entrypoint."""

from gds_etl_workbench.runtime import create_application_from_environment

app = create_application_from_environment()
