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

Read-only smoke test:

> List the GDS Tenants I can access. Do not make changes.

## Start a session

> Initialize GDS Workbench. Working directory: `<absolute-path>`. Tenant Code: `<CODE>`. Mode: `<Quick|Guided|Automatic|Custom>`. Scope: `<Full|Selected>`. Target: `<target>`. Selection: `<details>`.

One session belongs to one Tenant and optionally one Model. After a Model is selected, use another session for another Model.

Workbench opens once when the session starts. Keep it open. When the agent says results are ready, click **Refresh**. Edit in Workbench, ask the agent for changes, or reply “proceed”, “OK”, or another clear positive acknowledgement.

There is no separate user review command. The agent performs local comparison and validation internally. A positive acknowledgement accepts the exact current content. Any later content edit requires another look.

Before staging, the agent checks the authoritative revision. If it changed, work stops for a fresh Snapshot and reassessment. An unchanged result keeps the acknowledgement; changed content is shown again. A positive acknowledgement authorizes an ordinary free Tenant Lock, reconciliation, staging, and server Change Set validation. Lock override and Apply always require separate confirmation.

## Interaction modes

- **Quick**: bounded explanation, inspection, or small well-defined change.
- **Guided**: pauses at meaningful decisions.
- **Automatic**: makes supportable decisions and completes the current target without optional pauses.
- **Custom**: follows a bounded exception.
- **Grill With Docs**: a deep collaborative discussion around any GDS work. It writes loose session notes or ADRs as useful and may later promote accepted conclusions into governed records. It is not a Workflow Target.

Full covers every eligible input within the task boundary. Selected covers only explicitly named eligible inputs. Input count never dictates output count.

## Workflow

```text
Tenant intake and Metadata
→ Source/Bronze Model Input Scope (Model Apply and fresh Model Snapshot)
→ Profiling, Assertions, Analysis, optional Conceptual
→ Logical
→ Silver Target Registration
→ Logical Model Binding
→ Logical Mapping → Code and/or Validation

Logical Mapping
→ optional Dimensional
→ Gold Target Registration
→ Dimensional Model Binding
→ Dimensional Mapping → Code and/or Validation
```

Tenant Intake and Target Registration are Metadata work. Input Scope, Binding, Mapping, Code, and Validation are Model work. Input Scope Apply must finish before Profiling or model development. Metadata Apply must finish before Binding; Binding Apply must finish before Mapping.

Snapshots are manually downloaded from the MCP tool result and unzipped into the requested session area. The agent explains the destination but does not repeat a temporary signed URL in chat.

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

Conceptual is a compact business view. It groups supporting Objects and Systems into important concepts and relationships. It has no Attributes, keys, normalization, table design, or one-to-one requirement with physical or Logical records. The agent rejects a mechanical copy.

Logical is the normalized operational model. It includes every intended physical Attribute, including audit, technical, and constant-valued Attributes. Dimensional starts with business-process and fact grain.

Every modeling loop accounts for selected inputs as represented, context-only, excluded with reason, or blocked. Coverage does not force one output per input.

## Target registration and binding

Silver/Gold registration generates local Databricks DDL and complete Metadata records. DDL is handed to the user; only Metadata is applied. All GDS targets use the GDS Connection and retain the real `source_tenant_id`.

After a fresh Metadata Snapshot, Model Object Binding connects each Logical/Dimensional Entity to its registered Silver/Gold Object. Model Attribute Binding connects every modeled Attribute to the registered Attribute. Mapping never establishes these bindings.

## Mapping, code, and process handoff

Mapping is target-binding plus source-System oriented. It stores transformation, lineage, write behavior, and dependency information for already-bound targets. An attached Output Template guides the JSON shape. Without one, the plugin uses a flexible standard JSON document; the database does not hard-code its functional shape.

Code Generation decides whether a multi-System target uses separate files or one combined file. A combined Databricks SQL file uses isolated temporary-view branches and a final aligned `UNION ALL`. The orchestration layer performs loading and owns triggers.

Process/Process Group registration happens later only when the user supplies real artifact paths and orchestration details. The plugin never deploys or runs generated code.

## Validation Authoring and SQL Preflight

Validation Authoring creates Validation Groups and Validation Checks from applied Mapping and current Code when available. Records store definitions and SQL, never execution results.

SQL Preflight is optional and separate. It may check syntax before upstream data has loaded; an empty result is acceptable. The plugin never treats preflight output as persisted validation evidence.

## Safe boundaries

- Snapshots are manually downloaded from the MCP tool result, complete, and read-only.
- Local Workbench never calls MCP or performs server changes.
- Metadata and Model Change Sets remain separate.
- Tenant Lock, revision fencing, server validation, and Apply approval remain mandatory.
- The plugin never exposes foundational CRUD, arbitrary PostgreSQL, secret-returning tools, direct graph mutation, or generated-code execution.
