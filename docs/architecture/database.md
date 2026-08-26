# Release 1 database architecture

The Release 1 database is a canonical, fresh-install PostgreSQL 18 schema. It
is not an in-place migration set and it is not idempotent DDL. A new database
must execute the ordered install files from `database/01_reference.sql`
through `database/12_runtime_integrity.sql` exactly once. Run each file in its
own fail-fast transaction.

## Ownership and dependency order

The numbered interface is deliberately split by dependency rather than by
deployment unit:

1. `reference` lookup tables and shared validation helpers;
2. `core` projects, Tenants, Systems, Connections, Objects, Attributes,
   and ingestion mappings;
3. `security` identities, Tenant membership, governed Tenant Locks,
   centralized authorization functions, and the two database roles;
4. Model, environment targets, Scope, safe event projection, exactly two
   Modeling Assertion tables, and revision machinery;
5. Attribute Profile and Analysis;
6. Conceptual Object, Relationship, and typed physical Support;
7. the exact seven Logical families;
8. the exact seven Dimensional families;
9. Mapping Source System Dependency, Object Mapping, and Attribute Mapping;
10. MCP-owned Model and Metadata Change Sets, their events, and tool-call log;
11. group roles, the passwordless `gds_mcp_runtime` login, and its sole group
    membership;
12. final runtime privileges.

There are 73 tables across `reference`, `core`, `security`, `model`, `workflow`,
and `mcp`. Every table has a primary key. Generated numeric artifact IDs use
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

An active Metadata Discovery Scope row uniquely assigns each GDS Connection,
Zone, and normalized schema to one source Tenant. Eligibility, operational
visibility, snapshots, and execution contexts use that assigned Tenant for GDS
Objects and never fall back to the Connection owner. Non-GDS Objects use their
Connection Tenant. The active-only unique assignment index enforces this Core
rule without removing retained inactive scope history.

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

Modeling Assertions consist of one document table and one record table. Analysis
uses a generated result ID and stable physical Attribute/Object endpoints.
Conceptual Support contains exactly one Object or Assertion Record source and
exactly one typed relational parent: Conceptual Object or Conceptual
Relationship. Composite foreign keys keep Assertion support in the same Model.

Logical has exactly seven persisted families. Entity source rows contain one
Bronze Object or Assertion Record; Attribute source rows contain one physical
Attribute path or Assertion Record. Its natural identities remain
reserved across lifecycle. The database enforces orthogonal primary, natural,
and surrogate key facts; non-null keys; same-Model endpoints; authoritative
Model Scope; Bronze source eligibility; effective parent closure; unique
effective Attribute ordinals; and the rule that effective policy-owned audit
Attributes have no physical source mapping.

Dimensional has the corresponding seven families and no Relationship source
mapping. Entity and Attribute sources have the same typed physical/Assertion
choice. Facts and Bridges require both a nonblank grain definition and at
least one effective structured grain component. Entity and Attribute sources
must be active Silver objects/attributes reachable through effective Logical
Object/Attribute Mappings for the same Model. Measures, key roles, audit roles,
and Type 0/1/2 change behavior are constrained relationally; historized
Attributes require the Model's Gold technical-column policy.

Combined Mapping uses `workflow.mapping_source_system_dependency`,
`workflow.mapping_object`, and `workflow.mapping_attribute`. Typed
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

The numbered greenfield DDL currently enforces declarative constraints only:
primary keys, foreign keys, unique constraints, and column `CHECK` rules. Draft
cross-table graph validation was archived until its application behavior is
finalized. Existing read indexes remain available for evaluation.

## Installed and archived behavior

The numbered DDL installs active Principal/Tenant authorization plus governed
Tenant Lock acquisition, renewal, release, explicit override, audit, and bounded
expiry. It does not install the archived draft graph, revision, or lifecycle
triggers under `database/archived_functions_triggers/`; those need
separate finalized requirements and rejecting tests before activation.

## Durable MCP state

Model Change Sets store eight bounded object-shaped JSON documents—Model
Scope, Profiling, Assertion, Analysis, Conceptual, Logical, Dimensional, and
Mapping—plus queryable
base revision/digests, global `draft_revision`, validation outcome, sealed
candidate digest, activity/expiry, and terminal timestamps. Their lifecycle is
`active`, `validated`, `applied`, `expired`, `discarded`, or `superseded`.
Section writes advance the global draft revision exactly once, return the row
to `active`, clear validation, and refresh activity/expiry. Validation seals a
digest/outcome without advancing the draft revision. Terminal payloads are
retained and immutable. Event sequences are unique and append-only.

Tenant-owned Metadata Change Sets store sixteen bounded list-shaped documents:
Source/Bronze/Silver/Gold Objects and Attributes, both Ingestion Mappings, Copy
Group, Member Group, Copy Group Control, Copy, Process Group, and Process. One
ongoing draft is allowed per Tenant and creating Principal. Tenant Lock ownership
is the current concurrency boundary. Their events are append-only, and archive is
a retained terminal state rather than a row move or delete.

Nine governed functions back the MCP Metadata Change Set tools. Create, stage,
validate, and apply require the caller-owned Tenant Lock. Get and archive require
creator ownership but no current lock. Stage replaces one complete JSON list and
uses optimistic `draft_revision`. Validation shares the Snapshot Pydantic
schemas, canonical keys, uniqueness constraints, and reference definitions.
Apply repeats validation, resolves natural keys to IDs, and upserts all 16
eligible Core datasets atomically. The runtime role has no direct SELECT or DML
on Metadata Change Set, Stage Batch, chunk, or event tables. Begin and Put retain
bounded typed chunks without changing the draft; Commit verifies the manifest and
calls the same atomic complete-list Stage operation once. Object mutation is restricted to the
locked Tenant's connections or its active global Metadata Discovery Scopes.

The `ChangeSetsFeature` draft-expiry worker asks the repository to select one
bounded batch. In
PostgreSQL, `CURRENT_TIMESTAMP`, persisted status, and `FOR UPDATE SKIP LOCKED`
jointly decide eligibility; application wall-clock state never does. The same
transaction changes each due `active|validated` draft to `expired`, records its
terminal timestamp, and appends exactly one `expired` event with a worker actor,
correlation ID, draft revision, and `ttl_elapsed` reason. Repeated or concurrent
worker calls cannot append a second terminal event.

The production lifespan calls `security.expire_tenant_locks` immediately and
every 60 seconds. PostgreSQL selects at most 100 expired rows with
`FOR UPDATE SKIP LOCKED`, writes one `expired` event per row, and removes only
those stale locks in the same transaction. Interaction paths perform the same
event-before-replacement behavior. There is no time-based trigger.

Workflow Grant and grant-bound run-summary structures are intentionally absent.
Registered workload identities map directly to active Super Admin Principals.

## Durable web Workflow Run inputs

The `application` schema has 15 normalized tables. A governed Workflow Run
stores the exact active Entra identity used to create it, an optional bounded
Profiling/Analysis batch ID, its immutable Tenant witness, and one immutable
`workflow_run_object_selection` row per selected Object. Mapping selected
coverage also stores one normalized
`workflow_run_mapping_target_selection` target Object/source System pair. The
caller chooses `build|extend` and an artifact type but not a modeled layer or
route. PostgreSQL infers those from active, unlocked preregistered headers and
the target Zone, then freezes the exact `mapping.standard@1.0.0` profile digest.
Code Generation retains its explicit modeled Entity discriminator. The public
create function validates active Model Scope and workflow eligibility,
canonicalizes Object IDs, and derives the SHA-256 digest and count inside
PostgreSQL. Caller-supplied digest/count witnesses are not accepted. Profiling
and Analysis batch requests also require every selected eligible Object to
belong to one System; multi-System selection remains valid without a batch.
The `(model_id, tenant_id)` foreign key proves ownership, and a partial unique
index permits at most one `running` Workflow Run per Tenant while allowing
multiple queued and terminal Runs. `start_workflow_run` maps index contention to
one stable conflict without disclosing the competing Run.

Model Scope itself remains zone-neutral. Run eligibility selects Bronze inputs
for Profiling through Logical, applied-Logical Silver inputs for Dimensional,
and Silver or Gold targets for Logical or Dimensional Mapping/Code Generation.
The web role can read these rows and execute the governed create function, but
has no direct Application table or sequence mutation privilege.

`application.persist_profiling_results` is the only web Attribute Profile
write boundary. While the Profiling Run is `running`, it reauthorizes the bound
actor, requires the owned Tenant Lock and current Model revision, and requires
one bounded result for every active Bronze Attribute in the immutable selected
Objects. It replaces Profiles only in those Objects, advances the Model revision
once when storage changes, and returns that revision for terminal completion.

Two read-through, web-only `SECURITY DEFINER` functions provide Profiling
execution inputs. `get_profiling_execution_context` reauthorizes the bound Run
actor, owned Tenant Lock, running Profiling state, current revision, exact active
discovery assignments, and at least one active eligible Attribute per selected
Object before returning relation and batch metadata. It derives each catalog
from the assigned source Tenant. `get_profiling_connection_values` returns one
credential tuple per exact active GDS Connection for one active Environment. A
missing Environment or incomplete value set returns one fixed safe failure and
no partial secrets.

## Governed web Model authoring

Four `application` functions are the only web Model mutation boundary:
`create_model`, `update_model`, `archive_model`, and `replace_model_scope`.
They resolve the active actor, derive the owning Tenant from the target Model,
apply `tenant_model_write` authorization and current Tenant Lock ownership, and
fence existing Models with `model_revision`. Each actual change increments the
revision once and records one `model_revision_transaction`; an equivalent update
or Scope set is a no-op.

Scope replacement stores the exact unique active Object IDs supplied by the
caller only when every ID is in the canonical Tenant-visible closure. Empty sets
remain valid. Cross-Tenant and mixed-Zone Objects remain valid when reached by
discovery, copy/process references, active ingestion mappings, or current active
Scope. Existing inactive rows are reactivated without changing
`model_scope_is_locked`; absent rows become inactive rather than being deleted.
Workflow-specific zone and Mapping eligibility remains a later run-time rule,
not a Model Scope rule.

## Roles and privileges

The fresh cluster defines two non-login, non-superuser group roles:

- `gds_migration`: schema creation plus all release objects;
- `gds_app_write`: safe reads, constrained Model/workflow DML,
  sequence use, the pure `CHECK` validator, centralized authorization,
  governed Tenant Lock functions, and governed Metadata Change Set functions;
- `gds_web_write`: web reads plus the exact 23 secure `application` functions
  used for Models, Scope, preferences, prompts, runs, events, output templates,
  guides, and stored SQL artifacts.

`gds_mcp_runtime` is the LOGIN used by App Service. It has exactly one direct
membership, `gds_app_write`, and each transaction activates that group with
`SET LOCAL ROLE`.

`gds_web_runtime` is the separate web LOGIN. Its only direct membership is
`gds_web_write`; it never grants MCP access to the `application` schema.

`PUBLIC` loses schema, table, and function rights. The application role is
explicitly denied `core.connection_value`. Append-only events, revision
transactions, and audit projections cannot be
updated/deleted by the write role. The runtime role cannot directly mutate
Principal, Tenant-access, Tenant Lock, Model Scope, or Tenant Lock event tables,
and it cannot update web-only Model agent defaults. It can
insert into `mcp.tool_call_log`, but cannot select, update, delete, or
truncate that append-only table.

The bootstrap principal must have permission to create the three group roles;
the application LOGIN must have exactly one direct membership,
`gds_app_write`, and no owner, migration, administrator, elevated attribute, or
additional group capability. Startup and readiness compare its effective
release-schema table, schema, function, and sequence privileges exactly with
`gds_app_write`; only a boolean posture leaves repository access enabled. Azure
PostgreSQL deployment must use PostgreSQL 18 and preserve these grants.

## Verification

Run:

```bash
mcp_server/.venv/bin/pytest tests/mcp/test_database_authorization.py -q
```

The fixture rejects existing DSN/libpq connection environment, creates random
database, owner, runtime login, passwords, port, container name, and sentinel,
uses the pinned PostgreSQL 18 image, runs the preflight, installs files `01`
through `12`, runs the verifier, and exercises the actual runtime role and
pool. Cleanup validates
the per-run container label and stops only that container. There is no drop,
truncate, reset, external-DSN, or populated-database cleanup path.
