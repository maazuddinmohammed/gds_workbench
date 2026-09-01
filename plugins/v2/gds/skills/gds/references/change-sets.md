# Local and governed Change Sets

## Local contract

Before the first write to each dataset, call `describe_metadata_dataset` or `describe_model_dataset`
with compact detail; offline use local `describe`. Never author from memory. Request full only when
compact guidance plus targeted repair cannot explain a field. Files
contain complete records sorted by canonical key.

`model_scope` is Snapshot-readable but never Change Set-writable. Never create
`model-change-set/model_scope.json`, Stage it, or treat registration as scope activation.

- Missing file means no intent; do not Stage it. Missing datasets remain unchanged.
- Present array is complete intent and a complete replacement array for that server-pending dataset,
  never a patch. Present `[]` clears only pending server intent; it never deletes applied data.
- Omitted records are unchanged. Preserve nested members when editing a parent. Deactivate through a
  complete inactive record. Code/QA are Model datasets; one Code target remains one record.
- Never edit Snapshot files.

Every write provides the prior digest over sorted paths and exact bytes. Mismatch is conflict; never
overwrite. `empty` requires no pending entries.

## Review, acceptance, reconciliation

Review overlays pending on Snapshot and returns bounded actions/issues, digest, and Stage sizing.
Acceptance binds that digest. Edits return to `review`; validation yields `ready` or reason-bound
`overridden`. Override never bypasses server validation. Repair only reported paths; do not reload
every contract or regenerate valid records.

Reconcile once at Stage: fetch the cached/ongoing draft and compare complete records by normalized
canonical key. Exact records resume; non-overlap Stages their union; differing overlap is conflict
and never overwrite. Expired/archived drafts clear cache but preserve files. Stage uses revision
compare-and-swap; Validate seals that revision; Apply once, mark the area stale, and stop.

For blocked Mapping, fresh-Get and reconcile its cached draft. Archive only when classification is `exact`
and `cache_bound` is true. After approval clear it with expected ID/revision, then
`task-stash`; never leave live pending files while waiting. After upstream Apply and fresh Snapshots,
`task-restore` by digest, review, validate, and accept. Archive never deletes local files.
