# Atlas Connector: local VS Code bridge relay

The connector carries Codex MCP requests to the running Atlas VS Code extension.
The extension authenticates with VS Code's Microsoft provider and runs Stage.
The connector has no Microsoft sign-in, token cache, client ID, or npm runtime dependencies.

## Install and use

Place `atlas` and `atlas-connector` beside each other under `~/Tools/Atlas`
(Windows: `%USERPROFILE%\Tools\Atlas`). Install the matching Stage Runner VSIX.
From `atlas-connector`, run:

```sh
npm run setup
```

Open the same local working folder in VS Code and Codex. In VS Code, run
**Atlas: Start Codex Bridge**, complete sign-in if prompted, and keep the window
open. Start or restart Codex. **Atlas: Stop Codex Bridge** disconnects it.

Setup refreshes the generated sibling `codex-atlas` and Codex registration.
For a custom portable plugin location, pass `--plugin "/absolute/path/to/atlas"`.
A read-only connection check, from the working folder, is:

```sh
node "/full/path/to/atlas-connector/atlas-connector.cjs" check
```

## Update

Close both clients. From the parent Atlas folder:

```sh
python3 atlas-connector/update.py --plugin "/path/plugin.zip" --connector "/path/connector.zip"
cd atlas-connector
npm run setup
```

Use `python` on Windows. Install the matching new VSIX and start the bridge again.
Full instructions are in the accompanying plugin's `docs/install-and-update.md`,
`docs/codex-installation-and-setup.md`, and `docs/usage-guide.md`.

## Connection boundary

Each trusted open folder gets a private Unix socket or Windows named pipe.
A short-lived pairing capability is stored in the user's protected `.atlas-bridge`
directory, never in a project. Windows ACLs and Unix ownership/modes restrict it.
Microsoft tokens stay in the extension. Only reviewed governed MCP tools and the
two Stage Runner tools cross the bridge. File access stays within the paired folder.

One persistent local connection and remote MCP session are reused per Codex session.
Only Atlas calls use this path. Account, backend, or workspace changes invalidate
the bridge. Lost connections never replay writes; inspect server status before retrying.
Background calls never open sign-in. Local same-computer sessions are supported;
remote VS Code windows and Codex cloud tasks are not.
