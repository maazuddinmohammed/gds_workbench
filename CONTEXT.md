# GDS ETL Workbench

GDS ETL Workbench lets developers inspect governed metadata, prepare a complete Model change, validate it, and apply it through one controlled workflow.

## Language

**Tenant**:
The ownership scope for Principals, metadata, Models, and authorization.
_Avoid_: Customer, client, account scope

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
The governed metadata aggregate that contains scope, policy, effective Sections, and one current revision.
_Avoid_: Project, workspace model

**Model Scope**:
The server-owned active set of physical Objects that a Model can use. Membership
is added, reactivated, or archived only through a governed Model Change Set.
_Avoid_: Selection, source list

**Selected Scope**:
The explicit subset of eligible Model Scope inputs chosen for one Section workflow.
It never changes Model Scope membership.
_Avoid_: Model Scope, source list

**Modeling Assertion**:
One Model-owned structured factual statement derived from a document, email,
meeting note, or direct user input. An applicable Assertion provides governed
context for Analysis, Conceptual, Logical, Dimensional, or Mapping but is not executable lineage.
_Avoid_: Modeling Evidence, fact, transient context

**Section**:
One versioned part of a Model change: Model Scope, Profiling, Assertion,
Analysis, Conceptual, Logical, Dimensional, or Mapping.
_Avoid_: Phase document, payload type

**Model Change Set**:
The draft aggregate containing complete pending Model records grouped by dataset.
Validation evaluates them with the applied Model, and Apply commits the accepted
changes atomically.
_Avoid_: Patch, transaction draft

**Metadata Change Set**:
The Tenant-owned draft aggregate for Source/Bronze/Silver/Gold Objects and
Attributes plus Copy and Process configuration.
_Avoid_: Model Change Set, foundational CRUD

**Reference Metadata**:
The operator-governed shared vocabulary that classifies metadata and constrains
accepted values. Workbench users may read it but do not author it.
_Avoid_: Tenant Metadata, user-managed lookup values

**Foundational Metadata**:
The operator-governed Projects, Tenants, Systems, Connections, and discovery
scope that establish ownership and access context. Workbench users may read it
but do not author it.
_Avoid_: Tenant Metadata, user-editable platform configuration

**Target Registration**:
The governed metadata registration of Silver or Gold Objects and Attributes for
an applied modeled layer. It neither deploys physical targets nor creates Mapping records.
_Avoid_: Target deployment, Mapping

**Pending Record**:
One complete proposed record that inserts, updates, reactivates, or explicitly
deactivates an applied record. It is neither a field patch nor a complete future
dataset copy.
_Avoid_: Patch row, full dataset replacement

**Relationship Inference**:
A local, non-persisted hypothesis about possible physical relationships derived
from Snapshot metadata, profiles, Assertions, and existing Analysis Results. It
does not claim referential-integrity validation or create an Analysis Result.
_Avoid_: Analysis Result, validated relationship

**Logical Model**:
A normalized representation driven primarily by in-scope physical Objects and
Attributes. Profiles, Analysis Results, Conceptual records, and Assertions add
context and improve quality but do not drive its structure.
_Avoid_: Conceptual decomposition, physical copy

**Dimensional Model**:
An optional business-process and grain-oriented Model layer containing Facts,
Dimensions, Bridges, Attributes, and Relationships. Its physical inputs are
eligible Silver contributions established by applied Logical Mapping.
_Avoid_: Mandatory Logical projection, Mapping prerequisite

**Logical Mapping**:
The Mapping route that binds applied Logical Entities and Attributes to
preregistered Silver Objects and Attributes. Its applied bindings establish the
Silver contributions eligible for Dimensional modeling.
_Avoid_: Logical Section, Silver deployment

**Dimensional Mapping**:
The Mapping route that binds applied Dimensional Entities and Attributes to
preregistered Gold Objects and Attributes. It is stored in the Mapping Section.
_Avoid_: Dimensional Section, Gold deployment

**Stage Batch**:
A Change-Set-owned, revision-bound transport manifest whose ordered typed chunks are
invisible to validation and apply until one atomic Commit replaces a complete dataset.
_Avoid_: Append Stage, file upload, partial dataset

**Local Reference**:
A typed, Change-Set-scoped identity for a proposed record that has no database
ID yet. Apply resolves it to a server-generated ID; it never persists.
_Avoid_: Temporary database ID, client-generated database ID, name reference

**Candidate**:
An uncommitted workflow result that can become one or more Model Change Set Sections after validation.
_Avoid_: Agent answer, model output

**Workflow Run**:
One execution by an active registered workload Principal. The MCP server maps
the workload's Entra identity directly to its internal Principal.
_Avoid_: Job, session

**GDS Work Session**:
One Tenant-bound, resumable body of related user-directed work. It may span
multiple GDS focus areas, Workflow Targets, and governed drafts.
_Avoid_: Workflow Run, chat, permanent workspace

**GDS Workflow Target**:
One user-selected bounded outcome with at most one authoritative Apply boundary.
It never advances automatically into another Workflow Target.
_Avoid_: Model Section, focus area, end-to-end build

**Resolution Prompt**:
A concise GDS-generated handoff describing a blocked package, its evidence, the
required upstream Workflow Target, and the exact resume point.
_Avoid_: Automatic repair, error dump, raw prompt

**Mapping Code Generation**:
A read-only Workflow Target that creates selected SQL or Python artifacts from
applied Mapping records. It neither changes server state nor executes generated code.
_Avoid_: Mapping Section, Mapping Apply, code execution

**GDS Workbench**:
The local-only interface for inspecting immutable Snapshots, editing local
Change Sets, and performing preliminary validation. It has no authority to
Stage, server-Validate, Apply, or otherwise change server state.
_Avoid_: Server Change Set client, deployment interface

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
An immutable, bounded Tenant metadata archive delivered outside the MCP tool
result so an agent can inspect selected metadata without filling its context.
_Avoid_: Model Snapshot, metadata dump, workflow snapshot

**Metadata Discovery Scope**:
The Tenant-owned lookup scope that lets a Metadata Snapshot discover otherwise
unrelated global-data-store Objects. It neither establishes nor restricts lineage.
_Avoid_: Model Scope, lineage mapping, authorization grant

**Zone**:
The physical classification of an Object as exactly Source, Bronze, Silver, or
Gold.
_Avoid_: Modeling layer, inferred Connection type

**Verified Model Graph**:
The typed and indexed in-memory form of a verified Model Snapshot.
_Avoid_: Projection input, document map

**Mapping Package**:
The complete normalized Mapping result for the approved target Object and source System pairs.
_Avoid_: Mapping payload, mapper output

**Apply Receipt**:
The immutable result that binds an applied Model Change Set to its revision, digest, and idempotent outcome.
_Avoid_: Apply response

**DBML Export**:
The immutable, revision-bound Conceptual and/or Logical visualization bundle
generated from effective Model Sections. An MCP client chooses where to save
the downloaded bundle; an authorized DBML Workflow Run may publish it only
beneath the deployment-owned Databricks Volume root.
_Avoid_: Database dump, server-local export, arbitrary path write
