# Atlas setup guide

Set up Atlas once for VS Code Copilot. It takes about 15 minutes. Then use the
[usage guide](usage-guide.md).

## 1. Check what you need

- VS Code 1.136 or later, with GitHub Copilot.
- Node.js 20 or later, and Python 3.12 or later. Atlas's local tools use them.
- Chrome or Edge, for Atlas Local Workbench.
- A Microsoft account that your administrator enabled for Atlas. It's often a
  separate dev account, not your GitHub account.
- For Project work: access to the GDS Workbench web app, with your Project set up
  there. Atlas can't create Projects or change their source scope.
- Two files from your Atlas administrator:

| File | What it is |
|---|---|
| `atlas-agent-plugin-0.4.1.zip` | The Atlas plugin: skills, local tools and Atlas Local Workbench |
| `atlas-stage-runner-0.3.0.vsix` | Stage Runner, the VS Code extension that uploads approved changes |

## 2. Install the plugin

Extract the plugin ZIP into a `Tools/Atlas` folder in your home folder.

Windows (PowerShell):

```powershell
New-Item -ItemType Directory -Force "$HOME\Tools\Atlas" | Out-Null
Expand-Archive "$HOME\Downloads\atlas-agent-plugin-0.4.1.zip" "$HOME\Tools\Atlas"
```

macOS or Linux:

```sh
mkdir -p "$HOME/Tools/Atlas"
unzip "$HOME/Downloads/atlas-agent-plugin-0.4.1.zip" -d "$HOME/Tools/Atlas"
```

Check that `Tools/Atlas/atlas/plugin.json` exists. You never copy the plugin
into a project folder.

## 3. Register the plugin in VS Code

1. Open the Command Palette: **Ctrl+Shift+P**, or **Cmd+Shift+P** on macOS.
2. Run **Preferences: Open User Settings (JSON)**.
3. Paste these two settings inside the outer `{ }`, adding a comma after the
   setting above them:

   ```json
   "chat.plugins.enabled": true,
   "chat.pluginLocations": {
     "C:/Users/YOUR_NAME/Tools/Atlas/atlas": true
   }
   ```

   Replace the path with the full path to your `atlas` folder, using `/`, not `\`.
   On macOS it's `/Users/YOUR_NAME/Tools/Atlas/atlas`; on Linux,
   `/home/YOUR_NAME/Tools/Atlas/atlas`. Don't use `~` or variables. Save the
   file; a red underline means a JSON mistake.

See VS Code's [local plugin instructions](https://code.visualstudio.com/docs/agent-customization/agent-plugins#use-local-plugins).

## 4. Install Stage Runner

1. In the Command Palette, run **Extensions: Install from VSIX**.
2. Choose `atlas-stage-runner-0.3.0.vsix`, then reload VS Code.

If `code` is on your PATH, this does the same:

```sh
code --install-extension "/full/path/to/atlas-stage-runner-0.3.0.vsix" --force
```

## 5. Open a working folder and sign in

1. Create a new, empty folder for one Project, outside `Tools/Atlas`, such as
   `Documents/atlas-work/[project-name]`. Open it with **File > Open Folder** and
   trust it. Atlas adds its own folders here; put any specs or DDL you want it to
   read here too.
2. In the Command Palette, run **ATLAS: Check Stage Runner**.
3. Sign in with your Atlas Microsoft account.
4. Wait for `Atlas Stage Runner is ready`.

## 6. Check that it works

1. Open the Chat view. In the chat input, select **Local**, then **Agent**.
2. Select **Configure Tools** and check that **gds-workbench** (Atlas's server
   tools), **Check ATLAS Stage Runner** and **Stage Approved ATLAS Change Set**
   are selected.
3. Send:

   ```text
   Start atlas. List the tenants I can access.
   ```

4. If VS Code asks you to sign in for **gds-workbench**, use the same Microsoft
   account. Atlas's server connection signs in separately from Stage Runner.

Setup is done when Stage Runner is ready and Atlas lists your Tenants.
Continue with the [usage guide](usage-guide.md).

## Update Atlas

1. Get the new plugin ZIP and VSIX from your administrator, then close VS Code.
2. Move `Tools/Atlas/atlas` to a backup folder outside `Tools/Atlas`.
3. Extract the new ZIP as in [step 2](#2-install-the-plugin), using the new file
   name. Replace the whole folder and keep the same path.
4. Install the new VSIX as in [step 4](#4-install-stage-runner) and reload VS Code.
5. Run **ATLAS: Check Stage Runner**, check Atlas in Copilot, then delete the backup.

Your settings stay valid, and working folders keep their `.atlas` files. To roll
back, restore the backup folder and reinstall the previous VSIX.

## Troubleshooting

| Problem | What to do |
|---|---|
| Atlas doesn't appear in Copilot | Check that the registered path contains `plugin.json` and that `chat.plugins.enabled` is `true`. Your organization must allow plugins. |
| **ATLAS: Check Stage Runner** is missing | Check that Stage Runner is installed and enabled, then reload VS Code. |
| Atlas tools are missing in chat | Use a **Local** session with **Agent** selected, then turn the tools on in **Configure Tools**. |
| Stage Runner can't use the folder | Open the working folder itself and trust it. |
| VS Code asks you to sign in for **gds-workbench** | Sign in with the same account. This is Atlas's server connection. |
| Atlas says Stage Runner needs sign-in | Run **ATLAS: Check Stage Runner** and sign in. |
| Sign-in works but Atlas access fails | Ask your administrator to check your account's Atlas access. |
| "Snapshot extraction failed; Python 3.12+ is required" | Install Python 3.12 or later, then retry. |
| A version or compatibility error | Ask your administrator; the plugin, Stage Runner and server versions must match. |
| Atlas Local Workbench can't select a folder | Open it in Chrome or Edge. |
