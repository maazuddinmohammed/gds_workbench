# Logical or Dimensional Code Generation

This is a local-only workflow. Generate code only from the matching applied Mapping, and require every selected Mapping record to be active. It never creates a Model Change Set and never executes, uploads, deploys, or runs SQL.

Default artifact type is `sql_file`; SQL dialect and target are Databricks. Use Python file or notebook only when the user explicitly overrides the artifact type.

- Logical route: `code/logical-to-silver/<SOURCE_SYSTEM>/<SCHEMA>.<TARGET>.sql`
- Dimensional route: `code/dimensional-to-gold/<SOURCE_SYSTEM>/<SCHEMA>.<TARGET>.sql`

Generate one deterministic file per target plus source System. Embed the Model revision and Mapping digest in its header. Require complete executable lineage, joins, filters, expressions, aggregations, dependency order, and write mode. If any is unresolved, block with a Resolution Prompt; never emit placeholder executable logic.

Require the committed name-based `GeneratorDocumentV1` for every selected package. A raw ID-bearing Mapping package or generic JSON object is insufficient; never reconstruct it from names or database IDs. If the Snapshot/tool surface does not expose it, block and say: “Ask the platform owner to expose the committed name-based `GeneratorDocumentV1`, download a fresh Model Snapshot, then resume code generation.”

The same digest is a no-op. For a different digest, show a diff before writing. If a file was manually customized, never overwrite it; create a reviewable proposal. Full covers all eligible packages; Selected covers exact requested packages. On completion set the task `done` and stop.
