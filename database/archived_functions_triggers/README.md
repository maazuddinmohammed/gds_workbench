# Archived functions and triggers

Reference-only draft behavior removed from the greenfield numbered DDL.

- `support.sql.disabled`: transaction queue used by archived graph validation.
- `functions.sql.disabled`: 19 behavior functions.
- `triggers.sql.disabled`: 140 triggers.

Archived function groups:

- Model revision capture: 3.
- Workflow lifecycle guards: 5.
- Lock, identity, and append-only guards: 4.
- Graph validation: 3.
- Application-facing security helpers: 4.

Archived trigger groups:

- Model revision guard/capture: 27.
- Append-only guards: 13.
- Workflow lifecycle guards: 5.
- Business-lock guards: 25.
- Identity witnesses: 27.
- Locked-ancestor guards: 12.
- Graph enqueue/validation: 31.

These files are intentionally not executable `.sql` files. Do not load them as
migrations. Re-evaluate requirements, tests, permissions, indexes, and function
ownership before rebuilding any behavior in the numbered DDL.

This archive predates ADR 002 and therefore retains the historical
`modeling_evidence_*` names and context-only behavior. Do not copy those names
or semantics into active Assertion code.

If revisiting a behavior, use the numbered schema as the base and selectively
rebuild it. Do not bulk-enable this archive.

The main schema retains only structural `CHECK` helpers:

- `reference.is_nonblank(text)`
- `core.is_canonical_text_array(text[])`
