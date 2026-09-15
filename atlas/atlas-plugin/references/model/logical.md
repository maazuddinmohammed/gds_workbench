# Logical records

Owns the four Logical dataset contracts and their nested membership/source fields. Use [logical design](../logical-build/logical-design.md) for modeling decisions, [normalization](../logical-build/normalization.md) for splits/consolidation, [naming](naming.md) and [keys and audit columns](keys-and-audit.md) for policy. [Model Change Set authoring](change-sets.md), [record state](../record-state.md) and [local validation](../local-validation.md) own the shared mechanics.

## Files, identity and common values

Write complete changed records as JSON arrays under `model-change-set/<dataset>.json`. No section wrapper, Model/database IDs, SQL, batch bindings or invented fields. Preserve nested arrays when editing; local upsert does not make a field-level patch.

| Dataset | Natural key within the Model |
|---|---|
| `logical_submodel` | `logical_submodel_name` |
| `logical_entity` | `logical_entity_name` |
| `logical_attribute` | `logical_entity_name` + `logical_attribute_name` |
| `logical_relationship` | Both Entity/Attribute endpoints + `logical_relationship_name` |

Use shared key normalization; preserve existing spelling. Below, **name** means nonblank string ≤255 characters, **text** means nonblank string, **status** means `active`, `inactive` or `deprecated`, and **confidence** means `low`, `medium` or `high`. All dataset fields are required, even when nullable.

## Logical Submodel fields

| Field | Accepted value / meaning |
|---|---|
| `logical_submodel_name` | Name; business grouping identity. |
| `logical_submodel_definition` | Text defining the business grouping. |
| `logical_submodel_status` | Status. |
| `logical_submodel_is_locked` | Boolean; shared record-state rules apply. |

## Logical Entity fields

| Field | Accepted value / meaning |
|---|---|
| `logical_entity_name` | Name; Entity identity. |
| `logical_entity_definition` | Text defining the business meaning. |
| `logical_entity_type` | `core`, `reference`, `transaction`, `event`, `bridge`, `history`, `snapshot`, `association`, `aggregate` or `other`. |
| `logical_entity_type_detail` | Text only when type is `other`; otherwise null. |
| `logical_entity_grain` | Text explaining one row's business occurrence. |
| `logical_entity_dependency_order` | Integer ≥0; modeled Entity dependency order, not Process Group scheduling. |
| `logical_entity_confidence` | Confidence. |
| `logical_entity_status` | Status. |
| `logical_entity_is_locked` | Boolean. |
| `submodels` | Array of membership records below; `[]` is schema-valid. |
| `sources` | Array of Object or Assertion sources below; `[]` is schema-valid. |

## Logical Attribute fields

| Field | Accepted value / meaning |
|---|---|
| `logical_entity_name` | Name of the parent Logical Entity. |
| `logical_attribute_name` | Name; Attribute identity within its Entity. |
| `logical_attribute_definition` | Text defining the Attribute, including useful units/semantics. |
| `logical_attribute_data_type` | Nonblank string ≤100 characters; approved modeled type, not a fixed schema enum. |
| `logical_attribute_is_nullable` | Boolean; whether null is allowed. |
| `logical_attribute_is_primary_key` | Boolean; membership in the primary key. |
| `logical_attribute_is_natural_key` | Boolean; membership in business identity, possibly a composite tuple. |
| `logical_attribute_is_surrogate_key` | Boolean; marks this Entity's surrogate, not every foreign-key Attribute. |
| `logical_attribute_ordinal_position` | Integer >0; column position. |
| `logical_attribute_is_audit_column` | Boolean; classification under the approved audit policy. |
| `logical_attribute_status` | Status. |
| `logical_attribute_is_locked` | Boolean. |
| `sources` | Array of physical Attribute or Assertion sources below; `[]` is schema-valid. |

An Attribute cannot be both natural and surrogate key. Any primary/natural/surrogate flag requires `logical_attribute_is_nullable:false`. Naming, first-column surrogate policy, type compatibility and audit order are defined in their policy guides; these flags alone do not enforce them. Multiple natural-key flags describe a tuple, not independent uniqueness of every component.

## Logical Relationship fields

| Field | Accepted value / meaning |
|---|---|
| `logical_relationship_name` | Name; association identity together with the endpoints. |
| `logical_relationship_definition` | Text describing the association. |
| `from_logical_entity_name` | Name of the from Entity. |
| `from_logical_attribute_name` | Name of the from Attribute in that Entity. |
| `to_logical_entity_name` | Name of the to Entity. |
| `to_logical_attribute_name` | Name of the to Attribute in that Entity. |
| `logical_relationship_cardinality` | `one_to_one`, `one_to_many`, `many_to_one` or `many_to_many`, interpreted from → to. |
| `logical_relationship_confidence` | Confidence. |
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
| `support_source_type` | Entity: `object` or `assertion`. Attribute: `attribute` or `assertion`. |
| `source_object` | Only Entity/Object variant: complete physical Object key below. |
| `source_attribute` | Only Attribute/Attribute variant: complete physical Attribute key below. |
| `assertion_record` | Only Assertion variant: object containing `modeling_assertion_record_key`. |
| `source_order` | Positive integer or null; source ordering. Uniqueness is not required. |
| `rationale` | Text explaining this source's contribution. |
| `status` | Status. |
| `is_locked` | Boolean; independent source lock. |

Physical Object key fields: `tenant_code`, `system_code`, `connection_code` (nonblank strings ≤100), `object_schema`, `object_name` (nonblank strings ≤400). Physical Attribute key adds `attribute_name` (nonblank string ≤400). Assertion key is 1–100 characters matching `[A-Za-z][A-Za-z0-9_.-]{0,99}`; see [Assertions](assertions.md).

Copy actual physical placement keys using [Object ownership](../metadata/tables/object.md#ownership-and-physical-identity). Do not substitute the Model Tenant/source owner. No Conceptual, modeled Entity or modeled Attribute source variant exists. Concepts inform design; physical and Assertion sources express supported lineage.

Within one parent, each source type + normalized physical/Assertion key is unique, regardless `source_order`. An Entity can consolidate multiple Objects, and an Attribute can combine multiple physical Attributes. Source arrays describe provenance, not executable transformations.

## Scope, validation and limitations

- Physical sources for new/changed Logical records must resolve in eligible active Source/Bronze Model Input Scope. Attribute sources must name actual registered Attributes.
- **Every physical Attribute source requires the corresponding Object source on its parent Logical Entity.** Current Apply checks this; the shared graph validator does not fully check it before Apply. Atlas local validation must catch it first.
- Assertion sources must exist and apply to `logical`; active/applicable evidence is checked under the shared workflow rules. An Attribute's Assertion does not require a duplicate Assertion source on its parent.
- Source-less Entity/Attribute records are schema-valid. Use them when the design is generated, constant or otherwise has no physical source, with clear supported definitions/evidence. A real applicable Assertion may explain a calendar or approved rule; do not fabricate a source or create an Assertion for every technical choice.
- `submodels:[]` is schema-valid; no minimum membership exists. Membership references must resolve. Preserve valid active memberships; current reference checks alone do not ensure an active membership points to an active Submodel.
- Attributes require existing parents. Active Attributes require active Entities; active relationships require active endpoint Attributes and Entities. Follow shared lock/history rules for retained records and nested members.
- There is no applied Conceptual prerequisite in the current Model catalog. Complete Conceptual and Logical work locally together where the workflow allows; do not invent a typed Conceptual source to enforce phase order.
- Server Apply retains omitted nested sources/memberships. Preserve complete nested arrays locally so the effective draft accurately represents the retained graph.

## Complete synthetic records

These small examples illustrate record shape, not a complete table build. Assume the complete Customer/Order graphs, approved audit columns and physical metadata already exist unless supplied here. New full tables must follow [keys and audit columns](keys-and-audit.md).

`model-change-set/logical_submodel.json`:

```json
[{"logical_submodel_name":"Sales","logical_submodel_definition":"Customer purchase management.","logical_submodel_status":"active","logical_submodel_is_locked":false}]
```

`model-change-set/logical_entity.json`:

```json
[
  {
    "logical_entity_name": "Customer",
    "logical_entity_definition": "A person or organization purchasing goods from the business.",
    "logical_entity_type": "core",
    "logical_entity_type_detail": null,
    "logical_entity_grain": "One purchasing person or organization in the governed business identity domain.",
    "logical_entity_dependency_order": 0,
    "logical_entity_confidence": "high",
    "logical_entity_status": "active",
    "logical_entity_is_locked": false,
    "submodels": [{"submodel_name":"Sales","membership_status":"active","membership_is_locked":false}],
    "sources": [{"support_source_type":"object","source_object":{"tenant_code":"demo_store","system_code":"gds","connection_code":"lakehouse","object_schema":"bronze","object_name":"customer"},"source_order":1,"rationale":"Synthetic customer master identifies the purchasing party.","status":"active","is_locked":false}]
  }
]
```

`model-change-set/logical_attribute.json`; assumes existing CustomerID and the Entity/Object source above:

```json
[
  {
    "logical_entity_name": "Customer",
    "logical_attribute_name": "CustomerNumber",
    "logical_attribute_definition": "Business customer identifier within the governed customer domain; leading zeros are retained.",
    "logical_attribute_data_type": "STRING",
    "logical_attribute_is_nullable": false,
    "logical_attribute_is_primary_key": false,
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

`model-change-set/logical_relationship.json`; assumes active `Order.CustomerID` and `Customer.CustomerID` already exist:

```json
[
  {
    "logical_relationship_name": "PlacedByCustomer",
    "logical_relationship_definition": "An Order is placed by a Customer.",
    "from_logical_entity_name": "Order",
    "from_logical_attribute_name": "CustomerID",
    "to_logical_entity_name": "Customer",
    "to_logical_attribute_name": "CustomerID",
    "logical_relationship_cardinality": "many_to_one",
    "logical_relationship_confidence": "high",
    "logical_relationship_basis": "Synthetic metadata identifies one purchasing Customer reference on each Order; the logical foreign key resolves that Customer's surrogate.",
    "logical_relationship_cardinality_basis": "Infer many Orders to one Customer from these business roles. SQL was not run.",
    "logical_relationship_status": "active",
    "logical_relationship_is_locked": false
  }
]
```

## Source pointers

Field/source contracts: `mcp_server/gds_etl_workbench/domain/modeling_records.py`; canonical keys: `domain/snapshots/model.py`; graph checks: `application/change_sets/model_validation.py`; Attribute-parent source requirement: `application/change_sets/model_apply.py` (`_find_entity_object_source`); database rules: `database/07_workflow_logical.sql`. Shared catalog prerequisites are defined in `tools/snapshots/model/archive.py`.
