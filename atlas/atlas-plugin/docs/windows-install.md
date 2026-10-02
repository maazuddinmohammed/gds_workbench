# Install Atlas on a Windows VM

Use the exported Atlas ZIP supplied by your administrator. It contains the
plugin, all 13 skills, local helpers, Workbench and the Codex installation
catalog. You do not need the development repository or a build environment.

## Prerequisites

- Codex CLI with `codex plugin marketplace add` and `codex plugin add` support
  (installation contract tested with version 0.147.0), signed in on this VM.
- Node.js 20+ and Python 3.12+ for the main local helper runtime. Native Windows
  PowerShell 5.1 is the fallback described in the [runtime guide](runtime-guide.md).
- Chrome or Edge for Workbench and its working-folder picker.
- Network access to your organization's GDS backend and an authorized Microsoft
  account. Obtain the intended backend setup from your administrator.

The ZIP contains no credentials or bundled Node, Python or Codex installation.

## Install in Codex CLI

1. Extract the ZIP to a permanent folder on your VM, for example
   `C:\Tools\Atlas`. Locate the extracted `atlas` folder containing `plugin.json`.
2. Open Windows PowerShell and run the following, substituting that folder:

   ```powershell
   codex --version
   codex plugin marketplace add "C:\Tools\Atlas\atlas"
   codex plugin add atlas@gds-workbench
   codex plugin list --marketplace gds-workbench
   ```

3. Restart Codex and check that Atlas appears in `/skills`.
4. Open your own working directory and ask `Start atlas.` Select that working
   directory in Workbench when prompted. Keep working files separate from the
   extracted plugin folder.

Keep the extracted folder for marketplace refreshes. If you move it, add its new
location before refreshing the plugin. Installation changes this user's Codex
setup on this VM; it does not require the author's Codex installation.

## Current submission support

This release supplies Codex plugin installation. The Codex Stage adapter is
still pending, and Windows runtime and GDS authentication require verification.
Installing the ZIP does not make the VS Code Stage tools available to Codex.
If the required Stage tool is absent, preserve local work and continue submission
in the supported VS Code workflow.

For GitHub Copilot in VS Code, install Atlas using the host's Agent Plugins
installation flow and install the separately supplied Stage Runner VSIX with
**Extensions: Install from VSIX**. Open your working directory as a trusted
workspace, configure the intended backend, then run **Atlas: Check Stage Runner**.
Microsoft sign-in for that extension is separate from the plugin's MCP login.

Follow the [user guide](user-guide.md) and [submission procedure](../references/change-set-lifecycle.md)
for review, Stage and separate Apply approval.
