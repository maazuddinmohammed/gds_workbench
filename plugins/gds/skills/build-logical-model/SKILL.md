---
name: build-logical-model
description: "Build or revise a governed GDS Logical data model with entities, attributes, identifiers, normalization, relationships, source traceability, and naming policy. Use when a user asks for a Logical model, normalized business schema, keys and optionality, or exact Logical Model Change Set records."
---

# Build Logical Model

Build a platform-independent Logical layer tied to business meaning and source
evidence. Read [modeling method](../../references/modeling-method.md) only for
full-layer design, method ambiguity, or a requested stress test. Read
[model datasets](../../references/model-datasets.md) for exact keys only when needed.
Read [model tools](../../references/model-tools.md) around unfamiliar calls.
Read the [governed workflow](../../references/governed-model-workflow.md) only for a
server draft or Apply.
Use `get_model_logical_submodels`, `get_model_logical_entities`,
`get_model_logical_attributes`, and `get_model_logical_relationships` for focused
current-state reads.

## Route by intent

Choose the least-committed boundary from the user's verbs and context:

- **Inspect:** use focused reads and answer; do not draft or write.
- **Proposal:** return a compact design or diff; do not write.
- **Local draft:** for add, edit, retire, or “move to Change Set,” update only
  `GDS/model-change-set` through `$open-gds-metadata-workbench` when available. Keep
  the Snapshot immutable. Never call MCP, lock, Stage, Validate, or Apply.
- **Server draft:** use `$manage-gds-model` for generic create, resume, inspect, or
  archive intent; enter the governed workflow only when the user asks to Stage or Validate.
- **Apply:** show the authoritative `action_review` and obtain fresh explicit approval
  immediately before `apply_model_change_set`.

Do not ask for the boundary when it is clear. Never advance beyond it. If a required
local workspace is absent, stop at a proposal and ask only for that missing choice.
Use `$grill-data-model` only when the user explicitly asks for a grill or stress test.
Otherwise ask at most one smallest material question and continue with stated,
non-blocking assumptions.

Use `get_model` only when Model identity, revision, or policy is needed. Preserve
current naming templates and established names by default; use their established
patterns for new names. Do not ask a naming question or author `model_details` unless
the user explicitly requests a naming/template change.

Read only requested records and direct dependencies. Call `describe_model_dataset`
only for affected datasets whose records will be authored. Reading a related dataset
does not make it affected.

## Design the affected logical records

Give each Entity one meaning, explicit row grain, type/detail, dependency order,
submodel, confidence, lifecycle, and exact physical or Assertion sources. Normalize
repeating groups and mixed grains; document deliberate denormalization.

For affected Attributes, preserve meaning, logical type, ordinal, nullability,
identifier/audit roles, lifecycle, and source traceability. Key Attributes are
non-nullable. Natural and surrogate key flags are mutually exclusive. Do not infer a
durable business key from apparent uniqueness alone.

For affected Relationships, use existing Attribute endpoints and record direction,
cardinality, basis, confidence, and lifecycle. The cardinality enum does not encode
minimum participation; capture optionality truthfully in its basis without claiming
structural enforcement.

## Author affected records

Describe only authored Logical datasets. An Attribute-only change affects
`logical_attribute`; a Relationship-only change affects `logical_relationship`.
Include `logical_entity` or `logical_submodel` only when that parent is new or changed.
Draft complete, ID-free records with required nullable and nested-source fields.

A canonical-key change inserts a new record; retire the old key only when requested.
For server work, follow the governed workflow, reconcile resumed pending work, keep
Stage and Apply approvals separate, verify with focused reads/DBML, and release the
lock.

## Report

Normally report no more than three bullets and 120 words: outcome, affected
datasets/counts, and blocker or next boundary. Do not echo unchanged records, full
schemas, checklists, or raw tool output unless asked. Never omit conflicts, truncation,
validation warnings, or the authoritative Apply review.
