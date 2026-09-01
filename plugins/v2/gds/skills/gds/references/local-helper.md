# Local helper

Resolve one helper:

- Node: [gds-local.js](../scripts/gds-local.js), then `node <path> <command> ...`
- PowerShell 5.1/7: [gds-local.ps1](../scripts/gds-local.ps1), then
  `powershell -NoProfile -File <path> <command> ...`

Use `command-contract --command <name>` for syntax; never load every command. Before server mutation,
`contract-check` the exact `get_server_contract` result; incompatibility stops.

## Session and queue

Commands: `session-init`, `status`, `sql-policy`, `readiness`, `mapping-proof`, `generator-proof`,
`draft-cache`, `snapshot-refresh`, `task-add`, `task-plan`, `task-state`, `task-stash`, and
`task-restore`.

`task-state staged` requires acceptance/cache; `applied` requires validated cache. Invoke
after server success.

On resume use `status` once.

Cache draft ID/revision/status. ID/task is fixed. Changed digest needs a newer active Stage;
Apply clears it.

`task-stash` isolates pending files. Restore needs its task, fresh Snapshot, empty directory, and
exact digest; then re-review/accept.

Run `readiness` before planning. Targets are `logical-build`, `silver-registration`,
`logical-mapping`, `logical-code`, `dimensional-build`, `gold-registration`,
`dimensional-mapping`, `dimensional-code`, and `qa`. QA requires `--system-codes` with 1..1000
nonempty case-insensitively unique values.

Proof commands bind MCP proof to the Model Snapshot; replacement invalidates it.
`--proof-units` lists every Selected/Full pair; omit none.

`snapshot-refresh` requires a different ID and higher Model revision. It retires applied files only when pending records exactly match the replacement.

## Bounded Snapshot reads

Commands: `inspect`, `describe`, and `select`. `describe` defaults to compact; request full only
after a targeted repair remains unexplained.

`inspect` is Ad Hoc only; with target `readiness`, never call both. Prefer MCP `describe`, then bounded
`select`; offline use local `describe`. Narrow truncated queries; never read whole Snapshots.

First Model Snapshot binds ID/name. Another Model needs a new session.

## Local pending work

Commands: `copy`, `upsert`, `upsert-batch`, `discard`, `review`, `approve-reviewed`, `validate`, `accept`, and `reconcile`.

Every write needs the last digest; `empty` requires no files. `upsert-batch` validates 200 records maximum
and rejects duplicate keys. `discard` removes local intent only.

After explicit approval, run `approve-reviewed --area model --reviewed true` with latest digest.
It promotes schema-defined pending `status`/`*_status` values equal to `needs_review`; never Snapshots,
applied rows, text, or `is_active`. Then review, validate, accept. Never infer approval.

Local `validate` checks schemas, graphs, locks, Mapping→Code→QA order, and QA digests, returning
targeted `repairs`; it cannot prove database state or Databricks SQL safety. Model validation needs fresh
Metadata; Dimensional sources require applied Logical Mapping. Server Validate rechecks authorization,
locks, records, digests, and conflicts.

Repair only reported paths. Use `upsert-batch` per batch, `upsert` for one record, `copy` for
selection. Never write per field or split one `generated_code` artifact. Review is bounded.

After acceptance/fresh Get, `reconcile` returns `exact`, `contained`, `non_overlap`, or `conflict`
plus `cache_bound`; it writes nothing. False binding requires a newer `active` Stage.

## Local Workbench launcher

Run [open-workbench.sh](../scripts/open-workbench.sh) or
[open-workbench.ps1](../scripts/open-workbench.ps1), then select it.
