---
name: build-dimensional-model
description: "Build or revise a governed GDS Dimensional model using business process, explicit grain, facts, dimensions, measures, additivity, conformance, history, and source evidence. Use for star schemas, marts, fact/dimension design, SCD decisions, or exact Dimensional Model Change Set records."
---

# Build Dimensional Model

Build an analytics-ready Dimensional layer with explicit business decisions and source
evidence. Read [modeling method](../../references/modeling-method.md) only for
full-layer design, method ambiguity, or a requested stress test. Read
[model datasets](../../references/model-datasets.md) for exact keys only when needed.
Read [model tools](../../references/model-tools.md) around unfamiliar calls.
Read the [governed workflow](../../references/governed-model-workflow.md) only for a
server draft or Apply.
Use `get_model_dimensional_submodels`, `get_model_dimensional_entities`,
`get_model_dimensional_attributes`, and `get_model_dimensional_relationships` for
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

## Design the affected dimensional records

Make decisions in order: select the measurable process, declare one atomic Fact grain,
identify Dimensions single-valued at that grain, then identify Facts/measures true at
that grain. Separate distinct grains. Use a bridge only for an explicit multivalued
relationship.

For affected Entities/Attributes, preserve Fact/Dimension/bridge type, keys,
descriptors, measure roles, additivity/default aggregation, history behavior,
conformance, audit roles, lifecycle, confidence, and exact source support. Semi- or
non-additive measures require an aggregation basis. Keep measure-only fields null on
non-measures. Do not invent structured fields for policies represented only in
definitions, Assertions, decisions, or mapping documents.

## Author affected records

Describe only authored Dimensional datasets. An Attribute-only change affects
`dimensional_attribute`; include its Entity or submodel only when that parent is new or
changed. A Relationship-only change affects `dimensional_relationship`. Draft complete,
ID-free records with exact nullable and nested-source shapes.

A canonical-key change inserts a new record; retire the old key only when requested.
For server work, follow the governed workflow, reconcile resumed pending work, keep
Stage and Apply approvals separate, verify with focused reads/DBML, and release the
lock.

## Report

Normally report no more than three bullets and 120 words: outcome, affected
datasets/counts, and blocker or next boundary. Do not echo unchanged records, full
schemas, checklists, or raw tool output unless asked. Never omit conflicts, truncation,
validation warnings, or the authoritative Apply review.
