---
name: atlas-dimensional-build-grill-me
description: Develop or challenge a dimensional model collaboratively from eligible Silver context. Use for Grill Me Gold modeling to resolve analytical outcomes, grain, shared dimensions, measures and history through a focused modeling interview.
---

# Dimensional build — Grill Me

Follow [Dimensional context](../../references/dimensional-build/context.md), then the shared [modeling interview](../../references/modeling-interview.md). This skill owns the adaptive conversation; Guided has its own sequence.

1. Reuse the user's outcome, scope and existing decisions. Propose a short approach around meaningful business processes or questions; distinguish discussion-only work from authorized local Model authoring.
2. Inspect eligible Silver context and current model before asking. Resolve the next consequential decision using [dimensional design](../../references/dimensional-build/design.md): what one row means, which dimensions are shared, how measures aggregate, or what history a report must show. Recommend an answer from evidence and test it with a relevant concrete scenario.
3. Use [history and lookup rules](../../references/dimensional-build/history.md) when needed. Ask only questions that could change the design; group tightly related choices when useful. No mandatory full questionnaire, profiling run, Conceptual rebuild or Guided phase artifacts.
4. Build each agreed part through [Dimensional records](../../references/model/dimensional.md) and [Model Change Sets](../../references/model/change-sets.md). Reuse [naming](../../references/model/naming.md), [keys/audit](../../references/model/keys-and-audit.md), [record state](../../references/record-state.md) and applicable [Assertions](../../references/model/assertions.md). Do not fabricate supports for standalone structures.
5. Run [local validation](../../references/local-validation.md) and dimensional quality checks for each coherent part. Show the resulting decision/change and remaining uncertainty. If asked to proceed independently on an agreed approach, do so; return for material unresolved business choices.
6. Review whole-request coherence: shared dimensions, cross-process comparisons, grain, history and coverage. Preserve unrelated work; shared-dimension edits can affect other stars. Follow the shared [Change Set lifecycle](../../references/change-set-lifecycle.md) at the complete-batch/dependency boundary, not after every interview answer.

Example useful question: "When a customer changes segment, should old sales remain under the segment at sale time or move to the current segment?" Ask it only when the analytical requirement is unresolved; accepted model flags do not prove the framework can implement the answer.

Switching to Guided follows the [shared switching rule](../../references/dimensional-build/context.md#switching-build-skills). After verified Dimensional Apply, the same requested Gold registration, Binding and Mapping workflows apply. No separate GrillMe installation or parallel decision ledger is required.
