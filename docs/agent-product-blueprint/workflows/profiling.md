# Profiling workflow

## Purpose

Profiling measures eligible Attributes on registered Bronze Objects. The
result helps later workflows reason about nulls, distinctness, string lengths,
and relationship quality. Profiling is deterministic Spark work and uses no
agent runtime.

## Request and preconditions

The frozen request contains:

- one Model and Workflow Run;
- full Model Scope or an explicit non-empty Object subset;
- `development` or `test` batch environment; and
- `initial` or `incremental` batch mode.

The notebook hydrates this deterministic workflow with the internal `build`
operation.

Readiness requires an active Model, eligible selected Objects, verified
physical identifiers, and a valid per-Object Connection batch policy. Each
Object uses its own Connection. One Connection's values never filter another.

DD-108 defines the batch rules:

- No batch Attribute means an ordinary bounded unfiltered read.
- A configured name must resolve by exact case to one active integral
  Attribute on that Object.
- Initial mode uses one environment-specific equality value. Null means
  unconfigured and blocks that Object.
- Incremental mode uses all values in the environment-specific array. Null
  blocks. An explicit empty array is a successful deterministic no-op.
- Values must fit the physical byte, short, integer, long, or
  `DECIMAL(p,0)` type before Spark runs.

## Data flow

1. Run readiness and load the Profiling projection of the Model Snapshot.
2. Freeze Model revision and context identities.
3. Resolve one batch predicate for each selected Object.
4. Exclude inactive, technical, audit, and batch Attributes.
5. Create one coverage slot and one Spark computation per remaining Attribute.
6. Run computations under the notebook concurrency semaphore.
7. Compute row, non-null, null, blank, and distinct counts; minimum and maximum
   string lengths; and their bounded percentages.
8. Convert each computation into exactly one success or failure disposition.
9. Validate the complete bounded disposition set in process.
10. Reload context, require the frozen identity, and atomically publish the
    successful Profiles, final receipt, and terminal Profiling Run state.

Spark builds predicates with Column and literal APIs. It casts only the
already range-checked literal. It never casts the source column or interpolates
SQL.

## Persistence and revision

Profiling has no staging tables. Completion validates counts and coverage, then
replaces only successful Attribute Profiles and writes one final receipt in the
same transaction. Failed Attributes retain their prior Profile; the receipt
stores the bounded retained-failure count rather than individual failure rows.

The durable state machine moves `running` to `completed`,
`completed_with_warnings`, `failed`, or `expired`. Final states are immutable.

- At least one changed success and no failure: `completed`.
- Mixed success and failure: `completed_with_warnings`.
- Every eligible Attribute failed: `failed`, with prior Profiles retained.
- Explicit empty batches or no effective Profile changes: workflow no-op.
- Model revision advances once only if a stored Attribute Profile changes.

The final receipt and idempotency outcomes are immutable.

## Failure, retry, and concurrency

A bad batch policy, missing source identity, or changed context blocks before
publication. An individual Spark error becomes a retained nonfatal failure;
timeout and cancellation still stop the whole run. Coverage must have no
pending or fatal slots before publication.

Completion has one idempotency key. Replays return the stored outcome and
cannot duplicate a receipt or revision. Concurrent completion and grant
revocation/expiry serialize in PostgreSQL.

## Boundaries

Profiling cannot sample arbitrary SQL, select arbitrary columns, read secrets,
or store raw rows. The Profiling Run and final receipt remain the authoritative
execution/publication protocol; a Model Change Set may additionally carry its
bounded Profiling document for atomic orchestration with other Model documents.

Sources:
[`workflow.py`](../../../jobs/src/gds_etl_jobs/profiling/workflow.py),
[`batch.py`](../../../jobs/src/gds_etl_jobs/profiling/batch.py),
[`metrics.py`](../../../jobs/src/gds_etl_jobs/profiling/metrics.py),
[`spark.py`](../../../jobs/src/gds_etl_jobs/profiling/spark.py),
[`DD-108`](../../design/RELEASE-1-DECISIONS.md#71-dd-108--exact-profiling-developmenttest-batch-contract), and
[`test_profiling_workflow.py`](../../../tests/workflows/test_profiling_workflow.py).
