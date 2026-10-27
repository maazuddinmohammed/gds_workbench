# Logical records

Owns the three Logical dataset contracts, the read-only Entity type list and their nested source fields. Use [logical design](../logical-build/logical-design.md) for modeling decisions, [normalization](../logical-build/normalization.md) for splits/consolidation, [naming](naming.md) and [keys and audit columns](keys-and-audit.md) for policy. [Project Change Set authoring](change-sets.md), [record state](../record-state.md) and [local validation](../local-validation.md) own the shared mechanics.

## Files, identity and common values

Write complete changed records as JSON arrays under `project-change-set/<dataset>.json`. No section wrapper, internal numeric database IDs (including Project IDs), SQL, batch bindings or invented fields. Context source references require the portable `context_record_id` UUID; preserve that identity. Preserve nested arrays when editing; local upsert does not make a field-level patch.

| Dataset | Natural key within the Project |
|---|---|
| `logical_entity_type` | `logical_entity_type_code`; read-only list, never in a Change Set |
| `logical_entity` | `logical_entity_schema_name` + `logical_entity_name` |
| `logical_attribute` | `logical_entity_schema_name` + `logical_entity_name` + `logical_attribute_name` |
| `logical_relationship` | The child's foreign key: `from_logical_entity_schema_name` + `from_logical_entity_name` + `from_logical_attribute_name` |

Use shared key normalization; preserve existing spelling. Below, **name** means nonblank string ≤255 characters and **text** means nonblank string. Lifecycle is a boolean `*_is_active`: retire a record by setting it to `false`, never by deleting or omitting it. All dataset fields are required, even when nullable.

## Entity type list

`logical_entity_type` holds `logical_entity_type_code`, `logical_entity_type_description` and `logical_entity_type_is_active`. It is a read-only reference list: read it from the Project Snapshot and choose an active code; never author or stage it. Current codes are `core`, `reference`, `transaction`, `transaction_line`, `event`, `association`, `history`, `snapshot`, `agreement`, `plan`, `hierarchy`, `subtype`, `list` and `other` (only when no listed type fits; the definition says what it is), but the installed list decides. A retired code stays valid on unchanged records; new or changed records need an active one.

## Logical Entity fields

Read `project_details.logical_entity_scd_type` from the current Snapshot:
`type_1` requests overwrite semantics; `type_2` requests versioned history;
null leaves the choice unspecified. Configure it in web Project settings; it is
read-only in Project Change Sets. Use the choice to guide grain, keys and history
Attributes with the recorded audit policy and available evidence. Do not invent
history-column names or mutate locked Entities to satisfy it. A settings change
does not rewrite existing Entities or migrate data.

| Field | Accepted value / meaning |
|---|---|
| `logical_entity_schema_name` | Required configured Logical schema name; part of Entity identity. |
| `logical_entity_name` | Name; Entity identity. |
| `logical_entity_definition` | Text defining the business meaning. |
| `logical_entity_type` | An active `logical_entity_type_code`. There is no free-text type detail; a many-to-many link is an `association` Entity. |
| `logical_entity_grain` | Text explaining one row's business occurrence. |
| `logical_entity_dependency_order` | Integer ≥0; modeled Entity dependency order, not Process Group scheduling. |
| `logical_entity_is_active` | Boolean; `false` retires the Entity. |
| `logical_entity_is_locked` | Boolean. |
| `sources` | Array of Object or Context sources below; `[]` is schema-valid. |

## Logical Attribute fields

| Field | Accepted value / meaning |
|---|---|
| `logical_entity_schema_name` | Required configured Logical schema name; part of Entity identity. |
| `logical_entity_name` | Name of the parent Logical Entity. |
| `logical_attribute_name` | Name; Attribute identity within its Entity. |
| `logical_attribute_definition` | Text defining the Attribute, including useful units/semantics. |
| `logical_attribute_data_type` | Nonblank string ≤100 characters; approved modeled type, not a fixed schema enum. |
| `logical_attribute_is_nullable` | Boolean; whether null is allowed. |
| `logical_attribute_is_natural_key` | Boolean; membership in business identity, possibly a composite tuple. |
| `logical_attribute_is_surrogate_key` | Boolean; marks this Entity's surrogate, not every foreign-key Attribute. |
| `logical_attribute_ordinal_position` | Integer >0; column position. |
| `logical_attribute_is_audit_column` | Boolean; classification under the approved audit policy. |
| `logical_attribute_is_active` | Boolean; `false` retires the Attribute. |
| `logical_attribute_is_locked` | Boolean. |
| `sources` | Array of physical Attribute or Context sources below; `[]` is schema-valid. |

An Attribute cannot be both natural and surrogate key. Any natural/surrogate flag requires `logical_attribute_is_nullable:false`. Naming, first-column surrogate policy, type compatibility and audit order are defined in their policy guides; these flags alone do not enforce them. Multiple natural-key flags describe a tuple, not independent uniqueness of every component.

## Logical Relationship fields

A Relationship points child -> parent: from the child Entity's foreign-key Attribute to the parent's key, normally its own surrogate. One foreign-key Attribute has one parent, so the from endpoint alone identifies the record; there is no name or definition.

| Field | Accepted value / meaning |
|---|---|
| `from_logical_entity_schema_name` | Child Entity's configured Logical schema. |
| `from_logical_entity_name` | Child Entity. |
| `from_logical_attribute_name` | The child's foreign-key Attribute. |
| `to_logical_entity_schema_name` | Parent Entity's configured Logical schema. |
| `to_logical_entity_name` | Parent Entity. |
| `to_logical_attribute_name` | The parent's key Attribute, normally its surrogate. |
| `logical_relationship_cardinality` | `many_to_one`, or `one_to_one` when each parent row has at most one child. |
| `logical_relationship_basis` | Text explaining evidence, meaning and multiplicity, including optional participation; distinguish inference from measurements. |
| `logical_relationship_is_active` | Boolean; `false` retires the Relationship. |
| `logical_relationship_is_locked` | Boolean. |

There is no `unknown`, `one_to_many` or `many_to_many` cardinality, no optionality field, composite endpoint array or nested sources field. Model many-to-many as an `association` Entity with one Relationship from each of its foreign keys. Keep unresolved multiplicity in analysis/task evidence instead of inventing a value. A self-reference is allowed when the Attributes differ; identical normalized endpoints are not. Pointing an existing foreign key at a different parent updates its record; a different foreign-key Attribute is a new record, so retire the old one. SQL is not required for a well-supported inference.

## Nested sources

Each source has exactly one source field plus the shared fields below. `rationale` defaults to null; include it explicitly in complete authored records. Every other field is required.

| Field | Accepted value / meaning |
|---|---|
| `support_source_type` | Entity: `object` or `context_record`. Attribute: `attribute` or `context_record`. Names the source field that follows. |
| `source_object` | Only Entity/Object variant: complete physical Object key below. |
| `source_attribute` | Only Attribute/Attribute variant: complete physical Attribute key below. |
| `context_record` | Only Context variant: object containing `context_record_id`. |
| `rationale` | Text explaining this source's contribution, or null when the source needs no explanation. |
| `is_active` | Boolean; `false` retires the source. |
| `is_locked` | Boolean; independent source lock. |

Physical Object key fields: `tenant_code`, `system_code`, `connection_code` (nonblank strings ≤100), `object_schema`, `object_name` (nonblank strings ≤400). Physical Attribute key adds `attribute_name` (nonblank string ≤400). Context identity is a stable lowercase UUID; see [Context records](context.md).

Copy actual physical placement keys using [Object ownership](../metadata/tables/object.md#ownership-and-physical-identity). Do not substitute the Project Tenant/source owner. No Subject Area, modeled Entity or modeled Attribute source variant exists. Physical and Context sources express supported lineage; Subject Areas only choose Objects.

Within one parent, each source type + normalized physical/Context key is unique. An Entity can consolidate multiple Objects, and an Attribute can combine multiple physical Attributes. Source arrays describe provenance, not executable transformations or an order of precedence.

## Scope, validation and limitations

- Physical sources for new/changed Logical records must resolve in eligible active Source/Bronze Project Input Scope. Attribute sources must name actual registered Attributes.
- **Every physical Attribute source requires the corresponding Object source on its parent Logical Entity.** Current Apply checks this; the shared graph validator does not fully check it before Apply. Atlas local validation must catch it first.
- Context sources must exist and be relevant to the logical design; active evidence is checked under the shared workflow rules. An Attribute's Context does not require a duplicate Context source on its parent.
- Source-less Entity/Attribute records are schema-valid. Use them when the design is generated, constant or otherwise has no physical source, with clear supported definitions/evidence. A real applicable Context may explain a calendar or approved rule; do not fabricate a source or create a Context for every technical choice.
- A new or changed `logical_entity_type` must be an active code; validation reports `reference_code_invalid` otherwise. An active Relationship's to Attribute must be a natural or surrogate key of the parent; validation reports `relationship_target_not_key` otherwise.
- Attributes require existing parents. Active Attributes require active Entities; active relationships require active endpoint Attributes and Entities. Retiring an Entity therefore retires its active Attributes and the Relationships that use them in the same batch, as the web workflow's retirement does. Follow shared lock/history rules for retained records and nested sources.
- An Entity belongs to the Subject Areas of its active Object sources. Areas are a focus window, never evidence or an applied prerequisite: author Logical from eligible physical evidence and business Context only, and never infer dependency or lineage from Subject Area records.
- Server Apply retains omitted nested sources. Preserve complete nested arrays locally so the effective draft accurately represents the retained graph.

## Complete synthetic records

These small examples illustrate record shape, not a complete table build. Assume the complete Customer/Order graphs, approved audit columns and physical metadata already exist unless supplied here. New full tables must follow [keys and audit columns](keys-and-audit.md).

`project-change-set/logical_entity.json`:

```json
[
  {
    "logical_entity_schema_name": "silver", "logical_entity_name": "Customer",
    "logical_entity_definition": "A person or organization purchasing goods from the business.",
    "logical_entity_type": "core",
    "logical_entity_grain": "One purchasing person or organization in the governed business identity domain.",
    "logical_entity_dependency_order": 0,
    "logical_entity_is_active": true,
    "logical_entity_is_locked": false,
    "sources": [{"support_source_type":"object","source_object":{"tenant_code":"demo_store","system_code":"gds","connection_code":"lakehouse","object_schema":"bronze","object_name":"customer"},"rationale":"Synthetic customer master identifies the purchasing party.","is_active":true,"is_locked":false}]
  }
]
```

`project-change-set/logical_attribute.json`; assumes existing CustomerID and the Entity/Object source above:

```json
[
  {
    "logical_entity_schema_name": "silver", "logical_entity_name": "Customer",
    "logical_attribute_name": "CustomerNumber",
    "logical_attribute_definition": "Business customer identifier within the governed customer domain; leading zeros are retained.",
    "logical_attribute_data_type": "STRING",
    "logical_attribute_is_nullable": false,
    "logical_attribute_is_natural_key": true,
    "logical_attribute_is_surrogate_key": false,
    "logical_attribute_ordinal_position": 2,
    "logical_attribute_is_audit_column": false,
    "logical_attribute_is_active": true,
    "logical_attribute_is_locked": false,
    "sources": [{"support_source_type":"attribute","source_attribute":{"tenant_code":"demo_store","system_code":"gds","connection_code":"lakehouse","object_schema":"bronze","object_name":"customer","attribute_name":"customer_number"},"rationale":null,"is_active":true,"is_locked":false}]
  }
]
```

`project-change-set/logical_relationship.json`; assumes active `Order.CustomerID` (the child's foreign key) and `Customer.CustomerID` (the parent's surrogate) already exist:

```json
[
  {
    "from_logical_entity_schema_name": "silver", "from_logical_entity_name": "Order",
    "from_logical_attribute_name": "CustomerID",
    "to_logical_entity_schema_name": "silver", "to_logical_entity_name": "Customer",
    "to_logical_attribute_name": "CustomerID",
    "logical_relationship_cardinality": "many_to_one",
    "logical_relationship_basis": "Synthetic metadata identifies one purchasing Customer on each Order; the foreign key resolves that Customer's surrogate. Many Orders per Customer is inferred from these business roles; SQL was not run.",
    "logical_relationship_is_active": true,
    "logical_relationship_is_locked": false
  }
]
```
