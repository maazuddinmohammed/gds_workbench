# Logical workflow

## Purpose

Logical builds the implementation-oriented Silver model from governed Bronze
sources. It owns Submodels, Entities, memberships, Attributes, source mappings,
and Relationships. It also applies the Model's Silver naming and audit policy.

## Request and preconditions

The request freezes Build or Extend plus full or selected Bronze Object
coverage. The projected context includes selected sources, the effective
Logical baseline, Analysis relationship signals, applicable Evidence, locks,
downstream dependency paths, and the complete Silver DD-110 policy group.

Readiness blocks missing or invalid policy, ineligible sources, inconsistent
baseline identities, unresolved required dependencies, and required mutations
under locks.

## Data flow

1. Run readiness, load the Logical context, and freeze its identity.
2. Run one Topology Builder per selected source.
3. Validate exact source identity and topology dispositions.
4. Run the sole Topology Reconciler to produce one complete Entity ledger.
5. Run one Entity Detail Builder for every ledger Entity.
6. Require exact coverage for each expected Entity and artifact disposition.
7. Run the whole-Model Reconciler over topology, details, baseline, signals,
   and dependencies.
8. Apply deterministic Silver policy projection. Normalize names, reject
   collisions or overlength results, and create or reuse audit Attributes.
9. Compile all seven artifact families and deterministic structural findings.
10. Build bounded validation packages and run Validator Workers in parallel.
11. Run the Validator Lead. It cannot override unresolved deterministic or
    worker findings.
12. Feed the repair brief into bounded reconciliation rounds.
13. Compile one complete Logical Section, recheck context, and use no-op or
    atomic handoff.

## Persistence and revision

Logical persists exactly seven families:

- Submodel;
- Entity;
- Entity–Submodel membership;
- Attribute;
- Entity source mapping;
- Attribute source mapping; and
- Relationship.

Source mappings bind modeled artifacts to eligible Bronze Objects and
Attributes. Policy-owned audit Attributes have no source mapping and are marked
as audit columns. Composite database witnesses keep every child, source, and
Relationship in the same Model and parent graph.

The relational semantics are fixed:

- Entity type is `core`, `reference`, `transaction`, `event`, `bridge`,
  `history`, `snapshot`, `association`, `aggregate`, or `other`; only `other`
  requires a nonblank type detail.
- Primary, natural, and surrogate key membership are independent Boolean
  Attribute facts. Natural and surrogate cannot both be true. Every key
  Attribute is non-nullable. Composite primary keys are allowed.
- Foreign-key meaning comes from Relationships, not a duplicate Attribute
  flag. Relationship direction is authored semantic direction.
- Cardinality is `one_to_one`, `one_to_many`, `many_to_one`, or
  `many_to_many`; the workflow does not reverse or automatically replace it
  with a Bridge.
- Natural uniqueness spans all four lifecycle states. Retirement retains the
  stable ID and reserves its identity for later reactivation.
- There is no Logical Relationship source-mapping table. Relationships persist
  their definition and relationship/cardinality bases.

An effective change advances Model revision once for the full transaction.
Seven-family output with no operations completes as an exact no-op.

## Failure, retry, and concurrency

Topology or detail identity mismatch, incomplete coverage, invalid policy
projection, lifecycle closure failure, dependency damage, worker failure, or
invalid Lead acceptance blocks persistence. Missing validation packages may be
an explicit nonfatal no-package disposition; missing expected package results
are fatal.

The repair loop is bounded and stops on repeated Candidate digest. The shared
agent runtime owns provider retry and budget limits. The workflow rechecks
Model revision, source context, policy, and Evidence before a non-empty
handoff. PostgreSQL serializes same-Model apply and safely replays identical
idempotency keys.

## Boundaries

Logical agents do not choose final policy-owned names or audit Attributes.
Logical writes no Mapping rows and creates no Silver tables. It has no Spark
access and cannot read raw source rows.

Sources:
[`models.py`](../../../jobs/src/gds_etl_jobs/logical/models.py),
[`workflow.py`](../../../jobs/src/gds_etl_jobs/logical/workflow.py),
[`runtime/policy.py`](../../../jobs/src/gds_etl_jobs/runtime/policy.py),
[`DD-110`](../../design/RELEASE-1-DECISIONS.md#74-dd-110--exact-silvergold-naming-and-policy-storage), and
[`test_logical_workflow.py`](../../../tests/workflows/test_logical_workflow.py).
