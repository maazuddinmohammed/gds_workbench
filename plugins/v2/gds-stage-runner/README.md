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

## 0.1.1 receipt compatibility fix

Success and failure receipts are JSON inside a `LanguageModelTextPart`. Version 0.1.0
returned a JSON data part, which some Copilot hosts presented as an unreadable attachment.
The receipt fields and Stage behavior are unchanged. Payload records remain outside model context.

Install `gds-stage-runner-0.1.1.vsix`, reload VS Code, and confirm version **0.1.1** in
Extensions. **Check Stage Runner** checks authentication and a read-only MCP call; it
does not test a Stage transfer or the receipt returned to Copilot.

An unreadable receipt can follow a completed Stage. Keep that draft pending and inspect
its server status/revision before any recovery. Do not blindly Stage again or Apply;
a server fingerprint alone cannot reconstruct a missing local approval-to-Stage proof.

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

The host regression test invokes the tool from the actual unpacked VSIX using installed
VS Code, synthetic approved files, and an in-memory loopback MCP server. It checks
activation, readable success/failure receipts, direct and two-chunk transfers, changed
approval rejection, lost-write handling, and fingerprint verification. No account,
Azure service, or database is used.

On macOS/Linux, with VS Code and `unzip` installed, run from this extension directory:

```sh
npm run package:vsix
npm run test:host
```

The runner creates a disposable workspace and isolated user/extension directories.
Only that test profile enables automatic tool approval, using VS Code's API-test
context flag. It requires an explicit completed host result; CLI exit zero is insufficient.
Set `GDS_STAGE_TEST_CODE` to override the installed VS Code executable. An optional VSIX
argument permits regression testing an older package: `npm run test:host -- /path/to/candidate.vsix`.

These tests do not reproduce Windows, an actual Copilot conversation, or production
Microsoft sign-in. Those still require verification in their actual environment.
