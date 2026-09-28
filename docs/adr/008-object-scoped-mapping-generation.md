# 008 — Object-scoped Mapping generation

Status: Accepted, 2026-09-22

Historical contract: Physical Object selection, source identities, and Mapping
System-order configuration are superseded by ADR 012; other decisions retained.
See [Entity-owned Mapping and Code](012-entity-owned-mapping-and-code.md).

## Decision

The original September 22 design exposed manual System dependency ordering in
Mapping. The September 27 follow-up removes that table, dataset and editor.
Source-System selection still identifies transformation contributions; Process
Groups and Processes configure runtime ordering. VS Code's governed authoring
path remains available for Mapping Object and Attribute records.

Generate mappings selects one layer and any number of target Object–Source System
pairs. Selecting an Object includes its unlocked Attributes by default. Users
can exclude Objects or existing Attributes. An excluded unauthored Attribute must
be selected before a complete Mapping can be produced.

Logical and Dimensional are separate URL-addressable Mapping views. The selected
layer scopes Entity ledger reads and generation. The generation
dialog places mode, Model and reasoning effort above All unlocked Objects /
Selected Objects. Object details contain Attribute selection with bulk select
and clear actions; switching modes or returning to the Object list retains those
choices. Source System selects run scope; text search only filters visible rows.

Existing Object and Attribute lock columns remain authoritative. An Object lock
protects its children during generation, even when their individual locks are
open. Attribute locks and explicit exclusions preserve their existing records.
When any Attribute is preserved, its Object transformation document must remain
unchanged: arbitrary JSON or SQL cannot prove that different joins preserve the
field's row grain. Older/custom Object documents remain valid when unchanged.

The backend freezes the exact pairs and Attribute IDs in the run selection.
Revision, ownership, permissions, Tenant Lock and worker-claim checks still apply.
The legacy single-pair build/extend API remains supported; the UI uses generate.
No application prompt/context byte ceilings are introduced. The configurable
agent timeout remains 480 seconds by default.

Each pair uses the same applied Model revision, scoped source metadata, saved
lineage, relevant relationships, linked assertions and profile aggregates. Object
order and stable System/name sorting determine execution order. A preceding pair's draft is not an
applied upstream Mapping. One-shot and tool-assisted defaults expose equivalent
evidence; readers return complete paged records.

Successful pairs form one validated draft. Individual authoring failures produce
safe run events and do not discard independent successes. All-failed runs fail;
no-effect runs receive a durable receipt. Applying a draft remains explicit and
revalidates the combined future Model.

Declared new physical source references are checked against eligible Objects and
Attributes. Prompts distinguish evidence from assumptions and can return fixed
missing-evidence issue codes instead of inventing transformations. These checks
do not execute generated SQL or prove business correctness.

## Source coverage amendment — 2026-09-23

Selection crosses every bound target Object with the distinct active business
Systems represented in Model Input Scope. Source Objects use their Connection's
System; Bronze Objects use active ingestion lineage to their originating Systems,
never their shared GDS placement. Logical Mapping considers all eligible scoped
Source/Bronze inputs for the selected System. Dimensional Mapping considers bound
Silver inputs with an applied active Logical Mapping for that System. Saved Entity
source links supplement this candidate set instead of restricting it.

Every pair is assessed in both execution modes. A mapped result must cover every
actionable bound Attribute, preserving locks and exclusions. A System with no
applicable source returns an explicit `no_applicable_source` result recorded in
run events without an empty Mapping record. Existing Mapping or known Entity or
Attribute source lineage cannot be skipped this way; uncertain transformation
rules produce actionable evidence issues. The current Code context contains no
System dependency-order property; Object dependencies and business precedence
remain transformation concerns.

## Installation

The fresh-install SQL adds frozen Attribute selection to run records and extends
the governed create-run signature. It adds no lock columns. Prompt seed and
reviewed default exports are synchronized. Existing databases and saved prompt
versions are not modified by a code redeployment; this change includes no
migration, reset or backfill helper.
