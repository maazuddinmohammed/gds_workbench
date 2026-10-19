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

Run input snapshots use a key-share Run lock so heartbeat updates can continue
during preparation; Project and authorization locks remain in force. Executors
recheck the live claim before external execution and writes. Claim clocks start
after acquisition waits, and renewal/release validate expiry after lock waits.
Pickup records stale revision or lost write authorization as a terminal failure
instead of spending recovery attempts on a context that cannot execute.

## Persistent Project lock

`project.project.is_locked` is independent of the Tenant lease and individual record
locks. PostgreSQL triggers fence all Project-owned inserts, updates and deletes,
including Change Sets, workflow state/results, code, profiling and enrichment.
Checks lock the parent Project row in write transactions, serializing writes with
lock transitions. Both old and new owners are checked on reassignment.

The web-only command requires a human Architect (or higher), the Tenant Lock,
ownership and expected revision. Each transition advances the Project revision
and appends a lock audit event. Queued/running work must finish or be cancelled
before locking, so no in-flight execution remains behind a locked Project. Reads
remain available; expiring a draft during a read is deferred until unlock.
MCP and Change Sets expose no lock mutation. Runtime roles cannot update the
flag directly. Engineering SQL follows the same write fence and active-run check.

## Project ownership and evidence

A Project belongs to one Tenant, but its authorized physical input scope can span
readable Source Tenants. Source ownership is distinct from GDS placement. Access to
retained source references is rechecked; structural eligibility never grants access.

Logical and Dimensional Entity identity includes Project, layer, schema and name.
Mapping and Code belong directly to those Entities. Physical target registration
is optional later work, so modeling can proceed before operational metadata exists.
Typed references and composite foreign keys preserve Project/parent/layer ownership.

Context Types are a read-only global vocabulary. Each Project-owned Context Group
selects one Type and may identify a source System. Context Records hold text, an
optional plain-text source reference, status and lock. Each Record has one UUID,
generated once at draft creation and retained through edits, imports and retries.
Support references the actual UUID with typed physical/Logical/Context references
rather than one unchecked polymorphic ID. Requirements express desired behavior;
they do not prove source availability. Analysis likewise separates inferred
cardinality from measured validation instead of overwriting one with the other.

## Project, Lane and portable Context contracts

`project.project` owns modeling work. `core.lane` groups Tenants; its foreign keys
use `lane_id`. Conceptual, Logical and Dimensional models, AI model identifiers,
provider settings and library model APIs retain their technical meanings.

Project and Metadata Snapshots use schema version 3.0. Project Change Set results
use 2.0; Metadata Change Set results remain 1.0. Changed Atlas workspace, task,
operation, report and Stage contracts use 2.0. Old contracts require a fresh
Snapshot/workspace; source changes do not migrate populated databases or rewrite
frozen workflow history.

Portable Context is `context.types`, `context.groups`, `context.records`. The
catalog exposes read-only `context_type` alongside writable `context_group` and
`context_record`. Types/groups use published names; records and nested evidence
references retain `context_record_id`. Portable UUID identity is explicit schema
metadata, while internal numeric ownership/audit IDs remain excluded. Types have
no per-Project override. Group type and record ownership are validated server-side.
There is no second record key or classification, stored layer restriction,
confidence field or JSON import/detail metadata. Consumers assess relevance and
active evidence without treating a Context Record as proof of physical lineage.

## Logical-style Dimensional fields and evidence

Workflow records omit AI-assigned confidence fields. Analysis retains inference
reasoning and independently measured validation; Conceptual support retains its
source, role and reason.

Dimensional Attributes share Logical's natural-key, surrogate-key and audit flags.
Natural and surrogate flags are mutually exclusive; either requires non-nullable
data. Entity type, fact subtype, entity grain and relationship details remain.
Definitions carry measure meaning, units and valid aggregation conditions instead
of separate attribute-role, grain-component and aggregation fields. Entity source
mappings retain typed Logical/Context references and contribution rationale, without
a separate source-role label.

The Project Dimensional SCD setting is authoritative for history. Backend policy
projects configured history columns for Type 2 Dimensions; per-Attribute history
exceptions are not represented. Framework keys and audit columns remain protected
through configured templates and the effective relationship graph. Removing schema
fields does not relax Project ownership, Tenant Locks, revisions or idempotency.
These are fresh-install contract changes, not a populated-database migration.

## Plugin settings and enrichment

Project identity is immutable through Change Sets. Project description and allowed
schema/naming/SCD/template/default source-System settings use `project_details` in
the existing reviewed draft; no direct MCP settings save or web-agent-default
mutation is exposed. Source Systems use codes in portable records. Shared template
types validate both web projection and Change Set authoring.

Project-owned `object_enrichment` and `attribute_enrichment` use Snapshots, effective
local records and the same governed Change Set lifecycle as Analysis and design.
They require active applied Input Scope. Profiling remains backend-run; refresh its
Snapshot evidence before enrichment. Enrichment locks are read-only to the plugin;
a locked Object also protects its Attributes. The internal enrichment Apply
function verifies the owned validated draft, revision/digest, Tenant authorization
and locks. Saved-record witnesses also reject concurrent enrichment edits that do
not advance the Project revision. Runtime roles retain no direct enrichment table mutation privileges.
Later local phases can consume pending findings without per-phase Apply.

## Partial authoring and protected work

Conceptual is a standalone deliverable across web and Atlas. Neither Logical nor
Dimensional authoring consumes its objects, relationships or pending local records.
Their prompt variables/readers and default prompts expose only eligible evidence;
Conceptual is not a prerequisite or an overview quality warning for either layer.
Logical uses physical inputs; Dimensional continues to consume Logical outputs.
The complete snapshot stays private for final graph validation. Logical candidates
default to 70% coverage of distinct physical Objects selected for the run through active
source mappings on active Entities across the proposed and retained Project.
Required counts round up; repeated and unselected sources do not inflate coverage.
Attribute completeness is not enforced: physical
Attributes may be omitted or consolidated for the design. Included Attributes
retain source, reference, lock and key/audit validation. Dimensional candidates
default to 60% coverage of selected Logical Entities, without requiring every Silver Attribute to
be copied into an analytical model. Neither rule imposes a minimum output Entity
count. Below target, the existing repair loop receives counts, the shortfall and up
to 50 complete missing-source identities per attempt (fewer if the context budget
requires it). Independent Project-owned enforcement switches default off. When off,
an otherwise valid final candidate returns after the last configured attempt even
below target, with an explicit coverage warning; an empty Logical result can complete
as no effective change with a zero-coverage warning. When on, below-target candidates
fail after repair attempts and never reach Change Set handoff. Schema, reference,
lock, policy and full-graph failures remain blocking and retain existing recovery rules.

Mapping operates on frozen Entity/System pairs. Supported partial documents are
useful progress. Omitted selected, unlocked transformations clear on regeneration;
locked/unselected content stays protected. Protect parent rowset logic when any
child is protected. True failures leave their pair unchanged, distinct from a valid
empty result. Final validation covers the whole future Project before Apply.

Code may use partial applied Mapping with explicit typed-null/zero-row placeholders
and warnings. Missing rules cannot justify invented joins or business logic.
Validation and executable modeled-source lookups still require complete Mapping.
Input-currentness digests describe consistency, not production execution readiness.
A configured default Mapping System applies only to eligible Context-only Entities;
it cannot relabel real lineage or bypass missing upstream Mapping.

Output Templates are advisory JSON field guidance. Preserve custom documents intact
and interpret fields using their saved template definitions. Default-template field
names alone never authorize interpreting arbitrary custom JSON as executable lineage.

## Authoring versus execution

Generated Code and Validation are governed Project sections with explicit review and
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
fences. Explicit Project deletion is a product operation, not a database-reset helper.
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

Atlas runs in VS Code Copilot using one plugin and one deterministic Stage engine.
Copilot connects to governed MCP tools through the plugin's MCP configuration;
the extension exposes Check and Stage through VS Code language-model tools.
Both connections use VS Code-managed Microsoft authentication and must target
the same backend and authorized account. Validation and Apply remain distinct
governed steps.

The installed plugin lives at `Tools/Atlas/atlas`, separate from working folders.
Updates replace the whole plugin folder with a matching release, retaining a
backup until verification. The matching Stage Runner VSIX is installed separately.
Local builds change no cloud identity, backend authorization or deployment.

## Atlas boundaries enforced in code

Stage upload tools (`stage_*`, `begin_*`, `put_*`, `commit_*`) are listed and callable
only on requests with `x-gds-mcp-client: atlas-stage-runner`, which the Stage Runner
sends. Other connections, including Copilot's, receive an audited
`stage_runner_required` refusal. The header is self-declared, so it is not
authentication: every tool still authorizes the Principal. It stops an agent from
uploading drafts without the runner's local-approval digest check. In-memory
sessions act as the runner only under development identity. Release the Stage Runner
before the server; older servers ignore the header.

Apply requires `expected_candidate_digest`, the `candidate_digest` of the validation
the user approved. Project Apply compares it with the stored validation before
revalidating; Metadata Apply compares it with its fresh revalidation because current
metadata can change. A mismatch is `candidate_digest_conflict` and writes nothing.
Recording a new validation clears the local Apply approval. The argument breaks older
callers, so server 0.3.0 releases together with plugin 0.4.1, after Stage Runner 0.3.0.

`project_input_scope` and `profiling_profile` are web-managed: only the web app's
governed Input Scope command and Profiling runs change them. Atlas treats them as
read-only: helper writes, Workbench editing and Stage Runner manifests refuse them,
and local validation reports stale drafts as `web_managed_dataset`. The server
enforces the rule too: MCP Stage, Begin, Put and Commit refuse both datasets with
`web_managed_dataset` before writing anything (`WEB_MANAGED_PROJECT_DATASETS` in
`domain/snapshots/project.py`); the web app's generic Stage already refused them.
Shared validation and materialization still handle both, because the web commands
use them. After a failed governed MCP call,
`atlas-local next --area <area> --error <code>` returns one recovery action from a
fixed table and says stop for unknown codes.

## Deterministic plugin profiling

Atlas starts, polls, or cancels a Profiling run through three governed MCP tools.
The MCP worker resolves applied Project Input Scope, GDS execution credentials,
Source foreign-catalog coordinates or Bronze owner `tenant_catalog`, then builds
parameterized aggregate SQL and saves complete profiles atomically. The plugin
refreshes its Project Snapshot; it does not author SQL or stage profile results.
Batch ID lists are required on batched Objects and shared across a run. Separate
runs represent different selections. Request UUIDs provide idempotency, frozen
context digests reject metadata changes, and claim tokens fence stale/cancelled
workers. Existing Project/Tenant locks and one-running-workflow-per-Tenant remain.
The Databricks connector attempts statement cancellation; Workbench cancellation guarantees no later
save even if Databricks has not yet stopped its statement. Internal credential
and worker functions are never exposed as tools. SQL changes are fresh-install
contracts, not populated-database migrations.
## Atlas task workflows and context disclosure

Atlas 0.2 organizes agent instructions by requested outcome: investigation, source analysis,
conceptual/logical/dimensional design, mapping, code, verification, project changes,
physical metadata and registration. The entry skill routes these tasks; Guided and
Grill Me share the same modeling skill and records. Shared context is minimal;
platform knowledge, domain methods, tool procedures and evidence formats load on demand.
Since 0.4 each skill is a short step template whose commands come from the helper
contract; rules live once in references, with the golden rules in the working method.

Readiness is derived for selected artifacts from applied state, pending changes and
bound evidence, not a new global Project stage or a second progress ledger. Existing
Change Set authorization, locks, revisions, approval digests and uncertain-write
recovery remain authoritative. Project-owned enrichment and server-enforced analysis
scope/masking gaps are explicit; plugin instructions cannot implement missing backend
capabilities or replace their governed boundary.

Local reads support manifest/draft-bound continuation and field projection retaining
canonical identity. Task status defaults to bounded active-task context, with explicit
detail/history retrieval. Node and native PowerShell share this command contract;
neither surface grants additional access or proves business correctness.


### Project coverage and unified Gold audit settings

Logical and Dimensional coverage are Project-owned integer percentages (1–100),
with NOT NULL database defaults of 70 and 60. Each layer has a separate NOT NULL
boolean enforcement setting defaulting false. Governed create/update commands
resolve omitted/null inputs to those defaults and preserve revision/lock checks.
Snapshots carry the values; validators and prompts share the frozen run threshold,
and final acceptance uses the frozen enforcement choice.
Gold audit settings include key and Type 2 history rules in one editable template.
Existing separate key/history templates are combined on read; combined audit
settings take precedence. Internal key projection retains its surrogate/foreign
roles. Type 2 history uses the audit role and sits after SourceSystemID, before
GDSBatchID. Locked Attributes remain protected during reclassification/reordering.
These are fresh-install schema changes; no populated-database migration is added.
