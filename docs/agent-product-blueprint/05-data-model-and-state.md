# Data model and state

## Installation model

The database is a canonical fresh PostgreSQL 18 schema. It is not a migration
set and is not idempotent DDL. Apply the twelve install files once, in sorted
order, in one fail-fast transaction.

There are 73 tables in six schemas. Every foreign key uses `ON DELETE NO
ACTION`. Automated deletion and cascading cleanup are absent by design.

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

### `security`: identities, membership, and Tenant Locks

| Tables | Meaning |
|---|---|
| `principal` | User/service-principal metadata, active state, and explicit super-admin flag |
| `entra_principal_identity` | Entra Tenant/Object linkage with a witnessed Principal type |
| `tenant_principal_access` | Active, optionally expiring Tenant role: viewer, developer, architect, or tenant admin |
| `tenant_lock`, `tenant_lock_event` | Dormant long-lived Tenant Lease data and its audit |

Routine modeling does not use Tenant Leases. Release 1 exposes no public MCP
lock tool.

### `model`: governed Model aggregate

| Tables | Meaning |
|---|---|
| `model` | Owning Tenant, current revision, status, and five DD-110 policy documents |
| `model_scope` | Same-Tenant physical Object set the Model may use, with guarded lock state |
| `modeling_assertion_document`, `modeling_assertion_record` | Assertion source metadata and structured factual records |
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

## Modeling Assertion design

Modeling Assertions are Model-owned factual context. An Assertion may also be a
persisted support source for Conceptual, Logical, or Dimensional artifacts. The
design uses exactly two tables:

- a Document stores identity, optional Tenant/System provenance, optional file
  pattern/type/description, structured metadata, and active state; and
- its Records store type, bounded text, structured details, optional source
  location, applicable workflow layers, optional low/medium/high confidence,
  lifecycle, and the record-only business lock.

Original document bytes remain client-side. Release 1 has no upload, parser,
OCR, blob store, or retrieval-index service. A client extracts structured
records and submits Document/Record operations through the Assertion Section of
a Model Change Set. Assertions apply in the same graph transaction before
dependent Sections. The human `get_modeling_assertions` tool returns paginated
safe summaries; verified snapshots supply bounded typed context to workloads.

An effective support/source-mapping row may cite an active Assertion Record
marked `details.verified=true` and applicable to its layer. It stores a
same-Model foreign key to that Record. A discriminator and XOR check require
exactly one physical or Assertion source. Analysis and Mapping may consult
applicable Assertions but do not persist an Assertion foreign key. Assertion
changes alter the Assertion digest and stale dependent Candidates.

### `workflow`: applied modeling graph

| Layer | Tables |
|---|---|
| Profile | `attribute_profile` |
| Analysis | `analysis_result` |
| Conceptual | `conceptual_object`, `conceptual_relationship`, `conceptual_support` |
| Logical | `logical_submodel`, `logical_entity`, `logical_entity_submodel`, `logical_attribute`, `logical_entity_source_mapping`, `logical_attribute_source_mapping`, `logical_relationship` |
| Dimensional | `dimensional_submodel`, `dimensional_entity`, `dimensional_entity_submodel`, `dimensional_attribute`, `dimensional_entity_source_mapping`, `dimensional_attribute_source_mapping`, `dimensional_relationship` |
| Mapping | `mapping_source_system_dependency`, `mapping_object`, `mapping_attribute` |

Logical and Dimensional each use exactly seven table families. Combined Mapping
uses exactly three. Typed parent columns and composite witness keys prevent a row
from crossing layer, Model, Object, Attribute, Entity, or Mapping-header
boundaries.

Logical Entity source mappings point to an eligible Bronze Object or an
applicable Assertion Record. Logical Attribute source mappings point to a
physical Bronze Attribute path or an Assertion Record. Dimensional mappings
use the corresponding eligible Silver Object/Attribute or Assertion choice.
Physical Dimensional sources remain reachable through effective
Logical-to-Silver Mapping. Logical Mapping targets Silver; Dimensional Mapping
targets Gold.

### `mcp`: change and tool-call state

| Tables | Meaning |
|---|---|
| `model_change_set`, `model_change_set_event` | Eight-document Model draft, validation seal, expiry, and append-only activity |
| `metadata_change_set`, `metadata_change_set_event` | Sixteen-list Tenant metadata draft, validation seal, retained terminal state, and append-only activity |
| `tool_call_log` | Append-only bounded audit of completed MCP tool calls |

## Applied graph rules

- Every Model-owned row carries `model_id`.
- Parent-child and physical Object-Attribute witnesses include enough identity
  to reject cross-Model or cross-parent references.
- Numeric artifact IDs are PostgreSQL-generated `BIGINT` identities. Names are
  never relational mutation identity.
- Applied lifecycle is `active|needs_review|inactive|deprecated`; the first two
  are effective.
- Candidate-local references never persist. Apply resolves them before writing
  normalized rows.
- The numbered DDL currently enforces only declarative row and relationship
  constraints. Cross-table lifecycle and graph behavior remains uninstalled.

## Archived behavior

Revision, lock, lifecycle, append-only, identity, authorization, and effective
graph behavior is archived under `database/archived_functions_triggers/`.
Those drafts are not installed. Rebuild only after the corresponding functional
requirements and rejecting tests are finalized.

## Database roles

- `gds_migration`: creates and owns release objects.
- `gds_app_write`: safe reads, constrained Model/workflow DML, governed
  Metadata Change Set functions, and the pure `CHECK` validator.

`PUBLIC` has no release-schema, table, or function rights. The application role
cannot read `core.connection_value`, update/delete append-only records, write
foundational security rows, or execute archived behavior functions.

Exact source: [`database/`](../../database/). Design explanation:
[`docs/architecture/database.md`](../architecture/database.md).
