# Manual Azure Databricks UI deployment

The builder creates two independent, source-only upload folders:

- `gds-workbench-notebooks`: interactive workflows that execute inside the
  notebook process using a fixed PostgreSQL-bound Super Admin workload identity;
- `gds-workbench-app-source`: the optional web UI, HTTP backend, and background
  workflow worker running as one Databricks App.

The notebooks do not call or require the App. Neither upload requires a wheel.
Both uploads receive their own source copy of the shared workflow modules; they
do not call the separately deployed Azure App Service MCP server.

## 1. Build and verify

From the repository root on the VM:

```bash
python3 deployment/databricks_ui/build_uploads.py
```

That command builds the Databricks-only variant. Build a Foundry-enabled
variant, which still exposes all registered Databricks models, with:

```bash
python3 deployment/databricks_ui/build_uploads.py \
  --agent-provider microsoft_foundry
```

The Foundry command defaults to `artifacts/databricks-ui-foundry/`. Its
`app.yaml` is selected before the tree manifest, ZIP, and SHA-256 files are
created. Do not copy or replace a manifest after building.

To replace only an output previously created by this builder:

```bash
python3 deployment/databricks_ui/build_uploads.py --replace
```

For the Foundry output, keep the provider selection on rebuild:

```bash
python3 deployment/databricks_ui/build_uploads.py \
  --agent-provider microsoft_foundry \
  --replace
```

Output:

```text
artifacts/databricks-ui/
├── gds-workbench-app-source/
├── gds-workbench-app-source.zip
├── gds-workbench-notebooks/
├── gds-workbench-notebooks.zip
├── UPLOAD_INSTRUCTIONS.md
├── artifact-manifest.json
└── SHA256SUMS.txt
```

Verify transport ZIPs before extracting them:

```bash
cd artifacts/databricks-ui
shasum -a 256 -c SHA256SUMS.txt
```

For the Foundry build, change the first line to
`cd artifacts/databricks-ui-foundry`. Both checksum lines must end in `OK`.

## 2. Do not import the ZIP in the Workspace UI

The ZIPs are transport containers only. Azure Databricks can treat a mixed ZIP
as a notebook import and flatten its nested source folders. If a ZIP was copied
to the VM, extract it locally first. Upload the expanded same-named folder.

Use [Workspace files](https://learn.microsoft.com/en-us/azure/databricks/files/workspace)
to retain ordinary source files and nested directories. The notebook runtime is
[DBR 16.4 LTS](https://learn.microsoft.com/en-us/azure/databricks/release-notes/runtime/16.4lts):
Spark 3.5.2, Scala 2.13, and Python 3.12.3. Scala does not affect the Python
notebook code.

## 3. Expected Workspace trees

After upload, compare the Workspace browser with these trees. Stop and reupload
from an expanded folder if any level was flattened.

```text
<access-controlled Workspace parent>/
├── gds-workbench-app-source/
│   ├── app.foundry.yaml.example
│   ├── app.yaml
│   ├── DEPLOYMENT_GUIDE.md
│   ├── package.json
│   ├── package-lock.json
│   ├── pyproject.toml
│   ├── uv.lock
│   ├── mcp_server/
│   │   ├── pyproject.toml
│   │   └── gds_etl_workbench/...
│   └── web_app/
│       ├── backend/
│       │   ├── pyproject.toml
│       │   ├── gds_workbench_api/...
│       │   └── gds_workbench_runtime/...
│       └── frontend/
│           ├── package.json
│           ├── index.html
│           ├── tsconfig.json
│           ├── tsconfig.build.json
│           ├── vite.config.mjs
│           └── src/...
└── gds-workbench-notebooks/
    ├── .env.example
    ├── .env
    ├── requirements.txt
    ├── src/
    │   ├── gds_workbench_notebooks/...
    │   ├── gds_workbench_runtime/...
    │   ├── gds_workbench_api/...
    │   └── gds_etl_workbench/...
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
        ├── validation.py
        └── 91_apply_workflow_draft.py
```

Databricks may display the marked entries under `notebooks/` without `.py`;
the CLI explicitly strips notebook extensions. That is normal. Files below
`src/` are ordinary Python modules: they must retain `.py` and their nested
package paths. See the official
[Workspace command reference](https://learn.microsoft.com/en-us/azure/databricks/dev-tools/cli/reference/workspace-commands).

The builder includes `.env.example`, never `.env`. Hidden files may be omitted
by an OS or browser upload dialog. If `.env.example` is missing, upload it
explicitly. Create the real `.env` manually in the notebook root after upload.

## 4. Deploy the notebooks in the UI

Database installation, the `gds_notebook_runtime` password, and its active
`security.notebook_runtime_principal` binding to one Super Admin service
Principal must already exist. See `databricks_notebooks/README.md` for the exact
binding and `.env` shape.

1. In **Workspace**, open an access-controlled user/team parent folder. Do not
   pre-create a second same-named child folder.
2. Drag the expanded local `gds-workbench-notebooks` folder into that parent.
3. Confirm `requirements.txt`, `src/`, and `notebooks/` are siblings, and all
   four Python packages remain under `src/`. Source-package `.py` files must be
   regular Workspace files; entry-point `.py` files under `notebooks/` must be
   Python notebook objects.
4. Copy `.env.example` to `.env` in the uploaded root. Replace placeholders with
   the PostgreSQL host, port, database, exact user `gds_notebook_runtime`, its
   password, and the Model Serving endpoint name. Do not enter a DSN, App name,
   endpoint URL, or web environment variables.
5. Limit read access to `.env`, the folder, and attached compute. This shared
   credential maps every notebook user to the same high-trust Super Admin
   workload identity; it does not provide individual user attribution.
6. Attach compute using Azure Databricks Runtime 16.4 LTS, Spark 3.5.2, Scala
   2.13, and Python 3.12.3.
7. Install dependencies in a temporary setup cell:

   ```python
   %pip install -r /Workspace/Users/<workspace-user>/gds-workbench-notebooks/requirements.txt
   dbutils.library.restartPython()
   ```

   A compute-scoped installation of the same pinned file is also valid.
8. Run `01_runtime_preflight.py`.
9. Open `00_tenant_lock.py`. Run its first cell to create its widget bar, fill
   the inputs, then run the second cell: check first, then acquire the intended
   Tenant Lock. The lock notebook can be checked before preflight while
   diagnosing DB access, but preflight-first avoids holding a lock while the
   full runtime is broken.
10. Open a workflow notebook. Run its first cell to create that workflow's own
    widgets, fill them, then run its second cell to execute. For an authoring
    draft, review the bounded completion output in the workbench, then use
    `91_apply_workflow_draft.py` with exact current revision/digest fences and
    `Confirmation=APPLY`. No separate review command is required. Preflight alone has no widgets.
11. Renew a long-running lock when required, and release it after the last
    workflow.

The source is imported through `<uploaded-root>/src`; no distribution or wheel
is used. Drafts live in PostgreSQL `mcp.model_change_set`. `mcp` is a schema
name here. `gds_etl_workbench` supplies shared domain/application code.
`requirements.txt` pins the Python `mcp` package because `openai-agents`
requires it transitively; no MCP server process is started or separately
deployed.

## 5. Deploy the optional App in the UI

The App is a separate entry point with its own database role, resources, and
native Databricks App access control. Deploying it does not enable or alter the
notebooks. Databricks App users still need App `CAN USE`; this deployment is not
a public unauthenticated web site.

The default artifact exposes the registered Databricks Model Serving models.
To expose registered Microsoft Foundry models in the same app, build with
`--agent-provider microsoft_foundry` and upload from
`artifacts/databricks-ui-foundry/`. Do not edit or replace its generated
`app.yaml`: it is already the combined-provider manifest and is covered by both
the tree manifest and ZIP checksum. The complete provider instructions are
copied into the app root as `DEPLOYMENT_GUIDE.md`.

The upload intentionally contains frontend source, not a checked-in `dist/`
folder. During App deployment, Azure Databricks detects the root `package.json`,
installs Node dependencies with `npm install`, installs the locked Python
environment with `uv sync`, runs the root `npm run build`, and then runs the
`app.yaml` command. That build creates `web_app/frontend/dist`. See the official
[Azure Databricks App deployment logic](https://learn.microsoft.com/en-us/azure/databricks/dev-tools/databricks-apps/deploy).

1. In **Workspace**, drag the expanded `gds-workbench-app-source` folder into
   the intended parent.
2. Confirm `app.yaml` is directly inside it, with `mcp_server/` and `web_app/`
   beside it. Confirm `gds_workbench_runtime/` is beside
   `gds_workbench_api/` under `web_app/backend/`.
3. Create or open the custom Databricks App and select **Medium** compute.
4. Before adding App resources, store each sensitive value in an existing
   Databricks secret scope/key. In the App resource dialog, add a **Secret**,
   select that scope/key, grant **Can read**, and assign the exact custom
   resource key below. Do not paste a secret value into `app.yaml`.

   For the default Databricks artifact, configure these exact App resource
   keys:

   | Resource key | Type | Permission |
   |---|---|---|
   | `postgres-dsn` | Existing secret scope/key | Can read |
   | `cursor-signing-key` | Existing secret scope/key | Can read |
   | `entra-tenant-id` | Existing secret scope/key | Can read |
   | `databricks-environment-code` | Existing secret scope/key | Can read |
   Grant the App service principal `CAN_QUERY` on every Databricks Model Serving
   endpoint named by a Databricks `deployment_name` in
   `agent_capabilities.json`.

   For the Foundry artifact, add these read-only
   secret resources:

   | Resource key | Stored value |
   |---|---|
   | `foundry-openai-base-url` | `https://<resource>.openai.azure.com/openai/v1/` or `https://<resource>.services.ai.azure.com/openai/v1/` |
   | `foundry-api-key` | API key stored as a secret; never literal YAML. |

   The Foundry artifact uses API-key authentication for initial development.
   See its `DEPLOYMENT_GUIDE.md` for the Entra client-credential configuration
   contract. Project routes under `/api/projects/` are not accepted by this
   Chat Completions integration.

   `app.yaml` maps those resource keys into `GDS_WEB_*` environment variables.
   `valueFrom` is the resource key, not the secret value. The PostgreSQL DSN
   uses the separate `gds_web_runtime` login. Never put resource values in
   `app.yaml`.

   If startup reports `production database DSN requires sslmode=require or verify-full`,
   the value stored behind `postgres-dsn` is wrong or stale. Replace that secret
   value, keep the same App resource key, and redeploy. Do not change
   `GDS_WEB_ENVIRONMENT`.

   If startup reports `DATABRICKS_HOST must be a valid HTTPS origin`, upload the
   current App source. It normalizes a Databricks-supplied bare workspace host
   to HTTPS. Do not add `DATABRICKS_HOST` to `app.yaml`; Databricks owns it.

   If PostgreSQL reports that `~/.postgresql/root.crt` does not exist or that
   certificate verification failed, upload the current App source. It replaces
   an omitted or `system` CA source with its pinned CA bundle. For development,
   `sslmode=require` is also accepted as an encrypted, non-verifying fallback.

   Use these placeholder value shapes in the selected resources:

   | Resource key | Value shape |
   |---|---|
   | `postgres-dsn` | `host=<postgresql-host> port=5432 dbname=<database> user=gds_web_runtime password='<password>' sslmode=verify-full` |
   | `cursor-signing-key` | Approved random UTF-8 value, 32 through 4096 bytes. |
   | `entra-tenant-id` | Nonzero Entra Tenant UUID accepted by the application. |
   | `databricks-environment-code` | Existing registered database Environment code; not a Tenant ID or URL. |
   | `foundry-openai-base-url` | One accepted Foundry resource OpenAI v1 URL shown above. |
   | `foundry-api-key` | API key stored behind the App secret resource. |

   Development-only TLS fallback for `postgres-dsn`:

   `host=<postgresql-host> port=5432 dbname=<database> user=gds_web_runtime password='<password>' sslmode=require`

   Do not combine `sslmode=require` with `sslrootcert=system`; the App removes
   that incompatible combination, but omitting it keeps the configuration clear.

   Keep these non-secret `app.yaml` values unchanged:

   | Name | Value | Purpose |
   |---|---|---|
   | `NODE_ENV` | `production` | Frontend/server production behavior. |
   | `GDS_WEB_ENVIRONMENT` | `production` | Rejects local identity mode. |
   | `GDS_WEB_STATIC_DIR` | `web_app/frontend/dist` | Built frontend path inside App source. |
   | `GDS_WEB_AGENT_EXECUTION_MODE` | `remote` | Uses registry-defined model deployments. |
   | `GDS_WEB_DATABRICKS_EXECUTION_MODE` | `remote` | Runs Databricks SQL remotely. |
5. Configure the existing user-authorization scopes
   `iam.access-control:read` and `iam.current-user:read`.
6. Grant the approved user/group `CAN USE` on the App and grant the App service
   principal read access to the source folder and `CAN_QUERY` on every Databricks
   `deployment_name` registered in `agent_capabilities.json`.
7. Select **Deploy**, choose `gds-workbench-app-source`, and wait for `Running`.
8. Verify `/healthz`, `/readyz`, the UI, authorization, and one approved smoke
   workflow.

The App's `mcp_server/gds_etl_workbench` directory is bundled shared Python
source. The App starts the HTTP server and background workflow worker from
`gds_workbench_api.app_process`; it does not require a separately deployed MCP
server.

## 6. CLI upload alternative

Use this only when UI drag-and-drop is unreliable. Authenticate the current
Databricks CLI profile to the target workspace, then run from the repository
root.

Use [`sync`](https://learn.microsoft.com/en-us/azure/databricks/dev-tools/cli/reference/sync-commands)
for the notebook artifact's ordinary source files, excluding the marked entry
points. Then use
[`workspace import-dir`](https://learn.microsoft.com/en-us/azure/databricks/dev-tools/cli/reference/workspace-commands)
only for `notebooks/` so those files become notebook objects. Databricks
documents that imported notebooks have their extensions stripped; applying
`import-dir` to `src/` would therefore break Python imports.

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

Use `databricks sync`, not `workspace import-dir`, for the App. The App's
Python packages must keep every `.py` suffix:

```bash
databricks workspace mkdirs "/Users/<workspace-user>/gds-workbench-app-source"
databricks sync \
  artifacts/databricks-ui/gds-workbench-app-source \
  "/Workspace/Users/<workspace-user>/gds-workbench-app-source"

databricks apps deploy <app-name> \
  --source-code-path "/Workspace/Users/<workspace-user>/gds-workbench-app-source"
```

For the Foundry variant, use the same commands with
`artifacts/databricks-ui-foundry/gds-workbench-app-source` as the local source.

Inspect both remote trees afterward. If notebook dotfiles were skipped,
explicitly import `.env.example` and the securely prepared `.env`; never place
the password in the command itself. Configure notebook compute and App
resources/permissions in the UI as described above.

If neither folder upload nor the appropriate CLI command preserves the
hierarchy, manually
create the nested Workspace folders and upload their files level by level. Do
not continue with a flattened tree.
