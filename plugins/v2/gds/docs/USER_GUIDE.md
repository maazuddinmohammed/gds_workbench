# GDS Workbench plugin user guide

Use the plugin to turn registered data and business evidence into reviewed Metadata, models, mappings and SQL. The agent investigates and drafts locally; you review the result before it is applied.

## Start with an outcome

For a first modeling task:

> Guided: build the Logical model for Model `<name>` in Tenant `<code>`, using all applied inputs. Working directory: `<path>`. SQL policy: Essential. Reuse existing Profiles. Explain the grain, identity and relationship decisions before handoff.

For a smaller task:

> Profile only these three Objects. Use all rows. Stop after the profiling result; do not start modeling.

The agent reuses information you already supplied. Tenant, System, and Connection setup remains an operator/web prerequisite. Read-only inspection needs no local session.

The agent creates/downloads/installs Metadata and Model Snapshots, initializes or resumes the session, and opens Workbench once. Choose the session folder when Chrome/Edge requests local directory access. Click **Refresh** when the agent presents an updated draft. Another Model needs another session.

A **Snapshot** is the saved baseline. A **Change Set** contains complete proposed records. **Stage** sends acknowledged changes for server validation. **Apply** saves separately approved changes. A missing draft record leaves existing data unchanged.

## Choose how to work

| Choice | Behavior |
| --- | --- |
| Guided | Follow the requested workflow; resolve only missing decisions. A phase-only request stops at that phase. |
| Custom | Investigate a specific goal, review a proposed plan, then execute it. |
| Grill With Docs | Work through uncertain business rules and documentation before approving a plan. |
| SQL Never | Use saved or supplied evidence; unresolved facts stay unresolved. |
| SQL Essential | Query evidence gaps that block a responsible decision. |
| SQL As needed | Permit useful bounded evidence queries. |

Choose SQL policy once; the agent reuses it. Queries return bounded aggregates, but a small result can still scan a large table. The local planners generate SQL; they do not execute it. Source queries use registered foreign-catalog coordinates; Bronze queries use registered placement. Missing coordinates make that evidence unavailable. Masked fields are excluded, including masking inherited from registered Source mappings. Fully masked Objects return exclusion coverage without SQL.

## What good output looks like

Consider an order extract with one row per line. OrderNumber determines OrderDate and BillingCustomer; OrderNumber plus LineNumber identifies the line.

- **Metadata:** an Object definition states that row meaning. Attribute definitions distinguish order total from line amount, and billed customer from recipient. Units, tax treatment and currency are stated only when evidenced. “Amount value for Amount” is not useful enrichment.
- **Profiling:** records state measurement scope and missing/duplicate observations. Individual-column statistics do not establish a composite key or a functional dependency.
- **Analysis:** joint-key and dependency checks support the header/line distinction. Join coverage and unique referenced keys support customer relationships. Rejected and unresolved candidates remain visible.
- **Conceptual:** business concepts and verb-based relationships explain the purchase process. Physical tables are evidence, not an output inventory.
- **Logical:** Order holds header facts; OrderLine holds facts determined by the complete line key. The relationship resolves the complete business identifier to the generated surrogate. Historical shipping address stays tied to its historical meaning.

This is an example, not a required schema. A normalized source can legitimately remain one Entity. Repeated status values do not automatically justify a lookup Entity. An isolated reference Entity may be intentional. Equal identifiers from unrelated Systems require a confirmed identity rule or crosswalk before consolidation.

Metadata Enrichment preserves physical storage types and locked records. Choose fill-missing or overwrite-unlocked descriptions. Bronze may store STRING while a supported modeled type is numeric. A small sample only suggests a type: observed scale and DECIMAL(38, scale) do not prove future capacity. Expected range, units and conversion failures still matter.

For Profiling, choose reuse, selected reprofile or skip, and all rows or explicit batch assignments. For deeper modeling evidence, the agent can use deterministic key, dependency and join probes. Composite probes retain the complete tuple; single-column relationship records cannot represent composite proof. The agent keeps sanitized findings and current decisions in session-local object-analysis notes so later phases can reuse them.

One modeling owner reconciles the whole design. When delegation is enabled, workers investigate bounded questions or review the candidate; they return evidence and concerns. Delegation does not authorize additional stages or external actions.

## Review the result

Ask the agent to explain the actual candidate:

1. What does one occurrence or row represent, and what identifies it?
2. What was split, consolidated or retained, and which dependency or business rule supports that choice?
3. Which relationships have measured or documented support? Which candidates remain unresolved?
4. Where does each scoped input contribute? What was excluded, and why?
5. Which type, history and audit decisions remain uncertain?

For affected Conceptual/Logical work, local `validate` creates a modeling evidence report. It checks required decisions, citations, complete natural-key declarations and supported relationship evidence. It also reports disconnected Entities, source-support patterns, framework-column share and type warnings.

**Structural validity is not business quality.** `evidence_present` means required evidence references and consistency checks passed; it cannot prove the reasoning in a note or Assertion. Warnings are review signals, not Entity or relationship quotas. The plugin does not assign a quality score. A substantial new build receives a separate review of its actual records and evidence.

The agent completes the generated decision scaffold; users do not need to write JSON. Evidence notes cannot activate a relationship by themselves. An Assertion must reflect supplied or confirmed business evidence, not a rule invented to pass validation. Missing material evidence blocks only the affected decision.

## Workbench and approvals

Workbench shows a read-only Snapshot and editable Change Set. **Add selected to Change Set** copies complete records; **Save changes** writes locally. **Show details** opens Mapping, Code and Validation details. **Validate locally** checks structure; the agent's local helper also evaluates the modeling evidence. **Generate DBML** is an optional requested display export, not validation evidence.

The normal handoff is:

1. The agent presents the completed design, evidence limits and validation result; Refresh Workbench and inspect it.
2. An acknowledgement such as “proceed” accepts the exact current content and authorizes an ordinary available Tenant Lock, Stage and server validation. A design-question answer does not accept an unseen draft.
3. Stage Runner transports the acknowledged draft; you do not calculate chunks or hashes.
4. Review the authoritative server result and give separate Apply approval.
5. The agent applies once, refreshes the affected Snapshot and releases a lock it acquired.

Changed records, cited decisions/notes or supporting Snapshots invalidate modeling acceptance. Model revision changes require reassessment. Metadata has no tenant-wide revision; freshness, Tenant Lock and server validation protect it. Another lock owner stops handoff. Override needs explicit authorization and a reason.

An agent-owned rejected draft can be repaired and reviewed again. Only that exact failed unapplied draft may be replaced; unrelated overlaps remain conflicts. Applying Code, Validation or Process definitions does not deploy or run them.

## Recover without losing work

| Symptom | Next action |
| --- | --- |
| Workbench looks unchanged | Click Refresh to reload local files. This does not download a new server Snapshot. |
| Modeling evidence is missing | Inspect the report and resolve the specific grain, identity or relationship gap. More prose or higher confidence does not substitute for evidence. |
| Evidence changed after acknowledgement | Reassess the candidate, validate and review the revised result. |
| Snapshot replacement says a local folder is locked | Close Workbench and terminals inside that folder, then retry installing the verified ZIP. Do not delete pending records. |
| Snapshot installed with cleanup_pending | The new baseline is installed; a recoverable local backup remains. Resolve its file lock before cleanup. |
| Lock capability appears unavailable | The agent checks available MCP tool capabilities and schemas before reporting a blocker. |
| Apply outcome is uncertain | Read server status before retrying. Do not apply blindly again. |

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

## Continue beyond Logical

Applied Input Scope precedes modeling. Metadata Enrichment has its own Metadata Change Set and refresh boundary. Target Metadata must be applied before Binding, and Binding before Mapping. The agent continues only the requested journey.

Silver Target Registration and Gold Target Registration reuse approved model names, types and policies. Physical placement comes from the configured GDS Connection; Source Tenant remains the data owner. Scope access does not grant another Tenant's write authority. Binding currently requires target Source Tenant to equal Model Tenant; the agent reports incompatible ownership instead of rewriting it.

Naming defaults to PascalCase. Logical surrogates are generated BIGINT keys ending ID; foreign keys reference those values. Dimensional keys end in Key. Confirm the complete audit block and its types when the Model template is missing. SourceCreatedDate, SourceUpdatedDate, SourceCreatedBy and SourceUpdatedBy are optional. An absent template does not authorize silently adding ten framework columns to every Entity.

Mapping explains joins, grain changes, casts, null/error behavior and every target column. Confirmed installed custom Output Templates remain supported. Code follows applied Mapping; it does not invent deduplication, precedence or defaults. The runtime loads data and populates declared framework columns. Generated Code alone does not create Validation records.

Dimensional Build starts from the analytical question and fact grain, then measures, shared Dimensions and history. Joins must preserve grain and valid aggregation.

Validation Authoring creates focused checks with explicit expectations, severity and null/empty behavior. Optional preflight follows SQL policy; successful syntax or empty input does not prove correctness. Process Registration links artifacts and execution order; deployment, scheduling and execution remain separate handoffs.

For workflow detail, see the [workflow guides](../skills/gds/references/workflow-targets.md). For evidence-file behavior, see [modeling quality](../skills/gds/references/modeling-quality.md). For local recovery, see the [session contract](../skills/gds/references/session.md).

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


Plugin rebuilds do not upgrade running MCP/backend services or databases. Install matching local packages; use your normal separately approved deployment process for service changes.
