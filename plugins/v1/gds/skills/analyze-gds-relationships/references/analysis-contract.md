# Relationship analysis contract

## What this proves

Policy `1.0.0` compares distinct non-null source and target values without implicit
normalization. It returns only aggregates:

| Field | Definition |
|---|---|
| `validation_source_non_null_count` | Source rows with a non-null comparison value. |
| `validation_source_distinct_count` | Distinct non-null source values. |
| `validation_target_non_null_count` | Target rows with a non-null comparison value. |
| `validation_target_distinct_count` | Distinct non-null target values. |
| `validation_source_missing_target_count` | Distinct source values absent from the target. |
| `validation_unused_target_count` | Distinct target values absent from the source. |
| `validation_duplicate_target_key_count` | Target rows beyond the first row for each repeated non-null target value. |

The result is `inconclusive` when either endpoint has no non-null values, `supported`
when every source value exists in a unique target, and `unsupported` otherwise.
Unused target values do not invalidate a directed source-to-target relationship.

This validates value coverage and target uniqueness for the selected populations. It
does not prove business meaning, minimum participation, temporal validity, or a
declared database constraint. Put those limits in `relationship_basis`.

The `analysis_result` contract has one Attribute at each endpoint. This workflow does
not prove a composite-key relationship: separate component checks may be supporting
evidence, but must retain that limitation.

## Inputs

Resolve physical keys, data types, batch Attributes, and the source `connection_id`
from governed metadata. Both Attributes must be active in the Model Scope and owned by
the same Model Tenant. Relations must be exact three-part names; schema/table must
match each registered Object key.

One `environment_code` selects server-side connection parameters. Each endpoint has
its own optional batch selection. If an Object declares `batch_attribute_name`, ask
for `initial` with one ID or `incremental` with the complete ID list. Use `batch: null`
only when that Object has no batch Attribute. If either incremental list is empty,
generate no SQL and no `analysis_result` record.

The generator accepts integral batch Attributes, including `DECIMAL(p,0)`, and at most
1,000 unique IDs per endpoint. For another batch type, stop and report the unsupported
filter; never remove the required predicate or interpolate unvalidated values manually.

Values are compared as declared when normalized data type strings match. For unlike
types, `comparison_type` is required and casts both sides with `CAST`; failures remain
visible. Never silently trim, case-fold, parse, or use `TRY_CAST`.

## Generator spec

Create a temporary JSON file containing no secrets:

```json
{
  "connection_id": 41,
  "environment_code": "TEST",
  "relationship_kind": "foreign_key_candidate",
  "comparison_type": null,
  "from": {
    "physical_key": {
      "tenant_code": "TENANT",
      "system_code": "ERP",
      "connection_code": "SOURCE",
      "object_schema": "sales",
      "object_name": "orders",
      "attribute_name": "customer_id"
    },
    "relation": {"catalog": "gds_test", "schema": "sales", "table": "orders"},
    "data_type": "BIGINT",
    "batch": {"column": "batch_id", "data_type": "BIGINT", "mode": "incremental", "ids": [1001, 1002]}
  },
  "to": {
    "physical_key": {
      "tenant_code": "TENANT",
      "system_code": "CRM",
      "connection_code": "SOURCE",
      "object_schema": "crm",
      "object_name": "customers",
      "attribute_name": "customer_id"
    },
    "relation": {"catalog": "gds_test", "schema": "crm", "table": "customers"},
    "data_type": "BIGINT",
    "batch": null
  }
}
```

Run:

```text
node scripts/build-relationship-sql.js --spec /absolute/path/analysis-spec.json
```

The plan contains `analysis_identity`, batch summaries, the fixed policy version, the
expected columns, and one SQL statement. On `no_op=true`, do not execute or create a
record. Otherwise call `execute_databricks_sql` with the plan's `connection_id`,
`environment_code`, and `sql`.

## Result acceptance

Require exactly one row, these columns in order, and both truncation flags false:

```text
validation_source_non_null_count, validation_source_distinct_count,
validation_target_non_null_count, validation_target_distinct_count,
validation_source_missing_target_count, validation_unused_target_count,
validation_duplicate_target_key_count, validation_result
```

All counts must be non-negative. Distinct counts cannot exceed non-null counts;
missing/unused counts cannot exceed their respective distinct counts; and duplicate
target count must equal target non-null count minus target distinct count. Recompute
the policy outcome and require it to match.

For `relationship_confidence`, use `high` only when the selected populations are the
complete intended evidence and comparison semantics are unambiguous. Use `medium` for
bounded but representative evidence and `low` for exploratory evidence. Do not use
confidence to hide a failed validation.
