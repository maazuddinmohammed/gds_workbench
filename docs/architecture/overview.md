# Current MCP scaffold architecture

The deployed unit is one stateless Python 3.14 MCP application on Azure App
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
        tools/tenants/          Tenant list and Connection-grain detail reads
        tools/catalog/          Object visibility, detail, and ingestion lineage
        tools/ingestion/        Copy Group summary and detail reads
        tools/processing/       Process Group summary and detail reads
        tools/snapshots/metadata/
                                complete Metadata Snapshot vertical slice
tests/mcp/                     all MCP and disposable-database tests
```

Each tool keeps its MCP binding, strict request/result contracts, declared
`ToolPolicy`, pagination, and tool-specific SQL in one module. Shared
authentication, authorization interpretation, PostgreSQL transaction mechanics,
central tool-call audit, safe errors, and cursor signing remain architectural
boundaries. Each tool also declares its retained safe inputs and audit summary beside its
handler; the shared middleware appends the result without storing raw inputs or
outputs.

## Current surface

- Anonymous `GET /health/live`
- Anonymous `GET /health/ready`
- Anonymous OAuth protected-resource metadata at both RFC 9728 well-known paths
- Protected stateless `/mcp`
- Ten read-only MCP tools: `list_tenants`, `get_tenant_details`, `list_objects`,
  `get_objects`, `get_object_lineage`, `list_copy_groups`, `get_copy_group`,
  `list_process_groups`, `get_process_group`, and `get_metadata_snapshot`

`list_tenants` returns active global Tenants plus private Tenants for which the
human has active, unexpired Viewer-or-higher access. Registered workload
Principals must be active Super Admins and therefore see all active Tenants.
Local dev mode lists all active Tenants.

`get_metadata_snapshot` authorizes one Tenant, selects a fixed 29-dataset
closure in a repeatable-read read-only transaction, creates a deterministic ZIP
in temporary storage, uploads it create-only to private Blob Storage, and
returns a bounded descriptor containing a 15-minute read-only SAS for the exact
ZIP. Tenant authorization happens before the SAS is minted.

The interactive reads use the same server-owned Object closure as the Metadata
Snapshot. `list_objects` reports why each Object is included and whether an
ingestion mapping exists. Copy Groups are Tenant-owned. Process Groups are
resolved through Copy Groups belonging to the requested Tenant. Detail tools
return bounded safe projections and omit scripts, raw checkpoint values,
connection values, secret references, transformations, and executable paths.

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
