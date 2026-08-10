# Security and invariants

> Superseded for authentication, authorization, and Tenant Locks by
> [`docs/security.md`](../security.md) and
> [ADR 001](../adr/001-direct-principal-authorization-and-tenant-locks.md).

## Trust boundaries

1. Azure App Service Easy Auth authenticates the HTTP request.
2. The App Service parses only the bounded `X-MS-CLIENT-PRINCIPAL` envelope.
3. Repository lookup resolves the current registered Principal, Tenant,
   effective role, and active state. Request claims do not assert Model
   ownership or authorization.
4. The configured workload must match one exact Entra Tenant/Object identity
   and present application role `Workflow.Run`.
5. Workflow Grant identifiers delegate no authority by themselves. Every call
   rechecks identity, status, expiry, Model, operation, binding, the initiating
   user Principal, and the workload service Principal.
6. PostgreSQL roles and constraints remain a second independent boundary.

Protected routes require HTTPS when configured. Request middleware rejects
excess concurrency with `429` and bounds elapsed time. Health routes remain
anonymous and perform no identity work.

## Identity requirements

The decoded Easy Auth envelope is capped at 64 KiB, must contain 1–256 claims,
and caps each claim value at 4,096 characters. `tid`, `oid`, and `idtyp` must
each resolve unambiguously through the accepted claim aliases.

- Human: `idtyp=user`, one valid `tid`, one valid `oid`, and delegated scope
  `workbench.access`.
- Workload: `idtyp=app|application|serviceprincipal`, one valid `tid`, one valid
  `oid`, and application role `Workflow.Run`.
- The actor kind is server-derived. No request field, MCP metadata, or cached
  tool list may choose it.

## Tenant capability matrix

| Capability | Viewer | Developer | Architect | Tenant Admin |
|---|:---:|:---:|:---:|:---:|
| Tenant data read | Yes | Yes | Yes | Yes |
| Private Change Set or draft overlay | No | Yes | Yes | Yes |
| Permitted workflow development | No | Yes | Yes | Yes |
| Validate, apply, and lock Model changes | No | No | Yes | Yes |
| Tenant settings and access administration | No | No | No | Yes |

An active authenticated Principal without Tenant access receives implicit
Viewer capability only for a `global` Tenant. A `private` Tenant requires an
active, unexpired access row. `is_super_admin` is a Principal attribute, not a
Tenant role; it grants every application capability across active Tenants.
Neither global visibility nor super-admin status bypasses locks, revisions,
audit, Workflow Grant binding, or operation availability.

The downstream engineering capability does not create a Release 1 public
registration or foundational CRUD tool. Physical target registration remains
an external owner action.

Model-private failures normally return `not_found` so another Tenant's
ownership is not disclosed.

Sensitive calls resolve one active Entra identity and registered Principal.
Private-Tenant calls additionally resolve one active, unexpired Tenant access
row unless the Principal is a super admin. Mutations resolve and lock those
facts inside the transaction through a narrow, fully-qualified
`SECURITY DEFINER` function with a fixed safe `search_path`. The runtime role
receives no direct foundational security-table write access.

## Workflow Grant checks

Each workload call verifies:

1. exact configured workload identity and application role;
2. exact grant and run pair;
3. active or narrowly allowed completed state and unexpired deadline;
4. exact Model;
5. required delegated operation;
6. exact bound Change Set or Profiling Run when applicable; and
7. current authorization of the initiating human.

The initiating user Principal must remain active and authorized for the same
Tenant. The workload identity must remain bound to the registered service
Principal recorded on the grant.

## Mutation promotion

The service is read-only by default. `GDS_MUTATION_ENABLED=true` is invalid on
its own. Mutation registration also requires a read-only, external T24 evidence
file, the digest of those exact bytes, and the digest of the running release
artifact. Startup verifies the complete evidence and release binding before it
constructs a `VerifiedMutationPromotion` capability.

This gate controls registration. It does not replace per-request authorization,
database roles, locks, revisions, or grants.

## Sensitive data policy

Never expose, log, or commit:

- connection strings or connection values;
- secrets, secret contents, or secret references;
- bearer or workflow tokens;
- raw prompts, physical rows, raw provider or agent tool output, or run dumps;
- unrestricted exception text; or
- generator documents in ordinary telemetry.

Telemetry permits bounded operation names, safe codes, actor kind, correlation
IDs, counts, timings, revisions, and digests. Payload capture is always false.
Public operations may return only their validated, bounded product response;
this is distinct from exposing raw agent or provider output.

## Forbidden public surface

MCP and Workflow Control expose no foundational CRUD, Model Scope mutation,
lock toggle, Tenant Lease, individual graph mutation, arbitrary SQL, delete,
file upload, secret-returning, code-execution, or physical-deployment operation.

## Canonical Release 1 invariants

1. PostgreSQL is authoritative for applied and durable workflow state.
2. Every Model-owned row carries `model_id`.
3. Model-owned parent/child foreign keys carry `model_id`.
4. Object/Attribute pairs are relationally witnessed.
5. Server-generated IDs persist; names are not mutation identity.
6. Applied lifecycle is exactly four values.
7. Candidate state is never applied state.
8. Omission means unchanged.
9. Automated workflows do not physically delete.
10. Locks protect rows and owned descendants on every write path.
11. Validation reports all safe findings and performs no effective write.
12. Apply revalidates and commits all Sections or none.
13. One effective transaction advances the Model revision at most once.
14. Same-Model commits serialize; different Models can commit independently.
15. Routine modeling does not use Tenant Leases.
16. Deterministic context digests detect stale inputs.
17. Actor and ownership are derived server-side.
18. Global-Tenant data is readable by any active authenticated Principal;
    private-Tenant data requires active Tenant access or super-admin status.
19. Only effective architects, Tenant Admins, or super admins validate, apply,
    or lock Model changes.
20. Grants bind initiating user Principal, workload service Principal, Model,
    run, selection, operations, and expiry.
21. Databricks never connects to metadata PostgreSQL.
22. Raw physical data does not traverse MCP.
23. Sensitive data does not appear in ordinary results or logs.
24. Mutating tools require complete local or protected-CI release promotion
    evidence.
25. Tool and contract-resource exposure follows server-owned actor kind.
26. DBML is deterministic, revision-bound, content-addressed, reconstructible,
    and published only beneath a configured root.

Exact test ownership is in [`docs/traceability.md`](../traceability.md).
Security detail is in [`docs/security.md`](../security.md).
