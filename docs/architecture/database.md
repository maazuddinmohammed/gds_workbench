# Release 1 database architecture

The Release 1 database is a canonical, fresh-install PostgreSQL 16 schema. It
is not an in-place migration set and it is not idempotent DDL. A new database
must execute `database/01_reference.sql` through
`database/13_runtime_integrity.sql` exactly once, in numeric order, in one
fail-fast transaction.

## Ownership and dependency order

The numbered interface is deliberately split by dependency rather than by
deployment unit:

1. `reference` lookup tables and shared validation helpers;
2. `core` projects, Tenants, Systems, Connections, Objects, Attributes,
   and ingestion mappings;
3. `security` identities, Tenant membership, dormant Tenant Lease data,
   and the three database roles;
4. Model, environment targets, Scope, safe event projection, exactly two
   Modeling Evidence tables, and revision machinery;
5. Attribute Profile and Analysis;
6. Conceptual Object, Relationship, and typed physical Support;
7. the exact seven Logical families;
8. the exact seven Dimensional families;
9. Mapping Source System Dependency, Object Mapping, and Attribute Mapping;
10. Model and Metadata Change Sets, idempotency outcomes, and Apply Receipts;
11. Profiling Runs and final receipts;
12. Workflow Grants and Workflow Run summaries; and
13. cross-family guards, audited business locks, and final privileges.

There are 83 domain tables plus one internal transaction-validation queue
across `reference`, `core`, `security`, `model`, and `workflow`. Every table
has a primary key. Generated numeric artifact IDs use
`BIGINT GENERATED ALWAYS AS IDENTITY`; callers cannot persist their own numeric
identity. UUID workflow identities remain caller/server generated at the
application boundary where the public contract requires them.

Foreign keys use `ON DELETE NO ACTION`. Applied modeling state changes through
explicit lifecycle transitions; there are no cascading deletes. Composite
witness keys keep parent, child, Model, Object, and Attribute identity together
where a single-column foreign key could otherwise admit a cross-parent or
cross-Model reference.

## Foundational and Model invariants

Reference codes use trimmed, case-insensitive uniqueness. The deterministic CSV
fixtures under `tests/database/fixtures/reference/` have the same shape as the
external Excel loader and pass through the production table constraints.
Runtime DDL is not coupled to that loader.

Connection stores optional test initial and incremental batch metadata. A
nullable Object batch-attribute name must still be nonblank when present.

Connection values store optional literal configuration. General application
roles cannot select this table.

Tenant visibility is `global|private` and defaults to private. An active
authenticated Principal may read a global Tenant without membership. Private
reads and every mutation require active, unexpired Tenant access unless the
Principal has the explicit super-admin flag.

`security.principal` represents either a user or service principal. User shape
requires a unique case-insensitive email; service-principal shape requires an
Entra application ID and application/managed-identity type. Entra Tenant/Object
identity remains normalized in `security.entra_principal_identity`.
`security.tenant_principal_access` owns the fixed Viewer, Developer, Architect,
and Tenant Admin capability sets.

Copy Group Control carries Tenant and System witnesses. Composite foreign keys
require its Copy Group and optional Member Group to belong to that same scope.

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

Combined Mapping uses `workflow.mapping_source_system_dependency`,
`workflow.object_mapping`, and `workflow.attribute_mapping`. Typed
Logical/Dimensional parent columns are
exclusive. Composite keys bind children to the same header, target Object, and
Model. Effective Logical targets must be Silver and Dimensional targets Gold.
The current allowlisted package profile is `mapping.standard@1.0.0`; the
database accepts normalized profile keys and SemVer identities so an atomic
future allowlisted package upgrade is representable. Authored metadata is
all-null or complete and JSON/digests are bounded. Effective headers in one
target/System package share package metadata and object dependency order.
Source System waves are controlled once per Model/layer/System; Object waves
are consistent per Model/layer/target.

Statement-level triggers on the 30 graph-input tables enqueue one transient
request per writing transaction. One deferred constraint trigger validates the
final graph and removes that request, so a multi-row transaction performs one
whole-graph scan instead of one scan per changed row. If constraints are forced
immediate, validation runs once per affected statement. The mandatory
Model-row lock serializes effective writes for one Model, preventing same-Model write skew;
different Models retain independent lock domains. Read indexes cover proven
status, parent traversal, impact, source, target, and digest paths. Primary-key
or unique indexes serve exact lock-owner lookups; separate Boolean-first and
partial lock indexes are intentionally omitted because no current read path
uses them.

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

All 25 approved lock-bearing families have direct DML guards. Aggregate edges
also protect owned descendants: Conceptual parents protect Support; Logical and
Dimensional Entities protect their Attributes and source mappings; Submodels
jointly protect membership; source headers protect source children; and Object
Mapping protects Attribute Mapping. Relationships may continue to reference a
locked endpoint because reference use does not mutate the lock owner.

The Model-owned lock toggle is
`security.set_artifact_lock(bigint,text,bigint,boolean,uuid,uuid,text,uuid)`.
The two UUID arguments are the authenticated Entra Tenant/Object identity. The
function resolves the active user or service Principal rather than trusting an
internal Principal ID supplied by a request. It validates an active Tenant and
active Architect/Tenant Admin access or super admin, holds share locks on that
Tenant and the actor authorization rows, locks the active
Model row before the artifact, changes only lock/audit fields, advances one
Model revision, and appends `security.artifact_lock_event`. Its
artifact-type switch is an allowlist, SQL identifiers are never caller
supplied, its search path is fixed, and `PUBLIC` has no execution right. A
no-op request returns the current revision without a new audit row. Release 1
exposes no MCP route for this function; a future human command must authorize at
the application boundary before calling it. The internal lock flag has the
same owner check as revision capture, so a runtime role cannot bypass a locked
row by setting a custom GUC.

Core Object and Attribute locks use the separate Tenant-scoped
`security.set_metadata_artifact_lock(...)` function. It authorizes against the
artifact's owning Connection Tenant, resolves the same authenticated Entra
identity, and writes
`security.metadata_artifact_lock_event`; it never borrows authority from a
Model that merely references a cross-Tenant source.

`security.lock_model_row(bigint)` is the narrower application primitive.
It is a fixed-search-path `SECURITY DEFINER` function executable only by
`gds_app_write`; it returns only an existence Boolean while holding a real
`SELECT ... FOR UPDATE` lock through transaction end. The repository combines
that row lock with its process-independent advisory namespace. Apply acquires
this Model fence before the draft and rechecks active state and context. Draft
create, section put, and validation deliberately use their workflow-state
transactions and revision guards without taking a Model-row lock.

## Durable workflow state

Model Change Sets store eight bounded object-shaped JSON documents—Model
Scope, Profiling, Evidence, Analysis, Conceptual, Logical, Dimensional, and
Mapping—plus queryable
base revision/digests, global `draft_revision`, validation outcome, sealed
candidate digest, activity/expiry, and terminal timestamps. Their lifecycle is
`active`, `validated`, `applied`, `expired`, `discarded`, or `superseded`.
Section writes advance the global draft revision exactly once, return the row
to `active`, clear validation, and refresh activity/expiry. Validation seals a
digest/outcome without advancing the draft revision. Terminal payloads are
retained and immutable. Event sequences are unique and append-only.

Tenant-owned Metadata Change Sets store twelve bounded documents for
Source/Bronze/Silver/Gold Objects and Attributes, Copy Group, Copy, Process
Group, and Process. Their `base_metadata_digest` fences stale drafts; their
events and apply receipts are append-only.

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
audit values, initiating user Principal, registered service-principal identity,
Model, Tenant, and expiry.
They move through `pending`, `active`, and one terminal state. Change-set,
profiling-run, and Databricks bindings are write-once. A composite witness binds
safe workflow summaries to the same grant/run/Model/workflow tuple. Profiling
completion publishes successful Attribute Profiles and one final receipt in a
single transaction. Failed Attributes retain their prior Profile, while the
receipt records the bounded failure count. The operation ledger owns exact
request replay. Final profiling and apply receipts are append-only. No
workflow, grant, summary, or receipt column stores a bearer token, password,
credential, or connection secret.

## Roles and privileges

The fresh cluster defines three non-login, non-superuser roles:

- `gds_migration`: schema creation plus all release objects;
- `gds_app_read`: safe catalog/model/workflow reads; and
- `gds_app_write`: the same safe reads, constrained Model/workflow DML,
  sequence use, pure CHECK validators, the narrow artifact-lock function, and
  the bounded Principal-access and Model-row lock functions.

`PUBLIC` loses schema, table, and function rights. Both application roles are
explicitly denied `core.connection_value`. Append-only events, idempotency,
receipts, revision transactions, and audit projections cannot be
updated/deleted by the write role. Trigger functions and internal revision
functions are not directly executable by runtime roles. The Principal-access
function is `SECURITY DEFINER`, has a fixed `pg_catalog` search path, returns
only bounded identity, effective-role, and capability fields, joins an active
Tenant, and holds share locks on Tenant, identity, Principal, and access rows
without granting foundational table UPDATE. Global visibility projects Viewer
read capability only; expired/inactive access grants no authority, and super
admin projects all application capabilities.

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
applies the thirteen files once in a transaction, loads the CSV fixtures, runs exact
catalog/security assertions and accepted/rejected behavior cases, observes
same-Model blocking through `pg_blocking_pids`, proves different-Model commit
independence, and disposes only its marker-verified container. An unavailable
container runtime is a test failure, never a skip. It writes the observed
PostgreSQL patch version and executed assertion counts to the requested evidence
path. There is no drop, truncate,
reset, or external-DSN cleanup path.
