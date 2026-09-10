# Session contract

A session has one Tenant and at most one Model; its selected Model cannot change.

```text
GDS/<TENANT_CODE>/<SESSION>/
  session.json
  tasks/
  metadata/              metadata-change-set/
  model/                 model-change-set/
  code/
```

`manifest.json` allocates unreused IDs. `session.json` stores tasks, Model, SQL/subagent policy, stale areas and draft cache. Never store prompts, secrets, raw rows or history.

Open Workbench once after creation. On resume call local `status`. Treat `status.acceptance` as authoritative; verify digest, evidence binding and any Stage proof using `staging.md`. If they match and no Snapshot recovery is required, continue handoff without rerunning authoring, generators, validation or review; do not reopen Workbench unless asked.

## Tasks and coverage

Create `task-add --area metadata|model` before edits; Code/Validation are Model records. Record Snapshot IDs/revision. Maintain coverage through `task-plan` and its returned plan digest, separate from Change Set digest:

```text
Loop: target=<target>; phase=<phase>; scope=<n>; represented=<n>; context=<n>; excluded=<n>; blocked=<n>; next=<key|complete>
```

Coverage proves consideration, not output counts. Task states are internal; edits invalidate acceptance.

## Snapshots

The agent owns setup. For an unknown session path, ask once for working directory, run `session-init`, reuse the returned path.

For missing/stale Snapshots without an unapplied revision conflict:

1. Call `create_metadata_snapshot` for the Tenant, including required authorized `source_tenant_ids`, or `create_model_snapshot` for its Model.
2. Download the complete ZIP temporarily; never expose/save its signed URL.
3. `snapshot-install` verifies returned ID, bytes and SHA-256, replaces the area, and retires accepted applied records. Retirement recognizes schema defaults/equivalent decimals; approval digests remain byte-exact.
4. Delete ZIP; rerun `readiness`.

Never edit Snapshots or infer freshness from timestamps. Before Model Stage compare authoritative and installed revisions; mismatch requires `workflows/revision-recovery.md` before draft creation/caching. Direct installation over pending work fails; never auto-merge. Metadata has no tenant-wide revision: require freshness, Tenant Lock and server validation. Notify again for changed content; byte-identical reassessment retains acknowledgement.

Apply marks its area stale; refresh before dependent work. Model replacement requires a newer revision. For a locked folder, close Workbench/terminals inside it and retry the verified ZIP; never delete pending work. `cleanup_pending` means installation succeeded but recoverable backup cleanup remains, not failed Apply.

Metadata Enrichment needs both Snapshots and the scope Model's revision check; its task area is `metadata`. For another Source Tenant, retain scope evidence in the Model session and use that Tenant's metadata-only session (`metadata-authoring` readiness). Never install a foreign-owned Model there. Apply each Metadata Change Set under its own Tenant Lock, then refresh the main combined Metadata Snapshot. Shared input context grants no write authority.

## Reads and reusable evidence

`readiness` checks freshness, not applied workflow eligibility; check guide prerequisites. Bounded `select --where` reads Snapshot rows only. Overlay drafts by canonical key to inspect effective results.

`inspect_metadata`/`read_model_section` read live applied data; compare returned Model revision and reassess changes. Follow MCP `next_cursor`. Generated Code/Validation use local Snapshots. Local `select` has no cursor: narrow `truncated=true` results by known keys; discover missing keys through paginated MCP inventory. Never call partial coverage complete.

Keep `<session>/working/<task>/object-analysis/` with full physical Object keys indexing Markdown notes: grain, complete business-key tuples, dependencies, relationship decisions, evidence scope/method and open questions. Preserve Metadata findings before Apply. Cite Snapshot/query references; distinguish measured, documented and inferred evidence. Later phases read notes first; the modeling owner replaces superseded conclusions. No per-file JSON schema. `modeling-quality.md` binds cited notes to acceptance. Notes are temporary context, never Model state; omit rows, raw output, prompts and secrets.

`snapshot-install` installs downloaded archives. `snapshot-refresh` reconciles an existing replacement without fetching. Workbench **Refresh** only reloads local files.
