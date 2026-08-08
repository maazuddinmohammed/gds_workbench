# Release 1 database architecture

The Release 1 database is a canonical, fresh-install PostgreSQL 16 schema. It
is not an in-place migration set and it is not idempotent DDL. A new database
must execute `database/1_core_reference.sql` through
`database/9_workflow_mapping.sql` exactly once, in numeric order, in one
fail-fast transaction. `core.schema_version` records schema and contract
version `1.0.0` under the singleton key `gds_etl_workbench`.

## Ownership and dependency order

The numbered interface is deliberately split by dependency rather than by
deployment unit:

1. `core` reference codes and schema-version helpers;
2. foundational projects, Tenants, Systems, Connections, Objects, Attributes,
   and ingestion mappings;
3. `core_security` identities, Tenant membership, dormant Tenant Lease data,
   and the three database roles;
4. Model, environment targets, Scope, safe event projection, exactly two
   Modeling Evidence tables, and revision machinery;
5. Attribute Profile and Analysis;
6. Conceptual Object, Relationship, and typed physical Support;
7. the exact seven Logical and exact seven Dimensional families;
8. Model Change Sets, workflow grants/summaries, idempotency, profiling staging,
   and final receipts; and
9. the two combined Mapping tables plus cross-family guards, audited business
   locks, and final privileges.

There are 61 release tables across `core`, `core_security`, `model`, and
`workflow`. Every table has a primary key. Generated numeric artifact IDs use
`BIGINT GENERATED ALWAYS AS IDENTITY`; callers cannot persist their own numeric
identity. UUID workflow identities remain caller/server generated at the
application boundary where the public contract requires them.

Foreign keys use `ON DELETE NO ACTION`. Applied modeling state changes through
explicit lifecycle transitions; there are no cascading deletes. Composite
witness keys keep parent, child, Model, Object, and Attribute identity together
where a single-column foreign key could otherwise admit a cross-parent or
cross-Model reference.

## Foundational and Model invariants

Reference codes are normalized lowercase identifiers. The deterministic CSV
fixtures under `tests/database/fixtures/reference/` have the same shape as the
external Excel loader and pass through the production table constraints.
Runtime DDL is not coupled to that loader.

Connection profiling policy implements DD-108 with the four canonical columns:
development/test initial batch IDs and development/test ordered incremental
batch-ID arrays. Incremental arrays are one-dimensional, one-based, bounded,
strictly increasing, duplicate-free, null-free, and disjoint from the matching
initial ID. A nullable Object batch-attribute name must still be nonblank when
present.

Connection values enforce exactly one literal or Key Vault reference and a
deferred trigger checks that storage matches the reference parameter's
`is_key_vault` policy. General application roles cannot select this table.

A Model belongs to one Tenant but its Scope may intentionally include active
Bronze Objects from another Tenant. That open source-composition boundary is
tested. Downstream model-owned references remain Model-scoped. DD-110 is stored
only in the five canonical JSON policy columns. Structural checks require the
versioned naming, Silver audit, Gold technical, and Gold audit shapes and keep
each policy group all-null or complete.

## Applied modeling graph

The applied lifecycle is `active`, `needs_review`, `inactive`, or `deprecated`;
the first two states are effective. Candidate-local references and AI/human
acceptance labels never appear in applied tables.

Modeling Evidence consists of one document table and one record table. Analysis
uses a generated result ID and stable physical Attribute/Object endpoints.
Conceptual Support contains one physical Object and exactly one typed relational
parent: Conceptual Object or Conceptual Relationship. No transient Evidence ID
is a downstream Conceptual lineage column.

Logical has exactly seven persisted families. Its natural identities remain
reserved across lifecycle. The database enforces orthogonal primary, natural,
and surrogate key facts; non-null keys; same-Model endpoints; authoritative
Model Scope; Bronze source eligibility; effective parent closure; unique
effective Attribute ordinals; and the rule that effective policy-owned audit
Attributes have no physical source mapping.

Dimensional has the corresponding seven families and no Relationship source
mapping. Facts and Bridges require both a nonblank grain definition and at
least one effective structured grain component. Entity and Attribute sources
must be active Silver objects/attributes reachable through effective Logical
Object/Attribute Mappings for the same Model. Measures, key roles, audit roles,
and Type 0/1/2 change behavior are constrained relationally; historized
Attributes require the Model's Gold technical-column policy.

Combined Mapping is exactly `workflow.object_mapping` and
`workflow.attribute_mapping`. Typed Logical/Dimensional parent columns are
exclusive. Composite keys bind children to the same header, target Object, and
Model. Effective Logical targets must be Silver and Dimensional targets Gold.
The current allowlisted package profile is `mapping.standard@1.0.0`; the
database accepts normalized profile keys and SemVer identities so an atomic
future allowlisted package upgrade is representable. Authored metadata is
all-null or complete and JSON/digests are bounded. Effective headers in one
target/System package share package metadata and both dependency waves. Source
System waves are consistent per layer/System and target waves per layer/target.

Deferred constraint triggers validate the final transaction graph from both
child-side and parent/source-side mutations. The implementation intentionally
scans the final affected graph for correctness. The mandatory Model-row lock
serializes effective writes for one Model, preventing same-Model write skew;
different Models retain independent lock domains. Read indexes cover status,
parent traversal, impact, source, target, digest, and lock paths.

## Revision and business-lock protocol

Every effective mutation first locks its Model row. The first effective write
in one PostgreSQL transaction records `(model_id, txid_current())` and advances
`model_revision` once; later writes in that transaction reuse the record. A
byte-for-byte no-op update returns before revision capture. Draft validation,
change-set section writes, and other workflow-state mutations do not own a
revision trigger.

`model.record_effective_change` and its trigger entry points are protected
`SECURITY DEFINER` functions with `search_path=pg_catalog`. The revision-column
guard accepts its internal session flag only when the executing database role
is the protected function owner, so an application role cannot forge the
custom GUC to write a revision directly.

All 21 approved lock-bearing families have direct DML guards. Aggregate edges
also protect owned descendants: Conceptual parents protect Support; Logical and
Dimensional Entities protect their Attributes and source mappings; Submodels
jointly protect membership; source headers protect source children; and Object
Mapping protects Attribute Mapping. Relationships may continue to reference a
locked endpoint because reference use does not mutate the lock owner.

The only lock toggle is
`core_security.set_artifact_lock(bigint,text,bigint,boolean,bigint,text,uuid)`.
It validates an active Tenant and active architect/admin membership, holds
share locks on that Tenant and the actor authorization rows, locks the active
Model row before the artifact, changes only lock/audit fields, advances one
Model revision, and appends `core_security.artifact_lock_event`. Its
artifact-type switch is an allowlist, SQL identifiers are never caller
supplied, its search path is fixed, and `PUBLIC` has no execution right. A
no-op request returns the current revision without a new audit row. Release 1
exposes no MCP route for this function; a future human command must authorize at
the application boundary before calling it. The internal lock flag has the
same owner check as revision capture, so a runtime role cannot bypass a locked
row by setting a custom GUC.

`core_security.lock_model_row(bigint)` is the narrower application primitive.
It is a fixed-search-path `SECURITY DEFINER` function executable only by
`gds_app_write`; it returns only an existence Boolean while holding a real
`SELECT ... FOR UPDATE` lock through transaction end. The repository combines
that row lock with its process-independent advisory namespace. Apply acquires
this Model fence before the draft and rechecks active state and context. Draft
create, section put, and validation deliberately use their workflow-state
transactions and revision guards without taking a Model-row lock.

## Durable workflow state

Model Change Sets store six bounded object-shaped JSON sections plus queryable
base revision/digests, global `draft_revision`, validation outcome, sealed
candidate digest, activity/expiry, and terminal timestamps. Their lifecycle is
`active`, `validated`, `applied`, `expired`, `discarded`, or `superseded`.
Section writes advance the global draft revision exactly once, return the row
to `active`, clear validation, and refresh activity/expiry. Validation seals a
digest/outcome without advancing the draft revision. Terminal payloads are
retained and immutable. Event sequences are unique and append-only.

The `ChangeSetsFeature` draft-expiry worker asks the repository to select one
bounded batch. In
PostgreSQL, `CURRENT_TIMESTAMP`, persisted status, and `FOR UPDATE SKIP LOCKED`
jointly decide eligibility; application wall-clock state never does. The same
transaction changes each due `active|validated` draft to `expired`, records its
terminal timestamp, and appends exactly one `expired` event with a worker actor,
correlation ID, draft revision, and `ttl_elapsed` reason. Repeated or concurrent
worker calls cannot append a second terminal event.

The production lifespan runs the same bounded recovery pass through
`WorkflowRunsFeature`. Repository/database time expires `pending` grants at
their activation deadline and `active` grants at run expiry. PostgreSQL locks
each selected grant and its summary with `FOR UPDATE ... SKIP LOCKED`, then
commits both terminal `expired` states and the safe reason together. Apply and
expiry share the grant fence, so expiry between validation and apply makes apply
fail truthfully while leaving the validated draft and Model unchanged. The
worker runs an immediate pass at startup, repeats periodically, and reports only
bounded expiry metrics.

Workflow grants freeze the exact request, selection, allowed operations, fixed
Databricks workspace/job identity, source release, safe Notebook Definition
audit values, workload identity, Model, Tenant, and expiry.
They move through `pending`, `active`, and one terminal state. Change-set,
profiling-run, and Databricks bindings are write-once. A composite witness binds
safe workflow summaries to the same grant/run/Model/workflow tuple. Profiling
success and failure staging is append-only and mutually exclusive for each
run/Attribute. A batch idempotency key may cover multiple Attribute rows; stage
replays are still unique by run, key, and Attribute, while the operation ledger
owns exact request replay. Failure rows durably retain code, message, and the
required retryable classification. Final profiling and apply receipts are
append-only. No workflow, grant, summary, or staging column stores a bearer
token, password, credential, or connection secret.

## Roles and privileges

The fresh cluster defines three non-login, non-superuser roles:

- `gds_migration`: schema creation plus all release objects;
- `gds_app_read`: safe catalog/model/workflow reads; and
- `gds_app_write`: the same safe reads, constrained Model/workflow DML,
  sequence use, pure CHECK validators, the narrow artifact-lock function, and
  the bounded mutation-principal and Model-row lock functions.

`PUBLIC` loses schema, table, and function rights. Both application roles are
explicitly denied `core.connection_value`. Append-only events, idempotency,
staging, receipts, revision transactions, and audit projections cannot be
updated/deleted by the write role. Trigger functions and internal revision
functions are not directly executable by runtime roles. The mutation-principal
function is `SECURITY DEFINER`, has a fixed `pg_catalog` search path, returns
only bounded authorization fields, joins an active Tenant, and holds share
locks on Tenant, identity, account, and membership rows without granting
foundational table UPDATE. Read resolution likewise treats an inactive Tenant
membership as no authority while retaining only the safely authenticated human
identity.

The bootstrap principal must have permission to create the three group roles;
the application LOGIN must have exactly one direct membership,
`gds_app_write`, and no owner, migration, administrator, elevated attribute, or
additional group capability. Startup and readiness compare its effective
release-schema table, schema, function, and sequence privileges exactly with
`gds_app_write`; only a boolean posture leaves repository access enabled. Azure
PostgreSQL deployment must use PostgreSQL 16 and preserve these grants.

## Verification

Run:

```bash
bash tests/database/run_postgres_catalog.sh \
  --evidence-output artifacts/database-results.json
```

The harness rejects external DSNs and libpq/Azure connection environment,
centrally resolves and validates a local Unix Docker socket before inspecting
or starting an image, creates random credentials/database/container
coordinates, uses only the pinned `postgres:16.13-bookworm` digest, proves the
image/container/database identity,
applies the nine files once in a transaction, loads the CSV fixtures, runs exact
catalog/security assertions and accepted/rejected behavior cases, observes
same-Model blocking through `pg_blocking_pids`, proves different-Model commit
independence, and disposes only its marker-verified container. An unavailable
container runtime is a test failure, never a skip. It writes the observed
PostgreSQL patch version and executed assertion counts to the requested evidence
path. There is no drop, truncate,
reset, or external-DSN cleanup path.
