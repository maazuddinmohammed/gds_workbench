# GDS Stage Runner

This VS Code extension contributes one narrow language-model tool: `gds_stageApprovedManifest`. The GDS agent plugin still owns reasoning, local authoring, validation, approval, and Apply. The extension only transports one accepted Metadata or Model Change Set through existing governed MCP tools without placing payload rows in model context.

## Install

Production: install GDS Stage Runner from the organization's public or private VS Code
Marketplace. The Marketplace signs published extensions and VS Code verifies that signature.

1. Open VS Code **Extensions** and select the organization's Marketplace.
2. Find **GDS Stage Runner**, verify the trusted publisher, and choose **Install**.
3. Reload VS Code and run **GDS: Check Stage Runner**.

For temporary testing, install the local `.vsix` candidate distributed beside the GDS plugin
ZIP:

1. Open VS Code **Extensions**.
2. Choose **… → Install from VSIX…**.
3. Select the GDS Stage Runner file and reload VS Code.
4. Run **GDS: Check Stage Runner**.

Production is the default profile. VS Code may request normal Microsoft sign-in/consent for the exact MCP scope. The Microsoft account may differ from the user's GitHub account. Never enter a token, secret, tenant ID, or client ID.

For a loopback development server, set `gds.stageRunner.profile` to `local` and configure its loopback `/mcp` URL. For the temporary unauthenticated Azure deployment only, explicitly select `azureLocalTest`. The extension never guesses a profile.

If the plugin connects but Stage Runner fails, run **GDS: Check Stage Runner** from the
Command Palette (`Ctrl+Shift+P` on Windows, `Cmd+Shift+P` on macOS). This is a read-only
Tenant-list check. A failure includes the selected profile and a safe DNS, certificate,
proxy, timeout, connection, or HTTP status diagnosis when recognized. Unknown failures
remain `MCP_UNAVAILABLE`; response bodies, credentials, and server addresses are omitted.
The plugin and extension connect independently. `azureLocalTest` uses the extension's
pinned Azure address and ignores `gds.stageRunner.localUrl`.

The source defaults and distributed packages target the same App Service Environment
deployment. Keep `../gds/mcp.json` and `src/profile.ts` aligned when changing that
deployment, then rebuild both the plugin ZIP and Stage Runner VSIX. Editing an
extracted plugin's address does not update an already installed extension.

## Security boundary

- Input is only an absolute Stage request path plus its accepted SHA-256 digest.
- VS Code Restricted Mode disables Stage; the active GDS workspace must be trusted.
- Production endpoint, authorization resource, scope, and Entra authority are pinned/validated.
- Paths, Snapshot/task/draft identity, files, hashes, datasets, counts, revisions, and MCP responses fail closed.
- Tokens remain in memory and never enter logs, files, child processes, settings, or receipts.
- Payloads use only existing Stage MCP tools. There is no SQL, upload, Apply, discard, lock override, arbitrary URL, or arbitrary tool facility.
- Output is a bounded redacted receipt. If any write started, legacy fallback is forbidden.

## Build and test

Use Node 22:

```text
npm ci
npm test
npm run compile
npm run package:vsix
```

`package:vsix` creates an unsigned local test candidate under `plugins/v2/dist/`. Publishing to
the organization's public or private VS Code Marketplace is the production signing/distribution
step. Never distribute the local candidate as trusted production software.

The host smoke test checks activation, command/tool registration, and JSON receipts
inside VS Code. Run it against the unpacked VSIX with temporary settings:

```sh
stage_test_dir="$(mktemp -d)"
unzip -q ../dist/gds-stage-runner-0.1.0.vsix -d "$stage_test_dir/candidate"
code --user-data-dir "$stage_test_dir/user" --extensions-dir "$stage_test_dir/extensions" \
  --extensionDevelopmentPath="$stage_test_dir/candidate/extension" \
  --extensionTestsPath="$PWD/test/vscode-host.cjs" \
  --disable-workspace-trust --skip-welcome --skip-release-notes
```

This test does not sign in or stage against a deployed server. Keep the legacy
fallback until a real signed-in Stage has also been verified.
