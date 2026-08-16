---
name: build-logical-model
description: "Build or revise a governed GDS Logical data model with entities, attributes, identifiers, normalization, relationships, source traceability, and naming policy. Use when a user asks for a Logical model, normalized business schema, keys and optionality, or exact Logical Model Change Set records."
---

# Build Logical Model

Produce a platform-independent, normalized Logical layer tied to business meaning and
source evidence. Preserve GDS locking, revisions, and separate Apply approval.

Read these only when needed:

- [modeling method](../../references/modeling-method.md) for Logical design checks;
- [model datasets](../../references/model-datasets.md) for exact semantics and keys;
- [model tools](../../references/model-tools.md) for current MCP contracts; and
- [governed workflow](../../references/governed-model-workflow.md) before a write.

## Establish the brief and baseline

Confirm or discover Tenant, existing Model, business domain/process, consumers,
owner, sources, current Conceptual vocabulary, and stopping point: proposal,
validated draft, or applied change. Use `$grill-data-model` when the user wants a
bounded decision interview. Do not ask for information available through safe reads.

Use `get_model` first. Read current naming templates and ask whether to preserve,
adopt, or replace them. A replacement is one complete `model_details` record with all
unchanged values retained and valid template groups. Preview Entity and Attribute
names; the server does not enforce template-generated names.

Read existing Logical submodels, Entities, Attributes, and Relationships. Use
Conceptual reads, Model Scope, physical catalog, profiling/analysis, Modeling
Assertions, and current mappings only as needed. Track whether each statement is a
user decision, a governed assertion, observed source evidence, or an assumption.

## Design the Logical layer

For every `logical_entity`, define:

- business-readable name and definition;
- one explicit row/instance grain;
- type and required-nullable `logical_entity_type_detail`, which is non-null only for
  `logical_entity_type="other"`;
- dependency order and submodel membership;
- confidence, lifecycle status, lock state; and
- physical or Assertion sources with rationale.

For every `logical_attribute`, define meaning, logical data type, ordinal,
nullability, identifier roles, audit role, lifecycle, and source traceability. A key
Attribute is non-nullable. Natural and surrogate key flags are mutually exclusive.
Do not infer a durable business key from apparent uniqueness alone.

Normalize repeating groups and mixed-grain values. Separate facts about different
business subjects. Record deliberate denormalization only as an explicit decision
with a reason and acceptance check.

For every `logical_relationship`, use existing Attribute endpoints and record name,
definition, direction, `logical_relationship_cardinality`, basis, confidence, and
lifecycle. The cardinality enum records one/many direction only; it has no zero/minimum
participation value. Capture optionality truthfully in
`logical_relationship_cardinality_basis` and the authorized decision record or
Modeling Assertion, and label it descriptive rather than structured or enforced.
Check that endpoints differ, each parent exists, and the relationship matches the
declared grains and identifiers.

## Build and govern exact records

Call `describe_model_dataset` for `logical_submodel`, `logical_entity`,
`logical_attribute`, and `logical_relationship`, plus any approved supporting dataset.
Draft complete ID-free records with every required nullable field and exact nested
source shape. Do not copy database IDs into staged records.

Prepare complete pending dataset lists. Preview canonical-key effects, normalization
decisions, source lineage, naming, references, assumptions, and local validation.
Changing a canonical key inserts a new record; retire the old key explicitly when
that is the approved intent.

For proposal-only work, stop with a schema-checked handoff. Otherwise follow the
governed workflow: lock only after local review, reconcile a resumed Change Set,
Stage exact dataset replacements with the current revision, Validate and repair,
show the authoritative action review, and ask again immediately before Apply.
Verify the resulting Logical records/DBML and release the lock.

## Completion check

Report scope, naming posture, submodels, Entity grains, identifiers, key/optional
relationships, normalization decisions, source coverage, affected datasets,
validation/apply state, verified Model revision when applied, and open issues. Do not
declare completion while identifier, cardinality, ownership, or source decisions
needed by the requested scope remain unresolved.
