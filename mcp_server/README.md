# GDS ETL Workbench MCP scaffold

This is the Azure App Service code root. It contains one read-only MCP tool,
`list_tenants`, plus `/health/live` and `/health/ready`.

## Boundaries

- `adapters/`: Easy Auth and MCP/HTTP translation.
- `catalog/`: `list_tenants` use case.
- `domain/`: role/capability policy and safe errors.
- `infrastructure/`: PostgreSQL pool and SQL.
- `contracts/`: strict public request/result models.
- Tests live outside this deployable folder in `../tests/mcp/`.

Production trusts only Azure Easy Auth's bounded `X-MS-CLIENT-PRINCIPAL`
envelope. The request never supplies Principal IDs, Tenant IDs, or roles.
PostgreSQL resolves the active Principal and effective Tenant access.

`GDS_AUTH_MODE=dev` skips authentication and Tenant authorization and lists all
active Tenants. Configuration rejects this mode when
`GDS_ENVIRONMENT=production`.

## Local run

1. Copy `.env.example` to an untracked `.env`.
2. Supply a database DSN and a random cursor key of at least 32 bytes.
3. Export those settings into the shell. The app deliberately does not load
   `.env` files.
4. Run:

```bash
uv sync --project mcp_server --frozen
cd mcp_server
./startup.sh
```

Connect an MCP client to `http://localhost:8000/mcp`.

## Tests

```bash
uv run --project mcp_server ruff format --check mcp_server tests/mcp
uv run --project mcp_server ruff check mcp_server tests/mcp
uv run --project mcp_server pyright
uv run --project mcp_server pytest tests/mcp
```

Tests use typed fakes and never read `.env` or connect to an existing database.
A later database integration suite must create its own disposable PostgreSQL 16
container under the repository's database safety rules.

## Azure ZIP shape

Build the deterministic runtime-only ZIP:

```bash
uv run --project mcp_server python mcp_server/build_zip.py
```

The ZIP places `app.py`, `startup.sh`, `requirements.txt`, and
`BUILD_MANIFEST.json` at its root. The builder includes the complete
`gds_etl_workbench/` runtime package and excludes `.env`, `.env.example`, tests,
`.venv`, SQL, caches, and documentation. It refuses to overwrite an existing
artifact.

Azure App Service must use Python 3.12, build automation
(`SCM_DO_BUILD_DURING_DEPLOYMENT=1`), and startup command `startup.sh`. Configure
Easy Auth to require authentication, reject unauthenticated requests with 401,
accept only the intended Entra tenant/audience, and emit delegated scope
`workbench.access`. Configure the Entra access-token optional claim `idtyp`.
Health paths stay anonymous. The database login must have exactly one direct
membership: `gds_app_write`; the pool activates that `NOINHERIT` role.

Startup never applies DDL and the application exposes no database mutation.
