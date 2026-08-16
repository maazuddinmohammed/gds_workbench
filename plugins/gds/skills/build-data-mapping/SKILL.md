---
name: build-data-mapping
description: "Build or revise governed GDS source-to-model mappings from physical metadata, existing model lineage, and transformation decisions. Use for source-to-target mapping, mapping matrices, lineage extraction, Logical or Dimensional mappings, dependency order, or exact mapping Model Change Set records."
---

# Build Data Mapping

Create traceable Object- and Attribute-grain Model Mapping records without confusing
them with physical ingestion lineage.

Read these only when needed:

- [modeling method](../../references/modeling-method.md) for mapping quality checks;
- [model datasets](../../references/model-datasets.md) for exact mapping keys/rules;
- [model tools](../../references/model-tools.md) for both mapping families; and
- [governed workflow](../../references/governed-model-workflow.md) before a write.

## Select the mapping family

Use Model Mapping when a physical source maps to a Logical or Dimensional Entity:

```text
mapping_dependency → mapping_object → mapping_attribute
```

Use the existing `$manage-gds-metadata` workflow instead when mapping physical Source
objects to Bronze/Silver/Gold targets through `ingestion_object_mapping` and
`ingestion_attribute_mapping`. Never substitute one family for the other.

## Derive the baseline

Use `get_model` to select the existing Model. Read its scope and existing mapping
dependencies, Object mappings, and Attribute mappings. Read the target Logical or
Dimensional Entities/Attributes and the minimum physical catalog, profiling,
analysis, lineage, or Assertion evidence required.

Prefer existing source metadata and model records. When they are incomplete, ask for
the source system/Object/Attribute, target type/name/Attribute, joins, filters,
transformations, keys, defaults/null behavior, dependency order, data-quality rules,
artifact expectations, owner, and acceptance checks. Never put raw source row values,
credentials, or connection strings into records or reports.

## Derive mapping candidates from model sources

When the Logical or Dimensional model already carries nested source records, derive
candidates deterministically before asking for a manual matrix:

1. Each Entity source with `support_source_type="object"` yields one candidate
   `mapping_object` from its exact `source_object` key to that Entity.
2. Each Attribute source with `support_source_type="attribute"` yields one candidate
   `mapping_attribute` from its exact `source_attribute` key to that Attribute. It
   also requires an exact parent `mapping_object` for the source Attribute's Object
   and the same modeled Entity.
3. Create one `mapping_dependency` candidate for each distinct
   `(modeled_entity_type, source_system_code)` pair. Use the physical `system_code` as
   `source_system_code` only when that matches the Model's established source-system
   convention; otherwise preserve the existing convention or ask.
4. Assertion-only sources do not identify a physical mapping. Keep their evidence,
   but require an explicit physical Object/Attribute choice before creating a mapping.
5. Preserve multiple physical sources as separate canonical mappings; do not collapse
   them into one record.

Compare every candidate with current `mapping_dependency`, `mapping_object`, and
`mapping_attribute` records by their canonical keys. Classify it as existing,
changed, missing, conflicting, or unsupported before proposing records.

## Draft at two grains

For each source system and target layer, create one `mapping_dependency` with the
approved load order.

For each Object mapping, use the exact physical Object key, source system, modeled
Entity type/name, Object dependency order, lifecycle, and lock state. The six authored
artifact/package/transformation fields must be all null or all present. Do not invent
a package-document schema beyond the live record schema. Object transformation kind
is direct or derived.

For each Attribute mapping, use the exact physical Attribute key and the same source
system and modeled Entity identity as its parent Object mapping. Target an existing
modeled Attribute. A non-null transformation document uses kind direct or expression.
Record detailed joins, filters, casts, defaults, key handling, and quality rules only
inside fields permitted by the exact live schema.

Check that every Attribute mapping has an exact parent Object mapping, every target
exists in the declared Logical/Dimensional layer, every source is active in Model
Scope, every dependency exists, and the mapping preserves target grain and key rules.

## Review and govern

Call `describe_model_dataset` for all three mapping datasets and draft complete,
ID-free records with required nullable fields. Present a compact mapping matrix plus
unmapped sources/targets, dependency order, transformation choices, data-quality
rules, assumptions, canonical-key effects, and local validation. Do not claim a
transformation description was executed or proved by sample data.

For an extraction/report request, stop without writing. For a proposal, return the
checked matrix and records. For a server draft or applied mapping, follow the governed
workflow: reconcile resumed pending records, Stage complete lists, Validate the future
graph, show the authoritative action review, and obtain fresh explicit approval
immediately before Apply. Verify with fresh mapping reads and release the lock.

## Completion check

Report mapping family, selected Model/layer, source and target coverage, unmapped
items, dependencies, transformation/data-quality decisions, affected datasets,
validation/apply state, verified revision, and open issues. Missing target grain,
source identity, or transformation ownership prevents completion.
