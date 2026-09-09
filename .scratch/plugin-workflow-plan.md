# GDS plugin workflow redesign — review plan

Prepared 9 September 2026. This document consolidates the agreed workflow behavior. It is a plan, not an implementation or authorization to run external systems.

## 1. Interaction and modes

Use three modes:

- **Guided:** the existing orchestrated workflows, with the questions and behavior below. Combines the previous Guided and Automatic modes.
- **Custom:** understand the user's goal, ask focused questions, build a plan, obtain plan approval, then use the appropriate tools and workflows. Combines Quick and Custom.
- **Grill With Docs:** investigate and question more thoroughly using that skill, then produce an approved custom plan. Execution can use the applicable Guided workflows or Custom work without an unnecessary mode-change ceremony.

Infer mode and workflow from clear intent. Otherwise show relevant choices. Reuse supplied answers and approved preferences. Ask for missing information; do not restart intake at every step.

Keep these workflow choices separate: Metadata Authoring, Model Input Scope, Metadata Enrichment, Logical Build, Silver Target Registration, Logical Binding, Logical Mapping, Logical Code Generation, Dimensional Build, Gold Target Registration, Dimensional Binding, Dimensional Mapping, Dimensional Code Generation, Validation Authoring, and Process Registration.

### Guided initialization

1. Resolve missing Tenant, Model where required, and local session directory.
2. Select SQL policy once: Never, Essential, or As needed. Reuse it throughout Guided work. A policy controls permitted evidence gathering; it does not authorize deployment or physical loads.
3. Open the local Workbench once.
4. Create and install the relevant Metadata and Model Snapshots into the session. A Model Snapshot requires a selected Model. Metadata-only work must remain usable without one.
5. Resolve the workflow to enter, reusing any selection already given.

Refresh and extend snapshots when scope changes or applied changes affect later work. For multiple Source Tenants, collect the authorized metadata needed by the selected scope. Notify the user to refresh the existing Workbench when drafts are ready.

### Review and state changes

Prepare complete local drafts, perform functional review and local validation, then present them in Workbench. Follow the established acknowledgement, Tenant Lock, Stage, server validation, and separate Apply approval sequence. Refresh the applicable snapshot before dependent work. Preserve locked, unaffected, and out-of-scope records. Applying authored definitions does not execute data pipelines.

After code generation, resolve the user's next goal. Validation, optional Dimensional work, Process Registration, and finishing are possible destinations when applicable. Do not enter Dimensional or create Validation records automatically unless already included in the user's selected journey.

## 2. Ownership and input scope

- A Model has one fixed owning Tenant.
- Its input scope may include Objects from multiple authorized Source Tenants and Systems.
- Existing physical input Objects retain their source_tenant_id and full physical identity.
- Common Conceptual and Logical models consolidate across Tenants and Systems when business meaning and grain support it. Provenance alone does not justify separate concepts or entities.
- Bronze/Silver/Gold physical placement uses the selected Source Tenant's configured GDS Connection and its actual Tenant/System. Preserve the metadata/user-selected source_tenant_id; propose Model Tenant only as the default for new Silver/Gold. Do not create separate targets merely because contributing inputs belong to different Tenants. Current Binding's same-Source-Tenant restriction is a separate implementation limitation.
- Preserve original source lineage. Model access never grants access to another Tenant's underlying metadata or data.

This changes existing same-Tenant assumptions. Implement it through backend authorization, eligibility, snapshots, session handling, reference resolution, and Change Set validation together. Do not implement it only as plugin prose or a client-side bypass. Preserve governed Change Sets; do not add direct Model Scope mutation or foundational CRUD tools.

## 3. Shared orchestration reference

Keep one canonical, packaged, human-editable reference at plugins/v2/gds/skills/gds/references/orchestration-rules.md. Workflow guides link to its applicable chapters. Repository documentation links to the same authority.

Chapters can grow as behavior is explained: ingestion, mapping/code execution, target definitions, Process execution, and other actual orchestration areas. Avoid inventing an exhaustive taxonomy or requiring every possible rule now.

### Ingestion rules

- Source names and physical types remain actual source definitions.
- Source-to-Bronze correspondence is one-to-one. Bronze physical columns are STRING and lowercase snake_case; resolve normalization collisions explicitly.
- For RDBMS extraction to Parquet, Source selection expressions use dialect-correct quoting and aliasing. For example, an original field Customer Name can be extracted as customer_name while its registered source name stays unchanged.
- Bronze transformations read the actual incoming file field, including any extraction alias.
- A null attribute_custom_code delegates STRING casting to the framework. A populated custom expression must perform its own final STRING cast.

### Framework-executed SQL and DDL

- Persistent relations in framework-executed artifacts use schema.table. The framework selects the catalog. Temporary views remain unqualified.
- Do not apply this catalog omission blindly to direct evidence queries; those must resolve registered execution coordinates correctly.
- A target's own declared surrogate key is BIGINT and generated by Databricks. DDL must express the supported identity behavior. Load SQL omits that key; foreign keys still come from Mapping.
- Generated load SQL projects the approved data columns through SourceSystemID, inclusive. Framework-generated audit columns after SourceSystemID are absent, including absent placeholder expressions.
- Mapping records explain database/framework-populated attributes even though SQL does not supply them.
- Runtime batch placeholders follow the actual orchestration contract. Profiling's selected batch values must not become hardcoded load-script parameters.
- Runtime owns loading and merging. Transformation artifacts produce the target input dataset; they do not perform target DDL, INSERT, MERGE, UPDATE, DELETE, deployment, or scheduling.

### Process selection

- Runtime selection uses Tenant, System, and Copy Group.
- The Copy Group selector default means all Copy Groups within the selected Tenant and System. It is not a reason to replace actual stored Copy Group associations with a fabricated group.
- Generally a System uses one Copy Group. Preserve the flexibility to split ingestion and processing into several groups.
- Process Groups remain associated with actual Copy Groups; processing follows the relevant ingested groups. Preserve dependency requirements when groups are split.

## 4. Metadata Authoring

**Human intake:** resolve missing Tenant, registered source System/Connection, intended Source-only or Source-plus-Bronze output, and what source information is available.

Use flexible intake with fixed outputs. Accept DDLs, schema exports, documentation, existing authorized metadata/data access, or other supplied definitions. Actual rows are unnecessary if definitions provide enough evidence. Extract supported information, identify precise missing facts, and explain what is needed to continue. Do not invent schema details.

For Source-plus-Bronze work, produce Source and Bronze Objects/Attributes, Bronze DDL, ingestion Object/Attribute Mapping, and Copy configuration. Follow the shared naming, aliasing, and casting rules. Validate consistency across all outputs and present them together for review.

## 5. Model Input Scope

**First question:** show the Model's existing scope and ask what the user wants to add or update.

For additions, show accessible Source Tenants. Resolve Source versus Bronze explicitly, list candidate Objects grouped by System, and accept individual selections or all Objects for selected Tenant/System combinations. Repeat for additional Tenants when requested. Preserve existing membership unless a change is requested.

The Model's owning Tenant does not change. Later workflow selection can use a subset of saved Model scope without changing membership.

## 6. Metadata Enrichment

**First question:** determine whether to overwrite existing unlocked descriptions or fill missing descriptions only. Defer a dedicated custom per-record override mode. Locked descriptions never change.

For selected Objects:

1. Understand each Object's purpose and row meaning, then describe its Attributes consistently in that context.
2. For Bronze inferred types, prefer reliable Source metadata connected through registered ingestion Mapping.
3. Where reliable type evidence is missing, use permitted Databricks evidence checks under the saved SQL policy. Do not guess from column names alone.
4. Keep physical storage types separate from inferred modeling types. Preserve existing inferred types unless an explicitly requested correction requires reassessment.
5. Fill supported descriptions and missing inferred types, respecting Object and Attribute locks. Record uncertainty and ask only material clarification questions.
6. Group Metadata changes under their actual owning Source Tenants and apply through the established governed process.

Generated descriptions are hypotheses supported by available evidence, not independent proof for later relationship analysis.

## 7. Logical Build

### Existing work and selected scope

Inspect existing Analysis, Conceptual, and Logical results. Determine whether the user is adding inputs, refining an area, or rebuilding a selected portion. Reuse that intent across phases. Preserve valid existing work instead of automatically rebuilding.

Resolve all Objects in Model scope versus a selected subset, reusing an existing choice. Show full Tenant/System identity when needed.

### Profiling

Show where Profiles already exist. Ask whether to reuse them, reprofile selected Objects, or skip Profiling.

For requested fresh profiling, ask for all rows or batch selections. Accept natural language selections by Tenant, System, or particular Objects. Batch assignments can be shared or different across Systems.

The agent translates intent into a fixed structured plan. Deterministic code resolves each Object's registered batch column and originating System, using ingestion Mapping for Bronze. It generates the standard profiling SQL and result structure:

- Assigned batch plus registered batch column: filter by that batch.
- All rows selected or no registered batch column: no batch predicate.
- Conflicting or ambiguous assignments: clarify before generating the affected query.

Execution obeys SQL policy. Reusing a Profile must preserve awareness of its scope and evidence freshness. A generated query is not a completed measurement. Agent-authored SQL remains available for additional modeling investigations where permitted.

### Analysis

Ask for additional known relationships, business rules, or documents only if not already supplied; allow proceeding with existing evidence.

1. Understand every Object's meaning, grain, candidate identifiers, lifecycle, and relevant rules.
2. Propose relationships across the whole selected scope from meaning, compatible types, key roles, and Profiles. Include composite-key candidates where evidence warrants them.
3. Under SQL policy, measure uniqueness, matching coverage, missing references, and join multiplication with deterministic checks.
4. Interpret results semantically. Overlapping identifier values alone do not establish a relationship.
5. Review the whole relationship graph for contradictory candidates, competing joins, and unexplained isolated Objects.
6. Record supported, rejected, and unresolved findings with reasons, distinguishing inference from measured evidence.

Choose relationship-check scope deliberately: batch transactions may reference older master data. Unresolved findings remain visible and block only dependent decisions.

### Reusable session scratchpad

Use a predictable local folder such as <session>/working/<task>/object-analysis/, with an identity index and freeform Markdown notes per Object. This is not a mandatory JSON schema. Agents can append any useful discovery, reasoning, evidence reference, correction, or open question.

Conceptual and Logical work read and extend these notes before repeating investigation. Reassess affected findings when evidence changes. Do not persist raw rows, raw query dumps, secrets, or raw prompts. Scratchpad notes are not authoritative Model records or Change Set contents.

### Conceptual

Reuse a supplied glossary or preferred terminology; otherwise propose terms from Analysis.

- Create high-level business concepts across the complete selected scope before settling individual records.
- Consolidate equivalent meanings across physical Objects, Systems, and Tenants. Several Objects may support one concept, and an Object may support several concepts.
- Challenge overlapping concepts and require a meaningful business distinction before separating them.
- Describe business meaning and high-level relationships. Do not reproduce Logical Entities, Attributes, keys, or normalization decisions.
- Account for every input as contributing, context-only, excluded with reason, or unresolved. Do not lose important meaning.

Conceptual consolidation does not by itself establish common row identity across source systems.

### Logical

Before changing structure, reuse or confirm the Model's naming and audit policy. Show actual defaults and examples. Existing approved policies do not need repetitive questions.

1. Establish the affected existing graph and input evidence.
2. Account for every scoped Object and Attribute as a modeled contribution, context, justified exclusion, or unresolved input.
3. Define and consolidate Entities by meaning, grain, lifecycle, and business identifiers, across Tenants and Systems.
4. Consolidate equivalent Attributes while preserving source lineage and checking units, precision, code meanings, and time semantics. Keep useful System-specific attributes.
5. Normalize where distinct grains, repeating groups, dependencies, or independent lifecycles justify it. Avoid arbitrary lookup proliferation and duplicate representations.
6. Define keys and relationships using evidence. Surrogate keys do not erase source identity or solve cross-System reconciliation.
7. Organize submodels by business capability. Reuse common Entities through memberships rather than duplicating them.
8. Review the full graph for coverage, duplication, unnecessary splits, mixed grains, unsupported exclusions, and downstream impacts.
9. Apply naming, audit, and type policies consistently; validate the effective existing-plus-draft Model and present the complete change for review.

Logical types use reliable inferred type evidence. Bronze STRING storage is not the Logical type policy. Resolve unclear types before finalizing the affected definition. Exclusions need substantive reasons; unfamiliar, empty, or single-System fields are not automatically useless.

## 8. Keys and audit columns

- PascalCase Entity and Attribute names by default.
- Every Logical Entity has its own generated surrogate key first: CustomerID, OrderID, and so on. ID is uppercase.
- A Logical foreign key refers to the referenced surrogate value and compatible type, for example Order.CustomerID referencing Customer.CustomerID.
- Dimensional keys end in Key, with uppercase K and lowercase ey. Use the approved dim/fact naming convention. Wherever the dimensional design declares its own surrogate key, the target DDL generates it and load SQL omits it.
- Dimensional fields can retain meaningful Logical identifiers alongside dimensional keys, as in the supplied examples.

Ask whether to include optional SourceCreatedDate, SourceUpdatedDate, SourceCreatedBy, and SourceUpdatedBy. They are not automatic defaults. If included, dates are TIMESTAMP and by-fields are STRING; resolve their mappings and missing-source behavior. Place them before the shared audit block.

The ordered shared block is:

1. SourceSystemID
2. IsDataValid
3. HashKey
4. IsActive
5. GDSBatchID
6. PipelineRunID
7. CreatedDate
8. UpdatedDate
9. CreatedBy
10. UpdatedBy

SourceSystemID is BIGINT and reflects the originating registered System, sourced through the registered provenance/mapping path. The remaining nine fields are framework-populated. Retain them in Model, target DDL, and Binding, while excluding them from load SQL. Reuse authoritative audit-template types; the supplied photos did not establish every remaining field's type. Surface any missing template definitions rather than inventing types.

## 9. Silver and Gold Target Registration

Silver uses the applied Logical model. Gold uses the applied Dimensional model. Both follow the same process.

**Routine question:** the target schema name, if not already known.

Resolve Source Tenant from existing metadata or the user, proposing Model Tenant as the default for new targets. Resolve physical Tenant/System/Connection from that owner's configured GDS Connection. Report current Binding restrictions before preparing an incompatible target; never rewrite the chosen owner. Reuse approved entity names, descriptions, Attributes, types, nullability, key roles, natural keys, and audit fields.

Build one target definition and derive both Metadata and DDL from it. For every selected target, generate complete CREATE TABLE IF NOT EXISTS schema.table DDL, including generated identity keys. Do not include a catalog.

Produce migration statements separately by comparing the current Metadata Snapshot baseline with desired definitions. New targets need creation; unchanged targets need no migration; changed existing targets need explicit migration statements where supported and known. A live physical-schema lookup is not a mandatory prerequisite.

If a change cannot be established from available evidence, ask the user. If unresolved, still deliver complete creation DDL and known migrations, clearly identifying unresolved migration work. Do not invent changes or silently treat CREATE IF NOT EXISTS as schema reconciliation. The scripts assume physical state matches the documented baseline.

Apply target Metadata through the normal review flow, then refresh Metadata before Binding. Registration delivers scripts; it does not execute them. These target artifact requirements do not authorize populated-PostgreSQL migration helpers or changes to the fresh-install sequence.

## 10. Logical and Dimensional Binding

No routine question when targets and matches are clear.

Reuse valid applied bindings. Bind every selected Entity and modeled Attribute, including generated keys and audit fields, to its registered compatible target. Ask only about missing, incompatible, or ambiguous matches. Apply the Model changes and refresh before Mapping.

## 11. Logical and Dimensional Mapping

**Routine question:** confirm the default Mapping format or an existing custom Output Template, unless already established.

Keep the existing default structures:

- Object Mapping: source_objects and ordered steps.
- Attribute Mapping: source_attributes where applicable and transformation.

Preserve actual installed template identities and confirmed custom formats. Reuse existing valid mappings; update only affected work. Use full authorized physical source identities, including Source Tenant, and preserve aliases and lineage.

Object steps must explain the required output of each operation, enough for Code Generation to implement it:

1. Inputs, aliases, initial grain, and batch/filter scope.
2. Preparation stages and the columns/grain each produces.
3. Join types, predicates, key lookups, and unmatched behavior.
4. Any evidenced deduplication key, ordering, and tie handling.
5. Any confirmed value precedence or preservation rule.
6. Each System branch's target-shaped projection and ordered columns.
7. How branches combine, including any required identity reconciliation.

Attribute transformations supply the field-level expressions, conversions, defaults, null behavior, and invalid-value rules. Account explicitly for database/framework-populated fields without inventing physical source attributes for them.

Provide teaching examples matching the user's SQL structure: simple extraction, CTE/preparation stages, referenced-entity lookups, justified deduplication, existing-value preservation when specified, and multiple System branches producing one final dataset. Examples must not turn particular filters, latest-wins logic, COALESCE, or UNION ALL into universal business rules.

Every selected target and contributing System must be covered. UNION ALL does not resolve overlapping business identities. Capture dependency and collision/reconciliation policy in Mapping. File grouping belongs to Code Generation.

## 12. Logical and Dimensional Code Generation

**Routine question:** desired file grouping, if not already confirmed. Default to one target file with isolated temporary-view branches for contributing Systems. Present filenames and a representative SQL preview once per shared layout.

Read applied Mapping and Binding, plus relevant existing Code. Generate or update only affected artifacts.

- Translate meaningful steps into reusable temporary stages, using CTEs where appropriate. Later stages consume earlier results instead of repeating the whole pipeline.
- Apply mapped Attribute rules and project explicit ordered columns with aligned types across branches.
- Use evidence-based combination/reconciliation from Mapping. Do not repair business ambiguity by inventing logic in SQL.
- Follow the shared schema qualification, identity-key, audit-column, and runtime-parameter rules.
- Produce a self-contained SQL batch ending in the required dataset SELECT. Use unique unqualified temporary names; do not depend on another file's session state.
- Preserve the existing code-only generated-file contract; keep explanations outside SQL files. Teaching notes in references are separate.
- Review grain, joins, filters, conversions, null behavior, dependency order, and every mapped output. Optional bounded preflight obeys the saved SQL policy and current authorization.

Store code through the Model Change Set flow. Framework loading and deployment remain external. After code generation, resolve the next desired workflow instead of assuming Dimensional or Validation.

## 13. Dimensional Build

**First question:** which business processes and analytical questions the model should support. Reuse existing outcomes; if the user is unsure, propose possibilities from the Logical model for confirmation.

Inspect existing dimensional work, applied Logical Mapping, and eligible Silver contributions. Reuse valid structures and limit changes to the requested work.

1. Declare exactly what one fact row represents before choosing Dimensions or measures.
2. Identify descriptive Dimensions and reuse compatible conformed Dimensions across processes, Systems, and Tenants. Support role-playing without duplicating definitions unnecessarily.
3. Define facts, measures, calculations, and valid aggregation behavior at that grain.
4. Determine required fact behavior, Dimension history, current/event-time lookup, missing or late references, and genuine bridge needs. Resolve material business uncertainty as it arises.
5. Apply approved names, Key suffixes, technical fields, and audit policy.
6. Account for selected Silver contributions, justify exclusions, and verify that joins preserve grain and do not duplicate measures.
7. Review and apply, then offer Gold Target Registration as appropriate.

Gold registration, Dimensional Binding, Mapping, and Code Generation reuse the corresponding agreed workflows above.

## 14. Validation Authoring

**Opening intake:** show available Silver/Gold targets and Systems; resolve the desired layers, Systems, and targets, including both layers when requested. Establish whether checks address transformation output, loaded data, or both.

Keep the existing Validation Group and Validation Check tables and assertion contracts. Validation may follow Logical code without any Dimensional work. Ordinary code review does not automatically author Validation records.

1. Reuse existing valid checks and identify affected coverage.
2. Read Mapping, relevant Code, and supported business rules; establish matching scope and batch boundaries.
3. Propose focused groups by feature or failure type. Technical examples include identity/duplicates, output compatibility, and references. Functional groups cover actual supported features, such as order totals or customer consolidation.
4. Name groups clearly so layer, feature, and purpose are distinguishable, with the proper System association. Do not combine every technical check in one generic group or create a group for every trivial check.
5. Present representative coverage for confirmation, then author a limited set of distinct useful assertions. Derive expectations independently from Mapping and confirmed rules rather than copying generated code as its own oracle.
6. Specify comparison, severity, null behavior, empty-input behavior, and the real failure condition. Queries contain their own necessary preparation; Query A and Query B do not depend on each other's temporary objects.
7. Review and apply complete definitions. Optional preflight follows policy. Authoring before physical loads is supported; empty data does not prove the business checks pass.

No new table structure is required merely to organize checks by feature. Never invent unconfirmed business thresholds or multiply redundant checks for apparent coverage.

## 15. Process Registration

Read applied Code, Mapping, and Metadata first. Derive known filenames, targets, Systems, zones, existing groups, and relevant dependencies.

**Human intake:** request only missing execution details in one consolidated question, usually the artifact location/path, plus unresolved executable, Process Type, or Copy Group information.

Reuse suitable Process Groups and their actual ingestion Copy Group associations. Typically all relevant tables and processes for a System use one group, while multiple groups remain supported. Follow the Tenant/System/Copy Group selection rules in the shared reference.

Resolve artifact-to-Process assignments and dependency order. Several System-specific Process rows may reference one combined artifact when that matches the confirmed orchestration contract. Show assignments and order for confirmation; ask about genuinely unresolved prerequisites.

Create or update complete Metadata records through Workbench and the normal governed Apply flow. Preserve unaffected registrations. Do not guess runtime paths, schedule triggers, deploy code, or start processes.

## 16. Implementation approach and verification

Implement slowly, one cohesive change at a time. Explain and verify each change before moving to the next. Use existing helpers and contracts where semantics match; keep authoritative rules in the backend and presentation in the client.

Suggested sequence:

1. Reconcile this plan with CONTEXT.md and relevant ADRs; consolidate the shared orchestration reference and targeted examples.
2. Update mode routing and Guided intake. Split Workbench/snapshot initialization into separately verifiable changes as necessary.
3. Implement cross-Tenant scope support through small end-to-end slices covering ownership, authorization, snapshots, sessions, and references. Prevent ambiguous identities when codes repeat across Tenants.
4. Update Metadata Authoring and Enrichment guidance and any necessary existing helpers.
5. Integrate deterministic Profiling, including natural-language-to-plan translation and multi-System/Tenant batch assignment.
6. Add reusable scratchpad conventions and improve incremental Analysis, Conceptual, and Logical guidance. Resolve how the existing pairwise Analysis schema represents composite-key evidence before claiming executable composite relationship support.
7. Align target definitions, identity keys, audit projection, full creation DDL, and separate snapshot-based migration artifacts. Verify backend and plugin paths agree.
8. Align both layers' Binding, Mapping examples, Code Generation, and post-code routing.
9. Align Dimensional modeling guidance, focused Validation grouping, and Process Copy Group selection behavior.
10. Run the appropriate integration, packaging, and compatibility checks; rebuild the local plugin ZIP from the final source.

Meaningful verification should cover changed behavior, including unauthorized cross-Tenant inputs, duplicate names in different Tenants, lock/revision preservation, batch/no-batch profiling, identity/audit projection, migration-diff reporting, unchanged-record reuse, explicit branch alignment, validation scope/grouping, and default Copy Group selection. Do not add tests merely restating prose or the implementation.

Use installed project environments and the repository's documented checks. Database tests use only fixture-created disposable PostgreSQL containers. Do not substitute an existing database. Keep captured sensitive output hidden. Preserve Python 3.12 and applicable Windows compatibility. Rebuild local artifacts after source changes; rebuilding does not authorize publishing.

There are already uncommitted changes from the earlier narrowly authorized shared-reference work: the orchestration reference and repository pointer, SKILL.md and Metadata Authoring links/rules, instruction-footprint coverage, and rebuilt plugin ZIP. Review and incorporate them; do not describe the full redesign as already implemented. This consolidation adds no further repository changes.

## 17. Approval and completion requirements

Approved for implementation. Both builds invoke missing Metadata Enrichment before dependent modeling, reusing evidence and saved policies. Update the packaged user guide alongside the skill. Teach exact tool/helper use, efficient bounded reads and edits, snapshot/session initialization, Workbench, validation, and Stage Runner handoff. Remove ambiguity and conflicting instructions. Rebuild the local ZIP and verify source/package parity. Implement and verify one cohesive change at a time.
