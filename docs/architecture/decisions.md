# Current architecture decisions

These decisions explain boundaries that code alone does not explain. Runtime
contracts and numbered SQL remain authoritative. Superseded designs and historical
test counts are intentionally omitted.

## Independent servers, shared source

MCP runs on Azure App Service; the web App runs on Databricks with its own durable
worker. Each artifact receives shared domain/application code at build time and
connects directly to PostgreSQL with a separate least-privilege role. Web features
own their orchestration. MCP also owns a durable deterministic Profiling worker;
web and MCP claim only runs assigned to their backend. Shared aggregate SQL
planning lives in `application/profiling/execution.py`. Transport-neutral code must import without MCP handlers
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

## Persistent Model lock

`model.model.is_locked` is independent of the Tenant lease and individual record
locks. PostgreSQL triggers fence all Model-owned inserts, updates and deletes,
including Change Sets, workflow state/results, code, profiling and enrichment.
Checks lock the parent Model row in write transactions, serializing writes with
lock transitions. Both old and new owners are checked on reassignment.

The web-only command requires a human Architect (or higher), the Tenant Lock,
ownership and expected revision. Each transition advances the Model revision
and appends a lock audit event. Queued/running work must finish or be cancelled
before locking, so no in-flight execution remains behind a locked Model. Reads
remain available; expiring a draft during a read is deferred until unlock.
MCP and Change Sets expose no lock mutation. Runtime roles cannot update the
flag directly. Engineering SQL follows the same write fence and active-run check.

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

## Plugin settings and enrichment

Model identity is immutable through Change Sets. Model description and allowed
schema/naming/SCD/template/default source-System settings use `model_details` in
the existing reviewed draft; no direct MCP settings save or web-agent-default
mutation is exposed. Source Systems use codes in portable records. Shared template
types validate both web projection and Change Set authoring.

Model-owned `object_enrichment` and `attribute_enrichment` use Snapshots, effective
local records and the same governed Change Set lifecycle as Analysis and design.
They require active applied Input Scope. Profiling remains backend-run; refresh its
Snapshot evidence before enrichment. Enrichment locks are read-only to the plugin;
a locked Object also protects its Attributes. The internal enrichment Apply
function verifies the owned validated draft, revision/digest, Tenant authorization
and locks. Saved-record witnesses also reject concurrent enrichment edits that do
not advance the Model revision. Runtime roles retain no direct enrichment table mutation privileges.
Later local phases can consume pending findings without per-phase Apply.

## Partial authoring and protected work

Web Logical authoring receives no Conceptual records. Legacy Conceptual prompt
variables/readers remain compatible but expose absent data for Logical runs.
Current default prompts omit those variables and reader selections; older frozen
or custom versions retain their registrations.
The complete snapshot stays private for final graph validation. Logical candidates
must cover selected physical Objects through active source mappings across the
proposed and retained Model. Attribute completeness is not enforced: physical
Attributes may be omitted or consolidated for the design. Included Attributes
retain source, reference, lock and key/audit validation. Dimensional candidates
must cover selected Logical Entities, without requiring every Silver Attribute to
be copied into an analytical model. Neither rule imposes a minimum output Entity
count. Coverage failures use the existing repair loop and rejected-draft retention;
they cannot produce a successful handoff or a false no-op on an uncovered selection.

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

Code storage is independent of artifact format: `table` requires inline content;
`git` may omit it. Repository, commit/path and entry point are nullable unrestricted
text; parameters are nullable JSON of any shape. Change Sets and Snapshots preserve
these fields. Code-context freshness includes storage metadata as well as the inline
content digest; it does not inspect Git contents. Web SQL generation/downloads remain
table-only and regeneration preserves Git artifacts. Source changes describe fresh
installs, not an upgrade of an installed database.

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

## Atlas host compatibility

Atlas has one portable plugin and one deterministic Stage engine. Copilot uses
VS Code language-model tools. Codex uses a bundled stdio relay to the running
VS Code extension. Authentication, the reviewed remote-tool proxy and Stage all
execute in the extension; Microsoft tokens never cross the local bridge.
The connector has no separate login, app registration, MSAL cache or native npm
dependencies. Validation and Apply remain distinct governed steps.

The user opens the same local trusted folder in both clients and runs
**Atlas: Start Codex Bridge**. Each workspace gets a private Unix socket or
Windows named pipe, protected by a random session capability and a private
per-user descriptor. The server binds file access to that real workspace root;
the connector cannot widen it. One persistent local connection and remote MCP
session per Codex session avoid per-call startup and authentication overhead.
Only Atlas tool calls take this route. Workspace, profile and account changes
invalidate it. Disconnects never replay uncertain operations. VS Code must remain
open; remote VS Code windows and Codex cloud execution are unsupported.

The stable layout is `Tools/Atlas/atlas`, `atlas-connector`, and generated sibling
`codex-atlas`. Setup adapts transport without changing the portable source and
registers/refreshes Codex's installed copy. Generated copies contain no credentials.
Updates validate input, serialize local replacement, and retain rollback backups.
The ZIP updater replaces entire package folders, leaving working files separate.
The matching VSIX must also be installed. Local builds change no cloud identity,
backend authorization or deployment.

## Deterministic plugin profiling

Atlas starts, polls, or cancels a Profiling run through three governed MCP tools.
The MCP worker resolves applied Model Input Scope, GDS execution credentials,
Source foreign-catalog coordinates or Bronze owner `tenant_catalog`, then builds
parameterized aggregate SQL and saves complete profiles atomically. The plugin
refreshes its Model Snapshot; it does not author SQL or stage profile results.
Batch ID lists are required on batched Objects and shared across a run. Separate
runs represent different selections. Request UUIDs provide idempotency, frozen
context digests reject metadata changes, and claim tokens fence stale/cancelled
workers. Existing Model/Tenant locks and one-running-workflow-per-Tenant remain.
The Connector attempts cancellation; Workbench cancellation guarantees no later
save even if Databricks has not yet stopped its statement. Internal credential
and worker functions are never exposed as tools. SQL changes are fresh-install
contracts, not populated-database migrations.
## Atlas task workflows and context disclosure

Atlas 0.2 organizes agent instructions by requested outcome: investigation, source analysis,
conceptual/logical/dimensional design, mapping, code, verification, model changes,
physical metadata and registration. The entry skill routes these tasks; Guided and
Grill Me share the same modeling skill and records. Shared context is minimal;
platform knowledge, domain methods, tool procedures and evidence formats load on demand.

Readiness is derived for selected artifacts from applied state, pending changes and
bound evidence, not a new global Model stage or a second progress ledger. Existing
Change Set authorization, locks, revisions, approval digests and uncertain-write
recovery remain authoritative. Model-owned enrichment and server-enforced analysis
scope/masking gaps are explicit; plugin instructions cannot implement missing backend
capabilities or replace their governed boundary.

Local reads support manifest/draft-bound continuation and field projection retaining
canonical identity. Task status defaults to bounded active-task context, with explicit
detail/history retrieval. Node and native PowerShell share this command contract;
neither surface grants additional access or proves business correctness.
