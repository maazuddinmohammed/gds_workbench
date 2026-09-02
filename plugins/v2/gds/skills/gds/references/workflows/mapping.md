# Logical or Dimensional Mapping

Require active applied Model Binding. Logical maps scoped Source/Bronze inputs to bound Silver targets. Dimensional maps eligible Silver inputs to bound Gold targets.

The work unit is target `model_object_binding` plus source System. Mapping is target-oriented and describes transformations for already-bound targets; it never registers metadata or establishes Binding. Use `read_model_section` for applied Binding/Mapping and `inspect_metadata` for focused physical context.

For every selected unit, cover all required target Attributes through `model_attribute_binding`, preserve source lineage, joins, filters, expressions, write behavior, and dependency order, and report conflicts. Multiple Systems may map into one target. File grouping belongs to Code Generation, not Mapping.

If an Output Template exists, follow it as authoring guidance. Otherwise use this advisory default:

```json
{"schema_version":"1.0","sources":[],"steps":[],"write":{"mode":null,"natural_keys":[]},"dependencies":[],"notes":null}
```

Store object-level JSON in `mapping_transformation_document` and attribute-level JSON in `attribute_mapping_transformation_document`. The documents may evolve when the task requires it. JSON storage is flexible; never invent executable lineage or persist unresolved behavior as `needs_review`.
