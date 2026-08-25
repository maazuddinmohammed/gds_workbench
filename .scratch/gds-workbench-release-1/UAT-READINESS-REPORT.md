# GDS Workbench UAT Readiness Report

Date: 2026-08-25  
Verdict: **REQUESTED REMEDIATION READY; COMPLETE DEPLOYMENT STILL NO-GO**

No Azure, Databricks, model provider, staging, or production system was contacted.
Database tests and browser UAT used only fixture-created disposable PostgreSQL
containers with random credentials, database names, and run sentinels.

## Executive result

| Surface | Result | Evidence |
|---|---|---|
| MCP | Pass | 633 tests; Ruff and source Pyright clean; App Service ZIP 6/6 package tests |
| Plugin V2 | Pass with host gap | 87 Python passed, 27 PowerShell-only skipped; 39 Node passed; validator passed |
| Plugin V1 | Removed | V1 source, tests, archives, builder, and duplicate legacy MCP registration removed |
| Web backend | Pass | 799 backend and packaging tests; Ruff and scoped Pyright clean |
| Web frontend | Automated pass | 133 tests, typecheck, build, and production/full npm audits passed |
| Local containers | Pass | Fresh database, API, worker, and frontend build/start/health/proxy/cleanup passed |
| Browser UAT | Pass for implemented routes | Real React/FastAPI/PostgreSQL journey; no browser console or server errors after repair |

## Remediation completed

- Rebuilt `mcp_server/dist/gds-mcp-appservice.zip` from current source.
  It contains 88/88 source entries plus a valid build manifest, with no stale,
  missing, or extra source bytes. SHA-256:
  `79da69d32d4b096ee44509cb85b58597de7a0bf1c5d4e804d1328effea3dffc2`.
- Preserved only Plugin V2. Its deterministic archive is 115,068 bytes with
  SHA-256 `db7bb88ee4071a0afbb148fb6dd8a4a304278de537f18c67a84c7cb8a98ef069`.
- Repaired V2-only Windows CI paths and removed V1-dependent tests/docs.
- Kept frontend and backend as distinct images and containers. Local Compose now
  builds one shared backend image once, runs API and worker as separate containers,
  and runs frontend as a separate NGINX container.
- Added a non-internal loopback edge network for frontend/API while keeping
  PostgreSQL and the worker on the internal backend network. PostgreSQL remains
  unpublished. The worker no longer inherits the API HTTP health check.
- Fixed the Models ledger query to use canonical
  `application.workflow_run.workflow_run_state`; a regression test pins it.
- Updated Vite and affected transitive development dependencies. Both production
  and complete npm audits now report zero known vulnerabilities.
- Removed only exact, proven GDS build caches. No global Docker prune or unrelated
  container, image, or volume deletion occurred.

## Browser evidence

The production container stack was exercised through `http://127.0.0.1:8080`:

- Tenant chooser and Tenant Home;
- Tenant Lock acquire, held state, and release-confirmation UI;
- normalized Metadata ledger and row detail;
- Models ledger and Model overview;
- Scope, Profiling, Analysis, Assertions, Conceptual, Logical, and Dimensional;
- Model Prompt settings and Prompt library;
- Model-first Mapping and target-first Code Generation.

A disposable Model was created through the governed backend route because the
current React ledger has no create control. Browser console warnings/errors were
empty. API, frontend, worker, and PostgreSQL logs had no error or 5xx match after
the Models query repair. The stack and its database volume were deleted by the
safe runner after testing.

## Remaining deployment blockers

1. The production React Models ledger does not expose **New Model**, although the
   governed backend create operation exists.
2. The production React Scope screen does not expose **Add/Remove Objects**,
   although the governed backend replacement operation exists.
3. Twenty-seven V2 PowerShell runtime/parity tests require the repaired Windows CI
   job or a Windows host; this macOS host cannot execute them.
4. Browser UAT used deterministic local fake integrations. Real Azure identity,
   Databricks, and model-provider acceptance require explicit external approval
   and environment-specific testing.

The 790.64 kB minified JavaScript chunk warning is non-blocking but should become a
later performance/code-splitting task.

## Deployment decision

The MCP ZIP, Plugin V2, and separate-container local packaging requested in this
remediation are ready. Do not declare the complete web application deployment-ready
until the two missing React authoring controls are implemented or explicitly
removed from Release 1 scope, and the Windows V2 gate passes.
