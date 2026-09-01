# Local helper

Use Node [gds-local.js](../scripts/gds-local.js) or PowerShell
[gds-local.ps1](../scripts/gds-local.ps1). Run `command-contract --command <name>` for syntax; never
load all commands. Before server mutation, `contract-check` the exact `get_server_contract` result;
incompatibility stops.

## Session and evidence

Use `session-init`, `status`, `sql-policy`, `readiness`, proof/cache commands, task commands, and
`snapshot-refresh`. On resume call `status` once. With no current task it resumes first waiting,
else queued/todo; after Apply start it only when the user chooses to continue.

`task-state staged` requires acceptance/cache; `applied` requires validated cache. Invoke only after
server success. Cache draft ID/revision/status; cache never proves server state. A changed digest
needs a newer `active` Stage; Apply clears it.

`task-stash` isolates pending files; restore requires its task, fresh Snapshot, empty directory, and
exact digest, followed by review/acceptance.

Run `readiness` before planning. QA needs `--system-codes` with 1..1000 nonempty case-insensitively unique
values. Mapping/generator proof is bound to its Model Snapshot; replacement invalidates it.
`--proof-units` must list every Selected/Full pair.

## Bounded reads

Use `inspect`, `describe`, and `select`. `describe` defaults to compact; request full only after a
targeted repair remains unexplained. With target `readiness`, never call both it and `inspect`.
Prefer MCP `describe`, then bounded `select`; narrow truncation. Never read whole Snapshots. First
Model Snapshot binds ID/name; another Model needs another session.

## Pending work

Use `copy`, `upsert`, `upsert-batch`, `discard`, `review`, `approve-reviewed`, `validate`, `accept`,
and `reconcile`. Every write needs the last digest. `upsert-batch` accepts 200 records maximum and
rejects duplicate keys. `discard` removes only local intent.

After explicit final-review approval, call
`approve-reviewed --area model --reviewed true` at most once, and only for listed pending statuses.
Never infer approval. It changes schema-defined `status`/`*_status` from `needs_review` to `active`,
never Snapshots, applied rows, text, or `is_active`. Its `next_action` says to validate then accept
the promoted digest; no second review is needed for this deterministic status-only change. Never repeat `approve-reviewed`
after zero promotions. Any content change requires review.

Local `validate` checks schemas, graphs, locks, Mapping→Code→QA order, and QA digests; it returns
targeted `repairs` but cannot prove database state or Databricks SQL safety. Server Validate rechecks
authorization, locks, records, digests, and conflicts. Repair only reported paths. Never write per field
or split one `generated_code` artifact.

After acceptance/fresh Get, `reconcile` returns `exact`, `contained`, `non_overlap`, or `conflict`
plus `cache_bound`; it writes nothing. False binding requires a newer `active` Stage.

Launch local Workbench with [open-workbench.sh](../scripts/open-workbench.sh) or
[open-workbench.ps1](../scripts/open-workbench.ps1).
