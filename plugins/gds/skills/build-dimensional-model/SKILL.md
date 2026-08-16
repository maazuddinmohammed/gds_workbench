---
name: build-dimensional-model
description: "Build or revise a governed GDS Dimensional model using business process, explicit grain, facts, dimensions, measures, additivity, conformance, history, and source evidence. Use for star schemas, marts, fact/dimension design, SCD decisions, or exact Dimensional Model Change Set records."
---

# Build Dimensional Model

Design an analytics-ready Dimensional layer while keeping business decisions,
source feasibility, naming policy, and GDS governance explicit.

Read these only when needed:

- [modeling method](../../references/modeling-method.md) for the dimensional method;
- [model datasets](../../references/model-datasets.md) for record rules and keys;
- [model tools](../../references/model-tools.md) for exact MCP contracts; and
- [governed workflow](../../references/governed-model-workflow.md) before a write.

## Establish the brief and baseline

Confirm or discover Tenant, existing Model, measurable business process, users,
owner/steward, source systems, requirements, and stopping point. If grain, history,
sources, and ownership require a structured interview, offer `$grill-data-model`.

Use `get_model` and existing Dimensional/Logical/Conceptual reads. Inspect Model
Scope, physical catalog, profiling/analysis, Assertions, and Model Mapping only as
needed. Read current naming templates and get an explicit preserve/adopt/replace
decision. Replace templates only through a full `model_details` record, preserve
unchanged values, and preview sample Fact, Dimension, and Attribute names.

## Use the four design decisions in order

1. Select one measurable business process.
2. Declare the atomic Fact grain in one sentence: exactly what one row represents.
3. Identify Dimensions that are single-valued at that grain.
4. Identify Facts/measures that are true at that exact grain.

Do not choose measures before grain. Use separate Fact Entities for distinct grains.
If a Dimension can have multiple values for one Fact row, change the grain, omit the
Dimension, or design an explicit bridge.

For each proposed Entity and Attribute, decide:

- Entity type fact, dimension, or bridge; Fact type transaction, periodic snapshot,
  accumulating snapshot, or factless; explicit grain for Facts/bridges; and Dimension
  row grain when it is knowable;
- keys, descriptors, measures, degenerate Dimensions, bridge weights, technical and
  audit Attributes;
- additive, semi-additive, or non-additive behavior, default aggregation, and the
  aggregation basis required for semi/non-additive measures;
- conformed Dimensions/measures and role-playing Dimension names;
- fixed, overwrite, or historize behavior per descriptive Attribute, with a named
  steward decision;
- unknown/not-applicable members, late facts, late/inferred Dimension context, and
  effective periods where required; and
- source lineage, dependency order, confidence, lifecycle, and unresolved quality
  risks.

Keep non-measure fields' measure-only properties null. Ensure audit flags and roles
agree. Do not use a generic abstraction when distinct business meanings or Attribute
sets would be clearer.

Only change behavior and relationship role have dedicated structured fields for part
of this policy. Record conformance, unknown/default members, late-arrival handling,
and effective-period decisions in truthful existing definitions, an authorized
decision record or Modeling Assertion, and permitted mapping documents as
appropriate. Never invent JSON properties or claim those decisions are structurally
enforced when the live schema has no field for them.

## Build and govern exact records

Call `describe_model_dataset` for `dimensional_submodel`, `dimensional_entity`,
`dimensional_attribute`, and `dimensional_relationship`, plus approved supporting
datasets. Draft complete ID-free records, including required nullable fields and exact
nested source shapes.

Preview process/grain, Fact and Dimension inventory, measures/additivity, conformance,
SCD/history, bridges, late-arrival behavior, naming, source feasibility, canonical-key
effects, and local schema issues. A name/key change is an insert unless the old record
is explicitly retired.

Stop after a checked handoff when the user requested only design. For a server draft
or applied model, use the governed workflow. Reconcile resumed work, Stage complete
pending datasets, use server Validate as authoritative, show its action review, and
obtain a fresh Apply approval. Verify with focused reads and Dimensional DBML, then
release the Tenant Lock.

## Completion check

Report business process, atomic grain, Facts, Dimensions, measures and additivity,
conformance, SCD/history decisions, default/late-arrival patterns, mappings/evidence,
naming posture, affected datasets, validation/apply status, verified Model revision,
and open issues. Missing grain or source feasibility is a blocker, not a detail to
invent.
