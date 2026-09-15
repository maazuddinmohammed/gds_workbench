# Ingestion attribute mapping — `core.ingestion_attribute_mapping`

Optional reference correspondence from a Source Attribute to a Bronze Attribute beneath an Ingestion Object Mapping. Usually empty; the current orchestration framework does not use these records to select or transform columns.

**Datasets:** `ingestion_attribute_mapping`.
**Change Set:** editable.

## Keys

- Natural key: `source_tenant_code`, `source_system_code`, `source_connection_code`, `source_object_schema`, `source_object_name`, `source_attribute_name`, `target_tenant_code`, `target_system_code`, `target_connection_code`, `target_object_schema`, `target_object_name`, `target_attribute_name`.
- No additional unique tuple is published in the Snapshot registry.
- Use the published key normalization. Database IDs are not authoring fields.

## Fields

Every field is listed explicitly. Exact current MCP/Snapshot schemas remain authoritative if the contract changes.

| Field | Accepted value / presence | Meaning and use |
|---|---|---|
| `source_tenant_code` | string; minLength=1; maxLength=100; pattern=\S; required | Tenant code of the source physical endpoint; resolve the complete referenced key. This is placement, not the referenced Object's owner field. Reference: [ingestion object mapping](ingestion-object-mapping.md), [attribute](attribute.md). |
| `source_system_code` | string; minLength=1; maxLength=100; pattern=\S; required | System code of the source physical endpoint; resolve the complete referenced key. Reference: [ingestion object mapping](ingestion-object-mapping.md), [attribute](attribute.md). |
| `source_connection_code` | string; minLength=1; maxLength=100; pattern=\S; required | Connection code of the source physical endpoint; resolve the complete referenced key. Reference: [ingestion object mapping](ingestion-object-mapping.md), [attribute](attribute.md). |
| `source_object_schema` | string; minLength=1; maxLength=400; pattern=\S; required | Object schema of the source physical endpoint; resolve the complete referenced key. Reference: [ingestion object mapping](ingestion-object-mapping.md), [attribute](attribute.md). |
| `source_object_name` | string; minLength=1; maxLength=400; pattern=\S; required | Object name of the source physical endpoint; resolve the complete referenced key. Reference: [ingestion object mapping](ingestion-object-mapping.md), [attribute](attribute.md). |
| `source_attribute_name` | string; minLength=1; maxLength=400; pattern=\S; required | Actual registered source Attribute name. An extraction alias in custom code does not rename this identity. Reference: [attribute](attribute.md). |
| `target_tenant_code` | string; minLength=1; maxLength=100; pattern=\S; required | Tenant code of the target physical endpoint; resolve the complete referenced key. This is placement, not the referenced Object's owner field. Reference: [ingestion object mapping](ingestion-object-mapping.md), [attribute](attribute.md). |
| `target_system_code` | string; minLength=1; maxLength=100; pattern=\S; required | System code of the target physical endpoint; resolve the complete referenced key. Reference: [ingestion object mapping](ingestion-object-mapping.md), [attribute](attribute.md). |
| `target_connection_code` | string; minLength=1; maxLength=100; pattern=\S; required | Connection code of the target physical endpoint; resolve the complete referenced key. Reference: [ingestion object mapping](ingestion-object-mapping.md), [attribute](attribute.md). |
| `target_object_schema` | string; minLength=1; maxLength=400; pattern=\S; required | Object schema of the target physical endpoint; resolve the complete referenced key. Reference: [ingestion object mapping](ingestion-object-mapping.md), [attribute](attribute.md). |
| `target_object_name` | string; minLength=1; maxLength=400; pattern=\S; required | Object name of the target physical endpoint; resolve the complete referenced key. Reference: [ingestion object mapping](ingestion-object-mapping.md), [attribute](attribute.md). |
| `target_attribute_name` | string; minLength=1; maxLength=400; pattern=\S; required | Exact registered Bronze Attribute name; account for the field name actually emitted by extraction or supplied files. Reference: [attribute](attribute.md). |
| `is_active` | `false`, `true`; required | Default true for new records unless requested otherwise; preserve existing values on unrelated edits. Active status of this optional reference record does not control column ingestion. Attribute is_mapped remains unused; no synchronization is required. |

## References and dependencies

- `source_tenant_code`, `source_system_code`, `source_connection_code`, `source_object_schema`, `source_object_name`, `target_tenant_code`, `target_system_code`, `target_connection_code`, `target_object_schema`, `target_object_name` → [ingestion object mapping](ingestion-object-mapping.md): `source_tenant_code`, `source_system_code`, `source_connection_code`, `source_object_schema`, `source_object_name`, `target_tenant_code`, `target_system_code`, `target_connection_code`, `target_object_schema`, `target_object_name`. Required reference.
- `source_tenant_code`, `source_system_code`, `source_connection_code`, `source_object_schema`, `source_object_name`, `source_attribute_name` → [attribute](attribute.md): `tenant_code`, `system_code`, `connection_code`, `object_schema`, `object_name`, `attribute_name`. Required reference.
- `target_tenant_code`, `target_system_code`, `target_connection_code`, `target_object_schema`, `target_object_name`, `target_attribute_name` → [attribute](attribute.md): `tenant_code`, `system_code`, `connection_code`, `object_schema`, `object_name`, `attribute_name`. Required reference.
- Referenced by: no direct published metadata reference.

## Making changes

- Leave this dataset empty by default. Add records only for an explicit reference/documentation need; absence does not block ingestion or imply incomplete authoring.
- For supplied records, resolve the parent Object pair plus the two exact Attribute identities; each Attribute must belong to its stated endpoint Object.
- Source extraction and Bronze metadata/custom code drive the actual values and selected columns. Do not enforce complete column coverage, one-to-one correspondence, or a Source mapping for a Bronze constant.
- Read Source and Bronze [custom SELECT expressions](attribute.md#custom-select-expressions) when interpreting extraction aliases and conversion; do not invent a mapping transformation field.
- Changing an existing mapping endpoint requires the user's [manual database correction](../editing.md#manual-natural-key-changes); the agent supplies instructions only.
- Do not update or reconcile Attribute is_mapped when authoring mappings; it is currently unused downstream. See [Attribute](attribute.md) for new-record defaults.
- Follow [shared editing rules](../editing.md); validate the complete effective result and preserve unrelated fields.

## Validation checklist

Source-review coverage only; see [status meanings and common checks](../validation.md).

Apply these checks only to records that are present. No minimum record count or ingestion-coverage check is required.

| Rule | Check / why | Database | MCP backend | Local | Status |
|---|---|---|---|---|---|
| `ingestion_attribute_mapping.shape` | Complete source/target Object and Attribute keys; required is_active boolean. Reject malformed complete records before staging. | Column types, nullability and selected CHECKs; not exact JSON shape. | Strict Pydantic record; unknown fields forbidden. | Published JSON Schema and portable record rules. | Existing; not parity-tested |
| `ingestion_attribute_mapping.unique` | Parent Object Mapping + source Attribute + target Attribute unique. Prevent duplicate identity; inactive rows still reserve their keys. | Unique constraint/index. | Staged and effective uniqueness. | Pending/effective and cross-dataset uniqueness. | Existing; not parity-tested |
| `ingestion_attribute_mapping.references` | Parent Object Mapping exists; each Attribute belongs to its stated endpoint Object. Resolve dependencies using snapshot plus pending rows. | FK/composite FK and Apply joins. | Effective reference validation. | Effective natural-key reference validation. | Existing; not parity-tested |
| `ingestion_attribute_mapping.distinct` | Source and target Attribute must differ after key normalization. Prevent a self-Attribute mapping. | source_attribute_id <> target_attribute_id CHECK. | Pydantic model validator. | Portable ingestion_attribute_endpoints rule. | Existing; not parity-tested |
| `ingestion_attribute_mapping.scope` | Both endpoint Objects belong to selected Tenant; Connections owned or configured GDS. Keep edits in the authorized Tenant. | Apply joins owner and permitted Object connections. | Tenant-scope validation. | Snapshot-based Tenant-scope validation. | Existing; not parity-tested |
| `ingestion_attribute_mapping.live-dependencies` | Re-resolve dependencies at Apply; reject unexpected affected-row count. Snapshot checks cannot guarantee current server state. | Atomic Apply dependency/row-count check. | Server Apply result; do not infer success locally. | Cannot prove offline; retain server result. | Server-only |

## Source pointers

Development provenance; these source files are not runtime dependencies of the packaged skill.

User-confirmed intended behavior: these optional records are not required by ingestion or downstream workflows. Legacy GDS profiling still reads active mappings to propagate masking (`plugins/v2/gds/skills/gds/scripts/profiling.js:23`). Review that dependency when porting profiling; an empty mapping dataset does not prove a column is unmasked. Do not silently remove existing masking safeguards.

- `mcp_server/gds_etl_workbench/domain/metadata_records.py:29,226,241`.
- `mcp_server/gds_etl_workbench/domain/snapshots/metadata.py:179,441,450`.
- `database/02_core.sql:263,274,275,292,298`.
- `database/16_mcp_metadata_apply.sql:593,639,649`.
- `plugins/v2/gds/skills/gds/references/orchestration-rules.md:8`.
- `plugins/v2/gds/skills/gds/workbench/validation/common.js:205,357,525`.
- `mcp_server/gds_etl_workbench/application/change_sets/metadata_validation.py:354,474,533`.
- `plugins/v2/gds/skills/gds/workbench/validation/metadata.js:11,177,241`.

[All metadata tables](../index.md) · [Common validation](../validation.md)
