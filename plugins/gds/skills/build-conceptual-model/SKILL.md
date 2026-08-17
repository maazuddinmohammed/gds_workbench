---
name: build-conceptual-model
description: "Build or revise a governed GDS Conceptual data model from business scope, vocabulary, relationships, source evidence, and naming decisions. Use when a user asks for a Conceptual model, business concept map, domain vocabulary, high-level entities, or Conceptual relationships, including drafting or applying exact GDS Model Change Set records."
---

# Build Conceptual Model

Build a business-readable Conceptual layer with traceable evidence and governed writes.
Read [modeling method](../../references/modeling-method.md) only for full-layer design,
method ambiguity, or a requested stress test. Read
[model datasets](../../references/model-datasets.md) for exact keys only when needed.
Read [model tools](../../references/model-tools.md) around unfamiliar calls. Read the
[governed workflow](../../references/governed-model-workflow.md) only for a server
draft or Apply.
Use `get_model_conceptual_objects` and `get_model_conceptual_relationships` for
focused current-state reads.

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

## Design the affected concepts

Define each `conceptual_object` as one stable business concept with a singular name,
definition, type, instance grain, useful aliases, confidence, lifecycle, and exact
Object/Assertion support. Do not turn storage names into business definitions.

Define each `conceptual_relationship` in business language with distinct existing
endpoints, direction, cardinality, basis, confidence, lifecycle, and support. Use
`unknown` when evidence is insufficient. Mark uncertainty `needs_review`; never
manufacture certainty.

Check only the requested scope for duplicate terms, mixed grains, unsupported
cardinality, missing owners/evidence, and out-of-scope concepts.

## Author affected records

Describe `conceptual_object` only when Object records change and
`conceptual_relationship` only when Relationship records change. Describe a supporting
dataset only when this request actually authors it. Draft complete, ID-free records
with required nullable fields, natural keys, and exact nested support shapes.

Compare affected canonical keys with current state. A key change inserts a new record;
retire the old key only when requested. For server work, follow the governed workflow,
reconcile resumed pending work, keep Stage and Apply approvals separate, then verify
with focused reads or DBML and release the lock.

## Report

Normally report no more than three bullets and 120 words: outcome, affected
datasets/counts, and blocker or next boundary. Do not echo unchanged records, full
schemas, checklists, or raw tool output unless asked. Never omit conflicts, truncation,
validation warnings, or the authoritative Apply review.
