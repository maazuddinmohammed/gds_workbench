# Governed server handoff

Load only after accepted digest plus Stage intent, or an explicit upstream archive boundary.
Workbench never runs it.

## Minimal Stage, Validate, and Apply sequence

1. Call `check_tenant_lock`. Before `acquire_tenant_lock` when unowned, use the final-review approval
   if it explicitly included acquisition; otherwise ask. Another owner stops; override needs direction/reason.
2. If `status.cs` contains this task, verify through `get_metadata_change_set` or
   `get_model_change_set`; never Create. Otherwise call `create_metadata_change_set` or
   `create_model_change_set` once. Cache ID/revision/status. Cache is not server proof.
3. For a resumed draft, read summary and nonempty datasets, then local `reconcile`. New empty drafts
   need neither. Resolve conflicts and re-accept edits.
4. If reconciliation is `exact` with `cache_bound=true`, skip Stage. Otherwise use the Stage intent already granted
   for the accepted digest/actions. If reconciliation changes either, obtain new
   approval. Send all affected complete datasets in one Stage call via
   `stage_metadata_change_set` or `stage_model_change_set`; omitted datasets stay unchanged.

   Batch only when acceptance reports `batch`; it handles one dataset. Metadata uses
   `begin_metadata_stage_batch`, `put_metadata_stage_chunk`, `commit_metadata_stage_batch`; Model
   uses `begin_model_stage_batch`, `put_model_stage_chunk`, `commit_model_stage_batch`. In `records` mode
   keep records whole; each chunk hashes its canonical schema-normalized record array (sorted
   keys, compact JSON, UTF-8). Model `json_fragments` is only for oversized `generated_code`; split
   that canonical array's bytes, base64 each part, and hash decoded fragment bytes. `batch_sha256`
   hashes concatenated ordered lowercase chunk SHA-256 hex digests. Commit validates once; use its
   returned revision for the next batch.
5. If Stage ran, cache the active revision, run local `task-state ... staged`, and always call `validate_metadata_change_set`
   or `validate_model_change_set`; cache its validated revision/status.
   If Stage was skipped, first cache fresh verified revision/status, then run local `task-state ... staged`.
   Validate only if status is active.
   Repair returned paths only, then review/accept/Stage/Validate again.
6. Show authoritative `action_review`; obtain fresh Apply approval before
   `apply_metadata_change_set` or `apply_model_change_set`.
7. After Apply, set local task `applied`, stop, and `release_tenant_lock` if acquired here.

Archive only on explicit request with `archive_metadata_change_set` or
`archive_model_change_set`. At an upstream archive boundary, fresh-Get each cached nonempty dataset
and reconcile; unless classification is `exact` and `cache_bound` is true, do not archive. Show
ID/status/reason, get approval, archive, clear cache, then `task-stash`. Archive needs no Tenant Lock.
Never create a draft merely to look. After upstream Apply/fresh Snapshots, `task-restore`, review,
validate, and accept before normal handoff.
