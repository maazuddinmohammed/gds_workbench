# GDS MCP tools, snapshot schemas, and table validations

Temporary review copy · 15 September 2026 · current local source

## Coverage

| Requested item | Included |
|---|---|
| MCP tool grouping | All 37 tool names registered by the current server, grouped by purpose |
| Snapshot directories and schemas | Metadata: 28 datasets; Model: 25 datasets; archive trees, root documents, row fields, nested structures, lookups, schemas and response envelopes |
| Table constraints and validations | All 51 tables: 17 `core`, 6 `model`, 28 `workflow`; SQL constraints, late-added constraints, triggers, governed SQL functions, application checks and relevant client/read-time checks |
| Exact SQL reference | Expandable declarations for all 51 tables, including unique indexes and later ALTER statements |

**Scope:** inspected the current repository source, server registrations, snapshot builders/contracts, numbered fresh-install SQL, write paths and supporting tests. This describes the implementation in this checkout; no live MCP deployment or database was queried. Generated deployment copies under `artifacts/` were not treated as the authoritative source.

**Reading guide:** DB rules always apply to ordinary SQL writes. Function/App/UI rules apply only through the named path. A response validator checks data being returned; it does not constrain stored rows. Guidance text is advice unless an executable validator enforces it. Source links include line numbers. The report contains schemas and rules, not actual snapshot rows or connection values.

## Contents

- [1. MCP tools](#mcp-tools)
- [2. Metadata and Model snapshots](#snapshots)
- [3. Table validations](#table-validations)
  - [Core — 17 tables](#core-tables)
  - [Model — 6 tables](#model-tables)
  - [Workflow — 28 tables](#workflow-tables)
- [4. Exact SQL inventory](#sql-inventory)

<a id="mcp-tools"></a>


## 1. Currently exposed MCP tools

**37 tools** are registered by the current server composition. Grouping below is for review; it does not add tools or change their permissions. Registration is unconditional; authentication, Tenant/Model authorization, lock ownership, revision checks, and operation-specific rules govern each call. This is a source inventory, not a query against a deployed server.

Sources: [server registration](/Users/maazuddinmohammed/main/projects/gds_workbench_v2/mcp_server/gds_etl_workbench/adapters/mcp/server.py:74), [exact 37-tool test contract](/Users/maazuddinmohammed/main/projects/gds_workbench_v2/tests/mcp/test_tool_schema_contracts.py:29).

| Group | Count | Exposed tools | Purpose |
|---|---:|---|---|
| Tenant and Model discovery | 4 | `list_tenants`<br>`get_tenant_details`<br>`list_models`<br>`get_model_input_scope` | Find authorized Tenants, safe Tenant/Connection context, Models and their selected input Objects. |
| Focused data reads | 2 | `inspect_metadata`<br>`read_model_section` | Bounded live Metadata views and applied Model datasets. |
| Dataset/schema guidance | 2 | `describe_metadata_dataset`<br>`describe_model_dataset` | Return keys, accepted fields, references, rules and JSON Schema; no records. |
| Snapshots and diagram export | 3 | `create_metadata_snapshot`<br>`create_model_snapshot`<br>`export_model_dbml` | Create immutable ZIPs and return small download descriptors. |
| Tenant Lock management | 5 | `check_tenant_lock`<br>`acquire_tenant_lock`<br>`renew_tenant_lock`<br>`release_tenant_lock`<br>`override_tenant_lock` | Inspect/reserve/extend/release governed Tenant ownership; explicit override releases another owner's lock. |
| Metadata Change Sets | 10 | `create_metadata_change_set`<br>`stage_metadata_change_set`<br>`begin_metadata_stage_batch`<br>`put_metadata_stage_chunk`<br>`commit_metadata_stage_batch`<br>`get_metadata_change_set`<br>`get_metadata_change_set_fingerprint`<br>`validate_metadata_change_set`<br>`apply_metadata_change_set`<br>`archive_metadata_change_set` | Govern pending changes to the 16 operational Metadata datasets. |
| Model Change Sets | 10 | `create_model_change_set`<br>`stage_model_change_set`<br>`begin_model_stage_batch`<br>`put_model_stage_chunk`<br>`commit_model_stage_batch`<br>`get_model_change_set`<br>`get_model_change_set_fingerprint`<br>`validate_model_change_set`<br>`apply_model_change_set`<br>`archive_model_change_set` | Govern pending changes to the 25 Model datasets. |
| Databricks SQL | 1 | `execute_databricks_sql` | Governed multi-statement reads and temporary objects; bounded final-statement results. |

### 1.1 Read/export scope and distinctions

| Tool(s) | Current scope / important boundary | Source |
|---|---|---|
| `list_tenants`, `get_tenant_details` | Authorized Tenant inventory and bounded safe Tenant/Connection details. Connection credentials are excluded. | [list](/Users/maazuddinmohammed/main/projects/gds_workbench_v2/mcp_server/gds_etl_workbench/tools/tenants/list_tenants.py:71), [details](/Users/maazuddinmohammed/main/projects/gds_workbench_v2/mcp_server/gds_etl_workbench/tools/tenants/get_tenant_details.py:180) |
| `list_models`, `get_model_input_scope` | Model inventory under a Tenant; selected physical input Objects for a Model. The latter is read-only; Scope changes use Model Change Sets. | [Models](/Users/maazuddinmohammed/main/projects/gds_workbench_v2/mcp_server/gds_etl_workbench/tools/modeling/model_details.py:92), [Scope](/Users/maazuddinmohammed/main/projects/gds_workbench_v2/mcp_server/gds_etl_workbench/tools/modeling/model_input_scope.py:148) |
| `inspect_metadata` | `view`: `objects`, `object_details`, `object_lineage`, `copy_groups`, `copy_group_details`, `process_groups`, `process_group_details`. Objects list requires `zone`; detail views require matching IDs. Lineage is direct upstream/downstream/both. | [view contract](/Users/maazuddinmohammed/main/projects/gds_workbench_v2/mcp_server/gds_etl_workbench/tools/catalog/inspect_metadata.py:74) |
| `read_model_section` | 19 datasets: Profiling, Analysis, Assertions, Conceptual, Logical, Dimensional, Binding and Mapping. At most 200 rows/page. Generated Code and Validation are Snapshot-only here. Model header/Scope have dedicated context/read tools. | [dataset enum](/Users/maazuddinmohammed/main/projects/gds_workbench_v2/mcp_server/gds_etl_workbench/tools/modeling/read_model_section.py:51) |
| `describe_metadata_dataset`, `describe_model_dataset` | `detail=compact` (default): keys/rules/authoring schema. `full`: also column guidance and exact schema. Authenticated contract reads; no Tenant row selection. | [Metadata](/Users/maazuddinmohammed/main/projects/gds_workbench_v2/mcp_server/gds_etl_workbench/tools/snapshots/metadata/describe_metadata_dataset.py:43), [Model](/Users/maazuddinmohammed/main/projects/gds_workbench_v2/mcp_server/gds_etl_workbench/tools/snapshots/model/describe_model_dataset.py:31) |
| `create_metadata_snapshot` | One authorized Tenant; optional explicitly authorized `source_tenant_ids` adds Source/Bronze context. Extra context grants no write rights. | [tool](/Users/maazuddinmohammed/main/projects/gds_workbench_v2/mcp_server/gds_etl_workbench/tools/snapshots/metadata/get_metadata_snapshot.py:129) |
| `create_model_snapshot` | Complete registered Model datasets from one consistent database read, including applied Code and Validation definitions. | [tool](/Users/maazuddinmohammed/main/projects/gds_workbench_v2/mcp_server/gds_etl_workbench/tools/snapshots/model/get_model_snapshot.py:95) |
| `export_model_dbml` | Diagram ZIP for selected `model_type` (`full`, `conceptual`, `logical`, `dimensional`); `include_submodels=true` by default. Separate export, not an extra file inside the Metadata/Model ZIPs described below. | [tool](/Users/maazuddinmohammed/main/projects/gds_workbench_v2/mcp_server/gds_etl_workbench/tools/snapshots/dbml/get_model_dbml.py:107) |
| `execute_databricks_sql` | Default `environment_code=dev`; qualified persistent relations required; permits reads and unqualified temporary views/tables. Rejects persistent DDL and DML; returns at most 50 rows from final statement. | [tool](/Users/maazuddinmohammed/main/projects/gds_workbench_v2/mcp_server/gds_etl_workbench/tools/databricks/execute_sql.py:83) |

Older individual reader modules remain implementation helpers. Names such as `list_objects`, `get_object_details`, `get_object_lineage`, `get_model_snapshot` and `get_metadata_snapshot` are **not separately registered tools**. `inspect_metadata` composes the physical readers; current Snapshot tool names start with `create_`.

### 1.2 Shared Change Set lifecycle

Each operation below exists once for Metadata and once for Model, using the exact names in the group table.

| Operation | Meaning |
|---|---|
| `create_*_change_set` | Create or resume the caller's active/validated Change Set; requires caller-owned Tenant Lock. |
| `stage_*_change_set` | Replace complete **pending** lists for selected datasets, transactionally. Omitted datasets retain their pending content. Empty list clears that pending dataset. It does not mean deleting all applied database rows. |
| `begin_*_stage_batch` | Begin/resume one nonempty dataset replacement split into ordered chunks; does not increment draft revision. |
| `put_*_stage_chunk` | Submit one verified, numbered chunk to that batch. Model additionally supports fragment transport for large `generated_code` payloads. |
| `commit_*_stage_batch` | Verify completeness and digests, replace the pending dataset, increment draft revision once. |
| `get_*_change_set` | Read the current caller-owned pending Change Set/status and bounded dataset content. |
| `get_*_change_set_fingerprint` | Read bounded revision/digest/count evidence for exact pending content, without returning records. |
| `validate_*_change_set` | Revalidate references, record rules, authorization/locks and current state; persist validation result. |
| `apply_*_change_set` | Apply the validated draft under current locking/revision/idempotency rules. Separate high-impact operation requiring explicit approval in the server's client instructions. |
| `archive_*_change_set` | Close/discard the governed pending Change Set through its lifecycle. |

Metadata has no Tenant-wide revision. Model uses Model revision fencing: mismatch requires a new Snapshot and reassessment. Direct Stage and batch Stage replace pending datasets; server Apply reconciles their records with applied state.

Sources: [Metadata lifecycle](/Users/maazuddinmohammed/main/projects/gds_workbench_v2/mcp_server/gds_etl_workbench/application/change_sets/metadata.py:444), [Model lifecycle](/Users/maazuddinmohammed/main/projects/gds_workbench_v2/mcp_server/gds_etl_workbench/application/change_sets/model.py:971), [server usage requirements](/Users/maazuddinmohammed/main/projects/gds_workbench_v2/mcp_server/gds_etl_workbench/adapters/mcp/server.py:120).

Tenant Lock specifics: acquire fails if *any* active lock exists, including the caller's; renew extends an owned lock; release releases the caller's lock; override requires a nonblank audit reason and releases another owner's lock without acquiring a replacement. [Lock tools](/Users/maazuddinmohammed/main/projects/gds_workbench_v2/mcp_server/gds_etl_workbench/tools/tenants/tenant_locks.py:149).

<a id="snapshots"></a>

## 2. Metadata and Model Snapshots

### 2.1 Comparison and generation boundary

| Property | Metadata Snapshot | Model Snapshot |
|---|---|---|
| Public tool | `create_metadata_snapshot` | `create_model_snapshot` |
| ZIP root | `metadata-snapshot/` | `model-snapshot/` |
| Public/archive schema version | `2.0` | `2.0` |
| Logical datasets | 28 | 25 |
| Sections | 3: foundational, reference, operational | 11: Scope, Profiling, Analysis, Assertion, Conceptual, Logical, Dimensional, Binding, Mapping, Code, Validation |
| Physical Metadata tables represented | 22 | Not a 1:1 table export: nested child records are grouped into parent rows. |
| Row format | `flat-json-lines` | `nested-json-lines` |
| Schema files | 28 | 25 |
| Row files | 28 | 25 |
| Lookup files | 10 | 0 |
| Total files | 68 | 52 |
| Database IDs in dataset rows | None; references use codes/names | None; references use codes/names |
| Root identity | `tenant_code`, Snapshot UUID | `model_id`, `model_name`, `model_revision`, Snapshot UUID; catalog also `tenant_code` |
| Selection | Requested Tenant's Objects by `source_tenant_id`, related Attributes/mappings/orchestration/foundation/reference closure. Optional Source Tenants contribute Source/Bronze Objects only. | Selected Model's header, input scope, applied stage records and nested supporting records. Includes historical/inactive/deprecated data where the Snapshot queries preserve it. |

**“ID-free” describes dataset records.** The Model manifest/catalog still contain `model_id`; download descriptors contain their Tenant/Model scope ID. Neither ZIP is a complete database backup: audit/history tables, secrets, unrelated schemas and pending Change Sets are not exported as separate datasets.

Both are selected under a repeatable-read transaction (one consistent database view), encoded as UTF-8, checked, ZIP-compressed and hashed. Empty datasets retain empty `rows.jsonl` files; optional nested data appears as `[]`/`null` according to its schema, not as missing files. Values are emitted in record-field order, sorted by canonical key. Metadata additionally checks declared unique keys and cross-dataset references; Model validates typed rows and canonical-key uniqueness. [Metadata selection](/Users/maazuddinmohammed/main/projects/gds_workbench_v2/mcp_server/gds_etl_workbench/tools/snapshots/metadata/get_metadata_snapshot.py:231), [Model selection](/Users/maazuddinmohammed/main/projects/gds_workbench_v2/mcp_server/gds_etl_workbench/tools/snapshots/model/get_model_snapshot.py:212), [Model row limits/history selection](/Users/maazuddinmohammed/main/projects/gds_workbench_v2/mcp_server/gds_etl_workbench/application/model_snapshot.py:477).

Runtime constants: download URL up to **15 minutes**, artifact availability **24 hours**, both expanded and compressed ZIP limited to **256 MiB**. Model selection caps each dataset at 20,000 rows and total top-level dataset rows at 50,000. These row counts do not count each nested array element as a separate dataset row. Archives use a fresh UUID v4; identical logical content can therefore have different archive hashes on separate calls. [Runtime constants](/Users/maazuddinmohammed/main/projects/gds_workbench_v2/mcp_server/gds_etl_workbench/configuration.py:31), [archive writer](/Users/maazuddinmohammed/main/projects/gds_workbench_v2/mcp_server/gds_etl_workbench/tools/snapshots/archive.py:45).

### 2.2 Public request and response schemas

Schema notation below shows types and constant values, not sample data.

```text
create_metadata_snapshot request:
  tenant_id: positive signed-bigint integer
  schema_version: "2.0"                  default "2.0"
  source_tenant_ids: positive-bigint[]   default []; at most 200 entries

create_model_snapshot request:
  model_id: positive signed-bigint integer
  schema_version: "2.0"                  default "2.0"

Common successful response:
  schema_version: "2.0"
  snapshot_id: UUID v4 string
  snapshot_kind: "metadata" | "model"    matching called tool
  status: "ready"
  download_url: string                  temporary signed URL; 1–2048 characters
  download_url_expires_at: datetime string
  size_bytes: integer > 0               compressed ZIP bytes
  sha256: string                        exactly 64 lowercase hexadecimal characters
  content_type: "application/zip"

Metadata-only response field:
  tenant_id: positive signed-bigint integer

Model-only response fields:
  model_id: positive signed-bigint integer
  model_revision: integer > 0
```

The tool result contains a download descriptor, not Snapshot rows. `generated_at`, retention deadline and file/dataset counts are inside the archive manifest. A failed build returns a bounded MCP tool error, not `status="failed"` in this success schema. [Metadata contracts](/Users/maazuddinmohammed/main/projects/gds_workbench_v2/mcp_server/gds_etl_workbench/tools/snapshots/metadata/get_metadata_snapshot.py:81), [Model contracts](/Users/maazuddinmohammed/main/projects/gds_workbench_v2/mcp_server/gds_etl_workbench/tools/snapshots/model/get_model_snapshot.py:59).

### 2.3 Directory layouts

`<dataset>` names and their section are exhaustively listed in §§2.6–2.7. The brace lists below mean one directory per listed dataset.

```text
metadata-snapshot/
├── manifest.json
├── catalog.json
├── schemas/
│   └── <dataset>.schema.json                  # all 28 dataset names
└── data/
    ├── foundational/
    │   └── {project,tenant,system,connection}/rows.jsonl
    ├── reference/
    │   └── {system_type,connection_type,object_type,zone,
    │        chunk_type,file_type,data_operation,process_type}/rows.jsonl
    └── operational/
        ├── {source,bronze,silver,gold}_object/
        │   ├── rows.jsonl
        │   └── lookup.jsonl
        ├── {source,bronze,silver,gold}_attribute/
        │   ├── rows.jsonl
        │   └── lookup.jsonl
        ├── ingestion_object_mapping/rows.jsonl
        ├── ingestion_attribute_mapping/rows.jsonl
        ├── copy_group/rows.jsonl
        ├── member_group/rows.jsonl
        ├── copy_group_control/{rows,lookup}.jsonl
        ├── copy/{rows,lookup}.jsonl
        ├── process_group/rows.jsonl
        └── process/rows.jsonl

model-snapshot/
├── manifest.json
├── catalog.json
├── schemas/model/
│   └── <dataset>.schema.json                  # all 25 dataset names
└── data/
    ├── model_input_scope/{model_details,model_input_scope}/rows.jsonl
    ├── profiling/profiling_profile/rows.jsonl
    ├── analysis/analysis_result/rows.jsonl
    ├── assertion/{modeling_assertion_document,modeling_assertion_record}/rows.jsonl
    ├── conceptual/{conceptual_object,conceptual_relationship}/rows.jsonl
    ├── logical/{logical_submodel,logical_entity,
    │            logical_attribute,logical_relationship}/rows.jsonl
    ├── dimensional/{dimensional_submodel,dimensional_entity,
    │                dimensional_attribute,dimensional_relationship}/rows.jsonl
    ├── model_binding/{model_object_binding,model_attribute_binding}/rows.jsonl
    ├── mapping/{mapping_dependency,mapping_object,mapping_attribute}/rows.jsonl
    ├── code_generation/{generated_code,generated_code_source_system}/rows.jsonl
    └── validation/{validation_group,validation_check}/rows.jsonl
```

No `model.dbml`, separate SQL/Python files, README or prompts are generated inside these two Snapshot ZIPs. Generated program text stays in the `generated_code_content` JSON field; DBML has its own export tool.

The current plugin normally installs the ZIP contents as:

```text
GDS/<TENANT_CODE>/<SESSION>/
├── metadata/metadata-snapshot/...
├── model/model-snapshot/...
├── session.json
├── tasks/
├── metadata-change-set/
└── model-change-set/
```

Session/Change Set files are separate local workflow state, not Snapshot members. Cloud blob naming is `metadata/<tenant_id>/<snapshot_id>.zip` or `model/<model_id>/<snapshot_id>.zip`; attachment filename is `<kind>-snapshot-<scope_id>-<snapshot_id>.zip`. Server temporary build files are removed after upload. [Metadata writer](/Users/maazuddinmohammed/main/projects/gds_workbench_v2/mcp_server/gds_etl_workbench/tools/snapshots/metadata/archive.py:285), [Model writer](/Users/maazuddinmohammed/main/projects/gds_workbench_v2/mcp_server/gds_etl_workbench/tools/snapshots/model/archive.py:82), [storage naming](/Users/maazuddinmohammed/main/projects/gds_workbench_v2/mcp_server/gds_etl_workbench/tools/snapshots/storage.py:194), [session layout](/Users/maazuddinmohammed/main/projects/gds_workbench_v2/plugins/v2/gds/skills/gds/references/session.md:3), [installation](/Users/maazuddinmohammed/main/projects/gds_workbench_v2/plugins/v2/gds/skills/gds/scripts/gds-local.js:1980).

### 2.4 Root files and their exact structures

#### `manifest.json`: identity, counts and integrity inventory

All paths below are relative to the ZIP's `metadata-snapshot/` or `model-snapshot/` root.

```text
Common manifest fields:
  schema_version: "2.0"
  snapshot_kind: "metadata" | "model"
  snapshot_id: UUID v4 string
  database_ids_included: false
  generated_at: UTC ISO-8601 string ending in Z
  available_until: UTC ISO-8601 string ending in Z
  counts:
    logical_dataset_count: 28 | 25
    row_count: integer                     sum of dataset rows, excludes lookup duplicates
    file_count: 68 | 52                     includes manifest
    expanded_bytes: integer                includes manifest and all uncompressed file contents
  sections:
    <section-name>:
      dataset_count: integer
      row_count: integer
  catalog:
    path: "catalog.json"
    sha256: lowercase 64-character hex string
  schemas:
    directory: "schemas" | "schemas/model"
    dataset_count: 28 | 25
  members: array of:
    path: relative file path
    sha256: lowercase 64-character hex string
    size_bytes: integer                    uncompressed member bytes
    row_count: integer                     present only for rows/lookup files

Metadata-only manifest fields:
  tenant_code: string
  counts.physical_table_count: 22
  counts.lookup_file_count: 10

Model-only manifest fields:
  model_id: integer
  model_name: string
  model_revision: integer
```

`members` lists every file **except the manifest itself** (67 Metadata / 51 Model entries); it cannot contain its own hash. ZIP hash is in the MCP response. Section counts: Metadata foundational 4, reference 8, operational 16; Model counts match the dataset registry below. [Metadata manifest](/Users/maazuddinmohammed/main/projects/gds_workbench_v2/mcp_server/gds_etl_workbench/tools/snapshots/metadata/archive.py:348), [Model manifest](/Users/maazuddinmohammed/main/projects/gds_workbench_v2/mcp_server/gds_etl_workbench/tools/snapshots/model/archive.py:186), [member metadata](/Users/maazuddinmohammed/main/projects/gds_workbench_v2/mcp_server/gds_etl_workbench/tools/snapshots/archive.py:71).

#### Metadata `catalog.json`: dataset navigation

```text
schema_version: "2.0"
snapshot_kind: "metadata"
row_format: "flat-json-lines"
database_ids_included: false
instructions: string[]                      five fixed reading/navigation instructions
record_groups:
  - name: "objects"
    datasets: ["source_object","bronze_object","silver_object","gold_object"]
  - name: "attributes"
    datasets: ["source_attribute","bronze_attribute","silver_attribute","gold_attribute"]
sections: array of:
  name: "foundational" | "reference" | "operational"
  label: "Foundational" | "Reference" | "Operational"
  datasets: array of:
    name: dataset name
    label: human-readable plural label
    record_type: underlying portable record type
    row_count: integer
    canonical_key: string[]
    search_fields: string[]                 canonical key plus configured lookup fields, deduplicated
    schema_file: "schemas/<dataset>.schema.json"
    search_file: lookup path if present, otherwise rows path
    rows_file: "data/<section>/<dataset>/rows.jsonl"
    search_result_complete: boolean         false for 10 lookup-backed datasets; true otherwise
```

Instructions direct clients to read the catalog first, select only needed datasets, search keys, use lookup `line` to read full rows, and read schemas when meaning is needed. [Catalog builder](/Users/maazuddinmohammed/main/projects/gds_workbench_v2/mcp_server/gds_etl_workbench/tools/snapshots/metadata/archive.py:194).

#### Model `catalog.json`: Model context and section navigation

```text
schema_version: "2.0"
snapshot_kind: "model"
row_format: "nested-json-lines"
database_ids_included: false
model:
  model_id: integer
  model_name: string
  model_revision: integer
  tenant_code: string | null
  other_active_model_names: string[]
instructions: string[]                       five fixed reading/authoring instructions
sections: array of:
  name: one of 11 registered section names
  description: string
  authoring_prerequisites:
    required_applied_sections: string[]
    optional_applied_sections: string[]
    successive_change_set_required: false
  datasets: array of:
    name: dataset name
    row_count: integer
    canonical_key: string[]
    change_set_eligible: true
    schema_file: "schemas/model/<dataset>.schema.json"
    rows_file: "data/<section>/<dataset>/rows.jsonl"
```

Published catalog prerequisites: `code_generation` requires applied `mapping`; `validation` requires applied `mapping` and optionally uses `code_generation`; other catalog sections currently contain empty prerequisite lists. This catalog is not a full enumeration of backend workflow prerequisites. Instructions direct clients to read the catalog, choose needed sections, search keys, read schema before authoring and follow extensions/prerequisites. [Model catalog](/Users/maazuddinmohammed/main/projects/gds_workbench_v2/mcp_server/gds_etl_workbench/tools/snapshots/model/archive.py:104).

### 2.5 Dataset schema files, rows and lookup files

Each `*.schema.json` is a JSON Schema Draft 2020-12 document. It describes one row, not the entire JSONL file. Top-level records reject extra properties. `required` controls whether a field may be omitted in an authoring input; `null` is a separate allowed value. Snapshot serialization includes every declared field, including defaulted fields and nulls. JSONL means one JSON object per line, with a final newline; an empty file represents zero records.

| Schema field | Metadata schema | Model schema |
|---|---|---|
| `$schema` | `https://json-schema.org/draft/2020-12/schema` | Same |
| `$id` | `schemas/<dataset>.schema.json` | `schemas/model/<dataset>.schema.json` |
| `title`, `description` | Dataset label and row description | Record class name and row description |
| `type`, `additionalProperties` | `"object"`, `false` | Same |
| `properties`, `required` | Complete flat field schemas and required field list | Complete parent field schemas and required field list |
| `$defs` | Absent | Nested source/key/membership type definitions; empty `{}` when none |
| `x-gds-dataset` | Dataset name | Dataset name |
| `x-gds-record-type` | Portable record type (e.g. `object`) | Absent |
| `x-gds-section` | Absent | Registered section name |
| `x-gds-canonical-key` | Ordered natural-key field names | Ordered natural-key field names |
| `x-gds-change-set-eligible` | `false` for foundation/reference; `true` for operational | `true` for all 25 |
| `x-gds-database-ids-included` | Absent; catalog carries flag | `false` |
| `x-gds-key-normalization` | Contract below | Absent; actual comparison uses trim U+0020 + Unicode `casefold()` |
| `x-gds-unique-constraints` | List of key-field lists, including canonical key | Absent; backend/record rules enforce Model uniqueness |
| `x-gds-references` | `{columns, target_record_type, target_columns, nullable}[]` | No top-level extension; references appear in nested field types and authoring/validation rules |
| `x-gds-fixed-values` | Object-zone constant map; `{}` for other datasets | Absent |
| `x-gds-population-rules` | Human-readable guidance strings | Human-readable guidance strings |
| `x-gds-columns` | Column guidance objects below | Column guidance objects below |
| `x-gds-record-validation` | Present for 4 datasets listed below | Present for 18 datasets listed below |
| `allOf` | Absent | Only `logical_entity`: type `other` requires string `logical_entity_type_detail`; other types require null |

Metadata comparison normalization is `{version:"1.0", string_field_suffixes:["_code","_name","_schema"], trim_code_points:["U+0020"], case:"unicode-lowercase", unicode_normalization:"none", other_values:"identity"}`. It governs matching; exported text is not globally rewritten to lowercase. Model key comparison uses `casefold()` rather than Metadata's `lower()`. [Metadata key contract](/Users/maazuddinmohammed/main/projects/gds_workbench_v2/mcp_server/gds_etl_workbench/domain/snapshots/metadata.py:37), [Model key normalization](/Users/maazuddinmohammed/main/projects/gds_workbench_v2/mcp_server/gds_etl_workbench/domain/modeling_records.py:83).

```text
x-gds-columns[]:
  name: string
  data_types: string[]
  required: boolean
  nullable: boolean
  description: string
  population_guidance: string
  accepted_values:
    kind: "fixed" | "literal" | "reference" | "constrained" | "freeform"
    values: (string | number | boolean | null)[]
    references: array of:
      record_type: string
      datasets: string[]
      column: string
      composite_columns: string[]
      target_columns: string[]
      nullable: boolean
    constraints: object
  examples: (string | number | boolean | null)[]

x-gds-record-validation:
  version: "1.0"
  rules: string[]
```

Portable validation rule names:

- Metadata: `tenant` → `tenant_gds_connection_key`; `ingestion_object_mapping` → `ingestion_object_endpoints`; `ingestion_attribute_mapping` → `ingestion_attribute_endpoints`; `copy` → `copy_record_limit`.
- Model: each of `model_details`, `profiling_profile`, `analysis_result`, `modeling_assertion_document`, `modeling_assertion_record`, `conceptual_object`, `conceptual_relationship`, `logical_entity`, `logical_attribute`, `logical_relationship`, `dimensional_entity`, `dimensional_attribute`, `dimensional_relationship`, `mapping_object`, `mapping_attribute`, `generated_code`, `validation_group`, `validation_check` publishes one rule of the same name, except `model_details` publishes `model_details_policy`.

These extension rule names instruct local validators; plain JSON Schema alone does not implement all server checks. Column descriptions and population rules are guidance, not proof a condition is enforced. In particular, guidance that confines Scope to the Model's Source Tenant is narrower than current backend eligibility, which can permit authorized cross-Tenant Source/Bronze inputs. See table validation notes for enforcement. [Schema construction](/Users/maazuddinmohammed/main/projects/gds_workbench_v2/mcp_server/gds_etl_workbench/tools/snapshots/metadata/archive.py:77), [Model schema construction](/Users/maazuddinmohammed/main/projects/gds_workbench_v2/mcp_server/gds_etl_workbench/domain/snapshots/model.py:281), [column schema](/Users/maazuddinmohammed/main/projects/gds_workbench_v2/mcp_server/gds_etl_workbench/domain/snapshots/description.py:28), [portable rule registry](/Users/maazuddinmohammed/main/projects/gds_workbench_v2/mcp_server/gds_etl_workbench/domain/portable_validation.py:9).

`lookup.jsonl` exists only for the ten datasets marked in §2.6. Every lookup row contains **canonical-key fields + extra lookup fields + `line: integer >= 1`**. `line` is the matching one-based line number in the dataset's `rows.jsonl`; lookup rows and data rows have equal counts. It is an index for selecting full records, not another independently editable dataset. [Lookup generation](/Users/maazuddinmohammed/main/projects/gds_workbench_v2/mcp_server/gds_etl_workbench/tools/snapshots/metadata/archive.py:171).

For the following field tables: `string | null` means the key may hold JSON null; “Required” means omission is disallowed in the schema. Bounds use JSON Schema names. `pattern="\\S"` means at least one non-whitespace character. Common Model status values are `active`, `inactive`, `deprecated`; confidence is `low`, `medium`, `high`; cardinality is `one_to_one`, `one_to_many`, `many_to_one`, `many_to_many`. The detailed tables retain each field's actual enum.

Internal-only distinction: the Python `ModelSnapshot` aggregation object uses `schema_version="1.0"` and contains the 11 nested section objects. The ZIP writer splits it into the files above and publishes archive version `2.0`; no `snapshot.json` containing that internal object is emitted. [Internal aggregate](/Users/maazuddinmohammed/main/projects/gds_workbench_v2/mcp_server/gds_etl_workbench/domain/snapshots/model.py:218).

### 2.6 Metadata dataset registry and complete row schemas

Every dataset below has both its `rows.jsonl` and its named JSON Schema file, even when empty. Datasets sharing `ObjectRecord` or `AttributeRecord` use the same fields; Object schemas additionally fix `zone_code` to their directory zone. `line` exists only in lookup files.

| Section | Dataset | Source table | Canonical key | Extra lookup fields (in addition to key and `line`) | Change Set eligible |
|---|---|---|---|---|---|
| foundational | `project` | `core.project` | `project_code` | No lookup file | No |
| foundational | `tenant` | `core.tenant` | `tenant_code` | No lookup file | No |
| foundational | `system` | `core.system` | `system_code` | No lookup file | No |
| foundational | `connection` | `core.connection` | `tenant_code`, `system_code`, `connection_code` | No lookup file | No |
| reference | `system_type` | `reference.system_type` | `system_type_code` | No lookup file | No |
| reference | `connection_type` | `reference.connection_type` | `connection_type_code` | No lookup file | No |
| reference | `object_type` | `reference.object_type` | `object_type_code` | No lookup file | No |
| reference | `zone` | `reference.zone` | `zone_code` | No lookup file | No |
| reference | `chunk_type` | `reference.chunk_type` | `chunk_type_name` | No lookup file | No |
| reference | `file_type` | `reference.file_type` | `file_type_name` | No lookup file | No |
| reference | `data_operation` | `reference.data_operation` | `data_operation_name` | No lookup file | No |
| reference | `process_type` | `reference.process_type` | `process_type_name` | No lookup file | No |
| operational | `source_object` | `core.object` | `tenant_code`, `system_code`, `connection_code`, `object_schema`, `object_name` | `source_tenant_code`, `object_type_code`, `zone_code`, `is_locked`, `is_active` | Yes |
| operational | `source_attribute` | `core.attribute` | `tenant_code`, `system_code`, `connection_code`, `object_schema`, `object_name`, `attribute_name` | `attribute_data_type`, `attribute_inferred_data_type`, `is_natural_key`, `is_locked`, `is_active` | Yes |
| operational | `bronze_object` | `core.object` | `tenant_code`, `system_code`, `connection_code`, `object_schema`, `object_name` | `source_tenant_code`, `object_type_code`, `zone_code`, `is_locked`, `is_active` | Yes |
| operational | `bronze_attribute` | `core.attribute` | `tenant_code`, `system_code`, `connection_code`, `object_schema`, `object_name`, `attribute_name` | `attribute_data_type`, `attribute_inferred_data_type`, `is_natural_key`, `is_locked`, `is_active` | Yes |
| operational | `silver_object` | `core.object` | `tenant_code`, `system_code`, `connection_code`, `object_schema`, `object_name` | `source_tenant_code`, `object_type_code`, `zone_code`, `is_locked`, `is_active` | Yes |
| operational | `silver_attribute` | `core.attribute` | `tenant_code`, `system_code`, `connection_code`, `object_schema`, `object_name`, `attribute_name` | `attribute_data_type`, `attribute_inferred_data_type`, `is_natural_key`, `is_locked`, `is_active` | Yes |
| operational | `gold_object` | `core.object` | `tenant_code`, `system_code`, `connection_code`, `object_schema`, `object_name` | `source_tenant_code`, `object_type_code`, `zone_code`, `is_locked`, `is_active` | Yes |
| operational | `gold_attribute` | `core.attribute` | `tenant_code`, `system_code`, `connection_code`, `object_schema`, `object_name`, `attribute_name` | `attribute_data_type`, `attribute_inferred_data_type`, `is_natural_key`, `is_locked`, `is_active` | Yes |
| operational | `ingestion_object_mapping` | `core.ingestion_object_mapping` | `source_tenant_code`, `source_system_code`, `source_connection_code`, `source_object_schema`, `source_object_name`, `target_tenant_code`, `target_system_code`, `target_connection_code`, `target_object_schema`, `target_object_name` | No lookup file | Yes |
| operational | `ingestion_attribute_mapping` | `core.ingestion_attribute_mapping` | `source_tenant_code`, `source_system_code`, `source_connection_code`, `source_object_schema`, `source_object_name`, `source_attribute_name`, `target_tenant_code`, `target_system_code`, `target_connection_code`, `target_object_schema`, `target_object_name`, `target_attribute_name` | No lookup file | Yes |
| operational | `copy_group` | `core.copy_group` | `tenant_code`, `system_code`, `copy_group_name` | No lookup file | Yes |
| operational | `member_group` | `core.member_group` | `tenant_code`, `system_code`, `member_group_name` | No lookup file | Yes |
| operational | `copy_group_control` | `core.copy_group_control` | `tenant_code`, `system_code`, `copy_group_name`, `member_group_name` | `copy_group_control_last_run_time` | Yes |
| operational | `copy` | `core.copy` | `tenant_code`, `system_code`, `copy_group_name`, `source_tenant_code`, `source_system_code`, `source_connection_code`, `source_object_schema`, `source_object_name`, `target_tenant_code`, `target_system_code`, `target_connection_code`, `target_object_schema`, `target_object_name` | `copy_source_order`, `is_active` | Yes |
| operational | `process_group` | `core.process_group` | `tenant_code`, `system_code`, `zone_code`, `process_group_name` | No lookup file | Yes |
| operational | `process` | `core.process` | `tenant_code`, `system_code`, `zone_code`, `process_group_name`, `process_execution_order`, `process_location`, `process_executable` | No lookup file | Yes |

#### Metadata rows: `project`

Source: [ProjectRecord](/Users/maazuddinmohammed/main/projects/gds_workbench_v2/mcp_server/gds_etl_workbench/domain/metadata_records.py:35).

| Field | JSON type / allowed values / bounds | Required in contract |
|---|---|---|
| `project_code` | `string [minLength=1; maxLength=100; pattern="\\S"]` | Yes |
| `project_name` | `string [minLength=1; maxLength=200; pattern="\\S"]` | Yes |
| `project_description` | `string \| null` | Yes |
| `is_active` | `boolean` | Yes |

#### Metadata rows: `tenant`

Source: [TenantRecord](/Users/maazuddinmohammed/main/projects/gds_workbench_v2/mcp_server/gds_etl_workbench/domain/metadata_records.py:42).

| Field | JSON type / allowed values / bounds | Required in contract |
|---|---|---|
| `tenant_code` | `string [minLength=1; maxLength=100; pattern="\\S"]` | Yes |
| `project_code` | `string [minLength=1; maxLength=100; pattern="\\S"]` | Yes |
| `tenant_name` | `string [minLength=1; maxLength=200; pattern="\\S"]` | Yes |
| `tenant_description` | `string \| null` | Yes |
| `tenant_catalog` | `string [minLength=1; maxLength=255]` | Yes |
| `gds_admin_catalog` | `string [minLength=1; maxLength=255]` | Yes |
| `gds_connection_tenant_code` | `string [minLength=1; maxLength=100; pattern="\\S"] \| null` | Yes |
| `gds_connection_system_code` | `string [minLength=1; maxLength=100; pattern="\\S"] \| null` | Yes |
| `gds_connection_code` | `string [minLength=1; maxLength=100; pattern="\\S"] \| null` | Yes |
| `tenant_visibility` | `enum("global", "private")` | Yes |
| `is_active` | `boolean` | Yes |

Natural-key references:

- `project_code` → `project`(`project_code`); nullable=false.

- `gds_connection_tenant_code, gds_connection_system_code, gds_connection_code` → `connection`(`tenant_code, system_code, connection_code`); nullable=true.

#### Metadata rows: `system`

Source: [SystemRecord](/Users/maazuddinmohammed/main/projects/gds_workbench_v2/mcp_server/gds_etl_workbench/domain/metadata_records.py:69).

| Field | JSON type / allowed values / bounds | Required in contract |
|---|---|---|
| `system_code` | `string [minLength=1; maxLength=100; pattern="\\S"]` | Yes |
| `system_name` | `string [minLength=1; maxLength=200; pattern="\\S"]` | Yes |
| `system_description` | `string \| null` | Yes |
| `system_type_code` | `string [minLength=1; maxLength=100; pattern="\\S"]` | Yes |
| `is_active` | `boolean` | Yes |

Natural-key references:

- `system_type_code` → `system_type`(`system_type_code`); nullable=false.

#### Metadata rows: `connection`

Source: [ConnectionRecord](/Users/maazuddinmohammed/main/projects/gds_workbench_v2/mcp_server/gds_etl_workbench/domain/metadata_records.py:77).

| Field | JSON type / allowed values / bounds | Required in contract |
|---|---|---|
| `tenant_code` | `string [minLength=1; maxLength=100; pattern="\\S"]` | Yes |
| `system_code` | `string [minLength=1; maxLength=100; pattern="\\S"]` | Yes |
| `connection_code` | `string [minLength=1; maxLength=100; pattern="\\S"]` | Yes |
| `connection_name` | `string [minLength=1; maxLength=200; pattern="\\S"]` | Yes |
| `connection_description` | `string \| null` | No; default `null` |
| `connection_type_code` | `string [minLength=1; maxLength=100; pattern="\\S"]` | Yes |
| `has_foreign_catalog` | `boolean` | Yes |
| `foreign_catalog` | `string [maxLength=255] \| null` | Yes |
| `is_global_data_store` | `boolean` | Yes |
| `is_active` | `boolean` | Yes |

Natural-key references:

- `tenant_code` → `tenant`(`tenant_code`); nullable=false.

- `system_code` → `system`(`system_code`); nullable=false.

- `connection_type_code` → `connection_type`(`connection_type_code`); nullable=false.

#### Metadata rows: `system_type`

Source: [SystemTypeRecord](/Users/maazuddinmohammed/main/projects/gds_workbench_v2/mcp_server/gds_etl_workbench/domain/metadata_records.py:90).

| Field | JSON type / allowed values / bounds | Required in contract |
|---|---|---|
| `system_type_code` | `string [minLength=1; maxLength=100; pattern="\\S"]` | Yes |
| `system_type_name` | `string [minLength=1; maxLength=200; pattern="\\S"]` | Yes |
| `system_type_description` | `string \| null` | Yes |
| `is_active` | `boolean` | Yes |

#### Metadata rows: `connection_type`

Source: [ConnectionTypeRecord](/Users/maazuddinmohammed/main/projects/gds_workbench_v2/mcp_server/gds_etl_workbench/domain/metadata_records.py:97).

| Field | JSON type / allowed values / bounds | Required in contract |
|---|---|---|
| `connection_type_code` | `string [minLength=1; maxLength=100; pattern="\\S"]` | Yes |
| `connection_type_name` | `string [minLength=1; maxLength=200; pattern="\\S"]` | Yes |
| `connection_type_description` | `string \| null` | Yes |
| `is_active` | `boolean` | Yes |

#### Metadata rows: `object_type`

Source: [ObjectTypeRecord](/Users/maazuddinmohammed/main/projects/gds_workbench_v2/mcp_server/gds_etl_workbench/domain/metadata_records.py:104).

| Field | JSON type / allowed values / bounds | Required in contract |
|---|---|---|
| `object_type_code` | `string [minLength=1; maxLength=100; pattern="\\S"]` | Yes |
| `object_type_name` | `string [minLength=1; maxLength=200; pattern="\\S"]` | Yes |
| `object_type_description` | `string \| null` | Yes |
| `is_active` | `boolean` | Yes |

#### Metadata rows: `zone`

Source: [ZoneRecord](/Users/maazuddinmohammed/main/projects/gds_workbench_v2/mcp_server/gds_etl_workbench/domain/metadata_records.py:111).

| Field | JSON type / allowed values / bounds | Required in contract |
|---|---|---|
| `zone_code` | `string [minLength=1; maxLength=30; pattern="\\S"]` | Yes |
| `zone_name` | `string [minLength=1; maxLength=200; pattern="\\S"]` | Yes |
| `zone_description` | `string \| null` | Yes |
| `is_active` | `boolean` | Yes |

Additional unique key: `zone_name`.

#### Metadata rows: `chunk_type`

Source: [ChunkTypeRecord](/Users/maazuddinmohammed/main/projects/gds_workbench_v2/mcp_server/gds_etl_workbench/domain/metadata_records.py:121).

| Field | JSON type / allowed values / bounds | Required in contract |
|---|---|---|
| `chunk_type_name` | `string [minLength=1; maxLength=200; pattern="\\S"]` | Yes |
| `chunk_type_description` | `string \| null` | Yes |
| `is_active` | `boolean` | Yes |

#### Metadata rows: `file_type`

Source: [FileTypeRecord](/Users/maazuddinmohammed/main/projects/gds_workbench_v2/mcp_server/gds_etl_workbench/domain/metadata_records.py:127).

| Field | JSON type / allowed values / bounds | Required in contract |
|---|---|---|
| `file_type_name` | `string [minLength=1; maxLength=200; pattern="\\S"]` | Yes |
| `file_type_description` | `string \| null` | Yes |
| `is_active` | `boolean` | Yes |

#### Metadata rows: `data_operation`

Source: [DataOperationRecord](/Users/maazuddinmohammed/main/projects/gds_workbench_v2/mcp_server/gds_etl_workbench/domain/metadata_records.py:133).

| Field | JSON type / allowed values / bounds | Required in contract |
|---|---|---|
| `data_operation_name` | `string [minLength=1; maxLength=200; pattern="\\S"]` | Yes |
| `data_operation_description` | `string \| null` | Yes |
| `is_active` | `boolean` | Yes |

#### Metadata rows: `process_type`

Source: [ProcessTypeRecord](/Users/maazuddinmohammed/main/projects/gds_workbench_v2/mcp_server/gds_etl_workbench/domain/metadata_records.py:139).

| Field | JSON type / allowed values / bounds | Required in contract |
|---|---|---|
| `process_type_name` | `string [minLength=1; maxLength=200; pattern="\\S"]` | Yes |
| `process_type_description` | `string \| null` | Yes |
| `is_active` | `boolean` | Yes |

#### Metadata rows: `source_object`, `bronze_object`, `silver_object`, `gold_object`

Source: [ObjectRecord](/Users/maazuddinmohammed/main/projects/gds_workbench_v2/mcp_server/gds_etl_workbench/domain/metadata_records.py:145).

| Field | JSON type / allowed values / bounds | Required in contract |
|---|---|---|
| `tenant_code` | `string [minLength=1; maxLength=100; pattern="\\S"]` | Yes |
| `system_code` | `string [minLength=1; maxLength=100; pattern="\\S"]` | Yes |
| `connection_code` | `string [minLength=1; maxLength=100; pattern="\\S"]` | Yes |
| `source_tenant_code` | `string [minLength=1; maxLength=100; pattern="\\S"]` | Yes |
| `object_schema` | `string [minLength=1; maxLength=400; pattern="\\S"]` | Yes |
| `object_name` | `string [minLength=1; maxLength=400; pattern="\\S"]` | Yes |
| `fc_object_schema` | `string [maxLength=400] \| null` | Yes |
| `fc_object_name` | `string [maxLength=400] \| null` | Yes |
| `object_transformation` | `string \| null` | Yes |
| `object_description` | `string \| null` | Yes |
| `batch_attribute_name` | `string [maxLength=400] \| null` | Yes |
| `object_type_code` | `string [minLength=1; maxLength=100; pattern="\\S"]` | Yes |
| `zone_code` | `enum("source", "bronze", "silver", "gold")` | Yes |
| `is_locked` | `boolean` | Yes |
| `is_active` | `boolean` | Yes |

Each Object dataset fixes `zone_code` to `source`, `bronze`, `silver`, or `gold` respectively.

#### Metadata rows: `source_attribute`, `bronze_attribute`, `silver_attribute`, `gold_attribute`

Source: [AttributeRecord](/Users/maazuddinmohammed/main/projects/gds_workbench_v2/mcp_server/gds_etl_workbench/domain/metadata_records.py:163).

| Field | JSON type / allowed values / bounds | Required in contract |
|---|---|---|
| `tenant_code` | `string [minLength=1; maxLength=100; pattern="\\S"]` | Yes |
| `system_code` | `string [minLength=1; maxLength=100; pattern="\\S"]` | Yes |
| `connection_code` | `string [minLength=1; maxLength=100; pattern="\\S"]` | Yes |
| `object_schema` | `string [minLength=1; maxLength=400; pattern="\\S"]` | Yes |
| `object_name` | `string [minLength=1; maxLength=400; pattern="\\S"]` | Yes |
| `attribute_name` | `string [minLength=1; maxLength=400; pattern="\\S"]` | Yes |
| `fc_attribute_name` | `string [maxLength=400] \| null` | Yes |
| `attribute_ordinal_position` | `integer [maximum=2147483647; exclusiveMinimum=0]` | Yes |
| `attribute_description` | `string \| null` | Yes |
| `attribute_data_type` | `string [minLength=1; maxLength=100]` | Yes |
| `attribute_inferred_data_type` | `string [minLength=1; maxLength=100; pattern="\\S"] \| null` | Yes |
| `attribute_nullability` | `boolean` | Yes |
| `attribute_custom_code` | `string \| null` | Yes |
| `is_surrogate_key` | `boolean` | Yes |
| `is_natural_key` | `boolean` | Yes |
| `is_meta_data` | `boolean` | Yes |
| `is_masking_required` | `boolean` | Yes |
| `is_mapped` | `boolean` | Yes |
| `is_purge` | `boolean` | Yes |
| `is_locked` | `boolean` | Yes |
| `is_active` | `boolean` | Yes |

Additional unique key: Object canonical key plus `attribute_ordinal_position`.

#### Metadata rows: `ingestion_object_mapping`

Source: [IngestionObjectMappingRecord](/Users/maazuddinmohammed/main/projects/gds_workbench_v2/mcp_server/gds_etl_workbench/domain/metadata_records.py:190).

| Field | JSON type / allowed values / bounds | Required in contract |
|---|---|---|
| `source_tenant_code` | `string [minLength=1; maxLength=100; pattern="\\S"]` | Yes |
| `source_system_code` | `string [minLength=1; maxLength=100; pattern="\\S"]` | Yes |
| `source_connection_code` | `string [minLength=1; maxLength=100; pattern="\\S"]` | Yes |
| `source_object_schema` | `string [minLength=1; maxLength=400; pattern="\\S"]` | Yes |
| `source_object_name` | `string [minLength=1; maxLength=400; pattern="\\S"]` | Yes |
| `target_tenant_code` | `string [minLength=1; maxLength=100; pattern="\\S"]` | Yes |
| `target_system_code` | `string [minLength=1; maxLength=100; pattern="\\S"]` | Yes |
| `target_connection_code` | `string [minLength=1; maxLength=100; pattern="\\S"]` | Yes |
| `target_object_schema` | `string [minLength=1; maxLength=400; pattern="\\S"]` | Yes |
| `target_object_name` | `string [minLength=1; maxLength=400; pattern="\\S"]` | Yes |
| `is_active` | `boolean` | Yes |

Natural-key references:

- `source_tenant_code, source_system_code, source_connection_code, source_object_schema, source_object_name` → `object`(`tenant_code, system_code, connection_code, object_schema, object_name`); nullable=false.

- `target_tenant_code, target_system_code, target_connection_code, target_object_schema, target_object_name` → `object`(`tenant_code, system_code, connection_code, object_schema, object_name`); nullable=false.

#### Metadata rows: `ingestion_attribute_mapping`

Source: [IngestionAttributeMappingRecord](/Users/maazuddinmohammed/main/projects/gds_workbench_v2/mcp_server/gds_etl_workbench/domain/metadata_records.py:226).

| Field | JSON type / allowed values / bounds | Required in contract |
|---|---|---|
| `source_tenant_code` | `string [minLength=1; maxLength=100; pattern="\\S"]` | Yes |
| `source_system_code` | `string [minLength=1; maxLength=100; pattern="\\S"]` | Yes |
| `source_connection_code` | `string [minLength=1; maxLength=100; pattern="\\S"]` | Yes |
| `source_object_schema` | `string [minLength=1; maxLength=400; pattern="\\S"]` | Yes |
| `source_object_name` | `string [minLength=1; maxLength=400; pattern="\\S"]` | Yes |
| `source_attribute_name` | `string [minLength=1; maxLength=400; pattern="\\S"]` | Yes |
| `target_tenant_code` | `string [minLength=1; maxLength=100; pattern="\\S"]` | Yes |
| `target_system_code` | `string [minLength=1; maxLength=100; pattern="\\S"]` | Yes |
| `target_connection_code` | `string [minLength=1; maxLength=100; pattern="\\S"]` | Yes |
| `target_object_schema` | `string [minLength=1; maxLength=400; pattern="\\S"]` | Yes |
| `target_object_name` | `string [minLength=1; maxLength=400; pattern="\\S"]` | Yes |
| `target_attribute_name` | `string [minLength=1; maxLength=400; pattern="\\S"]` | Yes |
| `is_active` | `boolean` | Yes |

Natural-key references:

- `source_tenant_code, source_system_code, source_connection_code, source_object_schema, source_object_name, target_tenant_code, target_system_code, target_connection_code, target_object_schema, target_object_name` → `ingestion_object_mapping`(`source_tenant_code, source_system_code, source_connection_code, source_object_schema, source_object_name, target_tenant_code, target_system_code, target_connection_code, target_object_schema, target_object_name`); nullable=false.

- `source_tenant_code, source_system_code, source_connection_code, source_object_schema, source_object_name, source_attribute_name` → `attribute`(`tenant_code, system_code, connection_code, object_schema, object_name, attribute_name`); nullable=false.

- `target_tenant_code, target_system_code, target_connection_code, target_object_schema, target_object_name, target_attribute_name` → `attribute`(`tenant_code, system_code, connection_code, object_schema, object_name, attribute_name`); nullable=false.

#### Metadata rows: `copy_group`

Source: [CopyGroupRecord](/Users/maazuddinmohammed/main/projects/gds_workbench_v2/mcp_server/gds_etl_workbench/domain/metadata_records.py:266).

| Field | JSON type / allowed values / bounds | Required in contract |
|---|---|---|
| `tenant_code` | `string [minLength=1; maxLength=100; pattern="\\S"]` | Yes |
| `system_code` | `string [minLength=1; maxLength=100; pattern="\\S"]` | Yes |
| `copy_group_name` | `string [minLength=1; maxLength=200; pattern="\\S"]` | Yes |
| `copy_group_description` | `string \| null` | Yes |
| `is_member_group_required` | `boolean` | Yes |
| `is_active` | `boolean` | Yes |

Natural-key references:

- `tenant_code` → `tenant`(`tenant_code`); nullable=false.

- `system_code` → `system`(`system_code`); nullable=false.

#### Metadata rows: `member_group`

Source: [MemberGroupRecord](/Users/maazuddinmohammed/main/projects/gds_workbench_v2/mcp_server/gds_etl_workbench/domain/metadata_records.py:275).

| Field | JSON type / allowed values / bounds | Required in contract |
|---|---|---|
| `tenant_code` | `string [minLength=1; maxLength=100; pattern="\\S"]` | Yes |
| `system_code` | `string [minLength=1; maxLength=100; pattern="\\S"]` | Yes |
| `member_group_name` | `string [minLength=1; maxLength=200; pattern="\\S"]` | Yes |
| `member_group_description` | `string \| null` | Yes |
| `member_group_initial_load_date` | `string (date) \| null` | Yes |
| `is_active` | `boolean` | Yes |

Natural-key references:

- `tenant_code` → `tenant`(`tenant_code`); nullable=false.

- `system_code` → `system`(`system_code`); nullable=false.

#### Metadata rows: `copy_group_control`

Source: [CopyGroupControlRecord](/Users/maazuddinmohammed/main/projects/gds_workbench_v2/mcp_server/gds_etl_workbench/domain/metadata_records.py:284).

| Field | JSON type / allowed values / bounds | Required in contract |
|---|---|---|
| `tenant_code` | `string [minLength=1; maxLength=100; pattern="\\S"]` | Yes |
| `system_code` | `string [minLength=1; maxLength=100; pattern="\\S"]` | Yes |
| `copy_group_name` | `string [minLength=1; maxLength=200; pattern="\\S"]` | Yes |
| `member_group_name` | `string [minLength=1; maxLength=200; pattern="\\S"] \| null` | Yes |
| `copy_group_control_initial_load_date` | `string (date) \| null` | Yes |
| `copy_group_control_last_run_time` | `string (date-time) \| null` | Yes |
| `copy_group_control_last_run_value` | `string [minLength=1; pattern="\\S"] \| null` | Yes |

Natural-key references:

- `tenant_code, system_code, copy_group_name` → `copy_group`(`tenant_code, system_code, copy_group_name`); nullable=false.

- `tenant_code, system_code, member_group_name` → `member_group`(`tenant_code, system_code, member_group_name`); nullable=true.

#### Metadata rows: `copy`

Source: [CopyRecord](/Users/maazuddinmohammed/main/projects/gds_workbench_v2/mcp_server/gds_etl_workbench/domain/metadata_records.py:296).

| Field | JSON type / allowed values / bounds | Required in contract |
|---|---|---|
| `tenant_code` | `string [minLength=1; maxLength=100; pattern="\\S"]` | Yes |
| `system_code` | `string [minLength=1; maxLength=100; pattern="\\S"]` | Yes |
| `copy_group_name` | `string [minLength=1; maxLength=200; pattern="\\S"]` | Yes |
| `source_tenant_code` | `string [minLength=1; maxLength=100; pattern="\\S"]` | Yes |
| `source_system_code` | `string [minLength=1; maxLength=100; pattern="\\S"]` | Yes |
| `source_connection_code` | `string [minLength=1; maxLength=100; pattern="\\S"]` | Yes |
| `source_object_schema` | `string [minLength=1; maxLength=400; pattern="\\S"]` | Yes |
| `source_object_name` | `string [minLength=1; maxLength=400; pattern="\\S"]` | Yes |
| `target_tenant_code` | `string [minLength=1; maxLength=100; pattern="\\S"]` | Yes |
| `target_system_code` | `string [minLength=1; maxLength=100; pattern="\\S"]` | Yes |
| `target_connection_code` | `string [minLength=1; maxLength=100; pattern="\\S"]` | Yes |
| `target_object_schema` | `string [minLength=1; maxLength=400; pattern="\\S"]` | Yes |
| `target_object_name` | `string [minLength=1; maxLength=400; pattern="\\S"]` | Yes |
| `copy_source_record_limit` | `string [pattern="^-?[0-9]+$"] \| null` | Yes |
| `copy_source_record_limit_attribute` | `string [maxLength=400] \| null` | Yes |
| `chunk_type_name` | `string [minLength=1; maxLength=200; pattern="\\S"] \| null` | Yes |
| `copy_source_initial_sql_script` | `string \| null` | Yes |
| `copy_source_incremental_sql_script` | `string \| null` | Yes |
| `copy_source_file_name` | `string \| null` | Yes |
| `copy_source_file_pattern` | `string \| null` | Yes |
| `copy_source_file_delimiter` | `string [maxLength=20] \| null` | Yes |
| `source_file_type_name` | `string [minLength=1; maxLength=200; pattern="\\S"] \| null` | Yes |
| `copy_source_order` | `integer [maximum=2147483647; exclusiveMinimum=0]` | Yes |
| `source_data_operation_name` | `string [minLength=1; maxLength=200; pattern="\\S"]` | Yes |
| `target_data_operation_name` | `string [minLength=1; maxLength=200; pattern="\\S"]` | Yes |
| `is_active` | `boolean` | Yes |

Natural-key references:

- `tenant_code, system_code, copy_group_name` → `copy_group`(`tenant_code, system_code, copy_group_name`); nullable=false.

- `source_tenant_code, source_system_code, source_connection_code, source_object_schema, source_object_name, target_tenant_code, target_system_code, target_connection_code, target_object_schema, target_object_name` → `ingestion_object_mapping`(`source_tenant_code, source_system_code, source_connection_code, source_object_schema, source_object_name, target_tenant_code, target_system_code, target_connection_code, target_object_schema, target_object_name`); nullable=false.

- `chunk_type_name` → `chunk_type`(`chunk_type_name`); nullable=true.

- `source_file_type_name` → `file_type`(`file_type_name`); nullable=true.

- `source_data_operation_name` → `data_operation`(`data_operation_name`); nullable=false.

- `target_data_operation_name` → `data_operation`(`data_operation_name`); nullable=false.

Additional unique key: Copy Group canonical key plus `copy_source_order`.

#### Metadata rows: `process_group`

Source: [ProcessGroupRecord](/Users/maazuddinmohammed/main/projects/gds_workbench_v2/mcp_server/gds_etl_workbench/domain/metadata_records.py:333).

| Field | JSON type / allowed values / bounds | Required in contract |
|---|---|---|
| `tenant_code` | `string [minLength=1; maxLength=100; pattern="\\S"]` | Yes |
| `system_code` | `string [minLength=1; maxLength=100; pattern="\\S"]` | Yes |
| `zone_code` | `string [minLength=1; maxLength=30]` | Yes |
| `process_group_name` | `string [minLength=1; maxLength=200; pattern="\\S"]` | Yes |
| `process_group_description` | `string \| null` | Yes |
| `copy_group_name` | `string [minLength=1; maxLength=200; pattern="\\S"]` | Yes |
| `is_active` | `boolean` | Yes |

Natural-key references:

- `tenant_code` → `tenant`(`tenant_code`); nullable=false.

- `system_code` → `system`(`system_code`); nullable=false.

- `zone_code` → `zone`(`zone_code`); nullable=false.

- `tenant_code, system_code, copy_group_name` → `copy_group`(`tenant_code, system_code, copy_group_name`); nullable=false.

#### Metadata rows: `process`

Source: [ProcessRecord](/Users/maazuddinmohammed/main/projects/gds_workbench_v2/mcp_server/gds_etl_workbench/domain/metadata_records.py:343).

| Field | JSON type / allowed values / bounds | Required in contract |
|---|---|---|
| `tenant_code` | `string [minLength=1; maxLength=100; pattern="\\S"]` | Yes |
| `system_code` | `string [minLength=1; maxLength=100; pattern="\\S"]` | Yes |
| `zone_code` | `string [minLength=1; maxLength=30]` | Yes |
| `process_group_name` | `string [minLength=1; maxLength=200; pattern="\\S"]` | Yes |
| `process_execution_order` | `integer [maximum=2147483647; exclusiveMinimum=0]` | Yes |
| `process_location` | `string [minLength=1; pattern="\\S"]` | Yes |
| `process_executable` | `string [minLength=1; pattern="\\S"]` | Yes |
| `object_tenant_code` | `string [minLength=1; maxLength=100; pattern="\\S"]` | Yes |
| `object_system_code` | `string [minLength=1; maxLength=100; pattern="\\S"]` | Yes |
| `object_connection_code` | `string [minLength=1; maxLength=100; pattern="\\S"]` | Yes |
| `object_schema` | `string [minLength=1; maxLength=400; pattern="\\S"]` | Yes |
| `object_name` | `string [minLength=1; maxLength=400; pattern="\\S"]` | Yes |
| `process_type_name` | `string [minLength=1; maxLength=200; pattern="\\S"]` | Yes |
| `is_active` | `boolean` | Yes |

Natural-key references:

- `tenant_code, system_code, zone_code, process_group_name` → `process_group`(`tenant_code, system_code, zone_code, process_group_name`); nullable=false.

- `object_tenant_code, object_system_code, object_connection_code, object_schema, object_name` → `object`(`tenant_code, system_code, connection_code, object_schema, object_name`); nullable=false.

- `process_type_name` → `process_type`(`process_type_name`); nullable=false.

### 2.7 Model dataset registry and complete row schemas

All 25 Model datasets are Change Set eligible. Population rules below are published guidance; they do not replace actual backend checks (see the cross-Tenant Scope caveat in §2.5). A row can contain nested natural-key/source/membership objects. No separate child JSONL files exist for those nested arrays. Fields with a default are still included in emitted rows: serialization does not omit defaults or nulls.

| Section | Dataset | Canonical key |
|---|---|---|
| model_input_scope | `model_details` | Empty tuple: exactly one Model header row |
| model_input_scope | `model_input_scope` | `tenant_code`, `system_code`, `connection_code`, `object_schema`, `object_name` |
| profiling | `profiling_profile` | `tenant_code`, `system_code`, `connection_code`, `object_schema`, `object_name`, `attribute_name` |
| analysis | `analysis_result` | `from_tenant_code`, `from_system_code`, `from_connection_code`, `from_object_schema`, `from_object_name`, `from_attribute_name`, `to_tenant_code`, `to_system_code`, `to_connection_code`, `to_object_schema`, `to_object_name`, `to_attribute_name`, `relationship_kind` |
| assertion | `modeling_assertion_document` | `modeling_assertion_document_name` |
| assertion | `modeling_assertion_record` | `modeling_assertion_record_key` |
| conceptual | `conceptual_object` | `conceptual_object_name` |
| conceptual | `conceptual_relationship` | `from_conceptual_object_name`, `to_conceptual_object_name`, `conceptual_relationship_name` |
| logical | `logical_submodel` | `logical_submodel_name` |
| logical | `logical_entity` | `logical_entity_name` |
| logical | `logical_attribute` | `logical_entity_name`, `logical_attribute_name` |
| logical | `logical_relationship` | `from_logical_entity_name`, `from_logical_attribute_name`, `to_logical_entity_name`, `to_logical_attribute_name`, `logical_relationship_name` |
| dimensional | `dimensional_submodel` | `dimensional_submodel_name` |
| dimensional | `dimensional_entity` | `dimensional_entity_name` |
| dimensional | `dimensional_attribute` | `dimensional_entity_name`, `dimensional_attribute_name` |
| dimensional | `dimensional_relationship` | `from_dimensional_entity_name`, `from_dimensional_attribute_name`, `to_dimensional_entity_name`, `to_dimensional_attribute_name`, `dimensional_relationship_kind`, `dimensional_relationship_role_name` |
| model_binding | `model_object_binding` | `modeled_entity_type`, `modeled_entity_name` |
| model_binding | `model_attribute_binding` | `modeled_entity_type`, `modeled_entity_name`, `modeled_attribute_name` |
| mapping | `mapping_dependency` | `modeled_entity_type`, `source_system_code` |
| mapping | `mapping_object` | `modeled_entity_type`, `modeled_entity_name`, `source_system_code` |
| mapping | `mapping_attribute` | `modeled_entity_type`, `modeled_entity_name`, `modeled_attribute_name`, `source_system_code` |
| code_generation | `generated_code` | `modeled_entity_type`, `modeled_entity_name`, `artifact_name` |
| code_generation | `generated_code_source_system` | `modeled_entity_type`, `modeled_entity_name`, `artifact_name`, `source_system_code` |
| validation | `validation_group` | `tenant_code`, `system_code`, `validation_group_name` |
| validation | `validation_check` | `tenant_code`, `system_code`, `validation_group_name`, `validation_check_name` |

#### Model rows: `model_details`

Source: [ModelDetailsRecord](/Users/maazuddinmohammed/main/projects/gds_workbench_v2/mcp_server/gds_etl_workbench/domain/modeling_records.py:102).

| Field | JSON type / allowed values / bounds | Required in contract |
|---|---|---|
| `model_name` | `string [minLength=1; maxLength=255; pattern="\\S"]` | Yes |
| `model_description` | `string [minLength=1; maxLength=2000; pattern="\\S"] \| null` | Yes |
| `silver_model_naming_instructions` | `string [minLength=1; maxLength=32768; pattern="\\S"] \| null` | Yes |
| `silver_model_audit_columns_template` | `object<string, JSON value> \| null` | Yes |
| `gold_model_naming_instructions` | `string [minLength=1; maxLength=32768; pattern="\\S"] \| null` | Yes |
| `gold_model_technical_columns_template` | `object<string, JSON value> \| null` | Yes |
| `gold_model_audit_columns_template` | `object<string, JSON value> \| null` | Yes |

Population rules published in the schema:

- Treat Model policy as authoritative when it differs from default naming guidance.

#### Model rows: `model_input_scope`

Source: [ModelInputScopeRecord](/Users/maazuddinmohammed/main/projects/gds_workbench_v2/mcp_server/gds_etl_workbench/domain/modeling_records.py:141).

| Field | JSON type / allowed values / bounds | Required in contract |
|---|---|---|
| `tenant_code` | `string [minLength=1; maxLength=100; pattern="\\S"]` | Yes |
| `system_code` | `string [minLength=1; maxLength=100; pattern="\\S"]` | Yes |
| `connection_code` | `string [minLength=1; maxLength=100; pattern="\\S"]` | Yes |
| `object_schema` | `string [minLength=1; maxLength=400; pattern="\\S"]` | Yes |
| `object_name` | `string [minLength=1; maxLength=400; pattern="\\S"]` | Yes |
| `model_input_scope_is_locked` | `boolean` | Yes |
| `is_active` | `boolean` | Yes |

Population rules published in the schema:

- Select only Source or Bronze Objects whose source Tenant is the Model Tenant.
- When equivalent Source and Bronze Objects are selected, use Bronze unless the user directs otherwise.

#### Model rows: `profiling_profile`

Source: [ProfilingProfileRecord](/Users/maazuddinmohammed/main/projects/gds_workbench_v2/mcp_server/gds_etl_workbench/domain/modeling_records.py:150).

| Field | JSON type / allowed values / bounds | Required in contract |
|---|---|---|
| `tenant_code` | `string [minLength=1; maxLength=100; pattern="\\S"]` | Yes |
| `system_code` | `string [minLength=1; maxLength=100; pattern="\\S"]` | Yes |
| `connection_code` | `string [minLength=1; maxLength=100; pattern="\\S"]` | Yes |
| `object_schema` | `string [minLength=1; maxLength=400; pattern="\\S"]` | Yes |
| `object_name` | `string [minLength=1; maxLength=400; pattern="\\S"]` | Yes |
| `attribute_name` | `string [minLength=1; maxLength=400; pattern="\\S"]` | Yes |
| `row_count` | `integer [minimum=0]` | Yes |
| `non_null_count` | `integer [minimum=0]` | Yes |
| `null_count` | `integer [minimum=0]` | Yes |
| `blank_count` | `integer [minimum=0] \| null` | No; default `null` |
| `distinct_count` | `integer [minimum=0] \| null` | No; default `null` |
| `min_data_length` | `integer [minimum=0] \| null` | No; default `null` |
| `max_data_length` | `integer [minimum=0] \| null` | No; default `null` |
| `avg_data_length` | `number [minimum=0.0] \| string [pattern="^(?!^[-+.]*$)[+-]?0*(?:\\d{0,14}\|(?=[\\d.]{1,21}0*$)\\d{0,14}\\.\\d{0,6}0*$)"] \| null` | No; default `null` |
| `percent_populated` | `number [minimum=0.0; maximum=100.0] \| string [pattern="^(?!^[-+.]*$)[+-]?0*(?:\\d{0,3}\|(?=[\\d.]{1,8}0*$)\\d{0,3}\\.\\d{0,4}0*$)"] \| null` | No; default `null` |
| `percent_duplicates` | `number [minimum=0.0; maximum=100.0] \| string [pattern="^(?!^[-+.]*$)[+-]?0*(?:\\d{0,3}\|(?=[\\d.]{1,8}0*$)\\d{0,3}\\.\\d{0,4}0*$)"] \| null` | No; default `null` |
| `percent_null` | `number [minimum=0.0; maximum=100.0] \| string [pattern="^(?!^[-+.]*$)[+-]?0*(?:\\d{0,3}\|(?=[\\d.]{1,8}0*$)\\d{0,3}\\.\\d{0,4}0*$)"] \| null` | No; default `null` |
| `percent_blank` | `number [minimum=0.0; maximum=100.0] \| string [pattern="^(?!^[-+.]*$)[+-]?0*(?:\\d{0,3}\|(?=[\\d.]{1,8}0*$)\\d{0,3}\\.\\d{0,4}0*$)"] \| null` | No; default `null` |
| `percent_distinct` | `number [minimum=0.0; maximum=100.0] \| string [pattern="^(?!^[-+.]*$)[+-]?0*(?:\\d{0,3}\|(?=[\\d.]{1,8}0*$)\\d{0,3}\\.\\d{0,4}0*$)"] \| null` | No; default `null` |

Decimal values are serialized as strings in snapshots, even where this authoring schema also accepts JSON numbers. `avg_data_length`: up to 20 digits, 6 decimal places; percentages: 0–100, up to 7 digits, 4 decimal places.

Population rules published in the schema:

- Profile every selected Attribute needed to understand shape, quality, keys, or relationships.
- For Source, query only its foreign-catalog catalog/schema/Object/Attribute coordinates; missing coordinates are a blocking error.
- For Bronze, query the physical Object schema, Object name, and Attribute name.

#### Model rows: `analysis_result`

Source: [AnalysisResultRecord](/Users/maazuddinmohammed/main/projects/gds_workbench_v2/mcp_server/gds_etl_workbench/domain/modeling_records.py:252).

| Field | JSON type / allowed values / bounds | Required in contract |
|---|---|---|
| `from_tenant_code` | `string [minLength=1; maxLength=100; pattern="\\S"]` | Yes |
| `from_system_code` | `string [minLength=1; maxLength=100; pattern="\\S"]` | Yes |
| `from_connection_code` | `string [minLength=1; maxLength=100; pattern="\\S"]` | Yes |
| `from_object_schema` | `string [minLength=1; maxLength=400; pattern="\\S"]` | Yes |
| `from_object_name` | `string [minLength=1; maxLength=400; pattern="\\S"]` | Yes |
| `from_attribute_name` | `string [minLength=1; maxLength=400; pattern="\\S"]` | Yes |
| `to_tenant_code` | `string [minLength=1; maxLength=100; pattern="\\S"]` | Yes |
| `to_system_code` | `string [minLength=1; maxLength=100; pattern="\\S"]` | Yes |
| `to_connection_code` | `string [minLength=1; maxLength=100; pattern="\\S"]` | Yes |
| `to_object_schema` | `string [minLength=1; maxLength=400; pattern="\\S"]` | Yes |
| `to_object_name` | `string [minLength=1; maxLength=400; pattern="\\S"]` | Yes |
| `to_attribute_name` | `string [minLength=1; maxLength=400; pattern="\\S"]` | Yes |
| `relationship_kind` | `string [minLength=1; maxLength=100]` | Yes |
| `relationship_confidence` | `enum("low", "medium", "high")` | Yes |
| `relationship_basis` | `string [minLength=1; pattern="\\S"]` | Yes |
| `validation_policy_version` | `string [minLength=1; maxLength=50; pattern="^[0-9]+\\.[0-9]+\\.[0-9]+$"] \| null` | No; default `null` |
| `validation_result` | `enum("supported", "inconclusive", "unsupported") \| null` | No; default `null` |
| `validation_source_non_null_count` | `integer [minimum=0] \| null` | No; default `null` |
| `validation_source_distinct_count` | `integer [minimum=0] \| null` | No; default `null` |
| `validation_target_non_null_count` | `integer [minimum=0] \| null` | No; default `null` |
| `validation_target_distinct_count` | `integer [minimum=0] \| null` | No; default `null` |
| `validation_source_missing_target_count` | `integer [minimum=0] \| null` | No; default `null` |
| `validation_unused_target_count` | `integer [minimum=0] \| null` | No; default `null` |
| `validation_duplicate_target_key_count` | `integer [minimum=0] \| null` | No; default `null` |
| `analysis_result_status` | `enum("active", "inactive", "deprecated")` | Yes |
| `analysis_result_is_locked` | `boolean` | Yes |

Population rules published in the schema:

- Record tested grain, identity, functional-dependency, and relationship findings; keep unsupported or inconclusive findings explicit.

#### Model rows: `modeling_assertion_document`

Source: [ModelingAssertionDocumentRecord](/Users/maazuddinmohammed/main/projects/gds_workbench_v2/mcp_server/gds_etl_workbench/domain/modeling_records.py:313).

| Field | JSON type / allowed values / bounds | Required in contract |
|---|---|---|
| `modeling_assertion_document_name` | `string [minLength=1; maxLength=255; pattern="\\S"]` | Yes |
| `tenant_code` | `string [minLength=1; maxLength=100; pattern="\\S"] \| null` | Yes |
| `system_code` | `string [minLength=1; maxLength=100; pattern="\\S"] \| null` | Yes |
| `modeling_assertion_file_pattern` | `string [minLength=1; maxLength=500; pattern="\\S"] \| null` | Yes |
| `modeling_assertion_document_type` | `string [minLength=1; maxLength=100; pattern="\\S"] \| null` | Yes |
| `modeling_assertion_document_description` | `string [minLength=1; maxLength=2000; pattern="\\S"] \| null` | Yes |
| `modeling_assertion_document_metadata` | `object<string, JSON value>` | Yes |
| `is_active` | `boolean` | Yes |

Population rules published in the schema:

- Describe the local evidence document without storing raw prompts or physical rows.

#### Model rows: `modeling_assertion_record`

Source: [ModelingAssertionRecordRecord](/Users/maazuddinmohammed/main/projects/gds_workbench_v2/mcp_server/gds_etl_workbench/domain/modeling_records.py:349).

| Field | JSON type / allowed values / bounds | Required in contract |
|---|---|---|
| `modeling_assertion_record_key` | `string [minLength=1; maxLength=100; pattern="^[A-Za-z][A-Za-z0-9_.-]{0,99}$"]` | Yes |
| `modeling_assertion_document_name` | `string [minLength=1; maxLength=255; pattern="\\S"]` | Yes |
| `modeling_assertion_record_type` | `string [minLength=1; maxLength=100; pattern="\\S"]` | Yes |
| `modeling_assertion_text` | `string [minLength=1; pattern="\\S"]` | Yes |
| `modeling_assertion_details` | `object<string, JSON value>` | Yes |
| `modeling_assertion_source_location` | `object<string, JSON value> \| null` | Yes |
| `modeling_assertion_applicable_layers` | `array<enum("analysis", "conceptual", "logical", "dimensional", "mapping")>` | Yes |
| `modeling_assertion_confidence` | `enum("low", "medium", "high") \| null` | Yes |
| `modeling_assertion_record_status` | `enum("active", "inactive", "deprecated")` | Yes |
| `modeling_assertion_record_is_locked` | `boolean` | Yes |

Population rules published in the schema:

- Keep each assertion atomic, traceable, and applicable to at least one modeling layer.

#### Model rows: `conceptual_object`

Source: [ConceptualObjectRecord](/Users/maazuddinmohammed/main/projects/gds_workbench_v2/mcp_server/gds_etl_workbench/domain/modeling_records.py:443).

| Field | JSON type / allowed values / bounds | Required in contract |
|---|---|---|
| `conceptual_object_name` | `string [minLength=1; maxLength=255; pattern="\\S"]` | Yes |
| `conceptual_object_definition` | `string [minLength=1; pattern="\\S"]` | Yes |
| `conceptual_object_type` | `string [minLength=1; maxLength=100; pattern="\\S"]` | Yes |
| `conceptual_object_grain` | `string [minLength=1; pattern="\\S"]` | Yes |
| `conceptual_object_aliases` | `array<string>` | Yes |
| `conceptual_object_confidence` | `enum("low", "medium", "high")` | Yes |
| `conceptual_object_status` | `enum("active", "inactive", "deprecated")` | Yes |
| `conceptual_object_is_locked` | `boolean` | Yes |
| `supports` | `array<SupportRecord>` | Yes |

Population rules published in the schema:

- Model compact business concepts, not one Conceptual Object per physical Object or Logical Entity.
- Define the business process and what one occurrence of each concept represents.
- Classify coverage through supports; never duplicate the Logical model.
- Use PascalCase by default unless user or Model policy says otherwise.

#### Model rows: `conceptual_relationship`

Source: [ConceptualRelationshipRecord](/Users/maazuddinmohammed/main/projects/gds_workbench_v2/mcp_server/gds_etl_workbench/domain/modeling_records.py:464).

| Field | JSON type / allowed values / bounds | Required in contract |
|---|---|---|
| `from_conceptual_object_name` | `string [minLength=1; maxLength=255; pattern="\\S"]` | Yes |
| `to_conceptual_object_name` | `string [minLength=1; maxLength=255; pattern="\\S"]` | Yes |
| `conceptual_relationship_name` | `string [minLength=1; maxLength=255; pattern="\\S"]` | Yes |
| `conceptual_relationship_type` | `string [minLength=1; maxLength=100; pattern="\\S"]` | Yes |
| `conceptual_relationship_definition` | `string [minLength=1; pattern="\\S"]` | Yes |
| `conceptual_relationship_cardinality` | `enum("one_to_one", "one_to_many", "many_to_one", "many_to_many") \| "unknown"` | Yes |
| `conceptual_relationship_basis` | `string [minLength=1; pattern="\\S"]` | Yes |
| `conceptual_relationship_cardinality_basis` | `string [minLength=1; pattern="\\S"]` | Yes |
| `conceptual_relationship_confidence` | `enum("low", "medium", "high")` | Yes |
| `conceptual_relationship_status` | `enum("active", "inactive", "deprecated")` | Yes |
| `conceptual_relationship_is_locked` | `boolean` | Yes |
| `supports` | `array<SupportRecord>` | Yes |

Population rules published in the schema:

- Use business relationships and evidence-backed high-level cardinality.

#### Model rows: `logical_submodel`

Source: [LogicalSubmodelRecord](/Users/maazuddinmohammed/main/projects/gds_workbench_v2/mcp_server/gds_etl_workbench/domain/modeling_records.py:574).

| Field | JSON type / allowed values / bounds | Required in contract |
|---|---|---|
| `logical_submodel_name` | `string [minLength=1; maxLength=255; pattern="\\S"]` | Yes |
| `logical_submodel_definition` | `string [minLength=1; pattern="\\S"]` | Yes |
| `logical_submodel_status` | `enum("active", "inactive", "deprecated")` | Yes |
| `logical_submodel_is_locked` | `boolean` | Yes |

Population rules published in the schema:

- Group the normalized operational model by coherent business area.

#### Model rows: `logical_entity`

Source: [LogicalEntityRecord](/Users/maazuddinmohammed/main/projects/gds_workbench_v2/mcp_server/gds_etl_workbench/domain/modeling_records.py:584).

| Field | JSON type / allowed values / bounds | Required in contract |
|---|---|---|
| `logical_entity_name` | `string [minLength=1; maxLength=255; pattern="\\S"]` | Yes |
| `logical_entity_definition` | `string [minLength=1; pattern="\\S"]` | Yes |
| `logical_entity_type` | `enum("core", "reference", "transaction", "event", "bridge", "history", "snapshot", "association", "aggregate", "other")` | Yes |
| `logical_entity_type_detail` | `string [minLength=1; pattern="\\S"] \| null` | Yes |
| `logical_entity_grain` | `string [minLength=1; pattern="\\S"]` | Yes |
| `logical_entity_dependency_order` | `integer [minimum=0]` | Yes |
| `logical_entity_confidence` | `enum("low", "medium", "high")` | Yes |
| `logical_entity_status` | `enum("active", "inactive", "deprecated")` | Yes |
| `logical_entity_is_locked` | `boolean` | Yes |
| `submodels` | `array<SubmodelMembershipRecord>` | Yes |
| `sources` | `array<LogicalEntitySourceRecord>` | Yes |

Population rules published in the schema:

- Build a normalized operational Entity with a clear grain, supported identity, and complete in-scope coverage.
- Apply 1NF, 2NF, and 3NF where supported; split different grains, repeating groups, partial dependencies, transitive dependencies, and genuine associations.
- A physical Object maps one-to-one only after checking grain, dependencies, header/detail structure, history, and cross-System consolidation.
- Use PascalCase by default unless user or Model policy says otherwise.

#### Model rows: `logical_attribute`

Source: [LogicalAttributeRecord](/Users/maazuddinmohammed/main/projects/gds_workbench_v2/mcp_server/gds_etl_workbench/domain/modeling_records.py:623).

| Field | JSON type / allowed values / bounds | Required in contract |
|---|---|---|
| `logical_entity_name` | `string [minLength=1; maxLength=255; pattern="\\S"]` | Yes |
| `logical_attribute_name` | `string [minLength=1; maxLength=255; pattern="\\S"]` | Yes |
| `logical_attribute_definition` | `string [minLength=1; pattern="\\S"]` | Yes |
| `logical_attribute_data_type` | `string [minLength=1; maxLength=100; pattern="\\S"]` | Yes |
| `logical_attribute_is_nullable` | `boolean` | Yes |
| `logical_attribute_is_primary_key` | `boolean` | Yes |
| `logical_attribute_is_natural_key` | `boolean` | Yes |
| `logical_attribute_is_surrogate_key` | `boolean` | Yes |
| `logical_attribute_ordinal_position` | `integer [exclusiveMinimum=0]` | Yes |
| `logical_attribute_is_audit_column` | `boolean` | Yes |
| `logical_attribute_status` | `enum("active", "inactive", "deprecated")` | Yes |
| `logical_attribute_is_locked` | `boolean` | Yes |
| `sources` | `array<AttributeSourceRecord>` | Yes |

Population rules published in the schema:

- Include every physical target Attribute, including audit and constant-valued Attributes.
- Place each Attribute with the Entity whose whole key determines it.
- Use PascalCase; identifier Attributes end in ID unless user or Model policy overrides it.

#### Model rows: `logical_relationship`

Source: [LogicalRelationshipRecord](/Users/maazuddinmohammed/main/projects/gds_workbench_v2/mcp_server/gds_etl_workbench/domain/modeling_records.py:658).

| Field | JSON type / allowed values / bounds | Required in contract |
|---|---|---|
| `logical_relationship_name` | `string [minLength=1; maxLength=255; pattern="\\S"]` | Yes |
| `logical_relationship_definition` | `string [minLength=1; pattern="\\S"]` | Yes |
| `from_logical_entity_name` | `string [minLength=1; maxLength=255; pattern="\\S"]` | Yes |
| `from_logical_attribute_name` | `string [minLength=1; maxLength=255; pattern="\\S"]` | Yes |
| `to_logical_entity_name` | `string [minLength=1; maxLength=255; pattern="\\S"]` | Yes |
| `to_logical_attribute_name` | `string [minLength=1; maxLength=255; pattern="\\S"]` | Yes |
| `logical_relationship_cardinality` | `enum("one_to_one", "one_to_many", "many_to_one", "many_to_many")` | Yes |
| `logical_relationship_confidence` | `enum("low", "medium", "high")` | Yes |
| `logical_relationship_basis` | `string [minLength=1; pattern="\\S"]` | Yes |
| `logical_relationship_cardinality_basis` | `string [minLength=1; pattern="\\S"]` | Yes |
| `logical_relationship_status` | `enum("active", "inactive", "deprecated")` | Yes |
| `logical_relationship_is_locked` | `boolean` | Yes |

Population rules published in the schema:

- Reference existing Logical Entities and Attributes and provide relationship evidence.

#### Model rows: `dimensional_submodel`

Source: [DimensionalSubmodelRecord](/Users/maazuddinmohammed/main/projects/gds_workbench_v2/mcp_server/gds_etl_workbench/domain/modeling_records.py:700).

| Field | JSON type / allowed values / bounds | Required in contract |
|---|---|---|
| `dimensional_submodel_name` | `string [minLength=1; maxLength=255; pattern="\\S"]` | Yes |
| `dimensional_submodel_definition` | `string [minLength=1; pattern="\\S"]` | Yes |
| `dimensional_submodel_status` | `enum("active", "inactive", "deprecated")` | Yes |
| `dimensional_submodel_is_locked` | `boolean` | Yes |

Population rules published in the schema:

- Group Facts and Dimensions around a coherent business process.

#### Model rows: `dimensional_entity`

Source: [DimensionalEntityRecord](/Users/maazuddinmohammed/main/projects/gds_workbench_v2/mcp_server/gds_etl_workbench/domain/modeling_records.py:710).

| Field | JSON type / allowed values / bounds | Required in contract |
|---|---|---|
| `dimensional_entity_name` | `string [minLength=1; maxLength=255; pattern="\\S"]` | Yes |
| `dimensional_entity_definition` | `string [minLength=1; pattern="\\S"]` | Yes |
| `dimensional_entity_type` | `enum("fact", "dimension", "bridge")` | Yes |
| `dimensional_fact_type` | `enum("transaction", "periodic_snapshot", "accumulating_snapshot", "factless") \| null` | Yes |
| `dimensional_entity_grain_definition` | `string [minLength=1; pattern="\\S"] \| null` | Yes |
| `dimensional_entity_dependency_order` | `integer [minimum=0]` | Yes |
| `dimensional_entity_confidence` | `enum("low", "medium", "high")` | Yes |
| `dimensional_entity_status` | `enum("active", "inactive", "deprecated")` | Yes |
| `dimensional_entity_is_locked` | `boolean` | Yes |
| `submodels` | `array<SubmodelMembershipRecord>` | Yes |
| `sources` | `array<DimensionalEntitySourceRecord>` | Yes |

Population rules published in the schema:

- Follow the Kimball sequence: select the business process, declare fact grain, identify Dimensions, then identify Facts.
- Use PascalCase by default unless user or Model policy says otherwise.

#### Model rows: `dimensional_attribute`

Source: [DimensionalAttributeRecord](/Users/maazuddinmohammed/main/projects/gds_workbench_v2/mcp_server/gds_etl_workbench/domain/modeling_records.py:751).

| Field | JSON type / allowed values / bounds | Required in contract |
|---|---|---|
| `dimensional_entity_name` | `string [minLength=1; maxLength=255; pattern="\\S"]` | Yes |
| `dimensional_attribute_name` | `string [minLength=1; maxLength=255; pattern="\\S"]` | Yes |
| `dimensional_attribute_definition` | `string [minLength=1; pattern="\\S"]` | Yes |
| `dimensional_attribute_data_type` | `string [minLength=1; maxLength=100; pattern="\\S"]` | Yes |
| `dimensional_attribute_is_nullable` | `boolean` | Yes |
| `dimensional_attribute_ordinal_position` | `integer [exclusiveMinimum=0]` | Yes |
| `dimensional_attribute_role` | `enum("key", "descriptor", "measure", "degenerate_dimension", "bridge_weight", "technical", "audit")` | Yes |
| `dimensional_attribute_key_role` | `enum("none", "surrogate", "business", "foreign")` | Yes |
| `dimensional_attribute_is_grain_component` | `boolean` | Yes |
| `dimensional_attribute_additivity` | `enum("additive", "semi_additive", "non_additive") \| null` | Yes |
| `dimensional_attribute_default_aggregation` | `string [minLength=1; maxLength=100; pattern="\\S"] \| null` | Yes |
| `dimensional_attribute_aggregation_basis` | `string [minLength=1; pattern="\\S"] \| null` | Yes |
| `dimensional_attribute_change_behavior` | `enum("fixed", "overwrite", "historize") \| null` | Yes |
| `dimensional_attribute_is_audit_column` | `boolean` | Yes |
| `dimensional_attribute_confidence` | `enum("low", "medium", "high")` | Yes |
| `dimensional_attribute_status` | `enum("active", "inactive", "deprecated")` | Yes |
| `dimensional_attribute_is_locked` | `boolean` | Yes |
| `sources` | `array<AttributeSourceRecord>` | Yes |

Population rules published in the schema:

- Include every physical target Attribute, including technical, audit, and constant-valued Attributes.
- Use PascalCase; dimensional key Attributes end in Key unless user or Model policy overrides it.

#### Model rows: `dimensional_relationship`

Source: [DimensionalRelationshipRecord](/Users/maazuddinmohammed/main/projects/gds_workbench_v2/mcp_server/gds_etl_workbench/domain/modeling_records.py:825).

| Field | JSON type / allowed values / bounds | Required in contract |
|---|---|---|
| `dimensional_relationship_name` | `string [minLength=1; maxLength=255; pattern="\\S"]` | Yes |
| `dimensional_relationship_definition` | `string [minLength=1; pattern="\\S"]` | Yes |
| `from_dimensional_entity_name` | `string [minLength=1; maxLength=255; pattern="\\S"]` | Yes |
| `from_dimensional_attribute_name` | `string [minLength=1; maxLength=255; pattern="\\S"]` | Yes |
| `to_dimensional_entity_name` | `string [minLength=1; maxLength=255; pattern="\\S"]` | Yes |
| `to_dimensional_attribute_name` | `string [minLength=1; maxLength=255; pattern="\\S"]` | Yes |
| `dimensional_relationship_kind` | `string [minLength=1; maxLength=50; pattern="\\S"]` | Yes |
| `dimensional_relationship_cardinality` | `enum("one_to_one", "one_to_many", "many_to_one", "many_to_many")` | Yes |
| `dimensional_relationship_is_optional` | `boolean` | Yes |
| `dimensional_relationship_role_name` | `string [minLength=1; maxLength=255; pattern="\\S"] \| null` | Yes |
| `dimensional_relationship_confidence` | `enum("low", "medium", "high")` | Yes |
| `dimensional_relationship_basis` | `string [minLength=1; pattern="\\S"]` | Yes |
| `dimensional_relationship_cardinality_basis` | `string [minLength=1; pattern="\\S"]` | Yes |
| `dimensional_relationship_status` | `enum("active", "inactive", "deprecated")` | Yes |
| `dimensional_relationship_is_locked` | `boolean` | Yes |

Population rules published in the schema:

- Reference existing Dimensional Entities and Attributes and preserve the declared grain.

#### Model rows: `model_object_binding`

Source: [ModelObjectBindingRecord](/Users/maazuddinmohammed/main/projects/gds_workbench_v2/mcp_server/gds_etl_workbench/domain/modeling_records.py:887).

| Field | JSON type / allowed values / bounds | Required in contract |
|---|---|---|
| `tenant_code` | `string [minLength=1; maxLength=100; pattern="\\S"]` | Yes |
| `system_code` | `string [minLength=1; maxLength=100; pattern="\\S"]` | Yes |
| `connection_code` | `string [minLength=1; maxLength=100; pattern="\\S"]` | Yes |
| `object_schema` | `string [minLength=1; maxLength=400; pattern="\\S"]` | Yes |
| `object_name` | `string [minLength=1; maxLength=400; pattern="\\S"]` | Yes |
| `modeled_entity_type` | `enum("logical_entity", "dimensional_entity")` | Yes |
| `modeled_entity_name` | `string [minLength=1; maxLength=255; pattern="\\S"]` | Yes |
| `model_object_binding_status` | `enum("active", "inactive", "deprecated")` | Yes |
| `model_object_binding_is_locked` | `boolean` | Yes |

Population rules published in the schema:

- Bind each modeled Entity to exactly one already-registered Silver or Gold Object.
- Logical bindings target Silver; Dimensional bindings target Gold.
- The target Object source Tenant must equal the Model Tenant even though its physical Connection belongs to GDS.

#### Model rows: `model_attribute_binding`

Source: [ModelAttributeBindingRecord](/Users/maazuddinmohammed/main/projects/gds_workbench_v2/mcp_server/gds_etl_workbench/domain/modeling_records.py:897).

| Field | JSON type / allowed values / bounds | Required in contract |
|---|---|---|
| `modeled_entity_type` | `enum("logical_entity", "dimensional_entity")` | Yes |
| `modeled_entity_name` | `string [minLength=1; maxLength=255; pattern="\\S"]` | Yes |
| `modeled_attribute_name` | `string [minLength=1; maxLength=255; pattern="\\S"]` | Yes |
| `attribute_name` | `string [minLength=1; maxLength=400; pattern="\\S"]` | Yes |
| `model_attribute_binding_status` | `enum("active", "inactive", "deprecated")` | Yes |
| `model_attribute_binding_is_locked` | `boolean` | Yes |

Population rules published in the schema:

- Bind every modeled Attribute exactly once to an Attribute of its parent bound Object.
- Do not omit audit, technical, or constant-valued Attributes.

#### Model rows: `mapping_dependency`

Source: [MappingDependencyRecord](/Users/maazuddinmohammed/main/projects/gds_workbench_v2/mcp_server/gds_etl_workbench/domain/modeling_records.py:879).

| Field | JSON type / allowed values / bounds | Required in contract |
|---|---|---|
| `modeled_entity_type` | `enum("logical_entity", "dimensional_entity")` | Yes |
| `source_system_code` | `string [minLength=1; maxLength=100; pattern="\\S"]` | Yes |
| `source_system_dependency_order` | `integer [minimum=0]` | Yes |
| `mapping_source_system_dependency_status` | `enum("active", "inactive", "deprecated")` | Yes |
| `mapping_source_system_dependency_is_locked` | `boolean` | Yes |

Population rules published in the schema:

- Record source-System dependency order used by Mapping and Code Generation.

#### Model rows: `mapping_object`

Source: [MappingObjectRecord](/Users/maazuddinmohammed/main/projects/gds_workbench_v2/mcp_server/gds_etl_workbench/domain/modeling_records.py:912).

| Field | JSON type / allowed values / bounds | Required in contract |
|---|---|---|
| `modeled_entity_type` | `enum("logical_entity", "dimensional_entity")` | Yes |
| `modeled_entity_name` | `string [minLength=1; maxLength=255; pattern="\\S"]` | Yes |
| `source_system_code` | `string [minLength=1; maxLength=100; pattern="\\S"]` | Yes |
| `output_template_code` | `string [minLength=1; maxLength=100; pattern="\\S"] \| null` | Yes |
| `object_dependency_order` | `integer [minimum=0]` | Yes |
| `mapping_transformation_document` | `object<string, JSON value> \| null` | Yes |
| `object_mapping_status` | `enum("active", "inactive", "deprecated")` | Yes |
| `object_mapping_is_locked` | `boolean` | Yes |

Population rules published in the schema:

- Author one target-oriented Mapping per bound target Entity and source System.
- Store the complete transformation in mapping_transformation_document.
- An Output Template is advisory; without one, use the plugin standard JSON shape unless the user requests another format.

#### Model rows: `mapping_attribute`

Source: [MappingAttributeRecord](/Users/maazuddinmohammed/main/projects/gds_workbench_v2/mcp_server/gds_etl_workbench/domain/modeling_records.py:933).

| Field | JSON type / allowed values / bounds | Required in contract |
|---|---|---|
| `modeled_entity_type` | `enum("logical_entity", "dimensional_entity")` | Yes |
| `modeled_entity_name` | `string [minLength=1; maxLength=255; pattern="\\S"]` | Yes |
| `modeled_attribute_name` | `string [minLength=1; maxLength=255; pattern="\\S"]` | Yes |
| `source_system_code` | `string [minLength=1; maxLength=100; pattern="\\S"]` | Yes |
| `output_template_code` | `string [minLength=1; maxLength=100; pattern="\\S"] \| null` | Yes |
| `attribute_mapping_transformation_document` | `object<string, JSON value> \| null` | Yes |
| `attribute_mapping_status` | `enum("active", "inactive", "deprecated")` | Yes |
| `attribute_mapping_is_locked` | `boolean` | Yes |

Population rules published in the schema:

- Describe how one bound target Attribute is populated for one target/source-System Mapping.
- The transformation document is flexible JSON and may describe direct, derived, or constant logic.

#### Model rows: `generated_code`

Source: [GeneratedCodeRecord](/Users/maazuddinmohammed/main/projects/gds_workbench_v2/mcp_server/gds_etl_workbench/domain/modeling_records.py:960).

| Field | JSON type / allowed values / bounds | Required in contract |
|---|---|---|
| `modeled_entity_type` | `enum("logical_entity", "dimensional_entity")` | Yes |
| `modeled_entity_name` | `string [minLength=1; maxLength=255; pattern="\\S"]` | Yes |
| `artifact_name` | `string [minLength=1; maxLength=400; pattern="\\S"]` | Yes |
| `artifact_type` | `enum("sql_file", "python_file", "python_notebook")` | Yes |
| `generated_code_content` | `string [minLength=1; pattern="\\S"]` | Yes |
| `generated_code_status` | `enum("active", "inactive", "deprecated")` | Yes |
| `generated_code_is_locked` | `boolean` | Yes |

Population rules published in the schema:

- Code Generation decides whether Systems share one file or use separate files.
- artifact_name is a file name only; Process metadata owns deployment paths.
- Review SQL against Mapping first; execute a preflight only under the user's SQL policy.

#### Model rows: `generated_code_source_system`

Source: [GeneratedCodeSourceSystemRecord](/Users/maazuddinmohammed/main/projects/gds_workbench_v2/mcp_server/gds_etl_workbench/domain/modeling_records.py:988).

| Field | JSON type / allowed values / bounds | Required in contract |
|---|---|---|
| `modeled_entity_type` | `enum("logical_entity", "dimensional_entity")` | Yes |
| `modeled_entity_name` | `string [minLength=1; maxLength=255; pattern="\\S"]` | Yes |
| `artifact_name` | `string [minLength=1; maxLength=400; pattern="\\S"]` | Yes |
| `source_system_code` | `string [minLength=1; maxLength=100; pattern="\\S"]` | Yes |
| `generated_code_source_system_status` | `enum("active", "inactive", "deprecated")` | Yes |
| `generated_code_source_system_is_locked` | `boolean` | Yes |

Population rules published in the schema:

- List every source System covered by the named Code Artifact.

#### Model rows: `validation_group`

Source: [ValidationGroupRecord](/Users/maazuddinmohammed/main/projects/gds_workbench_v2/mcp_server/gds_etl_workbench/domain/modeling_records.py:1000).

| Field | JSON type / allowed values / bounds | Required in contract |
|---|---|---|
| `tenant_code` | `string [minLength=1; maxLength=100; pattern="\\S"]` | Yes |
| `system_code` | `string [minLength=1; maxLength=100; pattern="\\S"]` | Yes |
| `validation_group_name` | `string [minLength=1; maxLength=200; pattern="\\S"]` | Yes |
| `validation_group_description` | `string [minLength=1; pattern="\\S"] \| null` | Yes |
| `is_active` | `boolean` | Yes |
| `is_locked` | `boolean` | Yes |

Population rules published in the schema:

- Store Validation definitions only; never persist preflight execution results.

#### Model rows: `validation_check`

Source: [ValidationCheckRecord](/Users/maazuddinmohammed/main/projects/gds_workbench_v2/mcp_server/gds_etl_workbench/domain/modeling_records.py:1022).

| Field | JSON type / allowed values / bounds | Required in contract |
|---|---|---|
| `tenant_code` | `string [minLength=1; maxLength=100; pattern="\\S"]` | Yes |
| `system_code` | `string [minLength=1; maxLength=100; pattern="\\S"]` | Yes |
| `validation_group_name` | `string [minLength=1; maxLength=200; pattern="\\S"]` | Yes |
| `validation_check_name` | `string [minLength=1; maxLength=200; pattern="\\S"]` | Yes |
| `validation_check_description` | `string [minLength=1; pattern="\\S"] \| null` | Yes |
| `validation_category_code` | `string [pattern="^[a-z][a-z0-9_.-]{0,99}$"]` | Yes |
| `validation_severity` | `enum("blocking", "warning", "informational")` | Yes |
| `validation_query_sql` | `string [minLength=1; pattern="\\S"]` | Yes |
| `validation_comparison_query_sql` | `string [minLength=1; pattern="\\S"] \| null` | Yes |
| `validation_result_data_type` | `enum("boolean", "integer", "decimal", "text", "date", "timestamp") \| null` | Yes |
| `validation_comparison_operator` | `enum("executes_successfully", "is_null", "is_not_null", "is_true", "is_false", "equal", "not_equal", "greater_than", "greater_than_or_equal", "less_than", "less_than_or_equal", "in", "not_in")` | Yes |
| `validation_comparison_value_type` | `enum("none", "literal", "literal_list", "query")` | Yes |
| `validation_comparison_value` | `ValidationLiteral \| array<ValidationLiteral> \| null` | Yes |
| `is_active` | `boolean` | Yes |
| `is_locked` | `boolean` | Yes |

Population rules published in the schema:

- Author technical or functional checks from current Mapping and Code without waiting for orchestration load completion.
- Store the check definition, never a preflight result.

#### Nested Model row types (`$defs`)

These are embedded inside parent JSONL rows; they are not additional files. Typed nested objects also reject undeclared fields. Arbitrary `object<string, JSON value>` fields are JSON documents; their content is constrained by the applicable server validators and population rules, not a fixed property list here.

##### `AssertionRecordKey`

| Field | JSON type / allowed values / bounds | Required in contract |
|---|---|---|
| `modeling_assertion_record_key` | `string [minLength=1; maxLength=100; pattern="^[A-Za-z][A-Za-z0-9_.-]{0,99}$"]` | Yes |

##### `AssertionSupportRecord`

| Field | JSON type / allowed values / bounds | Required in contract |
|---|---|---|
| `support_source_type` | `"assertion"` | Yes |
| `assertion_record` | `AssertionRecordKey` | Yes |
| `support_role` | `string [minLength=1; maxLength=255; pattern="\\S"] \| null` | Yes |
| `support_reason` | `string [minLength=1; pattern="\\S"]` | Yes |
| `support_reason_detail` | `string [minLength=1; pattern="\\S"] \| null` | Yes |
| `support_confidence` | `enum("low", "medium", "high")` | Yes |
| `support_status` | `enum("active", "inactive", "deprecated")` | Yes |
| `support_is_locked` | `boolean` | Yes |

##### `ObjectSupportRecord`

| Field | JSON type / allowed values / bounds | Required in contract |
|---|---|---|
| `support_source_type` | `"object"` | Yes |
| `source_object` | `PhysicalObjectKey` | Yes |
| `support_role` | `string [minLength=1; maxLength=255; pattern="\\S"] \| null` | Yes |
| `support_reason` | `string [minLength=1; pattern="\\S"]` | Yes |
| `support_reason_detail` | `string [minLength=1; pattern="\\S"] \| null` | Yes |
| `support_confidence` | `enum("low", "medium", "high")` | Yes |
| `support_status` | `enum("active", "inactive", "deprecated")` | Yes |
| `support_is_locked` | `boolean` | Yes |

##### `PhysicalObjectKey`

| Field | JSON type / allowed values / bounds | Required in contract |
|---|---|---|
| `tenant_code` | `string [minLength=1; maxLength=100; pattern="\\S"]` | Yes |
| `system_code` | `string [minLength=1; maxLength=100; pattern="\\S"]` | Yes |
| `connection_code` | `string [minLength=1; maxLength=100; pattern="\\S"]` | Yes |
| `object_schema` | `string [minLength=1; maxLength=400; pattern="\\S"]` | Yes |
| `object_name` | `string [minLength=1; maxLength=400; pattern="\\S"]` | Yes |

##### `SupportRecord`

`ObjectSupportRecord \| AssertionSupportRecord`

##### `LogicalAssertionSourceRecord`

| Field | JSON type / allowed values / bounds | Required in contract |
|---|---|---|
| `support_source_type` | `"assertion"` | Yes |
| `assertion_record` | `AssertionRecordKey` | Yes |
| `source_order` | `integer [exclusiveMinimum=0] \| null` | No; default `null` |
| `rationale` | `string [minLength=1; pattern="\\S"]` | Yes |
| `status` | `enum("active", "inactive", "deprecated")` | Yes |
| `is_locked` | `boolean` | Yes |

##### `LogicalEntitySourceRecord`

`LogicalObjectSourceRecord \| LogicalAssertionSourceRecord`

##### `LogicalObjectSourceRecord`

| Field | JSON type / allowed values / bounds | Required in contract |
|---|---|---|
| `support_source_type` | `"object"` | Yes |
| `source_object` | `PhysicalObjectKey` | Yes |
| `source_order` | `integer [exclusiveMinimum=0] \| null` | No; default `null` |
| `rationale` | `string [minLength=1; pattern="\\S"]` | Yes |
| `status` | `enum("active", "inactive", "deprecated")` | Yes |
| `is_locked` | `boolean` | Yes |

##### `SubmodelMembershipRecord`

| Field | JSON type / allowed values / bounds | Required in contract |
|---|---|---|
| `submodel_name` | `string [minLength=1; maxLength=255; pattern="\\S"]` | Yes |
| `membership_status` | `enum("active", "inactive", "deprecated")` | Yes |
| `membership_is_locked` | `boolean` | Yes |

##### `AttributeAssertionSourceRecord`

| Field | JSON type / allowed values / bounds | Required in contract |
|---|---|---|
| `support_source_type` | `"assertion"` | Yes |
| `assertion_record` | `AssertionRecordKey` | Yes |
| `source_order` | `integer [exclusiveMinimum=0] \| null` | No; default `null` |
| `rationale` | `string [minLength=1; pattern="\\S"]` | Yes |
| `status` | `enum("active", "inactive", "deprecated")` | Yes |
| `is_locked` | `boolean` | Yes |

##### `AttributePhysicalSourceRecord`

| Field | JSON type / allowed values / bounds | Required in contract |
|---|---|---|
| `support_source_type` | `"attribute"` | Yes |
| `source_attribute` | `PhysicalAttributeKey` | Yes |
| `source_order` | `integer [exclusiveMinimum=0] \| null` | No; default `null` |
| `rationale` | `string [minLength=1; pattern="\\S"]` | Yes |
| `status` | `enum("active", "inactive", "deprecated")` | Yes |
| `is_locked` | `boolean` | Yes |

##### `AttributeSourceRecord`

`AttributePhysicalSourceRecord \| AttributeAssertionSourceRecord`

##### `PhysicalAttributeKey`

| Field | JSON type / allowed values / bounds | Required in contract |
|---|---|---|
| `tenant_code` | `string [minLength=1; maxLength=100; pattern="\\S"]` | Yes |
| `system_code` | `string [minLength=1; maxLength=100; pattern="\\S"]` | Yes |
| `connection_code` | `string [minLength=1; maxLength=100; pattern="\\S"]` | Yes |
| `object_schema` | `string [minLength=1; maxLength=400; pattern="\\S"]` | Yes |
| `object_name` | `string [minLength=1; maxLength=400; pattern="\\S"]` | Yes |
| `attribute_name` | `string [minLength=1; maxLength=400; pattern="\\S"]` | Yes |

##### `DimensionalAssertionSourceRecord`

| Field | JSON type / allowed values / bounds | Required in contract |
|---|---|---|
| `support_source_type` | `"assertion"` | Yes |
| `assertion_record` | `AssertionRecordKey` | Yes |
| `source_order` | `integer [exclusiveMinimum=0] \| null` | No; default `null` |
| `rationale` | `string [minLength=1; pattern="\\S"]` | Yes |
| `status` | `enum("active", "inactive", "deprecated")` | Yes |
| `is_locked` | `boolean` | Yes |
| `source_role` | `string [minLength=1; maxLength=255; pattern="\\S"]` | Yes |

##### `DimensionalEntitySourceRecord`

`DimensionalObjectSourceRecord \| DimensionalAssertionSourceRecord`

##### `DimensionalObjectSourceRecord`

| Field | JSON type / allowed values / bounds | Required in contract |
|---|---|---|
| `support_source_type` | `"object"` | Yes |
| `source_object` | `PhysicalObjectKey` | Yes |
| `source_order` | `integer [exclusiveMinimum=0] \| null` | No; default `null` |
| `rationale` | `string [minLength=1; pattern="\\S"]` | Yes |
| `status` | `enum("active", "inactive", "deprecated")` | Yes |
| `is_locked` | `boolean` | Yes |
| `source_role` | `string [minLength=1; maxLength=255; pattern="\\S"]` | Yes |

##### `ValidationLiteral`

`boolean \| integer \| number \| string`


<a id="table-validations"></a>

## 3. Table validations and constraints

Each table appears once in the main validation tables below. Shared rule sections named in a table are part of that table’s validation inventory.

<a id="core-tables"></a>

## 3A. `core` tables — 17 tables


### Core: shared database and application rules

- **DB (all 17 tables):** `<table>_id` is `BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY`: non-null, unique, database generated. There is no separate positive-ID CHECK. Every table has required `created_time`/`updated_time` (`TIMESTAMPTZ`, default `CURRENT_TIMESTAMP`) and `created_by`/`updated_by` (`VARCHAR(255)`, default `CURRENT_USER`). Defaults apply on insertion; no Core trigger automatically refreshes update fields. Text descriptions are nullable `TEXT` unless a row below says otherwise. All declared Core foreign keys use `ON DELETE NO ACTION`; ordinary nullable FKs use PostgreSQL's default `MATCH SIMPLE`. Table/index uniqueness includes inactive rows. Sources: [Core DDL](/Users/maazuddinmohammed/main/projects/gds_workbench_v2/database/02_core.sql:5).
- **DB text semantics:** `nonblank` below means `reference.is_nonblank`: not NULL and length after PostgreSQL `btrim` is greater than zero. This trims ordinary spaces, not all Unicode whitespace. `CI` uniqueness means `lower(btrim(value))`; it does not rewrite stored spelling or perform Unicode normalization. A nullable CHECK explicitly allowing NULL does not make a field required. Sources: [nonblank function](/Users/maazuddinmohammed/main/projects/gds_workbench_v2/database/01_reference.sql:5), [Core unique indexes](/Users/maazuddinmohammed/main/projects/gds_workbench_v2/database/02_core.sql:498).
- **Privileges, not CHECKs/triggers:** runtime roles receive Core reads, except whole-table reads of `core.connection_value`; Core direct INSERT/UPDATE/DELETE is absent from their grants. Operational writes use specific `SECURITY DEFINER` functions. The migration role receives all Core privileges. No trigger directly attached to a Core table appears in the numbered install SQL. Consequently, application-only checks below are not universal constraints on privileged SQL writes. Sources: [privilege reset](/Users/maazuddinmohammed/main/projects/gds_workbench_v2/database/19_runtime_integrity.sql:4), [runtime reads/write allowlist](/Users/maazuddinmohammed/main/projects/gds_workbench_v2/database/19_runtime_integrity.sql:1141), [migration privileges](/Users/maazuddinmohammed/main/projects/gds_workbench_v2/database/19_runtime_integrity.sql:1747).
- **App / Metadata Change Sets (MCS):** applies to `object`, `attribute`, both ingestion mappings, `copy_group`, `member_group`, `copy_group_control`, `copy`, `process_group`, `process`. All use strict row models, reject unknown fields, and use complete ID-free natural-key records. Required booleans are actual booleans; strings and integers are not coerced. Schema checks precede locks, Tenant ownership, staged and effective uniqueness, then references. Existing and staged rows are overlaid by canonical key; every effective reference must resolve. Codes are non-whitespace strings up to 100 characters; names have the table-specific 200/400 limits. Source: [strict records](/Users/maazuddinmohammed/main/projects/gds_workbench_v2/mcp_server/gds_etl_workbench/domain/metadata_records.py:10), [validation phases](/Users/maazuddinmohammed/main/projects/gds_workbench_v2/mcp_server/gds_etl_workbench/application/change_sets/metadata_validation.py:103), [dataset constraints/references](/Users/maazuddinmohammed/main/projects/gds_workbench_v2/mcp_server/gds_etl_workbench/domain/snapshots/metadata.py:231).
- **Function / MCS Apply:** active recognized identity and active Tenant; developer-or-higher metadata permission; service principals must be super-admin; valid unexpired Tenant Lock owned by caller. Change set must belong to the same Tenant and principal, be validated and unexpired, and match expected positive draft revision and lowercase 64-hex candidate digest. Apply checks dependencies again, resolves natural keys, and requires affected counts to equal staged counts; dependency drift raises SQLSTATE `40001`, rolling back atomic Apply. Attribute ordinal and Copy order uniqueness are temporarily deferred for swaps. App recomputes validation before Apply. Sources: [authorization](/Users/maazuddinmohammed/main/projects/gds_workbench_v2/database/03_security.sql:277), [Apply gate](/Users/maazuddinmohammed/main/projects/gds_workbench_v2/database/16_mcp_metadata_apply.sql:39), [deferred constraints](/Users/maazuddinmohammed/main/projects/gds_workbench_v2/database/16_mcp_metadata_apply.sql:269), [current-state validation](/Users/maazuddinmohammed/main/projects/gds_workbench_v2/mcp_server/gds_etl_workbench/application/change_sets/metadata.py:1291).
- **UI:** metadata editor mirrors schema-required fields, nullability, booleans, finite/safe numbers, integer limits, string code-point lengths, enums, regex patterns, calendar dates, and timezone-bearing date-times. Fixed fields and an existing row's natural-key fields cannot be edited in that form. Backend validation remains authoritative. Sources: [editor validation](/Users/maazuddinmohammed/main/projects/gds_workbench_v2/web_app/frontend/src/features/metadata/MetadataRowSurface.tsx:160), [field editability](/Users/maazuddinmohammed/main/projects/gds_workbench_v2/web_app/frontend/src/features/metadata/MetadataRowSurface.tsx:339).

### Core: table-by-table validations

| Schema | Table | Validations / constraints |
|---|---|---|
| `core` | `project` | • **DB:** `project_code VARCHAR(100)` and `project_name VARCHAR(200)` required and nonblank; code globally CI-unique.<br>• **DB:** `is_active` required, default true; nullable description.<br>• **App:** foundational snapshot record requires strict code/name/description/active fields; not eligible for MCS writes. Snapshot/schema validation is not a project administration write API.<br>• Sources: [DDL](/Users/maazuddinmohammed/main/projects/gds_workbench_v2/database/02_core.sql:5), [unique index](/Users/maazuddinmohammed/main/projects/gds_workbench_v2/database/02_core.sql:498), [record contract](/Users/maazuddinmohammed/main/projects/gds_workbench_v2/mcp_server/gds_etl_workbench/domain/metadata_records.py:35). |
| `core` | `tenant` | • **DB:** required `project_id` FK → `core.project`; required nonblank code(100), name(200). Code globally CI-unique.<br>• **DB:** required catalogs `tenant_catalog`, `gds_admin_catalog` each VARCHAR(255), but no DB nonblank CHECK on either.<br>• **DB:** visibility required, default `private`, exactly `global` or `private`; active required/default true. Description and `gds_connection_id BIGINT` nullable.<br>• **Gap:** no FK on `gds_connection_id`, and no table CHECK that it identifies an active global-data-store Connection.<br>• **App:** foundational record requires catalogs of 1–255 characters; optional three-part GDS Connection natural key must be entirely present or entirely absent, and when present resolves during MCS effective-reference validation. Not MCS-writeable.<br>• **Use-time functions:** governed Databricks/profiling paths require configured active GDS Connection; authorization ignores inactive Tenants.<br>• Sources: [DDL](/Users/maazuddinmohammed/main/projects/gds_workbench_v2/database/02_core.sql:19), [contract](/Users/maazuddinmohammed/main/projects/gds_workbench_v2/mcp_server/gds_etl_workbench/domain/metadata_records.py:42), [GDS resolver](/Users/maazuddinmohammed/main/projects/gds_workbench_v2/database/15_mcp_change_sets.sql:2292). |
| `core` | `system` | • **DB:** required nonblank code(100), name(200); code globally CI-unique. Required `system_type_id` FK → `reference.system_type`.<br>• **DB:** active required/default true; description nullable.<br>• **App:** foundational record uses strict bounded code/name and System Type natural-key reference; not MCS-writeable. No table CHECK requires the referenced System Type to be active.<br>• Sources: [DDL](/Users/maazuddinmohammed/main/projects/gds_workbench_v2/database/02_core.sql:43), [unique index](/Users/maazuddinmohammed/main/projects/gds_workbench_v2/database/02_core.sql:502), [contract](/Users/maazuddinmohammed/main/projects/gds_workbench_v2/mcp_server/gds_etl_workbench/domain/metadata_records.py:69). |
| `core` | `system_notebook_path` | • **DB:** `system_id`, `system_notebook_id` required; FKs → `core.system`, `reference.system_notebook`.<br>• **DB:** unique `(system_id, system_notebook_id)`; path required/nonblank TEXT. No DB URL/path-format or active-reference CHECK.<br>• **App:** no MCS dataset or ordinary write endpoint found; not included in Metadata Snapshot's dataset registry.<br>• Source: [DDL](/Users/maazuddinmohammed/main/projects/gds_workbench_v2/database/02_core.sql:60). |
| `core` | `connection` | • **DB:** required Tenant/System/Connection Type IDs, with FKs → `core.tenant`, `core.system`, `reference.connection_type`.<br>• **DB:** required nonblank code(100), name(200); unique `(system_id, tenant_id, CI connection_code)` and `(connection_id, tenant_id)`.<br>• **DB:** `has_foreign_catalog` and `is_global_data_store` required/default false; `is_active` required/default true. Optional `foreign_catalog VARCHAR(255)`, description, test initial BIGINT, and test incremental BIGINT array.<br>• **Gap:** no CHECK tying `has_foreign_catalog` to populated catalog, limiting GDS connections per Tenant, constraining test-batch signs/array size, or matching referenced active states.<br>• **App:** foundational strict snapshot record, not MCS-writeable; omits test-batch fields. At profiling execution, Source requires enabled nonblank foreign catalog. Databricks resolver accepts active non-GDS source Connection in active Tenant and resolves its active configured GDS Connection.<br>• Sources: [DDL](/Users/maazuddinmohammed/main/projects/gds_workbench_v2/database/02_core.sql:80), [unique index](/Users/maazuddinmohammed/main/projects/gds_workbench_v2/database/02_core.sql:504), [record](/Users/maazuddinmohammed/main/projects/gds_workbench_v2/mcp_server/gds_etl_workbench/domain/metadata_records.py:77), [profiling use-time gate](/Users/maazuddinmohammed/main/projects/gds_workbench_v2/web_app/backend/gds_workbench_api/features/profiling/workflow.py:487). |
| `core` | `connection_location` | • **DB:** required Connection, Location Type, Environment IDs; FKs → corresponding `core.connection`, `reference.location_type`, `reference.environment`.<br>• **DB:** unique `(connection_id, location_type_id, environment_id)`.<br>• **DB:** storage-account and container fields required nonblank VARCHAR(255); credential-reference and location-path fields required nonblank TEXT. No further format or existence checks in this DDL.<br>• **App:** no MCS dataset/ordinary write path found; not in Metadata Snapshot registry.<br>• Source: [DDL](/Users/maazuddinmohammed/main/projects/gds_workbench_v2/database/02_core.sql:109). |
| `core` | `connection_value` | • **DB:** required `environment_id`, `connection_id`, `connection_parameter_id`; FKs only for Connection and Connection Parameter.<br>• **DB:** unique `(connection_id, connection_parameter_id, environment_id)`; literal value nullable TEXT, otherwise nonblank.<br>• **Gap:** `environment_id` has no FK; no DB CHECK enforces Connection Parameter belongs to Connection Type, or validates credential/value format.<br>• **Function / use-time:** bounded Databricks resolver requires active Environment, active expected parameters and all required connection configuration fields; tool validates host format/length, warehouse-path format, credential length and surrounding whitespace, and resolved Tenant/environment consistency. These reject an execution, not arbitrary stored rows.<br>• **Privilege:** no whole-table runtime SELECT, and no MCS dataset or ordinary write endpoint.<br>• Sources: [DDL](/Users/maazuddinmohammed/main/projects/gds_workbench_v2/database/02_core.sql:144), [resolver](/Users/maazuddinmohammed/main/projects/gds_workbench_v2/database/15_mcp_change_sets.sql:2257), [use-time validation](/Users/maazuddinmohammed/main/projects/gds_workbench_v2/mcp_server/gds_etl_workbench/tools/databricks/execute_sql.py:197). |
| `core` | `object` | • **DB:** required Connection, source-Tenant, Object Type, Zone IDs with FKs; required/nonblank schema and name, each VARCHAR(400).<br>• **DB:** unique `(connection_id, CI schema, CI name)`, `(object_id, connection_id)`, `(object_id, zone_id)`.<br>• **DB:** lock required/default false; active required/default true. Optional foreign-catalog schema/name and batch-attribute name ≤400; transformation/description nullable TEXT.<br>• **Gap:** no DB CHECK for source-Tenant/placement/zone consistency, valid batch-attribute reference, foreign-catalog completeness, or lock immutability.<br>• **App / MCS:** Source/Bronze/Silver/Gold datasets fix the respective zone; source owner must be locked Tenant. Source placement must use its owned Connection; other three zones use configured GDS Connection. Natural-key uniqueness and Tenant/System/Object Type/Zone references checked; locked existing Object cannot change or have Attributes changed.<br>• **Function / Apply:** rechecks locks; Source requires non-GDS own-Tenant Connection; Bronze/Silver/Gold require configured GDS-flagged Connection. Conflict update cannot transfer source ownership; unresolved/mismatched dependencies abort.<br>• **Function/App:** review and enrichment gates below; profiling requires full Source foreign-catalog relation, or canonical Bronze relation. Catalog response bounds descriptions to 2000 characters and non-null foreign-catalog names to ≥1 character (response constraint only).<br>• Sources: [DDL](/Users/maazuddinmohammed/main/projects/gds_workbench_v2/database/02_core.sql:166), [MCS scope](/Users/maazuddinmohammed/main/projects/gds_workbench_v2/mcp_server/gds_etl_workbench/application/change_sets/metadata_validation.py:316), [Apply placement](/Users/maazuddinmohammed/main/projects/gds_workbench_v2/database/16_mcp_metadata_apply.sql:323), [response contract](/Users/maazuddinmohammed/main/projects/gds_workbench_v2/mcp_server/gds_etl_workbench/tools/catalog/get_objects.py:107). |
| `core` | `attribute` | • **DB:** required Object FK; required nonblank name VARCHAR(400); required INTEGER ordinal >0; unique `(object_id, ordinal)` DEFERRABLE INITIALLY IMMEDIATE, `(attribute_id, object_id)`, and `(object_id, CI name)`.<br>• **DB:** required data type VARCHAR(100), without DB nonblank/SQL-type grammar CHECK. Optional inferred type VARCHAR(100), NULL or nonblank; foreign-catalog name ≤400. Description/custom-code TEXT and business-glossary BIGINT optional; business-glossary ID has no FK.<br>• **DB:** nullability required/default true; active required/default true; surrogate/natural/meta-data/masking/mapped/purge/locked flags required/default false.<br>• **Gap:** no flag-combination rule, declared-type parser, unique/required key rule, or locked-parent trigger in DDL.<br>• **App / MCS:** ordinal 1..2,147,483,647; declared type 1–100 characters; inferred type non-whitespace ≤100; strict flags; Object reference and both natural-name/ordinal uniqueness. Parent must be mutable and Tenant-owned; own lock or parent lock blocks staged updates. Apply rechecks locks and resolves Attribute under owned Object; placement Tenant must be active.<br>• **Function/App:** review/enrichment rules below. Profiling requires foreign-catalog Attribute names for Source and consistent canonical names for Bronze. Catalog response additionally limits descriptions to 2000 characters and non-null foreign-catalog names to ≥1 character.<br>• Sources: [DDL](/Users/maazuddinmohammed/main/projects/gds_workbench_v2/database/02_core.sql:199), [record](/Users/maazuddinmohammed/main/projects/gds_workbench_v2/mcp_server/gds_etl_workbench/domain/metadata_records.py:163), [Apply](/Users/maazuddinmohammed/main/projects/gds_workbench_v2/database/16_mcp_metadata_apply.sql:408), [response](/Users/maazuddinmohammed/main/projects/gds_workbench_v2/mcp_server/gds_etl_workbench/tools/catalog/get_objects.py:88). |
| `core` | `ingestion_object_mapping` | • **DB:** source/target Object IDs required and FK-bound; IDs must differ.<br>• **DB:** unique `(source_object_id, target_object_id)` and witness `(mapping_id, source_object_id, target_object_id)`; active required/default true.<br>• **App / MCS:** source/target natural keys must differ after lowercase/ordinary-space trimming; both Object references resolve and are mutable under locked Tenant ownership and allowed placement.<br>• **Function / Apply:** both Objects must have source owner equal locked Tenant; each Connection must be Tenant-owned or its configured GDS; all resolution/count checks must succeed.<br>• **Gap:** no table CHECK of source→Bronze zone pairing, same-Tenant endpoints, active endpoints, or source-system consistency; do not infer these from the table's name.<br>• Sources: [DDL](/Users/maazuddinmohammed/main/projects/gds_workbench_v2/database/02_core.sql:237), [record](/Users/maazuddinmohammed/main/projects/gds_workbench_v2/mcp_server/gds_etl_workbench/domain/metadata_records.py:190), [Apply](/Users/maazuddinmohammed/main/projects/gds_workbench_v2/database/16_mcp_metadata_apply.sql:474). |
| `core` | `ingestion_attribute_mapping` | • **DB:** all five parent/endpoint IDs required; composite FK `(mapping_id, source_object_id, target_object_id)` matches exact Object Mapping; composite source and target Attribute/Object FKs prove each Attribute belongs to endpoint Object.<br>• **DB:** source and target Attribute IDs differ; unique `(ingestion_object_mapping_id, source_attribute_id, target_attribute_id)`; active required/default true.<br>• **App / MCS:** distinct normalized endpoint Attribute keys; exact parent Object Mapping and both Attribute references must resolve; endpoint Objects satisfy locked-Tenant ownership/placement rules.<br>• **Function / Apply:** re-resolves exact parent and Attribute ownership, both Objects belong to locked Tenant, both connections owned/configured GDS; count mismatch aborts.<br>• **Gap:** no DB or shared-row rule requires compatible endpoint data types or active parent/endpoints.<br>• Sources: [DDL](/Users/maazuddinmohammed/main/projects/gds_workbench_v2/database/02_core.sql:263), [record](/Users/maazuddinmohammed/main/projects/gds_workbench_v2/mcp_server/gds_etl_workbench/domain/metadata_records.py:226), [Apply](/Users/maazuddinmohammed/main/projects/gds_workbench_v2/database/16_mcp_metadata_apply.sql:558). |
| `core` | `copy_group` | • **DB:** required Tenant/System FKs; required/nonblank name VARCHAR(200); CI name unique within `(tenant_id, system_id)`; unique `(copy_group_id, tenant_id, system_id)` witness.<br>• **DB:** `is_member_group_required` required/default false; active required/default true; nullable description.<br>• **App / MCS:** exact Tenant owner, bounded non-whitespace name, Tenant/System reference and natural-key uniqueness checks; Apply resolves scoped natural keys and counts.<br>• **Gap:** flag does not cause a DB CHECK/trigger requiring child controls to have Member Group. Copy Group summary response limits description to 2000 characters, unlike stored TEXT/MCS record.<br>• Sources: [DDL](/Users/maazuddinmohammed/main/projects/gds_workbench_v2/database/02_core.sql:303), [unique index](/Users/maazuddinmohammed/main/projects/gds_workbench_v2/database/02_core.sql:518), [Apply](/Users/maazuddinmohammed/main/projects/gds_workbench_v2/database/16_mcp_metadata_apply.sql:657), [response](/Users/maazuddinmohammed/main/projects/gds_workbench_v2/mcp_server/gds_etl_workbench/tools/ingestion/copy_groups.py:149). |
| `core` | `member_group` | • **DB:** required Tenant/System FKs; required/nonblank name VARCHAR(200); CI name unique within `(tenant_id, system_id)`; unique `(member_group_id, tenant_id, system_id)` witness.<br>• **DB:** optional initial-load DATE and description; active required/default true. No date-window CHECK.<br>• **App / MCS:** strict date-or-null, exact Tenant owner, Tenant/System reference and natural-key uniqueness checks; Apply resolves scoped keys/counts. Control-detail response limits this group's description to 2000 characters (response-only).<br>• Sources: [DDL](/Users/maazuddinmohammed/main/projects/gds_workbench_v2/database/02_core.sql:326), [unique index](/Users/maazuddinmohammed/main/projects/gds_workbench_v2/database/02_core.sql:524), [Apply](/Users/maazuddinmohammed/main/projects/gds_workbench_v2/database/16_mcp_metadata_apply.sql:694), [response](/Users/maazuddinmohammed/main/projects/gds_workbench_v2/mcp_server/gds_etl_workbench/tools/ingestion/copy_groups.py:188). |
| `core` | `copy_group_control` | • **DB:** Copy Group/Tenant/System required; Member Group nullable. Composite FK requires Copy Group under same Tenant/System; optional composite Member Group FK enforces same scope when Member Group is supplied.<br>• **DB:** `UNIQUE NULLS NOT DISTINCT (copy_group_id, member_group_id)` allows one NULL-member row per Copy Group, not many.<br>• **DB:** initial-load DATE and last-run TIMESTAMPTZ nullable; last-run TEXT nullable or nonblank. No active flag, date-order rule, or flag-driven Member Group requirement.<br>• **App / MCS:** strict date/date-time or NULL, non-whitespace last-run value if supplied; locked-Tenant owner; exact scoped Copy Group and optional Member Group references; natural-key uniqueness treats NULL member as same key. Apply rejects unresolved supplied Member Group.<br>• Sources: [DDL](/Users/maazuddinmohammed/main/projects/gds_workbench_v2/database/02_core.sql:349), [record](/Users/maazuddinmohammed/main/projects/gds_workbench_v2/mcp_server/gds_etl_workbench/domain/metadata_records.py:284), [Apply](/Users/maazuddinmohammed/main/projects/gds_workbench_v2/database/16_mcp_metadata_apply.sql:730). |
| `core` | `copy` | • **DB:** required Copy Group, Ingestion Object Mapping, source Data Operation, target Data Operation FKs; optional Chunk Type/File Type FKs.<br>• **DB:** required INTEGER source order, unique `(copy_group_id, ingestion_object_mapping_id)` and `(copy_group_id, copy_source_order)` (latter DEFERRABLE INITIALLY IMMEDIATE); active required/default true.<br>• **DB:** optional source-record BIGINT limit; limit-attribute name VARCHAR(400); delimiter VARCHAR(20); initial/incremental SQL, filename, pattern nullable TEXT. No DB nonnegative limit or positive order CHECK, and no SQL/file consistency validator in table DDL.<br>• **App / MCS:** source order 1..2,147,483,647. Record limit represented as signed integer-text fitting BIGINT, including negative values. Locked-Tenant group ownership; source/target Objects mutable in same locked Tenant; exact mapping/group/operation and optional chunk/file references; group/order uniqueness.<br>• **Function / Apply:** endpoint owners locked Tenant and connections owned/configured GDS; exact parent Mapping; supplied optional reference must resolve; all counts match.<br>• **Response-only mismatch:** `CopyDetails` requires record limit ≥0, although DB and MCS row contract permit negative values.<br>• Sources: [DDL](/Users/maazuddinmohammed/main/projects/gds_workbench_v2/database/02_core.sql:388), [record](/Users/maazuddinmohammed/main/projects/gds_workbench_v2/mcp_server/gds_etl_workbench/domain/metadata_records.py:296), [Apply](/Users/maazuddinmohammed/main/projects/gds_workbench_v2/database/16_mcp_metadata_apply.sql:789), [read constraint](/Users/maazuddinmohammed/main/projects/gds_workbench_v2/mcp_server/gds_etl_workbench/tools/ingestion/copy_groups.py:170). |
| `core` | `process_group` | • **DB:** Tenant/System/Zone/Copy Group required; individual FKs → Tenant/System/Zone; composite Copy Group FK enforces same Tenant/System.<br>• **DB:** required/nonblank name VARCHAR(200); CI name unique within `(tenant_id, system_id, zone_id)`; active required/default true; nullable description.<br>• **App / MCS:** strict bounded name; zone-code 1–30 characters and resolves reference Zone; locked-Tenant owner; natural-key and same-scope Copy Group reference. Apply re-resolves exact Tenant/System/Zone/Copy Group and counts.<br>• **Gap:** no fixed-zone enum on Process Group table or row contract; Zone FK/reference controls available values.<br>• Sources: [DDL](/Users/maazuddinmohammed/main/projects/gds_workbench_v2/database/02_core.sql:432), [unique index](/Users/maazuddinmohammed/main/projects/gds_workbench_v2/database/02_core.sql:530), [record](/Users/maazuddinmohammed/main/projects/gds_workbench_v2/mcp_server/gds_etl_workbench/domain/metadata_records.py:333), [Apply](/Users/maazuddinmohammed/main/projects/gds_workbench_v2/database/16_mcp_metadata_apply.sql:946). |
| `core` | `process` | • **DB:** Connection/Object/Process Type/Process Group IDs required. Composite `(object_id, connection_id)` FK proves physical Object belongs to Connection; Process Type/Group FKs resolve.<br>• **DB:** required INTEGER execution order >0; required nonblank TEXT location and executable; unique `(process_group_id, process_execution_order, process_location, process_executable)` (raw text, not CI). Active required/default true.<br>• **App / MCS:** order 1..2,147,483,647, non-whitespace location/executable; locked-Tenant owner, exact scoped Process Group and Process Type reference; referenced Object mutable in locked Tenant; natural-key uniqueness preserves case/spaces for location/executable.<br>• **Function / Apply:** group resolves by Tenant/System/Zone/name; Object source owner locked Tenant; Object Connection belongs to Tenant or configured GDS; count mismatch aborts.<br>• **Gap:** no DB rule that Object and Process Group have matching zone/system, nor uniqueness on execution order alone; different locations/executables can share the same order.<br>• Sources: [DDL](/Users/maazuddinmohammed/main/projects/gds_workbench_v2/database/02_core.sql:465), [record](/Users/maazuddinmohammed/main/projects/gds_workbench_v2/mcp_server/gds_etl_workbench/domain/metadata_records.py:343), [Apply](/Users/maazuddinmohammed/main/projects/gds_workbench_v2/database/16_mcp_metadata_apply.sql:990). |

### Core Object / Attribute: additional governed review and enrichment rules

These are **write-path functions and application checks**, not triggers on `core.object` / `core.attribute`.

| Path | Additional validations applied to Core Object / Attribute writes |
|---|---|
| Web metadata review: `application.review_metadata_records` | • Human-user principal only; positive Tenant and correlation ID; record type exactly Object or Attribute; action `lock`, `unlock`, `deactivate`, `reactivate`, or `describe`.<br>• 1–200 unique positive BIGINT record IDs; expected revision per row exactly 64 lowercase hex; JSON body ≤32768 bytes, exact allowed keys. `describe` requires nullable/string description ≤2000 UTF-8 bytes and rejects control characters except tab/newline/carriage return; other actions reject the description field.<br>• Tenant read and metadata-write authorization; own valid Tenant Lock. No running workflow in Tenant. Every selected row must belong to selected source Tenant; per-record revision must still match.<br>• Object lock blocks describe/deactivate/reactivate. Parent Object lock blocks every Attribute review action, including Attribute unlock; Attribute's own lock blocks describe/deactivate/reactivate. Own-row lock/unlock remains available subject to parent/authorization rules.<br>• Same principal/Tenant/correlation replay requires same request digest; conflict rejected. Tenant Lock rechecked immediately before write; only changed values updated; audit event written; update actor/time server generated.<br>• Sources: [SQL function](/Users/maazuddinmohammed/main/projects/gds_workbench_v2/database/14_application_workflow_execution.sql:3407), [backend request validation](/Users/maazuddinmohammed/main/projects/gds_workbench_v2/web_app/backend/gds_workbench_api/features/metadata/review.py:26). |
| Workflow metadata enrichment: `application.complete_metadata_enrichment` | • Active Model/run, matching run owner, metadata-enrichment workflow, current expected Model revision, both Model-write and metadata-write authorization, live execution claim. Completion replay must match receipt digest and terminal state.<br>• Results array ≤10200 entries and ≤24 MiB; expected baseline digest 64 lowercase hex. Exact result keys; positive bounded Object/Attribute IDs; unique `(object, attribute, field)`; complete selected-field coverage; each result remains in selected Object/Attribute scope.<br>• Only fields `object_description`, `attribute_description`, `attribute_inferred_data_type`; object-description has NULL Attribute ID, other fields require Attribute ID. Status exactly applied/existing/locked/inactive/changed/unavailable/inconclusive. Only applied results may carry a value. Descriptions may be NULL; otherwise nonblank and ≤2000 UTF-8 bytes with bounded controls. Applied inferred type required/nonblank, ≤100 characters, no controls.<br>• Allowed evidence methods are `agent_description`, `source_comment`, `registered_type`, `source_schema`, `bronze_schema`, `source_sample`, `bronze_sample`, `none`. Applied descriptions require description/comment evidence; applied inferred types require type/schema/sample evidence. Sample count 0..50 and nonzero only for sample evidence; sampling masked target or source Attribute rejected.<br>• Locks and active flags checked; locked/inactive rows not patched. Baseline/description revision drift turns attempted patches into `changed`. Existing nonblank inferred type is preserved; descriptions can be replaced or cleared when eligible. Dependencies row-locked through completion; server writes update actor/time and result audit.<br>• Sources: [completion function](/Users/maazuddinmohammed/main/projects/gds_workbench_v2/database/14_application_workflow_execution.sql:2925), [field/evidence/lock checks](/Users/maazuddinmohammed/main/projects/gds_workbench_v2/database/14_application_workflow_execution.sql:3077), [strict result validation](/Users/maazuddinmohammed/main/projects/gds_workbench_v2/web_app/backend/gds_workbench_api/features/metadata_enrichment/contracts.py:108). |
| Enrichment candidate quality and inferred-type normalization (App) | • Generated description output must contain exactly requested target references; each value NULL or meaningful nonblank text ≤2000 UTF-8 bytes, no disallowed controls. Reject placeholder words (`todo`, `tbd`, `unknown`, `n/a`, `not available`) and descriptions merely repeating normalized field name.<br>• Native inferred types normalize through known aliases; unsupported/blank/NUL/overlength expressions return no inference. DECIMAL precision 1..38 and scale 0..precision; complex ARRAY/MAP/STRUCT type expressions parsed as types, nested scalar types must normalize, rendered result ≤100 characters. These quality/type rules affect enrichment output only; they are not a generic SQL-type CHECK on Attribute table.<br>• Sources: [description validator](/Users/maazuddinmohammed/main/projects/gds_workbench_v2/web_app/backend/gds_workbench_api/features/metadata_enrichment/service.py:36), [type normalizer](/Users/maazuddinmohammed/main/projects/gds_workbench_v2/web_app/backend/gds_workbench_api/features/metadata_enrichment/inference.py:65). |
| Profiling relation eligibility (read/execution only) | • Only Source or Bronze scoped Objects supported. Source requires enabled foreign catalog and nonblank foreign-catalog Object/Attribute names; Bronze uses canonical relation. Returned row relation/zone/Attribute fields must agree; at most one batch Attribute resolved.<br>• These reject profiling runs, without making the underlying stored metadata invalid to PostgreSQL.<br>• Source: [profiling relation resolver](/Users/maazuddinmohammed/main/projects/gds_workbench_v2/web_app/backend/gds_workbench_api/features/profiling/workflow.py:487). |


<a id="model-tables"></a>


## 3B. `model` tables — 6 tables

**How to read:** DB = enforced by PostgreSQL. Function = enforced only when that SQL function runs. App = enforced by the named Python write path. A lock column alone does not prevent SQL updates. Names and keys are not unique merely because they look like identifiers; only the listed unique constraints/indexes enforce uniqueness.

All six tables have their declared SQL column types and `NOT NULL` requirements; exact declarations appear in the final SQL inventory. The five entity/event tables use a generated identity primary key; `model_revision_transaction` uses a composite primary key. Audit defaults populate values on insert; they are not automatic update triggers. All FKs below use `ON DELETE NO ACTION`.

| Schema | Table | Validations / constraints |
|---|---|---|
| `model` | `model` | • **DB:** required Tenant, name, revision, active flag and audit fields. Name nonblank, ≤255 characters; optional description nonblank, ≤2,000.<br>• **DB:** Tenant FK → `core.tenant`; unique `(model_id, tenant_id)`; unique `(tenant_id, lower(btrim(model_name)))`, including inactive Models.<br>• **DB:** revision >0, initially 1; `is_active` initially true.<br>• **DB:** each optional Silver/Gold naming instruction must be nonblank and ≤32,768 UTF-8 bytes.<br>• **DB:** default SDK/provider codes match `^[a-z][a-z0-9_.-]{0,99}$`; model code matches `^[A-Za-z0-9][A-Za-z0-9_.:/-]{0,199}$`; reasoning code matches `^[a-z][a-z0-9_-]{0,49}$`.<br>• **DB:** agent-default CHECK permits all six defaults absent; configured branch requires all four code fields and checks turns 1–50 / retries 0–5. **SQL caveat:** numeric fields lack explicit `IS NOT NULL` in that branch; CHECK can evaluate UNKNOWN and pass when a numeric value is null. App enforces complete-or-absent.<br>• **Function:** `create_model`, `update_model`, `archive_model` require `tenant_model_write` authorization and caller-owned live Tenant Lock; update/archive require active Model and exact expected revision. Update with identical values returns existing row; changed update increments revision. Archive rejects any running workflow in the Tenant, sets inactive, increments revision. Each changed command writes revision history.<br>• **App, web complete-Model command:** strict types, unknown fields rejected, text stripped and nonblank; each template must be a JSON object or null and ≤32 KiB; all six agent settings complete or absent; SDK/provider/model/reasoning combination must exist and be compatible in capability registry; expected revision positive; URL Tenant must own Model.<br>• **App, Model Change Set:** exactly one future `model_details` record; conflicting other active Model name rejected before SQL; name/description/type limits; naming text ≤32 KiB; each template object ≤256 KiB. Apply rechecks base revision and graph, expected draft/digest and idempotency; increments revision conditionally.<br>• **Privilege:** MCP cannot create/archive Models or set agent defaults through direct grants; generic materializer can update listed policy/name/revision/audit columns only. **No DB JSON-object/size CHECK on template columns.** [DDL](/Users/maazuddinmohammed/main/projects/gds_workbench_v2/database/04_model.sql:5), [commands](/Users/maazuddinmohammed/main/projects/gds_workbench_v2/database/12_application_configuration.sql:77), [web contract](/Users/maazuddinmohammed/main/projects/gds_workbench_v2/web_app/backend/gds_workbench_api/features/models/command_contracts.py:31), [service](/Users/maazuddinmohammed/main/projects/gds_workbench_v2/web_app/backend/gds_workbench_api/features/models/command_service.py:136), [capabilities](/Users/maazuddinmohammed/main/projects/gds_workbench_v2/web_app/backend/gds_workbench_api/capabilities.py:158), [record schema](/Users/maazuddinmohammed/main/projects/gds_workbench_v2/mcp_server/gds_etl_workbench/domain/modeling_records.py:102), [graph validation](/Users/maazuddinmohammed/main/projects/gds_workbench_v2/mcp_server/gds_etl_workbench/application/change_sets/model_validation.py:365), [grants](/Users/maazuddinmohammed/main/projects/gds_workbench_v2/database/19_runtime_integrity.sql:1210). |
| `model` | `model_input_scope` | • **DB:** required Model/Object FKs; unique `(model_id, object_id)` across active/inactive rows; required lock flag defaults false, active flag true, audit fields required.<br>• **App:** physical natural key must resolve to an authorized visible Object; new/changed scope uses eligible active Source/Bronze Objects. Unchanged historical records can remain under the retained-history exception. Locked applied rows cannot be altered by ordinary staged replacement.<br>• **Function, additive web Scope:** 1–200 distinct positive non-null Object IDs; human principal only; active owned Model; matching expected revision; `tenant_model_write` and live owned Tenant Lock; no running workflow anywhere in Tenant; every selection eligible; `tenant_read` for each source Tenant; a locked inactive row cannot be reactivated. Existing active rows are idempotent; inactive rows are reactivated.<br>• **App:** request rejects unknown fields/coercion, sorts distinct IDs; shared future-graph validation also runs before adding. Caller records Change Set and advances Model revision in same transaction; SQL scope function does not itself increment revision.<br>• **Boundary:** DB FKs alone do not enforce active status, Source/Bronze zone, visibility, source ownership, or the lock flag. Current SQL eligibility supports Source/Bronze across source Tenants with access; generated guidance saying “source Tenant is the Model Tenant” is stronger than the current enforcement. [DDL](/Users/maazuddinmohammed/main/projects/gds_workbench_v2/database/04_model.sql:88), [eligibility](/Users/maazuddinmohammed/main/projects/gds_workbench_v2/database/11_workflow_eligibility.sql:78), [SQL add](/Users/maazuddinmohammed/main/projects/gds_workbench_v2/database/14_application_workflow_execution.sql:3338), [app add](/Users/maazuddinmohammed/main/projects/gds_workbench_v2/web_app/backend/gds_workbench_api/features/model_change_sets/input_scope.py:22), [graph scope](/Users/maazuddinmohammed/main/projects/gds_workbench_v2/mcp_server/gds_etl_workbench/application/change_sets/model_validation.py:389). |
| `model` | `model_event_log` | • **DB:** required Model FK, UUID correlation ID, sequence, attempt, workflow, stage, status, message, finding count and created audit fields. Optional run references/text/progress fields retain declared types/lengths.<br>• **DB:** sequence and attempt >0; unique `(model_id, correlation_id, model_event_log_sequence)`.<br>• **DB:** workflow ∈ `profiling`, `analysis`, `conceptual`, `logical`, `dimensional`, `mapping`, `code_generation`, `validation`, `metadata_enrichment`, `dbml`.<br>• **DB:** stage nonblank ≤100 characters; message nonblank ≤2,000; status ∈ `started`, `running`, `completed`, `warning`, `failed`, `blocked`.<br>• **DB:** optional current/total counts ≥0; current ≤total when both supplied; percent 0–100 when supplied, `NUMERIC(5,2)`; finding count ≥0, default 0.<br>• **DB:** optional `(workflow_run_id, model_id)` FK → corresponding `application.workflow_run` pair, added in install file 13.<br>• **Trigger:** statement-level `reject_model_event_log_mutation` rejects UPDATE, DELETE and TRUNCATE: append-only.<br>• **Function, append event:** sequence >1 and contiguous after current maximum; stage pattern `^[a-z][a-z0-9_.-]{0,99}$`; status only `running/warning/blocked`; message nonblank, ≤2,000 bytes, no control characters; finding count ≥0; current/total both null or both supplied with total >0 and 0≤current≤total; percent derived to 2 decimals.<br>• **Function:** active Model, authorization/owned live Tenant Lock, workflow actor ownership, exact Model revision; a new event requires running workflow; attempt 1…(retry count+1) for code/validation or a non-null execution mode, otherwise 1. Same sequence with identical fields replays existing event; different fields conflict. Start/claim/complete/fail/no-op lifecycle functions create their own bounded lifecycle events.<br>• **App:** event request uses strict types/no unknown fields, sequence >1, attempt 1–6, stage regex, allowed progress status, printable nonblank message ≤2,000 characters, paired counts with positive total and current≤total. Lifecycle verifies run belongs to the requested active Model/Tenant/workflow/execution mode; worker paths verify live workflow claim. Failure metadata requires bounded printable message and safe failure-code pattern. [Event contract/service](/Users/maazuddinmohammed/main/projects/gds_workbench_v2/web_app/backend/gds_workbench_api/features/workflows/authoring/lifecycle.py:122).<br>• **Boundary:** base table does not require percentage to equal current/total, paired nullness, contiguous ordering, or run ownership; those are function/write-path rules. [DDL + trigger](/Users/maazuddinmohammed/main/projects/gds_workbench_v2/database/04_model.sql:105), [late FK](/Users/maazuddinmohammed/main/projects/gds_workbench_v2/database/13_application_workflow_runs.sql:709), [append function](/Users/maazuddinmohammed/main/projects/gds_workbench_v2/database/13_application_workflow_runs.sql:3463). |
| `model` | `modeling_assertion_document` | • **DB:** required Model FK, name, metadata JSON, active flag and audit fields; optional Tenant FK and System FK; optional workflow run must belong to same Model via composite FK.<br>• **DB:** unique `(document_id, model_id)`; unique Model + case-insensitive space-trimmed document name, including inactive documents.<br>• **DB:** name nonblank ≤255; optional file pattern nonblank ≤500; optional type nonblank ≤100; optional description nonblank ≤2,000.<br>• **DB:** metadata must be a JSON object, defaults `{}`; active defaults true.<br>• **App:** exact ID-free record schema; optional Tenant code must equal Model Tenant code; optional System code must resolve to an active System. Metadata ≤65,536 bytes and passes bounded safe-JSON rules below; section ≤4 MiB. Model Change Set authorization, revision/digest/idempotency and graph checks apply.<br>• **Boundary:** DB does not enforce that optional Tenant owns Model, that referenced Tenant/System are active, or metadata byte/complexity/content limits. No dedicated document lock field. [DDL](/Users/maazuddinmohammed/main/projects/gds_workbench_v2/database/04_model.sql:188), [late FK](/Users/maazuddinmohammed/main/projects/gds_workbench_v2/database/13_application_workflow_runs.sql:715), [record contract](/Users/maazuddinmohammed/main/projects/gds_workbench_v2/mcp_server/gds_etl_workbench/domain/modeling_records.py:313), [scope validation](/Users/maazuddinmohammed/main/projects/gds_workbench_v2/mcp_server/gds_etl_workbench/application/change_sets/model_validation.py:457). |
| `model` | `modeling_assertion_record` | • **DB:** required Model FK and composite `(document_id, model_id)` FK; optional workflow run must belong to same Model; unique `(record_id, model_id)` and unique Model + lower/space-trimmed record key.<br>• **DB:** key matches `^[A-Za-z][A-Za-z0-9_.-]{0,99}$`; type nonblank ≤100; text nonblank.<br>• **DB:** details object required, defaults `{}`; optional source location must be object; applicable layers required, defaults empty array, must be contained in `analysis/conceptual/logical/dimensional/mapping`.<br>• **DB:** optional confidence `low/medium/high`; required status `active/inactive/deprecated`, default active; lock required, default false; audit fields required.<br>• **App:** assertion text ≤262,144 characters; details ≤262,144 bytes; optional source location ≤65,536 bytes; both JSON fields pass safe-JSON rules below; layer entries unique; exact strict schema and no unknown fields.<br>• **App:** referenced document name must exist in future Model graph. Downstream supports/source mappings referencing the record must find it and include their layer in its applicability. Ordinary Change Set replacement cannot change an applied locked record.<br>• **Boundary:** SQL permits empty/duplicate layer entries (array containment, not uniqueness/nonempty validation); app permits empty but rejects duplicates. “At least one layer” in generated authoring guidance is advice, not this record validator. SQL text has no app-equivalent length ceiling. The shared assertion-reference check tests existence and layer applicability; it does not itself require active assertion/document status. [DDL](/Users/maazuddinmohammed/main/projects/gds_workbench_v2/database/04_model.sql:233), [late FK](/Users/maazuddinmohammed/main/projects/gds_workbench_v2/database/13_application_workflow_runs.sql:721), [record contract](/Users/maazuddinmohammed/main/projects/gds_workbench_v2/mcp_server/gds_etl_workbench/domain/modeling_records.py:349), [reference checks](/Users/maazuddinmohammed/main/projects/gds_workbench_v2/mcp_server/gds_etl_workbench/application/change_sets/model_validation.py:795), [support checks](/Users/maazuddinmohammed/main/projects/gds_workbench_v2/mcp_server/gds_etl_workbench/application/change_sets/model_validation.py:1345). |
| `model` | `model_revision_transaction` | • **DB:** composite PK `(model_id, transaction_id)`; Model FK; both IDs required; required nonblank change kind ≤100; required change timestamp and actor ≤255.<br>• **DB:** transaction ID defaults `txid_current()`, timestamp current time, actor `SESSION_USER`. No positivity CHECK on transaction ID.<br>• **Function:** Model create/update/archive and selected workflow persistence functions insert revision-history rows; PK prevents duplicate Model/transaction pairs. This is not a trigger that automatically records every arbitrary Model update.<br>• **Privilege:** INSERT/UPDATE/DELETE/TRUNCATE/REFERENCES/TRIGGER/MAINTAIN revoked from both runtime roles. **No append-only trigger declared on this table**; unlike `model_event_log`, immutability for those roles comes from grants and controlled functions. [DDL](/Users/maazuddinmohammed/main/projects/gds_workbench_v2/database/04_model.sql:295), [revision write example](/Users/maazuddinmohammed/main/projects/gds_workbench_v2/database/12_application_configuration.sql:304), [privileges](/Users/maazuddinmohammed/main/projects/gds_workbench_v2/database/19_runtime_integrity.sql:1147). |

### Assertion safe-JSON rules

Applied to document metadata, record details, and non-null source location by [assertion_safety.py](/Users/maazuddinmohammed/main/projects/gds_workbench_v2/mcp_server/gds_etl_workbench/domain/assertion_safety.py:40):

- JSON serialization must succeed; bytes measured from compact UTF-8 JSON.
- Maximum 4,096 visited nodes; maximum depth 12; each nested string ≤32,768 characters; object keys must be strings.
- Keys normalized by trimming spaces, lowercasing, and replacing hyphens with underscores. Blocked categories include raw content/rows/prompts/tool output, binary/file/workbook/worksheet content, credentials, connection strings, and tokens. The exact blocked-key set and substring checks are linked above; this report contains no stored values.
- Applies to structured JSON fields, not a semantic secret scanner over every prose string.

### Shared Model write rules and limits

- Runtime identity is resolved server-side. Active principal and identity required; workload principal must be super-admin. `tenant_read`: viewer or higher; metadata write: developer or higher; Model write: architect or higher. Expired Tenant access is ignored. Writes require a non-expired Tenant Lock owned by that same principal. These checks run in [authorization](/Users/maazuddinmohammed/main/projects/gds_workbench_v2/database/03_security.sql:242), not a universal table trigger.
- Model Change Sets validate strict schemas, duplicate normalized natural keys (`strip(" ").casefold()`), existing and nested locked records, physical scope, references, active dependencies, and graph consistency before applying. Validation is phased and stops after the first failing phase; returned issues are capped at 1,000. [Future graph](/Users/maazuddinmohammed/main/projects/gds_workbench_v2/mcp_server/gds_etl_workbench/application/change_sets/model_validation.py:140).
- Staging a record is an upsert by canonical key into the future graph; omission does not delete existing rows. Retained historical references are treated differently from newly authored/changed references. [Graph merge](/Users/maazuddinmohammed/main/projects/gds_workbench_v2/mcp_server/gds_etl_workbench/application/change_sets/model_validation.py:171).
- Apply revalidates the current locked Model revision. Workflow-bound Change Sets cannot be mutated through generic MCP Change Set operations. Expected draft revision, candidate digest and idempotency prevent stale or repeated conflicting application. [MCP apply/validation](/Users/maazuddinmohammed/main/projects/gds_workbench_v2/mcp_server/gds_etl_workbench/application/change_sets/model.py:2684), [web Apply](/Users/maazuddinmohammed/main/projects/gds_workbench_v2/web_app/backend/gds_workbench_api/features/workflows/authoring/change_set_apply.py:95).
- Local plugin/Workbench validation mirrors exported schema/portable record rules for feedback; server validation remains authoritative. Guidance prose in snapshot schemas can contain recommendations stronger than executable validators.


<a id="workflow-tables"></a>

## 3C. `workflow` tables — 28 tables


### Workflow tables — 28

**How to read this table**

- **DB** = declarative PostgreSQL constraint; **Function** = enforced only when that governed SQL function is called; **App** = enforced by the named Python/API path. A CHECK/foreign key does not imply a runtime authorization check.
- **W-BASE applies to every row below.** All 28 tables have required `created_time`, `created_by` (VARCHAR255), `updated_time`, `updated_by` (VARCHAR255), with current timestamp/current user defaults. Except `attribute_profile`, each table has its own BIGINT `GENERATED ALWAYS AS IDENTITY` primary key; that key is required and unique. The profile primary key is `(model_id, attribute_id)`.
- The table’s “Required” bullet lists every other `NOT NULL` column. Fields omitted from it may be NULL unless a CHECK condition requires them. Bounded string fields have their declared maximum in “String limits”; other type bounds come from PostgreSQL BIGINT/INTEGER/BOOLEAN/JSONB/TEXT and the source DDL. `*_is_locked`/`is_locked` defaults false; statuses default active, `is_active` defaults true; nullable Agent Run IDs are VARCHAR500 where present. No automatic lock/update-time/revision trigger was found for these workflow tables.
- Every listed FK uses `ON DELETE NO ACTION`; none cascades deletion. `lower(btrim(...))` uniqueness trims ordinary spaces and lowercases in PostgreSQL. Application natural-key comparisons use ordinary-space trimming + Unicode `casefold()`; these are different implementations.
- `reference.is_nonblank(x)` means **non-NULL and nonempty after ordinary-space trim**; it does not reject all whitespace-only text. Python’s `\S` contracts are stricter. SQL CHECK rejects false, but allows NULL/unknown. [Definition](/Users/maazuddinmohammed/main/projects/gds_workbench_v2/database/01_reference.sql:5).

| Schema | Table | Validations / constraints |
|---|---|---|
| workflow | `attribute_profile` | • **DB / source:** [05_workflow_analysis.sql](/Users/maazuddinmohammed/main/projects/gds_workbench_v2/database/05_workflow_analysis.sql:5).<br>• **Required:** `model_id`, `attribute_id`, `object_id`, `source_context_digest`, `row_count`, `non_null_count`, `null_count`.<br>• **String limits:** `source_context_digest CHAR(64)`. Status strings VARCHAR20; Agent Run ID VARCHAR500 where present.<br>• **PK:** `(model_id, attribute_id)`.<br>• **FK:** `FOREIGN KEY (model_id) REFERENCES model.model (model_id)`.<br>• **FK:** `FOREIGN KEY (model_id, object_id) REFERENCES model.model_input_scope (model_id, object_id)`.<br>• **FK:** `FOREIGN KEY ( attribute_id, object_id ) REFERENCES core.attribute (attribute_id, object_id)`.<br>• **Later FK:** `FOREIGN KEY (workflow_run_id, model_id) REFERENCES application.workflow_run (workflow_run_id, model_id)` [13_application_workflow_runs.sql](/Users/maazuddinmohammed/main/projects/gds_workbench_v2/database/13_application_workflow_runs.sql:727).<br>• **DB check:** `source_context_digest`: exactly 64 lowercase hex characters.<br>• **DB check:** Counts ≥0; `non_null_count + null_count = row_count`; nullable `blank_count` and `distinct_count` must be between 0 and non-null count.<br>• **DB check:** Nullable minimum/maximum/average lengths ≥0; minimum ≤ maximum when both exist.<br>• **DB check:** All five nullable percentages between 0 and 100; percentage type `NUMERIC(7,4)`; average length `NUMERIC(20,6)`.<br>• **App/function:** W-BASE + W-PROFILE. Snapshot row uses `ProfilingProfileRecord`; governed persistence validates metric formulas/current source and exact selected coverage. |
| workflow | `analysis_result` | • **DB / source:** [05_workflow_analysis.sql](/Users/maazuddinmohammed/main/projects/gds_workbench_v2/database/05_workflow_analysis.sql:68).<br>• **Required:** `model_id`, `from_object_id`, `from_attribute_id`, `to_object_id`, `to_attribute_id`, `relationship_kind`, `relationship_confidence`, `relationship_basis`, `analysis_result_status`, `analysis_result_is_locked`.<br>• **String limits:** `validation_source_context_digest CHAR(64)`; `relationship_kind VARCHAR(100)`; `relationship_confidence VARCHAR(10)`; `validation_policy_version VARCHAR(50)`; `validation_policy_digest CHAR(64)`; `validation_result VARCHAR(30)`. Status strings VARCHAR20; Agent Run ID VARCHAR500 where present.<br>• **FK:** `FOREIGN KEY (model_id) REFERENCES model.model (model_id)`.<br>• **FK:** `FOREIGN KEY (model_id, from_object_id) REFERENCES model.model_input_scope (model_id, object_id)`.<br>• **FK:** `FOREIGN KEY (model_id, to_object_id) REFERENCES model.model_input_scope (model_id, object_id)`.<br>• **FK:** `FOREIGN KEY ( from_attribute_id, from_object_id ) REFERENCES core.attribute (attribute_id, object_id)`.<br>• **FK:** `FOREIGN KEY ( to_attribute_id, to_object_id ) REFERENCES core.attribute (attribute_id, object_id)`.<br>• **Unique:** `UNIQUE ( model_id, from_attribute_id, to_attribute_id, relationship_kind )`.<br>• **Later FK:** `FOREIGN KEY (inference_workflow_run_id, model_id) REFERENCES application.workflow_run (workflow_run_id, model_id)` [13_application_workflow_runs.sql](/Users/maazuddinmohammed/main/projects/gds_workbench_v2/database/13_application_workflow_runs.sql:733).<br>• **Later FK:** `FOREIGN KEY (validation_workflow_run_id, model_id) REFERENCES application.workflow_run (workflow_run_id, model_id)` [13_application_workflow_runs.sql](/Users/maazuddinmohammed/main/projects/gds_workbench_v2/database/13_application_workflow_runs.sql:733).<br>• **DB check:** From/to Attribute IDs differ; relationship kind and basis nonblank; confidence ∈ low/medium/high; status ∈ active/inactive/deprecated.<br>• **DB check:** The 10 SQL validation evidence fields—policy version, policy digest, result and seven aggregate counts—are either all NULL or all present.<br>• **DB check:** Validation workflow-run ID requires validation result and source-context digest; a non-NULL source-context digest requires a result.<br>• **DB check:** Policy version matches `^[0-9]+\.[0-9]+\.[0-9]+$`; both digest fields, when present, are exactly 64 lowercase hex characters.<br>• **DB check:** Validation result ∈ supported/inconclusive/unsupported; all seven aggregate counts, when supplied, ≥0.<br>• **App/function:** W-BASE + W-ANALYSIS. Strict endpoint/evidence contract and run-scoped inference/validation apply. |
| workflow | `conceptual_object` | • **DB / source:** [06_workflow_conceptual.sql](/Users/maazuddinmohammed/main/projects/gds_workbench_v2/database/06_workflow_conceptual.sql:3).<br>• **Required:** `model_id`, `conceptual_object_name`, `conceptual_object_definition`, `conceptual_object_type`, `conceptual_object_grain`, `conceptual_object_aliases`, `conceptual_object_confidence`, `conceptual_object_status`, `conceptual_object_is_locked`.<br>• **String limits:** `conceptual_object_name VARCHAR(255)`; `conceptual_object_type VARCHAR(100)`; `conceptual_object_confidence VARCHAR(10)`. Status strings VARCHAR20; Agent Run ID VARCHAR500 where present.<br>• **FK:** `FOREIGN KEY (model_id) REFERENCES model.model (model_id)`.<br>• **Unique:** `UNIQUE (conceptual_object_id, model_id)`.<br>• **Unique index:** `( model_id, lower(btrim(conceptual_object_name)) )`.<br>• **Later FK:** `FOREIGN KEY (workflow_run_id, model_id) REFERENCES application.workflow_run (workflow_run_id, model_id)` [13_application_workflow_runs.sql](/Users/maazuddinmohammed/main/projects/gds_workbench_v2/database/13_application_workflow_runs.sql:743).<br>• **DB check:** Name, definition, type, grain nonblank; confidence ∈ low/medium/high; status ∈ active/inactive/deprecated.<br>• **DB check:** Aliases array required, default empty. SQL does not require unique/nonblank array elements; application normalizes and rejects duplicate aliases.<br>• **App/function:** W-BASE + W-CONCEPTUAL. Aliases and nested support natural keys unique after normalization; nested support validation applies. |
| workflow | `conceptual_relationship` | • **DB / source:** [06_workflow_conceptual.sql](/Users/maazuddinmohammed/main/projects/gds_workbench_v2/database/06_workflow_conceptual.sql:52).<br>• **Required:** `model_id`, `from_conceptual_object_id`, `to_conceptual_object_id`, `conceptual_relationship_name`, `conceptual_relationship_type`, `conceptual_relationship_definition`, `conceptual_relationship_cardinality`, `conceptual_relationship_basis`, `conceptual_relationship_cardinality_basis`, `conceptual_relationship_confidence`, `conceptual_relationship_status`, `conceptual_relationship_is_locked`.<br>• **String limits:** `conceptual_relationship_name VARCHAR(255)`; `conceptual_relationship_type VARCHAR(100)`; `conceptual_relationship_cardinality VARCHAR(30)`; `conceptual_relationship_confidence VARCHAR(10)`. Status strings VARCHAR20; Agent Run ID VARCHAR500 where present.<br>• **FK:** `FOREIGN KEY (model_id) REFERENCES model.model (model_id)`.<br>• **FK:** `FOREIGN KEY ( from_conceptual_object_id, model_id ) REFERENCES workflow.conceptual_object ( conceptual_object_id, model_id )`.<br>• **FK:** `FOREIGN KEY ( to_conceptual_object_id, model_id ) REFERENCES workflow.conceptual_object ( conceptual_object_id, model_id )`.<br>• **Unique:** `UNIQUE (conceptual_relationship_id, model_id)`.<br>• **Unique index:** `( model_id, from_conceptual_object_id, to_conceptual_object_id, lower(btrim(conceptual_relationship_name)) )`.<br>• **Later FK:** `FOREIGN KEY (workflow_run_id, model_id) REFERENCES application.workflow_run (workflow_run_id, model_id)` [13_application_workflow_runs.sql](/Users/maazuddinmohammed/main/projects/gds_workbench_v2/database/13_application_workflow_runs.sql:749).<br>• **DB check:** From/to conceptual Objects differ; name, type, definition, basis and cardinality basis nonblank.<br>• **DB check:** Cardinality ∈ one_to_one/one_to_many/many_to_one/many_to_many/unknown; confidence ∈ low/medium/high; status ∈ active/inactive/deprecated.<br>• **App/function:** W-BASE + W-CONCEPTUAL. Endpoints must resolve; active Relationship requires both active Objects. |
| workflow | `conceptual_support` | • **DB / source:** [06_workflow_conceptual.sql](/Users/maazuddinmohammed/main/projects/gds_workbench_v2/database/06_workflow_conceptual.sql:130).<br>• **Required:** `model_id`, `supported_artifact_type`, `support_source_type`, `conceptual_support_reason`, `conceptual_support_confidence`, `conceptual_support_status`, `conceptual_support_is_locked`.<br>• **String limits:** `supported_artifact_type VARCHAR(30)`; `support_source_type VARCHAR(20)`; `conceptual_support_role VARCHAR(255)`; `conceptual_support_confidence VARCHAR(10)`. Status strings VARCHAR20; Agent Run ID VARCHAR500 where present.<br>• **FK:** `FOREIGN KEY (model_id) REFERENCES model.model (model_id)`.<br>• **FK:** `FOREIGN KEY ( conceptual_object_id, model_id ) REFERENCES workflow.conceptual_object ( conceptual_object_id, model_id )`.<br>• **FK:** `FOREIGN KEY ( conceptual_relationship_id, model_id ) REFERENCES workflow.conceptual_relationship ( conceptual_relationship_id, model_id )`.<br>• **FK:** `FOREIGN KEY ( model_id, source_object_id ) REFERENCES model.model_input_scope (model_id, object_id)`.<br>• **FK:** `FOREIGN KEY ( modeling_assertion_record_id, model_id ) REFERENCES model.modeling_assertion_record ( modeling_assertion_record_id, model_id )`.<br>• **Unique index:** `( model_id, conceptual_object_id, source_object_id ) WHERE supported_artifact_type = 'conceptual_object' AND support_source_type = 'object'`.<br>• **Unique index:** `( model_id, conceptual_object_id, modeling_assertion_record_id ) WHERE supported_artifact_type = 'conceptual_object' AND support_source_type = 'assertion'`.<br>• **Unique index:** `( model_id, conceptual_relationship_id, source_object_id ) WHERE supported_artifact_type = 'conceptual_relationship' AND support_source_type = 'object'`.<br>• **Unique index:** `( model_id, conceptual_relationship_id, modeling_assertion_record_id ) WHERE supported_artifact_type = 'conceptual_relationship' AND support_source_type = 'assertion'`.<br>• **Later FK:** `FOREIGN KEY (workflow_run_id, model_id) REFERENCES application.workflow_run (workflow_run_id, model_id)` [13_application_workflow_runs.sql](/Users/maazuddinmohammed/main/projects/gds_workbench_v2/database/13_application_workflow_runs.sql:755).<br>• **DB check:** Exactly one typed parent: `conceptual_object` with object ID and NULL relationship ID, or `conceptual_relationship` with relationship ID and NULL object ID.<br>• **DB check:** Exactly one typed source: `object` with source-object ID and NULL assertion ID, or `assertion` with assertion-record ID and NULL source-object ID.<br>• **DB check:** Reason nonblank; optional role and reason-detail nonblank if present; confidence ∈ low/medium/high; status ∈ active/inactive/deprecated.<br>• **App/function:** W-BASE + W-CONCEPTUAL via the parent’s `supports` array. Assertion must exist and apply to conceptual layer; physical support must be eligible; matching nested locked support cannot change; omitted records are retained by upsert/merge. |
| workflow | `logical_submodel` | • **DB / source:** [07_workflow_logical.sql](/Users/maazuddinmohammed/main/projects/gds_workbench_v2/database/07_workflow_logical.sql:3).<br>• **Required:** `model_id`, `logical_submodel_name`, `logical_submodel_definition`, `logical_submodel_status`, `logical_submodel_is_locked`.<br>• **String limits:** `logical_submodel_name VARCHAR(255)`. Status strings VARCHAR20; Agent Run ID VARCHAR500 where present.<br>• **FK:** `FOREIGN KEY (model_id) REFERENCES model.model (model_id)`.<br>• **Unique:** `UNIQUE (logical_submodel_id, model_id)`.<br>• **Unique index:** `(model_id, lower(btrim(logical_submodel_name)))`.<br>• **Later FK:** `FOREIGN KEY (workflow_run_id, model_id) REFERENCES application.workflow_run (workflow_run_id, model_id)` [13_application_workflow_runs.sql](/Users/maazuddinmohammed/main/projects/gds_workbench_v2/database/13_application_workflow_runs.sql:761).<br>• **DB check:** Name and definition nonblank; status ∈ active/inactive/deprecated.<br>• **App/function:** W-BASE + W-LOGICAL. Normalized canonical name unique; authoring cannot set locks or modify a locked applied Submodel. |
| workflow | `logical_entity` | • **DB / source:** [07_workflow_logical.sql](/Users/maazuddinmohammed/main/projects/gds_workbench_v2/database/07_workflow_logical.sql:31).<br>• **Required:** `model_id`, `logical_entity_name`, `logical_entity_definition`, `logical_entity_type`, `logical_entity_grain`, `logical_entity_dependency_order`, `logical_entity_confidence`, `logical_entity_status`, `logical_entity_is_locked`.<br>• **String limits:** `logical_entity_name VARCHAR(255)`; `logical_entity_type VARCHAR(50)`; `logical_entity_confidence VARCHAR(10)`. Status strings VARCHAR20; Agent Run ID VARCHAR500 where present.<br>• **FK:** `FOREIGN KEY (model_id) REFERENCES model.model (model_id)`.<br>• **Unique:** `UNIQUE (logical_entity_id, model_id)`.<br>• **Unique index:** `(model_id, lower(btrim(logical_entity_name)))`.<br>• **Later FK:** `FOREIGN KEY (workflow_run_id, model_id) REFERENCES application.workflow_run (workflow_run_id, model_id)` [13_application_workflow_runs.sql](/Users/maazuddinmohammed/main/projects/gds_workbench_v2/database/13_application_workflow_runs.sql:767).<br>• **DB check:** Name, definition, grain nonblank; type ∈ core/reference/transaction/event/bridge/history/snapshot/association/aggregate/other.<br>• **DB check:** For type `other`, type-detail required and nonblank; for every other type, type-detail must be NULL.<br>• **DB check:** Dependency order ≥0; confidence ∈ low/medium/high; status ∈ active/inactive/deprecated.<br>• **App/function:** W-BASE + W-LOGICAL. Memberships and sources unique after normalization; every named Submodel exists; assertions must apply to logical layer; sources must be eligible. |
| workflow | `logical_entity_submodel` | • **DB / source:** [07_workflow_logical.sql](/Users/maazuddinmohammed/main/projects/gds_workbench_v2/database/07_workflow_logical.sql:81).<br>• **Required:** `model_id`, `logical_entity_id`, `logical_submodel_id`, `logical_entity_submodel_status`, `logical_entity_submodel_is_locked`.<br>• **FK:** `FOREIGN KEY (model_id) REFERENCES model.model (model_id)`.<br>• **FK:** `FOREIGN KEY ( logical_entity_id, model_id ) REFERENCES workflow.logical_entity (logical_entity_id, model_id)`.<br>• **FK:** `FOREIGN KEY ( logical_submodel_id, model_id ) REFERENCES workflow.logical_submodel (logical_submodel_id, model_id)`.<br>• **Unique:** `UNIQUE (model_id, logical_entity_id, logical_submodel_id)`.<br>• **Later FK:** `FOREIGN KEY (workflow_run_id, model_id) REFERENCES application.workflow_run (workflow_run_id, model_id)` [13_application_workflow_runs.sql](/Users/maazuddinmohammed/main/projects/gds_workbench_v2/database/13_application_workflow_runs.sql:773).<br>• **DB check:** Status ∈ active/inactive/deprecated.<br>• **App/function:** W-BASE + W-LOGICAL via Entity `submodels`: normalized Submodel membership names unique; Submodel must exist; locked nested memberships preserved. |
| workflow | `logical_attribute` | • **DB / source:** [07_workflow_logical.sql](/Users/maazuddinmohammed/main/projects/gds_workbench_v2/database/07_workflow_logical.sql:115).<br>• **Required:** `model_id`, `logical_entity_id`, `logical_attribute_name`, `logical_attribute_definition`, `logical_attribute_data_type`, `logical_attribute_is_nullable`, `logical_attribute_is_primary_key`, `logical_attribute_is_natural_key`, `logical_attribute_is_surrogate_key`, `logical_attribute_ordinal_position`, `logical_attribute_is_audit_column`, `logical_attribute_status`, `logical_attribute_is_locked`.<br>• **String limits:** `logical_attribute_name VARCHAR(255)`; `logical_attribute_data_type VARCHAR(100)`. Status strings VARCHAR20; Agent Run ID VARCHAR500 where present.<br>• **FK:** `FOREIGN KEY (model_id) REFERENCES model.model (model_id)`.<br>• **FK:** `FOREIGN KEY ( logical_entity_id, model_id ) REFERENCES workflow.logical_entity (logical_entity_id, model_id)`.<br>• **Unique:** `UNIQUE (logical_attribute_id, model_id)`.<br>• **Unique:** `UNIQUE (logical_attribute_id, logical_entity_id, model_id)`.<br>• **Unique index:** `( model_id, logical_entity_id, lower(btrim(logical_attribute_name)) )`.<br>• **Later FK:** `FOREIGN KEY (workflow_run_id, model_id) REFERENCES application.workflow_run (workflow_run_id, model_id)` [13_application_workflow_runs.sql](/Users/maazuddinmohammed/main/projects/gds_workbench_v2/database/13_application_workflow_runs.sql:779).<br>• **DB check:** Name, definition and data type nonblank; ordinal position >0; status ∈ active/inactive/deprecated.<br>• **DB check:** Cannot be both natural and surrogate key; any primary/natural/surrogate key must be non-nullable.<br>• **App/function:** W-BASE + W-LOGICAL. Parent Entity exists; active Attribute requires active Entity; source natural keys unique; configured audit columns projected by backend. |
| workflow | `logical_entity_source_mapping` | • **DB / source:** [07_workflow_logical.sql](/Users/maazuddinmohammed/main/projects/gds_workbench_v2/database/07_workflow_logical.sql:183).<br>• **Required:** `model_id`, `logical_entity_id`, `support_source_type`, `logical_entity_source_mapping_rationale`, `logical_entity_source_mapping_status`, `logical_entity_source_mapping_is_locked`.<br>• **String limits:** `support_source_type VARCHAR(20)`. Status strings VARCHAR20; Agent Run ID VARCHAR500 where present.<br>• **FK:** `FOREIGN KEY (model_id) REFERENCES model.model (model_id)`.<br>• **FK:** `FOREIGN KEY ( logical_entity_id, model_id ) REFERENCES workflow.logical_entity (logical_entity_id, model_id)`.<br>• **FK:** `FOREIGN KEY ( model_id, source_object_id ) REFERENCES model.model_input_scope (model_id, object_id)`.<br>• **FK:** `FOREIGN KEY ( modeling_assertion_record_id, model_id ) REFERENCES model.modeling_assertion_record ( modeling_assertion_record_id, model_id )`.<br>• **Unique:** `UNIQUE ( logical_entity_source_mapping_id, logical_entity_id, source_object_id, model_id )`.<br>• **Unique index:** `( model_id, logical_entity_id, source_object_id ) WHERE support_source_type = 'object'`.<br>• **Unique index:** `( model_id, logical_entity_id, modeling_assertion_record_id ) WHERE support_source_type = 'assertion'`.<br>• **Later FK:** `FOREIGN KEY (workflow_run_id, model_id) REFERENCES application.workflow_run (workflow_run_id, model_id)` [13_application_workflow_runs.sql](/Users/maazuddinmohammed/main/projects/gds_workbench_v2/database/13_application_workflow_runs.sql:785).<br>• **DB check:** Exactly one typed source: `object` with source-object ID and NULL assertion ID, or `assertion` with assertion-record ID and NULL object ID.<br>• **DB check:** Nullable source order >0; rationale nonblank; status ∈ active/inactive/deprecated.<br>• **App/function:** W-BASE + W-LOGICAL via Entity `sources`: source natural keys unique; physical Objects in active Model Input Scope for new authoring; assertion exists and applies to logical layer; locked nested sources preserved. |
| workflow | `logical_attribute_source_mapping` | • **DB / source:** [07_workflow_logical.sql](/Users/maazuddinmohammed/main/projects/gds_workbench_v2/database/07_workflow_logical.sql:262).<br>• **Required:** `model_id`, `logical_entity_id`, `logical_attribute_id`, `support_source_type`, `logical_attribute_source_mapping_rationale`, `logical_attribute_source_mapping_status`, `logical_attribute_source_mapping_is_locked`.<br>• **String limits:** `support_source_type VARCHAR(20)`. Status strings VARCHAR20; Agent Run ID VARCHAR500 where present.<br>• **FK:** `FOREIGN KEY (model_id) REFERENCES model.model (model_id)`.<br>• **FK:** `FOREIGN KEY ( logical_entity_source_mapping_id, logical_entity_id, source_object_id, model_id ) REFERENCES workflow.logical_entity_source_mapping ( logical_entity_source_mapping_id, logical_entity_id, source_object_id, model_id )`.<br>• **FK:** `FOREIGN KEY ( logical_attribute_id, logical_entity_id, model_id ) REFERENCES workflow.logical_attribute ( logical_attribute_id, logical_entity_id, model_id )`.<br>• **FK:** `FOREIGN KEY ( source_attribute_id, source_object_id ) REFERENCES core.attribute (attribute_id, object_id)`.<br>• **FK:** `FOREIGN KEY ( modeling_assertion_record_id, model_id ) REFERENCES model.modeling_assertion_record ( modeling_assertion_record_id, model_id )`.<br>• **Unique index:** `( model_id, logical_entity_source_mapping_id, logical_attribute_id, source_attribute_id ) WHERE support_source_type = 'attribute'`.<br>• **Unique index:** `( model_id, logical_attribute_id, modeling_assertion_record_id ) WHERE support_source_type = 'assertion'`.<br>• **Later FK:** `FOREIGN KEY (workflow_run_id, model_id) REFERENCES application.workflow_run (workflow_run_id, model_id)` [13_application_workflow_runs.sql](/Users/maazuddinmohammed/main/projects/gds_workbench_v2/database/13_application_workflow_runs.sql:791).<br>• **DB check:** Exactly one typed source: `attribute` requires entity-source-mapping ID, source-object ID and source-attribute ID, with assertion ID NULL; `assertion` requires assertion ID and all three physical/source-parent fields NULL.<br>• **DB check:** Composite FKs ensure modeled Attribute belongs to the declared Entity and physical source Attribute belongs to the declared Object; physical branch references its exact Entity-source witness.<br>• **DB check:** Nullable source order >0; rationale nonblank; status ∈ active/inactive/deprecated.<br>• **App/function:** W-BASE + W-LOGICAL via Attribute `sources`: source keys unique; physical Attributes in active Model Input Scope for new authoring; assertion exists and applies to logical layer; locked nested sources preserved; materializer requires physical Entity-source witness. |
| workflow | `logical_relationship` | • **DB / source:** [07_workflow_logical.sql](/Users/maazuddinmohammed/main/projects/gds_workbench_v2/database/07_workflow_logical.sql:358).<br>• **Required:** `model_id`, `logical_relationship_name`, `logical_relationship_definition`, `logical_relationship_from_entity_id`, `logical_relationship_from_attribute_id`, `logical_relationship_to_entity_id`, `logical_relationship_to_attribute_id`, `logical_relationship_cardinality`, `logical_relationship_confidence`, `logical_relationship_basis`, `logical_relationship_cardinality_basis`, `logical_relationship_status`, `logical_relationship_is_locked`.<br>• **String limits:** `logical_relationship_name VARCHAR(255)`; `logical_relationship_cardinality VARCHAR(50)`; `logical_relationship_confidence VARCHAR(10)`. Status strings VARCHAR20; Agent Run ID VARCHAR500 where present.<br>• **FK:** `FOREIGN KEY (model_id) REFERENCES model.model (model_id)`.<br>• **FK:** `FOREIGN KEY ( logical_relationship_from_entity_id, model_id ) REFERENCES workflow.logical_entity (logical_entity_id, model_id)`.<br>• **FK:** `FOREIGN KEY ( logical_relationship_to_entity_id, model_id ) REFERENCES workflow.logical_entity (logical_entity_id, model_id)`.<br>• **FK:** `FOREIGN KEY ( logical_relationship_from_attribute_id, logical_relationship_from_entity_id, model_id ) REFERENCES workflow.logical_attribute ( logical_attribute_id, logical_entity_id, model_id )`.<br>• **FK:** `FOREIGN KEY ( logical_relationship_to_attribute_id, logical_relationship_to_entity_id, model_id ) REFERENCES workflow.logical_attribute ( logical_attribute_id, logical_entity_id, model_id )`.<br>• **Unique index:** `( model_id, logical_relationship_from_entity_id, logical_relationship_from_attribute_id, logical_relationship_to_entity_id, logical_relationship_to_attribute_id, lower(btrim(logical_relationship_name)) )`.<br>• **Later FK:** `FOREIGN KEY (workflow_run_id, model_id) REFERENCES application.workflow_run (workflow_run_id, model_id)` [13_application_workflow_runs.sql](/Users/maazuddinmohammed/main/projects/gds_workbench_v2/database/13_application_workflow_runs.sql:797).<br>• **DB check:** From/to Entity+Attribute endpoints differ; name, definition, basis and cardinality basis nonblank; cardinality ∈ one_to_one/one_to_many/many_to_one/many_to_many; confidence ∈ low/medium/high; status ∈ active/inactive/deprecated.<br>• **App/function:** W-BASE + W-LOGICAL. Both Entity/Attribute endpoints must resolve; active Relationship requires both active Entities and Attributes; normalized endpoints differ. |
| workflow | `dimensional_submodel` | • **DB / source:** [08_workflow_dimensional.sql](/Users/maazuddinmohammed/main/projects/gds_workbench_v2/database/08_workflow_dimensional.sql:3).<br>• **Required:** `model_id`, `dimensional_submodel_name`, `dimensional_submodel_definition`, `dimensional_submodel_status`, `dimensional_submodel_is_locked`.<br>• **String limits:** `dimensional_submodel_name VARCHAR(255)`. Status strings VARCHAR20; Agent Run ID VARCHAR500 where present.<br>• **FK:** `FOREIGN KEY (model_id) REFERENCES model.model (model_id)`.<br>• **Unique:** `UNIQUE (dimensional_submodel_id, model_id)`.<br>• **Unique index:** `( model_id, lower(btrim(dimensional_submodel_name)) ) WHERE dimensional_submodel_status = 'active'`.<br>• **Later FK:** `FOREIGN KEY (workflow_run_id, model_id) REFERENCES application.workflow_run (workflow_run_id, model_id)` [13_application_workflow_runs.sql](/Users/maazuddinmohammed/main/projects/gds_workbench_v2/database/13_application_workflow_runs.sql:803).<br>• **DB check:** Name and definition nonblank; status ∈ active/inactive/deprecated; name uniqueness applies only to active rows.<br>• **App/function:** W-BASE + W-GOLD. Strict canonical-name duplicate checks also apply to candidate records with inactive status; authoring cannot set locks. |
| workflow | `dimensional_entity` | • **DB / source:** [08_workflow_dimensional.sql](/Users/maazuddinmohammed/main/projects/gds_workbench_v2/database/08_workflow_dimensional.sql:39).<br>• **Required:** `model_id`, `dimensional_entity_name`, `dimensional_entity_definition`, `dimensional_entity_type`, `dimensional_entity_dependency_order`, `dimensional_entity_confidence`, `dimensional_entity_status`, `dimensional_entity_is_locked`.<br>• **String limits:** `dimensional_entity_name VARCHAR(255)`; `dimensional_entity_type VARCHAR(20)`; `dimensional_fact_type VARCHAR(30)`; `dimensional_entity_confidence VARCHAR(10)`. Status strings VARCHAR20; Agent Run ID VARCHAR500 where present.<br>• **FK:** `FOREIGN KEY (model_id) REFERENCES model.model (model_id)`.<br>• **Unique:** `UNIQUE (dimensional_entity_id, model_id)`.<br>• **Unique index:** `( model_id, lower(btrim(dimensional_entity_name)) ) WHERE dimensional_entity_status = 'active'`.<br>• **Later FK:** `FOREIGN KEY (workflow_run_id, model_id) REFERENCES application.workflow_run (workflow_run_id, model_id)` [13_application_workflow_runs.sql](/Users/maazuddinmohammed/main/projects/gds_workbench_v2/database/13_application_workflow_runs.sql:809).<br>• **DB check:** Name and definition nonblank; type ∈ fact/dimension/bridge.<br>• **DB check:** Fact-type CHECK permits transaction/periodic_snapshot/accumulating_snapshot/factless for a fact; non-facts must have NULL fact-type. **SQL NULL detail:** a fact with NULL fact-type passes this nullable CHECK; application rejects it.<br>• **DB check:** Facts and bridges require nonblank grain definition; dimensions permit NULL or nonblank grain.<br>• **DB check:** Dependency order ≥0; confidence ∈ low/medium/high; status ∈ active/inactive/deprecated; name uniqueness applies only to active rows.<br>• **App/function:** W-BASE + W-GOLD. Fact type required iff fact; membership/source keys unique; referenced Submodels exist; assertions apply to dimensional layer; new physical sources require Silver Logical contribution. |
| workflow | `dimensional_entity_submodel` | • **DB / source:** [08_workflow_dimensional.sql](/Users/maazuddinmohammed/main/projects/gds_workbench_v2/database/08_workflow_dimensional.sql:113).<br>• **Required:** `model_id`, `dimensional_entity_id`, `dimensional_submodel_id`, `dimensional_entity_submodel_status`, `dimensional_entity_submodel_is_locked`.<br>• **FK:** `FOREIGN KEY (model_id) REFERENCES model.model (model_id)`.<br>• **FK:** `FOREIGN KEY ( dimensional_entity_id, model_id ) REFERENCES workflow.dimensional_entity (dimensional_entity_id, model_id)`.<br>• **FK:** `FOREIGN KEY ( dimensional_submodel_id, model_id ) REFERENCES workflow.dimensional_submodel (dimensional_submodel_id, model_id)`.<br>• **Unique index:** `( model_id, dimensional_entity_id, dimensional_submodel_id ) WHERE dimensional_entity_submodel_status = 'active'`.<br>• **Later FK:** `FOREIGN KEY (workflow_run_id, model_id) REFERENCES application.workflow_run (workflow_run_id, model_id)` [13_application_workflow_runs.sql](/Users/maazuddinmohammed/main/projects/gds_workbench_v2/database/13_application_workflow_runs.sql:815).<br>• **DB check:** Status ∈ active/inactive/deprecated; Entity/Submodel pair unique only among active memberships.<br>• **App/function:** W-BASE + W-GOLD via Entity `submodels`: normalized membership names unique; referenced Submodel exists; locked nested membership preserved. |
| workflow | `dimensional_attribute` | • **DB / source:** [08_workflow_dimensional.sql](/Users/maazuddinmohammed/main/projects/gds_workbench_v2/database/08_workflow_dimensional.sql:152).<br>• **Required:** `model_id`, `dimensional_entity_id`, `dimensional_attribute_name`, `dimensional_attribute_definition`, `dimensional_attribute_data_type`, `dimensional_attribute_is_nullable`, `dimensional_attribute_ordinal_position`, `dimensional_attribute_role`, `dimensional_attribute_key_role`, `dimensional_attribute_is_grain_component`, `dimensional_attribute_is_audit_column`, `dimensional_attribute_confidence`, `dimensional_attribute_status`, `dimensional_attribute_is_locked`.<br>• **String limits:** `dimensional_attribute_name VARCHAR(255)`; `dimensional_attribute_data_type VARCHAR(100)`; `dimensional_attribute_role VARCHAR(30)`; `dimensional_attribute_key_role VARCHAR(20)`; `dimensional_attribute_additivity VARCHAR(30)`; `dimensional_attribute_default_aggregation VARCHAR(100)`; `dimensional_attribute_change_behavior VARCHAR(20)`; `dimensional_attribute_confidence VARCHAR(10)`. Status strings VARCHAR20; Agent Run ID VARCHAR500 where present.<br>• **FK:** `FOREIGN KEY (model_id) REFERENCES model.model (model_id)`.<br>• **FK:** `FOREIGN KEY ( dimensional_entity_id, model_id ) REFERENCES workflow.dimensional_entity (dimensional_entity_id, model_id)`.<br>• **Unique:** `UNIQUE (dimensional_attribute_id, model_id)`.<br>• **Unique:** `UNIQUE (dimensional_attribute_id, dimensional_entity_id, model_id)`.<br>• **Unique index:** `( model_id, dimensional_entity_id, lower(btrim(dimensional_attribute_name)) ) WHERE dimensional_attribute_status = 'active'`.<br>• **Later FK:** `FOREIGN KEY (workflow_run_id, model_id) REFERENCES application.workflow_run (workflow_run_id, model_id)` [13_application_workflow_runs.sql](/Users/maazuddinmohammed/main/projects/gds_workbench_v2/database/13_application_workflow_runs.sql:821).<br>• **DB check:** Name, definition and data type nonblank; ordinal position >0; confidence ∈ low/medium/high; status ∈ active/inactive/deprecated.<br>• **DB check:** Role ∈ key/descriptor/measure/degenerate_dimension/bridge_weight/technical/audit; key role ∈ none/surrogate/business/foreign; non-none key role requires role key or technical.<br>• **DB check:** Measure: nonblank default aggregation; additivity, if present, ∈ additive/semi_additive/non_additive; semi/non-additive measures require nonblank aggregation basis. Application additionally requires non-NULL additivity. Non-measures must have NULL additivity, default aggregation and aggregation basis.<br>• **DB check:** Optional change behavior ∈ fixed/overwrite/historize; audit Boolean must equal `(role = audit)`; name uniqueness applies only to active rows.<br>• **App/function:** W-BASE + W-GOLD. Parent exists and is active for active Attribute; measure additivity/aggregation required; source keys unique; generated technical/audit/surrogate/foreign-key columns reserved for policy projection. |
| workflow | `dimensional_entity_source_mapping` | • **DB / source:** [08_workflow_dimensional.sql](/Users/maazuddinmohammed/main/projects/gds_workbench_v2/database/08_workflow_dimensional.sql:259).<br>• **Required:** `model_id`, `dimensional_entity_id`, `support_source_type`, `dimensional_entity_source_role`, `dimensional_entity_source_mapping_rationale`, `dimensional_entity_source_mapping_status`, `dimensional_entity_source_mapping_is_locked`.<br>• **String limits:** `support_source_type VARCHAR(20)`; `dimensional_entity_source_role VARCHAR(255)`. Status strings VARCHAR20; Agent Run ID VARCHAR500 where present.<br>• **FK:** `FOREIGN KEY (model_id) REFERENCES model.model (model_id)`.<br>• **FK:** `FOREIGN KEY ( dimensional_entity_id, model_id ) REFERENCES workflow.dimensional_entity (dimensional_entity_id, model_id)`.<br>• **FK:** `FOREIGN KEY ( modeling_assertion_record_id, model_id ) REFERENCES model.modeling_assertion_record ( modeling_assertion_record_id, model_id )`.<br>• **Unique:** `UNIQUE ( dimensional_entity_source_mapping_id, dimensional_entity_id, source_object_id, model_id )`.<br>• **Unique index:** `( model_id, dimensional_entity_id, source_object_id ) WHERE support_source_type = 'object' AND dimensional_entity_source_mapping_status = 'active'`.<br>• **Unique index:** `( model_id, dimensional_entity_id, modeling_assertion_record_id ) WHERE support_source_type = 'assertion' AND dimensional_entity_source_mapping_status = 'active'`.<br>• **Later FK:** `FOREIGN KEY ( model_id, source_object_id ) REFERENCES workflow.model_object_binding (model_id, object_id)` [09_workflow_mapping.sql](/Users/maazuddinmohammed/main/projects/gds_workbench_v2/database/09_workflow_mapping.sql:113).<br>• **Later FK:** `FOREIGN KEY (workflow_run_id, model_id) REFERENCES application.workflow_run (workflow_run_id, model_id)` [13_application_workflow_runs.sql](/Users/maazuddinmohammed/main/projects/gds_workbench_v2/database/13_application_workflow_runs.sql:827).<br>• **DB check:** Exactly one typed source: `object` with source-object ID and NULL assertion ID, or `assertion` with assertion ID and NULL source-object ID.<br>• **DB check:** Source role and rationale nonblank; nullable source order >0; status ∈ active/inactive/deprecated.<br>• **DB check:** Object branch references a Model Object Binding, **not** Model Input Scope; active Silver/Logical/Mapping eligibility is application/function enforcement. Typed-source uniqueness applies only to active rows.<br>• **App/function:** W-BASE + W-GOLD via Entity `sources`: source keys unique; assertion applies to dimensional layer; new Objects require active Silver Logical contribution; frozen run selection enforced in authoring. |
| workflow | `dimensional_attribute_source_mapping` | • **DB / source:** [08_workflow_dimensional.sql](/Users/maazuddinmohammed/main/projects/gds_workbench_v2/database/08_workflow_dimensional.sql:340).<br>• **Required:** `model_id`, `dimensional_entity_id`, `dimensional_attribute_id`, `support_source_type`, `dimensional_attribute_source_mapping_rationale`, `dimensional_attribute_source_mapping_status`, `dimensional_attribute_source_mapping_is_locked`.<br>• **String limits:** `support_source_type VARCHAR(20)`. Status strings VARCHAR20; Agent Run ID VARCHAR500 where present.<br>• **FK:** `FOREIGN KEY (model_id) REFERENCES model.model (model_id)`.<br>• **FK:** `FOREIGN KEY ( dimensional_entity_source_mapping_id, dimensional_entity_id, source_object_id, model_id ) REFERENCES workflow.dimensional_entity_source_mapping ( dimensional_entity_source_mapping_id, dimensional_entity_id, source_object_id, model_id )`.<br>• **FK:** `FOREIGN KEY ( dimensional_attribute_id, dimensional_entity_id, model_id ) REFERENCES workflow.dimensional_attribute ( dimensional_attribute_id, dimensional_entity_id, model_id )`.<br>• **FK:** `FOREIGN KEY ( source_attribute_id, source_object_id ) REFERENCES core.attribute (attribute_id, object_id)`.<br>• **FK:** `FOREIGN KEY ( modeling_assertion_record_id, model_id ) REFERENCES model.modeling_assertion_record ( modeling_assertion_record_id, model_id )`.<br>• **Unique index:** `( model_id, dimensional_entity_source_mapping_id, dimensional_attribute_id, source_attribute_id ) WHERE support_source_type = 'attribute' AND dimensional_attribute_source_mapping_status = 'active'`.<br>• **Unique index:** `( model_id, dimensional_attribute_id, modeling_assertion_record_id ) WHERE support_source_type = 'assertion' AND dimensional_attribute_source_mapping_status = 'active'`.<br>• **Later FK:** `FOREIGN KEY (workflow_run_id, model_id) REFERENCES application.workflow_run (workflow_run_id, model_id)` [13_application_workflow_runs.sql](/Users/maazuddinmohammed/main/projects/gds_workbench_v2/database/13_application_workflow_runs.sql:833).<br>• **DB check:** Exactly one typed source: `attribute` requires entity-source-mapping ID, source-object ID and source-attribute ID, with assertion ID NULL; `assertion` requires assertion ID and all three physical/source-parent fields NULL.<br>• **DB check:** Composite FKs ensure modeled Attribute belongs to the declared Entity and physical Attribute belongs to the source Object; physical branch references its exact Entity-source witness.<br>• **DB check:** Nullable source order >0; rationale nonblank; status ∈ active/inactive/deprecated; typed-source uniqueness applies only to active rows.<br>• **App/function:** W-BASE + W-GOLD via Attribute `sources`: source keys unique; assertion applies to dimensional layer; new Attributes require active Silver Logical contribution; physical Entity-source witness resolved on apply. |
| workflow | `dimensional_relationship` | • **DB / source:** [08_workflow_dimensional.sql](/Users/maazuddinmohammed/main/projects/gds_workbench_v2/database/08_workflow_dimensional.sql:438).<br>• **Required:** `model_id`, `dimensional_relationship_name`, `dimensional_relationship_definition`, `dimensional_relationship_from_entity_id`, `dimensional_relationship_from_attribute_id`, `dimensional_relationship_to_entity_id`, `dimensional_relationship_to_attribute_id`, `dimensional_relationship_kind`, `dimensional_relationship_cardinality`, `dimensional_relationship_is_optional`, `dimensional_relationship_confidence`, `dimensional_relationship_basis`, `dimensional_relationship_cardinality_basis`, `dimensional_relationship_status`, `dimensional_relationship_is_locked`.<br>• **String limits:** `dimensional_relationship_name VARCHAR(255)`; `dimensional_relationship_kind VARCHAR(50)`; `dimensional_relationship_cardinality VARCHAR(50)`; `dimensional_relationship_role_name VARCHAR(255)`; `dimensional_relationship_confidence VARCHAR(10)`. Status strings VARCHAR20; Agent Run ID VARCHAR500 where present.<br>• **FK:** `FOREIGN KEY (model_id) REFERENCES model.model (model_id)`.<br>• **FK:** `FOREIGN KEY ( dimensional_relationship_from_entity_id, model_id ) REFERENCES workflow.dimensional_entity (dimensional_entity_id, model_id)`.<br>• **FK:** `FOREIGN KEY ( dimensional_relationship_to_entity_id, model_id ) REFERENCES workflow.dimensional_entity (dimensional_entity_id, model_id)`.<br>• **FK:** `FOREIGN KEY ( dimensional_relationship_from_attribute_id, dimensional_relationship_from_entity_id, model_id ) REFERENCES workflow.dimensional_attribute ( dimensional_attribute_id, dimensional_entity_id, model_id )`.<br>• **FK:** `FOREIGN KEY ( dimensional_relationship_to_attribute_id, dimensional_relationship_to_entity_id, model_id ) REFERENCES workflow.dimensional_attribute ( dimensional_attribute_id, dimensional_entity_id, model_id )`.<br>• **Unique index:** `( model_id, dimensional_relationship_from_entity_id, dimensional_relationship_from_attribute_id, dimensional_relationship_to_entity_id, dimensional_relationship_to_attribute_id, lower(btrim(dimensional_relationship_kind)), coalesce(lower(btrim(dimensional_relationship_role_name)), '') ) WHERE dimensional_relationship_status = 'active'`.<br>• **Later FK:** `FOREIGN KEY (workflow_run_id, model_id) REFERENCES application.workflow_run (workflow_run_id, model_id)` [13_application_workflow_runs.sql](/Users/maazuddinmohammed/main/projects/gds_workbench_v2/database/13_application_workflow_runs.sql:839).<br>• **DB check:** From/to Entity+Attribute endpoints differ; name, definition, kind, basis and cardinality basis nonblank.<br>• **DB check:** Cardinality ∈ one_to_one/one_to_many/many_to_one/many_to_many; optional role name nonblank if present; confidence ∈ low/medium/high; status ∈ active/inactive/deprecated.<br>• **DB check:** Optionality Boolean is required; active-row identity uses endpoints + normalized kind + normalized role (NULL role treated as empty), rather than relationship name.<br>• **App/function:** W-BASE + W-GOLD. Endpoints exist; active Relationship requires active Entities/Attributes; Fact/Bridge → Dimension policy projects/rebinds foreign-key endpoints and optionality. |
| workflow | `model_object_binding` | • **DB / source:** [09_workflow_mapping.sql](/Users/maazuddinmohammed/main/projects/gds_workbench_v2/database/09_workflow_mapping.sql:3).<br>• **Required:** `model_id`, `object_id`, `modeled_entity_type`, `model_object_binding_status`, `model_object_binding_is_locked`.<br>• **String limits:** `modeled_entity_type VARCHAR(30)`. Status strings VARCHAR20; Agent Run ID VARCHAR500 where present.<br>• **FK:** `FOREIGN KEY (model_id) REFERENCES model.model (model_id)`.<br>• **FK:** `FOREIGN KEY (object_id) REFERENCES core.object (object_id)`.<br>• **FK:** `FOREIGN KEY ( logical_entity_id, model_id ) REFERENCES workflow.logical_entity ( logical_entity_id, model_id )`.<br>• **FK:** `FOREIGN KEY ( dimensional_entity_id, model_id ) REFERENCES workflow.dimensional_entity ( dimensional_entity_id, model_id )`.<br>• **Unique:** `UNIQUE (model_id, object_id)`.<br>• **Unique index:** `(model_id, logical_entity_id) WHERE modeled_entity_type = 'logical_entity'`.<br>• **Unique index:** `(model_id, dimensional_entity_id) WHERE modeled_entity_type = 'dimensional_entity'`.<br>• **Later FK:** `FOREIGN KEY (workflow_run_id, model_id) REFERENCES application.workflow_run (workflow_run_id, model_id)` [13_application_workflow_runs.sql](/Users/maazuddinmohammed/main/projects/gds_workbench_v2/database/13_application_workflow_runs.sql:845).<br>• **DB check:** Exactly one typed entity: `logical_entity` with logical Entity ID and NULL dimensional Entity ID, or `dimensional_entity` with dimensional Entity ID and NULL logical Entity ID.<br>• **DB check:** Status ∈ active/inactive/deprecated; physical Object and modeled Entity uniqueness includes inactive/deprecated rows.<br>• **App/function:** W-BASE + W-BINDING. Correct modeled layer/Tenant/physical target and active parent; no active target collision; exact modeled+physical Attribute coverage. |
| workflow | `model_attribute_binding` | • **DB / source:** [09_workflow_mapping.sql](/Users/maazuddinmohammed/main/projects/gds_workbench_v2/database/09_workflow_mapping.sql:62).<br>• **Required:** `model_object_binding_id`, `attribute_id`, `model_attribute_binding_status`, `model_attribute_binding_is_locked`.<br>• **FK:** `FOREIGN KEY (model_object_binding_id) REFERENCES workflow.model_object_binding (model_object_binding_id)`.<br>• **FK:** `FOREIGN KEY (attribute_id) REFERENCES core.attribute (attribute_id)`.<br>• **FK:** `FOREIGN KEY (logical_attribute_id) REFERENCES workflow.logical_attribute (logical_attribute_id)`.<br>• **FK:** `FOREIGN KEY (dimensional_attribute_id) REFERENCES workflow.dimensional_attribute (dimensional_attribute_id)`.<br>• **Unique:** `UNIQUE (model_object_binding_id, attribute_id)`.<br>• **Unique index:** `(logical_attribute_id) WHERE logical_attribute_id IS NOT NULL`.<br>• **Unique index:** `(dimensional_attribute_id) WHERE dimensional_attribute_id IS NOT NULL`.<br>• **Later FK:** `FOREIGN KEY (workflow_run_id) REFERENCES application.workflow_run (workflow_run_id)` [13_application_workflow_runs.sql](/Users/maazuddinmohammed/main/projects/gds_workbench_v2/database/13_application_workflow_runs.sql:851).<br>• **DB check:** Exactly one of logical Attribute ID / dimensional Attribute ID non-NULL; status ∈ active/inactive/deprecated.<br>• **DB check:** FK existence alone does not connect the physical Attribute to the parent Binding’s Object or the modeled Attribute to the parent’s Entity/type; application resolves and verifies those relationships.<br>• **App/function:** W-BASE + W-BINDING. Correct physical Object, modeled Entity and layer; active Attribute/Object parents; one active binding per physical Attribute; full two-sided coverage. |
| workflow | `mapping_source_system_dependency` | • **DB / source:** [09_workflow_mapping.sql](/Users/maazuddinmohammed/main/projects/gds_workbench_v2/database/09_workflow_mapping.sql:120).<br>• **Required:** `model_id`, `modeled_entity_type`, `source_system_id`, `source_system_dependency_order`, `mapping_source_system_dependency_status`, `mapping_source_system_dependency_is_locked`.<br>• **String limits:** `modeled_entity_type VARCHAR(30)`. Status strings VARCHAR20; Agent Run ID VARCHAR500 where present.<br>• **FK:** `FOREIGN KEY (model_id) REFERENCES model.model (model_id)`.<br>• **FK:** `FOREIGN KEY (source_system_id) REFERENCES core.system (system_id)`.<br>• **Unique:** `UNIQUE (model_id, modeled_entity_type, source_system_id)`.<br>• **Later FK:** `FOREIGN KEY (workflow_run_id, model_id) REFERENCES application.workflow_run (workflow_run_id, model_id)` [13_application_workflow_runs.sql](/Users/maazuddinmohammed/main/projects/gds_workbench_v2/database/13_application_workflow_runs.sql:857).<br>• **DB check:** Modeled entity type ∈ logical_entity/dimensional_entity; source-System dependency order ≥0; status ∈ active/inactive/deprecated.<br>• **App/function:** W-BASE + W-MAPPING. Active System required; exact layer/System reference used by Mapping Objects; route readiness checks graph shape, frozen selected System, earlier-wave edges and cycles. |
| workflow | `mapping_object` | • **DB / source:** [09_workflow_mapping.sql](/Users/maazuddinmohammed/main/projects/gds_workbench_v2/database/09_workflow_mapping.sql:153).<br>• **Required:** `model_id`, `model_object_binding_id`, `source_system_id`, `object_dependency_order`, `object_mapping_status`, `object_mapping_is_locked`.<br>• **FK:** `FOREIGN KEY (model_id) REFERENCES model.model (model_id)`.<br>• **FK:** `FOREIGN KEY (model_object_binding_id) REFERENCES workflow.model_object_binding (model_object_binding_id)`.<br>• **FK:** `FOREIGN KEY (source_system_id) REFERENCES core.system (system_id)`.<br>• **Unique:** `UNIQUE ( model_object_binding_id, source_system_id )`.<br>• **Later FK:** `FOREIGN KEY (output_template_id) REFERENCES application.output_template (output_template_id)` [12_application_configuration.sql](/Users/maazuddinmohammed/main/projects/gds_workbench_v2/database/12_application_configuration.sql:2097).<br>• **Later FK:** `FOREIGN KEY (workflow_run_id, model_id) REFERENCES application.workflow_run (workflow_run_id, model_id)` [13_application_workflow_runs.sql](/Users/maazuddinmohammed/main/projects/gds_workbench_v2/database/13_application_workflow_runs.sql:863).<br>• **DB check:** Object dependency order ≥0; nullable transformation must be a JSON object with PostgreSQL text serialization ≤524,288 bytes; status ∈ active/inactive/deprecated.<br>• **DB check:** FK existence alone does not require the Object Binding to belong to the row’s Model, or require matching dependency/template type; application resolves/checks these.<br>• **App/function:** W-BASE + W-MAPPING. Binding/dependency/System resolve; active row requires active Binding/dependency and non-NULL transformation; complete active Attribute Mapping per source System; template resolved by target type. |
| workflow | `mapping_attribute` | • **DB / source:** [09_workflow_mapping.sql](/Users/maazuddinmohammed/main/projects/gds_workbench_v2/database/09_workflow_mapping.sql:195).<br>• **Required:** `mapping_object_id`, `model_attribute_binding_id`, `attribute_mapping_status`, `attribute_mapping_is_locked`.<br>• **FK:** `FOREIGN KEY (mapping_object_id) REFERENCES workflow.mapping_object (mapping_object_id)`.<br>• **FK:** `FOREIGN KEY ( model_attribute_binding_id ) REFERENCES workflow.model_attribute_binding ( model_attribute_binding_id )`.<br>• **Unique:** `UNIQUE ( mapping_object_id, model_attribute_binding_id )`.<br>• **Later FK:** `FOREIGN KEY (output_template_id) REFERENCES application.output_template (output_template_id)` [12_application_configuration.sql](/Users/maazuddinmohammed/main/projects/gds_workbench_v2/database/12_application_configuration.sql:2106).<br>• **Later FK:** `FOREIGN KEY (workflow_run_id) REFERENCES application.workflow_run (workflow_run_id)` [13_application_workflow_runs.sql](/Users/maazuddinmohammed/main/projects/gds_workbench_v2/database/13_application_workflow_runs.sql:869).<br>• **DB check:** Nullable transformation must be a JSON object with PostgreSQL text serialization ≤65,536 bytes; status ∈ active/inactive/deprecated.<br>• **DB check:** FK existence alone does not require the Attribute Binding to belong to the Mapping Object’s Binding; application resolves/checks this.<br>• **App/function:** W-BASE + W-MAPPING. Mapping Object and Attribute Binding resolve to same modeled Entity; active row needs active parents and non-NULL transformation; source System active; candidate exact actionable coverage/template shape. |
| workflow | `generated_code` | • **DB / source:** [10_workflow_code_validation.sql](/Users/maazuddinmohammed/main/projects/gds_workbench_v2/database/10_workflow_code_validation.sql:3).<br>• **Required:** `model_object_binding_id`, `artifact_name`, `artifact_type`, `generated_code_content`, `code_input_digest`, `generated_code_is_locked`, `generated_code_status`.<br>• **String limits:** `artifact_name VARCHAR(400)`; `artifact_type VARCHAR(30)`; `code_input_digest CHAR(64)`; `generated_code_digest CHAR(64)`. Status strings VARCHAR20; Agent Run ID VARCHAR500 where present.<br>• **FK:** `FOREIGN KEY (model_object_binding_id) REFERENCES workflow.model_object_binding (model_object_binding_id)`.<br>• **Unique index:** `( model_object_binding_id, lower(btrim(artifact_name)) )`.<br>• **Later FK:** `FOREIGN KEY (workflow_run_id) REFERENCES application.workflow_run (workflow_run_id)` [13_application_workflow_runs.sql](/Users/maazuddinmohammed/main/projects/gds_workbench_v2/database/13_application_workflow_runs.sql:875).<br>• **DB check:** Artifact name nonblank, trimmed, no slash/backslash, and not `.`/`..`; artifact type ∈ sql_file/python_file/python_notebook.<br>• **DB check:** Content nonblank; input digest exactly 64 lowercase hex characters; generated-code digest computed/stored as SHA-256(content bytes).<br>• **DB check:** Status ∈ active/inactive/deprecated; artifact-name uniqueness is per Object Binding and includes all statuses.<br>• **App/function:** W-BASE + W-CODE. Correct physical target; active Object Binding; apply requires complete active Mapping and derives current code-input digest; content/filename and frozen coverage checks. |
| workflow | `generated_code_source_system` | • **DB / source:** [10_workflow_code_validation.sql](/Users/maazuddinmohammed/main/projects/gds_workbench_v2/database/10_workflow_code_validation.sql:53).<br>• **Required:** `generated_code_id`, `source_system_id`, `generated_code_source_system_is_locked`, `generated_code_source_system_status`.<br>• **FK:** `FOREIGN KEY (generated_code_id) REFERENCES workflow.generated_code (generated_code_id)`.<br>• **FK:** `FOREIGN KEY (source_system_id) REFERENCES core.system (system_id)`.<br>• **Unique:** `UNIQUE ( generated_code_id, source_system_id )`.<br>• **Later FK:** `FOREIGN KEY (workflow_run_id) REFERENCES application.workflow_run (workflow_run_id)` [13_application_workflow_runs.sql](/Users/maazuddinmohammed/main/projects/gds_workbench_v2/database/13_application_workflow_runs.sql:881).<br>• **DB check:** Status ∈ active/inactive/deprecated; one source-System row per code artifact/System pair.<br>• **App/function:** W-BASE + W-CODE. Code artifact exists; System active; active assignment requires active Code and corresponding active Mapping; mapped Systems assigned exactly once during Code authoring. |
| workflow | `validation_group` | • **DB / source:** [10_workflow_code_validation.sql](/Users/maazuddinmohammed/main/projects/gds_workbench_v2/database/10_workflow_code_validation.sql:84).<br>• **Required:** `model_id`, `tenant_id`, `system_id`, `validation_group_name`, `mapping_context_digest`, `is_locked`, `is_active`.<br>• **String limits:** `validation_group_name VARCHAR(200)`; `mapping_context_digest CHAR(64)`; `code_context_digest CHAR(64)`. Status strings VARCHAR20; Agent Run ID VARCHAR500 where present.<br>• **FK:** `FOREIGN KEY ( model_id, tenant_id ) REFERENCES model.model (model_id, tenant_id)`.<br>• **FK:** `FOREIGN KEY (system_id) REFERENCES core.system (system_id)`.<br>• **Unique:** `UNIQUE ( validation_group_id, model_id, tenant_id, system_id )`.<br>• **Unique index:** `( model_id, tenant_id, system_id, lower(btrim(validation_group_name)) )`.<br>• **Later FK:** `FOREIGN KEY (workflow_run_id, model_id) REFERENCES application.workflow_run (workflow_run_id, model_id)` [13_application_workflow_runs.sql](/Users/maazuddinmohammed/main/projects/gds_workbench_v2/database/13_application_workflow_runs.sql:887).<br>• **DB check:** Name nonblank; nullable description nonblank and ≤16,384 UTF-8 bytes.<br>• **DB check:** Mapping-context digest required, code-context digest nullable; both exactly 64 lowercase hex characters when supplied.<br>• **DB check:** Composite Model/Tenant FK enforces owner agreement; name uniqueness includes inactive groups.<br>• **App/function:** W-BASE + W-VALIDATION. Tenant must own Model; System active; active group requires active Mapping for System; apply derives mapping/code context digests and requires complete Mapping. |
| workflow | `validation_check` | • **DB / source:** [10_workflow_code_validation.sql](/Users/maazuddinmohammed/main/projects/gds_workbench_v2/database/10_workflow_code_validation.sql:148).<br>• **Required:** `validation_group_id`, `validation_check_name`, `validation_category_code`, `validation_severity`, `validation_query_sql`, `validation_comparison_operator`, `validation_comparison_value_type`, `is_locked`, `is_active`.<br>• **String limits:** `validation_check_name VARCHAR(200)`; `validation_category_code VARCHAR(100)`; `validation_severity VARCHAR(20)`; `validation_result_data_type VARCHAR(20)`; `validation_comparison_operator VARCHAR(30)`; `validation_comparison_value_type VARCHAR(20)`. Status strings VARCHAR20; Agent Run ID VARCHAR500 where present.<br>• **FK:** `FOREIGN KEY (validation_group_id) REFERENCES workflow.validation_group (validation_group_id)`.<br>• **Unique index:** `( validation_group_id, lower(btrim(validation_check_name)) )`.<br>• **DB check:** Name nonblank; nullable description nonblank and ≤16,384 bytes; category matches `^[a-z][a-z0-9_.-]{0,99}$`; severity ∈ blocking/warning/informational.<br>• **DB check:** Primary query nonblank and ≤100,000 bytes; comparison query nullable, otherwise nonblank and ≤100,000 bytes.<br>• **DB check:** Nullable result type ∈ boolean/integer/decimal/text/date/timestamp; comparison value-type ∈ none/literal/literal_list/query; comparison JSON nullable, otherwise ≤65,536 bytes.<br>• **DB check:** Operators and exact value/result/query combinations: see **W-ASSERT** below. Literal/list JSON type must match result type; integer must be integral JSON-number syntax; lists contain 1–10,000 items and homogeneous matching types.<br>• **DB check:** Date/timestamp SQL CHECK verifies JSON string type only; Python additionally parses real ISO date/timestamp values. SQL CHECK NULL behavior remains distinct from strict application schema.<br>• **App/function:** W-BASE + W-ASSERT + W-VALIDATION. Parent group resolves; active check requires active group; Tenant matches Model and System active; governed SQL validation; true ISO date/timestamp values and finite decimal literals. |

#### W-BASE — shared workflow application validation

Applies to every workflow row through its dataset or enclosing nested record, subject to the route exceptions below.

- **Exact schemas:** strict Python/Pydantic types; unknown keys forbidden; database/audit IDs are not agent-authored fields. Canonical keys are normalized using ordinary-space trim + Unicode casefold. Duplicate canonical keys are rejected. Code, name and string limits are those in the row model; portable names generally ≤255, physical names ≤400, codes ≤100. [Record base/types](/Users/maazuddinmohammed/main/projects/gds_workbench_v2/mcp_server/gds_etl_workbench/domain/modeling_records.py:29), [staged validation](/Users/maazuddinmohammed/main/projects/gds_workbench_v2/mcp_server/gds_etl_workbench/application/change_sets/model_validation.py:92).
- **Whole proposed model:** changes are overlaid on the current snapshot, then schema, locks, physical eligibility, canonical uniqueness, references and active dependencies are checked. Existing locked records cannot change. Matching locked nested supports/memberships/sources cannot change. Omitted records are retained by the upsert/authoring merge paths; omission is not an instruction to delete. [Future graph](/Users/maazuddinmohammed/main/projects/gds_workbench_v2/mcp_server/gds_etl_workbench/application/change_sets/model_validation.py:146), [nested locks](/Users/maazuddinmohammed/main/projects/gds_workbench_v2/mcp_server/gds_etl_workbench/application/change_sets/model_validation.py:1544).
- **Historical exception:** unchanged applied physical references may use the broader visible catalog. The same exception permits only lock-field changes or active→inactive lifecycle changes, including matching nested records. New or materially changed authoring must satisfy current active eligibility. Deprecated/reactivated/materially modified evidence does not automatically receive this exception. [Retention check](/Users/maazuddinmohammed/main/projects/gds_workbench_v2/mcp_server/gds_etl_workbench/application/change_sets/model_validation.py:326), [physical validation](/Users/maazuddinmohammed/main/projects/gds_workbench_v2/mcp_server/gds_etl_workbench/application/change_sets/model_validation.py:389).
- **SQL eligibility functions, consumed by application:** active Model and Model Tenant; active source-owner Tenant, Object, Connection, System, Zone; physical Attribute additionally active. Model inputs use Source/Bronze; Logical targets Silver; Dimensional targets Gold. Silver Dimensional-source Objects require active Logical Binding, active Mapping with a transformation, matching active source-System dependency and active source System; Attributes additionally need active Attribute Binding and matching active Attribute Mapping with a transformation. [Object eligibility](/Users/maazuddinmohammed/main/projects/gds_workbench_v2/database/11_workflow_eligibility.sql:78), [Attribute eligibility](/Users/maazuddinmohammed/main/projects/gds_workbench_v2/database/11_workflow_eligibility.sql:746).
- **Workflow Run FK scope:** direct-model tables bind `(workflow_run_id, model_id)` to the same Run/Model; `analysis_result` does this for inference and validation Run IDs. `model_attribute_binding`, `mapping_attribute`, `generated_code`, `generated_code_source_system` only FK the Run ID, because they derive Model via parents; `validation_check` has no Run-ID column. [Late constraints](/Users/maazuddinmohammed/main/projects/gds_workbench_v2/database/13_application_workflow_runs.sql:727).
- **Route protections:** authorization, Tenant Lock ownership, Model revision fencing, digest revalidation and idempotent apply are enforced by the governed application/SQL routes described in the report’s common Model protections. These are not universal workflow-table triggers. SQL grants allow selected runtime roles to materialize rows. [Runtime grants](/Users/maazuddinmohammed/main/projects/gds_workbench_v2/database/19_runtime_integrity.sql:1178).

#### W-PROFILE — `workflow.attribute_profile`

- **Record schema:** counts/lengths nonnegative; counts reconcile; optional blank/distinct ≤non-null; min≤max; exact Decimal precision/scale and percentage ranges. [ProfilingProfileRecord](/Users/maazuddinmohammed/main/projects/gds_workbench_v2/mcp_server/gds_etl_workbench/domain/modeling_records.py:150).
- **Governed persistence:** JSON array ≤32 MiB and 0–50,000 Profiles; every item has exactly the 16 expected keys; IDs positive integers; counters/lengths integer-shaped or permitted NULL; decimal metrics numbers or NULL; digest 64 lowercase hex; Attribute IDs unique. [Payload checks](/Users/maazuddinmohammed/main/projects/gds_workbench_v2/database/14_application_workflow_execution.sql:1843).
- **Exact percentages:** populated=100×non-null/rows; null=100×null/rows; duplicates=100×(non-null−distinct)/non-null; blank=100×blank/non-null; distinct=100×distinct/non-null. Round to four decimals; zero denominators yield 0; unavailable blank/distinct metrics yield NULL where appropriate. Counts and min/max reconcile. [Metric checks](/Users/maazuddinmohammed/main/projects/gds_workbench_v2/database/14_application_workflow_execution.sql:1987).
- **Persistence context:** Run exists, caller authorized and owns Run, profiling workflow running, expected Model revision current, immutable selection complete and still eligible, submitted Attributes exactly cover selected eligible Attributes, supplied source digests equal recomputed current source context. [Context/coverage checks](/Users/maazuddinmohammed/main/projects/gds_workbench_v2/database/14_application_workflow_execution.sql:2056).

#### W-ANALYSIS — `workflow.analysis_result`

- **Evidence arithmetic in Python:** source and target distinct≤non-null; distinct=0 iff corresponding non-null=0; missing-target≤source distinct; unused-target≤target distinct; matched distinct counts equal (`source distinct−missing = target distinct−unused`); duplicate-target=`target non-null−target distinct`. Outcome: either side empty→inconclusive; otherwise no missing targets and no duplicate targets→supported; otherwise unsupported. [Evidence validator](/Users/maazuddinmohammed/main/projects/gds_workbench_v2/mcp_server/gds_etl_workbench/domain/modeling_records.py:194).
- **Inference candidate:** ≤20,000 relationships; immutable unique selected Attributes 1–50,000; both endpoints in selection unless an unchanged applied relationship is retained; duplicate identity with conflicting confidence/basis rejected; locked applied relationship cannot change; inference may author inference fields only, preserving existing validation/lifecycle data through merge. [Inference validator](/Users/maazuddinmohammed/main/projects/gds_workbench_v2/web_app/backend/gds_workbench_api/features/analysis/candidate.py:40).
- **SQL persistence:** exact 12-key item shape; JSON array ≤32 MiB and 0–50,000 Results; positive BIGINT result IDs, unique IDs, nonnegative BIGINT counts, valid policy version/digests/outcome. Checks count bounds, zero/nonzero equivalence, duplicate-target formula and outcome. **Difference:** the matched-distinct equality above is enforced in Python; it is not repeated in this SQL persistence function. [SQL payload/evidence checks](/Users/maazuddinmohammed/main/projects/gds_workbench_v2/database/14_application_workflow_execution.sql:1326).
- **Persistence context:** authorization and actor identity match, analysis-validation Run running, expected revision current, exact current eligible result-ID coverage and recomputed source-context digests. Locked/inactive/unselected rows do not become arbitrary write targets. [SQL context checks](/Users/maazuddinmohammed/main/projects/gds_workbench_v2/database/14_application_workflow_execution.sql:1600).

#### W-CONCEPTUAL — Objects, Relationships, Support

- Strict row contracts; aliases unique after normalization; source supports unique by typed natural key. Relationships require different normalized endpoint names; references must resolve and active Relationships require active endpoint Objects. [Row schemas](/Users/maazuddinmohammed/main/projects/gds_workbench_v2/mcp_server/gds_etl_workbench/domain/modeling_records.py:403), [graph validation](/Users/maazuddinmohammed/main/projects/gds_workbench_v2/mcp_server/gds_etl_workbench/application/change_sets/model_validation.py:795).
- Assertion supports must exist and declare conceptual as an applicable layer. New physical supports must be active Model inputs; unchanged retained evidence has the W-BASE exception. [Physical references](/Users/maazuddinmohammed/main/projects/gds_workbench_v2/mcp_server/gds_etl_workbench/application/change_sets/model_validation.py:477), [assertion layer check](/Users/maazuddinmohammed/main/projects/gds_workbench_v2/mcp_server/gds_etl_workbench/application/change_sets/model_validation.py:1308).
- Web authoring: total Objects+Relationships≤20,000; selected Objects 1–50,000 and unique; assertion keys/applied keys unique; physical support limited to immutable Run selection and assertion supports to immutable context. Agent cannot set top-level/support locks; applied locks preserved and changed locked values rejected; omitted existing content merged back. [Candidate validator](/Users/maazuddinmohammed/main/projects/gds_workbench_v2/web_app/backend/gds_workbench_api/features/conceptual/candidate.py:34).

#### W-LOGICAL — all seven Logical tables

- Strict row contracts repeat SQL semantics; normalized nested membership and source keys unique. Every Submodel, Entity and Relationship endpoint resolves; active Attribute requires active parent Entity; active Relationship requires active Entities and Attributes. Assertion sources must exist and apply to logical layer. New physical sources must come from active Model inputs. Physical Attribute source materialization requires the Entity’s corresponding physical Object-source row. [Row schemas](/Users/maazuddinmohammed/main/projects/gds_workbench_v2/mcp_server/gds_etl_workbench/domain/modeling_records.py:497), [modeled-layer references](/Users/maazuddinmohammed/main/projects/gds_workbench_v2/mcp_server/gds_etl_workbench/application/change_sets/model_validation.py:1249), [physical source witness](/Users/maazuddinmohammed/main/projects/gds_workbench_v2/mcp_server/gds_etl_workbench/application/change_sets/model_apply.py:2184).
- Web authoring: all four top-level arrays together≤20,000; selected Objects 1–50,000; selected Attributes≤50,000; selected/applied/assertion keys unique. Changed physical sources must be in immutable Run selection; assertions in immutable Run context. Agent cannot set any top-level/nested locks or author audit columns. Existing records/nested memberships/sources are merged; locked changes rejected. [Candidate validator](/Users/maazuddinmohammed/main/projects/gds_workbench_v2/web_app/backend/gds_workbench_api/features/logical/candidate.py:43).
- Backend audit-column projection: optional policy has schema version 1.0 and 1–32 unique normalized names; semantic name≤255, type≤100, optional definition≤2,000, strict Boolean nullability. Applied to every active Entity after business ordinals; generated columns are active audit columns with no source/key flags. Existing name collision is accepted only for matching audit/type/nullability and no sources; locked changes rejected. [Policy checks/projection](/Users/maazuddinmohammed/main/projects/gds_workbench_v2/web_app/backend/gds_workbench_api/features/logical/policy.py:40).

#### W-GOLD — all seven Dimensional tables

- Strict row contracts repeat SQL semantics and close nullable CHECK gaps: fact type required iff Entity is a fact; measure additivity/default aggregation required; semi/non-additive measures need aggregation basis. Membership/source keys unique. Every Submodel/Entity/Relationship endpoint resolves; active Attributes and Relationships require active parents/endpoints. Assertion sources must apply to dimensional layer. New physical sources require active Silver Logical contributions. [Records](/Users/maazuddinmohammed/main/projects/gds_workbench_v2/mcp_server/gds_etl_workbench/domain/modeling_records.py:700), [physical checks](/Users/maazuddinmohammed/main/projects/gds_workbench_v2/mcp_server/gds_etl_workbench/application/change_sets/model_validation.py:508).
- Web authoring: total top-level records 1–20,000; selected Silver Objects 1–50,000; Attributes≤50,000; natural keys unique; changed physical sources limited to immutable selection; assertions limited to immutable context. Agent cannot set top-level/nested locks or author technical/audit/surrogate/foreign-key columns. Existing/omitted content merged and locked changes rejected. [Candidate validator](/Users/maazuddinmohammed/main/projects/gds_workbench_v2/web_app/backend/gds_workbench_api/features/dimensional/candidate.py:43).
- Complete Gold naming + technical + audit policy group is required before authoring. Strict policy parsing validates supported schema version/field types, names, placeholder syntax, audit name uniqueness and Type-2 nullability/name uniqueness. Policy projection generates dimension surrogate keys, Type-2 columns for active historized business Attributes, and audit columns; normalized generated-name collisions or inconsistent existing columns fail. [Gold policy](/Users/maazuddinmohammed/main/projects/gds_workbench_v2/web_app/backend/gds_workbench_api/features/dimensional/policy.py:46).
- Fact/Bridge Relationships must use the from endpoint and point to a Dimension with exactly one active technical surrogate key. Backend generates FK name/type/definition; nullability follows relationship optionality; duplicate generated FK names fail. Final Relationship endpoints are rebound to generated FK/surrogate columns. Generated policy names≤255 and definitions≤2,000; conflicting existing role/type/nullability/key-role/source fields or changes to locked columns fail. Technical/audit ordinals follow business columns. [FK projection](/Users/maazuddinmohammed/main/projects/gds_workbench_v2/web_app/backend/gds_workbench_api/features/dimensional/policy.py:313), [column conflict checks](/Users/maazuddinmohammed/main/projects/gds_workbench_v2/web_app/backend/gds_workbench_api/features/dimensional/policy.py:578).

#### W-BINDING — Object and Attribute Bindings

- Modeled Entity/Attribute must exist in the stated logical/dimensional layer. New physical targets must be eligible Silver/Gold targets respectively; historical references follow W-BASE. Active Object Binding needs active modeled Entity; active Attribute Binding needs active modeled Attribute and active Object Binding. [Binding/reference checks](/Users/maazuddinmohammed/main/projects/gds_workbench_v2/mcp_server/gds_etl_workbench/application/change_sets/model_validation.py:649), [active dependencies](/Users/maazuddinmohammed/main/projects/gds_workbench_v2/mcp_server/gds_etl_workbench/application/change_sets/model_validation.py:967).
- Active physical Object may bind only one modeled Entity; active physical Attribute may bind only one modeled Attribute. Every active Object Binding needs exactly one active Binding for **every active modeled Attribute and every active physical Attribute**, with no extras. [Full coverage](/Users/maazuddinmohammed/main/projects/gds_workbench_v2/mcp_server/gds_etl_workbench/application/change_sets/model_validation.py:749).
- Attribute’s physical target is derived from its parent Object Binding; materialization resolves modeled Attribute within that parent Entity/layer and physical Attribute within the bound Object. [Materializer](/Users/maazuddinmohammed/main/projects/gds_workbench_v2/mcp_server/gds_etl_workbench/application/change_sets/model_apply.py:2443).

#### W-MAPPING — dependencies, Mapping Objects and Mapping Attributes

- Shared graph: referenced source System active; Object Binding exists; layer/System dependency exists; Attribute Mapping’s Object and Attribute Binding resolve consistently. Active Object Mapping needs active Binding + dependency + non-NULL transformation. Active Attribute Mapping needs active Object Mapping + Attribute Binding + non-NULL transformation. Each active source-System Mapping must cover every active bound target Attribute. New authoring also requires eligible current physical targets. [Graph checks](/Users/maazuddinmohammed/main/projects/gds_workbench_v2/mcp_server/gds_etl_workbench/application/change_sets/model_validation.py:569), [references](/Users/maazuddinmohammed/main/projects/gds_workbench_v2/mcp_server/gds_etl_workbench/application/change_sets/model_validation.py:855), [active coverage](/Users/maazuddinmohammed/main/projects/gds_workbench_v2/mcp_server/gds_etl_workbench/application/change_sets/model_validation.py:988).
- Route readiness: immutable Run identity/revision/correlation/pair/layer/route/templates match; selected source System/dependency active; dependency graph references valid, selected System/order unchanged, edges strictly earlier→later wave, no cycle. Target active and in expected Silver/Gold zone with active scope/Tenant/System/Connection and global-data-store connection; bound target Attributes active. Sources nonempty, active and complete, in Source/Bronze for Logical→Silver or Silver for Dimensional→Gold; target modeled Entity active and active Attribute coverage exact. [Readiness](/Users/maazuddinmohammed/main/projects/gds_workbench_v2/web_app/backend/gds_workbench_api/features/mapping/readiness.py:97).
- Output templates must exist, be active, match mapping_object/mapping_attribute target type and frozen schema digest. `build` applies only when Mapping is unauthored; `extend` only when already authored. Locked authored transformations preserved; locked incomplete transformations block execution. [Readiness continuation](/Users/maazuddinmohammed/main/projects/gds_workbench_v2/web_app/backend/gds_workbench_api/features/mapping/readiness.py:177).
- Candidate schema version 1.0; transformation-only fields; nonempty JSON objects; object≤524,288 and Attribute≤65,536 canonical UTF-8 JSON bytes; no NaN/Infinity serialization; Attribute array≤5,000 and names unique case-insensitively. Exactly the actionable Object transformation and every actionable bound Attribute once; backend derives IDs/lifecycle/lock/template selections. Selected template JSON Schema is checked by the shared candidate repair validator. [Candidate contract](/Users/maazuddinmohammed/main/projects/gds_workbench_v2/web_app/backend/gds_workbench_api/features/mapping/contracts.py:12), [reconciliation](/Users/maazuddinmohammed/main/projects/gds_workbench_v2/web_app/backend/gds_workbench_api/features/mapping/reconciliation.py:24), [schema enforcement](/Users/maazuddinmohammed/main/projects/gds_workbench_v2/web_app/backend/gds_workbench_api/features/workflows/authoring/repair.py:528).
- On apply, output template code is resolved using the expected target type; generated Mapping data use server-derived identities and current authoring policy. [Template resolution](/Users/maazuddinmohammed/main/projects/gds_workbench_v2/mcp_server/gds_etl_workbench/application/change_sets/model_apply.py:2526).

#### W-CODE — Generated Code and source-System assignments

- Portable record: filename length≤400, nonblank, trim-stable, no directory separators, not dot/dot-dot; nonblank content rejects C0 controls except tab/newline/CR; artifact type exactly SQL/Python-file/Python-notebook variants. Active artifact needs active Object Binding. Source-System assignment must resolve to an artifact and active System; active assignment needs active Code and corresponding active Mapping. [Record checks](/Users/maazuddinmohammed/main/projects/gds_workbench_v2/mcp_server/gds_etl_workbench/domain/modeling_records.py:960), [graph checks](/Users/maazuddinmohammed/main/projects/gds_workbench_v2/mcp_server/gds_etl_workbench/application/change_sets/model_validation.py:1063).
- During Code authoring, each mapped source System must have exactly one active artifact assignment per Entity; duplicates always fail. Upstream Mapping may outgrow unchanged Code, leaving stale Code until reauthored; the human lifecycle-review route can retain stale Code without requiring missing assignments. [Coverage exception](/Users/maazuddinmohammed/main/projects/gds_workbench_v2/mcp_server/gds_etl_workbench/application/change_sets/model_validation.py:1091).
- Web candidate: 1–50,000 frozen unique targets; 1–50,000 artifacts; each target covered; no unknown target refs; filename unique case-insensitively per target. Source-code arrays≤200, nonblank and unique; support artifacts assign no System; each transformation artifact assigns ≥1 System; transformation artifacts collectively cover all frozen Systems exactly once and at least one transformation exists per target. [Candidate checks](/Users/maazuddinmohammed/main/projects/gds_workbench_v2/web_app/backend/gds_workbench_api/features/code_generation/candidate.py:33).
- Generated SQL must be nonblank, no Markdown fences/unsafe controls, and parse in Databricks dialect into executable SQL statements. This validates **stored generated artifacts**; permitted parse classes include query, DDL, DML, command/use/set/transaction. It is not the read-only Databricks execution allowlist. Candidate envelope limits apply separately. [SQL parser](/Users/maazuddinmohammed/main/projects/gds_workbench_v2/web_app/backend/gds_workbench_api/features/code_generation/candidate.py:285).
- Materializer requires complete active Mapping context for the binding, computes/stores current input digest server-side, and resolves assignments against the artifact. [Apply currentness](/Users/maazuddinmohammed/main/projects/gds_workbench_v2/mcp_server/gds_etl_workbench/application/change_sets/model_apply.py:2579), [context SQL function](/Users/maazuddinmohammed/main/projects/gds_workbench_v2/database/11_workflow_eligibility.sql:331).

#### W-ASSERT — Validation Check operator matrix

`A` is `validation_query_sql`; `B` is `validation_comparison_query_sql`; `value` is `validation_comparison_value`. A is always required/nonblank. This matrix summarizes the intended SQL combinations and the strict application behavior.

| Operator | Result type | Value type | Value | B |
|---|---|---|---|---|
| executes_successfully | NULL | none | NULL | NULL |
| is_null / is_not_null | Required supported type | none | NULL | NULL |
| is_true / is_false | boolean | none | NULL | NULL |
| equal / not_equal | Required supported type | literal **or** query | Required literal **or** NULL for query | NULL for literal **or** required query |
| greater_than / greater_than_or_equal / less_than / less_than_or_equal | integer / decimal / date / timestamp | literal **or** query | Required literal **or** NULL for query | NULL for literal **or** required query |
| in / not_in | Required supported type | literal_list | 1–10,000 matching values | NULL |

- Literal/list type matching: Boolean→JSON Boolean; integer→JSON integral number (Python bool is not accepted as integer); decimal→number (Python rejects non-finite floats); text→string; date/timestamp→string plus Python ISO parsing. No mixed-type list. [SQL checks](/Users/maazuddinmohammed/main/projects/gds_workbench_v2/database/10_workflow_code_validation.sql:242), [Python checks](/Users/maazuddinmohammed/main/projects/gds_workbench_v2/mcp_server/gds_etl_workbench/domain/modeling_records.py:1022).
- SQL’s nullable CHECK expressions can evaluate to NULL, which passes PostgreSQL CHECK. The exact application schema validates the full intended shape; do not treat every “required supported type” in this matrix as a standalone SQL NOT NULL declaration.

#### W-VALIDATION — Validation Groups and Checks

- Shared graph: Tenant code must own Model; System active; Check’s group must exist; active Check requires active group; active group needs active Mapping for its source System. Active query A and optional query B must pass governed read-only Databricks SQL validation; all non-execution-only A queries and every B query must end in a row-returning statement. [Graph checks](/Users/maazuddinmohammed/main/projects/gds_workbench_v2/mcp_server/gds_etl_workbench/application/change_sets/model_validation.py:613), [active parent checks](/Users/maazuddinmohammed/main/projects/gds_workbench_v2/mcp_server/gds_etl_workbench/application/change_sets/model_validation.py:1110), [SQL validation call](/Users/maazuddinmohammed/main/projects/gds_workbench_v2/mcp_server/gds_etl_workbench/application/change_sets/model_validation.py:1220).
- Per-System candidate: exact frozen System ref; strict extra-forbidden schema;≤500 groups,≤1,000 checks/group,≤10,000 checks/System,≤16 MiB canonical candidate JSON; normalized group names unique per System and Check names unique per group; W-ASSERT, query/description/value limits and governed SQL checks apply. Tenant/System/status/lock ownership derived by backend. [Candidate checks](/Users/maazuddinmohammed/main/projects/gds_workbench_v2/web_app/backend/gds_workbench_api/features/validation/candidate.py:28).
- Reconciliation requires exactly one candidate for every frozen System and unique current/desired keys. Existing locked groups/checks preserved; omitted unlocked active groups/checks become inactive. Only effective changes staged. [Reconciliation](/Users/maazuddinmohammed/main/projects/gds_workbench_v2/web_app/backend/gds_workbench_api/features/validation/candidate.py:371).
- Apply requires complete active Mapping for the System; server derives Mapping/code-context digests from current resolved target/Code context; invalid/incomplete target/source context fails. [Context materialization](/Users/maazuddinmohammed/main/projects/gds_workbench_v2/mcp_server/gds_etl_workbench/application/change_sets/model_apply.py:2690).


<a id="sql-inventory"></a>


## 4. Exact SQL inventory — columns, constraints and unique indexes

This source-derived appendix makes every SQL type, length, precision, required column, default, CHECK, foreign key, unique constraint and unique index inspectable. Expand a table to read its declarations. Later ALTER statements are included after CREATE TABLE. Ordinary performance indexes are omitted because they do not validate data. Trigger and application behavior is described in Section 3.

PostgreSQL CHECK rejects FALSE, but permits UNKNOWN (usually caused by NULL). A nullable foreign-key column does not require a referenced row when its key is null. `reference.is_nonblank(x)` is exactly `x IS NOT NULL AND length(btrim(x)) > 0`: trims spaces, not all whitespace. Application `\S`/`.strip()` checks can be stricter. `lower(btrim(x))` indexes normalize spaces and case, not Unicode casefolding. A DEFAULT is an insert fallback, not a rule forcing that value or updating timestamps later.

### core: exact declarations

<details>
<summary><code>core.project</code></summary>


[02_core.sql:5](/Users/maazuddinmohammed/main/projects/gds_workbench_v2/database/02_core.sql:5)

```sql
CREATE TABLE core.project (
    project_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    project_code VARCHAR(100) NOT NULL,
    project_name VARCHAR(200) NOT NULL,
    project_description TEXT,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_time TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    created_by VARCHAR(255) NOT NULL DEFAULT CURRENT_USER,
    updated_time TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_by VARCHAR(255) NOT NULL DEFAULT CURRENT_USER,
    CONSTRAINT ck_project_code CHECK (reference.is_nonblank(project_code)),
    CONSTRAINT ck_project_name CHECK (reference.is_nonblank(project_name))
);
```


[02_core.sql:498](/Users/maazuddinmohammed/main/projects/gds_workbench_v2/database/02_core.sql:498)

```sql
CREATE UNIQUE INDEX ux_project_code_ci
    ON core.project (lower(btrim(project_code)));
```


</details>

<details>
<summary><code>core.tenant</code></summary>


[02_core.sql:19](/Users/maazuddinmohammed/main/projects/gds_workbench_v2/database/02_core.sql:19)

```sql
CREATE TABLE core.tenant (
    tenant_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    project_id BIGINT NOT NULL,
    tenant_code VARCHAR(100) NOT NULL,
    tenant_name VARCHAR(200) NOT NULL,
    tenant_description TEXT,
    tenant_catalog VARCHAR(255) NOT NULL,
    gds_admin_catalog VARCHAR(255) NOT NULL,
    gds_connection_id BIGINT,
    tenant_visibility VARCHAR(20) NOT NULL DEFAULT 'private',
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_time TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    created_by VARCHAR(255) NOT NULL DEFAULT CURRENT_USER,
    updated_time TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_by VARCHAR(255) NOT NULL DEFAULT CURRENT_USER,
    CONSTRAINT fk_tenant_project FOREIGN KEY (project_id)
        REFERENCES core.project (project_id) ON DELETE NO ACTION,
    CONSTRAINT ck_tenant_code CHECK (reference.is_nonblank(tenant_code)),
    CONSTRAINT ck_tenant_name CHECK (reference.is_nonblank(tenant_name)),
    CONSTRAINT ck_tenant_visibility CHECK (
        tenant_visibility IN ('global', 'private')
    )
);
```


[02_core.sql:500](/Users/maazuddinmohammed/main/projects/gds_workbench_v2/database/02_core.sql:500)

```sql
CREATE UNIQUE INDEX ux_tenant_code_ci
    ON core.tenant (lower(btrim(tenant_code)));
```


</details>

<details>
<summary><code>core.system</code></summary>


[02_core.sql:43](/Users/maazuddinmohammed/main/projects/gds_workbench_v2/database/02_core.sql:43)

```sql
CREATE TABLE core.system (
    system_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    system_code VARCHAR(100) NOT NULL,
    system_name VARCHAR(200) NOT NULL,
    system_description TEXT,
    system_type_id BIGINT NOT NULL,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_time TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    created_by VARCHAR(255) NOT NULL DEFAULT CURRENT_USER,
    updated_time TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_by VARCHAR(255) NOT NULL DEFAULT CURRENT_USER,
    CONSTRAINT fk_system_system_type FOREIGN KEY (system_type_id)
        REFERENCES reference.system_type (system_type_id) ON DELETE NO ACTION,
    CONSTRAINT ck_system_code CHECK (reference.is_nonblank(system_code)),
    CONSTRAINT ck_system_name CHECK (reference.is_nonblank(system_name))
);
```


[02_core.sql:502](/Users/maazuddinmohammed/main/projects/gds_workbench_v2/database/02_core.sql:502)

```sql
CREATE UNIQUE INDEX ux_system_code_ci
    ON core.system (lower(btrim(system_code)));
```


</details>

<details>
<summary><code>core.system_notebook_path</code></summary>


[02_core.sql:60](/Users/maazuddinmohammed/main/projects/gds_workbench_v2/database/02_core.sql:60)

```sql
CREATE TABLE core.system_notebook_path (
    system_notebook_path_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    system_id BIGINT NOT NULL,
    system_notebook_id BIGINT NOT NULL,
    system_notebook_path TEXT NOT NULL,
    created_time TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    created_by VARCHAR(255) NOT NULL DEFAULT CURRENT_USER,
    updated_time TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_by VARCHAR(255) NOT NULL DEFAULT CURRENT_USER,
    CONSTRAINT fk_system_notebook_path_system FOREIGN KEY (system_id)
        REFERENCES core.system (system_id) ON DELETE NO ACTION,
    CONSTRAINT fk_system_notebook_path_notebook FOREIGN KEY (system_notebook_id)
        REFERENCES reference.system_notebook (system_notebook_id) ON DELETE NO ACTION,
    CONSTRAINT uq_system_notebook_path
        UNIQUE (system_id, system_notebook_id),
    CONSTRAINT ck_system_notebook_path CHECK (
        reference.is_nonblank(system_notebook_path)
    )
);
```


</details>

<details>
<summary><code>core.connection</code></summary>


[02_core.sql:80](/Users/maazuddinmohammed/main/projects/gds_workbench_v2/database/02_core.sql:80)

```sql
CREATE TABLE core.connection (
    connection_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    tenant_id BIGINT NOT NULL,
    system_id BIGINT NOT NULL,
    connection_code VARCHAR(100) NOT NULL,
    connection_name VARCHAR(200) NOT NULL,
    connection_description TEXT,
    connection_type_id BIGINT NOT NULL,
    has_foreign_catalog BOOLEAN NOT NULL DEFAULT FALSE,
    foreign_catalog VARCHAR(255),
    is_global_data_store BOOLEAN NOT NULL DEFAULT FALSE,
    test_initial_batch_id BIGINT,
    test_incremental_batch_ids BIGINT[],
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_time TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    created_by VARCHAR(255) NOT NULL DEFAULT CURRENT_USER,
    updated_time TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_by VARCHAR(255) NOT NULL DEFAULT CURRENT_USER,
    CONSTRAINT fk_connection_tenant FOREIGN KEY (tenant_id)
        REFERENCES core.tenant (tenant_id) ON DELETE NO ACTION,
    CONSTRAINT fk_connection_system FOREIGN KEY (system_id)
        REFERENCES core.system (system_id) ON DELETE NO ACTION,
    CONSTRAINT fk_connection_type FOREIGN KEY (connection_type_id)
        REFERENCES reference.connection_type (connection_type_id) ON DELETE NO ACTION,
    CONSTRAINT uq_connection_id_tenant UNIQUE (connection_id, tenant_id),
    CONSTRAINT ck_connection_code CHECK (reference.is_nonblank(connection_code)),
    CONSTRAINT ck_connection_name CHECK (reference.is_nonblank(connection_name))
);
```


[02_core.sql:504](/Users/maazuddinmohammed/main/projects/gds_workbench_v2/database/02_core.sql:504)

```sql
CREATE UNIQUE INDEX ux_connection_system_tenant_code_ci
    ON core.connection (
        system_id,
        tenant_id,
        lower(btrim(connection_code))
    );
```


</details>

<details>
<summary><code>core.connection_location</code></summary>


[02_core.sql:109](/Users/maazuddinmohammed/main/projects/gds_workbench_v2/database/02_core.sql:109)

```sql
CREATE TABLE core.connection_location (
    connection_location_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    connection_id BIGINT NOT NULL,
    location_type_id BIGINT NOT NULL,
    environment_id BIGINT NOT NULL,
    connection_location_storage_account VARCHAR(255) NOT NULL,
    connection_location_secret_reference TEXT NOT NULL,
    connection_location_container VARCHAR(255) NOT NULL,
    connection_location_path TEXT NOT NULL,
    created_time TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    created_by VARCHAR(255) NOT NULL DEFAULT CURRENT_USER,
    updated_time TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_by VARCHAR(255) NOT NULL DEFAULT CURRENT_USER,
    CONSTRAINT fk_connection_location_connection FOREIGN KEY (connection_id)
        REFERENCES core.connection (connection_id) ON DELETE NO ACTION,
    CONSTRAINT fk_connection_location_type FOREIGN KEY (location_type_id)
        REFERENCES reference.location_type (location_type_id) ON DELETE NO ACTION,
    CONSTRAINT fk_connection_location_environment FOREIGN KEY (environment_id)
        REFERENCES reference.environment (environment_id) ON DELETE NO ACTION,
    CONSTRAINT uq_connection_location
        UNIQUE (connection_id, location_type_id, environment_id),
    CONSTRAINT ck_connection_location_storage_account CHECK (
        reference.is_nonblank(connection_location_storage_account)
    ),
    CONSTRAINT ck_connection_location_secret_reference CHECK (
        reference.is_nonblank(connection_location_secret_reference)
    ),
    CONSTRAINT ck_connection_location_container CHECK (
        reference.is_nonblank(connection_location_container)
    ),
    CONSTRAINT ck_connection_location_path CHECK (
        reference.is_nonblank(connection_location_path)
    )
);
```


</details>

<details>
<summary><code>core.connection_value</code></summary>


[02_core.sql:144](/Users/maazuddinmohammed/main/projects/gds_workbench_v2/database/02_core.sql:144)

```sql
CREATE TABLE core.connection_value (
    connection_value_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    environment_id BIGINT NOT NULL,
    connection_id BIGINT NOT NULL,
    connection_parameter_id BIGINT NOT NULL,
    connection_value TEXT,
    created_time TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    created_by VARCHAR(255) NOT NULL DEFAULT CURRENT_USER,
    updated_time TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_by VARCHAR(255) NOT NULL DEFAULT CURRENT_USER,
    CONSTRAINT fk_connection_value_connection FOREIGN KEY (connection_id)
        REFERENCES core.connection (connection_id) ON DELETE NO ACTION,
    CONSTRAINT fk_connection_value_parameter FOREIGN KEY (connection_parameter_id)
        REFERENCES reference.connection_parameter (connection_parameter_id)
        ON DELETE NO ACTION,
    CONSTRAINT uq_connection_value_parameter
        UNIQUE (connection_id, connection_parameter_id, environment_id),
    CONSTRAINT ck_connection_literal_value CHECK (
        connection_value IS NULL OR reference.is_nonblank(connection_value)
    )
);
```


</details>

<details>
<summary><code>core.object</code></summary>


[02_core.sql:166](/Users/maazuddinmohammed/main/projects/gds_workbench_v2/database/02_core.sql:166)

```sql
CREATE TABLE core.object (
    object_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    connection_id BIGINT NOT NULL,
    source_tenant_id BIGINT NOT NULL,
    object_schema VARCHAR(400) NOT NULL,
    object_name VARCHAR(400) NOT NULL,
    fc_object_schema VARCHAR(400),
    fc_object_name VARCHAR(400),
    object_transformation TEXT,
    object_description TEXT,
    batch_attribute_name VARCHAR(400),
    object_type_id BIGINT NOT NULL,
    zone_id BIGINT NOT NULL,
    is_locked BOOLEAN NOT NULL DEFAULT FALSE,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_time TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    created_by VARCHAR(255) NOT NULL DEFAULT CURRENT_USER,
    updated_time TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_by VARCHAR(255) NOT NULL DEFAULT CURRENT_USER,
    CONSTRAINT fk_object_connection FOREIGN KEY (connection_id)
        REFERENCES core.connection (connection_id) ON DELETE NO ACTION,
    CONSTRAINT fk_object_source_tenant FOREIGN KEY (source_tenant_id)
        REFERENCES core.tenant (tenant_id) ON DELETE NO ACTION,
    CONSTRAINT fk_object_type FOREIGN KEY (object_type_id)
        REFERENCES reference.object_type (object_type_id) ON DELETE NO ACTION,
    CONSTRAINT fk_object_zone FOREIGN KEY (zone_id)
        REFERENCES reference.zone (zone_id) ON DELETE NO ACTION,
    CONSTRAINT uq_object_id_connection UNIQUE (object_id, connection_id),
    CONSTRAINT uq_object_id_zone UNIQUE (object_id, zone_id),
    CONSTRAINT ck_object_schema CHECK (reference.is_nonblank(object_schema)),
    CONSTRAINT ck_object_name CHECK (reference.is_nonblank(object_name))
);
```


[02_core.sql:510](/Users/maazuddinmohammed/main/projects/gds_workbench_v2/database/02_core.sql:510)

```sql
CREATE UNIQUE INDEX ux_object_connection_schema_name_ci
    ON core.object (
        connection_id,
        lower(btrim(object_schema)),
        lower(btrim(object_name))
    );
```


</details>

<details>
<summary><code>core.attribute</code></summary>


[02_core.sql:199](/Users/maazuddinmohammed/main/projects/gds_workbench_v2/database/02_core.sql:199)

```sql
CREATE TABLE core.attribute (
    attribute_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    object_id BIGINT NOT NULL,
    attribute_name VARCHAR(400) NOT NULL,
    fc_attribute_name VARCHAR(400),
    attribute_ordinal_position INTEGER NOT NULL,
    attribute_description TEXT,
    attribute_data_type VARCHAR(100) NOT NULL,
    attribute_inferred_data_type VARCHAR(100),
    attribute_nullability BOOLEAN NOT NULL DEFAULT TRUE,
    attribute_custom_code TEXT,
    business_glossary_id BIGINT,
    is_surrogate_key BOOLEAN NOT NULL DEFAULT FALSE,
    is_natural_key BOOLEAN NOT NULL DEFAULT FALSE,
    is_meta_data BOOLEAN NOT NULL DEFAULT FALSE,
    is_masking_required BOOLEAN NOT NULL DEFAULT FALSE,
    is_mapped BOOLEAN NOT NULL DEFAULT FALSE,
    is_purge BOOLEAN NOT NULL DEFAULT FALSE,
    is_locked BOOLEAN NOT NULL DEFAULT FALSE,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_time TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    created_by VARCHAR(255) NOT NULL DEFAULT CURRENT_USER,
    updated_time TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_by VARCHAR(255) NOT NULL DEFAULT CURRENT_USER,
    CONSTRAINT fk_attribute_object FOREIGN KEY (object_id)
        REFERENCES core.object (object_id) ON DELETE NO ACTION,
    CONSTRAINT uq_attribute_object_ordinal
        UNIQUE (object_id, attribute_ordinal_position)
        DEFERRABLE INITIALLY IMMEDIATE,
    CONSTRAINT uq_attribute_id_object UNIQUE (attribute_id, object_id),
    CONSTRAINT ck_attribute_name CHECK (reference.is_nonblank(attribute_name)),
    CONSTRAINT ck_attribute_ordinal CHECK (attribute_ordinal_position > 0),
    CONSTRAINT ck_attribute_inferred_data_type CHECK (
        attribute_inferred_data_type IS NULL
        OR reference.is_nonblank(attribute_inferred_data_type)
    )
);
```


[02_core.sql:516](/Users/maazuddinmohammed/main/projects/gds_workbench_v2/database/02_core.sql:516)

```sql
CREATE UNIQUE INDEX ux_attribute_object_name_ci
    ON core.attribute (object_id, lower(btrim(attribute_name)));
```


</details>

<details>
<summary><code>core.ingestion_object_mapping</code></summary>


[02_core.sql:237](/Users/maazuddinmohammed/main/projects/gds_workbench_v2/database/02_core.sql:237)

```sql
CREATE TABLE core.ingestion_object_mapping (
    ingestion_object_mapping_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    source_object_id BIGINT NOT NULL,
    target_object_id BIGINT NOT NULL,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_time TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    created_by VARCHAR(255) NOT NULL DEFAULT CURRENT_USER,
    updated_time TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_by VARCHAR(255) NOT NULL DEFAULT CURRENT_USER,
    CONSTRAINT fk_ingestion_source_object FOREIGN KEY (source_object_id)
        REFERENCES core.object (object_id) ON DELETE NO ACTION,
    CONSTRAINT fk_ingestion_target_object FOREIGN KEY (target_object_id)
        REFERENCES core.object (object_id) ON DELETE NO ACTION,
    CONSTRAINT uq_ingestion_object_source_target
        UNIQUE (source_object_id, target_object_id),
    CONSTRAINT uq_ingestion_object_witness
        UNIQUE (
            ingestion_object_mapping_id,
            source_object_id,
            target_object_id
        ),
    CONSTRAINT ck_ingestion_objects_different CHECK (
        source_object_id <> target_object_id
    )
);
```


</details>

<details>
<summary><code>core.ingestion_attribute_mapping</code></summary>


[02_core.sql:263](/Users/maazuddinmohammed/main/projects/gds_workbench_v2/database/02_core.sql:263)

```sql
CREATE TABLE core.ingestion_attribute_mapping (
    ingestion_attribute_mapping_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    ingestion_object_mapping_id BIGINT NOT NULL,
    source_object_id BIGINT NOT NULL,
    target_object_id BIGINT NOT NULL,
    source_attribute_id BIGINT NOT NULL,
    target_attribute_id BIGINT NOT NULL,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_time TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    created_by VARCHAR(255) NOT NULL DEFAULT CURRENT_USER,
    updated_time TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_by VARCHAR(255) NOT NULL DEFAULT CURRENT_USER,
    CONSTRAINT fk_ingestion_attribute_parent FOREIGN KEY (
        ingestion_object_mapping_id,
        source_object_id,
        target_object_id
    ) REFERENCES core.ingestion_object_mapping (
        ingestion_object_mapping_id,
        source_object_id,
        target_object_id
    ) ON DELETE NO ACTION,
    CONSTRAINT fk_ingestion_source_attribute FOREIGN KEY (
        source_attribute_id,
        source_object_id
    ) REFERENCES core.attribute (attribute_id, object_id) ON DELETE NO ACTION,
    CONSTRAINT fk_ingestion_target_attribute FOREIGN KEY (
        target_attribute_id,
        target_object_id
    ) REFERENCES core.attribute (attribute_id, object_id) ON DELETE NO ACTION,
    CONSTRAINT uq_ingestion_attribute_source_target
        UNIQUE (
            ingestion_object_mapping_id,
            source_attribute_id,
            target_attribute_id
        ),
    CONSTRAINT ck_ingestion_attributes_different CHECK (
        source_attribute_id <> target_attribute_id
    )
);
```


</details>

<details>
<summary><code>core.copy_group</code></summary>


[02_core.sql:303](/Users/maazuddinmohammed/main/projects/gds_workbench_v2/database/02_core.sql:303)

```sql
CREATE TABLE core.copy_group (
    copy_group_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    tenant_id BIGINT NOT NULL,
    system_id BIGINT NOT NULL,
    copy_group_name VARCHAR(200) NOT NULL,
    copy_group_description TEXT,
    is_member_group_required BOOLEAN NOT NULL DEFAULT FALSE,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_time TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    created_by VARCHAR(255) NOT NULL DEFAULT CURRENT_USER,
    updated_time TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_by VARCHAR(255) NOT NULL DEFAULT CURRENT_USER,
    CONSTRAINT fk_copy_group_tenant FOREIGN KEY (tenant_id)
        REFERENCES core.tenant (tenant_id) ON DELETE NO ACTION,
    CONSTRAINT fk_copy_group_system FOREIGN KEY (system_id)
        REFERENCES core.system (system_id) ON DELETE NO ACTION,
    CONSTRAINT uq_copy_group_scope
        UNIQUE (copy_group_id, tenant_id, system_id),
    CONSTRAINT ck_copy_group_name CHECK (
        reference.is_nonblank(copy_group_name)
    )
);
```


[02_core.sql:518](/Users/maazuddinmohammed/main/projects/gds_workbench_v2/database/02_core.sql:518)

```sql
CREATE UNIQUE INDEX ux_copy_group_name_ci
    ON core.copy_group (
        tenant_id,
        system_id,
        lower(btrim(copy_group_name))
    );
```


</details>

<details>
<summary><code>core.member_group</code></summary>


[02_core.sql:326](/Users/maazuddinmohammed/main/projects/gds_workbench_v2/database/02_core.sql:326)

```sql
CREATE TABLE core.member_group (
    member_group_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    tenant_id BIGINT NOT NULL,
    system_id BIGINT NOT NULL,
    member_group_name VARCHAR(200) NOT NULL,
    member_group_description TEXT,
    member_group_initial_load_date DATE,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_time TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    created_by VARCHAR(255) NOT NULL DEFAULT CURRENT_USER,
    updated_time TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_by VARCHAR(255) NOT NULL DEFAULT CURRENT_USER,
    CONSTRAINT fk_member_group_tenant FOREIGN KEY (tenant_id)
        REFERENCES core.tenant (tenant_id) ON DELETE NO ACTION,
    CONSTRAINT fk_member_group_system FOREIGN KEY (system_id)
        REFERENCES core.system (system_id) ON DELETE NO ACTION,
    CONSTRAINT uq_member_group_scope
        UNIQUE (member_group_id, tenant_id, system_id),
    CONSTRAINT ck_member_group_name CHECK (
        reference.is_nonblank(member_group_name)
    )
);
```


[02_core.sql:524](/Users/maazuddinmohammed/main/projects/gds_workbench_v2/database/02_core.sql:524)

```sql
CREATE UNIQUE INDEX ux_member_group_name_ci
    ON core.member_group (
        tenant_id,
        system_id,
        lower(btrim(member_group_name))
    );
```


</details>

<details>
<summary><code>core.copy_group_control</code></summary>


[02_core.sql:349](/Users/maazuddinmohammed/main/projects/gds_workbench_v2/database/02_core.sql:349)

```sql
CREATE TABLE core.copy_group_control (
    copy_group_control_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    copy_group_id BIGINT NOT NULL,
    member_group_id BIGINT,
    tenant_id BIGINT NOT NULL,
    system_id BIGINT NOT NULL,
    copy_group_control_initial_load_date DATE,
    copy_group_control_last_run_time TIMESTAMPTZ,
    copy_group_control_last_run_value TEXT,
    created_time TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    created_by VARCHAR(255) NOT NULL DEFAULT CURRENT_USER,
    updated_time TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_by VARCHAR(255) NOT NULL DEFAULT CURRENT_USER,
    CONSTRAINT fk_copy_group_control_copy_group FOREIGN KEY (
        copy_group_id,
        tenant_id,
        system_id
    ) REFERENCES core.copy_group (
        copy_group_id,
        tenant_id,
        system_id
    ) ON DELETE NO ACTION,
    CONSTRAINT fk_copy_group_control_member_group FOREIGN KEY (
        member_group_id,
        tenant_id,
        system_id
    ) REFERENCES core.member_group (
        member_group_id,
        tenant_id,
        system_id
    ) ON DELETE NO ACTION,
    CONSTRAINT uq_copy_group_control
        UNIQUE NULLS NOT DISTINCT (copy_group_id, member_group_id),
    CONSTRAINT ck_copy_group_control_last_run_value CHECK (
        copy_group_control_last_run_value IS NULL
        OR reference.is_nonblank(copy_group_control_last_run_value)
    )
);
```


</details>

<details>
<summary><code>core.copy</code></summary>


[02_core.sql:388](/Users/maazuddinmohammed/main/projects/gds_workbench_v2/database/02_core.sql:388)

```sql
CREATE TABLE core.copy (
    copy_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    copy_group_id BIGINT NOT NULL,
    ingestion_object_mapping_id BIGINT NOT NULL,
    copy_source_record_limit BIGINT,
    copy_source_record_limit_attribute VARCHAR(400),
    chunk_type_id BIGINT,
    copy_source_initial_sql_script TEXT,
    copy_source_incremental_sql_script TEXT,
    copy_source_file_name TEXT,
    copy_source_file_pattern TEXT,
    copy_source_file_delimiter VARCHAR(20),
    source_file_type_id BIGINT,
    copy_source_order INTEGER NOT NULL,
    source_data_operation_id BIGINT NOT NULL,
    target_data_operation_id BIGINT NOT NULL,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_time TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    created_by VARCHAR(255) NOT NULL DEFAULT CURRENT_USER,
    updated_time TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_by VARCHAR(255) NOT NULL DEFAULT CURRENT_USER,
    CONSTRAINT fk_copy_group FOREIGN KEY (copy_group_id)
        REFERENCES core.copy_group (copy_group_id) ON DELETE NO ACTION,
    CONSTRAINT fk_copy_ingestion_object_mapping FOREIGN KEY (
        ingestion_object_mapping_id
    ) REFERENCES core.ingestion_object_mapping (ingestion_object_mapping_id)
        ON DELETE NO ACTION,
    CONSTRAINT fk_copy_chunk_type FOREIGN KEY (chunk_type_id)
        REFERENCES reference.chunk_type (chunk_type_id) ON DELETE NO ACTION,
    CONSTRAINT fk_copy_source_file_type FOREIGN KEY (source_file_type_id)
        REFERENCES reference.file_type (file_type_id) ON DELETE NO ACTION,
    CONSTRAINT fk_copy_source_data_operation FOREIGN KEY (
        source_data_operation_id
    ) REFERENCES reference.data_operation (data_operation_id) ON DELETE NO ACTION,
    CONSTRAINT fk_copy_target_data_operation FOREIGN KEY (
        target_data_operation_id
    ) REFERENCES reference.data_operation (data_operation_id) ON DELETE NO ACTION,
    CONSTRAINT uq_copy_group_mapping
        UNIQUE (copy_group_id, ingestion_object_mapping_id),
    CONSTRAINT uq_copy_group_order
        UNIQUE (copy_group_id, copy_source_order)
        DEFERRABLE INITIALLY IMMEDIATE
);
```


</details>

<details>
<summary><code>core.process_group</code></summary>


[02_core.sql:432](/Users/maazuddinmohammed/main/projects/gds_workbench_v2/database/02_core.sql:432)

```sql
CREATE TABLE core.process_group (
    process_group_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    tenant_id BIGINT NOT NULL,
    system_id BIGINT NOT NULL,
    zone_id BIGINT NOT NULL,
    process_group_name VARCHAR(200) NOT NULL,
    process_group_description TEXT,
    copy_group_id BIGINT NOT NULL,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_time TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    created_by VARCHAR(255) NOT NULL DEFAULT CURRENT_USER,
    updated_time TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_by VARCHAR(255) NOT NULL DEFAULT CURRENT_USER,
    CONSTRAINT fk_process_group_tenant FOREIGN KEY (tenant_id)
        REFERENCES core.tenant (tenant_id) ON DELETE NO ACTION,
    CONSTRAINT fk_process_group_system FOREIGN KEY (system_id)
        REFERENCES core.system (system_id) ON DELETE NO ACTION,
    CONSTRAINT fk_process_group_zone FOREIGN KEY (zone_id)
        REFERENCES reference.zone (zone_id) ON DELETE NO ACTION,
    CONSTRAINT fk_process_group_copy_group FOREIGN KEY (
        copy_group_id,
        tenant_id,
        system_id
    ) REFERENCES core.copy_group (
        copy_group_id,
        tenant_id,
        system_id
    ) ON DELETE NO ACTION,
    CONSTRAINT ck_process_group_name CHECK (
        reference.is_nonblank(process_group_name)
    )
);
```


[02_core.sql:530](/Users/maazuddinmohammed/main/projects/gds_workbench_v2/database/02_core.sql:530)

```sql
CREATE UNIQUE INDEX ux_process_group_name_ci
    ON core.process_group (
        tenant_id,
        system_id,
        zone_id,
        lower(btrim(process_group_name))
    );
```


</details>

<details>
<summary><code>core.process</code></summary>


[02_core.sql:465](/Users/maazuddinmohammed/main/projects/gds_workbench_v2/database/02_core.sql:465)

```sql
CREATE TABLE core.process (
    process_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    connection_id BIGINT NOT NULL,
    object_id BIGINT NOT NULL,
    process_execution_order INTEGER NOT NULL,
    process_location TEXT NOT NULL,
    process_executable TEXT NOT NULL,
    process_type_id BIGINT NOT NULL,
    process_group_id BIGINT NOT NULL,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_time TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    created_by VARCHAR(255) NOT NULL DEFAULT CURRENT_USER,
    updated_time TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_by VARCHAR(255) NOT NULL DEFAULT CURRENT_USER,
    CONSTRAINT fk_process_object_connection FOREIGN KEY (
        object_id,
        connection_id
    ) REFERENCES core.object (object_id, connection_id) ON DELETE NO ACTION,
    CONSTRAINT fk_process_type FOREIGN KEY (process_type_id)
        REFERENCES reference.process_type (process_type_id) ON DELETE NO ACTION,
    CONSTRAINT fk_process_group FOREIGN KEY (process_group_id)
        REFERENCES core.process_group (process_group_id) ON DELETE NO ACTION,
    CONSTRAINT uq_process_group_order
        UNIQUE (process_group_id, process_execution_order, process_location, process_executable),
    CONSTRAINT ck_process_execution_order CHECK (process_execution_order > 0),
    CONSTRAINT ck_process_location CHECK (
        reference.is_nonblank(process_location)
    ),
    CONSTRAINT ck_process_executable CHECK (
        reference.is_nonblank(process_executable)
    )
);
```


</details>

### model: exact declarations

<details>
<summary><code>model.model</code></summary>


[04_model.sql:5](/Users/maazuddinmohammed/main/projects/gds_workbench_v2/database/04_model.sql:5)

```sql
CREATE TABLE model.model (
    model_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    tenant_id BIGINT NOT NULL,
    model_name VARCHAR(255) NOT NULL,
    model_description VARCHAR(2000),
    model_revision BIGINT NOT NULL DEFAULT 1,
    silver_model_naming_instructions TEXT,
    silver_model_audit_columns_template JSONB,
    gold_model_naming_instructions TEXT,
    gold_model_technical_columns_template JSONB,
    gold_model_audit_columns_template JSONB,
    default_agent_sdk_code VARCHAR(100),
    default_agent_provider_code VARCHAR(100),
    default_agent_model_code VARCHAR(200),
    default_reasoning_effort_code VARCHAR(50),
    default_max_turns INTEGER,
    default_validation_retry_count INTEGER,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_time TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    created_by VARCHAR(255) NOT NULL DEFAULT CURRENT_USER,
    updated_time TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_by VARCHAR(255) NOT NULL DEFAULT CURRENT_USER,
    CONSTRAINT fk_model_tenant FOREIGN KEY (tenant_id)
        REFERENCES core.tenant (tenant_id) ON DELETE NO ACTION,
    CONSTRAINT uq_model_id_tenant UNIQUE (model_id, tenant_id),
    CONSTRAINT ck_model_name CHECK (reference.is_nonblank(model_name)),
    CONSTRAINT ck_model_description CHECK (
        model_description IS NULL
        OR reference.is_nonblank(model_description)
    ),
    CONSTRAINT ck_model_revision CHECK (model_revision > 0),
    CONSTRAINT ck_model_silver_naming_instructions CHECK (
        silver_model_naming_instructions IS NULL
        OR (
            reference.is_nonblank(silver_model_naming_instructions)
            AND octet_length(silver_model_naming_instructions) <= 32768
        )
    ),
    CONSTRAINT ck_model_gold_naming_instructions CHECK (
        gold_model_naming_instructions IS NULL
        OR (
            reference.is_nonblank(gold_model_naming_instructions)
            AND octet_length(gold_model_naming_instructions) <= 32768
        )
    ),
    CONSTRAINT ck_model_default_agent_configuration CHECK (
        (
            default_agent_sdk_code IS NULL
            AND default_agent_provider_code IS NULL
            AND default_agent_model_code IS NULL
            AND default_reasoning_effort_code IS NULL
            AND default_max_turns IS NULL
            AND default_validation_retry_count IS NULL
        ) OR (
            default_agent_sdk_code IS NOT NULL
            AND default_agent_provider_code IS NOT NULL
            AND default_agent_model_code IS NOT NULL
            AND default_reasoning_effort_code IS NOT NULL
            AND default_max_turns BETWEEN 1 AND 50
            AND default_validation_retry_count BETWEEN 0 AND 5
        )
    ),
    CONSTRAINT ck_model_default_agent_codes CHECK (
        (
            default_agent_sdk_code IS NULL
            OR default_agent_sdk_code ~ '^[a-z][a-z0-9_.-]{0,99}$'
        )
        AND (
            default_agent_provider_code IS NULL
            OR default_agent_provider_code ~ '^[a-z][a-z0-9_.-]{0,99}$'
        )
        AND (
            default_agent_model_code IS NULL
            OR default_agent_model_code
                ~ '^[A-Za-z0-9][A-Za-z0-9_.:/-]{0,199}$'
        )
        AND (
            default_reasoning_effort_code IS NULL
            OR default_reasoning_effort_code ~ '^[a-z][a-z0-9_-]{0,49}$'
        )
    )
);
```


[04_model.sql:309](/Users/maazuddinmohammed/main/projects/gds_workbench_v2/database/04_model.sql:309)

```sql
CREATE UNIQUE INDEX ux_model_tenant_name_ci
    ON model.model (tenant_id, lower(btrim(model_name)));
```


</details>

<details>
<summary><code>model.model_input_scope</code></summary>


[04_model.sql:88](/Users/maazuddinmohammed/main/projects/gds_workbench_v2/database/04_model.sql:88)

```sql
CREATE TABLE model.model_input_scope (
    model_input_scope_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    model_id BIGINT NOT NULL,
    object_id BIGINT NOT NULL,
    model_input_scope_is_locked BOOLEAN NOT NULL DEFAULT FALSE,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_time TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    created_by VARCHAR(255) NOT NULL DEFAULT CURRENT_USER,
    updated_time TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_by VARCHAR(255) NOT NULL DEFAULT CURRENT_USER,
    CONSTRAINT fk_model_input_scope_model FOREIGN KEY (model_id)
        REFERENCES model.model (model_id) ON DELETE NO ACTION,
    CONSTRAINT fk_model_input_scope_object FOREIGN KEY (object_id)
        REFERENCES core.object (object_id) ON DELETE NO ACTION,
    CONSTRAINT uq_model_input_scope UNIQUE (model_id, object_id)
);
```


</details>

<details>
<summary><code>model.model_event_log</code></summary>


[04_model.sql:105](/Users/maazuddinmohammed/main/projects/gds_workbench_v2/database/04_model.sql:105)

```sql
CREATE TABLE model.model_event_log (
    model_event_log_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    model_id BIGINT NOT NULL,
    correlation_id UUID NOT NULL,
    agent_run_id VARCHAR(500),
    workflow_run_id BIGINT,
    model_event_log_sequence BIGINT NOT NULL,
    model_event_log_attempt INTEGER NOT NULL,
    model_workflow VARCHAR(30) NOT NULL,
    model_event_log_stage VARCHAR(100) NOT NULL,
    model_event_log_status VARCHAR(30) NOT NULL,
    model_event_log_message VARCHAR(2000) NOT NULL,
    model_event_log_current INTEGER,
    model_event_log_total INTEGER,
    model_event_log_percent NUMERIC(5, 2),
    finding_count INTEGER NOT NULL DEFAULT 0,
    created_time TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    created_by VARCHAR(255) NOT NULL DEFAULT CURRENT_USER,
    CONSTRAINT fk_model_event_log_model FOREIGN KEY (model_id)
        REFERENCES model.model (model_id) ON DELETE NO ACTION,
    CONSTRAINT ck_model_event_log_workflow CHECK (
        model_workflow IN (
            'profiling', 'analysis', 'conceptual',
            'logical', 'dimensional', 'mapping',
            'code_generation', 'validation', 'metadata_enrichment', 'dbml'
        )
    ),
    CONSTRAINT ck_model_event_log_order CHECK (
        model_event_log_sequence > 0
        AND model_event_log_attempt > 0
    ),
    CONSTRAINT ck_model_event_log_stage CHECK (
        reference.is_nonblank(model_event_log_stage)
    ),
    CONSTRAINT ck_model_event_log_status CHECK (
        model_event_log_status IN (
            'started', 'running', 'completed', 'warning', 'failed', 'blocked'
        )
    ),
    CONSTRAINT ck_model_event_log_message CHECK (
        reference.is_nonblank(model_event_log_message)
    ),
    CONSTRAINT ck_model_event_log_progress CHECK (
        (model_event_log_current IS NULL OR model_event_log_current >= 0)
        AND (model_event_log_total IS NULL OR model_event_log_total >= 0)
        AND (
            model_event_log_current IS NULL
            OR model_event_log_total IS NULL
            OR model_event_log_current <= model_event_log_total
        )
        AND (
            model_event_log_percent IS NULL
            OR model_event_log_percent BETWEEN 0 AND 100
        )
        AND finding_count >= 0
    ),
    CONSTRAINT uq_model_event_log_sequence UNIQUE (
        model_id,
        correlation_id,
        model_event_log_sequence
    )
);
```


[13_application_workflow_runs.sql:709](/Users/maazuddinmohammed/main/projects/gds_workbench_v2/database/13_application_workflow_runs.sql:709)

```sql
ALTER TABLE model.model_event_log
    ADD CONSTRAINT fk_model_event_log_workflow_run
    FOREIGN KEY (workflow_run_id, model_id)
    REFERENCES application.workflow_run (workflow_run_id, model_id)
    ON DELETE NO ACTION;
```


</details>

<details>
<summary><code>model.modeling_assertion_document</code></summary>


[04_model.sql:188](/Users/maazuddinmohammed/main/projects/gds_workbench_v2/database/04_model.sql:188)

```sql
CREATE TABLE model.modeling_assertion_document (
    modeling_assertion_document_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    model_id BIGINT NOT NULL,
    tenant_id BIGINT,
    system_id BIGINT,
    modeling_assertion_document_name VARCHAR(255) NOT NULL,
    modeling_assertion_file_pattern VARCHAR(500),
    modeling_assertion_document_type VARCHAR(100),
    modeling_assertion_document_description VARCHAR(2000),
    modeling_assertion_document_metadata JSONB NOT NULL DEFAULT '{}'::JSONB,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    agent_run_id VARCHAR(500),
    workflow_run_id BIGINT,
    created_time TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    created_by VARCHAR(255) NOT NULL DEFAULT CURRENT_USER,
    updated_time TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_by VARCHAR(255) NOT NULL DEFAULT CURRENT_USER,
    CONSTRAINT fk_assertion_document_model FOREIGN KEY (model_id)
        REFERENCES model.model (model_id) ON DELETE NO ACTION,
    CONSTRAINT fk_assertion_document_tenant FOREIGN KEY (tenant_id)
        REFERENCES core.tenant (tenant_id) ON DELETE NO ACTION,
    CONSTRAINT fk_assertion_document_system FOREIGN KEY (system_id)
        REFERENCES core.system (system_id) ON DELETE NO ACTION,
    CONSTRAINT uq_assertion_document_id_model
        UNIQUE (modeling_assertion_document_id, model_id),
    CONSTRAINT ck_assertion_document_name CHECK (
        reference.is_nonblank(modeling_assertion_document_name)
    ),
    CONSTRAINT ck_assertion_file_pattern CHECK (
        modeling_assertion_file_pattern IS NULL
        OR reference.is_nonblank(modeling_assertion_file_pattern)
    ),
    CONSTRAINT ck_assertion_document_type CHECK (
        modeling_assertion_document_type IS NULL
        OR reference.is_nonblank(modeling_assertion_document_type)
    ),
    CONSTRAINT ck_assertion_document_description CHECK (
        modeling_assertion_document_description IS NULL
        OR reference.is_nonblank(modeling_assertion_document_description)
    ),
    CONSTRAINT ck_assertion_document_metadata CHECK (
        jsonb_typeof(modeling_assertion_document_metadata) = 'object'
    )
);
```


[04_model.sql:311](/Users/maazuddinmohammed/main/projects/gds_workbench_v2/database/04_model.sql:311)

```sql
CREATE UNIQUE INDEX ux_assertion_document_model_name_ci
    ON model.modeling_assertion_document (
        model_id,
        lower(btrim(modeling_assertion_document_name))
    );
```


[13_application_workflow_runs.sql:715](/Users/maazuddinmohammed/main/projects/gds_workbench_v2/database/13_application_workflow_runs.sql:715)

```sql
ALTER TABLE model.modeling_assertion_document
    ADD CONSTRAINT fk_modeling_assertion_document_workflow_run
    FOREIGN KEY (workflow_run_id, model_id)
    REFERENCES application.workflow_run (workflow_run_id, model_id)
    ON DELETE NO ACTION;
```


</details>

<details>
<summary><code>model.modeling_assertion_record</code></summary>


[04_model.sql:233](/Users/maazuddinmohammed/main/projects/gds_workbench_v2/database/04_model.sql:233)

```sql
CREATE TABLE model.modeling_assertion_record (
    modeling_assertion_record_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    model_id BIGINT NOT NULL,
    modeling_assertion_document_id BIGINT NOT NULL,
    modeling_assertion_record_key VARCHAR(100) NOT NULL,
    modeling_assertion_record_type VARCHAR(100) NOT NULL,
    modeling_assertion_text TEXT NOT NULL,
    modeling_assertion_details JSONB NOT NULL DEFAULT '{}'::JSONB,
    modeling_assertion_source_location JSONB,
    modeling_assertion_applicable_layers TEXT[] NOT NULL DEFAULT '{}',
    modeling_assertion_confidence VARCHAR(10),
    modeling_assertion_record_status VARCHAR(20) NOT NULL DEFAULT 'active',
    modeling_assertion_record_is_locked BOOLEAN NOT NULL DEFAULT FALSE,
    agent_run_id VARCHAR(500),
    workflow_run_id BIGINT,
    created_time TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    created_by VARCHAR(255) NOT NULL DEFAULT CURRENT_USER,
    updated_time TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_by VARCHAR(255) NOT NULL DEFAULT CURRENT_USER,
    CONSTRAINT fk_assertion_record_model FOREIGN KEY (model_id)
        REFERENCES model.model (model_id) ON DELETE NO ACTION,
    CONSTRAINT fk_assertion_record_document FOREIGN KEY (
        modeling_assertion_document_id,
        model_id
    ) REFERENCES model.modeling_assertion_document (
        modeling_assertion_document_id,
        model_id
    ) ON DELETE NO ACTION,
    CONSTRAINT uq_assertion_record_id_model
        UNIQUE (modeling_assertion_record_id, model_id),
    CONSTRAINT ck_assertion_record_key CHECK (
        modeling_assertion_record_key ~ '^[A-Za-z][A-Za-z0-9_.-]{0,99}$'
    ),
    CONSTRAINT ck_assertion_record_type CHECK (
        reference.is_nonblank(modeling_assertion_record_type)
    ),
    CONSTRAINT ck_assertion_record_text CHECK (
        reference.is_nonblank(modeling_assertion_text)
    ),
    CONSTRAINT ck_assertion_record_details CHECK (
        jsonb_typeof(modeling_assertion_details) = 'object'
    ),
    CONSTRAINT ck_assertion_source_location CHECK (
        modeling_assertion_source_location IS NULL
        OR jsonb_typeof(modeling_assertion_source_location) = 'object'
    ),
    CONSTRAINT ck_assertion_applicable_layers CHECK (
        modeling_assertion_applicable_layers <@ ARRAY[
            'analysis', 'conceptual', 'logical', 'dimensional', 'mapping'
        ]::TEXT[]
    ),
    CONSTRAINT ck_assertion_confidence CHECK (
        modeling_assertion_confidence IS NULL
        OR modeling_assertion_confidence IN ('low', 'medium', 'high')
    ),
    CONSTRAINT ck_assertion_record_status CHECK (
        modeling_assertion_record_status IN (
            'active', 'inactive', 'deprecated'
        )
    )
);
```


[04_model.sql:316](/Users/maazuddinmohammed/main/projects/gds_workbench_v2/database/04_model.sql:316)

```sql
CREATE UNIQUE INDEX ux_assertion_record_model_key_ci
    ON model.modeling_assertion_record (
        model_id,
        lower(btrim(modeling_assertion_record_key))
    );
```


[13_application_workflow_runs.sql:721](/Users/maazuddinmohammed/main/projects/gds_workbench_v2/database/13_application_workflow_runs.sql:721)

```sql
ALTER TABLE model.modeling_assertion_record
    ADD CONSTRAINT fk_modeling_assertion_record_workflow_run
    FOREIGN KEY (workflow_run_id, model_id)
    REFERENCES application.workflow_run (workflow_run_id, model_id)
    ON DELETE NO ACTION;
```


</details>

<details>
<summary><code>model.model_revision_transaction</code></summary>


[04_model.sql:295](/Users/maazuddinmohammed/main/projects/gds_workbench_v2/database/04_model.sql:295)

```sql
CREATE TABLE model.model_revision_transaction (
    model_id BIGINT NOT NULL,
    transaction_id BIGINT NOT NULL DEFAULT txid_current(),
    change_kind VARCHAR(100) NOT NULL,
    changed_time TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    changed_by VARCHAR(255) NOT NULL DEFAULT SESSION_USER,
    PRIMARY KEY (model_id, transaction_id),
    CONSTRAINT fk_model_revision_transaction_model FOREIGN KEY (model_id)
        REFERENCES model.model (model_id) ON DELETE NO ACTION,
    CONSTRAINT ck_model_revision_change_kind CHECK (
        reference.is_nonblank(change_kind)
    )
);
```


</details>

### workflow: exact declarations

<details>
<summary><code>workflow.attribute_profile</code></summary>


[05_workflow_analysis.sql:5](/Users/maazuddinmohammed/main/projects/gds_workbench_v2/database/05_workflow_analysis.sql:5)

```sql
CREATE TABLE workflow.attribute_profile (
    model_id BIGINT NOT NULL,
    attribute_id BIGINT NOT NULL,
    object_id BIGINT NOT NULL,
    agent_run_id VARCHAR(500),
    workflow_run_id BIGINT,
    source_context_digest CHAR(64) NOT NULL,
    row_count BIGINT NOT NULL,
    non_null_count BIGINT NOT NULL,
    null_count BIGINT NOT NULL,
    blank_count BIGINT,
    distinct_count BIGINT,
    min_data_length INTEGER,
    max_data_length INTEGER,
    avg_data_length NUMERIC(20, 6),
    percent_populated NUMERIC(7, 4),
    percent_duplicates NUMERIC(7, 4),
    percent_null NUMERIC(7, 4),
    percent_blank NUMERIC(7, 4),
    percent_distinct NUMERIC(7, 4),
    created_time TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    created_by VARCHAR(255) NOT NULL DEFAULT CURRENT_USER,
    updated_time TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_by VARCHAR(255) NOT NULL DEFAULT CURRENT_USER,
    PRIMARY KEY (model_id, attribute_id),
    CONSTRAINT fk_attribute_profile_model FOREIGN KEY (model_id)
        REFERENCES model.model (model_id) ON DELETE NO ACTION,
    CONSTRAINT fk_attribute_profile_scope FOREIGN KEY (model_id, object_id)
        REFERENCES model.model_input_scope (model_id, object_id) ON DELETE NO ACTION,
    CONSTRAINT fk_attribute_profile_attribute FOREIGN KEY (
        attribute_id,
        object_id
    ) REFERENCES core.attribute (attribute_id, object_id) ON DELETE NO ACTION,
    CONSTRAINT ck_attribute_profile_digest CHECK (
        source_context_digest ~ '^[0-9a-f]{64}$'
    ),
    CONSTRAINT ck_attribute_profile_counts CHECK (
        row_count >= 0
        AND non_null_count >= 0
        AND null_count >= 0
        AND non_null_count + null_count = row_count
        AND (blank_count IS NULL OR blank_count BETWEEN 0 AND non_null_count)
        AND (distinct_count IS NULL OR distinct_count BETWEEN 0 AND non_null_count)
    ),
    CONSTRAINT ck_attribute_profile_lengths CHECK (
        (min_data_length IS NULL OR min_data_length >= 0)
        AND (max_data_length IS NULL OR max_data_length >= 0)
        AND (
            min_data_length IS NULL
            OR max_data_length IS NULL
            OR min_data_length <= max_data_length
        )
        AND (avg_data_length IS NULL OR avg_data_length >= 0)
    ),
    CONSTRAINT ck_attribute_profile_percentages CHECK (
        (percent_populated IS NULL OR percent_populated BETWEEN 0 AND 100)
        AND (percent_duplicates IS NULL OR percent_duplicates BETWEEN 0 AND 100)
        AND (percent_null IS NULL OR percent_null BETWEEN 0 AND 100)
        AND (percent_blank IS NULL OR percent_blank BETWEEN 0 AND 100)
        AND (percent_distinct IS NULL OR percent_distinct BETWEEN 0 AND 100)
    )
);
```


[13_application_workflow_runs.sql:727](/Users/maazuddinmohammed/main/projects/gds_workbench_v2/database/13_application_workflow_runs.sql:727)

```sql
ALTER TABLE workflow.attribute_profile
    ADD CONSTRAINT fk_attribute_profile_workflow_run
    FOREIGN KEY (workflow_run_id, model_id)
    REFERENCES application.workflow_run (workflow_run_id, model_id)
    ON DELETE NO ACTION;
```


</details>

<details>
<summary><code>workflow.analysis_result</code></summary>


[05_workflow_analysis.sql:68](/Users/maazuddinmohammed/main/projects/gds_workbench_v2/database/05_workflow_analysis.sql:68)

```sql
CREATE TABLE workflow.analysis_result (
    analysis_result_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    model_id BIGINT NOT NULL,
    agent_run_id VARCHAR(500),
    inference_workflow_run_id BIGINT,
    validation_workflow_run_id BIGINT,
    validation_source_context_digest CHAR(64),
    from_object_id BIGINT NOT NULL,
    from_attribute_id BIGINT NOT NULL,
    to_object_id BIGINT NOT NULL,
    to_attribute_id BIGINT NOT NULL,
    relationship_kind VARCHAR(100) NOT NULL,
    relationship_confidence VARCHAR(10) NOT NULL DEFAULT 'medium',
    relationship_basis TEXT NOT NULL,
    validation_policy_version VARCHAR(50),
    validation_policy_digest CHAR(64),
    validation_result VARCHAR(30),
    validation_source_non_null_count BIGINT,
    validation_source_distinct_count BIGINT,
    validation_target_non_null_count BIGINT,
    validation_target_distinct_count BIGINT,
    validation_source_missing_target_count BIGINT,
    validation_unused_target_count BIGINT,
    validation_duplicate_target_key_count BIGINT,
    analysis_result_status VARCHAR(20) NOT NULL DEFAULT 'active',
    analysis_result_is_locked BOOLEAN NOT NULL DEFAULT FALSE,
    created_time TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    created_by VARCHAR(255) NOT NULL DEFAULT CURRENT_USER,
    updated_time TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_by VARCHAR(255) NOT NULL DEFAULT CURRENT_USER,
    CONSTRAINT fk_analysis_result_model FOREIGN KEY (model_id)
        REFERENCES model.model (model_id) ON DELETE NO ACTION,
    CONSTRAINT fk_analysis_from_scope FOREIGN KEY (model_id, from_object_id)
        REFERENCES model.model_input_scope (model_id, object_id) ON DELETE NO ACTION,
    CONSTRAINT fk_analysis_to_scope FOREIGN KEY (model_id, to_object_id)
        REFERENCES model.model_input_scope (model_id, object_id) ON DELETE NO ACTION,
    CONSTRAINT fk_analysis_from_attribute FOREIGN KEY (
        from_attribute_id,
        from_object_id
    ) REFERENCES core.attribute (attribute_id, object_id) ON DELETE NO ACTION,
    CONSTRAINT fk_analysis_to_attribute FOREIGN KEY (
        to_attribute_id,
        to_object_id
    ) REFERENCES core.attribute (attribute_id, object_id) ON DELETE NO ACTION,
    CONSTRAINT uq_analysis_result_identity UNIQUE (
        model_id,
        from_attribute_id,
        to_attribute_id,
        relationship_kind
    ),
    CONSTRAINT ck_analysis_distinct_endpoints CHECK (
        from_attribute_id <> to_attribute_id
    ),
    CONSTRAINT ck_analysis_relationship_kind CHECK (
        reference.is_nonblank(relationship_kind)
    ),
    CONSTRAINT ck_analysis_confidence CHECK (
        relationship_confidence IN ('low', 'medium', 'high')
    ),
    CONSTRAINT ck_analysis_basis CHECK (reference.is_nonblank(relationship_basis)),
    CONSTRAINT ck_analysis_validation_payload CHECK (
        num_nonnulls(
            validation_policy_version,
            validation_policy_digest,
            validation_result,
            validation_source_non_null_count,
            validation_source_distinct_count,
            validation_target_non_null_count,
            validation_target_distinct_count,
            validation_source_missing_target_count,
            validation_unused_target_count,
            validation_duplicate_target_key_count
        ) IN (0, 10)
        AND (
            validation_workflow_run_id IS NULL
            OR validation_result IS NOT NULL
        )
    ),
    CONSTRAINT ck_analysis_policy_version CHECK (
        validation_policy_version ~ '^[0-9]+\.[0-9]+\.[0-9]+$'
    ),
    CONSTRAINT ck_analysis_source_context_digest CHECK (
        validation_source_context_digest IS NULL
        OR (
            validation_source_context_digest ~ '^[0-9a-f]{64}$'
            AND validation_result IS NOT NULL
        )
    ),
    CONSTRAINT ck_analysis_web_validation_context CHECK (
        validation_workflow_run_id IS NULL
        OR validation_source_context_digest IS NOT NULL
    ),
    CONSTRAINT ck_analysis_policy_digest CHECK (
        validation_policy_digest ~ '^[0-9a-f]{64}$'
    ),
    CONSTRAINT ck_analysis_validation_result CHECK (
        validation_result IN ('supported', 'inconclusive', 'unsupported')
    ),
    CONSTRAINT ck_analysis_counts CHECK (
        validation_source_non_null_count >= 0
        AND validation_source_distinct_count >= 0
        AND validation_target_non_null_count >= 0
        AND validation_target_distinct_count >= 0
        AND validation_source_missing_target_count >= 0
        AND validation_unused_target_count >= 0
        AND validation_duplicate_target_key_count >= 0
    ),
    CONSTRAINT ck_analysis_result_status CHECK (
        analysis_result_status IN (
            'active', 'inactive', 'deprecated'
        )
    )
);
```


[13_application_workflow_runs.sql:733](/Users/maazuddinmohammed/main/projects/gds_workbench_v2/database/13_application_workflow_runs.sql:733)

```sql
ALTER TABLE workflow.analysis_result
    ADD CONSTRAINT fk_analysis_result_inference_workflow_run
    FOREIGN KEY (inference_workflow_run_id, model_id)
    REFERENCES application.workflow_run (workflow_run_id, model_id)
    ON DELETE NO ACTION,
    ADD CONSTRAINT fk_analysis_result_validation_workflow_run
    FOREIGN KEY (validation_workflow_run_id, model_id)
    REFERENCES application.workflow_run (workflow_run_id, model_id)
    ON DELETE NO ACTION;
```


</details>

<details>
<summary><code>workflow.conceptual_object</code></summary>


[06_workflow_conceptual.sql:3](/Users/maazuddinmohammed/main/projects/gds_workbench_v2/database/06_workflow_conceptual.sql:3)

```sql
CREATE TABLE workflow.conceptual_object (
    conceptual_object_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    model_id BIGINT NOT NULL,
    agent_run_id VARCHAR(500),
    workflow_run_id BIGINT,
    conceptual_object_name VARCHAR(255) NOT NULL,
    conceptual_object_definition TEXT NOT NULL,
    conceptual_object_type VARCHAR(100) NOT NULL,
    conceptual_object_grain TEXT NOT NULL,
    conceptual_object_aliases TEXT[] NOT NULL DEFAULT '{}',
    conceptual_object_confidence VARCHAR(10) NOT NULL DEFAULT 'medium',
    conceptual_object_status VARCHAR(20) NOT NULL DEFAULT 'active',
    conceptual_object_is_locked BOOLEAN NOT NULL DEFAULT FALSE,
    created_time TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    created_by VARCHAR(255) NOT NULL DEFAULT CURRENT_USER,
    updated_time TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_by VARCHAR(255) NOT NULL DEFAULT CURRENT_USER,
    CONSTRAINT fk_conceptual_object_model FOREIGN KEY (model_id)
        REFERENCES model.model (model_id) ON DELETE NO ACTION,
    CONSTRAINT uq_conceptual_object_id_model
        UNIQUE (conceptual_object_id, model_id),
    CONSTRAINT ck_conceptual_object_name CHECK (
        reference.is_nonblank(conceptual_object_name)
    ),
    CONSTRAINT ck_conceptual_object_definition CHECK (
        reference.is_nonblank(conceptual_object_definition)
    ),
    CONSTRAINT ck_conceptual_object_type CHECK (
        reference.is_nonblank(conceptual_object_type)
    ),
    CONSTRAINT ck_conceptual_object_grain CHECK (
        reference.is_nonblank(conceptual_object_grain)
    ),
    CONSTRAINT ck_conceptual_object_confidence CHECK (
        conceptual_object_confidence IN ('low', 'medium', 'high')
    ),
    CONSTRAINT ck_conceptual_object_status CHECK (
        conceptual_object_status IN (
            'active', 'inactive', 'deprecated'
        )
    )
);
```


[06_workflow_conceptual.sql:46](/Users/maazuddinmohammed/main/projects/gds_workbench_v2/database/06_workflow_conceptual.sql:46)

```sql
CREATE UNIQUE INDEX ux_conceptual_object_model_name
    ON workflow.conceptual_object (
        model_id,
        lower(btrim(conceptual_object_name))
    );
```


[13_application_workflow_runs.sql:743](/Users/maazuddinmohammed/main/projects/gds_workbench_v2/database/13_application_workflow_runs.sql:743)

```sql
ALTER TABLE workflow.conceptual_object
    ADD CONSTRAINT fk_conceptual_object_workflow_run
    FOREIGN KEY (workflow_run_id, model_id)
    REFERENCES application.workflow_run (workflow_run_id, model_id)
    ON DELETE NO ACTION;
```


</details>

<details>
<summary><code>workflow.conceptual_relationship</code></summary>


[06_workflow_conceptual.sql:52](/Users/maazuddinmohammed/main/projects/gds_workbench_v2/database/06_workflow_conceptual.sql:52)

```sql
CREATE TABLE workflow.conceptual_relationship (
    conceptual_relationship_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    model_id BIGINT NOT NULL,
    agent_run_id VARCHAR(500),
    workflow_run_id BIGINT,
    from_conceptual_object_id BIGINT NOT NULL,
    to_conceptual_object_id BIGINT NOT NULL,
    conceptual_relationship_name VARCHAR(255) NOT NULL,
    conceptual_relationship_type VARCHAR(100) NOT NULL,
    conceptual_relationship_definition TEXT NOT NULL,
    conceptual_relationship_cardinality VARCHAR(30) NOT NULL,
    conceptual_relationship_basis TEXT NOT NULL,
    conceptual_relationship_cardinality_basis TEXT NOT NULL,
    conceptual_relationship_confidence VARCHAR(10) NOT NULL DEFAULT 'medium',
    conceptual_relationship_status VARCHAR(20) NOT NULL DEFAULT 'active',
    conceptual_relationship_is_locked BOOLEAN NOT NULL DEFAULT FALSE,
    created_time TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    created_by VARCHAR(255) NOT NULL DEFAULT CURRENT_USER,
    updated_time TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_by VARCHAR(255) NOT NULL DEFAULT CURRENT_USER,
    CONSTRAINT fk_conceptual_relationship_model FOREIGN KEY (model_id)
        REFERENCES model.model (model_id) ON DELETE NO ACTION,
    CONSTRAINT fk_conceptual_relationship_from_object FOREIGN KEY (
        from_conceptual_object_id,
        model_id
    ) REFERENCES workflow.conceptual_object (
        conceptual_object_id,
        model_id
    ) ON DELETE NO ACTION,
    CONSTRAINT fk_conceptual_relationship_to_object FOREIGN KEY (
        to_conceptual_object_id,
        model_id
    ) REFERENCES workflow.conceptual_object (
        conceptual_object_id,
        model_id
    ) ON DELETE NO ACTION,
    CONSTRAINT uq_conceptual_relationship_id_model
        UNIQUE (conceptual_relationship_id, model_id),
    CONSTRAINT ck_conceptual_relationship_objects_different CHECK (
        from_conceptual_object_id <> to_conceptual_object_id
    ),
    CONSTRAINT ck_conceptual_relationship_name CHECK (
        reference.is_nonblank(conceptual_relationship_name)
    ),
    CONSTRAINT ck_conceptual_relationship_type CHECK (
        reference.is_nonblank(conceptual_relationship_type)
    ),
    CONSTRAINT ck_conceptual_relationship_definition CHECK (
        reference.is_nonblank(conceptual_relationship_definition)
    ),
    CONSTRAINT ck_conceptual_relationship_cardinality CHECK (
        conceptual_relationship_cardinality IN (
            'one_to_one', 'one_to_many', 'many_to_one',
            'many_to_many', 'unknown'
        )
    ),
    CONSTRAINT ck_conceptual_relationship_basis CHECK (
        reference.is_nonblank(conceptual_relationship_basis)
        AND reference.is_nonblank(conceptual_relationship_cardinality_basis)
    ),
    CONSTRAINT ck_conceptual_relationship_confidence CHECK (
        conceptual_relationship_confidence IN ('low', 'medium', 'high')
    ),
    CONSTRAINT ck_conceptual_relationship_status CHECK (
        conceptual_relationship_status IN (
            'active', 'inactive', 'deprecated'
        )
    )
);
```


[06_workflow_conceptual.sql:122](/Users/maazuddinmohammed/main/projects/gds_workbench_v2/database/06_workflow_conceptual.sql:122)

```sql
CREATE UNIQUE INDEX ux_conceptual_relationship_identity
    ON workflow.conceptual_relationship (
        model_id,
        from_conceptual_object_id,
        to_conceptual_object_id,
        lower(btrim(conceptual_relationship_name))
    );
```


[13_application_workflow_runs.sql:749](/Users/maazuddinmohammed/main/projects/gds_workbench_v2/database/13_application_workflow_runs.sql:749)

```sql
ALTER TABLE workflow.conceptual_relationship
    ADD CONSTRAINT fk_conceptual_relationship_workflow_run
    FOREIGN KEY (workflow_run_id, model_id)
    REFERENCES application.workflow_run (workflow_run_id, model_id)
    ON DELETE NO ACTION;
```


</details>

<details>
<summary><code>workflow.conceptual_support</code></summary>


[06_workflow_conceptual.sql:130](/Users/maazuddinmohammed/main/projects/gds_workbench_v2/database/06_workflow_conceptual.sql:130)

```sql
CREATE TABLE workflow.conceptual_support (
    conceptual_support_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    model_id BIGINT NOT NULL,
    agent_run_id VARCHAR(500),
    workflow_run_id BIGINT,
    supported_artifact_type VARCHAR(30) NOT NULL,
    conceptual_object_id BIGINT,
    conceptual_relationship_id BIGINT,
    support_source_type VARCHAR(20) NOT NULL,
    source_object_id BIGINT,
    modeling_assertion_record_id BIGINT,
    conceptual_support_role VARCHAR(255),
    conceptual_support_reason TEXT NOT NULL,
    conceptual_support_reason_detail TEXT,
    conceptual_support_confidence VARCHAR(10) NOT NULL DEFAULT 'medium',
    conceptual_support_status VARCHAR(20) NOT NULL DEFAULT 'active',
    conceptual_support_is_locked BOOLEAN NOT NULL DEFAULT FALSE,
    created_time TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    created_by VARCHAR(255) NOT NULL DEFAULT CURRENT_USER,
    updated_time TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_by VARCHAR(255) NOT NULL DEFAULT CURRENT_USER,
    CONSTRAINT fk_conceptual_support_model FOREIGN KEY (model_id)
        REFERENCES model.model (model_id) ON DELETE NO ACTION,
    CONSTRAINT fk_conceptual_support_object_parent FOREIGN KEY (
        conceptual_object_id,
        model_id
    ) REFERENCES workflow.conceptual_object (
        conceptual_object_id,
        model_id
    ) ON DELETE NO ACTION,
    CONSTRAINT fk_conceptual_support_relationship_parent FOREIGN KEY (
        conceptual_relationship_id,
        model_id
    ) REFERENCES workflow.conceptual_relationship (
        conceptual_relationship_id,
        model_id
    ) ON DELETE NO ACTION,
    CONSTRAINT fk_conceptual_support_physical_object FOREIGN KEY (
        model_id,
        source_object_id
    ) REFERENCES model.model_input_scope (model_id, object_id) ON DELETE NO ACTION,
    CONSTRAINT fk_conceptual_support_assertion_record FOREIGN KEY (
        modeling_assertion_record_id,
        model_id
    ) REFERENCES model.modeling_assertion_record (
        modeling_assertion_record_id,
        model_id
    ) ON DELETE NO ACTION,
    CONSTRAINT ck_conceptual_support_typed_parent CHECK (
        (
            supported_artifact_type = 'conceptual_object'
            AND conceptual_object_id IS NOT NULL
            AND conceptual_relationship_id IS NULL
        ) OR (
            supported_artifact_type = 'conceptual_relationship'
            AND conceptual_relationship_id IS NOT NULL
            AND conceptual_object_id IS NULL
        )
    ),
    CONSTRAINT ck_conceptual_support_typed_source CHECK (
        (
            support_source_type = 'object'
            AND source_object_id IS NOT NULL
            AND modeling_assertion_record_id IS NULL
        ) OR (
            support_source_type = 'assertion'
            AND modeling_assertion_record_id IS NOT NULL
            AND source_object_id IS NULL
        )
    ),
    CONSTRAINT ck_conceptual_support_role CHECK (
        conceptual_support_role IS NULL
        OR reference.is_nonblank(conceptual_support_role)
    ),
    CONSTRAINT ck_conceptual_support_reason CHECK (
        reference.is_nonblank(conceptual_support_reason)
    ),
    CONSTRAINT ck_conceptual_support_reason_detail CHECK (
        conceptual_support_reason_detail IS NULL
        OR reference.is_nonblank(conceptual_support_reason_detail)
    ),
    CONSTRAINT ck_conceptual_support_confidence CHECK (
        conceptual_support_confidence IN ('low', 'medium', 'high')
    ),
    CONSTRAINT ck_conceptual_support_status CHECK (
        conceptual_support_status IN (
            'active', 'inactive', 'deprecated'
        )
    )
);
```


[06_workflow_conceptual.sql:221](/Users/maazuddinmohammed/main/projects/gds_workbench_v2/database/06_workflow_conceptual.sql:221)

```sql
CREATE UNIQUE INDEX ux_conceptual_support_object_parent_object_source
    ON workflow.conceptual_support (
        model_id,
        conceptual_object_id,
        source_object_id
    ) WHERE supported_artifact_type = 'conceptual_object'
        AND support_source_type = 'object';
```


[06_workflow_conceptual.sql:228](/Users/maazuddinmohammed/main/projects/gds_workbench_v2/database/06_workflow_conceptual.sql:228)

```sql
CREATE UNIQUE INDEX ux_conceptual_support_object_parent_assertion_source
    ON workflow.conceptual_support (
        model_id,
        conceptual_object_id,
        modeling_assertion_record_id
    ) WHERE supported_artifact_type = 'conceptual_object'
        AND support_source_type = 'assertion';
```


[06_workflow_conceptual.sql:235](/Users/maazuddinmohammed/main/projects/gds_workbench_v2/database/06_workflow_conceptual.sql:235)

```sql
CREATE UNIQUE INDEX ux_conceptual_support_relationship_parent_object_source
    ON workflow.conceptual_support (
        model_id,
        conceptual_relationship_id,
        source_object_id
    ) WHERE supported_artifact_type = 'conceptual_relationship'
        AND support_source_type = 'object';
```


[06_workflow_conceptual.sql:242](/Users/maazuddinmohammed/main/projects/gds_workbench_v2/database/06_workflow_conceptual.sql:242)

```sql
CREATE UNIQUE INDEX ux_conceptual_support_relationship_parent_assertion_source
    ON workflow.conceptual_support (
        model_id,
        conceptual_relationship_id,
        modeling_assertion_record_id
    ) WHERE supported_artifact_type = 'conceptual_relationship'
        AND support_source_type = 'assertion';
```


[13_application_workflow_runs.sql:755](/Users/maazuddinmohammed/main/projects/gds_workbench_v2/database/13_application_workflow_runs.sql:755)

```sql
ALTER TABLE workflow.conceptual_support
    ADD CONSTRAINT fk_conceptual_support_workflow_run
    FOREIGN KEY (workflow_run_id, model_id)
    REFERENCES application.workflow_run (workflow_run_id, model_id)
    ON DELETE NO ACTION;
```


</details>

<details>
<summary><code>workflow.logical_submodel</code></summary>


[07_workflow_logical.sql:3](/Users/maazuddinmohammed/main/projects/gds_workbench_v2/database/07_workflow_logical.sql:3)

```sql
CREATE TABLE workflow.logical_submodel (
    logical_submodel_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    model_id BIGINT NOT NULL,
    agent_run_id VARCHAR(500),
    workflow_run_id BIGINT,
    logical_submodel_name VARCHAR(255) NOT NULL,
    logical_submodel_definition TEXT NOT NULL,
    logical_submodel_status VARCHAR(20) NOT NULL DEFAULT 'active',
    logical_submodel_is_locked BOOLEAN NOT NULL DEFAULT FALSE,
    created_time TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    created_by VARCHAR(255) NOT NULL DEFAULT CURRENT_USER,
    updated_time TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_by VARCHAR(255) NOT NULL DEFAULT CURRENT_USER,
    CONSTRAINT fk_logical_submodel_model FOREIGN KEY (model_id)
        REFERENCES model.model (model_id) ON DELETE NO ACTION,
    CONSTRAINT uq_logical_submodel_id_model UNIQUE (logical_submodel_id, model_id),
    CONSTRAINT ck_logical_submodel_name CHECK (reference.is_nonblank(logical_submodel_name)),
    CONSTRAINT ck_logical_submodel_definition CHECK (
        reference.is_nonblank(logical_submodel_definition)
    ),
    CONSTRAINT ck_logical_submodel_status CHECK (
        logical_submodel_status IN ('active', 'inactive', 'deprecated')
    )
);
```


[07_workflow_logical.sql:28](/Users/maazuddinmohammed/main/projects/gds_workbench_v2/database/07_workflow_logical.sql:28)

```sql
CREATE UNIQUE INDEX ux_logical_submodel_model_name
    ON workflow.logical_submodel (model_id, lower(btrim(logical_submodel_name)));
```


[13_application_workflow_runs.sql:761](/Users/maazuddinmohammed/main/projects/gds_workbench_v2/database/13_application_workflow_runs.sql:761)

```sql
ALTER TABLE workflow.logical_submodel
    ADD CONSTRAINT fk_logical_submodel_workflow_run
    FOREIGN KEY (workflow_run_id, model_id)
    REFERENCES application.workflow_run (workflow_run_id, model_id)
    ON DELETE NO ACTION;
```


</details>

<details>
<summary><code>workflow.logical_entity</code></summary>


[07_workflow_logical.sql:31](/Users/maazuddinmohammed/main/projects/gds_workbench_v2/database/07_workflow_logical.sql:31)

```sql
CREATE TABLE workflow.logical_entity (
    logical_entity_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    model_id BIGINT NOT NULL,
    agent_run_id VARCHAR(500),
    workflow_run_id BIGINT,
    logical_entity_name VARCHAR(255) NOT NULL,
    logical_entity_definition TEXT NOT NULL,
    logical_entity_type VARCHAR(50) NOT NULL,
    logical_entity_type_detail TEXT,
    logical_entity_grain TEXT NOT NULL,
    logical_entity_dependency_order INTEGER NOT NULL DEFAULT 0,
    logical_entity_confidence VARCHAR(10) NOT NULL DEFAULT 'medium',
    logical_entity_status VARCHAR(20) NOT NULL DEFAULT 'active',
    logical_entity_is_locked BOOLEAN NOT NULL DEFAULT FALSE,
    created_time TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    created_by VARCHAR(255) NOT NULL DEFAULT CURRENT_USER,
    updated_time TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_by VARCHAR(255) NOT NULL DEFAULT CURRENT_USER,
    CONSTRAINT fk_logical_entity_model FOREIGN KEY (model_id)
        REFERENCES model.model (model_id) ON DELETE NO ACTION,
    CONSTRAINT uq_logical_entity_id_model UNIQUE (logical_entity_id, model_id),
    CONSTRAINT ck_logical_entity_name CHECK (reference.is_nonblank(logical_entity_name)),
    CONSTRAINT ck_logical_entity_definition CHECK (
        reference.is_nonblank(logical_entity_definition)
    ),
    CONSTRAINT ck_logical_entity_type CHECK (
        logical_entity_type IN (
            'core', 'reference', 'transaction', 'event', 'bridge',
            'history', 'snapshot', 'association', 'aggregate', 'other'
        )
    ),
    CONSTRAINT ck_logical_entity_type_detail CHECK (
        (logical_entity_type = 'other' AND reference.is_nonblank(logical_entity_type_detail))
        OR (logical_entity_type <> 'other' AND logical_entity_type_detail IS NULL)
    ),
    CONSTRAINT ck_logical_entity_grain CHECK (reference.is_nonblank(logical_entity_grain)),
    CONSTRAINT ck_logical_entity_dependency_order CHECK (
        logical_entity_dependency_order >= 0
    ),
    CONSTRAINT ck_logical_entity_confidence CHECK (
        logical_entity_confidence IN ('low', 'medium', 'high')
    ),
    CONSTRAINT ck_logical_entity_status CHECK (
        logical_entity_status IN ('active', 'inactive', 'deprecated')
    )
);
```


[07_workflow_logical.sql:78](/Users/maazuddinmohammed/main/projects/gds_workbench_v2/database/07_workflow_logical.sql:78)

```sql
CREATE UNIQUE INDEX ux_logical_entity_model_name
    ON workflow.logical_entity (model_id, lower(btrim(logical_entity_name)));
```


[13_application_workflow_runs.sql:767](/Users/maazuddinmohammed/main/projects/gds_workbench_v2/database/13_application_workflow_runs.sql:767)

```sql
ALTER TABLE workflow.logical_entity
    ADD CONSTRAINT fk_logical_entity_workflow_run
    FOREIGN KEY (workflow_run_id, model_id)
    REFERENCES application.workflow_run (workflow_run_id, model_id)
    ON DELETE NO ACTION;
```


</details>

<details>
<summary><code>workflow.logical_entity_submodel</code></summary>


[07_workflow_logical.sql:81](/Users/maazuddinmohammed/main/projects/gds_workbench_v2/database/07_workflow_logical.sql:81)

```sql
CREATE TABLE workflow.logical_entity_submodel (
    logical_entity_submodel_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    model_id BIGINT NOT NULL,
    agent_run_id VARCHAR(500),
    workflow_run_id BIGINT,
    logical_entity_id BIGINT NOT NULL,
    logical_submodel_id BIGINT NOT NULL,
    logical_entity_submodel_status VARCHAR(20) NOT NULL DEFAULT 'active',
    logical_entity_submodel_is_locked BOOLEAN NOT NULL DEFAULT FALSE,
    created_time TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    created_by VARCHAR(255) NOT NULL DEFAULT CURRENT_USER,
    updated_time TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_by VARCHAR(255) NOT NULL DEFAULT CURRENT_USER,
    CONSTRAINT fk_logical_entity_submodel_model FOREIGN KEY (model_id)
        REFERENCES model.model (model_id) ON DELETE NO ACTION,
    CONSTRAINT fk_logical_entity_submodel_entity FOREIGN KEY (
        logical_entity_id,
        model_id
    ) REFERENCES workflow.logical_entity (logical_entity_id, model_id)
        ON DELETE NO ACTION,
    CONSTRAINT fk_logical_entity_submodel_submodel FOREIGN KEY (
        logical_submodel_id,
        model_id
    ) REFERENCES workflow.logical_submodel (logical_submodel_id, model_id)
        ON DELETE NO ACTION,
    CONSTRAINT uq_logical_entity_submodel_identity
        UNIQUE (model_id, logical_entity_id, logical_submodel_id),
    CONSTRAINT ck_logical_entity_submodel_status CHECK (
        logical_entity_submodel_status IN (
            'active', 'inactive', 'deprecated'
        )
    )
);
```


[13_application_workflow_runs.sql:773](/Users/maazuddinmohammed/main/projects/gds_workbench_v2/database/13_application_workflow_runs.sql:773)

```sql
ALTER TABLE workflow.logical_entity_submodel
    ADD CONSTRAINT fk_logical_entity_submodel_workflow_run
    FOREIGN KEY (workflow_run_id, model_id)
    REFERENCES application.workflow_run (workflow_run_id, model_id)
    ON DELETE NO ACTION;
```


</details>

<details>
<summary><code>workflow.logical_attribute</code></summary>


[07_workflow_logical.sql:115](/Users/maazuddinmohammed/main/projects/gds_workbench_v2/database/07_workflow_logical.sql:115)

```sql
CREATE TABLE workflow.logical_attribute (
    logical_attribute_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    model_id BIGINT NOT NULL,
    agent_run_id VARCHAR(500),
    workflow_run_id BIGINT,
    logical_entity_id BIGINT NOT NULL,
    logical_attribute_name VARCHAR(255) NOT NULL,
    logical_attribute_definition TEXT NOT NULL,
    logical_attribute_data_type VARCHAR(100) NOT NULL,
    logical_attribute_is_nullable BOOLEAN NOT NULL DEFAULT TRUE,
    logical_attribute_is_primary_key BOOLEAN NOT NULL DEFAULT FALSE,
    logical_attribute_is_natural_key BOOLEAN NOT NULL DEFAULT FALSE,
    logical_attribute_is_surrogate_key BOOLEAN NOT NULL DEFAULT FALSE,
    logical_attribute_ordinal_position INTEGER NOT NULL,
    logical_attribute_is_audit_column BOOLEAN NOT NULL DEFAULT FALSE,
    logical_attribute_status VARCHAR(20) NOT NULL DEFAULT 'active',
    logical_attribute_is_locked BOOLEAN NOT NULL DEFAULT FALSE,
    created_time TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    created_by VARCHAR(255) NOT NULL DEFAULT CURRENT_USER,
    updated_time TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_by VARCHAR(255) NOT NULL DEFAULT CURRENT_USER,
    CONSTRAINT fk_logical_attribute_model FOREIGN KEY (model_id)
        REFERENCES model.model (model_id) ON DELETE NO ACTION,
    CONSTRAINT fk_logical_attribute_entity FOREIGN KEY (
        logical_entity_id,
        model_id
    ) REFERENCES workflow.logical_entity (logical_entity_id, model_id)
        ON DELETE NO ACTION,
    CONSTRAINT uq_logical_attribute_id_model UNIQUE (logical_attribute_id, model_id),
    CONSTRAINT uq_logical_attribute_witness
        UNIQUE (logical_attribute_id, logical_entity_id, model_id),
    CONSTRAINT ck_logical_attribute_name CHECK (
        reference.is_nonblank(logical_attribute_name)
    ),
    CONSTRAINT ck_logical_attribute_definition CHECK (
        reference.is_nonblank(logical_attribute_definition)
    ),
    CONSTRAINT ck_logical_attribute_data_type CHECK (
        reference.is_nonblank(logical_attribute_data_type)
    ),
    CONSTRAINT ck_logical_attribute_key_origin CHECK (
        NOT (
            logical_attribute_is_natural_key
            AND logical_attribute_is_surrogate_key
        )
    ),
    CONSTRAINT ck_logical_attribute_key_nullable CHECK (
        NOT (
            logical_attribute_is_primary_key
            OR logical_attribute_is_natural_key
            OR logical_attribute_is_surrogate_key
        ) OR NOT logical_attribute_is_nullable
    ),
    CONSTRAINT ck_logical_attribute_ordinal CHECK (
        logical_attribute_ordinal_position > 0
    ),
    CONSTRAINT ck_logical_attribute_status CHECK (
        logical_attribute_status IN ('active', 'inactive', 'deprecated')
    )
);
```


[07_workflow_logical.sql:176](/Users/maazuddinmohammed/main/projects/gds_workbench_v2/database/07_workflow_logical.sql:176)

```sql
CREATE UNIQUE INDEX ux_logical_attribute_entity_name
    ON workflow.logical_attribute (
        model_id,
        logical_entity_id,
        lower(btrim(logical_attribute_name))
    );
```


[13_application_workflow_runs.sql:779](/Users/maazuddinmohammed/main/projects/gds_workbench_v2/database/13_application_workflow_runs.sql:779)

```sql
ALTER TABLE workflow.logical_attribute
    ADD CONSTRAINT fk_logical_attribute_workflow_run
    FOREIGN KEY (workflow_run_id, model_id)
    REFERENCES application.workflow_run (workflow_run_id, model_id)
    ON DELETE NO ACTION;
```


</details>

<details>
<summary><code>workflow.logical_entity_source_mapping</code></summary>


[07_workflow_logical.sql:183](/Users/maazuddinmohammed/main/projects/gds_workbench_v2/database/07_workflow_logical.sql:183)

```sql
CREATE TABLE workflow.logical_entity_source_mapping (
    logical_entity_source_mapping_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    model_id BIGINT NOT NULL,
    agent_run_id VARCHAR(500),
    workflow_run_id BIGINT,
    logical_entity_id BIGINT NOT NULL,
    support_source_type VARCHAR(20) NOT NULL,
    source_object_id BIGINT,
    modeling_assertion_record_id BIGINT,
    logical_entity_source_mapping_order INTEGER,
    logical_entity_source_mapping_rationale TEXT NOT NULL,
    logical_entity_source_mapping_status VARCHAR(20) NOT NULL DEFAULT 'active',
    logical_entity_source_mapping_is_locked BOOLEAN NOT NULL DEFAULT FALSE,
    created_time TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    created_by VARCHAR(255) NOT NULL DEFAULT CURRENT_USER,
    updated_time TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_by VARCHAR(255) NOT NULL DEFAULT CURRENT_USER,
    CONSTRAINT fk_logical_entity_source_model FOREIGN KEY (model_id)
        REFERENCES model.model (model_id) ON DELETE NO ACTION,
    CONSTRAINT fk_logical_entity_source_entity FOREIGN KEY (
        logical_entity_id,
        model_id
    ) REFERENCES workflow.logical_entity (logical_entity_id, model_id)
        ON DELETE NO ACTION,
    CONSTRAINT fk_logical_entity_source_scope FOREIGN KEY (
        model_id,
        source_object_id
    ) REFERENCES model.model_input_scope (model_id, object_id) ON DELETE NO ACTION,
    CONSTRAINT fk_logical_entity_source_assertion_record FOREIGN KEY (
        modeling_assertion_record_id,
        model_id
    ) REFERENCES model.modeling_assertion_record (
        modeling_assertion_record_id,
        model_id
    ) ON DELETE NO ACTION,
    CONSTRAINT uq_logical_entity_source_witness UNIQUE (
        logical_entity_source_mapping_id,
        logical_entity_id,
        source_object_id,
        model_id
    ),
    CONSTRAINT ck_logical_entity_source_typed_source CHECK (
        (
            support_source_type = 'object'
            AND source_object_id IS NOT NULL
            AND modeling_assertion_record_id IS NULL
        ) OR (
            support_source_type = 'assertion'
            AND modeling_assertion_record_id IS NOT NULL
            AND source_object_id IS NULL
        )
    ),
    CONSTRAINT ck_logical_entity_source_order CHECK (
        logical_entity_source_mapping_order IS NULL
        OR logical_entity_source_mapping_order > 0
    ),
    CONSTRAINT ck_logical_entity_source_rationale CHECK (
        reference.is_nonblank(logical_entity_source_mapping_rationale)
    ),
    CONSTRAINT ck_logical_entity_source_status CHECK (
        logical_entity_source_mapping_status IN (
            'active', 'inactive', 'deprecated'
        )
    )
);
```


[07_workflow_logical.sql:249](/Users/maazuddinmohammed/main/projects/gds_workbench_v2/database/07_workflow_logical.sql:249)

```sql
CREATE UNIQUE INDEX ux_logical_entity_source_object
    ON workflow.logical_entity_source_mapping (
        model_id,
        logical_entity_id,
        source_object_id
    ) WHERE support_source_type = 'object';
```


[07_workflow_logical.sql:255](/Users/maazuddinmohammed/main/projects/gds_workbench_v2/database/07_workflow_logical.sql:255)

```sql
CREATE UNIQUE INDEX ux_logical_entity_source_assertion
    ON workflow.logical_entity_source_mapping (
        model_id,
        logical_entity_id,
        modeling_assertion_record_id
    ) WHERE support_source_type = 'assertion';
```


[13_application_workflow_runs.sql:785](/Users/maazuddinmohammed/main/projects/gds_workbench_v2/database/13_application_workflow_runs.sql:785)

```sql
ALTER TABLE workflow.logical_entity_source_mapping
    ADD CONSTRAINT fk_logical_entity_source_mapping_workflow_run
    FOREIGN KEY (workflow_run_id, model_id)
    REFERENCES application.workflow_run (workflow_run_id, model_id)
    ON DELETE NO ACTION;
```


</details>

<details>
<summary><code>workflow.logical_attribute_source_mapping</code></summary>


[07_workflow_logical.sql:262](/Users/maazuddinmohammed/main/projects/gds_workbench_v2/database/07_workflow_logical.sql:262)

```sql
CREATE TABLE workflow.logical_attribute_source_mapping (
    logical_attribute_source_mapping_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    model_id BIGINT NOT NULL,
    agent_run_id VARCHAR(500),
    workflow_run_id BIGINT,
    logical_entity_source_mapping_id BIGINT,
    logical_entity_id BIGINT NOT NULL,
    logical_attribute_id BIGINT NOT NULL,
    support_source_type VARCHAR(20) NOT NULL,
    source_object_id BIGINT,
    source_attribute_id BIGINT,
    modeling_assertion_record_id BIGINT,
    logical_attribute_source_mapping_order INTEGER,
    logical_attribute_source_mapping_rationale TEXT NOT NULL,
    logical_attribute_source_mapping_status VARCHAR(20) NOT NULL DEFAULT 'active',
    logical_attribute_source_mapping_is_locked BOOLEAN NOT NULL DEFAULT FALSE,
    created_time TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    created_by VARCHAR(255) NOT NULL DEFAULT CURRENT_USER,
    updated_time TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_by VARCHAR(255) NOT NULL DEFAULT CURRENT_USER,
    CONSTRAINT fk_logical_attribute_source_model FOREIGN KEY (model_id)
        REFERENCES model.model (model_id) ON DELETE NO ACTION,
    CONSTRAINT fk_logical_attribute_source_parent FOREIGN KEY (
        logical_entity_source_mapping_id,
        logical_entity_id,
        source_object_id,
        model_id
    ) REFERENCES workflow.logical_entity_source_mapping (
        logical_entity_source_mapping_id,
        logical_entity_id,
        source_object_id,
        model_id
    ) ON DELETE NO ACTION,
    CONSTRAINT fk_logical_attribute_source_attribute FOREIGN KEY (
        logical_attribute_id,
        logical_entity_id,
        model_id
    ) REFERENCES workflow.logical_attribute (
        logical_attribute_id,
        logical_entity_id,
        model_id
    ) ON DELETE NO ACTION,
    CONSTRAINT fk_logical_attribute_source_physical FOREIGN KEY (
        source_attribute_id,
        source_object_id
    ) REFERENCES core.attribute (attribute_id, object_id) ON DELETE NO ACTION,
    CONSTRAINT fk_logical_attribute_source_assertion_record FOREIGN KEY (
        modeling_assertion_record_id,
        model_id
    ) REFERENCES model.modeling_assertion_record (
        modeling_assertion_record_id,
        model_id
    ) ON DELETE NO ACTION,
    CONSTRAINT ck_logical_attribute_source_typed_source CHECK (
        (
            support_source_type = 'attribute'
            AND logical_entity_source_mapping_id IS NOT NULL
            AND source_object_id IS NOT NULL
            AND source_attribute_id IS NOT NULL
            AND modeling_assertion_record_id IS NULL
        ) OR (
            support_source_type = 'assertion'
            AND modeling_assertion_record_id IS NOT NULL
            AND logical_entity_source_mapping_id IS NULL
            AND source_object_id IS NULL
            AND source_attribute_id IS NULL
        )
    ),
    CONSTRAINT ck_logical_attribute_source_order CHECK (
        logical_attribute_source_mapping_order IS NULL
        OR logical_attribute_source_mapping_order > 0
    ),
    CONSTRAINT ck_logical_attribute_source_rationale CHECK (
        reference.is_nonblank(logical_attribute_source_mapping_rationale)
    ),
    CONSTRAINT ck_logical_attribute_source_status CHECK (
        logical_attribute_source_mapping_status IN (
            'active', 'inactive', 'deprecated'
        )
    )
);
```


[07_workflow_logical.sql:344](/Users/maazuddinmohammed/main/projects/gds_workbench_v2/database/07_workflow_logical.sql:344)

```sql
CREATE UNIQUE INDEX ux_logical_attribute_source_physical
    ON workflow.logical_attribute_source_mapping (
        model_id,
        logical_entity_source_mapping_id,
        logical_attribute_id,
        source_attribute_id
    ) WHERE support_source_type = 'attribute';
```


[07_workflow_logical.sql:351](/Users/maazuddinmohammed/main/projects/gds_workbench_v2/database/07_workflow_logical.sql:351)

```sql
CREATE UNIQUE INDEX ux_logical_attribute_source_assertion
    ON workflow.logical_attribute_source_mapping (
        model_id,
        logical_attribute_id,
        modeling_assertion_record_id
    ) WHERE support_source_type = 'assertion';
```


[13_application_workflow_runs.sql:791](/Users/maazuddinmohammed/main/projects/gds_workbench_v2/database/13_application_workflow_runs.sql:791)

```sql
ALTER TABLE workflow.logical_attribute_source_mapping
    ADD CONSTRAINT fk_logical_attribute_source_mapping_workflow_run
    FOREIGN KEY (workflow_run_id, model_id)
    REFERENCES application.workflow_run (workflow_run_id, model_id)
    ON DELETE NO ACTION;
```


</details>

<details>
<summary><code>workflow.logical_relationship</code></summary>


[07_workflow_logical.sql:358](/Users/maazuddinmohammed/main/projects/gds_workbench_v2/database/07_workflow_logical.sql:358)

```sql
CREATE TABLE workflow.logical_relationship (
    logical_relationship_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    model_id BIGINT NOT NULL,
    agent_run_id VARCHAR(500),
    workflow_run_id BIGINT,
    logical_relationship_name VARCHAR(255) NOT NULL,
    logical_relationship_definition TEXT NOT NULL,
    logical_relationship_from_entity_id BIGINT NOT NULL,
    logical_relationship_from_attribute_id BIGINT NOT NULL,
    logical_relationship_to_entity_id BIGINT NOT NULL,
    logical_relationship_to_attribute_id BIGINT NOT NULL,
    logical_relationship_cardinality VARCHAR(50) NOT NULL,
    logical_relationship_confidence VARCHAR(10) NOT NULL DEFAULT 'medium',
    logical_relationship_basis TEXT NOT NULL,
    logical_relationship_cardinality_basis TEXT NOT NULL,
    logical_relationship_status VARCHAR(20) NOT NULL DEFAULT 'active',
    logical_relationship_is_locked BOOLEAN NOT NULL DEFAULT FALSE,
    created_time TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    created_by VARCHAR(255) NOT NULL DEFAULT CURRENT_USER,
    updated_time TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_by VARCHAR(255) NOT NULL DEFAULT CURRENT_USER,
    CONSTRAINT fk_logical_relationship_model FOREIGN KEY (model_id)
        REFERENCES model.model (model_id) ON DELETE NO ACTION,
    CONSTRAINT fk_logical_relationship_from_entity FOREIGN KEY (
        logical_relationship_from_entity_id,
        model_id
    ) REFERENCES workflow.logical_entity (logical_entity_id, model_id)
        ON DELETE NO ACTION,
    CONSTRAINT fk_logical_relationship_to_entity FOREIGN KEY (
        logical_relationship_to_entity_id,
        model_id
    ) REFERENCES workflow.logical_entity (logical_entity_id, model_id)
        ON DELETE NO ACTION,
    CONSTRAINT fk_logical_relationship_from_attribute FOREIGN KEY (
        logical_relationship_from_attribute_id,
        logical_relationship_from_entity_id,
        model_id
    ) REFERENCES workflow.logical_attribute (
        logical_attribute_id,
        logical_entity_id,
        model_id
    ) ON DELETE NO ACTION,
    CONSTRAINT fk_logical_relationship_to_attribute FOREIGN KEY (
        logical_relationship_to_attribute_id,
        logical_relationship_to_entity_id,
        model_id
    ) REFERENCES workflow.logical_attribute (
        logical_attribute_id,
        logical_entity_id,
        model_id
    ) ON DELETE NO ACTION,
    CONSTRAINT ck_logical_relationship_distinct_endpoints CHECK (
        (logical_relationship_from_entity_id, logical_relationship_from_attribute_id)
        <> (logical_relationship_to_entity_id, logical_relationship_to_attribute_id)
    ),
    CONSTRAINT ck_logical_relationship_name CHECK (
        reference.is_nonblank(logical_relationship_name)
    ),
    CONSTRAINT ck_logical_relationship_definition CHECK (
        reference.is_nonblank(logical_relationship_definition)
    ),
    CONSTRAINT ck_logical_relationship_cardinality CHECK (
        logical_relationship_cardinality IN (
            'one_to_one', 'one_to_many', 'many_to_one', 'many_to_many'
        )
    ),
    CONSTRAINT ck_logical_relationship_confidence CHECK (
        logical_relationship_confidence IN ('low', 'medium', 'high')
    ),
    CONSTRAINT ck_logical_relationship_bases CHECK (
        reference.is_nonblank(logical_relationship_basis)
        AND reference.is_nonblank(logical_relationship_cardinality_basis)
    ),
    CONSTRAINT ck_logical_relationship_status CHECK (
        logical_relationship_status IN ('active', 'inactive', 'deprecated')
    )
);
```


[07_workflow_logical.sql:436](/Users/maazuddinmohammed/main/projects/gds_workbench_v2/database/07_workflow_logical.sql:436)

```sql
CREATE UNIQUE INDEX ux_logical_relationship_identity
    ON workflow.logical_relationship (
        model_id,
        logical_relationship_from_entity_id,
        logical_relationship_from_attribute_id,
        logical_relationship_to_entity_id,
        logical_relationship_to_attribute_id,
        lower(btrim(logical_relationship_name))
    );
```


[13_application_workflow_runs.sql:797](/Users/maazuddinmohammed/main/projects/gds_workbench_v2/database/13_application_workflow_runs.sql:797)

```sql
ALTER TABLE workflow.logical_relationship
    ADD CONSTRAINT fk_logical_relationship_workflow_run
    FOREIGN KEY (workflow_run_id, model_id)
    REFERENCES application.workflow_run (workflow_run_id, model_id)
    ON DELETE NO ACTION;
```


</details>

<details>
<summary><code>workflow.dimensional_submodel</code></summary>


[08_workflow_dimensional.sql:3](/Users/maazuddinmohammed/main/projects/gds_workbench_v2/database/08_workflow_dimensional.sql:3)

```sql
CREATE TABLE workflow.dimensional_submodel (
    dimensional_submodel_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    model_id BIGINT NOT NULL,
    agent_run_id VARCHAR(500),
    workflow_run_id BIGINT,
    dimensional_submodel_name VARCHAR(255) NOT NULL,
    dimensional_submodel_definition TEXT NOT NULL,
    dimensional_submodel_status VARCHAR(20) NOT NULL DEFAULT 'active',
    dimensional_submodel_is_locked BOOLEAN NOT NULL DEFAULT FALSE,
    created_time TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    created_by VARCHAR(255) NOT NULL DEFAULT CURRENT_USER,
    updated_time TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_by VARCHAR(255) NOT NULL DEFAULT CURRENT_USER,
    CONSTRAINT fk_dimensional_submodel_model FOREIGN KEY (model_id)
        REFERENCES model.model (model_id) ON DELETE NO ACTION,
    CONSTRAINT uq_dimensional_submodel_id_model
        UNIQUE (dimensional_submodel_id, model_id),
    CONSTRAINT ck_dimensional_submodel_name CHECK (
        reference.is_nonblank(dimensional_submodel_name)
    ),
    CONSTRAINT ck_dimensional_submodel_definition CHECK (
        reference.is_nonblank(dimensional_submodel_definition)
    ),
    CONSTRAINT ck_dimensional_submodel_status CHECK (
        dimensional_submodel_status IN (
            'active', 'inactive', 'deprecated'
        )
    )
);
```


[08_workflow_dimensional.sql:33](/Users/maazuddinmohammed/main/projects/gds_workbench_v2/database/08_workflow_dimensional.sql:33)

```sql
CREATE UNIQUE INDEX ux_dimensional_submodel_effective_name
    ON workflow.dimensional_submodel (
        model_id,
        lower(btrim(dimensional_submodel_name))
    ) WHERE dimensional_submodel_status = 'active';
```


[13_application_workflow_runs.sql:803](/Users/maazuddinmohammed/main/projects/gds_workbench_v2/database/13_application_workflow_runs.sql:803)

```sql
ALTER TABLE workflow.dimensional_submodel
    ADD CONSTRAINT fk_dimensional_submodel_workflow_run
    FOREIGN KEY (workflow_run_id, model_id)
    REFERENCES application.workflow_run (workflow_run_id, model_id)
    ON DELETE NO ACTION;
```


</details>

<details>
<summary><code>workflow.dimensional_entity</code></summary>


[08_workflow_dimensional.sql:39](/Users/maazuddinmohammed/main/projects/gds_workbench_v2/database/08_workflow_dimensional.sql:39)

```sql
CREATE TABLE workflow.dimensional_entity (
    dimensional_entity_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    model_id BIGINT NOT NULL,
    agent_run_id VARCHAR(500),
    workflow_run_id BIGINT,
    dimensional_entity_name VARCHAR(255) NOT NULL,
    dimensional_entity_definition TEXT NOT NULL,
    dimensional_entity_type VARCHAR(20) NOT NULL,
    dimensional_fact_type VARCHAR(30),
    dimensional_entity_grain_definition TEXT,
    dimensional_entity_dependency_order INTEGER NOT NULL DEFAULT 0,
    dimensional_entity_confidence VARCHAR(10) NOT NULL DEFAULT 'medium',
    dimensional_entity_status VARCHAR(20) NOT NULL DEFAULT 'active',
    dimensional_entity_is_locked BOOLEAN NOT NULL DEFAULT FALSE,
    created_time TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    created_by VARCHAR(255) NOT NULL DEFAULT CURRENT_USER,
    updated_time TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_by VARCHAR(255) NOT NULL DEFAULT CURRENT_USER,
    CONSTRAINT fk_dimensional_entity_model FOREIGN KEY (model_id)
        REFERENCES model.model (model_id) ON DELETE NO ACTION,
    CONSTRAINT uq_dimensional_entity_id_model
        UNIQUE (dimensional_entity_id, model_id),
    CONSTRAINT ck_dimensional_entity_name CHECK (
        reference.is_nonblank(dimensional_entity_name)
    ),
    CONSTRAINT ck_dimensional_entity_definition CHECK (
        reference.is_nonblank(dimensional_entity_definition)
    ),
    CONSTRAINT ck_dimensional_entity_type CHECK (
        dimensional_entity_type IN ('fact', 'dimension', 'bridge')
    ),
    CONSTRAINT ck_dimensional_fact_type CHECK (
        (
            dimensional_entity_type = 'fact'
            AND dimensional_fact_type IN (
                'transaction', 'periodic_snapshot',
                'accumulating_snapshot', 'factless'
            )
        ) OR (
            dimensional_entity_type <> 'fact'
            AND dimensional_fact_type IS NULL
        )
    ),
    CONSTRAINT ck_dimensional_entity_grain CHECK (
        (
            dimensional_entity_type IN ('fact', 'bridge')
            AND reference.is_nonblank(dimensional_entity_grain_definition)
        ) OR (
            dimensional_entity_type = 'dimension'
            AND (
                dimensional_entity_grain_definition IS NULL
                OR reference.is_nonblank(dimensional_entity_grain_definition)
            )
        )
    ),
    CONSTRAINT ck_dimensional_entity_dependency_order CHECK (
        dimensional_entity_dependency_order >= 0
    ),
    CONSTRAINT ck_dimensional_entity_confidence CHECK (
        dimensional_entity_confidence IN ('low', 'medium', 'high')
    ),
    CONSTRAINT ck_dimensional_entity_status CHECK (
        dimensional_entity_status IN (
            'active', 'inactive', 'deprecated'
        )
    )
);
```


[08_workflow_dimensional.sql:107](/Users/maazuddinmohammed/main/projects/gds_workbench_v2/database/08_workflow_dimensional.sql:107)

```sql
CREATE UNIQUE INDEX ux_dimensional_entity_effective_name
    ON workflow.dimensional_entity (
        model_id,
        lower(btrim(dimensional_entity_name))
    ) WHERE dimensional_entity_status = 'active';
```


[13_application_workflow_runs.sql:809](/Users/maazuddinmohammed/main/projects/gds_workbench_v2/database/13_application_workflow_runs.sql:809)

```sql
ALTER TABLE workflow.dimensional_entity
    ADD CONSTRAINT fk_dimensional_entity_workflow_run
    FOREIGN KEY (workflow_run_id, model_id)
    REFERENCES application.workflow_run (workflow_run_id, model_id)
    ON DELETE NO ACTION;
```


</details>

<details>
<summary><code>workflow.dimensional_entity_submodel</code></summary>


[08_workflow_dimensional.sql:113](/Users/maazuddinmohammed/main/projects/gds_workbench_v2/database/08_workflow_dimensional.sql:113)

```sql
CREATE TABLE workflow.dimensional_entity_submodel (
    dimensional_entity_submodel_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    model_id BIGINT NOT NULL,
    agent_run_id VARCHAR(500),
    workflow_run_id BIGINT,
    dimensional_entity_id BIGINT NOT NULL,
    dimensional_submodel_id BIGINT NOT NULL,
    dimensional_entity_submodel_status VARCHAR(20) NOT NULL DEFAULT 'active',
    dimensional_entity_submodel_is_locked BOOLEAN NOT NULL DEFAULT FALSE,
    created_time TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    created_by VARCHAR(255) NOT NULL DEFAULT CURRENT_USER,
    updated_time TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_by VARCHAR(255) NOT NULL DEFAULT CURRENT_USER,
    CONSTRAINT fk_dimensional_entity_submodel_model FOREIGN KEY (model_id)
        REFERENCES model.model (model_id) ON DELETE NO ACTION,
    CONSTRAINT fk_dimensional_entity_submodel_entity FOREIGN KEY (
        dimensional_entity_id,
        model_id
    ) REFERENCES workflow.dimensional_entity (dimensional_entity_id, model_id)
        ON DELETE NO ACTION,
    CONSTRAINT fk_dimensional_entity_submodel_submodel FOREIGN KEY (
        dimensional_submodel_id,
        model_id
    ) REFERENCES workflow.dimensional_submodel (dimensional_submodel_id, model_id)
        ON DELETE NO ACTION,
    CONSTRAINT ck_dimensional_entity_submodel_status CHECK (
        dimensional_entity_submodel_status IN (
            'active', 'inactive', 'deprecated'
        )
    )
);
```


[08_workflow_dimensional.sql:145](/Users/maazuddinmohammed/main/projects/gds_workbench_v2/database/08_workflow_dimensional.sql:145)

```sql
CREATE UNIQUE INDEX ux_dimensional_entity_submodel_effective
    ON workflow.dimensional_entity_submodel (
        model_id,
        dimensional_entity_id,
        dimensional_submodel_id
    ) WHERE dimensional_entity_submodel_status = 'active';
```


[13_application_workflow_runs.sql:815](/Users/maazuddinmohammed/main/projects/gds_workbench_v2/database/13_application_workflow_runs.sql:815)

```sql
ALTER TABLE workflow.dimensional_entity_submodel
    ADD CONSTRAINT fk_dimensional_entity_submodel_workflow_run
    FOREIGN KEY (workflow_run_id, model_id)
    REFERENCES application.workflow_run (workflow_run_id, model_id)
    ON DELETE NO ACTION;
```


</details>

<details>
<summary><code>workflow.dimensional_attribute</code></summary>


[08_workflow_dimensional.sql:152](/Users/maazuddinmohammed/main/projects/gds_workbench_v2/database/08_workflow_dimensional.sql:152)

```sql
CREATE TABLE workflow.dimensional_attribute (
    dimensional_attribute_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    model_id BIGINT NOT NULL,
    agent_run_id VARCHAR(500),
    workflow_run_id BIGINT,
    dimensional_entity_id BIGINT NOT NULL,
    dimensional_attribute_name VARCHAR(255) NOT NULL,
    dimensional_attribute_definition TEXT NOT NULL,
    dimensional_attribute_data_type VARCHAR(100) NOT NULL,
    dimensional_attribute_is_nullable BOOLEAN NOT NULL DEFAULT TRUE,
    dimensional_attribute_ordinal_position INTEGER NOT NULL,
    dimensional_attribute_role VARCHAR(30) NOT NULL,
    dimensional_attribute_key_role VARCHAR(20) NOT NULL DEFAULT 'none',
    dimensional_attribute_is_grain_component BOOLEAN NOT NULL DEFAULT FALSE,
    dimensional_attribute_additivity VARCHAR(30),
    dimensional_attribute_default_aggregation VARCHAR(100),
    dimensional_attribute_aggregation_basis TEXT,
    dimensional_attribute_change_behavior VARCHAR(20),
    dimensional_attribute_is_audit_column BOOLEAN NOT NULL DEFAULT FALSE,
    dimensional_attribute_confidence VARCHAR(10) NOT NULL DEFAULT 'medium',
    dimensional_attribute_status VARCHAR(20) NOT NULL DEFAULT 'active',
    dimensional_attribute_is_locked BOOLEAN NOT NULL DEFAULT FALSE,
    created_time TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    created_by VARCHAR(255) NOT NULL DEFAULT CURRENT_USER,
    updated_time TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_by VARCHAR(255) NOT NULL DEFAULT CURRENT_USER,
    CONSTRAINT fk_dimensional_attribute_model FOREIGN KEY (model_id)
        REFERENCES model.model (model_id) ON DELETE NO ACTION,
    CONSTRAINT fk_dimensional_attribute_entity FOREIGN KEY (
        dimensional_entity_id,
        model_id
    ) REFERENCES workflow.dimensional_entity (dimensional_entity_id, model_id)
        ON DELETE NO ACTION,
    CONSTRAINT uq_dimensional_attribute_id_model
        UNIQUE (dimensional_attribute_id, model_id),
    CONSTRAINT uq_dimensional_attribute_witness
        UNIQUE (dimensional_attribute_id, dimensional_entity_id, model_id),
    CONSTRAINT ck_dimensional_attribute_name CHECK (
        reference.is_nonblank(dimensional_attribute_name)
    ),
    CONSTRAINT ck_dimensional_attribute_definition CHECK (
        reference.is_nonblank(dimensional_attribute_definition)
    ),
    CONSTRAINT ck_dimensional_attribute_data_type CHECK (
        reference.is_nonblank(dimensional_attribute_data_type)
    ),
    CONSTRAINT ck_dimensional_attribute_ordinal CHECK (
        dimensional_attribute_ordinal_position > 0
    ),
    CONSTRAINT ck_dimensional_attribute_role CHECK (
        dimensional_attribute_role IN (
            'key', 'descriptor', 'measure', 'degenerate_dimension',
            'bridge_weight', 'technical', 'audit'
        )
    ),
    CONSTRAINT ck_dimensional_attribute_key_role CHECK (
        dimensional_attribute_key_role IN ('none', 'surrogate', 'business', 'foreign')
        AND (
            dimensional_attribute_key_role = 'none'
            OR dimensional_attribute_role IN ('key', 'technical')
        )
    ),
    CONSTRAINT ck_dimensional_measure_policy CHECK (
        (
            dimensional_attribute_role = 'measure'
            AND dimensional_attribute_additivity IN (
                'additive', 'semi_additive', 'non_additive'
            )
            AND reference.is_nonblank(dimensional_attribute_default_aggregation)
            AND (
                dimensional_attribute_additivity = 'additive'
                OR reference.is_nonblank(dimensional_attribute_aggregation_basis)
            )
        ) OR (
            dimensional_attribute_role <> 'measure'
            AND dimensional_attribute_additivity IS NULL
            AND dimensional_attribute_default_aggregation IS NULL
            AND dimensional_attribute_aggregation_basis IS NULL
        )
    ),
    CONSTRAINT ck_dimensional_change_behavior CHECK (
        dimensional_attribute_change_behavior IS NULL
        OR dimensional_attribute_change_behavior IN (
            'fixed', 'overwrite', 'historize'
        )
    ),
    CONSTRAINT ck_dimensional_audit_role CHECK (
        dimensional_attribute_is_audit_column
        = (dimensional_attribute_role = 'audit')
    ),
    CONSTRAINT ck_dimensional_attribute_confidence CHECK (
        dimensional_attribute_confidence IN ('low', 'medium', 'high')
    ),
    CONSTRAINT ck_dimensional_attribute_status CHECK (
        dimensional_attribute_status IN (
            'active', 'inactive', 'deprecated'
        )
    )
);
```


[08_workflow_dimensional.sql:252](/Users/maazuddinmohammed/main/projects/gds_workbench_v2/database/08_workflow_dimensional.sql:252)

```sql
CREATE UNIQUE INDEX ux_dimensional_attribute_effective_name
    ON workflow.dimensional_attribute (
        model_id,
        dimensional_entity_id,
        lower(btrim(dimensional_attribute_name))
    ) WHERE dimensional_attribute_status = 'active';
```


[13_application_workflow_runs.sql:821](/Users/maazuddinmohammed/main/projects/gds_workbench_v2/database/13_application_workflow_runs.sql:821)

```sql
ALTER TABLE workflow.dimensional_attribute
    ADD CONSTRAINT fk_dimensional_attribute_workflow_run
    FOREIGN KEY (workflow_run_id, model_id)
    REFERENCES application.workflow_run (workflow_run_id, model_id)
    ON DELETE NO ACTION;
```


</details>

<details>
<summary><code>workflow.dimensional_entity_source_mapping</code></summary>


[08_workflow_dimensional.sql:259](/Users/maazuddinmohammed/main/projects/gds_workbench_v2/database/08_workflow_dimensional.sql:259)

```sql
CREATE TABLE workflow.dimensional_entity_source_mapping (
    dimensional_entity_source_mapping_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    model_id BIGINT NOT NULL,
    agent_run_id VARCHAR(500),
    workflow_run_id BIGINT,
    dimensional_entity_id BIGINT NOT NULL,
    support_source_type VARCHAR(20) NOT NULL,
    source_object_id BIGINT,
    modeling_assertion_record_id BIGINT,
    dimensional_entity_source_role VARCHAR(255) NOT NULL,
    dimensional_entity_source_mapping_order INTEGER,
    dimensional_entity_source_mapping_rationale TEXT NOT NULL,
    dimensional_entity_source_mapping_status VARCHAR(20) NOT NULL DEFAULT 'active',
    dimensional_entity_source_mapping_is_locked BOOLEAN NOT NULL DEFAULT FALSE,
    created_time TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    created_by VARCHAR(255) NOT NULL DEFAULT CURRENT_USER,
    updated_time TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_by VARCHAR(255) NOT NULL DEFAULT CURRENT_USER,
    CONSTRAINT fk_dimensional_entity_source_model FOREIGN KEY (model_id)
        REFERENCES model.model (model_id) ON DELETE NO ACTION,
    CONSTRAINT fk_dimensional_entity_source_entity FOREIGN KEY (
        dimensional_entity_id,
        model_id
    ) REFERENCES workflow.dimensional_entity (dimensional_entity_id, model_id)
        ON DELETE NO ACTION,
    CONSTRAINT fk_dimensional_entity_source_assertion_record FOREIGN KEY (
        modeling_assertion_record_id,
        model_id
    ) REFERENCES model.modeling_assertion_record (
        modeling_assertion_record_id,
        model_id
    ) ON DELETE NO ACTION,
    CONSTRAINT uq_dimensional_entity_source_witness UNIQUE (
        dimensional_entity_source_mapping_id,
        dimensional_entity_id,
        source_object_id,
        model_id
    ),
    CONSTRAINT ck_dimensional_entity_source_typed_source CHECK (
        (
            support_source_type = 'object'
            AND source_object_id IS NOT NULL
            AND modeling_assertion_record_id IS NULL
        ) OR (
            support_source_type = 'assertion'
            AND modeling_assertion_record_id IS NOT NULL
            AND source_object_id IS NULL
        )
    ),
    CONSTRAINT ck_dimensional_entity_source_role CHECK (
        reference.is_nonblank(dimensional_entity_source_role)
    ),
    CONSTRAINT ck_dimensional_entity_source_order CHECK (
        dimensional_entity_source_mapping_order IS NULL
        OR dimensional_entity_source_mapping_order > 0
    ),
    CONSTRAINT ck_dimensional_entity_source_rationale CHECK (
        reference.is_nonblank(dimensional_entity_source_mapping_rationale)
    ),
    CONSTRAINT ck_dimensional_entity_source_status CHECK (
        dimensional_entity_source_mapping_status IN (
            'active', 'inactive', 'deprecated'
        )
    )
);
```


[08_workflow_dimensional.sql:325](/Users/maazuddinmohammed/main/projects/gds_workbench_v2/database/08_workflow_dimensional.sql:325)

```sql
CREATE UNIQUE INDEX ux_dimensional_entity_source_object_effective
    ON workflow.dimensional_entity_source_mapping (
        model_id,
        dimensional_entity_id,
        source_object_id
    ) WHERE support_source_type = 'object'
        AND dimensional_entity_source_mapping_status = 'active';
```


[08_workflow_dimensional.sql:332](/Users/maazuddinmohammed/main/projects/gds_workbench_v2/database/08_workflow_dimensional.sql:332)

```sql
CREATE UNIQUE INDEX ux_dimensional_entity_source_assertion_effective
    ON workflow.dimensional_entity_source_mapping (
        model_id,
        dimensional_entity_id,
        modeling_assertion_record_id
    ) WHERE support_source_type = 'assertion'
        AND dimensional_entity_source_mapping_status = 'active';
```


[09_workflow_mapping.sql:113](/Users/maazuddinmohammed/main/projects/gds_workbench_v2/database/09_workflow_mapping.sql:113)

```sql
ALTER TABLE workflow.dimensional_entity_source_mapping
    ADD CONSTRAINT fk_dimensional_entity_source_binding FOREIGN KEY (
        model_id,
        source_object_id
    ) REFERENCES workflow.model_object_binding (model_id, object_id)
        ON DELETE NO ACTION;
```


[13_application_workflow_runs.sql:827](/Users/maazuddinmohammed/main/projects/gds_workbench_v2/database/13_application_workflow_runs.sql:827)

```sql
ALTER TABLE workflow.dimensional_entity_source_mapping
    ADD CONSTRAINT fk_dimensional_entity_source_mapping_workflow_run
    FOREIGN KEY (workflow_run_id, model_id)
    REFERENCES application.workflow_run (workflow_run_id, model_id)
    ON DELETE NO ACTION;
```


</details>

<details>
<summary><code>workflow.dimensional_attribute_source_mapping</code></summary>


[08_workflow_dimensional.sql:340](/Users/maazuddinmohammed/main/projects/gds_workbench_v2/database/08_workflow_dimensional.sql:340)

```sql
CREATE TABLE workflow.dimensional_attribute_source_mapping (
    dimensional_attribute_source_mapping_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    model_id BIGINT NOT NULL,
    agent_run_id VARCHAR(500),
    workflow_run_id BIGINT,
    dimensional_entity_source_mapping_id BIGINT,
    dimensional_entity_id BIGINT NOT NULL,
    dimensional_attribute_id BIGINT NOT NULL,
    support_source_type VARCHAR(20) NOT NULL,
    source_object_id BIGINT,
    source_attribute_id BIGINT,
    modeling_assertion_record_id BIGINT,
    dimensional_attribute_source_mapping_order INTEGER,
    dimensional_attribute_source_mapping_rationale TEXT NOT NULL,
    dimensional_attribute_source_mapping_status VARCHAR(20) NOT NULL DEFAULT 'active',
    dimensional_attribute_source_mapping_is_locked BOOLEAN NOT NULL DEFAULT FALSE,
    created_time TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    created_by VARCHAR(255) NOT NULL DEFAULT CURRENT_USER,
    updated_time TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_by VARCHAR(255) NOT NULL DEFAULT CURRENT_USER,
    CONSTRAINT fk_dimensional_attribute_source_model FOREIGN KEY (model_id)
        REFERENCES model.model (model_id) ON DELETE NO ACTION,
    CONSTRAINT fk_dimensional_attribute_source_parent FOREIGN KEY (
        dimensional_entity_source_mapping_id,
        dimensional_entity_id,
        source_object_id,
        model_id
    ) REFERENCES workflow.dimensional_entity_source_mapping (
        dimensional_entity_source_mapping_id,
        dimensional_entity_id,
        source_object_id,
        model_id
    ) ON DELETE NO ACTION,
    CONSTRAINT fk_dimensional_attribute_source_attribute FOREIGN KEY (
        dimensional_attribute_id,
        dimensional_entity_id,
        model_id
    ) REFERENCES workflow.dimensional_attribute (
        dimensional_attribute_id,
        dimensional_entity_id,
        model_id
    ) ON DELETE NO ACTION,
    CONSTRAINT fk_dimensional_attribute_source_physical FOREIGN KEY (
        source_attribute_id,
        source_object_id
    ) REFERENCES core.attribute (attribute_id, object_id) ON DELETE NO ACTION,
    CONSTRAINT fk_dimensional_attribute_source_assertion_record FOREIGN KEY (
        modeling_assertion_record_id,
        model_id
    ) REFERENCES model.modeling_assertion_record (
        modeling_assertion_record_id,
        model_id
    ) ON DELETE NO ACTION,
    CONSTRAINT ck_dimensional_attribute_source_typed_source CHECK (
        (
            support_source_type = 'attribute'
            AND dimensional_entity_source_mapping_id IS NOT NULL
            AND source_object_id IS NOT NULL
            AND source_attribute_id IS NOT NULL
            AND modeling_assertion_record_id IS NULL
        ) OR (
            support_source_type = 'assertion'
            AND modeling_assertion_record_id IS NOT NULL
            AND dimensional_entity_source_mapping_id IS NULL
            AND source_object_id IS NULL
            AND source_attribute_id IS NULL
        )
    ),
    CONSTRAINT ck_dimensional_attribute_source_order CHECK (
        dimensional_attribute_source_mapping_order IS NULL
        OR dimensional_attribute_source_mapping_order > 0
    ),
    CONSTRAINT ck_dimensional_attribute_source_rationale CHECK (
        reference.is_nonblank(dimensional_attribute_source_mapping_rationale)
    ),
    CONSTRAINT ck_dimensional_attribute_source_status CHECK (
        dimensional_attribute_source_mapping_status IN (
            'active', 'inactive', 'deprecated'
        )
    )
);
```


[08_workflow_dimensional.sql:422](/Users/maazuddinmohammed/main/projects/gds_workbench_v2/database/08_workflow_dimensional.sql:422)

```sql
CREATE UNIQUE INDEX ux_dimensional_attribute_source_physical_effective
    ON workflow.dimensional_attribute_source_mapping (
        model_id,
        dimensional_entity_source_mapping_id,
        dimensional_attribute_id,
        source_attribute_id
    ) WHERE support_source_type = 'attribute'
        AND dimensional_attribute_source_mapping_status = 'active';
```


[08_workflow_dimensional.sql:430](/Users/maazuddinmohammed/main/projects/gds_workbench_v2/database/08_workflow_dimensional.sql:430)

```sql
CREATE UNIQUE INDEX ux_dimensional_attribute_source_assertion_effective
    ON workflow.dimensional_attribute_source_mapping (
        model_id,
        dimensional_attribute_id,
        modeling_assertion_record_id
    ) WHERE support_source_type = 'assertion'
        AND dimensional_attribute_source_mapping_status = 'active';
```


[13_application_workflow_runs.sql:833](/Users/maazuddinmohammed/main/projects/gds_workbench_v2/database/13_application_workflow_runs.sql:833)

```sql
ALTER TABLE workflow.dimensional_attribute_source_mapping
    ADD CONSTRAINT fk_dimensional_attribute_source_mapping_workflow_run
    FOREIGN KEY (workflow_run_id, model_id)
    REFERENCES application.workflow_run (workflow_run_id, model_id)
    ON DELETE NO ACTION;
```


</details>

<details>
<summary><code>workflow.dimensional_relationship</code></summary>


[08_workflow_dimensional.sql:438](/Users/maazuddinmohammed/main/projects/gds_workbench_v2/database/08_workflow_dimensional.sql:438)

```sql
CREATE TABLE workflow.dimensional_relationship (
    dimensional_relationship_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    model_id BIGINT NOT NULL,
    agent_run_id VARCHAR(500),
    workflow_run_id BIGINT,
    dimensional_relationship_name VARCHAR(255) NOT NULL,
    dimensional_relationship_definition TEXT NOT NULL,
    dimensional_relationship_from_entity_id BIGINT NOT NULL,
    dimensional_relationship_from_attribute_id BIGINT NOT NULL,
    dimensional_relationship_to_entity_id BIGINT NOT NULL,
    dimensional_relationship_to_attribute_id BIGINT NOT NULL,
    dimensional_relationship_kind VARCHAR(50) NOT NULL,
    dimensional_relationship_cardinality VARCHAR(50) NOT NULL,
    dimensional_relationship_is_optional BOOLEAN NOT NULL,
    dimensional_relationship_role_name VARCHAR(255),
    dimensional_relationship_confidence VARCHAR(10) NOT NULL DEFAULT 'medium',
    dimensional_relationship_basis TEXT NOT NULL,
    dimensional_relationship_cardinality_basis TEXT NOT NULL,
    dimensional_relationship_status VARCHAR(20) NOT NULL DEFAULT 'active',
    dimensional_relationship_is_locked BOOLEAN NOT NULL DEFAULT FALSE,
    created_time TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    created_by VARCHAR(255) NOT NULL DEFAULT CURRENT_USER,
    updated_time TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_by VARCHAR(255) NOT NULL DEFAULT CURRENT_USER,
    CONSTRAINT fk_dimensional_relationship_model FOREIGN KEY (model_id)
        REFERENCES model.model (model_id) ON DELETE NO ACTION,
    CONSTRAINT fk_dimensional_relationship_from_entity FOREIGN KEY (
        dimensional_relationship_from_entity_id,
        model_id
    ) REFERENCES workflow.dimensional_entity (dimensional_entity_id, model_id)
        ON DELETE NO ACTION,
    CONSTRAINT fk_dimensional_relationship_to_entity FOREIGN KEY (
        dimensional_relationship_to_entity_id,
        model_id
    ) REFERENCES workflow.dimensional_entity (dimensional_entity_id, model_id)
        ON DELETE NO ACTION,
    CONSTRAINT fk_dimensional_relationship_from_attribute FOREIGN KEY (
        dimensional_relationship_from_attribute_id,
        dimensional_relationship_from_entity_id,
        model_id
    ) REFERENCES workflow.dimensional_attribute (
        dimensional_attribute_id,
        dimensional_entity_id,
        model_id
    ) ON DELETE NO ACTION,
    CONSTRAINT fk_dimensional_relationship_to_attribute FOREIGN KEY (
        dimensional_relationship_to_attribute_id,
        dimensional_relationship_to_entity_id,
        model_id
    ) REFERENCES workflow.dimensional_attribute (
        dimensional_attribute_id,
        dimensional_entity_id,
        model_id
    ) ON DELETE NO ACTION,
    CONSTRAINT ck_dimensional_relationship_distinct_endpoints CHECK (
        (
            dimensional_relationship_from_entity_id,
            dimensional_relationship_from_attribute_id
        ) <> (
            dimensional_relationship_to_entity_id,
            dimensional_relationship_to_attribute_id
        )
    ),
    CONSTRAINT ck_dimensional_relationship_name CHECK (
        reference.is_nonblank(dimensional_relationship_name)
    ),
    CONSTRAINT ck_dimensional_relationship_definition CHECK (
        reference.is_nonblank(dimensional_relationship_definition)
    ),
    CONSTRAINT ck_dimensional_relationship_kind CHECK (
        reference.is_nonblank(dimensional_relationship_kind)
    ),
    CONSTRAINT ck_dimensional_relationship_cardinality CHECK (
        dimensional_relationship_cardinality IN (
            'one_to_one', 'one_to_many', 'many_to_one', 'many_to_many'
        )
    ),
    CONSTRAINT ck_dimensional_relationship_role CHECK (
        dimensional_relationship_role_name IS NULL
        OR reference.is_nonblank(dimensional_relationship_role_name)
    ),
    CONSTRAINT ck_dimensional_relationship_confidence CHECK (
        dimensional_relationship_confidence IN ('low', 'medium', 'high')
    ),
    CONSTRAINT ck_dimensional_relationship_bases CHECK (
        reference.is_nonblank(dimensional_relationship_basis)
        AND reference.is_nonblank(dimensional_relationship_cardinality_basis)
    ),
    CONSTRAINT ck_dimensional_relationship_status CHECK (
        dimensional_relationship_status IN (
            'active', 'inactive', 'deprecated'
        )
    )
);
```


[08_workflow_dimensional.sql:533](/Users/maazuddinmohammed/main/projects/gds_workbench_v2/database/08_workflow_dimensional.sql:533)

```sql
CREATE UNIQUE INDEX ux_dimensional_relationship_effective_identity
    ON workflow.dimensional_relationship (
        model_id,
        dimensional_relationship_from_entity_id,
        dimensional_relationship_from_attribute_id,
        dimensional_relationship_to_entity_id,
        dimensional_relationship_to_attribute_id,
        lower(btrim(dimensional_relationship_kind)),
        coalesce(lower(btrim(dimensional_relationship_role_name)), '')
    ) WHERE dimensional_relationship_status = 'active';
```


[13_application_workflow_runs.sql:839](/Users/maazuddinmohammed/main/projects/gds_workbench_v2/database/13_application_workflow_runs.sql:839)

```sql
ALTER TABLE workflow.dimensional_relationship
    ADD CONSTRAINT fk_dimensional_relationship_workflow_run
    FOREIGN KEY (workflow_run_id, model_id)
    REFERENCES application.workflow_run (workflow_run_id, model_id)
    ON DELETE NO ACTION;
```


</details>

<details>
<summary><code>workflow.model_object_binding</code></summary>


[09_workflow_mapping.sql:3](/Users/maazuddinmohammed/main/projects/gds_workbench_v2/database/09_workflow_mapping.sql:3)

```sql
CREATE TABLE workflow.model_object_binding (
    model_object_binding_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    model_id BIGINT NOT NULL,
    object_id BIGINT NOT NULL,
    modeled_entity_type VARCHAR(30) NOT NULL,
    logical_entity_id BIGINT,
    dimensional_entity_id BIGINT,
    agent_run_id VARCHAR(500),
    workflow_run_id BIGINT,
    model_object_binding_status VARCHAR(20) NOT NULL DEFAULT 'active',
    model_object_binding_is_locked BOOLEAN NOT NULL DEFAULT FALSE,
    created_time TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    created_by VARCHAR(255) NOT NULL DEFAULT CURRENT_USER,
    updated_time TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_by VARCHAR(255) NOT NULL DEFAULT CURRENT_USER,
    CONSTRAINT fk_model_object_binding_model FOREIGN KEY (model_id)
        REFERENCES model.model (model_id) ON DELETE NO ACTION,
    CONSTRAINT fk_model_object_binding_object FOREIGN KEY (object_id)
        REFERENCES core.object (object_id) ON DELETE NO ACTION,
    CONSTRAINT fk_model_object_binding_logical_entity FOREIGN KEY (
        logical_entity_id,
        model_id
    ) REFERENCES workflow.logical_entity (
        logical_entity_id,
        model_id
    ) ON DELETE NO ACTION,
    CONSTRAINT fk_model_object_binding_dimensional_entity FOREIGN KEY (
        dimensional_entity_id,
        model_id
    ) REFERENCES workflow.dimensional_entity (
        dimensional_entity_id,
        model_id
    ) ON DELETE NO ACTION,
    CONSTRAINT uq_model_object_binding_model_object
        UNIQUE (model_id, object_id),
    CONSTRAINT ck_model_object_binding_typed_entity CHECK (
        (
            modeled_entity_type = 'logical_entity'
            AND logical_entity_id IS NOT NULL
            AND dimensional_entity_id IS NULL
        ) OR (
            modeled_entity_type = 'dimensional_entity'
            AND dimensional_entity_id IS NOT NULL
            AND logical_entity_id IS NULL
        )
    ),
    CONSTRAINT ck_model_object_binding_status CHECK (
        model_object_binding_status IN ('active', 'inactive', 'deprecated')
    )
);
```


[09_workflow_mapping.sql:54](/Users/maazuddinmohammed/main/projects/gds_workbench_v2/database/09_workflow_mapping.sql:54)

```sql
CREATE UNIQUE INDEX ux_model_object_binding_logical_entity
    ON workflow.model_object_binding (model_id, logical_entity_id)
    WHERE modeled_entity_type = 'logical_entity';
```


[09_workflow_mapping.sql:58](/Users/maazuddinmohammed/main/projects/gds_workbench_v2/database/09_workflow_mapping.sql:58)

```sql
CREATE UNIQUE INDEX ux_model_object_binding_dimensional_entity
    ON workflow.model_object_binding (model_id, dimensional_entity_id)
    WHERE modeled_entity_type = 'dimensional_entity';
```


[13_application_workflow_runs.sql:845](/Users/maazuddinmohammed/main/projects/gds_workbench_v2/database/13_application_workflow_runs.sql:845)

```sql
ALTER TABLE workflow.model_object_binding
    ADD CONSTRAINT fk_model_object_binding_workflow_run
    FOREIGN KEY (workflow_run_id, model_id)
    REFERENCES application.workflow_run (workflow_run_id, model_id)
    ON DELETE NO ACTION;
```


</details>

<details>
<summary><code>workflow.model_attribute_binding</code></summary>


[09_workflow_mapping.sql:62](/Users/maazuddinmohammed/main/projects/gds_workbench_v2/database/09_workflow_mapping.sql:62)

```sql
CREATE TABLE workflow.model_attribute_binding (
    model_attribute_binding_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    model_object_binding_id BIGINT NOT NULL,
    logical_attribute_id BIGINT,
    dimensional_attribute_id BIGINT,
    attribute_id BIGINT NOT NULL,
    agent_run_id VARCHAR(500),
    workflow_run_id BIGINT,
    model_attribute_binding_status VARCHAR(20) NOT NULL DEFAULT 'active',
    model_attribute_binding_is_locked BOOLEAN NOT NULL DEFAULT FALSE,
    created_time TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    created_by VARCHAR(255) NOT NULL DEFAULT CURRENT_USER,
    updated_time TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_by VARCHAR(255) NOT NULL DEFAULT CURRENT_USER,
    CONSTRAINT fk_model_attribute_binding_parent
        FOREIGN KEY (model_object_binding_id)
        REFERENCES workflow.model_object_binding (model_object_binding_id)
        ON DELETE NO ACTION,
    CONSTRAINT fk_model_attribute_binding_target
        FOREIGN KEY (attribute_id)
        REFERENCES core.attribute (attribute_id)
        ON DELETE NO ACTION,
    CONSTRAINT fk_model_attribute_binding_logical
        FOREIGN KEY (logical_attribute_id)
        REFERENCES workflow.logical_attribute (logical_attribute_id)
        ON DELETE NO ACTION,
    CONSTRAINT fk_model_attribute_binding_dimensional
        FOREIGN KEY (dimensional_attribute_id)
        REFERENCES workflow.dimensional_attribute (dimensional_attribute_id)
        ON DELETE NO ACTION,
    CONSTRAINT uq_model_attribute_binding_target
        UNIQUE (model_object_binding_id, attribute_id),
    CONSTRAINT ck_model_attribute_binding_typed CHECK (
        num_nonnulls(logical_attribute_id, dimensional_attribute_id) = 1
    ),
    CONSTRAINT ck_model_attribute_binding_status CHECK (
        model_attribute_binding_status IN ('active', 'inactive', 'deprecated')
    )
);
```


[09_workflow_mapping.sql:102](/Users/maazuddinmohammed/main/projects/gds_workbench_v2/database/09_workflow_mapping.sql:102)

```sql
CREATE UNIQUE INDEX ux_model_attribute_binding_logical
    ON workflow.model_attribute_binding (logical_attribute_id)
    WHERE logical_attribute_id IS NOT NULL;
```


[09_workflow_mapping.sql:106](/Users/maazuddinmohammed/main/projects/gds_workbench_v2/database/09_workflow_mapping.sql:106)

```sql
CREATE UNIQUE INDEX ux_model_attribute_binding_dimensional
    ON workflow.model_attribute_binding (dimensional_attribute_id)
    WHERE dimensional_attribute_id IS NOT NULL;
```


[13_application_workflow_runs.sql:851](/Users/maazuddinmohammed/main/projects/gds_workbench_v2/database/13_application_workflow_runs.sql:851)

```sql
ALTER TABLE workflow.model_attribute_binding
    ADD CONSTRAINT fk_model_attribute_binding_workflow_run
    FOREIGN KEY (workflow_run_id)
    REFERENCES application.workflow_run (workflow_run_id)
    ON DELETE NO ACTION;
```


</details>

<details>
<summary><code>workflow.mapping_source_system_dependency</code></summary>


[09_workflow_mapping.sql:120](/Users/maazuddinmohammed/main/projects/gds_workbench_v2/database/09_workflow_mapping.sql:120)

```sql
CREATE TABLE workflow.mapping_source_system_dependency (
    mapping_source_system_dependency_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    model_id BIGINT NOT NULL,
    modeled_entity_type VARCHAR(30) NOT NULL,
    source_system_id BIGINT NOT NULL,
    source_system_dependency_order INTEGER NOT NULL DEFAULT 0,
    agent_run_id VARCHAR(500),
    workflow_run_id BIGINT,
    mapping_source_system_dependency_status VARCHAR(20) NOT NULL DEFAULT 'active',
    mapping_source_system_dependency_is_locked BOOLEAN NOT NULL DEFAULT FALSE,
    created_time TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    created_by VARCHAR(255) NOT NULL DEFAULT CURRENT_USER,
    updated_time TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_by VARCHAR(255) NOT NULL DEFAULT CURRENT_USER,
    CONSTRAINT fk_mapping_source_dependency_model FOREIGN KEY (model_id)
        REFERENCES model.model (model_id) ON DELETE NO ACTION,
    CONSTRAINT fk_mapping_source_dependency_system FOREIGN KEY (source_system_id)
        REFERENCES core.system (system_id) ON DELETE NO ACTION,
    CONSTRAINT uq_mapping_source_dependency_binding
        UNIQUE (model_id, modeled_entity_type, source_system_id),
    CONSTRAINT ck_mapping_source_dependency_entity_type CHECK (
        modeled_entity_type IN ('logical_entity', 'dimensional_entity')
    ),
    CONSTRAINT ck_mapping_source_dependency_order CHECK (
        source_system_dependency_order >= 0
    ),
    CONSTRAINT ck_mapping_source_dependency_status CHECK (
        mapping_source_system_dependency_status IN (
            'active', 'inactive', 'deprecated'
        )
    )
);
```


[13_application_workflow_runs.sql:857](/Users/maazuddinmohammed/main/projects/gds_workbench_v2/database/13_application_workflow_runs.sql:857)

```sql
ALTER TABLE workflow.mapping_source_system_dependency
    ADD CONSTRAINT fk_mapping_source_system_dependency_workflow_run
    FOREIGN KEY (workflow_run_id, model_id)
    REFERENCES application.workflow_run (workflow_run_id, model_id)
    ON DELETE NO ACTION;
```


</details>

<details>
<summary><code>workflow.mapping_object</code></summary>


[09_workflow_mapping.sql:153](/Users/maazuddinmohammed/main/projects/gds_workbench_v2/database/09_workflow_mapping.sql:153)

```sql
CREATE TABLE workflow.mapping_object (
    mapping_object_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    model_id BIGINT NOT NULL,
    model_object_binding_id BIGINT NOT NULL,
    source_system_id BIGINT NOT NULL,
    output_template_id BIGINT,
    object_dependency_order INTEGER NOT NULL DEFAULT 0,
    mapping_transformation_document JSONB,
    agent_run_id VARCHAR(500),
    workflow_run_id BIGINT,
    object_mapping_status VARCHAR(20) NOT NULL DEFAULT 'active',
    object_mapping_is_locked BOOLEAN NOT NULL DEFAULT FALSE,
    created_time TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    created_by VARCHAR(255) NOT NULL DEFAULT CURRENT_USER,
    updated_time TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_by VARCHAR(255) NOT NULL DEFAULT CURRENT_USER,
    CONSTRAINT fk_mapping_object_model FOREIGN KEY (model_id)
        REFERENCES model.model (model_id) ON DELETE NO ACTION,
    CONSTRAINT fk_mapping_object_binding FOREIGN KEY (model_object_binding_id)
        REFERENCES workflow.model_object_binding (model_object_binding_id)
        ON DELETE NO ACTION,
    CONSTRAINT fk_mapping_object_source_system FOREIGN KEY (source_system_id)
        REFERENCES core.system (system_id) ON DELETE NO ACTION,
    CONSTRAINT uq_mapping_object_binding_system UNIQUE (
        model_object_binding_id,
        source_system_id
    ),
    CONSTRAINT ck_mapping_object_dependency_order CHECK (
        object_dependency_order >= 0
    ),
    CONSTRAINT ck_mapping_object_transformation CHECK (
        mapping_transformation_document IS NULL
        OR (
            jsonb_typeof(mapping_transformation_document) = 'object'
            AND octet_length(mapping_transformation_document::TEXT) <= 524288
        )
    ),
    CONSTRAINT ck_mapping_object_status CHECK (
        object_mapping_status IN ('active', 'inactive', 'deprecated')
    )
);
```


[12_application_configuration.sql:2097](/Users/maazuddinmohammed/main/projects/gds_workbench_v2/database/12_application_configuration.sql:2097)

```sql
ALTER TABLE workflow.mapping_object
    ADD CONSTRAINT fk_mapping_object_output_template
    FOREIGN KEY (output_template_id)
    REFERENCES application.output_template (output_template_id)
    ON DELETE NO ACTION;
```


[13_application_workflow_runs.sql:863](/Users/maazuddinmohammed/main/projects/gds_workbench_v2/database/13_application_workflow_runs.sql:863)

```sql
ALTER TABLE workflow.mapping_object
    ADD CONSTRAINT fk_mapping_object_workflow_run
    FOREIGN KEY (workflow_run_id, model_id)
    REFERENCES application.workflow_run (workflow_run_id, model_id)
    ON DELETE NO ACTION;
```


</details>

<details>
<summary><code>workflow.mapping_attribute</code></summary>


[09_workflow_mapping.sql:195](/Users/maazuddinmohammed/main/projects/gds_workbench_v2/database/09_workflow_mapping.sql:195)

```sql
CREATE TABLE workflow.mapping_attribute (
    mapping_attribute_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    mapping_object_id BIGINT NOT NULL,
    model_attribute_binding_id BIGINT NOT NULL,
    output_template_id BIGINT,
    attribute_mapping_transformation_document JSONB,
    agent_run_id VARCHAR(500),
    workflow_run_id BIGINT,
    attribute_mapping_status VARCHAR(20) NOT NULL DEFAULT 'active',
    attribute_mapping_is_locked BOOLEAN NOT NULL DEFAULT FALSE,
    created_time TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    created_by VARCHAR(255) NOT NULL DEFAULT CURRENT_USER,
    updated_time TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_by VARCHAR(255) NOT NULL DEFAULT CURRENT_USER,
    CONSTRAINT fk_mapping_attribute_parent FOREIGN KEY (mapping_object_id)
        REFERENCES workflow.mapping_object (mapping_object_id)
        ON DELETE NO ACTION,
    CONSTRAINT fk_mapping_attribute_binding FOREIGN KEY (
        model_attribute_binding_id
    ) REFERENCES workflow.model_attribute_binding (
        model_attribute_binding_id
    ) ON DELETE NO ACTION,
    CONSTRAINT uq_mapping_attribute_target UNIQUE (
        mapping_object_id,
        model_attribute_binding_id
    ),
    CONSTRAINT ck_mapping_attribute_transformation CHECK (
        attribute_mapping_transformation_document IS NULL
        OR (
            jsonb_typeof(attribute_mapping_transformation_document) = 'object'
            AND octet_length(attribute_mapping_transformation_document::TEXT) <= 65536
        )
    ),
    CONSTRAINT ck_mapping_attribute_status CHECK (
        attribute_mapping_status IN ('active', 'inactive', 'deprecated')
    )
);
```


[12_application_configuration.sql:2106](/Users/maazuddinmohammed/main/projects/gds_workbench_v2/database/12_application_configuration.sql:2106)

```sql
ALTER TABLE workflow.mapping_attribute
    ADD CONSTRAINT fk_mapping_attribute_output_template
    FOREIGN KEY (output_template_id)
    REFERENCES application.output_template (output_template_id)
    ON DELETE NO ACTION;
```


[13_application_workflow_runs.sql:869](/Users/maazuddinmohammed/main/projects/gds_workbench_v2/database/13_application_workflow_runs.sql:869)

```sql
ALTER TABLE workflow.mapping_attribute
    ADD CONSTRAINT fk_mapping_attribute_workflow_run
    FOREIGN KEY (workflow_run_id)
    REFERENCES application.workflow_run (workflow_run_id)
    ON DELETE NO ACTION;
```


</details>

<details>
<summary><code>workflow.generated_code</code></summary>


[10_workflow_code_validation.sql:3](/Users/maazuddinmohammed/main/projects/gds_workbench_v2/database/10_workflow_code_validation.sql:3)

```sql
CREATE TABLE workflow.generated_code (
    generated_code_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    model_object_binding_id BIGINT NOT NULL,
    artifact_name VARCHAR(400) NOT NULL,
    artifact_type VARCHAR(30) NOT NULL,
    generated_code_content TEXT NOT NULL,
    code_input_digest CHAR(64) NOT NULL,
    generated_code_digest CHAR(64) GENERATED ALWAYS AS (
        encode(
            sha256(generated_code_content::BYTEA),
            'hex'
        )
    ) STORED,
    agent_run_id VARCHAR(500),
    workflow_run_id BIGINT,
    generated_code_is_locked BOOLEAN NOT NULL DEFAULT FALSE,
    generated_code_status VARCHAR(20) NOT NULL DEFAULT 'active',
    created_time TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    created_by VARCHAR(255) NOT NULL DEFAULT CURRENT_USER,
    updated_time TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_by VARCHAR(255) NOT NULL DEFAULT CURRENT_USER,
    CONSTRAINT fk_generated_code_binding FOREIGN KEY (model_object_binding_id)
        REFERENCES workflow.model_object_binding (model_object_binding_id)
        ON DELETE NO ACTION,
    CONSTRAINT ck_generated_code_artifact_name CHECK (
        reference.is_nonblank(artifact_name)
        AND artifact_name = btrim(artifact_name)
        AND artifact_name !~ '[/\\]'
        AND artifact_name NOT IN ('.', '..')
    ),
    CONSTRAINT ck_generated_code_artifact_type CHECK (
        artifact_type IN ('sql_file', 'python_file', 'python_notebook')
    ),
    CONSTRAINT ck_generated_code_content CHECK (
        reference.is_nonblank(generated_code_content)
    ),
    CONSTRAINT ck_generated_code_input_digest CHECK (
        code_input_digest ~ '^[0-9a-f]{64}$'
    ),
    CONSTRAINT ck_generated_code_status CHECK (
        generated_code_status IN ('active', 'inactive', 'deprecated')
    )
);
```


[10_workflow_code_validation.sql:47](/Users/maazuddinmohammed/main/projects/gds_workbench_v2/database/10_workflow_code_validation.sql:47)

```sql
CREATE UNIQUE INDEX ux_generated_code_artifact_name_ci
    ON workflow.generated_code (
        model_object_binding_id,
        lower(btrim(artifact_name))
    );
```


[13_application_workflow_runs.sql:875](/Users/maazuddinmohammed/main/projects/gds_workbench_v2/database/13_application_workflow_runs.sql:875)

```sql
ALTER TABLE workflow.generated_code
    ADD CONSTRAINT fk_generated_code_workflow_run
    FOREIGN KEY (workflow_run_id)
    REFERENCES application.workflow_run (workflow_run_id)
    ON DELETE NO ACTION;
```


</details>

<details>
<summary><code>workflow.generated_code_source_system</code></summary>


[10_workflow_code_validation.sql:53](/Users/maazuddinmohammed/main/projects/gds_workbench_v2/database/10_workflow_code_validation.sql:53)

```sql
CREATE TABLE workflow.generated_code_source_system (
    generated_code_source_system_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    generated_code_id BIGINT NOT NULL,
    source_system_id BIGINT NOT NULL,
    agent_run_id VARCHAR(500),
    workflow_run_id BIGINT,
    generated_code_source_system_is_locked BOOLEAN NOT NULL DEFAULT FALSE,
    generated_code_source_system_status VARCHAR(20) NOT NULL DEFAULT 'active',
    created_time TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    created_by VARCHAR(255) NOT NULL DEFAULT CURRENT_USER,
    updated_time TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_by VARCHAR(255) NOT NULL DEFAULT CURRENT_USER,
    CONSTRAINT fk_generated_code_source_system_code
        FOREIGN KEY (generated_code_id)
        REFERENCES workflow.generated_code (generated_code_id)
        ON DELETE NO ACTION,
    CONSTRAINT fk_generated_code_source_system_system
        FOREIGN KEY (source_system_id)
        REFERENCES core.system (system_id)
        ON DELETE NO ACTION,
    CONSTRAINT uq_generated_code_source_system UNIQUE (
        generated_code_id,
        source_system_id
    ),
    CONSTRAINT ck_generated_code_source_system_status CHECK (
        generated_code_source_system_status IN (
            'active', 'inactive', 'deprecated'
        )
    )
);
```


[13_application_workflow_runs.sql:881](/Users/maazuddinmohammed/main/projects/gds_workbench_v2/database/13_application_workflow_runs.sql:881)

```sql
ALTER TABLE workflow.generated_code_source_system
    ADD CONSTRAINT fk_generated_code_source_system_workflow_run
    FOREIGN KEY (workflow_run_id)
    REFERENCES application.workflow_run (workflow_run_id)
    ON DELETE NO ACTION;
```


</details>

<details>
<summary><code>workflow.validation_group</code></summary>


[10_workflow_code_validation.sql:84](/Users/maazuddinmohammed/main/projects/gds_workbench_v2/database/10_workflow_code_validation.sql:84)

```sql
CREATE TABLE workflow.validation_group (
    validation_group_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    model_id BIGINT NOT NULL,
    tenant_id BIGINT NOT NULL,
    system_id BIGINT NOT NULL,
    agent_run_id VARCHAR(500),
    workflow_run_id BIGINT,
    validation_group_name VARCHAR(200) NOT NULL,
    validation_group_description TEXT,
    mapping_context_digest CHAR(64) NOT NULL,
    code_context_digest CHAR(64),
    is_locked BOOLEAN NOT NULL DEFAULT FALSE,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_time TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    created_by VARCHAR(255) NOT NULL DEFAULT CURRENT_USER,
    updated_time TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_by VARCHAR(255) NOT NULL DEFAULT CURRENT_USER,
    CONSTRAINT fk_validation_group_model_tenant FOREIGN KEY (
        model_id,
        tenant_id
    ) REFERENCES model.model (model_id, tenant_id) ON DELETE NO ACTION,
    CONSTRAINT fk_validation_group_system FOREIGN KEY (system_id)
        REFERENCES core.system (system_id) ON DELETE NO ACTION,
    CONSTRAINT uq_validation_group_scope_witness UNIQUE (
        validation_group_id,
        model_id,
        tenant_id,
        system_id
    ),
    CONSTRAINT ck_validation_group_name CHECK (
        reference.is_nonblank(validation_group_name)
    ),
    CONSTRAINT ck_validation_group_description CHECK (
        validation_group_description IS NULL
        OR (
            reference.is_nonblank(validation_group_description)
            AND octet_length(validation_group_description) <= 16384
        )
    ),
    CONSTRAINT ck_validation_group_digests CHECK (
        mapping_context_digest ~ '^[0-9a-f]{64}$'
        AND (
            code_context_digest IS NULL
            OR code_context_digest ~ '^[0-9a-f]{64}$'
        )
    )
);
```


[10_workflow_code_validation.sql:132](/Users/maazuddinmohammed/main/projects/gds_workbench_v2/database/10_workflow_code_validation.sql:132)

```sql
CREATE UNIQUE INDEX ux_validation_group_scope_name_ci
    ON workflow.validation_group (
        model_id,
        tenant_id,
        system_id,
        lower(btrim(validation_group_name))
    );
```


[13_application_workflow_runs.sql:887](/Users/maazuddinmohammed/main/projects/gds_workbench_v2/database/13_application_workflow_runs.sql:887)

```sql
ALTER TABLE workflow.validation_group
    ADD CONSTRAINT fk_validation_group_workflow_run
    FOREIGN KEY (workflow_run_id, model_id)
    REFERENCES application.workflow_run (workflow_run_id, model_id)
    ON DELETE NO ACTION;
```


</details>

<details>
<summary><code>workflow.validation_check</code></summary>


[10_workflow_code_validation.sql:148](/Users/maazuddinmohammed/main/projects/gds_workbench_v2/database/10_workflow_code_validation.sql:148)

```sql
CREATE TABLE workflow.validation_check (
    validation_check_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    validation_group_id BIGINT NOT NULL,
    validation_check_name VARCHAR(200) NOT NULL,
    validation_check_description TEXT,
    validation_category_code VARCHAR(100) NOT NULL,
    validation_severity VARCHAR(20) NOT NULL,
    validation_query_sql TEXT NOT NULL,
    validation_comparison_query_sql TEXT,
    validation_result_data_type VARCHAR(20),
    validation_comparison_operator VARCHAR(30) NOT NULL,
    validation_comparison_value_type VARCHAR(20) NOT NULL,
    validation_comparison_value JSONB,
    is_locked BOOLEAN NOT NULL DEFAULT FALSE,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_time TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    created_by VARCHAR(255) NOT NULL DEFAULT CURRENT_USER,
    updated_time TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_by VARCHAR(255) NOT NULL DEFAULT CURRENT_USER,
    CONSTRAINT fk_validation_check_group FOREIGN KEY (validation_group_id)
        REFERENCES workflow.validation_group (validation_group_id)
        ON DELETE NO ACTION,
    CONSTRAINT ck_validation_check_name CHECK (
        reference.is_nonblank(validation_check_name)
    ),
    CONSTRAINT ck_validation_check_description CHECK (
        validation_check_description IS NULL
        OR (
            reference.is_nonblank(validation_check_description)
            AND octet_length(validation_check_description) <= 16384
        )
    ),
    CONSTRAINT ck_validation_check_category CHECK (
        validation_category_code ~ '^[a-z][a-z0-9_.-]{0,99}$'
    ),
    CONSTRAINT ck_validation_check_severity CHECK (
        validation_severity IN ('blocking', 'warning', 'informational')
    ),
    CONSTRAINT ck_validation_check_query_a CHECK (
        reference.is_nonblank(validation_query_sql)
        AND octet_length(validation_query_sql) <= 100000
    ),
    CONSTRAINT ck_validation_check_query_b CHECK (
        validation_comparison_query_sql IS NULL
        OR (
            reference.is_nonblank(validation_comparison_query_sql)
            AND octet_length(validation_comparison_query_sql) <= 100000
        )
    ),
    CONSTRAINT ck_validation_check_result_type CHECK (
        validation_result_data_type IS NULL
        OR validation_result_data_type IN (
            'boolean', 'integer', 'decimal', 'text', 'date', 'timestamp'
        )
    ),
    CONSTRAINT ck_validation_check_operator CHECK (
        validation_comparison_operator IN (
            'executes_successfully',
            'is_null', 'is_not_null',
            'is_true', 'is_false',
            'equal', 'not_equal',
            'greater_than', 'greater_than_or_equal',
            'less_than', 'less_than_or_equal',
            'in', 'not_in'
        )
    ),
    CONSTRAINT ck_validation_check_value_type CHECK (
        validation_comparison_value_type IN (
            'none', 'literal', 'literal_list', 'query'
        )
    ),
    CONSTRAINT ck_validation_check_value_size CHECK (
        validation_comparison_value IS NULL
        OR octet_length(validation_comparison_value::TEXT) <= 65536
    ),
    CONSTRAINT ck_validation_check_assertion_shape CHECK (
        CASE
            WHEN validation_comparison_operator = 'executes_successfully'
            THEN
                validation_result_data_type IS NULL
                AND validation_comparison_value_type = 'none'
                AND validation_comparison_value IS NULL
                AND validation_comparison_query_sql IS NULL
            WHEN validation_comparison_operator IN ('is_null', 'is_not_null')
            THEN
                validation_result_data_type IS NOT NULL
                AND validation_comparison_value_type = 'none'
                AND validation_comparison_value IS NULL
                AND validation_comparison_query_sql IS NULL
            WHEN validation_comparison_operator IN ('is_true', 'is_false')
            THEN
                validation_result_data_type = 'boolean'
                AND validation_comparison_value_type = 'none'
                AND validation_comparison_value IS NULL
                AND validation_comparison_query_sql IS NULL
            WHEN validation_comparison_operator IN ('equal', 'not_equal')
            THEN
                validation_result_data_type IS NOT NULL
                AND (
                    (
                        validation_comparison_value_type = 'literal'
                        AND validation_comparison_value IS NOT NULL
                        AND validation_comparison_query_sql IS NULL
                    ) OR (
                        validation_comparison_value_type = 'query'
                        AND validation_comparison_value IS NULL
                        AND validation_comparison_query_sql IS NOT NULL
                    )
                )
            WHEN validation_comparison_operator IN (
                'greater_than', 'greater_than_or_equal',
                'less_than', 'less_than_or_equal'
            )
            THEN
                validation_result_data_type IN (
                    'integer', 'decimal', 'date', 'timestamp'
                )
                AND (
                    (
                        validation_comparison_value_type = 'literal'
                        AND validation_comparison_value IS NOT NULL
                        AND validation_comparison_query_sql IS NULL
                    ) OR (
                        validation_comparison_value_type = 'query'
                        AND validation_comparison_value IS NULL
                        AND validation_comparison_query_sql IS NOT NULL
                    )
                )
            WHEN validation_comparison_operator IN ('in', 'not_in')
            THEN
                validation_result_data_type IS NOT NULL
                AND validation_comparison_value_type = 'literal_list'
                AND validation_comparison_query_sql IS NULL
                AND CASE jsonb_typeof(validation_comparison_value)
                    WHEN 'array' THEN
                        jsonb_array_length(validation_comparison_value)
                            BETWEEN 1 AND 10000
                    ELSE FALSE
                END
            ELSE FALSE
        END
    ),
    CONSTRAINT ck_validation_check_literal_type CHECK (
        validation_comparison_value_type NOT IN ('literal', 'literal_list')
        OR CASE validation_comparison_value_type
            WHEN 'literal' THEN
                CASE validation_result_data_type
                    WHEN 'boolean' THEN
                        jsonb_typeof(validation_comparison_value) = 'boolean'
                    WHEN 'integer' THEN
                        CASE jsonb_typeof(validation_comparison_value)
                            WHEN 'number' THEN
                                coalesce(
                                    validation_comparison_value #>> '{}'
                                        ~ '^-?(0|[1-9][0-9]*)$',
                                    FALSE
                                )
                            ELSE FALSE
                        END
                    WHEN 'decimal' THEN
                        jsonb_typeof(validation_comparison_value) = 'number'
                    WHEN 'text' THEN
                        jsonb_typeof(validation_comparison_value) = 'string'
                    WHEN 'date' THEN
                        jsonb_typeof(validation_comparison_value) = 'string'
                    WHEN 'timestamp' THEN
                        jsonb_typeof(validation_comparison_value) = 'string'
                    ELSE FALSE
                END
            WHEN 'literal_list' THEN
                CASE validation_result_data_type
                    WHEN 'boolean' THEN
                        NOT jsonb_path_exists(
                            validation_comparison_value,
                            '$[*] ? (@.type() != "boolean")'
                        )
                    WHEN 'integer' THEN
                        validation_comparison_value::TEXT ~
                            '^\[[[:space:]]*-?(0|[1-9][0-9]*)'
                            '([[:space:]]*,[[:space:]]*'
                            '-?(0|[1-9][0-9]*))*[[:space:]]*\]$'
                    WHEN 'decimal' THEN
                        NOT jsonb_path_exists(
                            validation_comparison_value,
                            '$[*] ? (@.type() != "number")'
                        )
                    WHEN 'text' THEN
                        NOT jsonb_path_exists(
                            validation_comparison_value,
                            '$[*] ? (@.type() != "string")'
                        )
                    WHEN 'date' THEN
                        NOT jsonb_path_exists(
                            validation_comparison_value,
                            '$[*] ? (@.type() != "string")'
                        )
                    WHEN 'timestamp' THEN
                        NOT jsonb_path_exists(
                            validation_comparison_value,
                            '$[*] ? (@.type() != "string")'
                        )
                    ELSE FALSE
                END
            ELSE FALSE
        END
    )
);
```


[10_workflow_code_validation.sql:356](/Users/maazuddinmohammed/main/projects/gds_workbench_v2/database/10_workflow_code_validation.sql:356)

```sql
CREATE UNIQUE INDEX ux_validation_check_group_name_ci
    ON workflow.validation_check (
        validation_group_id,
        lower(btrim(validation_check_name))
    );
```


</details>
