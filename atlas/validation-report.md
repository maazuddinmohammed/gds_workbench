# Atlas 0.1.0 local verification

Verified 15 September 2026. Local implementation and artifacts only; no deployment, external writes, Databricks execution or populated-database changes.

## Delivered

- Portable Agent Plugins 1.0 package: 14 skills, compact shared references, templates and user/runtime guides.
- Workspace/session/tasks, separate Metadata-owner roots, Snapshot installation, local drafts, input-bound validation and separate review/Stage/Apply evidence.
- Deterministic batch-aware profiling/analysis planning, bounded aggregate import, shared effective-graph validation and Snapshot-plus-draft DBML.
- Readable Workbench with local editing, Snapshot/proposal comparison and modular validation files.
- Modular Stage Runner, including direct/chunked/large-Code submission and read-only recovery of uncertain Stage writes.
- Required backend contracts: Process Group dependency order, repeated Copy order, key/audit alignment, protected Bindings and governed Mapping consumer context.

DDL and transformation code are agent-authored using the supplied rules/templates, matching the existing plugin approach. The plugin does not silently synchronize code files from Snapshots. New Python generation and new Member-table support remain outside the agreed first release; existing records are preserved.

## Results

Counts describe separate suites, not a deduplicated total. Focused reruns are not added to their containing suites.

| Suite | Result |
|---|---|
| MCP/backend, including disposable PostgreSQL integration | 2,552 passed |
| Deployment packaging | 61 passed |
| Web frontend | 375 passed; types and production build passed |
| Notebook source on Python 3.12 | 161 passed |
| Extracted notebook artifact probes on Python 3.12 | 3 passed |
| Existing GDS plus Atlas Workbench/planner JavaScript | 197 passed, no skips |
| Atlas Stage Runner | 103 passed; TypeScript and bundle passed |
| Packaged VS Code extension host | 7 checks passed |
| Native PowerShell fallback | 22 passed on PowerShell 7.5.2, no skips |
| Atlas workspace/lifecycle/profiling/package Python suite | 53 passed, no skips; includes native cases above |
| Existing GDS plugin Python regression suite | 352 passed, no skips, with PowerShell available |
| Python Ruff/Pyright, whitespace | Passed for changed backend/MCP source and new Atlas Python helpers/tests; zero final type errors |

Database tests used only repository-created disposable PostgreSQL containers with random credentials, databases and per-run sentinels. The full backend run used the approved local Docker fixture path; no existing service or supplied DSN was substituted.

Final package verification compares the delivered ZIP byte-for-byte with a fresh deterministic source build. An intermediate stale archive was rebuilt after final formatting; the final combined suite passes against the rebuilt artifact.

## What the tests cover

- Owner/Model isolation; absolute safe paths; archive traversal/symlink rejection; Snapshot hashes and revision fences; preservation of unrelated pending edits.
- Effective Snapshot-plus-draft graphs; schema/key/reference/lock validation; source coverage; naming, surrogate/audit policy and truthful optional evidence.
- Batched SQL and type handling; masked-column exclusion; bounded groups; exact input/query/result bindings; complete aggregate coverage and metric consistency.
- Approval/digest/revision binding; server-review evidence; separate Apply approval; uncertain Stage recovery without write replay; rollback-safe Snapshot/DBML replacement.
- Deterministic plugin packaging, source/archive equality, manifest/skill contracts, packaged links and required assets.

See the [validation code index](atlas-plugin/docs/validation-index.md) for rule-to-file/function/test mappings. Static SQL checks do not prove runtime SQL semantics; agent/user review remains necessary for business meaning and model quality. Live authorization, locks and server state are revalidated by the backend.

## Validation parity follow-up

A subsequent comparison with GDS found four native PowerShell gaps not covered by the first suite. The fallback now checks missing registered Metadata owners, declared task Snapshot bindings, cross-owner key-contract agreement and generated SQL policy. Regression cases reproduce the original omissions and require the same rejection through Node and PowerShell, including local acknowledgement.

Independent Metadata work is not blocked by an unrelated missing owner's Snapshot. Existing SQL/Python artifacts and inactive records remain preserved. Decision files, SQL evidence queries and Assertions stay optional: record/graph and Analysis-count checks run directly; checks about a chosen citation use the declared evidence. SQL parity cases also exercise quoting, temporary stages and Unicode identifier casing under English and Turkish locales.

The final 53-case Atlas suite passed against the rebuilt plugin ZIP; all 197 combined GDS/Atlas JavaScript cases passed. Ruff, formatting, Pyright and whitespace checks passed. Backend and extension source did not change in this follow-up; their results above are from the complete implementation run.

## Instruction dry runs

Three synthetic tasks were reviewed with a smaller model and a stronger model: metadata-only enrichment, Logical modeling under SQL Never, and selective code regeneration with locks/manual edits. The smaller model's review improved from 14/18 to 18/18 after clarifying the instructions. The stronger model scored 17/18 before final documentation corrections. These are limited, subjective instruction reviews, not execution tests or a general model-quality benchmark. Raw prompts/transcripts were not retained.

## Verification limits

- Windows PowerShell 5.1 was unavailable on this macOS host. Its CI parity job is configured; the local native run used PowerShell 7.5.2.
- Browser URL policy blocked local-page automation. Workbench DOM/interaction tests passed, but native directory-picker permissions, zoom and visual rendering need manual browser verification. The restriction was not bypassed.
- The existing frontend build reports a bundle-size warning; the build succeeds.
- No live Databricks or deployed-backend end-to-end run was performed. Existing installations need the separate [backend compatibility review](../docs/atlas-backend-compatibility.md).

## Artifacts

- [Plugin ZIP](dist/atlas-agent-plugin-0.1.0.zip)
- [Stage Runner VSIX](dist/atlas-stage-runner-0.1.0.vsix)
- [MCP backend ZIP](../mcp_server/dist/gds-mcp-appservice-atlas-0.1.0.zip)

Artifacts were rebuilt locally. They have not been installed, published or deployed by this work.
