# ADR 009: Layer-scoped Code Generation and Validation

- Status: accepted
- Date: 2026-09-22

## Decision

Logical/Silver and Dimensional/Gold are separate navigation scopes for Code
Generation and Validation. The URL carries the selected layer; the backend
filters eligible inputs, applied records, and authoring context.

Code Generation selects contributing source Systems and SQL file layout before
choosing all unlocked Objects or an explicit Object subset. A Run
freezes the explicit Object selection, System codes, and file layout. The user
chooses one transformation file per Object/System or one combined file per
Object. Existing source assignments still cover every mapped System exactly
once across the retained and newly generated files.

Partial regeneration preserves files outside the selected Systems. A combined
file cannot be partly replaced: select all its Systems. Locked Code and source
assignments remain protected. Transformation SQL follows the published guide
and the Atlas convention: self-contained temporary stages followed by an
explicit target-shaped SELECT. Combined files must follow applied Mapping;
the generator must not invent cross-System reconciliation.

Validation selects Systems within a layer. Each new Group retains its authoring
layer independently of Workflow Run provenance, including after manual review.
Layer-prefixed names keep the existing System/Group natural key unambiguous.
A locked Group preserves all its Checks; an individually locked Check also
keeps its parent Group active. Unlocked definitions remain eligible for
regeneration. Authoring covers supported technical integrity and functional
business rules, with independent expectations and no redundant quota. Static
validation rejects constant checks, nonnegative COUNT assertions, and identical
actual/expected queries; this is not proof of business correctness.
Legacy Groups remain shared and visible in both layers; layer-scoped generation
preserves them and the other layer's Groups. Existing whole-System currentness
digests remain conservative: a relevant change in either layer can mark a Group
stale even though the authoring inputs were limited to one layer.

## Consequences

The existing Model Change Set, review, Apply, revision, Tenant Lock, and replay
boundaries remain authoritative. Generating or applying Code stores definitions;
it does not deploy SQL or execute a production load.

New fields and triggers belong to the fresh-install SQL sequence. This change
does not migrate or backfill a populated database. Local verification uses a
fresh disposable database and synthetic provider responses.
