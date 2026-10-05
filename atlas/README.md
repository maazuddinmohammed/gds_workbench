# atlas

Atlas is a portable Agent Plugins 1.0 plugin with 12 task-oriented skills, shared domain references, workspace helpers, Atlas Local Workbench and a shared Stage Runner with VS Code and Codex hosts.

## User guides

Complete the setup guide for your host. Then use the same usage guide.

| Guide | When to use it |
|---|---|
| [Codex installation and setup](atlas-plugin/docs/codex-installation-and-setup.md) | Install the plugin, relay and VSIX; start the bridge in VS Code. |
| [Copilot - VS Code installation and setup](atlas-plugin/docs/copilot-vs-code-installation-and-setup.md) | Register the plugin, install Stage Runner, and sign in to Atlas. |
| [Shared install and updates](atlas-plugin/docs/install-and-update.md) | One permanent location; replace both ZIPs with the package updater. |
| [Atlas usage](atlas-plugin/docs/usage-guide.md) | Start work, review local changes, Stage, Apply, and resume later. |

The plugin ZIP includes these guides and shared install/update instructions in its `docs/` folder. Users do not
need a source checkout or a local build.

Before authorized delegation, Atlas saves a [sub-agent model policy](atlas-plugin/docs/usage-guide.md#choose-the-sub-agent-policy)
per working folder: current model only, agent-selected model, or one specified
model. A saved preference does not authorize delegation. Independent work needs
no policy selection; unsupported model selection keeps work in the main agent.

## Repository layout

- `atlas-plugin/`: plugin source, `plugin.json`, governed MCP configuration, skills, references, scripts and Atlas Local Workbench.
- `atlas-vs-code/`: VS Code extension, shared Stage engine, and Codex connector source under `src/connector/`.
- `atlas-connector/`: bundled local Codex relay, installation and ZIP update commands.
- `build_plugin.py`, `build_connector.py`: deterministic ZIP builders.
- `dist/`: current plugin ZIP, connector ZIP, and Stage Runner VSIX.

The [local runtime reference](atlas-plugin/references/local-runtime.md) covers
technical helper commands and the Windows PowerShell fallback. The [bridge reference](atlas-connector/README.md) covers local Codex routing.
VS Code supplies Microsoft authentication; users provide no connector client ID.

Plugin, companion, and backend must support the current Snapshot and Mapping
contracts; see [architecture decisions](../docs/architecture/decisions.md).
Backend setup follows the [MCP README](../mcp_server/README.md) and
[fresh-install database sequence](../database/README.md).

The current artifacts are Atlas plugin 0.3.0, VS Code Stage Runner 0.2.0 and Atlas Connector 0.2.0. Rebuild the matching artifacts after source changes; version labels alone do not prove source equality. Installing the plugin does not install the extension or update the deployed backend. Publication and deployment require separate approval.

## Build

Build from the repository root:

```sh
python3 atlas/build_plugin.py --output /absolute/path/new-atlas.zip
npm --prefix atlas/atlas-vs-code run compile
npm --prefix atlas/atlas-vs-code run package:vsix
python3 atlas/build_connector.py --output /absolute/path/new-connector.zip
```

The plugin builder refuses an existing output, unsafe links or unreviewed file families. The portable archive has one `atlas/` root. Only Connector setup generates a Codex catalog; this avoids installing a remote-only plugin without Stage. The VSIX and connector are separate companions. Connector setup generates local Codex MCP wiring with absolute program paths. The shared layout keeps `atlas`, `atlas-connector`, and generated `codex-atlas` beside one another. `npm run setup` installs or refreshes the generated copy and Codex registration. The Python updater replaces both package folders while retaining backups. The Copilot MCP configuration is unchanged. Never include native node_modules, token caches or per-user setup output in either archive.

## Maintainer boundaries

The [entry skill](atlas-plugin/skills/atlas/SKILL.md) routes outcomes across 12 task-oriented skills. Guided and Grill Me are interaction modes within one modeling workflow. Shared [architecture](atlas-plugin/references/platform/architecture.md), [readiness](atlas-plugin/references/platform/readiness.md) and [capabilities](atlas-plugin/references/platform/capabilities.md) explain platform knowledge, actual prerequisites and unsupported operations. Topic methods and record guides stay on demand; templates format existing evidence without another state store.

Local `select` supports digest-bound continuation and field projection with canonical keys retained. `status` defaults to the active task summary; explicit task detail and paged history avoid loading unrelated evidence. Both Node and native PowerShell expose the same command contract. These are local read aids, not authorization or business-readiness verdicts.

Code owns exact fields, limits and behavior. Distributed skills and references are runtime instructions; retain their links when changing the package.

| Source | Responsibility |
|---|---|
| `workbench/app.js`, `ui/`, `ui-state.js` | Browser operation flows, record editing and findings. |
| `workbench/workspace.js` | Snapshot integrity, local persistence, conflicts and exports. |
| `workbench/core.js` | Shared identity, overlay and Python-compatible serialization. |
| `workbench/validation/`, `model-quality.js` | Shared browser/helper checks; server remains authoritative. |
| `workbench/dbml.js` | Pure effective-Model rendering; export is a user-only Atlas Local Workbench action. |
| `scripts/atlas-local.js`, `scripts/*.ps1` | Local command execution and Windows fallback. Exact flags live in `contracts/local-helper.json`. |
| `atlas-vs-code/src/connector/` | Private local bridge, reviewed MCP proxy and install wiring for Codex. |
| `atlas-vs-code/src/stage-runner.ts`, `stage-request.ts`, `stage-transport.ts` | Approval/input binding, revision checks, transport and uncertain-write recovery. |

Copilot and Codex execute the same Stage engine inside VS Code and use Atlas Local Workbench serialization. The connector only relays Codex requests; it does not implement a second Stage engine. Preserve canonical bytes, owner isolation, locks, input hashes and Windows parity together. Local validation, Stage and Apply remain separate operations; [submission and recovery](atlas-plugin/references/change-set-lifecycle.md) owns the runtime procedure.

## Verification

Run repository checks in [AGENTS.md](../AGENTS.md), including Python Atlas tests, `node --test tests/atlas/*.test.mjs`, extension tests and compilation. `tests/atlas/test_packaging.py` checks deterministic source equality for both ZIPs, isolated Codex installation and every packaged Markdown link. Rebuild the corresponding package after source changes.

[Agent scenarios](../tests/atlas/agent_scenarios.md) cover intent, evidence and workflow boundaries for instruction walkthroughs or an explicitly authorized independent evaluation. Packaging/link checks and local helper tests do not establish live-agent or deployed-backend behavior.

`npm --prefix atlas/atlas-vs-code run test:host` checks the packaged VSIX in an installed VS Code using an isolated workspace and loopback fixture; it never downloads a host. Inspect Atlas Local Workbench folder access, keyboard/zoom behavior and DBML export in Chrome/Edge separately. Synthetic tests must preserve drafts and locked records, reject stale approval/revision evidence, and verify recovery without replaying uncertain writes. Use only fixture-created disposable PostgreSQL; local checks do not establish live provider or Databricks behavior.
