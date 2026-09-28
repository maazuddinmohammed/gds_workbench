# Production simplification pass — 2026-09-23

This pass preserves the existing MVP and independent deployments in ADR 007.
Changes were applied and checked one cohesive area at a time. No dependencies,
database migrations, external writes, or deployments were introduced.

## Follow the data

| Entry | Where to follow the work |
| --- | --- |
| MCP command | `mcp_server/gds_etl_workbench/runtime.py` registers `tools/`; Change Set tools use shared `application/change_sets/` rules and PostgreSQL transactions. |
| Metadata Snapshot | The MCP adapter calls `application/metadata_snapshot/selection.py` for authorized selection, then archive encoding and the bounded ZIP writer in `infrastructure/snapshot_archive.py`. Storage/upload stays in `tools/snapshots/`. |
| Web request | `web_app/backend/gds_workbench_api/main.py` mounts feature routers. Each feature's service contains its application flow; its repository owns database I/O. |
| Workflow Run | `features/workflows/execution/assembly.py` wires the worker and feature workflows. Plan/context loading, lifecycle, candidate handoff and no-op completion remain in `workflows/authoring/`. |
| Frontend workflow selection | `web_app/frontend/src/features/workflows/api.ts:loadWorkflowScope` loads the complete bounded selection; screens retain only display and unsaved selection state. |

All backend paths in the table are relative to `web_app/backend/gds_workbench_api/`
unless a full repository-relative path is shown. PostgreSQL remains authoritative
for authorization, Tenant Locks, revisions, idempotency and governed Apply.

## Applied simplifications

- Removed two sample-data UI prototypes, their routes and CSS: 748 source lines
  and four files. Existing production screens retain their interactions.
- Finished Change Set transport separation. Application modules no longer import
  MCP tools or authentication adapters, including through Snapshot selection.
  Removed dynamic `Context` injection and private-helper/alias indirection.
  This structural correction adds 94 source lines and two files; those explicit
  imports buy transport independence rather than a line-count reduction.
- Replaced repeated workflow dependency declarations with shared contracts beside
  their implementations. Eight identical write-transaction interfaces now use
  `WorkflowExecutionDatabase`. Inlined the sole no-op repository call within its
  existing fenced transaction. Removed 555 source lines without changing the
  workflow execution bodies. Narrower lifecycle types remain explicit.
- Fixed a pre-existing intermittent Excel export failure. Openpyxl overwrites
  document modification time during save; canonical export now retains the
  declared fixed properties. The regression test forces different save dates,
  and fails on the original implementation.
- Consolidated four scope-pagination implementations in the existing workflow
  module: 98 fewer source lines, no new files. Bronze, Enrichment and Dimensional
  filters, revision consistency, cursor repetition and the 250-page limit remain
  explicit. Eighteen regression cases cover these rules and richer Profiling fields.

The shared Python `Protocol` declarations describe required methods; they do not
add runtime objects or a generic workflow framework. Two Mapping type aliases
were retained for existing callers, then removed in the September 27 cleanup
below. Feature-specific execution, SQL integrity checks,
Windows fallback behavior and separate deployment artifacts remain necessary.

## Review evidence

Independent AST comparisons found equivalent bodies after explicit renaming in
82 moved Change Set classes/functions and unchanged values in all 48 SQL constants.
Snapshot moves preserve their definitions. All 37 MCP tool schemas, descriptions, annotations
and policy metadata match the pre-change digests.

Shared imports are tested in a fresh process with MCP SDK, tools and authentication
adapters actively blocked. Workflow execution methods were compared independently;
no-op inlining retains its exact SQL parameters, claim fence, transaction,
error translation and receipt checks.

Pre-existing uncommitted Model-editing work was retained. Source reductions compare
against the working tree at the start of this pass, excluding tests, documentation,
generated artifacts and those earlier edits.

| Production source | Net lines | Net files |
| --- | ---: | ---: |
| MCP | +95 | +2 |
| Backend | −555 | 0 |
| Frontend | −846 | −4 |
| **Total** | **−1,306** | **−2** |

The totals include the Excel fix and one formatting correction found by the full
checks. No new dependency or generic workflow framework was added.

## Verification scope

| Final check | Result |
| --- | --- |
| MCP, backend, disposable PostgreSQL, packaging and GDS plugin Python | 3,173 passed; 89 PowerShell-dependent skips |
| Atlas Python, run separately | 43 passed; 33 PowerShell-dependent skips |
| Frontend | 448 passed; TypeScript and production build passed |
| GDS Workbench JavaScript | 95 passed |
| Atlas Workbench JavaScript | 114 passed |
| GDS Stage Runner | 92 passed; types and bundle passed |
| Atlas Stage Runner | 114 passed; types and bundle passed |
| MCP/backend Ruff formatting, lint and strict Pyright | Passed; zero type errors |
| Final whitespace check | Passed |

Total: **4,079 passing tests; 122 platform skips**. Frontend retains the existing
large-bundle warning. Commands are recorded in [AGENTS.md](../../AGENTS.md);
Python suites use source `PYTHONPATH`, Ruff runs in each project's directory,
and Pyright uses each project's explicit interpreter.

Local verification uses source imports and fixture-created disposable PostgreSQL
containers with random identities, credentials and sentinels. MCP and HTTP routes,
workflow execution, package extraction and frontend interactions are covered by
the existing suites and the added regression checks.

Windows PowerShell execution, live VS Code extension-host operation, and live
Azure/Databricks/Foundry operation require their respective environments. This
pass does not claim a production deployment or a live-provider acceptance test.

Fresh local artifacts were rebuilt and compared directly with their sources:
96 files in the MCP archive, 467 in the App archive and 123 in the Atlas plugin.
The tracked Atlas ZIP was rebuilt after updating its source-reference documents.

## Entity-owned workflow follow-ups — 2026-09-27

- Model Settings reuses the creation form and existing governed update operation.
  Schema lists, naming rules, column policies and agent defaults remain one Model
  document. Revision conflicts and refresh failures preserve unsaved edits.
- Analysis stores inferred cardinality separately from observed endpoint
  uniqueness. Generation supplies inference explicitly; deterministic validation
  preserves it. Web and Atlas show differences as nonblocking review warnings.
- Ten Mapping prompt schemas now derive from the existing Python preparation
  records. Payload and schema projection share the exact internal-field rule;
  arbitrary business documents remain opaque. Curated examples, public shapes,
  legacy resolvers and Code/Validation contracts are unchanged. The complete
  pre-change and generated contract structures were compared for equality.
  The shared tool-name type now lives beside execution contracts, keeping run
  plans independent of the catalog/readers that consume these schemas.

## Mapping System order removal — 2026-09-27

Removed Mapping System dependency order from the fresh-install database,
Model datasets, governed Change Sets, snapshots, Mapping API/UI, authoring
context and Atlas. The web Mapping page opens directly on Entity mappings.
Removed-dataset drafts/catalogs are rejected; there is no migration or cleanup
operation for an existing database.

Code consumer context is now `entity-3`. Source Systems sort by System code
and identity solely for deterministic context and digests. That list conveys
neither runtime scheduling nor business precedence. Approved transformation
rules still express source precedence; Entity/Object dependency order and
lookup readiness still govern modeled prerequisites. Process Group dependency
order and Process execution order remain the runtime scheduling metadata.

## Repository cleanup — 2026-09-27

- Removed the unused Mapping target-picker endpoint, query, client method and
  redundant type aliases. Mapping generation retains its active Entity picker.
- Target Export options now return the revision and placement used by the dialog.
  Removed the unused schema-options query and response fields; saved Entity
  schemas and custom Object Type export overrides remain supported.
- Removed an unused Atlas Workbench helper and retired Code Generation,
  Metadata and Prompt CSS. Retained CSS selectors, declarations, media conditions
  and cascade order were compared before and after removal.
- Corrected MCP authoring instructions and active Atlas documentation to describe
  Entity-owned Mapping/Code and optional target registration. Mapping Apply remains
  required for downstream Code/Validation. Historical compatibility guards remain.
- Removed the superseded MCP schema/tool dump and six completed scratch notes
  with no inbound references. Pending plans, historical decisions and original
  design assets remain.
- Removed six obsolete archives, the retired notebook virtual environment,
  obsolete empty feature directories and generated cache files. Current MCP,
  web, Atlas and extension distributions remain; affected packages were rebuilt.
  Ignore rules now cover test/lint caches, TypeScript build metadata and the
  retired notebook environment.

No migration, backfill or populated-database cleanup was introduced. PostgreSQL
verification uses only fixture-created disposable containers.

Final cleanup verification: 2,878 MCP/backend/database/packaging tests, 440
frontend tests, 47 Atlas Python tests and 128 Atlas JavaScript tests passed.
Frontend types and production build passed; changed Python modules passed
Ruff and Pyright. The 38 Windows PowerShell tests were skipped on macOS.
Current distribution references and Markdown file links were checked;
no stale references or missing file targets remained. Test caches were removed
after verification. Extension source was unchanged in this cleanup.
