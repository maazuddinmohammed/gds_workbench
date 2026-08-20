---
name: build-logical-model
description: "Build or revise a governed GDS Logical data model with entities, attributes, identifiers, normalization, relationships, source traceability, and naming policy. Use when a user asks for a Logical model, normalized business schema, keys and optionality, or exact Logical Model Change Set records."
---

# Build Logical Model

Build a platform-independent Logical layer tied to business meaning and source
evidence. Follow the shared
[Model authoring workflow](../../references/model-authoring-workflow.md). Read the
[modeling method](../../references/modeling-method.md) only for full-layer design,
method ambiguity, or a requested stress test. Read [model datasets](../../references/model-datasets.md)
for exact keys and [model tools](../../references/model-tools.md) around unfamiliar
calls only when needed.
Use `get_model_logical_submodels`, `get_model_logical_entities`,
`get_model_logical_attributes`, and `get_model_logical_relationships` for focused
current-state reads.

## Design

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

## Author

Describe only authored Logical datasets. An Attribute-only change affects
`logical_attribute`; a Relationship-only change affects `logical_relationship`.
Include `logical_entity` or `logical_submodel` only when that parent is new or changed.
Draft complete, ID-free records with required nullable and nested-source fields.

Check canonical keys, parent references, distinct endpoints, ordinals, key/nullability
rules, and source support. Then stop at the boundary selected by the shared workflow.
