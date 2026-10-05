# Codex installation and setup

Atlas in Codex uses the Atlas extension running in VS Code. Keep VS Code open
with the same local working folder. Microsoft sign-in stays inside VS Code.
No Atlas client ID, application registration, secret, or connector login is needed.

## 1. Install prerequisites

- VS Code 1.136+ and Atlas Stage Runner 0.2.0 or later.
- Node.js 22+ with npm; Python 3.12+ for Snapshot and package ZIP helpers.
- Codex CLI with plugin commands; installation is tested with CLI 0.147.0.
- Chrome or Edge for Atlas Local Workbench.
- Your dev Microsoft account already authorized for Atlas through VS Code.

If needed, install Codex and complete your normal Codex sign-in:

```sh
npm install -g @openai/codex
codex login
```

Your Codex account and Atlas Microsoft account may differ. See the
[official Codex installation guide](https://learn.chatgpt.com/docs/codex/cli#getting-started).
You can use VS Code for the bridge without using Copilot Chat.

## 2. Install the shared packages and extension

Follow [shared installation](install-and-update.md#first-installation).
Both clients use the same `Tools/Atlas` location.

In VS Code, run **Extensions: Install from VSIX** from the Command Palette.
Select `atlas-stage-runner-0.2.0.vsix` and reload VS Code.

## 3. Register Atlas with Codex once

Windows PowerShell:

```powershell
cd "$HOME\Tools\Atlas\atlas-connector"
npm run setup
```

macOS / Linux:

```sh
cd "$HOME/Tools/Atlas/atlas-connector"
npm run setup
```

Setup creates or refreshes `Tools/Atlas/codex-atlas` and registers it with Codex.
The connector is bundled and needs no `npm install`, native module, or Microsoft
configuration. Repeat this command after replacing the packages.

## 4. Start the bridge for your working folder

1. Open your working folder in a **local VS Code window**. Trust that folder.
2. Run **Atlas: Start Codex Bridge** from the Command Palette.
3. Complete Microsoft sign-in if prompted. Use your dev account with Atlas access.
4. Wait for **Atlas Codex Bridge is ready**. Keep this window open.
5. Open Codex in that exact same folder. Restart an existing Codex session if needed.
6. Ask: **Start atlas. List the tenants I can access.**

For example, open `~/Work/SalesModel` in VS Code and start Codex there. Use the
working folder, not the installation folder or a subfolder. In a VS Code multi-root
workspace, each open folder receives its own bridge. Use one bridge window per folder.

The connection is persistent. Only Atlas tool calls pass through it; normal Codex
chat and other tools do not. The extension keeps its remote MCP connection open
for each connected Codex session. Cloud tasks, remote SSH windows, and WSL windows
are outside this local same-computer setup.

Continue with the [usage guide](usage-guide.md).

## Reconnect or stop

After reopening VS Code, changing working folders, changing the backend profile,
or signing out, run **Atlas: Start Codex Bridge** again. Restart Codex if its tool
connection was lost. Use the same Microsoft account for existing drafts.

Run **Atlas: Stop Codex Bridge** to disconnect Codex from Atlas. Closing VS Code
also disconnects it. If a connection closes during Stage or Apply, inspect the
operation's server status before retrying. An interrupted write is never replayed
automatically. Follow [Stage recovery](../references/change-set-lifecycle.md).

An optional terminal check runs from your **working folder**:

```sh
node "/full/path/to/Tools/Atlas/atlas-connector/atlas-connector.cjs" check
```

This checks the running bridge. It never opens Microsoft sign-in.

## Updates

Follow the [shared update commands](install-and-update.md#updates). Install the
matching VSIX, run `npm run setup`, then start the bridge in VS Code again.

## Setup help

| Problem | Action |
|---|---|
| `BRIDGE_UNAVAILABLE` | Open the exact Codex working folder in local VS Code and run **Atlas: Start Codex Bridge**. |
| `BRIDGE_ALREADY_RUNNING` | Stop the bridge in the other VS Code window for that folder. |
| `WORKSPACE_UNTRUSTED` | Trust the intended working folder in VS Code. |
| `AUTHENTICATION_REQUIRED` or `ACCOUNT_CHANGED` | Restart the bridge in VS Code and select the correct dev account. |
| `BRIDGE_STORAGE_UNSAFE` | Ask your administrator to check permissions on the per-user `.atlas-bridge` directory. |
| Tools outdated | Run `npm run setup` from the connector folder and restart Codex. |
| Setup interrupted | Follow [recovery](install-and-update.md#recovery). |

Manual registration, if needed, from `atlas-connector`:

```sh
node atlas-connector.cjs setup
codex plugin marketplace add ../codex-atlas
codex plugin add atlas@gds-workbench
```

For a custom plugin path, use `npm run setup -- --plugin "/absolute/path/to/atlas"`
each time. The shared default needs no options. See the
[official plugin instructions](https://developers.openai.com/plugins/build/plugins#add-a-marketplace-from-the-cli).
