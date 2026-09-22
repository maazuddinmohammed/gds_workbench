# Manual Azure Databricks App deployment

The builder creates one source-only upload folder, `gds-workbench-app-source`,
containing the web UI, FastAPI backend, and background workflow worker. It
includes the shared governed domain code and runs independently of the Azure
App Service MCP server.

## 1. Build and verify

From the repository root on the VM:

```bash
python3 deployment/databricks_ui/build_uploads.py
```

The single build uses Microsoft Foundry through the OpenAI Agents SDK and
writes `artifacts/databricks-ui/`. Canonical `app.yaml` is included before the
tree manifest, ZIP, and SHA-256 files are created. Do not copy or replace a
manifest after building.

To replace only an output previously created by this builder:

```bash
python3 deployment/databricks_ui/build_uploads.py --replace
```

Output:

```text
artifacts/databricks-ui/
├── gds-workbench-app-source/
├── gds-workbench-app-source.zip
├── UPLOAD_INSTRUCTIONS.md
├── artifact-manifest.json
└── SHA256SUMS.txt
```

Verify the transport ZIP before extracting it:

```bash
cd artifacts/databricks-ui
shasum -a 256 -c SHA256SUMS.txt
```

The checksum line must end in `OK`.

## 2. Do not import the ZIP in the Workspace UI

The ZIP is a transport container only. Azure Databricks can treat a mixed ZIP
as a notebook import and flatten its nested source folders. If a ZIP was copied
to the VM, extract it locally first. Upload the expanded same-named folder.

Use [Workspace files](https://learn.microsoft.com/en-us/azure/databricks/files/workspace)
to retain ordinary source files and nested directories.

## 3. Expected Workspace tree

After upload, compare the Workspace browser with this tree. Stop and reupload
from an expanded folder if any level was flattened.

```text
<access-controlled Workspace parent>/
└── gds-workbench-app-source/
    ├── app.yaml
    ├── DEPLOYMENT_GUIDE.md
    ├── package.json
    ├── package-lock.json
    ├── pyproject.toml
    ├── uv.lock
    ├── mcp_server/
    │   ├── pyproject.toml
    │   └── gds_etl_workbench/...
    └── web_app/
        ├── backend/
        │   ├── pyproject.toml
        │   └── gds_workbench_api/...
        └── frontend/
            ├── package.json
            ├── index.html
            ├── tsconfig.json
            ├── tsconfig.build.json
            ├── vite.config.mjs
            └── src/...
```

Python modules must retain `.py` and their nested package paths.

## 4. Deploy the App in the UI

Databricks App users need App `CAN USE`. The App has its own database role,
resources, and native Databricks App access control.

The artifact exposes the registered Microsoft Foundry models through the
OpenAI Agents SDK. Users choose the model and reasoning effort; execution mode
is a workflow choice. Do not edit or replace its generated `app.yaml`: the
canonical manifest is covered by the tree manifest and ZIP checksum. Complete
authentication instructions are copied into the App root as
`DEPLOYMENT_GUIDE.md`.

The upload intentionally contains frontend source, not a checked-in `dist/`
folder. During App deployment, Azure Databricks detects the root `package.json`,
installs Node dependencies with `npm install`, installs the locked Python
environment with `uv sync`, runs the root `npm run build`, and then runs the
`app.yaml` command. That build creates `web_app/frontend/dist`. See the official
[Azure Databricks App deployment logic](https://learn.microsoft.com/en-us/azure/databricks/dev-tools/databricks-apps/deploy).

1. In **Workspace**, drag the expanded `gds-workbench-app-source` folder into
   the intended parent.
2. Confirm `app.yaml` is directly inside it, with `mcp_server/` and `web_app/`
   beside it. Confirm `gds_workbench_api/` is under `web_app/backend/`.
3. Create or open the custom Databricks App and select **Medium** compute.
4. Before adding App resources, store each sensitive value in an existing
   Databricks secret scope/key. In the App resource dialog, add a **Secret**,
   select that scope/key, grant **Can read**, and assign the exact custom
   resource key below. Do not paste a secret value into `app.yaml`.

   Configure these exact read-only App resource keys:

   | Resource key | Type | Permission |
   |---|---|---|
   | `postgres-dsn` | Existing secret scope/key | Can read |
   | `cursor-signing-key` | Existing secret scope/key | Can read |
   | `entra-tenant-id` | Existing secret scope/key | Can read |
   | `databricks-environment-code` | Existing secret scope/key | Can read |
   | `foundry-openai-base-url` | Existing secret scope/key | Can read |
   | `foundry-api-key` | Existing secret scope/key | Can read |

   Canonical `app.yaml` uses API-key authentication.
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
   | `foundry-openai-base-url` | `https://<resource>.openai.azure.com/openai/v1/` or, for API-key authentication, `https://<resource>.services.ai.azure.com/openai/v1/`. |
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
   principal read access to the source folder. Keep the existing governed
   Databricks SQL permissions; authorize Foundry through the configured API key
   or dedicated Entra application.
7. Select **Deploy**, choose `gds-workbench-app-source`, and wait for `Running`.
8. Verify `/healthz`, `/readyz`, the UI, authorization, and one approved smoke
   workflow.

The App's `mcp_server/gds_etl_workbench` directory is bundled shared Python
source. The App starts the HTTP server and background workflow worker from
`gds_workbench_api.app_process`; it does not require a separately deployed MCP
server.

## 5. CLI upload alternative

Use this only when UI drag-and-drop is unreliable. Authenticate the current
Databricks CLI profile to the target workspace, then run from the repository
root.

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

Inspect the remote tree afterward. Configure App resources and permissions in
the UI as described above.

If neither folder upload nor the appropriate CLI command preserves the
hierarchy, manually
create the nested Workspace folders and upload their files level by level. Do
not continue with a flattened tree.
