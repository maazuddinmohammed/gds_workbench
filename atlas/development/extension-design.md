# Atlas Stage Runner code map

The VSIX supplies `atlas_checkStageRunner` and `atlas_stageApprovedManifest`, plus the **Atlas: Check Stage Runner** command. [Submission and recovery](../atlas-plugin/references/change-set-lifecycle.md) owns the runtime procedure; [the extension README](../atlas-vs-code/README.md) owns installation and settings.

## Source boundaries

| Module | Responsibility |
|---|---|
| `extension.ts` | Check/Stage tool registration, workspace trust, authentication adapter, cancellation and one-document JSON result files. |
| `stage-runner.ts` | Scope resolution, server reconciliation, pre-write recheck, Stage coordination, uncertain-result recovery and receipt checkpoint. |
| `stage-request.ts` | Workspace containment, regular files, owner/task/operation binding, input hashes, approved digest and expected-file-hash operation writes. |
| `stage-transport.ts` | Direct/chunk/fragment limits, canonical hashes, response/revision checks and governed fingerprint verification. |
| `stage-contract.ts` | Wire types, constants and errors. |
| `auth.ts`, `profile.ts`, `mcp-client.ts` | Microsoft authentication, validated profiles, MCP lifecycle and bounded authentication retry. |
| `receipt.ts`, `unicode.ts` | Safe failures and shared normalization. Serialization comes from `atlas-plugin/workbench/core.js`. |

Keep check read-only and return only safe backend identity. Stage derives the acknowledged digest from the bound operation when `expectedDigest` is omitted; an explicit value must match. Neither path generates a new approval. Cached draft evidence cannot replace the live revision/fingerprint check before a write.

Evidence binds the original task/owner, backend, Snapshot inputs, local content and server draft. Task navigation does not move approval. Server reconciliation preserves unrelated records; the complete authoritative action review remains necessary before separate Apply approval. Credentials stay in memory.

## Local verification

```text
npm --prefix atlas/atlas-vs-code test
npm --prefix atlas/atlas-vs-code run compile
npm --prefix atlas/atlas-vs-code run package:vsix
npm --prefix atlas/atlas-vs-code run test:host
```

Tests cover transport, malformed responses, operation/owner isolation, digest/revision checks, lost writes, read-only recovery, response files and packaged-host behavior. The host fixture uses a disposable workspace and loopback backend. Packaging does not publish or deploy.
