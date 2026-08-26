# Logical or Dimensional Code Generation

This is a local-only workflow. Generate code only from the matching applied Mapping, and require every selected Mapping record to be active. It never creates a Model Change Set and never executes, uploads, deploys, or runs SQL.

Default artifact type is `sql_file`; SQL dialect and target are Databricks. Use Python file or notebook only when the user explicitly overrides the artifact type.

- Logical route: `code/logical-to-silver/<SOURCE_SYSTEM>/<SCHEMA>.<TARGET>.sql`
- Dimensional route: `code/dimensional-to-gold/<SOURCE_SYSTEM>/<SCHEMA>.<TARGET>.sql`

Generate one deterministic file per target plus source System. Embed the Model revision and Mapping digest in its header. Require complete executable lineage, joins, filters, expressions, aggregations, dependency order, and write mode. If any is unresolved, block with a Resolution Prompt; never emit placeholder executable logic.

Require the committed name-based `GeneratorDocumentV1` for every selected package. For each exact target Object plus source System pair, call `get_model_code_generation_document` with the applied Model ID and route entity type. The read-only tool derives and strictly validates the document from active applied Mapping; use `result.document` directly in memory. A raw ID-bearing Mapping package or generic JSON object is insufficient; never reconstruct it from names or database IDs.

Bind only `result.proof` locally, then rerun readiness:

```text
generator-proof --session <session> --target logical-code|dimensional-code --proof <result.proof-JSON>
```

Then rerun readiness with `--proof-units <[{target_object_id,source_system_id},...]-JSON>` containing every selected unit. Selected lists exactly its requested packages; Full lists every eligible package. Never omit a unit to make readiness pass. Each proof must match the current Model Snapshot ID/revision. Never persist the Generator document or raw tool result as proof. If the MCP tool is missing from the deployed runtime: “Ask the platform owner to deploy the latest MCP server,” then stop safely.

The same digest is a no-op. For a different digest, show a diff before writing. If a file was manually customized, never overwrite it; create a reviewable proposal. Full covers all eligible packages; Selected covers exact requested packages. On completion set the task `done` and stop.
