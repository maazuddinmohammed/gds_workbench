# GDS ETL Workbench

GDS ETL Workbench lets developers inspect governed metadata, prepare a complete Model change, validate it, and apply it through one controlled workflow.

## Language

**Tenant**:
The ownership scope for Principals, metadata, Models, and authorization.
_Avoid_: Customer, client, account scope

**Source Tenant**:
The single Tenant whose data a physical Object represents, independent of the
Systems or Connections contributing to it. An Object may combine contributors
within that Tenant but never data from another Tenant. Every physical Object has
exactly one Source Tenant; shared or cross-Tenant Objects are not supported.
_Avoid_: Connection owner, source System, GDS Connection

**Physical Object Placement**:
The Connection on an Object identifies where that Object is registered. A
Source Object uses its source Connection. Bronze, Silver, and Gold Objects use
the active Connection identified for the Source Tenant as
`is_tenant_gds_connection=true`; it must also be a Global Data Store Connection.
That Connection identifies the GDS Tenant and GDS System. Their Source Tenant
still identifies the Tenant whose data they contain and does not change to the
GDS Tenant.
_Avoid_: Source Tenant, modeled ownership, inferred Connection

**Active Tenant**:
The Tenant chosen as the current Workbench authorization and navigation scope.
It determines visible metadata, Models, and Tenant Lock state without selecting a Model.
_Avoid_: Current Model, selected GDS Connection

**Tenant Code**:
The unique human-readable natural key identifying a Tenant. It is distinct from
the server-generated Tenant ID and the descriptive Tenant name.
_Avoid_: Tenant ID, Tenant name

**Principal**:
One active internal identity representing either a user or an Entra service
principal. Authentication maps an Entra Tenant/Object pair to this record.
_Avoid_: User account when referring to both identity kinds

**Tenant Visibility**:
`global` permits every active authenticated Principal to read; `private`
requires Tenant access. Visibility never grants mutation authority.
_Avoid_: Public write access, open Tenant

**Tenant Role**:
One Tenant-scoped capability set: Viewer, Developer, Architect, or Tenant Admin.
_Avoid_: Global role, database role

**Super Admin**:
An explicit Principal flag granting all application authorization across active
Tenants without bypassing locks, revisions, audits, or operation boundaries.
_Avoid_: Database superuser, automatic workload admin

**Tenant Lock**:
The database-time lease that permits ordinary Tenant writes only for its exact
owning Principal. A different human or workload Principal is blocked until the
owner releases it, it expires, or an authorized Principal explicitly overrides
it with an audited reason. Acquisition is always an explicit Principal action.
_Avoid_: Tenant Lease token, lock Boolean, implicit override

**Tool Policy**:
One server-owned authorization category declared beside a tool:
Tenant Read, Tenant Metadata Write, Tenant Model Write, Tenant Lock Manage, or
Super Admin Only. Client input never chooses the policy.
_Avoid_: Caller role, per-tool role code

**MCP Tool Call Log**:
One append-only record for a completed MCP tool call containing bounded,
server-derived audit metadata and no raw input, output, prompt, or secret.
_Avoid_: Transcript, request dump, tool output log

**Model**:
The governed metadata aggregate that contains input scope, bindings, policy,
effective Sections, and one current revision.
_Avoid_: Project, workspace model

**Model Input Scope**:
The server-owned active set of physical Source or Bronze input Objects that a
Model can use. A Source Object may be used directly when it is accessible
through a foreign catalog and Bronze is skipped. Model-produced Silver and Gold
targets use Model Object Bindings; they are not inputs. Selected Scope controls
which eligible inputs participate. If equivalent Source and Bronze Objects are
both selected, Bronze is the default transformation input unless the user
directs otherwise.
_Avoid_: Selection, source list

**Selected Scope**:
The explicit subset of eligible Model Input Scope Objects chosen for one Section
workflow. It never changes Model Input Scope membership.
_Avoid_: Model Input Scope, source list

**Modeling Assertion**:
One Model-owned structured factual statement derived from a document, email,
meeting note, or direct user input. An applicable Assertion provides governed
context for Analysis, Conceptual, Logical, Dimensional, or Mapping but is not executable lineage.
_Avoid_: Modeling Evidence, fact, transient context

**Section**:
One versioned part of a Model change: Model Input Scope, Profiling, Assertion,
Analysis, Conceptual, Logical, Dimensional, Model Binding, Mapping, Code
Generation, or Validation.
_Avoid_: Phase document, payload type

**Model Change Set**:
The draft aggregate containing complete pending Model records grouped by dataset.
Validation evaluates them with the applied Model, and Apply commits the accepted
changes atomically. It never creates or updates physical metadata.
_Avoid_: Patch, transaction draft

**Metadata Change Set**:
The Tenant-owned draft aggregate for Source/Bronze/Silver/Gold Objects and
Attributes plus Copy and Process configuration. It never creates Model records.
_Avoid_: Model Change Set, foundational CRUD

**Reference Metadata**:
The operator-governed shared vocabulary that classifies metadata and constrains
accepted values. Workbench users may read it but do not author it.
_Avoid_: Tenant Metadata, user-managed lookup values

**Foundational Metadata**:
The operator-governed Projects, Tenants, Systems, and Connections that establish
ownership and access context. Workbench users may read it but do not author it.
_Avoid_: Tenant Metadata, user-editable platform configuration

**Target Registration**:
The governed establishment of Silver or Gold Object and Attribute metadata for
a future Model Object Binding through a Metadata Change Set. It neither deploys
targets nor describes source transformations.
_Avoid_: Target deployment, Mapping

**Model Object Binding**:
The Model-owned identity binding from one modeled Entity to one
already-registered physical target Object: Logical to Silver or Dimensional to
Gold.
_Avoid_: Mapping, Model Input Scope, target deployment, Model Realization

**Model Attribute Binding**:
The Model-owned identity binding from one modeled Attribute to one
already-registered physical target Attribute under a Model Object Binding.
Every target Attribute, including audit, technical, or constant-valued
Attributes, has a corresponding modeled Attribute and Model Attribute Binding.
_Avoid_: Mapping Attribute, Attribute Realization

**Model Binding**:
The Workflow Target that creates Logical-to-Silver or Dimensional-to-Gold Model
Object and Model Attribute Bindings after the physical target metadata has been
applied. It uses a Model Change Set and never registers metadata or describes
source transformations. In the standard path, the agent deterministically
resolves the exact Target Registration intent against a fresh Metadata Snapshot;
a missing or ambiguous target blocks the binding.
_Avoid_: Target Registration, Mapping, Model Realization

**Pending Record**:
One complete proposed record that inserts, updates, reactivates, or explicitly
deactivates an applied record. It is neither a field patch nor a complete future
dataset copy. Unresolved review uncertainty is local workflow state; a generated
record proceeding toward Apply uses an actionable record state rather than a
persisted `needs_review` state.
_Avoid_: Patch row, full dataset replacement

**Relationship Inference**:
A local, non-persisted hypothesis about possible physical relationships derived
from Snapshot metadata, profiles, Assertions, and existing Analysis Results. It
does not claim referential-integrity validation or create an Analysis Result.
_Avoid_: Analysis Result, validated relationship

**Conceptual Model**:
A compact business view of the important concepts in scope and their business
relationships. One concept may group evidence from many physical Objects,
Systems, and Assertions. It does not define Attributes, keys, normalization, or
an expected one-to-one correspondence with physical Objects or Logical Entities.
A relationship may record high-level business cardinality when supported by
business evidence; otherwise its cardinality remains unknown. Cardinality never
infers keys or dictates Logical structure.
_Avoid_: Table inventory, Logical Model, one concept per Object

**Coverage Loop**:
The internal accounting loop that classifies every selected input as represented
by one or more results, context only, explicitly excluded with a reason, or
blocked. It proves coverage without imposing output count or a one-to-one
projection from inputs to authored records.
_Avoid_: Output quota, one record per source

**Logical Model**:
A normalized representation driven primarily by in-scope physical Objects and
Attributes. Profiles, Analysis Results, Conceptual records, and Assertions add
context and improve quality but do not drive its structure. It is also the
complete modeled contract for its Silver target binding, including audit and
constant-valued Attributes when those columns exist physically.
_Avoid_: Conceptual decomposition, physical copy

**Dimensional Model**:
An optional business-process and grain-oriented Model layer containing Facts,
Dimensions, Bridges, Attributes, and Relationships. Its physical inputs are
eligible Silver Objects with active Model Object Bindings populated through
applied Logical Mapping.
_Avoid_: Mandatory Logical projection, Mapping prerequisite

**Logical Mapping**:
The target-oriented transformation rules that populate the Silver Object in an
active Logical Model Object Binding from bounded Source or Bronze Objects. It
does not create the binding.
_Avoid_: Logical Section, Silver deployment

**Mapping Transformation Document**:
The flexible JSON transformation description for a Mapping Object or Attribute.
PostgreSQL guarantees only valid JSON storage. An attached Output Template is
advisory authoring guidance rather than a database or server validation schema.
Without a Template, the agent uses the standard plugin JSON format automatically
unless the user requests another format.
_Avoid_: Hard-coded Mapping package schema, executable code

**Dimensional Mapping**:
The target-oriented transformation rules that populate the Gold Object in an
active Dimensional Model Object Binding from eligible Silver Objects. It does
not create the binding.
_Avoid_: Dimensional Section, Gold deployment

**Stage Batch**:
A Change-Set-owned, revision-bound transport manifest whose ordered typed chunks
are invisible to validation and Apply until one atomic Commit replaces a
complete dataset. Ordinary datasets use complete record chunks. Generated Code
may instead use JSON byte fragments that Commit reassembles into one complete
Code record; fragment boundaries never become Model state.
_Avoid_: Append Stage, file upload, partial dataset

**Local Reference**:
A typed, Change-Set-scoped identity for a proposed record that has no database
ID yet. Apply resolves it to a server-generated ID; it never persists.
_Avoid_: Temporary database ID, client-generated database ID, name reference

**Candidate**:
An uncommitted workflow result that can become one or more Model Change Set Sections after validation.
_Avoid_: Agent answer, model output

**Workflow Run**:
One durable, Tenant-owned execution request created by an authorized human or
registered workload Principal. Runs move from queued to running to one terminal
state. At most one Workflow Run may be running for a Tenant at a time.
_Avoid_: Job, session

**Plugin Authoring Path**:
The primary developer-facing GDS authoring path, delivered through an
open-standard plugin and used mainly in VS Code. It provides interactive access
through MCP and persists accepted results through governed Change Sets.
_Avoid_: Only GDS workflow, web replacement

**Web Authoring Path**:
The non-plugin GDS authoring path for users who need a guided web experience. It
executes independent durable Workflow Runs using its configured Foundry or
Databricks models and persists accepted results through governed Change Sets.
_Avoid_: Simplified workflow, secondary workflow logic

**Authoring Parity**:
The requirement that Plugin and Web Authoring Paths follow the same domain
dependencies, persisted record contracts, Change Set boundaries, and Apply
rules. They use separate agents and orchestration, and their generated content
need not be identical.
_Avoid_: Shared agent runtime, identical generated output

**GDS Work Session**:
One Tenant-bound, resumable body of related user-directed work. It may have no
Model for metadata-only work or bind to exactly one Model. Once bound, its Model
cannot change. It may span multiple GDS focus areas, Workflow Targets, and
governed drafts within that boundary.
_Avoid_: Workflow Run, chat, permanent workspace

**GDS Interaction Mode**:
One explicit collaboration style for a GDS request: Quick, Guided, Automatic,
Custom, or Grill With Docs. It changes depth and checkpoint behavior without
changing Workflow Targets, governance, or Apply boundaries.
_Avoid_: Workflow Target, execution permission

**Quick Mode**:
Small, bounded GDS work without a complete-coverage promise. Any mutation still
uses the normal session, Change Set, validation, and approval boundaries.
_Avoid_: Ungoverned edit, Automatic Mode

**Guided Mode**:
GDS work that pauses at meaningful semantic checkpoints selected for the active
Workflow Target or Section.
_Avoid_: Step-by-step tool narration, mandatory pause after every record

**Automatic Mode**:
GDS work that makes supported local decisions and continues through the selected
scope without optional pauses. It still stops for blockers, Snapshot handoffs,
the local review handoff, Stage, Apply, and Workflow Target boundaries.
_Avoid_: Unattended Apply, evidence-free decisions

**Custom Mode**:
A user-defined GDS workflow shape for work that does not fit the standard
interaction patterns. It never relaxes domain or governance rules.
_Avoid_: Bypass mode, arbitrary execution

**Grill With Docs Mode**:
A lazily loaded interactive mode that examines any GDS request branch by branch,
asks one focused question at a time, and updates agreed local documentation as
shared understanding develops. It may support any Workflow Target or discovery
work but is never itself a Workflow Target. The agent chooses a lightweight
session document or ADR appropriate to the discussion and may promote accepted
conclusions into governed records or artifacts.
_Avoid_: Grill Workflow Target, unstructured brainstorming

**GDS Workflow Target**:
One user-selected bounded outcome with at most one authoritative Apply boundary.
It never advances automatically into another Workflow Target.
_Avoid_: Model Section, focus area, end-to-end build

**Resolution Prompt**:
A concise GDS-generated handoff describing a blocked package, its evidence, the
required upstream Workflow Target, and the exact resume point.
_Avoid_: Automatic repair, error dump, raw prompt

**Code Artifact**:
One Model-owned SQL file, Python file, or Python notebook generated for one
bound target Object. A target may have multiple Code Artifacts, distinguished
by Artifact Name. It is proposed and applied through the Code Generation
Section. Its content and digest are Model state; applying it never executes or
deploys the artifact. It has no separate domain-size cap; transport batching
does not split it into multiple Model records. Each artifact records the source
Systems whose applied Mapping contributed to it. The server derives one Code
Input Digest from its Mapping and input context and one Generated Code Digest
from its exact content; neither is authored by the agent or user.
_Avoid_: Process, deployment, executed code

**Artifact Name**:
The file name that distinguishes Code Artifacts for the same bound target
Object. The external deployment path is supplied later through Process metadata.
_Avoid_: Artifact key, deployment path, Process executable

**Code Handoff**:
The manual boundary after Code generation and optional Process metadata
authoring. The user places Code Artifacts at the supplied external paths and
starts the Orchestration Layer. Runtime errors return as explicit input for a
later Code correction.
_Avoid_: Automatic deployment, pipeline execution, trigger management

**Orchestration Layer**:
The external runtime that owns triggers, dependency execution, and physical
loads. GDS Workbench can author Code and Process metadata but does not operate
this runtime.
_Avoid_: GDS Workbench, Code Generation, MCP execution

**Mapping Code Generation**:
The Workflow Target that creates one or more Code Artifacts per selected bound
target Object from applied Mapping, then hands the Candidate to a
governed Model Change Set. Apply advances the Model revision. Generation never
executes or deploys code.
_Avoid_: Mapping Section, local-only code, code execution

**Validation Group**:
One Model-owned Validation Authoring grouping for a Tenant and System. It contains related
Validation Checks and uses applied Mapping plus any current relevant Code
Artifacts as authoring context. Code may be absent.
_Avoid_: server validation phase, Workflow Run group

**Validation Check**:
One deterministic validation definition containing Query A, optional Query B or a
literal operand, and an explicit comparison contract. It stores authoring
intent; storing or applying it never executes it. A governed authoring policy
may separately preflight the SQL and report the outcome locally. Execution
results and sampled physical rows are not Model state.
_Avoid_: Model Change Set validation, agent judgment at runtime

**Validation Authoring**:
The Workflow Target that derives Validation Groups and Validation Checks from
applied Mapping, any current relevant Code Artifacts when present, and explicit
user input, then hands the Candidate to a governed Model Change Set. Apply
advances the Model revision. Validation Authoring may occur before physical loads. A
governed SQL preflight may check syntax and shape, but absent loaded data does
not invalidate authored checks and cannot prove their functional result. Operational
execution is a separate concern.
_Avoid_: QA, Validate, server validation, Profiling

**Change Set Validation**:
The authoritative server gate that validates one exact Metadata or Model Change
Set revision and candidate digest before Apply. It does not execute Validation
Checks or judge loaded data.
_Avoid_: Validation Authoring, SQL Preflight

**SQL Preflight**:
An optional bounded execution used during Code or Validation Authoring to check
SQL syntax and result shape. Its outcome and sampled rows are local evidence,
not Model state or proof that a functional Validation Check passes.
_Avoid_: Validation Check execution, Change Set Validation

**Local Review Handoff**:
The notification after a locally complete Candidate is ready for human
inspection. GDS Workbench opens once for the Work Session and remains pointed at
that session; the user refreshes it to see the latest local contents. When work
is ready, the agent only notifies the user to inspect it. The user may edit in
Workbench, ask the agent for changes, or say `proceed`. There is no user-facing
Review operation, command, or state. An unambiguous positive acknowledgement,
including `proceed` or `OK`, accepts the current exact contents and permits
acquiring an ordinary free Tenant Lock, reconciliation, Stage, and Change Set
validation. Lock override and Apply require separate explicit approval.
Reconciliation requires the authoritative revision to still match the revision
used by the local Snapshot. A mismatch stops the workflow: the user downloads
the fresh Snapshot from the MCP tool result and replaces the affected local
Snapshot area. The agent reassesses the Candidate without attempting an
automatic merge. It never repeats a temporary signed URL in chat. If
reassessment changes Candidate contents, the agent notifies the user to refresh
and inspect them again; otherwise the prior instruction to proceed remains
valid. Internal validation and state tracking may support this behavior but
must not add review ceremony.
_Avoid_: Review phase, review record, server approval

**GDS Workbench**:
The local-only interface for inspecting immutable Snapshots, editing local
Change Sets, and performing preliminary validation. It has no authority to
Stage, validate a Change Set on the server, Apply, or otherwise change server
state.
_Avoid_: Server Change Set client, deployment interface

**Workbench Schema Compatibility**:
A governed schema change is complete only when GDS Workbench can display, edit,
and locally validate its eligible records. Snapshot JSON Schemas remain the
source for fields and form controls; canonical keys, cross-record domain checks,
and Workbench tests must change with the governing schema when affected.
_Avoid_: Separate Workbench schema, display-only compatibility

**Workflow Authoring Guide**:
Plugin instructions for one GDS Workflow Target that explain required context,
field ownership and population, coverage loops, validation expectations,
blockers, review handoff, and the next eligible target. Guides cover metadata,
Profiling, Analysis, Conceptual, Logical, Dimensional, Target Registration,
Model Binding, Mapping, Code Generation, Validation Authoring, and later Process
registration without replacing authoritative server validation.
_Avoid_: Prompt dump, duplicate database policy, optional workflow decoration

**Default Model Naming**:
The advisory naming convention used unless the user or Model policy supplies an
override. Conceptual, Logical, and Dimensional names use PascalCase. Logical
identifier Attributes end in `ID`, with both letters capitalized. Dimensional
key Attributes end in `Key`. These are authoring-quality rules in Workflow
Authoring Guides, not database integrity constraints.
_Avoid_: Mandatory database casing rule, `Id` suffix, user override rejection

**Local Validation Override**:
An explicit human acceptance of exact local Change Set contents despite
preliminary validation findings. It never bypasses authoritative server
validation or permits Apply.
_Avoid_: Server validation bypass, Apply approval

**Actor Kind**:
The server-derived `human` or `workload` classification used to project the MCP
tool and contract-resource inventory. Client-declared metadata never selects it.
_Avoid_: Client mode, audience hint

**Notebook Definition**:
The notebook-owned model, reasoning, prompt, tool, and workflow configuration compiled once at notebook startup.
_Avoid_: Profile registry, release asset

**Model Snapshot**:
The immutable, bounded Model context archive returned through MCP for one workflow.
_Avoid_: Dump, export

**Metadata Snapshot**:
An immutable, bounded Source Tenant metadata archive containing registered
physical metadata regardless of Model Object Binding. It is delivered outside the
MCP tool result so an agent can inspect it without filling its context.
_Avoid_: Model Snapshot, metadata dump, workflow snapshot

**Zone**:
The physical classification of an Object as exactly Source, Bronze, Silver, or
Gold.
_Avoid_: Modeling layer, inferred Connection type

**Verified Model Graph**:
The typed and indexed in-memory form of a verified Model Snapshot.
_Avoid_: Projection input, document map

**Mapping Transformation Document**:
The flexible JSON Mapping description for one bound target Object and source
System. An Output Template may guide its shape, but the database does not impose
a fixed functional schema.
_Avoid_: Mapping Package, fixed Mapping profile

**Apply Receipt**:
The immutable result that binds an applied Model Change Set to its revision, digest, and idempotent outcome.
_Avoid_: Apply response

**DBML Export**:
The immutable, revision-bound Conceptual and/or Logical visualization bundle
generated from effective Model Sections. An MCP client chooses where to save
the downloaded bundle; an authorized DBML Workflow Run may publish it only
beneath the deployment-owned Databricks Volume root.
_Avoid_: Database dump, server-local export, arbitrary path write
