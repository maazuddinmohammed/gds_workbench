# Manual Databricks App upload

Use [the deployment runbook](../../web_app/DEPLOYMENT_GUIDE.md) for identities,
resources, acceptance and rollback. This file covers packaging/upload mechanics only.
Building locally does not deploy or authorize external changes.

Before redeployment, run [check_workflow_compatibility.sql](check_workflow_compatibility.sql)
in a fresh SQL session on the intended database. It reads catalogs inside a read-only
transaction and reports a summary plus failed workflow-function, permission or usage
column checks. It never executes workflow functions. PASS covers these workflow
contracts; the app's `/readyz` also checks other schema, reference data and login rules.

For an exhausted Run, use [inspect_workflow_recovery.sql](inspect_workflow_recovery.sql)
after setting its Tenant, Project and Run IDs. It reports bounded recovery, usage and
event counters in a read-only transaction; it omits event messages, tokens and physical
data. Both diagnostic files are included beside the source ZIP and covered by its
checksum list. They can be run before deploying.

```bash
python3 deployment/databricks_ui/build_uploads.py
```

The builder creates `artifacts/databricks-ui/` with one source directory and transport
ZIP, upload instructions, manifest and checksums. `--replace` replaces only output
previously owned by this builder. Canonical `app.yaml` is included before hashing;
never edit a generated artifact afterward.

Both Python packages include runtime `.py` and `.json` files in their `uv` build
cache keys. Source updates rebuild installed packages even when versions stay unchanged.

On Windows, the builder retries brief directory locks automatically. If access is
still denied, close programs using the artifact folders and retry with `--replace`,
or choose a new folder with `--output artifacts/databricks-ui-new`. A failed rebuild
restores the previous output. If restoration is also blocked, the error identifies
the preserved `previous` folder; recover it after releasing the lock.

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
