# Dimensional records

Owns the three Dimensional dataset contracts, the read-only fact type list and nested source fields. Use [dimensional design](../dimensional-build/design.md) for modeling decisions, [naming](naming.md) and [keys and audit columns](keys-and-audit.md) for policy. [Project Change Sets](change-sets.md), [record state](../record-state.md) and [local validation](../local-validation.md) own shared mechanics.

## Files, identity and common values

Write complete changed records as JSON arrays under `project-change-set/<dataset>.json`. No section wrappers, internal numeric database IDs (including Project IDs), SQL, batch bindings or invented policy fields. Context source references require the portable `context_record_id` UUID; preserve that identity. Preserve nested arrays when editing.

| Dataset | Natural key within the Project |
|---|---|
| `dimensional_fact_type` | `dimensional_fact_type_code`; read-only list, never in a Change Set |
| `dimensional_entity` | `dimensional_entity_schema_name` + `dimensional_entity_name` |
| `dimensional_attribute` | `dimensional_entity_schema_name` + `dimensional_entity_name` + `dimensional_attribute_name` |
| `dimensional_relationship` | The child's foreign key: `from_dimensional_entity_schema_name` + `from_dimensional_entity_name` + `from_dimensional_attribute_name` |

Use shared normalization and preserve existing spelling. Below, **name** is a nonblank string ≤255 characters and **text** is a nonblank string. Lifecycle is a boolean `*_is_active`: retire a record by setting it to `false`, never by deleting or omitting it. All dataset fields are required, including nullable fields, except the Relationship's role and basis, which default to null; include them explicitly in complete authored records.

## Fact type list

`dimensional_fact_type` holds `dimensional_fact_type_code`, `dimensional_fact_type_description` and `dimensional_fact_type_is_active`. It is a read-only reference list: choose an active code for each fact; never author or stage it. Current codes are `transaction`, `periodic_snapshot`, `accumulating_snapshot` and `factless`, but the installed list decides. A retired code stays valid on unchanged records; new or changed facts need an active one.

## Dimensional Entity fields

| Field | Accepted value / meaning |
|---|---|
| `dimensional_entity_schema_name` | Required configured Dimensional schema name; part of Entity identity. |
| `dimensional_entity_name` | Name; Entity identity. |
| `dimensional_entity_definition` | Text defining the business meaning. |
| `dimensional_entity_type` | `fact`, `dimension` or `bridge`. |
| `dimensional_fact_type` | Facts: an active `dimensional_fact_type_code`. Other Entity types: null. |
| `dimensional_entity_grain_definition` | Text defining one row; required non-null for facts/bridges. Dimensions permit null in the schema; provide explicit grain for a complete design. |
| `dimensional_entity_dependency_order` | Integer ≥0; modeled dependency order, not Process Group scheduling. |
| `dimensional_entity_is_active` | Boolean; `false` retires the Entity. |
| `dimensional_entity_is_locked` | Boolean. |
| `sources` | Array of Entity/Logical Entity or Entity/Context sources below; `[]` is valid. |

## Dimensional Attribute fields

| Field | Accepted value / meaning |
|---|---|
| `dimensional_entity_schema_name` | Required configured Dimensional schema name; part of Entity identity. |
| `dimensional_entity_name` | Name of the parent Dimensional Entity. |
| `dimensional_attribute_name` | Name; Attribute identity within its Entity. |
| `dimensional_attribute_definition` | Text defining meaning, units and relevant behavior. |
| `dimensional_attribute_data_type` | Nonblank string ≤100 characters; approved modeled type, not a fixed schema enum. |
| `dimensional_attribute_is_nullable` | Boolean; whether null is allowed. On a foreign key it also makes the Relationship optional. |
| `dimensional_attribute_is_natural_key` | Boolean; participates in the complete business-key tuple. |
| `dimensional_attribute_is_surrogate_key` | Boolean; generated own-row identifier. |
| `dimensional_attribute_ordinal_position` | Integer >0; column position. |
| `dimensional_attribute_is_audit_column` | Boolean; identifies approved audit columns. |
| `dimensional_attribute_is_active` | Boolean; `false` retires the Attribute. |
| `dimensional_attribute_is_locked` | Boolean. |
| `sources` | Array of Logical Attribute or Context sources below; `[]` is valid. |

Natural and surrogate flags are mutually exclusive; either requires non-nullability. Multiple natural-key Attributes describe a complete business-key tuple. A generated surrogate does not by itself establish business grain. Foreign-key participation comes from effective relationships; technical and audit fields follow the configured Project templates. Explain measure meaning, units, aggregation rules, grain participation and allocation semantics in the Attribute definition. History follows the Project's `dimensional_entity_scd_type`; no per-Attribute history choice exists.

## Dimensional Relationship fields

A Relationship points child -> parent: from a fact, bridge or outrigger foreign-key Attribute to the dimension's key, normally its surrogate. One foreign-key Attribute has one dimension, so the from endpoint alone identifies the record; there is no name, definition, kind, cardinality or optionality field.

| Field | Accepted value / meaning |
|---|---|
| `from_dimensional_entity_schema_name` | Child Entity's configured Dimensional schema. |
| `from_dimensional_entity_name` | Child fact, bridge or outrigger dimension. |
| `from_dimensional_attribute_name` | The child's foreign-key Attribute. |
| `to_dimensional_entity_schema_name` | Parent dimension's configured Dimensional schema. |
| `to_dimensional_entity_name` | Parent dimension. |
| `to_dimensional_attribute_name` | The dimension's key Attribute, normally its surrogate. |
| `dimensional_relationship_role_name` | Name or null. Set it only for a role-playing dimension, such as OrderDate versus ShipDate on one Date dimension. |
| `dimensional_relationship_basis` | Text or null. Write it when the link does not follow a Logical Relationship or needs a complete composite/history predicate explained. |
| `dimensional_relationship_is_active` | Boolean; `false` retires the Relationship. |
| `dimensional_relationship_is_locked` | Boolean. |

Kind, optionality and cardinality are worked out, never stored: every Relationship is many-to-one; the kind follows the Entity types (fact to dimension, bridge to dimension, dimension to dimension as an outrigger); it is optional when the foreign-key Attribute is nullable. Same-Entity relationships are allowed when Attributes differ; identical normalized endpoints are rejected. A one-column edge alone cannot encode a composite join or history predicate. SQL is not required for supported inference.

## Nested sources

Each source variant contains its one matching source field plus the common fields. `rationale` defaults to null; include it explicitly in complete authored records. Every other field is required.

| Field | Accepted value / meaning |
|---|---|
| `support_source_type` | Entity: `logical_entity` or `context_record`. Attribute: `logical_attribute` or `context_record`. Names the source field that follows. |
| `source_logical_entity` | Only Logical Entity variant: schema-qualified Logical Entity key below. |
| `source_logical_attribute` | Only Logical Attribute variant: schema-qualified Logical Attribute key below. |
| `context_record` | Only Context variant: object containing `context_record_id`. |
| `rationale` | Text explaining the contribution, or null when the source needs no explanation. |
| `is_active` | Boolean; `false` retires the source. |
| `is_locked` | Boolean; independent nested source lock. |

Logical Entity key: `logical_entity_schema_name` (nonblank string ≤400) and `logical_entity_name` (name). Logical Attribute key adds `logical_attribute_name` (name). Context identity is a stable lowercase UUID; see [Context records](context.md).

Sources refer directly to the current Project's applied Logical design. Target registration and Logical Mapping are separate downstream readiness concerns.

Within one parent, each source type + normalized Logical/Context key is unique. Describe each source's complete contribution once in its rationale. Source arrays record provenance, not transformation SQL, join aliases or an order of precedence.

## Scope and current enforcement

- New/changed Logical sources must belong to the current Project and resolve by schema/name. Active support requires active Logical Entities and Attributes.
- An Attribute's Logical source requires matching Logical Entity support on its parent Dimensional Entity.
- Context records must exist and be relevant to the dimensional design. Follow shared evidence/state rules; an Attribute's Context does not require a duplicate Context source on its Entity.
- Empty sources are valid. Generated calendars, constants and other justified standalone structures need no fake source or compulsory Context. Explain their generation/business meaning; attach a real applicable Context only when useful.
- A new or changed fact's `dimensional_fact_type` must be an active code; validation reports `reference_code_invalid` otherwise. An active Relationship's to Attribute must be a natural or surrogate key of the dimension; validation reports `relationship_target_not_key` otherwise.
- Attributes require real parents; active Attributes require active Entities. Active relationships require active endpoint Attributes and Entities. As in the web workflow, retiring an Entity retires its active Attributes and the Relationships that use them in the same batch, and retiring a fact or bridge Relationship retires its foreign-key Attribute.
- Preserve locked records and nested sources. Apply retains omitted nested sources; preserve complete arrays so the local effective graph represents what will remain.
- The workflow starts from applied Logical Entities and Attributes. A Dimensional Entity belongs to the Subject Areas of its Logical sources; areas only choose which Logical Entities a Build reads and are never evidence. Physical registration and Logical Mapping are not prerequisites for Dimensional design.

## Additional Atlas checks and unresolved capabilities

These are design/local-validation requirements; current record-schema validation alone does not prove them.

| Check | Why it matters |
|---|---|
| One own generated BIGINT surrogate first; approved key naming, nullability and audit policy | Key flags alone do not enforce the complete layout. |
| Unique active ordinals and complete target columns | Positive ordinals alone permit duplicate positions and missing columns. |
| Complete business key, row grain and compatible key types | Flags/edge existence cannot prove identity or correct joins. |
| Measure meaning, additivity and aggregation at the stated grain | Definitions must explain valid totals and prevent double-counting. |
| Applicable sources resolve to usable records | Reference existence is weaker than active evidence. |
| Relationships point at the dimension's key and preserve grain, including complete composite/history predicates | Each record has only one Attribute per endpoint. |
| History behavior has an executable consumer contract before Mapping/code | A Project Type 2 setting does not prove that the framework implements loading. |

Entity/Attribute records have no dedicated SCD type, effective-date, current-row, unknown-member, late-arrival, allocation or bridge-policy fields. The Project supplies `dimensional_entity_scd_type` for dimensions; facts and bridges do not inherit dimension history. Use approved modeled technical Attributes/templates plus concise definitions/bases; do not invent payload fields or assume generic `IsActive` implements history. The user confirms Type 1/Type 2 support and framework population of the configured Type 2 fields using natural keys; [history rules](../dimensional-build/history.md) own this population contract.

## Complete synthetic records

These examples illustrate record shapes, not a complete new table build. Assume complete existing Customer/SalesLine graphs, configured keys/audits and active Logical contributions where referenced. New tables must include all columns from [keys and audit columns](keys-and-audit.md).

`project-change-set/dimensional_entity.json`:

```json
[
  {
    "dimensional_entity_schema_name": "gold", "dimensional_entity_name": "SalesLine",
    "dimensional_entity_definition": "A completed sale line available for product and customer analysis.",
    "dimensional_entity_type": "fact",
    "dimensional_fact_type": "transaction",
    "dimensional_entity_grain_definition": "One completed order line within its originating System.",
    "dimensional_entity_dependency_order": 1,
    "dimensional_entity_is_active": true,
    "dimensional_entity_is_locked": false,
    "sources": [{"support_source_type":"logical_entity","source_logical_entity":{"logical_entity_schema_name":"silver","logical_entity_name":"OrderLine"},"rationale":"Synthetic completed order lines supply the fact grain and line measures.","is_active":true,"is_locked":false}]
  }
]
```

`project-change-set/dimensional_attribute.json`; assumes its Logical Entity source above and existing preceding Attributes:

```json
[
  {
    "dimensional_entity_schema_name": "gold", "dimensional_entity_name": "SalesLine",
    "dimensional_attribute_name": "Quantity",
    "dimensional_attribute_definition": "Number of units sold on this completed order line, in the governed common unit. SUM is valid across associated dimensions because sale lines are disjoint.",
    "dimensional_attribute_data_type": "DECIMAL(18,4)",
    "dimensional_attribute_is_nullable": false,
    "dimensional_attribute_is_natural_key": false,
    "dimensional_attribute_is_surrogate_key": false,
    "dimensional_attribute_ordinal_position": 5,
    "dimensional_attribute_is_audit_column": false,
    "dimensional_attribute_is_active": true,
    "dimensional_attribute_is_locked": false,
    "sources": [{"support_source_type":"logical_attribute","source_logical_attribute":{"logical_entity_schema_name":"silver","logical_entity_name":"OrderLine","logical_attribute_name":"Quantity"},"rationale":null,"is_active":true,"is_locked":false}]
  }
]
```

`project-change-set/dimensional_relationship.json`; assumes active `SalesLine.OrderDateKey` and `SalesLine.ShipDateKey` (non-nullable foreign keys) and `Date.DateKey`, so one Date dimension plays two roles:

```json
[
  {
    "from_dimensional_entity_schema_name": "gold", "from_dimensional_entity_name": "SalesLine",
    "from_dimensional_attribute_name": "OrderDateKey",
    "to_dimensional_entity_schema_name": "gold", "to_dimensional_entity_name": "Date",
    "to_dimensional_attribute_name": "DateKey",
    "dimensional_relationship_role_name": "OrderDate",
    "dimensional_relationship_basis": null,
    "dimensional_relationship_is_active": true,
    "dimensional_relationship_is_locked": false
  },
  {
    "from_dimensional_entity_schema_name": "gold", "from_dimensional_entity_name": "SalesLine",
    "from_dimensional_attribute_name": "ShipDateKey",
    "to_dimensional_entity_schema_name": "gold", "to_dimensional_entity_name": "Date",
    "to_dimensional_attribute_name": "DateKey",
    "dimensional_relationship_role_name": "ShipDate",
    "dimensional_relationship_basis": "Ship date has no Logical Relationship; the Logical OrderLine ShipDate value is looked up in the calendar.",
    "dimensional_relationship_is_active": true,
    "dimensional_relationship_is_locked": false
  }
]
```

`OrderDate` and `ShipDate` are illustrative role names, not enforced vocabulary or defaults.
