# Logical records

Owns the four Logical dataset contracts and their nested membership/source fields. Use [logical design](../logical-build/logical-design.md) for modeling decisions, [normalization](../logical-build/normalization.md) for splits/consolidation, [naming](naming.md) and [keys and audit columns](keys-and-audit.md) for policy. [Project Change Set authoring](change-sets.md), [record state](../record-state.md) and [local validation](../local-validation.md) own the shared mechanics.

## Files, identity and common values

Write complete changed records as JSON arrays under `project-change-set/<dataset>.json`. No section wrapper, internal numeric database IDs (including Project IDs), SQL, batch bindings or invented fields. Context source references require the portable `context_record_id` UUID; preserve that identity. Preserve nested arrays when editing; local upsert does not make a field-level patch.

| Dataset | Natural key within the Project |
|---|---|
| `logical_submodel` | `logical_submodel_name` |
| `logical_entity` | `logical_entity_schema_name` + `logical_entity_name` |
| `logical_attribute` | `logical_entity_schema_name` + `logical_entity_name` + `logical_attribute_name` |
| `logical_relationship` | Both schema-qualified Entity/Attribute endpoints + `logical_relationship_name` |

Use shared key normalization; preserve existing spelling. Below, **name** means nonblank string ≤255 characters, **text** means nonblank string, **status** means `active`, `inactive` or `deprecated`. All dataset fields are required, even when nullable.

## Logical Submodel fields

| Field | Accepted value / meaning |
|---|---|
| `logical_submodel_name` | Name; business grouping identity. |
| `logical_submodel_definition` | Text defining the business grouping. |
| `logical_submodel_status` | Status. |
| `logical_submodel_is_locked` | Boolean; shared record-state rules apply. |

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
| `logical_entity_type` | `core`, `reference`, `transaction`, `event`, `bridge`, `history`, `snapshot`, `association`, `aggregate` or `other`. |
| `logical_entity_type_detail` | Text only when type is `other`; otherwise null. |
| `logical_entity_grain` | Text explaining one row's business occurrence. |
| `logical_entity_dependency_order` | Integer ≥0; modeled Entity dependency order, not Process Group scheduling. |
| `logical_entity_status` | Status. |
| `logical_entity_is_locked` | Boolean. |
| `submodels` | Array of membership records below; `[]` is schema-valid. |
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
| `logical_attribute_status` | Status. |
| `logical_attribute_is_locked` | Boolean. |
| `sources` | Array of physical Attribute or Context sources below; `[]` is schema-valid. |

An Attribute cannot be both natural and surrogate key. Any natural/surrogate flag requires `logical_attribute_is_nullable:false`. Naming, first-column surrogate policy, type compatibility and audit order are defined in their policy guides; these flags alone do not enforce them. Multiple natural-key flags describe a tuple, not independent uniqueness of every component.

## Logical Relationship fields

| Field | Accepted value / meaning |
|---|---|
| `logical_relationship_name` | Name; association identity together with the endpoints. |
| `logical_relationship_definition` | Text describing the association. |
| `from_logical_entity_schema_name` | Required configured Logical schema name; part of Entity identity. |
| `from_logical_entity_name` | Name of the from Entity. |
| `from_logical_attribute_name` | Name of the from Attribute in that Entity. |
| `to_logical_entity_schema_name` | Required configured Logical schema name; part of Entity identity. |
| `to_logical_entity_name` | Name of the to Entity. |
| `to_logical_attribute_name` | Name of the to Attribute in that Entity. |
| `logical_relationship_cardinality` | `one_to_one`, `one_to_many`, `many_to_one` or `many_to_many`, interpreted from → to. |
| `logical_relationship_basis` | Text explaining evidence and meaning; distinguish inference from measurements. |
| `logical_relationship_cardinality_basis` | Text explaining the specified multiplicity. |
| `logical_relationship_status` | Status. |
| `logical_relationship_is_locked` | Boolean. |

There is no `unknown` cardinality, explicit optionality, composite endpoint array or nested sources field. Keep unresolved multiplicity in analysis/task evidence instead of inventing a value. A same-Entity relationship is allowed when the Attributes differ; identical normalized Entity/Attribute endpoints are not. SQL is not required for a well-supported inference.

## Nested memberships and sources

Membership contains exactly these three required fields. One Entity may belong to multiple Submodels; repeat each normalized Submodel name only once.

| Field | Accepted value / meaning |
|---|---|
| `submodel_name` | Name of a real effective Logical Submodel. |
| `membership_status` | Status. |
| `membership_is_locked` | Boolean; independent nested lock. |

Each source has exactly one source field plus the shared fields below. All fields are required except `source_order`, which defaults to null; include it explicitly in complete authored records.

| Field | Accepted value / meaning |
|---|---|
| `support_source_type` | Entity: `object` or `context_record`. Attribute: `attribute` or `context_record`. |
| `source_object` | Only Entity/Object variant: complete physical Object key below. |
| `source_attribute` | Only Attribute/Attribute variant: complete physical Attribute key below. |
| `context_record` | Only Context variant: object containing `context_record_id`. |
| `source_order` | Positive integer or null; source ordering. Uniqueness is not required. |
| `rationale` | Text explaining this source's contribution. |
| `status` | Status. |
| `is_locked` | Boolean; independent source lock. |

Physical Object key fields: `tenant_code`, `system_code`, `connection_code` (nonblank strings ≤100), `object_schema`, `object_name` (nonblank strings ≤400). Physical Attribute key adds `attribute_name` (nonblank string ≤400). Context identity is a stable lowercase UUID; see [Context records](context.md).

Copy actual physical placement keys using [Object ownership](../metadata/tables/object.md#ownership-and-physical-identity). Do not substitute the Project Tenant/source owner. No Conceptual, modeled Entity or modeled Attribute source variant exists. Physical and Context sources express supported lineage; Conceptual output does not inform Logical design.

Within one parent, each source type + normalized physical/Context key is unique, regardless `source_order`. An Entity can consolidate multiple Objects, and an Attribute can combine multiple physical Attributes. Source arrays describe provenance, not executable transformations.

## Scope, validation and limitations

- Physical sources for new/changed Logical records must resolve in eligible active Source/Bronze Project Input Scope. Attribute sources must name actual registered Attributes.
- **Every physical Attribute source requires the corresponding Object source on its parent Logical Entity.** Current Apply checks this; the shared graph validator does not fully check it before Apply. Atlas local validation must catch it first.
- Context sources must exist and be relevant to the logical design; active evidence is checked under the shared workflow rules. An Attribute's Context does not require a duplicate Context source on its parent.
- Source-less Entity/Attribute records are schema-valid. Use them when the design is generated, constant or otherwise has no physical source, with clear supported definitions/evidence. A real applicable Context may explain a calendar or approved rule; do not fabricate a source or create a Context for every technical choice.
- `submodels:[]` is schema-valid; no minimum membership exists. Membership references must resolve. Preserve valid active memberships; current reference checks alone do not ensure an active membership points to an active Submodel.
- Attributes require existing parents. Active Attributes require active Entities; active relationships require active endpoint Attributes and Entities. Follow shared lock/history rules for retained records and nested members.
- Conceptual is neither an input nor an applied prerequisite for Logical. Author Logical from eligible physical evidence and business Context only; never infer dependency or lineage from Conceptual records.
- Server Apply retains omitted nested sources/memberships. Preserve complete nested arrays locally so the effective draft accurately represents the retained graph.

## Complete synthetic records

These small examples illustrate record shape, not a complete table build. Assume the complete Customer/Order graphs, approved audit columns and physical metadata already exist unless supplied here. New full tables must follow [keys and audit columns](keys-and-audit.md).

`project-change-set/logical_submodel.json`:

```json
[{"logical_submodel_name":"Sales","logical_submodel_definition":"Customer purchase management.","logical_submodel_status":"active","logical_submodel_is_locked":false}]
```

`project-change-set/logical_entity.json`:

```json
[
  {
    "logical_entity_schema_name": "silver", "logical_entity_name": "Customer",
    "logical_entity_definition": "A person or organization purchasing goods from the business.",
    "logical_entity_type": "core",
    "logical_entity_type_detail": null,
    "logical_entity_grain": "One purchasing person or organization in the governed business identity domain.",
    "logical_entity_dependency_order": 0,
    "logical_entity_status": "active",
    "logical_entity_is_locked": false,
    "submodels": [{"submodel_name":"Sales","membership_status":"active","membership_is_locked":false}],
    "sources": [{"support_source_type":"object","source_object":{"tenant_code":"demo_store","system_code":"gds","connection_code":"lakehouse","object_schema":"bronze","object_name":"customer"},"source_order":1,"rationale":"Synthetic customer master identifies the purchasing party.","status":"active","is_locked":false}]
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
    "logical_attribute_status": "active",
    "logical_attribute_is_locked": false,
    "sources": [{"support_source_type":"attribute","source_attribute":{"tenant_code":"demo_store","system_code":"gds","connection_code":"lakehouse","object_schema":"bronze","object_name":"customer","attribute_name":"customer_number"},"source_order":1,"rationale":"Preserves the synthetic source's business identifier.","status":"active","is_locked":false}]
  }
]
```

`project-change-set/logical_relationship.json`; assumes active `Order.CustomerID` and `Customer.CustomerID` already exist:

```json
[
  {
    "logical_relationship_name": "PlacedByCustomer",
    "logical_relationship_definition": "An Order is placed by a Customer.",
    "from_logical_entity_schema_name": "silver", "from_logical_entity_name": "Order",
    "from_logical_attribute_name": "CustomerID",
    "to_logical_entity_schema_name": "silver", "to_logical_entity_name": "Customer",
    "to_logical_attribute_name": "CustomerID",
    "logical_relationship_cardinality": "many_to_one",
    "logical_relationship_basis": "Synthetic metadata identifies one purchasing Customer reference on each Order; the logical foreign key resolves that Customer's surrogate.",
    "logical_relationship_cardinality_basis": "Infer many Orders to one Customer from these business roles. SQL was not run.",
    "logical_relationship_status": "active",
    "logical_relationship_is_locked": false
  }
]
```
