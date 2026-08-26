# GDS Workbench V2 user guide

This is human-readable documentation bundled with the V2 plugin. The agent does not load it as skill instructions. It explains what V2 can do and gives copy-ready conversation requests for new users.

## What V2 includes

V2 combines four parts:

- **Conversation agent** — chooses the workflow, reasons over bounded evidence, maintains the plan, and asks for approvals.
- **GDS MCP server** — performs authorized reads, creates signed Snapshots, and exposes governed Tenant Lock and Metadata/Model Change Set operations.
- **Local helper** — maintains session state, reads bounded Snapshot records, checks readiness, and manages local pending changes, review, validation, and reconciliation.
- **Local Workbench** — optional browser editor/reviewer for an existing session. It cannot call MCP, use the network, create sessions/tasks, Stage, server-Validate, Apply, archive, execute SQL, or deploy.

## Installation and distribution

V2 follows Agent Plugins 1.0. The plugin is the `gds/` directory whose root contains `plugin.json`, `mcp.json`, and `skills/gds/SKILL.md`. The ZIP is only a release transport, not the plugin root.

For local VS Code testing, extract the ZIP and register the inner `gds/` directory in VS Code `settings.json`:

```json
{
  "chat.plugins.enabled": true,
  "chat.pluginLocations": {
    "/absolute/path/to/gds": true
  }
}
```

Reload VS Code, then verify each portable component:

1. Open the Extensions view and search `@agentPlugins`, or run **Chat: Open Customizations** and open **Plugins**. Confirm that `gds` is installed and enabled.
2. Run **Chat: Configure Skills** and confirm that the `gds` skill appears.
3. Run **MCP: List Servers** and confirm that `gds-workbench` appears. Start it if stopped. VS Code should prompt for Microsoft Entra sign-in through the server's OAuth discovery flow; the plugin contains no credential or token.
4. Start a new agent chat and run the read-only Tenant smoke prompt below.

Agent Plugins 1.0 defines the package format, not publication. This repository's `.github/plugin/marketplace.json` publishes the nested `plugins/v2/gds` source. After the repository is available to users, add its `owner/repository` value to `chat.plugins.marketplaces`, browse `@agentPlugins`, and install `gds`. A local clone can be registered as a `file:///absolute/path/to/repository` marketplace.

```json
{
  "chat.plugins.marketplaces": ["owner/repository"]
}
```

For **Chat: Install Plugin From Source**, use a dedicated Git repository whose root is this `gds/` directory; this monorepository's root is not the plugin root. Do not publish credentials, temporary download URLs, or an environment-specific package without review.

## Start here

After installing the plugin and completing the Microsoft Entra prompt for its configured MCP server, a safe connection check is:

> List the GDS Tenants I can access. Do not make any changes.

For Snapshot-backed work, use this structure:

> Initialize GDS Workbench. Working directory: `<absolute-path>`. Tenant Code: `<CODE>`. Focus: `<Metadata|Model|Code|Validation|Ad Hoc>`. Target: `<target, if applicable>`. Mode: `<Guided|Automatic|Custom>`. Scope: `<Full|Selected>`. Selection and outcome: `<bounded details>`. Stop at `<local review|Stage approval|Apply boundary>`.

Give a Tenant Code, never a Tenant ID for the local folder. One session is bound to one Tenant Code and one Model. Work on another Model in a new session.

To continue later:

> Resume my current GDS session in `<working-directory>` for Tenant Code `<CODE>`. Show status, blockers, and the next decision without repeating completed work.

After a session exists:

> Open the local GDS Workbench for my current session.

For a known workflow target, V2 runs readiness once and does not precede it with inspect. Ad Hoc inspection or non-target Metadata/Assertion work uses one bounded inspect per required area.

## Modes and scope

- **Quick / Ad Hoc** — read-only explanation or bounded inspection. An explanation needs no session; local Snapshot inspection does.
- **Guided** — builds with explicit review checkpoints. Logical Build pauses by Object group.
- **Automatic** — covers the complete declared scope in compact batches. It is not unattended: review, Stage approval, server Validate, and fresh Apply approval still apply.
- **Custom** — handles bounded asks and exceptions outside the standard automatic shape.
- **Full** — every currently eligible item for the selected target.
- **Selected** — only explicitly named items. Name exact Objects, processes, entities, or target/source pairs.

A requested number defines input scope, not an output quota. For example, “use these 40 Objects” does not require exactly 40 output Entities.

## What you can ask V2 to do

### 1. Metadata inspection and governed changes

V2 can inspect Snapshot-published Metadata and author complete Metadata Change Set records. It preserves fields without evidence. Omission means unchanged, never deletion; deactivation must be explicit.

Read-only example:

> Initialize GDS Workbench for Tenant Code `ACME`. Ad Hoc read-only: inspect Metadata for `CRM.public.Customer`, its Attributes, Connection, and active ingestion relationships. Summarize only; do not create a task or changes.

Change example:

> Initialize GDS Workbench for Tenant Code `ACME`. Metadata, Custom, Selected: update complete records for `CRM.public.Customer` and the named Attributes only. Preserve every field without evidence, use explicit deactivation only, and pause at local review.

### 2. Profiling evidence

Profiling is not a V2 execution target. V2 can read, summarize, validate, and use existing applied Profile evidence. It must not query Databricks or run profiling SQL as part of Model work.

> Initialize GDS Workbench for `ACME`. Ad Hoc read-only: summarize existing applied Profile evidence for Customer and Order, including null, distinct, uniqueness, and key signals. Identify missing or inconsistent evidence. Do not execute SQL or mutate records.

### 3. Analysis

Analysis is a selectable section inside **Logical Build**, not a separate workflow target. It uses existing Profile, physical-key, Analysis, and Assertion evidence. Inference-only rows are allowed; deterministic validation fields must be complete measured evidence and must never be invented.

> Guided Logical Build, Selected scope, Analysis section only for Customer and Order. Infer evidence-supported relationships and confidence. Allow inference-only rows, never fabricate measured validation fields, show covered/excluded/blocked items, and stop at the Model Apply boundary.

### 4. Conceptual modeling

Conceptual is also a Logical Build section. It improves vocabulary and boundaries but cannot independently determine Logical structure.

> Guided Logical Build, Selected scope, Conceptual section only for Customer and Order. Propose evidence-supported concepts and relationships with definitions, grain/cardinality basis, confidence, and support. Report covered, excluded, and blocked items. Do not let Conceptual alone drive Logical structure.

### 5. Logical modeling

Logical Build can run Analysis → Conceptual → Logical or an ordered subset. It uses only active scoped physical Objects whose Snapshot says `is_bronze_source_eligible=true`. A Bronze label alone is insufficient.

> Automatic Logical Build, Full scope, sections Analysis → Conceptual → Logical for every eligible Bronze source. Build evidence-backed third-normal-form Entities, Attributes, keys, relationships, sources, rationale, and confidence. Checkpoint every section, report unresolved evidence, and stop after one Model Apply.

### 6. Dimensional modeling

Dimensional Build is optional and requires active applied Logical Mapping. It uses only eligible Silver contributions. It defines fact grain, dimensions, bridges, measures, aggregation, history, conformance, role-playing, keys, lineage, and relationship optionality.

> Guided Dimensional Build, Selected business process `Order Fulfillment`. Declare fact grain first; define facts, dimensions, bridges, measures, aggregation, history, role-playing, and relationship optionality from eligible Silver contributions. Report unresolved items instead of guessing and stop after one Model Apply.

### 7. Silver or Gold target registration

Target Registration projects an applied Logical or Dimensional model into local Databricks DDL plus complete Metadata pending records. Supply one destination System, Connection, schema, and Object Type. Metadata is applied; DDL remains local. Registration never activates Model Scope.

> Automatic Silver Target Registration, Selected entities Customer and Order. Destination System `<system>`, Connection `<connection>`, schema `<schema>`, Object Type `<type>`. Reuse compatible targets, generate deterministic local Databricks DDL and complete Metadata changes, and stop after Metadata Apply.

Use **Gold Target Registration** for applied Dimensional entities.

### 8. Logical or Dimensional Mapping

Mapping works on an exact target Object plus source System unit. Logical Mapping maps Bronze/Logical evidence to registered Silver targets. Dimensional Mapping maps eligible Silver sources to registered Gold targets. V2 uses governed authoring context and candidate materialization; it never invents database IDs, transformations, lineage, dependencies, or write modes.

> Automatic Logical Mapping, Selected: Silver target Customer from source System CRM. Use the governed authoring context and materializer for that exact target/source unit, report every blocker, review the complete materialized changes, and stop after one Model Apply.

For Gold, request **Dimensional Mapping** and name the Gold target Object plus source System; optionally narrow the eligible Silver source Objects. A target must first be activated through the separate authorized web Model Scope path, followed by a fresh Model Snapshot.

### 9. Logical or Dimensional code generation

Code Generation requires active applied Mapping and the governed `GeneratorDocumentV1` for every exact target/source unit. Default output is a deterministic Databricks SQL file. Python or notebook output requires an explicit artifact override. Generated output remains local and is never executed, uploaded, or deployed.

> Logical Code Generation, Selected: Customer target plus CRM source, artifact `sql_file`, Databricks. Use the governed `GeneratorDocumentV1` for the exact unit. Generate the deterministic local file, embed Model revision and Mapping digest, show a diff if output changed, preserve manual customization, and never execute or deploy it.

Use **Dimensional Code Generation** for applied active Dimensional Mapping.

### 10. Validation and review

Local validation checks the effective Snapshot-plus-pending graph and creates no report files. It cannot prove live data/runtime correctness and cannot replace governed server Validate.

> Validation only: review and locally validate the current Model Change Set. Show bounded issues, action counts, affected canonical keys, digest, and Stage sizing. Do not mutate, Stage, or Apply.

For a staged draft:

> Resume the staged Model draft. Get its exact current status and revision. If it is `active`, server-Validate that exact revision; if it is already `validated`, reuse that exact validated revision. Show the authoritative `action_review`, and do not Apply until I provide fresh approval.

### 11. Assertion preparation

Assertion preparation is optional Custom Model work before a main target. Persist only evidence explicitly supplied by the user. Assertions inform reasoning but are not executable lineage.

> Create a Custom Selected Assertion-preparation task for the supplied Customer-to-Order business rule. Record only my stated evidence and rationale, review it with me, and stop after its Model Apply.

### 12. Governed Ad Hoc Databricks SQL

The MCP server may expose governed Databricks SQL for explicit Ad Hoc requests. It permits reads and unqualified temporary objects only, rejects DML and persistent DDL, and returns at most 50 final rows. Do not use it to run profiling/model workflows or generated workflow code.

> Ad Hoc read-only: using active source Connection `<connection or connection_id>` in Environment `<environment_code>`, run this reviewed Databricks query through the governed SQL tool: `<query>`. Fully qualify every physical relation as `catalog.schema.table`, return at most the allowed bounded result, and make no persistent or data-changing operation.

## Normal dependency path

Logical Build → Silver Target Registration → authorized external Model Scope activation and fresh Model Snapshot → Logical Mapping → Logical Code Generation and/or Dimensional Build → Gold Target Registration → authorized external scope activation and fresh Model Snapshot → Dimensional Mapping → Dimensional Code Generation.

V2 stops after each Apply and shows only eligible next targets. Logical Code is not required before Dimensional Build.

## Snapshots and approval gates

For first mutation or stale input, V2 asks the user to download and unzip exactly one fresh generated Snapshot root into the stated `metadata/` or `model/` directory. The plugin never downloads/unzips it. Snapshot files are immutable. Never paste temporary download URLs, credentials, full Snapshots, raw rows, or raw tool output into chat.

The governed mutation sequence is:

1. Readiness for a known target, or bounded inspect for non-target work.
2. Ordered plan and complete local pending records.
3. Human review and local validation/acceptance.
4. Tenant Lock check. Obtain explicit approval before acquiring an unowned lock. Another owner's lock stops the workflow unless an authorized override is explicitly directed with a reason.
5. Obtain separate Stage approval, then create/resume/reconcile and Stage the governed server draft.
6. Server Validate and authoritative action review.
7. Fresh Apply approval immediately before Apply.
8. Apply once, mark only the written area stale, release an acquired lock, and stop.

Stage approval and local override are never Apply approval. Automatic mode never bypasses these gates.

## Common blockers

| Problem | Correct response |
|---|---|
| Missing or stale Snapshot | Download/unzip one replacement exactly where requested, then resume. |
| Expired Snapshot URL | Request a fresh Snapshot result; never paste or log the URL. |
| Tenant locked by another owner | Wait or ask the owner to release it. An authorized override requires explicit user direction and a reason; never infer it. |
| Target not Model-Scope eligible | Authorized web owner applies scope, then replace Model Snapshot. |
| Local digest conflict | Refresh and review; never overwrite external edits. |
| Server draft conflict | Fetch and reconcile; never overwrite or archive implicitly. |
| Local validation failure | Fix, review, and accept again; override only bounded domain failures with an explicit reason. |
| Missing mapping/generator tool | Ask the platform owner to deploy the latest MCP server and stop. |
| Missing grain, lineage, evidence, write mode, or optionality | Answer the Resolution Prompt; never request placeholders. |

## What V2 intentionally cannot do

- Mutate Model Scope; that is a separate web-governed owner operation.
- Use Application Prompt or Workflow Run surfaces.
- Run or rerun profiling/model SQL.
- Execute, upload, or deploy generated workflow code.
- Perform foundational CRUD, arbitrary PostgreSQL, deletion by omission, or invented identifiers.
- Bypass authorization, Tenant Locks, revision fencing, local/server validation, or approvals.
- Automatically run multiple targets across Apply boundaries.
- Work on multiple Models in one session.
- Export/import/share a session through a supported command. Treat session files, Snapshots, pending records, and generated code as local potentially sensitive material.

## Prompting checklist

For best results, state:

1. Working directory and Tenant Code.
2. Focus area and exact workflow target.
3. Guided, Automatic, or Custom mode.
4. Full or Selected scope with exact selected items.
5. Required destination pattern or artifact type when applicable.
6. Evidence and business decisions the agent must use.
7. Desired stop point.

Do not ask “build everything automatically and apply it.” Ask for one target, one bounded scope, and one approval boundary at a time.
