# Working context

Use this shared entry contract once per task, including direct skill entry. Load only the selected workflow and the references needed for its next decision. Reading another skill changes instructions in the same conversation; it is not a portable skill-call API.

## Golden rules

1. **Server truth comes only from governed MCP tools and installed Snapshots.** Never invent IDs, codes, revisions, digests or results. Read Snapshot records only through the helper: `inspect` for the catalog, `describe --dataset <name>` for a schema and `select --dataset <name> --view effective` for records including pending drafts. Never open, search or parse Snapshot `data/` files directly: they omit pending drafts and flood the context. Never edit Snapshot files or `.atlas/` state by hand.
2. **Local edits go through the helper.** Run each helper command as its own terminal command with literal absolute paths: `node <plugin>/scripts/atlas-local.js <command> --session <working-directory> ...`, where `<plugin>` is the installed Atlas plugin folder (it holds `skills/` and `scripts/`) and the working directory is the user's. When Node is unavailable, run `powershell.exe -NoProfile -File <plugin>/scripts/atlas-local.ps1 <command> ...` the same way. Never add `cd`, `&&`, `;`, pipes, redirects, loops or shell variables: hosts refuse such commands or ask the user to approve each one. Save long results with `--output-file`. Write complete records and preserve other pending drafts. Each write takes `--expected-digest`: the `digest` returned by the previous write or `review` (`empty` only for an empty draft). Commands written like `next --session <dir>` in skills mean this helper.
3. **Submit only through `next`.** It returns one action at a time. The user approves Stage and, separately, Apply. Earlier messages, task notes or a host confirmation never count as either approval.
4. **Never call Stage upload tools** (`stage_*`, `begin_*`, `put_*`, `commit_*`); the server refuses them. Never override a Tenant Lock unless the user explicitly asks.
5. **Project Input Scope and Profiling results are read-only here.** The web app manages Input Scope; backend Profiling writes profiles.
6. **Subject Areas decide which Objects a Logical or Dimensional Build works on; they are not modeling evidence.** Never cite an area or its definition as a source for Logical, Dimensional, Mapping, Code or SQL Validation work.
7. **Label evidence.** Separate measured, declared and inferred facts; a sample is not proof and unknown stays unknown. Run SQL only through `execute_databricks_sql` under the saved SQL policy and [query scope](query-scope.md).
8. **Ask instead of guessing consequential business decisions:** grain, identity, history, cross-System matching and missing-value policy. Stop at the requested outcome.
9. **Keep secrets and raw data out of chat and files:** no credentials, signed URLs, raw rows, prompts or tool dumps.
10. **After a failed MCP call**, run `next --session <dir> --area <area> --error <code>` and follow its one recovery action; when it says stop, stop and report the error. Never work around a failed governed read such as `read_mapping_context` by rebuilding its result from Snapshot rows.

## Initialize or resume

1. Identify the requested outcome before setup. General Atlas explanations and supplied-code discussion need no Tenant, Project, workspace or Workbench.
2. Resolve verified Tenant and Project identity only when records are needed, using [available reads](tools/initialization.md). Reuse explicit or valid saved selections; ask only for missing or ambiguous identity.
3. For local work, resolve an absolute directory. Reuse the saved directory; otherwise announce and use the actual current directory. An invalid supplied path needs correction. Preserve existing drafts and bindings. A different primary Tenant or Project needs a separate directory.
4. Inspect the active task and relevant unfinished work. Follow clear intent; ask about resuming only when it is ambiguous. Create one task per meaningful authoring outcome, not per tool call. `validate` also needs an active task: if none is active, run `task-add` first, even when the user asked only for a check or to change nothing. A task is local bookkeeping under `.atlas/`; it changes no records and submits nothing. Use [state and evidence](platform/state.md) for bindings and refresh decisions.
5. Resolve SQL policy/environment only when evidence execution is relevant. Never prohibits execution; Essential resolves blocking gaps; Proactive permits useful investigation within authorized scope. All queries follow [query scope](query-scope.md). Preparing SQL does not execute it or authorize execution.
6. Open/reuse Workbench when local authoring or review needs it, or when requested; use the [verified launcher](tools/initialization.md). A read-only explanation needs no browser setup.

Use the [interview method](modeling-interview.md#interaction-mode) for requested Grill Me discussion or consequential unresolved decisions. Otherwise explain and work through coherent parts without a mode-selection questionnaire. Load [delegation policy](tools/delegation.md) only before useful, authorized delegation.

Before authoring, read [record state](record-state.md) and [governance](platform/governance.md). Existing-output changes use [impact and update scope](methods/change-impact.md). Backend authorization remains authoritative. Missing capabilities follow the [capability boundaries](platform/capabilities.md); never invent a tool or substitute a different record meaning.
