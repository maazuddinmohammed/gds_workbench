# Local helper

Use Node `scripts/gds-local.js` or PowerShell `scripts/gds-local.ps1`. Run `command-contract --command <name>` for syntax.

State: `session-init`, `status`, `sql-policy`, task commands, `readiness`, `snapshot-refresh`. Snapshot reads: `inspect`, `describe`, bounded `select`. Complete-record edits: `copy`, `upsert`, `upsert-batch`, `discard`.

Before user review, run `validate`. It compiles the effective graph and writes `reports/local-validation/<area>.json`. Use `review` only for its action summary. After acknowledgement, `accept` the exact digest, fetch server state, then `reconcile`.

After reconciliation, read `staging.md`. Run `prepare-stage` with the exact server pending datasets and execute its ordered `operations`; never split records, calculate hashes, or infer revision flow.

`validate` checks signed schemas, key uniqueness, declared references, locks, and safe local state. Workbench runs the same checks. Server authorization, constraints, and Change Set validation remain authoritative.

`generate-dbml --session <session> --area model` writes the effective local Model to `model-dbml/`; Workbench uses the same renderer.

`task-state staged` requires digest acceptance and server-draft cache. `applied` requires a validated cache. Edits remove acceptance; never relaunch it after every update.
