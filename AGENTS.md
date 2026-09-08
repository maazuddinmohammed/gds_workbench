# Repository execution rules

These rules apply to every file and command in this repository.

## Strict Rules

- Be extremely concise. Sacrifice grammar for the sake of consision.
- I haven't developed an mcp server or web applications before. I know python and sql. So when explaining anything I want you to do that accordingly.
- I want you to implement slowly one chnage at a time never build a feature in one go.

## Database and external safety

- Local and CI database tests may use only a fixture-created disposable PostgreSQL container with random credentials, a random database, and a per-run sentinel. Reject user-supplied, environment, default, local-service, Azure, staging, and production DSNs before any connection.
- Never add drop, truncate, reset, destructive cleanup, migration, or backfill helpers for populated databases. Container disposal is the only local database cleanup. It can be added in comments if it is part of server cleanup.
- Do not deploy, push, open a pull request, alter cloud identity/policy, run Databricks, or write to Azure/external systems without explicit approval.

## Security and public surface

- Never commit or log secrets, connection values or strings, bearer/workflow tokens, secret names or references, raw prompts, raw physical rows, raw tool output, or unredacted run dumps.
- MCP must not expose foundational CRUD, Model Scope mutation, direct lock-table toggles, individual graph mutation, arbitrary SQL, delete, secret-returning, file-upload, or code-execution tools. The only arbitrary-SQL exception is the governed `execute_databricks_sql` tool: it may accept multi-statement Databricks SQL, allow reads and unqualified temporary views/tables only, reject persistent DDL and all DML, never return or log credentials, and return at most 50 rows from the final statement. Any future Tenant Lock tool must call only the governed acquire, renew, release, or explicit override operations and preserve their role, ownership, duration, reason, and audit rules.
- Derive actor, Tenant, Model ownership, and authorization server-side. Preserve least privilege, redaction, Tenant Lock protection, revision fencing, and idempotency.

## Frontend and backend responsibility

- When application logic could reasonably live in either frontend or backend, prefer the backend.
- Keep authoritative authorization, validation, normalization, reconciliation, digest, workflow, and state-transition rules in the backend. The frontend may mirror bounded checks for immediate feedback, but the backend must revalidate them.
- Keep presentation, interaction behavior, and temporary unsaved UI state in the frontend when they naturally belong there.

### Code Structure and Abstraction

Optimize for readability, locality, and traceability, not maximum decomposition.

- Prefer fewer, cohesive, moderately larger functions when the logic naturally belongs together.
- A primary function should expose enough of the execution flow that a developer can understand it without repeatedly jumping between helpers/files.
- Do not create helpers merely to shorten a function or abstract a few simple lines.
- Avoid trivial wrappers, pass-through functions, one-use helpers, excessive call depth, and abstractions based only on hypothetical future reuse.
- Keep logic inline when it is simple, used once, and clearer in context.
- Extract logic when it provides meaningful value: reuse, substantial complexity, a clear domain operation, independent testing, or an architectural boundary such as database access, authentication, validation, or external I/O.
- Do not use function length as the primary metric. A larger cohesive function is preferable to many tiny functions when it improves understanding.
- Before creating an abstraction, ask: --Does this reduce cognitive load, or does it just make the reader navigate elsewhere?--
- During refactoring, actively look for unnecessary indirection and consolidate it where doing so improves readability without introducing meaningful duplication.
- Make fewer, more meaningful abstractions—not simply fewer functions.

## Agent skills

### Issue tracker

Local Markdown under `.scratch/`. See `docs/agents/issue-tracker.md`.

### Triage labels

Default five-label vocabulary. See `docs/agents/triage-labels.md`.

### Domain docs

Single-context: root `CONTEXT.md`, with ADRs under `docs/adr/`. See
`docs/agents/domain.md`.

### Frontend design system

Before frontend work, read `docs/design-system.md` and preserve its interaction,
accessibility, and visual rules.

## Code map and simplification

- MCP: `mcp_server/gds_etl_workbench/runtime.py` wires authentication, tools,
  auditing, and PostgreSQL. `tools/` and `adapters/mcp/` own transport;
  `application/`, `domain/`, and `infrastructure/` hold shared rules and storage.
- Backend: `web_app/backend/gds_workbench_api/main.py` mounts feature routers.
  Workflow assembly lives in `features/workflows/execution/assembly.py`;
  shared candidate parsing and diagnostics live in `features/workflows/authoring/repair.py`.
- Notebooks: `databricks_notebooks/src/gds_workbench_notebooks/` calls the same
  in-process workflow assembly. Preserve Python 3.12 compatibility.
- Plugin: `plugins/v2/gds/skills/gds/` contains local helpers and Workbench.
  `workbench/core.js` owns shared JavaScript normalization and stable serialization.
- VS Code extension: `plugins/v2/gds-stage-runner/src/extension.ts` exposes the
  local Stage tool; `stage-runner.ts` verifies approval digests and stages chunks.
  Reuse Workbench serialization: chunk hashes must match Python's JSON encoding.
- Frontend: `web_app/frontend/src/features/` owns screens; reuse matching
  components from `shared/ui.tsx` and formatters from `shared/presentation.ts`.
- SQL: `database/00_preflight.sql`, ordered install files `01`–`19`, then
  `20_verify_install.sql`. Never turn this fresh-install sequence into migrations.
- Packaging: `deployment/databricks_ui/build_uploads.py`,
  `plugins/build_gds_v2_plugin_zip.py`, and `mcp_server/build_zip.py`.
  Shared source is copied into independent artifacts;
  see `docs/adr/005-independent-deployments-with-shared-source.md`.
- Before deleting code, check imports, registrations, dynamic references, tests,
  and packaged consumers. Similar names do not prove identical behavior.
- Reuse existing helpers when semantics match. Keep authorization, byte limits,
  Unicode normalization, revision checks, and Windows fallback behavior intact.
- Explain major architecture changes before starting them. Make and verify one
  cohesive simplification at a time. See `docs/architecture/simplification-audit.md`.

## Local verification

Run from the repository root. Use installed project environments. Source
`PYTHONPATH` entries below prevent tests from exercising stale installed copies.
Database tests require local Docker and the disposable fixtures above; never
substitute an existing database. Keep captured database output hidden.

```bash
# MCP, backend, SQL contracts, plugin helpers, and packaging.
PYTHONPATH=mcp_server:web_app/backend:. web_app/backend/.venv/bin/python -m pytest -c web_app/backend/pyproject.toml tests/mcp tests/web_backend tests/web_packaging tests/plugin_v2 --tb=no --show-capture=no -q

# Notebook source and shared workflows on Python 3.12.
PYTHONPATH=databricks_notebooks/src:mcp_server:web_app/backend .venv-notebooks/bin/python -m pytest databricks_notebooks/tests --tb=no --show-capture=no -q

# Frontend tests, types, and production build.
npm --prefix web_app/frontend run check

# Plugin Workbench JavaScript tests (root npm dependencies required).
node --test tests/plugin_v2/*.test.mjs

# VS Code extension tests, types, and bundle.
npm --prefix plugins/v2/gds-stage-runner test
npm --prefix plugins/v2/gds-stage-runner run compile
```

Use each Python project's Ruff and Pyright settings. When calling Pyright from
the root, pass both `--project` and that project's `--pythonpath`; otherwise it
may use the wrong interpreter. `.github/workflows/web-app.yml` also lists the
three extracted-notebook artifact probes to run with Python 3.12.
PowerShell fallback execution requires Windows PowerShell 5.1; preserve the
checks in `.github/workflows/plugin-windows.yml`.
After changing plugin or extension source, rebuild its matching local ZIP/VSIX
and generated bundle; packaging tests compare them with source. Rebuilding does
not authorize publishing.
