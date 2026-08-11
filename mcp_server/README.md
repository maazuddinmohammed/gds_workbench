# GDS ETL Workbench MCP scaffold

This is the Azure App Service code root. It contains one read-only MCP tool,
`list_tenants`, plus `/health/live` and `/health/ready`.

## Boundaries

- `adapters/`: Easy Auth, MCP server composition, and centralized tool-call audit.
- `tools/`: vertical tool modules. Each module keeps its MCP binding, contracts,
  authorization flow, pagination, and SQL together.
- `application/`: shared authorization boundary and signed pagination cursor.
- `domain/`: role and Tool Policy vocabulary plus safe errors.
- `infrastructure/`: shared PostgreSQL pool, readiness, read transactions, and
  bounded append-only audit inserts.
- Tests live outside this deployable folder in `../tests/mcp/`.

Production trusts only Azure Easy Auth's bounded `X-MS-CLIENT-PRINCIPAL`
envelope. The request never supplies Principal IDs, Tenant IDs, or roles.
PostgreSQL resolves the active Principal and effective Tenant access.

Every completed tool call by an active resolved Principal appends one bounded
row to `mcp.tool_call_log`. Tool modules allowlist their own safe input
summary. Raw arguments, cursors, prompts, output, rows, tokens, and exceptions
are not logged.

Humans require delegated scope `workbench.access`. Workloads require application
permission `workbench.workflow` and an active registered service Principal with
the server-owned Super Admin flag.

`GDS_AUTH_MODE=dev` skips Entra authentication and Tenant role/visibility checks,
uses the synthetic display name `Local Developer`, and lists all active Tenants.
Configuration accepts this mode only with `GDS_ENVIRONMENT=local`. Tenant Lock,
revision, audit, and business invariants remain production behavior for future
write tools.

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

Tests never read `.env` or connect to an existing database. Database tests reject
connection environment, create random credentials and a per-run sentinel in a
disposable loopback PostgreSQL 16 container, install the canonical SQL once, and
dispose only that verified container.

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
and accept only the intended Entra tenant/audience. Human tokens need delegated
scope `workbench.access`; workload tokens need application permission
`workbench.workflow`. Configure the Entra access-token optional claim `idtyp`.
Health paths stay anonymous. The database login must have exactly one direct
membership: `gds_app_write`; the pool activates that `NOINHERIT` role.

Startup never applies DDL. The only background database mutation is bounded,
audited expiration of stale Tenant Locks. No Tenant Lock MCP tool is registered
in this scaffold.
