# GDS ETL Workbench product blueprint

> Historical planning snapshot: its Workflow Grant, fixed Workflow Control,
> dormant Tenant Lease, and 22-tool descriptions are not current implementation
> requirements. For authentication and authorization use current numbered SQL,
> [`docs/security.md`](../security.md), and
> [ADR 001](../adr/001-direct-principal-authorization-and-tenant-locks.md).

This directory explains Release 1 as one coherent product. It is written for an
AI agent that must understand the intent before changing or rebuilding the
system.

The guide describes the development working tree inspected on 2026-08-07. The
effective Release 1 shape is:

- one PostgreSQL 16 authoritative metadata store;
- one Entra-authenticated modular App Service;
- one actor-filtered MCP endpoint with 22 tools;
- three fixed human Workflow Control routes;
- seven source-loaded Databricks notebooks; and
- no general management UI, generated-code execution, or direct Databricks
  access to metadata PostgreSQL.

## How to use this guide

Read the files in this order:

1. [Product intent and scope](01-product-intent.md)
2. [Domain language](02-domain-language.md)
3. [System architecture](03-system-architecture.md)
4. [Repository map](04-repository-map.md)
5. [Data model and state](05-data-model-and-state.md)
6. [Interfaces and contracts](06-interfaces-and-contracts.md)
7. [Security and invariants](07-security-and-invariants.md)
8. [Model Change Sets](08-model-change-sets.md)
9. [Workflow Control and notebook runtime](09-workflow-control-and-runtime.md)
10. [Workflow index](workflows/README.md), then each workflow page
11. [Operations and deployment](10-operations-and-deployment.md)
12. [Testing and release](11-testing-and-release.md)
13. [Decision record](12-decisions.md)
14. [Rebuild guide](13-rebuild-guide.md)
15. [Current gaps and external boundaries](14-current-gaps.md)
16. [Source map](15-source-map.md)

Use this blueprint for intent, responsibilities, sequences, and design
rationale. Use the linked SQL, Pydantic models, generated JSON Schemas, and
registries for exact storage and wire shapes. Copying those machine-readable
contracts into prose would create a second source that can drift.

## Authority when sources disagree

Use this order:

1. [`AGENTS.md`](../../AGENTS.md) for workspace, database, external-action, and
   security rules.
2. Sections 0 through 0.3 of
   [`IMPLEMENTATION_PLAN.md`](../../IMPLEMENTATION_PLAN.md) and the accepted
   ADRs for later architecture amendments.
3. The rest of `IMPLEMENTATION_PLAN.md`, including its approved DD-108,
   DD-109, and DD-110 contracts.
4. The frozen Feature 001 material in `reference_snapshot/` where the plan
   explicitly delegates detail.
5. Current production SQL, contract assets, and source code for implemented
   behavior. These control over historical blueprint inventory descriptions.
6. [`IMPLEMENTATION_STATUS.md`](../../IMPLEMENTATION_STATUS.md) and
   [`docs/traceability.md`](../traceability.md) for dated evidence, not new
   requirements.

This directory explains those sources. It does not supersede them.

## Maintenance rule

When behavior changes, update the smallest affected blueprint files and their
source links. Record a new design decision when the change alters a boundary,
trust model, public contract, durable state, workflow meaning, or release
scope. Keep observed defects in [current gaps](14-current-gaps.md) until the
implementation and its rejecting test are corrected.
