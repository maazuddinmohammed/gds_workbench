# Governed server handoff

Load only after digest acceptance plus Stage intent, or an explicit upstream archive boundary.
Workbench never runs this sequence. Use these exact tools; never discover alternatives.

## Minimal Stage, Validate, and Apply sequence

1. Call `check_tenant_lock`. Ask before `acquire_tenant_lock` when unowned. Another owner's lock
stops; override needs explicit direction and reason.
2. If `status.cs` contains this task, verify it with `get_metadata_change_set` or
`get_model_change_set`; never Create. Otherwise call `create_metadata_change_set` or
`create_model_change_set` once; cache ID/revision/status. Cache is not server proof.
3. For a resumed draft, read its summary and each nonzero dataset; local `reconcile`. New empty
drafts need neither. Keep only normalized complete records. Resolve conflicts and re-accept edits.
4. If reconciliation is `exact` with `cache_bound=true`, skip Stage. Otherwise show review and
ask for Stage approval. Normal size: send all affected complete datasets in one Stage call through
`stage_metadata_change_set` or `stage_model_change_set`. Each item replaces that pending dataset;
omitted datasets stay unchanged. Use direct Stage for `[]`.

   Batch only when acceptance reports `batch`; it handles one dataset and requires records.
Metadata: `begin_metadata_stage_batch`, `put_metadata_stage_chunk`,
`commit_metadata_stage_batch`. Model: `begin_model_stage_batch`, `put_model_stage_chunk`,
`commit_model_stage_batch`. In `records` mode keep records whole; chunk SHA-256 hashes canonical
UTF-8 JSON of its schema-normalized record array (sorted keys, compact separators, unescaped
Unicode). Model `json_fragments` is only for oversized `generated_code`: build that same canonical
complete array, split bytes within advertised bounds, base64 chunks, hash decoded fragment bytes,
and send total bytes. `batch_sha256` hashes the ASCII concatenation of ordered lowercase chunk SHA-256 hex digests.
Commit validates the dataset and increments revision once; use its returned revision for
the next batch. Fragments are transport, never Model state.
5. If Stage ran, cache the active revision, run local `task-state ... staged`, and always call `validate_metadata_change_set`
or `validate_model_change_set`; cache its validated revision/status.
If Stage was skipped, first cache fresh verified revision/status, transition only from
ready/overridden, and Validate only if status is active. On failure repair only returned
dataset/record/field paths, re-review, re-accept, re-Stage, and revalidate.
6. Show authoritative `action_review`. Obtain fresh Apply approval before
`apply_metadata_change_set` or `apply_model_change_set`; Stage approval/override is insufficient.
7. After Apply, run local `task-state ... --state applied`, stop, and release an acquired lock with
`release_tenant_lock`.

Archive only on explicit request via `archive_metadata_change_set` or `archive_model_change_set`;
clear exact ID/revision, preserve files, and release an acquired lock.

At an upstream archive boundary, fresh-Get the cached Mapping draft and every nonzero dataset, then
local `reconcile`. Continue only when classification is `exact` and `cache_bound` is true; otherwise
do not archive. Show ID/status/reason, get approval, archive, clear expected ID/revision, then
`task-stash`. Archive needs no Tenant Lock. Never create a draft merely to look. After upstream
Apply and fresh Snapshots, `task-restore`, review, validate, and accept before normal handoff.
