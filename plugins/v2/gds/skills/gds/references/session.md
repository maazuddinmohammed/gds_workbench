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

`manifest.json` allocates unreused IDs. `session.json` keeps task, Model, SQL policy, stale areas, and server-draft cache. Never store prompts, secrets, raw rows, or history.

Open Workbench once after session creation. On resume call local `status`. Treat `status.acceptance` as authoritative. If its digest matches, do not rerun authoring, generators, validation, or review. Continue handoff; do not reopen Workbench unless asked.

## Tasks and coverage

Record Snapshot IDs and Model revision first. Long work adds:

```text
Loop: target=<target>; phase=<phase>; scope=<n>; represented=<n>; context=<n>; excluded=<n>; blocked=<n>; next=<key|complete>
```

Coverage proves each input was considered, not produced as output.

Task states are internal. Local edits invalidate digest acceptance.

## Snapshot freshness

The agent owns setup. If the session path is unknown, ask once for the working directory, run `session-init`, and reuse its path.

When a required Snapshot is missing or stale:

1. Call `create_metadata_snapshot` for the session Tenant or `create_model_snapshot` for its Model.
2. Download its complete ZIP temporarily. Never expose or save the signed URL.
3. Run `snapshot-install` with returned ID, bytes, and SHA-256. It verifies and replaces the area, retiring exact applied records when stale.
4. Delete the ZIP and rerun `readiness`.

Ask only for unresolved download/session information. Never edit Snapshots or infer freshness from timestamps.

Before Model Stage, compare the authoritative Model revision with the installed Model Snapshot. On mismatch, refresh and reassess; never auto-merge. Metadata has no tenant-wide revision: require its Snapshot to be non-stale, acquire the Tenant Lock, and let server validation recheck current database state. Never infer a Metadata revision. Notify again only if local content changed; byte-identical content retains acknowledgement.

Apply marks its area stale. Refresh before dependent work. Model replacement requires a newer revision.
