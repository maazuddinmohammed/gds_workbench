# GDS ETL Workbench

Atlas provides a plugin and web application for governed metadata and data-model
authoring. Code, numbered SQL, and runtime schemas are authoritative. This file
fixes domain vocabulary; it does not duplicate field contracts or prompt bodies.

## Ownership and identity

| Term | Meaning |
| --- | --- |
| Lane | Foundational grouping of Tenants (`core.lane`); independent of a modeling Project. |
| Tenant | Ownership and authorization scope for metadata, Projects and Principals. |
| Active Tenant | Current navigation and authorization scope; it need not select a Project. |
| Source Tenant | `Object.source_tenant_id`: whose metadata/data an Object represents, independent of Connection placement. |
| Principal | One internal human or workload identity resolved from authenticated Entra identity. |
| Tenant Role | Viewer, Developer, Architect or Tenant Admin; roles are cumulative. |
| Super Admin | Explicit Principal capability across active Tenants; never bypasses locks, revisions or audit. |
| Tenant Lock | Database-time lease for one exact Principal. Ordinary writes require its ownership; override is explicit and audited. |
| Project Lock | Persistent read-only fence for all Project-owned records and workflows; only a human through the web UI or engineering SQL may toggle it. Metadata is independent. |
| Project | Tenant-owned aggregate: input scope, schema/policy settings, authored sections and current revision. |
| Project Input Scope | Saved eligible physical Source/Bronze Objects; it may span readable Source Tenants. |
| Selected Scope | Exact Objects or modeled Entities selected for one workflow; does not change Project Input Scope. |
| Modeled Entity | Logical or Dimensional Entity identified by Project, layer, schema and name; Attribute identity extends that key. |
| Zone | Source: original system; Bronze: ingested physical data; Silver: Logical output; Gold: Dimensional output. |

Source Objects use their source Connection. Bronze/Silver/Gold physical placement
uses the selected Source Tenant's active GDS Connection and that Connection's
Tenant/System keys. Never substitute source ownership for placement identity.
Project-generated executable coordinates use the Project Tenant's configured GDS
placement. Authoring an Entity does not register a physical Object.

Natural keys retain the complete Tenant/System/Connection/schema/Object/Attribute
path when physical identity requires it. Equal names in different schemas or
Systems are independent. Internal numeric IDs are not business identifiers.

## Evidence and modeling

| Term | Meaning |
| --- | --- |
| Profiling | Deterministic measurements for selected physical Attributes, over all rows or an explicit batch. |
| Attribute Profile | Current saved measurements with time/row-scope provenance; refresh replaces current measurements. |
| Metadata Enrichment | Runs after Profiling. Project-owned Object descriptions and Attribute descriptions, inferred types, natural/primary key, nullability and PII findings; human edits and locks stay Project-specific. Data Dictionary and Technical Data Dictionary export current saved results. |
| Ingestion Mapping | Registered Source-to-Bronze Object/Attribute lineage; source provenance cannot be guessed from names. |
| Analysis Result | Inferred relationship between real physical Attributes: endpoints, kind and inferred cardinality, with no stored reasoning. Inferred cardinality and measured validation remain separate. |
| Per-table Analysis | Analysis run that makes one one-shot call per selected table. Each call sees its table in full plus a key directory of every selected table, and returns only links that start in its table. A second link on an already linked column pair is dropped before the draft. |
| Context Type | Global read-only classification shared across Projects; defined by name and description. |
| Context Group | Project-owned collection of related knowledge with one Context Type, optional description and source System. |
| Context Record | Reusable requirement, source information, convention, decision or other knowledge. Contains a stable UUID, text, optional plain-text source reference, status and lock. Requirements are not proof that data exists. |
| Subject Area | Named business capability, such as Sales or Billing, over active Bronze Input Scope Objects; an Object may belong to several. It chooses the Objects one Logical or Dimensional Build call works on and is never modeling evidence. Unassigned Objects have no active membership and are not stored. |
| Build | Logical or Dimensional Run over ordered Subject Areas: one agent call per area, each seeing earlier areas' work, into one draft. The web app builds one area per Run, listing most-shared areas first; the backend accepts several. |
| Optimize | Logical or Dimensional Run over the whole applied model: cross-area links, merges of duplicates and type or name fixes. |
| Logical Model | Schema-qualified normalized Entities, Attributes and child-to-parent relationships supported by physical inputs or Context records. Entity types come from `reference.logical_entity_type`. |
| Dimensional Model | Schema-qualified dimensions, facts and bridges supported by applied Logical Entities/Attributes or Context records. Fact types come from `reference.dimensional_fact_type`. |
| Source Context | Business/physical source dictionary used to interpret evidence. Exact fields come from workflow input contracts. |
| GDS Context | Target platform placement and project configuration; not source business evidence. |

Logical and Dimensional SCD policies are independent Project settings (`type_1`,
`type_2`, or unspecified). Dimensional Type 1 overwrites mutable descriptors;
Type 2 preserves Dimension versions. Stable identity stays fixed; Fact/Bridge
behavior is unchanged. Runs freeze both policies and Mapping receives both.
Dimensional Attributes use the same natural-key, surrogate-key and audit flags as
Logical Attributes. Foreign-key meaning comes from relationships and configured
templates. Entity type, fact type and entity grain remain explicit. A relationship runs
from a child's foreign-key Attribute to its parent and is identified by that Attribute;
a Dimensional relationship is optional when that Attribute is nullable. There are no
Submodels, and every model record's lifecycle is its `is_active` flag. Attribute
definitions carry measure meaning, units and aggregation restrictions; there are
no separate attribute-role, aggregation, grain-component or change-behavior fields.
Project SCD policy owns history; per-column history exceptions are not represented.
Source mapping rationale describes each contribution without a separate source role.
Workflow records do not store AI-assigned confidence scores.
The combined Gold audit template includes standard surrogate/foreign key rules and
IsCurrentRecord/RecordStartTime/RecordEndTime columns for Type 2 Dimensions.
Blank audit settings use the shared PascalCase template: SourceSystemID BIGINT,
IsDataValid BOOLEAN, HashKey STRING, IsActive BOOLEAN, GDSBatchID BIGINT,
PipelineRunID STRING, CreatedDate/UpdatedDate TIMESTAMP, CreatedBy/UpdatedBy STRING.
These audit fields default nullable; history current/start fields are required and
end time nullable. History fields follow SourceSystemID, before GDSBatchID. The orchestrator
projects these columns; agents cannot omit them. Settings display effective defaults
and allow per-Project overrides or reset; an explicit empty audit column list disables common audit fields.
Existing saved Projects change only through reviewed authoring, never a backfill.

Subject Areas only choose Objects, in both web and Atlas workflows. Their records
never feed Logical or Dimensional authoring as evidence. A Logical Build call uses its
area's physical metadata, enrichment, Profiles, Analysis and Context records plus the
Entities already built; a Dimensional Build call uses the area's Logical Entities and
their supporting evidence. Logical coverage defaults to 70% of the area's distinct
Objects; Dimensional coverage defaults to 60% of its Logical Entities, rounding counts up.
Physical Attributes may be selected, consolidated or omitted for the Logical
design; included Attributes still require valid references and source evidence.
Consolidation may map several physical inputs to one modeled record. Existing
active applied coverage counts alongside new mappings. Below target, missing-source
feedback triggers the configured repair attempts. Each layer has a Project-owned
Enforce coverage threshold switch, default off. After the final attempt, enabled
enforcement rejects below-target candidates; disabled enforcement returns otherwise
valid partial coverage with a warning. Other validation failures always block handoff.
Analytical Attribute selection and aggregation remain valid.

Missing information, measured zero, failed validation and contradictory evidence
are different states. Preserve each. A Context Record can explain required behavior;
it cannot invent physical columns or executable lineage. Inferred reasoning must
not replace observed validation results. Assess relevance at the current grain.
Prompt Attribute context preserves registered natural-key metadata separately from
Project enrichment. Unknown enrichment never erases registered evidence; disagreement
remains visible, and neither flag alone proves measured uniqueness.

## Mapping, Code and Validation

**Mapping** belongs to a modeled Entity and contributing source System. Its Object
transformation describes sources, rowset, filters and stages; Attribute documents
describe field expressions and sources. Output Templates define advisory document
fields. Custom documents remain opaque, complete JSON; their field names do not
acquire default-template semantics automatically.

Partial Mapping is valid authoring progress. Regeneration clears omitted selected,
unlocked transformations. Locked/unselected records remain intact. Protect existing
Object logic when any child Attribute is protected. Missing transformations are
blank, never fabricated to satisfy a coverage count.
Generated-key/framework-only notes do not establish a contributing source System.
Manual Mapping editing selects eligible Object sources before Attribute sources,
preserves custom JSON, and uses the same locks and revision-fenced review writes.

**Code Artifact** is an Entity-owned named file plus explicit source-System
assignments. Storage is `table` (inline content) or `git` (optional inline content
and nullable free-form repository, commit/path, entry-point and JSON parameters).
The web workflow still generates table-stored SQL only. Code consumes applied Mapping
and its template definitions. Partial
Mapping may produce reviewed SQL with typed-null or zero-row placeholders and
warnings. A current input digest does not prove runnable business logic.
Generated surrogate keys are database-owned; separately named source identifiers
remain Mapping-owned. The external orchestration layer owns loads and merges.

**Validation Group / Check** stores deterministic query/comparison definitions.
Validation authoring consumes complete Mapping and relevant current Code when
available. Apply never executes these definitions or stores physical query results.
**Change Set Validation** checks candidate/project integrity; **SQL Preflight** is a
separate governed bounded query check. Neither proves all business results.

**Target Registration** is optional export of applied Logical/Dimensional Entities
to Silver/Gold metadata, followed by Metadata Change Set review and Apply. It is
not a prerequisite for Mapping or Code. **Code Handoff** is manual file placement
and external orchestration, requiring separate authorization.

Analysis Excel export includes all findings matching the active filters, fenced to
the current Project revision. Databricks DDL downloads use applied active Logical or
Dimensional fields.
Downloads do not execute SQL or change physical metadata. Agent call/transport
timeout defaults to 120 minutes; an explicit configured override wins. This limits
each model call, not total Workflow Run duration. Provider credentials refresh
before requests, retries and tool turns; worker claim heartbeats remain independent.
Long runs still require a valid Tenant Lock through completion.

## Governed work

| Term | Meaning |
| --- | --- |
| Section | An authored Project area with a shared Snapshot/Change Set contract. |
| Candidate | Uncommitted workflow output; validation and review precede Apply. |
| Project Change Set | Revision-fenced draft for Project scope and authored sections. |
| Metadata Change Set | Governed draft for physical metadata registration/changes. |
| Snapshot | Immutable authorized metadata/project export, with versioned schemas, natural keys and stable Context Record UUIDs; Project snapshots pin a revision. |
| Local Reference | Typed draft-local identity for a new record; Apply resolves the server-generated ID where that record type uses one. Context Records keep their draft-created UUID as the saved identity. |
| Stage Batch | Atomic bounded transport for replacing complete datasets. Code fragments reassemble into complete records before validation. |
| Workflow Run | Durable queued/running/terminal execution. At most one runs per Tenant, independently of Tenant Lock ownership. The run owner holding the Tenant Lock can cancel queued/running runs; cancellation revokes the claim and retains saved results. |
| Prompt Template | Versioned system/instruction text, selected variables and readers. Runs freeze their effective published versions. |
| Default Prompt | Published assignment resolved through supported scope/default rules; editing seed files does not update an installed database. |
| Apply Receipt | Durable result of explicit governed Apply, including resulting revision and idempotent replay identity. |
| DBML Export | Local display of the effective Project graph, not executable database deployment. |

Plugin and web use the same persisted contracts and governed Change Sets, with
independent orchestration. Plugin Profiling runs deterministically in the MCP
backend: start, status, cancel, then refresh the Project Snapshot. The web
application never calls MCP internally.
Plugin Project enrichment and allowed settings use the existing reviewed Project Change Set.
Project names and web-agent defaults are not plugin-editable. Pending enrichment and
analysis may feed subsequent local design before one related submission.
A stale Snapshot/revision requires refresh and reassessment. Project-owned authored
state, physical metadata, and external deployment remain separate boundaries.

See [architecture](docs/architecture/overview.md), [decisions](docs/architecture/decisions.md),
[workflows](docs/workflows.md), and [security](docs/security.md).

## Orchestration metadata

A pipeline trigger selects one Tenant and a comma-separated list of Systems.
Omitting Copy Groups selects all applicable groups within each selected System;
supplied groups restrict that selection. A Member Group is an optional filter for
a Copy Group, associated through Copy Group Control in the same Tenant/System.
Use Member Groups only when explicitly requested; keep ordinary controls' Member
Group null. Member rows supply the code and attribute name for that filter.
Their natural key is Member Group + Member Code. This metadata describes inputs
to the external orchestration framework; authoring it does not run a pipeline.

Nullable JSONB `value` stores optional additional details on Object, Attribute,
Copy, Process, Copy Group, Process Group, Member Group, Member, Tenant, System,
Connection and Connection Location. It has no implicit execution semantics.
Preserve existing details; populate only when requested. Never store credentials
or secret references there. Foundational records remain read-only in authoring.

Project coverage settings are whole percentages from 1–100, stored with database
defaults of 70 for Logical and 60 for Dimensional. Independent enforcement switches
default false. Run context and validation use the same saved settings. Gold settings
expose one audit template including generated
key and Type 2 history rules; older separate stored rules remain readable. Type 2
history fields are audit Attributes immediately after SourceSystemID and before
GDSBatchID. Surrogate and foreign keys retain their key semantics.
