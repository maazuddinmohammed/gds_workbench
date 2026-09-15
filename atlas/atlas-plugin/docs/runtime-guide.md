# Local runtime

Run from the installed `atlas` plugin directory. `--session` always means the user's working directory containing `.atlas`, never the plugin source directory. Node.js 20+ is the main runtime; Snapshot ZIP installation also requires Python 3.12+. Windows PowerShell 5.1 provides the native fallback. Commands do not connect to databases or execute SQL.

```sh
node scripts/atlas-local.js command-contract
node scripts/atlas-local.js command-contract --command session-init
```

The [machine command contract](../contracts/local-helper.json) lists exact arguments and limits. Use structured argument arrays for JSON/text; do not interpolate them into shell code. On Windows invoke `powershell.exe -NoProfile -File scripts/atlas-local.ps1 <command> ...` when Node is unavailable.

## Initialize and resume

After resolving the verified Tenant, absolute path and any needed Model:

```sh
node scripts/atlas-local.js session-init --root /work/customer --tenant DEMO --tenant-id 7
node scripts/atlas-local.js task-add --session /work/customer --outcome 'Enrich customer descriptions' --workflow atlas-metadata-enrichment
node scripts/atlas-local.js status --session /work/customer
```

`session-init` reuses the same identity; it cannot replace another Tenant/Model. `model-select --model-id <id> --model-name <name>` attaches the first Model when a later workflow needs it. A different Model needs another directory. `owner-add` registers a verified additional Metadata owner for Model-derived work.

`task-select --task <UUID>` resumes a task without replacing workspace drafts or operation evidence. `task-update` takes the task file digest from `status` and either concise `--progress` or a complete replacement `--file`. Only outcome and schema version are mandatory. Add input bindings, paths and evidence when useful.

Set SQL choices using `sql-policy --policy never|essential|proactive [--environment dev|qa|stg|prod]`. Default environment is `dev` when SQL is permitted. Policy is an agent execution constraint; local query generation itself does not execute SQL. Under `never`, planning uses a saved environment or labels its context `dev`; this never permits execution.

## Install, read and edit

1. Request the required Snapshot through `create_metadata_snapshot` or `create_model_snapshot`; obtain the archive using the host's supported download capability. Do not persist signed URLs/tokens in session records.
2. Call `snapshot-install` with the downloaded file and returned ID, size and SHA-256. The helper validates archive paths, members, hashes and scope before installation. It preserves the previous Snapshot under `.atlas/temp` and refuses unapplied draft replacement.
3. Use `inspect` for the catalog, `describe --dataset <name>` for the compact schema, and `select --dataset <name> --where <JSON> --view effective` for current records. `--view snapshot` reads applied baseline only. Both are bounded; narrow a truncated selection by known keys.
4. Create complete proposed records with `upsert` or `upsert-batch`, using the last `review` digest (`empty` only for a truly empty draft directory). `copy` imports selected baseline records while preserving existing proposals. `discard` removes a local proposal, not an applied record.
5. Run `validate` after each coherent phase and repair findings. It binds all used Snapshots, draft bytes and modeling evidence. Metadata ownership is separate from physical GDS placement.

Model-derived Metadata selection should record the Model Snapshot binding in `task.inputs.snapshots`. Validation verifies those declared inputs and includes them in approval evidence. Get identities/hashes from the installed manifest, never from filenames or invented revision values.

A baseline conflict while unapplied work exists requires explicit three-way review of original, current and proposed records. Preserve the old draft and Snapshot; do not empty the draft or edit a manifest to force installation. Complete or resolve the current operation before changing that baseline.

## Workbench and DBML

Use `bash scripts/open-workbench.sh` or `scripts/open-workbench.ps1`. This opens the bundled static app in Chrome/Edge; it does not start a server. Select the working directory in the browser, then reload local files after agent edits. Existing owners and operation status remain visible.

`generate-dbml --session <path> --area model` validates and renders the complete effective Model. It replaces `model-dbml` only after inputs remain unchanged; previous exports are retained in `.atlas/temp`. The browser uses the same merger and structural validation. DBML generation is not proof of business modeling quality.

## Profiling and Analysis files

`profile-plan --plan-file <input.json>` accepts this wrapper; all IDs/coordinates below are synthetic:

```json
{
  "selections": {
    "systems": [{"source_tenant_code": "DEMO", "system_code": "CRM", "batch_ids": ["10", "11"]}]
  },
  "execution_connections": [{"connection_id": 23, "is_global_data_store": false, "source_tenant_codes": ["DEMO"]}]
}
```

Resolve Connection access through MCP first. `selections.objects` can override batch lists for exact Object keys; `selected_objects` narrows active applied Model Input Scope. See [profiling](../references/logical-build/profiling.md) and [query scope](../references/query-scope.md). All registered owner Metadata Snapshots are combined by canonical key, with conflicting shared records rejected.

The result identifies a `plan.json` and numbered SQL files under `.atlas/temp/<task>/`. Each query includes SHA-256, physical scope, batch IDs, expected Attribute rows and execution Connection/environment. Send one SQL file's text per governed call, following policy. Check returned columns, row/cell truncation and all expected Attribute indexes before using results. Never persist raw tool envelopes or physical data rows.

`profile-results` takes the generated plan, current draft digest and a JSON array of curated aggregate results:

```json
[{
  "file": "0001.sql",
  "connection_id": 23,
  "environment": "dev",
  "executed_at": "2026-09-15T12:00:00Z",
  "truncated": false,
  "rows": []
}]
```

`rows` must contain every expected Attribute's exact 14-column result (index plus 13 metrics); the empty example above shows shape only and fails for a nonempty planned group. The helper checks scope, query hashes, coverage and metrics, then merges `profiling_profile` records and saves concise durable evidence. It does not call Databricks.

For `analysis-plan`, use the same wrapper; `selections` is `{batches:<profiling-selection>, probes:[...]}`. Supported probe shapes live in the [relationship guide](../references/logical-build/find-relationships.md); use `analysis.js` only for needed measurements. The agent converts interpreted results into the exact [Analysis record](../references/model/analysis-result.md) with `upsert-batch`; metadata-derived inference needs no fabricated SQL evidence.

## Mapping, code and DDL

Use `read_mapping_context` for all five components with one Model revision/context digest; follow every cursor before treating the view as complete. Save only the selected resolved records and their binding, not raw tool envelopes. `complete:false` blocks code generation until the reported gaps are resolved. The [Mapping guide](../references/model/mapping-documents.md#complete-context-for-coding-and-validation) defines exact calls.

Creation DDL and transformation SQL are agent-authored using the relevant workflow references. DDL stays separate from registered transformation artifacts. Read saved `generated_code` content using effective selection; copy it to the selected `code/` path only if absent or byte-identical. A differing file requires conflict review. Preserve exact content between a file and its complete Code record; neither export nor registration deploys it.

## Review and submission

Follow the [shared lifecycle](../references/change-set-lifecycle.md). Operation evidence, validation reports and Stage manifests stay under `.atlas/tasks/<task>.evidence/`; temporary downloads and query intermediates belong under `.atlas/temp/`. Do not hand-edit operation receipts or use narrative task progress as proof of approval.
