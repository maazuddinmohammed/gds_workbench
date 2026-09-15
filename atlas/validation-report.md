# Atlas 0.1.1 local verification

Verified 15 September 2026. Artifacts are ready for installation; nothing was deployed, published or written to external systems.

## This release

- First-class `atlas_checkStageRunner` returns readiness and safe backend identity.
- Accept can import the actual draft response and prepare the Stage manifest in one invocation.
- Preparation imports or verifies cached draft evidence; Stage still checks current server state.
- Stage reads the acknowledged digest from its operation. Apply approval can use the saved review without a copied digest or extra input file.
- Local evidence uses canonical identifiers and accepts existing supported server/legacy aliases. Conflicting aliases fail.
- Helpers and extension tools can export exactly one JSON document. Existing files are protected; optional export failures preserve the operation outcome.
- Operation checkpoints accept exact governed responses or supported MCP envelopes, without a curated intermediate file.
- Logical and Dimensional/Gold Guided and Grill Me are explicit starter choices. The user guide is shorter; developer documentation and the preview image are excluded from the plugin.
- Every workflow uses the shared submission procedure. Domain references retain detailed contracts through progressive disclosure.

The prior catalog/startup changes remain included: evidence SQL uses the physical owner's `tenant_catalog`, and Atlas opens/reuses Workbench at startup before setup questions.

## Current verification

Counts describe separate suites, not a deduplicated total. Focused reruns are not added to their containing suites.

| Check | Result |
|---|---|
| Atlas workspace, lifecycle, profiling, native fallback and packaging | 66 passed; no skips |
| Existing GDS plus Atlas Workbench/planner JavaScript | 206 passed; no skips |
| Atlas Stage Runner | 114 passed; TypeScript and bundle passed |
| Packaged VS Code extension host | 9 checks passed against a disposable loopback fixture |
| Skill structure | All 14 skills passed validation |
| Python Ruff, formatting and Pyright | Passed; zero type errors |
| Whitespace | Passed |
| Release archives | Version 0.1.1 and integrity verified; plugin matches a fresh deterministic source build; VSIX bundle/README match source |

Native cases ran with PowerShell 7.5.2. CI includes the shared handoff cases for Windows PowerShell 5.1; this host does not verify that exact runtime.

New regressions cover direct Metadata/Model responses, malformed or concatenated JSON, conflicting identifiers, invalid scope/types, changed acknowledged files, changed server review, separate Apply approval, output overwrite/path protection, failed optional export, and re-accepting changed content before Stage. Failed-validation recovery keeps its separate earlier-draft binding.

A separate instruction review exercised approved Metadata enrichment followed by Stage without Apply, then a later explicit Apply. Both paths use exact response files and operation-bound evidence. This was an instruction review, not a live server execution.

See the [validation code index](development/validation-index.md) for modular rule implementations and tests. Static checks do not prove business meaning or runtime SQL semantics; server authorization, locks and revision checks remain authoritative.

## Earlier verification of unchanged components

These results come from the complete implementation run, not a rerun for this plugin/extension update:

| Suite | Result |
|---|---|
| MCP/backend, including disposable PostgreSQL integration | 2,552 passed |
| Deployment packaging | 61 passed |
| Web frontend | 375 passed; types and production build passed |
| Notebook source on Python 3.12 | 161 passed |
| Extracted notebook artifact probes | 3 passed |
| Existing GDS plugin Python regression suite | 352 passed with PowerShell available |

Database tests used only fixture-created disposable PostgreSQL containers, random credentials/databases and per-run sentinels. No existing database was substituted.

Earlier synthetic instruction reviews covered metadata enrichment, Logical modeling with SQL Never, and selective code regeneration. The smaller-model review reached 18/18 after clarification; the stronger-model review scored 17/18 before final corrections. These are limited subjective reviews, not execution tests or general model benchmarks.

## Limits

- No live Databricks or deployed-backend end-to-end execution was performed. Existing installations still need the separate [backend compatibility review](../docs/atlas-backend-compatibility.md).
- Workbench DOM/interaction tests passed. Browser policy prevented local-page automation; directory permissions, zoom and visual rendering still need manual browser verification.
- The earlier web frontend build succeeded with a bundle-size warning.
- New Python generation and new Member-table support remain outside the agreed first release; existing records are preserved.

## Artifacts

- [Atlas plugin ZIP](dist/atlas-agent-plugin-0.1.1.zip)
- [Atlas Stage Runner VSIX](dist/atlas-stage-runner-0.1.1.vsix)
- [Previously built MCP backend ZIP](../mcp_server/dist/gds-mcp-appservice-atlas-0.1.0.zip)

Superseded Atlas 0.1.0 ZIP/VSIX files were removed. Install the matching 0.1.1 plugin and extension together. No installation or deployment was performed here.
