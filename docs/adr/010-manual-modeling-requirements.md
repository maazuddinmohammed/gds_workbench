# ADR 010: Document-based Modeling Assertions

- Status: implemented
- Date: 2026-09-22

## Decision

Reuse the existing Assertion Document and Record tables. Documents group multiple
assertions; their free-text type describes the source or collection. Each Record
has its own free-text type, stable key, statement, optional notes and reference.
Assertions can express domain facts, definitions, relationships, conventions,
constraints, requirements or KPI semantics. No separate requirements table or
upload pipeline is introduced. Existing structured details are preserved on edit.

The UI opens Documents, then the selected Document's Records, then Record details.
Add Assertion accepts a new or existing document name. Existing documents retain
their type and Tenant/System scope when adding or editing a record. A new document
applies to the entire Model or a registered System within the Model's Tenant.
Manual provenance lives in record source location and document metadata, independent
of the user-defined type. Imported records remain editable through governed import.

Saves retain human authorization, owned Tenant Lock, revision fencing, running-run
protection, graph validation, idempotency and audit. Locked records cannot be edited.
Existing lifecycle review handles lock/unlock and deactivate/reactivate.

## Workflow use

Assertions appears before Analysis. Active records in active documents are available
to Analysis, Conceptual, Logical, Dimensional, Mapping, SQL and Validation. Context
remains filtered by authorized Model and joint Tenant/System scope. Dimensional also
includes the business Systems contributing to selected Silver Objects.

The layer picker is removed. The stored `modeling_assertion_applicable_layers` field
remains for import/export compatibility; it no longer gates context or support
references. New manual records populate all five legacy values. No migration or
backfill is needed to make previously authored assertions available downstream.

Prompts explain the free-text types, statement, notes, provenance and legacy
structured details. Agents determine task relevance, distinguish facts from desired
capabilities, and corroborate physical claims. Assertions never prove that missing
source data exists or authorize bypassing workflow rules.

Mapping receives scoped assertions without requiring Entity links. SQL and Validation
receive the same automatically available context through
`object_transformations[].entity.assertions`. SQL implements approved Mapping;
relevant contradictions or missing rules produce a safe diagnostic. Validation uses
independently derived expectations rather than tautological comparisons.

Assertion contents participate in the SQL input digest; relevant edits invalidate
SQL/Validation currentness. Saving an assertion never automatically runs workflows.
Users review and regenerate affected stages in order.
