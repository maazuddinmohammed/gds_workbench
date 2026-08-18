# GDS ETL Workbench MCP scaffold

This is the Azure App Service code root. It contains governed read, Databricks
SQL, Tenant Lock, Metadata Change Set, and Model Change Set tools:

- `list_tenants`, `get_tenant_details`, `get_model`, `get_model_scope`;
- `list_objects`, `get_objects`, `get_object_lineage`;
- `list_copy_groups`, `get_copy_group`;
- `list_process_groups`, `get_process_group`; and
- `describe_metadata_dataset`, `get_metadata_snapshot`;
- `execute_databricks_sql`;
- `check_tenant_lock`, `acquire_tenant_lock`, `renew_tenant_lock`,
  `release_tenant_lock`, `override_tenant_lock`; and
- `create_metadata_change_set`, `stage_metadata_change_set`,
  `get_metadata_change_set`, `validate_metadata_change_set`,
  `apply_metadata_change_set`, `archive_metadata_change_set`;
- `get_model_profiling`, `get_model_analysis`, Modeling Assertion, Conceptual,
  Logical, Dimensional, and Mapping reads;
- `describe_model_dataset`, `get_model_snapshot`, `get_model_dbml`; and
- `create_model_change_set`, `stage_model_change_set`,
  `get_model_change_set`, `validate_model_change_set`,
  `apply_model_change_set`, `archive_model_change_set`.

It also contains health routes and private Snapshot storage.

`describe_metadata_dataset` returns a model-friendly column card for one dataset:
meaning, required/nullability state, population guidance, fixed or literal values,
reference value sources, constraints, examples, and the exact shared JSON Schema.
The same guidance is embedded in Metadata Snapshot schema files.

## Boundaries

- `adapters/`: Easy Auth, MCP server composition, and centralized tool-call audit.
- `tools/`: vertical tool modules. Each module keeps its MCP binding, contracts,
  authorization flow, pagination, and SQL together.
- `tools/catalog/`: Object visibility, Object detail, and ingestion-lineage reads.
- `tools/ingestion/`: Tenant-owned Copy Group reads.
- `tools/processing/`: Process Group reads resolved through Tenant Copy Groups.
- `tools/databricks/`: SQL validation, bounded Connector execution, and the
  governed `execute_databricks_sql` MCP binding.
- `tools/tenants/tenant_locks.py`: all five governed Tenant Lock contracts and
  fixed SQL calls in one module.
- `tools/modeling/`: focused, paginated Model reads with shared Logical and
  Dimensional query machinery.
- `tools/change_sets/`: governed Metadata and Model Change Set contracts,
  shared contract/action-review primitives, validation, and atomic materialization.
- `tools/snapshots/`: shared deterministic archive, private storage, and temporary
  build/upload/cleanup orchestration for every Snapshot kind.
- `tools/snapshots/metadata/`: Metadata Snapshot contracts, fixed SQL, archive
  content, and MCP binding.
- `tools/snapshots/model/`: the 19-dataset ID-free Model contract registry,
  schema description, and complete Model Snapshot.
- `tools/snapshots/dbml/`: deterministic conceptual, logical, and dimensional
  DBML projection, ZIP generation, and MCP binding.
- `application/`: shared authorization boundary and signed pagination cursor.
- `domain/`: role and Tool Policy vocabulary, safe errors, and shared ID-free
  metadata/modeling Pydantic records used by snapshots and Change Sets.
- `infrastructure/`: shared PostgreSQL pool, readiness, read transactions,
  governed-function write transactions, and append-only audit inserts.
- Tests live outside this deployable folder in `../tests/mcp/`.

Production trusts only Azure Easy Auth's bounded `X-MS-CLIENT-PRINCIPAL`
envelope. Tool requests supply the target Tenant ID, but never Principal IDs or roles.
PostgreSQL resolves the active Principal and effective Tenant access.

Every completed tool call by an active resolved Principal appends one row to
`mcp.tool_call_log`. Each tool explicitly declares which normal input arguments
may be retained, and those values are copied into `input_metadata`. PostgreSQL
does not impose an application-specific byte ceiling on that JSONB object. The
normal MCP request-body limit remains 1 MiB. Cursors, lock purpose/reason text,
staged physical records, prompts, output, credentials, tokens, connection values,
and exceptions are not logged. The complete SQL submitted to
`execute_databricks_sql` remains the deliberate SQL exception.

Humans require delegated scope `workbench.access`. Workloads require application
permission `workbench.workflow` and an active registered service Principal with
the server-owned Super Admin flag.

`GDS_ENVIRONMENT=local` disables request authentication and maps every request
to one explicitly configured, database-backed `Local Developer` user. That user
must be seeded with `is_super_admin=true`. It can read every Tenant and use all
authorized tools, but Tenant Locks, revisions, validation, audit, and business
invariants still apply. Never expose local mode to an untrusted network.
Production ignores this path and derives Easy Auth, HTTPS, and the public host
allowlist.

## Local run

1. Generate one UUID for `GDS_LOCAL_PRINCIPAL_OBJECT_ID`. Copy
   `database/seed/03_local_super_admin.template.sql` outside the repository,
   replace its three placeholders, and run that copy once as the database
   administrator. Use the same UUID in the seed and application setting.
2. Copy `.env.example` to an untracked `.env`.
3. Supply the canonical `gds_mcp_runtime` database DSN, a random cursor key of
   at least 32 bytes, and the private Azure Blob account URL/container used for
   Metadata Snapshots. The pool activates its `gds_app_write` membership in
   both local and production modes.
4. Export those settings into the shell. The app deliberately does not load
   `.env` files.
5. Run:

```bash
uv sync --project mcp_server --frozen --python 3.14
cd mcp_server
./startup.sh
```

On Windows PowerShell, run this from the repository root after setting the same
environment variables:

```powershell
uv sync --project mcp_server --frozen --python 3.14
uv run --project mcp_server --frozen python -m uvicorn --app-dir mcp_server app:app --host 127.0.0.1 --port 8000
```

`startup.sh` and Gunicorn are for the Linux Azure host. Windows local development
uses Uvicorn directly.

Connect an MCP client to `http://localhost:8000/mcp`.

`GDS_MCP_PUBLIC_URL`, `GDS_ENTRA_TENANT_ID`, and
`GDS_ENTRA_API_CLIENT_ID` publish the MCP OAuth protected-resource metadata.
They are public deployment identifiers and do not need Key Vault. The server
derives the Entra authorization-server URL and the delegated
`workbench.access` scope from them. In local mode, the Tenant ID also forms the
database identity key with `GDS_LOCAL_PRINCIPAL_OBJECT_ID`; the API Client ID is
metadata only because authentication is disabled. Production must omit
`GDS_LOCAL_PRINCIPAL_OBJECT_ID`.

`GDS_DATABRICKS_SQL_MAX_ROWS` configures the returned final-statement rows from
1 through the hard cap of 50; its default is 50.
`GDS_DATABRICKS_SQL_TIMEOUT_SECONDS` configures the statement/socket timeout
from 1 through 600 seconds; its default is 120. Schema version, snapshot bounds,
PostgreSQL pool sizing, connection budget, Gunicorn workers, and request timeout
remain checked-in runtime policy.

`execute_databricks_sql` accepts a positive global `connection_id` and up to 25
semicolon-separated statements. It permits reads and unqualified temporary
views/tables only, rejects DML and persistent DDL, executes the batch on one
Databricks SQL Warehouse session, and returns only the final statement's bounded
result. PostgreSQL supplies the host, HTTP path, and token through one fixed
least-privilege function. Those connection values are never logged. The complete
submitted SQL and its character count are retained in the append-only tool-call
log; callers must never place credentials in SQL.

Call `get_metadata_snapshot` with a positive `tenant_id`. Its small result
contains a 15-minute read-only SAS URL for the exact ZIP, URL expiry time, byte
count, and SHA-256. It never contains snapshot rows or ZIP bytes. Tenant Read is
authorized before the URL is created. Opening the URL downloads directly from
the private Blob container. The SAS URL is returned only in the MCP result and
must not be logged.

Model-focused reads return database IDs for navigation but omit agent-run and
audit columns. Empty filter lists mean all matching Model records.
`get_model` accepts one authorized Tenant ID and returns up to 200 active Model
headers, naming/audit policy templates, revisions, and Model Scope Object counts.
`get_model_scope` accepts one authorized Model ID and returns up to 2,000 active
Scope Objects with expanded Tenant, System, Connection, Object Type, Zone, and
physical Object names. Database IDs remain in this focused navigation result.
`get_model_snapshot` returns only a temporary read-only URL plus ZIP metadata;
its 19 archive datasets are ID-free and use the exact Pydantic records accepted
by Model Change Sets. `get_model_dbml` accepts `full`, `conceptual`, `logical`,
or `dimensional`; each selected layer always has a complete DBML file. When
`include_submodels` is true, logical and dimensional layers also have one file
per active Submodel and a default file only when active Entities are unassigned.
The MCP result contains only the temporary URL and bounded ZIP metadata. Call
`describe_model_dataset` before authoring a dataset.
Each `stage_model_change_set` item replaces that dataset's pending records;
omitted pending datasets remain unchanged. Validate reports the first failed
phase and a bounded action review, including physical Model Scope checks. Apply
revalidates and writes atomically. Stage `model_details` to update the Model name,
description, or naming/audit templates. Stage `model_scope` with `is_active=true`
to add/reactivate an Object or `is_active=false` to archive it; locked Scope rows
cannot be archived. `archive_model_change_set` retains an
abandoned draft as terminal history; it does not delete it.

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

Azure App Service must use Python 3.14, build automation
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
`metadata/`, `model/`, and `dbml/` prefixes at or after the configured retention
period. The application does not create containers, alter roles, or run broad
Blob cleanup.

Startup never applies DDL. Background mutation is limited to bounded, audited
expiration of stale Tenant Locks. Lock tools can mutate locks only through the
governed SQL functions; they cannot directly change the lock tables.
