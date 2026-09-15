# Model Binding records

Owns `model_object_binding`, `model_attribute_binding` and their structural checks. The [Entity Binding skill](../../skills/atlas-entity-binding/SKILL.md) owns name matching and necessary user questions. Use [Model Change Set authoring](change-sets.md) for local writes/MCP contract discovery, [record state](../record-state.md) for protection and [local validation](../local-validation.md) for validation order.

## Identity and field shape

Write complete changed record arrays to `model-change-set/model_object_binding.json` and `model-change-set/model_attribute_binding.json`. Both datasets are in Model section `model_binding`. All fields below are required, non-null and without record-schema defaults. New supported bindings use `active` and unlocked; preserve existing state under shared rules.

Object Binding natural key: `modeled_entity_type` + `modeled_entity_name`. Its five physical fields identify the registered target, not a contributing source.

| Field | Accepted value / meaning |
|---|---|
| `tenant_code` | Nonblank string, 1–100 characters; physical target Connection's Tenant. |
| `system_code` | Nonblank string, 1–100 characters; physical target System. |
| `connection_code` | Nonblank string, 1–100 characters; physical target Connection. |
| `object_schema` | Nonblank string, 1–400 characters; registered target schema. |
| `object_name` | Nonblank string, 1–400 characters; registered target Object. |
| `modeled_entity_type` | `logical_entity` or `dimensional_entity`; selects the modeled layer. |
| `modeled_entity_name` | Nonblank string, 1–255 characters; exact modeled Entity name. |
| `model_object_binding_status` | `active`, `inactive` or `deprecated`. |
| `model_object_binding_is_locked` | Boolean. |

Attribute Binding natural key: `modeled_entity_type` + `modeled_entity_name` + `modeled_attribute_name`. The physical Object derives from the matching Object Binding; only its target Attribute name appears here.

| Field | Accepted value / meaning |
|---|---|
| `modeled_entity_type` | `logical_entity` or `dimensional_entity`; **required again**, even though it must match the parent. |
| `modeled_entity_name` | Nonblank string, 1–255 characters; **required again** to identify the parent binding. |
| `modeled_attribute_name` | Nonblank string, 1–255 characters; exact modeled Attribute under that Entity. |
| `attribute_name` | Nonblank string, 1–400 characters; actual registered Attribute under the bound physical Object. |
| `model_attribute_binding_status` | `active`, `inactive` or `deprecated`. |
| `model_attribute_binding_is_locked` | Boolean. |

No Model/database IDs, `source_tenant_code`, physical Object fields in Attribute bindings, types, ordinals, expressions, joins or nested sources belong in these records. Names on the two sides may differ when the assignment is explicitly established. Binding records identity correspondence; it does not define how to populate values.

## Eligibility and complete coverage

- Logical Entities bind to registered Silver Objects; Dimensional Entities bind to Gold Objects. These are **target eligibility rules**, not Source/Bronze Model Input Scope membership. Do not add Silver/Gold targets to Input Scope.
- Copy the target's real five-part physical GDS key from Metadata; see [ownership](../metadata/tables/object.md#ownership-and-physical-identity). Current eligibility requires its `source_tenant_code` to equal the Model Tenant. A different legitimate owner is a current Binding limitation, not permission to change ownership.
- The workflow requires applied modeling records and fresh Metadata confirming applied target registration. The catalog has no separate required applied section for Binding; do not confuse broader effective-graph validation with that workflow prerequisite.
- One modeled Entity binds to one physical Object within the Model. Each physical target Object may bind to only one modeled Entity, across both modeled types.
- An active Object Binding requires an active modeled Entity. Each active Attribute Binding requires its active Object Binding and an active modeled Attribute. Target Objects/Attributes must meet current active eligibility.
- Every active modeled Attribute **and every active eligible physical Attribute under the target** needs exactly one active Attribute Binding. Include surrogates, foreign keys, audit, technical, constants and source-less/generated fields. Extra registered columns cannot simply be ignored; missing modeled counterparts require upstream resolution.
- Schema/reference checks do not establish matching business meaning or compatible types, capacity, nullability and key/audit roles. Compare those with the agreed target definition. Equivalent type spellings require a known platform equivalence; do not assume a later cast repairs a wrong assignment.
- SQL is unnecessary for ordinary Binding. It matches registered/model identities; it does not discover data relationships, validate joins or execute DDL.

## Existing records and reassignment

Reuse correct existing bindings; omit unchanged records from pending work. A locked active Entity, Object or Attribute can be read and referenced without changing it. A locked Binding itself cannot change. Preserve inactive/deprecated assignments and inspect them before creating a new assignment.

Database uniqueness reserves binding assignments across lifecycle states: `(Model, physical Object)`, each modeled Entity, `(Object Binding, physical Attribute)` and each modeled Attribute are not active-only identities. Backend graph checks reserve physical targets across lifecycle states; an inactive assignment is not a free target.

Changing the Object Binding's target also changes the physical identity implied by all its Attribute Bindings, even when their `attribute_name` text stays unchanged. Treat an existing target reassignment as consequential work: inspect all child bindings and downstream Mapping/Code before proceeding; do not silently rebind during name matching.

**Implemented reassignment guard:** backend validation rejects retargeting an already-bound modeled Entity or Attribute (`binding_reassignment_unsupported`). A parent retarget that changes a locked child's derived physical identity also reports `record_locked`, even if the child's Attribute name is unchanged.

Apply still upserts Object Bindings by physical target and Attribute Bindings by parent/physical Attribute. The guard protects this existing contract; it does not implement a binding migration. Preserve existing assignments and report a requested reassignment until a supported governed operation is established. Never bypass this through deactivation, alternate names, deletion or direct database mutation.

## Binding checks

Run these with the shared local effective-graph checks before the shared [Change Set lifecycle](../change-set-lifecycle.md). Coverage distinguishes automated rules from workflow review.

| Rule | Check / reason | Current coverage |
|---|---|---|
| `binding.shape` | Exact required fields, keys, allowed layer/status and real endpoint names; no extra IDs/expressions. | Schema and graph checks. |
| `binding.eligibility` | Correct Silver/Gold layer, physical placement, Model-compatible owner and active registered target. | Authoritative eligibility and local mirror; confirm bound context. |
| `binding.parents` | Real modeled Entity/Attribute and parent Object Binding; active child requires active parents. | Graph checks. |
| `binding.coverage` | One active binding for every active modeled and eligible physical target Attribute, including generated/audit fields. | Both-side graph coverage checks. |
| `binding.unique` | One-to-one assignments and occupied inactive/deprecated history; preserve exact identities. | Database and backend graph uniqueness reserve all statuses. |
| `binding.compatibility` | Confirm types/capacity, nullability, key/audit meaning and established target assignment agree. | Additional workflow/local check; not established by current binding schema. |
| `binding.protection` | Preserve locks/status; parent reassignment must not change a locked child's derived target. | Direct locks and derived-target guard checked by backend; mirrored in local validation. |
| `binding.reassignment` | Existing assignment and downstream dependencies preserved; no unsupported automatic retarget. | Backend explicitly rejects existing retargets; workflow preserves assignments. |

## Complete synthetic examples

Assume the complete active Logical `Customer`, Dimensional `DimCustomer` and registered targets already exist in the Model Tenant's eligible GDS placement. These arrays demonstrate complete **records**, not complete coverage of those tables; all other modeled/physical columns must already have matching bindings or be included in the actual draft.

`model-change-set/model_object_binding.json`:

```json
[
  {
    "tenant_code": "demo_store",
    "system_code": "gds",
    "connection_code": "lakehouse",
    "object_schema": "silver",
    "object_name": "Customer",
    "modeled_entity_type": "logical_entity",
    "modeled_entity_name": "Customer",
    "model_object_binding_status": "active",
    "model_object_binding_is_locked": false
  },
  {
    "tenant_code": "demo_store",
    "system_code": "gds",
    "connection_code": "lakehouse",
    "object_schema": "gold",
    "object_name": "DimCustomer",
    "modeled_entity_type": "dimensional_entity",
    "modeled_entity_name": "DimCustomer",
    "model_object_binding_status": "active",
    "model_object_binding_is_locked": false
  }
]
```

`model-change-set/model_attribute_binding.json`:

```json
[
  {
    "modeled_entity_type": "logical_entity",
    "modeled_entity_name": "Customer",
    "modeled_attribute_name": "CustomerID",
    "attribute_name": "CustomerID",
    "model_attribute_binding_status": "active",
    "model_attribute_binding_is_locked": false
  },
  {
    "modeled_entity_type": "dimensional_entity",
    "modeled_entity_name": "DimCustomer",
    "modeled_attribute_name": "CustomerKey",
    "attribute_name": "CustomerKey",
    "model_attribute_binding_status": "active",
    "model_attribute_binding_is_locked": false
  }
]
```

The Dimensional example uses the assumed existing key name; actual names come from the applied Model and confirmed registration, not this example. Bind generated keys like any other target column without inventing source expressions.

## Source pointers

Fields: `mcp_server/gds_etl_workbench/domain/modeling_records.py` (`ModelObjectBindingRecord`, `ModelAttributeBindingRecord`); keys: `domain/snapshots/model.py`; graph/coverage/locks: `application/change_sets/model_validation.py` (`_validate_bindings`, `_validate_active_dependencies`, `validate_future_graph`); Apply identity handling: `application/change_sets/model_apply.py` (`_UPSERT_MODEL_OBJECT_BINDING_SQL`, `_UPSERT_MODEL_ATTRIBUTE_BINDING_SQL`); database identity/eligibility: `database/09_workflow_mapping.sql`, `database/11_workflow_eligibility.sql`.

The old GDS Binding guide's instruction not to repeat Entity type does not describe the current ID-free Attribute Binding payload; include both required modeled Entity fields above.
