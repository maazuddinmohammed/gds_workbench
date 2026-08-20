# Profiling contract

## Inputs

Resolve these from `get_objects`; ask only for values not exposed by governed tools.

| Value | Source | Rule |
|---|---|---|
| Physical key | `get_objects` | Tenant, System, Connection, Object schema/name, and each Attribute name. |
| `connection_id` | `get_objects` | The Object's active source Connection, never its GDS Connection. |
| Relation | User or established context | Exact three-part `catalog.schema.table`. Schema/table must exactly match the registered Object key; every component is quoted. |
| `environment_code` | User or established context | Pass to `execute_databricks_sql`; use the canonical code returned by the tool. |
| Attributes | `get_objects` | Active, `is_meta_data=false`, excluding the batch Attribute. |
| Batch | `get_objects` plus user | Required only when `batch_attribute_name` is non-null. Preserve exact Attribute case. |

Databricks `environment_code` and profiling batch mode are different inputs. The former
chooses server-side connection parameters. Batch mode chooses the source rows included
in the aggregates.

## Generator spec

Create a temporary JSON file containing no secrets:

```json
{
  "connection_id": 41,
  "environment_code": "TEST",
  "physical_key": {
    "tenant_code": "TENANT",
    "system_code": "ERP",
    "connection_code": "SOURCE",
    "object_schema": "sales",
    "object_name": "orders"
  },
  "relation": {
    "catalog": "gds_test",
    "schema": "sales",
    "table": "orders"
  },
  "columns": [
    {"name": "order_id", "data_type": "BIGINT"},
    {"name": "status", "data_type": "STRING"}
  ],
  "batch": {
    "column": "batch_id",
    "data_type": "BIGINT",
    "mode": "incremental",
    "ids": ["1001", "1002"]
  }
}
```

Use `"batch": null` only when the registered Object has no batch Attribute. Batch IDs
may be JSON integers within JavaScript's safe range or decimal strings. Strings preserve
the full signed BIGINT range. `initial` requires one ID. `incremental` accepts up to
1,000 unique IDs. An empty incremental list emits no SQL and no Profile records; it is a
deliberate no-op, never a full scan or a set of zero-valued Profiles.

Run:

```text
node scripts/build-profile-sql.js --spec /absolute/path/profile-spec.json
```

The script prints one JSON execution plan. Call `execute_databricks_sql` for each
`chunks[].sql`, using the plan's `connection_id` and `environment_code`. Each chunk has
at most 50 Attributes and one read statement under 100,000 characters. When
`chunk_count=0`, report the configured no-op and do not Stage or replace
`profiling_profile`.

## Metrics

Each final result row already uses the exact `profiling_profile` field names.

| Metric | Definition |
|---|---|
| `row_count` | Rows after the exact batch predicate. |
| `non_null_count` | Non-null values for the Attribute. |
| `null_count` | `row_count - non_null_count`. |
| `blank_count` | String values whose trimmed value is empty; null for non-strings. |
| `distinct_count` | Exact distinct non-null scalar values; null for unsupported complex types. |
| length fields | Minimum, maximum, and average string length; null for non-strings. |
| `percent_populated` | `non_null_count / row_count * 100`. |
| `percent_null` | `null_count / row_count * 100`. |
| `percent_duplicates` | `(non_null_count - distinct_count) / non_null_count * 100`. |
| `percent_distinct` | `distinct_count / non_null_count * 100`. |
| `percent_blank` | `blank_count / non_null_count * 100`; null for non-strings. |

Percentages round to four decimals; average length rounds to six. A zero denominator
produces zero when the metric applies. The Profile contract additionally requires:

- `non_null_count + null_count = row_count`;
- blank and distinct counts do not exceed non-null count; and
- minimum length does not exceed maximum length.

Do not convert optional null metrics to zero. Returned floating values are JSON numbers
and can be used directly in Change Set records.

## Result columns

Require this exact order from every chunk:

```text
tenant_code, system_code, connection_code, object_schema, object_name,
attribute_name, row_count, non_null_count, null_count, blank_count,
distinct_count, min_data_length, max_data_length, avg_data_length,
percent_populated, percent_duplicates, percent_null, percent_blank,
percent_distinct
```

Reject `rows_truncated=true`, `cells_truncated=true`, incomplete chunk coverage, or an
unexpected Attribute. Never compensate by sampling or inventing metrics.
