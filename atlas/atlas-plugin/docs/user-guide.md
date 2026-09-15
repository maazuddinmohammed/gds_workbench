# atlas user guide

Atlas provides metadata and data-modeling skills, shared references, local helpers and Workbench. The companion VS Code extension handles governed Stage. Start with [installation and runtime](runtime-guide.md); the examples below show normal conversation, not commands you must memorize.

## Start

For the completed plugin, use natural language:

```text
Start atlas.
```

Atlas asks only for missing selections:

| Selection | Question / behavior |
|---|---|
| Tenant | Which Tenant are you working on? Enter its name/code, or say "list tenants." |
| Folder | Supply an absolute path or reuse the saved workspace. If neither is available, atlas states that it is using the current directory before setup. |
| Workflow | What would you like to do? A clear request selects the matching workflow. |
| Model | Asked only when needed. Enter a name/ID, or request the available Models. |
| SQL | Never, Essential, or Proactive. Essential resolves blocking evidence gaps; Proactive also permits useful investigation. |
| Environment | When needed: `dev` (default), `qa`, `stg`, or `prod`. |

The workflow choices are metadata authoring, metadata enrichment, logical build, target registration, entity binding, mapping, Gold build, code generation, validation, process metadata, and Custom. Custom covers requests outside the named workflows, with inputs determined from the requested outcome. Logical and Gold builds each offer **Guided** or **Grill Me**, routed to separate skills. The [entry skill](../skills/atlas/SKILL.md) selects the appropriate workflow; all share context, record rules and the submission lifecycle.

Existing workspace information is shown before repeated questions. If unfinished work makes intent unclear, atlas asks: "Would you like to resume this task or start new work?"

To provide the known selections together:

```text
Start atlas.
Tenant: [tenant name or code]
Working directory: [absolute path]
Workflow: logical build — Guided
Model: [model name]
SQL policy: Essential
Environment: dev
```

Say "List the tenants I can access" or "List models for this tenant" when you need choices. Supplied names are resolved without making you select them again. Atlas reuses a valid saved directory; otherwise, an omitted directory uses the current directory after Atlas tells you. A supplied invalid directory needs correction.

The selected workflow determines which snapshots are required and prepares them without overwriting pending work. For authoring/review, Atlas then opens or reuses the local Workbench for the workspace and continues that workflow. Simple read-only explanations do not need a Workbench launch; you can request it explicitly. Starting Atlas does not regenerate existing outputs or approve data changes.

## Workbench workspace

Each working directory holds one primary Tenant and, when needed, one active Model. Use separate directories for other Models. Model-derived work can edit Metadata owned by several Tenants in the same directory: Atlas keeps their Snapshots, drafts and receipts in separate owner subfolders. Workbench shows the selected Metadata owner; the Model stays unchanged. Each owner still has a separate server Change Set and Apply.

In Workbench, choose **Open working directory** and select the folder containing `.atlas`. Workbench shows the saved context and existing drafts. You can review and edit local changes; the agent uses those same files. Snapshots remain the applied baseline.

**Save local changes** saves a proposal. **Reload local files** reads changes the agent has written; it does not fetch a fresh Snapshot. Conflicting edits require resolution before saving. Local save, validation, review, Stage and Apply remain separate steps.

The approved table design keeps the glassy surrounding interface, with larger text, clear columns and full record details. **Validate locally** keeps its existing review/correct/revalidate flow. **Generate DBML** uses the complete Model Snapshot plus saved local changes, regardless of the table's current filter or page; unsaved edits must be resolved first. The generated files will have a readable DBML preview.

The bundled Atlas Workbench supports local review/edit, shared validation and DBML from Snapshot plus pending changes. See [Workbench design](workbench-design.md).

## Custom requests

```text
Start atlas with a Custom request.
Tenant: [tenant name or code]
Working directory: [absolute path]
Explain why [local SQL file] produces duplicate order lines.
Use the supplied files; do not execute queries.
```

Custom can investigate supplied code, reverse engineer logic, explain a model or explore source data. Atlas selects a short approach from the requested outcome and asks only for missing facts. Model/snapshots/SQL selections are conditional; explaining a supplied file does not require downloading every snapshot or changing that file.

When the request fits an existing workflow, Atlas uses its instructions or relevant reference with the same context. Custom is separate from the dedicated Logical/Dimensional Grill Me workflows. It preserves the same scope, record protection and review/Apply rules. See [Custom](../skills/atlas-custom/SKILL.md).

## Existing work and regeneration

Dimensional Build, Target Registration, Binding, Mapping, Code Generation, Validation authoring and Process metadata inspect existing work before creating replacements. Atlas shows what is new, affected, reusable or protected and resolves your scope once for the related work. An explicit request in the conversation already supplies that choice.

After known model changes, the question is:

> New or affected: Customer — Email added; customer.sql — output column added. Update these items, or select a subset from this list?

Choices: **Update affected** or **Choose affected items**. Atlas does not offer a blanket rebuild of unchanged work for this change-driven request. You can explicitly request broader regeneration. A key/lookup change may affect other targets; Atlas explains those dependencies before expanding the selected work.

For a general request with existing outputs and no specific change, choices are **Reuse existing**, **Selected items**, or **All in scope**. With no existing outputs, choose **All listed targets** or **Selected targets**. Missing history stays visible; it does not justify assuming all work is fresh or rebuilding everything.

Unchanged work and manual edits are preserved. Regeneration does not unlock records, drop/recreate physical tables or execute Validation checks. The detailed rules live in the shared [working method](../references/working-method.md#existing-work-and-update-scope).

## Metadata authoring

Use this workflow to add or change Objects, Attributes, ingestion mappings, Copy Groups, Member Groups, Copy controls, Copies, Process Groups, or Processes. The selected Tenant, System, Connections, and lookup values must already be registered.

Example prompt; replace bracketed values:

```text
Use atlas for metadata authoring.
Tenant: [tenant code]
Working directory: [absolute path]
Set landing-file naming for [Copy Group and Copy endpoints]
using the verified convention from [existing working Copy].
Preserve the other settings.
```

For a larger request:

```text
Use atlas for metadata authoring.
Tenant: [tenant code]
Working directory: [absolute path]
Register the Source Objects and Attributes from [schema export path]
under [registered System and Connection].
SQL policy: Never.
```

Atlas resolves the requested records and missing definitions, prepares required metadata context, and opens/reuses the local Workbench when the runtime is available. You review proposed changes and actual validation findings before governed submission/Apply. Generating DDL or Process configuration does not execute it.

New editable records with an is_active field default to true unless you request otherwise. Atlas preserves existing activation values during unrelated edits. Copy order defaults to 1 and currently only controls sorting. Process Group dependency order also defaults to 1 and remains editable outside the group's natural key; the Atlas-compatible backend accepts equal Copy orders. Existing installations need an explicit upgrade and historical order review; see the [compatibility note](../references/metadata/tables/copy.md#copy-order-and-default).

Renames and other changes to existing natural-key fields require a manual database correction by you. Atlas supplies instructions and dependency checks; it does not perform or simulate the rename. After you complete it, Atlas refreshes the Snapshot before continuing affected work.

Attribute `is_mapped` and `is_purge` are currently unused downstream. Atlas defaults them to false on new records and preserves existing values during unrelated edits.

For SQL Source and Bronze, `attribute_custom_code` supplies a complete SELECT expression, including any required cast and output alias. Empty code uses the column unchanged; Bronze adds no automatic STRING cast. See the [expression examples](../references/metadata/tables/attribute.md#custom-select-expressions). Silver/Gold custom code and the unused `object_transformation` field default to null on new records.

Ingestion requires Copy Group, Copy and Object Mapping to be active. An inactive Copy Group skips all its Copies without rewriting their flags. Multiple Source Objects can feed one Bronze Object. Bronze metadata chooses the loaded columns and expressions, so extra Source fields, constants and an empty Attribute Mapping dataset are valid. Source file transfer copies contents unchanged; Source custom code applies to relational SQL extraction, with API support depending on the connector. Bronze may transform data after it lands.

Member-based execution is deferred: new Copy Groups use is_member_group_required=false. New controls use null Member Group, last-run time and last-run value; the framework maintains run state afterward. Populate the initial-load date only when the load configuration needs a specific filter date; otherwise use null. Preserve existing state during unrelated edits. The separate Member table is listed for later schema and tool coverage.

Chunking is optional: request it explicitly for a large table, then Atlas selects applicable registered logic from its description. Target Data Operation selects the loading function; Copy Into appends. The source operation is required but unused. Initial/incremental SQL fields contain complete WHERE fragments, such as `WHERE status = 'active'`; the framework inserts the value as supplied. Empty fields add no filter.

Record-limit fields are parameters for the selected chunking logic. Filename/pattern fields control intermediate landing names in Source → landing → Bronze. Atlas proposes defaults from verified working conventions; for custom or unclear behavior, it asks for the relevant orchestration code or an example and checks how the fields are actually consumed. Existing values are preserved during unrelated edits.

The external pipeline takes one Tenant name, comma-separated System names, and optional Copy Group/Member Group selectors. Null group selectors include all applicable groups; activation gates still apply. Copies load Source → landing → Bronze, then linked Process Groups supply the Processes. All selected Silver Process Groups finish successfully before Gold starts. Within each Zone phase, the agreed design adds process_group_dependency_order: equal-level groups pool Processes across Systems, running each Process execution order in parallel and waiting for all invocations to succeed before advancing. The next dependency level waits for the current level to finish successfully. See [pipeline selection](../references/metadata/tables/copy-group.md#pipeline-selection) and [execution behavior](../references/metadata/tables/process.md#execution-behavior). The field is accepted by the Atlas-compatible schemas; applying the metadata does not deploy orchestration code.

The orchestration runs a shared executable once within the same execution stage. You may register it again at a later order: for example, order 1 populates IDs and order 3 resolves a self-lookup using those IDs. Atlas preserves both registrations; execution remains the orchestration framework's responsibility.

Process Type identifies SQL or Python logic. Process location is the file path; executable is the actual filename including .sql or .python. Atlas uses the registered type and preserves the supplied filename. A Process has no independent stored Zone: its payload's zone_code identifies its Process Group. Target Object and group Zones normally match, but cross-Zone cases remain allowed without an equality validation rule.

## Metadata enrichment

Use enrichment to improve three fields: Object description, Attribute description and Attribute inferred data type. Select Objects through Tenant/System/Zone context or an existing Model's Input Scope. A Model is optional for direct selection; it supplies scope rather than changing where enrichment values are stored.

Example with an explicit update policy:

```text
Use atlas for metadata enrichment.
Tenant: [tenant code]
Working directory: [absolute path]
System: [originating system name]
Zone: bronze
Objects: [object names]
Fill missing descriptions and inferred data types.
SQL policy: Essential.
```

For Model scope, replace the System/Zone/Object selection with: `Use all active Objects in the Input Scope of [model name].` Atlas resolves exact metadata keys and ownership before editing.

Atlas gathers Tenant/System/Connection context, studies the Object and its columns, resolves meaningful questions using permitted evidence, describes the Object, then its Attributes, and infers types separately. Descriptions explain the data's meaning without generic Zone labels. Physical types remain unchanged. See the [concrete workflow](../skills/atlas-metadata-enrichment/SKILL.md) and [quality examples](../references/metadata/enrichment-quality.md).

By default, Atlas takes Zones from your request or Model scope and asks when neither supplies them. It includes active, unlocked Attributes of the selected Objects and fills only missing descriptions/types. Existing values change only when you request improvement/replacement. Unresolved meanings stay visible; parent Object locks still protect Attributes. Related local edits are accumulated and reviewed together.

## Logical build

Example prompt:

```text
Use atlas for logical build — guided.
Tenant: [tenant code]
Working directory: [absolute path]
Model: [model name]
SQL policy: Essential
```

Atlas reuses supplied context and asks for missing choices. It checks existing session/work before starting new work, then offers fresh or existing Metadata/Model Snapshots when suitable existing inputs are available. Pending changes are preserved and reconciled before any baseline replacement.

If the approach was not supplied, Atlas asks: "How do you want to build this model?" Choose **Guided** or **Grill Me**. Atlas then loads the selected skill. The same choice applies to Dimensional/Gold Build once its workflows are finalized; it does not use Logical Build's sequence automatically.

The [Guided skill](../skills/atlas-logical-build-guided/SKILL.md) follows Profiling → Analysis → Conceptual → Logical. At profiling, Atlas asks whether to start if results are missing, or whether to reuse, redo all selected Objects or redo specific Objects if profiles exist. Missing Analysis, Conceptual and Logical results start automatically once prerequisites are met; existing results prompt a reuse or redo/revise choice. Partial coverage is shown explicitly, and earlier answers are reused.

The [Grill Me skill](../skills/atlas-logical-build-grill-me/SKILL.md) uses a modeling interview grounded in your scope and saved Model: inspect evidence first, recommend answers, test concrete scenarios and develop agreed parts with you. Both skills share domain references, SQL policy and the Change Set lifecycle. Guided does not load the interview instructions. A separate GrillMe installation is not required.

Example Grill Me prompt:

```text
Use atlas for logical build — Grill Me.
Tenant: [tenant code]
Working directory: [absolute path]
Model: [model name]
SQL policy: Essential
Interview me about the Sales model. Start with Orders and Order Lines.
Inspect the existing scope first. Recommend answers and challenge
grain, customer identity and lifecycle with concrete examples.
Build each agreed part locally as we go.
Reuse existing evidence and preserve unrelated model records.
```

Atlas asks only for a missing outcome or starting scope, proposes a short approach, then works through a meaningful part with you. Grill Me uses Profiling, Analysis, Conceptual and Logical methods as needed; it does not require every intermediate artifact. It resolves consequential decisions in dependency order, normally one at a time, grouping related clarifications when helpful. Answers become concise task decisions and relevant Model definitions; Assertions are used only when useful. Scope/prerequisite rules and local validation still apply.

You can ask it to continue through the agreed plan independently. Completed parts accumulate locally; a discussion or part boundary does not trigger Stage/Apply. Before completing the request, Atlas reviews coverage and coherence across all parts. Switching between the Guided and Grill Me skills preserves existing work.

For profiling, supply batch IDs by originating System, for example:

```text
Profile the selected Model inputs.
For CRM, use batches 10 and 11.
For ERP, use batch 27.
```

Atlas applies those selections only to Objects with a registered batch Attribute. It asks for missing batch choices together by System; an explicit Object choice can override the System choice. Batched Objects use IN even for one ID. Unbatched Objects have no batch filter. Missing batch IDs never silently become an all-batches query.

Selecting several batches measures their combined stored rows; it does not remove repeated records or reconstruct the latest state. Atlas generates a JSON plan and bounded SQL files, reads and executes each permitted query group through Databricks, then saves validated aggregate profiles locally. SQL Never allows preparation without execution. See the [profiling guide](../references/logical-build/profiling.md).

If the profiling generator fails, the agent can write equivalent SQL and prepare the same query files and plan. The fallback keeps the selected batches, metric definitions, SQL policy and result checks. Missing batch choices or access still require resolution.

Relationship analysis considers all Objects in the Model's scope. Clear names, roles and business context can establish an inferred relationship and cardinality without SQL, such as Orders.customer_id referencing Customer. A separate pass checks string types/categories/statuses and differently named lookup references. SQL is used selectively under your policy; any queries retain each endpoint's approved batch selection. A category without a real scoped reference Object remains a modeling suggestion. See [finding relationships](../references/logical-build/find-relationships.md).

Atlas distinguishes inferred business cardinality from measured multiplicity. It saves both using the existing Analysis record format: metadata-only inferences keep all measurement fields null and explain the conclusion in the basis. Composite keys remain intact in evidence because the current record has only one Attribute per endpoint.

Record payloads use registered codes, not database IDs. Object source_tenant_code identifies its owner; tenant_code in the physical key identifies its Connection's Tenant. These may differ in Bronze/Silver/Gold. For an explicitly shared Silver Object, the configured GDS Tenant may also be the chosen owner. See the [ownership examples](../references/metadata/tables/object.md#ownership-and-physical-identity).

### Conceptual modeling

Atlas identifies business meanings and grain, checks existing concepts and aliases, then consolidates equivalent meanings. CRM customers and ERP customer master may support one Customer concept. Sales accounts and ledger accounts remain separate when their meanings differ. Multiple Objects can support one concept, and one Object may support several.

It then defines business relationships, preserves distinct roles such as billing and shipping, and explains cardinality. Clear metadata can support inference without SQL; uncertain cardinality stays unknown. Classifications may use their owning Object as support without inventing a physical lookup table.

Concepts and relationships are saved as two local Model datasets with nested supports. Each support references an actual scoped Object or applicable Assertion Record. Intentionally independent concepts may have no physical support; Atlas explains their basis instead of fabricating evidence. New concept and relationship names use PascalCase by default, such as Customer and Places. Atlas validates schema, exact references, scope, protection and business coverage before completing the phase. See [business-concept steps](../references/logical-build/business-concepts.md) and [complete payload examples](../references/model/conceptual.md).

The current schema rejects conceptual self-relationships. Atlas records such needs for review instead of duplicating concepts to make them fit. Logical Attributes, keys, normalization and audit columns follow in the Logical phase.

### Logical modeling

Atlas defines each Entity's grain and business identity, decides what belongs together, then designs Attributes, relationships and lineage. The [normalization guide](../references/logical-build/normalization.md) includes all twelve agreed decision factors. Repetition alone does not force a lookup table; historical transaction values remain distinct from current reference values. A surrogate does not replace business uniqueness.

Confirmed defaults, unless you choose an override:

- PascalCase modeled names. Identifier suffix `ID` stays uppercase; ordinary Attributes remain names such as CustomerName.
- Each new table starts with a generated BIGINT surrogate: CustomerID for Logical, CustomerKey for Dimensional. Foreign keys are mapped values, not generated identities.
- The complete existing GDS audit block follows business fields and applicable Source audit fields. Actual types/nullability come from the Model's configured template; missing definitions are resolved before completion.

The [key/audit guide](../references/model/keys-and-audit.md) gives the exact column order and population ownership. All intended columns remain in the Model, DDL and Binding. Load SQL excludes the own surrogate and nine framework fields, while supplying SourceSystemID from registered provenance. Existing backend projections still need alignment with these defaults.

Submodels group meaningful business subjects where useful. A small Model need not have artificial groups; a broad Model can use several. An Entity can belong to Sales and Service without being duplicated. Cross-group relationships remain visible.

Calendars and justified fixed-value tables may be designed independently with empty sources. Assertions are optional for useful user/documented business rules; Atlas does not invent them for every generated field. Source-derived outputs retain real Object/Attribute lineage so Mapping and Code can use it. Generation, constant values and provenance still need a supported downstream population method.

Local checks include actual Attribute endpoints, compatible keys, source coverage, active memberships, locks, column order and audit policy. Each Attribute's physical source also needs its corresponding Object source on the Entity. Structural validity is followed by review of grain, identity, historical meaning, consolidation, relationships and coverage. See [logical-design steps](../references/logical-build/logical-design.md) and [record examples](../references/model/logical.md).

## Dimensional build

```text
Use atlas for Gold build in Guided mode.
Model: [model name]
Business process: order sales
Questions: sales amount and quantity by customer, product and order date
Reuse compatible existing dimensions; update only affected work.
```

Atlas reuses the current workspace and applied Logical Mapping/Silver context. It works through the business purpose, what one row represents, dimensions, facts, history/relationships and quality review. It does not automatically repeat Logical profiling or create Gold tables for every Silver table. A dimension-only request, such as a calendar, skips fact-specific steps.

Choose **Grill Me** for collaborative decisions in smaller parts:

```text
Use atlas for Gold build in Grill Me mode.
Help me design sales reporting from the eligible Silver model.
Start with order-line grain and customer history.
```

Both skills share the same modeling rules. Atlas reuses compatible dimensions, distinguishes date roles, checks aggregation and prevents joins from multiplying measures. Standalone dates/constants are valid without fabricated sources. PascalCase, first-column generated BIGINT keys ending in Key, and the agreed audit block remain defaults.

The framework supports Type 1 and Type 2. Atlas chooses the appropriate design from reporting needs and asks about unresolved consequences, such as current versus sale-time customer segment. The framework populates Type 2 fields using natural keys; the GDS seed calls them `EffectiveFrom`, `EffectiveTo` and `IsCurrent`. Atlas uses the actual configured names, keeps these fields in the Model/DDL/Binding and marks them framework-populated in Mapping, omitted from transformation SQL. They remain separate from the shared `IsActive` audit field.

Atlas saves the related Dimensional work locally, validates it and follows shared review/Stage/Apply. Gold registration, Binding and Mapping are subsequent requested workflows. See [Guided](../skills/atlas-dimensional-build-guided/SKILL.md), [Grill Me](../skills/atlas-dimensional-build-grill-me/SKILL.md), [design rules](../references/dimensional-build/design.md), [history](../references/dimensional-build/history.md) and [exact record fields](../references/model/dimensional.md).

## Target registration

Use selected applied Logical Entities for Silver targets or applied Dimensional Entities for Gold targets. Example:

```text
Use atlas for Silver target registration.
Tenant: [source/data tenant code]
Working directory: [absolute path]
Model: [model name]
Entities: Customer, Order, OrderLine
Target schema: sales
DDL: selected tables — Customer, Order
```

If no schema was supplied or already agreed, Atlas asks: "Which schema should these targets use?" One schema is the default assignment. You can instead specify, for example, "Customer in crm; Order and OrderLine in sales." Atlas resolves any unassigned Entities without guessing a split.

Silver/Gold physical Objects belong to the configured GDS Connection. Their source_tenant_code retains the actual source/data owner; the physical key uses that GDS Connection's Tenant/System/Connection. Mixed targets use the explicit ownership rule already agreed in [Object ownership](../references/metadata/tables/object.md#ownership-and-physical-identity). Atlas does not silently replace the owner with the Model Tenant.

Before DDL generation, unless already answered, Atlas asks: **"Do you want creation DDL?"** For a known change-driven update, choices are **No DDL**, **Affected targets**, or **Selected affected targets**. For a general DDL request, the choices are:

- **No DDL** — prepare target Metadata only.
- **All registration targets** — generate DDL for all Entities selected for registration.
- **Selected tables** — provide Entity/table names.
- **Entire model** — use the current Model or name another Model and the required Silver/Gold layer.

DDL selection and Metadata registration scope are separate. A wider or different Model selection requests SQL files only for those additional targets; it does not add Metadata changes or trigger Stage/Apply. Atlas resolves missing schema assignments and includes every intended column in each selected table's DDL. Generating SQL needs no evidence-query permission; execution remains separate.

Atlas derives complete Object/Attribute metadata and any requested creation DDL from the same target definitions. It includes all modeled columns, compares existing registrations, preserves locks and shows differences for review. DDL follows existing GDS conventions: `CREATE TABLE IF NOT EXISTS schema.table` without catalog, an identity only for the table's own surrogate, and all audit columns. Natural-key changes remain manual. Applying Metadata does not execute DDL; existing-table differences require their own supported resolution.

The shared lifecycle validates/reviews locally, stages and validates on the server, then applies the separately approved content. Before Apply, Atlas checks freshness and reconciles any required refresh without discarding the draft. After successful Apply, it installs a fresh Metadata Snapshot. It stops before Entity Binding. Current Binding ownership restrictions are checked before calling a target ready for that next workflow; see [registration instructions](../skills/atlas-target-registration/SKILL.md).

## Entity Binding

After target registration is applied and confirmed in a fresh Metadata Snapshot:

```text
Use atlas for Entity Binding.
Model: [model name]
Bind Customer, Order and OrderLine to their registered Silver targets.
Use the target assignments from registration.
```

Reuse the existing workspace context; specify Tenant and working directory if starting a new session. For Gold, select Dimensional Entities and their registered Gold targets.

Atlas matches each Entity within its confirmed GDS Connection and target schema, then matches modeled Attributes to registered columns under that Object. It uses exact normalized names or explicit registration overrides. Unique compatible matches proceed directly to a local draft; it asks only about ambiguities, missing/incompatible columns or intended reassignment.

Every active modeled Attribute and every active registered target Attribute must be bound exactly once, including generated keys, audit fields and constants. Extra target columns require an upstream decision; Atlas does not invent modeled Attributes or discard columns to make coverage pass. Existing valid Bindings and protected records remain preserved.

Binding writes two Model datasets and follows the shared local validation, Workbench review, Stage, server validation and Apply process. After verified Apply, Atlas refreshes the Model Snapshot and stops before Mapping. Name matching needs no SQL; Binding establishes registered storage assignments, not source transformations or proof that physical tables were deployed. See [Entity Binding](../skills/atlas-entity-binding/SKILL.md) and its [record contract](../references/model/binding.md).

## Mapping

After Entity Binding is applied:

```text
Use atlas for logical mapping.
Model: [model name]
Target: Customer
Source Systems: CRM, ERP
Keep source-qualified customer records separate.
Use the existing GDS mapping template.
```

Reuse the current workspace context. For Gold, request Dimensional Mapping to the bound Gold targets. The example's separate-identity rule is a user choice, not a universal customer-model default.

Atlas resolves model supports, target bindings, source identities and field definitions while authoring. It prepares one Mapping branch per target/System using the unchanged GDS templates: **Object sources + short ordered steps**, then **Attribute sources + one field rule**. Keys, joins, filter placement, dependencies and cross-System identity/reconciliation must be explicit. File grouping is chosen during Code Generation.

Every active bound target column has a Mapping, including generated keys and audit fields. Mapping identifies the own surrogate and framework fields as omitted from load SQL; business fields and selected Source audit fields are projected in target order, with `SourceSystemID` last. It does not invent generated-field expressions or source lineage.

Coding and Validation will receive a complete Mapping view containing instructions, resolved target/source metadata, physical column names/types/order and dependencies. The agent need not traverse the model to rediscover the design. The governed `read_mapping_context` reader supplies revision/digest-bound components and reports missing context. Short instructions stay in Mapping documents; structured technical context is assembled rather than manually copied into a prose handoff.

Atlas asks only about unresolved business or runtime rules, validates the complete local batch and follows shared review/Stage/Validate/Apply. After verified Apply, it refreshes the Model Snapshot. See [Mapping workflow](../skills/atlas-mapping/SKILL.md), [exact records](../references/model/mapping.md) and [templates/examples](../references/model/mapping-documents.md).

## Code Generation

After Mapping is applied, request the desired files explicitly:

```text
Use atlas for Code Generation.
Model: [model name]
Targets: Customer, Order
Language: SQL
Files: one per target, containing all contributing Systems
```

Alternatively specify `Files: separate per System and target`, with target-specific exceptions if needed. Atlas asks which grouping you want unless you already supplied the choice, then shows concrete filenames and Systems. It does not assume a file-layout default.

**The first release generates SQL.** New Python generation is deferred until its consumer contract is established. Existing Python artifacts and assignments remain preserved; Atlas does not silently convert them to SQL. See [release scope](../references/release-scope.md).

A Model Snapshot already contains saved Code text in its Code JSONL records; it does not regenerate SQL or automatically write standalone files. Atlas reads that content together with pending changes and local file edits before offering reuse or selective regeneration. Extracting an existing saved file is different from generating new logic. See [saved Code in snapshots](../references/snapshots/model.md#saved-code-and-local-files).

Atlas consumes the complete Mapping view, translates Object steps into self-contained temporary views and applies Attribute rules. Each file ends with the exact ordered target SELECT through SourceSystemID. The own surrogate, framework audit fields and applicable framework-populated Type 2 fields are omitted. Natural-key values remain supplied as mapped. The framework performs loading; generated transformations do not contain target DDL or INSERT/MERGE statements.

Separate files cannot depend on temporary state from each other. Combined files implement Mapping's explicit branch reconciliation. Every mapped System is assigned to exactly one active file for that target. Missing transformation decisions return to Mapping; Atlas does not invent them inside generated code.

Atlas checks SQL syntax and behavior against Mapping, preserves locked/unaffected artifacts and keeps local file text aligned with the Model Change Set. Live probes are optional under SQL policy and authorization. You review the final content through the shared Stage/Validate/Apply process. Applying Code stores it; deployment and execution remain separate. See [Code Generation](../skills/atlas-code-generation/SKILL.md), [SQL structure/examples](../references/code-generation/sql.md) and [artifact fields](../references/model/generated-code.md).

## Validation

```text
Use atlas for Validation.
Model: [model name]
Layer: Silver
Systems: CRM
Targets: Customer, Order
Update: new or affected checks only
```

Atlas reuses workspace context and applied Mapping. It reads current Code when testing transformation implementation, then shows affected, reusable and protected checks. Explicit selections in your request are reused.

Atlas decides whether each useful check belongs on transformation output or a loaded target. It uses both only for distinct failures, without asking you to choose a general mode. You can still request a specific scope. It asks only for missing System, load/window or business facts needed to write meaningful checks.

Atlas groups checks by **technical purpose** or **functional feature**, scoped to a target or System where useful—for example, `SilverCustomerTechnicalIdentity` or `SilverOrderFunctionalPricing`. Each Check tests one meaningful claim. Reconciliation fits the relevant feature; there is no automatic checklist for every column/target and no fixed check count. Redundant or already-proven checks are omitted; simple checks remain when they detect a real risk.

Checks use complete keys, aligned populations and deliberate empty/null behavior. Equal row counts alone do not prove correct keys or values. The proposal explains each check's purpose briefly so you can review the coverage.

Checks are saved as Validation Groups and Checks through the shared local review/Stage/Validate/Apply process. Existing selected-update rules and locks apply. SQL preflight is optional under policy and authorization; applying definitions neither runs their SQL nor schedules them. Local record validation, actual SQL evidence and unexecuted assertions are reported separately.

See [Validation workflow](../skills/atlas-validation/SKILL.md), [check design](../references/validation/check-design.md) and [exact fields/examples](../references/model/validation.md). Saved Validation queries use verified catalog-qualified coordinates; transformation Code keeps its framework coordinates. The first release authors checks without adding an external execution/comparison service.

## Process metadata

```text
Use atlas for Process metadata.
Model: [model name]
Layer: Silver
Targets: Customer, Order
Runtime location: [confirmed framework path]
Use the existing Process and Copy Groups where applicable.
Register only new or affected artifacts.
```

Atlas derives filenames, target bindings and contributing Systems from applied Code and Mapping. It reuses confirmed runtime details and asks one consolidated question only for missing locations, ambiguous Copy Group links or unresolved execution order. It preserves the file grouping already chosen during Code Generation.

You review a compact assignment: **System → Copy Group → Process Group/Zone → dependency level → Process order → file location/name → target**. Existing confirmed assignments are reused. Related Group/Process records accumulate in one local Metadata Change Set and follow the shared review/Stage/Validate/Apply process.

Changing an existing Process's order, path or filename changes its natural key and therefore requires your manual database correction. An intentional additional execution at another stage remains a new registration. Mapping orders are not automatically copied into Process orders, and Process Group dependency order uses the separate agreed field.

Registration does not deploy files, create triggers or run the pipeline. A code-text change alone does not create a new Process. See the [Process metadata workflow](../skills/atlas-process-metadata/SKILL.md), [Process fields and execution rules](../references/metadata/tables/process.md) and [Process Group fields](../references/metadata/tables/process-group.md).

## Protected and inactive records

Every workflow follows the same [record-state rules](../references/record-state.md). Locked records remain unchanged; a Metadata Object lock also protects its Attributes and prevents additions. Active locked inputs can still be read and used. Unlocked records remain subject to scope and validation. Inactive/deprecated records are preserved and are not silently reactivated.

After each authored phase's local batch, Atlas runs [local validation](../references/local-validation.md) and repairs failures before treating it as complete. Attribute endpoints must actually exist and satisfy the workflow's scope rules; conceptual endpoints must resolve to real Concepts. Local checks and SQL evidence answer different questions.

## Work locally, then submit

When starting metadata authoring, Atlas obtains a fresh Metadata Snapshot. It keeps that baseline throughout the related local work, including multiple tasks and edits. Resuming unfinished work preserves its baseline and draft; refreshes are reconciled rather than installed over pending changes.

The Snapshot stays unchanged. Atlas writes proposed records to `metadata-change-set/` or `model-change-set/` and reads the effective result: the Snapshot plus pending changes. This lets related records be authored and validated together before submission.

Complete the related local batch, then follow the shared [Change Set lifecycle](../references/change-set-lifecycle.md):

1. Atlas validates locally and shows the proposed changes and findings in Workbench.
2. You review that content in Workbench and acknowledge it in the agent conversation; the agent uses the VS Code extension to Stage it to a server Change Set.
3. Atlas verifies staging and runs server validation.
4. You review the complete server changes and approve Apply separately.
5. Atlas applies, verifies the result and refreshes context before dependent work needs the applied values.

Stage saves proposed changes to a server draft; Apply persists the validated changes. Neither is a Git commit or push. A new task, local edit or bounded helper call does not trigger another Apply. Metadata and Model Change Sets remain separate.

For Stage, open the working directory in VS Code with the matching extension enabled. The agent prepares the approved manifest and supplies its path/digest to the extension; you do not copy payload records. The host may show a Stage confirmation. If the current host cannot access the extension tool, Atlas retains the local work and identifies the supported submission host needed. See [extension readiness](../references/change-set-lifecycle.md#extension-readiness); current GDS commands are implementation references until Atlas packaging and workspace support are delivered.

Shared guides explain [Metadata Snapshot files and editing](../references/snapshots/metadata.md) and [Model Snapshot files and editing](../references/snapshots/model.md). Workflows reuse these rules instead of defining their own file readers.

## Resume

```text
Resume atlas in [absolute path].
```

Atlas reports the current outcome, unfinished work, blockers, and next action. Starting new work preserves unfinished artifacts.

## Where to find details

- [Atlas entry](../skills/atlas/SKILL.md): startup, existing-context reuse and workflow selection; [Custom](../skills/atlas-custom/SKILL.md) adapts to other requests.
- [Working method](../references/working-method.md): saved context, tasks, temporary files, snapshots, handoff.
- [Workspace contract](../references/workspace-contract.md) and [release scope](../references/release-scope.md): file fields, owner subfolders, supported hosts and acceptance checks.
- [Record state](../references/record-state.md) and [local validation](../references/local-validation.md): shared protection, scope, reference checks and repair sequence.
- [Change Set lifecycle](../references/change-set-lifecycle.md): local checks, Workbench review, extension staging, server validation and Apply approval.
- [Extension design](extension-design.md): module responsibilities and behavior-preserving refactor plan.
- [Metadata Snapshot](../references/snapshots/metadata.md) and [Model Snapshot](../references/snapshots/model.md): files, targeted reads, local drafts and refresh boundaries.
- [Terminology](../references/terminology.md): shared meanings.
- [Metadata table index](../references/metadata/index.md): all editable tables and read-only reference context.
- [Metadata authoring instructions](../skills/atlas-metadata-authoring/SKILL.md): workflow behavior.
- [Metadata enrichment instructions](../skills/atlas-metadata-enrichment/SKILL.md): context, description quality and type evidence.
- [Logical Guided](../skills/atlas-logical-build-guided/SKILL.md) and [Logical Grill Me](../skills/atlas-logical-build-grill-me/SKILL.md): separate workflows using shared domain rules.
- [Dimensional Guided](../skills/atlas-dimensional-build-guided/SKILL.md) and [Dimensional Grill Me](../skills/atlas-dimensional-build-grill-me/SKILL.md): eligible Silver context, analytical design and shared [Dimensional records](../references/model/dimensional.md).
- [Modeling interview](../references/modeling-interview.md): scope-aware questioning and durable decisions for Grill Me workflows.
- [Target registration](../skills/atlas-target-registration/SKILL.md): schema selection, optional DDL scope, GDS placement and registration boundaries.
- [Entity Binding](../skills/atlas-entity-binding/SKILL.md): name-based matches, exception questions, complete column coverage and local Binding records.
- [Mapping](../skills/atlas-mapping/SKILL.md): per-System branches, concise Object/Attribute rules, dependency order and complete context for Coding/Validation. [Templates](../references/model/mapping-documents.md) retain the existing GDS shape; [records](../references/model/mapping.md) give all outer fields.
- [Code Generation](../skills/atlas-code-generation/SKILL.md): file grouping, Mapping-to-SQL translation and local checking; [Code records](../references/model/generated-code.md) define artifacts/assignments.
- [Validation](../skills/atlas-validation/SKILL.md): selection and definition authoring; [check design](../references/validation/check-design.md) owns expected behavior/populations, and [records](../references/model/validation.md) owns fields/operators.
- [Process metadata](../skills/atlas-process-metadata/SKILL.md): applied artifact assignments, runtime locations, Copy Group links and execution-order review; shared metadata table pages own field and scheduling rules.
- [Query scope](../references/query-scope.md): shared batch selections, coordinates and governed Databricks execution.
- [Business concepts](../references/logical-build/business-concepts.md): conceptual modeling and consolidation rules.
- [Logical design](../references/logical-build/logical-design.md) and [normalization](../references/logical-build/normalization.md): Entity boundaries, keys, sources, standalone structures and Submodels.
- [Naming](../references/model/naming.md) and [keys/audit](../references/model/keys-and-audit.md): confirmed defaults and framework population.
- [Model Change Sets](../references/model/change-sets.md): local authoring and MCP/helper usage; [Profile](../references/model/profiling-profile.md), [Analysis](../references/model/analysis-result.md), [Conceptual](../references/model/conceptual.md), [Logical](../references/model/logical.md), [Assertions](../references/model/assertions.md) and [Binding](../references/model/binding.md) give exact fields and complete examples.

Do not provide credentials or secret values in prompts or task notes. Use registered connections through the configured tools.
