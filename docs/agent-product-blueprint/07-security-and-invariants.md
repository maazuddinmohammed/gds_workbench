# Security and invariants

## Trust boundaries

1. Azure App Service Easy Auth authenticates the HTTP request.
2. The App Service parses only the bounded `X-MS-CLIENT-PRINCIPAL` envelope.
3. Repository lookup resolves current human account, Tenant, role, and active
   state. Request claims do not assert Model ownership.
4. The configured workload must match one exact Entra Tenant/Object identity
   and present application role `Workflow.Run`.
5. Workflow Grant identifiers delegate no authority by themselves. Every call
   rechecks identity, status, expiry, Model, operation, binding, and initiating
   human.
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

## Human capability matrix

| Capability | Developer | Architect | Admin |
|---|:---:|:---:|:---:|
| Open catalog read | Yes | Yes | Yes |
| Owned Model read | Yes | Yes | Yes |
| Bounded Modeling Evidence summary | Yes | Yes | Yes |
| Private Change Set or draft overlay | No | Yes | Yes |
| Model mutation | No | Yes | Yes |
| Profiling | No | Yes | Yes |
| Workflow authorization | No | Yes | Yes |
| Downstream engineering registration capability | Yes | No | Yes |
| Security administration | No | No | Yes |

The downstream engineering capability does not create a Release 1 public
registration or foundational CRUD tool. Physical target registration remains
an external owner action.

Model-private failures normally return `not_found` so another Tenant's
ownership is not disclosed.

Sensitive human calls resolve one active Entra identity, account, and exactly
one active owning-Tenant membership. More than one match is ambiguous and is
rejected; the server never selects one. Mutations resolve and lock the exact
Tenant, identity, account, and membership facts inside the transaction through
a narrow, fully-qualified `SECURITY DEFINER` function with a fixed safe
`search_path`. The runtime role receives no direct foundational security-table
write access.

## Workflow Grant checks

Each workload call verifies:

1. exact configured workload identity and application role;
2. exact grant and run pair;
3. active or narrowly allowed completed state and unexpired deadline;
4. exact Model;
5. required delegated operation;
6. exact bound Change Set or Profiling Run when applicable; and
7. current authorization of the initiating human.

The initiating human must still be active, linked to the same account and
Tenant, and be an architect or admin with workflow-authorization capability.

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
18. Source catalog is open to active humans with one active Tenant membership;
    private Model state is not.
19. Only active owning-Tenant architects/admins profile or mutate Models.
20. Grants bind human, Model, run, selection, operations, workload, and expiry.
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
