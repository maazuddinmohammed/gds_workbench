# ADR 003: Tenant-wide Workflow Run exclusivity

- Status: accepted and implemented
- Date: 2026-08-25

## Context

Profiling, Analysis, modeling, Mapping, and Code Generation read or change
shared Tenant state. Concurrent workflows for different Models in the same
Tenant can invalidate each other's frozen inputs and downstream assumptions.
API prechecks cannot prevent races across web replicas, workers, and notebooks.

## Decision

Every Workflow Run stores an immutable, server-derived `tenant_id` constrained
to its Model by a composite foreign key. PostgreSQL permits at most one row in
the `running` state for each Tenant through a partial unique index.

Queued and terminal Runs may coexist. Starting the same already-running Run is
an idempotent replay. A different Run receives the stable
`tenant_workflow_conflict` response. Completing or failing the active Run frees
the Tenant for the next start. Different Tenants may run concurrently.

This execution invariant is distinct from the governed Tenant Lock. The Tenant
Lock authorizes writes by one Principal; Workflow Run exclusivity schedules
execution across all workflow types and callers.

## Consequences

FastAPI, workers, and Databricks notebooks share one race-safe database rule.
Callers never choose or mutate the Tenant witness. Creation remains available
while another Run is active, so a blocked start leaves a durable queued Run.
