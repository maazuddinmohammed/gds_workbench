---
name: atlas-logical-model
description: Build or refine Atlas logical Entities, Attributes, relationships and Submodels with explicit grain, identity and normalization. Supports Guided explanation and requested Grill Me discussion in the same workflow.
---

# Build a logical model

Produce the requested normalized design with explicit grain, complete identity and defensible lineage. Work through coherent parts and verify each before dependent work.

Use applicable profiling, [Model enrichment](../../references/model/enrichment.md) and analysis from the effective local view, including pending proposals. Reuse earlier local results without applying each phase.

Reserve effective audit-template names for framework fields. Give source/business fields distinct semantic names, such as `SourceCreatedDate`. Keep exactly one correctly marked framework block in complete final plugin records; see [keys and audit](../../references/model/keys-and-audit.md).

## Enter at the needed point

Follow [Logical context](../../references/logical-build/context.md). Inspect selected source evidence and effective existing design. For a larger source-to-model request, use [source analysis](../atlas-source-analysis/SKILL.md) for material evidence gaps and [conceptual modeling](../atlas-conceptual-model/SKILL.md) for business concepts when needed; return here with their evidence. Reuse valid outputs instead of repeating a fixed phase chain.

Guided explanation is the default. Requested Grill Me uses [modeling interview](../../references/modeling-interview.md) with the same task, snapshots and rules. Clarify consequential missing business decisions in either mode; no separate mode menu or installation. SQL Never permits metadata-based modeling with explicit unmeasured findings.

## Design and author

1. Use [logical design](../../references/logical-build/logical-design.md) to establish each Entity's business meaning, one-row grain and complete natural identity, including source namespace where necessary. Resolve ambiguity before designing dependent keys/relationships.
2. Apply [normalization decisions](../../references/logical-build/normalization.md) to actual dependencies and lifecycle, not a mechanical split-per-table rule. Reuse equivalent concepts and distinguish real roles. Preserve the requested scope and explicit design decisions.
3. Use configured logical schemas, [Entity ownership](../../references/model/entity-ownership.md), [naming](../../references/model/naming.md) and [key/audit policy](../../references/model/keys-and-audit.md). Read actual Model policies/templates; examples are not proof of configured types or defaults.
4. Design Attributes, key roles, nullability and relationships using [Logical records](../../references/model/logical.md). Logical cardinality must be supported; unresolved candidates stay in task evidence. A physical Attribute source requires its matching Object source on the Entity. Intentional generated structures may lack physical sources; available lineage must not be hidden.
5. Organize useful Submodels around understandable business areas without duplicating Entities solely for grouping. Persist supported FK relationships and perform the [relationship/graph review](../../references/logical-build/logical-design.md#relationship-and-graph-review). Explain isolated Entities/disconnected groups; standalone designs are allowed with an applicable reason. Matching names alone do not establish a relationship.
6. Respect [record state](../../references/record-state.md) and [existing-work scope](../../references/methods/change-impact.md). Write complete changed records through [Model authoring](../../references/model/change-sets.md); preserve unrelated drafts, protected records and valid manual decisions. Assertions are optional attributable rules, not required for every answer.
7. Run [local validation](../../references/local-validation.md) and design-quality checks after each coherent batch. Check the complete effective graph, selected-input coverage and dependency effects, not just the last Entity. Resolve failures before dependent work; report uncertain or excluded inputs explicitly.

## Completion and transitions

Show requested coverage, grain/identity decisions, relationships, validation results and unresolved business questions. Accumulate related local phases where contracts permit; use the [Change Set lifecycle](../../references/change-set-lifecycle.md) when ready or when a downstream applied prerequisite requires it. Do not Stage/Apply after every Entity or interview answer.

After required modeling changes are applied, requested [Mapping](../atlas-mapping/SKILL.md) or [Dimensional modeling](../atlas-dimensional-model/SKILL.md) can continue. [Target registration](../atlas-registration/SKILL.md) is an optional operational handoff, not a Mapping prerequisite. For a change spanning existing downstream artifacts, use [model change](../atlas-model-change/SKILL.md).
