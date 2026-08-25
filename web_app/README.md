# GDS Workbench web application

The supported production deployment is one Azure Databricks App:

```text
Databricks-authenticated browser
  -> FastAPI serves React and /api/* on one origin
  -> embedded durable workflow worker
  -> existing PostgreSQL and governed Databricks connections
  -> Databricks Model Serving through the app service principal
```

This deploys the web application only. The MCP server remains separate, keeps
its Azure authentication, and is not started or changed by the Databricks App.
The deployment performs no database DDL or migration.

## Security boundaries

- Databricks Apps OAuth and app `CAN_USE` protect the app URL.
- The backend resolves each user from the forwarded access token through
  Databricks `current_user.me()`.
- Existing PostgreSQL Principal, Tenant, role, Tenant Lock, ownership, revision,
  and idempotency rules remain authoritative.
- The app service principal receives only `CAN_QUERY` on the attached Model
  Serving endpoint. Users do not receive model endpoint access.
- Secrets enter the app only through Databricks App resource references.
- Existing GDS Databricks SQL connections and MCP authentication are unchanged.

## Run safely on a local computer

Requirements: Docker Desktop or Docker Engine with Compose.

From the repository root:

```bash
python3 web_app/local/run.py
```

Open <http://127.0.0.1:8080>. Stop with `Ctrl-C`.

The runner creates random local credentials and a fresh PostgreSQL 18 container,
loads only local fixtures, uses local identity plus fake Agent and Databricks
adapters, and disposes the database on exit. It does not call Azure,
Databricks, Model Serving, MCP, or a persistent database.

Optional loopback ports:

```bash
python3 web_app/local/run.py --frontend-port 9080 --api-port 9000
```

## Verify a release locally

Backend checks require Python 3.14 and `uv`. Frontend checks require Node 22.16
through 22.x and npm.

```bash
uv sync --frozen
uv run --project web_app/backend python -m pytest -c web_app/backend/pyproject.toml tests/web_backend
uv run --project web_app/backend python -m pytest -c web_app/backend/pyproject.toml tests/web_packaging
uv run --project web_app/backend ruff check web_app/backend/gds_workbench_api tests/web_backend tests/web_packaging
uv run --project web_app/backend pyright --project web_app/backend
npm ci
npm run check
```

Docker remains available for the disposable local stack. Production Databricks
deployment uploads source and pinned lock files; it does not deploy a container
image or Azure Container App.

## Deployment files

| File | Role |
|---|---|
| [`databricks.yml`](../databricks.yml) | App, user permission, secret resources, Model Serving resource, and deployment targets. |
| [`app.yaml`](../app.yaml) | Starts the combined FastAPI and worker process and binds runtime resources. |
| [`pyproject.toml`](../pyproject.toml) and [`uv.lock`](../uv.lock) | Root Python application dependencies. |
| [`package.json`](../package.json) and [`package-lock.json`](../package-lock.json) | Root React build and pinned Node dependencies. |

Use [`DEPLOYMENT_GUIDE.md`](DEPLOYMENT_GUIDE.md) for prerequisites, authentication,
resource permissions, variables, exact operator commands, production acceptance,
the Foundry-default data compatibility gate, and rollback.
