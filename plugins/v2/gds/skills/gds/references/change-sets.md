# Local and governed Change Sets

## Local contract

Before the first write to each dataset, call `describe_metadata_dataset` or `describe_model_dataset`
with default compact detail; offline, use local `describe`. Never author from memory. Request `full`
only when compact guidance plus targeted repair cannot explain a field. Files are
complete records sorted by canonical key.

`model_scope` is Snapshot-readable but never Change Set-writable. Never create
`model-change-set/model_scope.json`, Stage it, or treat registration as scope activation.

- Missing file: no local intent; do not Stage it. Missing datasets remain unchanged.
- Present array: complete local intent and complete replacement array for that server-pending dataset
  at Stage, never a patch.
- Present `[]`: clear only that server-pending dataset. It never deletes applied data; use direct
  Stage because Batch requires records.
- Missing records are unchanged; never delete by omission.
- Preserve all nested members when editing an existing Model parent record.
- Code/QA are Model datasets. Deactivate with complete inactive records. Each Code target remains
  one complete record; large Code uses only `server-handoff.md` fragment transport.
- Never edit Snapshot files.

Every write uses the prior digest over sorted paths and exact bytes. Mismatch is conflict; never
overwrite. `empty` requires no entries.

## Review and acceptance

Overlay pending on Snapshot; return bounded actions/issues, digest, and Stage sizing. Acceptance
binds it. Edits return to `review`; validation yields `ready` or reason-bound `overridden`.
Override never bypasses server validation.

On failure, repair only reported dataset, record, and field paths, then rerun local
validation. Do not reload every contract or regenerate valid records.

## Stage reconciliation

Reconcile once at Stage, not on every local edit:

1. Fetch the cached or one ongoing draft.
2. Compare complete records by normalized canonical key.
3. Exact/same records resume; non-overlap Stages their union; differing overlap is conflict and
   never overwrite.
4. Expired/archived clears cache, preserves files, and creates only at Stage.

Stage uses revision compare-and-swap. Validate seals that revision; Apply it once, mark its area stale, and stop.

If Mapping needs upstream work, isolate it. Fresh-Get and `reconcile` its cached draft. Archive only
when classification is `exact` and `cache_bound` is true. Get approval, clear with expected
ID/revision, then `task-stash`. Never set `waiting` with live pending files.

After upstream Apply replace Snapshots, `task-restore` by digest, review, validate, and accept. Archive never deletes local files.
