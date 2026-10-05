# GDS ETL Workbench

Atlas provides a plugin and web application for governed metadata and data-model
authoring. Code, numbered SQL, and runtime schemas are authoritative. This file
fixes domain vocabulary; it does not duplicate field contracts or prompt bodies.

## Ownership and identity

| Term | Meaning |
| --- | --- |
| Tenant | Ownership and authorization scope for metadata, Models and Principals. |
| Active Tenant | Current navigation and authorization scope; it need not select a Model. |
| Source Tenant | `Object.source_tenant_id`: whose metadata/data an Object represents, independent of Connection placement. |
| Principal | One internal human or workload identity resolved from authenticated Entra identity. |
| Tenant Role | Viewer, Developer, Architect or Tenant Admin; roles are cumulative. |
| Super Admin | Explicit Principal capability across active Tenants; never bypasses locks, revisions or audit. |
| Tenant Lock | Database-time lease for one exact Principal. Ordinary writes require its ownership; override is explicit and audited. |
| Model Lock | Persistent read-only fence for all Model-owned records and workflows; only a human through the web UI or engineering SQL may toggle it. Metadata is independent. |
| Model | Tenant-owned aggregate: input scope, schema/policy settings, authored sections and current revision. |
| Model Input Scope | Saved eligible physical Source/Bronze Objects; it may span readable Source Tenants. |
| Selected Scope | Exact Objects or modeled Entities selected for one workflow; does not change Model Input Scope. |
| Modeled Entity | Logical or Dimensional Entity identified by Model, layer, schema and name; Attribute identity extends that key. |
| Zone | Source: original system; Bronze: ingested physical data; Silver: Logical output; Gold: Dimensional output. |

Source Objects use their source Connection. Bronze/Silver/Gold physical placement
uses the selected Source Tenant's active GDS Connection and that Connection's
Tenant/System keys. Never substitute source ownership for placement identity.
Model-generated executable coordinates use the Model Tenant's configured GDS
placement. Authoring an Entity does not register a physical Object.

Natural keys retain the complete Tenant/System/Connection/schema/Object/Attribute
path when physical identity requires it. Equal names in different schemas or
Systems are independent. Internal numeric IDs are not business identifiers.

## Evidence and modeling

| Term | Meaning |
| --- | --- |
| Profiling | Deterministic measurements for selected physical Attributes, over all rows or an explicit batch. |
| Attribute Profile | Current saved measurements with time/row-scope provenance; refresh replaces current measurements. |
| Metadata Enrichment | Runs after Profiling. Model-owned Object descriptions and Attribute descriptions, inferred types, natural/primary key, nullability and PII findings; human edits and locks stay Model-specific. Data Dictionary and Technical Data Dictionary export current saved results. |
| Ingestion Mapping | Registered Source-to-Bronze Object/Attribute lineage; source provenance cannot be guessed from names. |
| Analysis Result | Inferred relationship between real physical Attributes, including reasoning and confidence. Inferred cardinality and measured validation remain separate. |
| Modeling Assertion | Persisted contextual statement, requirement, KPI/reporting need or source fact with document provenance. Requirements are not proof that data exists. |
| Conceptual Model | Business concepts and relationships supported by physical evidence or Assertions. |
| Logical Model | Schema-qualified normalized Entities, Attributes and relationships supported by physical inputs or Assertions. |
| Dimensional Model | Schema-qualified dimensions, facts and bridges supported by applied Logical Entities/Attributes or Assertions. |
| Source Context | Business/physical source dictionary used to interpret evidence. Exact fields come from workflow input contracts. |
| GDS Context | Target platform placement and model configuration; not source business evidence. |

Logical and Dimensional SCD policies are independent Model settings (`type_1`,
`type_2`, or unspecified). Dimensional Type 1 overwrites mutable descriptors;
Type 2 preserves Dimension versions. Stable identity stays fixed; Fact/Bridge
behavior is unchanged. Runs freeze both policies and Mapping receives both.
Blank Gold technical settings use standard surrogate/foreign keys and
IsCurrentRecord/RecordStartTime/RecordEndTime columns for Type 2 Dimensions.
Blank audit settings use the shared PascalCase template: SourceSystemID BIGINT,
IsDataValid BOOLEAN, HashKey STRING, IsActive BOOLEAN, GDSBatchID BIGINT,
PipelineRunID STRING, CreatedDate/UpdatedDate TIMESTAMP, CreatedBy/UpdatedBy STRING.
These audit fields default nullable; history current/start fields are required and
end time nullable. History fields precede the common audit fields. The orchestrator
projects these columns; agents cannot omit them. Settings display effective defaults
and allow per-Model overrides or reset; explicit empty audit columns disable audits.
Existing saved Models change only through reviewed authoring, never a backfill.

Missing information, measured zero, failed validation and contradictory evidence
are different states. Preserve each. An Assertion can explain required behavior;
it cannot invent physical columns or executable lineage. Saved Analysis confidence
must not replace observed validation results. Assess relevance at the current grain.

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
assignments. Code consumes applied Mapping and its template definitions. Partial
Mapping may produce reviewed SQL with typed-null or zero-row placeholders and
warnings. A current input digest does not prove runnable business logic.
Generated surrogate keys are database-owned; separately named source identifiers
remain Mapping-owned. The external orchestration layer owns loads and merges.

**Validation Group / Check** stores deterministic query/comparison definitions.
Validation authoring consumes complete Mapping and relevant current Code when
available. Apply never executes these definitions or stores physical query results.
**Change Set Validation** checks candidate/model integrity; **SQL Preflight** is a
separate governed bounded query check. Neither proves all business results.

**Target Registration** is optional export of applied Logical/Dimensional Entities
to Silver/Gold metadata, followed by Metadata Change Set review and Apply. It is
not a prerequisite for Mapping or Code. **Code Handoff** is manual file placement
and external orchestration, requiring separate authorization.

Analysis Excel export includes all findings matching the active filters, fenced to
the current Model revision. Databricks DDL downloads use applied active Logical or
Dimensional fields; Conceptual downloads use one export-only ConceptID per concept.
Downloads do not execute SQL or change physical metadata. Agent call/transport
timeout defaults to 60 minutes (previously 15); an explicit configured override wins.

## Governed work

| Term | Meaning |
| --- | --- |
| Section | An authored Model area with a shared Snapshot/Change Set contract. |
| Candidate | Uncommitted workflow output; validation and review precede Apply. |
| Model Change Set | Revision-fenced draft for Model scope and authored sections. |
| Metadata Change Set | Governed draft for physical metadata registration/changes. |
| Snapshot | Immutable authorized metadata/model export, with versioned schemas and natural keys; Model snapshots pin a revision. |
| Local Reference | Typed draft-local identity for a new record; Apply resolves the server-generated ID. |
| Stage Batch | Atomic bounded transport for replacing complete datasets. Code fragments reassemble into complete records before validation. |
| Workflow Run | Durable queued/running/terminal execution. At most one runs per Tenant, independently of Tenant Lock ownership. The run owner holding the Tenant Lock can cancel queued/running runs; cancellation revokes the claim and retains saved results. |
| Prompt Template | Versioned system/instruction text, selected variables and readers. Runs freeze their effective published versions. |
| Default Prompt | Published assignment resolved through supported scope/default rules; editing seed files does not update an installed database. |
| Apply Receipt | Durable result of explicit governed Apply, including resulting revision and idempotent replay identity. |
| DBML Export | Local display of the effective Model graph, not executable database deployment. |

Plugin and web use the same persisted contracts and governed Change Sets, with
independent orchestration. Plugin Profiling runs deterministically in the MCP
backend: start, status, cancel, then refresh the Model Snapshot. The web
application never calls MCP internally.
A stale Snapshot/revision requires refresh and reassessment. Model-owned authored
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
