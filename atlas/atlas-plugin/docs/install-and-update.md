# Shared Atlas installation and updates

Use one permanent installation for Copilot and Codex. Keep project work elsewhere.

| System | Installation | Example working folder |
|---|---|---|
| Windows | `%USERPROFILE%\Tools\Atlas` | `%USERPROFILE%\Work\SalesModel` |
| macOS / Linux | `~/Tools/Atlas` | `~/Work/SalesModel` |

```text
Tools/Atlas/
  atlas/              Portable plugin shared by both clients.
  atlas-connector/    Local Codex relay and ZIP updater.
  codex-atlas/         Generated Codex plugin; refreshed by setup.
```

Copilot reads `atlas` directly. Codex uses the generated copy with local bridge
wiring. Both use the same plugin release and the same VS Code Stage engine.
Microsoft authentication belongs to VS Code; no connector account setup is needed.

## First installation

Get these release files:

| File | Purpose |
|---|---|
| `atlas-agent-plugin-0.3.0.zip` | Skills, helpers, and Workbench for both clients |
| `atlas-connector-0.2.0.zip` | Codex relay and shared package updater |
| `atlas-stage-runner-0.2.0.vsix` | VS Code Stage Runner and Codex bridge |

Save them in Downloads. Extract the two ZIPs into the same Atlas folder.

Windows PowerShell:

```powershell
New-Item -ItemType Directory -Force "$HOME\Tools\Atlas" | Out-Null
Expand-Archive "$HOME\Downloads\atlas-agent-plugin-0.3.0.zip" "$HOME\Tools\Atlas"
Expand-Archive "$HOME\Downloads\atlas-connector-0.2.0.zip" "$HOME\Tools\Atlas"
```

macOS / Linux:

```sh
mkdir -p "$HOME/Tools/Atlas"
unzip "$HOME/Downloads/atlas-agent-plugin-0.3.0.zip" -d "$HOME/Tools/Atlas"
unzip "$HOME/Downloads/atlas-connector-0.2.0.zip" -d "$HOME/Tools/Atlas"
```

Each ZIP includes its package folder. Avoid an extra nesting level. In VS Code,
run **Extensions: Install from VSIX**, choose the downloaded VSIX, and reload.
Finish [Codex setup](codex-installation-and-setup.md) and/or
[Copilot setup](copilot-vs-code-installation-and-setup.md).

## Updates

Close Codex and VS Code. Download the matching release ZIPs and VSIX. Run each
command only after the previous one succeeds. Use the downloaded version filenames.

Windows PowerShell:

```powershell
cd "$HOME\Tools\Atlas"
python atlas-connector/update.py --plugin "$HOME\Downloads\atlas-agent-plugin-0.3.0.zip" --connector "$HOME\Downloads\atlas-connector-0.2.0.zip"
cd atlas-connector
npm run setup
```

macOS / Linux:

```sh
cd "$HOME/Tools/Atlas"
python3 atlas-connector/update.py --plugin "$HOME/Downloads/atlas-agent-plugin-0.3.0.zip" --connector "$HOME/Downloads/atlas-connector-0.2.0.zip"
cd atlas-connector
npm run setup
```

Copilot-only users skip `npm run setup`. The updater needs only Python 3.12+.
Run it from the parent Atlas folder, outside the folders being replaced.
It validates both ZIPs, replaces whole package folders, and retains the previous
packages in `atlas-backup-...`. Removed release files do not linger. Download only
trusted release ZIPs; these checks do not establish publisher identity.

Install the updated VSIX with **Extensions: Install from VSIX** and reload VS Code.
Alternatively, if `code` is on PATH:

```sh
code --install-extension "/full/path/to/atlas-stage-runner-0.2.0.vsix" --force
```

Keep the plugin location unchanged. For Codex, open the working folder in VS Code,
run **Atlas: Start Codex Bridge**, and restart Codex in the same folder. Copilot's
existing plugin location setting remains valid. Working files and VS Code sign-in
are separate from the replaced packages. Remove the package backup after verification.

## Recovery

- Retry interrupted setup with `npm run setup`, with clients closed.
- Codex registration failed: confirm `codex plugin --help` works and use the
  manual commands in the Codex setup guide.
- A stale `.atlas-setup.lock`: confirm no setup or updater is running, then remove
  only that lock file and retry.
- `codex-atlas.previous` remains: retain the current `codex-atlas` and move the
  previous folder aside. If the current folder is missing, restore the previous
  folder to that name. Rerun setup; keep a backup until verification.
- An interrupted package replacement: restore each package present in that run's
  `atlas-backup-...` folder. A package absent from the backup stayed in place.
  Retry the updater. Keep working folders separate and intact.
- A stale bridge after a VS Code crash: reopen VS Code and start the bridge.
  If another window still owns it, stop the bridge in that window first.

The generated Codex copy contains no credentials. If it is damaged, move only
`codex-atlas` aside and rerun setup to recreate it from the supplied plugin.

## Backend compatibility

Install the matching plugin and VSIX for Model-owned enrichment. The deployed MCP/backend and database install contract must also include the enrichment datasets and Change Set section; replacing laptop files alone does not update a server or database. Refresh the Model Snapshot after the compatible backend is available. If `object_enrichment` or `attribute_enrichment` is missing from the advertised contracts, retain local work and request the compatible server release. Never substitute physical Metadata updates. Web audit-prompt changes require the updated published prompt versions as well.
