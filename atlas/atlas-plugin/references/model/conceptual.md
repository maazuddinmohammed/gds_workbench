# Conceptual records

Owns the exact `conceptual_object`, `conceptual_relationship` and nested `supports` fields. Use [business concepts](../logical-build/business-concepts.md) for modeling decisions, [Model Change Set authoring](change-sets.md) for local writes, [record state](../record-state.md) for locks and lifecycle, and [local validation](../local-validation.md) before completing work.

## Identity and file shape

- `model-change-set/conceptual_object.json`: array of complete changed concepts; key is `conceptual_object_name` within the owning Model.
- `model-change-set/conceptual_relationship.json`: array of complete changed relationships; key is `from_conceptual_object_name` + `to_conceptual_object_name` + `conceptual_relationship_name`.
- Preserve existing names. Compare keys through the shared normalizer, which strips surrounding ASCII spaces and case-folds text. A new spelling is not a rename operation.
- Follow [Model naming](naming.md): new Conceptual Object and Relationship names default to PascalCase, including `Customer` and `Places`. Explicit user overrides remain possible; payload field names remain unchanged.
- Supports belong inside their parent; there is no separate Conceptual Support Change Set dataset. Preserve existing nested members and merge by source identity before writing the complete parent record.
- No section wrapper, Model/database IDs, Attribute arrays, SQL, batch fields or task evidence fields belong in these payloads. Attribute findings may inform explanations but are not Conceptual Attributes or typed supports.

## Conceptual Object fields

All nine fields are required; none is nullable.

| Field | Accepted value / meaning |
|---|---|
| `conceptual_object_name` | Nonblank string, 1–255 characters; established business name and natural key. |
| `conceptual_object_definition` | Nonblank text defining the business concept and its boundary. |
| `conceptual_object_type` | Nonblank string, 1–100 characters; consistent business category. Open text, not a lookup or fixed enum. |
| `conceptual_object_grain` | Nonblank text describing one business occurrence, not a physical key. |
| `conceptual_object_aliases` | Array of strings, unique after key normalization; `[]` is valid. Include supported synonyms only. |
| `conceptual_object_confidence` | `low`, `medium` or `high`; confidence in the explained meaning. |
| `conceptual_object_status` | `active`, `inactive` or `deprecated`. |
| `conceptual_object_is_locked` | Boolean; obey shared record-state rules. |
| `supports` | Array of Object or Assertion supports in the format below; `[]` is schema-valid. |

Alias strings have no individual nonblank/length constraint in the current schema; meaningful aliases and relevant available supports are modeling-quality requirements, not existing schema minimums. Intentionally independent concepts may have empty supports under the business-concepts method.

## Conceptual Relationship fields

All 12 fields are required; none is nullable.

| Field | Accepted value / meaning |
|---|---|
| `from_conceptual_object_name` | Nonblank string, 1–255 characters; exact existing or locally authored from concept. |
| `to_conceptual_object_name` | Nonblank string, 1–255 characters; exact existing or locally authored to concept. |
| `conceptual_relationship_name` | Nonblank string, 1–255 characters; meaningful business association name, normally a verb phrase. |
| `conceptual_relationship_type` | Nonblank string, 1–100 characters; consistent open category, not a lookup or fixed enum. |
| `conceptual_relationship_definition` | Nonblank description of the association between the concepts. |
| `conceptual_relationship_cardinality` | `one_to_one`, `one_to_many`, `many_to_one`, `many_to_many` or `unknown`; interpreted from → to. |
| `conceptual_relationship_basis` | Nonblank explanation of the supporting meaning/evidence and material limits. |
| `conceptual_relationship_cardinality_basis` | Nonblank explanation of multiplicity, or why it is unknown. |
| `conceptual_relationship_confidence` | `low`, `medium` or `high`; uncertainty about cardinality need not invalidate the association. |
| `conceptual_relationship_status` | `active`, `inactive` or `deprecated`. |
| `conceptual_relationship_is_locked` | Boolean; obey shared record-state rules. |
| `supports` | Array of Object or Assertion supports; the relationship's own evidence, not automatically its endpoints' supports. |

`one_to_many` means one from occurrence can relate to multiple to occurrences, each associated with one from occurrence; `many_to_one` reverses this. These values do not encode minimum participation. Explain inferred cardinality honestly; SQL measurement is not mandatory. Use `unknown` when the association is supported but its multiplicity is unclear.

Both endpoints must exist in the effective Model, and an active relationship requires active endpoints. Normalized endpoints must differ: the current schema cannot represent self-relationships. Record that limitation; do not duplicate a concept to bypass it.

## Nested support fields

Each support has exactly one source variant plus the six common fields. All listed fields for the selected variant are required; only `support_role` and `support_reason_detail` allow null.

| Field | Accepted value / meaning |
|---|---|
| `support_source_type` | `object` or `assertion`; selects the matching source field below. |
| `source_object` | Object variant only: complete five-field physical key described below. No `assertion_record` field. |
| `assertion_record` | Assertion variant only: object containing `modeling_assertion_record_key`, described below. No `source_object` field. |
| `support_role` | Nonblank string, 1–255 characters, or null; the source's role in supporting this parent. |
| `support_reason` | Nonblank explanation of how this source supports the concept or association. |
| `support_reason_detail` | Nonblank additional evidence/qualification, or null. |
| `support_confidence` | `low`, `medium` or `high`. |
| `support_status` | `active`, `inactive` or `deprecated`. |
| `support_is_locked` | Boolean; a support has its own lock as well as its parent's protection. |

| Source key field | Accepted value / meaning |
|---|---|
| `source_object.tenant_code` | Nonblank string, 1–100 characters; physical placement Tenant. |
| `source_object.system_code` | Nonblank string, 1–100 characters; registered physical System. |
| `source_object.connection_code` | Nonblank string, 1–100 characters; registered physical Connection. |
| `source_object.object_schema` | Nonblank string, 1–400 characters; registered schema. |
| `source_object.object_name` | Nonblank string, 1–400 characters; registered Object. |
| `assertion_record.modeling_assertion_record_key` | 1–100 characters matching `[A-Za-z][A-Za-z0-9_.-]{0,99}`; an existing or locally authored Assertion Record key. |

Copy physical keys from eligible Metadata; [Object ownership](../metadata/tables/object.md#ownership-and-physical-identity) explains why a Bronze support retains its GDS placement rather than substituting its source owner. Object supports do not accept `source_tenant_code`, Attribute names or IDs. Assertions are referenced by Record key, not Document name.

Source identity must be unique **within each parent**: Object type + normalized five-part key, or Assertion type + normalized Record key. Changing the role does not permit a duplicate source. Several Objects can support one concept, and one Object can support several concepts or relationships.

## Contract checks and boundaries

- New/changed physical supports must resolve to eligible active Model Input Scope; descriptive mention of an outside Object does not make it eligible as support.
- Assertion supports must resolve in the effective Model and apply to the `conceptual` layer. The modeling method additionally checks active, applicable evidence; current reference validation alone does not prove that evidence is adequate or active.
- The schema permits empty supports. The business-concepts method retains real available lineage and permits justified independent concepts; Assertions are optional when useful, never invented to fill a support array.
- Preserve retained history according to shared record-state rules. An inactive record's key remains occupied; an unlocked record is not automatically permission to change it.
- Conceptual records have no required applied predecessor section in the current Snapshot catalog. Locally completed Analysis and Conceptual work may share a Change Set where workflow prerequisites allow.
- Server Apply upserts supplied supports and retains omitted existing supports. Preserve complete nested arrays locally so the effective draft agrees with what will remain after Apply.

## Complete synthetic concepts

Illustrates `model-change-set/conceptual_object.json`. Assume both customer Objects describe the same purchasing-party concept; different Systems alone establish neither sameness nor difference. All physical keys are fictitious and must be replaced with eligible registered keys.

```json
[
  {
    "conceptual_object_name": "Customer",
    "conceptual_object_definition": "A person or organization that purchases goods from the business.",
    "conceptual_object_type": "party",
    "conceptual_object_grain": "One purchasing person or organization.",
    "conceptual_object_aliases": ["Buyer"],
    "conceptual_object_confidence": "high",
    "conceptual_object_status": "active",
    "conceptual_object_is_locked": false,
    "supports": [
      {
        "support_source_type": "object",
        "source_object": {"tenant_code": "demo_store", "system_code": "gds", "connection_code": "lakehouse", "object_schema": "bronze", "object_name": "crm_customer"},
        "support_role": "Customer identity",
        "support_reason": "The synthetic CRM definition identifies the purchasing person or organization.",
        "support_reason_detail": null,
        "support_confidence": "high",
        "support_status": "active",
        "support_is_locked": false
      },
      {
        "support_source_type": "object",
        "source_object": {"tenant_code": "demo_store", "system_code": "gds", "connection_code": "lakehouse", "object_schema": "bronze", "object_name": "sales_customer"},
        "support_role": "Sales customer representation",
        "support_reason": "The synthetic sales definition describes the same purchasing party rather than a separate account.",
        "support_reason_detail": "Shared business meaning supports one concept; no row-level identity matching is claimed.",
        "support_confidence": "high",
        "support_status": "active",
        "support_is_locked": false
      }
    ]
  },
  {
    "conceptual_object_name": "Order",
    "conceptual_object_definition": "A customer's request to purchase goods from the business.",
    "conceptual_object_type": "business_transaction",
    "conceptual_object_grain": "One customer purchase request, which may contain multiple order lines.",
    "conceptual_object_aliases": [],
    "conceptual_object_confidence": "high",
    "conceptual_object_status": "active",
    "conceptual_object_is_locked": false,
    "supports": [
      {
        "support_source_type": "object",
        "source_object": {"tenant_code": "demo_store", "system_code": "gds", "connection_code": "lakehouse", "object_schema": "bronze", "object_name": "orders"},
        "support_role": "Purchase requests",
        "support_reason": "The synthetic Object description identifies individual customer purchase requests.",
        "support_reason_detail": null,
        "support_confidence": "high",
        "support_status": "active",
        "support_is_locked": false
      }
    ]
  }
]
```

## Complete synthetic relationship

Illustrates `model-change-set/conceptual_relationship.json`. The interpretation comes from synthetic metadata; no SQL or physical uniqueness measurement is claimed.

```json
[
  {
    "from_conceptual_object_name": "Customer",
    "to_conceptual_object_name": "Order",
    "conceptual_relationship_name": "Places",
    "conceptual_relationship_type": "association",
    "conceptual_relationship_definition": "A Customer places an Order to request goods.",
    "conceptual_relationship_cardinality": "one_to_many",
    "conceptual_relationship_basis": "Synthetic metadata describes Orders as customer purchase requests and customer_id as the purchasing Customer reference.",
    "conceptual_relationship_cardinality_basis": "Infer one Customer to many Orders from the purchase-request role and single purchasing Customer reference. Minimum participation is unspecified; SQL was not run.",
    "conceptual_relationship_confidence": "high",
    "conceptual_relationship_status": "active",
    "conceptual_relationship_is_locked": false,
    "supports": [
      {
        "support_source_type": "object",
        "source_object": {"tenant_code": "demo_store", "system_code": "gds", "connection_code": "lakehouse", "object_schema": "bronze", "object_name": "orders"},
        "support_role": "Purchasing Customer reference",
        "support_reason": "The synthetic customer_id definition identifies the Customer placing this Order.",
        "support_reason_detail": null,
        "support_confidence": "high",
        "support_status": "active",
        "support_is_locked": false
      }
    ]
  }
]
```

## Synthetic Assertion support variant

This object may be a member of either parent's `supports` array only when the referenced applicable Assertion Record exists. It is not a standalone dataset file and does not create an Assertion.

```json
{
  "support_source_type": "assertion",
  "assertion_record": {"modeling_assertion_record_key": "customer-definition"},
  "support_role": "Business definition",
  "support_reason": "The synthetic confirmed business definition identifies a Customer as the purchasing person or organization.",
  "support_reason_detail": null,
  "support_confidence": "high",
  "support_status": "active",
  "support_is_locked": false
}
```

## Source pointers

Current field contracts: `mcp_server/gds_etl_workbench/domain/modeling_records.py` (`ConceptualObjectRecord`, `ConceptualRelationshipRecord`, `ObjectSupportRecord`, `AssertionSupportRecord`). Keys: `domain/snapshots/model.py`; prerequisites: `tools/snapshots/model/archive.py`; scope/references/locks: `application/change_sets/model_validation.py`; support upserts: `application/change_sets/model_apply.py`; database contracts: `database/06_workflow_conceptual.sql`.
