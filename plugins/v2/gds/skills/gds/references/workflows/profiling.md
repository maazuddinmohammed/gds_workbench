# Profiling

Use active applied Input Scope. Resolve reuse/reprofile/skip and all rows/batches from supplied intent or existing Profiles. Batch rules may name Source Tenant, originating System or Object; clarify conflicts only.

## Deterministic planning

Read `profile-plan`'s local command contract. Create a JSON plan with required `default_batch_id` (null means all rows), optional `tenants`, `systems`, `objects`, and `selected_objects`. Example:

```json
{
  "default_batch_id": null,
  "systems": [{"source_tenant_code": "DEMO", "system_code": "CRM", "batch_id": "batch-a"}]
}
```

Tenant entries contain `source_tenant_code`, `batch_id`. System entries additionally contain `system_code`. Object entries contain the five physical key fields (`tenant_code`, `system_code`, `connection_code`, `object_schema`, `object_name`) plus `batch_id`. `selected_objects` contains only those five fields; omission means all applied inputs. Use actual registered keys, not example values.

Specific Object assignments override System, then Tenant, then the default. Review the resolved intent if natural-language rules conflict. Run:

```sh
node scripts/gds-local.js profile-plan --session <session> --plan-file <plan.json>
```

The helper reads immutable Metadata/Model Snapshots directly, resolves Bronze's originating System through ingestion Mapping, and writes aggregate-only SQL plus an Attribute-key index under the task's working folder. Do not regenerate standard measurements by writing SQL manually. Each query returns at most 50 aggregate rows and respects the SQL size limit. The helper performs no remote execution.

A batch filter requires an assigned batch AND a registered batch column; otherwise no batch predicate. User batch text is encoded as data, never interpolated as SQL syntax. Read one generated query at a time only when executing it; the manifest maps `attribute_index` to physical Attribute keys, not database IDs.

## Evidence coordinates and execution

The planner uses registered Source foreign-catalog coordinates and Bronze placement. Missing coordinates fail; never substitute names or connect directly to Source.

Execute only under saved SQL policy/current authorization. Resolve the registered non-GDS source Connection for `execute_databricks_sql`; the server routes GDS execution. Never guess connection IDs.

Convert only returned aggregate metrics into complete `profiling_profile` records using the index and compact dataset schema; discard the temporary index field. Never fabricate metrics or persist raw tool envelopes/physical rows. Keep measurement time, batch scope, snapshot IDs, and unavailable outcomes in sanitized task evidence; do not invent record fields. Existing Profile evidence is reusable only with its known scope/freshness.

Report scoped, reused, measured, unprofiled, excluded and blocked coverage. Use `../analysis-probes.md` for deeper key/dependency/join evidence.

Non-null batch IDs are strings, for example `"712"`; `null` means all rows. Report each Object’s resolved scope before execution, including unfiltered Objects without a batch column.
