# Analysis workflow

## Purpose

Analysis discovers candidate Attribute relationships between Bronze Objects
and validates them against physical data. Agents propose and reconcile
relationships. Deterministic Spark evidence assigns the final classification.

## Request and preconditions

The request freezes Build or Extend, full or selected Object coverage, and one
execution mode:

- `discovery_only`: create a pending Analysis draft and stop for later review;
- `validation_only`: validate an exact staged draft or effective
  Relationships; or
- `discovery_and_validation`: perform both parts in one run.

Validation-only with staged input carries the exact Model Change Set ID and
expected draft revision. Readiness requires an active Model, selected Bronze
Objects in the permitted context, usable Attributes, verified Spark endpoints,
and valid applicable Assertion context. Missing Profiles are reported as a
warning and may lower confidence. Locked changes are rejected.

## Discovery flow

1. Run readiness, load the Analysis context, and freeze its identity.
2. Select the exact requested Bronze Objects.
3. Run Candidate Finder and Relationship Resolver work per Object under one
   concurrency limit.
4. Require complete Object and outgoing-relationship dispositions. Composite
   key proposals are unsupported in Release 1.
5. Reconcile all proposals into one pending Analysis Section. Extend includes
   and revalidates every existing outgoing Relationship in the selected impact
   set; omission never retires it. Selected Extend preserves Relationships
   outside that set, full Extend revalidates all, and Build requires an empty
   effective Analysis layer.
6. Run the Reviewer. Feed blocking findings into bounded repair rounds.
7. Stop on acceptance, repeated Candidate digest, or the repair limit.
8. If no relationship changes or revalidation work exists, complete an exact
   no-op. Otherwise stage the pending Section.
9. In discovery-only mode, return `awaiting_validation` with the exact draft
   identity.

## Validation flow

1. Load the exact staged relationships or current effective Relationships.
2. Use fixed Spark reads for the registered source and target endpoints.
3. Compute inclusion, uniqueness, non-null, distinct, missing-target,
   unused-target, and duplicate-key counts.
4. Require one evidence result for every proposed relationship.
5. Apply the immutable classification rule:
   - non-empty endpoints, complete source inclusion, and unique target become
     `supported`;
   - otherwise a verified applicable Assertion becomes `needs_review`;
   - otherwise an existing Relationship becomes `inactive`;
   - otherwise the proposal is `rejected` and is not persisted.
6. Recheck the frozen context.
7. Replace the pending draft with the final canonical Analysis operations.
8. Ask the server to validate and apply that exact draft.

## Persistence and revision

Discovery-only persists an active Model Change Set and leaves the Workflow Run
in `awaiting_validation`. It does not change the effective Model. Final
validation writes the complete Analysis Section through the normal atomic
apply rules. Persisted Analysis rows retain stable physical Object and
Attribute endpoints.

An effective change advances the Model revision once. A valid final result
that changes nothing returns no-op with the same revision.

## Failure, retry, and concurrency

Finder, Resolver, Reconciler, or Reviewer identity and coverage errors block
the Candidate. Reviewer rejection may enter the bounded repair loop. Spark
failure, incomplete Spark evidence, or disagreement with the fixed
classification rule blocks validation; ordinary `rejected` or `inactive`
classification is not a runtime failure.

Validation-only and combined execution must check for a previously completed
frozen-Candidate outcome before doing work, so Spark validation runs at most
once across retries. The current combined path omits that replay check; see
[current gaps](../14-current-gaps.md). Pending put, final put, and apply use
distinct deterministic idempotency keys. Draft revision compare-and-swap
prevents two continuations from applying different content.

## Boundaries

Agents cannot decide physical validation status. Spark cannot invent
relationships. Analysis writes only its Section and never changes Model Scope,
Assertions, locks, or physical data.

Sources:
[`workflow.py`](../../../jobs/src/gds_etl_jobs/analysis/workflow.py),
[`classification.py`](../../../jobs/src/gds_etl_jobs/analysis/classification.py),
[`spark.py`](../../../jobs/src/gds_etl_jobs/analysis/spark.py),
[`test_analysis_modes.py`](../../../tests/workflows/test_analysis_modes.py), and
[`test_analysis_classification.py`](../../../tests/workflows/test_analysis_classification.py).
