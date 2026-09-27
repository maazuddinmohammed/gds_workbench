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
remain for existing callers. Feature-specific execution, SQL integrity checks,
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
