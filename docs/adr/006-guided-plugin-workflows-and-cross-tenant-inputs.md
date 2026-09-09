# ADR 006: Guided Plugin Workflows and Cross-Tenant Inputs

- Status: accepted
- Date: 2026-09-09

## Decision

The plugin exposes Guided, Custom, and Grill With Docs. Guided initializes the
session, SQL policy, Workbench, and snapshots, then follows selected workflows.
Custom clarifies the goal and executes an approved plan. Grill With Docs performs
deeper investigation before that plan. Existing answers and applied work survive
workflow boundaries. Both builds invoke missing Metadata Enrichment.

A Model belongs to one Tenant. Its Source/Bronze scope may span readable Source
Tenants. Bronze/Silver/Gold placement follows the selected Source Tenant's GDS
Connection and that Connection's Tenant/System. Source ownership remains a
metadata/user choice; Model Tenant is the default proposal for new Silver/Gold.
The current Binding implementation still requires target Source Tenant to equal
Model Tenant. This is an implementation restriction, not a registration invariant.

Model authorization rechecks access to retained Source Tenant references,
including inactive scope. Structural SQL eligibility alone grants no access.
Physical catalogs and materialization carry the authorized source-owner set;
foreign Silver/Gold targets remain excluded. Combined Metadata Snapshots accept
explicit authorized Source Tenant IDs, adding Source/Bronze context only.
Metadata writes still use each Object owner's session and Tenant Lock. The
single-owner web Metadata Enrichment Run preserves its ownership restriction.

Standard profiling SQL is generated locally from snapshots and a fixed batch
plan. JavaScript and native PowerShell produce the same aggregates. Execution
uses the existing governed SQL tool under saved policy. Modeling investigations
remain evidence-driven; freeform per-Object notes support downstream reuse.

The packaged orchestration reference owns conventions shared across workflows:
Bronze casting/names, Source ownership versus GDS placement, generated identities, audit
projection, schema qualification, Mapping/Code behavior, and Copy Group selection.
The user guide describes intake and lifecycle; workflow references teach only
the relevant mechanics and decisions.

## Consequences

No public CRUD, arbitrary execution, new workflow tables, or deployment action
is introduced. Snapshot schemas remain authoritative. Locks, revision fencing,
digest-bound acknowledgement, Stage validation, and separate Apply approval
remain in place. CREATE IF NOT EXISTS and known migration SQL are user artifacts,
not populated-PostgreSQL migration helpers. Updated SQL remains fresh-install
source; existing databases are never modified by a plugin rebuild.

The approved detailed workflow plan is in `.scratch/plugin-workflow-plan.md`.
