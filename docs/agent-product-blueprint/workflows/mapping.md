# Mapping workflow

## Purpose

Mapping binds effective modeled Entities and Attributes to preregistered
physical targets. Logical maps to Silver. Dimensional maps to Gold. The output
is a governed Mapping Section plus a name-only Generator Document that another
system may use to generate an artifact.

## Request and preconditions

The frozen request contains:

- Build or Extend;
- full coverage, optionally filtered to source Systems, or exact target
  Object/source System pairs for selected coverage; and
- `sql_file`, `python_file`, or `python_notebook` artifact type.

The caller does not choose a route. The workflow infers
`logical_to_silver` or `dimensional_to_gold` from immutable preregistered
headers and rejects mixed or wrong-zone targets. The current request schema
still exposes a caller-supplied route; this is an implementation gap, not the
accepted design.

Readiness requires effective modeled artifacts, registered targets in the
correct zone, preregistered Object Mapping headers, frozen executable and
provenance lineage, compatible unlocked existing bindings, and the exact
allowlisted `mapping.standard@1.0.0` profile and schema digest. An existing
binding can never be repointed.

For Mapping, `build` treats preregistered headers as inputs and fills only
missing Object transformation content and child binding/content. It preserves
all existing transformations. `extend` may also revise complete unlocked
Object and Attribute transformations. Both modes reuse binding identities;
partial profile upgrades, mixed package versions, and required changes under a
lock block the package.

## Package flow

The unit of work is one target Object and source System pair.

1. Check first for a committed Mapping outcome that still needs Generator
   materialization. If found, skip all modeling and resume from committed data.
2. Run readiness, load the Mapping context, freeze its identity, and validate
   the exact package inventory.
3. Process packages in parallel under the workflow semaphore.
4. Run Header Mapper for artifact instructions, profile identity, executable
   sources, non-executable provenance, package metadata, and transformation.
5. Split target Attributes into batches of at most 500 and run Attribute
   Mapper for complete target and existing-child coverage.
6. Validate identities, source aliases, lineage, transformations, locks,
   authored-content completeness, and immutable bindings.
7. Run Target Validator and bounded package repair.
8. Derive deterministic source System and target dependency graphs.
9. Reject missing dependencies, cycles, inconsistent wave order, unsafe shared
   targets, and invalid multi-System batch discriminators.
10. Compile changed headers and children into one Mapping Section.
11. Recheck context and complete no-op or atomic apply.
12. Refetch receipt-bound committed Mapping state and create the Generator
    Document from committed names and provenance.

## Persistence and revision

DD-109 permits exactly two tables:

- `workflow.object_mapping` for the typed Entity-to-target/source package
  header; and
- `workflow.attribute_mapping` for typed Attribute-to-target Attribute
  contributors.

Headers in one package must have byte-equivalent profile, artifact,
instruction, wave, package document, and digest fields. Logical targets must be
registered Silver; Dimensional targets must be registered Gold. Parent and
child identity witnesses, partial unique indexes, and deferred graph checks
preserve bindings across every lifecycle state.

One effective Mapping apply advances Model revision once. No-op materializes
the current committed state without changing revision. The Generator Document
contains names and provenance, not database IDs, and is not physical target
deployment.

## Failure, retry, and concurrency

Any fatal package or inner coverage failure blocks the whole Section. Provider
repair is bounded. Dependency and shared-target safety run deterministically
before persistence. Context drift stops before apply.

Apply and Generator materialization are intentionally separate. If apply
succeeds but committed-state reconstruction or materialization fails, the
result is `materialization_pending` with the durable applied revision. A retry
loads that completed receipt and committed Mapping state, then materializes
without applying again. Handoff, no-op, and committed materialization outcomes
remain idempotent under concurrent retries.

## Boundaries

Mapping does not create target Objects, execute SQL or Python, upload files, or
read physical rows. Original ingestion and prior Mapping sources may appear as
provenance, but only approved executable aliases may be used as executable
inputs.

Sources:
[`contracts.py`](../../../jobs/src/gds_etl_jobs/mapping/contracts.py),
[`workflow.py`](../../../jobs/src/gds_etl_jobs/mapping/workflow.py),
[`dependencies.py`](../../../jobs/src/gds_etl_jobs/mapping/dependencies.py),
[`materialize.py`](../../../jobs/src/gds_etl_jobs/mapping/materialize.py),
[`DD-109`](../../design/RELEASE-1-DECISIONS.md#72-dd-109--exact-combined-mapping-persistence), and
[`test_mapping_workflow.py`](../../../tests/workflows/test_mapping_workflow.py).
