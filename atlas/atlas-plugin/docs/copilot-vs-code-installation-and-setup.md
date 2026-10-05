# Copilot - VS Code installation and setup guide

Set up Atlas once in your VS Code user profile. Then follow the
[shared usage guide](usage-guide.md) for all working folders.

## 1. Check the required software and access

- VS Code 1.136 or later, with GitHub Copilot access.
- Node.js 20 or later, and Python 3.12 or later, for Atlas local tools.
- Chrome or Edge, for Atlas Local Workbench.
- A **dev Microsoft account with Atlas access**.

Sign in to Copilot with your usual GitHub account. Use the dev Microsoft account
when Atlas asks you to sign in. These accounts can be different.

## 2. Get the Atlas files

Get these files from your Atlas administrator:

| File | Purpose |
|---|---|
| `atlas-agent-plugin-0.3.0.zip` | Skills, local tools, and Atlas Local Workbench. |
| `atlas-connector-0.2.0.zip` | Shared ZIP updater; also supplies the Codex relay. |
| `atlas-stage-runner-0.2.0.vsix` | The Stage Runner extension for VS Code. |

Follow the [shared installation steps](install-and-update.md#first-installation).
Use `%USERPROFILE%\Tools\Atlas\atlas` on Windows or `~/Tools/Atlas/atlas` on
macOS/Linux. Codex uses the same release from this location.
Keep working files elsewhere. You do not copy the plugin into each project.

## 3. Register the plugin in VS Code

1. Open the Command Palette: **Ctrl+Shift+P**, or **Cmd+Shift+P** on macOS.
2. Run **Preferences: Open User Settings (JSON)**.
3. Add the settings below. Use the actual path to your extracted `atlas` folder.
   Keep your existing settings and any other plugin entries.

   ```json
   {
     "chat.plugins.enabled": true,
     "chat.pluginLocations": {
       "C:/Users/YOUR_NAME/Tools/Atlas/atlas": true
     }
   }
   ```

4. Replace `YOUR_NAME` with your Windows user folder name. On macOS or Linux,
   use the full path, such as `/Users/YOUR_NAME/Tools/Atlas/atlas` or
   `/home/YOUR_NAME/Tools/Atlas/atlas`. Do not use `~` or environment variables here. Save the file.

User settings make the plugin available across folders in this VS Code profile.
See the [VS Code local plugin instructions](https://code.visualstudio.com/docs/agent-customization/agent-plugins#use-local-plugins).

## 4. Install Stage Runner

1. Open the Command Palette.
2. Run **Extensions: Install from VSIX**.
3. Select `atlas-stage-runner-0.2.0.vsix`.
4. Reload VS Code when asked.

This is the standard [VSIX installation procedure](https://code.visualstudio.com/docs/configure/extensions/extension-marketplace#install-from-a-vsix).

## 5. Open a working folder and sign in

1. Use **File > Open Folder** to open the folder where you want Atlas to work.
2. Trust the folder if it is your intended working folder. Stage Runner requires
   a trusted workspace.
3. Run **Atlas: Check Stage Runner** from the Command Palette.
4. When Microsoft sign-in opens, select your **dev Microsoft account** and
   complete any required verification.
5. Wait for the message `Atlas Stage Runner is ready`.

The supplied plugin and extension already select the Atlas backend. You do not
need to enter an app ID, client secret, or token. Keep the default Stage Runner
profile unless your administrator supplies different instructions.

## 6. Confirm that Copilot can use Atlas

1. Open Copilot Chat in a local VS Code agent session.
2. Check that the Atlas MCP tools and these extension tools are enabled:
   **Check Atlas Stage Runner** and **Stage Approved Atlas Change Set**.
3. Send this request:

   ```text
   Start atlas. List the tenants I can access.
   ```

4. If the plugin's MCP connection asks for sign-in, select the **same dev
   Microsoft account** used in step 5.

The plugin connection and extension use separate VS Code sign-in flows. A second
prompt can be normal. Setup is complete when Stage Runner is ready and Atlas
can list your available Tenants. Continue with the [usage guide](usage-guide.md).

Before useful, authorized delegation, Atlas asks for a **sub-agent policy**: **Current model only**,
**Agent selects the model**, or **Specified model only**. For the last choice,
give an exact available model name or ID. The choice is saved per working folder;
see [the shared policy steps](usage-guide.md#choose-the-sub-agent-policy).
If your VS Code agent cannot enforce the rule, Atlas continues without sub-agents.

Use [VS Code's tool controls](https://code.visualstudio.com/docs/agents/run/tools#select-tools-for-a-request)
to enable a missing tool. Keep VS Code connected while the extension tools run.

## Updates

Follow the [shared update commands](install-and-update.md#updates), then install
the updated VSIX using **Extensions: Install from VSIX** and reload VS Code.
Keep the same plugin location. No new settings or client ID are required.
Copilot-only users skip `npm run setup`; Codex users run it after replacement.

## When Atlas asks you to sign in again

Run **Atlas: Check Stage Runner** again and complete the Microsoft prompt. If the
plugin's MCP connection also asks, sign in there with the same dev account.
No terminal login or new plugin installation is needed.

VS Code manages its Microsoft session. Atlas does not save your password in the
plugin or working folder. Codex bridge requests use this extension session. The
Copilot plugin MCP connection still uses its separate VS Code-managed connection.

## Setup help

| Problem | Action |
|---|---|
| Atlas is missing | Check that the registered path contains `plugin.json`, plugin support is enabled, and your organization permits the plugin. |
| The check command is missing | Confirm that the Stage Runner extension is installed and enabled. Reload VS Code. |
| Stage Runner cannot use the folder | Open the intended folder as a trusted workspace. |
| Sign-in succeeds but Atlas access fails | Ask your administrator to check access for your dev account. |
| Atlas Local Workbench cannot select a folder | Open it in Chrome or Edge. |
