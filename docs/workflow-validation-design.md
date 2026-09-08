# Workflow validation lists

Check generated results against the initial authorized scope/index before saving.
Use complete natural keys, including each Attribute's parent Object.

## Object Metadata Enrichment — One-shot

1. Returned Object key exists in the initial authorized scope/index.
2. No duplicate Object targets.
3. Locked Object descriptions cannot change.

## Attribute Metadata Enrichment — One-shot

1. Returned Attribute key exists under the stated Object in the initial authorized scope/index.
2. No duplicate Attribute targets.
3. Locked Attribute descriptions cannot change.

## Analysis — One-shot and Tool-assisted

1. The complete from-Attribute key and its parent Object exist in the initial authorized scope/index.
2. The complete to-Attribute key and its parent Object exist in the initial authorized scope/index.
3. No duplicate relationships: identity is from key + to key + relationship kind within the Model.
4. Locked relationships cannot change.
5. Values satisfy the actual Pydantic/database contract, including confidence values and distinct endpoints.

Analysis confidence accepts `low`, `medium`, and `high`; the approved generation
policy asks for high-confidence findings. `relationship_kind` is nonblank text,
not an enum. Analysis has no cardinality field. Status and lock values come from
the backend; the model cannot author them. `relationship_basis` is an existing
required field. See the [field audit](workflow-prompts/field-provenance.json).

## Conceptual — One-shot and Tool-assisted

1. New/changed Object supports use complete physical Object keys in the initial authorized scope/index.
2. Assertion supports reference eligible active Conceptual-applicable records from active Documents in the frozen context.
3. Relationship endpoint names exist in the applied-plus-candidate Model and are distinct; active relationships require active concepts.
4. No duplicate concept identities, relationship identities, support sources within a parent, or aliases within a concept.
5. Locked records and supports cannot change. Returned lock fields are false; the backend retains saved locks.
6. Required fields and values match the existing Pydantic/database contract, including status, confidence, cardinality, and the correct Object/Assertion support variant.

Concept identity is its name; relationship identity is from name + to name +
relationship name. Cardinality accepts one_to_one, one_to_many, many_to_one,
many_to_many, or unknown. Confidence accepts low/medium/high; the prompt's
approved high/medium authoring policy is separate from stored accepted values.
Omitted records/supports remain, unchanged results are no-ops, and correctable
candidate issues use the existing bounded repair loop. Conceptual duplicate
checks remain strict; do not claim the Analysis duplicate-collapse change has
been implemented in this workflow.

## Logical — One-shot and Tool-assisted

1. New/changed Entity Object sources use complete physical Object keys in the initial authorized scope/index.
2. New/changed Attribute sources use complete physical Attribute keys under their actual in-scope Object.
3. Assertion sources reference eligible active Logical-applicable records from active Documents in the frozen context.
4. Submodel memberships, Attribute parents, and relationship endpoints exist in the applied-plus-candidate Model; active references require active parents/endpoints and relationship endpoint pairs are distinct.
5. No duplicate Submodel, Entity, Attribute, relationship, per-Entity membership, or per-parent source identities.
6. Locked records, sources, and memberships cannot change; candidate lock fields are false and saved locks are retained.
7. Required fields and values match existing Pydantic/database rules, including type/type-detail, cardinality, confidence, key/nullability policy, and positive or nonnegative order fields. AI-authored audit Attributes are rejected.
8. Preserve existing deterministic audit-template projection and whole-graph dependency checks before saving; read-only dependency context remains excluded from prompts/readers.

Logical Attribute identity is Entity + Attribute name; relationship identity is
both Entity/Attribute endpoint pairs + relationship name. Cardinality has four
values and excludes unknown. Stored confidence remains low/medium/high; the
approved quality policy uses high/medium Entities and high-only relationships.
Attributes have no confidence field. Audit flags in AI candidates must be false;
configured audit Attributes are projected by the existing backend. Omitted
records/sources/memberships remain; unchanged results are no-ops; Logical
duplicates remain strict. Existing bounded correction handles reported issues.
This documents current checks and does not authorize new runtime validation.

## Dimensional — One-shot and Tool-assisted

1. New/changed Entity Object sources use complete eligible Silver Object keys in the initial authorized scope/index.
2. New/changed Attribute sources use complete eligible Silver Attribute keys under the actual selected Object.
3. Assertion sources reference eligible active Dimensional-applicable records from active Documents in the frozen context.
4. Submodel memberships, Attribute parents, and relationship endpoints exist in the applied-plus-candidate Model before policy projection; active references require active records and endpoint pairs are distinct.
5. No duplicate Submodel, Entity, Attribute, relationship, per-Entity membership, or per-parent source identities. Relationship identity includes both endpoint pairs, kind, and nullable role.
6. Locked records, sources, and memberships cannot change; returned lock fields are false and saved locks are retained.
7. Required fields/values match existing Pydantic/database rules: fact type/grain, role/key-role, measure policy, cardinality, confidence, orders, and the 1-20,000 combined-record bound. Reject AI-authored technical/audit/surrogate/FK Attributes.
8. Validate both configured Gold templates, apply existing surrogate/history/audit and FK projection, then preserve final identity/lock and whole-graph dependency checks before saving.

These document existing checks. The proposed generation policy uses high/medium
Entities and Attributes, and high-confidence relationships with supported
cardinality/optionality. It does not change stored enums. The six-field
relationship identity includes kind and nullable role, not relationship name.
Gold projection owns technical/audit/surrogate/FK Attributes. Relationship
endpoints must exist before that projection; final projected identities also
undergo backend checks. No dependency context is added.

Current Dimensional candidates require 1-20,000 records. A valid unchanged saved
model-authored record can yield a no-op; all-empty abstention currently fails
validation and bounded retries. Do not invent output to satisfy the minimum.
This is an existing limitation, not a new success outcome or schema change.

## Duplicate handling and reuse

Identical returned Analysis records collapse to one, preserving the first
occurrence. The same natural identity with different confidence or basis returns
a correction error. Changed unlocked existing records update that identity;
unchanged records are no-ops. Omitted records are not deleted.

The repeated checks are natural-key scope lookup, duplicates, locks, and schema
validation. Reuse existing key normalization, candidate validators, Pydantic
models, and the configured correction loop. Correction errors identify the
original candidate row. No separate validation framework is needed.

Metadata description output remains a map: validate unique target keys without
changing its envelope. Existing output shape, required coverage, text limits,
and transaction-time authorization/revision/database checks still apply.

## Profiling — deterministic

1. Selected Object/Attribute keys exist in the authorized scope.
2. Batch configuration is valid for every selected Object.
3. Measurement targets are complete and unique.
4. Counts, lengths, and percentages satisfy the existing metric rules.

Profiling retains all-or-nothing saving and has no model correction loop.


## Mapping — before staging

1. Frozen target/Source System pair, route, active bindings and selected eligible sources resolve before authoring.
2. Object presence matches readiness; Attribute names cover exactly every actionable bound Attribute once.
3. Reject duplicate Attribute identities using the existing case-insensitive name rule.
4. Preserve locked/preserve records; author/extend only backend-computed actionable records.
5. Validate schema_version, exact outer fields, nonnegative dependency order, nonempty documents and existing record/byte bounds.
6. Derive real modeled/physical identities and selected template codes server-side; reject candidate-owned IDs, status, locks and provenance.
7. Validate staged records and effective Model graph, including references, dependency order/cycles, locks and revision rules.
8. Use bounded repair. Flexible document contents and template guidance are not falsely described as strict reference/type validation.

## Code Generation — before staging

1. Every target_ref resolves to a frozen target and every frozen target is covered.
2. Artifact file names are valid and unique within target; reject paths and dot names.
3. System assignments are known and cover every target's frozen System exactly once.
4. Validate artifact_role: transformations assign Systems; support assigns none.
5. Validate exact schema and bounds; parse SQL-only Databricks statements and reject fences/control garbage.
6. Derive stored natural identities, bindings, assignments and provenance; preserve generated-code locks.
7. Validate combined candidate/Change Set limits and effective Model graph before staging/apply.
8. Repair against frozen scope. Parsing is not execution or complete semantic relation/column checking.

## Validation — before staging

1. Exact system_ref resolves to frozen scope; combined run covers all selected Systems once.
2. Group names are unique within System; Check names within Group, using normalized keys.
3. Validate schema, severity/operator/type enums and operator/operand combinations.
4. Validate typed scalars/lists, homogeneous nonempty lists, date/time forms and Query B requirements.
5. Validate governed Databricks SQL/qualification. Scalar one-row/one-column shape is an execution check.
6. Preserve locked Groups/Checks; retire omitted unlocked active definitions under existing complete-ledger reconciliation.
7. Validate count/byte bounds and active Group-parent references in the effective Model graph.
8. Repair before staging; server-side ownership, scope, Tenant Lock and revision fences remain authoritative.

## Implementation status

Implementation was authorized on 2026-09-07. The current change adds the
Object/Attribute enrichment split, natural-key description targets, five scoped
enrichment inputs, workflow-local variable catalogs, optional frozen readers,
and restricted Jinja rendering. The same saved prompt configurations run in the
web worker and packaged notebooks. Backend scope, lock, revision, candidate,
whole-graph, and transaction checks remain authoritative.

Connection description is now an optional foundational field. Saved Profile
context carries available timestamp and run/batch provenance. Historical batch
column names unavailable in stored evidence remain null.

Analysis collapses exact duplicates and rejects conflicting duplicates. Other
workflow-specific duplicate and omission rules remain as listed above. Code and
Validation retain their public null execution mode while their internal model
calls support configured readers. See [implementation verification](workflow-implementation-verification.md)
for final local test and artifact results.

The same lists are available as [JSON](workflow-prompts/validation-contracts.json).
