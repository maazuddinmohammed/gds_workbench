# atlas

Atlas is a portable Agent Plugins 1.0 plugin with 12 task-oriented skills, shared domain references, workspace helpers, Atlas Local Workbench and Stage Runner for VS Code Copilot.

## User guides

Complete the Copilot setup guide, then follow the usage guide.

| Guide | When to use it |
|---|---|
| [Copilot - VS Code installation and setup](atlas-plugin/docs/copilot-vs-code-installation-and-setup.md) | Register the plugin, install Stage Runner, and sign in to Atlas. |
| [Installation and updates](atlas-plugin/docs/install-and-update.md) | Install the plugin ZIP and matching Stage Runner VSIX in one permanent location. |
| [Atlas usage](atlas-plugin/docs/usage-guide.md) | Start work, review local changes, Stage, Apply, and resume later. |

The plugin ZIP includes these guides and install/update instructions in its `docs/` folder. Users do not
need a source checkout or a local build.

Before authorized delegation, Atlas saves a [sub-agent model policy](atlas-plugin/docs/usage-guide.md#choose-the-sub-agent-policy)
per working folder: current model only, agent-selected model, or one specified
model. A saved preference does not authorize delegation. Independent work needs
no policy selection; unsupported model selection keeps work in the main agent.

## Repository layout

- `atlas-plugin/`: plugin source, `plugin.json`, governed MCP configuration, skills, references, scripts and Atlas Local Workbench.
- `atlas-vs-code/`: VS Code Copilot extension and deterministic Stage engine.
- `build_plugin.py`: deterministic plugin ZIP builder.
- `dist/`: current plugin ZIP and Stage Runner VSIX.

The [local runtime reference](atlas-plugin/references/local-runtime.md) covers
technical helper commands and the Windows PowerShell fallback.
VS Code supplies Microsoft authentication.

Plugin, companion, and backend must support the current Snapshot and Mapping
contracts; see [architecture decisions](../docs/architecture/decisions.md).
Backend setup follows the [MCP README](../mcp_server/README.md) and
[fresh-install database sequence](../database/README.md).

The current artifacts are Atlas plugin 0.4.0 and VS Code Stage Runner 0.3.0. Rebuild the matching artifacts after source changes; version labels alone do not prove source equality. Installing the plugin does not install the extension or update the deployed backend. Publication and deployment require separate approval.

## Build

Build from the repository root:

```sh
python3 atlas/build_plugin.py --output /absolute/path/new-atlas.zip
npm --prefix atlas/atlas-vs-code run compile
npm --prefix atlas/atlas-vs-code run package:vsix
```

The plugin builder refuses an existing output, unsafe links or unreviewed file families. The archive has one `atlas/` root. Copilot loads that folder directly; the Stage Runner VSIX is installed separately. Updates replace the whole plugin folder while retaining a backup. Never include node_modules, token caches or per-user setup output in the archive.

## Maintainer boundaries

The [entry skill](atlas-plugin/skills/atlas/SKILL.md) routes outcomes across 12 task-oriented skills. Guided and Grill Me are interaction modes within one modeling workflow. Shared [architecture](atlas-plugin/references/platform/architecture.md), [readiness](atlas-plugin/references/platform/readiness.md) and [capabilities](atlas-plugin/references/platform/capabilities.md) explain platform knowledge, actual prerequisites and unsupported operations. Topic methods and record guides stay on demand; templates format existing evidence without another state store.

Local `select` supports digest-bound continuation and field projection with canonical keys retained. `status` defaults to the active task summary; explicit task detail and paged history avoid loading unrelated evidence. Both Node and native PowerShell expose the same command contract. These are local read aids, not authorization or business-readiness verdicts.

Code owns exact fields, limits and behavior. Distributed skills and references are runtime instructions; retain their links when changing the package.

Each skill uses one short template (When to use, What you need, Steps, Done when, Ask the user when, Next) with at most 450 words and five reference links; shared rules live once in the [golden rules](atlas-plugin/references/working-method.md#golden-rules). Submission runs through `atlas-local next`, which returns one action at a time and one recovery action for a failed MCP call. `policy-apply` and `coverage` reuse the web workflow's policy columns and coverage rule. `tests/atlas/test_instructions.py` enforces the template and command flags; the [evaluation harness](../tests/atlas/eval/README.md) scores agent runs against a replayed MCP server.

| Source | Responsibility |
|---|---|
| `workbench/app.js`, `ui/`, `ui-state.js` | Browser operation flows, record editing and findings. |
| `workbench/workspace.js` | Snapshot integrity, local persistence, conflicts and exports. |
| `workbench/core.js` | Shared identity, overlay and Python-compatible serialization. |
| `workbench/validation/`, `project-quality.js` | Shared browser/helper checks; server remains authoritative. |
| `workbench/dbml.js` | Pure effective-Project rendering; export is a user-only Atlas Local Workbench action. |
| `scripts/atlas-local.js`, `scripts/*.ps1` | Local command execution and Windows fallback. Exact flags live in `contracts/local-helper.json`. |
| `atlas-vs-code/src/stage-runner.ts`, `stage-request.ts`, `stage-transport.ts` | Approval/input binding, revision checks, transport and uncertain-write recovery. |

Copilot executes Stage inside VS Code using Atlas Local Workbench serialization. Preserve canonical bytes, owner isolation, locks, input hashes and Windows parity together. Local validation, Stage and Apply remain separate operations; [submission and recovery](atlas-plugin/references/change-set-lifecycle.md) owns the runtime procedure.

## Verification

Run repository checks in [AGENTS.md](../AGENTS.md), including Python Atlas tests, `node --test tests/atlas/*.test.mjs`, extension tests and compilation. `tests/atlas/test_packaging.py` checks deterministic plugin source equality, the packaged Stage Runner and every packaged Markdown link. Rebuild the corresponding package after source changes.

[Agent scenarios](../tests/atlas/agent_scenarios.md) cover intent, evidence and workflow boundaries for instruction walkthroughs or an explicitly authorized independent evaluation. Packaging/link checks and local helper tests do not establish live-agent or deployed-backend behavior.

`npm --prefix atlas/atlas-vs-code run test:host` checks the packaged VSIX in an installed VS Code using an isolated workspace and loopback fixture; it never downloads a host. Inspect Atlas Local Workbench folder access, keyboard/zoom behavior and DBML export in Chrome/Edge separately. Synthetic tests must preserve drafts and locked records, reject stale approval/revision evidence, and verify recovery without replaying uncertain writes. Use only fixture-created disposable PostgreSQL; local checks do not establish live provider or Databricks behavior.
