# GDS Workbench architecture

GDS Workbench has two workflow entry points over one governed PostgreSQL
model:

```text
VS Code Agent Plugin --> Azure App Service MCP --> PostgreSQL
Databricks web App -----------------------------> PostgreSQL
```

The Agent Plugin is the primary developer experience. The web application runs
equivalent workflows for users who do not use the plugin. It uses OpenAI Agents
SDK with Microsoft Foundry deployments and executes workflows in its background
worker. The web App does not call the MCP server.

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

The public surface is intentionally narrow: exactly 37 governed MCP tools and
no MCP prompts or resources. The plugin owns interaction behavior; the server
instructions contain only shared safety and dependency rules.

- Tenant, Model, Metadata, and Model-section reads;
- complete Metadata and Model Snapshots;
- Metadata and Model Change Set lifecycles;
- five governed Tenant Lock operations; and
- bounded Databricks SQL preflight.

DBML generation remains a local browser Workbench display export from the effective
Snapshot plus pending Change Set.

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

## Web backend ownership

The backend is one `gds_workbench_api` Python package. Each feature keeps its
HTTP endpoints, workflow/service logic, and PostgreSQL access together.

| Module | Responsibility |
|---|---|
| `runtime.py` | Creates settings, database access, identity providers, services, and application lifespan. |
| `main.py` | Creates the FastAPI application, mounts feature routers, and installs shared error handling and health endpoints. |
| `dependencies.py` | Supplies one reusable FastAPI authentication dependency, bound to the router's identity provider. Services still enforce authorization. |
| `features/` | Owns each feature's inputs, responses, business rules, and database access. |
| `features/workflows/execution/assembly.py` | Connects workflow orchestrators, repositories, and external adapters for the background worker. |
| `features/profiling/router.py` | Validates HTTP requests and starts governed Profiling Runs. |
| `features/profiling/repository.py` | Reads and writes Profiling state through governed PostgreSQL functions. |
| `features/profiling/workflow.py` | Coordinates Profiling execution, claim checks, and result persistence. |
| `features/profiling/execution.py` | Builds and evaluates bounded Profiling queries using the packaged `config/profiling.json` policy. |
| `integrations/` | Owns Microsoft Foundry and Databricks execution adapters. |

Routers resolve the authenticated Principal through FastAPI `Depends` and pass
it to services. They do not accept caller-authored identity or replace
backend authorization, Tenant Locks, revision checks, or idempotency rules.

Authoring `Workflow` classes own both `start` and `execute_started`. Starting records a governed Run; the worker claims it before
execution. Assembly supplies the lifecycle, Agent, repository, and Change Set
handoff dependencies directly. There is no separate forwarding Workflow wrapper
around a database executor.

## Frontend ownership

`web_app/frontend/src/features/` owns screens and their temporary form state.
`shared/ui.tsx` supplies common controls and display components;
`shared/presentation.ts` supplies matching formatters.

`features/models/WorkflowModels.tsx` owns the active-Model picker used by
Mapping, Code Generation, and Validation. Callers select the workflow and supply
the Model reader; the component handles paging, refresh, table states, labels,
and navigation.

`features/workflows/useWorkflowRunSubmission.ts` owns create/start retry state
for the four run dialogs. It remembers the original command, idempotency key,
and created Run before starting it. A start retry reuses that Run and its
original settings. Each dialog supplies its workflow's start operation and
keeps its own form, validation, errors, and success refresh behavior. Profiling
keeps its separate queued-Run interaction.

## Database and deployment

There is no shared deployed Python process. Build packaging copies the shared
`gds_etl_workbench` application/domain source into each independent artifact:
the Azure App Service MCP ZIP and the Databricks App upload. The web App owns
its HTTP API, workflow execution, and integrations in `gds_workbench_api`.
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
[ADR 007](../adr/007-web-owned-workflows-and-notebook-retirement.md).
