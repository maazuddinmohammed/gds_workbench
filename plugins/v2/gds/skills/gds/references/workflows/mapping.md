# Logical or Dimensional Mapping

Require active applied Model Binding. Logical maps scoped Source/Bronze inputs to bound Silver targets; Dimensional maps eligible Silver inputs to bound Gold.

Before authoring, present the applicable Output Template code, object-level and attribute-level JSON shapes and target exceptions; wait for user confirmation. Without a template, recommend the advisory default below. One confirmation covers selected targets sharing the structure; structural changes require confirmation again. Existing explicit acknowledgement satisfies this gate in every interaction mode.

The work unit is target `model_object_binding` plus source System. Mapping transforms bound targets; never register metadata or establish Binding here. Use bounded local `select` for the Model Snapshot, `read_model_section` for live applied Binding/Mapping and `inspect_metadata` for focused physical context. Reconcile changed revisions before authoring.

Cover every active bound target Attribute through `model_attribute_binding`, including technical/constants. Preserve or author active `mapping_dependency` per modeled layer/source System with supported execution order. Keep Object order consistent. Multiple Systems may contribute to one target; Code Generation decides files.

After confirmation, follow the selected Output Template. Global advisory defaults `mapping_object_default` and `mapping_attribute_default` serve both routes. Set outer `output_template_code` only when configuration or evidence establishes it is installed; otherwise use JSON null. Snapshots list existing Mapping template codes, not installed schemas. Never invent IDs, seed populated databases or create Workflow Runs for manual plugin authoring. Preserve custom selections, locked and unaffected documents.

Default Object inner document — two required, nullable keys:

- `source_objects`: only Objects used in this target query, with `tenant_code`, `system_code`, `connection_code`, `object_schema`, `object_name`, `alias`, in that order. Use actual physical keys and unique aliases; evidenced self-joins may repeat an Object with different aliases. Resolve SQL coordinates from Metadata; do not add fields.
- `steps`: ordered natural-language query-building instructions. Specify starting Object, preparation, join order/type and exact columns/predicates, filter placement, grouping/deduplication when applicable. State inputs and resulting grain; never invent winners. Do not paste a complete SQL query or pipeline into every step. Runtime owns loading.

Default Attribute inner document — required `transformation`, optional `source_attributes`:

- `source_attributes`: nullable list of keys ordered `tenant_code`, `system_code`, `connection_code`, `object_schema`, `object_name`, `attribute_name`. No alias field. Preserve registered names here; resolve differing `fc_attribute_name` for Source SQL. Constants/generated values may omit it or use null.
- `transformation`: one field's SQL expression or precise generation rule, including casts, null/default, aggregation and invalid-value behavior. Use Object aliases; clarify self-join roles. Keep field rules here, not duplicated in Object steps.

Each step names its output: available columns, row grain, and how later stages consume it. Explain lookup failure behavior, deduplication tie handling, and value preservation only when evidence supplies that rule. Each System branch ends with the same ordered runtime input columns; state how branches combine. Account for database/framework columns using `../orchestration-rules.md`. Read `../examples/mapping-steps.md` for step-to-SQL examples when needed.

Code Generation translates Object steps into successive `CREATE OR REPLACE TEMPORARY VIEW` statements, reuses earlier views and applies Attribute rules before the final target-column SELECT. Keep template shapes/nullability unchanged. See `../examples/mapping-documents.md`; obtain outer fields from dataset schemas. Template nullability and registry `is_required` govern values/presence. Flexible storage and advisory templates still require functional review.

Before validation, trace sources to every target Attribute; reconcile storage, inferred source and bound target types, invalid-value handling, identifier formatting, decimals and timezones. Check grain, optional joins and cross-System disjoint keys or evidenced reconciliation/precedence. Deduplication needs evidenced keys/order. Reject conflicting Object/Attribute rules, missing lineage and vague instructions.

Store JSON in `mapping_transformation_document` and `attribute_mapping_transformation_document`. Resolve executable gaps before activating the affected target; never persist `needs_review`. Schema/graph validation cannot prove business correctness.
