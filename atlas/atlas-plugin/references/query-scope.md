# Query scope and Databricks execution

Shared authority for evidence-query coordinates, batch selection and execution. Profiling, relationship analysis and other workflows link here; their topic guides define the measurements. The deterministic Atlas Profiling and Analysis planners implement shared batch scope; the governed execution tool remains server-authoritative.

## Resolve coordinates and access

1. Bind the requested Model/Tenant context, exact authorized Objects, Metadata/Model Snapshot identities and selected environment. For Model analysis, query only active applied Input Scope; a discovered candidate outside scope does not add itself to scope.
2. Resolve [Object ownership and physical identity](metadata/tables/object.md#ownership-and-physical-identity). Source uses registered foreign-catalog relation/Attribute coordinates. Bronze/Silver/Gold use their actual catalog, Object and Attribute names when eligible for the requesting workflow. Physical placement determines SQL coordinates; the owning Model or Source Tenant is not a substitute catalog name.
3. Resolve an active non-GDS source Connection ID through authorized capabilities. The execution tool uses it to resolve its Tenant's GDS execution Connection/environment. Bind this ID/key before SQL preparation; do not pass the physical GDS Connection merely because the Object resides there. A cross-System/Tenant query must be authorized and accessible through the chosen execution context; do not move data or broaden access to make it work.
4. Apply saved SQL policy and environment from the [working method](working-method.md). Never allows query preparation, not execution. Inspect direct masking and known expression lineage; empty Attribute Mappings are not proof that data is unprotected. The SQL tool does not enforce these metadata masking rules for the agent.

## Batch selection

| Object metadata | Required behavior |
|---|---|
| batch_attribute_name populated | Resolve its active same-Object Attribute and supported physical type; require explicit nonempty batch_ids. Always use IN, including one ID. |
| batch_attribute_name absent | No batch predicate; a System assignment does not add one. |
| Declared batch Attribute missing, inactive, protected or unsupported | Resolve the problem before querying this Object. Do not remove the filter. |

Use the existing task's resolved choices when applicable. Group missing questions by **Source Tenant and originating System**, for example: "Which batch IDs should we use for CRM's batched Objects? Enter one or more IDs. Unbatched Objects will have no batch filter."

An explicit Object assignment overrides its System assignment. Several Systems can share IDs when the user says so. Bronze's originating System comes from verified Object Mapping provenance, not its physical GDS System. Missing or ambiguous origin, including multi-System targets with conflicting selections, needs explicit Object-level resolution; never select the first mapping or silently combine System lists.

No batch selection means unresolved, not all batches. Never infer the latest batch or broaden a zero-row selection. Store IDs as strings, preserve values and reject null/blank IDs or empty lists for batched Objects. Deduplicate/order the selection deterministically without changing its meaning.

Quote each identifier component with backticks, doubling embedded backticks. Encode each batch value's UTF-8 bytes as hex and use `CAST(CAST(X'<hex>' AS STRING) AS <validated physical type>)` in IN, reusing the verified encoder. Reject invalid or lossy conversions. User text and unvalidated types must not become SQL syntax.

Multiple IDs select their combined stored rows. They do not deduplicate repeated loads, reconstruct latest state or create separate measurements per batch. Do not split a batch set into independent aggregates and sum distinct counts.

## Joins and time scope

Resolve each endpoint independently and apply its filter **before** uniqueness, null, coverage and multiplicity measurements. An unbatched endpoint still has no batch predicate. A shared batch number across Systems does not prove matching populations or time periods.

Readable example for STRING batch columns, assuming these exact selections were supplied:

```sql
WITH orders_scope AS (
  SELECT * FROM `catalog`.`sales`.`orders`
  WHERE `batch_id` IN ('11')
), customer_scope AS (
  SELECT * FROM `catalog`.`sales`.`customers`
  WHERE `batch_id` IN ('10', '11')
)
-- Measure the candidate against these two scoped relations.
```

This illustrates row scope, not a complete executable probe. Generated queries select only needed Attributes and use the safe encoder above. Neither side automatically inherits the other's IDs. If missing matches may reflect older parent data, record that limitation and resolve the appropriate parent selection with the user. Do not silently remove its filter or add batch ID to the business join key.

## Execute bounded SQL

Current contract:

```text
execute_databricks_sql(
  connection_id=<resolved non-GDS source Connection ID>,
  sql=<contents of one prepared SQL file>,
  environment_code=<selected environment>,
  schema_version="1.0"
)
```

- SQL is text; the tool does not read local paths. Verify the file/hash, Connection, environment and row scope before execution.
- Current limits: 100,000 SQL characters, at most 25 statements, at most 50 result rows (deployment may configure fewer). Only the final statement returns rows. Prefer one standalone aggregate statement per file; do not concatenate independent SELECTs expecting every result.
- Each call has its own connection. Do not depend on temporary state surviving across calls. Reuse registered query coordinates without directly connecting to Source systems.
- Check `row_limit`, `rows_truncated`, `cells_truncated`, returned columns and expected result identifiers/counts. Incomplete results are not evidence for the full planned query. Preserve integer/decimal precision; the topic guide defines how to interpret metrics.
- If limits truncate a group, discard its partial measurement and prepare smaller result groups under the same row scope. Retain successful unaffected groups. A topic's permitted SQL-authoring fallback follows these same rules; it does not expand authorization.

## Evidence and recovery

Keep exact Object/Attribute keys, endpoint batch sets or unbatched state, actual environment/Connection, Snapshot IDs, Model revision, query hashes, execution time and coverage in concise task evidence. Never put these into record fields that do not exist. Do not persist raw physical rows or raw tool envelopes.

Planning is not execution. A SQL failure, unavailable evidence or mismatch remains explicit. Different row counts across supposedly identical scopes require reconciliation; equal counts alone do not prove stable data. Reuse evidence only with its scope and limitations intact.

Source contracts: `tools/databricks/execute_sql.py`, `infrastructure/databricks_sql.py`, current `scripts/profiling.js` and `scripts/analysis.js`. Atlas profiling accepts explicit batch-ID lists; Analysis reuses their exact endpoint filters. See the [runtime guide](../docs/runtime-guide.md) for planning inputs and output files.
