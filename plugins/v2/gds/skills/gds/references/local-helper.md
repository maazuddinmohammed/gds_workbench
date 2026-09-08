# Local helper

Use `scripts/gds-local.js` for governed local work. `.ps1` is a native compatibility helper. Never inspect helper source to rediscover a command; use `command-contract --command <name>` when needed.

State: session/status/task commands, `subagent-policy`, `sql-policy`, `readiness`, `snapshot-install`, `snapshot-refresh`. Reads: `inspect`, `describe`, bounded `select`. Edits: `copy`, `upsert`, `upsert-batch`, `discard`.

`subagent-policy --mode inherit|disabled|fixed` records only the user's Automatic-mode choice. `fixed` also requires the exact user-supplied VS Code model name. Never store prompts, tokens, credentials, or an agent-selected model.

Download the MCP ZIP temporarily; run `snapshot-install` with exact returned `snapshot_id`, `size_bytes`, and `sha256`; delete it after success. Never expose the signed URL. Installation verifies every member, replaces safely, and reconciles stale areas.

Before notifying, run `validate`; it writes `reports/local-validation/<area>.json`. Run `review` only for a requested action summary. Local edits set the task to `review`. If it is still `doing` after a restore, set `task-state --task <ID> --state review`; after acknowledgement run `accept --digest <validated-digest>`. Never use local override to bypass an unresolved quality or safety failure.

Then follow `server-handoff.md` to bind the active `draft-cache`; read `staging.md`, run `prepare-stage-request`, and invoke `gds_stageApprovedManifest` with only the returned path and accepted digest. Never read payload files or server pending rows into model context.

When server validation returns `valid=false`, cache its active revision with `draft-cache --validation-failed true` before local repair. A corrected, revalidated, re-acknowledged digest may replace only that same task's failed draft through the Stage Runner; other overlap remains a conflict.

JavaScript `validate` checks exported record rules, uniqueness, references, Tenant/GDS scope, locks, Model dependencies, Bindings, Mapping, Code, and Validation. It and Workbench share the same validators; server validation remains authoritative.

Never generate, regenerate, read, or inspect DBML unless the user explicitly asks. `generate-dbml` exports the effective Model to `model-dbml/`.

`task-state staged` requires digest acceptance and server-draft cache. `applied` requires a validated cache. Edits remove acceptance; never relaunch it after every update.

Example bounded Snapshot read (replace the Entity name from actual scope):

```sh
node scripts/gds-local.js select --session <session> --area model --dataset logical_attribute --where '{"logical_entity_name":"Customer"}' --limit 50
```

Paths are relative to this skill directory; quote actual filesystem paths for the host shell. For PowerShell use `scripts/gds-local.ps1` and its same command contract. `--expected-digest` guards local edits; `task-plan` uses its separate plan digest. Read the specific `command-contract` rather than guessing flags. Local Snapshot reads, authoring helpers, Workbench and the Stage extension have separate jobs; the extension neither designs nor Applies results.
