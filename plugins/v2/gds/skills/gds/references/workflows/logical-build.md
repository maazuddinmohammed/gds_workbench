# Logical Build

Require applied Model Input Scope and fresh Metadata/Model Snapshots. Read `model-input-scope.md`; load phase guides on entry. Use bounded Snapshot `select` plus current-task drafts; follow `../session.md` for live reads/revisions.

## Intake

Show existing results; resolve add/refine/rebuild intent once. Select all scoped Objects or named inputs without changing membership. Preserve valid existing results, locks and unrelated work; inspect downstream dependencies before structural changes.

Invoke `metadata-enrichment.md` for missing descriptions/types, reusing overwrite/fill-missing policy. Its separate Metadata task must Apply and refresh before dependent modeling. Keep unavailable evidence explicit. Read `../model-conventions.md`; confirm missing naming/audit choices only.

## Phases

1. **Profiling:** read `profiling.md`; resolve reuse, selected reprofile or skip from existing Profiles. Request batches only for measurements; use the deterministic planner and saved SQL policy.
2. **Analysis:** read `analysis.md`; investigate Object meaning and relationships across scope, measure signaled candidates when permitted, and retain supported/rejected/unresolved findings.
3. **Conceptual:** read `conceptual.md`; form reusable business concepts across Objects/Tenants/Systems, accounting for inputs without reproducing the Logical inventory.
4. **Logical:** build the operational model from these findings and reusable object-analysis notes.

Read `assertions.md` for existing Assertions or user-confirmed business rules. Generated interpretation is not an Assertion. Reuse findings; revisit affected evidence rather than restarting every phase.

## Logical decisions

Establish each Entity's row meaning, complete business-key tuple, lifecycle, source support and Attribute determinants. Explain retain/split/consolidate choices and plausible alternatives with evidence. A surrogate does not distinguish duplicate business occurrences.

- Consolidate equivalent Entities when meaning/grain agree across Tenants/Systems. Preserve source-qualified keys or confirmed crosswalks when local identifiers overlap; similar names do not prove shared identity.
- Consolidate Attributes only when units, precision, codes and time semantics agree. Preserve lineage and useful System-specific fields.
- Apply 1NF/2NF/3NF where supported: separate mixed grains, repeating groups, header/detail, independent lifecycles and genuine many-to-many relationships. Repeated values alone do not justify lookup Entities.
- Each Entity's generated BIGINT surrogate comes first, ending `ID`; foreign keys reference surrogates. Retain evidenced natural identifiers. Surrogates do not establish cross-System identity.
- Preserve identifier formatting, decimal capacity and date/time meaning. Sample types do not define production bounds; assess units/range and cast failures. Bronze STRING describes storage. Resolve unclear meanings before finalizing affected Attributes.
- Establish relationship direction, optionality, cardinality and complete source-key-to-surrogate lookup. Single-column Analysis cannot prove composite lookup: preserve tuple measurements in notes and cite applicable business Assertions where records cannot express them. Defer affected uncertain structures.
- Group submodels by business capability; share Entity memberships rather than duplicate Entities.

## Review

Account for every scoped Object AND Attribute as contribution, context, substantive exclusion or blocked. Empty, unfamiliar or single-System data is not automatically useless.

Inspect actual effective records alongside `../modeling-quality.md` diagnostics. Challenge duplicate representations, mixed grains, missing consolidation, excessive splits and unsupported exclusions. Source-shaped structures need grain/dependency justification. Explain isolated Entities and audit share without manufacturing Entities/edges to improve metrics. Trace outputs to evidence and inputs to outcomes; retain investigation in notes.

For substantial builds, a fresh reviewer examines grain, dependencies, relationships and types; the modeling owner resolves findings. With delegation disabled, perform that review explicitly in the same task. Query specific gaps under saved policy. Complete functional review before local validation/handoff; structural validity does not prove business correctness. Supported records remain `active`; never invent `needs_review` status or call blocked coverage complete.
