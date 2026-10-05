# Atlas Stage Runner

VS Code companion and local Codex bridge for the Atlas plugin. It checks the backend connection and stages reviewed Metadata or Model changes. **Stage never Applies changes.**

## User guides

The supplied Atlas plugin contains:

- `docs/copilot-vs-code-installation-and-setup.md`: installation and sign-in.
- `docs/usage-guide.md`: the shared Copilot and Codex procedure.

Before authorized delegation, the plugin resolves and saves the sub-agent model
policy in the working folder. Independent work needs no policy selection.
Copilot must support the selected rule; Stage Runner does not select models or
start sub-agents.

The remaining sections are a technical reference for maintainers. Production
uses Microsoft sign-in. Plugin and extension connections are separate; SQL
environment does not select the backend.

Settings: `atlas.stageRunner.profile` accepts `production`, `local` or `azureLocalTest`. For `local`, set `atlas.stageRunner.localUrl` to a loopback HTTP `/mcp` endpoint.

## Agent tools

```javascript
atlas_checkStageRunner({})
// { schema_version: "1.0", status: "ready", backend: { profile, endpoint_sha256 } }

atlas_stageApprovedManifest({ manifestPath: preparedManifestPath })
```

The check returns readiness and backend identity without URLs, credentials or tenant records. Stage reads the accepted digest from the prepared manifest and verifies its acknowledged operation, current files, Snapshot inputs and server draft. Optional `expectedDigest` adds an explicit comparison; a mismatch stops submission.

Both tools accept `outputFile`: an absolute path to a **new `.json` file under the workspace `.atlas/temp/` directory**. Its parent directory must exist. The file contains exactly one JSON receipt; existing files and symlinks are never overwritten. If export fails, the response includes `receipt_export`; the reported operation outcome remains unchanged.

Stage receipts use `operation_id`, `task_id`, `owner_tenant_id`, `change_set_id`, `starting_revision`, `draft_revision`, `accepted_digest`, `stage_fingerprint` and `fingerprint_verified`. The verified receipt is also stored in the operation automatically. Pass the saved response directly to Atlas helpers; do not retype hashes or curate fields.

## Review and recovery

Atlas validates locally, asks you to review in Atlas Local Workbench, then records your acknowledgement. It creates or reads the server draft and prepares the manifest before calling Stage Runner. Server validation and a **separate Apply approval** follow Stage.

If Stage has an uncertain outcome, use the same manifest with `recoverOnly: true`. Recovery only reads the server: it restores a receipt when the active draft and fingerprint match the saved intent. Partial or conflicting results need review; never retry blindly.

Copilot calls these tools through VS Code's language-model API. Codex uses the
[Atlas Connector](../atlas-connector/README.md) as a private local relay. Install
this extension for either client. In the trusted local working folder, run
**Atlas: Start Codex Bridge** and keep VS Code open. Open Codex in the same folder.
**Atlas: Stop Codex Bridge** disconnects it. No new Microsoft app registration or
client ID is needed. Microsoft tokens stay in the extension.

The bridge uses private local sockets/named pipes, short-lived pairing, a pinned
Microsoft account, and the reviewed governed tool allowlist. Stage payloads are
read by this extension and never relayed through model context. Workspace,
backend or account changes stop the bridge; unfinished writes are not replayed.
