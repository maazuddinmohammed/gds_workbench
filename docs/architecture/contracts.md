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

## `get_metadata_snapshot`

Policy: `tenant_read`

Annotations: read-only, non-idempotent, non-destructive, closed-world.

Request:

| Field | Contract |
|---|---|
| `tenant_id` | positive PostgreSQL BIGINT |
| `schema_version` | exactly `"2.0"`; default `"2.0"` |

The result contains only schema version, Snapshot UUID, kind/status, Tenant ID,
a 15-minute read-only SAS URL for the exact ZIP, `download_url_expires_at`, ZIP
byte count, ZIP SHA-256, and `application/zip` content type. Metadata rows,
JSONL, indexes, manifest, and ZIP bytes never enter MCP. Tenant Read is
authorized before the SAS is minted. Tool-call logs never store the URL.

## Tenant Lock tools

Policy: `tenant_lock_manage`

All five tools accept a positive `tenant_id` and schema version `"1.0"`. Identity,
role, and lock ownership are derived server-side.

| Tool | Additional request fields | Result |
|---|---|---|
| `check_tenant_lock` | none | `is_locked`; safe active-lock details or null |
| `acquire_tenant_lock` | `duration_minutes` 1–240 (default 60); optional nonblank `purpose` up to 500 characters | `acquired=true`; caller-owned lock details |
| `renew_tenant_lock` | `duration_minutes` 1–240 (default 60) | `renewed=true`; caller-owned lock details |
| `release_tenant_lock` | none | `released=true`; `is_locked=false` |
| `override_tenant_lock` | nonblank `reason` up to 2,000 characters | `overridden=true`; `is_locked=false`; previous safe lock details |

Acquire fails for every active lock, including one owned by the caller. Renew and
release require caller ownership. Override releases only another Principal's lock
and never acquires a replacement. Lock details contain only owner display name,
caller-ownership flag, optional purpose, and PostgreSQL-owned timestamps.

## Health

`/health/live` returns only `{"status":"live"}`. `/health/ready` returns bounded
ready/not-ready state, a safe posture code, and schema version. Neither route
performs authentication or discloses settings or connection information.

## Stable error shape

MCP tool failures use safe `code: message` text because the SDK serializes tool
exceptions. Relevant codes are `authentication_required`,
`authorization_denied`, `tenant_not_found`, `tenant_lock_required`,
`tenant_locked`, `invalid_request`, `dependency_unavailable`, and
`internal_error`. Metadata Change Set validation also returns `object_locked`
when a staged Object or Attribute belongs to an existing locked Object. Apply
rechecks the same lock in PostgreSQL before writing.

Future tools must keep their contracts and declared policy beside their handler
and use shared authorization. They may not accept Principal IDs, roles, actor
kind, Tool Policy, lock ownership, or arbitrary SQL from the client.
