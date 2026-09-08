# Session contract

Use one session per Tenant Code. It may be metadata-only; its selected Model cannot change.

```text
GDS/<TENANT_CODE>/<SESSION>/
  session.json
  tasks/
  metadata/              metadata-change-set/
  model/                 model-change-set/
  code/
```

`manifest.json` allocates unreused IDs. `session.json` keeps task, Model, SQL/subagent policy, stale areas, and server-draft cache. Never store prompts, secrets, raw rows, or history.

Open Workbench once after session creation. On resume call local `status`. Check the pending digest against acceptance and verify any Stage proof via `staging.md`. Treat `status.acceptance` as authoritative. If its digest matches and no Snapshot recovery is required, do not rerun authoring, generators, validation, or review. Continue handoff; do not reopen Workbench unless asked.

## Tasks and coverage

Create one `task-add --area metadata|model` task before edits, including Code/Validation as Model records. Record Snapshot IDs and Model revision. Keep coverage in its plan using `task-plan` and the returned plan digest, separate from the Change Set digest:

```text
Loop: target=<target>; phase=<phase>; scope=<n>; represented=<n>; context=<n>; excluded=<n>; blocked=<n>; next=<key|complete>
```

Coverage proves each input was considered, not produced as output.

Task states are internal. Local edits invalidate digest acceptance.

## Snapshot freshness

The agent owns setup. If the session path is unknown, ask once for the working directory, run `session-init`, and reuse its path.

When a required Snapshot is missing or stale (not an unapplied revision conflict):

1. Call `create_metadata_snapshot` for the session Tenant or `create_model_snapshot` for its Model.
2. Download its complete ZIP temporarily. Never expose or save the signed URL.
3. Run `snapshot-install` with returned ID, bytes, and SHA-256. It verifies and replaces the area, retiring exact applied records when stale.
4. Delete the ZIP and rerun `readiness`.

Ask only for unresolved download/session information. Never edit Snapshots or infer freshness from timestamps.

Before Model Stage, compare the authoritative Model revision with the installed Model Snapshot. On mismatch, follow `workflows/revision-recovery.md` before creating/caching a draft; direct install over pending work fails; never auto-merge. Metadata has no tenant-wide revision: require its Snapshot to be non-stale, acquire the Tenant Lock, and let server validation recheck current database state. Never infer a Metadata revision. Notify again only if local content changed; byte-identical content retains acknowledgement.

Apply marks its area stale. Refresh before dependent work. Model replacement requires a newer revision.

Metadata Enrichment requires both Snapshots and a selected Model. Its task area is `metadata`; check Model revision before handoff because that Snapshot determines scope. Physical results are shared by every Model using those Objects.

## Read the right data

`readiness` checks Snapshot presence/freshness, not applied workflow eligibility. Check the active guide's prerequisites separately. Author against installed Snapshots using bounded `select --where`; it reads Snapshot rows only. To inspect the effective result, overlay the corresponding local draft records by canonical key. Do not confuse draft records with applied data.

`inspect_metadata` and `read_model_section` read live applied data. Compare Model reads' returned revision to the installed revision; reassess on mismatch. Follow MCP `next_cursor` when traversing a dataset. Generated Code/Validation require local Snapshot reads. Local `select` has no cursor: when `truncated=true`, narrow by known entity/object/System/attribute keys; never call a partial page complete. Use paginated MCP inventory reads to discover missing keys.

`snapshot-install` installs a newly downloaded archive. `snapshot-refresh` only reconciles a replacement already on disk; it does not fetch a Snapshot. Use `snapshot-install` for the normal refresh path. Workbench **Refresh** only reloads local files.
