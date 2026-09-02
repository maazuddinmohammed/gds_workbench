# GDS Workbench MCP server

This folder is the Python 3.14 Azure App Service that exposes the governed GDS
MCP surface. The server is stateless. PostgreSQL owns authorization, Tenant
Locks, revision fencing, Change Set validation, idempotency, and audit truth.

## Public MCP surface

The server registers 35 focused tools:

- Tenant and Model navigation: `list_tenants`, `get_tenant_details`,
  `list_models`, `get_model_input_scope`.
- Tenant Locks: `check_tenant_lock`, `acquire_tenant_lock`,
  `renew_tenant_lock`, `release_tenant_lock`, `override_tenant_lock`.
- Metadata Change Sets: create, stage, inspect, validate, apply, archive, plus
  their bounded Stage Batch transport.
- Model Change Sets: create, stage, inspect, validate, apply, archive, plus
  their bounded Stage Batch transport.
- Focused reads: `inspect_metadata`, `read_model_section`.
- Snapshots and contracts: `describe_metadata_dataset`,
  `create_metadata_snapshot`, `describe_model_dataset`, `create_model_snapshot`,
  `export_model_dbml`.
- Governed SQL preflight: `execute_databricks_sql`.

It registers no MCP prompts or resources. The plugin owns user interaction;
server instructions contain only shared safety and dependency rules.

Foundational CRUD, individual graph mutation, direct lock-table writes,
PostgreSQL SQL, file upload, secret reads, and code execution are not exposed.

## Delivery boundaries

- Metadata Change Sets own all physical metadata registration.
- Model Change Sets own Model Input Scope, profiling, analysis, Assertions,
  conceptual/logical/dimensional Models, Model Bindings, Mapping, generated
  Code, and Validation definitions.
- Target physical Objects and Attributes must be applied through a Metadata
  Change Set before their Model Bindings can be applied.
- Mapping refers to existing Model Bindings; it does not establish physical
  identity.
- Generated Code and Validation are definitions only. Model Change Sets never
  execute them and never store execution results.
- A changed Model revision invalidates the caller's working Snapshot. Download
  a fresh Snapshot and reassess before continuing.

`create_model_snapshot` produces one ID-free 25-dataset archive. Its sections are
Model Input Scope, Profiling, Analysis, Assertion, Conceptual, Logical,
Dimensional, Model Binding, Mapping, Code Generation, and Validation. Every
dataset uses the same strict Pydantic contract for Snapshot reads and Change
Set writes. Call `describe_model_dataset` for exact schema and guidance.

Model Input Scope may contain Source and Bronze Objects. When both represent
the same input, Bronze is the default. Source profiling is valid only through a
foreign catalog and uses Connection `foreign_catalog`, Object
`fc_object_schema`/`fc_object_name`, and Attribute `fc_attribute_name`.
Missing foreign-catalog coordinates are a hard error. Bronze profiling uses its
normal Object schema/name and Attribute name.

## Security

Production trusts only Azure Easy Auth's bounded
`X-MS-CLIENT-PRINCIPAL` envelope. PostgreSQL resolves the active Principal and
effective Tenant access. Human tokens require delegated scope
`workbench.access`; workload tokens require application permission
`workbench.workflow` and an active registered Super Admin service Principal.

`GDS_ENVIRONMENT=local` disables request authentication and maps requests to
one explicitly configured database-backed Local Developer. Tenant Locks,
revisions, validation, audit, and business invariants still apply. Never expose
local mode to an untrusted network.

Completed tool calls append a redacted `mcp.tool_call_log` row. The server
never logs credentials, tokens, connection values, raw prompts, staged records,
submitted SQL, returned rows, raw outputs, or exception text.

`execute_databricks_sql` is the only arbitrary-SQL exception. It accepts at
most 25 statements, permits reads and unqualified temporary views/tables,
rejects DML and persistent DDL, and returns at most 50 rows from the final
statement. Connection values are derived server-side and never returned.

## Local run

1. Seed the Local Developer identity using an untracked copy of
   `database/seed/03_local_super_admin.template.sql`.
2. Copy `.env.example` to an untracked `.env` and provide the governed runtime
   settings. The application does not load `.env` automatically.
3. Run:

```bash
uv sync --project mcp_server --frozen --python 3.14
cd mcp_server
./startup.sh
```

For Windows development, run Uvicorn from the repository root:

```powershell
uv sync --project mcp_server --frozen --python 3.14
uv run --project mcp_server --frozen python -m uvicorn --app-dir mcp_server app:app --host 127.0.0.1 --port 8000
```

Connect the client to `http://localhost:8000/mcp`.

## Tests

```bash
uv run --project mcp_server ruff format --check mcp_server tests/mcp
uv run --project mcp_server ruff check mcp_server tests/mcp
uv run --project mcp_server pyright --project mcp_server mcp_server/gds_etl_workbench
uv run --project mcp_server pytest tests/mcp
```

Database tests reject external DSNs. They create random credentials, a random
database, and a sentinel in one disposable PostgreSQL container, then dispose
the verified container. No cleanup SQL targets a populated database.

## Deployment ZIP

```bash
uv run --project mcp_server python mcp_server/build_zip.py
```

The runtime ZIP contains only `app.py`, `startup.sh`, `requirements.txt`,
`BUILD_MANIFEST.json`, and `gds_etl_workbench/`. It excludes SQL, tests,
documentation, environments, caches, and nested archives. Startup never
applies DDL.
