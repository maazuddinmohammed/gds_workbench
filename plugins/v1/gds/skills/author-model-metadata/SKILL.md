---
name: author-model-metadata
description: "Explain exact GDS physical Metadata JSON shapes—not Model records—or produce synthetic examples from live schemas. Use for physical field meanings, canonical keys, validation rules, source/zone Metadata, or ingestion lineage examples. Route real workspace and Change Set work to the dedicated workflow skills."
---

# Author Model Metadata

Explain physical Metadata JSON. Do not mutate workspace files or enter a server
Change Set from this skill.

## Smallest path

1. Identify the exact dataset. Do not guess from an approximate name.
2. Call `describe_metadata_dataset(dataset, schema_version="1.0")`.
3. Explain only the requested fields, canonical key, constraints, dependencies, and
   population rules.
4. If requested, draft an obviously synthetic complete record: no database IDs,
   secrets, connection values, raw physical rows, or undocumented properties.
5. Validate it against the returned schema before calling it schema-valid. Otherwise
   label it unvalidated.

Use `get_metadata_snapshot(tenant_id, schema_version="2.0")` only when the user asks
for a broad baseline or comparison with current records. Never repeat or store its
temporary URL. Use focused catalog/search data when a bounded lookup is enough.

## Route real work

- For browsing, selecting Snapshot rows, or editing a local draft, use
  `$open-gds-metadata-workbench`. Snapshot data remains immutable.
- For local helper commands or any create, resume, inspect, Stage, Validate, Apply,
  or archive intent, use `$manage-gds-metadata` and stop at the requested boundary.
- For Model JSON, use `describe_model_dataset` and the matching Model skill.

Schema success does not prove cross-record references, Tenant scope, locks, or server
policy. Normally report at most three bullets and 120 words: answer, validation state,
and the next boundary. Do not echo full schemas or raw tool output unless asked.
