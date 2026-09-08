# Logical or Dimensional Mapping

Require active applied Model Binding. Logical maps scoped Source/Bronze inputs to bound Silver targets. Dimensional maps eligible Silver inputs to bound Gold targets.

Before authoring Mapping, present its output structure and wait for user confirmation: applicable Output Template code, object-level and attribute-level JSON shapes, and target-specific exceptions. Without a template, recommend the advisory default below. One confirmation covers selected targets sharing the structure; structural changes require confirmation again. Existing explicit acknowledgement satisfies this gate; do not ask again. This applies in every interaction mode.

The work unit is target `model_object_binding` plus source System. Mapping transforms already-bound targets; it never registers metadata or establishes Binding. Use bounded local `select` for the Model Snapshot. `read_model_section` reads live applied Binding/Mapping; `inspect_metadata` reads focused physical context. Reconcile Snapshot freshness before authoring; never mix revisions silently.

For every selected unit, cover every active bound target Attribute through `model_attribute_binding`, including technical and constant fields. Read/preserve or author an active `mapping_dependency` for each modeled layer/source System and its supported execution order. Keep object dependency order consistent. Multiple Systems may map into one target. File grouping belongs to Code Generation, not Mapping.

After confirmation, follow the selected Output Template. Global advisory defaults `mapping_object_default` and `mapping_attribute_default` serve both Mapping routes. Without a custom selection, use these document shapes. Set outer `output_template_code` to the default code only when configuration or evidence establishes it is installed; otherwise use JSON null. The Model Snapshot lists existing Mapping template codes, not installed template schemas. Never assume older databases contain these defaults. Governed Apply resolves codes; never invent template IDs, seed populated databases, or create Workflow Runs for manual plugin authoring. Preserve confirmed custom selections and existing documents; never rewrite locked or unaffected records merely to adopt defaults.

The default Object inner document has two required keys, each permitting JSON null:

- `source_objects`: list of complete actual physical keys and unique aliases. Each entry contains `tenant_code`, `system_code`, `connection_code`, `object_schema`, `object_name`, `alias`, in that order. Resolve SQL coordinates from Metadata and use them in the steps; do not add a `sql_relation` field. The same Object may have different aliases for an evidenced self-join.
- `steps`: ordered list of implementable Object transformation instructions. Include applicable joins and exact predicates, filters, grouping, deduplication, dependency and write behavior. Array order is execution order. State evidenced grain and key behavior here when needed; there is no separate grain field. Do not invent a winning row or an unsupported rule.

The default Attribute inner document has required `transformation` and optional `source_attributes`:

- `source_attributes`: optional nullable list of complete physical Attribute keys, ordered `tenant_code`, `system_code`, `connection_code`, `object_schema`, `object_name`, `attribute_name`. Keep registered Attribute names here; Source SQL uses `fc_attribute_name` when it differs. There is no alias field. A constant or generated value may omit the list or use JSON null.
- `transformation`: required SQL expression or precise implementable generation rule. Include needed cast, null/default, aggregation and invalid-value behavior. Use Object aliases and clarify self-join source roles here. There is no separate description field.

Template guidance defines nullability; registry `is_required` controls field presence. Flexible storage and advisory templates still require functional review.

See `../examples/mapping-documents.md` for object/direct/derived/constant inner documents. Obtain outer fields from each dataset schema. Confirmed templates may organize the same decisions differently.

Before local validation, trace every draft source to each target Attribute. Reconcile storage, inferred source and bound target types; check invalid-value handling, identifier formatting, exact decimals and timezones. Verify joins preserve grain and optional relationships. Multiple Systems require disjoint target keys or evidenced identity reconciliation and precedence. Deduplication requires evidenced keys/order, never invented winners. Reject conflicting object/attribute logic, missing lineage and vague “populate from source” instructions.

Store object-level JSON in `mapping_transformation_document` and attribute-level JSON in `attribute_mapping_transformation_document`. Unresolved executable behavior blocks the affected target; report the missing decision and resolve it before marking the Mapping active. Never persist it as `needs_review`. Schema/graph validation does not prove business correctness.
