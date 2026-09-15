---
name: atlas-validation
description: Author or update meaningful technical and functional SQL Validation Groups and Checks for applied Logical or Dimensional Mapping and code. Select where each check adds value, preserve existing checks, and validate definitions locally before review and Apply.
---

# Validation

This workflow authors Validation definitions. SQL execution and interpretation require the separate governed execution and consumer contracts; storing a definition does not run it.

## Resolve the work

1. Follow the [working method](../../references/working-method.md). Reuse Tenant, working directory, Model, selected Systems and Logical/Silver or Dimensional/Gold targets. Both layers may be selected explicitly; Gold is not a prerequisite for Silver checks. Start/reuse Workbench through its verified launcher.
2. Load fresh-enough [Model Snapshot context](../../references/snapshots/model.md), preserving pending work. Require applied, complete Mapping/Binding and the [complete Mapping view](../../references/model/mapping-documents.md#complete-context-for-coding-and-validation). Load relevant current Code/assignments when testing transformation implementation. Loaded-target checks can be derived from Mapping without Code; never substitute a newly imagined implementation for missing actual code.
3. Inspect existing Groups/Checks, applied input changes, pending edits and [record state](../../references/record-state.md). Resolve [existing work and update scope](../../references/working-method.md#existing-work-and-update-scope). Reuse an explicit selection; otherwise offer the contextual affected/selected/reuse choices. Preserve locked, inactive and unrelated definitions.
4. Let the agent choose transformation output or loaded target **per meaningful failure**, following [check design](../../references/validation/check-design.md). Honor explicit user scope; do not ask a routine output/target/both question or generate both by default. Resolve only missing population, runtime or environment/parameter facts that affect the selected checks.
5. Show a compact, model-specific proposal grouped by technical purpose or functional feature: assertion, location/scope, expected basis and intended severity. Remove redundant checks; do not generate a check for every field, target or possible concern. Ask only about unresolved business expectations or material choices. SQL policy governs optional evidence execution, not SQL authoring.

## Author and verify

1. Build purposeful Groups and one-assertion Checks using [check design](../../references/validation/check-design.md). Derive expected behavior from Mapping and confirmed business rules; use actual Code as the implementation being tested. Keep expected comparisons independent and populations aligned.
2. Follow [Validation records](../../references/model/validation.md) for exact fields, operators, typed operands, SQL limits, ownership and complete examples. Use [Model Change Set authoring](../../references/model/change-sets.md) to write complete changed records locally. The System association does not add SQL filters.
3. Preserve selected-update boundaries. Merge by canonical key and retain unrelated pending work. Do not send a partial selection to a reconciler expecting a complete System ledger. Review freshness changes at Group/System level before claiming retained checks are current.
4. Run [local validation](../../references/local-validation.md), the record checks and [check-design review](../../references/validation/check-design.md#review-the-complete-local-batch). Repair shape, scope, safety, population and expectation errors. Missing Mapping intent returns to Mapping; do not invent a business rule to make a test pass.
5. Optional preflight follows [query scope](../../references/query-scope.md) and the check-design guide. Keep test substitutions separate from saved definitions. Record structural validation, executed evidence and unexecuted checks distinctly; do not claim the external runner/comparator was tested.
6. Review the complete local batch in Workbench: new/changed/protected checks, coverage, expected behavior, findings and unresolved prerequisites. Follow the shared [Change Set lifecycle](../../references/change-set-lifecycle.md); no Stage/Apply per Check. After verified Apply, refresh the Model Snapshot and confirm saved definitions and authoritative freshness information where available.

Stop at the agreed boundary. Apply stores definitions; scheduling, running the pipeline, loading targets and Process configuration remain separate actions.

## Targeted exceptions

- Unknown null comparison, tolerance, timezone or runtime placeholder behavior: inspect the actual consumer contract/code or ask for the missing rule; no assumed evaluator behavior.
- Saved Checks use [fully qualified Validation SQL](../../references/model/validation.md#sql-eligibility-and-protection), while framework Code keeps its own runtime qualification. Prepare separate qualified probes; do not rewrite Code or invent catalogs.
- An unchanged or locked Check is affected by input changes: report its stale/unverified state; do not rename it, bypass protection or mark the Group fresh without review.
- Python transformation: SQL may validate its registered output, but does not automatically execute Python. Verify an actual supported output/runner contract before proposing an implementation-output check.
