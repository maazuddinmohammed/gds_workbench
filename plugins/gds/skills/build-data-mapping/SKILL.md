---
name: build-data-mapping
description: "Build or revise governed GDS source-to-model mappings from physical metadata, existing model lineage, and transformation decisions. Use for source-to-target mapping, mapping matrices, lineage extraction, Logical or Dimensional mappings, dependency order, or exact mapping Model Change Set records."
---

# Build Data Mapping

Build traceable Object- and Attribute-grain Model Mapping records. Read
[modeling method](../../references/modeling-method.md) only for full-layer design,
method ambiguity, or a requested stress test. Read
[model datasets](../../references/model-datasets.md) for exact keys only when needed.
Read [model tools](../../references/model-tools.md) around unfamiliar calls. Read the
[governed workflow](../../references/governed-model-workflow.md) only for a server
draft or Apply.
Use `get_model_mapping_dependencies`, `get_model_object_mappings`, and
`get_model_attribute_mappings` for focused current-state reads.

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

## Select and derive affected mappings

Use Model Mapping for physical sources mapped to Logical or Dimensional Entities:
`mapping_dependency → mapping_object → mapping_attribute`. Use
`$manage-gds-metadata` for physical Source-to-Bronze/Silver/Gold ingestion mappings.

Derive candidates from exact nested model sources before asking for a manual matrix.
Object sources can identify Object mappings; Attribute sources require their exact
parent Object mapping. Assertion-only support does not identify a physical source.
Preserve separate canonical mappings for multiple sources.

Check requested mappings for exact source/target identity, active Model Scope,
dependency order, target grain/key rules, transformation choices, and unmapped items.
Do not claim transformation text was executed or proved by sample data.

## Author affected records

Describe only mapping datasets being authored. Include `mapping_dependency` or
`mapping_object` with an Attribute mapping only when that required parent is missing or
changed. Existing parents are read dependencies, not affected datasets. Extraction
requests stop after focused reads.

Draft complete, ID-free records. Keep Object artifact/package/transformation fields in
their required all-null or all-present group. An Attribute mapping must have an exact
parent Object mapping and existing modeled target. For server work, follow the governed
workflow, reconcile resumed pending work, keep Stage and Apply approvals separate,
verify with focused mapping reads, and release the lock.

## Report

Normally report no more than three bullets and 120 words: outcome, affected
datasets/counts, and blocker or next boundary. Do not echo unchanged records, full
schemas, checklists, or raw tool output unless asked. Never omit conflicts, truncation,
validation warnings, or the authoritative Apply review.
