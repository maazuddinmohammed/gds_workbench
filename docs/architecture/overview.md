# GDS Workbench architecture

GDS Workbench has three workflow entry points over one governed PostgreSQL
model:

```text
VS Code Agent Plugin --> Azure App Service MCP --> PostgreSQL
Databricks web App -----------------------------> PostgreSQL
Databricks notebooks ----------------------------> PostgreSQL
```

The Agent Plugin is the primary developer experience. The web application runs
equivalent workflows for users who do not use the plugin. Databricks notebooks
may use different models through Microsoft Foundry or Databricks; they share the
same in-process workflow implementation with the web App. Neither the web App
nor notebooks call the MCP server.

## Plugin

`plugins/v2/gds/` is an Agent Plugins 1.0 bundle with root `plugin.json`,
`mcp.json`, and `skills/`. It provides Quick, Guided, Automatic, and Custom
interaction modes. Grill With Docs is loaded only when requested.

The plugin keeps a local Snapshot session and one Workbench tab. The user
refreshes the Workbench to inspect changed files. A positive acknowledgement
means local review is complete and authorizes an ordinary free Tenant Lock,
reconciliation, Stage, and Change Set validation. Lock override and Apply still
require separate explicit approval. A revision mismatch stops for a fresh
manually downloaded Snapshot and reassessment.

## MCP server

The deployed unit is one stateless Python 3.14 application on Azure App Service.
Azure Easy Auth validates tokens. PostgreSQL resolves the Principal, Tenant
access, Tenant Lock, Model ownership, revision, and permissions for every
sensitive operation.

The public surface is intentionally narrow: exactly 35 governed MCP tools and
no MCP prompts or resources. The plugin owns interaction behavior; the server
instructions contain only shared safety and dependency rules.

- Tenant, Model, Metadata, and Model-section reads;
- complete Metadata and Model Snapshots;
- Metadata and Model Change Set lifecycles;
- five governed Tenant Lock operations;
- deterministic DBML projection; and
- bounded Databricks SQL preflight.

It exposes no foundational CRUD, individual model-graph mutation, direct lock
toggle, arbitrary PostgreSQL, secret-returning, file-upload, or code-execution
tool.

## Change Set boundary

Metadata Change Sets register every physical Object and Attribute. A Model
Change Set can then bind logical or dimensional records to those existing
physical records. Mapping consumes Bindings; Code consumes Mapping; Validation
consumes the current Mapping and Code context.

Snapshots are the handoff boundary. If the Model revision changes, work stops
until a fresh Snapshot is downloaded and reassessed. The server derives
technical digests and provenance; agent-authored documents do not carry
server-internal integrity fields.

## Database and deployment

There is no shared deployed Python process. Build packaging copies the shared
`gds_etl_workbench` application/domain source into each independent artifact:
the Azure App Service MCP ZIP, the Databricks App upload, and the Databricks
notebook upload. The web App also packages `gds_workbench_api` and
`gds_workbench_runtime`; notebooks package only their pruned in-process subset.
Each runtime connects directly to PostgreSQL with its own least-privilege
database role.

Numbered SQL files define a greenfield PostgreSQL 18 installation. Startup does
not apply DDL. No migration, backfill, destructive cleanup, or populated-database
reset path exists.

The MCP runtime ZIP contains only the application entry points, dependency list,
build manifest, and Python package. SQL, tests, docs, local environments, and
secrets are excluded.

See [security](../security.md), [database architecture](database.md), and
[ADR 001](../adr/001-direct-principal-authorization-and-tenant-locks.md). The
deployment/source boundary is recorded in
[ADR 005](../adr/005-independent-deployments-with-shared-source.md).
