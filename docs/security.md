# Release 1 security contract

## Trust boundaries

Azure Easy Auth v2 is responsible for token signature, issuer, audience, and
lifetime validation. Application code accepts only the normalized trusted claim
envelope, validates the required `tid`/`oid` and human/workload shape, and maps
that pair to an active internal account on each authorization-sensitive call.
Caller-supplied Tenant, owner, role, grant scope, or actor values are never
trusted.

Production requires HTTPS. Test authentication is an explicit signed-fixture
mode whose key is rejected in production. Configuration failures disclose key
names only and make readiness fail while liveness remains available.

The resolved principal's server-owned `ActorKind` is the MCP audience boundary.
Client metadata, cached inventory, annotations, request fields, and known tool
names cannot select or widen it. The 25 MCP definitions are disjoint: five
human-only catalog/navigation tools, nine shared Model/change-set/DBML tools,
and eleven workload-only Workflow Run, Profiling Run, Mapping-materialization,
and DBML-completion tools. Discovery, direct dispatch, capabilities, registry, and tool-schema
resources apply the same projection on every request. A hidden tool or schema
is rejected before schema validation with the generic response used for an
unknown name.

Mutating MCP registration is a capability established at process start, not an
environment boolean. A bare `GDS_MUTATION_ENABLED=true` fails configuration.
The runtime requires a non-writable, non-symlink T24 evidence file outside the
application tree, an independent SHA-256 pin for that file, and the selected ZIP
SHA-256. It accepts only complete `local` or protected `ci` evidence containing
the exact release gate order (including the OSV audits), no skipped/failed/
expected-failed/warning outcomes, and one matching App Service artifact. It
then binds the evidence revision, contract bundle/registry, lock, staged digest,
and every packaged source file to the canonical embedded build manifest before
constructing the mutation-registration capability.

## Authorization

- Active authenticated users may discover bounded cross-Tenant source metadata.
- Applied Model state is limited to owning-Tenant developer, architect, or admin.
- Draft, graph, and profiling mutations require owning architect/admin authority.
- Admin-only security/recovery actions are not exposed as general MCP tools.
- An owning-Tenant architect/admin human with `workbench.access` may
  authorize/revoke a narrowly bound workflow grant only through the fixed
  non-MCP workflow-control routes. Authorize and revoke require verified
  mutation promotion. Only the configured
  `Workflow.Run` workload identity may activate/use the grant through MCP.
  Model, human, run, change set, workflow, selection, operations, activation
  deadline, expiry, status, and revocation are rechecked; a bare handle has no
  authority.
- Read-only workflow status is available outside MCP to the initiating human
  with current workflow authorization or an owning-Tenant security admin. It
  requires the exact run/grant pair, normalizes private and missing identifiers
  to not-found, and returns scalar state, bounded aggregate counts, binding
  presence, and a diagnostic count—not the workload contract or raw diagnostics.
- Unauthorized and not-found paths intentionally avoid existence disclosure.

Database roles separate deployment, application, and read-only access. Runtime
roles cannot execute DDL, bypass Model revisions, mutate locked aggregates, or
alter/delete authoritative audit. The application role receives no foundational
CRUD, Tenant Lease, direct graph delete, lock-toggle, or generic SQL capability.
The production database LOGIN must have exactly one direct group membership,
`gds_app_write`; it must not be the schema owner, migration identity, Azure
administrator, superuser, or a member of any stronger release-schema role. On
pool startup and every readiness probe, the adapter compares the session's
effective schema, table, sequence, and function privileges with the frozen
`gds_app_write` posture and checks all elevated role attributes. The result is a
boolean only. A mismatch invalidates repository access, closes a newly opened
pool, and leaves process-only liveness available while readiness stays failed.

Mutation authorization fences the exact active identity, account, and Tenant
membership rows through a fixed-search-path `SECURITY DEFINER` function. Only
`gds_app_write` may execute that bounded function. This preserves transaction
stability without granting UPDATE on foundational security tables or exposing a
foundational mutation surface.

## Data and secret handling

MCP never transports physical source rows. Recursive redaction covers results,
diagnostics, journals, snapshots, and exception chains. Logs and traces exclude
prompts, model output, generator documents, credentials, DSNs, bearer/workflow
tokens, source values, and full payloads. Secrets arrive only through injected
settings or managed identity/Key Vault; `.env` files are ignored and never
loaded by production code.

Model Snapshot archives use an explicit transport-neutral allowlist. They omit
MCP capabilities, registry, schema catalog, and all MCP tool request/result DTO
schemas so a human snapshot cannot become an offline map of the workload
transport surface.

The server ZIP uses an explicit allowlist and rejects secret signatures,
symlinks, SQL, tests, notebooks, Spark/jobs dependencies, reference material,
caches, and nested archives. Repository, archive, dependency-vulnerability,
license, and SBOM gates run in `scripts/verify_local.sh`.

## Principal threats and controls

| Threat | Control |
|---|---|
| Spoofed ownership or actor | server-side Entra mapping and ownership lookup |
| Human discovery or guessed invocation of workload MCP tools | per-request `ActorKind` projection across discovery, dispatch, registry, capabilities, and schemas; generic unknown response |
| Cross-Tenant Model access | role/owner authorization plus composite database keys |
| Stale or partial graph commit | whole-candidate validation, revision/CAS, one transaction |
| Lock bypass | future-graph checks plus database triggers |
| Grant replay/escalation | exact binding, expiry/revocation recheck, actor-bound idempotency |
| Duplicate/racing apply | Model/advisory locks, request hash, immutable receipt |
| Secret disclosure | strict schemas, recursive redaction, safe errors, scans |
| Database mis-targeting | fixture-owned local DSNs; one-connection sentinel-guarded T25 deployment |
| Premature mutation registration | complete T24 evidence plus evidence/artifact/source/manifest identity gate |
| Workflow-control expansion | three fixed JSON-only routes; strict DTOs; authorize/revoke promotion gate; read-safe status only |
| Arbitrary computation | no SQL/code/file-upload tools; bounded deterministic jobs ports |

T25 is disabled and `EXTERNAL`. Its early preflight performs bounded reads only.
Its separately authorized DDL command requires an expiring target-, operation-,
network-, sentinel-, and release-bound approval record, rejects alternate DSNs,
uses bounded timeouts plus a transaction deployment lease, rejects concurrent
clients, proves no non-sentinel user objects exist, and revalidates the same
connection and sentinel immediately before one atomic canonical install. It has
no override, drop, truncate, reset, or cleanup path. App Service artifact
selection is derived only from complete release-mode T24 evidence, revalidates
the exact gate order and clean test partition, and rechecks the recorded archive
path, size, digest, and sidecar. The database guard applies the same T24
precondition before any T25 connection.

The T24 record is presently unsigned, and an extracted process cannot recover
the byte identity of a ZIP that the platform no longer exposes. Therefore the
deployment platform remains the trust root for mapping the selector's ZIP SHA
to the mounted application and for protecting the three promotion settings and
read-only evidence mount. Runtime per-file manifest verification detects stale
or altered extracted application content, but it cannot defend against a fully
privileged platform operator forging both configuration and the unsigned local
record. A provider-signed deployment attestation would be required to remove
that residual trust; no external attestation call is made in Release 1.
