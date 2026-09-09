# Shared orchestration rules

Read the applicable chapter before authoring. This is the canonical, expandable plugin reference for confirmed external runtime behavior. Add concrete consumer rules here as they become known; examples illustrate structure, not universal business logic. See [model conventions](model-conventions.md) for naming and audit policy.

## Ingestion orchestration pipeline

1. One Source Object has one Bronze counterpart, preserving source-column correspondence. Source names/types remain actual. Bronze physical types are `STRING`; names use lowercase snake_case. Resolve normalization collisions explicitly.
2. Registered RDBMS extraction writes Parquet. Source `attribute_custom_code` contributes to the extraction SELECT: quote the original identifier using its dialect and alias when needed, e.g. `"Customer Name" AS customer_name`. Preserve the original `attribute_name` and foreign-catalog identity.
3. Bronze reads the actual file field, including an extraction alias. Independently supplied files may have different names. Map the incoming field to the exact Bronze column.
4. Bronze `attribute_custom_code=null` delegates STRING casting to the loader. Populated custom code must perform its own final STRING cast; the loader does not add one. Do not invent a transformation field.

Resolve actual System Type, format, and supported expression syntax. Type conversion does not establish append/overwrite or batch policy.

## Target definitions and loading

Bronze/Silver/Gold use the chosen Source Tenant's configured `gds_connection_id`. Copy physical Tenant/System/Connection from that Connection into Object keys; never substitute Source or Model Tenant. `source_tenant_id` identifies the metadata/user-selected owner. Model Tenant is only a default for new Silver/Gold. Preserve contributor lineage. See Target Registration for current Binding restrictions.

Framework-executed SQL/DDL uses `schema.table`, without catalog: runtime selects the catalog. Temporary views are unqualified. If placements require different catalog contexts, resolve supported runtime access before code generation; never silently redirect a source to the target catalog. Direct evidence queries still need the registered execution coordinates; do not strip their required catalog.

Create all selected targets with `CREATE TABLE IF NOT EXISTS schema.table`. The target's own surrogate column is [`BIGINT GENERATED ALWAYS AS IDENTITY`](https://docs.databricks.com/aws/en/tables/features/generated-columns#use-identity-columns-in-delta-lake); omit it from load SQL. Foreign keys are mapped values, not generated identities. Use an alternative identity mode only when the actual target contract requires it. Produce known snapshot-based migration statements separately; CREATE IF NOT EXISTS does not alter existing tables. Registration supplies scripts, not execution.

## Mapping and code orchestration

Object steps define preparation, joins, filters, grain, branch outputs, and reconciliation. Attribute transformations supply field expressions and invalid/null behavior. Use self-contained temporary-view stages and one final explicit-column SELECT; the runtime performs physical loading/merge.

Project data columns, selected optional Source audit fields, and `SourceSystemID` last. Omit the target's own generated key and the nine framework-populated audit columns defined in `model-conventions.md`. Keep all modeled columns in DDL/Binding; Mapping identifies database/framework population without fabricated source expressions.

Use the registered runtime batch placeholder (the supplied SQL examples use `wid_GDSBatchID`) only where Mapping requires a batch filter. Do not substitute a profiling batch literal or filter historical lookup tables indiscriminately. Aligned UNION ALL requires disjoint keys or an explicit preceding identity reconciliation. File grouping belongs to Code Generation.

## Process orchestration

Runtime selection is Tenant, System, and Copy Group. `default` as the Copy Group selector means all Copy Groups for that Tenant/System. Stored Process Groups reference actual Copy Groups; never fabricate a group named default to represent the selector.

Normally one System uses one Copy Group; multiple groups permit selective ingestion and processing. Reuse the associated ingestion Copy Group unless ambiguous. Only relevant ingested groups are processed. Check prerequisite order when splitting groups. Derive filenames/targets from applied Code and Mapping; obtain missing paths and execution details from the user. Registration does not deploy, schedule, or run artifacts.

## Extending this reference

For a new rule, record when it applies, the actual consumer behavior, affected fields, and a small fictional example where useful. Distinguish user-confirmed behavior from runtime verification. Keep secrets, connection values, physical rows, prompts, and execution dumps out of these instructions.
