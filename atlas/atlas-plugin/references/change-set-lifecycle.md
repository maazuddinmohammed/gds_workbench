# Change Set lifecycle

Shared procedure for workflows that change Metadata or Model records. Read-only work stops before submission. Generated code uses this procedure only when it is part of a supported Change Set; saving files does not deploy or execute them.

Use the Atlas helper and matching VS Code extension. Exact local commands are in the [runtime guide](../docs/runtime-guide.md) and [machine contract](../contracts/local-helper.json).

## Local work to Apply

1. **Finish the related local work.** Keep Snapshot files unchanged; accumulate complete proposed records in the local Change Set. Read the effective Snapshot-plus-pending result. Preserve earlier edits and unrelated work.
2. **Validate locally.** Follow the shared [local validation sequence](local-validation.md) against that effective result. Repair failures and retain actual findings; a written checklist is not a validation result.
3. **Review in Workbench.** Show the complete local batch, meaningful differences, evidence and actual validation results. In the first release, obtain the user's acknowledgement in the agent conversation after that review; helpers record its exact content binding. No Workbench acknowledgement/Stage/Apply buttons are required. Bind acknowledgement to the local digest; changed content requires renewed checks and review.
4. **Prepare the server draft.** Verify scope, required freshness and governed Tenant Lock. Inspect existing task-bound drafts and receipts first. Create or reuse the correct Metadata or Model Change Set without overwriting unrelated pending work. A matching staged or validated draft can resume at its next step.
5. **Stage through the extension.** Check [extension readiness](#extension-readiness), prepare the supported manifest and invoke the [Stage tool](#atlas-helper-and-stage-contracts) with its path and accepted digest. The extension reads and transports the records. Do not paste payloads into tool calls or reconstruct hashes. Several transport chunks still represent one logical Change Set.
6. **Verify staging.** Require the successful Stage receipt and verified server fingerprint. Retain the approved local digest, area, Change Set ID, resulting draft revision and server fingerprint in durable task evidence. Inspect unexpected server content before proceeding; existing pending records may have been retained during reconciliation.
7. **Validate on the server.** Validate that exact resulting draft revision. The backend remains authoritative. On failure, preserve diagnostics, repair locally, repeat affected local checks and review, then use the supported restaging flow. Never report a local pass as a server pass.
8. **Ask for Apply approval.** Present the complete authoritative server action review and validation result, including retained server changes. Ask: "Apply these validated changes to [Tenant/Model]?" Approval covers that reviewed revision and content. Local Workbench acknowledgement and successful staging do not authorize Apply.
9. **Apply and verify.** Recheck scope, local digest, server revision/fingerprint and validated status against the reviewed checkpoint. Apply once using the governed operation. Confirm the actual result, retain its receipt and release a lock acquired for this work when appropriate. After verified Apply, mark affected Snapshots stale; refresh before dependent work needs applied values. Retire only local records confirmed as applied.

Stage transfers proposed records to a server draft. Apply persists the validated changes. Neither is a Git commit, push, deployment or pipeline run.

## Workflow-specific inputs

Each workflow supplies its affected area, records, checks and input requirements; it links here instead of repeating the procedure.

Use [Model Change Set authoring](model/change-sets.md) for local Model record construction and dataset contracts. This lifecycle owns transport/review/Apply, not field definitions or modeling decisions.

- **Metadata:** bind owning Tenant and Metadata Change Set revision. Metadata has no Tenant-wide revision counter; preserve its freshness, locking and validation protections.
- **Model:** bind Model identity, applied Model revision and Model Change Set revision. Recheck the applied revision before handoff.
- **Model-selected enrichment:** write Metadata only. Recheck the Model revision used to select scope; reconcile a changed selection before submission.
- **Mixed work:** Metadata and Model have separate drafts and Applies. Order them by dependencies; there is no combined atomic Apply.
- **Several Metadata owners:** Model-derived work stays in one working directory with [owner-specific roots](workspace-contract.md#model-derived-metadata-owners). Resolve the selected owner before every read, validation, manifest or receipt operation. Each owner has a separate server Change Set and approval binding; preserve the primary Tenant/Model context.

## Resume and uncertainty

- Reuse a matching task-bound checkpoint; do not stage again merely because a new task or turn began. A newly read fingerprint cannot recreate missing historical approval.
- If content, scope or revisions differ from the reviewed checkpoint, reconcile and obtain the review required for the changed content. Do not silently clear a conflicting draft.
- If Stage or Apply returns an uncertain result, inspect authoritative summary/status and fingerprint before retrying. Partial staging is not permission to fall back to another transport.
- If a required helper, extension or review surface is unavailable, retain the local work and report the missing capability. Do not invent a successful review, receipt or alternative submission path.
- Store bounded receipts and evidence in the existing task; do not create a second handoff checklist or save raw payloads, tokens or tool dumps.

## Extension readiness

- The matching Stage Runner must be installed and enabled in a VS Code workspace containing the approved manifest and files. Restricted Mode disables Stage; workspace trust is a user/host decision, never something the agent bypasses.
- Confirm the current agent host actually exposes the extension's language-model tool. A portable plugin or MCP connection does not automatically expose VS Code extension tools in another host. If unavailable, retain the local work and continue submission in a supported host; do not invent an Atlas tool or alternate payload transport.
- Atlas provides **Atlas: Check Stage Runner** (`atlasStageRunner.check`) for a read-only connection/authentication check when needed. It does not prove that a transfer succeeded. Plugin and extension connections are independent; use their intended matching backend. SQL environment (`dev`, `qa`, `stg`, `prod`) is not the extension's connection profile.
- Reuse an already working connection; do not repeat setup at every workflow or batch. Resolve sign-in through the extension's supported host flow, never through copied tokens or credentials.
- The host may show its own Stage confirmation. Preserve that interaction; it does not replace acknowledgement of the exact local content or separate approval to Apply.

The companion extension is packaged separately as a VSIX; see [extension design](../docs/extension-design.md).

## Atlas helper and Stage contracts

Run `node scripts/atlas-local.js <command>` from the installed plugin directory. Every `--session` is the workspace root containing `.atlas`; add `--owner <verified-Tenant-id>` for another registered Metadata owner.

| Step | Helper contract |
|---|---|
| Review and checks | `review --session <path> --area metadata|model`, then `validate` with the same scope. Resolve all errors; retain the actual digest and checks performed. |
| Record acknowledgement | After conversation acknowledgement, `accept --session <path> --area <area> --digest <reviewed-digest> --backend-profile <profile> --endpoint-sha256 <hash>`. Obtain the safe backend identity from Check Stage Runner; never store connection values. |
| Bind server draft | `draft-cache --session <path> --area <area> --id <UUID> --revision <n> --status active`, from verified create/get results. The operation cannot be rebound to another draft. |
| Prepare request | `prepare-stage-request --session <path> --area <area>`. Preserve returned manifest path and digest exactly. |
| Record server validation | `operation-record --session <path> --area <area> --checkpoint validation --file <curated-result.json>`. The file carries the authoritative owner/Model, Change Set ID, revision, valid/status, candidate digest, counts and complete action review. |
| Record separate Apply approval | After the user approves that server review, `operation-record ... --checkpoint apply-approval --file <same-result.json> --review-digest <saved-review-sha256>`. Changed local files or inputs invalidate this step. |
| Record completed Apply | `operation-record ... --checkpoint apply --file <curated-apply-result.json>`. Requires the separately approved candidate; marks the Snapshot for refresh. |

There is no fixed task-stage transition. Flexible task progress is independent of operation checkpoints. Discover full flags with `command-contract --command <name>`.

The extension tool takes the preparation result:

```javascript
atlas_stageApprovedManifest({
  manifestPath: result.manifest,
  expectedDigest: result.accepted_digest
})
```

Success requires `status=staged` and `fingerprintVerified=true`. The extension saves the receipt and resulting draft revision directly to the bound operation; a different active task does not redirect it. It retains existing server-only records through reconciliation, so the subsequent server action review must include them.

For an uncertain Stage result, invoke the same tool with `recoverOnly:true`. It performs reads only and verifies the previously recorded complete intended dataset counts/hashes plus governed fingerprint at the current revision. Exact confirmation restores the receipt; partial/different content or missing prior intent remains uncertain. It never silently replays writes. Preserve the operation and resolve that draft explicitly when proof is unavailable.

On server `valid=false`, `operation-record` preserves the failed revision/digest. Repair locally, validate, review and accept again; the new operation inherits the failed draft for the supported failed-draft retry. Do not clear or recreate a draft to conceal conflicts. Successful restaging updates the revision; repeat server validation and obtain a new Apply approval.

A confirmed Apply is recorded even if local files were subsequently edited; refresh retires only proposals equal to confirmed applied Snapshot records. Unrelated/new proposals remain. Unknown Apply outcomes require authoritative status inspection before retrying, never an invented success receipt.

Local digest, server fingerprint and validation candidate digest identify different representations. Server normalization means they need not match. The receipt links approved local content to the staging result; complete server action review remains necessary.

Governed operations use the `metadata` or `model` family: `create_*_change_set`, `get_*_change_set`, `get_*_change_set_fingerprint`, `validate_*_change_set`, and `apply_*_change_set`. Validate and Apply require `expected_draft_revision`. The extension's Stage-batch commit finalizes transport only.

All 13 workflow skills link here, including both build pairs and Custom when changing governed records. Atlas entry only routes. Keep transport instructions here and dataset-specific rules in their references.
