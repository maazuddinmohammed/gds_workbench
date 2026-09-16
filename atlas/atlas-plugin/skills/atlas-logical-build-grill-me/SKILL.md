---
name: atlas-logical-build-grill-me
description: Develop or challenge a logical model collaboratively through a scope-aware modeling interview. Use when Atlas selects Grill Me logical build or the user wants to reason through grain, identity, relationships and design choices step by step.
---

# Logical build — Grill Me

This skill owns collaborative model building. It uses the same domain rules and record contracts as Guided, with an adaptive interview sequence.

## Establish context

Follow [Logical build context](../../references/logical-build/context.md), then load the [modeling interview](../../references/modeling-interview.md). Reuse the user's selected workflow, outcome and starting area. Inspect existing scope and decisions before asking questions.

## Work with the user

1. Resolve only missing outcome or starting scope; propose a short revisable approach. Preserve requested coverage and distinguish discussion-only work from authorized local authoring.
2. Follow the interview reference: inspect evidence, select a consequential decision, recommend an answer, test relevant business scenarios and record the decision. Work on coherent parts and inspect their neighbors; no mandatory Guided phase sequence or full questionnaire.
3. Use the topic guides below when needed. Reuse applicable evidence and ask about consequential uncertainty; SQL remains optional under the saved policy and shared batch rules. Do not create intermediate artifacts solely to imitate Guided.
4. Build or revise each agreed part locally through [Model Change Sets](../../references/model/change-sets.md), preserving locks, inactive history and unrelated work. Follow actual prerequisites; an adaptive sequence cannot bypass an applied dependency.
5. Run [local validation](../../references/local-validation.md) and business-quality checks for the completed part. Show the decision/change and remaining uncertainty, then continue. If asked to follow the agreed plan independently, do so; return for decisions that need user input.
6. Before completing the request, run the shared [relationship and graph review](../../references/logical-build/logical-design.md#relationship-and-graph-review) across requested parts: persist supported FK relationships and resolve unexplained isolated Entities/disconnected groups with the user, reusing applicable decisions. Standalone designs are allowed; matching names alone do not justify a link. Keep partial progress explicit. Follow the shared [Change Set lifecycle](../../references/change-set-lifecycle.md) for the related batch or an applied dependency; a question, answer or part boundary does not trigger Stage/Apply.

## Topic references

Read only what the current decision needs:

- [Profiling](../../references/logical-build/profiling.md): prepare/reuse measurements and execute only permitted queries.
- [Finding relationships](../../references/logical-build/find-relationships.md): identity/role and categorical references, evidence and cardinality.
- [Business concepts](../../references/logical-build/business-concepts.md): business meanings, consolidation and supports.
- [Logical design](../../references/logical-build/logical-design.md) and [normalization](../../references/logical-build/normalization.md): grain, boundaries, lineage, relationships and Submodels.
- [Naming](../../references/model/naming.md), [keys/audit](../../references/model/keys-and-audit.md) and [Logical records](../../references/model/logical.md): common defaults and exact payloads.
- [Assertions](../../references/model/assertions.md): attributable reusable rules when useful; not every answer needs a new Assertion.

The interview reference owns questioning and decision capture. Domain rules remain shared; avoid copying them into this skill. No separate GrillMe installation is required. This workflow is distinct from Atlas's top-level Custom workflow.

## Continue or switch

Follow the [switching rule](../../references/logical-build/context.md#switching-workflows) if the user selects Guided. Once the requested model is ready and required modeling changes are applied, continue through [target registration](../atlas-target-registration/SKILL.md) and [Entity Binding](../atlas-entity-binding/SKILL.md) when requested. Those workflows own storage assignment; modeling decisions remain available to Mapping and Code Generation.
