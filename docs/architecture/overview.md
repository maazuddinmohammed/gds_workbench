# Current MCP scaffold architecture

The deployed unit is one stateless Python 3.12 MCP application on Azure App
Service backed by PostgreSQL 18.

```text
human MCP client -------- delegated Entra token ---+
                                                    +--> Easy Auth --> /mcp
registered workflow app -- application Entra token +                    |
                                                                         v
                                                                  PostgreSQL 18
```

Azure Easy Auth validates tokens. Middleware parses one bounded claim envelope
and attaches a server-derived human or workload request Principal. PostgreSQL
maps the Entra Tenant/Object pair to the active internal Principal and owns
Tenant visibility, Tenant Role, Super Admin, Tenant Lock, and audit truth.

The Streamable HTTP MCP transport is explicitly `stateless_http=True`. No MCP
session stores authentication or authorization state. Every sensitive request
re-resolves current database facts.

## Code shape

```text
mcp_server/
    app.py
    startup.sh
    gds_etl_workbench/
        runtime.py
        configuration.py
        adapters/auth/          Easy Auth parsing and request middleware
        adapters/mcp/          server composition, health, tool-call audit
        application/            shared authorization and cursor boundaries
        domain/                 policy vocabulary and safe errors
        infrastructure/         PostgreSQL pool, readiness, expiry worker call
        tools/tenants/          complete list_tenants vertical slice
        tools/snapshots/metadata/
                                complete Metadata Snapshot vertical slice
tests/mcp/                     all MCP and disposable-database tests
```

Each tool keeps its MCP binding, strict request/result contracts, declared
`ToolPolicy`, pagination, and tool-specific SQL in one module. Shared
authentication, authorization interpretation, PostgreSQL transaction mechanics,
central tool-call audit, safe errors, and cursor signing remain architectural
boundaries. Each tool also declares its bounded audit-input summary beside its
handler; the shared middleware appends the result without storing raw inputs or
outputs.

## Current surface

- Anonymous `GET /health/live`
- Anonymous `GET /health/ready`
- Protected stateless `/mcp`
- Protected `GET /metadata-snapshots/{tenant_id}/{snapshot_id}/download`
- Two read-only MCP tools: `list_tenants`, `get_metadata_snapshot`

`list_tenants` returns active global Tenants plus private Tenants for which the
human has active, unexpired Viewer-or-higher access. Registered workload
Principals must be active Super Admins and therefore see all active Tenants.
Local dev mode lists all active Tenants.

`get_metadata_snapshot` authorizes one Tenant, selects a fixed 29-dataset
closure in a repeatable-read read-only transaction, creates a deterministic ZIP
in temporary storage, uploads it create-only to private Blob Storage, and
returns only the protected application URL and bounded descriptor. Download
requests reauthorize Tenant access before minting a fresh read-only SAS.

No write or Tenant Lock MCP tool is registered. The database already exposes
governed authorization and acquire/renew/release/override/expiry functions for
future tool or FastAPI adapters.

## Deployment boundary

The App Service ZIP root contains `app.py`, `startup.sh`, `requirements.txt`,
`BUILD_MANIFEST.json`, and the runtime package. It excludes SQL, tests, `.env`,
documentation, caches, and nested archives. Database DDL is installed separately
and never at application startup.

The server opens one bounded PostgreSQL pool. Production connections activate
the `NOINHERIT` `gds_app_write` role. Readiness checks PostgreSQL 18, required
schema functions, and the runtime role posture. The only background write is a
bounded Tenant Lock expiry pass at startup and every 60 seconds.

See [the security contract](../security.md) and
[ADR 001](../adr/001-direct-principal-authorization-and-tenant-locks.md).
