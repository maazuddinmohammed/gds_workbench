# Mapping records

Owns the three Mapping datasets, their identities and structural checks. The [Mapping document guide](mapping-documents.md) owns the exact existing GDS inner templates and how to make Mapping independently usable by Coding and Validation. Use [Model Change Sets](change-sets.md) for local writes/MCP discovery and [record state](../record-state.md) for protection.

## Identity and local files

All three datasets belong to Model section `mapping`. Read the current Snapshot catalog and each dataset schema first. Write complete changed records as JSON arrays to `model-change-set/<dataset>.json`; these are neither patches nor workflow candidate envelopes.

| Dataset | Natural key within the Model |
|---|---|
| `mapping_dependency` | `modeled_entity_type` + `source_system_code` |
| `mapping_object` | `modeled_entity_type` + `modeled_entity_name` + `source_system_code` |
| `mapping_attribute` | `modeled_entity_type` + `modeled_entity_name` + `modeled_attribute_name` + `source_system_code` |

Compare keys with the shared Model normalization; preserve actual names. One target receiving Systems A and B has separate Object Mapping records and complete Attribute Mapping sets for A and B. File grouping is a later Code Generation choice, absent from these keys.

All fields below are required, with no record-schema defaults. Only the explicitly nullable fields accept JSON null. New completed records normally use `active` and unlocked; preserve existing state.

## Dependency fields

One record per modeled layer/source System, shared by all that System's target contributions in this Model. This is a separate dataset, not nested under an Object Mapping.

| Field | Accepted value / meaning |
|---|---|
| `modeled_entity_type` | `logical_entity` or `dimensional_entity`. |
| `source_system_code` | Nonblank string, 1–100 characters; contributing source System, not the physical GDS placement System. |
| `source_system_dependency_order` | Integer ≥0; source-System dependency order for this layer. Preserve established order; do not substitute Attribute ordinal or Process Group order. |
| `mapping_source_system_dependency_status` | `active`, `inactive` or `deprecated`. |
| `mapping_source_system_dependency_is_locked` | Boolean. |

## Object Mapping fields

| Field | Accepted value / meaning |
|---|---|
| `modeled_entity_type` | `logical_entity` or `dimensional_entity`. |
| `modeled_entity_name` | Nonblank string, 1–255 characters; exact bound modeled Entity. |
| `source_system_code` | Nonblank string, 1–100 characters; the System contribution this Mapping defines. |
| `output_template_code` | Nonblank string, 1–100 characters, or null; actual selected installed Object template code. Never invent installation from a familiar name. |
| `object_dependency_order` | Integer ≥0; dependency order of this target/System transformation. Different from System order and Attribute ordinal. |
| `mapping_transformation_document` | JSON object or null; maximum 524,288 compact UTF-8 bytes. Full target/System transformation document, not a SQL filename. |
| `object_mapping_status` | `active`, `inactive` or `deprecated`. |
| `object_mapping_is_locked` | Boolean. |

## Attribute Mapping fields

| Field | Accepted value / meaning |
|---|---|
| `modeled_entity_type` | `logical_entity` or `dimensional_entity`; required again to identify the parent. |
| `modeled_entity_name` | Nonblank string, 1–255 characters; exact parent modeled Entity. |
| `modeled_attribute_name` | Nonblank string, 1–255 characters; exact bound modeled Attribute, which may differ from its physical target name. |
| `source_system_code` | Nonblank string, 1–100 characters; must identify the same contribution as its Object Mapping. |
| `output_template_code` | Nonblank string, 1–100 characters, or null; actual selected installed Attribute template code. |
| `attribute_mapping_transformation_document` | JSON object or null; maximum 65,536 compact UTF-8 bytes. One target field's population or generation rule. |
| `attribute_mapping_status` | `active`, `inactive` or `deprecated`. |
| `attribute_mapping_is_locked` | Boolean. |

## Inner documents and templates

- Mapping has no typed outer `supports`, `sources`, target physical keys, expressions, types, ordinal, file path, Model ID or database-ID fields. Put the self-contained transformation content inside the existing inner template, as the [document guide](mapping-documents.md) specifies.
- The generic record schema accepts a JSON object with flexible nested JSON values. It does not define or validate the inner source/step/Attribute template. Keep the exact agreed GDS template; flexible storage is not permission to invent extra template fields.
- A document is an object, not a JSON-encoded string, array or Markdown block. Source-less/generated behavior uses the template's permitted null/omitted source collection and an explicit generation rule; an active record cannot have a null whole document.
- Manual plugin Apply resolves a non-null template code to an active Output Template of target type `mapping_object` or `mapping_attribute`. `mapping_object_default` and `mapping_attribute_default` are valid only when installation is established; otherwise use the agreed inner shapes with outer code null. Snapshot codes do not describe installed template schemas.
- Active `{}` documents can pass generic record/graph checks. They are not complete Mapping. Template shape, real source references and executable meaning require the additional checks below.
- Pydantic size checks use compact JSON UTF-8; PostgreSQL also limits its `jsonb::text` byte length. Leave headroom instead of filling a document to the compact limit. These are maximums, not writing targets.

The backend's workflow-specific `{schema_version, object_mapping, attribute_mappings}` candidate is a different contract whose envelope identities are derived server-side. Do not use that shape in these local Model Change Set dataset arrays or invent workflow provenance fields.

## Eligibility, coverage and state

- This workflow starts from active applied Entity/Attribute Bindings and confirmed target registration. Logical targets are eligible Silver Objects; Dimensional targets are eligible Gold Objects. See [Binding](binding.md) for physical placement and current owner restrictions. Mapping's Snapshot catalog has no required applied section of its own; applied Binding is the workflow prerequisite.
- Primary Logical contributors follow active Model Input Scope; primary Dimensional contributors follow eligible Silver Logical contributions. A required FK/existing-value lookup may additionally read an active registered/bound target, such as Silver Customer while mapping Order. Resolve it from authorized Model/target context and verify the complete key and lifecycle; do not add Silver lookups to Source/Bronze Input Scope. Unrelated Model/Tenant data still requires its actual governed read eligibility. Target Binding eligibility alone does not validate every source key written inside a document.
- `source_system_code` must identify an active System. Current generic validation checks active System existence, not whether its claimed contribution matches every inner source. Confirm actual source origin; the physical GDS System and source lineage System may differ.
- Every Object Mapping requires an existing Object Binding and matching layer/System Dependency. An active Object Mapping additionally needs both active and a non-null transformation document.
- Every Attribute Mapping requires its exact Object Mapping and Attribute Binding. An active Attribute Mapping additionally needs both active and a non-null transformation document.
- Every active bound target Attribute must have one active Attribute Mapping **for each active target/System contribution**. Include surrogates, audit, technical, constants and generated fields. Documenting their generation does not add them to the transformation SELECT; apply the shared [key/audit policy](keys-and-audit.md).
- Inactive/deprecated rows keep their keys. Do not create duplicate identities, automatically reactivate them or omit an existing contribution to imply deletion. Current active-System checks can still report inactive source-System history; report that limitation rather than rewriting preserved records.
- A locked Mapping record cannot change, including any part of its whole transformation document. Separate Dependency, Object and Attribute records have separate locks; no implicit parent-lock cascade is established by the generic model contract. Keep a changed Object's aliases, inputs and semantics compatible with preserved/locked Attribute rules.

## Update and downstream behavior

Local effective-state checks overlay complete changed records on the immutable Snapshot. Apply upserts Dependency by Model/layer/System, Object Mapping by bound target/System, and Attribute Mapping by parent Mapping/bound Attribute. The transformation JSON is replaced whole; there is no inner-document merge. Preserve unaffected content when changing a record.

Dependency order is mutable outside the natural key; it is not an extra execution instance. The same target/System cannot be recorded twice at two orders by changing only `object_dependency_order`. Record any required repeated execution explicitly in the transformation intent and resolve its later Code/Process representation instead of creating duplicate Mapping keys.

Dependency, Object and Attribute records can accumulate in one local Mapping batch and one Model Change Set. Do not submit per field or System. Follow the shared [review/Stage/Validate/Apply lifecycle](../change-set-lifecycle.md); refresh the Model Snapshot after verified Apply before downstream Coding/Validation consumes it. Those catalog sections require applied Mapping. Applying Mapping never generates files, runs SQL or deploys code.

## Mapping checks

| Rule | Check / reason | Current coverage |
|---|---|---|
| `mapping.shape` | Exact 5/8/8 fields, canonical identities, enums, booleans, nonnegative orders and JSON size. | Generic schema, duplicate-key checks and database constraints. |
| `mapping.parents` | Real target Bindings, layer/System Dependency and matching Object parent; active child requires active parents and a document. | Generic graph checks. |
| `mapping.coverage` | Every active bound target Attribute represented once for each active target/System Mapping, including generated fields. | Generic graph checks; SELECT participation is a separate content check. |
| `mapping.eligibility` | Current Silver/Gold target and actual eligible sources, source origin and physical key/SQL-name resolution. | Target eligibility and active System checked; inner source content needs additional local checks. |
| `mapping.template` | Exact agreed inner shape and meaningful content; non-null installed codes have correct template type. | Apply resolves installed codes; generic graph does not validate template structure or completeness. |
| `mapping.standalone` | Complete Mapping view supplies resolved target/source/field context plus explicit order/key/filter/generation instructions, without reconstructing modeling history. | Additional workflow/local check defined in the document guide. |
| `mapping.dependencies` | Required predecessor lookups and execution orders agree; no unsupported cycle or ambiguous repeated execution. | Integers and Dependency existence checked; execution semantics/cycles need additional checks. |
| `mapping.protection` | Locks, lifecycle and unchanged mappings preserved; changed shared Object logic does not contradict preserved Attribute rules. | Direct record locks checked; cross-document semantic compatibility needs review. |
| `mapping.meaning` | Grain, complete keys, joins, null/cast policy, branch compatibility and supported reconciliation are coherent. | Additional evidence-based review; schema validity does not prove results. |

These additional checks are documentation requirements for Atlas implementation, not newly implemented runtime guarantees.

## Complete outer-record examples

These synthetic arrays show complete active records using the [document guide's CRM example](mapping-documents.md#concise-examples). Assume applied Customer Binding, eligible sources, compatible target definitions and every other required Attribute Mapping already exist or are included in the real draft. These are complete records, not complete table coverage. Orders of 1 assume no predecessor; they are illustrative, not defaults for dependent targets. Template installation is not assumed, so codes are null.

`model-change-set/mapping_dependency.json`:

```json
[
  {
    "modeled_entity_type": "logical_entity",
    "source_system_code": "CRM",
    "source_system_dependency_order": 1,
    "mapping_source_system_dependency_status": "active",
    "mapping_source_system_dependency_is_locked": false
  }
]
```

`model-change-set/mapping_object.json`:

```json
[
  {
    "modeled_entity_type": "logical_entity",
    "modeled_entity_name": "Customer",
    "source_system_code": "CRM",
    "output_template_code": null,
    "object_dependency_order": 1,
    "mapping_transformation_document": {
      "source_objects": [
        {
          "tenant_code": "GDS",
          "system_code": "GDS",
          "connection_code": "DEMO_GDS",
          "object_schema": "bronze",
          "object_name": "crm_customer",
          "alias": "c"
        }
      ],
      "steps": [
        "Read bronze.crm_customer as c at one row per customer_reference. No joins, filters, batching, aggregation or deduplication apply.",
        "Apply Attribute transformations and return CustomerCode, CustomerName, SourceSystemID in that order for silver.Customer. CustomerID is database-generated; the audit fields marked framework-populated are omitted.",
        "Output grain and merge key are (SourceSystemID, CustomerCode). CRM and ERP preserve separate identities with disjoint keys; aligned branches may use UNION ALL. No predecessor target is required; the runtime loads the result."
      ]
    },
    "object_mapping_status": "active",
    "object_mapping_is_locked": false
  }
]
```

`model-change-set/mapping_attribute.json`:

```json
[
  {
    "modeled_entity_type": "logical_entity",
    "modeled_entity_name": "Customer",
    "modeled_attribute_name": "CustomerCode",
    "source_system_code": "CRM",
    "output_template_code": null,
    "attribute_mapping_transformation_document": {
      "source_attributes": [
        {
          "tenant_code": "GDS",
          "system_code": "GDS",
          "connection_code": "DEMO_GDS",
          "object_schema": "bronze",
          "object_name": "crm_customer",
          "attribute_name": "customer_reference"
        }
      ],
      "transformation": "Return c.customer_reference unchanged as CustomerCode (STRING, non-null). Preserve leading zeros, case and whitespace; confirmed inputs are nonblank. No cast or default."
    },
    "attribute_mapping_status": "active",
    "attribute_mapping_is_locked": false
  }
]
```

## Source pointers

Fields/JSON limits: `mcp_server/gds_etl_workbench/domain/modeling_records.py` (`MappingDependencyRecord`, `MappingObjectRecord`, `MappingAttributeRecord`, `_json_size`); canonical keys/section: `domain/snapshots/model.py`; prerequisites: `tools/snapshots/model/archive.py`; active parents/coverage/locks/eligibility: `application/change_sets/model_validation.py`; active System catalog: `application/change_sets/model.py`; replacement/template resolution: `application/change_sets/model_apply.py`; database uniqueness/size: `database/09_workflow_mapping.sql`. Existing inner-template authority: `database/seed/07_global_mapping_output_templates.template.sql` and `plugins/v2/gds/skills/gds/references/workflows/mapping.md`.
