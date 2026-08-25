# Local and governed Change Sets

## Local contract

Use `metadata-change-set/<dataset>.json` or `model-change-set/<dataset>.json`. Each file is a JSON array of complete pending records sorted by the Snapshot-published canonical key.

`model_scope` is Snapshot-readable but never Change Set-writable. Never create `model-change-set/model_scope.json`, include it in Stage, or treat Target Registration as scope activation.

- Missing file: no local intent for that dataset; do not Stage it.
- Present nonempty array: added, changed, reactivated, or explicitly deactivated complete records.
- Present `[]`: explicitly clear that dataset’s server-pending records. It never deletes applied data.
- Missing records mean unchanged applied data. Never represent deletion by omission.
- Preserve all nested members when editing an existing Model parent record.
- Never edit Snapshot files.

Every local write uses the prior workspace digest. The digest covers sorted relative paths and exact bytes. Reject a mismatch as an external-edit conflict; never overwrite it. `empty` is allowed only when the Change Set directory truly has no entries.

## Review and acceptance

Overlay pending records on the immutable Snapshot by canonical key. Validate the effective graph, then return bounded issues, action counts, actions, digest, and Stage sizing in one review cycle.

Human acceptance is bound to the exact digest. Any edit moves the task back to `review`. Passing local validation moves accepted work to `ready`. Explicitly accepting local failures moves it to `overridden` and records a reason. Local override never bypasses server validation.

## Stage reconciliation

Reconcile once at Stage, not on every local edit:

1. Fetch the cached server draft if one exists; otherwise find or create the one ongoing draft.
2. Compare server pending and local complete records by normalized canonical key.
3. Exact overlap: resume without restaging.
4. Non-overlap: preserve both and Stage the union.
5. Same key and same complete record: preserve once.
6. Same key and different record: report a conflict and never overwrite.
7. Expired or archived draft: clear only its cache; preserve local files; create a new draft only at Stage.

Stage uses revision compare-and-swap. Server Validate must seal the exact staged revision. Apply only that validated revision. After successful Apply update the task, mark only its written area stale, and stop.

If Mapping needs upstream work, isolate it before switching tasks. For a cached server draft, perform a fresh Get and `reconcile` against its local task. Archive is safe only when classification is `exact` and `cache_bound` is true; otherwise server work is unrelated, conflicting, or tied to an older local digest, so stop. Show the exact draft and reason, get Archive approval, archive, then clear cache with its expected ID/revision. Run `task-stash`; never set `waiting` directly with live pending files. If no draft exists, stash directly.

Run the upstream task through Apply, replace required Snapshots, then `task-restore` using its reported digest. Review against the fresh Snapshot, validate, and accept again. At Stage, follow the normal handoff: reconcile only a resumed draft after it is cached. Archive never deletes local files; stash moves them intact.
