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

## Start a session

> Initialize GDS Workbench. Working directory: `<absolute-path>`. Tenant Code: `<CODE>`. Mode: `<Quick|Guided|Automatic|Custom>`. Scope: `<Full|Selected>`. Target: `<target>`. Selection: `<details>`.

One session belongs to one Tenant and optionally one Model. After a Model is selected, use another session for another Model.

Workbench opens once when the session starts. Keep it open. When the agent says results are ready, click **Refresh**. Each sheet has a read-only **Snapshot** ledger and an editable **Change Set** ledger. Select Snapshot rows and choose **Add selected to Change Set**, or add a new row in Change Set. Editing is available only for Change Set drafts; **Save changes** writes immediately to the local session.

Each sheet has up to three useful multi-select filters. Mapping documents, generated SQL, and Validation SQL stay compact in the ledger; choose **Show details** to open the complete content on its own record page. **Validate locally** runs the same effective-graph checks used by the agent and stores the digest-bound report under `reports/local-validation/`. **Generate DBML** is optional: use it only when you want a visual export of the current Model Snapshot plus local Model Change Set. Model edits never generate it automatically, and the agent does not inspect it unless asked.

Edit in Workbench, ask the agent for changes, or reply “proceed”, “OK”, or another clear positive acknowledgement.

There is no separate user review command. Before presenting work, the agent compiles and validates the complete effective local graph. A positive acknowledgement accepts the exact current content. Any later content edit makes the report stale and requires another look.

Before staging Model work, the agent checks the authoritative Model revision. If it changed before a server draft exists, the agent stashes pending work, installs a fresh Model Snapshot, restores the draft, and reassesses. A cached server draft requires explicit disposition first; it is never silently cleared. Unchanged, valid work can reuse your acknowledgement while rebinding it to the new Snapshot. Metadata has no tenant-wide revision; the agent requires a non-stale Metadata Snapshot and relies on the Tenant Lock plus server validation against current database state. An unchanged result keeps the acknowledgement; changed local content is shown again. A positive acknowledgement authorizes an ordinary free Tenant Lock, deterministic staging, and server Change Set validation. The agent gives the Stage Runner only a local manifest path and accepted digest. The extension privately reconciles and transports all present datasets through existing MCP tools, then returns only revision, fingerprint, and counts. Payload rows and MCP subcall results do not enter chat context. The helper output fields `manifest` and `accepted_digest` become the extension arguments `manifestPath` and `expectedDigest`. A small local Stage proof retains the accepted digest, Change Set ID, resulting revision and fingerprint; resume checks it against the server before proceeding. Users never calculate chunks or hashes manually. Conflicts stop for resolution. Lock override and Apply always require separate confirmation.

Server validation returns grouped counts and at most 25 bounded error examples, not the complete Change Set. If it rejects the agent's own staged draft, the agent records that exact failed revision, fixes the local records, validates them again, and asks the user to acknowledge changed content. It may then replace only that same task's unapplied failed draft and rerun server validation. Unrelated or externally changed overlaps remain conflicts.

## Interaction modes

- **Quick**: bounded explanation, inspection, or small well-defined change.
- **Guided**: pauses at meaningful decisions.
- **Automatic**: makes supportable decisions and completes the current target without optional pauses.
- **Custom**: follows a bounded exception.
- **Grill With Docs**: a deep collaborative discussion around any GDS work. It writes loose session notes or ADRs as useful and may later promote accepted conclusions into governed records. It is not a Workflow Target.

At the start of Automatic mode, the agent asks once how subagents may run: inherit the model currently selected in VS Code (default), disable subagents, or use an exact model name chosen by the user. The choice is saved for that local session. The agent never chooses, upgrades, or silently substitutes a subagent model.

Full covers every eligible input within the task boundary. Selected covers only explicitly named eligible inputs. Input count never dictates output count.

Before a selected target may use live data, the agent asks once per session for SQL policy: **Never** uses Metadata/Snapshots/user evidence only; **Essential** queries only to resolve an otherwise blocking evidence gap; **As needed** permits bounded queries when they materially improve the result. The choice is reused until the user changes it.

## Work targets

Core modeling stages are Profiling, Analysis, Conceptual, Logical, optional Dimensional, Mapping and Code Generation. The governed targets below also cover preparation and split work by layer; they are not a checklist to run for every request. Read-only reviews can span stages without a session.

There is no separate graphical target menu. The agent infers the target from the request and asks only when the intended result is unclear. Available targets are:

1. Metadata Authoring
2. Model Input Scope Authoring
3. Logical Build
4. Silver Target Registration
5. Logical Model Binding
6. Logical Mapping
7. Logical Code Generation
8. Dimensional Build
9. Gold Target Registration
10. Dimensional Model Binding
11. Dimensional Mapping
12. Dimensional Code Generation
13. Validation Authoring
14. Process Registration
15. Metadata Enrichment

Tenant, System, and Connection setup is an external operator/web prerequisite, not a plugin target. Profiling, relationship Analysis, and Conceptual are required phases inside Logical Build. Assertions are supporting evidence and may be authored within relevant work only from user-confirmed business facts.

## Required pre-authoring confirmations

| Target | What the agent confirms first |
| --- | --- |
| Silver Target Registration | Exact target schema name or Entity-to-schema assignment |
| Model Binding | No optional confirmation; it proceeds from applied model and target Metadata unless a match is missing or ambiguous |
| Logical or Dimensional Mapping | Output Template code and proposed object/attribute JSON structure |
| Logical or Dimensional Code Generation | Artifact/file grouping, SQL pattern, and a small representative preview |
| Validation Authoring | Selected Systems/targets and applicable technical, reconciliation, and functional/business categories |
| Process Registration | Missing artifact/orchestration details, followed by the resolved registration plan |

These confirmations remain required in Automatic mode. One confirmation may cover all selected records that share the same structure; a material change is confirmed again.

## Workflow

```text
External foundational setup, then Metadata Authoring
→ Source/Bronze Model Input Scope (Model Apply and fresh Model Snapshot)
→ Profiling → relationship Analysis → Conceptual → Logical
→ Silver Target Registration
→ Logical Model Binding
→ Logical Mapping → Code and/or Validation

Logical Mapping
→ optional Dimensional
→ Gold Target Registration
→ Dimensional Model Binding
→ Dimensional Mapping → Code and/or Validation
```

Metadata Authoring and Target Registration are Metadata work. Input Scope, Binding, Mapping, Code, and Validation are Model work. Input Scope Apply must finish before Profiling or model development. Metadata Apply must finish before Binding; Binding Apply must finish before Mapping.

**Metadata Enrichment** uses one Model's active Source/Bronze Input Scope to generate selected Object/Attribute descriptions and fill missing `attribute_inferred_data_type`. Both Model and Metadata Snapshots are required. Valid generated descriptions replace unlocked descriptions; a generated null clears the description. Enrichment adds no locks. Locked Objects/Attributes, inactive records, children of locked Objects, existing inferred types, and the original `attribute_data_type` are preserved. Technical failures leave affected fields unchanged. These updates affect physical Metadata shared by Models. Source schema and registered types take priority over bounded sample inference; masked fields are never sampled. The plugin presents a normal Metadata Change Set for acknowledgement, Stage, server validation, and Apply. Ask: “Run Metadata Enrichment for Model `<name>`, Selected scope `<objects>`.”

Enrichment first establishes each Object's purpose, row grain and relationships, then describes Attributes in that business context. Permitted bounded queries may resolve missing meaning; unsupported acronym expansions, code definitions and business rules remain blank. Related descriptions are reconciled before presentation.

The agent creates each required Snapshot, downloads its ZIP to a temporary file, and installs it into the known session automatically. It asks for the working directory only when no session path is known. The installer verifies the returned Snapshot ID, size, SHA-256, and every archive member; temporary signed URLs are never repeated or saved in chat or session files.

## Metadata rules

`source_tenant_id` always means whose data an Object contains.

- Source Objects use their real source Connection.
- Bronze, Silver, and Gold use the active Connection identified by `is_tenant_gds_connection=true`; it must also be a Global Data Store Connection. Its Tenant and System describe physical placement.
- `source_tenant_id` remains the data-owning Tenant even when the Object lives in GDS.
- One physical Object never mixes source Tenants. It may combine several Systems belonging to the same Tenant.

Model Input Scope permits Source and Bronze. When equivalent Source and Bronze Objects are both selected, Bronze wins by default. Source is used when Bronze is skipped, the user chooses Source, or foreign-catalog architecture requires it.

## Profiling coordinates

Source profiling always uses the foreign catalog:

- Connection `foreign_catalog`
- Object `fc_object_schema`
- Object `fc_object_name`
- Attribute `fc_attribute_name`

Missing foreign-catalog coordinates are an error. The workflow never connects directly to Source or silently falls back to ordinary Source names.

Bronze profiling uses tenant catalog plus `object_schema`, `object_name`, and `attribute_name`.

## Modeling quality

Default naming is PascalCase for Conceptual, Logical, and Dimensional. Logical identifiers end in `ID`, such as `CustomerID`. Dimensional keys end in `Key`, such as `CustomerKey`. User instructions or Model policy override defaults.

Logical Build profiles every scoped input, then tests grain, keys, functional dependencies, repeating groups, header/detail patterns, history, and relationships. It queries bounded evidence when the session policy permits it. A source table becomes one similarly shaped Logical Entity only when that examination supports the result.

Before presenting a result, the agent inspects the completed candidate against the effective Snapshot-plus-draft graph. Every input must be accounted for and every output justified. It removes unsupported additions, reconciles duplicates and mixed grains, repairs references, and explicitly retires superseded mutable records within scope. Simply omitting an applied record leaves it active. Locked and out-of-scope records stay protected. Local/server schema validation cannot establish business correctness by itself.

Conceptual starts from business processes and state changes. It defines a small reusable business vocabulary and verb-based relationships. It has no Attributes, keys, normalization, table design, or required one-to-one correspondence with physical or Logical records.

Logical is the normalized operational model. It applies 1NF, 2NF, and 3NF where the evidence supports them, separates different grains and lifecycles, and consolidates Systems only when their business meaning and grain agree. It includes every intended physical Attribute, including audit, technical, and constant-valued Attributes. Submodels represent coherent business capabilities; shared Entities use memberships rather than copies per source System. Common table structure does not prove shared customer identity; consolidation requires supported identity and survivorship rules.

Dimensional follows the Kimball sequence for each process: choose the business process, declare one fact-row grain, identify Dimensions, then identify Facts. The process-to-dimension matrix is an internal completeness check, not a stored model record. Final review checks join fanout, history lookup, unknown/late members, Bridge allocation, snapshot completeness and valid aggregation. Missing policy is exposed rather than defaulted.

Every modeling loop accounts for selected inputs as represented, context-only, excluded with reason, or blocked. Coverage does not force one output per input.

## Target registration and binding

Before Silver registration begins, the agent asks the user to confirm the exact target schema name or Entity-to-schema assignment. It then generates local Databricks DDL and complete Metadata records. DDL is handed to the user; only Metadata is applied. All GDS targets use the GDS Connection and retain the real `source_tenant_id`.

After a fresh Metadata Snapshot, Model Object Binding connects each Logical/Dimensional Entity to its registered Silver/Gold Object. Model Attribute Binding connects every modeled Attribute to the registered Attribute. No additional design confirmation is required unless metadata is missing or ambiguous. Mapping never establishes these bindings.

## Mapping, code, and process handoff

Before Mapping begins, the agent presents the Output Template code and proposed object/attribute JSON structure—or recommends the flexible standard structure when no template applies—and waits for confirmation. Mapping is target-binding plus source-System oriented. Its default object and attribute documents have two keys: `transformation_source` and `transformation_logic`. They identify exact source objects/columns and specify the operations needed to populate the bound target, including grain, keys, joins, conversions, null behavior and applicable reconciliation. Required `mapping_dependency` records carry source-System ordering. The JSON shape stays flexible for confirmed templates; incomplete transformation decisions block the affected target.

Before Code Generation begins, the agent presents the proposed artifact/file layout and a small SQL preview for confirmation. Code Generation uses separate files when selected, or isolated temporary-view branches in a combined file. An aligned `UNION ALL` is sufficient only for disjoint target keys; otherwise Mapping must supply identity reconciliation and precedence. SQL generation cannot silently invent those rules or repair Mapping by adding `DISTINCT`, prior-target preferences or unsupported lookup tables. The orchestration layer performs loading and owns triggers.

Process/Process Group registration happens later. The agent derives known details, asks one consolidated question for missing artifact paths and orchestration metadata, and confirms the resolved registration plan before authoring. The plugin never deploys or runs generated code.

## Validation Authoring and SQL Preflight

Before Validation Authoring begins, the agent presents the selected Systems/targets and proposed technical, reconciliation, and functional/business categories with representative examples. After confirmation, it creates Validation Groups and Validation Checks from applied Mapping and current Code when available. Records store definitions and SQL, never execution results.

SQL is first reviewed statement by statement against applied Mapping. Code generation does not automatically start Validation Authoring or run repeated execution tests. SQL Preflight is optional, external Databricks execution under the saved SQL policy, and separate. It may check syntax before upstream data has loaded; an empty result is acceptable. The plugin never treats preflight output as persisted validation evidence.

## Safe boundaries

- Snapshots are complete and read-only. The agent automatically creates and safely installs a missing or stale Snapshot in the known session.
- Local Workbench never calls MCP or performs server changes.
- Metadata and Model Change Sets remain separate.
- Tenant Lock, revision fencing, server validation, and Apply approval remain mandatory.
- The plugin never exposes foundational CRUD, arbitrary PostgreSQL, secret-returning tools, direct graph mutation, or generated-code execution.

## Example requests

- “Review these Conceptual and Logical drafts using the supplied evidence. Read-only; SQL policy Never. Explain business-grain problems and unsupported assumptions.”
- “Build Logical for the applied Input Scope. SQL policy Essential. Reconcile concepts, normalize by meaning, assign business submodels, and explain cross-System identity decisions before presenting the result.”
- “Enrich missing descriptions for these scoped Objects. Use the saved SQL policy to understand the data first. Leave unsupported meanings blank.”
- “Create Logical Mapping for these bound Silver targets. Use transformation_source and transformation_logic for object and attribute documents; show one populated example for confirmation.”
- “Generate SQL from applied Mapping. Review the actual SQL against each transformation. Report incomplete Mapping for correction; do not start Validation Authoring automatically.”

The packaged `references/examples/modeling-decisions.md` and `mapping-documents.md` show the reasoning and document shape. Their fictional names and policies are never defaults for your data. The plugin can make evidence limits explicit and require correction; instructions alone cannot guarantee that every business inference is true.
