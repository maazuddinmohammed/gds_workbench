---
name: analyze-gds-relationships
description: "Validate candidate relationships between registered GDS physical Attributes with governed aggregate Databricks SQL and prepare analysis_result evidence. Use for key overlap, referential coverage, target uniqueness, missing references, or new Model relationship analysis; not for general exploration or raw-row inspection."
---

# Analyze GDS Relationships

Test one directed source-to-target Attribute relationship using aggregate-only evidence.
Never request or expose credentials, connection values, raw physical rows, prompts, or
raw tool output. Use only `execute_databricks_sql` for SQL.

Follow the shared [Model authoring workflow](../../references/model-authoring-workflow.md).
Read [analysis contract](references/analysis-contract.md) before generating SQL or
records. Route other SQL to `$run-gds-databricks-sql`.

## Resolve intent and scope

Use `get_model`, `get_model_scope`, `list_objects`, and `get_objects` only as needed to
resolve both active scoped Attributes, their exact physical keys, actual source
Connection IDs, data types, and `batch_attribute_name` values. Use
`get_model_analysis` to avoid duplicating current evidence. Reuse an established
`relationship_kind` for the same semantics; do not create spelling variants of one
kind.

Required execution choices are:

- directed from/to Attributes and one stable `relationship_kind`;
- exact `catalog.schema.table` relations;
- one `environment_code`; and
- batch mode/IDs for each endpoint that declares a batch Attribute.

Ask only for missing choices that change the tested population or comparison. Preserve
identifier case. Do not silently swap direction, remove a batch predicate, normalize
values, or cast unlike types. An empty incremental batch on either endpoint is a no-op.

## Generate and execute

1. Call `describe_model_dataset(dataset="analysis_result")` before authoring; its live
   schema is authoritative.
2. Build the JSON spec in the contract. Use the from Object's actual source
   `connection_id`, not a Global Data Store Connection ID.
3. Run `node scripts/build-relationship-sql.js --spec <path>`.
4. If Databricks execution was not clearly authorized, show the endpoints,
   environment, batch scope, and comparison type, then ask once.
5. Call `execute_databricks_sql` once with the emitted SQL, source `connection_id`, and
   `environment_code`. The server derives Tenant ownership and resolves the Tenant's
   Global Data Store connection values server-side.
6. Reject truncation, unexpected columns or row count, or failed count invariants.
   Never replace exact metrics with samples.

Use an explicit `comparison_type` only when the user accepts that cast as the intended
relationship semantics. SQL is retained in the tool audit log; never put secrets in it.

## Turn evidence into a record

Merge the emitted identity, returned metrics, policy version `1.0.0`, and a concise
`relationship_basis` that names the tested populations and any cast. Confidence
expresses evidence coverage, not whether the result is favorable. Use `needs_review`
as the default new `analysis_result_status`; use `active` only after the evidence and
relationship are accepted. New records are unlocked.

Return an ID-free `analysis_result` proposal by default. For local or server work,
follow the selected shared boundary and preserve unseen pending work.

Report the relationship, environment, population scope, result, seven counts, and next
boundary. Do not echo SQL or raw tool output unless requested.
