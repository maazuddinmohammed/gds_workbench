# Current MCP contracts

The scaffold exposes stateless Streamable HTTP at `/mcp`. Request and result
models are immutable Pydantic models with unknown fields forbidden.

## `list_tenants`

Policy: `tenant_read`

Annotations: read-only, idempotent, non-destructive, closed-world.

Request:

| Field | Contract |
|---|---|
| `schema_version` | exactly `"1.0"`; default `"1.0"` |
| `page_size` | integer 1 through 200; default 50 |
| `cursor` | null or signed opaque string up to 2,048 characters |

Result:

| Field | Contract |
|---|---|
| `schema_version` | exactly `"1.0"` |
| `tenants` | at most 200 Tenant summaries |
| `next_cursor` | null or signed opaque cursor |

Each Tenant summary contains positive `tenant_id`, bounded code/name/description,
`global|private` visibility, and the server-derived effective role. The cursor
contains collection and offset only; it never carries identity or authority.

Global Tenants are visible to every active registered human Principal. Private
Tenants require active, unexpired Viewer-or-higher access. Active registered
workloads must be Super Admin Principals and see all active Tenants. Local dev
mode sees all active Tenants with effective role `development`.

## Health

`/health/live` returns only `{"status":"live"}`. `/health/ready` returns bounded
ready/not-ready state, a safe posture code, and schema version. Neither route
performs authentication or discloses settings or connection information.

## Stable error shape

MCP tool failures use safe `code: message` text because the SDK serializes tool
exceptions. Relevant codes are `authentication_required`,
`authorization_denied`, `tenant_not_found`, `tenant_lock_required`,
`tenant_locked`, `invalid_request`, `dependency_unavailable`, and
`internal_error`.

Future tools must keep their contracts and declared policy beside their handler
and use shared authorization. They may not accept Principal IDs, roles, actor
kind, Tool Policy, lock ownership, or arbitrary SQL from the client.
