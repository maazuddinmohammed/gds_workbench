# Manual Azure Databricks UI uploads

This builder creates two clean, deterministic upload ZIPs from the canonical
repository sources. It copies no secret values, database installers, tests,
documentation, local tooling, caches, or generated build output.

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

Verify both ZIPs before uploading them:

```bash
cd artifacts/databricks-ui
shasum -a 256 -c SHA256SUMS.txt
```

Both lines must end in `OK`.

The ZIPs contain folder contents, not an additional outer folder. Follow the
target-folder steps below so the files are not scattered or double-nested.

After both imports, the Workspace source tree must look like this:

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

1. In **Workspace**, open the intended access-controlled user/team location.
2. Create and open a folder named `gds-workbench-app-source`.
3. In that folder, select **Import** and upload
   `gds-workbench-app-source.zip`.
4. Confirm `app.yaml` is directly inside the folder.
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

1. In **Workspace**, create and open a folder named
   `gds-workbench-notebooks` beside, not inside, the App source folder.
2. In that folder, select **Import** and upload
   `gds-workbench-notebooks.zip`.
3. Confirm `requirements.txt`, `gds_workbench_notebooks/`, and `notebooks/` are
   siblings.
4. Confirm the three files under `gds_workbench_notebooks/` are regular
   workspace **FILE** objects.
5. Confirm the eight files under `notebooks/` are Python **NOTEBOOK** objects.
6. Use Databricks Runtime 14.0 or newer and Python 3.10 or newer.
7. Install `requirements.txt` as a notebook-scoped library when the compute
   image does not already satisfy it.
8. Set the non-secret widgets, including the deployed physical `AppName`, then
   run only after the App is healthy and the user owns the required Tenant
   Lock.

Do not import either ZIP from the parent Workspace folder. Each ZIP is designed
to be imported from inside its already-created same-named target folder.
