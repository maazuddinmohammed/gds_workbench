# Model datasets

Model Snapshot v2 contains eight Sections and 19 ID-free datasets. The JSON Schema
returned by `describe_model_dataset` is authoritative for current fields, required
nullable values, nested discriminators, types, patterns, and enums. Every staged
record is a complete record, never a patch.

## Registry and canonical keys

| Section | Dataset | Canonical key | Purpose |
|---|---|---|---|
| model_scope | `model_details` | singleton (`[]`) | Model name, description, and five naming/audit templates. |
| model_scope | `model_scope` | tenant + system + connection + schema + object | Active physical Object scope and lock state. |
| profiling | `profiling_profile` | physical Attribute key | Counts, lengths, and percentages used as source evidence. |
| analysis | `analysis_result` | from Attribute + to Attribute + relationship kind | Analyzed source relationship evidence. |
| assertion | `modeling_assertion_document` | document name | Assertion document identity and metadata. |
| assertion | `modeling_assertion_record` | stable assertion key | One sourced modeling statement and applicable layers. |
| conceptual | `conceptual_object` | object name | Business concept, definition, type, grain, aliases, and support. |
| conceptual | `conceptual_relationship` | from object + to object + relationship name | Business relationship and cardinality evidence. |
| logical | `logical_submodel` | submodel name | Logical grouping. |
| logical | `logical_entity` | entity name | Entity, grain, type, memberships, and sources. |
| logical | `logical_attribute` | entity + attribute | Attribute data type, nullability, keys, ordinal, and sources. |
| logical | `logical_relationship` | from entity/attribute + to entity/attribute + name | Attribute-level relationship and cardinality. |
| dimensional | `dimensional_submodel` | submodel name | Dimensional grouping or business process. |
| dimensional | `dimensional_entity` | entity name | Fact, dimension, or bridge, with fact type and grain. |
| dimensional | `dimensional_attribute` | entity + attribute | Key, descriptor, measure, degenerate, weight, technical, or audit field. |
| dimensional | `dimensional_relationship` | endpoints + kind + nullable role | Fact/dimension/bridge relationship and role. |
| mapping | `mapping_dependency` | modeled entity type + source system | Load dependency order for a source system. |
| mapping | `mapping_object` | physical Object + source system + modeled type/name | Object-level source-to-model mapping and optional authored artifact bundle. |
| mapping | `mapping_attribute` | physical Attribute + source system + modeled type/name/attribute | Attribute-level transformation mapping. |

Physical Object keys are `tenant_code`, `system_code`, `connection_code`,
`object_schema`, `object_name`; Attribute keys add `attribute_name`. Model key
comparison trims ASCII U+0020 at both ends of every string and compares with
Unicode case folding. The browser can only approximate full Unicode case folding,
so server validation remains authoritative.

`model_details` is the only empty-key singleton. A future graph must contain exactly
one. All other canonical-key components must be present and nonblank where textual.

## Shared lifecycle and evidence

- Top-level modeled status is `active`, `needs_review`, `inactive`, or
  `deprecated`; confidence is `low`, `medium`, or `high`.
- Cardinality is `one_to_one`, `one_to_many`, `many_to_one`, or `many_to_many`;
  Conceptual relationships also allow `unknown`.
- Locked applied records and matching locked nested memberships, supports, or
  sources cannot be changed.
- Conceptual support and Logical/Dimensional sources are discriminated nested
  objects referencing either physical scope or Modeling Assertions. Use the exact
  nested schema; do not flatten them.
- Omitted staged datasets and omitted applied records remain in the future graph.
  An empty staged list clears that pending dataset only; it does not delete applied
  rows.
- To retire a record, stage its same canonical key with `is_active=false`, or with
  status `inactive`/`deprecated`, according to its schema. Changing a key inserts a
  distinct record and does not retire the old key.

## Important record rules

- `model_details`: silver templates are an all-or-none pair; gold templates are an
  all-or-none triple. Each template is at most 256 KiB.
- `profiling_profile`: non-null + null count equals row count; blank/distinct counts
  cannot exceed non-null; minimum length cannot exceed maximum; percentages are
  0–100.
- Relationship endpoints must differ. Model validation checks every referenced
  object, attribute, submodel, assertion, source, and mapping target in the complete
  future graph.
- Logical entity type is one of core, reference, transaction, event, bridge,
  history, snapshot, association, aggregate, or other. The
  `logical_entity_type_detail` property is always required and nullable: it must be
  non-null exactly when `logical_entity_type` is other.
- Logical attributes cannot be both natural and surrogate keys. Any key flag makes
  the attribute non-nullable.
- Dimensional entity type is fact, dimension, or bridge. The nullable
  `dimensional_fact_type` and `dimensional_entity_grain_definition` properties are
  always required. `dimensional_fact_type` is non-null exactly when
  `dimensional_entity_type` is fact and is transaction, periodic snapshot,
  accumulating snapshot, or factless. Facts and bridges require a non-null explicit
  grain.
- Dimensional attribute role is key, descriptor, measure, degenerate dimension,
  bridge weight, technical, or audit. Measures require additivity and default
  aggregation; semi/non-additive measures require an aggregation basis. Non-measures
  leave measure-only fields null. Audit status and audit role must agree.
- `mapping_object`'s six authored properties are always required and nullable; their
  values are all null or all non-null. Artifact type is SQL file, Python file, or
  Python notebook. A transformation document requires only `schema_version="1.0"`
  and kind direct/derived at object level.
- The `mapping_attribute` transformation property is required and nullable. A
  non-null transformation document requires
  `schema_version="1.0"` and kind direct/expression. Do not invent an undocumented
  package schema.

Generated JSON Schema does not encode every cross-field, byte-size, lock, scope, or
cross-dataset rule. Offline validation is an early check; only
`validate_model_change_set` proves the server future graph is valid.

## Reference graph

Model Scope must resolve to visible physical catalog objects. Profiling and analysis
Attributes must be active in that scope. Assertion records reference their document.
Conceptual relationships reference both objects. Logical/Dimensional memberships
reference submodels; Attributes reference Entities; Relationships reference both
Attributes. Assertion evidence must declare the target applicable layer. Model
Mapping must reference an active source system, matching dependency, active physical
Object/Attribute, the declared modeled Entity/Attribute, and an exact parent
`mapping_object` for every `mapping_attribute`.

## Snapshot archive

An authoritative Model Snapshot uses this verified archive shape:

```text
model-snapshot/
├── manifest.json
├── catalog.json
├── schemas/model/<dataset>.schema.json
└── data/<section>/<dataset>/rows.jsonl
```

It has no metadata-style lookup/search files. The archive is limited to 20,000 rows
per dataset and 50,000 total rows. A Workbench export named
`proposed-model-snapshot.json` is a local aggregate proposal, not this immutable
archive; it must keep the baseline Model revision and be validated on the server
through a Change Set.
