---
name: build-dimensional-model
description: "Build or revise a governed GDS Dimensional model using business process, explicit grain, facts, dimensions, measures, additivity, conformance, history, and source evidence. Use for star schemas, marts, fact/dimension design, SCD decisions, or exact Dimensional Model Change Set records."
---

# Build Dimensional Model

Build an analytics-ready Dimensional layer with explicit business decisions and source
evidence. Follow the shared
[Model authoring workflow](../../references/model-authoring-workflow.md). Read the
[modeling method](../../references/modeling-method.md) only for full-layer design,
method ambiguity, or a requested stress test. Read [model datasets](../../references/model-datasets.md)
for exact keys and [model tools](../../references/model-tools.md) around unfamiliar
calls only when needed.
Use `get_model_dimensional_submodels`, `get_model_dimensional_entities`,
`get_model_dimensional_attributes`, and `get_model_dimensional_relationships` for
focused current-state reads.

## Design

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

## Author

Describe only authored Dimensional datasets. An Attribute-only change affects
`dimensional_attribute`; include its Entity or submodel only when that parent is new or
changed. A Relationship-only change affects `dimensional_relationship`. Draft complete,
ID-free records with exact nullable and nested-source shapes.

Check canonical keys, parent references, exact grain, measure/additivity rules, history
decisions, conformance, and source support. Then stop at the boundary selected by the
shared workflow.
