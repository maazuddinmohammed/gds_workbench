# Atlas Stage Runner

VS Code companion for `atlas-plugin`. The language-model tool `atlas_stageApprovedManifest` transports one locally validated and acknowledged Metadata or Model Change Set. Atlas retains reasoning, review, server validation and separate Apply approval.

## Install and connect

1. Install the locally built `atlas-stage-runner-0.1.0.vsix` with **Extensions: Install from VSIX**.
2. Open the working directory in a trusted VS Code workspace and reload the window.
3. Run **Atlas: Check Stage Runner**. The command returns the selected profile and endpoint SHA-256 for the local acknowledgement helper; it never returns tokens or connection values.

Settings: `atlas.stageRunner.profile` (`production`, `local`, `azureLocalTest`) and `atlas.stageRunner.localUrl` for an exact loopback HTTP `/mcp` endpoint. Production uses the existing pinned GDS backend and Microsoft sign-in. Plugin and extension connections are separate. SQL environment is unrelated to this connection profile.

The tool is registered through VS Code's language-model API. Another agent host needs its own supported integration; installing the portable plugin does not expose this tool there.

## Stage contract

```javascript
atlas_stageApprovedManifest({
  manifestPath: result.manifest,
  expectedDigest: result.accepted_digest
})
```

Use the actual manifest path and accepted digest returned by Atlas's `prepare-stage-request` helper. The manifest lives under `.atlas/tasks/<task-id>.evidence/` and binds one operation, owner root, backend, Snapshot inputs, validation report, acknowledgement, draft revision and complete local batch.

The extension:

- Rejects changed content/proof, stale inputs, symlinks, escaped paths, wrong owners/backends and unsupported records.
- Reconciles nonconflicting server records and sends bounded direct, chunked or generated-code fragment requests.
- Rechecks approval before writing; preserves cancellation, revision and fingerprint checks.
- Records an uncertain attempt before the first possible write. Unknown outcomes require authoritative inspection, never blind retry.
- Stores a bounded verified receipt and updated draft checkpoint after successful Stage. No raw payload rows or credentials are returned.

Task navigation and editable progress do not grant or revoke approval. Different Metadata owners have separate roots and operations; a request cannot aggregate owners. Moving the whole working directory preserves relative references.

Stage does not Apply, run SQL, deploy files or commit code. The receipt's legacy fallback flag is retained for transport compatibility; it does not authorize an alternative submission flow.

## Local development

```sh
npm test
npm run compile
npm run package:vsix
npm run test:host
```

Tests use synthetic local files and in-memory/loopback MCP fixtures. The packaged-host check requires an installed VS Code and uses its own temporary workspace/profile; it never downloads a host. Override its host executable with `ATLAS_STAGE_TEST_CODE` if needed.

`stage-request.ts` owns local proof/path verification; `stage-runner.ts` owns reconciliation and coordination; `stage-transport.ts` owns bounded transport and response checks. Canonical serialization and Unicode behavior are bundled from `../atlas-plugin/workbench/`.

For an uncertain Stage, invoke the same tool with `recoverOnly: true`. It performs
read-only governed queries and restores a receipt only when the current active
draft matches the reconciled record hashes saved before the attempted write and
its governed fingerprint. It never replays Stage. Partial commits, subsequent
conflicting edits, server-normalized rows differing from the saved intent, or old
attempts without saved hashes remain uncertain and require explicit draft review.
