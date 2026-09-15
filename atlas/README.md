# atlas

Atlas is a portable Agent Plugins 1.0 plugin with 14 skills, shared domain references, workspace helpers, local Workbench and a companion VS Code Stage Runner.

- `atlas-plugin/`: plugin source, `plugin.json`, governed MCP configuration, skills, references, scripts and Workbench.
- `atlas-vs-code/`: separately installable extension; plugin portability does not install a VS Code extension.
- `build_plugin.py`: deterministic plugin ZIP builder.
- `dist/`: local plugin ZIP and Stage Runner VSIX; rebuilding does not publish or install them.

Use Node.js 20+ and Python 3.12+ for the main local runtime. A native Windows PowerShell 5.1 fallback is included. Workbench uses Chrome/Edge directory access. Read the [user guide](atlas-plugin/docs/user-guide.md) and [runtime guide](atlas-plugin/docs/runtime-guide.md). Maintainer documentation lives in [development](development/validation-index.md), outside the distributed plugin.

Install the ZIP through an Agent Plugins 1.0-compatible host. Install the companion VSIX in VS Code, configure its intended matching backend and run **Atlas: Check Stage Runner**. The backend must support Atlas's Process Group order, Mapping context reader and associated validation changes; existing installations need the [operator compatibility review](../docs/atlas-backend-compatibility.md). Backend deployment is separate.

Build from the repository root:

```sh
python3 atlas/build_plugin.py --output /absolute/path/new-atlas.zip
npm --prefix atlas/atlas-vs-code run compile
npm --prefix atlas/atlas-vs-code run package:vsix
```

The plugin builder refuses an existing output, unsafe links or unreviewed file families. Archives have one `atlas/` root. The VSIX is distributed alongside the ZIP, not embedded as a portable plugin capability. Existing GDS artifacts remain separate.

See the [verification report](validation-report.md) for test results and remaining platform checks.
