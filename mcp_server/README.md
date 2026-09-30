# MCP server

Python Azure App Service exposing stateless Streamable HTTP at `/mcp`.
`gds_etl_workbench/runtime.py` and `tools/` define the current public inventory;
Pydantic contracts beside handlers define exact arguments/results. No copied API
schema in docs is authoritative.

## Boundaries

The public surface provides Tenant/Model/metadata reads, governed Tenant Lock
operations, Metadata/Model Snapshot creation, Change Set lifecycles and bounded
Databricks SQL preflight. It exposes no MCP prompts/resources, foundational CRUD,
individual graph mutation, arbitrary PostgreSQL, credential reads, uploads or code
execution. Atlas owns interaction and local review.

Metadata Change Sets own physical registration. Model Change Sets own scope and
authored Model sections, including Entity-owned Mapping, Code and Validation.
Apply stores definitions; it does not execute/deploy generated artifacts. Target
registration remains an optional Metadata handoff. A changed Model revision requires
a fresh Snapshot and reassessment. Dataset descriptions and snapshot contracts are
available through the registered describe tools.

Azure Easy Auth authenticates production calls. PostgreSQL resolves the active
Principal, Tenant role, lock and revision in governed transactions. Human and workload
requirements, audit redaction and least privilege are in [security](../docs/security.md).
`execute_databricks_sql` permits only authorized reads and unqualified temporary
objects, rejects persistent DDL/DML and returns bounded results. Its validator owns
exact SQL limits; credentials and raw submitted SQL never enter audit logs.

## Local verification and startup

Use the disposable PostgreSQL fixture and commands in [AGENTS.md](../AGENTS.md) for
all database tests. Never substitute an environment DSN, default/local service or
external database. For the complete disposable web review stack, see
[web local run](../web_app/README.md); it does not start MCP.

For an explicitly configured local MCP process, use `.env.example` as the settings
contract. The app does not load `.env` automatically. Keep local identity on loopback,
use only a disposable fixture database and retain locks/revision/audit checks:

```bash
uv sync --project mcp_server --frozen
uv run --project mcp_server --frozen python -m uvicorn --app-dir mcp_server app:app --host 127.0.0.1 --port 8000
```

The client endpoint is `http://127.0.0.1:8000/mcp`. Do not log resolved settings,
connection strings or tool payloads.

## Packaging

```bash
uv run --project mcp_server python mcp_server/build_zip.py
```

The builder emits runtime entrypoints, pinned requirements, a manifest and Python
source only. SQL, tests, docs, environments and secrets are excluded. Rebuild after
shared-source changes; use [Azure deployment](../docs/AZURE_FRESH_DEPLOYMENT.md) for
approved external rollout. Building locally does not deploy anything.
