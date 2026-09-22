# 008 — Object-scoped Mapping generation

Status: Accepted, 2026-09-22

## Decision

System dependency order is edited manually in Mapping through the governed Model
Change Set service. It is not an agent stage. Each entry identifies a Model,
modeled layer and Source System; existing dependency locks still apply. The
current execution contract requires an active dependency entry for each selected
System. VS Code's existing governed authoring path remains available.

Generate mappings selects one layer and any number of target Object–Source System
pairs. Selecting an Object includes its unlocked Attributes by default. Users
can exclude Objects or existing Attributes. An excluded unauthored Attribute must
be selected before a complete Mapping can be produced.

Logical and Dimensional are separate URL-addressable Mapping views. The selected
layer scopes ledger reads, manual dependency forms and generation. The generation
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
lineage, relevant relationships, linked assertions and profile aggregates. System
and Object orders determine execution order. A preceding pair's draft is not an
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

## Installation

The fresh-install SQL adds frozen Attribute selection to run records and extends
the governed create-run signature. It adds no lock columns. Prompt seed and
reviewed default exports are synchronized. Existing databases and saved prompt
versions are not modified by a code redeployment; this change includes no
migration, reset or backfill helper.
