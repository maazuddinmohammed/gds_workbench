# Profiling Profile record

Owns `profiling_profile` field meanings and calculations. Use [Model Change Set authoring](change-sets.md) to read/write records and [query scope](../query-scope.md) to bind measurements. The workflow's profiling reference owns SQL generation, execution and retries.

## Identity and fields

Natural key: `tenant_code`, `system_code`, `connection_code`, `object_schema`, `object_name`, `attribute_name`. Use the registered physical Attribute key; see [ownership and physical identity](../metadata/tables/object.md#ownership-and-physical-identity). One current profile exists per Attribute in a Model; batches are not separate profile identities.

Required fields are marked **required**. Nullable measurements default to null when omitted; author complete records with these fields explicit. Let N = `row_count`, P = `non_null_count`, D = `distinct_count`, B = `blank_count`.

| Field | Accepted value / calculation |
|---|---|
| `tenant_code` | **Required.** Registered physical Tenant code; nonblank string, 1–100 characters. |
| `system_code` | **Required.** Registered physical System code; nonblank string, 1–100 characters. |
| `connection_code` | **Required.** Registered physical Connection code; nonblank string, 1–100 characters. |
| `object_schema` | **Required.** Registered Object schema; nonblank string, 1–400 characters. |
| `object_name` | **Required.** Registered Object name; nonblank string, 1–400 characters. |
| `attribute_name` | **Required.** Registered Attribute name; nonblank string, 1–400 characters. |
| `row_count` | **Required.** Nonnegative integer; `COUNT(*)` within the resolved row scope. |
| `non_null_count` | **Required.** Nonnegative integer; `COUNT(attribute)`. Includes blank strings. |
| `null_count` | **Required.** Nonnegative integer; N − P. |
| `blank_count` | Nonnegative integer or null. Supported strings: count non-null values whose `TRIM` value is empty; otherwise null. |
| `distinct_count` | Nonnegative integer or null. Supported strings/scalars: `COUNT(DISTINCT attribute)`, excluding null; otherwise null. |
| `min_data_length` | Nonnegative integer or null. Minimum string `LENGTH`, without trimming; null when inapplicable or no non-null string exists. |
| `max_data_length` | Nonnegative integer or null. Maximum string `LENGTH`, without trimming; null when inapplicable or no non-null string exists. |
| `avg_data_length` | Nonnegative decimal or null; at most 20 digits and six decimal places. Mean non-null string `LENGTH`, rounded to six decimals; null when inapplicable or no non-null string exists. |
| `percent_populated` | Percentage or null; 100 × P / N. |
| `percent_duplicates` | Percentage or null; 100 × (P − D) / P when D is supported. Counts extra occurrences beyond the first, not all rows in duplicate groups. |
| `percent_null` | Percentage or null; 100 × (N − P) / N. |
| `percent_blank` | Percentage or null; 100 × B / P when B is supported. |
| `percent_distinct` | Percentage or null; 100 × D / P when D is supported. |

Percentages are decimal values from 0–100 with at most seven digits and four decimal places. Round to four decimals. The current deterministic template returns **0 for a zero denominator**; an unsupported metric remains null. This convention does not make empty observations evidence of uniqueness or quality.

Supported strings are registered `STRING`, `CHAR` or `VARCHAR`, including their supported length forms. Distinct metrics additionally support registered boolean, numeric, date and timestamp scalar types in the verified generator. Complex/unrecognized types still receive row/non-null/null counts; unsupported distinct/string metrics are null. Use physical types for these operations, not inferred business types.

## Record checks and interpretation

- P + `null_count` = N; B and D, when present, are ≤ P.
- Minimum length ≤ maximum length when both exist; empty strings have length zero and participate in non-null/distinct counts.
- All counts/lengths are integers, not numeric strings, fractions or booleans. Preserve decimal precision; do not silently round integers through JavaScript's unsafe range.
- Validate formulas against the query result; the current record validator checks ranges/count consistency but does not recompute every percentage or enforce every type-specific null rule.
- The new/changed Attribute must belong to eligible Model Input Scope. Atlas profiling requires **active applied Input Scope** before measurement; broader effective-scope backend validation does not remove that prerequisite. Preserve historical records according to shared authoring rules.
- `attribute_index` is query transport metadata. Remove it after resolving the full Attribute key. Do not add Model/row IDs, status/lock fields, batch IDs, environment, measured-at, SQL or hashes to this record.
- Keep measurement scope, execution time and query bindings in durable task evidence under the shared query-scope rules. Reprofiling replaces this key's current measurements; it does not preserve batch history in this dataset.

For equivalent SQL, return Attribute indexes and counts as BIGINT, minimum/maximum lengths as INT, and average/percentages as DOUBLE, with typed nulls where inapplicable. Use floating-point arithmetic and the zero-denominator guard before percentage rounding. Convert results into the published record types and check them before local upsert.

## Complete synthetic example

Illustrates `model-change-set/profiling_profile.json`; keys are fictitious and must resolve to actual eligible Metadata before submission.

```json
[
  {
    "tenant_code": "demo_store",
    "system_code": "gds",
    "connection_code": "lakehouse",
    "object_schema": "bronze",
    "object_name": "customer",
    "attribute_name": "customer_name",
    "row_count": 10,
    "non_null_count": 8,
    "null_count": 2,
    "blank_count": 1,
    "distinct_count": 6,
    "min_data_length": 0,
    "max_data_length": 8,
    "avg_data_length": 4.125,
    "percent_populated": 80,
    "percent_duplicates": 25,
    "percent_null": 20,
    "percent_blank": 12.5,
    "percent_distinct": 75
  }
]
```

## Source pointers

Current contract: `mcp_server/gds_etl_workbench/domain/modeling_records.py` (`ProfilingProfileRecord`), `domain/snapshots/model.py` dataset key and `application/change_sets/model_validation.py` scope checks. Current formulas and SQL types: `plugins/v2/gds/skills/gds/scripts/profiling.js` (`buildQuery`). Changes to these calculations belong here and in the shared generator/validators, not in duplicate workflow instructions.
