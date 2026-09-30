# Security boundaries

Implementation sources: MCP `adapters/auth/`, `tools/`, `domain/databricks_sql.py`, backend
`dependencies.py` and identity adapters, plus `database/03_security.sql`, runtime
privileges and governed write functions. Code and SQL own exact schemas and limits.

## Identity and authorization

MCP production trusts the Azure Easy Auth `X-MS-CLIENT-PRINCIPAL` envelope.
Human tokens require `idtyp=user` and `workbench.access`; workloads require
`idtyp=app`, `workbench.workflow` and an active registered Super Admin Principal.
Exactly one Entra Tenant/Object identity maps to an active internal Principal.

The web App uses Databricks OAuth and App `CAN_USE`. It resolves the forwarded
user token through Databricks `current_user.me()` and an active SCIM user with
an Entra object UUID. Browser-supplied actor, role or ownership fields confer no
authority. Authentication is separate from PostgreSQL authorization.

| Policy | Minimum capability | Owned Tenant Lock |
| --- | --- | --- |
| Tenant Read | Viewer or global-Tenant visibility | No |
| Tenant Metadata Write | Developer | Yes |
| Tenant Model Write | Architect | Yes |
| Tenant Lock Manage | Developer | No existing lock required |
| Super Admin Only | Explicit Super Admin | Still required by ordinary write operations |

Global visibility grants reads only. Private/inaccessible tenants have indistinguishable
not-found behavior. Authorization, lock ownership and revision checks belong in the
same transaction as writes. Runtime roles cannot perform arbitrary DDL or bypass
function-owned state transitions. Preserve fixed search paths and least privilege.

## Locks, claims and retries

Tenant Lock ownership is the exact Principal, not its role or human/workload kind.
Acquire requires a free lock; owners renew or release their own lock. Explicit,
reasoned override releases another owner's lock without acquiring a replacement.
Database time determines expiration. Super Admin does not bypass another owner.
Public conflict details expose only bounded display/timing context.

Workflow Run exclusivity and worker claims are separate from Tenant Locks. Final
writes recheck the live claim and frozen revision. Tokens remain internal; only
safe digests and bounded state enter storage/read models. Idempotent retries reuse
the original operation identity rather than creating duplicate work.

## Local mode and external boundaries

Local authentication is allowed only under explicit local settings and loopback
access. It does not weaken locks, revisions, validation or audit. Tests and the local
runner use fixture-created disposable PostgreSQL only. Production uses TLS and
separate runtime logins; see the deployment runbooks.

Stage Runner is a separate MCP client using VS Code's Microsoft authentication
provider. Restricted Mode disables it. Credentials remain in process/request headers,
never manifests, child processes, agent context or receipts. The local profile accepts
only loopback MCP. Any nonproduction profile must be explicitly selected.

`execute_databricks_sql` is the sole arbitrary-SQL exception: authorized reads and
unqualified temporary views/tables only, with qualified physical references and bounded
results. It rejects DML, persistent DDL and secret-returning operations before connecting.
Connection configuration is resolved server-side and never returned. The SQL validator
and tool handler define exact statement/row limits.

Snapshots are immutable private archives with short-lived read-only download URLs.
Authorize before upload/download handoff; never log the signed URL or export raw
physical rows. Stage fragments reassemble before validation and Apply.

## Audit and safe errors

Never log credentials, secret references, identity tokens, connection strings, raw
prompts, physical rows, staged records, tool/model output or connector exception text.
Audit stores only bounded server-derived identifiers, counts, policy and safe outcomes.
MCP audit is append-only and unavailable audit persistence fails the call safely.

Anonymous liveness/readiness and OAuth discovery reveal no configuration or identity.
Protected routes return stable bounded error codes; inaccessible state must not be
revealed through diagnostics. Keep model payload tracing disabled. Apply authorizes
storage changes, never automatic deployment or production execution.
