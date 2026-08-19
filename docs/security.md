# Authentication, authorization, and Tenant Locks

This is the current security contract for the MCP scaffold. PostgreSQL and the
numbered greenfield SQL are authoritative when prose and older planning material
disagree.

## Public surface

- `/health/live` is anonymous and process-only.
- `/health/ready` is anonymous and returns bounded database posture only.
- `/.well-known/oauth-protected-resource` and its `/mcp` path variant are
  anonymous, cacheable, non-secret OAuth discovery documents.
- `/mcp` uses stateless Streamable HTTP.
- `get_metadata_snapshot` authorizes Tenant Read before returning a 15-minute,
  read-only SAS for the exact private Blob.
- Metadata discovery and Snapshot tools are read-only.
- `execute_databricks_sql` is the sole SQL exception. It accepts reads and
  unqualified temporary views/tables for an authorized active global Connection;
  it rejects all DML and persistent DDL.
- Five governed Tenant Lock tools are registered: check, acquire, renew, release,
  and explicit override.

## Authentication

Azure App Service Easy Auth validates token signature, issuer, audience, and
lifetime. Application code accepts only its bounded `X-MS-CLIENT-PRINCIPAL`
envelope.

Human tokens require:

- exactly one `tid` and `oid`;
- `idtyp=user`; and
- delegated scope `workbench.access`.

Workload tokens require:

- exactly one `tid` and `oid`;
- `idtyp=app`; and
- application permission `workbench.workflow` in the `roles` claim.

Middleware resolves this envelope once and attaches the resulting request
Principal to trusted request state. Tools do not trust caller-supplied Principal,
Tenant Role, actor kind, ownership, or policy values.

The Entra Tenant/Object pair must map to one active
`security.entra_principal_identity` and active `security.principal`. A workload
Principal must also have `is_super_admin=true`; merely obtaining a valid token is
not enough.

## Local development mode

`GDS_ENVIRONMENT=local` derives development authentication. It creates the
synthetic request actor `Local Developer`, skips Entra and Tenant role/visibility
checks, and permits all active Tenants to be listed. It does not change database
Tenant Lock, revision, audit, or business invariants. Production derives Easy
Auth and HTTPS, derives the host allowlist from `GDS_MCP_PUBLIC_URL`, and requires
verified PostgreSQL TLS.

## Tool policies

Every tool declares one policy beside its handler. Shared authorization and the
database function interpret it.

| Tool policy | Minimum authority | Active owned Tenant Lock |
|---|---|---|
| `tenant_read` | Viewer, or implicit Viewer on a global Tenant | No |
| `tenant_metadata_write` | Developer | Yes |
| `tenant_model_write` | Architect | Yes |
| `tenant_lock_manage` | Developer | No |
| `super_admin_only` | Super Admin | No unless the operation separately writes Tenant state |

Tenant Roles are cumulative: Viewer < Developer < Architect < Tenant Admin.
Tenant Admin may perform every Tenant-scoped operation. Super Admin is a global
Principal flag, not a Tenant Role. It bypasses Tenant visibility/membership and
role requirements, but never Tenant Lock ownership, revisions, audit, history,
idempotency, or business invariants.

Global visibility grants read access only. Private reads require an active,
unexpired Viewer-or-higher access row. Missing and inaccessible private Tenants
must produce the same `tenant_not_found` response. `list_tenants` simply omits
inaccessible private Tenants.

## Tenant Lock behavior

One active lock may exist per Tenant. Ownership is the exact internal Principal;
human versus workload type does not affect ownership.

- Ordinary metadata and Model writes require an unexpired lock owned by the
  current Principal.
- A different owner's lock blocks humans, workloads, Tenant Admins, and Super
  Admins alike.
- Lock management requires Developer, Architect, Tenant Admin, or Super Admin.
- Acquire succeeds only when the Tenant is unlocked. An existing lock, including
  the caller's own lock, fails; the owner must use renew instead.
- Only the owner may renew or release.
- Override is explicit, requires a nonblank reason, and force-releases only a
  different owner's active lock. It records `force_unlocked`, does not acquire a
  replacement, and does not remove the prior owner's Tenant access.
- Default duration is 60 minutes; callers may request 1 through 240 minutes.
- PostgreSQL `CURRENT_TIMESTAMP` owns acquired and expiry time.
- Stale locks do not authorize or block writes. Interaction paths record
  `expired`, and the App Service invokes bounded `expire_tenant_locks` batches at
  startup and every 60 seconds.

The lock event stream records `acquired`, `renewed`, `released`,
`force_unlocked`, and `expired`. Expiry has no acting Principal. Override records
both the displaced owner and acting Principal.

Lock conflict responses may disclose only the owner's normalized display name
and bounded lock timing/purpose. They never disclose email, Entra IDs, bearer
tokens, internal lock identifiers, or internal Principal IDs.

## Transaction and database boundary

`security.authorize_tenant_operation` is a fixed-search-path,
`SECURITY DEFINER` function. It resolves the exact active Entra identity,
Principal, Tenant, effective role, policy, and active Tenant Lock. Future write
tools must call it in the same database transaction as their state change.

Governed lock functions are:

- `security.check_tenant_lock`
- `security.acquire_tenant_lock`
- `security.renew_tenant_lock`
- `security.release_tenant_lock`
- `security.override_tenant_lock`
- `security.expire_tenant_locks`

Every runtime transaction locally activates the `NOINHERIT` role
`gds_app_write`. It cannot run
DDL, delete product state, modify Principal/Tenant-access rows, or directly
mutate Tenant Lock tables. It receives only explicit function execution and the
existing allowlisted table privileges. `PUBLIC` receives no release-schema
rights.

Workflow Grant tables, procedures, privileges, and grant-bound run summaries do
not exist. Registered workloads authenticate and authorize directly as active
service Principals.

`mcp.get_databricks_sql_connection_values(bigint)` is a fixed-search-path,
`SECURITY DEFINER` function and the only runtime path to the three Databricks
connection values. It returns values only when exactly one active Environment
has a complete host, HTTP path, and token set for an active global Connection.
The runtime role still has no table-wide `SELECT` on `core.connection_value`.

## MCP tool-call log

`mcp.tool_call_log` stores one row after each completed MCP tool call by
an active server-resolved Principal.
It records the server-generated call ID, server-resolved Principal snapshot,
Actor Kind, Tool Policy, optional Tenant, safe input metadata, safe outcome,
safe failure code, and one PostgreSQL timestamp.

The table is append-only. The runtime role may insert but cannot select, update,
delete, or truncate it. A database trigger also rejects update, delete, and
truncate attempts by more privileged callers. Input metadata must be a JSON
object. PostgreSQL applies no application-specific byte ceiling; normal network
tool calls remain subject to the MCP server's 1 MiB request-body limit. Input
metadata never contains signed cursors, lock purpose/reason text, staged physical
records, prompts, tool output, bearer tokens, Databricks connection values, or
exception text. Callers must never place credentials in submitted SQL.

Central MCP middleware performs the append after the tool returns. Each tool
registers its server-owned Tool Policy, exact safe argument names to retain, and
a summarizer for prohibited payloads beside its handler. Unregistered and
secret-bearing fields are dropped. `list_tenants` retains schema version and page
size and records only whether a cursor was supplied; it never records the cursor.
`get_metadata_snapshot` retains schema version and requested Tenant ID. The
middleware checks only MCP's `isError` flag and never reads or stores tool output.
Tenant Lock tools record only Tenant ID, schema version, bounded duration, and
whether optional purpose or required override reason was supplied. Purpose and
override reason text are not copied into the MCP tool-call log.
Metadata Change Set tools retain their safe identifiers, dataset selection, and
expected revision. Stage records only dataset/record counts; complete staged
physical records are not copied into the tool-call log.
`execute_databricks_sql` records schema version, Connection ID, the complete
submitted SQL, and its character count. SQL is retained only in the append-only
database audit record, not application logs. Returned rows, host, HTTP path,
token, and connector exception text are never logged.

Authentication rejected before MCP execution and identities that do not map to
an active internal Principal cannot produce a Principal-owned tool-call row.
Calls by active Principals fail safely if the required audit insert is
unavailable.

## Safe failures

Stable public codes include `authentication_required`, `authorization_denied`,
`tenant_not_found`, `tenant_lock_required`, `tenant_locked`, `invalid_request`,
`payload_too_large`, and `dependency_unavailable`. Unexpected exceptions become a bounded
`internal_error`; raw SQL, connection values, claims, and exception text are not
returned.

Databricks failures use stable codes for a missing global Connection,
missing/ambiguous/invalid connection configuration, Warehouse connection
failure, rejected statement index, or oversized bounded result. No underlying
connector message is returned.
