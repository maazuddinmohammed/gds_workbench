# GDS Workbench web application

The supported production deployment is one Azure Databricks App:

```text
Databricks-authenticated browser
  -> FastAPI serves React and /api/* on one origin
  -> embedded durable workflow worker
  -> existing PostgreSQL and governed Databricks connections
  -> OpenAI Agents SDK and Microsoft Foundry model deployments
```

This deploys the web application only. The MCP server remains separate, keeps
its Azure authentication, and is not started or changed by the Databricks App.
The deployment performs no database DDL or migration. PostgreSQL must already
be at this release's schema revision, including the approved tenant-wide
Workflow Run exclusivity contract and the Code Generation and Validation Model
Sections; see the deployment guide before rollout.

## Security boundaries

- Databricks Apps OAuth and app `CAN_USE` protect the app URL.
- The backend resolves each user from the forwarded access token through
  Databricks `current_user.me()`.
- Existing PostgreSQL Principal, Tenant, role, Tenant Lock, ownership, revision,
  and idempotency rules remain authoritative.
- Agent workflows use Microsoft Foundry through the OpenAI Agents SDK. The
  checked-in App uses an API-key secret resource; explicit Entra application
  credentials are also supported. Users receive neither credential.
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
Databricks, Foundry, MCP, or a persistent database.

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
| [`databricks.yml`](../databricks.yml) | Databricks App, user permission, six read-only secret resources including Foundry configuration, and targets. |
| [`app.yaml`](../app.yaml) | Starts the combined process and binds PostgreSQL, Databricks SQL, and Foundry resources. |
| [`pyproject.toml`](../pyproject.toml) and [`uv.lock`](../uv.lock) | Root Python application dependencies. |
| [`package.json`](../package.json) and [`package-lock.json`](../package-lock.json) | Root React build and pinned Node dependencies. |
| [`databricks_notebooks/README.md`](../databricks_notebooks/README.md) | Independent source upload, PostgreSQL configuration, widgets, workflow order, retries, and manual Apply gates for interactive notebooks. |

Use [`DEPLOYMENT_GUIDE.md`](DEPLOYMENT_GUIDE.md) for prerequisites, authentication,
resource permissions, Foundry authentication, exact operator commands, Model
default compatibility, production acceptance, and rollback.
