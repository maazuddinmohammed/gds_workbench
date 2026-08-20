---
name: run-gds-databricks-sql
description: "Prepare, explain, or execute governed Databricks SQL through GDS. Use for general Databricks read analysis, multi-statement SQL, temporary views/tables, connection/environment routing, or execute_databricks_sql errors; route standardized profiling and relationship analysis to their dedicated skills."
---

# Run GDS Databricks SQL

Use only the governed `execute_databricks_sql` tool. It never accepts or returns a
hostname, warehouse path, token, or connection value.

Read [execution contract](references/execution-contract.md) when explaining routing,
checking SQL policy, or diagnosing an error. For fixed Change Set-ready Profile metrics
use `$profile-gds-data`; for relationship evidence use `$analyze-gds-relationships`.

## Resolve the request

Required inputs are:

- the active tenant-owned source `connection_id` (not the Tenant's Global Data Store
  Connection ID);
- the configured `environment_code`; and
- 1–100,000 characters of Databricks SQL.

Derive the source Connection with `list_objects`, `get_objects`, or
`get_tenant_details` when the user identifies a registered Object but not its ID. Ask
only for values that cannot be derived. Environment matching is case-insensitive, but
preserve the configured spelling in plans and results.

Every persistent physical relation must be `catalog.schema.table`. Preserve identifier
case and quote special names. The batch may contain at most 25 read statements or
unqualified temporary views/tables; it may not contain DML, persistent DDL, secrets,
credential functions, or an unqualified physical relation. The final statement should
return the desired bounded result.

## Prepare or execute

- **Explain/review/generate:** validate the SQL shape and return it without executing.
- **Execute/run:** the user's explicit request authorizes the Databricks call. State
  the source Connection ID, Environment, statement count, and physical relations, then
  call `execute_databricks_sql` once. Do not add unrelated statements.
- **Ambiguous:** show that same compact plan and ask once before execution.

Submitted SQL is retained in the append-only tool audit. Never place credentials,
tokens, sensitive literals, raw prompts, or comments containing secrets in it. Do not
echo SQL the user did not request to see.

Accept at most the final 50 rows. Treat `rows_truncated=true` as incomplete, and
`cells_truncated=true` as lossy. Narrow or aggregate the query; never imply the bounded
result is complete. On connection-configuration errors, verify only the selected
Connection and Environment and ask an administrator to repair server-held values.
Never request those values from the user.

Report the Connection ID, Environment, statement count, result columns/count,
truncation, and the answer or blocker. Do not claim that temporary objects persist
beyond the execution session.
