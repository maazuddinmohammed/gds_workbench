---
name: atlas-verify
description: Verify Atlas models, mappings, generated artifacts or changes, and author SQL Validation definitions when requested. Distinguishes structural checks, business review, saved check definitions and measured execution evidence.
---

# Verify the requested result

Select the kind of verification from the user's outcome. “Validate this logical model” does not require Mapping or SQL check authoring.

| Requested result | Inputs and action |
|---|---|
| Record validity | Selected effective records, schemas and dependencies; run shared local validators. Server authorization/validation is separately authoritative. |
| Modeling quality | Relevant evidence, definitions, grain, identity, relationships and coverage; use the matching logical/dimensional/conceptual quality guide. Structural acceptance does not prove meaning. |
| Mapping or Code correctness | Applied prerequisites, complete Mapping consumer context and actual selected Code when implementation is tested. Check coverage, translation, population and dependency rules. |
| Persisted SQL Validation Groups/Checks | Applied complete Mapping; load actual Code when testing its implementation. Follow [SQL-check authoring](../../references/methods/sql-validation.md). Loaded-target checks may derive from Mapping without Code. |
| Measured data result | Explicit execution authorization, SQL policy and an available governed route. Follow [query scope](../../references/query-scope.md); distinguish prepared SQL from observed results and unsupported consumer behavior. |

## Inspect, check, report

1. Follow [working context](../../references/working-method.md) and [focused reads](../../references/tools/reads.md). Bind the selected scope, snapshot/revision and pending content. Reuse applicable check results only when their input bindings still match. A general explanation of a check needs no workspace setup.
2. Use [local validation](../../references/local-validation.md) for authoring invariants. Inspect actual findings and check statuses; do not treat `review_required`, `not_run` or `server_only` as passes. Run only relevant checks for ordinary local artifacts.
3. Review business correctness against attributable requirements and evidence. Use [logical design](../../references/logical-build/logical-design.md), [dimensional quality](../../references/dimensional-build/design.md#quality-checks), [conceptual methods](../../references/logical-build/business-concepts.md), [Mapping documents](../../references/model/mapping-documents.md) or [SQL checks](../../references/code-generation/sql.md#local-content-checks) as applicable, not all at once.
4. Keep completeness boundaries intact. Partial Mapping may support explicitly incomplete draft Code with typed placeholders. It cannot satisfy the complete-Mapping prerequisite for authoring SQL Validation definitions, and its output cannot be presented as executable business correctness.
5. Repair local defects through the owning skill when repair is requested or part of the ongoing authoring task. Preserve [record state](../../references/record-state.md), manual work and update scope. Missing business intent returns to the relevant modeling/Mapping decision; do not invent an expectation merely to pass a check.
6. Return the requested result using the optional [verification format](../../templates/validation-summary.md): scope/bindings, checks actually run, evidence, unresolved findings and required next action. Report authored, structurally checked, semantically reviewed, executed and applied states separately. SQL Never leaves execution not run.

Authored changes use the [Change Set lifecycle](../../references/change-set-lifecycle.md). Saving checks does not run the external comparator, schedule a pipeline or execute generated transformations. No unsupported execution fallback is implied. Route defects to [model change](../atlas-model-change/SKILL.md), [mapping](../atlas-mapping/SKILL.md), [code](../atlas-code-generation/SKILL.md) or [metadata](../atlas-metadata/SKILL.md) according to their cause.
