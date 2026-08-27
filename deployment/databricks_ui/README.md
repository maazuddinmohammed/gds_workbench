# Manual Azure Databricks UI uploads

This builder creates two clean source folders plus deterministic transport ZIPs
from the canonical repository sources. It copies no secret values, database
installers, tests, documentation, local tooling, caches, or generated build
output.

## Build

From the repository root:

```bash
python3 deployment/databricks_ui/build_uploads.py
```

To replace only a previous output created by this builder:

```bash
python3 deployment/databricks_ui/build_uploads.py --replace
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

Verify both ZIPs before transporting or extracting them:

```bash
cd artifacts/databricks-ui
shasum -a 256 -c SHA256SUMS.txt
```

Both lines must end in `OK`.

Use the two expanded folders as the primary Databricks UI input. Azure
Databricks supports dragging files and folders into the Workspace browser. Do
not import either ZIP directly into the Databricks UI: custom mixed-file ZIP
imports can flatten the hierarchy. The ZIPs contain folder contents and exist
for transport and reproducibility.

After both folder uploads, the Workspace source tree must look like this:

```text
<access-controlled team folder>/
├── gds-workbench-app-source/
│   ├── app.yaml
│   ├── pyproject.toml
│   ├── uv.lock
│   ├── package.json
│   ├── package-lock.json
│   ├── mcp_server/
│   │   ├── pyproject.toml
│   │   └── gds_etl_workbench/...
│   └── web_app/
│       ├── backend/
│       │   ├── pyproject.toml
│       │   ├── uv.lock
│       │   └── gds_workbench_api/...
│       └── frontend/
│           ├── package.json
│           ├── index.html
│           ├── tsconfig.json
│           ├── tsconfig.build.json
│           ├── vite.config.mjs
│           └── src/...
└── gds-workbench-notebooks/
    ├── requirements.txt
    ├── gds_workbench_notebooks/
    │   ├── __init__.py
    │   ├── app_client.py
    │   └── notebook.py
    └── notebooks/
        ├── analysis_inference.py
        ├── analysis_validation.py
        ├── code_generation.py
        ├── conceptual.py
        ├── dimensional.py
        ├── logical.py
        ├── mapping.py
        └── profiling.py
```

`mcp_server/` is a Python library dependency used by the backend in the same
App process. Do not create or deploy a separate Databricks MCP server.

## Upload the App source

1. On the VM, locate the expanded `gds-workbench-app-source` folder.
2. In **Workspace**, open the intended access-controlled user/team parent
   location. Do not create another same-named folder first.
3. Drag the entire local `gds-workbench-app-source` folder from the VM file
   browser into the Databricks Workspace browser.
4. Confirm `app.yaml` is directly inside `gds-workbench-app-source`, with
   `mcp_server/` and `web_app/` beside it.
5. Create or open the custom Databricks App.
6. Configure **Medium** compute.
7. Configure exactly these App resources:

   | Resource key | Type | Permission |
   |---|---|---|
   | `postgres-dsn` | Dedicated-scope secret | Read |
   | `cursor-signing-key` | Dedicated-scope secret | Read |
   | `entra-tenant-id` | Dedicated-scope secret | Read |
   | `databricks-environment-code` | Dedicated-scope secret | Read |
   | `agent-model-endpoint` | Standard Model Serving endpoint | Can query |

8. Configure only `iam.access-control:read` and `iam.current-user:read` as
   user-authorization scopes.
9. Grant the approved group `CAN USE` on the App.
10. Grant the App service principal read access to the source folder.
11. Select **Deploy**, choose `gds-workbench-app-source`, and wait for
    `Running`.
12. Verify `/healthz`, `/readyz`, the React UI, authorization, and one approved
    smoke workflow.

The environment-specific secret values, secret scope, user group, App name,
registered environment code, and endpoint name must already exist. Enter them
only through approved Databricks/Azure UI workflows. Never add them to these
files.

## Upload the notebooks

1. On the VM, locate the expanded `gds-workbench-notebooks` folder.
2. In **Workspace**, open the same parent location used for the App source. Do
   not create another same-named folder first.
3. Drag the entire local `gds-workbench-notebooks` folder from the VM file
   browser into the Databricks Workspace browser.
4. Confirm `requirements.txt`, `gds_workbench_notebooks/`, and `notebooks/` are
   siblings inside `gds-workbench-notebooks`.
5. Confirm the three files under `gds_workbench_notebooks/` are regular
   workspace **FILE** objects.
6. Confirm the eight files under `notebooks/` are Python **NOTEBOOK** objects.
7. Use Databricks Runtime 14.0 or newer and Python 3.10 or newer.
8. Install `requirements.txt` as a notebook-scoped library when the compute
   image does not already satisfy it.
9. Set the non-secret widgets, including the deployed physical `AppName`, then
   run only after the App is healthy and the user owns the required Tenant
   Lock.

## ZIP compatibility fallback

If the expanded folders cannot be copied to the VM, copy the ZIPs instead,
verify their checksums, and extract each ZIP locally into its same-named folder.
Then drag the extracted folder into Workspace. Do not upload the ZIP itself.

If folder drag-and-drop is unavailable in the workspace, use the Databricks App
**From Git** UI deployment or upload the files into manually created nested
folders. Do not continue from a flattened source tree.
