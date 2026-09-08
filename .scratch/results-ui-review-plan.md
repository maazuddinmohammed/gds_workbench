# Results review: bounded presentation changes

Read-only preparation, 2026-09-05. No production edits. Read
`docs/design-system.md`, actual result/detail components, DTOs, existing screen
tests, matching CSS, and current diff. This is a source review; browser evidence
is required after implementation.

## Preserve current work

- Analysis selection, lock/unlock/deactivate/reactivate, revision refresh and
  safe conflict handling were already added. Keep those controls intact.
- Shared `DetailState` replaces duplicate local implementations; keep it.
- Existing modeled/Mapping/Code/Validation Run monitor already starts collapsed,
  opens for a newly started Run, and has authoritative draft review, retained
  failed drafts and token/cost receipts. Do not build another Run panel.
- Keep manual Refresh, cursor pagination, Tenant/Model/revision/Lock context,
  explicit permission failures, literal SQL rendering, and all truncation notices.
- Existing ledgers are reasonable comparison surfaces. The clearest remaining
  problem is detail hierarchy: identifiers/provenance often precede the result.

## 1. Profiling: compare metrics, inspect one Attribute

Files: `features/profiling/ProfilingDetail.tsx`, `styles/profiling.css`,
`features/profiling/ProfilingScreen.test.tsx` (under `web_app/frontend/src`).

Current detail has 12 context facts, then 22 table columns. Provenance repeats
Workflow Run, Agent Run, timestamps and a 64-character digest per Attribute.

Smallest useful change:

- Keep Object name, Source Tenant/System/Connection, Model revision, latest
  profile time and returned Attribute count visible. Put numeric identifiers in
  an explicit Record details disclosure after the evidence.
- Main table: Attribute, catalog type, rows, populated %, distinct %, duplicate
  %, null %, blank %, and a labeled Review action. Keep sticky Attribute identity
  and real horizontal scrolling.
- Review opens an inline selected-Attribute inspector beneath the table (local
  state, no new request): counts, lengths, the exact recorded percentages, then
  provenance/digest. One selected Attribute at a time, named heading, close
  action, keyboard focus/return. Preserve every existing metric.
- Keep zero as zero, nullable metrics as Not recorded; do not recompute counts
  or percentages. The DTO only exposes `attribute_data_type`, so label it Catalog
  type. An inferred type needs a real API field before this screen can show it.
- Keep `profiles_truncated` prominent; returned records are not total coverage.

Test a multi-Attribute record, zero/null metrics, long names/digests, keyboard
selection/close, exact provenance, truncation, back-link filter restoration and
narrow horizontal scrolling. Existing numeric count fields are numbers; only
average length/percentages permit decimal strings. No new numeric conversion
layer is justified by this review.

## 2. Stored SQL: bring the artifact forward

Files: `features/code_generation/GeneratedSqlDetail.tsx`,
`styles/code-generation.css`, `features/code_generation/CodeGenerationScreen.test.tsx`.

Stored SQL currently comes after target, contributing Systems, applied Mapping
supports and generation provenance. Move it directly after compact target and
current/stale status. Follow with Mapping supports and generation provenance.
Keep Download, Regenerate, permission gating, literal text and byte count.

The DTO supplies currentness, source Systems and Mapping support provenance; it
does not supply execution success. Do not label generated SQL as executed or
validated against live data. Preserve stale-artifact empty support explanations,
support truncation and legacy guide/generator absence. Link an actual Mapping
support ID to its existing Mapping detail route rather than showing only text.

Test semantic section order, exact SQL text, stale/current and legacy records,
bounded support notice, working Mapping link and unchanged regeneration flow.

## 3. Analysis: distinguish inference from measured validation

Files: `features/analysis/AnalysisDetail.tsx`,
`styles/analysis-assertions-modeled.css`, `features/analysis/AnalysisScreen.test.tsx`.

The detail already has sensible endpoint and basis sections. Improve it locally:

- Header shows `status` and lock state in addition to validation state/result.
  A null result means Not validated; no invented failure or quality score.
- Keep exact from/to identities, schema, Source Tenant/System and Connection.
  The current page omits Connection even though `AnalysisEndpoint` supplies it.
- Label the basis/kind/confidence block Relationship inference. Label the
  separate `evidence` block Recorded validation evidence.
- Align source/target non-null and distinct counts in a small comparison table;
  show missing targets, unused targets and duplicate target keys beside the
  recorded result. Do not infer a result from the counts in the browser.
- Put policy version/digest with provenance. Digest exists in the DTO but is
  currently omitted; preserve exact value in a labeled disclosure.
- Keep the full relationship basis and `relationship_basis_truncated` notice.
  Use existing date formatters and restore detail heading focus consistently.

Test active/inactive and locked/unlocked independently; unvalidated evidence-null
versus supported/inconclusive/unsupported; zeros; exact endpoints and safe text.
Do not modify the recently fixed Analysis review command path.

## 4. Conceptual, Logical, Dimensional: decision, evidence, record metadata

Files: `features/conceptual/ConceptualDetail.tsx`,
`features/logical/LogicalDetail.tsx`,
`features/dimensional/DimensionalDetail.tsx`,
`styles/analysis-assertions-modeled.css`, matching `*Screen.test.tsx`.

- Keep names, definitions, grain, relationship endpoints and rationale first.
  Confidence is a recorded judgment, not a computed quality score.
- Evidence rows keep full source identity, role/order where present, rationale,
  status/lock and Assertion text immediately readable. Remove repeated source
  names from the secondary fact grid. IDs, Workflow Run and timestamps move
  together into explicit Record details inside the existing evidence row.
- Place Submodel membership after supporting source evidence. Memberships are a
  compact ledger (name, status, lock, provenance), not repeated fact cards.
- Split Logical Attribute facts into Type/nullability and Keys. Split
  Dimensional facts into Type/role, Keys/grain, and Aggregation/change behavior.
  Render only meaningful optional groups; preserve explicit native values.
  Do not show a grid of Not applicable fields on every non-measure Attribute.
- Fix Conceptual relationship endpoint display to preserve exact object names;
  it currently passes identifiers through `humanize`, replacing underscores.
- Logical detail headers lack the existing Conceptual/Dimensional heading focus
  behavior. Match it while preserving routes and state badges.

DTO limits: Entity detail does not contain an Attribute roster; relationship
detail does not contain measured profiling/Analysis evidence. Do not invent
rosters, lineage graphs, numeric confidence, policy explanations or source
samples. A source support is a reference plus authored rationale, not proof that
the relationship was measured. Keep native Object/Attribute/Assertion variants.

Test multiple physical/Assertion sources, preserved exact names, long rationale,
membership and source states, source details keyboard behavior, boolean false,
null optional groups and heading focus. Verify each family separately.

## 5. Mapping: transformation first; preserve native open JSON

Files: `features/mapping/MappingDetail.tsx`,
`features/mapping/MappingDocumentView.tsx`, `styles/models-scope.css`,
`features/mapping/MappingScreen.test.tsx`.

Current Attribute detail has four context/delivery sections before its document;
Object detail repeats template code and related metadata across two sections.

- Lead with one target-to-modeled-source comparison, physical zone/type where
  available, Source System, state/lock, and template name. Then show the
  transformation document; follow with parent Mapping and provenance.
- Keep the actual template name/code/state together once. Numeric IDs and exact
  template digest belong in Record details. Link the parent Object Mapping.
- `mapping_document` is intentionally `JsonObject | null`, with arbitrary
  template keys. Its detail DTO exposes template provenance, not the template
  schema. Do not impose invented fields such as joins/filters/expression or
  infer lineage by parsing authored prose/SQL.
- Improve the existing recursive renderer locally: show exact field keys along
  with readable labels, preserve primitive types and array order, and put nested
  content under its actual key rather than repeated generic Record cards.
  Distinguish null, empty object, empty array, empty string and absent document.
  Keep unknown keys visible and render strings as text. No new schema framework.

Test a seeded template-shaped document, independent free-form document, nested
arrays/objects and unusual exact keys, null/empty/string/boolean/number values,
long SQL-like strings, literal HTML and active/inactive template provenance.

## 6. Validation: check definitions are not execution results

Files: `features/validation/ValidationLedger.tsx`,
`features/validation/ValidationScreen.tsx`, `styles/validation.css`,
`features/validation/ValidationScreen.test.tsx`.

The native API stores authored groups/checks, severity, Query A/B, comparison
operator/value/type, active state and context currentness. It has no execution
receipt or pass/fail counts. Keep explicit Applied check definitions wording and
a concise explanation that the Run authors a draft for review/Apply.

- Keep grouping and current/stale Mapping/Code badges; label freshness separately
  from severity and active state so Current cannot be read as Passed.
- In the selected Check, place the recorded assertion (operator, operand and
  type) before SQL; then Query A and optional Query B.
- Add `aria-controls` to the existing detail button and focus the selected Check
  heading; restore trigger focus when closed. This can remain the current inline
  inspector, without a new drawer or result type.
- Preserve exact category/operator where interpretation requires it; do not
  invent a friendly operator mapping without checking the canonical enum.

Test definition-only wording, current/stale without pass/fail claims, query and
literal/list assertions, zero/false/empty operands, group changes, keyboard
review and existing permission/revision handling.

## Verification and sequence

Implement one numbered slice, inspect its native fixtures, run its focused
tests/types, then browser-review wide and 58rem/42rem layouts before the next.
Finish with `npm --prefix web_app/frontend run check`. Keep semantic tokens,
ordinary ledgers, literal governed output and all access/error boundaries.
No package or shared generic presentation framework is needed.

Dimensional workflow reliability work remains separately frozen in
`.scratch/dimensional-full-graph-repair-preparation.md` and its four passing
read-only witnesses. No Dimensional production changes are authorized by this
results review.
