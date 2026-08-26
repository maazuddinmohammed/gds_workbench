# Local helper

Resolve a bundled helper link to its installed absolute path, then use one runtime:

- macOS/Linux with Node available: [gds-local.js](../scripts/gds-local.js), then `node <resolved-helper-path> <command> ...`
- Windows PowerShell 5.1/7: [gds-local.ps1](../scripts/gds-local.ps1), then `powershell -NoProfile -File <resolved-helper-path> <command> ...`

Commands are local-only and emit compact JSON.

## Session and queue

```text
session-init --root <working-directory> --tenant <TENANT_CODE>
status --session <session>
readiness --session <session> --target <workflow-target-slug> [--proof-units <target/source-pair-JSON-array>]
mapping-proof --session <session> --target logical-mapping|dimensional-mapping --proof <server-proof-JSON>
generator-proof --session <session> --target logical-code|dimensional-code --proof <server-proof-JSON>
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

Use `status` once on resume. It returns state without rows; `resume` is the first waiting task. `task-plan` uses an expected digest.

After governed Create/resume, Stage, or Validate, cache its ID, revision, and status. ID/task cannot change. A changed digest requires a newer active Stage revision. Apply clears the cache.

`task-stash` isolates pending files, invalidates acceptance, and waits. `task-restore` requires that task, fresh Snapshot, empty live directory, and exact digest. Then review, validate, and accept again.

Run `readiness` before planning. Targets are `logical-build`, `silver-registration`, `logical-mapping`, `logical-code`, `dimensional-build`, `gold-registration`, `dimensional-mapping`, and `dimensional-code`. It returns inputs, counts, grouped blockers, ten examples at most, and a Resolution Prompt—never rows. `ready` proves only local prerequisites.

Proof commands accept only their matching MCP proof, bind it to the current Model Snapshot, and store no payload. A replaced Snapshot invalidates it. Rerun proof-gated readiness with `--proof-units '[{"target_object_id":101,"source_system_id":201}]'`. Selected lists every requested unit; Full lists every eligible unit. Every listed pair needs a current proof; never omit one.

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

Run `reconcile` after acceptance and fresh server Get. It requires the same task's cached draft; returns `exact`, `contained`, `non_overlap`, or `conflict` plus `cache_bound`; and never writes either side. A false binding requires Stage and a newer `active` Stage revision before local `staged`.

## Local Workbench launcher

After session creation, resolve and run [open-workbench.sh](../scripts/open-workbench.sh) with `bash` on macOS/Linux or [open-workbench.ps1](../scripts/open-workbench.ps1) with PowerShell on Windows. It opens the bundled static Workbench; select the existing session directory.
