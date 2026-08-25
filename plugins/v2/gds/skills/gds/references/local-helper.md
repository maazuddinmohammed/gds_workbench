# Local helper

Use exactly one runtime:

- macOS/Linux with Node available: `node <plugin>/scripts/gds-local.js <command> ...`
- Windows PowerShell 5.1/7: `powershell -NoProfile -File <plugin>\scripts\gds-local.ps1 <command> ...`

PowerShell needs no Node, Python, npm, or module. Use one runtime per operation. Commands are local-only and emit one compact JSON object.

## Session and queue

```text
session-init --root <working-directory> --tenant <TENANT_CODE>
status --session <session>
readiness --session <session> --target <workflow-target-slug>
draft-cache --session <session> --area metadata|model --id <UUID> --revision <n> --status active|validated
draft-cache --session <session> --area metadata|model --clear true --expected-id <UUID> --expected-revision <n>
snapshot-refresh --session <session> --area metadata|model
task-add --session <session> --area <area> --title <short-title> --plan <JSON-array>
task-plan --session <session> --task <ID> --plan <JSON-array> --expected-digest <digest>
task-state --session <session> --task <ID> --state <state>
task-stash --session <session> --task <ID> --expected-digest <digest>
task-restore --session <session> --task <ID> --expected-digest <digest>
```

`task-state staged` requires acceptance and draft cache bound to the same task/digest. `applied` also requires validated cache. Invoke them only after matching server success; Apply marks that area stale.

Use `status` once on resume. It returns Model, current/resume plan, queue, cache, staleness, Snapshot/pending summaries, and stashes without Snapshot rows. `resume` is the first waiting task without mutation. `task-plan` uses an expected digest.

After governed Create/resume, Stage, or Validate, cache its exact ID, revision, and status. ID/task cannot change. A changed accepted digest binds only with a newer `active` Stage revision; Validate may then advance status/revision. Clear after confirmed Archive/expiry using cached ID/revision. Apply clears it. Cache is not server proof.

`task-stash` isolates current Metadata/Model pending files, invalidates acceptance, and waits. It requires valid nonempty JSON, exact digest, and no cached draft. `task-restore` requires that task, no current task, fresh Snapshot, empty live directory, and exact stash digest. Then review, validate, and accept again. Never orphan pending work with `task-state`.

Run `readiness` once before planning a Workflow Target. Slugs are `logical-build`, `silver-registration`, `logical-mapping`, `logical-code`, `dimensional-build`, `gold-registration`, `dimensional-mapping`, and `dimensional-code`. It returns Snapshot inputs, counts, grouped blockers, at most ten examples, and a Resolution Prompt—never rows. `ready` proves local prerequisites, not the plan or human checkpoint.

`snapshot-refresh` requires a different Snapshot ID and, for Model, higher revision. It retires applied files only when every nonempty pending record exactly matches the signed replacement; otherwise files and staleness remain.

## Bounded Snapshot reads

```text
inspect --session <session> --area metadata|model
describe --session <session> --area <area> --dataset <name>
select --session <session> --area <area> --dataset <name> --where <JSON-object> --limit <1..200>
```

Use `inspect` once only for Ad Hoc catalog discovery. Target `readiness` already verifies required Snapshots; never call both as setup. `describe` only a filtered/authored dataset, then `select` required records. Never read an entire Snapshot. If truncated, narrow `--where`.

The first trusted Model Snapshot binds `[Model ID, Model name]` into the session. Later revisions of that Model are allowed; another Model ID requires a new session. Metadata Snapshot Tenant Code must match the Tenant Code directory.

## Local pending work

```text
copy --session <session> --area <area> --dataset <name> --where <JSON-object> --expected-digest <digest|empty>
upsert --session <session> --area <area> --dataset <name> --record <complete-JSON-object> --expected-digest <digest|empty>
upsert-batch --session <session> --area <area> --changes <dataset-to-record-array-JSON> --expected-digest <digest|empty>
discard --session <session> --area <area> --dataset <name> --key <canonical-key-JSON> --expected-digest <digest>
review --session <session> --area <area>
validate --session <session> --area <area>
accept --session <session> --area <area> --digest <digest> [--override true --reason <reason>]
reconcile --session <session> --area <area> --server <server-pending-JSON-object>
```

Every write needs the last digest; `empty` requires no files. `upsert-batch` accepts `{dataset:[complete records]}`, validates atomically, rejects duplicate keys, and allows at most 200 records. `discard` removes local intent and leaves `[]`; applied data is untouched.

Use one `upsert-batch` per reasoning batch, singular `upsert` for one record, and `copy` for a bounded Snapshot selection. Never write per field. `review` and `validate` return bounded summaries; Workbench provides the same local surface without server controls.

Run `reconcile` after acceptance and fresh server Get. It requires the same task's cached draft; returns `exact`, `contained`, `non_overlap`, or `conflict` plus `cache_bound`; and never writes either side. A false binding requires Stage and a newer cache revision before local `staged`.
