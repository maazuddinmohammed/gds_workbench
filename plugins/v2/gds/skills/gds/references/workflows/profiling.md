# Profiling

Use active applied Model Input Scope. Show existing Profiles and ask reuse, selected reprofile, or skip. For fresh measurements ask all rows or batch selections, accepting natural language by Source Tenant, originating System, or specific Object. Reuse answers; clarify conflicting assignments.

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

Source coordinates are Connection `foreign_catalog`, Object `fc_object_schema`, Object `fc_object_name`, and Attribute `fc_attribute_name`. Missing coordinates are an error. Never connect directly to a Source or substitute ordinary names. Bronze uses its placement `tenant_catalog`, `object_schema`, `object_name`, and `attribute_name`.

Execute generated queries only under saved SQL policy and current authorization. `never` executes none; `essential` resolves a blocking gap; `as_needed` permits useful bounded measurements. Resolve the registered non-GDS source Connection accepted by `execute_databricks_sql`; the server routes its GDS execution. Do not pass a guessed connection ID.

Convert only returned aggregate metrics into complete `profiling_profile` records using the index and compact dataset schema; discard the temporary index field. Never fabricate metrics or persist raw tool envelopes/physical rows. Keep measurement time, batch scope, snapshot IDs, and unavailable outcomes in sanitized task evidence; do not invent record fields. Existing Profile evidence is reusable only with its known scope/freshness.

Report scoped, reused, measured, unprofiled, excluded, and blocked coverage. Additional modeling investigations may use agent-written SQL where permitted, without replacing the fixed standard profiling contract.

Non-null batch IDs are strings, for example `"712"`; `null` means all rows. Report each Object’s resolved scope before execution, including unfiltered Objects without a batch column.
