# Conceptual workflow

## Purpose

Conceptual builds the stable business view of the Model. It owns Conceptual
Objects, Relationships, and Support links from those artifacts to governed
physical Objects or Assertion Records.

## Request and preconditions

The frozen request contains Build or Extend and full or selected Bronze Object
coverage. Readiness requires a valid active Model, resolvable selected sources,
applicable Assertions, compatible baseline Conceptual artifacts, and no required
change beneath a lock.

Creation or reactivation needs a valid basis. The basis is either a physical
Object in the verified context or an applicable verified Assertion Record.
Name-only invention is not sufficient.

## Data flow

1. Run readiness, load the Conceptual context, and freeze its identity.
2. Run one Object Builder per selected source under the workflow semaphore.
3. Validate returned source identity and every proposal, then create one
   complete Object ledger over the baseline.
4. Derive bounded Relationship Evidence Packages from the ledger and context.
5. Run Relationship Builders in parallel and record one disposition for every
   package.
6. Build one Relationship ledger containing baseline, successful outputs, and
   explicit failed-package dispositions.
7. Run the whole-Model Reconciler.
8. Deterministically compile Objects, Relationships, and Supports and collect
   structural or Assertion findings.
9. Run the Conceptual Validator. It must accept the Candidate and meet the
   configured quality target.
10. Repeat reconciliation within the bounded repair limit when needed.
11. Compile the accepted Candidate to one complete Conceptual Section, recheck
    context, and complete as no-op or atomic apply.

## Persistence and revision

The Section writes only:

- `workflow.conceptual_object`;
- `workflow.conceptual_relationship`; and
- `workflow.conceptual_support`.

Creation-basis data is verified by the server. Support persists exactly one
governed Object or same-Model Assertion Record link, not the agent's raw
reasoning. Omitted effective artifacts remain unchanged; explicit lifecycle
intent controls inactivation or deprecation.

An effective Conceptual change advances Model revision once. An operation-free
accepted Candidate uses the exact no-op path and keeps the revision.

## Failure, retry, and concurrency

Object Builder failure is fatal because it breaks the complete Object ledger.
A non-timeout Relationship Builder exception may become an explicit nonfatal
failed-package disposition. Missing, duplicate, mismatched, or unaccounted
packages are fatal coverage errors.

The repair loop keeps a bounded best Candidate, stops on repeated digest, and
never accepts unresolved blocking findings. Provider retries occur only inside
the shared bounded agent runtime. Context drift, timeout, or cancellation stops
before handoff. Generic create, put, validate, and apply keys make handoff
replay-safe.

## Boundaries

Conceptual has no Spark access and reads no physical rows. Agents cannot write
Assertions, Model Scope, policy, locks, or other Sections. Conceptual artifacts
describe business meaning; they do not create physical Silver or Gold objects.

Sources:
[`models.py`](../../../jobs/src/gds_etl_jobs/conceptual/models.py),
[`workflow.py`](../../../jobs/src/gds_etl_jobs/conceptual/workflow.py),
[`database/06_workflow_conceptual.sql`](../../../database/06_workflow_conceptual.sql), and
[`test_conceptual_workflow.py`](../../../tests/workflows/test_conceptual_workflow.py).
