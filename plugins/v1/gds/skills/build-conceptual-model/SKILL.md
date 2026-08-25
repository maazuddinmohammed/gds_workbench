---
name: build-conceptual-model
description: "Build or revise a governed GDS Conceptual data model from business scope, vocabulary, relationships, source evidence, and naming decisions. Use when a user asks for a Conceptual model, business concept map, domain vocabulary, high-level entities, or Conceptual relationships, including drafting or applying exact GDS Model Change Set records."
---

# Build Conceptual Model

Build a business-readable Conceptual layer with traceable evidence. Follow the shared
[Model authoring workflow](../../references/model-authoring-workflow.md). Read the
[modeling method](../../references/modeling-method.md) only for full-layer design,
method ambiguity, or a requested stress test. Read [model datasets](../../references/model-datasets.md)
for exact keys and [model tools](../../references/model-tools.md) around unfamiliar
calls only when needed.
Use `get_model_conceptual_objects` and `get_model_conceptual_relationships` for
focused current-state reads.

## Design

Define each `conceptual_object` as one stable business concept with a singular name,
definition, type, instance grain, useful aliases, confidence, lifecycle, and exact
Object/Assertion support. Do not turn storage names into business definitions.

Define each `conceptual_relationship` in business language with distinct existing
endpoints, direction, cardinality, basis, confidence, lifecycle, and support. Use
`unknown` when evidence is insufficient. Mark uncertainty `needs_review`; never
manufacture certainty.

Check only the requested scope for duplicate terms, mixed grains, unsupported
cardinality, missing owners/evidence, and out-of-scope concepts.

## Author

Describe `conceptual_object` only when Object records change and
`conceptual_relationship` only when Relationship records change. Describe a supporting
dataset only when this request actually authors it. Draft complete, ID-free records
with required nullable fields, natural keys, and exact nested support shapes.

Check canonical keys, references, distinct endpoints, duplicate terms, and support.
Then stop at the boundary selected by the shared workflow.
