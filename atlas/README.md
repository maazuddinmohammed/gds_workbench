# atlas

Atlas is a portable Agent Plugins 1.0 plugin with 13 skills, shared domain references, workspace helpers, local Workbench and a companion VS Code Stage Runner.

- `atlas-plugin/`: plugin source, `plugin.json`, governed MCP configuration, skills, references, scripts and Workbench.
- `atlas-vs-code/`: separately installable extension; plugin portability does not install a VS Code extension.
- `build_plugin.py`: deterministic plugin ZIP builder.
- `dist/`: local plugin ZIP and Stage Runner VSIX; rebuilding does not publish or install them.

Use Node.js 20+ and Python 3.12+ for the main local runtime. A native Windows PowerShell 5.1 fallback is included. Workbench uses Chrome/Edge directory access. Read the [user guide](atlas-plugin/docs/user-guide.md) and [runtime guide](atlas-plugin/docs/runtime-guide.md).

Install the ZIP through an Agent Plugins 1.0-compatible host. Install the companion VSIX in VS Code, configure its intended matching backend and run **Atlas: Check Stage Runner**. Plugin, extension and backend must support the current Entity-owned Model Snapshot and Mapping context contracts; see [architecture decisions](../docs/architecture/decisions.md). Backend setup follows the [MCP README](../mcp_server/README.md) and [fresh-install database sequence](../database/README.md).

The current local artifacts are Atlas plugin 0.1.3 and Stage Runner 0.1.1. Rebuild both after their source changes; version labels alone do not prove source equality. Installing the plugin does not install the extension or update the deployed backend. Publication and deployment require separate approval.

## Export for Windows users

Distribute `dist/atlas-agent-plugin-0.1.3.zip`. The ZIP contains the portable plugin, helpers, Workbench, a Codex installation catalog and [Windows installation instructions](atlas-plugin/docs/windows-install.md). Recipients extract it on their VM and install from the resulting `atlas` directory; they need no source checkout or build tools.

For example, after extracting to `C:\Tools\Atlas`, the folder containing `plugin.json` is `C:\Tools\Atlas\atlas`. In Windows PowerShell:

```powershell
codex plugin marketplace add "C:\Tools\Atlas\atlas"
codex plugin add atlas@gds-workbench
codex plugin list --marketplace gds-workbench
```

The builder generates `atlas/.agents/plugins/marketplace.json` with `source.path` set to `./`. All installed content comes from the exported folder. The existing [GitHub Copilot marketplace](../.github/plugin/marketplace.json) continues to use the same portable plugin source. Distribute `dist/atlas-stage-runner-0.1.1.vsix` alongside the ZIP for Copilot in VS Code.

Codex package installation is tested independently from the source checkout with CLI 0.147.0. Full Windows runtime and authenticated GDS access still need verification. Codex Stage submission requires the pending adapter for the shared Stage engine; the VSIX tools are exposed through VS Code's language-model API. Until the adapter is available, complete submission through the supported VS Code workflow in the [Stage Runner guide](atlas-vs-code/README.md).

## Build

Build from the repository root:

```sh
python3 atlas/build_plugin.py --output /absolute/path/new-atlas.zip
npm --prefix atlas/atlas-vs-code run compile
npm --prefix atlas/atlas-vs-code run package:vsix
```

The plugin builder refuses an existing output, unsafe links or unreviewed file families. Archives have one `atlas/` root, including the generated Codex catalog. The VSIX is distributed alongside the ZIP, not embedded as a portable plugin capability.

## Maintainer boundaries

Code owns exact fields, limits and behavior. Distributed skills and references are runtime instructions; retain their links when changing the package.

| Source | Responsibility |
|---|---|
| `workbench/app.js`, `ui/`, `ui-state.js` | Browser operation flows, record editing and findings. |
| `workbench/workspace.js` | Snapshot integrity, local persistence, conflicts and exports. |
| `workbench/core.js` | Shared identity, overlay and Python-compatible serialization. |
| `workbench/validation/`, `model-quality.js` | Shared browser/helper checks; server remains authoritative. |
| `workbench/dbml.js` | Pure effective-Model rendering; export is a user-only Workbench action. |
| `scripts/atlas-local.js`, `scripts/*.ps1` | Local command execution and Windows fallback. Exact flags live in `contracts/local-helper.json`. |
| `atlas-vs-code/src/stage-runner.ts`, `stage-request.ts`, `stage-transport.ts` | Approval/input binding, revision checks, transport and uncertain-write recovery. |

The extension consumes Workbench serialization. Preserve canonical bytes, owner isolation, locks, input hashes and Windows parity together. Local validation, Stage and Apply remain separate operations; [submission and recovery](atlas-plugin/references/change-set-lifecycle.md) owns the runtime procedure.

## Verification

Run repository checks in [AGENTS.md](../AGENTS.md), including Python Atlas tests, `node --test tests/atlas/*.test.mjs`, extension tests and compilation. `tests/atlas/test_packaging.py` checks deterministic source equality and every packaged Markdown link. Rebuild the corresponding package after source changes.

`npm --prefix atlas/atlas-vs-code run test:host` checks the packaged VSIX in an installed VS Code using an isolated workspace and loopback fixture; it never downloads a host. Inspect Workbench folder access, keyboard/zoom behavior and DBML export in Chrome/Edge separately. Synthetic tests must preserve drafts and locked records, reject stale approval/revision evidence, and verify recovery without replaying uncertain writes. Use only fixture-created disposable PostgreSQL; local checks do not establish live provider or Databricks behavior.
