# Model-owned enrichment

Enrichment captures Model-specific meaning after profiling and before analysis. It changes neither physical Metadata nor web-agent defaults. Use the existing [Model Change Set authoring](change-sets.md), [effective local view](../platform/state.md), and review/Stage/Validate/Apply lifecycle.

## Inputs and reuse

Prefer profiling → enrichment → analysis → conceptual → logical for a full source-to-model request. Reuse applicable results; this is guidance, not a mandatory phase machine. Refresh Model evidence after a completed backend profiling run, preserving and reconciling pending proposals. After local enrichment, analysis can read it immediately with `select --view effective`; conceptual and logical work can consume the same local evidence. Do not Stage/Apply each phase. Submit related proposals together when the user is ready, respecting actual applied prerequisites for later workflows.

Inspect selected active applied Input Scope, registered physical types/comments, applicable profiles, current enrichment and concise business context. Distinguish measurements from inferences. A batch/sample does not prove whole-table uniqueness, non-nullability or absence of PII. `null` means unknown, not false. A PII finding never weakens physical masking or authorizes reading protected rows.

## Complete records

Use `object_enrichment` and `attribute_enrichment` datasets in the Model Snapshot and local `model-change-set` directory. `read_model_section` also serves both. Canonical keys are the owner-qualified physical Object key, plus `attribute_name` for an Attribute. No Model ID, database ID, execution history or raw samples belong in these records.

```json
[
  {
    "tenant_code": "GDS",
    "system_code": "ERP",
    "connection_code": "Warehouse",
    "object_schema": "bronze",
    "object_name": "Orders",
    "object_description": "Customer orders, one row per order.",
    "is_locked": false,
    "expected_revision": null
  }
]
```

```json
[
  {
    "tenant_code": "GDS",
    "system_code": "ERP",
    "connection_code": "Warehouse",
    "object_schema": "bronze",
    "object_name": "Orders",
    "attribute_name": "OrderNumber",
    "attribute_description": "Order identifier within the originating System.",
    "attribute_inferred_data_type": "STRING",
    "is_natural_key": true,
    "is_primary_key": null,
    "is_nullable": null,
    "is_pii": null,
    "is_locked": false,
    "expected_revision": null
  }
]
```

Descriptions accept nonblank text up to 2,000 UTF-8 bytes or null; inferred type accepts nonblank text up to 100 characters or null. Flags accept booleans or null. Descriptions allow tabs/newlines, not other control characters; inferred types allow no controls. Unknown fields fail validation.

`expected_revision` is a read-only saved-record witness. Copy it from the Snapshot when editing; new findings use null. Never invent or refresh this value alone: if it conflicts, refresh and reconcile the actual findings first. Server Validate and Apply reject stale findings, including concurrent web edits.

Preserve all unrelated fields when editing an existing record. Preserve saved human decisions unless the requested change explicitly covers them. `is_locked` is read-only: copy its saved value; new records use false. A locked Object enrichment also protects its Attribute enrichment. Attribute findings can exist without an Object enrichment row. Omitted records remain unchanged; there is no delete or lock-toggle operation.

Record concise rationale/evidence bindings in existing task evidence, not invented record fields. Persisted results use the same Model-owned tables as the web application. Physical-description corrections remain separate Metadata Change Sets.
