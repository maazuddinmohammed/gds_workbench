# Verify and decide the remaining Atlas improvement items

Status: needs-triage

The Atlas improvement plan is merged to `main` (PR #1, merge commit `6e6ea937`): Stage
contract fixes and server-contract fixture; doc cleanup and instruction lint; eval
harness (`tests/atlas/eval/`); helper commands `next`, `policy-apply`, `coverage`;
boundaries in code (Stage upload gate, Apply `expected_candidate_digest`, read-only
`project_input_scope`/`profiling_profile`, `next --error`); one skill template;
shared web/Atlas rule test. Plugin 0.4.0, Stage Runner 0.3.0. Both CI workflows passed
on the PR, including Windows PowerShell 5.1 parity. See
`docs/architecture/decisions.md` "Atlas boundaries enforced in code".

Open items:

1. Decide whether MCP Stage should also reject `project_input_scope` and
   `profiling_profile`. Today only Atlas refuses them; server E2E tests in
   `tests/mcp/test_database_project_change_set_round_trip.py` stage both through MCP.
2. Closed: MCP server bumped to 0.3.0 (version, pins, lockfiles, release note in
   `mcp_server/README.md`); decision in `docs/architecture/decisions.md`.
3. Live agent evaluations ran once: Claude Code 2.1.218 headless, Sonnet 5.5 (effort
   high), 12 scenarios x 3, about $24 at API prices. 27/36 passed. No run used Stage
   upload, Apply or lock override, or edited a Snapshot. Eight scenarios passed 3/3.
   Harness defects to fix before the next run:
   - `physical-description` (0/3): the fixture has no empty descriptions; agents
     correctly changed nothing.
   - `code-from-mapping` (0/3): replay demands the optional `expected_project_revision`
     on `read_mapping_context`. Two runs stopped through `next --error`; one rebuilt
     Code from Snapshot rows and skipped `validate`.
   - `helper:<command>` checks count calls, not success: `logical-validate-only`
     scored 3/3 but validated in 1/3.
   - The README Claude Code template needs allow rules for `-p` mode:
     `--allowedTools "mcp__gds-workbench" "Bash(node *)" "Bash(cd *)"`. Inside Claude
     Code, run the CLI with `env -i` and its own login.
   Instruction fixes (proposed, not applied):
   - `validate` requires a task, so agents skip or fail it on no-change requests: it
     succeeded in 0/3 `mapping-applied-target` and 1/3 `logical-validate-only` runs.
     State that `task-add` is local bookkeeping, or let `validate` run without a task.
   - Read records with `select`/`inspect`: 26 of the 27 runs that read records opened
     Snapshot data files directly.
   - One helper call per terminal command, with absolute paths: 86 shell commands,
     mostly compound one-liners, were refused; a host that asks before shell commands
     prompts for each.
   - After a failed governed read, run `next --error` and stop; never rebuild from
     Snapshot rows.
   `dimension-from-logical` (2/3): one run asked about SCD type and key split before
   drafting, which is acceptable.

Acceptance:

- Items 1 and 2 have recorded decisions in `docs/architecture/decisions.md`.
- At least one live evaluation run per scenario is scored, or the decision not to run
  them is recorded.

Sources: `atlas/atlas-plugin/scripts/`, `mcp_server/gds_etl_workbench/adapters/mcp/stage_runner_gate.py`,
`tests/atlas/`.
