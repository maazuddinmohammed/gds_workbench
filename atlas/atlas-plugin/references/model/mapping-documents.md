# Mapping transformation documents

Shared by Mapping authoring, Code Generation and Validation. This page owns the existing GDS inner templates and concise transformation instructions. [Mapping records](mapping.md) owns outer fields/keys; [keys/audit](keys-and-audit.md) owns population policy; the [Mapping skill](../../skills/atlas-mapping/SKILL.md) owns sequence and questions.

## Exact existing template

Reuse `mapping_object_default` and `mapping_attribute_default` using the source fields for the selected layer. Set outer `output_template_code` to the corresponding code only when its installed active definition and target type are established; otherwise use null with this agreed shape. Existing Snapshot codes are not proof that a template is installed. Do not seed a database or create a Workflow Run to select a template.

| Object document field | Shape and meaning |
|---|---|
| `source_objects` | Required, nullable array. Each item contains `tenant_code`, `system_code`, `connection_code`, `object_schema`, `object_name`, `alias`, in that order. List actual query inputs with full physical identities. Aliases are unique; a real self-join may repeat an Object with different aliases. |
| `source_logical_entities` | Dimensional alternative to `source_objects`: nullable array of `logical_entity_schema_name`, `logical_entity_name`, `alias`. References applied Logical design. |
| `steps` | Required, nullable ordered array of strings. Concrete query-building steps; each substantial stage identifies its inputs, result and grain. |

| Attribute document field | Shape and meaning |
|---|---|
| `source_attributes` | Optional, nullable array. Each item contains `tenant_code`, `system_code`, `connection_code`, `object_schema`, `object_name`, `attribute_name`, in that order. Registered source identities, with no alias field. |
| `transformation` | Required string: one field's expression or precise population rule. State necessary type conversion, null/default/invalid-value behavior and source role. |

These are inner documents stored in `mapping_transformation_document` and `attribute_mapping_transformation_document`. They are not complete Change Set records. Preserve permitted nullability: null sources can describe a constant/generated value; null steps must not hide missing transformation logic. A null whole document means a missing transformation, not an authored business rule. Partial Mapping can be saved under the [record rules](mapping.md#eligibility-coverage-and-state); Code exposes missing Attribute rules as typed NULL placeholders requiring review. Validation still requires complete Mapping. Preserve real custom template selections rather than silently converting existing documents.

Newly staged active documents with only empty objects/arrays, nulls or whitespace must use explicit null, for both default and custom templates. Local and MCP validation reject these content-free documents; they do not silently normalize approved records. Numeric zero and boolean false can be meaningful custom rules and remain intact.

For Dimensional Attribute documents, use `source_logical_attributes` instead of `source_attributes`; each item has `logical_entity_schema_name`, `logical_entity_name`, `logical_attribute_name`. Preserve `transformation`. Logical documents keep physical sources.

## Object-level steps

Use an ordered list, normally one or two sentences per step. Split distinct operations; expand only when a precise rule needs more detail. Do not paste a complete SQL query, repeat every Attribute expression or impose unnecessary stages.

1. **Inputs and preparation:** identify the starting alias/relation and input grain. State necessary preparation and actual runtime SQL names when they differ from metadata names. Supporting evidence alone does not mean a table is read. Include required authorized target/reference lookups in `source_objects`; a Silver FK lookup is not a new Source/Bronze Input Scope member.
2. **Joins/lookups:** give each input, join type, full key predicates and expected row effect. State missing/multiple-match behavior; preserve an optional join by putting the filter in its intended ON/input/WHERE location.
3. **Filters and grain changes:** put each predicate at the required stage. State grouping, aggregation or deduplication only when applicable, including full keys, deterministic tie handling and resulting grain. Do not invent row winners.
4. **Output:** name the target, approved output grain/business-key tuple and exact SQL-populated physical columns in order. Apply the Attribute rules; finish with `SourceSystemID`. Account for omitted database/framework fields through their Attribute rules.
5. **System interaction/dependencies:** state disjoint identities or the complete reconciliation/precedence rule, predecessor targets and any existing-value lookup. Keep `object_dependency_order` consistent with actual target dependencies. System list order does not establish business precedence or scheduling; the runtime schedule belongs to Process Groups and Processes.

Only use applicable operations; a simple direct branch can combine these into a few steps. An intermediate result must carry the columns later joins/expressions need. No transformation may depend on a temporary view created by another file/session.

## Attribute-level instructions

For each active modeled Attribute and contributing System, state its actual source columns and implementable value rule. Use Object aliases in expressions; describe self-join roles in text because Attribute lineage has no alias field.

- **Direct/derived:** expression and target-compatible type; preserve evidenced identifier formatting, precision, timezone, nullability and invalid-value rules. Storage STRING does not make every value semantically text, but leading-zero identifiers must not become numbers merely because they parse.
- **Foreign key:** exact lookup Object/alias, complete business-key match, returned target key and missing/multiple-match behavior. Generate only the table's own key; a referenced key is a mapped value.
- **Constant/generated business value:** actual constant or supported generation rule and its provenance. No fabricated physical source; unconfirmed constants/defaults remain unresolved.
- **Own surrogate:** explicitly database-generated; omit from the load SELECT. Preserve its exact target column/type in the complete Mapping view.
- **Framework audit:** explicitly framework-populated; omit from the load SELECT. Keep a Mapping record for each such bound field, with no fabricated expression or source.
- **SourceSystemID:** provide the actual originating-System value/expression per branch. It is the last SQL-populated column; physical GDS placement is not source provenance.

The approved [audit policy](keys-and-audit.md#population-boundary-and-implementation-alignment) identifies the nine framework fields and optional Source audit fields. Resolve the actual policy while authoring and capture the applicable population in the Mapping; downstream readers should not rederive it from model flags. No inference that every surrogate-looking name is generated.

For Dimensional history, use the shared [history and lookup rules](../dimensional-build/history.md): preserve the chosen change behavior, complete natural keys and temporal FK lookup. Mark the configured Type 2 fields as framework-populated and omitted from transformation SQL. Technical role alone does not establish that rule for other columns.

Keep the target's physical name, type, nullability and ordinal in the resolved Mapping context below. If a source's SQL column differs from registered `attribute_name` (for example `fc_attribute_name`), retain the registered lineage and specify the resolved executable name in the transformation. A coding reader must not guess the translation.

## Runtime and multiple Systems

Each target/System has its own Object and Attribute mappings. Source System A and System B may both contribute to Customer; Code Generation later chooses combined or separate files. Both layouts must preserve the same mapped semantics and complete required preparation.

Each branch returns the same ordered physical aliases and compatible types. UNION ALL is valid for disjoint target identities or after explicit reconciliation. Different files do not make colliding keys safe. Do not choose arbitrary System precedence, DISTINCT, prior-target fallback or a synthetic origin merely to combine branches.

Mapping states the output and key rules; the framework performs target loading. The shared [SQL workflow instructions](../code-generation/sql.md) translates those rules into self-contained temporary-view stages and one final explicit-column SELECT. Framework SQL uses resolved `schema.table` coordinates without catalog under the confirmed GDS runtime convention; evidence queries use their governed execution coordinates. Resolve incompatible cross-catalog placement explicitly instead of redirecting a source.

Runtime batch filters apply only where required by the transformation/consumer. State the exact column, predicate, placeholder name/type and how it is supplied. Existing GDS examples use `wid_GDSBatchID`; confirm applicability before using it. Never copy a profiling batch literal into production logic or apply a current-batch filter indiscriminately to historical lookups. Python logic must preserve the same mapped row/field semantics; its artifact/entrypoint convention belongs to Code Generation. Current backend Code Generation authoring supports SQL; Python consumer support remains to be designed and implemented.

## Complete context for coding and validation

The coding/validation agent reads all components of one target-oriented Mapping view: Mapping instructions plus resolved technical context. Code may consume partial saved transformations; Validation requires the view's `complete=true` signal. Raw `mapping_object`/`mapping_attribute` arrays alone omit modeled target types and ordinal information. The read/assembly layer must resolve those once from the approved Entity and source context, so the consuming agent does not traverse the model or reinterpret its design.

Reuse the existing backend downstream projection where compatible:

| Context component | Information the consumer needs |
|---|---|
| `target_metadata` | Planned Entity schema/name and every modeled Attribute's name, type/capacity, nullability and ordinal. This is an executable projection of the design, not proof of physical registration. |
| `source_metadata` | Actual permitted input identities, SQL coordinates/column names and relevant source types; distinguish originating System from GDS placement. |
| `source_systems` | Selected originating Systems and their resolved IDs/names; list order is stable presentation only. |
| `object_transformations` | Every selected nonempty System branch's Object document (possibly null), modeled identity and Object dependency order; use only authored grain, keys, branch policy and prerequisites. |
| `attribute_transformations` | Complete per-System modeled Attribute coverage, schema-qualified modeled target names and Attribute documents, including generated/framework rules. |

This is a derived read view, not a fourth Change Set dataset, a second manually maintained mapping or a large prose handoff. It must preserve record boundaries and complete coverage when paged. Use one consistent approved revision/context; required target/source changes make the view stale and need reconciliation. Do not put internal IDs, credentials or physical rows into author instructions.

Use the governed `read_mapping_context` MCP tool. Start with the verified applied Model revision and selected target:

```text
read_mapping_context(
  model_id=<verified positive ID>,
  modeled_entity_type="logical_entity" | "dimensional_entity",
  modeled_entity_schema_name=<exact configured schema>,
  modeled_entity_name=<exact target name>,
  component="target_metadata",
  expected_model_revision=<applied revision>,
  page_size=50,
  schema_version="1.0"
)
```

Read all five components listed above. Each response supplies `model_id`, `model_revision`, `context_digest`, `component`, `records`, `complete`, `issues` and `next_cursor`. Pass the first `context_digest` as `expected_context_digest` on every subsequent component/page; retain the same Model revision, target and optional `source_system_codes` selection. Follow each non-null `next_cursor` with unchanged page size. A component with a cursor is not fully read even when `complete=true` (that flag describes context validity).

Cache only the assembled component records and their Model/target/System/revision/digest bindings as read-only task input. Do not keep opaque tool envelopes or fabricate missing columns. On changed revision/digest, refresh all components; never combine old and new pages. `complete=false` and `issues` remain authoritative findings: Code may expose absent Attribute transformations as typed NULL placeholders in the known target types/order, while Validation must resolve every issue before authoring. A missing Object document requires an explicit review finding; never invent source rows, joins or business rules. When row-producing evidence is unavailable, emit a typed zero-row projection. Malformed non-null documents, contradictory authored rules and unresolved source identities still require correction; the partial allowance does not make those valid. Additional lookups named by Mapping are checked under the same governed eligibility.

The backend resolves foreign SQL coordinates, physical columns/types, batch declarations, key/audit population, the originating SourceSystemID value and eligible lookup inputs. Mapping still owns business rules, exact predicates, grain, precedence and any runtime placeholder semantics. A derived view cannot turn ambiguous prose into a confirmed decision.

## Concise examples

Fictional confirmed case: Customer preserves a separate record per `(SourceSystemID, CustomerCode)`. CRM and ERP IDs are disjoint; codes are unique/nonblank within each System. The applied target and source definitions supply actual types and order. No batch filtering or cross-System customer unification is required in this example.

CRM Object inner document:

```json
{
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
}
```

CustomerCode Attribute inner document:

```json
{
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
}
```

Other example field rules: CustomerName returns `NULLIF(TRIM(c.display_name), '')` as nullable STRING; SourceSystemID returns the verified registered `c.source_system_id` as BIGINT. Include their exact Attribute lineage in the actual documents. The CustomerID rule says database-generated, omitted from SELECT; each framework field has its own corresponding omission rule. These examples illustrate inner documents, not complete table coverage.

ERP receives its own documents using the actual ERP source columns and the same final target projection. Source-specific field differences remain in those Attribute rules. The Mapping does not assign file names.

## Document quality checks

These extend the structural checks in [Mapping records](mapping.md). Template/reference checks run locally; grain, transformation fidelity and business meaning require agent review. The [local validation](../local-validation.md) distinguishes enforcement.

| Rule | Check / reason |
|---|---|
| `mapping.template` | Exact agreed keys, permitted nulls, key order and installed template selection; no invented fields or hidden unknown logic. |
| `mapping.lineage` | Every actual query input/Attribute exists and is eligible; SQL names, aliases and self-join roles resolve. Supporting Objects are not automatically read. |
| `mapping.steps` | Implementable ordered operations, exact predicates/filter placement and available intermediate columns; no contradictory repeated field rules. |
| `mapping.grain` | Joins, grouping and deduplication preserve the declared grain/key; any winner, tie or missing-lookup policy is evidenced. |
| `mapping.types` | Source/target semantics, casts, precision, formatting, null/default/invalid-value behavior agree. |
| `mapping.projection` | Full active bound Attribute coverage per System; final explicit columns end at SourceSystemID, own surrogate/framework fields excluded only from SELECT. |
| `mapping.branches` | Same target shape and explicit cross-System identity/reconciliation policy; file layout does not alter semantics. |
| `mapping.orders` | Object order satisfies named prerequisites; contribution order, System list order and Attribute ordinal do not schedule execution. |
| `mapping.consumer` | Complete consistent Mapping view supplies every fact needed to write code and judge it, without reinterpreting upstream model design. |

Review source → Object step → Attribute rule → final column, then derive the expected grain, key, null and reconciliation behavior using only the saved Mapping view. A structural pass does not prove business correctness. Save supported partial transformations and leave missing documents blank; Code may preserve them as explicitly reviewed placeholders, while Validation remains blocked until Mapping is complete. Optional SQL retains the shared query policy.

## Source pointers

Exact template: `database/seed/07_global_mapping_output_templates.template.sql`. Record contract: [Mapping records](mapping.md). Runtime/code conventions: [SQL generation](../code-generation/sql.md). Complete-context projection: `web_app/backend/gds_workbench_api/features/workflows/authoring/downstream_inputs.py`; underlying eligibility projections: `database/11_workflow_eligibility.sql`.

Atlas uses the current published template. Confirm runtime coordinates from the saved Entity schemas and governed source context. The governed consumer view and shared local checks implement the corresponding technical boundaries; semantic review remains necessary.
