---
name: atlas-dimensional-build-guided
description: Build or refine a dimensional model from applied Logical Mapping and eligible Silver contributions through business process, grain, dimensions, facts and quality review. Use for Guided Gold modeling; collaborative Grill Me modeling has its own skill.
---

# Dimensional build — Guided

Follow [Dimensional context](../../references/dimensional-build/context.md), then use this sequence. Reuse existing work and explicit user decisions; do not run the Grill Me interview or repeat Logical Build's phase chain.

## Guided sequence

| Step | Action |
|---|---|
| Business purpose | Identify the operational activity and analytical questions from the requested scope. A dimension-only request needs its intended use, not an invented fact/process. Ask only where the outcome is unresolved. |
| Grain | State exactly what one selected Entity row represents: fact event/period, dimension member/version or bridge membership, including business identity. Resolve consequential ambiguity before dependent design. |
| Dimensions | Identify context at that grain; reuse compatible shared dimensions, distinguish roles and establish conformance across Systems/processes. |
| Facts, when in scope | Choose the appropriate fact behavior and measures; define additivity, aggregation, units and valid analysis axes. Skip for dimension-only work. |
| Complete the design | Apply shared keys/audit, Attribute history rules, real relationships, lineage, useful Submodels and any justified bridges or standalone structures. |
| Review and validate | Check analytical correctness and coverage, then validate the complete effective records. Repair contradictions before treating the model as ready. |

Use [dimensional design](../../references/dimensional-build/design.md) for these decisions and [history](../../references/dimensional-build/history.md) only when change behavior or time-sensitive lookup needs it. These are decision steps, not separate mandatory datasets or approvals. Revisit affected earlier decisions when later evidence changes them.

## Reuse and author locally

1. Follow the shared [update-scope rules](../../references/working-method.md#existing-work-and-update-scope). New/missing selected work proceeds from the resolved outcome; existing work is reused or revised according to the user's selection. Show shared-dimension effects before extending scope; preserve unrelated and protected records.
2. Use [Dimensional records](../../references/model/dimensional.md) and [Model Change Sets](../../references/model/change-sets.md) to write complete records locally. Do not add unsupported SCD, bus-matrix or Logical-source fields. Keep population decisions in supported definitions/basis and lineage in real source records.
3. Run [local validation](../../references/local-validation.md) and the [design quality checks](../../references/dimensional-build/design.md#quality-checks) after each coherent batch. SQL is optional under policy; its actual scope and limits remain explicit. A structurally valid star can still give wrong totals.
4. Review requested coverage across all selected processes, not only the last part. Follow the shared [Change Set lifecycle](../../references/change-set-lifecycle.md) for the complete batch or required applied dependency; do not Stage/Apply per fact or dimension.
5. After verified Apply, refresh the Model Snapshot. Continue to [Gold target registration](../atlas-target-registration/SKILL.md), [Binding](../atlas-entity-binding/SKILL.md) or [Mapping](../atlas-mapping/SKILL.md) only when requested or already part of the agreed journey.

Unresolved grain, history or identity stays explicit. Do not fill a schema field with a guess, create an Assertion to disguise uncertainty or force unsupported runtime behavior into code.
