# Local helper

Use `scripts/gds-local.js` for governed local work. `.ps1` is a native compatibility helper. Never inspect helper source to rediscover a command; use `command-contract --command <name>` when needed.

For setup, query `command-contract --command session-init`, then run `session-init --root <directory> --tenant <code>`. Use the returned session path. Installing the first Model Snapshot binds its Model to the session; there is no Model-selection command. Run `bash scripts/open-workbench.sh` or `./scripts/open-workbench.ps1` without arguments. In Chrome/Edge, have the user choose the session directory through Workbench's folder picker; the browser grants that local access once.

State: session/status/task commands, `subagent-policy`, `sql-policy`, `readiness`, `snapshot-install`, `snapshot-refresh`. Reads: `inspect`, `describe`, bounded `select`. Edits: `copy`, `upsert`, `upsert-batch`, `discard`. `profile-plan` generates standard aggregate SQL from saved selections; read `workflows/profiling.md` when needed.

`analysis-plan --session <session> --plan-file <JSON-path>` writes bounded aggregate SQL for selected key, dependency, and join probes. It never executes queries or creates Analysis Results. Read `analysis-probes.md` for the exact probe format and interpretation; execution still follows the saved SQL policy.

`subagent-policy --mode inherit|disabled|fixed` records the user's authorized delegation choice. `fixed` also requires the exact user-supplied VS Code model name. Never store prompts, tokens, credentials, or an agent-selected model.

Follow `session.md` for verified Snapshot installation/recovery.

Before notifying, run `validate`; it writes `reports/local-validation/<area>.json`. Run `review` only for a requested action summary. Local edits set the task to `review`. If it is still `doing` after a restore, set `task-state --task <ID> --state review`; after acknowledgement run `accept --digest <validated-digest>`. Never use local override to bypass an unresolved quality or safety failure.

Then follow `server-handoff.md` to bind the active `draft-cache`; read `staging.md`, run `prepare-stage-request`, and invoke `gds_stageApprovedManifest` with only the returned path and accepted digest. Never read payload files or server pending rows into model context.

For rejected server drafts, follow `server-handoff.md`; only the task-bound failed draft may be replaced after repair and renewed acknowledgement.

Local `validate` shares Workbench validators; server validation remains authoritative.

Never generate, regenerate, read, or inspect DBML unless the user explicitly asks. `generate-dbml` exports the effective Model to `model-dbml/`.

`task-state staged` requires digest acceptance and server-draft cache. `applied` requires a validated cache. Edits remove acceptance; never relaunch it after every update.

Example bounded Snapshot read (replace the Entity name from actual scope):

```sh
node scripts/gds-local.js select --session <session> --area model --dataset logical_attribute --where '{"logical_entity_name":"Customer"}' --limit 50
```

Paths are relative to this skill; quote them for the host shell. PowerShell uses `scripts/gds-local.ps1` with the same command contract. `--expected-digest` guards edits; `task-plan` has a separate plan digest. Stage Runner neither designs nor Applies.

For bounded edits: `copy` the matching complete records using the current `--expected-digest` (`empty` only for an empty draft). Read the resulting `<session>/<area>-change-set/<dataset>.json` array locally; preserve unknown fields and modify only intended fields. Pass complete changed records to `upsert-batch --changes <dataset-to-record-array-JSON>` with the returned digest. Pass large JSON through a script's process argument array; don't print records. The helper merges by canonical key, invalidates acceptance, and returns the new digest. Then validate the complete effective graph.
