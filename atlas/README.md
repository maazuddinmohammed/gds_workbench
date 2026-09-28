# atlas

Atlas is a portable Agent Plugins 1.0 plugin with 13 skills, shared domain references, workspace helpers, local Workbench and a companion VS Code Stage Runner.

- `atlas-plugin/`: plugin source, `plugin.json`, governed MCP configuration, skills, references, scripts and Workbench.
- `atlas-vs-code/`: separately installable extension; plugin portability does not install a VS Code extension.
- `build_plugin.py`: deterministic plugin ZIP builder.
- `dist/`: local plugin ZIP and Stage Runner VSIX; rebuilding does not publish or install them.

Use Node.js 20+ and Python 3.12+ for the main local runtime. A native Windows PowerShell 5.1 fallback is included. Workbench uses Chrome/Edge directory access. Read the [user guide](atlas-plugin/docs/user-guide.md) and [runtime guide](atlas-plugin/docs/runtime-guide.md). Maintainer documentation lives in [development](development/validation-index.md), outside the distributed plugin.

Install the ZIP through an Agent Plugins 1.0-compatible host. Install the companion VSIX in VS Code, configure its intended matching backend and run **Atlas: Check Stage Runner**. Plugin, extension and backend must support the current Entity-owned Model Snapshot and Mapping context contracts; see [ADR 012](../docs/adr/012-entity-owned-mapping-and-code.md). Backend setup follows the [MCP README](../mcp_server/README.md) and [fresh-install database sequence](../database/README.md).

The current local artifacts are Atlas plugin 0.1.2 and Stage Runner 0.1.1. Rebuild both after their source changes; version labels alone do not prove source equality. Installing the plugin does not install the extension or update the deployed backend. Publication and deployment require separate approval.

Build from the repository root:

```sh
python3 atlas/build_plugin.py --output /absolute/path/new-atlas.zip
npm --prefix atlas/atlas-vs-code run compile
npm --prefix atlas/atlas-vs-code run package:vsix
```

The plugin builder refuses an existing output, unsafe links or unreviewed file families. Archives have one `atlas/` root. The VSIX is distributed alongside the ZIP, not embedded as a portable plugin capability.

Use the [release verification scenarios](development/release-verification.md) and repository checks in [AGENTS.md](../AGENTS.md). The [September 16 verification report](validation-report.md) is historical.
