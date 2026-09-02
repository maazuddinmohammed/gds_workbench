# Local helper

Use Node `scripts/gds-local.js` or PowerShell `scripts/gds-local.ps1`. Run `command-contract --command <name>` for one command's syntax.

Use `session-init`, `status`, `sql-policy`, task commands, `readiness`, and `snapshot-refresh` for state. Use `inspect`, `describe`, and bounded `select` for local Snapshot reads. Use `copy`, `upsert`, `upsert-batch`, and `discard` for complete local records.

After authoring, run `review` and `validate` internally. Tell the user to Refresh Workbench. After an unambiguous positive acknowledgement, run `accept` for the exact digest, then obtain current server state and run `reconcile`. These helper names are implementation details, not user steps.

`validate` is schema-driven: it checks signed JSON Schemas, canonical-key uniqueness, declared references, locks, and safe local state. It does not replace authorization, database constraints, or Change Set validation on the server.

`task-state staged` requires digest acceptance and server-draft cache. `applied` requires a validated cache. A content edit removes acceptance. Workbench may remain open throughout; never relaunch it after every update.
