# Current MCP contracts

The scaffold exposes stateless Streamable HTTP at `/mcp`. Request and result
models are immutable Pydantic models with unknown fields forbidden.

## Transport envelope

The MCP request body is limited to 2 MiB. A Model Stage Batch record chunk or
decoded generated-Code JSON fragment is limited to 1 MiB; the larger request
envelope leaves room for base64 and JSON-RPC framing. In `json_fragments` mode,
Commit concatenates the ordered decoded bytes, validates the canonical JSON
record array, and stages one complete `generated_code` record. Fragmentation is
transport-only and does not impose a Code Artifact domain-size limit.

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

## `execute_databricks_sql`

Policy: `tenant_read`

Annotations: non-read-only because temporary objects may be created,
non-destructive, non-idempotent, open-world.

Request:

| Field | Contract |
|---|---|
| `connection_id` | positive ID of an active, non-GDS source Connection |
| `environment_code` | 1–100 characters; matched case-insensitively to one active Environment |
| `sql` | 1–100,000 characters; at most 25 semicolon-separated statements |
| `schema_version` | exactly `"1.0"`; default `"1.0"` |

The server resolves the source Connection's active Tenant and authorizes Tenant
Read. It then resolves `tenant.gds_connection_id` to an active Global Data Store
Connection and retrieves that Connection's values for the requested active
Environment. The Environment must contain `databricks_host_name`,
`databricks_http_path`, and `databricks_token`.

Allowed statements are reads and `CREATE [OR REPLACE] TEMP VIEW/TABLE` with an
unqualified temporary-object name. Physical relations must use
`catalog.schema.table`; CTE and batch temporary names remain unqualified. DML,
persistent DDL, commands, `SELECT INTO`, secret-returning functions, and
external/location-backed temporary objects are rejected before connection.
Statements execute sequentially in one Databricks session. Only the final
statement's result is returned, with at most 50 rows and 500 columns. The result
reports row/cell truncation. Connection values never enter the result or audit
log. Only the submitted SQL's character count and SHA-256 digest enter the
append-only tool-call audit record; submitted SQL itself is not logged.

## Health

`/health/live` returns only `{"status":"live"}`. `/health/ready` returns bounded
ready/not-ready state, a safe posture code, and schema version. Neither route
performs authentication or discloses settings or connection information.

## Stable error shape

MCP tool failures use safe `code: message` text because the SDK serializes tool
exceptions. Relevant codes are `authentication_required`,
`authorization_denied`, `tenant_not_found`, `tenant_lock_required`,
`tenant_locked`, `invalid_request`, `dependency_unavailable`, and
`internal_error`. Stage Batch operations additionally use `stage_batch_conflict`,
`stage_batch_not_found`, `stage_batch_not_active`, `stage_batch_incomplete`, and
`stage_chunk_conflict`. Metadata Change Set validation also returns `object_locked`
when a staged Object or Attribute belongs to an existing locked Object. Apply
rechecks the same lock in PostgreSQL before writing.

Databricks-specific codes distinguish missing/ambiguous/invalid connection
configuration, connection failure, failing statement index, and an oversized
bounded result. Messages never contain connector exception text or credentials.

Future tools must keep their contracts and declared policy beside their handler
and use shared authorization. They may not accept Principal IDs, roles, actor
kind, Tool Policy, or lock ownership from the client. Arbitrary SQL is forbidden
except through the governed `execute_databricks_sql` contract above.
