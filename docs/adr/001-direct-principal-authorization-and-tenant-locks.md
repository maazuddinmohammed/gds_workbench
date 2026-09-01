# ADR 001: Direct Principal authorization and governed Tenant Locks

- Status: accepted and implemented
- Date: 2026-08-10

## Context

The workbench is internal. Human MCP clients and registered workloads both need
one authorization model. The prior greenfield design included Workflow Grants
and treated the Tenant-wide lock as dormant. Current requirements instead make
registered workloads Super Admin Principals and make Tenant Lock ownership the
mandatory concurrency gate for ordinary writes.

## Decision

Human tokens use delegated scope `workbench.access`. Workload tokens use
application permission `workbench.workflow`. Both map their Entra Tenant/Object
identity to an active internal Principal on authorization-sensitive calls.

Workloads must be explicitly registered, active, and marked Super Admin. No
Workflow Grant delegates authority. The canonical schema omits
`workflow.workflow_grant` and `workflow.workflow_run_summary`.

Tools declare one of five server-owned policies: Tenant Read, Tenant Metadata
Write, Tenant Model Write, Tenant Lock Manage, or Super Admin Only. PostgreSQL
resolves the effective role and lock state.

Ordinary metadata writes require Developer plus an active owned Tenant Lock.
Ordinary Model writes require Architect plus an active owned Tenant Lock. Lock
management requires Developer and deliberately does not require an existing
lock. Override is explicit and audited.

Locks default to 60 minutes, allow 1 through 240 minutes, use PostgreSQL time,
and expire automatically through a bounded App Service worker. Super Admin does
not bypass an active lock owned by another Principal.

Local dev mode is permitted only under `GDS_ENVIRONMENT=local`. It skips Entra
and Tenant role/visibility checks but does not weaken database lock, revision,
audit, or business invariants.

## Consequences

Backend and future MCP adapters can call the same database authorization and
lock functions. A caller cannot obtain authority by presenting a role,
Principal ID, actor kind, policy, or lock token. Workflow launch coordination is
outside this MCP scaffold and can be designed later without pre-adding an unused
delegation model.

Superseded planning documents that described Workflow Grants, fixed Workflow
Control routes, a dormant Tenant Lease, or obsolete tool inventories were
removed. This ADR, current numbered SQL, and current MCP source are authoritative.
