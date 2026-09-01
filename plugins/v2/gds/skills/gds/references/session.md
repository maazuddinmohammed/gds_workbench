# Compact session contract

Use one session for related work against one Tenant Code and one Model. Code and QA are `model`
tasks; `code/` contains only local Target Registration DDL.

## Layout and state

```text
GDS/<TENANT_CODE>/<SESSION>/
  session.json
  tasks/<ID>/<area>-change-set/  # only while stashed
  metadata/  metadata-change-set/
  model/     model-change-set/
  code/
```

`manifest.json`, beside the sessions, contains `{"current":"03","highest":3}`. Allocate `01`..`99`,
then `100` onward. Never reuse a deleted number.

Keep `session.json` compact:

```json
{"current":"02","model":[41,"Customer Model"],"sql":"never","tasks":[["01","metadata","Add metadata","applied"],["02","model","Build models","doing"]],"stale":["metadata"],"cs":{"model":["uuid",2,"active","02","digest"]}}
```

- `current`: task ID or `null`; `model`: bound ID/name; `sql`: `never`, `essential`, or `as_needed`;
  `tasks`: ID/area/title/state tuples.
- `stale`: areas made stale by Apply. `cs`: ID/revision/status/task ID/accepted local digest; cache
  never proves server state.

Omit empty keys. Do not store tenant, paths, timestamps, raw prompts, goal prose, or history. Store
an Automatic target order as ordinary task titles/plans, never a second journey structure.

`tasks/<ID>.json` holds ordered actions; acceptance/Apply markers are lazy sidecars. Stashing moves
pending work below `tasks/<ID>/`, removes acceptance, and reports `status.stashes`. Restore only to
an empty area after a fresh Snapshot, then re-accept. This prevents same-area task unions.

First plan line is readiness proof: `Inputs: metadata=<snapshot-id>; model=<snapshot-id>@<revision>`.
Long work adds `Loop: target=<target>; phase=<phase>; scope=<n>; covered=<n>; excluded=<n>; blocked=<n>; next=<key|final-review>`.
Update it after each batch. `status` returns current plan, or the first waiting task, else queued/todo.
Task state alone never identifies a final review;
the Loop line does. Reuse matching inputs; otherwise rerun one gate.
If resume finds `review` with a stale Loop line, recompute coverage from pending records before continuing.

## States

`queued`/`todo`/`doing` are captured/selected/active; `waiting`/`review` are blocked/local bytes changed;
`ready`/`overridden` are valid/digest-approved; `staged`/`applied` are reconciled/applied;
`done`/`cancelled` end without Apply. Infer next from queue order and retain completed tuples.

## Freshness

When a required Snapshot is absent, stop with:

> Download and unzip exactly one fresh `<area>` Snapshot into `<session>/<area>/`. Keep its generated root folder and every file unchanged, then tell me when it is ready.

The user downloads and unzips; the plugin never does. First mutation needs a fresh Snapshot. Reuse
it until Apply marks only that area stale; Stage/Validate do not. For replacement run
`snapshot-refresh`. If proof mismatches, run `readiness` for a known target or `inspect` otherwise—never both.
Label stale Quick reads `unverified`; never infer freshness from file time.
Model revision and Metadata contract proof are authoritative. Code/QA context digests bind current
Model records to Mapping and relevant Code.

Use one Model per session. Governed calls use `status.model[0]`; another Model needs another session.
