# Current architecture decisions

These decisions explain boundaries that code alone does not explain. Runtime
contracts and numbered SQL remain authoritative. Superseded designs and historical
test counts are intentionally omitted.

## Independent servers, shared source

MCP runs on Azure App Service; the web App runs on Databricks with its own durable
worker. Each artifact receives shared domain/application code at build time and
connects directly to PostgreSQL with a separate least-privilege role. Web features
own workflow orchestration. Transport-neutral code must import without MCP handlers
or authentication adapters. This avoids a runtime dependency between deployments.

## Authorization and concurrency

Authenticated Entra identities resolve to active internal Principals. Workloads
must be explicitly registered as Super Admins. No separate grant model delegates
workflow authority. PostgreSQL derives ownership and authorization in the same
transaction as writes.

Tenant Locks and Run exclusivity solve different problems. The lock permits writes
by its exact Principal; a database unique constraint permits at most one running
Workflow Run per Tenant across processes. Super Admins bypass neither. Claim,
revision and idempotency fences prevent stale workers or uncertain retries from
reapplying work.

## Model ownership and evidence

A Model belongs to one Tenant, but its authorized physical input scope can span
readable Source Tenants. Source ownership is distinct from GDS placement. Access to
retained source references is rechecked; structural eligibility never grants access.

Logical and Dimensional Entity identity includes Model, layer, schema and name.
Mapping and Code belong directly to those Entities. Physical target registration
is optional later work, so modeling can proceed before operational metadata exists.
Typed references and composite foreign keys preserve Model/parent/layer ownership.

Assertions retain source documents and individual contextual records. Support
references the actual record, with typed physical/Logical/Assertion references
rather than one unchecked polymorphic ID. Requirements express desired behavior;
they do not prove source availability. Analysis likewise separates inferred
cardinality from measured validation instead of overwriting one with the other.

## Partial authoring and protected work

Mapping operates on frozen Entity/System pairs. Supported partial documents are
useful progress. Omitted selected, unlocked transformations clear on regeneration;
locked/unselected content stays protected. Protect parent rowset logic when any
child is protected. True failures leave their pair unchanged, distinct from a valid
empty result. Final validation covers the whole future Model before Apply.

Code may use partial applied Mapping with explicit typed-null/zero-row placeholders
and warnings. Missing rules cannot justify invented joins or business logic.
Validation and executable modeled-source lookups still require complete Mapping.
Input-currentness digests describe consistency, not production execution readiness.
A configured default Mapping System applies only to eligible Assertion-only Entities;
it cannot relabel real lineage or bypass missing upstream Mapping.

Output Templates are advisory JSON field guidance. Preserve custom documents intact
and interpret fields using their saved template definitions. Default-template field
names alone never authorize interpreting arbitrary custom JSON as executable lineage.

## Authoring versus execution

Generated Code and Validation are governed Model sections with explicit review and
Apply. Applying definitions never executes or deploys them. Generated surrogate
keys belong to Databricks/framework population; source business identifiers remain
separate mapped fields. Mapping stores transformation dependencies; external Process
Groups/Processes own execution order and loads. Stable source-System sorting is
not business precedence.

SQL/orchestration authoring rules belong in the Code Prompt. Frozen run facts are
structured `artifact_requirements`; validators enforce layout, target/System
coverage, SQL restrictions and governed persistence independently of prompt text.

Manual editing/removal uses backend previews, dependency checks, locks and revision
fences. Explicit Model deletion is a product operation, not a database-reset helper.
Snapshots and Stage payloads use the same effective graph contracts across web/MCP/
Atlas. An old Snapshot must be refreshed before further work.

## Installation and verification

The SQL release installs an empty PostgreSQL database. It is not an upgrade or
backfill path. Runtime startup never applies DDL. Local integration tests create
one disposable container with random credentials/database and a per-run sentinel;
container disposal is the only local database cleanup.

Prompt/default seeds have their documented replay behavior; that does not make
numbered schema installation repeatable. Changes to source and artifacts do not
change installed databases or deployments. Live provider/Databricks execution needs
separate operational validation beyond local contract and synthetic output tests.
