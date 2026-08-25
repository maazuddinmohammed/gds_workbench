# Governed model tool contract

Use the connected MCP server's advertised input schema as the final contract. This
reference records the current plugin release contract; stop and reconcile any live
schema difference before writing. Never invent a tool, argument, record field, ID,
cursor, revision, or candidate digest.

## Runtime inventory

The current server registers these 57 tools, in this order:

```text
list_tenants                       get_tenant_details
get_model                          get_model_scope
check_tenant_lock                  acquire_tenant_lock
renew_tenant_lock                  release_tenant_lock
override_tenant_lock
create_metadata_change_set         stage_metadata_change_set
begin_metadata_stage_batch         put_metadata_stage_chunk
commit_metadata_stage_batch
get_metadata_change_set            validate_metadata_change_set
apply_metadata_change_set          archive_metadata_change_set
create_model_change_set            stage_model_change_set
begin_model_stage_batch            put_model_stage_chunk
commit_model_stage_batch
get_model_change_set               validate_model_change_set
apply_model_change_set             archive_model_change_set
list_objects                       get_objects
get_object_lineage                 list_copy_groups
get_copy_group                     list_process_groups
get_process_group
get_model_profiling                get_model_analysis
get_modeling_assertion_documents   get_modeling_assertion_records
get_model_conceptual_objects       get_model_conceptual_relationships
get_model_logical_submodels        get_model_logical_entities
get_model_logical_attributes       get_model_logical_relationships
get_model_dimensional_submodels    get_model_dimensional_entities
get_model_dimensional_attributes   get_model_dimensional_relationships
get_model_mapping_dependencies     get_model_object_mappings
get_model_attribute_mappings       execute_databricks_sql
describe_model_dataset             get_model_snapshot
get_model_dbml                     describe_metadata_dataset
get_metadata_snapshot
```

There is no public Model-create tool, naming-template mutation tool, direct model
CRUD tool, individual graph mutation tool, or direct mapping-write tool. All model
writes go through a Model Change Set.

## Read and discover

- `list_tenants(page_size?, cursor?)`: find visible Tenants. Page size is 1–200,
  default 50. Follow opaque cursors unchanged.
- `get_model(tenant_id, page_size?, cursor?)`: return active Models, revisions, scope
  counts, and the five silver/gold naming and audit templates. Page size is 1–200,
  default 200. Follow `next_cursor` unchanged until the requested scope is complete.
- `get_model_scope(model_id, page_size?, cursor?)`: return active scoped physical
  Objects. Page size is 1–2,000, default 2,000; follow `next_cursor` unchanged.
- `get_model_profiling(model_id, object_ids?, page_size?, cursor?)` and
  `get_model_analysis(...)`: read profiling and relationship evidence.
- `get_modeling_assertion_documents(model_id, page_size?, cursor?)` and
  `get_modeling_assertion_records(model_id, modeling_assertion_document_ids?,
  page_size?, cursor?)`: read governed source assertions.
- `get_model_conceptual_objects(model_id, supporting_object_ids?, page_size?,
  cursor?)` and `get_model_conceptual_relationships(model_id,
  conceptual_object_ids?, page_size?, cursor?)`: read the Conceptual layer.
- `get_model_logical_submodels`, `get_model_logical_entities`,
  `get_model_logical_attributes`, and `get_model_logical_relationships`: all take
  `model_id`; entity reads may filter by `supporting_object_ids`, while attribute
  and relationship reads may filter by `logical_entity_ids`.
- The four `get_model_dimensional_*` tools use the dimensional equivalents.
- `get_model_mapping_dependencies(model_id, page_size?, cursor?)`,
  `get_model_object_mappings(model_id, object_ids?, page_size?, cursor?)`, and
  `get_model_attribute_mappings(...)`: read Model Mapping lineage.

Other paged Model reads default to 50 rows and allow 1–200. ID filters allow at most
100 unique positive IDs; an omitted or empty filter means all visible records.
Focused reads return database IDs for navigation. Never put those IDs into the
ID-free records staged by a Model Change Set.

## Exact record contracts and exports

- `describe_model_dataset(dataset, schema_version="1.0")`: return one exact
  ID-free JSON Schema, Section, canonical key, and usage notes. Request only the
  datasets being authored. Valid dataset names are in
  [model-datasets.md](model-datasets.md).
- `get_model_snapshot(model_id, schema_version="2.0")`: create an immutable,
  ID-free ZIP descriptor. It is intentionally non-idempotent. Do not repeat, log,
  or save its temporary `download_url`; let the user use the original result.
- `get_model_dbml(model_id, model_type, include_submodels?,
  schema_version="2.0")`: create a review ZIP descriptor. `model_type` is
  `full`, `conceptual`, `logical`, or `dimensional`.

Snapshot and DBML calls create new artifacts; do not retry them blindly. A local
proposed model JSON document is not an authoritative MCP Model Snapshot and must
retain the baseline revision.

## Tenant Lock

Model writes require the current server-derived Principal to own the Tenant Lock.
Use `check_tenant_lock(tenant_id)` first. Ask before
`acquire_tenant_lock(tenant_id, duration_minutes=60, purpose=None,
schema_version="1.0")`; duration is 1–240. Renew only the caller's lock and release
it when the workflow ends.
`override_tenant_lock` only releases another Principal's lock and requires its own
explicit approval; it never acquires a replacement. Never infer Principal, Tenant,
role, ownership, or authorization in client input.

## Model Change Set inputs

All calls use `schema_version="1.0"` unless the advertised server schema says
otherwise.

- `create_model_change_set(model_id)`: create or resume the current Principal's
  one active/validated draft. Requires an owned lock. Returns the Change Set UUID,
  `draft_revision`, status, and four-hour expiry.
- `get_model_change_set(model_id, model_change_set_id, dataset?)`: owner-only read;
  no current lock required. With no dataset, returns counts. With one dataset,
  returns its complete pending records.
- `stage_model_change_set(model_id, model_change_set_id,
  expected_draft_revision, changes)`: `changes` contains 1–19 unique objects of
  `{dataset, records}`. Each record list has at most 20,000 entries. The entire
  draft has at most 50,000 pending records and each Section document at most
  16 MiB. Each supplied list replaces only that pending dataset; omitted pending
  datasets remain. One successful call increments the draft revision once, clears
  prior validation, and refreshes the four-hour expiry.
- For one complete dataset too large for a normal request, prepare 1–64 ordered
  chunks of at most 450 KiB. `begin_model_stage_batch` binds the approved manifest
  without changing the revision. `put_model_stage_chunk` validates and stores one
  idempotent typed chunk. `commit_model_stage_batch` verifies all counts and hashes,
  then performs the same complete dataset replacement and one revision increment as
  normal Stage. Chunks are invisible to Get, Validate, and Apply before Commit.
- `validate_model_change_set(model_id, model_change_set_id,
  expected_draft_revision)`: requires the lock and exact revision. It validates
  schema, locks, scope, uniqueness, references, then the complete future graph.
  On success it returns a sealed `candidate_digest` and authoritative
  `action_review`; on failure it remains active with bounded errors.
- `apply_model_change_set(model_id, model_change_set_id,
  expected_draft_revision)`: destructive and non-idempotent. It requires validated
  status, the same revision, owned lock, matching stored digest, and a fresh
  transactional revalidation. Call only after the user approves the displayed
  authoritative action review.
- `archive_model_change_set(model_id, model_change_set_id,
  expected_draft_revision)`: retain and end an active/validated draft. No current
  lock is required. The API reports archived; the stored terminal status is
  discarded.

Begin, Put, and Commit Stage Batch calls are idempotent for the exact manifest/chunk.
Never replay normal Stage, Validate, Apply, Archive, Snapshot, DBML, or lock mutations
after an ambiguous error. Read current state first and reconcile the latest revision.

## Naming templates

Read current templates from `get_model`. To change them, stage exactly one complete
`model_details` record. The silver naming/audit pair must be wholly present or wholly
null. The gold naming/technical/audit triple follows the same rule. Each non-null
JSON template is limited to 256 KiB. The server stores and validates the JSON shape
but does not prove that proposed names follow the template; preview names and get
the user's decision before staging.

## Two mapping families

- Model Mapping datasets—`mapping_dependency`, `mapping_object`, and
  `mapping_attribute`—connect physical source records to Logical or Dimensional
  records. Write them through a Model Change Set.
- Metadata ingestion lineage—`ingestion_object_mapping` and
  `ingestion_attribute_mapping`—connect physical Source and Target objects. Write
  them through a Metadata Change Set.

Do not substitute one family for the other. Do not use `execute_databricks_sql` to
mutate models or mappings; it is a separate governed, read/temporary-only analysis
tool.
