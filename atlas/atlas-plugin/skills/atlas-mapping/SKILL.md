---
name: atlas-mapping
description: Define transformations from eligible inputs to bound Silver or Gold targets. Author concise Object steps, Attribute rules and dependencies per target/source System so Coding and Validation can consume the complete Mapping without reconstructing the model.
---

# Mapping

Logical Mapping supplies Silver targets; Dimensional Mapping supplies Gold targets. Each Mapping branch is one bound target and originating source System. Code Generation later chooses one file per target or separate System/target files.

## Establish inputs

1. Follow the [working method](../../references/working-method.md). Reuse Tenant, working directory, Model, selected targets and Logical/Silver or Dimensional/Gold route. Resolve SQL policy/environment only when evidence queries are relevant. Start/reuse Workbench through its verified launcher.
2. Require active applied [Entity Binding](../atlas-entity-binding/SKILL.md). Read the bound [Model](../../references/snapshots/model.md) and [Metadata](../../references/snapshots/metadata.md) Snapshots, including pending Mapping work. Confirm current target/source definitions; reconcile any required refresh without replacing pending edits. Binding/model changes needed upstream must finish before dependent Mapping authoring.
3. Read the [Mapping record contract](../../references/model/mapping.md). Resolve every active bound target Attribute, including keys, audits, constants and generated fields. Inspect existing branch documents and dependencies under [record state](../../references/record-state.md); preserve valid locked and unrelated work.
4. Use the exact existing GDS [Mapping templates](../../references/model/mapping-documents.md). The user's request to reuse them is already the selection decision. Show a representative result and exceptions; do not ask again merely to choose the same template. Verify installed template codes before referencing them; preserve a previously selected custom template or resolve an actual conflict.
5. Resolve [existing work and update scope](../../references/working-method.md#existing-work-and-update-scope). Inspect existing Mapping and known model/source/Binding changes; show affected target/System branches and their reasons. Ask the contextual selection question unless already answered. Regenerate selected affected logic and retain compatible unchanged rules; do not rebuild every target because the Model revision changed.

## Author the complete transformation

1. **Resolve contributions.** Start from the modeled supporting Objects/Attributes, source ownership and existing mappings. Determine which inputs actually supply this target/System branch. Include needed lookup/preparation inputs; do not copy every supporting Object into the query or infer origin from its physical GDS System. Apply the route-specific eligibility checks.
2. **Establish grain and identity.** Retain the agreed target grain and complete business/merge-key tuple, including source namespace where needed. Distinguish generated own keys from mapped foreign keys. For multiple Systems, state whether identities stay separate or are reconciled and how; file grouping does not settle collisions or precedence.
3. **Write Object steps.** Follow the [document guide](../../references/model/mapping-documents.md#object-level-steps): read/preparation, joins and exact predicates, filter placement, any justified grouping/deduplication, output grain and final ordered projection. Use short ordered instructions; include only necessary stages. Resolve any generation-only inputs and runtime parameter rules.
4. **Write Attribute rules.** Follow [Attribute instructions](../../references/model/mapping-documents.md#attribute-level-instructions). Cover each active bound target column per System with real lineage and an expression or generation rule. Reconcile storage/inferred/target types, identifier formatting, precision, nulls and invalid values. Keep field transformations here; Object steps refer to them.
5. **Resolve dependencies.** Preserve or author the layer/System `mapping_dependency` and branch `object_dependency_order`. Explain actual predecessor/lookups where needed; order must satisfy them. Keep source contribution order, Attribute ordinal, System order and Object order distinct. Equal ordering is suitable only when confirmed work is independent; unresolved cycles or repeated execution needs require an explicit supported plan.
6. **Check independent usability.** Follow the [consumer context](../../references/model/mapping-documents.md#complete-context-for-coding-and-validation) and checks. A coding/validation reader must obtain target placement, physical aliases, types/nullability/order, all System branches, dependencies and population rules from one complete Mapping view. Do not make it rediscover the design through Conceptual/Logical records or interpret a list of supports as transformation logic.
7. **Write and validate locally.** Save complete changed records in `model-change-set/mapping_dependency.json`, `mapping_object.json` and `mapping_attribute.json` using [Model authoring](../../references/model/change-sets.md). Preserve previous pending content. Run [local validation](../../references/local-validation.md), Mapping structural checks and the document-quality checks. Repair substantive gaps before considering the affected branch ready.
8. **Review and finish.** Show sources, concise steps, Attribute rules, generated omissions and dependency order in Workbench. Accumulate related branches locally; then follow the shared [Change Set lifecycle](../../references/change-set-lifecycle.md). After verified Apply, refresh the Model Snapshot and confirm the applied Mapping. Stop before [Code Generation](../atlas-code-generation/SKILL.md) unless already requested.

## Ask only about unresolved rules

Group related exceptions and recommend an evidence-based option:

- **Cross-System identity:** keep source-qualified records separate, or reconcile the same business entity? If reconciled, what matching/survivorship rule applies?
- **Competing rows:** which evidenced key and ordering choose a row, and what happens on a tie? Do not assume latest-wins or add DISTINCT.
- **Lookup/conversion failures:** reject, preserve a null where allowed, or use a specified fallback? Do not invent missing-value policy.
- **Consumer behavior:** if runtime batching, parameters or loading behavior are unclear, ask for the relevant rule or orchestration code and inspect it.

Reuse confirmed answers. Straightforward direct mappings need no interview. Independent branches may progress while a blocked branch remains explicit; no invented `needs_review` status or activation of incomplete instructions. SQL is optional evidence under [query scope](../../references/query-scope.md), with its batch and masking rules; saved profiling batch IDs are not runtime transformation parameters.
