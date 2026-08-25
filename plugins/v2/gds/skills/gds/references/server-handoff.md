# Governed server handoff

Load this only after the exact local digest is accepted and the user wants to Stage, or when `change-sets.md` requires an explicit upstream archive boundary. Workbench never performs this sequence.

Choose the Metadata or Model tool names below. Do not discover alternate mutation tools.

## Minimal Stage, Validate, and Apply sequence

1. Call `check_tenant_lock`. Ask before `acquire_tenant_lock` when unowned. Another owner's lock stops; never override without explicit direction and reason.
2. If `status.cs` contains this task, verify that exact draft with `get_metadata_change_set` or `get_model_change_set`; never call Create. Otherwise call `create_metadata_change_set` or `create_model_change_set` once and cache its exact ID, revision, and status. Cache is not server proof.
3. For a resumed draft, read its summary then each nonzero dataset and run local `reconcile`. A new empty draft needs no Get/reconcile. Normalize only complete records; never store raw output. Resolve conflicts and re-accept changed bytes.
4. If reconciliation is `exact` with `cache_bound=true`, skip Stage. Otherwise show the local review, ask for Stage approval, and send every affected complete dataset in one Stage call: `stage_metadata_change_set` or `stage_model_change_set`. Never Stage per record or field. Use Begin/Put/Commit Stage Batch only when acceptance reports `batch`.
5. If Stage ran, cache its new active revision, run local `task-state ... staged`, and always call `validate_metadata_change_set` or `validate_model_change_set`; cache its validated revision/status. If Stage was skipped, first cache fresh verified revision/status, run that local transition only from ready/overridden, and Validate only if status is active. On failure, repair the first failed phase; re-review, re-accept, re-Stage, and revalidate.
6. Show the authoritative server `action_review`. Obtain fresh Apply approval immediately before `apply_metadata_change_set` or `apply_model_change_set`; Stage approval and local override are not Apply approval.
7. After successful Apply, run local `task-state ... --state applied`, stop at the boundary, and release any lock this workflow acquired with `release_tenant_lock`.

Archive only at explicit user request with `archive_metadata_change_set` or `archive_model_change_set`, then clear cache using that exact ID/revision. Preserve local files and release an acquired lock.

At an upstream archive boundary, use a fresh matching Get for the cached Mapping draft, including every nonzero pending dataset, then local `reconcile`. Continue only when classification is `exact` and `cache_bound` is true. Any other result means unrelated, conflicting, or older-digest work: do not archive. Show exact ID/status/reason, obtain Archive approval, archive, clear with expected ID/revision, then `task-stash`. Archive needs no Tenant Lock. Never create a draft merely to look. After upstream Apply and fresh Snapshots, `task-restore`, then review, validate, and accept again before normal Stage handoff.
