# Local runtime reference

Technical commands for agents and maintainers. For normal use, follow the
[usage guide](../docs/usage-guide.md).

Call each helper by absolute path as its own terminal command, as in the examples below, where `<plugin>` is the installed `atlas` plugin folder. Never `cd` first or combine commands with `&&`, `;`, pipes, redirects, loops or shell variables: hosts refuse such commands or ask the user to approve each one. `--session` always means the user's working directory containing `.atlas`, never the plugin source directory. Node.js 20+ is the main runtime; Snapshot ZIP installation also requires Python 3.12+. Windows PowerShell 5.1 provides the native fallback. Local helpers do not connect to databases or execute SQL. For governed submission, install the Stage Runner VSIX in VS Code. Microsoft credentials stay in VS Code. See [Copilot - VS Code setup](../docs/copilot-vs-code-installation-and-setup.md).

```sh
node <plugin>/scripts/atlas-local.js command-contract
node <plugin>/scripts/atlas-local.js command-contract --command session-init
```

The [machine command contract](../contracts/local-helper.json) lists exact arguments and limits. Commands that require an existing session accept `--output-file <new .atlas/temp/name.json>` to save one JSON result document; existing files are preserved and diagnostics stay separate. Use structured argument arrays for JSON/text; do not interpolate them into shell code. On Windows invoke `powershell.exe -NoProfile -File <plugin>/scripts/atlas-local.ps1 <command> ...` when Node is unavailable.

## Initialize and resume

After resolving the verified Tenant, absolute path and any needed Project:

```sh
node <plugin>/scripts/atlas-local.js session-init --root /work/customer --tenant DEMO --tenant-id 7
node <plugin>/scripts/atlas-local.js task-add --session /work/customer --outcome 'Enrich customer descriptions' --workflow atlas-metadata
node <plugin>/scripts/atlas-local.js status --session /work/customer
```

`session-init` reuses the same identity; it cannot replace another Tenant/Project. `project-select --project-id <id> --project-name <name>` attaches the first Project when a later workflow needs it. A different Project needs another directory. `owner-add` registers a verified additional Metadata owner for Project-derived work.

`status` returns the active task summary and total task count. Use `status --task <UUID> --detail full` for its complete bindings/evidence, or `status --history true --limit 50 [--cursor <next_cursor>]` for bounded history. Summary text is clipped explicitly; it cannot replace reading the complete task before replacement. A cursor binds the task list/session and query, while each task digest reflects its current content.

`task-select --task <UUID>` resumes a task without replacing workspace drafts or operation evidence. `task-update` takes the task file digest from `status` and either concise `--progress` or a complete replacement `--file`. Only outcome and schema version are mandatory. Add input bindings, paths and evidence when useful.

Set SQL choices using `sql-policy --policy never|essential|proactive [--environment dev|qa|stg|prod]`. Default environment is `dev` when SQL is permitted. Policy is an agent execution constraint; local query generation itself does not execute SQL. Under `never`, planning uses a saved environment or labels its context `dev`; this never permits execution.

Save the user's [sub-agent policy](tools/delegation.md) with one
of these commands. Run only the command that matches the selected choice:

```sh
node <plugin>/scripts/atlas-local.js subagent-policy --session /work/customer --mode current
node <plugin>/scripts/atlas-local.js subagent-policy --session /work/customer --mode auto
node <plugin>/scripts/atlas-local.js subagent-policy --session /work/customer --mode custom --model '<exact-model-name-or-id>'
```

Replace the custom model placeholder with the user's verified host model name
or ID. `--model` is required only for `custom` and rejected for the other modes.
The native PowerShell helper supports the same command and flags. `status`
returns `session.subagent_policy`; no field means the choice is unresolved.
Save it before useful authorized delegation or after an explicit user change. This setting survives task
switches and resume. It does not configure the host or start a sub-agent.

## Install, read and edit

1. Request the required Snapshot through `create_metadata_snapshot` or `create_project_snapshot`; obtain the archive using the host's supported download capability. Do not persist signed URLs/tokens in session records.
2. Call `snapshot-install` with the downloaded file and returned ID, size and SHA-256. The helper validates archive paths, members, hashes and scope before installation. It preserves the previous Snapshot under `.atlas/temp` and refuses unapplied draft replacement.
3. Use `inspect` for the catalog, `describe --dataset <name>` for the compact schema, and `select --dataset <name> --where <JSON> --view effective` for current records. Never open, search or parse Snapshot `data/` files instead: they omit pending drafts and flood the context. `--view snapshot` reads applied baseline only. Both are bounded. Follow `next_cursor` until null with the same filters/view/limit; changed Snapshot or selected draft inputs reject continuation. Optional `--fields '["object_description"]'` retains canonical keys and omits unrelated fields. Fetch complete effective records before editing; projected records are not complete proposals.
4. Create complete proposed records with `upsert` or `upsert-batch`, using the last `review` digest (`empty` only for a truly empty draft directory). `copy` imports selected baseline records while preserving existing proposals. `discard` removes a local proposal, not an applied record.
5. Run `validate` after each coherent phase and repair findings. It binds all used Snapshots, draft bytes and modeling evidence, and saves its report in the active task's evidence: when no task is active, run `task-add` first, including for check-only requests. Metadata ownership is separate from physical GDS placement.

Project-derived Metadata selection should record the Project Snapshot binding in `task.inputs.snapshots`. Validation verifies those declared inputs and includes them in approval evidence. Get identities/hashes from the installed manifest, never from filenames or invented revision values.

A baseline conflict while unapplied work exists requires explicit three-way review of original, current and proposed records. Preserve the old draft and Snapshot; do not empty the draft or edit a manifest to force installation. Complete or resolve the current operation before changing that baseline.

## Atlas Local Workbench

When local authoring/review needs it or the user requests it, open or reuse Atlas Local Workbench with `bash <plugin>/scripts/open-workbench.sh` or `<plugin>/scripts/open-workbench.ps1`. No Tenant, Project, workflow or Snapshot is required to open it. This opens the bundled static app in Chrome/Edge; it does not start a server. Once `.atlas` is ready, select the working directory in the browser, then reload local files after agent edits. Existing owners and operation status remain visible.

DBML is a user-only Atlas Local Workbench export of the complete Snapshot plus saved changes. There is no Atlas CLI or MCP export command. Agents use Project records and local validation; they never generate, read, inspect or use DBML. For an export request, direct the user to **Generate DBML** in Atlas Local Workbench.

## Profiling runs and Analysis files

Profiling runs through `start_profiling_run`, `get_profiling_run_status`, and
`cancel_profiling_run`. Follow the [profiling reference](logical-build/profiling.md).
The backend generates SQL and saves Attribute Profiles. After completion, install a fresh
Project Snapshot. Do not create SQL files, import results, or stage Profiling records.

Analysis retains `analysis-plan --session <directory> --plan-file <input.json>`.
The wrapper is `{selections: {batches: <batch-selections>, probes: [...]}, execution_connections: [...]}`.
Batch selections use `systems`/`objects` assignments with explicit `batch_ids`, and
`selected_objects` when narrowing scope. Each execution Connection entry contains
`connection_id`, `is_global_data_store: false`, and `source_tenant_codes` covering its endpoints.
All registered owner Metadata Snapshots are combined by canonical key; conflicting records fail.
Use the [relationship guide](logical-build/find-relationships.md) for probe shapes and
[query scope](query-scope.md) for safe execution and result handling. Numbered SQL files and
the plan are saved under `.atlas/temp/<task>/`. Analysis results remain agent-interpreted
and authored through the existing Analysis Change Set workflow.

## Mapping, code and DDL

Use `read_mapping_context` for all five components with one Project revision/context digest; follow every cursor before treating the view as fully read. If a call fails, run `next --session <dir> --area project --error <code>` and follow it; Snapshot Mapping rows lack resolved types and ordinals, so never rebuild the view from them. Save only the selected resolved records and their binding, not raw tool envelopes. Code may author from nonempty partial Mapping while retaining `complete:false` and reported gaps: missing Attribute rules use typed NULL placeholders with explicit review findings; missing Object logic cannot justify invented sources, joins or rows. Use a typed zero-row projection if row production lacks evidence. Malformed or contradictory authored rules still need correction. Validation continues to require `complete:true`. The [Mapping guide](project/mapping-documents.md#complete-context-for-coding-and-validation) defines exact calls.

Creation DDL and transformation SQL are agent-authored using the relevant workflow references. DDL stays separate from registered transformation artifacts. Read saved `generated_code` content using effective selection; copy it to the selected `code/` path only if absent or byte-identical. A differing file requires conflict review. Preserve exact content between a file and its complete Code record; neither export nor registration deploys it.

## Review and submission

Submit by repeating `next` as described in [submit with next](change-set-lifecycle.md#submit-with-next): local acknowledgement → Check Stage Runner → resolve draft → accept/prepare → Stage → server validation → separate Apply approval → Apply. Use its exact actions and direct response files; do not copy digests or curate JSON fields manually. Operation evidence, validation reports and Stage manifests stay under `.atlas/tasks/<task>.evidence/`; temporary downloads and query intermediates belong under `.atlas/temp/`. Do not hand-edit operation receipts or use narrative task progress as proof of approval.
