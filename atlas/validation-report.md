# Atlas 0.1.2 historical verification

Verified 16 September 2026. This records that earlier source state, including retired components; its counts and compatibility conclusions are not verification of the current packages. Packages were rebuilt locally; nothing was deployed, published or executed against live Databricks. Use the [release verification scenarios](development/release-verification.md) for current checks.

## Changes

- Removed MCP `export_model_dbml`, its renderer/archive/contracts and registration. The public catalog now contains 37 tools.
- Removed Atlas CLI/native DBML generation. User Workbench export still combines the Snapshot with saved local changes. Agents use structured Model records, never DBML.
- Logical Guided and Grill Me share explicit relationship review. Supported FKs require relationship records; isolated Entities and disconnected groups require a user keep/connect decision. No invented joins or changes to locked records.
- Local/native graph checks flag both isolated Entities and disconnected components. Intentional standalone structures remain valid.
- SQL responses use compact JSON text with unchanged structured results and output schema. SQL calculations, batch filters, row limits and authorization rules are unchanged.
- Profiling imports the canonical aggregate result directly. Checks cover column names, coverage, bindings, truncation, indexes and metrics before writes. Curated input remains supported. Native numeric coercion is rejected; environment spelling follows MCP's case-insensitive comparison.
- Optional `max_attributes_per_query` accepts 1–50, default 50. Smaller groups preserve Object/batch scope. Guides use one response copy, bounded progress and automatic profile import.

## Response-size finding

An in-memory MCP client called the real registered tool with a fake executor returning 50 synthetic Attribute rows and 14 metric columns. No warehouse or real data was used.

| Measurement | Before | After |
|---|---:|---:|
| Text JSON bytes | 10,129 | 4,612 |
| Serialized MCP result bytes | 15,843 | 9,499 |

Results are lossless: about 54% less text and 40% fewer serialized bytes. Text and structured copies remain available for [MCP client compatibility](https://modelcontextprotocol.io/specification/2025-11-25/server/tools#structured-content); Atlas consumes only one.

This demonstrates avoidable serialization overhead, not the cause of the reported live error or a measured query speedup. Host limits, accumulated context and unusually large results still require the exact host error/logs to distinguish. Smaller groups are available for recovery; successful unrelated groups need not rerun.

## Verification

Counts describe separate suites, not an additive total. Focused reruns cover final changes.

| Check | Result |
|---|---|
| MCP/backend, including disposable PostgreSQL integration | 2,546 passed |
| Atlas workspace, lifecycle, profiling, native fallback and packaging | 74 passed in the full run; 2 new index cases and final compatibility cases passed in focused reruns (76 collected cases covered) |
| Existing GDS plus Atlas Workbench/planner JavaScript | 209 passed |
| Legacy GDS Python | 350 passed initially; 2 documentation-policy checks updated and passed; final packaging/docs rerun passed all 37 cases |
| Deployment packaging | 61 passed |
| Skill structure and Markdown references | All 14 skills and links/anchors passed |
| Python Ruff, formatting and Pyright | Passed; zero type errors |
| Whitespace and independent review | Passed; native index coercion found during review was fixed and tested |
| Release archives | Integrity and deterministic source equality verified; removed MCP DBML code absent |

Database tests used fixture-created disposable PostgreSQL containers with random credentials/databases and per-run sentinels. The sandbox initially blocked Docker; the approved local retry passed. No existing database was used.

Native tests ran with PowerShell 7.5.2. Windows CI now includes profiling importer cases; this host did not execute Windows PowerShell 5.1. Browser DBML overlay/export tests passed. Stage Runner source is unchanged; its previously verified 0.1.1 VSIX remains compatible.

See the [validation code index](development/validation-index.md) for modular rule implementations. Static graph checks expose missing connections; they do not prove business semantics.

## Current packages

- [Atlas plugin 0.1.2](dist/atlas-agent-plugin-0.1.2.zip)
- [MCP backend](../mcp_server/dist/gds-mcp-appservice-0.2.0.zip)
- [Stage Runner 0.1.1](dist/atlas-stage-runner-0.1.1.vsix)

These canonical local artifacts replace older archive variants. They may contain changes made after the historical verification above; check them against current source and tests before release.

Installing Atlas alone does not update the server. Current setup instructions are in the [Atlas README](README.md) and [MCP README](../mcp_server/README.md). Publication or deployment requires separate approval.
