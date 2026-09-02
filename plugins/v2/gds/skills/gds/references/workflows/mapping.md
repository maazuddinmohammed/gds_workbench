# Logical or Dimensional Mapping

Require active applied Model Binding. Logical maps scoped Source/Bronze inputs to bound Silver targets. Dimensional maps eligible Silver inputs to bound Gold targets.

Before authoring any Mapping record, present the proposed output structure and wait for user confirmation. Show the Output Template code when one applies, a concise object-level and attribute-level JSON shape, and any target-specific exceptions. When no template applies, recommend the advisory default below. One confirmation may cover every selected target that shares the structure; a later structural change requires confirmation again. This gate is required in every interaction mode.

The work unit is target `model_object_binding` plus source System. Mapping is target-oriented and describes transformations for already-bound targets; it never registers metadata or establishes Binding. Use `read_model_section` for applied Binding/Mapping and `inspect_metadata` for focused physical context.

For every selected unit, cover all required target Attributes through `model_attribute_binding`, preserve source lineage, joins, filters, expressions, write behavior, and dependency order, and report conflicts. Multiple Systems may map into one target. File grouping belongs to Code Generation, not Mapping.

After confirmation, follow the selected Output Template as authoring guidance. Otherwise use the confirmed advisory default:

```json
{"schema_version":"1.0","sources":[],"steps":[],"write":{"mode":null,"natural_keys":[]},"dependencies":[],"notes":null}
```

Store object-level JSON in `mapping_transformation_document` and attribute-level JSON in `attribute_mapping_transformation_document`. The documents may evolve when the task requires it. JSON storage is flexible; never invent executable lineage or persist unresolved behavior as `needs_review`.
