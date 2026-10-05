---
name: atlas-dimensional-model
description: Build or refine Atlas dimensional/Gold models from eligible applied Logical inputs, resolving analytical grain, dimensions, facts, measures and history. Supports Guided explanation and requested Grill Me discussion without separate skills.
---

# Build a dimensional model

Follow [Dimensional context](../../references/dimensional-build/context.md). Reuse applied eligible Silver inputs and existing analytical decisions; do not repeat the Logical profiling/conceptual chain. Use [Grill Me discussion](../../references/modeling-interview.md) only when requested or useful for unresolved decisions.

1. **Purpose and grain.** Resolve the analytical questions and business process from evidence and the request. State what one row represents for each selected fact, dimension or bridge, including business identity. A dimension-only request needs its intended member/version grain, not an invented fact or unrelated process.
2. **Dimensions.** Follow [dimensional design](../../references/dimensional-build/design.md): reuse compatible shared dimensions, distinguish roles and establish conformance across Systems/processes. Identify consequences for other stars before expanding an edit.
3. **Facts when requested.** Select appropriate event/snapshot behavior and measures. Define additivity, valid aggregation axes, units and population. A structurally valid star can still double-count or give wrong totals.
4. **History and keys.** Load [history](../../references/dimensional-build/history.md) when change behavior or historical lookup needs it. Resolve effective time and missing-version behavior from actual requirements and consumer support. Use configured dimensional schemas, [naming](../../references/model/naming.md), [keys/audit](../../references/model/keys-and-audit.md) and [Entity ownership](../../references/model/entity-ownership.md); do not guess missing template fields.
5. **Complete design.** Define real relationships, lineage, useful Submodels and justified bridges/standalone structures. Preserve grain/history decisions in supported definitions/basis. Use [Dimensional records](../../references/model/dimensional.md); do not invent SCD, bus-matrix or Logical-source fields.
6. **Update locally.** Follow [record state](../../references/record-state.md), [impact/update scope](../../references/methods/change-impact.md) and [Model authoring](../../references/model/change-sets.md). Preserve unchanged, protected and unrelated designs; current scope does not imply rebuilding all stars.
7. **Verify.** Run [local validation](../../references/local-validation.md) and [dimensional quality checks](../../references/dimensional-build/design.md#quality-checks) for each coherent part, then check cross-process coherence and requested coverage. SQL evidence remains optional under policy. Unresolved grain, identity or history must not be filled with a guess or disguised as an Assertion.

Done means the requested analytical design has defensible grain, measures, conformance, history and coverage, with checked records and explicit unresolved limits. Follow the shared [Change Set lifecycle](../../references/change-set-lifecycle.md) for the related batch or applied prerequisite. After verified Apply, refresh context before requested [Mapping](../atlas-mapping/SKILL.md) or optional [registration](../atlas-registration/SKILL.md). Mode changes never reset work or authorize Stage/Apply.
