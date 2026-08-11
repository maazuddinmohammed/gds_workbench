# Dimensional workflow

## Purpose

Dimensional builds the analytical Gold model. It owns Facts, Dimensions,
Bridges, their Attributes, Relationships, Submodels, memberships, and source
mappings. Its sources are governed Silver contributions, not arbitrary Bronze
Objects.

## Request and preconditions

The request freezes Build or Extend plus full or selected eligible Silver
Object coverage. A source is eligible only when an active registered
Logical-to-Silver Mapping connects it to the effective Logical model.

The context also contains the Dimensional baseline, resolved source
contributions, relationship signals, locks, Profiles when available, and the
complete Gold DD-110 policy group. Readiness blocks invalid target lineage,
missing policy, incompatible existing technical endpoints, broken dependencies,
or required changes beneath locks.

## Data flow

1. Run readiness, load the Dimensional context, and freeze its identity.
2. Run Topology Builders per eligible Silver source.
3. Reconcile one complete Dimensional Entity ledger with exact source
   contribution and signal ownership.
4. Run Entity Detail Builders and require all expected dispositions.
5. Run the whole-Model Reconciler.
6. Apply the first deterministic Gold projection. Create or reuse Dimension
   surrogate keys and audit Attributes. Add the required Type 2 technical
   Attributes only when a current Dimension Attribute is marked `historize`.
7. Compile Relationships and roles.
8. Apply the second projection. Create Fact and Bridge foreign keys with names
   derived from the role or referenced Dimension, copy the surrogate-key type,
   and derive nullability from Relationship optionality.
9. Validate structural rules such as Fact/Bridge grain, measure roles, keys,
   history policy, lifecycle, and dependency order.
10. Run Validator Workers by package, then the Validator Lead.
11. Use bounded repair until accepted or stopped.
12. Compile all seven families, recheck context, and use no-op or atomic
    handoff.

## Persistence and revision

Dimensional uses the seven Dimensional tables parallel to the Logical graph:
Submodel, Entity, membership, Attribute, Entity source mapping, Attribute
source mapping, and Relationship.

Entity source mappings point to an eligible registered Silver Object or
applicable Assertion Record. Attribute source mappings point to a physical
Silver Attribute path or applicable Assertion Record. Policy-owned technical
and audit Attributes are produced by code, not agent invention. A complete
effective change advances Model revision once; an empty operation set leaves it
unchanged.

Entity type is Fact, Dimension, or Bridge. Facts and Bridges require a
nonblank authoritative grain plus structured grain/key components; a Dimension
may omit grain. Measures are Attribute roles, conformed Dimensions reuse one
Dimension, and role-playing is a Relationship role. Dimension Attributes may
use mixed Type 0/1/2 behavior. The graph stores Silver source lineage but no
transformation SQL or Relationship-source table. Stable natural uniqueness,
parent closure, Model/physical witnesses, and aggregate locks apply across the
seven families.

## Failure, retry, and concurrency

Incomplete contribution ownership, wrong Entity role, invalid grain, policy
collision, incompatible surrogate or foreign key, dependency failure, coverage
gap, or invalid Validator result blocks persistence. A missing Profile for an
otherwise eligible Silver Object produces a warning, not an automatic block.

Worker phases run under shared concurrency. The bounded repair loop stops on
repeated digest or attempt limit. Context drift, timeout, and cancellation stop
before handoff. The generic handoff and PostgreSQL Model fence provide replay
and same-Model serialization.

## Boundaries

Dimensional cannot use an unregistered Silver Object, write Mapping, deploy a
Gold Object, or execute transformations. It has no Spark access. The agent may
propose business structure but cannot override code-owned technical policy.

Sources:
[`models.py`](../../../jobs/src/gds_etl_jobs/dimensional/models.py),
[`projection.py`](../../../jobs/src/gds_etl_jobs/dimensional/projection.py),
[`workflow.py`](../../../jobs/src/gds_etl_jobs/dimensional/workflow.py),
[`DD-110`](../../design/RELEASE-1-DECISIONS.md#74-dd-110--exact-silvergold-naming-and-policy-storage), and
[`test_dimensional_workflow.py`](../../../tests/workflows/test_dimensional_workflow.py).
