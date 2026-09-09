# GDS Workbench plugin user guide

This is human-readable documentation bundled with the plugin. The agent does not load it as skill instructions.

## Install in VS Code

The `gds/` directory follows Agent Plugins 1.0: `plugin.json`, `mcp.json`, and `skills/` are at the plugin root. The ZIP is release transport; register the extracted inner `gds/` directory.

```json
{
  "chat.plugins.enabled": true,
  "chat.pluginLocations": {
    "/absolute/path/to/gds": true
  }
}
```

Reload VS Code, open **Chat: Open Customizations**, and confirm `gds` under Plugins. Run **Chat: Configure Skills** to confirm the GDS skill and **MCP: List Servers** to confirm `gds-workbench`. Authentication is client-managed; the plugin contains no credentials.

### Install the Stage Runner

The GDS agent-plugin ZIP keeps all reasoning and workflow guidance. GDS Stage Runner contributes
only the deterministic Stage tool. Install both once. For production, install Stage Runner from
your organization's public or private VS Code Marketplace; VS Code verifies the Marketplace
signature.

1. Open **Extensions** in VS Code and select your organization's Marketplace.
2. Find **GDS Stage Runner**, verify the trusted publisher, and choose **Install**.
3. Reload VS Code.
4. Run **GDS: Check Stage Runner** from the Command Palette.

For temporary testing, the release workspace also builds an unsigned
`gds-stage-runner-<version>.vsix` candidate:

1. Open **Extensions** in VS Code.
2. Choose **… → Install from VSIX…**.
3. Select the local GDS Stage Runner candidate, then reload VS Code.
4. Run **GDS: Check Stage Runner** from the Command Palette.

Production is the default profile. The extension uses the release-pinned HTTPS MCP endpoint, reads its protected-resource metadata, and asks VS Code's built-in Microsoft authentication provider for the exact delegated scope. Normal Microsoft sign-in/consent may appear on first use or after expiry. Choose the Microsoft development account authorized for GDS; it may differ from the GitHub account used by VS Code. Never enter a token, secret, tenant ID, or client ID into GDS settings.

For a loopback server, set:

```json
{
  "gds.stageRunner.profile": "local",
  "gds.stageRunner.localUrl": "http://127.0.0.1:8000/mcp"
}
```

Local accepts only loopback HTTP ending in `/mcp` and does not request authentication. During the temporary unauthenticated Azure test deployment only, set `gds.stageRunner.profile` to `azureLocalTest`; it uses the pinned Azure endpoint without authentication. Change it back to `production` when Easy Auth is enabled. The extension does not guess the server mode.

The plugin and Stage Runner packages use the same App Service Environment address.
Stage Runner keeps its own built-in address; changing this plugin's `mcp.json` does
not redirect an installed extension. Install the matching VSIX when switching deployments.

The extension runs in VS Code's extension-host Node runtime; users do not install Node separately
for Stage. Never distribute the unsigned local candidate as production software.

Read-only smoke test:

> List the GDS Tenants I can access. Do not make changes.

## Start working

Describe your goal in ordinary language, for example:

> Use Guided mode for Model `<name>` in Tenant `<code>`. Working directory: `<absolute-path>`. SQL policy: Essential. Build Logical from the selected inputs, then help me create Silver validations.

The agent infers the mode and workflow when clear. Otherwise it shows relevant choices. Read-only inspection does not require a session. Tenant, System, and Connection setup remains an operator/web prerequisite.

## Three modes

- **Guided:** follow one or more selected orchestrated workflows. The agent asks meaningful questions and reuses your answers.
- **Custom:** explain your goal, answer focused questions, review a proposed plan, then approve execution using appropriate tools and workflows.
- **Grill With Docs:** investigate a less-defined or complex goal more thoroughly against documentation and evidence. Review the resulting plan before execution.

Quick and Custom are combined into Custom. Automatic and Guided are combined into Guided. These choices do not change authorization or Apply boundaries.

At Guided entry, choose SQL policy once:

- **Never:** use metadata, saved Profiles, and supplied evidence; execute no SQL.
- **Essential:** query only an evidence gap that blocks a responsible decision.
- **As needed:** allow useful bounded evidence queries.

The agent initializes or resumes the local Tenant session, opens Workbench once, and creates/downloads/installs Metadata and, when a Model is selected, Model Snapshots. It then resolves what to do next. Metadata-only work does not need a Model. Installing the first Model Snapshot binds that Model to the session; another Model needs another session.

The Workbench launcher opens the packaged local page in Chrome/Edge. Choose the session folder when the browser asks for local directory access. Keep that tab open and click **Refresh** when the agent says new work is ready.

## Workbench and approvals

Each sheet has a read-only Snapshot and an editable Change Set. **Add selected to Change Set** copies complete selected records into the draft; **Save changes** writes locally. Mapping, Code, and Validation details open through **Show details**. **Validate locally** checks the effective Snapshot-plus-draft graph. **Generate DBML** is an optional user-requested visual export.

A missing draft record means no change, not deletion. Snapshots are immutable. The agent reads bounded selections, preserves unrelated/locked records, and uses deterministic local helpers for editing and validation.

The normal handoff is:

1. The agent completes functional review and local validation, then asks you to Refresh Workbench.
2. Review, edit, or request changes. A clear acknowledgement such as “proceed” accepts the exact current content and authorizes an ordinary available Tenant Lock, Stage, and server validation. Answering a design question does not accept an unseen draft.
3. Stage Runner privately transports and reconciles the approved records. The agent passes only the manifest path and accepted digest; you do not calculate chunks or hashes.
4. Review the server's authoritative result and give separate Apply approval.
5. After Apply, the agent refreshes the affected Snapshot before dependent work and releases a lock it acquired.

Edits invalidate prior acceptance. Model revision changes require fresh evidence and reassessment, never a silent merge. Metadata has no tenant-wide revision: freshness, Tenant Lock, and server validation protect it. A different lock owner, changed server draft, or uncertain Stage outcome requires resolution. Lock override always needs explicit authorization and a reason.

Server rejection of the agent's own draft can be repaired and reviewed again. The runner can replace only that exact failed, unapplied draft; unrelated overlaps remain conflicts. Applying Code, Validation, or Process definitions never deploys or runs them.

## Available workflows and opening questions

The agent reuses information you already supplied. A question is asked only when its answer is missing or ambiguous.

| Workflow | Main intake |
| --- | --- |
| Metadata Authoring | Owning Tenant/System, Source-only or Source-plus-Bronze, and available source definitions |
| Model Input Scope Authoring | Show existing scope; resolve additions/updates, Source Tenants, Source/Bronze, and Objects |
| Metadata Enrichment | Fill missing descriptions or overwrite unlocked descriptions |
| Logical Build | Existing-work intent, selected inputs, missing naming/audit choices, Profile reuse/reprofile/skip and batch choices |
| Silver Target Registration | Target schema name |
| Logical Model Binding | No routine question; resolve only missing/ambiguous matches |
| Logical Mapping | Default format or installed custom Output Template |
| Logical Code Generation | File grouping and representative SQL preview |
| Dimensional Build | Business processes and analytical questions, plus missing history/grain choices |
| Gold Target Registration | Target schema name |
| Dimensional Model Binding | No routine question; resolve only missing/ambiguous matches |
| Dimensional Mapping | Reuse or confirm Mapping format |
| Dimensional Code Generation | Reuse or confirm file grouping and preview |
| Validation Authoring | Silver/Gold/both, Systems/targets, transformation output or loaded data, and focused coverage |
| Process Registration | Missing runtime paths and execution details, then resolved assignments/order |

One confirmation covers a shared layout or policy. Material changes are shown again. The agent does not ask separately about every record.

## Typical journeys

```text
Metadata Authoring → Model Input Scope
→ missing Metadata Enrichment → Profiling → Analysis → Conceptual → Logical
→ Silver Target Registration → Logical Binding → Mapping → Code
→ choose the next goal: Validation, optional Dimensional work, Process, or finish

Dimensional Build → Gold Target Registration → Dimensional Binding
→ Mapping → Code → choose the next goal
```

Both builds invoke missing Metadata Enrichment and reuse complete enrichment. Dimensional work follows registered upstream lineage to enrich Source/Bronze inputs; applied Logical definitions remain authoritative for Silver. Enrichment uses its own Metadata Change Set and refresh boundary. The agent does not mix physical Metadata edits into a Model draft.

Input Scope must be applied before dependent modeling; target Metadata before Binding; Binding before Mapping. Readiness checks Snapshot freshness, while the agent separately checks these applied prerequisites.

## Metadata, ownership, and scope

Supply DDLs, schema exports, documentation, or other available definitions. The agent extracts supported fields and asks precise gaps. Physical rows are not required if definitions suffice. Source-plus-Bronze produces Objects/Attributes, Bronze DDL, ingestion Mapping, and Copy configuration together.

Source names/types remain actual. Each Source Object has one Bronze counterpart. Bronze columns are STRING and lowercase snake_case. RDBMS extraction aliases names into Parquet; Bronze reads those actual incoming names. Without custom Attribute code, the framework casts to STRING; custom Bronze expressions perform their own final cast.

A Model belongs to one Tenant; input scope can include Objects from several authorized Source Tenants. Choose Source or Bronze explicitly. Scope selection does not change ownership or silently prefer Bronze. Model access does not grant access to another Tenant's data.

Common Silver/Gold targets belong to the Model Tenant and use that Tenant's configured GDS Connection. Their source_tenant_id is the Model Tenant, while contributing source lineage is retained. Physical GDS Tenant/System placement can differ from the owning Tenant. Source/Bronze Objects retain their original Source Tenant.

## Enrichment, profiling, and modeling quality

Enrichment preserves locked Objects/Attributes and physical storage types. Choose fill-missing or overwrite-unlocked descriptions; existing inferred types are preserved unless correction is requested. The agent describes each Object's row meaning and its Attributes consistently. Unsupported meaning stays unchanged and is reported.

For Bronze inferred types, reliable Source metadata is resolved through registered ingestion Mapping. Permitted evidence queries address gaps. Generated descriptions are not proof of relationships. Masked fields are not sampled.

For Profiling, inspect saved results and choose reuse, selected reprofile, or skip. Specify all rows or batches in ordinary language, for example “CRM uses batch A, ERP uses batch B, this table uses all rows.” The agent resolves Tenant/System/Object assignments into a fixed plan. Deterministic generation filters only when a batch is assigned and a registered batch column exists. Execution follows SQL policy. Missing measurements remain identified as missing.

Source evidence queries use foreign_catalog, fc_object_schema, fc_object_name, and fc_attribute_name. Missing coordinates are reported; the agent does not connect directly to Source. Bronze queries use its actual placement coordinates.

Analysis examines Object meaning, grain, identifiers, dependencies, and plausible relationships across the full scope. Permitted deterministic checks measure uniqueness, matching coverage, orphans, and join multiplication. Equal IDs alone do not prove shared identity. Batch transactions may reference historical master data, so relationship checks need appropriate scope.

Investigation notes live in a predictable session-local object-analysis folder. Freeform notes and an identity index let Conceptual/Logical/Dimensional reuse findings instead of starting over. Notes contain sanitized reasoning and evidence references, not raw rows or execution dumps.

Conceptual forms higher-level business concepts. Several physical Objects may support one concept. Equivalent meanings can consolidate across Tenants and Systems; the result does not repeat the Logical entity inventory.

Logical defines Entities by grain, lifecycle, and business identifiers. It consolidates equivalent Entities/Attributes, keeps useful System-specific information, and balances normalization against unnecessary splitting. Every scoped Object and Attribute is accounted for. Exclusions require a substantive reason. Existing results are refined incrementally; locks and unrelated work remain protected.

Dimensional starts with business process and fact grain, then Dimensions and measures. It defines history, valid aggregation, and missing/late-reference behavior. Shared Dimensions are reused when meanings and keys agree; role-playing does not automatically duplicate them. Joins must preserve grain and avoid measure duplication.

## Naming, keys, and audit policy

The agent shows actual approved templates rather than inventing missing defaults. PascalCase is the default. Logical surrogate keys end in ID, e.g. CustomerID; foreign keys reference those values. Dimensional keys end in Key, e.g. CustomerKey, with the approved dim/fact prefixes.

Every Logical Entity has its own generated BIGINT surrogate first. Declared target surrogate keys are generated by Databricks; DDL expresses identity behavior and load SQL omits them. Foreign keys remain mapped columns.

SourceCreatedDate, SourceUpdatedDate, SourceCreatedBy, and SourceUpdatedBy are optional: the agent asks whether to include them. If selected, they precede the shared block:

SourceSystemID, IsDataValid, HashKey, IsActive, GDSBatchID, PipelineRunID, CreatedDate, UpdatedDate, CreatedBy, UpdatedBy.

SourceSystemID identifies the originating System. The following nine columns are framework-populated. All intended columns remain in Model, DDL, and Binding, but load SQL ends at SourceSystemID. Mapping explicitly identifies database/framework population. Confirm missing audit-template types rather than assuming them.

## Target registration and Binding

Registration reuses applied model names, types, keys, nullability, descriptions, and audit policy. It builds consistent Metadata and complete CREATE TABLE IF NOT EXISTS schema.table DDL for all selected targets. The framework sets catalog, so artifacts omit it.

Separate migration statements describe known differences from the Metadata Snapshot baseline. If a change is unclear, the agent asks; unresolved changes are listed while complete creation DDL and known migrations are delivered. CREATE IF NOT EXISTS does not alter an existing table. Registration applies Metadata, not DDL.

After refresh, Binding matches every modeled Entity/Attribute to compatible registered targets, including generated columns. Only missing or ambiguous matches require clarification.

## Mapping and SQL generation

Default Object documents use source_objects and ordered steps. Default Attribute documents use transformation and optional source_attributes. Confirmed installed custom templates remain supported.

Object steps explain inputs, preparation, joins, filters, grain changes, branch outputs, and reconciliation. Attribute rules define expressions, casts, invalid/null behavior, and any confirmed defaults. Every target column is accounted for, including columns populated by the framework. Steps and teaching SQL examples describe the desired output, not arbitrary business rules.

Code Generation uses one file per target with separate System branches by default, or the approved separate files. It creates reusable temporary stages and an explicit final SELECT. UNION ALL needs disjoint keys or mapped reconciliation. The agent does not invent deduplication, precedence, lookups, or existing-value fallback to compensate for incomplete Mapping.

Generated files contain code only. Runtime performs loading/merge. SQL review traces each step and output against Mapping. Validation Authoring is a separate selected workflow; code review alone creates no Validation records.

## Validation and Process registration

Choose Silver, Gold, or both, then Systems/targets and transformation-output or loaded-data checks. The agent proposes a focused coverage plan with representative examples.

Groups separate meaningful purposes: key uniqueness, output compatibility, references, or supported business features. They are not just one Technical and one Functional bucket. Each check catches a distinct relevant failure, with an explicit comparison, severity, and null/empty-input behavior. Expectations come independently from Mapping and confirmed rules. Existing valid checks are reused.

Checks can be authored before data loads. Optional preflight follows SQL policy; empty input or successful syntax does not prove business correctness. Stored definitions do not contain execution results.

Process Registration derives known artifacts, targets, Systems, and dependencies, then asks for missing paths and execution details. Process Groups reuse actual ingestion Copy Groups. Usually one group covers a System; split groups remain supported. Runtime inputs are Tenant, System, and Copy Group; selector default means all Copy Groups for that Tenant/System. It is not a replacement for their actual stored associations.

Review artifact-to-Process assignments and execution order before Metadata Apply. Deployment, scheduling, and physical execution remain external handoffs.

## Example requests

- “Guided: show the current Model scope, then add selected Bronze Objects from these two accessible Tenants.”
- “Build Logical using existing Profiles; fill missing metadata first. Reuse the naming policy and ask about unclear business identity.”
- “Custom: investigate why these mappings lose order lines. Propose a plan before changes.”
- “Grill With Docs: help define the analytical processes and grain for this dimensional model.”
- “Generate SQL from applied Mapping. Use one file per target; then ask which validations I need.”
- “Create focused Silver and Gold validations for these Systems, grouped by technical purpose and business feature.”

## Agent efficiency and safety

The skill loads only relevant references. It teaches session setup, exact helper command discovery, bounded snapshot reads, complete-record edits, digest validation, and the Stage Runner handoff. Snapshots and Stage payloads are not dumped into chat. The server remains authoritative for ownership, access, locks, references, revisions, normalization, and Apply.

The shared skill reference references/orchestration-rules.md is the place to extend confirmed runtime behavior. Request updates there with the agent; keep examples fictional and consumer rules precise. Instructions improve consistency but cannot guarantee that an unsupported business inference is true.

Cross-Tenant scope and combined snapshots require the matching MCP/backend and SQL release. A plugin rebuild does not upgrade running services or databases. Generated deployment artifacts require the normal separate deployment process.
