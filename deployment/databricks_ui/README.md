# Manual Databricks App upload

Use [the deployment runbook](../../web_app/DEPLOYMENT_GUIDE.md) for identities,
resources, acceptance and rollback. This file covers packaging/upload mechanics only.
Building locally does not deploy or authorize external changes.

```bash
python3 deployment/databricks_ui/build_uploads.py
```

The builder creates `artifacts/databricks-ui/` with one source directory and transport
ZIP, upload instructions, manifest and checksums. `--replace` replaces only output
previously owned by this builder. Canonical `app.yaml` is included before hashing;
never edit a generated artifact afterward.

```bash
cd artifacts/databricks-ui
shasum -a 256 -c SHA256SUMS.txt
```

Upload the expanded `gds-workbench-app-source` directory to an access-controlled
Databricks Workspace location. Do not import the ZIP as notebooks; that can flatten
Python/package paths. Verify this nesting before selecting the App source folder:

```text
gds-workbench-app-source/
├── app.yaml
├── DEPLOYMENT_GUIDE.md
├── package.json, package-lock.json
├── pyproject.toml, uv.lock
├── mcp_server/gds_etl_workbench/
└── web_app/
    ├── backend/gds_workbench_api/
    └── frontend/src/
```

Python files retain `.py` and package directories. The copied deployment guide is
self-contained for runtime configuration. The artifact contains source, not frontend
`dist`; managed deployment runs the root build before starting the supervised App.
Use approved App resources and user scopes from canonical manifests/runbook.

For an approved CLI upload, use `databricks workspace import-dir` with the expanded
source folder and intended profile, then select that Workspace folder as App source.
Check CLI help for destination overwrite behavior before replacing an existing upload.
Uploading source and starting/deploying an App are separate operations.
