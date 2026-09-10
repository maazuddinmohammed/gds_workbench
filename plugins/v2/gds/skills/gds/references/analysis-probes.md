# Analysis probes

Generate evidence queries for signaled candidates:

```sh
node scripts/gds-local.js analysis-plan --session "<session>" --plan-file "<probes.json>"
```

PowerShell uses `./scripts/gds-local.ps1` with identical arguments.

Example selection; replace names with registered Metadata:

```json
{"scope":"all_rows","probes":[{
  "id":"order_line_identity","kind":"key",
  "object":{"tenant_code":"OWNER","system_code":"ERP","connection_code":"SOURCE",
    "object_schema":"sales","object_name":"OrderLines"},
  "columns":["OrderID","LineNumber"]
}]}
```

Exact shapes:

- **key:** `id`, `kind`, `object`, `columns`.
- **dependency:** `id`, `kind`, `object`, `determinants`, `dependents`; lists must not overlap.
- **join:** `id`, `kind`, `from`, `to`; each endpoint is `{"object":<full key>,"columns":[<names>]}`. List order pairs columns; lengths and registered types must match. Different columns on one Object allow self-reference.

Limits: 1–50 probes; 1–8 distinct Attributes per list; unique IDs of at most 64 characters (letter first, then letters/digits/underscore/hyphen). No expressions, casts, filters, or batches.

Fresh Snapshots resolve active Model Input Scope and registered Source foreign/Bronze storage coordinates. Direct masking and masking inherited through registered ingestion Attribute Mapping block probes.

Numbered SQL and a source-qualified manifest remain under the task. Each query returns one aggregate row; no source values. `execution_state=not_run`: planning is not evidence. All-row scan cost and consistency across separate executions are unknown. Execute only under the saved SQL policy.

Interpret carefully:

- Keys count null-key rows, complete-key tuples, and duplicate rows beyond the first.
- Dependencies count conflicting determinant groups, not duplicate rows. Null-determinant rows are counted separately and excluded; null dependents are tuple values.
- Joins count missing/unused distinct tuples, duplicate-target extras, and separate null-key rows. Empty endpoints are inconclusive. Supported aggregates do not prove business identity or future cardinality.

Preserve counts, measurement time/scope, and decisions in sanitized object-analysis notes. Never turn composite findings into fabricated individual Analysis pairs. Single-Attribute join measurements use the complete existing `validation_*` group and policy `1.0.0` after execution. Empty evidence and structural uncertainty cannot finalize a design.
