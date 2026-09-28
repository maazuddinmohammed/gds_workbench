# Mapping records

Owns the two Mapping datasets, their identities and structural checks. The [Mapping document guide](mapping-documents.md) owns the exact existing GDS inner templates and how to make Mapping independently usable by Coding and Validation. Use [Model Change Sets](change-sets.md) for local writes/MCP discovery and [record state](../record-state.md) for protection.

## Identity and local files

Both datasets belong to Model section `mapping`. Read the current Snapshot catalog and each dataset schema first. Write complete changed records as JSON arrays to `model-change-set/<dataset>.json`; these are neither patches nor workflow candidate envelopes.

| Dataset | Natural key within the Model |
|---|---|
| `mapping_object` | `modeled_entity_type` + `modeled_entity_schema_name` + `modeled_entity_name` + `source_system_code` |
| `mapping_attribute` | `modeled_entity_type` + `modeled_entity_schema_name` + `modeled_entity_name` + `modeled_attribute_name` + `source_system_code` |

Compare keys with the shared Model normalization; preserve actual names. One target receiving Systems A and B has separate Object Mapping records and Attribute Mapping sets for A and B. Partial transformations can be saved and used for reviewed Code authoring when the pair has at least one saved transformation. Empty pairs are excluded; Validation still requires complete Mapping. File grouping is a later Code Generation choice, absent from these keys.

All fields below are required, with no record-schema defaults. Only the explicitly nullable fields accept JSON null. New completed records normally use `active` and unlocked; preserve existing state.

## Object Mapping fields

| Field | Accepted value / meaning |
|---|---|
| `modeled_entity_type` | `logical_entity` or `dimensional_entity`. |
| `modeled_entity_schema_name` | Required schema from the selected modeled layer. |
| `modeled_entity_name` | Nonblank string, 1–255 characters; exact modeled Entity. |
| `source_system_code` | Nonblank string, 1–100 characters; the System contribution this Mapping defines. |
| `output_template_code` | Nonblank string, 1–100 characters, or null; actual selected installed Object template code. Never invent installation from a familiar name. |
| `object_dependency_order` | Integer ≥0; dependency order of this target/System transformation. Distinct from Attribute ordinal and the later Process schedule. |
| `mapping_transformation_document` | JSON object or null; maximum 524,288 compact UTF-8 bytes. Full target/System transformation document, not a SQL filename. |
| `object_mapping_status` | `active`, `inactive` or `deprecated`. |
| `object_mapping_is_locked` | Boolean. |

## Attribute Mapping fields

| Field | Accepted value / meaning |
|---|---|
| `modeled_entity_type` | `logical_entity` or `dimensional_entity`; required again to identify the parent. |
| `modeled_entity_schema_name` | Required schema from the selected modeled layer. |
| `modeled_entity_name` | Nonblank string, 1–255 characters; exact parent modeled Entity. |
| `modeled_attribute_name` | Nonblank string, 1–255 characters; exact modeled Attribute. |
| `source_system_code` | Nonblank string, 1–100 characters; must identify the same contribution as its Object Mapping. |
| `output_template_code` | Nonblank string, 1–100 characters, or null; actual selected installed Attribute template code. |
| `attribute_mapping_transformation_document` | JSON object or null; maximum 65,536 compact UTF-8 bytes. One target field's population or generation rule. |
| `attribute_mapping_status` | `active`, `inactive` or `deprecated`. |
| `attribute_mapping_is_locked` | Boolean. |

## Inner documents and templates

- Mapping has no typed outer `supports`, `sources`, target physical keys, expressions, types, ordinal, file path, Model ID or database-ID fields. Put the self-contained transformation content inside the existing inner template, as the [document guide](mapping-documents.md) specifies.
- The generic record schema accepts a JSON object with flexible nested JSON values. It does not define or validate the inner source/step/Attribute template. Keep the exact agreed GDS template; flexible storage is not permission to invent extra template fields.
- A populated document is an object, not a JSON-encoded string, array or Markdown block. Source-less/generated behavior uses the template's permitted null/omitted source collection and an explicit generation rule. A null whole document means no transformation is available. It is not a business rule to return NULL; Code authoring exposes an absent Attribute rule as a typed NULL placeholder with an explicit review finding.
- Manual plugin Apply resolves a non-null template code to an active Output Template of target type `mapping_object` or `mapping_attribute`. `mapping_object_default` and `mapping_attribute_default` are valid only when installation is established; otherwise use the agreed inner shapes with outer code null. Snapshot codes do not describe installed template schemas.
- Newly authored or reactivated active documents cannot be content-free objects, including `{}`, empty default templates or nested null/empty/whitespace values. Stage an explicit null document for a missing transformation; custom template codes do not bypass this rule. Unchanged historical documents retain their approved bytes and digest. Template shape, real source references and executable meaning require the additional checks below.
- Pydantic size checks use compact JSON UTF-8; PostgreSQL also limits its `jsonb::text` byte length. Leave headroom instead of filling a document to the compact limit. These are maximums, not writing targets.

The backend's workflow-specific `{schema_version, object_mapping, attribute_mappings}` candidate is a different contract whose envelope identities are derived server-side. Do not use that shape in these local Model Change Set dataset arrays or invent workflow provenance fields.

## Eligibility, coverage and state

- This workflow starts from active applied schema-qualified Entities/Attributes. See [Entity ownership](entity-ownership.md). Physical target registration is not an authoring prerequisite.
- Primary Logical contributors follow active Model Input Scope; primary Dimensional contributors follow applied Logical Entities/Attributes through source_logical_entities/source_logical_attributes in the transformation documents. A required FK/existing-value lookup additionally uses an eligible peer modeled Entity, such as Logical Customer while mapping Order or Dimensional Customer while mapping a Fact. Resolve it from authorized modeled context with complete schema keys and lifecycle; do not add lookups to physical Model Input Scope or require target registration. Unrelated Model/Tenant data still requires its actual governed read eligibility. Entity eligibility alone does not validate every source key written inside a document.
- `source_system_code` must identify an active System. Current generic validation checks active System existence, not whether its claimed contribution matches every inner source. Confirm actual source origin; the physical GDS System and source lineage System may differ.
- Every Object Mapping requires its existing modeled Entity. An active Object Mapping needs an active Entity. A new active target/System pair needs at least one non-null Object or active Attribute document. Attribute-only output uses a null Object document; Object-only output may have no Attribute records. Mapping has no separate System-order configuration; scheduling belongs to Process Groups and Processes.
- Every Attribute Mapping requires its exact Object Mapping and modeled Attribute in the same Entity. Active records need active parents; a null document explicitly records a missing transformation. Missing Attribute records are also incomplete.
- Code authoring accepts each active target/System contribution with any saved Object or Attribute transformation and preserves the full active target Attribute shape. Missing Attribute rules become typed NULL placeholders; missing Object logic stays a review finding. Never infer joins or create rows to fill those gaps; use a typed zero-row projection when row production cannot be established. Apply the shared [key/audit policy](keys-and-audit.md) for proven generated/framework omissions. Validation still requires non-null Object and Attribute documents for every active target/System contribution. Incomplete Mapping is also unavailable as an executable modeled-source lookup.
- Inactive/deprecated rows keep their keys. Do not create duplicate identities, automatically reactivate them or omit an existing contribution to imply deletion. Current active-System checks can still report inactive source-System history; report that limitation rather than rewriting preserved records.
- A locked Mapping record cannot change, including any part of its whole transformation document. Object and Attribute records have separate locks; no implicit parent-lock cascade is established by the generic model contract. Keep a changed Object's aliases, inputs and semantics compatible with preserved/locked Attribute rules.

## Update and downstream behavior

For Logical Mapping, read the frozen Model's `logical_entity_scd_type`:
`type_1` guides overwrite semantics and `type_2` guides versioned history. Null
does not imply a default. Use existing modeled Attributes and evidenced matching,
change-detection and history rules; report missing rules instead of fabricating
them. This setting does not override Dimensional change behavior or migrate data.

Local effective-state checks overlay complete changed records on the immutable Snapshot. Apply upserts Object Mapping by modeled Entity/System and Attribute Mapping by parent Mapping/modeled Attribute. The transformation JSON is replaced whole; there is no inner-document merge. Preserve unaffected content when changing a record.

To clear an existing unlocked transformation, stage its complete record with the document explicitly null. Omitting a record from a Change Set preserves it. An existing pair may retain an empty internal header after all transformations are cleared; this preserves identity/history and does not make it usable by Code Generation. Never invent replacement logic or change locked/unselected records.

Dependency order is mutable outside the natural key; it is not an extra execution instance. The same target/System cannot be recorded twice at two orders by changing only `object_dependency_order`. Record any required repeated execution explicitly in the transformation intent and resolve its later Code/Process representation instead of creating duplicate Mapping keys.

Object and Attribute records can accumulate in one local Mapping batch and one Model Change Set. Do not submit per field or System. Follow the shared [review/Stage/Validate/Apply lifecycle](../change-set-lifecycle.md); refresh the Model Snapshot after verified Apply before downstream Coding/Validation consumes it. Those catalog sections require applied Mapping. Applying Mapping never generates files, runs SQL or deploys code.

## Mapping checks

| Rule | Check / reason | Current coverage |
|---|---|---|
| `mapping.shape` | Exact fields from the current schema, canonical identities, enums, booleans, nonnegative orders and JSON size. | Generic schema, duplicate-key checks and database constraints. |
| `mapping.parents` | Real modeled Entities/Attributes and matching Object parent; active child requires active parents. New active pairs need at least one Object or Attribute document. | Generic graph checks. |
| `mapping.coverage` | Partial Mapping can be saved. Code authoring requires an Object document and every active modeled Attribute represented once per active target/System Mapping, including generated fields. | Generic graph checks at Code authoring; SELECT participation is a separate content check. |
| `mapping.eligibility` | Current modeled target and eligible sources, source origin and physical key/SQL-name resolution. | Target eligibility and active System checked; inner source content needs additional local checks. |
| `mapping.template` | Exact agreed inner shape and meaningful content; non-null installed codes have correct template type. | Apply resolves installed codes; generic graph does not validate template structure or completeness. |
| `mapping.standalone` | Complete Mapping view supplies resolved target/source/field context plus explicit order/key/filter/generation instructions, without reconstructing modeling history. | Additional workflow/local check defined in the document guide. |
| `mapping.dependencies` | Required predecessor lookups and execution orders agree; no unsupported cycle or ambiguous repeated execution. | Nonnegative integer orders checked; execution semantics/cycles need additional checks. |
| `mapping.protection` | Locks, lifecycle and unchanged mappings preserved; changed shared Object logic does not contradict preserved Attribute rules. | Direct record locks checked; cross-document semantic compatibility needs review. |
| `mapping.meaning` | Grain, complete keys, joins, null/cast policy, branch compatibility and supported reconciliation are coherent. | Additional evidence-based review; schema validity does not prove results. |

These additional checks are documentation requirements for Atlas implementation, not newly implemented runtime guarantees.

## Complete outer-record examples

These synthetic arrays show complete active records using the [document guide's CRM example](mapping-documents.md#concise-examples). Assume applied silver.Customer Entity, eligible sources, compatible target definitions and every other required Attribute Mapping already exist or are included in the real draft. These are complete records, not complete table coverage. Orders of 1 assume no predecessor; they are illustrative, not defaults for dependent targets. Template installation is not assumed, so codes are null.

`model-change-set/mapping_object.json`:

```json
[
  {
    "modeled_entity_type": "logical_entity",
    "modeled_entity_schema_name": "silver",
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
    "modeled_entity_schema_name": "silver",
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

## Modeled lookup references

Logical Mapping uses physical `source_objects` / `source_attributes` for scoped
Source/Bronze inputs. When resolving a peer Logical Entity's key or current value,
add `source_logical_entities` entries with `logical_entity_schema_name`,
`logical_entity_name`, and `alias`; its Attribute references use
`source_logical_attributes` with those two key fields plus `logical_attribute_name`.
These modeled references do not require Silver registration.

Dimensional Mapping uses those Logical lists for upstream inputs. An additional
peer Dimensional key lookup uses `source_dimensional_entities` with
`dimensional_entity_schema_name`, `dimensional_entity_name`, and `alias`, and
`source_dimensional_attributes` with those key fields plus
`dimensional_attribute_name`. Physical source lists are null or absent for this
route. Logical Mapping does not consume Dimensional source lists.

Keep aliases unique across all input lists. Every referenced Attribute must belong
to a declared input in the matching list. Use active, authorized same-Model source
Entities and the selected System's applied Mapping context. Empty or nullable lists
do not authorize inventing a source, and modeled names alone never prove a join.
An authored Mapping may precede a peer Mapping. `read_mapping_context` preserves
`complete=false` and its issues for missing transformations or source context.
Code may expose missing target rules as reviewed typed NULL placeholders, but
cannot treat an incomplete peer as an executable source or invent a join.
Missing row-producing evidence requires a typed zero-row projection; unresolved
or contradictory authored references still require correction. Validation
requires `complete=true` before authoring.

## Source pointers

Fields/JSON limits: `mcp_server/gds_etl_workbench/domain/modeling_records.py` (`MappingObjectRecord`, `MappingAttributeRecord`, `_json_size`); canonical keys/section: `domain/snapshots/model.py`; prerequisites: `tools/snapshots/model/archive.py`; active parents/coverage/locks/eligibility: `application/change_sets/model_validation.py`; active System catalog: `application/change_sets/model.py`; replacement/template resolution: `application/change_sets/model_apply.py`; database uniqueness/size: `database/09_workflow_mapping.sql`. Existing inner-template authority: `database/seed/07_global_mapping_output_templates.template.sql`.
