# Atlas installation and updates

Install Atlas once for VS Code Copilot. Keep project work elsewhere.

| System | Installation | Example working folder |
|---|---|---|
| Windows | `%USERPROFILE%\Tools\Atlas` | `%USERPROFILE%\Work\SalesProject` |
| macOS / Linux | `~/Tools/Atlas` | `~/Work/SalesProject` |

```text
Tools/Atlas/
  atlas/              Plugin, local helpers, and Atlas Local Workbench.
```

Copilot reads the `atlas` folder directly. VS Code supplies Microsoft sign-in.

## First installation

Get these release files:

| File | Purpose |
|---|---|
| `atlas-agent-plugin-0.3.0.zip` | Skills, helpers, and Workbench for Copilot |
| `atlas-stage-runner-0.2.0.vsix` | VS Code Stage Runner |

Save them in Downloads. Extract the plugin ZIP into your Atlas installation folder.

Windows PowerShell:

```powershell
New-Item -ItemType Directory -Force "$HOME\Tools\Atlas" | Out-Null
Expand-Archive "$HOME\Downloads\atlas-agent-plugin-0.3.0.zip" "$HOME\Tools\Atlas"
```

macOS / Linux:

```sh
mkdir -p "$HOME/Tools/Atlas"
unzip "$HOME/Downloads/atlas-agent-plugin-0.3.0.zip" -d "$HOME/Tools/Atlas"
```

The ZIP includes its `atlas` folder. Avoid an extra nesting level. In VS Code,
run **Extensions: Install from VSIX**, choose the downloaded VSIX, and reload.
Finish [Copilot setup](copilot-vs-code-installation-and-setup.md).

## Updates

1. Close VS Code. Download the matching plugin ZIP and VSIX from your administrator.
2. Move the installed `atlas` folder to a backup location outside `Tools/Atlas`.
   Keep working folders and their `.atlas` files intact.
3. Extract the new plugin ZIP into `Tools/Atlas`, using the first-install commands
   above with the downloaded version filename. Replace the whole plugin folder
   so removed release files do not linger. Keep the registered path unchanged.
4. Install the updated VSIX with **Extensions: Install from VSIX** and reload VS Code.
5. Run **Atlas: Check Stage Runner** and confirm Atlas works in Copilot before
   removing the backup.

If `code` is on PATH, the VSIX can also be installed with:

```sh
code --install-extension "/full/path/to/atlas-stage-runner-0.2.0.vsix" --force
```

The plugin location setting remains valid. Working files and VS Code sign-in
are separate from the replaced package. No terminal setup command is required.

## Recovery

If extraction or verification fails, close VS Code, move the new plugin folder
aside, and restore the backup to its original `Tools/Atlas/atlas` path. Reinstall
the previous matching VSIX if needed. Keep working folders separate and intact.

## Backend compatibility

Install the matching plugin and VSIX for Project-owned enrichment. The deployed MCP/backend and database install contract must also include the enrichment datasets and Change Set section; replacing laptop files alone does not update a server or database. Refresh the Project Snapshot after the compatible backend is available. If `object_enrichment` or `attribute_enrichment` is missing from the advertised contracts, retain local work and request the compatible server release. Never substitute physical Metadata updates. Web audit-prompt changes require the updated published prompt versions as well.
