# Authentication, authorization, and Tenant Locks

This is the current security contract for the MCP scaffold. PostgreSQL and the
numbered greenfield SQL are authoritative when prose and older planning material
disagree.

## Public surface

- `/health/live` is anonymous and process-only.
- `/health/ready` is anonymous and returns bounded database posture only.
- `/mcp` uses stateless Streamable HTTP.
- The only registered MCP tool is read-only `list_tenants`.
- No Tenant Lock tool is registered yet. The governed database operations exist
  so a later MCP or FastAPI adapter can use the same rules.

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

`GDS_AUTH_MODE=dev` is accepted only when `GDS_ENVIRONMENT=local`. It creates the
synthetic request actor `Local Developer`, skips Entra and Tenant role/visibility
checks, and permits all active Tenants to be listed. It does not change database
Tenant Lock, revision, audit, or business invariants. Production requires
`GDS_AUTH_MODE=azure_easy_auth`, HTTPS, explicit hosts, and verified PostgreSQL
TLS.

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
- Acquire is retry-safe for the existing owner.
- Only the owner may renew or release.
- Override is explicit, replaces only the lock, requires a nonblank reason, and
  records `force_unlocked`; it does not remove the prior owner's Tenant access.
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

- `security.acquire_tenant_lock`
- `security.renew_tenant_lock`
- `security.release_tenant_lock`
- `security.override_tenant_lock`
- `security.expire_tenant_locks`

The runtime login activates the `NOINHERIT` role `gds_app_write`. It cannot run
DDL, delete product state, modify Principal/Tenant-access rows, or directly
mutate Tenant Lock tables. It receives only explicit function execution and the
existing allowlisted table privileges. `PUBLIC` receives no release-schema
rights.

Workflow Grant tables, procedures, privileges, and grant-bound run summaries do
not exist. Registered workloads authenticate and authorize directly as active
service Principals.

## Safe failures

Stable public codes include `authentication_required`, `authorization_denied`,
`tenant_not_found`, `tenant_lock_required`, `tenant_locked`, `invalid_request`,
and `dependency_unavailable`. Unexpected exceptions become a bounded
`internal_error`; raw SQL, connection values, claims, and exception text are not
returned.
