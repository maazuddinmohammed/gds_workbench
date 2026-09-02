# Session contract

Use one session for one Tenant Code. A session may be metadata-only; after a Model is selected it cannot switch Models.

```text
GDS/<TENANT_CODE>/<SESSION>/
  session.json
  tasks/
  metadata/              metadata-change-set/
  model/                 model-change-set/
  code/
```

`manifest.json` beside the sessions allocates `01`, `02`, and so on without reuse. `session.json` keeps only current task, Model, SQL policy, task tuples, stale areas, and server-draft cache. Never store prompts, secrets, raw rows, or history.

Open Workbench once after creating the session. On resume call local `status`; do not reopen Workbench unless asked.

## Tasks and coverage

The first plan line records Snapshot IDs and Model revision. Long authoring adds:

```text
Loop: target=<target>; phase=<phase>; scope=<n>; represented=<n>; context=<n>; excluded=<n>; blocked=<n>; next=<key|complete>
```

Coverage proves that every selected input was considered. It does not require one output per input.

Internal task states may include `queued`, `doing`, `review`, `ready`, `staged`, and `applied`. Do not present them as user actions. Local edits invalidate digest acceptance.

## Snapshot freshness

The user manually downloads the complete Snapshot from the MCP tool result and unzips its single root into `metadata/` or `model/`. Tell the user where to place it, but never repeat its temporary signed URL in chat. Never edit Snapshot files or infer freshness from timestamps.

Before Stage, compare the authoritative revision with the reviewed Snapshot revision. If different, stop and request a fresh Snapshot. Reassess all affected records; never auto-merge. If content changes, notify the user again. If content remains byte-identical, the existing acknowledgement remains valid.

Apply marks only the written area stale. `snapshot-refresh` retires applied local intent only after a replacement Snapshot proves the exact applied records and, for Model, a newer revision.
