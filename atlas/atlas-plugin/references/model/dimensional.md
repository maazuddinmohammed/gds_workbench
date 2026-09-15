# Dimensional records

Owns the four Dimensional dataset contracts and nested membership/source fields. Use [dimensional design](../dimensional-build/design.md) for modeling decisions, [naming](naming.md) and [keys and audit columns](keys-and-audit.md) for policy. [Model Change Sets](change-sets.md), [record state](../record-state.md) and [local validation](../local-validation.md) own shared mechanics.

## Files, identity and common values

Write complete changed records as JSON arrays under `model-change-set/<dataset>.json`. No section wrappers, Model/database IDs, SQL, batch bindings or invented policy fields. Preserve nested arrays when editing.

| Dataset | Natural key within the Model |
|---|---|
| `dimensional_submodel` | `dimensional_submodel_name` |
| `dimensional_entity` | `dimensional_entity_name` |
| `dimensional_attribute` | `dimensional_entity_name` + `dimensional_attribute_name` |
| `dimensional_relationship` | Both Entity/Attribute endpoints + `dimensional_relationship_kind` + nullable `dimensional_relationship_role_name` |

Relationship **name is not its key**. Role and kind are key components; changing them changes identity. Use shared normalization and preserve existing spelling. Below, **name** is a nonblank string ≤255 characters, **text** is a nonblank string, **status** is `active`, `inactive` or `deprecated`, and **confidence** is `low`, `medium` or `high`. All dataset fields are required, including nullable fields.

## Dimensional Submodel fields

| Field | Accepted value / meaning |
|---|---|
| `dimensional_submodel_name` | Name; business grouping identity. |
| `dimensional_submodel_definition` | Text defining the business grouping. |
| `dimensional_submodel_status` | Status. |
| `dimensional_submodel_is_locked` | Boolean; shared record-state rules apply. |

## Dimensional Entity fields

| Field | Accepted value / meaning |
|---|---|
| `dimensional_entity_name` | Name; Entity identity. |
| `dimensional_entity_definition` | Text defining the business meaning. |
| `dimensional_entity_type` | `fact`, `dimension` or `bridge`. |
| `dimensional_fact_type` | Facts: `transaction`, `periodic_snapshot`, `accumulating_snapshot` or `factless`. Other Entity types: null. |
| `dimensional_entity_grain_definition` | Text defining one row; required non-null for facts/bridges. Dimensions permit null in the schema; provide explicit grain for a complete design. |
| `dimensional_entity_dependency_order` | Integer ≥0; modeled dependency order, not Process Group scheduling. |
| `dimensional_entity_confidence` | Confidence. |
| `dimensional_entity_status` | Status. |
| `dimensional_entity_is_locked` | Boolean. |
| `submodels` | Array of membership records below; `[]` is valid. |
| `sources` | Array of Entity/Object or Entity/Assertion sources below; `[]` is valid. |

## Dimensional Attribute fields

| Field | Accepted value / meaning |
|---|---|
| `dimensional_entity_name` | Name of the parent Dimensional Entity. |
| `dimensional_attribute_name` | Name; Attribute identity within its Entity. |
| `dimensional_attribute_definition` | Text defining meaning, units and relevant behavior. |
| `dimensional_attribute_data_type` | Nonblank string ≤100 characters; approved modeled type, not a fixed schema enum. |
| `dimensional_attribute_is_nullable` | Boolean; whether null is allowed. |
| `dimensional_attribute_ordinal_position` | Integer >0; column position. |
| `dimensional_attribute_role` | `key`, `descriptor`, `measure`, `degenerate_dimension`, `bridge_weight`, `technical` or `audit`. |
| `dimensional_attribute_key_role` | `none`, `surrogate`, `business` or `foreign`. Any non-`none` value requires Attribute role `key` or `technical`. |
| `dimensional_attribute_is_grain_component` | Boolean; participates in the declared row grain. |
| `dimensional_attribute_additivity` | Measures: `additive`, `semi_additive` or `non_additive`. Other roles: null. |
| `dimensional_attribute_default_aggregation` | Measures: nonblank string ≤100 characters describing the approved default aggregation. Other roles: null. |
| `dimensional_attribute_aggregation_basis` | Text explaining valid aggregation dimensions/conditions; required for semi-/non-additive measures, optional for additive measures. Other roles: null. |
| `dimensional_attribute_change_behavior` | `fixed`, `overwrite`, `historize` or null; intended change behavior, not an executable history implementation. |
| `dimensional_attribute_is_audit_column` | Boolean; must equal whether Attribute role is `audit`. |
| `dimensional_attribute_confidence` | Confidence. |
| `dimensional_attribute_status` | Status. |
| `dimensional_attribute_is_locked` | Boolean. |
| `sources` | Array of physical Attribute or Assertion sources below; `[]` is valid. |

The key role is one value, not several flags. Explain additional identity/grain meaning in the definition; do not invent `is_primary_key`, `is_natural_key` or `is_surrogate_key` fields. Multiple business-key Attributes describe a complete tuple. A generated surrogate does not by itself establish business grain. A `bridge_weight` is not a `measure` for these schema rules: its three measure-policy fields must be null; explain allocation semantics in its definition.

## Dimensional Relationship fields

| Field | Accepted value / meaning |
|---|---|
| `dimensional_relationship_name` | Name; readable association label, outside the natural key. |
| `dimensional_relationship_definition` | Text describing the association. |
| `from_dimensional_entity_name` | Name of the from Entity. |
| `from_dimensional_attribute_name` | Name of its from Attribute. |
| `to_dimensional_entity_name` | Name of the to Entity. |
| `to_dimensional_attribute_name` | Name of its to Attribute. |
| `dimensional_relationship_kind` | Nonblank string ≤50 characters; reuse the Model's established relationship vocabulary, not an invented enum. |
| `dimensional_relationship_cardinality` | `one_to_one`, `one_to_many`, `many_to_one` or `many_to_many`, interpreted from → to. |
| `dimensional_relationship_is_optional` | Boolean; explicit association optionality, distinct from cardinality. |
| `dimensional_relationship_role_name` | Name or null; distinguishes meaningful roles such as OrderDate versus ShipDate. |
| `dimensional_relationship_confidence` | Confidence. |
| `dimensional_relationship_basis` | Text explaining meaning and evidence. |
| `dimensional_relationship_cardinality_basis` | Text explaining multiplicity and any conditions needed to preserve it. |
| `dimensional_relationship_status` | Status. |
| `dimensional_relationship_is_locked` | Boolean. |

No `unknown` cardinality, composite endpoint array or nested sources field exists. Same-Entity relationships are allowed when Attributes differ; identical normalized Entity/Attribute endpoints are rejected. Explain complete composite joins and history predicates in the basis; a one-column edge alone cannot encode them. SQL is not required for supported inference.

## Nested memberships and sources

Membership has exactly three required fields. An Entity may belong to multiple Submodels; each normalized Submodel name appears once.

| Field | Accepted value / meaning |
|---|---|
| `submodel_name` | Name of a real effective Dimensional Submodel. |
| `membership_status` | Status. |
| `membership_is_locked` | Boolean; independent nested lock. |

Each source variant contains its one matching source field plus all applicable common fields. Only `source_order` may be omitted, defaulting to null; include it explicitly in complete authored records. Entity sources have seven fields; Attribute sources have six.

| Field | Accepted value / meaning |
|---|---|
| `support_source_type` | Entity: `object` or `assertion`. Attribute: `attribute` or `assertion`. |
| `source_object` | Only Entity/Object variant: complete physical Object key below. |
| `source_attribute` | Only Attribute/Attribute variant: complete physical Attribute key below. |
| `assertion_record` | Only Assertion variant: object containing `modeling_assertion_record_key`. |
| `source_role` | Required only on Entity sources, including Assertions: name describing the contribution. Not a fixed enum. |
| `source_order` | Positive integer or null; source ordering, not a unique identifier. |
| `rationale` | Text explaining the contribution. |
| `status` | Status. |
| `is_locked` | Boolean; independent nested source lock. |

Physical Object key: `tenant_code`, `system_code`, `connection_code` (nonblank strings ≤100), `object_schema`, `object_name` (nonblank strings ≤400). Physical Attribute key adds `attribute_name` (nonblank string ≤400). Assertion key is 1–100 characters matching `[A-Za-z][A-Za-z0-9_.-]{0,99}`; see [Assertions](assertions.md).

Use actual physical placement keys from [Object ownership](../metadata/tables/object.md#ownership-and-physical-identity), not the Model Tenant/source owner. No modeled Logical Entity/Attribute, Conceptual Object or Dimensional Entity source variant exists. Applied Logical lineage resolves through its registered Silver Objects/Attributes.

Within one parent, each source type + normalized physical/Assertion key is unique **regardless role or order**. Do not duplicate a source merely to assign a second role; describe its complete contribution once. Source arrays record provenance, not transformation SQL or join aliases.

## Scope and current enforcement

- New/changed physical sources must be eligible active **Silver Logical contributions**. They are not Source/Bronze Model Input Scope entries and are not Gold targets.
- Object eligibility requires the current Model's active Logical Object Binding, active Object Mapping with a non-null document, active source-System dependency and active originating System, plus active physical metadata. Attribute eligibility additionally requires its active Attribute Binding/Mapping and non-null Attribute document.
- An Attribute's physical source requires a matching Object source on its parent Dimensional Entity. Apply enforces that relationship; the shared graph validator does not fully catch its absence. Check it locally first.
- Assertions must exist and apply to `dimensional`. Follow shared evidence/state rules; an Attribute's Assertion does not require a duplicate Assertion source on its Entity.
- Empty sources/memberships are valid. Generated calendars, constants and other justified standalone structures need no fake source or compulsory Assertion. Explain their generation/business meaning; attach a real applicable Assertion only when useful.
- Attributes require real parents; active Attributes require active Entities. Active relationships require active endpoint Attributes and Entities. Membership references must resolve; existing reference checks alone do not require an active Submodel for an active membership.
- Preserve locked records and nested members. Apply retains omitted nested sources/memberships; preserve complete arrays so the local effective graph represents what will remain.
- The workflow starts from applied Logical Mapping. The generic Dimensional Snapshot catalog has no blanket applied-section prerequisite, and the Change Set validator can recognize eligible Logical bindings/mappings from the same effective batch. Do not confuse this capability with permission to bypass the workflow's reviewed upstream baseline.

## Additional Atlas checks and unresolved capabilities

These are design/local-validation requirements; current record-schema validation alone does not prove them.

| Check | Why it matters |
|---|---|
| One own generated BIGINT surrogate first; approved key naming, nullability and audit policy | Dimensional key-role flags do not enforce these requirements. |
| Unique active ordinals and complete target columns | Positive ordinals alone permit duplicate positions and missing columns. |
| Complete business key, row grain and compatible key types | Flags/edge existence cannot prove identity or correct joins. |
| Measure meaning, additivity and aggregation at the stated grain | Valid enum values do not prevent double-counting or invalid totals. |
| Active memberships and applicable sources resolve to usable records | Reference existence is weaker than active evidence. |
| Relationships preserve grain, including complete composite/history predicates | Each record has only one Attribute per endpoint. |
| History behavior has an executable consumer contract before Mapping/code | `historize` does not prove that the framework implements Type 2. |

No dedicated SCD type, effective-date, current-row, unknown-member, late-arrival, allocation or bridge-policy fields exist. Use approved modeled technical Attributes/templates plus concise definitions/bases; do not invent payload fields or assume generic `IsActive` implements history. The user confirms Type 1/Type 2 support and framework population of the configured Type 2 fields using natural keys; [history rules](../dimensional-build/history.md) own this population contract.

## Complete synthetic records

These examples illustrate record shapes, not a complete new table build. Assume complete existing Customer/SalesLine graphs, configured keys/audits and active Silver Logical contributions where referenced. New tables must include all columns from [keys and audit columns](keys-and-audit.md). The physical Tenant below is the synthetic GDS Connection owner, not a substituted source owner.

`model-change-set/dimensional_submodel.json`:

```json
[{"dimensional_submodel_name":"Sales","dimensional_submodel_definition":"Completed sales and their purchasing context.","dimensional_submodel_status":"active","dimensional_submodel_is_locked":false}]
```

`model-change-set/dimensional_entity.json`:

```json
[
  {
    "dimensional_entity_name": "SalesLine",
    "dimensional_entity_definition": "A completed sale line available for product and customer analysis.",
    "dimensional_entity_type": "fact",
    "dimensional_fact_type": "transaction",
    "dimensional_entity_grain_definition": "One completed order line within its originating System.",
    "dimensional_entity_dependency_order": 1,
    "dimensional_entity_confidence": "high",
    "dimensional_entity_status": "active",
    "dimensional_entity_is_locked": false,
    "submodels": [{"submodel_name":"Sales","membership_status":"active","membership_is_locked":false}],
    "sources": [{"support_source_type":"object","source_object":{"tenant_code":"demo_platform","system_code":"gds","connection_code":"lakehouse","object_schema":"silver","object_name":"OrderLine"},"source_role":"SalesEvents","source_order":1,"rationale":"Synthetic completed order lines supply the fact grain and line measures.","status":"active","is_locked":false}]
  }
]
```

`model-change-set/dimensional_attribute.json`; assumes its Entity/Object source above and existing preceding Attributes:

```json
[
  {
    "dimensional_entity_name": "SalesLine",
    "dimensional_attribute_name": "Quantity",
    "dimensional_attribute_definition": "Number of units sold on this completed order line, in the governed common unit.",
    "dimensional_attribute_data_type": "DECIMAL(18,4)",
    "dimensional_attribute_is_nullable": false,
    "dimensional_attribute_ordinal_position": 5,
    "dimensional_attribute_role": "measure",
    "dimensional_attribute_key_role": "none",
    "dimensional_attribute_is_grain_component": false,
    "dimensional_attribute_additivity": "additive",
    "dimensional_attribute_default_aggregation": "SUM",
    "dimensional_attribute_aggregation_basis": "Synthetic policy defines one common unit and disjoint sale lines, allowing summation across the associated dimensions.",
    "dimensional_attribute_change_behavior": null,
    "dimensional_attribute_is_audit_column": false,
    "dimensional_attribute_confidence": "high",
    "dimensional_attribute_status": "active",
    "dimensional_attribute_is_locked": false,
    "sources": [{"support_source_type":"attribute","source_attribute":{"tenant_code":"demo_platform","system_code":"gds","connection_code":"lakehouse","object_schema":"silver","object_name":"OrderLine","attribute_name":"Quantity"},"source_order":1,"rationale":"Preserves the governed line quantity.","status":"active","is_locked":false}]
  }
]
```

`model-change-set/dimensional_relationship.json`; assumes active `SalesLine.CustomerKey` and `Customer.CustomerKey`, with the latter unique and no version ambiguity in this synthetic design:

```json
[
  {
    "dimensional_relationship_name": "PurchasedByCustomer",
    "dimensional_relationship_definition": "A completed SalesLine belongs to its purchasing Customer.",
    "from_dimensional_entity_name": "SalesLine",
    "from_dimensional_attribute_name": "CustomerKey",
    "to_dimensional_entity_name": "Customer",
    "to_dimensional_attribute_name": "CustomerKey",
    "dimensional_relationship_kind": "FactToDimension",
    "dimensional_relationship_cardinality": "many_to_one",
    "dimensional_relationship_is_optional": false,
    "dimensional_relationship_role_name": "Purchaser",
    "dimensional_relationship_confidence": "high",
    "dimensional_relationship_basis": "Synthetic policy requires every completed line to resolve its purchasing Customer surrogate.",
    "dimensional_relationship_cardinality_basis": "Many completed lines can reference one unique Customer row; inferred from the declared business roles, without SQL execution.",
    "dimensional_relationship_status": "active",
    "dimensional_relationship_is_locked": false
  }
]
```

`FactToDimension`, `Purchaser` and `SalesEvents` are illustrative vocabulary, not enforced enums or defaults.

## Source pointers

Fields/nested validation: `mcp_server/gds_etl_workbench/domain/modeling_records.py`; canonical keys: `domain/snapshots/model.py`; current graph checks: `application/change_sets/model_validation.py`; Attribute-parent source requirement: `application/change_sets/model_apply.py` (`_find_entity_object_source`); database constraints: `database/08_workflow_dimensional.sql`; physical eligibility: `database/11_workflow_eligibility.sql`; catalog prerequisites: `tools/snapshots/model/archive.py`.
