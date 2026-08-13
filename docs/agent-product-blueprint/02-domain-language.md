# Domain language

> Historical planning detail. Workflow Grant terminology below is superseded by
> [ADR 001](../adr/001-direct-principal-authorization-and-tenant-locks.md) and
> is not present in the current database.

Use these names consistently. They encode ownership and workflow boundaries.

## Core concepts

| Term | Meaning | Do not substitute |
|---|---|---|
| Project | Foundational parent of one or more Tenants | Product Model |
| Tenant | Visibility and ownership boundary for Principals, metadata, Models, and authorization | Customer, client, workspace |
| Principal | Registered application actor: a user or service principal | User account |
| Tenant Access | One Principal's active, optionally expiring Tenant role | Membership |
| System | Business or technical source system | Connection |
| Connection | Tenant-owned link to a System; owns physical Objects and profiling batch policy | Credential |
| Object | Registered physical Bronze, Silver, or Gold object | Model entity |
| Attribute | Stable physical child of an Object | Modeled attribute unless qualified |
| Ingestion Mapping | Original-source to Bronze Object or Attribute lineage | Modeling Mapping |
| Model | Governed aggregate containing Scope, policies, effective Sections, and one current revision | Project, workspace model |
| Model Scope | Server-owned set of Bronze Objects and Attributes a Model may use | Selection, source list |
| Selected Scope | Explicit subset requested for one run | Model Scope |
| Impact Scope | Selected items plus required dependants | Selection |
| Modeling Assertion | Model-owned document metadata and structured factual Assertion Records that may persist as artifact support | Modeling Evidence, fact |
| Section | One versioned part of a Model: Assertion, Analysis, Conceptual, Logical, Dimensional, or Mapping | Patch, payload type |
| Model Change Set | Model-owned eight-document draft that validates one future graph and applies atomically | Patch, transaction draft |
| Metadata Change Set | Tenant-owned sixteen-document draft for physical metadata and Copy/Process configuration | Model Change Set |
| Candidate | Uncommitted workflow result that may become one or more draft Sections | Agent answer |
| Apply Receipt | Immutable result binding a change set to its digest, generated IDs, revision, and replay outcome | Apply response only |

## Workflow concepts

| Term | Meaning |
|---|---|
| Workflow Grant | Server-created authorization binding one initiating user Principal, one workload service Principal identity, Model, workflow, request, allowed operations, deployment, and expiry |
| Workflow Run | One execution under a Workflow Grant |
| Workflow Control | Three non-MCP human operations: authorize, revoke, and safe status |
| Actor Kind | Server-derived `human` or `workload`; client metadata cannot choose it |
| Notebook Definition | Notebook-owned model, prompt, tool, phase, retry, and limit configuration compiled once at startup |
| Model Snapshot | Immutable, bounded, revisioned Model context archive returned through MCP |
| Verified Model Graph | Typed and indexed in-memory form of a verified Model Snapshot |
| Profiling Run | Durable execution and atomic-publication aggregate for Attribute profiles and failures |
| Mapping Package | Complete normalized Mapping result for one target Object and source System pair |
| DBML Export | Immutable revision-bound Conceptual or Logical visualization bundle |

## Modeling layers

- **Analysis** records candidate Attribute-level relationships between Bronze
  Objects and their deterministic physical validation.
- **Conceptual** records stable business Objects, Relationships, and typed
  Object/Assertion Support.
- **Logical** records implementation-oriented Silver submodels, entities,
  Attributes, relationships, memberships, and Bronze/Assertion source mappings.
- **Dimensional** records Gold facts, dimensions, bridges, Attributes,
  relationships, memberships, and Silver/Assertion source mappings.
- **Mapping** binds Logical entities to Silver targets or Dimensional entities
  to Gold targets, with transformation and generator metadata.

Bronze Object IDs are the canonical source identity for modeling. Original
source Objects remain provenance through Ingestion Mapping.

## Lifecycle and intent

Applied artifacts use exactly:

- `active`
- `needs_review`
- `inactive`
- `deprecated`

`active` and `needs_review` are effective. The shared reconciler vocabulary is
`create`, `update`, `unchanged`, `reactivate`, `needs_review`, `inactivate`, and
`deprecate`. Each workflow narrows that set: Analysis permits only its defined
subset, while Mapping rows use `create`, `update`, or `unchanged`
dispositions. Application compilation converts allowed intents to Section
operations. Omission always means unchanged; it never means retire.

## State vocabularies

- Model Change Set: `active`, `validated`, `applied`, `expired`, `discarded`,
  `superseded`.
- Workflow Grant: `pending`, `active`, `revoked`, `expired`, `completed`.
- Workflow Run Summary: `pending`, `running`, `awaiting_validation`,
  `completed`, `completed_with_warnings`, `blocked`, `failed`, `expired`,
  `revoked`.
- Profiling Run: `running`, `completed`, `completed_with_warnings`, `failed`,
  `expired` in durable PostgreSQL state.

Primary source: [`CONTEXT.md`](../../CONTEXT.md). Exact enums are in
[`domain/entities.py`](../../mcp_server/src/gds_etl_workbench/domain/entities.py)
and the numbered SQL files.
