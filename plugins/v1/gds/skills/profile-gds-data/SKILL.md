---
name: profile-gds-data
description: "Profile a registered physical Databricks table and prepare GDS Model Change Set profiling_profile records. Use for table/column profiling, batch-aware Profile metrics, null/distinct/blank/length evidence, or Profile records; use the generic Databricks skill for other SQL."
---

# Profile GDS Data

Build aggregate-only profiling evidence through governed `gds-workbench` tools. Never
request or expose connection values, credentials, raw physical rows, prompts, or raw
tool output. `execute_databricks_sql` is the only allowed SQL surface.

Follow the shared [Model authoring workflow](../../references/model-authoring-workflow.md).
Read [profiling contract](references/profiling-contract.md) before generating SQL or
records. Read [model datasets](../../references/model-datasets.md) only if another
affected dataset is authored. Route non-profile SQL to `$run-gds-databricks-sql`.

## Resolve the scope

Use `list_objects` and `get_objects` to resolve one registered active Object, its actual
source `connection_id`, physical key, Attributes, and `batch_attribute_name`. Use
`get_model` and `get_model_scope` when the result is intended for a Model. The Object
must already be in active Model Scope before its Profiles can validate.

Required execution values are:

- the exact `catalog.schema.table` Databricks relation;
- the active `environment_code`; and
- batch mode and ID values only when the Object declares `batch_attribute_name`.

Ask only for missing values that cannot be derived. Preserve exact identifier case. If a
batch Attribute exists, ask for `initial` with exactly one ID or `incremental` with the
complete ID list. Never silently remove the batch predicate, switch modes or
environments, or profile the batch Attribute. If there is no batch Attribute, use an
unfiltered aggregate query.

An empty incremental ID list is a configured no-op. Generate no SQL and no Profile
records; do not Stage or replace `profiling_profile` with zero-valued evidence.

Profile active, non-metadata Attributes only. Exclude the batch Attribute. Do not infer a
physical catalog or reuse another Object's Connection or batch IDs.

## Generate and execute

1. Call `describe_model_dataset` for `profiling_profile` when records will be authored;
   its live schema is authoritative.
2. Build the documented JSON spec from governed metadata and the user's choices.
   Require the relation schema/table to exactly match the registered Object key.
3. Run `node scripts/build-profile-sql.js --spec <path>`. The script emits bounded SQL
   chunks and the exact source `connection_id` and `environment_code` for each call.
4. If the user's request did not clearly authorize Databricks execution, show the
   relation, Attribute count, environment, and batch mode/count, then ask once. Never
   echo the generated SQL unless requested; submitted SQL is retained in the audit log.
5. Call `execute_databricks_sql` once per emitted chunk. Use the emitted source
   `connection_id`, not the Tenant's Global Data Store Connection ID. The server derives
   the Tenant and its Global Data Store Connection and resolves that Environment's
   connection parameters server-side.
6. Reject a result when rows or cells were truncated, columns differ from the documented
   record fields, an Attribute is missing/duplicated, or any count invariant fails.
   Combine chunks only after every chunk succeeds.

On `databricks_connection_*`, verify the source Connection and Environment choice, then
ask an administrator to correct stored values; never request them. On
`databricks_statement_failed`, report the statement index and correct only SQL. On
`databricks_result_too_large`, reduce the generated Attribute chunk size without
sampling rows or weakening metrics.

The tool returns aggregate rows only. Never add sample-value, top-value, pattern-value,
or raw-row queries. For more than 50 eligible Attributes, use every emitted chunk; do
not accept a truncated final result.

## Deliver

Return complete ID-free `profiling_profile` records as a proposal by default. These are
agent-assisted Change Set evidence, not an authoritative Profiling Run receipt. Use the
shared workflow for local/server boundaries and preserve unseen pending work.

Report the relation, environment, batch mode/count, successful Profile count, excluded
Attribute count, and any blocker. Do not echo unchanged records or raw results.
