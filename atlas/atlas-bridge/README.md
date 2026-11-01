# Atlas Bridge

Atlas Bridge extension for the Atlas Plugin in VS Code Copilot. It checks the backend connection and stages reviewed Metadata or Project changes. **Stage never Applies changes.**

## User guides

The supplied Atlas Plugin contains:

- `docs/copilot-vs-code-installation-and-setup.md`: installation and sign-in.
- `docs/usage-guide.md`: the Copilot workflow.

Before authorized delegation, the plugin resolves and saves the sub-agent model
policy in the working folder. Independent work needs no policy selection.
Copilot must support the selected rule; Atlas Bridge does not select models or
start sub-agents.

The remaining sections are a technical reference for maintainers. Production
uses Microsoft sign-in. Plugin and extension connections are separate; SQL
environment does not select the backend.

Settings: `atlas.bridge.profile` accepts `production`, `local` or `azureLocalTest`. For `local`, set `atlas.bridge.localUrl` to a loopback HTTP `/mcp` endpoint.

For existing installations, follow the plugin setup guide's **First update to
Atlas Bridge** section: disable the previous extension, transfer customized
settings, select the renamed `atlas-mcp` connection and check sign-in. The deployed
`x-gds-mcp-client: atlas-stage-runner` wire identifier remains unchanged for compatibility;
it is a transport marker, not authentication or the component's name.

## Agent tools

```javascript
atlas_checkBridge({})
// { schema_version: "1.0", status: "ready", backend: { profile, endpoint_sha256 } }

atlas_stageApprovedManifest({ manifestPath: preparedManifestPath })
```

The check returns readiness and backend identity without URLs, credentials or tenant records. Stage reads the accepted digest from the prepared manifest and verifies its acknowledged operation, current files, Snapshot inputs and server draft. Optional `expectedDigest` adds an explicit comparison; a mismatch stops submission.

Both tools accept `outputFile`: an absolute path to a **new `.json` file under the workspace `.atlas/temp/` directory**. Its parent directory must exist. The file contains exactly one JSON receipt; existing files and symlinks are never overwritten. If export fails, the response includes `receipt_export`; the reported operation outcome remains unchanged.

Stage receipts use `operation_id`, `task_id`, `owner_tenant_id`, `change_set_id`, `starting_revision`, `draft_revision`, `accepted_digest`, `stage_fingerprint` and `fingerprint_verified`. The verified receipt is also stored in the operation automatically. Pass the saved response directly to Atlas helpers; do not retype hashes or curate fields.

## Review and recovery

Atlas validates locally, asks you to review in Atlas Local Workbench, then records your acknowledgement. It creates or reads the server draft and prepares the manifest before calling Atlas Bridge. Server validation and a **separate Apply approval** follow Stage.

If Stage has an uncertain outcome, use the same manifest with `recoverOnly: true`. Recovery only reads the server: it restores a receipt when the active draft and fingerprint match the saved intent. Partial or conflicting results need review; never retry blindly.

Copilot calls these tools through VS Code's language-model API in a trusted
workspace. Microsoft tokens stay in VS Code and go only to the authenticated
backend. Atlas Bridge reads payload files directly and returns bounded receipts.
