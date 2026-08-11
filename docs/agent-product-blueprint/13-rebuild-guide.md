# Rebuild guide

This is the dependency order for recreating Release 1. Build vertical behavior
in this order; do not start from notebooks or generated artifacts.

## 0. Verify the immutable evidence source

Before reading delegated Feature 001 detail, run
[`scripts/verify_bootstrap.sh`](../../scripts/verify_bootstrap.sh). It must
verify every entry in [`reference_snapshot/MANIFEST.sha256`](../../reference_snapshot/MANIFEST.sha256),
the snapshot's read-only permissions, and isolation from the live reference
workspace. Never place the snapshot on a production import path.

## 1. Freeze vocabulary, decisions, and exclusions

1. Adopt the terms in [domain language](02-domain-language.md).
2. Record DD-108, DD-109, and DD-110 exactly.
3. Apply ADR-0001 through ADR-0004 in order.
4. Fix the public boundaries: 22 MCP tools, three Workflow Control routes,
   seven workflows, eight Model Change Set documents, and no foundational
   CRUD, arbitrary SQL, code-execution, or generated-code execution public
   surface.
5. Turn the security rules and 26 traced invariants into rejecting tests.

This prevents a convenient implementation choice from changing product intent.

## 2. Define contracts before adapters

Create strict immutable models for identifiers, lifecycle states, requests,
results, errors, Sections, snapshots, DBML, Mapping profiles, workflow
deployments, and receipts. Forbid unknown fields. Implement canonical JSON v1
and golden vectors once, then require byte parity in the server and jobs
package.

Generate schemas, examples, capabilities, registry, deployment registry, and
Mapping schema from source definitions. Generated files are build outputs and
must reproduce byte-for-byte from a clean checkout.

## 3. Install the fresh PostgreSQL schema

Apply the eleven numbered SQL files once, in sorted order, in one fail-fast transaction.
Implement:

- reference, foundational, security, Model, applied workflow, Mapping,
  Change Set, event, and MCP audit tables;
- composite witness keys and `ON DELETE NO ACTION` foreign keys;
- immutable binding, append-only, lifecycle, lock, and final-graph triggers;
- Model row and advisory locking plus one revision increment per effective
  transaction; and
- the migration, read, and write role posture with `PUBLIC` revoked.

Do not add startup DDL, down migrations, destructive cleanup, or an upgrade
chain to v1. Verify only in a fixture-created disposable PostgreSQL container.

## 4. Build the server core inward-out

Implement pure domain types and policies first: authorization capability,
state machines, canonical digests, redaction, naming, readiness, graph checks,
Section compilation, snapshot construction, DBML rendering, and idempotency.

Define narrow repository, clock, identifier, and artifact-cache ports. Implement
PostgreSQL as the only production repository. Every sensitive mutation must
resolve current identity and mutable facts again inside its transaction.

Then implement the six features:

1. Catalog navigation.
2. Model context, readiness, snapshots, and DBML.
3. Model Change Sets.
4. Mapping materialization.
5. Profiling Runs.
6. Workflow Runs and human Workflow Control.

Keep feature calls direct. Do not introduce an internal network or generic
dispatcher.

## 5. Add authentication and public surfaces

Parse only bounded normalized Easy Auth claims. Derive human or workload actor
kind on the server. Implement Tenant/Model/capability rules and the exact
workload grant fence before exposing tools.

Bind the 22 tools directly to feature methods. Discovery and dispatch require
actor authorization plus promotion registration. Capabilities distinguish
actor-available from enabled tools; the registry exposes the complete actor
inventory; schemas expose only enabled tools. A hidden name must fail like an
unknown name before input validation.

Add only the three fixed Workflow Control routes and anonymous live/ready
health routes. Invalid configuration should produce a live but unready app with
product routes unavailable.

## 6. Implement mutation aggregates

Implement Model Change Sets as whole-Section replacement with global draft
revision compare-and-swap. Validation compiles the complete future graph and
seals its digest. Apply rechecks every fence, allocates final IDs, resolves
local references, strips transient fields, commits one graph, writes one
receipt, and advances revision only for effective change.

Implement Workflow Grant, Workflow Run, and Profiling Run state machines with
database-time expiry. Apply, revoke, and expiry must share locks. Bind each
idempotency key to canonical request bytes and the stored response.

## 7. Build the independent jobs runtime

Create a Python 3.12 source package that imports no server code and has no
metadata-database driver or credentials. Its only server integration is typed
MCP through managed identity.

Implement snapshot download and archive verification, workflow-specific
projection, exact coverage ledgers, one deadline, cancellation, concurrency,
token and model-call budgets, classified outer retry, deterministic Section
compilation, receipt verification, and redacted telemetry.

Implement three code-owned agent adapters behind one interface. They must share
the same Foundry endpoint and safety envelope. Deep Agents gets no filesystem,
execution, persistence, memory, skills, plugins, or default subagents.

## 8. Implement workflows in dependency order

Use the workflow pages for exact behavior:

1. [Profiling](workflows/profiling.md)
2. [Analysis](workflows/analysis.md)
3. [Conceptual](workflows/conceptual.md)
4. [Logical](workflows/logical.md)
5. External Silver Object/Attribute and Mapping-header registration
6. [Mapping](workflows/mapping.md) for `logical_to_silver`
7. [Dimensional](workflows/dimensional.md)
8. External Gold Object/Attribute and Mapping-header registration
9. Mapping for `dimensional_to_gold`
10. Optional [DBML](workflows/dbml.md)

Profiling and DBML are deterministic. The other five workflows use bounded
typed agents plus deterministic compilation and validation. No workflow creates
physical Silver/Gold objects or executes generated Mapping code.

## 9. Package with explicit allowlists

Build a deterministic App Service ZIP containing only the entry point, startup
script, frozen dependencies, manifest, and production server package. Build a
separate deterministic Databricks release containing seven thin notebooks,
the jobs source, and its hash-bound dependency input. Neither artifact may
contain tests, secrets, the reference snapshot, or the other runtime.

Startup must never apply DDL. Deployments start read-only. Mutation surfaces
appear only after the exact artifact verifies against complete T24 evidence.

## 10. Prove the product, not only units

Test every contract boundary, state transition, role, actor inventory, lock,
revision fence, graph invariant, idempotent replay, expiry race, archive check,
redaction rule, and excluded surface. Inject failure at each persistence
boundary and prove rollback.

The packaged acceptance path must boot the extracted ZIP against disposable
PostgreSQL, run the complete workflow sequence, cross both external registration
pauses with fixtures, restart the service, and verify durable receipts and
replays. Reproduce both artifacts twice. Only then run the clean T24 aggregate
and its consent-gated audits. T25 remains a separate explicitly authorized
environment smoke.

## Rebuild completion definition

A rebuild is locally complete only when P00/T26 through T24 pass from a clean
checkout with no skipped, expected-failed, warning, flaky-retry, adverse, or
external result counted as success. Environment release is complete only after
T25 has separate real Azure and Databricks evidence. See
[testing and release](11-testing-and-release.md).
