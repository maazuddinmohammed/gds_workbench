---
name: atlas-entity-binding
description: Bind applied Logical Entities and Attributes to registered Silver targets, or Dimensional Entities and Attributes to Gold targets. Match confirmed target assignments and names, resolve ambiguities, and prepare complete local Model Binding records before Mapping.
---

# Entity binding

Binding identifies where modeled Entities and Attributes are stored. It does not define source joins, transformations or loading logic.

## Establish inputs

1. Follow the [working method](../../references/working-method.md). Reuse Tenant, working directory, Model, selected Entities and Silver/Gold context. Use applied Logical records for Silver or applied Dimensional records for Gold.
2. Require completed target Metadata registration and a fresh [Metadata Snapshot](../../references/snapshots/metadata.md) confirming its result. Read the current [Model Snapshot](../../references/snapshots/model.md) plus existing pending Bindings. Preserve drafts when a refresh needs reconciliation. Do not bind against merely proposed Metadata or unpublished modeled changes.
3. Reuse the Entity-to-schema/target assignments from [target registration](../atlas-target-registration/SKILL.md). Resolve the owner's exact configured GDS placement and check current Binding eligibility in the [Binding contract](../../references/model/binding.md). Targets are registered Silver/Gold Objects, not Source/Bronze Input Scope additions.
4. Inspect existing Binding records and follow [record state](../../references/record-state.md). Active locked model/target records may be referenced; existing Binding locks still prevent changes. Reuse the Workbench through its verified launcher. Name-based Binding requires no SQL or new SQL-policy question.
5. Resolve [existing work and update scope](../../references/working-method.md#existing-work-and-update-scope). Show existing matches plus new/missing or affected Entities/Attributes; ask the contextual scope question unless the user already selected it. Reuse valid unaffected Bindings. Scope selection does not authorize unsupported reassignment.

## Match and bind locally

1. **Resolve the target Object.** Prefer the explicit registration assignment or a still-valid existing Binding. Otherwise match the Entity name within the confirmed GDS placement, owner, target zone and schema. Use published name normalization; preserve actual registered spelling. A unique compatible exact match can proceed directly to local authoring.
2. **Resolve the target Attributes.** Match modeled names to registered names under that exact Object, using explicit registration overrides when present. Do not strip prefixes, remove punctuation, use ordinal position or accept fuzzy matches as proof. Similar names may inform a recommendation when a user decision is needed.
3. **Check compatibility and coverage.** Compare meaning, types/capacity, nullability, key/audit roles and agreed target definition. Every active modeled Attribute and every active eligible physical target Attribute needs exactly one Binding, including generated keys, foreign keys, audits and constants. Use [Binding checks](../../references/model/binding.md); names alone do not establish compatibility.
4. **Resolve only exceptions.** Use the questions below for ambiguous targets, missing records, incompatible definitions or requested reassignment. Continue independent matches. Do not alter Metadata or the modeled design, fabricate missing Attributes, unlock or reactivate records to clear a Binding failure.
5. **Write complete records.** Use the [Binding schema and examples](../../references/model/binding.md) with [Model Change Set authoring](../../references/model/change-sets.md). Save `model-change-set/model_object_binding.json` and `model_attribute_binding.json`; preserve unrelated pending work and valid existing Bindings. Include all needed Attribute Bindings alongside each proposed Object Binding. Reuse unchanged locked Bindings without editing them.
6. **Validate and hand off.** Run [local validation](../../references/local-validation.md) plus the Binding checks against the effective Model. Repair failures, show the complete Entity/Object and Attribute/column matches in Workbench, and follow the shared [Change Set lifecycle](../../references/change-set-lifecycle.md). No extra design-confirmation pause is needed for unambiguous matches; normal review and separate Apply approval still apply.
7. **Verify the result.** After verified Model Apply, refresh the Model Snapshot and confirm selected Bindings. Report bound, unchanged and unresolved Entities accurately. Stop before [Mapping](../atlas-mapping/SKILL.md); a complete partial batch does not mean every requested Entity is finished.

## Questions only when needed

| Situation | Question / behavior |
|---|---|
| Several compatible targets or columns | Show full target keys or column names: "Which should this Entity/Attribute use?" Recommend one only when existing assignment or meaning supports it. |
| Missing or extra modeled/physical columns | Show the exact differences and recommend the appropriate upstream correction: "Should we correct the model or target registration?" Do not fabricate a match or silently exclude columns. |
| Existing Binding points elsewhere | Show current/proposed targets and affected Attribute Bindings/downstream work. Resolve explicit reassignment intent and protection before changing it. |
| Inactive assignment or unavailable target | Preserve its identity; resolve intended lifecycle/upstream correction rather than creating a duplicate or silently reactivating it. |

Ask related exceptions together. Reuse prior answers; successful exact matches need no individual approval. Type spelling differences may be equivalent, but unsupported conversions or ownership/layer conflicts cannot be resolved by choosing the closest name.

## Gotchas

- Attribute Binding repeats modeled Entity type/name as its key, but gets its physical Object from the parent Binding. Do not copy a physical Object key or expression into that record.
- The current database reserves Binding target identities across inactive/deprecated history. A target that appears unused among active rows may still be occupied.
- Existing Object/Attribute reassignment needs the [Binding guide's governed-operation check](../../references/model/binding.md#existing-records-and-reassignment). Current ordinary upsert is not a verified retarget path; do not submit a guessed reassignment or let a parent change redirect locked child Bindings.
- Extra active target columns prevent complete Binding until the modeled/registered inventories are reconciled. Preserve them; do not remove them inside this workflow.
- Model Binding does not prove that DDL was executed. It binds registered Metadata; deployed-table verification is a separate concern.
- Current target ownership must equal the Model Tenant for Binding. Report a mismatch; do not replace physical GDS keys with source keys or rewrite actual ownership.
