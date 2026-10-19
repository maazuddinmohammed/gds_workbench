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
plugin copy whose helper logs each call and its exit status), `mcp.json`,
`codex-mcp.toml`, `prompt.md` (skill catalog + request) and `logs/`. Nothing contacts a
real backend, Databricks or Azure.

## Run

From the repository root, with the backend virtual environment:

```bash
PYTHONPATH=mcp_server:web_app/backend:. web_app/backend/.venv/bin/python -m tests.atlas.eval.harness --scenario all --out /tmp/atlas-eval --dry-run
```

Then run an agent. The template receives `{prompt}`, `{workspace}`, `{mcp_config}`,
`{codex_config}`, `{plugin}` and `{transcript}` (already shell-quoted) and runs with the
working folder as its current directory. Write the agent's JSON event stream to
`{transcript}` so skill-read and final-message checks can run. Verify flags against your
installed CLI version; the Codex template is untested.

Claude Code (used for the first live run, CLI 2.1.218). In `-p` mode nobody approves tool
calls, so `--allowedTools` pre-approves the replay server and the helper (`node`, `cd`).
`--setting-sources project,local` and `--disable-slash-commands` keep your own settings,
hooks and skills out of the run; `--no-session-persistence` keeps runs out of your session
history; `--max-budget-usd` caps each run.

```bash
PYTHONPATH=mcp_server:web_app/backend:. web_app/backend/.venv/bin/python -m tests.atlas.eval.harness --scenario logical-sql-never --out /tmp/atlas-eval --agent-command 'claude -p "$(cat {prompt})" --mcp-config {mcp_config} --strict-mcp-config --add-dir {plugin} --allowedTools "mcp__gds-workbench" "Bash(node *)" "Bash(cd *)" --setting-sources project,local --disable-slash-commands --no-session-persistence --max-budget-usd 4 --output-format stream-json --verbose --permission-mode acceptEdits > {transcript}'
```

Inside the Claude desktop app (or any Claude Code session) the nested CLI must not inherit
the host's `CLAUDE_*` variables and needs its own login. Put the `env -i ...` part below in
front of `claude -p` in the template, and log in once the same way:

```bash
env -i HOME="$HOME" PATH="$PATH" USER="$USER" LOGNAME="$LOGNAME" SHELL="$SHELL" TMPDIR="$TMPDIR" LANG=en_US.UTF-8 claude auth login
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
only with a transcript). A required helper command needs a run that exited 0; forbidden
commands and budgets count every attempt.

## Maintain

- New scenario: add it to `scenarios.json`; `../test_eval_harness.py` validates names
  against the real tool inventory, helper contract and skills.
- Schema, seed or Snapshot changes: regenerate the world (needs Docker):
  `PYTHONPATH=mcp_server:web_app/backend:. web_app/backend/.venv/bin/python -m tests.atlas.eval.build_fixtures`.
  `test_eval_world_matches_current_server` fails while the recording is stale.
