# MCP server

Python Azure App Service exposing stateless Streamable HTTP at `/mcp`.
`gds_etl_workbench/runtime.py` and `tools/` define the current public inventory;
Pydantic contracts beside handlers define exact arguments/results. No copied API
schema in docs is authoritative.

## Boundaries

The public surface provides Tenant/Project/metadata reads, governed Tenant Lock
operations, Metadata/Project Snapshot creation, Change Set lifecycles and bounded
Databricks SQL preflight. It exposes no MCP prompts/resources, foundational CRUD,
individual graph mutation, arbitrary PostgreSQL, credential reads, uploads or code
execution. Atlas owns interaction and local review. Stage upload tools are listed and
callable only on requests carrying `x-gds-mcp-client: atlas-stage-runner`; others get
an audited `stage_runner_required` refusal. That header is not authentication.

Metadata Change Sets own physical registration. Project Change Sets own scope and
authored Project sections, including Entity-owned Mapping, Code and Validation.
Apply requires the approved validation's `expected_candidate_digest` and stores
definitions; it does not execute/deploy generated artifacts. Target
registration remains an optional Metadata handoff. A changed Project revision requires
a fresh Snapshot and reassessment. Dataset descriptions and snapshot contracts are
available through the registered describe tools.

Azure Easy Auth authenticates production calls. PostgreSQL resolves the active
Principal, Tenant role, lock and revision in governed transactions. Human and workload
requirements, audit redaction and least privilege are in [security](../docs/security.md).
`execute_databricks_sql` permits only authorized reads and unqualified temporary
objects, rejects persistent DDL/DML and returns bounded results. Its validator owns
exact SQL limits; credentials and raw submitted SQL never enter audit logs.

## Snapshot storage

Snapshot ZIPs share one configured private container. New uploads use
`metadata/<tenant_id>/YYYYMMDD/<snapshot_id>.zip` or
`project/<tenant_id>/YYYYMMDD/<snapshot_id>.zip`. The date is the snapshot creation
date in UTC; Project Tenant ownership comes from the authorized Project record.
Project ID remains in the Blob metadata and download filename. Files inside the
ZIP retain their existing structure. Existing Blobs and issued download URLs
are unaffected; no archives are moved.

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

### Profiling runs

`start_profiling_run(project_id, selected_object_ids, expected_project_revision, request_id,
batch_ids?, environment_code="dev")` starts deterministic server profiling.
`get_profiling_run_status(run_id)` reports progress and saved counts;
`cancel_profiling_run(run_id)` revokes the claim and requests statement cancellation.
Use a fresh UUID per request, preserving it for identical retries. Batch IDs are a
shared string list, required for selected batched Objects. The server resolves
Source/Bronze relations and GDS Connection values; no SQL or credentials travel
through these tool arguments/results. Refresh the Project Snapshot after completion.

Every MCP process runs a lease-based worker. PostgreSQL claims prevent duplicate
execution across processes and separate MCP Profiling from web workers. Runs
survive process restarts; expired claims can be recovered up to five times. Only
complete, current, authorized results commit. Project and Tenant Lock rules apply.

## Release notes

### 0.3.0

Breaking for older clients:

- `apply_metadata_change_set` and `apply_project_change_set` require
  `expected_candidate_digest`, the `candidate_digest` of the approved validation.
  Calls without it fail argument validation; a mismatch is
  `candidate_digest_conflict` and writes nothing.
- Stage upload tools work only on requests carrying
  `x-gds-mcp-client: atlas-stage-runner`; others get `stage_runner_required`.

Fixed:

- Metadata Snapshot schemas include their `$defs`. The `value` field referenced a
  missing definition, so Atlas rejected every Metadata record copied from a Snapshot.
  Install a fresh Metadata Snapshot to get the fixed schemas.

Release order: Atlas Stage Runner 0.3.0 first (older servers ignore its header), then
server 0.3.0 together with Atlas plugin 0.4.1. Each release needs separate approval.
