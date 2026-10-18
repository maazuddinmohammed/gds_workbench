# Verify and decide the remaining Atlas improvement items

Status: needs-triage

The Atlas improvement plan is implemented and tested locally (uncommitted): Stage
contract fixes and server-contract fixture; doc cleanup and instruction lint; eval
harness (`tests/atlas/eval/`); helper commands `next`, `policy-apply`, `coverage`;
boundaries in code (Stage upload gate, Apply `expected_candidate_digest`, read-only
`project_input_scope`/`profiling_profile`, `next --error`); one skill template;
shared web/Atlas rule test. Plugin 0.4.0, Stage Runner 0.3.0. See
`docs/architecture/decisions.md` "Atlas boundaries enforced in code".

Open items:

1. Windows PowerShell 5.1 is still unverified. All native parity tests pass locally with
   PowerShell 7.6 on macOS (`ATLAS_POWERSHELL=$(command -v pwsh)`), but the Windows job
   (`.github/workflows/plugin-windows.yml`) has failed since before this work: 50 of 71
   `stage-runner.test.ts` tests failed with `MANIFEST_CHANGED` because the test helper
   stored Windows backslash paths. `sealManifest` now stores `/` paths like the helpers;
   confirm the Windows run passes and reaches the 5.1 parity step.
2. Decide whether MCP Stage should also reject `project_input_scope` and
   `profiling_profile`. Today only Atlas refuses them; server E2E tests in
   `tests/mcp/test_database_project_change_set_round_trip.py` stage both through MCP.
3. Decide whether to bump the MCP server version label (`mcp_server/pyproject.toml`,
   both `gds-etl-workbench-mcp==0.2.0` pins and lockfiles). Apply gained a required
   argument, so release the server with plugin 0.4.0 and Stage Runner 0.3.0
   (Stage Runner first; older servers ignore its header).
4. Live agent evaluations (`tests/atlas/eval/README.md`) have not been run; they call
   a model and cost money.

Acceptance:

- The Windows job passes, including the PowerShell 5.1 parity step.
- Items 2 and 3 have recorded decisions in `docs/architecture/decisions.md`.
- At least one live evaluation run per scenario is scored, or the decision not to run
  them is recorded.

Sources: `atlas/atlas-plugin/scripts/`, `mcp_server/gds_etl_workbench/adapters/mcp/stage_runner_gate.py`,
`tests/atlas/`.
