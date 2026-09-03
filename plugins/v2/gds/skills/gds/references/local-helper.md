# Local helper

Use `scripts/gds-local.js` for governed local work. `.ps1` is a native compatibility helper. Never inspect helper source to rediscover a command; use `command-contract --command <name>` when needed.

State: session/status/task commands, `readiness`, `snapshot-install`, `snapshot-refresh`. Reads: `inspect`, `describe`, bounded `select`. Edits: `copy`, `upsert`, `upsert-batch`, `discard`.

Download the MCP ZIP temporarily; run `snapshot-install` with exact returned `snapshot_id`, `size_bytes`, and `sha256`; delete it after success. Never expose the signed URL. Installation verifies every member, replaces safely, and reconciles stale areas.

Before notifying, run `validate`; it writes `reports/local-validation/<area>.json`. Run `review` only for a requested action summary. After acknowledgement: `accept`, fetch server state, `reconcile`.

Then read `staging.md`, run `prepare-stage` with exact server pending datasets, and execute its ordered operations. Never invent splits, hashes, or revision flow.

When server validation returns `valid=false`, cache its active revision with `draft-cache --validation-failed true` before local repair. A corrected, revalidated, re-acknowledged digest may replace only that same task's failed draft through `prepare-stage`; other overlap remains a conflict.

JavaScript `validate` checks exported record rules, uniqueness, references, Tenant/GDS scope, locks, Model dependencies, Bindings, Mapping, Code, and Validation. It and Workbench share the same validators; server validation remains authoritative.

Never generate, regenerate, read, or inspect DBML unless the user explicitly asks. `generate-dbml` exports the effective Model to `model-dbml/`.

`task-state staged` requires digest acceptance and server-draft cache. `applied` requires a validated cache. Edits remove acceptance; never relaunch it after every update.
