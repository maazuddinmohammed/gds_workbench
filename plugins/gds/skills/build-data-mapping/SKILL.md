---
name: build-data-mapping
description: "Build or revise governed GDS source-to-model mappings from physical metadata, existing model lineage, and transformation decisions. Use for source-to-target mapping, mapping matrices, lineage extraction, Logical or Dimensional mappings, dependency order, or exact mapping Model Change Set records."
---

# Build Data Mapping

Build traceable Object- and Attribute-grain Model Mapping records. Follow the shared
[Model authoring workflow](../../references/model-authoring-workflow.md). Read the
[modeling method](../../references/modeling-method.md) only for full-layer design,
method ambiguity, or a requested stress test. Read [model datasets](../../references/model-datasets.md)
for exact keys and [model tools](../../references/model-tools.md) around unfamiliar
calls only when needed.
Use `get_model_mapping_dependencies`, `get_model_object_mappings`, and
`get_model_attribute_mappings` for focused current-state reads.

## Select and derive

Use Model Mapping for physical sources mapped to Logical or Dimensional Entities:
`mapping_dependency → mapping_object → mapping_attribute`. Use
`$manage-gds-metadata` for physical Source-to-Bronze/Silver/Gold ingestion mappings.

Derive candidates from exact nested model sources before asking for a manual matrix.
Object sources can identify Object mappings; Attribute sources require their exact
parent Object mapping. Assertion-only support does not identify a physical source.
Preserve separate canonical mappings for multiple sources.

Check requested mappings for exact source/target identity, active Model Scope,
dependency order, target grain/key rules, transformation choices, and unmapped items.
Do not claim transformation text was executed or proved by sample data.

## Author

Describe only mapping datasets being authored. Include `mapping_dependency` or
`mapping_object` with an Attribute mapping only when that required parent is missing or
changed. Existing parents are read dependencies, not affected datasets. Extraction
requests stop after focused reads.

Draft complete, ID-free records. Keep Object artifact/package/transformation fields in
their required all-null or all-present group. An Attribute mapping must have an exact
parent Object mapping and existing modeled target. Check scope, dependencies, source
and target keys, transformation completeness, and unmapped items. Then stop at the
boundary selected by the shared workflow.
