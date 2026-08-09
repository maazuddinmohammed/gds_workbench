# Workflow guide

Release 1 has seven predefined Databricks workflows. A human authorizes one
exact Workflow Run through Workflow Control. The Databricks task then receives
only the Workflow Run and Workflow Grant IDs. The server, not the notebook,
supplies the Model, request, selection, operation allowlist, release, and
expiry.

## Workflow index

| Workflow | Main purpose | Compute | Result |
|---|---|---|---|
| [Profiling](profiling.md) | Measure eligible Bronze Attributes | Spark | Attribute Profiles and a Profiling Run receipt |
| [Analysis](analysis.md) | Discover and physically validate Bronze relationships | Agents and Spark | Analysis Section |
| [Conceptual](conceptual.md) | Build the business-level model | Agents and deterministic checks | Conceptual Section |
| [Logical](logical.md) | Build the implementation-oriented Silver model | Agents and policy projection | Logical Section |
| [Dimensional](dimensional.md) | Build the analytical Gold model | Agents and policy projection | Dimensional Section |
| [Mapping](mapping.md) | Bind modeled artifacts to registered physical targets | Agents and graph planning | Mapping Section and derived Generator Document |
| [DBML](dbml.md) | Publish a revision-bound model visualization | Deterministic archive handling | Files in a governed Volume and completion receipt |

## Checked-in Notebook Definitions

All definitions use source release `2026.08.06.2`.

| Workflow | Job / definition | Ordered agent phases | Concurrency / Section cap / repair rounds |
|---|---|---|---|
| Profiling | `gds-profiling` / `profiling-2` | None | 8 / 1 MiB / 0 |
| Analysis | `gds-analysis` / `analysis-2` | Candidate Finder, Relationship Resolver, Reconciler, Reviewer | 8 / 8 MiB / 3 |
| Conceptual | `gds-conceptual` / `conceptual-2` | Object Builder, Relationship Builder, Reconciler, Validator | 8 / 8 MiB / 3 |
| Logical | `gds-logical` / `logical-2` | Topology Builder, Topology Reconciler, Entity Detail Builder, Reconciler, Validator Worker, Validator Lead | 8 / 12 MiB / 3 |
| Dimensional | `gds-dimensional` / `dimensional-2` | Topology Builder, Topology Reconciler, Entity Detail Builder, Reconciler, Validator Worker, Validator Lead | 8 / 12 MiB / 3 |
| Mapping | `gds-mapping` / `mapping-2` | Header Mapper, Attribute Mapper, Target Validator | 8 / 16 MiB / 3 |
| DBML | `gds-dbml` / `dbml-1` | None | 1 / 1 MiB / 0 |

The five agent-backed notebooks currently select `openai_agents_sdk`. Their
common phase defaults are Foundry deployment `gds-modeling-agent`, high
reasoning, no explicit verbosity, eight turns, two outer retries,
`metadata.read` plus `evidence.read`, a 2 MiB package cap, and 4 MiB context.
Selecting Deep Agents automatically reduces context to 64 KiB. Mapping's
Target Validator is narrower: medium reasoning, four turns, one retry,
`metadata.read` only, and a 1 MiB package cap. Prompts remain notebook-owned;
safety and resource policy remain code-owned.

## Common execution rules

All workflows follow the runtime described in
[Workflow Control and notebook runtime](../09-workflow-control-and-runtime.md):

1. Compile the checked-in Notebook Definition once.
2. Activate the exact Workflow Grant and load its immutable contract.
3. Verify workflow, job key, source release, Notebook Definition version,
   allowed operations, Databricks identity, state, and expiry.
4. Run readiness before expensive work.
5. Load and verify an immutable Model Snapshot. DBML instead verifies its
   revision-bound export archive.
6. For a snapshot-backed workflow, freeze the Model revision plus
   source-context, policy, and Evidence identities.
7. For those six workflows, track a terminal coverage disposition for every
   owned work item. DBML requires exact manifest and file coverage instead.
8. Recheck authoritative context before a non-empty write.
9. Persist through a specialized finalization, an exact no-op, or an atomic
   Model Change Set.
10. Return canonical redacted JSON and payload-free telemetry.

The Workflow Grant expiry is the absolute deadline. Cancellation propagates to
agent calls and Spark job groups. A timeout, cancellation, coverage gap,
repeated Candidate digest, exhausted repair limit, or authoritative context
change stops the workflow before persistence.

## Candidate and revision rules

For Conceptual, Logical, and Dimensional, `build` creates the initial layer and
fails when effective artifacts already exist. `extend` starts from the
effective layer and changes only the selected sources' dependency closure.
Full extend reconciles the layer; selected extend preserves everything outside
its impact closure. Omission means unchanged. Locks override every mode.
Analysis follows these meanings during discovery; effective-only validation is
extend-style. Mapping has the specialized semantics on its own page.

These are the accepted semantics. The current four modeling runners do not yet
enforce every Build precondition; see [current gaps](../14-current-gaps.md).

Analysis, Conceptual, Logical, Dimensional, and Mapping produce a complete
Candidate for their owned Section. They never patch an applied row directly.
An empty operation document uses `complete_workflow_no_op`. A non-empty
document is validated as part of the complete future Model graph and applied
atomically. The Model revision advances once only when effective stored state
changes.

Profiling uses its own direct run and atomic-publication receipt. DBML is
read-only with respect to the Model. See
[Model Change Sets](../08-model-change-sets.md) for the shared apply protocol.

Every server mutation has a deterministic idempotency key. The server stores
the request digest and result. Reusing the same key with the same request
returns the durable result; using it for different input is rejected. DBML
filesystem publication instead uses a content-derived directory identity.
Workflows verify all returned identifiers, revisions, and digests before
accepting a receipt.

## Dependency outline

Readiness, not a hard-coded global pipeline, decides whether a run is allowed.
A typical progression is:

1. Profile Bronze metadata.
2. Discover and validate Analysis relationships.
3. Build Conceptual and Logical Sections.
4. Pause for external Silver Object, Attribute, and Mapping-header registration.
5. Map Logical entities to registered Silver Objects.
6. Build Dimensional artifacts from eligible Silver contributions.
7. Pause for external Gold Object, Attribute, and Mapping-header registration.
8. Map Dimensional entities to registered Gold Objects.
9. Export Conceptual or Logical DBML when a visualization is needed.

## Fixed boundaries

- Jobs have no PostgreSQL driver or database credentials.
- Metadata reads and writes use typed, grant-bound MCP operations.
- Agents receive governed metadata and Evidence, not raw physical rows.
- Only Profiling and Analysis read physical data through fixed Spark adapters.
- Workflows cannot change Model Scope, policy, locks, authorization, or their
  own operation allowlist.
- Mapping returns generator metadata. It does not execute generated code or
  create Silver or Gold objects.
- DBML writes only beneath the configured Unity Catalog Volume root.

Primary implementation sources:
[`notebook.py`](../../../jobs/src/gds_etl_jobs/notebook.py),
[`runtime/launch.py`](../../../jobs/src/gds_etl_jobs/runtime/launch.py),
[`runtime/handoff.py`](../../../jobs/src/gds_etl_jobs/runtime/handoff.py), and
[`adapters/production.py`](../../../jobs/src/gds_etl_jobs/adapters/production.py).
