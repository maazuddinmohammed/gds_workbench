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

Before staging, the agent checks the authoritative revision. If it changed, work stops for a fresh Snapshot and reassessment. An unchanged result keeps the acknowledgement; changed content is shown again. A positive acknowledgement authorizes an ordinary free Tenant Lock, reconciliation, staging, and server Change Set validation. The agent reconciles existing non-overlapping draft records and automatically chooses direct or chunked staging; conflicts stop for resolution. Users never calculate chunks or hashes manually. Lock override and Apply always require separate confirmation.

## Interaction modes

- **Quick**: bounded explanation, inspection, or small well-defined change.
- **Guided**: pauses at meaningful decisions.
- **Automatic**: makes supportable decisions and completes the current target without optional pauses.
- **Custom**: follows a bounded exception.
- **Grill With Docs**: a deep collaborative discussion around any GDS work. It writes loose session notes or ADRs as useful and may later promote accepted conclusions into governed records. It is not a Workflow Target.

Full covers every eligible input within the task boundary. Selected covers only explicitly named eligible inputs. Input count never dictates output count.

Before a selected target may use live data, the agent asks once per session for SQL policy: **Never** uses Metadata/Snapshots/user evidence only; **Essential** queries only to resolve an otherwise blocking evidence gap; **As needed** permits bounded queries when they materially improve the result. The choice is reused until the user changes it.

## Work targets

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

Logical Build considers every scoped table during Profiling and relationship Analysis, identifies the business concept or concepts it supports, consolidates matching concepts across Systems, and then builds the Logical Model. Conceptual is a required compact business view, with no Attributes, keys, normalization, table design, or one-to-one requirement with physical or Logical records.

Logical is the normalized operational model. It includes every intended physical Attribute, including audit, technical, and constant-valued Attributes. Dimensional starts with business-process and fact grain.

Every modeling loop accounts for selected inputs as represented, context-only, excluded with reason, or blocked. Coverage does not force one output per input.

## Target registration and binding

Before Silver registration begins, the agent asks the user to confirm the exact target schema name or Entity-to-schema assignment. It then generates local Databricks DDL and complete Metadata records. DDL is handed to the user; only Metadata is applied. All GDS targets use the GDS Connection and retain the real `source_tenant_id`.

After a fresh Metadata Snapshot, Model Object Binding connects each Logical/Dimensional Entity to its registered Silver/Gold Object. Model Attribute Binding connects every modeled Attribute to the registered Attribute. No additional design confirmation is required unless metadata is missing or ambiguous. Mapping never establishes these bindings.

## Mapping, code, and process handoff

Before Mapping begins, the agent presents the Output Template code and proposed object/attribute JSON structure—or recommends the flexible standard structure when no template applies—and waits for confirmation. Mapping is target-binding plus source-System oriented. It stores transformation, lineage, write behavior, and dependency information for already-bound targets; the database does not hard-code its functional shape.

Before Code Generation begins, the agent presents the proposed artifact/file layout and a small SQL preview for confirmation. Code Generation then uses separate files when selected, or for the default combined multi-System pattern uses isolated temporary-view branches and a final aligned `UNION ALL`. The orchestration layer performs loading and owns triggers.

Process/Process Group registration happens later. The agent derives known details, asks one consolidated question for missing artifact paths and orchestration metadata, and confirms the resolved registration plan before authoring. The plugin never deploys or runs generated code.

## Validation Authoring and SQL Preflight

Before Validation Authoring begins, the agent presents the selected Systems/targets and proposed technical, reconciliation, and functional/business categories with representative examples. After confirmation, it creates Validation Groups and Validation Checks from applied Mapping and current Code when available. Records store definitions and SQL, never execution results.

SQL Preflight is optional and separate. It may check syntax before upstream data has loaded; an empty result is acceptable. The plugin never treats preflight output as persisted validation evidence.

## Safe boundaries

- Snapshots are manually downloaded from the MCP tool result, complete, and read-only.
- Local Workbench never calls MCP or performs server changes.
- Metadata and Model Change Sets remain separate.
- Tenant Lock, revision fencing, server validation, and Apply approval remain mandatory.
- The plugin never exposes foundational CRUD, arbitrary PostgreSQL, secret-returning tools, direct graph mutation, or generated-code execution.

## Resetting a Model for retesting

Database owners may use `database/seed/06_model_cleanup.template.sql` during an
intentional plugin retest. Copy the template, replace
`__REPLACE_WITH_MODEL_ID__` with one positive Model ID, inspect the rendered
SQL, stop application/orchestration writers, and run it with
`psql -X -v ON_ERROR_STOP=1`.

The reset removes model-owned workflows, Change Sets, audit rows, modeled
layers, Bindings, Mapping, Code, Validations, and bound Silver/Gold physical
metadata. It preserves input Objects and refuses a bound Object used by another
Model. Tenant-scoped historical Metadata Change Set documents cannot be linked
reliably to a Model and remain. This owner-only reset is not an MCP tool or a
normal production lifecycle operation.
