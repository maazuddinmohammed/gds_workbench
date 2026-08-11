# Release 1 database architecture

The Release 1 database is a canonical, fresh-install PostgreSQL 16 schema. It
is not an in-place migration set and it is not idempotent DDL. A new database
must execute all eleven numbered files from `database/01_reference.sql`
through `database/11_runtime_integrity.sql` exactly once, in sorted order, in
one fail-fast transaction.

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
11. final runtime privileges.

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

Tenant-owned Metadata Change Sets store twelve bounded documents for
Source/Bronze/Silver/Gold Objects and Attributes, Copy Group, Copy, Process
Group, and Process. Their `base_metadata_digest` fences stale drafts; their
events are append-only.

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

## Roles and privileges

The fresh cluster defines two non-login, non-superuser roles:

- `gds_migration`: schema creation plus all release objects;
- `gds_app_write`: safe reads, constrained Model/workflow/MCP DML,
  sequence use, the pure `CHECK` validator, centralized authorization,
  and governed Tenant Lock functions.

`PUBLIC` loses schema, table, and function rights. The application role is
explicitly denied `core.connection_value`. Append-only events, revision
transactions, and audit projections cannot be
updated/deleted by the write role. The runtime role cannot directly mutate
Principal, Tenant-access, Tenant Lock, or Tenant Lock event tables. It can
insert into `mcp.tool_call_log`, but cannot select, update, delete, or
truncate that append-only table.

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
mcp_server/.venv/bin/pytest tests/mcp/test_database_authorization.py -q
```

The fixture rejects existing DSN/libpq connection environment, creates random
database, owner, runtime login, passwords, port, container name, and sentinel,
uses the pinned PostgreSQL 16 image, installs all eleven files once in one
transaction, and exercises the actual runtime role and pool. Cleanup validates
the per-run container label and stops only that container. There is no drop,
truncate, reset, external-DSN, or populated-database cleanup path.
