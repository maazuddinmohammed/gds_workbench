# Atlas Stage Runner

VS Code companion for the Atlas plugin. It checks the backend connection and stages reviewed Metadata or Model changes. **Stage never Applies changes.**

## Install

1. Install `atlas-stage-runner-0.1.1.vsix` using **Extensions: Install from VSIX**.
2. Open your Atlas working directory in a trusted workspace; reload VS Code.
3. Start Atlas. The agent checks Stage Runner before preparing changes for submission.

You can also run **Atlas: Check Stage Runner** from the Command Palette. Production uses Microsoft sign-in. Plugin and extension connections are separate; SQL environment does not select the backend.

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

Atlas validates locally, asks you to review in Workbench, then records your acknowledgement. It creates or reads the server draft and prepares the manifest before calling Stage Runner. Server validation and a **separate Apply approval** follow Stage.

If Stage has an uncertain outcome, use the same manifest with `recoverOnly: true`. Recovery only reads the server: it restores a receipt when the active draft and fingerprint match the saved intent. Partial or conflicting results need review; never retry blindly.

These tools use VS Code's language-model API. Other agent hosts need a supported integration; installing the plugin alone does not expose VS Code tools there.
