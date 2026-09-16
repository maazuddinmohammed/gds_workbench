# Local runtime

Run from the installed `atlas` plugin directory. `--session` always means the user's working directory containing `.atlas`, never the plugin source directory. Node.js 20+ is the main runtime; Snapshot ZIP installation also requires Python 3.12+. Windows PowerShell 5.1 provides the native fallback. Local helpers do not connect to databases or execute SQL. Install the matching Stage Runner VSIX in VS Code for governed submission; its connection is separate from MCP.

```sh
node scripts/atlas-local.js command-contract
node scripts/atlas-local.js command-contract --command session-init
```

The [machine command contract](../contracts/local-helper.json) lists exact arguments and limits. Commands that require an existing session accept `--output-file <new .atlas/temp/name.json>` to save one JSON result document; existing files are preserved and diagnostics stay separate. Use structured argument arrays for JSON/text; do not interpolate them into shell code. On Windows invoke `powershell.exe -NoProfile -File scripts/atlas-local.ps1 <command> ...` when Node is unavailable.

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

## Workbench

At every Atlas start/resume, immediately open or reuse Workbench with `bash scripts/open-workbench.sh` or `scripts/open-workbench.ps1`. No Tenant, Model, workflow or Snapshot is required to open it. This opens the bundled static app in Chrome/Edge; it does not start a server. Once `.atlas` is ready, select the working directory in the browser, then reload local files after agent edits. Existing owners and operation status remain visible.

DBML is a user-only Workbench export of the complete Snapshot plus saved changes. There is no Atlas CLI or MCP export command. Agents use Model records and local validation; they never generate, read, inspect or use DBML. For an export request, direct the user to **Generate DBML** in Workbench.

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

Optional `selections.max_attributes_per_query` is an integer 1–50 (default 50). Lower it when planning for a smaller server result limit or host response size; it preserves each Object's complete selected batch set.

The result identifies a `plan.json` and numbered SQL files under `.atlas/temp/<task>/`. Each query includes SHA-256, physical scope, batch IDs, expected Attribute rows and execution Connection/environment. Process one SQL file and its result at a time under [query scope](../references/query-scope.md#execute-bounded-sql). Prefer `structuredContent`, otherwise parse one JSON text result; process only one copy. Check columns, row/cell truncation and expected Attribute indexes. Do not echo SQL, plans or results into conversation; report completed/total groups and unresolved counts.

Save each complete profiling aggregate payload under `result`, with the query filename and actual execution time. Keep only this canonical JSON payload, not the MCP envelope or both response copies; never persist physical data rows or credentials. `profile-results` takes the generated plan, current draft digest and one JSON array of groups. This synthetic example profiles one string Attribute:

```json
[{
  "file": "0001.sql",
  "executed_at": "2026-09-15T12:00:00Z",
  "result": {
    "schema_version": "1.0",
    "connection_id": 23,
    "environment_code": "dev",
    "statement_count": 1,
    "row_limit": 50,
    "columns": ["attribute_index", "row_count", "non_null_count", "null_count", "blank_count", "distinct_count", "min_data_length", "max_data_length", "avg_data_length", "percent_populated", "percent_duplicates", "percent_null", "percent_blank", "percent_distinct"],
    "rows": [[1, 10, 10, 0, 0, 10, 1, 5, 3, 100, 0, 0, 0, 100]],
    "row_count": 1,
    "rows_truncated": false,
    "cells_truncated": false
  }
}]
```

Once all planned groups are complete, run `profile-results --session <directory> --plan-file <plan.json> --results-file <aggregates.json> --expected-digest <current-digest>`. It verifies complete responses/bindings, matches the 14 columns by name, checks coverage/metrics, maps indexes to physical keys, merges `profiling_profile` records and saves concise durable evidence. Do not reshape responses or manually rebuild/upsert those records as well. The older curated named-row format remains accepted for compatibility. The helper does not call Databricks.

For an oversized/truncated response, discard only that group's partial result and follow [group recovery](../references/logical-build/profiling.md#files-and-execution) with the same Object/batch scope. Lowering the group maximum generates a new plan, not an automatic partial retry. Preserve successful unaffected queries/results; import requires one complete result for every query in the current plan.

For `analysis-plan`, use the same wrapper; `selections` is `{batches:<profiling-selection>, probes:[...]}`. Supported probe shapes live in the [relationship guide](../references/logical-build/find-relationships.md); use `analysis.js` only for needed measurements. The agent converts interpreted results into the exact [Analysis record](../references/model/analysis-result.md) with `upsert-batch`; metadata-derived inference needs no fabricated SQL evidence.

## Mapping, code and DDL

Use `read_mapping_context` for all five components with one Model revision/context digest; follow every cursor before treating the view as complete. Save only the selected resolved records and their binding, not raw tool envelopes. `complete:false` blocks code generation until the reported gaps are resolved. The [Mapping guide](../references/model/mapping-documents.md#complete-context-for-coding-and-validation) defines exact calls.

Creation DDL and transformation SQL are agent-authored using the relevant workflow references. DDL stays separate from registered transformation artifacts. Read saved `generated_code` content using effective selection; copy it to the selected `code/` path only if absent or byte-identical. A differing file requires conflict review. Preserve exact content between a file and its complete Code record; neither export nor registration deploys it.

## Review and submission

Follow the [complete submission sequence](../references/change-set-lifecycle.md#complete-submission-sequence): Check Stage Runner → local acknowledgement → resolve draft → accept/prepare → Stage → server validation → separate Apply approval → Apply. Use its exact commands and direct response files; do not copy digests or curate JSON fields manually. Operation evidence, validation reports and Stage manifests stay under `.atlas/tasks/<task>.evidence/`; temporary downloads and query intermediates belong under `.atlas/temp/`. Do not hand-edit operation receipts or use narrative task progress as proof of approval.
