# Independent Azure Databricks notebooks

These notebooks are a second entry point to the Workbench workflows. They do
not call the Databricks App, its HTTP API, or an MCP server. Each notebook:

1. adds the uploaded `<root>/src` folder to `sys.path`;
2. reads the root `.env` file;
3. authenticates to PostgreSQL as `gds_notebook_runtime`;
4. lets PostgreSQL resolve the one fixed Super Admin workload identity;
5. creates, claims, and runs the selected workflow in the notebook process; and
6. writes the same governed results used by the web application.

The App can be deployed separately, or not at all. The notebook path needs no
App configuration or App authorization. PostgreSQL authentication, Tenant
Locks, revision checks, and Databricks model-serving authorization still apply.

## Required runtime

Use **Azure Databricks Runtime 16.4 LTS**, **Apache Spark 3.5.2**, **Scala
2.13**, and **Python 3.12.3**. Scala does not affect these Python notebooks; it
only identifies the selected DBR image. See the official
[DBR 16.4 LTS release notes](https://learn.microsoft.com/en-us/azure/databricks/release-notes/runtime/16.4lts)
and [Workspace files documentation](https://learn.microsoft.com/en-us/azure/databricks/files/workspace).

Use an access-controlled single-user or otherwise approved compute policy. The
compute identity must be able to use Databricks unified authentication and
query the configured Model Serving endpoint.

## Database prerequisites

These steps are DBA work and happen before the notebooks are uploaded:

1. Install and verify the database in the order documented in
   `database/README.md`. This includes `gds_notebook_runtime`, its governed
   wrappers, and transaction-scoped workflow role membership.
2. Set a unique password interactively. Do not put the password in SQL or shell
   history:

   ```text
   \password gds_notebook_runtime
   ```

3. Create or select one active `service_principal` row with
   `is_super_admin = true` and one active Entra identity row for it.
4. Bind that exact Principal, exact database role OID/name, and the registered
   Databricks environment code in `security.notebook_runtime_principal`.
5. Before running an agentic notebook, configure an effective published Prompt
   for every agentic stage used by its execution mode. The reference seed adds
   stage and variable definitions only; it intentionally contains no Prompt
   bodies or assignments. For `analysis_inference`, configure **Analysis /
   Relationship Inference** for the selected execution mode (the widget defaults
   to `tool_assisted`):

   - in the web application, acquire the Tenant Lock;
   - under **Prompts**, create a Tenant Prompt Template for that stage, add its
     first version, and publish it;
   - under the target Model's **Prompts** settings, configure that published
     version as the Model default.

   `PromptOverridesJSON={}` then uses that effective Model default. An override
   is optional and is only for selecting another already-published Prompt
   version for the same stage.

For an already-created Super Admin service Principal, the DBA can use this
shape after replacing every placeholder:

```sql
INSERT INTO security.notebook_runtime_principal (
    database_role_oid,
    database_role_name,
    entra_principal_identity_id,
    principal_id,
    principal_type,
    databricks_environment_code
)
SELECT 'gds_notebook_runtime'::regrole::oid,
       'gds_notebook_runtime',
       identity.entra_principal_identity_id,
       principal.principal_id,
       'service_principal',
       '<registered-environment-code>'
  FROM security.principal AS principal
  JOIN security.entra_principal_identity AS identity
    ON identity.principal_id = principal.principal_id
   AND identity.principal_type = principal.principal_type
 WHERE principal.principal_type = 'service_principal'
   AND principal.is_super_admin
   AND principal.is_active
   AND identity.is_active
   AND identity.entra_tenant_id = '<entra-tenant-id>'::uuid
   AND identity.entra_object_id = '<entra-object-id>'::uuid;
```

The statement must insert exactly one row. The environment code is the code
registered for the Databricks environment in PostgreSQL; it is not a URL,
workspace ID, Tenant ID, or value chosen by a notebook user.

### Security consequence of the fixed identity

This is a high-trust shared workload design. Anyone who can read the root
`.env` obtains the same database credential and acts as the same Super Admin
service Principal. Actions cannot be attributed to individual notebook users.
That identity can operate across authorized Tenants, acquire governed Tenant
Locks, and explicitly activate the shared workflow database role for a
transaction. Restrict Workspace folder, file, compute, and log access; do not
share the credential; rotate it when access changes.

## Expected uploaded tree

Upload the built `gds-workbench-notebooks` folder without changing this shape:

```text
gds-workbench-notebooks/
├── .env.example
├── .env                         # created manually; never committed
├── requirements.txt
├── src/
│   ├── gds_workbench_notebooks/ # widgets, bootstrap, DB control
│   ├── gds_workbench_runtime/   # transport-neutral Profiling runtime
│   ├── gds_workbench_api/       # shared workflow execution modules
│   └── gds_etl_workbench/       # shared domain/application code
└── notebooks/
    ├── 00_tenant_lock.py
    ├── 01_runtime_preflight.py
    ├── profiling.py
    ├── analysis_inference.py
    ├── analysis_validation.py
    ├── conceptual.py
    ├── logical.py
    ├── dimensional.py
    ├── mapping.py
    ├── code_generation.py
    ├── 90_review_workflow_draft.py
    └── 91_apply_workflow_draft.py
```

The notebook files find this root, prepend `<root>/src`, and import ordinary
Python source files. No wheel or other distribution is built or installed.
Keep all four packages under `src/`.

The Workspace browser or `workspace import-dir` can display the entries under
`notebooks/` without their `.py` suffix because their first line marks them as
Databricks notebooks. That is expected. The ordinary modules below `src/` must
remain files with their `.py` suffix and nested package folders intact. See the
official [Workspace command reference](https://learn.microsoft.com/en-us/azure/databricks/dev-tools/cli/reference/workspace-commands).

`gds_etl_workbench` is the historical package name for shared Workbench domain
and workflow code. Its presence does not deploy an MCP server.
`requirements.txt` pins the Python `mcp` library because `openai-agents`
requires it transitively when both supported agent SDKs are retained. That is
an installed library, not a running MCP process. None of these notebook entry
points starts an MCP server, FastAPI server, or Databricks App.

## Upload and configure in the UI

The expanded folder is the primary upload input. Do not import the ZIP into the
Workspace UI: the ZIP importer can flatten a mixed notebook/source tree.

1. Build the upload artifacts from the repository root:

   ```bash
   python3 deployment/databricks_ui/build_uploads.py
   ```

   Add `--replace` only when replacing an earlier builder-created output.

2. If the artifact was transported as a ZIP, verify it, then extract it on the
   VM. Drag the extracted `gds-workbench-notebooks` folder, not the ZIP, into an
   access-controlled Workspace parent folder.
3. Compare the Workspace tree with the tree above. Stop if folders were
   flattened. Files under `src/` must remain regular Workspace files; files
   under `notebooks/` are Python notebook objects.
4. Create `.env` in the uploaded root by copying `.env.example` and replacing
   every placeholder. Browser/OS upload dialogs sometimes omit dotfiles; if
   `.env.example` or `.env` is missing, create or upload that file explicitly in
   the Workspace file editor.
5. Attach DBR 16.4 LTS compute.
6. Install the source package dependencies in a setup cell:

   ```python
   %pip install -r /Workspace/Users/<workspace-user>/gds-workbench-notebooks/requirements.txt
   dbutils.library.restartPython()
   ```

   An administrator may instead install the same pinned requirements as a
   compute-scoped library. Repeat the install when a new compute environment
   does not retain notebook-scoped libraries.

Workspace files support ordinary Python modules and make the notebook
directory the current working directory on this DBR generation. See the
official [Workspace files basics](https://learn.microsoft.com/en-us/azure/databricks/files/workspace-basics).

## Root `.env`

Use exactly this syntax and replace all angle-bracket placeholders. Do not add
unknown fields or inline comments:

```dotenv
GDS_NOTEBOOK_POSTGRES_HOST=<postgresql-hostname>
GDS_NOTEBOOK_POSTGRES_PORT=5432
GDS_NOTEBOOK_POSTGRES_DATABASE=<postgresql-database>
GDS_NOTEBOOK_POSTGRES_USER=gds_notebook_runtime
GDS_NOTEBOOK_POSTGRES_PASSWORD=<notebook-runtime-password>
GDS_NOTEBOOK_POSTGRES_SSLMODE=require
GDS_NOTEBOOK_POSTGRES_CONNECT_TIMEOUT_SECONDS=10
GDS_NOTEBOOK_POSTGRES_STATEMENT_TIMEOUT_SECONDS=30
GDS_NOTEBOOK_WORKFLOW_LEASE_SECONDS=30
GDS_NOTEBOOK_WORKFLOW_HEARTBEAT_SECONDS=10
GDS_NOTEBOOK_AGENT_TIMEOUT_SECONDS=120
```

Databricks model endpoint names do not belong in `.env`. Add each selectable
Databricks model and its exact `deployment_name` to
`src/gds_workbench_api/config/agent_capabilities.json`, then upload that registry
with the notebooks. The same JSON defines SDK, mode, and reasoning compatibility.
The checked-in choices are `databricks-primary` (served by
`databricks-gpt-oss-120b`) and `databricks-claude-opus-5`.

| Field | Meaning |
|---|---|
| `POSTGRES_HOST` | PostgreSQL DNS name only, without `https://` or a DSN. |
| `POSTGRES_PORT` | PostgreSQL port, normally `5432`. |
| `POSTGRES_DATABASE` | Installed Workbench database name. |
| `POSTGRES_USER` | Must be exactly `gds_notebook_runtime`. |
| `POSTGRES_PASSWORD` | Password set by the DBA for that role. Quote it only when needed. |
| `POSTGRES_SSLMODE` | `require`, `verify-ca`, or `verify-full`; use the strongest mode supported by the approved CA setup. |
| `POSTGRES_CONNECT_TIMEOUT_SECONDS` | Connection timeout, `1` through `60`. |
| `POSTGRES_STATEMENT_TIMEOUT_SECONDS` | Control-statement timeout, `1` through `300`. |
| `WORKFLOW_LEASE_SECONDS` | Exact Run claim duration, `1` through `300`. |
| `WORKFLOW_HEARTBEAT_SECONDS` | Claim heartbeat, `1` through `299` and shorter than the lease. |
| `AGENT_TIMEOUT_SECONDS` | Agent call timeout, `1` through `600`. |

The code reads this file directly and does not copy its contents to widgets or
process environment. `.env` is intentionally excluded from the repository and
generated artifacts. It is still a plaintext Workspace file, so its ACL is a
security boundary.

## Run order

```text
01 preflight -> 00 lock check/acquire -> workflow -> 90 review -> 91 apply
-> next workflow/review/apply -> 00 lock release
```

1. Run `01_runtime_preflight.py`. It checks Python 3.12, the `.env`, database
   readiness, the fixed Super Admin binding, shared source imports, and
   Databricks unified authentication/model endpoint readiness.
2. Run `00_tenant_lock.py` with `Action=check`, then `Action=acquire` for the
   intended `TenantID`. Supply a bounded reason and duration. The numeric file
   prefix groups lock management first in the tree, but running preflight before
   acquire avoids holding a lock while setup is broken. A simple lock check may
   also be run before preflight when diagnosing database access.
3. Open one workflow notebook. Run its first cell to create that notebook's
   widget bar. For an Agent workflow, this cell reads the root `.env` for runtime
   settings and offers only Databricks models registered in the packaged JSON.
   Fill the widgets, then run the second cell to execute. Use a new nonzero UUID
   for `IdempotencyKey`; reuse it only when retrying identical inputs. `Run all`
   with blank required widgets is expected to stop validation.
4. For an authoring workflow that returns a draft, run
   `90_review_workflow_draft.py` with `TenantID`, `ModelID`, `WorkflowRunID`,
   and optionally `Dataset`. Blank `Dataset` returns the bounded summary; a
   selected dataset returns its bounded review records.
5. When the draft is correct, run `91_apply_workflow_draft.py` with `TenantID`,
   `ModelID`, `WorkflowRunID`, `ExpectedModelRevision`,
   `ExpectedDraftRevision`, `ExpectedCandidateDigest`, a new `IdempotencyKey`,
   and `Confirmation=APPLY`. Apply revalidates all fences; it does not trust the
   earlier review.
6. Refresh the current Model revision before the next workflow. Follow the
   normal dependency order:

   ```text
   profiling -> analysis_inference -> review/apply -> analysis_validation
   -> conceptual -> review/apply -> logical -> review/apply
   -> logical mapping -> review/apply -> optional logical code_generation
   -> optional dimensional -> review/apply -> dimensional mapping
   -> review/apply -> dimensional code_generation
   ```

   Review and Apply are manual gates after each applicable Analysis Inference,
   Conceptual, Logical, Dimensional, or Mapping authoring run. An applied
   logical Mapping unlocks logical Code Generation and is required before
   Dimensional inputs become eligible. Code Generation reads applied Mapping
   and does not create its own Apply draft.

7. Run `00_tenant_lock.py` with `Action=release` when all work is finished. Use
   `renew` before expiry during a long controlled session. There is no force
   unlock action in the notebook.

Drafts are durable PostgreSQL data in `mcp.model_change_set` and related
change-set tables. Here `mcp` is a PostgreSQL schema name, not evidence that an
MCP server is running. Profiling and Code Generation do not necessarily create
an Apply draft; a no-op authoring run also has nothing to apply.

Only one workflow may run for a Tenant at a time. A conflict or expired claim
is reported as a bounded error. Do not change inputs under the same
`IdempotencyKey`; retry only after the active run/claim is clear.

### Workflow widget essentials

Every workflow notebook creates `TenantID`, `ModelID`,
`ExpectedModelRevision`, `SelectedObjectIDsJSON`, and `IdempotencyKey` widgets.
Selected IDs are a unique positive-integer JSON array such as `[101,102]`.

| Notebook | Additional widgets |
|---|---|
| `profiling` | Optional `RequestedBatchID`. |
| `analysis_inference` | Optional `RequestedBatchID`, `ExecutionMode`, and agent widgets. |
| `analysis_validation` | Optional `RequestedBatchID`. |
| `conceptual`, `logical`, `dimensional` | `ExecutionMode` plus agent widgets. |
| `mapping` | `ExecutionMode`, operation, artifact type, source System ID, optional output-template IDs, and agent widgets. Exactly one target Object ID is required. |
| `code_generation` | Modeled entity type, selected/all-eligible coverage, optional SQL Guide Version ID, and agent widgets. |

Agent widget choices come from the packaged shared registry at
`src/gds_workbench_api/config/agent_capabilities.json`, filtered to Databricks
models and their exact execution profiles. Databricks widget dropdowns cannot
cascade, so each dropdown can show the union of registered choices. The
notebook rejects any SDK, model, execution-mode, and reasoning-effort
combination that is not present in one exact profile. The `default` reasoning
value omits the provider setting. The separate `none` value explicitly disables
reasoning on models that support that value. `default` is first in the shipped
profiles, so it is the current notebook default. Narrow the Databricks profile
to the values verified for the exact endpoint model; for example, GPT OSS uses
`low`, `medium`, or `high`. Claude Opus 5 currently exposes `default` only
because these adapters do not translate its separate thinking-token controls.

The provider remains fixed to Databricks. The packaged JSON registry supplies
the physical Databricks Model Serving endpoint for each selectable model code.
If only a secondary Databricks model is registered, it is the model widget's
only choice and default. A registry without any Databricks model stops the first
cell before creating Agent widgets. Foundry App settings are not used by these
independent notebooks. Maximum turns and validation-retry
defaults and bounds also come from the shared registry. PostgreSQL and the
shared runtime revalidate every widget; a widget never selects the acting
identity or Databricks environment.

Agentic authoring `ExecutionMode` widgets offer `one_shot`, `tool_assisted`, and
`detailed_coverage`; they default to `tool_assisted` so larger scopes use the
bounded local context tools instead of embedding the complete context. If the
registry has no compatible `tool_assisted` profile, the notebook selects the
first compatible registered mode. Code Generation has no mode widget and uses
only registered `detailed_coverage` profiles.

The Tenant Lock and draft review/apply notebooks use the same two-cell pattern:
run the first cell to create their own widgets, fill them, then run the second
cell. Runtime Preflight has no user inputs, so it correctly has no widgets.

## CLI upload alternative

The UI remains the deployment method. When browser drag-and-drop is unreliable,
use [`sync`](https://learn.microsoft.com/en-us/azure/databricks/dev-tools/cli/reference/sync-commands)
for ordinary source files and
[`workspace import-dir`](https://learn.microsoft.com/en-us/azure/databricks/dev-tools/cli/reference/workspace-commands)
only for the marked notebook entry points. Databricks documents that
`import-dir` strips extensions from notebooks, so using it on `src/` would
break Python imports.

```bash
databricks workspace mkdirs "/Users/<workspace-user>/gds-workbench-notebooks"
databricks sync \
  artifacts/databricks-ui/gds-workbench-notebooks \
  "/Users/<workspace-user>/gds-workbench-notebooks" \
  --exclude "notebooks/**"
databricks workspace import-dir \
  artifacts/databricks-ui/gds-workbench-notebooks/notebooks \
  "/Users/<workspace-user>/gds-workbench-notebooks/notebooks" \
  --overwrite
```

Inspect the remote tree afterward. Create the real `.env` outside the
repository with restrictive local permissions, then explicitly import it if
the recursive command omitted dotfiles:

```bash
databricks workspace import \
  "/Users/<workspace-user>/gds-workbench-notebooks/.env" \
  --file "/secure/local/path/.env" \
  --format AUTO \
  --overwrite
```

Never pass a password on the command line. Complete compute attachment,
dependency installation, `.env` ACL checks, and notebook execution in the UI.
