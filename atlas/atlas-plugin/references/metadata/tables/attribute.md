# Attribute — `core.attribute`

A physical field/column of an Object, with source/storage type, ordinal, optional expression, and metadata flags.

**Datasets:** `source_attribute`, `bronze_attribute`, `silver_attribute`, `gold_attribute`.
**Change Set:** editable.

## Keys

- Natural key: `tenant_code`, `system_code`, `connection_code`, `object_schema`, `object_name`, `attribute_name`.
- Also unique: `tenant_code`, `system_code`, `connection_code`, `object_schema`, `object_name`, `attribute_ordinal_position`.
- Use the published key normalization. Database IDs are not authoring fields.

## Fields

Every field is listed explicitly. Exact current MCP/Snapshot schemas remain authoritative if the contract changes.

| Field | Accepted value / presence | Meaning and use |
|---|---|---|
| `tenant_code` | string; minLength=1; maxLength=100; pattern=\S; required | Physical Connection Tenant from the parent Object key; may differ from the Object's metadata owner. Reference: [object](object.md). |
| `system_code` | string; minLength=1; maxLength=100; pattern=\S; required | Stable code identifying the System. Reference: [object](object.md). |
| `connection_code` | string; minLength=1; maxLength=100; pattern=\S; required | Stable code identifying the Connection. Reference: [object](object.md). |
| `object_schema` | string; minLength=1; maxLength=400; pattern=\S; required | Schema containing the Object. Reference: [object](object.md). |
| `object_name` | string; minLength=1; maxLength=400; pattern=\S; required | Name identifying the Object. Reference: [object](object.md). |
| `attribute_name` | string; minLength=1; maxLength=400; pattern=\S; required | Name identifying the Attribute. |
| `fc_attribute_name` | string; maxLength=400; required; null allowed | Optional foreign-catalog name of the Attribute. |
| `attribute_ordinal_position` | integer; maximum=2147483647; exclusiveMinimum=0; required | One-based position of the Attribute within its Object. Use a positive integer unique within the Object and preserve the intended column order. |
| `attribute_description` | string; required; null allowed | Meaning of the Attribute in its Object's context, including supported units/code/time distinctions where useful; see [enrichment quality](../enrichment-quality.md). Null when no description is available. |
| `attribute_data_type` | string; minLength=1; maxLength=100; required | Physical data type of the Attribute. Use the data-type spelling accepted by the owning platform, including precision or scale when applicable. |
| `attribute_inferred_data_type` | string; minLength=1; maxLength=100; pattern=\S; required; null allowed | Evidence-supported logical interpretation separate from physical storage. Preserve known values during unrelated edits; follow the [type evidence procedure](../enrichment-quality.md#infer-types-with-evidence) when enriching. |
| `attribute_nullability` | `false`, `true`; required | Whether the physical Attribute permits null values. Use true when null is permitted and false when every row must contain a value. |
| `attribute_custom_code` | string; required; null allowed | Complete replacement SELECT item for SQL Source extraction or Bronze loading; include the output alias. Default null. Source file transfer ignores it; API support is connector-dependent; Silver/Gold ignore it. See rules below. |
| `is_surrogate_key` | `false`, `true`; required | Whether this physical Attribute is designated as a surrogate key; does not itself create or generate database values. |
| `is_natural_key` | `false`, `true`; required | Whether the physical Attribute participates in the Object's business identity; unrelated to the metadata row's own natural key. |
| `is_meta_data` | `false`, `true`; required | Whether the Attribute contains operational metadata rather than business data. Use true for audit, lineage, or framework-maintained Attributes; otherwise use false. |
| `is_masking_required` | `false`, `true`; required | Marks data requiring masking protection. Preserve it during unrelated edits; evidence queries must respect masking rules. |
| `is_mapped` | `false`, `true`; required | Currently unused downstream (user-confirmed). Default new records to false; preserve existing values in unrelated edits. Do not derive it from mappings. |
| `is_purge` | `false`, `true`; required | Currently unused downstream (user-confirmed). Default new records to false; preserve existing values in unrelated edits. No purge behavior is assigned. |
| `is_locked` | `false`, `true`; required | Attribute protection flag; an existing locked Attribute or locked parent Object prevents ordinary changes. |
| `is_active` | `false`, `true`; required | Default true for new records unless requested otherwise. False retains an inactive record, its name and ordinal; it does not create version history. Preserve existing values on unrelated edits. |

## References and dependencies

- `tenant_code`, `system_code`, `connection_code`, `object_schema`, `object_name` → [object](object.md): `tenant_code`, `system_code`, `connection_code`, `object_schema`, `object_name`. Required reference.
- Referenced by: [ingestion attribute mapping](ingestion-attribute-mapping.md).

## Making changes

- Select the Attribute dataset associated with the parent Object's zone; resolve the complete parent Object key.
- Attribute rename requires the user's [manual database correction](../editing.md#manual-natural-key-changes); the agent supplies instructions only. Ordinal remains an editable non-key field and must stay unique within the Object.
- Stage only affected records. Even unchanged re-staging of a locked Attribute or an Attribute under a locked Object fails the lock check.
- Preserve physical attribute_data_type when updating attribute_inferred_data_type. Business-meaning enrichment is separate.
- Source names/types stay actual. Confirmed Source-to-Bronze ingestion guidance uses lowercase snake_case Bronze names and STRING storage; resolve collisions.
- Read Custom SELECT expressions below when authoring or interpreting attribute_custom_code. Bronze STRING storage does not imply automatic conversion; write an explicit cast when conversion is needed.
- `is_mapped` and `is_purge` remain required booleans but need no downstream reasoning or consistency checks for now. Use false on new records; do not reset existing values during unrelated edits.
- Follow [shared editing rules](../editing.md); validate the complete effective result and preserve unrelated fields.

## Custom SELECT expressions

User-confirmed framework behavior: relational SQL Source extraction and Bronze loading build the SELECT list one Attribute at a time. Bronze metadata determines the output columns; it need not consume every extracted Source column.

| Custom code | Generated SELECT item |
|---|---|
| Null or blank | The Attribute name, using the column unchanged. No automatic cast or output alias is added, including in Bronze. |
| Populated | The custom code replaces the entire SELECT item. Supply the full expression, any required cast, and the intended output alias. The framework does not append the Attribute name or a missing alias. |

- SQL Source: use the source database's dialect and actual source names. The extraction query produces the landed Parquet fields; aliases can make names compatible with that file and Bronze.
- File Source: transfer files unchanged. Source custom code is not applied during the copy and cannot repair or rename file fields. Subsequent Bronze loading can still select and transform the incoming fields.
- API Source: custom-code support and interpretation depend on the actual connector/orchestrator. Confirm that contract before relying on it; SQL expression semantics are not assumed.
- Bronze: select the columns defined by Bronze metadata from the actual incoming fields, including extraction aliases. Custom expressions may use a subset of fields, combine values, or produce constants. Alias each result to its intended Bronze Attribute; explicitly cast when conversion is needed.
- Extra extracted columns may be ignored. No complete Source-to-Bronze column correspondence or populated Attribute Mapping dataset is required. Each Source feeding a shared Bronze target must supply the inputs its Bronze expressions reference.
- Silver/Gold: the framework does not use this field. Default new records to null; preserve existing values during unrelated edits.
- An output alias changes the query result's field name; it does not rename the registered Attribute. Custom code supplies one SELECT item, not a complete query or merge policy.

Example: a SQL Server Source Attribute named `Customer ID` can use:

```sql
[Customer ID] AS customer_id
```

Bronze then reads `customer_id`. If conversion to STRING is needed, use:

```sql
CAST(customer_id AS STRING) AS customer_id
```

Keep the Source metadata name `Customer ID`. With blank Bronze custom code, `customer_id` is selected unchanged; its target STRING declaration does not add a cast.

A fixed domain column can use `'retail' AS business_domain`; it needs a Bronze Attribute but no corresponding Source Attribute or Attribute Mapping record.

## Validation checklist

Source-review coverage only; see [status meanings and common checks](../validation.md).

| Rule | Check / why | Database | MCP backend | Local | Status |
|---|---|---|---|---|---|
| `attribute.shape` | Exact Attribute fields; required type 1..100 chars; inferred type null/nonblank; ordinal 1..2147483647; explicit booleans. Reject malformed complete records before staging. | Column types, nullability and selected CHECKs; not exact JSON shape. | Strict Pydantic record; unknown fields forbidden. | Published JSON Schema and portable record rules. | Existing; not parity-tested |
| `attribute.unique` | Object + normalized Attribute name unique across zone datasets. Prevent duplicate identity; inactive rows still reserve their keys. | Unique constraint/index. | Staged and effective uniqueness. | Pending/effective and cross-dataset uniqueness. | Existing; not parity-tested |
| `attribute.ordinal` | Ordinal must be positive and unique within its Object. Preserve unambiguous column order. | Positive CHECK; deferred unique constraint permits atomic reorder. | Positive bounded integer and effective uniqueness. | Schema integer limits and effective uniqueness. | Existing; not parity-tested |
| `attribute.references` | Parent Object natural key must resolve. Resolve dependencies using snapshot plus pending rows. | FK/composite FK and Apply joins. | Effective reference validation. | Effective natural-key reference validation. | Existing; not parity-tested |
| `attribute.scope` | Parent Object must belong to selected Tenant and permitted placement; Apply also requires active Connection Tenant. Keep edits in the authorized Tenant. | Apply joins owner and permitted Object connections. | Tenant-scope validation. | Snapshot-based Tenant-scope validation. | Existing; not parity-tested |
| `attribute.lock` | Do not change a locked Attribute or an Attribute under a locked Object. Respect independent and parent protection. | Apply checks touched Object/Attribute locks. | Object and Attribute lock phase. | Baseline lock validation. | Existing; not parity-tested |
| `attribute.physical-type` | Use platform-valid physical type spelling/precision/scale; preserve physical type when setting inferred type. Length alone does not validate a data type. | VARCHAR storage; no platform grammar check. | String shape; no platform grammar validation located. | String shape; platform-specific validation requires separate implementation. | Review |
| `attribute.custom-code` | For SQL Source/Bronze, check actual inputs, dialect, SELECT item, alias and required cast; constants need no source field. Source file copy ignores custom code; API use requires connector evidence. | Text storage only. | String/null shape; no expression-semantic check located. | Proposed applicability/expression/type check; runtime results require permitted evidence. | Proposed; user-confirmed consumer rule |
| `attribute.mapped-state` | Mapping-flag consistency intentionally deferred: is_mapped is currently unused. Do not reconcile it from mappings or block authoring over its value. | Boolean shape still applies. | No semantic reconciliation required. | No semantic reconciliation required. | Deferred by user; not a pending check |
| `attribute.live-dependencies` | Re-resolve dependencies at Apply; reject unexpected affected-row count. Snapshot checks cannot guarantee current server state. | Atomic Apply dependency/row-count check. | Server Apply result; do not infer success locally. | Cannot prove offline; retain server result. | Server-only |

## Source pointers

Development provenance; these source files are not runtime dependencies of the packaged skill.

User-confirmed Atlas decision: is_mapped and is_purge have no current downstream use. This supersedes older field guidance suggesting mapping reconciliation or purge behavior; it does not change their published boolean contracts.

The user-confirmed SELECT rules above supersede older GDS guidance claiming automatic Bronze STRING casting. Blank custom code uses the column unchanged. Source pointers below remain evidence for field contracts and the other stated conventions.

- `mcp_server/gds_etl_workbench/domain/metadata_records.py:29,163,171,173`.
- `database/02_core.sql:199,206,215,223,225,230,516,517`.
- `plugins/v2/gds/skills/gds/references/orchestration-rules.md:5`.
- `plugins/v2/gds/skills/gds/workbench/validation/common.js:357,525`.
- `mcp_server/gds_etl_workbench/domain/snapshots/metadata.py:159,415,416`.
- `mcp_server/gds_etl_workbench/application/change_sets/metadata_validation.py:103,270,354,474,533`.
- `plugins/v2/gds/skills/gds/workbench/validation/metadata.js:11,93,177,241`.
- `database/16_mcp_metadata_apply.sql:140,226,270,445,469`.
- `mcp_server/gds_etl_workbench/domain/snapshots/metadata_guidance.py:45,194`.

[All metadata tables](../index.md) · [Common validation](../validation.md)
