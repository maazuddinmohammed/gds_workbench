# Copy — `core.copy`

Ingestion configuration for one Object Mapping within a Copy Group: extraction filters, landing-file naming, format, ordering, optional chunking, and target operation. The required source operation has no current runtime effect.

**Datasets:** `copy`.
**Change Set:** editable.

## Keys

- Natural key: `tenant_code`, `system_code`, `copy_group_name`, `source_tenant_code`, `source_system_code`, `source_connection_code`, `source_object_schema`, `source_object_name`, `target_tenant_code`, `target_system_code`, `target_connection_code`, `target_object_schema`, `target_object_name`.
- Copy order is outside the natural key and is not unique within a group. Distinct Copies may share order 1.
- Use the published key normalization. Database IDs are not authoring fields.

## Fields

Every field is listed explicitly. Exact current MCP/Snapshot schemas remain authoritative if the contract changes.

| Field | Accepted value / presence | Meaning and use |
|---|---|---|
| `value` | any valid JSON; optional; null allowed | Optional additional details. Preserve existing JSON; populate only when requested. No implied execution behavior. |
| `tenant_code` | string; minLength=1; maxLength=100; pattern=\S; required | Owning Tenant code for this group/record; match the selected Change Set Tenant. Reference: [copy group](copy-group.md). |
| `system_code` | string; minLength=1; maxLength=100; pattern=\S; required | Stable code identifying the System. Reference: [copy group](copy-group.md). |
| `copy_group_name` | string; minLength=1; maxLength=200; pattern=\S; required | Name identifying the Copy Group. Reference: [copy group](copy-group.md). |
| `source_tenant_code` | string; minLength=1; maxLength=100; pattern=\S; required | Tenant code of the source physical endpoint; resolve the complete referenced key. This is placement, not the referenced Object's owner field. Reference: [ingestion object mapping](ingestion-object-mapping.md). |
| `source_system_code` | string; minLength=1; maxLength=100; pattern=\S; required | System code of the source physical endpoint; resolve the complete referenced key. Reference: [ingestion object mapping](ingestion-object-mapping.md). |
| `source_connection_code` | string; minLength=1; maxLength=100; pattern=\S; required | Connection code of the source physical endpoint; resolve the complete referenced key. Reference: [ingestion object mapping](ingestion-object-mapping.md). |
| `source_object_schema` | string; minLength=1; maxLength=400; pattern=\S; required | Object schema of the source physical endpoint; resolve the complete referenced key. Reference: [ingestion object mapping](ingestion-object-mapping.md). |
| `source_object_name` | string; minLength=1; maxLength=400; pattern=\S; required | Object name of the source physical endpoint; resolve the complete referenced key. Reference: [ingestion object mapping](ingestion-object-mapping.md). |
| `target_tenant_code` | string; minLength=1; maxLength=100; pattern=\S; required | Tenant code of the target physical endpoint; resolve the complete referenced key. This is placement, not the referenced Object's owner field. Reference: [ingestion object mapping](ingestion-object-mapping.md). |
| `target_system_code` | string; minLength=1; maxLength=100; pattern=\S; required | System code of the target physical endpoint; resolve the complete referenced key. Reference: [ingestion object mapping](ingestion-object-mapping.md). |
| `target_connection_code` | string; minLength=1; maxLength=100; pattern=\S; required | Connection code of the target physical endpoint; resolve the complete referenced key. Reference: [ingestion object mapping](ingestion-object-mapping.md). |
| `target_object_schema` | string; minLength=1; maxLength=400; pattern=\S; required | Object schema of the target physical endpoint; resolve the complete referenced key. Reference: [ingestion object mapping](ingestion-object-mapping.md). |
| `target_object_name` | string; minLength=1; maxLength=400; pattern=\S; required | Object name of the target physical endpoint; resolve the complete referenced key. Reference: [ingestion object mapping](ingestion-object-mapping.md). |
| `copy_source_record_limit` | string; pattern=^-?[0-9]+$; required; null allowed | Numeric parameter for selected chunking logic, stored as a signed BIGINT decimal string. Null leaves it unset; exact meaning and allowed values come from the chunk description/code. |
| `copy_source_record_limit_attribute` | string; maxLength=400; required; null allowed | Text parameter for selected chunking logic. The description/code determines its use and whether it must name a real Attribute. Null when unused. |
| `chunk_type_name` | string; minLength=1; maxLength=200; pattern=\S; required; null allowed | Registered logic splitting a large initial extraction into smaller queries. Default null; use only when the user explicitly requests chunking. Reference: [chunk type](../read-only/chunk-type.md). |
| `copy_source_initial_sql_script` | string; required; null allowed | Optional filter fragment for initial extraction, including the WHERE keyword. Inserted as supplied; null/blank adds nothing. |
| `copy_source_incremental_sql_script` | string; required; null allowed | Optional filter fragment for incremental extraction, including the WHERE keyword. Inserted as supplied; null/blank adds nothing. Use only confirmed control-value placeholders. |
| `copy_source_file_name` | string; required; null allowed | Name used for the intermediate landing artifact between Source and Bronze. Exact construction comes from the framework's landing writer/reader convention; null when unused. |
| `copy_source_file_pattern` | string; required; null allowed | Pattern/template used by the framework for intermediate landing naming. Placeholder syntax and interaction with file_name are consumer-defined; null when unused. |
| `copy_source_file_delimiter` | string; maxLength=20; required; null allowed | Delimiter expected by the applicable framework reader for delimited data. Confirm its stage/format when unclear; null when unused. |
| `source_file_type_name` | string; minLength=1; maxLength=200; pattern=\S; required; null allowed | Registered file format for the representation consumed by the applicable framework step. Use actual extraction output or supplied-file evidence, not the field prefix alone. Reference: [file type](../read-only/file-type.md). |
| `copy_source_order` | integer; maximum=2147483647; exclusiveMinimum=0; required | Sort value used like ORDER BY; no current execution-stage barrier. Agreed new-record default 1. Compatible Atlas installations permit repeated order values. |
| `source_data_operation_name` | string; minLength=1; maxLength=200; pattern=\S; required | Required registered value with no runtime effect. Prefer a registered unused-source value or reuse the existing Copy convention; never invent a name or use null. Reference: [data operation](../read-only/data-operation.md). |
| `target_data_operation_name` | string; minLength=1; maxLength=200; pattern=\S; required | Selects the framework's target loading function. Copy Into appends; other operations follow their registered descriptions and confirmed scope. Reference: [data operation](../read-only/data-operation.md). |
| `is_active` | `false`, `true`; required | Default true for new records unless requested otherwise; preserve existing values on unrelated edits. Copy Group, Copy and Object Mapping must all be active for selection. Any false skips this Copy; stored flags and identities remain unchanged. |

## References and dependencies

- `tenant_code`, `system_code`, `copy_group_name` → [copy group](copy-group.md): `tenant_code`, `system_code`, `copy_group_name`. Required reference.
- `source_tenant_code`, `source_system_code`, `source_connection_code`, `source_object_schema`, `source_object_name`, `target_tenant_code`, `target_system_code`, `target_connection_code`, `target_object_schema`, `target_object_name` → [ingestion object mapping](ingestion-object-mapping.md): `source_tenant_code`, `source_system_code`, `source_connection_code`, `source_object_schema`, `source_object_name`, `target_tenant_code`, `target_system_code`, `target_connection_code`, `target_object_schema`, `target_object_name`. Required reference.
- `chunk_type_name` → [chunk type](../read-only/chunk-type.md): `chunk_type_name`. Nullable reference; use the full declared key when populated.
- `source_file_type_name` → [file type](../read-only/file-type.md): `file_type_name`. Nullable reference; use the full declared key when populated.
- `source_data_operation_name` → [data operation](../read-only/data-operation.md): `data_operation_name`. Required reference.
- `target_data_operation_name` → [data operation](../read-only/data-operation.md): `data_operation_name`. Required reference.
- Referenced by: no direct published metadata reference.

## Making changes

- Requires an existing or pending Ingestion Object Mapping; both endpoints retain complete physical keys.
- Check the [activation gate](ingestion-object-mapping.md#making-changes): Copy Group, Copy and Object Mapping must all be active. Disabled configurations remain valid; report that they will be skipped.
- Use registered [Data Operations](../read-only/data-operation.md). Source is required but unused; target selects the loading function. Copy Into appends. Confirm Override/custom behavior from the registered description.
- Enable [chunking](../read-only/chunk-type.md) only for a large table when the user explicitly requests it; default null and preserve existing settings during unrelated edits.
- Treat both record-limit fields as chunk-function inputs. Use the selected description/code for their meaning, defaults and ranges; field names alone do not establish a row cap or column reference. Leave unused inputs null on new records.
- Do not infer append/overwrite, batching, or chunk semantics from data type conversion.
- Use the [framework-dependent value rules](../editing.md#framework-dependent-values) to propose defaults for SQL/file settings. Custom or unclear usage calls for the relevant code or a verified working example.
- Source file transfer preserves file contents; Source Attribute custom code is not applied. SQL extraction supports it; API behavior needs connector confirmation. Subsequent Bronze projection follows its own [Attribute rules](attribute.md#custom-select-expressions).
- copy_source_order is mutable and outside the natural key. Preserve unrelated values and use the [compatible order contract](copy.md#copy-order-and-default).
- The Copy record contract contains no is_sync field. Do not introduce that field without a separately agreed contract change.
- Validation gap: authoring/DB accepts signed BIGINT chunk parameters, but the inspection response requires nonnegative values. Actual zero/negative meanings depend on the selected chunk function.
- Follow [shared editing rules](../editing.md); validate the complete effective result and preserve unrelated fields.

## Copy order and default

- Current framework behavior: copy_source_order sorts Copies like ORDER BY. It does not require all Copies at one value to succeed before the next value starts or define how many run concurrently.
- Default new Copies to 1 in the agreed design and write it explicitly; the current field remains required. Preserve existing values unless the user requests a change.
- Running equal-order Copies together and then advancing is only a possible future behavior; do not document or implement it as current semantics.
- Fresh-install SQL and published validation permit repeated order values while retaining Copy identity uniqueness and positive-int32 checks. Apply no longer defers the removed `uq_copy_group_order` constraint.
- If the server rejects a repeated order value, its backend predates this contract: report it instead of renumbering Copies. Preserve existing order values unless a change is requested.

Stored order values do not add an orchestration barrier.

## Landing names

The path is Source → landing files → Bronze. Despite the field prefix, copy_source_file_name and copy_source_file_pattern describe intermediate landing names rather than source-file selection.

- Propose one normal naming configuration from verified working metadata or documented conventions for the same connector/framework. Show the proposed values; preserve unrelated existing names.
- Both fields may be used together. Their combination, placeholders and generated names come from the actual landing writer and Bronze reader; no universal mutual-exclusion or wildcard rule is assumed.
- Relational extraction lands Parquet under the confirmed framework convention. File/API paths also use landing names, with their actual format governed by the connector. Preserving file contents does not require preserving the original filename.
- For custom naming, unclear descriptions or a writer/reader mismatch, ask for the relevant orchestration code and trace how both fields are consumed before finalizing values.

## Initial and incremental filters

The framework uses Copy Group Control state to choose initial or incremental extraction, then inserts the corresponding filter into the SELECT built from Attribute metadata. The saved value must include WHERE; the framework does not add it. These fields supply query fragments, not complete queries or pre-extraction commands.

- Default unused filter fields to null. If the selected field is null/blank, no filter is added from it. Both blank permits full extraction in either mode, such as a dimension-table reload; do not invent an incremental condition.
- Attribute custom code controls the SELECT items; these Copy fields control filtering. The target Data Operation independently determines how extracted data is loaded. Full extraction does not imply target replacement.
- Include the WHERE keyword and a complete condition using the actual source fields and SQL dialect. If a filter needs dynamic control values, use the framework's confirmed placeholder/substitution syntax; ask only when that required syntax is unknown. Do not guess mode selection from one control field.
- This SQL construction applies to relational extraction. Do not apply SQL filters to file-copy or API paths without the applicable connector contract.

For a source with a string `status` column, a saved filter can be `WHERE status = 'active'`. Saving only `status = 'active'` would omit the required keyword. Runtime control-value placeholder spellings remain connector/framework-specific; none are invented by this reference.

## Validation checklist

Enforcement is explained in [common checks](../validation.md#interpreting-table-checklists); run the local validator, then review anything marked for you.

| Rule | Check / why | Enforced by |
|---|---|---|
| `copy.shape` | Complete group/endpoint keys; nullable copy settings; explicit operations/order/active; delimiter <=20. Reject malformed complete records before staging. | Local validator + server |
| `copy.unique` | Copy Group + Ingestion Object Mapping unique. Prevent duplicate identity; inactive rows still reserve their keys. | Local validator + server |
| `copy.order` | Positive sorting value, default 1 for new rows; repeated values allowed. No runtime sequencing guarantee. | Local validator + server |
| `copy.references` | Copy Group and Object Mapping exist; optional Chunk/File Types resolve; source/target Operations resolve. Resolve dependencies using snapshot plus pending rows. | Local validator + server |
| `copy.chunking` | New/changed chunking requires the user's large-table request and a registered technique applicable to this table/System. Preserve unrelated existing settings. | Your review (no automated check) |
| `copy.target-operation` | Target function must match requested loading behavior. Copy Into appends; Override/custom scope comes from description. Source reference remains required but unused. | Your review (no automated check) |
| `copy.filters` | Nonblank initial/incremental fragments must include WHERE, a valid source condition and any confirmed placeholders. Blank is allowed and adds nothing; the framework adds no WHERE keyword. | Your review (no automated check) |
| `copy.scope` | Copy Group belongs to selected Tenant; endpoint Objects owned by it and on permitted Connections. Keep edits in the authorized Tenant. | Local validator + server |
| `copy.record-limit` | Chunk numeric parameter is null or a signed decimal string within BIGINT range. Preserve precision; do not impose a universal positive-only rule or row-cap meaning. | Local validator + server |
| `copy.limit-attribute` | Check parameter usage against selected chunk logic. Require a real source Attribute only if that logic expects one; apply function-specific ranges/defaults to numeric input. | Your review (no automated check) |
| `copy.landing-naming` | Filename/pattern must agree with the landing writer and Bronze reader. Validate only the confirmed combination/placeholders; do not treat them as source-selection filters. | Your review (no automated check) |
| `copy.live-dependencies` | Re-resolve dependencies at Apply; reject unexpected affected-row count. Snapshot checks cannot guarantee current server state. | Server only, at Apply |
| `copy.record-limit-contract-alignment` | Align signed authoring/DB limit with nonnegative inspect_metadata CopyDetails response; do not invent a positive-only authoring rule. A valid signed authoring value may not satisfy the current read-response contract. Validator note: Portable authoring validator accepts signed BIGINT range. | Your review |

## Confirmed behavior

Copy fields follow the consumer rules above: SQL values are WHERE fragments, source operation is unused, record-limit fields feed opt-in chunking, and filename/pattern fields name landing artifacts. Schemas govern field presence, types and registered references. Recheck behavioral meanings against the applicable framework version when custom usage or conflicting evidence arises.

[All metadata tables](../index.md) · [Common validation](../validation.md)
