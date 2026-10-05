---
name: atlas-conceptual-model
description: Build or refine Atlas business concepts and conceptual relationships from scoped evidence and requirements. Use for business meaning, conceptual modeling or a needed conceptual part of a larger modeling request.
---

# Model business concepts

Produce concepts with clear business meaning and supported relationships. A conceptual model is not a renamed physical schema or a premature logical design.

1. Follow [working context](../../references/working-method.md). For persisted work, resolve the Model, selected applied Input Scope, required [Metadata](../../references/snapshots/metadata.md) / [Model](../../references/snapshots/model.md) evidence and effective existing Conceptual records. Preserve bound drafts. Discussion-only work need not create records or a workspace.
2. Read [business concepts](../../references/logical-build/business-concepts.md) and the [Conceptual record contract](../../references/model/conceptual.md). Inspect relevant source meanings, Analysis, profiles and attributable [Assertions](../../references/model/assertions.md). Use [domain rules](../../references/domains/index.md) only with verified applicability. Missing material evidence returns to [source analysis](../atlas-source-analysis/SKILL.md); profiling is not a mandatory ceremony.
3. Identify the business subject, what one instance represents, lifecycle and meaningful distinctions. Reuse/consolidate equivalent concepts; separate genuinely different roles. Resolve consequential ambiguity with the shared [interview method](../../references/modeling-interview.md), reusing confirmed answers. Unknown facts remain unknown.
4. Attach actual physical or Assertion supports and explain justified standalone/generated concepts. A requirement is not proof that a physical source exists. Do not fabricate supports or create an Assertion merely to make validation pass.
5. Define business relationships and their basis. Conceptual cardinality can be unknown. Do not invent a multiplicity from column names or copy physical foreign keys without understanding their business meaning.
6. For changes, follow [record state](../../references/record-state.md) and [impact/update scope](../../references/methods/change-impact.md). Write complete records through [Model authoring](../../references/model/change-sets.md), preserving pending work and unrelated concepts. Capture consequential decisions in existing evidence; the optional [decision format](../../templates/modeling-decision.md) adds no new ledger.
7. Run [local validation](../../references/local-validation.md) and conceptual quality review. Check real endpoints, eligible supports, coherent definitions and coverage of selected inputs. Report exclusions, uncertainty and affected downstream designs rather than silently rewriting them.

Done means the requested concepts and relationships are explained, represented where authoring was requested, and checked against their evidence. Follow the [Change Set lifecycle](../../references/change-set-lifecycle.md) when submitting; a conceptual phase boundary alone does not require Apply. Continue to [logical modeling](../atlas-logical-model/SKILL.md) only when requested. Existing valid conceptual work can be reused without rebuilding it.
