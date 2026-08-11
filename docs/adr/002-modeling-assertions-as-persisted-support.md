# ADR 002: Modeling Assertions as persisted support

- Status: accepted and implemented
- Date: 2026-08-10

## Context

The prior design called model-owned factual statements Modeling Evidence and
treated them only as transient workflow context. That name was too narrow for
statements derived from documents, emails, meeting notes, or direct user input.
It also prevented the applied Model from retaining why an artifact exists when
the basis was not a physical Object or Attribute.

## Decision

The domain term is **Modeling Assertion**. The existing two-table structure is
retained and renamed:

- `model.modeling_assertion_document` stores source-document metadata; and
- `model.modeling_assertion_record` stores one structured factual assertion.

Model Change Sets use the Assertion Section, `assertion_document`, and
`base_assertion_digest`. Modeling Assertion reads use Assertion terminology.
Generic test, release, and analytical evidence keeps its existing meaning.

Applied support persists a foreign key to the Assertion Record, never merely to
its Document. Every support/source-mapping row has a discriminator and separate
nullable physical and Assertion IDs. A check constraint requires exactly one
source, allowing normal foreign keys to preserve referential integrity and
same-Model ownership.

- Conceptual Support accepts an Object or Assertion Record.
- Logical and Dimensional Entity source mappings accept an Object or Assertion
  Record.
- Logical and Dimensional Attribute source mappings accept a physical Attribute
  path or Assertion Record. Assertion-backed rows have no physical parent,
  Object, or Attribute IDs.

Physical eligibility rules remain unchanged. Application graph validation must
also require an effective Assertion Record, an active Document, and matching
layer applicability before effective use.

## Consequences

Assertions can be the durable basis for Conceptual, Logical, and Dimensional
artifacts. Multiple bases remain multiple support rows. A plain polymorphic ID
is not used because PostgreSQL could not enforce both target foreign keys.

This repository installs a fresh canonical schema, so the decision changes the
numbered DDL and contracts directly rather than adding an in-place migration.
Older context-only Modeling Evidence decisions and documentation are
superseded by this ADR.
