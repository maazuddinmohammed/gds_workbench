# Logical or Dimensional Code Generation

Require matching active applied Mapping. Default is `sql_file`; Python file or notebook needs
explicit override. Apply stores Code and never executes, uploads, or deploys it.

Load the compact `generated_code` dataset contract immediately before its first write.

For each target, enumerate active source Systems. Missing generator proof at preflight is an
expected preflight action, not a terminal blocker: call `get_model_code_generation_document` per
exact target/source pair with applied Model ID
and route entity type. Use every `result.document` (`GeneratorDocumentV1`) directly in memory; never reconstruct it
from names or database IDs. A raw Mapping package or generic JSON object is insufficient.

Bind each `result.proof`, then run final readiness with every pair in `--proof-units`:

```text
generator-proof --session <session> --target logical-code|dimensional-code --proof <result.proof-JSON>
```

All results for one target must agree on `target_mapping_context_digest` and
`target_source_context_digest`. Copy those target digests—not legacy
`mapping_context_digest`—into one complete `generated_code` record for that target Object.
Hash the complete UTF-8 content into `generated_code_digest`. It has no Code-specific size
cap and remains one logical artifact and record; oversized records use
`server-handoff.md` fragment transport.

Default GDS/Julius Databricks SQL may contain semicolon-separated statements and same-session
temporary views. For a multi-System target, use the user-approved layout; the combined default is
one isolated temporary-view branch per System followed by one aligned `UNION ALL`. Load
`../examples/multi-system-target.sql` only for that case. Use a governed batch predicate/token when
provided; never invent one. The final statement must match the target shape and natural key. Runtime
performs the merge; never emit it.

Process may contain one row per System pointing to this same artifact. Do not duplicate the artifact:
runtime executes it once, parallelizes distinct safe same-order artifacts, and stops later orders on
failure. An upstream/common target read can support a dependency; a target self-read may be a prior-state
lookup. Never infer a rerun or execution order without Mapping, Process, or user evidence. The governed
Model still stores one artifact per target Object; alternate external file layouts require an explicit task contract.

Require complete lineage, joins, filters, expressions, aggregations, and dependency order.
Unresolved executable logic blocks with a Resolution Prompt; never emit placeholders. When
the MCP tool is missing: “Ask the platform owner to deploy the latest MCP server,” then stop.

Compare against current Code. Same digest is a no-op; show changed content before writing and
preserve locked records. Use complete explicit inactive records for intended deactivation,
never omission. Stage `generated_code` only after Mapping Apply, follow governed Model gates,
and stop after Model Apply.
