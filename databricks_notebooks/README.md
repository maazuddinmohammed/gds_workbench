# Workbench Workflow notebooks

These are interactive source notebooks, not Jobs and not a wheel. Each notebook
collects non-secret widgets and calls the deployed Databricks App API. FastAPI
creates, authorizes, starts, and reports the same Workflow Run used by the web
application. The App worker executes the existing workflow engine. No workflow
logic, PostgreSQL access, model credential, or lock mutation is duplicated here.

## Prerequisites

- Deploy and start the Workbench Databricks App first. Its `/api/*` routes must be
  reachable.
- Use Databricks CLI 0.294.0 or newer for upload. Older legacy clients can convert
  ordinary package `.py` files into notebooks, which breaks source imports.
- Grant the notebook user `CAN USE` on that App.
- Enable App user authorization with `iam.access-control:read` and
  `iam.current-user:read`. The notebook exchanges its internal token for an
  App-audience token with `all-apis`; no token is entered in a widget.
- Use Databricks Runtime 14.0 or newer so the notebook directory is the current
  working directory. Python 3.10 or newer is required.
- The user must already have the existing PostgreSQL Principal, Tenant/Model
  authorization, and an owned active Tenant Lock required by the backend.

See the official Databricks documentation for
[notebook-to-App token exchange](https://learn.microsoft.com/en-us/azure/databricks/dev-tools/databricks-apps/connect-local),
[App user authorization](https://learn.microsoft.com/en-us/azure/databricks/dev-tools/databricks-apps/auth),
and [workspace Python modules](https://learn.microsoft.com/en-us/azure/databricks/notebooks/share-code).

## Upload the source folders

Keep `notebooks/` and `gds_workbench_notebooks/` as siblings. From the repository
root, authenticate the Databricks CLI to the target workspace, then run:

```bash
databricks workspace mkdirs /Users/<user>/gds-workbench-notebooks
databricks workspace import-dir databricks_notebooks/gds_workbench_notebooks /Users/<user>/gds-workbench-notebooks/gds_workbench_notebooks --overwrite
databricks workspace import-dir databricks_notebooks/notebooks /Users/<user>/gds-workbench-notebooks/notebooks --overwrite
databricks workspace import /Users/<user>/gds-workbench-notebooks/requirements.txt --file databricks_notebooks/requirements.txt --format AUTO --overwrite
```

Use a controlled team folder instead of a personal folder when several users
need the notebooks, and apply workspace ACLs there. Do not use `/Shared` for a
production source location.

The notebook adds its parent source folder to `sys.path`, then imports
`gds_workbench_notebooks`. No wheel build or installation is involved. The
package files must remain regular `.py` workspace files; the files under
`notebooks/` are Databricks source notebooks. If the compute image does not
already satisfy `requirements.txt`, install that file as a notebook-scoped
library before running a workflow.

## Widgets

Every notebook has these widgets:

| Widget | Value |
|---|---|
| `AppName` | Deployed App resource name. The SDK resolves its URL automatically. |
| `TenantID` | Positive Tenant ID. |
| `ModelID` | Positive Model ID. |
| `ExpectedModelRevision` | Current positive Model revision; the backend rejects stale input. |
| `SelectedObjectIDsJSON` | Unique positive IDs, for example `[101,102]`. |
| `IdempotencyKey` | Nonzero UUID. Reuse the same value and unchanged inputs when retrying. |
| `WaitTimeoutSeconds` | `0` returns after start; `1`-`86400` polls for a terminal state. |

Notebook-specific widgets:

| Notebook | Additional widgets |
|---|---|
| `profiling` | `RequestedBatchID` (optional) |
| `analysis_inference` | `RequestedBatchID` (optional), agent widgets |
| `analysis_validation` | `RequestedBatchID` (optional) |
| `conceptual` | `ExecutionMode`, agent widgets |
| `logical` | `ExecutionMode`, agent widgets |
| `dimensional` | `ExecutionMode`, agent widgets |
| `mapping` | `ExecutionMode`, `MappingOperation`, `MappingArtifactType`, `MappingSourceSystemID`, `MappingObjectOutputTemplateID` (optional), `MappingAttributeOutputTemplateID` (optional), agent widgets |
| `code_generation` | `ModeledEntityType`, `CodeGenerationCoverage`, `SqlGenerationGuideVersionID` (optional), agent widgets |

Agent widgets are `AgentSDK`, `AgentProvider`, `AgentModel`, `ReasoningEffort`,
`MaxTurns`, `ValidationRetryCount`, and `PromptOverridesJSON`. Defaults select
the registered Databricks provider. To use Foundry, select
`microsoft_foundry` and its registered model code. The backend remains the
authority and rejects unavailable or incompatible combinations.

`ExecutionMode` accepts `one_shot`, `tool_assisted`, or `detailed_coverage`.
Analysis inference is fixed to `one_shot`; Analysis validation and Profiling are
deterministic. Mapping requires exactly one selected target and always uses
selected coverage. Code Generation requires selected IDs for
`selected_targets`, or `[]` for `all_eligible_targets`.

## Draft validation and Apply gates

Typical dependency order:
`profiling` → `analysis_inference` → `analysis_validation` → `conceptual` →
`logical` → logical `mapping` → optional logical `code_generation` →
optional `dimensional` → dimensional `mapping` → dimensional
`code_generation`.

This order pauses at each applicable gate before moving right:

1. Run Profiling, then Analysis Inference.
2. When Analysis Inference produces changes, open its backend-validated draft in
   the web application, review it, and explicitly select Apply. Apply revalidates
   all fences and atomically materializes the draft.
3. Run Analysis Validation only after the Analysis draft is applied.
4. Run Conceptual and Logical in order. After each Run that produces changes,
   review and Apply its validated draft in the web application.
5. Before logical Mapping, the Silver targets must already be registered and
   eligible in Model Scope. Run Mapping against a logical/Silver target and
   Apply its draft. This applied Mapping unlocks logical Code Generation and is
   also required before Dimensional inputs become eligible.
6. If Dimensional modeling is needed, run it only after logical Mapping is
   applied. Apply its draft, register and scope the Gold targets through the
   existing governed application path, then run and Apply dimensional Mapping.
7. Run each Code Generation route only after its matching Mapping is applied.
   Code Generation reads applied Mapping and does not create an Apply draft.

After each Apply, refresh `ExpectedModelRevision` before creating the next Run.
A no-op authoring Run has no draft to apply. The notebooks never apply a draft,
mutate a Tenant Lock, or automatically start a downstream workflow.

## Run and retry

1. Open one notebook, attach supported compute, and fill all required widgets.
2. Create a new UUID for the first attempt and keep it with the run inputs.
3. Run the notebook. It prints only Run ID, workflow, state, creation status,
   and bounded failure details when present.
4. Review the Run in the web application or set `WaitTimeoutSeconds` to poll with
   bounded 2-to-30-second backoff.

Only one Workflow Run may be running per Tenant. If another Run is running, the
notebook reports HTTP `409` in plain language and states that its new Run remains
queued. Wait for the active Run to finish, then rerun with the same
`IdempotencyKey` and unchanged inputs. The notebook never acquires, extends, or
releases a Tenant Lock.

No `.env` file, App URL, database DSN, Azure credential, Databricks token, model
secret, or MCP setting belongs in these notebooks. `AppName` is the only App
locator; unified authentication supplies the workspace context and the client
performs the required App-audience token exchange.
