# Compact session contract

Use a session for related work against one Tenant Code and one Model. A session can grow across metadata, model, code, and validation tasks.

## Layout

```text
GDS/<TENANT_CODE>/
  manifest.json
  01/
    session.json
    tasks/
      <ID>/<area>-change-set/  # only while stashed
    metadata/
    metadata-change-set/
    model/
    model-change-set/
    code/
```

`manifest.json` contains only the current session and highest allocated number:

```json
{"current":"03","highest":3}
```

Allocate two digits through `99`, then `100`, `101`, and so on. Never reuse a deleted session number. Tenant directories use Tenant Code, never Tenant ID.

## Session state

Keep `session.json` compact:

```json
{"current":"02","model":[41,"Customer Model"],"tasks":[["01","metadata","Add metadata","applied"],["02","model","Build models","doing"]],"stale":["metadata"],"cs":{"model":["uuid",2,"active","02","digest"]}}
```

- `current`: current task ID, or `null` when none.
- `model`: optional bound `[Model ID, Model name]`. The first trusted Model Snapshot adds it automatically; another Model ID is rejected.
- `tasks`: queue tuples `[task ID, area, short title, state]` in creation order.
- `stale`: only areas made stale by a successful Apply.
- `cs`: draft cache as `[ID, revision, status, task ID, accepted local digest]`. It never proves server state.

Omit empty optional keys. Do not store goal, tenant, session ID, path, timestamps, raw prompts, history, targets, or sub-focus lists here.

Each `tasks/<ID>.json` holds short ordered actions. Normally read only the current plan. Acceptance and Apply input markers use lazy `<ID>.accept.json` and `<ID>.applied.json` sidecars, read only at Stage or refresh.

Stash pending Metadata/Model work before switching tasks. The helper moves the whole area directory under `tasks/<ID>/`, deletes its acceptance, and reports it through `status.stashes`; no session field is added. Restore only a waiting task into an empty live directory with a fresh area Snapshot, then review, validate, and accept again. This prevents same-area task unions.

First plan line is readiness proof: `Inputs: metadata=<snapshot-id>; model=<snapshot-id>@<revision>` (omit unused). Resume `status` returns it, Snapshot tuples, and first waiting task without mutation. Matching inputs and no staleness reuse readiness. Otherwise rerun one gate and update the plan.

## States

- `queued`: captured but not selected.
- `todo`: eligible and selected as the next task.
- `doing`: local work is active.
- `waiting`: blocked by missing input, stale Snapshot, or upstream Apply.
- `review`: local changes await human review or failed local validation.
- `ready`: review accepted and local validation passed.
- `overridden`: validation failures explicitly accepted for the exact local digest.
- `staged`: current local digest reconciled with a server draft.
- `applied`: governed changes successfully applied.
- `done`: read-only or local-only output completed.
- `cancelled`: terminal without Apply.

Infer next from queue order; never store it. Preserve completed tuples: one compact read costs fewer hops than rediscovery.

## Freshness

When a required area has no Snapshot, stop and issue one exact handoff:

> Download and unzip exactly one fresh `<area>` Snapshot into `<session>/<area>/`. Keep its generated root folder and every file unchanged, then tell me when it is ready.

The user downloads and unzips; the plugin never does. For a marked-stale replacement, run `snapshot-refresh` first. If readiness proof then mismatches, run `readiness` for a known target or `inspect` otherwise—never both.

- The first mutating use of an area in a new session requires a newly downloaded and unzipped Snapshot.
- Reuse it in the same session until a successful Apply writes that area.
- Apply marks only the written area stale; Stage and Validate do not.
- A stale required area moves the task to `waiting` until the user replaces its one Snapshot version.
- Quick reads may use stale data only with an `unverified` label.
- Never use file time as freshness evidence.
- Model revision is authoritative when present. Metadata has no cross-session freshness proof unless its Snapshot contract supplies one.
- Generated code is stale when its embedded Model revision or Mapping digest differs from current inputs.

There is one Model per session. Starting work against another Model requires another session. Use `status.model[0]` for governed server calls; never infer or ask again for the bound Model ID.
