# atlas extension

`atlas/atlas-vs-code` supplies the local **Atlas: Check Stage Runner** command
(`atlasStageRunner.check`) and `atlas_stageApprovedManifest` language-model tool.
Its local VSIX is `atlas/dist/atlas-stage-runner-0.1.0.vsix`. The plugin and extension
are independently packaged; VS Code must install the extension to expose its tool.
Other hosts need a supported integration; the plugin format alone does not expose
VS Code tools.

## Responsibility

Transport acknowledged Metadata or Model Change Sets through existing governed
Stage tools. The [Change Set lifecycle](../references/change-set-lifecycle.md)
owns preparation, invocation, server validation and separate Apply approval.
The extension reads files itself, preserves nonconflicting server records, stages
bounded requests and returns a compact receipt. It does not author records, run
SQL, Apply, publish or commit code.

## Source boundaries

| Module | Responsibility |
|---|---|
| `extension.ts` | Tool/command registration, workspace trust, authentication adapter, cancellation, readable results. |
| `stage-runner.ts` | Scope resolution, server reconciliation, immediate pre-write recheck, Stage coordination, uncertain-result recovery and receipt checkpoint. |
| `stage-request.ts` | Workspace containment, regular files, owner/task/operation binding, snapshot/report/evidence/payload hashes, expected-file-hash operation writes. |
| `stage-transport.ts` | Direct/chunk/fragment limits, canonical hashes, response/revision checks and governed fingerprint verification. |
| `stage-contract.ts` | Shared wire types, constants and errors. |
| `auth.ts`, `profile.ts`, `mcp-client.ts` | Existing Microsoft authentication, validated backend profiles, MCP connection lifecycle and bounded authentication retry. |
| `receipt.ts`, `unicode.ts` | Safe failures and shared normalization. Canonical serialization comes from `../atlas-plugin/workbench/core.js`. |

## Workspace and approval binding

The tool accepts `{manifestPath, expectedDigest}`. The manifest path is absolute;
paths inside manifests and operation records remain workspace-relative. Stage
checks the current owner-specific operation in `.atlas/session.json`, its task
UUID, owner root, backend identity, snapshot inputs, acknowledged local digest,
validation report, retained evidence and server draft revision. Navigating to a
different task does not revoke an existing valid operation.

Metadata uses the registered owner (`.` or `metadata-owners/tenant-<id>`). Model
uses the primary tenant. Tenant access is resolved using the governed tenant list.
Local schema validation remains in the helper/Workbench; Stage verifies the
bound valid report and backend revalidates server operations.

**Check Stage Runner** returns safe `profile` and `endpoint_sha256` identifiers
for `accept`. Settings are `atlas.stageRunner.profile` and
`atlas.stageRunner.localUrl`. Production authentication, allowed tools/datasets,
Unicode behavior, byte limits and revision fencing retain GDS safeguards.
Credentials stay in memory.

## Uncertain Stage recovery

Before the first possible write, Stage persists an `unknown` attempt with the
accepted digest and reconciled per-dataset record counts and canonical hashes.
Successful fingerprint verification stores the receipt and advanced draft
revision with an expected-file-hash write. Cancellation or lost responses never
trigger blind replay.

Invoke the same tool with `{manifestPath, expectedDigest, recoverOnly: true}` to
recover. It performs read-only governed queries, requires an advanced active
draft revision, matches complete records to the saved intent, verifies the
fingerprint against those records, and rechecks local approval before writing a
verified receipt. It sends no Stage requests.

Partial commits, conflicting later edits, server-normalized rows differing from
the saved intent, and older unknown attempts without intent hashes remain
uncertain. Inspect/reconcile them explicitly. Failure receipt fields do not
authorize an alternate write channel.

## Local verification

The extension suite covers direct/chunk/fragment transport, malformed responses,
owner/task isolation, evidence changes, revision/digest/fingerprint checks,
cancellation, lost writes, and read-only recovery. Compile and package locally:

```text
npm --prefix atlas/atlas-vs-code test
npm --prefix atlas/atlas-vs-code run compile
npm --prefix atlas/atlas-vs-code run package:vsix
npm --prefix atlas/atlas-vs-code run test:host
```

The packaged-host fixture uses a disposable workspace and loopback backend.
Local packaging does not publish or deploy the extension.
