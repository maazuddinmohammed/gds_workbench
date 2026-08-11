# GDS ETL Workbench

GDS ETL Workbench lets developers inspect governed metadata, prepare a complete Model change, validate it, and apply it through one controlled workflow.

## Language

**Tenant**:
The ownership scope for Principals, metadata, Models, and authorization.
_Avoid_: Customer, client, account scope

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
it with an audited reason.
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
The server-owned set of source Objects and Attributes that a Model can use.
_Avoid_: Selection, source list

**Modeling Assertion**:
One Model-owned structured factual statement derived from a document, email,
meeting note, or direct user input. An Assertion Record may durably support a
Conceptual, Logical, or Dimensional artifact.
_Avoid_: Modeling Evidence, fact, transient context

**Section**:
One versioned part of a Model change: Model Scope, Profiling, Assertion,
Analysis, Conceptual, Logical, Dimensional, or Mapping.
_Avoid_: Phase document, payload type

**Model Change Set**:
The draft aggregate that replaces whole Sections, validates one future Model graph, and applies atomically.
_Avoid_: Patch, transaction draft

**Metadata Change Set**:
The Tenant-owned draft aggregate for Source/Bronze/Silver/Gold Objects and
Attributes plus Copy and Process configuration.
_Avoid_: Model Change Set, foundational CRUD

**Candidate**:
An uncommitted workflow result that can become one or more Model Change Set Sections after validation.
_Avoid_: Agent answer, model output

**Workflow Run**:
One execution by an active registered workload Principal. The MCP server maps
the workload's Entra identity directly to its internal Principal.
_Avoid_: Job, session

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

**Verified Model Graph**:
The typed and indexed in-memory form of a verified Model Snapshot.
_Avoid_: Projection input, document map

**Profiling Run**:
The bounded execution and atomic-publication aggregate for Attribute profiles and failures.
_Avoid_: Profile job

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
