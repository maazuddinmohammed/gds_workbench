# Data model and state

## Installation model

The database is a canonical fresh PostgreSQL 16 schema. It is not a migration
set and is not idempotent DDL. Apply the nine numbered files once, in numeric
order, in one fail-fast transaction. `core.schema_version` records
`gds_etl_workbench` schema and contract version `1.0.0`.

There are 61 tables in four schemas. Every foreign key uses `ON DELETE NO
ACTION`. Automated deletion and cascading cleanup are absent by design.

## Schema inventory

### `core`: foundational and physical metadata

| Tables | Meaning |
|---|---|
| `schema_version`, `environment`, `system_type`, `zone`, `connection_type`, `object_type`, `connection_parameter` | Reference vocabulary and installed version |
| `project`, `tenant` | Administrative ownership hierarchy |
| `system`, `connection` | Source-system identity and Tenant-specific access/configuration metadata |
| `object`, `attribute` | Registered physical Bronze, Silver, and Gold structures |
| `connection_value` | Literal or Key Vault-backed connection values; hidden from runtime reads |
| `ingestion_object_mapping`, `ingestion_attribute_mapping` | Original-source to Bronze lineage |

`Connection` owns the four DD-108 development/test, initial/incremental batch
settings. An Object may name its exact batch Attribute. A Connection value must
store exactly one literal or Key Vault reference and must match the referenced
parameter policy.

`core.project` is a foundational administrative parent retained by the physical
schema. It is not the governed product Model and must never be used as its
substitute.

### `core_security`: identities, membership, locks, and audit

| Tables | Meaning |
|---|---|
| `user_account`, `user_entra_identity` | Active human account and Entra linkage |
| `tenant_user_access` | Active Tenant role: developer, architect, or admin |
| `tenant_lock`, `tenant_lock_event` | Dormant long-lived Tenant Lease data and its audit |
| `artifact_lock_event` | Append-only business-lock audit |

Routine modeling does not use Tenant Leases. Artifact lock changes are
available only through a narrow database function; Release 1 exposes no public
MCP lock tool.

### `model`: governed Model aggregate

| Tables | Meaning |
|---|---|
| `model` | Owning Tenant, current revision, status, and five DD-110 policy documents |
| `model_environment_target` | Model deployment target metadata |
| `model_scope` | Exact physical Object set the Model may use |
| `modeling_evidence_document`, `modeling_evidence_record` | Evidence metadata and structured verified records |
| `model_event_log` | Safe event projection |
| `model_revision_transaction` | One revision advance witness per Model and PostgreSQL transaction |

A Model belongs to one Tenant. Its Scope may include active Bronze Objects
owned through another Tenant; this supports governed cross-Tenant source
composition. Downstream modeled rows stay bound to the Model.

The five policy columns are:

- `silver_model_naming_template`
- `silver_model_audit_columns_template`
- `gold_model_naming_template`
- `gold_model_technical_columns_template`
- `gold_model_audit_columns_template`

The Silver pair is all-null or complete. The Gold group is all-null or
complete. Readiness, not bootstrap, rejects an incomplete layer policy.

## Modeling Evidence design

Modeling Evidence is Model-owned context, not a physical source or persisted
downstream lineage. It uses exactly two tables:

- a Document stores identity, optional Tenant/System provenance, optional file
  pattern/type/description, structured metadata, and active state; and
- its Records store type, bounded text, structured details, optional source
  location, applicable workflow layers, optional low/medium/high confidence,
  lifecycle, and the record-only business lock.

Original document bytes remain client-side. Release 1 has no upload, parser,
OCR, blob store, or retrieval-index service. A client extracts structured
records and submits Document/Record operations through the Evidence Section of
a Model Change Set. Evidence applies in the same graph transaction before
dependent Sections. The human `get_modeling_evidence` tool returns paginated
safe summaries; verified snapshots supply bounded typed context to workloads.

A Conceptual create/reactivate may cite active Evidence marked
`details.verified=true` and applicable to Conceptual. The compiler verifies the
basis, then removes the transient Evidence references before persistence.
Analysis and the other modeling workflows may consult applicable records, but
no applied Analysis, Conceptual, Logical, Dimensional, Mapping, Support, or
source-mapping row stores an Evidence foreign key. Evidence changes alter the
Evidence digest and stale dependent Candidates.

### `workflow`: applied modeling graph

| Layer | Tables |
|---|---|
| Profile | `attribute_profile` |
| Analysis | `analysis_result` |
| Conceptual | `conceptual_object`, `conceptual_relationship`, `conceptual_support` |
| Logical | `logical_submodel`, `logical_entity`, `logical_entity_submodel`, `logical_attribute`, `logical_entity_source_mapping`, `logical_attribute_source_mapping`, `logical_relationship` |
| Dimensional | `dimensional_submodel`, `dimensional_entity`, `dimensional_entity_submodel`, `dimensional_attribute`, `dimensional_entity_source_mapping`, `dimensional_attribute_source_mapping`, `dimensional_relationship` |
| Mapping | `object_mapping`, `attribute_mapping` |

Logical and Dimensional each use exactly seven table families. Combined Mapping
uses exactly two. Typed parent columns and composite witness keys prevent a row
from crossing layer, Model, Object, Attribute, Entity, or Mapping-header
boundaries.

Logical source mappings point to eligible Bronze objects and Attributes.
Dimensional source mappings point to eligible Silver objects and Attributes
reachable through effective Logical-to-Silver Mapping. Logical Mapping targets
Silver; Dimensional Mapping targets Gold.

### `workflow`: change and run state

| Tables | Meaning |
|---|---|
| `model_change_set`, `model_change_set_event` | Six-section draft, validation seal, expiry, and append-only activity |
| `idempotency_outcome` | Request digest and durable replay result |
| `workflow_grant`, `workflow_run_summary` | Frozen authorization and safe run status |
| `profiling_run` | Immutable profiling selection and state |
| `profiling_result_stage`, `profiling_failure_stage` | Mutually exclusive append-only Attribute outcomes |
| `profiling_final_receipt` | Final profile publication outcome |
| `model_apply_receipt`, `model_apply_receipt_ref` | Applied candidate and local-to-database ID mappings |

## Applied graph rules

- Every Model-owned row carries `model_id`.
- Parent-child and physical Object-Attribute witnesses include enough identity
  to reject cross-Model or cross-parent references.
- Numeric artifact IDs are PostgreSQL-generated `BIGINT` identities. Names are
  never relational mutation identity.
- Applied lifecycle is `active|needs_review|inactive|deprecated`; the first two
  are effective.
- Candidate-local references never persist. Apply resolves them to generated
  IDs and records the mapping in the receipt.
- Effective parent closure, source eligibility, key/grain rules, audit policy,
  Mapping package consistency, and dependency waves are enforced in SQL and
  application validation.
- Deferred constraint triggers inspect the final transaction graph, so write
  order inside one transaction does not weaken integrity.

## Revisions and locks

Every effective write first locks the Model row. The first real effective
change in one database transaction advances `model_revision` once. Later
effective row changes in that transaction reuse the same revision witness.
Draft edits, validation, reads, no-ops, and DBML export do not advance it.

A byte-identical update exits before revision capture. Sequence values do not
roll back, so an aborted apply may leave unused numeric IDs without leaving
partial rows.

Twenty-one artifact families carry business locks. Direct DML guards protect a
locked row and its owned descendants. The only lock toggle is the allowlisted
`core_security.set_artifact_lock(...)` function. It verifies the active Tenant,
architect/admin membership, Model, artifact kind, and revision, then writes an
append-only event. Public application roles cannot forge its internal flags.

## Database roles

- `gds_migration`: creates and owns release objects.
- `gds_app_read`: safe catalog, Model, and workflow reads.
- `gds_app_write`: safe reads plus constrained Model/workflow DML and narrow
  security-definer functions.

`PUBLIC` has no release-schema, table, or function rights. Application roles
cannot read `core.connection_value`, update/delete append-only records, write
Model revisions directly, or execute internal trigger functions.

Exact source: [`database/`](../../database/). Design explanation:
[`docs/architecture/database.md`](../architecture/database.md).
