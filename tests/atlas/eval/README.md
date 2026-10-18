# Atlas agent evaluations

Measures whether an agent following the packaged Atlas skills does the right things.
Use it before and after any skill or reference change; compare reports, not impressions.

## What runs where

| Piece | Role |
|---|---|
| `fixtures/` | Real Metadata/Project Snapshots and recorded MCP responses from a disposable database seeded with the demo project "Customer Orders 360". |
| `fake_mcp.py` | Real MCP tool surface (names, descriptions, schemas, instructions) answering from the recording; logs every call. Stage transport, Apply and lock override are refused. |
| `scenarios.json` | Requests plus checks. Rows mirror `../agent_scenarios.md`. |
| `harness.py` | Builds one sandbox per scenario, runs your agent command, scores logs and files. |

Every sandbox has `workspace/` (the agent's working folder), `plugin/atlas/` (packaged
plugin copy whose helper logs each call), `mcp.json`, `codex-mcp.toml`, `prompt.md`
(skill catalog + request) and `logs/`. Nothing contacts a real backend, Databricks or Azure.

## Run

From the repository root, with the backend virtual environment:

```bash
PYTHONPATH=mcp_server:web_app/backend:. web_app/backend/.venv/bin/python -m tests.atlas.eval.harness --scenario all --out /tmp/atlas-eval --dry-run
```

Then run an agent. The template receives `{prompt}`, `{workspace}`, `{mcp_config}`,
`{codex_config}`, `{plugin}` and `{transcript}` (already shell-quoted) and runs with the
working folder as its current directory. Write the agent's JSON event stream to
`{transcript}` so skill-read and final-message checks can run. Verify flags against your
installed CLI version; these are starting points, not tested contracts.

Claude Code:

```bash
PYTHONPATH=mcp_server:web_app/backend:. web_app/backend/.venv/bin/python -m tests.atlas.eval.harness --scenario logical-sql-never --out /tmp/atlas-eval --agent-command 'claude -p "$(cat {prompt})" --mcp-config {mcp_config} --strict-mcp-config --add-dir {plugin} --output-format stream-json --verbose --permission-mode acceptEdits > {transcript}'
```

Codex (merge `codex-mcp.toml` into the Codex configuration for the run):

```bash
PYTHONPATH=mcp_server:web_app/backend:. web_app/backend/.venv/bin/python -m tests.atlas.eval.harness --scenario logical-sql-never --out /tmp/atlas-eval --agent-command 'codex exec --json --skip-git-repo-check -C {workspace} "$(cat {prompt})" > {transcript}'
```

Re-score without rerunning: add `--score-only`. Each sandbox gets `report.json`.

Live runs call a model and cost money. Run several repetitions per scenario: one run is
an anecdote. Copilot in VS Code is the production host; CLI agents are proxies.

## Checks

Always: no Stage transport tools (`stage_*`, `begin_*`, `put_*`, `commit_*`), no Apply or
lock override, no hand edits to installed Snapshots. Per scenario: required/forbidden MCP
tools and helper commands, Conceptual datasets not read by downstream work, required or
forbidden draft files, call budgets, skills read and final-message content (the last two
only with a transcript).

## Maintain

- New scenario: add it to `scenarios.json`; `../test_eval_harness.py` validates names
  against the real tool inventory, helper contract and skills.
- Schema, seed or Snapshot changes: regenerate the world (needs Docker):
  `PYTHONPATH=mcp_server:web_app/backend:. web_app/backend/.venv/bin/python -m tests.atlas.eval.build_fixtures`.
  `test_eval_world_matches_current_server` fails while the recording is stale.
