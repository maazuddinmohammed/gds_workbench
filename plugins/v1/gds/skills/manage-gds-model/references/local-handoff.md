# Local Model Change Set handoff

Use this only when a saved `GDS/model-change-set` must enter the governed
server workflow. The helper is cross-platform Node.js, reads no network data,
and never calls MCP. It preserves dataset files and changes only the local
control/review state.

Run commands from the `manage-gds-model` skill directory. Replace placeholders
with exact structured fields returned by the governed tools.
The examples use POSIX `\` line continuation. In Windows PowerShell, run the
same arguments on one line or replace each trailing `\` with a backtick.

## 1. Check the local draft

```sh
node scripts/model-change-set.js validate \
  --change-set "<absolute-path>/GDS/model-change-set"
```

Require `ok=true`. Output contains only identity, status, counts, sizes, and
SHA-256 values. It never prints record bodies.

## 2. Recheck the baseline and create or resume

Enter the governed write window described in
[governed-model-workflow](../../../references/governed-model-workflow.md).
After the lock is owned:

1. call `get_model` and compare its current revision to
   `model.model_revision` in `model-change-set.json`;
2. call `create_model_change_set`;
3. use its `created`, `model_change_set_id`, `draft_revision`, and `status`
   fields exactly.

For a new server draft (`created=true`):

```sh
node scripts/model-change-set.js bind \
  --change-set "<absolute-path>/GDS/model-change-set" \
  --model-id <model-id> \
  --current-model-revision <get-model-revision> \
  --model-change-set-id "<change-set-uuid>" \
  --draft-revision <draft-revision> \
  --server-status "<active-or-validated>" \
  --created true
```

The command fails on baseline drift and leaves the local state unbound.

## Resumed draft reconciliation

When `created=false`, first call `get_model_change_set` without `dataset`. Then
call it once for every dataset whose count is nonzero. Reconcile those complete
lists into the local files without dropping local or server work.

Build a temporary normalized document from structured fields only. Save it
outside `GDS/model-change-set` because that directory accepts only governed
local-state files:

```text
{
  "schema_version": "1.0",
  "model_id": 41,
  "model_change_set_id": "00000000-0000-4000-8000-000000000000",
  "status": "active",
  "draft_revision": 3,
  "dataset_counts": [
    {"dataset": "conceptual_object", "record_count": 2}
  ],
  "datasets": {
    "conceptual_object": [
      <complete ID-free record 1 from the focused get call>,
      <complete ID-free record 2 from the focused get call>
    ]
  }
}
```

`datasets` must contain the exact complete list for each nonzero count. Do not
save a raw tool transcript, URLs, credentials, prompts, or physical rows. Bind
with `--created false --server-draft "<normalized-json-path>"`. The helper
checks that every server record remains in the local draft with the same
canonical key and body. Local-only additions are allowed. A conflict stops
without changing local state. After a successful bind, remove the temporary
normalized document; never commit it.

## 3. Seal the Stage review

```sh
node scripts/model-change-set.js prepare-stage \
  --change-set "<absolute-path>/GDS/model-change-set"
```

Require `stage_ready=true`. The command validates schemas, uniqueness, record
and Section limits; rejects unchanged pending records; and writes
`stage-review.json`. The review contains actions, bounded natural keys, counts,
sizes, and hashes—not full records.

Open the Workbench review to copy the bound Stage JSON, or construct
`stage_model_change_set.changes` from the exact reviewed dataset arrays. Show
the exact review and ask before Stage. Any file edit makes the review stale.

### Large reviewed dataset

When one reviewed dataset cannot fit a normal Stage request, run from this skill
directory and write the new output directly under the ignored `GDS` root:

```sh
node ../../scripts/prepare-stage-batch.js \
  --kind model \
  --dataset-file "<absolute-path>/GDS/model-change-set/datasets/conceptual_object.json" \
  --dataset conceptual_object \
  --output "<absolute-path>/GDS/model-conceptual-object-stage-batch"
```

Call `begin_model_stage_batch` with the manifest, send each exact chunk through
`put_model_stage_chunk`, then call `commit_model_stage_batch` using the original
revision. Begin/Put do not alter the Change Set. Commit performs the same complete
dataset replacement and one revision increment as normal Stage. The three calls are
idempotent only for the exact manifest/chunk bodies. Stage approval still happens
before Begin; Apply still requires fresh approval later.

## 4. Record only a successful Stage

After `stage_model_change_set` or `commit_model_stage_batch` succeeds, pass every
returned dataset count:

```sh
node scripts/model-change-set.js record-stage \
  --change-set "<absolute-path>/GDS/model-change-set" \
  --model-change-set-id "<change-set-uuid>" \
  --expected-current-revision <sent-revision> \
  --server-revision <returned-revision> \
  --server-dataset-count "conceptual_object=2"
```

Repeat `--server-dataset-count` for each reviewed dataset. The helper requires
an exact one-step revision increase, fresh hashes, and exact counts before
recording Stage markers. Do not run it after an error or ambiguous result;
inspect the server draft first.

## 5. Record server validation

After `validate_model_change_set` returns:

```sh
node scripts/model-change-set.js record-validation \
  --change-set "<absolute-path>/GDS/model-change-set" \
  --model-change-set-id "<change-set-uuid>" \
  --expected-current-revision <sent-revision> \
  --server-revision <returned-revision> \
  --server-status "<active-or-validated>"
```

`validated` is accepted only when every local file still matches its recorded
Stage hash. The server's `action_review`, candidate digest, warnings, and
revision remain authoritative. This local status never authorizes Apply; show
that review and obtain fresh approval first.
