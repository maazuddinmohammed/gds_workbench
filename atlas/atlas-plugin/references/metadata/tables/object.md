# Object — `core.object`

A physical Object registered at a Connection, owned by a Source Tenant and classified into a Zone; its Attributes are separate records.

**Datasets:** `source_object`, `bronze_object`, `silver_object`, `gold_object`.
**Change Set:** editable.

## Keys

- Natural key: `tenant_code`, `system_code`, `connection_code`, `object_schema`, `object_name`.
- No additional unique tuple is published in the Snapshot registry.
- Use the published key normalization. Database IDs are not authoring fields.

## Ownership and physical identity

This section owns the distinction for all workflows. Snapshot Object records already provide both codes; backend IDs are resolved separately.

| Field/context | Meaning |
|---|---|
| Object tenant_code | Physical Connection's Tenant; part of the natural key with System, Connection, schema and Object name. |
| Object source_tenant_code | Data/metadata owner, resolving database source_tenant_id. Must match the authorized Metadata Change Set/locked Tenant; not part of the physical key. |
| Profiling tenant_code; Analysis from_tenant_code/to_tenant_code | Physical endpoint Tenant codes. Copy them from the registered keys, not from Object ownership or Model ownership. |
| Ingestion Mapping source_tenant_code/target_tenant_code | Physical endpoint Tenant codes. The source_ prefix here does not mean the referenced Object's owner field. |
| Model owner and tool IDs | Bind the governed Model/Change Set or execution request. They do not replace physical keys in ID-free records. |

Source Objects use their actual owned non-GDS Connection, so owner and physical Tenant match. Bronze, Silver and Gold use the owner's explicitly configured GDS Connection; owner and physical Tenant **may match or differ**.

For a single-origin Silver/Gold target, source_tenant_code retains the actual source/data Tenant established by input provenance. Resolve that Tenant's configured GDS Connection for physical placement. Do not substitute the source Connection, the Model Tenant or the physical GDS Tenant merely because it is convenient. An existing target retains its registered owner; mixed targets follow the explicit choice below.

For a Silver Object combining data from several Tenants, the user may choose the GDS Connection's Tenant as its source_tenant_code. This makes owner and physical Tenant equal when that Tenant is authorized to own the Object and its configured GDS Connection is this exact Connection. Treat this as an explicit ownership choice for the mixed target, not an automatic rule for all downstream Objects. Input provenance still needs to be retained.

Synthetic examples:

| Object | tenant_code | source_tenant_code |
|---|---|---|
| Tenant A's Source Customer | tenant_a | tenant_a |
| Tenant A's Bronze Customer in the shared store | store | tenant_a |
| Tenant A's Silver Customer or Gold Customer dimension in the shared store | store | tenant_a |
| Explicitly shared Silver Customer owned by the store Tenant | store | store |

Metadata changes use the chosen Object owner's Change Set. Existing ownership cannot be transferred through Apply by resubmitting the same physical key with another owner. Never add tenant_id, source_tenant_id or object_id to these ID-free records; use returned IDs only in tool arguments that require them.

## Fields

Every field is listed explicitly. Exact current MCP/Snapshot schemas remain authoritative if the contract changes.

| Field | Accepted value / presence | Meaning and use |
|---|---|---|
| `tenant_code` | string; minLength=1; maxLength=100; pattern=\S; required | Tenant component of the physical Connection key; may differ from the Source Tenant owning the data. Reference: [tenant](../read-only/tenant.md). |
| `system_code` | string; minLength=1; maxLength=100; pattern=\S; required | Stable code identifying the System. Reference: [system](../read-only/system.md). |
| `connection_code` | string; minLength=1; maxLength=100; pattern=\S; required | Stable code identifying the Connection. |
| `source_tenant_code` | string; minLength=1; maxLength=100; pattern=\S; required | Data/metadata owner; must match the Change Set Tenant. This field is not part of the physical natural key. Reference: [tenant](../read-only/tenant.md). |
| `object_schema` | string; minLength=1; maxLength=400; pattern=\S; required | Schema containing the Object. |
| `object_name` | string; minLength=1; maxLength=400; pattern=\S; required | Name identifying the Object. |
| `fc_object_schema` | string; maxLength=400; required; null allowed | Optional foreign-catalog schema containing the Object. |
| `fc_object_name` | string; maxLength=400; required; null allowed | Optional foreign-catalog name of the Object. |
| `object_transformation` | string; required; null allowed | Currently unused downstream (user-confirmed). Default new records to null; preserve existing values during unrelated edits. Column SELECT expressions belong in attribute_custom_code. |
| `object_description` | string; required; null allowed | Meaning and purpose of the Object, including supported row grain. Avoid generic Zone/storage boilerplate; see [enrichment quality](../enrichment-quality.md). Null when no description is available. |
| `batch_attribute_name` | string; maxLength=400; required; null allowed | Optional Attribute identifying a batch within this Object. Follow shared [query-scope rules](../../query-scope.md#batch-selection) for profiling and relationship evidence; a populated value requires resolved explicit IDs and a supported active Attribute. |
| `object_type_code` | string; minLength=1; maxLength=100; pattern=\S; required | Registered Object Type code describing the physical kind; resolve its current description. Reference: [object type](../read-only/object-type.md). |
| `zone_code` | `source`, `bronze`, `silver`, `gold`; exact dataset zone; required | Physical layer represented by the selected Object dataset. The four datasets share one database Object table. Reference: [zone](../read-only/zone.md). |
| `is_locked` | `false`, `true`; required | Object protection flag. Existing locked Objects cannot be changed, including through their Attributes; do not unlock by ordinary authoring. |
| `is_active` | `false`, `true`; required | Default true for new records unless requested otherwise. False retains an inactive record and its identity; it does not create version history. Preserve existing values on unrelated edits. |

## References and dependencies

- `tenant_code` → [tenant](../read-only/tenant.md): `tenant_code`. Required reference.
- `source_tenant_code` → [tenant](../read-only/tenant.md): `tenant_code`. Required reference.
- `system_code` → [system](../read-only/system.md): `system_code`. Required reference.
- `object_type_code` → [object type](../read-only/object-type.md): `object_type_code`. Required reference.
- `zone_code` → [zone](../read-only/zone.md): `zone_code`. Required reference.
- Referenced by: [attribute](attribute.md), [ingestion object mapping](ingestion-object-mapping.md), [process](process.md).

## Making changes

- All four zone datasets share one physical-table identity. Owner and Zone are not part of the natural key.
- Follow [ownership and physical identity](object.md#ownership-and-physical-identity) for placement and the selected Change Set Tenant.
- Changing Connection/schema/name requires the user's [manual database correction](../editing.md#manual-natural-key-changes). The agent supplies instructions only. Apply does not transfer Object ownership.
- Preserve existing protection and unrelated fields. Check Attributes, mappings, Copies, Model bindings and Processes when changing classification or activity.
- Stage only affected records. Even unchanged re-staging of a locked Object or its Attributes fails the lock check.
- Foreign-catalog coordinates are conditional on the requested evidence operation; they are not universally mandatory.
- Follow [shared editing rules](../editing.md); validate the complete effective result and preserve unrelated fields.

## Validation checklist

Source-review coverage only; see [status meanings and common checks](../validation.md).

| Rule | Check / why | Database | MCP backend | Local | Status |
|---|---|---|---|---|---|
| `object.shape` | Exact Object fields; required codes/names; schema/name <=400; explicit booleans; nullable optional fields. Reject malformed complete records before staging. | Column types, nullability and selected CHECKs; not exact JSON shape. | Strict Pydantic record; unknown fields forbidden. | Published JSON Schema and portable record rules. | Existing; not parity-tested |
| `object.unique` | Connection + normalized schema/name unique across all four zone datasets; owner and zone are not key fields. Prevent duplicate identity; inactive rows still reserve their keys. | Unique constraint/index. | Staged and effective uniqueness. | Pending/effective and cross-dataset uniqueness. | Existing; not parity-tested |
| `object.references` | Connection, owner Tenant, Object Type and Zone must resolve. Resolve dependencies using snapshot plus pending rows. | FK/composite FK and Apply joins. | Effective reference validation. | Effective natural-key reference validation. | Existing; not parity-tested |
| `object.placement` | Owner is selected Tenant; source uses owned non-GDS Connection; bronze/silver/gold use configured GDS Connection. Separate metadata ownership from physical placement. | Apply checks owner, configured Connection and is_global_data_store. | Owner/configured membership checked; GDS-flag parity review. | Owner/configured membership checked; GDS-flag parity review. | Review |
| `object.zone` | zone_code is source/bronze/silver/gold and matches dataset. Avoid writing the row into the wrong zone document. | Zone FK; Apply zone placement branches. | Record enum and fixed dataset values. | Published enum/fixed schema values. | Existing; not parity-tested |
| `object.lock` | Do not stage a locked existing Object or any of its Attributes. Preserve governed record protection. | Apply locks and checks touched Object rows. | Object/Attribute lock phase. | Baseline lock check; live recheck still required. | Existing; not parity-tested |
| `object.batch-attribute` | Non-null batch_attribute_name should resolve within this Object. Analysis batch filtering additionally requires an active Attribute and supported scalar type. | No storage FK; analysis endpoint resolution checks active same-Object membership. | Metadata-authoring membership check not located; analysis validates the scalar type. | Metadata-authoring membership check not located. | Review: authoring coverage gap |
| `object.foreign-catalog` | When source profiling is needed, resolve foreign catalog plus exact foreign schema/Object/Attribute names. Do not invent physical source names. | Nullable text columns; no complete-catalog check here. | Workflow prerequisite; not unconditional shape requirement. | Check as prerequisite from snapshot/evidence; not a blanket required field. | Review |
| `object.live-dependencies` | Re-resolve dependencies at Apply; reject unexpected affected-row count. Snapshot checks cannot guarantee current server state. | Atomic Apply dependency/row-count check. | Server Apply result; do not infer success locally. | Cannot prove offline; retain server result. | Server-only |

## Source pointers

Development provenance; these source files are not runtime dependencies of the packaged skill.

- `mcp_server/gds_etl_workbench/domain/metadata_records.py:29,145,152,158`.
- `database/02_core.sql:166,176,185,510`.
- `database/16_mcp_metadata_apply.sql:140,305,344,345,377`.
- `plugins/v2/gds/skills/gds/workbench/validation/common.js:357,398,525`.
- `mcp_server/gds_etl_workbench/domain/snapshots/metadata.py:158,390,404`.
- `mcp_server/gds_etl_workbench/application/change_sets/metadata_validation.py:103,270,451,474,533`.
- `plugins/v2/gds/skills/gds/workbench/validation/metadata.js:11,93,207,241,282`.
- `mcp_server/gds_etl_workbench/domain/snapshots/metadata_guidance.py:68,132,397`.
- `database/14_application_workflow_execution.sql:796,848`.
- `web_app/backend/gds_workbench_api/features/analysis/validation_execution.py:434`.

Guidance correction for implementation: `domain/snapshots/metadata_guidance.py` currently says downstream ownership "differs" from physical Tenant. It should say "may differ"; equality is permitted under the configured-Connection rules above. No backend change is made by this document.

[All metadata tables](../index.md) · [Common validation](../validation.md)
