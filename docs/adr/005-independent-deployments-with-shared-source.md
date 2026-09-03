# ADR 005: Independent Deployments with Shared Source

- Status: accepted
- Date: 2026-09-03

## Context

The MCP server runs on Azure App Service. The web application and notebooks run
on Databricks. Reusing Python rules must not imply one shared process or a new
network dependency between these deployments.

## Decision

- Keep three independent runtime artifacts: MCP, Databricks App, and Databricks
  notebooks.
- Reuse code at build time. Each artifact receives its own required copy of the
  `gds_etl_workbench` source; no runtime imports cross deployment boundaries.
- Keep transport-neutral contracts, validation, read selection, and
  materialization under `domain/`, `application/`, or `infrastructure/`.
- Keep MCP registration under `tools/` and `adapters/mcp/`. Web production code
  must not import MCP tools or authentication adapters.
- Keep web and notebook workflow orchestration in process. Neither calls the
  MCP server or the other deployment.
- Keep separate least-privilege PostgreSQL runtime roles for MCP, web, and
  notebooks.
- The plugin owns user interaction and lifecycle sequencing. MCP server
  instructions describe governed operation constraints only.

## Consequences

No new service, wheel registry, database object, or deployment-time RPC is
introduced. Existing build commands remain valid. A shared-source change must
rebuild every affected artifact; deterministic manifests and checksums record
the exact files placed in each artifact.
