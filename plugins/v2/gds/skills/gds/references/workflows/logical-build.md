# Logical Build

Require applied Model Input Scope and fresh Metadata/Model Snapshots. Read `model-input-scope.md`; load each phase guide when entering it. Use bounded Snapshot `select` and current-task draft evidence between phases; follow `../session.md` on live reads/revisions. Other workflows still require applied prerequisites.

## Intake and prerequisites

Show existing results. Resolve whether the user is adding inputs, refining areas, or rebuilding selected work; reuse supplied intent. Select all scoped Objects or named inputs without changing membership. Preserve valid existing results, locks, and unrelated work; inspect downstream dependencies before structural changes.

Invoke `metadata-enrichment.md` for missing descriptions/inferred types. Reuse the saved overwrite/fill-missing policy or ask once. It is a separate physical Metadata task; Apply and refresh before dependent modeling. Unavailable evidence remains explicit, not fabricated. Read `../model-conventions.md` and confirm only missing naming/audit choices.

## Phases

1. **Profiling:** read `profiling.md`; show existing Profiles and ask reuse, selected reprofile, or skip. Resolve batch choices only for requested measurements. Use the deterministic planner and saved SQL policy.
2. **Analysis:** read `analysis.md`; understand every Object, propose relationships across the complete scope, measure supported candidates when permitted, and retain supported/rejected/unresolved findings.
3. **Conceptual:** read `conceptual.md`; build high-level business concepts, consolidate equivalent meanings across Objects/Tenants/Systems, and account for every input. Do not reproduce the Logical inventory.
4. **Logical:** use the evidence and reusable object-analysis notes to build the operational model below.

Read `assertions.md` only for existing Assertions or user-confirmed business rules. Generated interpretation is not an Assertion. Reuse and update affected findings across phases; do not repeat full analysis on every run.

## Logical decisions

For each candidate Entity, state business grain, identifiers, lifecycle, source support, and Attribute determinants.

- Consolidate equivalent Entities across Tenants/Systems when meaning and grain agree. Source provenance is not a reason to separate them; similar names do not prove common row identity.
- Consolidate equivalent Attributes after checking units, precision, code definitions, and time semantics. Preserve lineage and useful System-specific fields.
- Apply 1NF/2NF/3NF where supported. Separate mixed grains, repeating groups, header/detail, independent lifecycles, and genuine many-to-many relationships. Do not create tiny lookup Entities just because values repeat.
- Every Logical Entity has its own generated BIGINT surrogate first, ending `ID`. Foreign keys reference those surrogate values. Retain evidence-based natural identifiers; surrogate keys do not establish cross-System identity.
- Use reliable inferred types, preserving leading-zero identifiers, exact decimals, and date/time meaning. Bronze STRING is storage, not the modeled type. Resolve unclear definitions before finalizing affected Attributes.
- Define relationship direction, optionality, and cardinality from evidence. Clarify or defer only affected decisions when structural uncertainty remains.
- Organize submodels by business capability. Share Entities through memberships, not copies per System/submodel.

## Coverage and review

Account for every scoped Object AND Attribute as a contribution, context-only, excluded with a substantive reason, or blocked. Empty, unfamiliar, or single-System data is not automatically useless.

Review the effective graph for duplicate representations, missing consolidation, excessive splits, mixed grains, and unsupported exclusions. Challenge source-table-shaped results; keep them only when grain/dependency analysis supports them. Trace outputs back to evidence and inputs forward to outcomes. Use definitions/source rationale for meaningful exceptions; keep investigative notes in the scratchpad.

Use the saved SQL policy for specific gaps; static validity is not business correctness. Complete functional review before local validation and the normal Model Change Set handoff. Supported records are `active`; never manufacture `needs_review` status or call blocked coverage complete.
