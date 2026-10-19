# Attribute — `core.attribute`

A physical field/column of an Object, with source/storage type, ordinal, optional expression, and metadata flags.

**Datasets:** `source_attribute`, `bronze_attribute`, `silver_attribute`, `gold_attribute`.
**Change Set:** editable.

## Keys

- Natural key: `tenant_code`, `system_code`, `connection_code`, `object_schema`, `object_name`, `attribute_name`.
- Also unique: `tenant_code`, `system_code`, `connection_code`, `object_schema`, `object_name`, `attribute_ordinal_position`.
- Use the published key normalization. Database IDs are not authoring fields.

## Fields

Run `describe --dataset <dataset>` for every field's type, limits, required and null rules, description and population guidance. This table lists only fields with rules that `describe` does not state.

| Field | Meaning and use |
|---|---|
| `value` | Optional additional details. Preserve existing JSON; populate only when requested. No implied execution behavior. |
| `tenant_code` | Physical Connection Tenant from the parent Object key; may differ from the Object's metadata owner. Reference: [object](object.md). |
| `attribute_description` | Meaning of the Attribute in its Object's context, including supported units/code/time distinctions where useful; see [enrichment quality](../enrichment-quality.md). Null when no description is available. |
| `attribute_inferred_data_type` | Evidence-supported logical interpretation separate from physical storage. Preserve known values during unrelated edits; follow the [type evidence procedure](../enrichment-quality.md#infer-types-with-evidence) when enriching. |
| `attribute_custom_code` | Complete replacement SELECT item for SQL Source extraction or Bronze loading; include the output alias. Default null. Source file transfer ignores it; API support is connector-dependent; Silver/Gold ignore it. See rules below. |
| `is_surrogate_key` | Whether this physical Attribute is designated as a surrogate key; does not itself create or generate database values. |
| `is_natural_key` | Whether the physical Attribute participates in the Object's business identity; unrelated to the metadata row's own natural key. |
| `is_masking_required` | Marks data requiring masking protection. Preserve it during unrelated edits; evidence queries must respect masking rules. |
| `is_mapped` | Currently unused downstream (user-confirmed). Default new records to false; preserve existing values in unrelated edits. Do not derive it from mappings. |
| `is_purge` | Currently unused downstream (user-confirmed). Default new records to false; preserve existing values in unrelated edits. No purge behavior is assigned. |
| `is_locked` | Attribute protection flag; an existing locked Attribute or locked parent Object prevents ordinary changes. |
| `is_active` | Default true for new records unless requested otherwise. False retains an inactive record, its name and ordinal; it does not create version history. Preserve existing values on unrelated edits. |

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

Enforcement is explained in [common checks](../validation.md#interpreting-table-checklists); run the local validator, then review anything marked for you.

| Rule | Check / why | Enforced by |
|---|---|
| `attribute.shape` | Exact Attribute fields; required type 1..100 chars; inferred type null/nonblank; ordinal 1..2147483647; explicit booleans. Reject malformed complete records before staging. | Local validator + server |
| `attribute.unique` | Object + normalized Attribute name unique across zone datasets. Prevent duplicate identity; inactive rows still reserve their keys. | Local validator + server |
| `attribute.ordinal` | Ordinal must be positive and unique within its Object. Preserve unambiguous column order. | Local validator + server |
| `attribute.references` | Parent Object natural key must resolve. Resolve dependencies using snapshot plus pending rows. | Local validator + server |
| `attribute.scope` | Parent Object must belong to selected Tenant and permitted placement; Apply also requires active Connection Tenant. Keep edits in the authorized Tenant. | Local validator + server |
| `attribute.lock` | Do not change a locked Attribute or an Attribute under a locked Object. Respect independent and parent protection. | Local validator + server |
| `attribute.physical-type` | Use platform-valid physical type spelling/precision/scale; preserve physical type when setting inferred type. Length alone does not validate a data type. Validator note: String shape; platform-specific validation requires separate implementation. | Your review |
| `attribute.custom-code` | For SQL Source/Bronze, check actual inputs, dialect, SELECT item, alias and required cast; constants need no source field. Source file copy ignores custom code; API use requires connector evidence. | Your review (no automated check) |
| `attribute.mapped-state` | Mapping-flag consistency intentionally deferred: is_mapped is currently unused. Do not reconcile it from mappings or block authoring over its value. | Not checked, by decision |
| `attribute.live-dependencies` | Re-resolve dependencies at Apply; reject unexpected affected-row count. Snapshot checks cannot guarantee current server state. | Server only, at Apply |

## Confirmed behavior

`is_mapped` and `is_purge` have no current downstream use: keep their boolean values, default new records to false, and do not reconcile them from mappings.

Bronze loading does not cast automatically; follow the SELECT rules above. Blank custom code selects the column unchanged.

[All metadata tables](../index.md) · [Common validation](../validation.md)
