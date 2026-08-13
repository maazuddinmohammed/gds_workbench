# GDS ETL Workbench MCP scaffold

This is the Azure App Service code root. It contains ten read tools and five
Tenant Lock tools:

- `list_tenants`, `get_tenant_details`;
- `list_objects`, `get_objects`, `get_object_lineage`;
- `list_copy_groups`, `get_copy_group`;
- `list_process_groups`, `get_process_group`; and
- `get_metadata_snapshot`; and
- `check_tenant_lock`, `acquire_tenant_lock`, `renew_tenant_lock`,
  `release_tenant_lock`, `override_tenant_lock`.

It also contains health routes and private Metadata Snapshot storage.

## Boundaries

- `adapters/`: Easy Auth, MCP server composition, and centralized tool-call audit.
- `tools/`: vertical tool modules. Each module keeps its MCP binding, contracts,
  authorization flow, pagination, and SQL together.
- `tools/catalog/`: Object visibility, Object detail, and ingestion-lineage reads.
- `tools/ingestion/`: Tenant-owned Copy Group reads.
- `tools/processing/`: Process Group reads resolved through Tenant Copy Groups.
- `tools/tenants/tenant_locks.py`: all five governed Tenant Lock contracts and
  fixed SQL calls in one module.
- `tools/snapshots/metadata/`: Metadata Snapshot contracts, fixed SQL, archive
  generation, Azure storage, and MCP binding.
- `application/`: shared authorization boundary and signed pagination cursor.
- `domain/`: role and Tool Policy vocabulary, safe errors, and shared ID-free
  metadata Pydantic records used by snapshots and future change sets.
- `infrastructure/`: shared PostgreSQL pool, readiness, read transactions,
  governed-function write transactions, and bounded append-only audit inserts.
- Tests live outside this deployable folder in `../tests/mcp/`.

Production trusts only Azure Easy Auth's bounded `X-MS-CLIENT-PRINCIPAL`
envelope. Tool requests supply the target Tenant ID, but never Principal IDs or roles.
PostgreSQL resolves the active Principal and effective Tenant access.

Every completed tool call by an active resolved Principal appends one bounded
row to `mcp.tool_call_log`. Tool modules allowlist their own safe input
summary. Raw arguments, cursors, prompts, output, rows, tokens, and exceptions
are not logged.

Humans require delegated scope `workbench.access`. Workloads require application
permission `workbench.workflow` and an active registered service Principal with
the server-owned Super Admin flag.

`GDS_ENVIRONMENT=local` derives development authentication, disables the HTTPS
requirement, uses the synthetic display name `Local Developer`, and lists all
active Tenants. Production derives Easy Auth, HTTPS, and the public host
allowlist. Tenant Lock, revision, audit, and business invariants remain
production behavior. Local Development identity cannot own a production lock.

## Local run

1. Copy `.env.example` to an untracked `.env`.
2. Supply a database DSN, a random cursor key of at least 32 bytes, and the
   private Azure Blob account URL/container used for Metadata Snapshots.
3. Export those settings into the shell. The app deliberately does not load
   `.env` files.
4. Run:

```bash
uv sync --project mcp_server --frozen
cd mcp_server
./startup.sh
```

Connect an MCP client to `http://localhost:8000/mcp`.

`GDS_MCP_PUBLIC_URL`, `GDS_ENTRA_TENANT_ID`, and
`GDS_ENTRA_API_CLIENT_ID` publish the MCP OAuth protected-resource metadata.
They are public deployment identifiers and do not need Key Vault. The server
derives the Entra authorization-server URL and the delegated
`workbench.access` scope from them.

Schema version, snapshot bounds, PostgreSQL pool sizing, connection budget,
Gunicorn workers, and request timeout are checked-in runtime policy. They are
not environment overrides.

Call `get_metadata_snapshot` with a positive `tenant_id`. Its small result
contains a 15-minute read-only SAS URL for the exact ZIP, URL expiry time, byte
count, and SHA-256. It never contains snapshot rows or ZIP bytes. Tenant Read is
authorized before the URL is created. Opening the URL downloads directly from
the private Blob container. The SAS URL is returned only in the MCP result and
must not be logged.

## Tests

```bash
uv run --project mcp_server ruff format --check mcp_server tests/mcp
uv run --project mcp_server ruff check mcp_server tests/mcp
uv run --project mcp_server pyright
uv run --project mcp_server pytest tests/mcp
```

Tests never read `.env` or connect to an existing database. Database tests reject
connection environment, create random credentials and a per-run sentinel in a
disposable loopback PostgreSQL 18 container, install the canonical SQL once, and
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
Configure these Easy Auth excluded paths so health and OAuth discovery remain
anonymous:

```text
/health/live
/health/ready
/.well-known/oauth-protected-resource
/.well-known/oauth-protected-resource/mcp
```

`/mcp` remains protected. The database login must have exactly one direct
membership: `gds_app_write`; the pool activates that `NOINHERIT` role.

The configured Blob container must already exist and remain private. Grant the
App Service identity narrowly scoped Blob create/read access and Storage Blob
Delegator at account scope. Configure lifecycle deletion for the code-owned
`metadata/` prefix at or after the configured retention period. The application
does not create containers, alter roles, or run broad Blob cleanup.

Startup never applies DDL. Background mutation is limited to bounded, audited
expiration of stale Tenant Locks. Lock tools can mutate locks only through the
governed SQL functions; they cannot directly change the lock tables.
