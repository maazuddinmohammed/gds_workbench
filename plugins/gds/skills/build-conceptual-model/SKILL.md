---
name: build-conceptual-model
description: "Build or revise a governed GDS Conceptual data model from business scope, vocabulary, relationships, source evidence, and naming decisions. Use when a user asks for a Conceptual model, business concept map, domain vocabulary, high-level entities, or Conceptual relationships, including drafting or applying exact GDS Model Change Set records."
---

# Build Conceptual Model

Build a business-readable Conceptual layer while preserving GDS governance,
traceability, naming policy, revision fencing, and explicit Apply approval.

Read these only when needed:

- [modeling method](../../references/modeling-method.md) for Conceptual quality checks;
- [model datasets](../../references/model-datasets.md) for dataset meaning and keys;
- [model tools](../../references/model-tools.md) for exact MCP names and limits; and
- [governed workflow](../../references/governed-model-workflow.md) before any write.

## Establish the brief

Confirm or discover the Tenant, existing Model, domain boundary, intended audience,
business owner, source systems, and requested stopping point: proposal, validated
draft, or applied change. Ask only for material facts that cannot be read safely.
When ambiguity spans several decisions, offer `$grill-data-model`; do not start an
extended interview silently.

Use `get_model` to select an existing Model and read its revision and naming
templates. There is no public Model-create tool. Use `get_model_scope`, focused
physical catalog reads, profiling/analysis, Modeling Assertions, and existing
Conceptual reads for the minimum evidence needed. Do not treat table names as
business definitions.

Ask the user to choose one naming posture:

1. preserve the current templates;
2. use them for proposed names without changing them; or
3. replace them through a complete `model_details` record.

For option 3, preserve every unchanged `model_details` value, preview representative
names, and respect the silver-pair/gold-triple all-or-none rules. Never claim the
server enforces names generated from a template.

## Design the Conceptual layer

Create a small shared vocabulary first. For each `conceptual_object`, define one
stable business concept with a singular name, definition, object type, explicit
instance grain, aliases only when useful, confidence, lifecycle status, and exact
source/Assertion support.

For each `conceptual_relationship`:

- use existing Conceptual object names at both endpoints;
- phrase the relationship in business language;
- record definition, type, direction, cardinality, basis, confidence, and support;
- use `unknown` cardinality when evidence is insufficient; and
- keep endpoints distinct.

Check for duplicate or overloaded terms, storage-specific concepts, mixed grains,
unexplained aliases, unsupported cardinality, missing owners, and out-of-scope
objects. Mark uncertainty `needs_review`; never manufacture certainty.

## Build exact records

Call `describe_model_dataset` for `conceptual_object` and
`conceptual_relationship`, plus `model_details`, `modeling_assertion_document`,
`modeling_assertion_record`, or `model_scope` only if the approved proposal changes
them. Use every required field, including required nullable fields. Use natural keys
and nested source keys, never database IDs.

Prepare complete pending lists. Compare each canonical key with current state and
show inserts, updates, deactivations/reactivations, unchanged records, naming effects,
evidence, assumptions, and open decisions. A key change inserts another record; it
does not rename or retire the original.

If the user requested only a proposal, stop after schema checks and a compact handoff.
If the user requested a server draft or applied model, follow the governed workflow
exactly. Reconcile any resumed draft before Stage. Server Validate is authoritative.
Display its action review, then obtain a fresh explicit approval immediately before
Apply. Verify with fresh reads or DBML and release the Tenant Lock.

## Completion check

Report the selected Tenant/Model, scope, naming decision, affected datasets, source
evidence, accepted decisions, assumptions, validation/apply status, resulting Model
revision when applied, and unresolved issues. Never call a Conceptual model complete
when its business vocabulary, owner, evidence, or relationship decisions remain
unknown.
