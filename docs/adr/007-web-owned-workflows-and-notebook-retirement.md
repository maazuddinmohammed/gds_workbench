# ADR 007: Web-owned workflows and notebook retirement

- Status: accepted
- Date: 2026-09-21
- Supersedes: [ADR 005](005-independent-deployments-with-shared-source.md)

## Context

The web application no longer needs a separate Databricks notebook entry point.
Maintaining notebook identity, configuration, packaging, and Python compatibility
adds a second execution path for the same workflows.

## Decision

- Retire the interactive notebook runtime, its source, tests, CI job, and upload
  artifact. Remove its roles and wrappers from the fresh-install SQL contract.
- Keep two independent server artifacts: the Azure App Service MCP server and
  the Databricks App. The App retains its HTTP server and background worker.
- Keep web workflow execution in `gds_workbench_api/features/`. Profiling belongs
  to its feature package; there is no separate `gds_workbench_runtime` package.
- Keep FastAPI routers focused on HTTP inputs, dependency resolution, and
  responses. Feature services execute workflows; repositories own database I/O.
- Continue copying governed `gds_etl_workbench` domain/application source into
  both artifacts at build time. The App does not call the MCP server or import
  its transport/authentication adapters.
- Preserve Databricks App hosting, governed Databricks SQL execution, and
  generated Code Artifacts, including Python notebooks. Those are independent
  of the retired interactive workflow runtime.
- Preserve authorization, Tenant Locks, revision fencing, idempotency, and
  explicit Apply boundaries. Existing databases are not altered automatically.

## Consequences

One backend package owns web workflows and configuration. Packaging emits only
an App upload and no pruned notebook source tree. Backend, frontend, disposable
PostgreSQL, and extracted App artifact checks cover the retained behavior. No
migration, cleanup command, cloud deployment, or external write is introduced.
