# Workflow configuration implementation — 2026-09-07

The user authorized implementation after the design review. Existing uncommitted
work is preserved. No live database migration, deployment, push, or publication
is part of this change.

The implementation provides fourteen independently editable default prompt
configurations across the existing workflows. Metadata enrichment uses separate
Object and Attribute prompt identities under its existing run. The catalog
contains 169 workflow/stage variable registrations. Readers query frozen
precomputed evidence using natural keys, optional selectors, bounded pages, and
run-bound cursors. Explicitly selecting no tools is supported.

The renderer supports data access, projections, filtering, conditions, and
bounded loops using restricted Jinja. Unknown variables/fields fail before the
model call; absent registered values render as null. Only rendered evidence and
backend output/repair controls reach the provider. The backend retains its full
scope ledger for validation. [Jinja sandbox documentation](https://jinja.palletsprojects.com/en/stable/sandbox/)
explains the sandbox boundary; this implementation also adds syntax, work, and
output-size limits.

Prompt screens provide grouped searchable variables, schemas/examples, cursor
insertion, optional tool selection, separate System and Instruction editors, and
a synthetic preview. Preview does not load live metadata, save a version, or call
a model. Code and Validation retain public null execution mode while their
internal model calls support optional readers.

Mapping, Code Generation, and Validation retain their existing output and save
rules. Validation is a complete active ledger: omitted unlocked records retire,
and saved locks remain protected. See [validation lists](workflow-validation-design.md).

## Verification

| Check | Result |
|---|---|
| Full MCP/backend/SQL/packaging/Python plugin suite | 2,721 passed; 44 PowerShell tests skipped because PowerShell is unavailable |
| Final duplicate-key adapter/repair follow-up | 50 passed, including repeated fields and description targets |
| Final rebuilt web/notebook packaging | 61 passed |
| Notebook source, Python 3.12 | 159 passed |
| Extracted notebook artifact, Python 3.12 | All 3 probes passed |
| Frontend | 351 tests; TypeScript and production build passed |
| Workbench JavaScript | 52 passed |
| Stage Runner extension | 73 passed; types, compile, and VSIX passed |
| Python static checks | Backend/MCP/notebook Ruff and Pyright passed |
| Dependency locks | Root/backend frozen lock checks passed offline |
| Workspace diff | Whitespace check passed |

The full suite includes installed default prompt execution through all modeling
and downstream workflow paths, physical metadata completion, correction loops,
locks, replay, scope validation, and governed persistence. The final adapter
follow-up rejects repeated JSON object keys before parsing can discard earlier
values, then exercises the existing bounded repair path. An explicit empty tool
selection also reaches the mocked hosted SDK with no tools and no forced tool
choice. Provider payload checks confirm hidden context is excluded.

Database tests used only fixture-created disposable PostgreSQL containers.
Provider calls were mocked. Browser checks used synthetic data at desktop and
390px viewport widths. Live Azure/Databricks/provider behavior and Windows
PowerShell 5.1 execution remain outside this local verification.

## Local artifacts

- [Web application source ZIP](../artifacts/databricks-ui/gds-workbench-app-source.zip)
- [Notebook source ZIP](../artifacts/databricks-ui/gds-workbench-notebooks.zip)
- [MCP App Service ZIP](../mcp_server/dist/gds-mcp-appservice-0.2.0.zip)
- [GDS plugin ZIP](../plugins/v2/dist/gds-agent-plugin-0.5.0.zip)
- [Stage Runner VSIX](../plugins/v2/dist/gds-stage-runner-0.1.0.vsix)
- [Frontend production entry](../web_app/frontend/dist/index.html)

These are local rebuilds. Existing databases were not migrated: SQL changes
remain part of the repository's fresh-install sequence. Windows PowerShell 5.1
fallback execution requires its Windows runner. No live provider, Azure, or
Databricks execution was performed.

## Mapping defaults and local review — 2026-09-08

The approved global templates are installed by the new governed seed `07`:
Object Mapping uses nullable `source_objects` and `steps`; Attribute Mapping
uses optional nullable `source_attributes` and required `transformation`.
New Logical and Dimensional Mapping runs resolve omitted/null selectors to
these defaults. Independent custom choices and frozen run replay are preserved.
The Mapping dialog labels this choice **Use global default**.

The plugin's manual Mapping guidance uses the same document shapes. Its Model
Snapshot does not contain the template catalog, so it references a default code
only when installation is established; otherwise it retains a null template code.
It does not change existing Mapping documents or seed populated databases.

Focused verification covered 34 disposable PostgreSQL cases for seed replay,
conflicting definitions, custom/default combinations, both Mapping routes,
missing defaults and frozen run replay. Backend command/local runner/container
checks passed 78 cases. The frontend passed 354 tests, TypeScript and production
build; notebook source passed 159 tests and all three extracted-artifact probes.
The full MCP/backend/SQL/packaging/plugin regression and final affected-suite
rerun account for 2,747 passing checks and 44 Windows PowerShell skips. The two
initial plugin documentation/archive failures were corrected; the complete
plugin follow-up passed 192 checks with the same 44 skips. The plugin ZIP and
web/notebook source archives were rebuilt locally.

An actual production Docker build exposed a test helper included by TypeScript.
The helper now lives in the existing excluded test directory; the production
dependency graph excludes Vitest and the `npm ci --omit=dev` image build passes.

The supported local runner created a fresh disposable PostgreSQL stack with
generated credentials and a per-run sentinel. The running application returned
200 from `/healthz`, `/readyz` and `/`. Its read-only output-template API verified
both active defaults, valid schema digests and exact ordered fields. Browser
review confirmed the local Tenant and the fourteen published Prompt Templates.
The Prompts page is open at `http://127.0.0.1:8080/tenants/1/prompts`.
Local fake provider/Databricks adapters remain in use. Existing external
databases were not modified.

## Cleanup and complete rebuild — 2026-09-08

Audited Python modules/configuration, frontend imports and exports, plugin
registrations, extension assets and packaged consumers before removing code.
Removed 461 lines of unreachable legacy Code/Validation prompt-input builders
and fallbacks; canonical workflow variables already handled all twelve names.
The distinct Mapping compatibility paths remain. Removed two unused frontend
components (`NumberField` and `LogicalAttributesLedger`) and their unused types.
Existing uncommitted source files and approved design documents were preserved.

Cleared the obsolete marked `artifacts/databricks-ui-foundry` build (637 files,
9.36 MB), 78 generated cache directories and Finder metadata. Moved 158 unused
scratch logs, previews and diagnostic scripts to a local recovery directory
outside the repository. Markdown working notes and the final analysis diagram
remain. The 290 MB notebook test environment is now excluded from Docker's
build context; installed development environments remain available.

Corrected stale plugin version, runtime configuration and enrichment references.
Plugin enrichment now describes replacement of selected unlocked descriptions,
preserved locks and no automatic locking, consistent with the confirmed rules.
Instruction length limits remain unchanged.

Rebuilt the frontend, combined web Docker image, MCP ZIP, web and notebook
source ZIPs, plugin ZIP and Stage Runner VSIX. All five archives match source;
the expanded web/notebook trees, manifests and checksums also match. The existing
local review app and its disposable database were left running.

Frontend 354 tests, Workbench JavaScript 52 tests, extension 73 tests and notebook
159 tests passed. Python lint/format/type checks passed for MCP, backend and
notebooks. Packaging checks passed (73 web/plugin cases and 5 MCP cases), along
with all three extracted Python 3.12 notebook probes. The combined Docker image
built successfully from cleaned source.

The fresh final MCP/backend/SQL/packaging/plugin regression passed **2,749 tests**
with **44 Windows PowerShell skips**. It ran after every cleanup edit and archive
rebuild, using only fixture-created disposable PostgreSQL containers. Final
workspace whitespace checks passed. No commit, push or deployment was performed.
