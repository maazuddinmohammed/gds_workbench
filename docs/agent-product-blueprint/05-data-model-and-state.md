# Data model and state

## Installation model

The database is a canonical fresh PostgreSQL 16 schema. It is not a migration
set and is not idempotent DDL. Apply the thirteen numbered files once, in numeric
order, in one fail-fast transaction.

There are 83 domain tables plus one internal transaction-validation queue in
five schemas. Every foreign key uses `ON DELETE NO ACTION`. Automated deletion
and cascading cleanup are absent by design.

## Schema inventory

### `reference`: lookup vocabulary

| Tables | Meaning |
|---|---|
| `environment`, `system_type`, `zone`, `connection_type`, `object_type`, `connection_parameter` | Platform and connection vocabulary |
| `purge_policy`, `system_notebook`, `location_type`, `file_type`, `domain`, `data_operation`, `chunk_type`, `pipeline`, `process_type`, `currency`, `job_type`, `lane` | Operational lookup vocabulary |

### `core`: foundational and physical metadata

| Tables | Meaning |
|---|---|
| `project`, `tenant` | Administrative ownership hierarchy |
| `system`, `connection` | Source-system identity and Tenant-specific access/configuration metadata |
| `object`, `attribute` | Registered physical structures with guarded lock state |
| `connection_value` | Literal or Key Vault-backed connection values; hidden from runtime reads |
| `ingestion_object_mapping`, `ingestion_attribute_mapping` | Original-source to Bronze lineage |
| `system_notebook_path`, `connection_location` | System notebook and environment-specific connection locations |
| `copy_group`, `member_group`, `copy_group_control`, `copy` | Ingestion grouping and copy configuration |
| `process_group`, `process` | Processing groups and ordered executables |

`Connection` owns optional test initial and incremental batch settings. An
Object may name its exact batch Attribute. Connection values hold optional
literal configuration and remain hidden from runtime reads.

Every Tenant has `tenant_visibility = global|private`, defaulting to `private`.
Global visibility grants active authenticated Principals read access only;
mutation still requires a Tenant role or super admin.

`core.project` is a foundational administrative parent retained by the physical
schema. It is not the governed product Model and must never be used as its
substitute.

`copy_group_control` stores Tenant/System witnesses. Its composite foreign keys
prevent a Copy Group from being paired with a Member Group from another scope.

### `security`: identities, membership, locks, and audit

| Tables | Meaning |
|---|---|
| `principal` | User/service-principal metadata, active state, and explicit super-admin flag |
| `entra_principal_identity` | Entra Tenant/Object linkage with a witnessed Principal type |
| `tenant_principal_access` | Active, optionally expiring Tenant role: viewer, developer, architect, or tenant admin |
| `tenant_lock`, `tenant_lock_event` | Dormant long-lived Tenant Lease data and its audit |
| `artifact_lock_event`, `metadata_artifact_lock_event` | Append-only Model and Tenant metadata lock audit |

Routine modeling does not use Tenant Leases. Artifact lock changes are
available only through a narrow database function; Release 1 exposes no public
MCP lock tool.

### `model`: governed Model aggregate

| Tables | Meaning |
|---|---|
| `model` | Owning Tenant, current revision, status, and five DD-110 policy documents |
| `model_scope` | Same-Tenant physical Object set the Model may use, with guarded lock state |
| `modeling_evidence_document`, `modeling_evidence_record` | Evidence metadata and structured verified records |
| `model_event_log` | Safe event projection |
| `model_revision_transaction` | One revision advance witness per Model and PostgreSQL transaction |

A Model belongs to one Tenant. Its Scope may intentionally include active
Bronze Objects owned through another Tenant. Downstream modeled rows stay
bound to the Model.

The five policy columns are:

- `silver_model_naming_template`
- `silver_model_audit_columns_template`
- `gold_model_naming_template`
- `gold_model_technical_columns_template`
- `gold_model_audit_columns_template`

The Silver pair is all-null or complete. The Gold group is all-null or
complete. PostgreSQL does not validate template-specific JSON shapes;
application readiness validates policy content before dependent workflows.

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
| Mapping | `mapping_source_system_dependency`, `object_mapping`, `attribute_mapping` |

Logical and Dimensional each use exactly seven table families. Combined Mapping
uses exactly three. Typed parent columns and composite witness keys prevent a row
from crossing layer, Model, Object, Attribute, Entity, or Mapping-header
boundaries.

Logical source mappings point to eligible Bronze objects and Attributes.
Dimensional source mappings point to eligible Silver objects and Attributes
reachable through effective Logical-to-Silver Mapping. Logical Mapping targets
Silver; Dimensional Mapping targets Gold.

### `workflow`: change and run state

| Tables | Meaning |
|---|---|
| `model_change_set`, `model_change_set_event` | Eight-document Model draft, validation seal, expiry, and append-only activity |
| `metadata_change_set`, `metadata_change_set_event` | Twelve-document Tenant metadata draft and append-only activity |
| `idempotency_outcome` | Request digest and durable replay result |
| `workflow_grant`, `workflow_run_summary` | Frozen authorization and safe run status |
| `profiling_run` | Immutable profiling selection and state |
| `profiling_final_receipt` | Append-only atomic Profile publication outcome and counts |
| `model_apply_receipt`, `model_apply_receipt_ref` | Applied candidate and local-to-database ID mappings |
| `metadata_apply_receipt`, `metadata_apply_receipt_ref` | Applied Core metadata candidate and local-to-database ID mappings |
| `effective_graph_validation_queue` | Transient per-transaction request for one deferred whole-graph validation |

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
- Statement-level source triggers enqueue one transient request; one deferred
  queue trigger inspects the final transaction graph. Write order inside one
  transaction does not weaken integrity, and row batches do not repeat the
  whole-graph scan.

## Revisions and locks

Every effective write first locks the Model row. The first real effective
change in one database transaction advances `model_revision` once. Later
effective row changes in that transaction reuse the same revision witness.
Draft edits, validation, reads, no-ops, and DBML export do not advance it.

A byte-identical update exits before revision capture. Sequence values do not
roll back, so an aborted apply may leave unused numeric IDs without leaving
partial rows.

Twenty-five artifact families carry business locks. Direct DML guards protect a
locked row and its owned descendants. `security.set_artifact_lock(...)` handles
Model-owned locks; `security.set_metadata_artifact_lock(...)` handles Core
Object/Attribute locks against their owning Tenant. Both require
Architect/Tenant Admin access or super admin, resolve the actor from the
authenticated Entra Tenant/Object identity, and write append-only audit.
Public application roles cannot forge their internal flags.

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
