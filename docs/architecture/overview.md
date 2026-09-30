# Architecture

Code and SQL define behavior. These paths are the navigation map, not a second
contract registry.

```text
Atlas plugin + Stage Runner -> Azure App Service MCP -> PostgreSQL
Databricks App: React -> FastAPI + durable worker ----> PostgreSQL
                                     -> Foundry / governed Databricks SQL
```

The two servers deploy independently. Packaging copies shared
`gds_etl_workbench` source into each artifact; the web App does not call MCP.
There is no separate notebook workflow runtime.

## Source map

| Concern | Authoritative source |
| --- | --- |
| MCP composition, tool registration, audit | `mcp_server/gds_etl_workbench/runtime.py`, `tools/`, `adapters/mcp/` |
| Transport-neutral rules and storage | MCP package `application/`, `domain/`, `infrastructure/` |
| HTTP setup and dependencies | `web_app/backend/gds_workbench_api/main.py`, `runtime.py`, `dependencies.py` |
| Web feature orchestration and SQL I/O | Backend `features/<feature>/` |
| Worker composition | Backend `features/workflows/execution/assembly.py` |
| Prompt variables, readers and rendering | Backend `features/workflows/authoring/` |
| Frontend screens | `web_app/frontend/src/features/` |
| Shared UI and formatting | Frontend `shared/ui.tsx`, `shared/presentation.ts` |
| Atlas local workspace and review | `atlas/atlas-plugin/`; serialization in `workbench/core.js` |
| Stage transport and approval checks | `atlas/atlas-vs-code/src/stage-runner.ts` |
| Database contract | Ordered `database/01_*.sql` through `19_*.sql`, then `20_verify_install.sql` |
| Release entrypoints | `mcp_server/build_zip.py`, `deployment/databricks_ui/build_uploads.py`, `atlas/build_plugin.py` |

## Data and execution boundaries

PostgreSQL owns authorization, Tenant Locks, immutable run inputs, revision fencing,
idempotency and Apply. Services revalidate all authoritative rules; browser state
is presentation and unsaved interaction state only.

Model Input Scope contains authorized Source/Bronze Objects. Logical/Dimensional
Entities own Mapping and Code directly. Physical target registration is an optional
later Metadata handoff. Code consumes applied Mapping; Validation consumes complete
Mapping and relevant current Code. Apply stores definitions, not execution results.

The web worker claims a durable Run before execution. Run creation freezes its
selection, published Prompt versions, settings and relevant revisions. Feature
workflows own preparation, candidate validation and handoff to a governed draft.
Recoverable authoring failures may be scoped to an independent target; permission,
lock, claim and revision failures remain fatal.

MCP exposes governed reads, Snapshot creation, Change Set lifecycles, Tenant Lock
operations and bounded Databricks SQL. Its handlers are the tool inventory. Do not
add foundational CRUD, arbitrary PostgreSQL, credentials, uploads or code execution.
No MCP prompts/resources mirror the plugin workflows.

## Snapshots and staging

Snapshot selection and encoding live in `application/metadata_snapshot/` and
`application/model_snapshot.py`; dataset schemas are in `domain/snapshots/`.
The bounded archive writer is `infrastructure/snapshot_archive.py`. MCP adapters
handle storage and return a short-lived private download descriptor; rows and ZIP
bytes do not enter tool results or audit logs.

Keep archive member paths safe, encoding deterministic, dataset schemas aligned
with Change Set input schemas, and complete natural keys intact. Snapshot limits
must fail explicitly rather than silently truncate a record. A changed Model
revision invalidates work based on the earlier Snapshot.

Stage transport never applies partial datasets. Byte-fragment mode is transport
for complete generated Code records. Python, JavaScript and Windows PowerShell
serialization must produce matching digests. Stage Runner verifies the approved
manifest and content before sending bounded chunks; Apply remains a separate step.

## Build and verify

Use [AGENTS.md](../../AGENTS.md) for exact checks and database-fixture safety.
Every shared-source change must rebuild each affected local artifact. Tests compare
packaged source with the repository. Build output does not authorize deployment.

- [Database installation](../../database/README.md)
- [MCP operations](../../mcp_server/README.md) and [Azure deployment](../AZURE_FRESH_DEPLOYMENT.md)
- [Web local run](../../web_app/README.md) and [Databricks deployment](../../web_app/DEPLOYMENT_GUIDE.md)
- [Atlas](../../atlas/README.md)
- [Security](../security.md), [workflow sources](../workflows.md), [design rules](../design-system.md)
