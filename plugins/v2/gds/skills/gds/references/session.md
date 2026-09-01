# Compact session contract

Use a session for related work against one Tenant Code and one Model. Code Generation and QA
are `model` tasks because records live in the Model Snapshot/Change Set. `code/` holds local Target
Registration DDL only.

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

Allocate `01`..`99`, then `100` onward. Never reuse a deleted number. Use Tenant Code directories.

## Session state

Keep `session.json` compact:

```json
{"current":"02","model":[41,"Customer Model"],"sql":"never","tasks":[["01","metadata","Add metadata","applied"],["02","model","Build models","doing"]],"stale":["metadata"],"cs":{"model":["uuid",2,"active","02","digest"]}}
```

- `current`: current task ID or `null`.
- `model`: bound `[Model ID, Model name]`.
- `sql`: `never`, `essential`, or `as_needed`; ask before live-data use and change only as directed.
- `tasks`: `[task ID, area, title, state]` tuples.
- `stale`: areas made stale by Apply.
- `cs`: draft cache as `[ID, revision, status, task ID, accepted local digest]`. It never proves server state.

Omit empty optional keys. Do not store goal, tenant, session ID, path, timestamps, raw prompts,
history, targets, or sub-focus here.

`tasks/<ID>.json` holds ordered actions. Acceptance/Apply markers are lazy sidecars read at Stage or refresh.

Stash pending Metadata/Model work before switching. The helper moves the area under `tasks/<ID>/`,
deletes acceptance, and reports `status.stashes`. Restore only into an empty live directory with a
fresh Snapshot, then re-accept. This prevents same-area task unions.

First plan line is readiness proof: `Inputs: metadata=<snapshot-id>; model=<snapshot-id>@<revision>`.
Resume `status` returns it and the first waiting task. Reuse matching inputs; otherwise rerun one gate.

## States

- `queued`, `todo`, `doing`: captured, selected, active.
- `waiting`, `review`: blocked or awaiting review.
- `ready`, `overridden`: valid or explicitly accepted for the exact digest.
- `staged`, `applied`: reconciled or successfully applied.
- `done`, `cancelled`: terminal without further work.

Infer next from queue order; preserve completed tuples.

## Freshness

When a required area has no Snapshot, stop and issue one exact handoff:

> Download and unzip exactly one fresh `<area>` Snapshot into `<session>/<area>/`. Keep its generated root folder and every file unchanged, then tell me when it is ready.

The user downloads and unzips; the plugin never does. For a marked-stale replacement, run `snapshot-refresh` first. If readiness proof then mismatches, run `readiness` for a known target or `inspect` otherwise—never both.

- First mutation needs a newly downloaded/unzipped Snapshot; reuse until Apply.
- Apply marks only its area stale; Stage/Validate do not. Stale tasks wait for replacement.
- Label stale Quick reads `unverified`. Never use file time as freshness evidence.
- Model revision is authoritative; Metadata needs contract-supplied freshness proof.
- Current Code and QA are Model Snapshot datasets; their published context digests bind them to upstream Mapping and any current relevant Code when present.

Use one Model per session. Use `status.model[0]` for governed calls; another Model needs another session.
