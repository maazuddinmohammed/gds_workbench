# Change Set lifecycle

Use this procedure for Metadata or Model changes. Finish related work locally, then submit one reviewed batch at a meaningful completion/dependency boundary. Read-only work stops before submission; saving generated files does not deploy or execute them.

Run `node scripts/atlas-local.js <command>` from the installed plugin directory. `--session` is the working directory containing `.atlas`; add `--owner <verified-Tenant-id>` for another registered Metadata owner. The [runtime guide](../docs/runtime-guide.md) covers the PowerShell fallback; [command-contract](../contracts/local-helper.json) owns exact flags.

## Complete submission sequence

Keep these steps together. The normal path needs no hand-curated evidence file or copied digest.

1. **Finish and validate locally.** Accumulate complete proposed records without editing Snapshots. Run `review`, then `validate` against Snapshot plus all pending changes. Follow [local validation](local-validation.md); repair errors and rerun affected checks. Save `review` with `--output-file <workspace>/.atlas/temp/review.json`; read `review.json.digest` programmatically into `accept --digest`. Never transcribe it from conversation memory.
2. **Check Stage Runner.** Call `atlas_checkStageRunner({outputFile: "<workspace>/.atlas/temp/check.json"})`. Require `status="ready"`; its `backend` contains the safe profile and endpoint fingerprint. Reuse a verified matching result while the connection is unchanged. Check does not prove Stage success.
3. **Review in Workbench and obtain acknowledgement.** Show the complete proposed batch and actual findings. The user acknowledges the reviewed content in the conversation. An edit invalidates that acknowledgement; revalidate and review before accepting changed content.
4. **Resolve the server draft.** Check task-bound operation evidence first. Under the required Tenant Lock, create or get the correct Change Set using governed MCP. Save that operation's exact JSON response temporarily as `draft.json`; do not rename fields or reconstruct it. Existing matching staged/validated work can resume at its next checkpoint.
5. **Accept and prepare together.** Run `accept` with the reviewed digest, Check result and draft response, using `--prepare-stage true` as below. This verifies bindings, records acknowledgement and returns `stage_manifest_path`. It neither stages nor applies. The split commands below remain available when acknowledgement occurred before the server draft was known.
6. **Stage through the extension.** Invoke `atlas_stageApprovedManifest({manifestPath: preparation.stage_manifest_path})`. The extension reads the approved digest from the bound operation, rechecks local evidence and current server state, and transports the files. Require `status="staged"` and `fingerprint_verified=true`. The extension records the receipt/revision in the original bound operation. Do not paste record payloads into tools or reconstruct hashes.
7. **Validate the exact server draft.** Call the area's governed validation tool with the resulting `expected_draft_revision`. Save its exact JSON response and record it with the validation command below. Server validation remains authoritative; a local pass is not a server pass.
8. **Present the server review and ask separately to Apply.** Show the complete action review, including retained server-only changes. Ask “Apply these validated changes to [Tenant/Model]?” After approval, record `apply-approval --digest-from-operation true`. The helper reads the saved review binding and rejects changed files/evidence; no input file is required.
9. **Apply, record and refresh.** Apply the approved revision through governed MCP, then pass its exact response to the `apply` checkpoint. Confirm the actual outcome; release a lock acquired for this work when appropriate. Refresh affected Snapshots before dependent work consumes applied values. Retire only proposals confirmed as applied; retain unrelated/new edits.

Several transport chunks are one logical Change Set. Stage transfers proposals to a server draft; Apply persists them. Neither is a Git commit, deployment or pipeline run.

## Exact local commands

Use structured argument arrays where available. Paths and UUIDs below are placeholders; use actual helper/tool results.

```text
accept --session <workspace> --area metadata|model
  --digest <digest-from-reviewed-helper-result>
  --backend-file <workspace>/.atlas/temp/check.json
  --draft-file <workspace>/.atlas/temp/draft.json
  --prepare-stage true
  --output-file <workspace>/.atlas/temp/prepared.json

operation-record --session <workspace> --area metadata|model
  --checkpoint validation --file <workspace>/.atlas/temp/validation.json

operation-record --session <workspace> --area metadata|model
  --checkpoint apply-approval --digest-from-operation true

operation-record --session <workspace> --area metadata|model
  --checkpoint apply --file <workspace>/.atlas/temp/apply.json
```

Each block above is one invocation with arguments on multiple display lines; do not run each line as a separate shell command. Read `stage_manifest_path` from the preparation JSON rather than transcribing it. Optional Stage `expectedDigest` remains an extra check; if supplied, read the exact value from operation/helper output. Never substitute a recomputed digest for the acknowledged digest.

If the draft was not available at acknowledgement, omit `--draft-file`/`--prepare-stage` from `accept`, then use either:

- `prepare-stage-request --session <workspace> --area <area> --draft-file <exact-server-response.json>` to import and prepare in one command; or
- `draft-cache --session <workspace> --area <area> --file <exact-server-response.json>`, followed by `prepare-stage-request` with the same scope.

Preparation uses the current operation's draft and verifies local identity, revision/status and content bindings. A cached response cannot prove live freshness; Stage Runner checks current server state before writes. An operation cannot silently switch to another Change Set.

## Response and evidence files

- Each `--output-file` is a new `.atlas/temp/*.json` file containing **one JSON document**; use a new filename on retry. Existing files are preserved. Tool output files follow the same rule; diagnostics are separate. Do not append pretty JSON, compact JSON or prose to the same file.
- If optional output export reports `receipt_export.status="failed"`, use the returned command result; its completed operation remains valid. Do not repeat the mutation just to recreate an output file.
- `--file`/`--draft-file` accept the operation payload, its `structuredContent` wrapper, or a single MCP text block containing JSON. Pass the actual governed create/get/validate/apply response. Ambiguous/conflicting shapes fail; repair the source capture instead of creating a curated replacement.
- Helpers normalize supported server aliases, including `metadata_change_set_id` and `model_change_set_id`, to local `change_set_id`. Never rename IDs manually or infer one from a filename.
- Durable evidence stays under `.atlas/tasks/<task>.evidence/`. Temporary operation JSON belongs under `.atlas/temp/`; retain only bounded verified evidence afterward, not credentials, arbitrary tool dumps or physical query rows.
- `accepted_digest`, server fingerprint and validation `candidate_digest` identify different representations. Do not compare them as interchangeable values. The receipt links approved local content to its Stage result.

Task progress remains flexible prose. It cannot authorize a write or replace a validation result, operation checkpoint or receipt.

## Workflow-specific bindings

Field authoring belongs in [Model Change Sets](model/change-sets.md) and the Metadata table guides; this procedure owns review and submission.

| Work | Required binding |
|---|---|
| Metadata | Owning Tenant and Metadata draft revision. No invented Tenant-wide metadata revision. |
| Model | Model identity, applied Model revision and Model draft revision. Recheck the applied revision before handoff. |
| Model-selected enrichment | Metadata only; also recheck the Model revision that selected scope. Reconcile changed selection before submission. |
| Mixed Metadata/Model work | Separate drafts and Applies ordered by dependencies; no combined atomic Apply. |
| Several Metadata owners | Same workspace, [separate owner roots](workspace-contract.md#model-derived-metadata-owners), authorization, drafts and approval bindings. Resolve owner on each helper call. |

## Extension readiness

The matching VSIX must be installed and enabled in a trusted VS Code workspace containing the approved manifest/files. Trust is a user/host decision. A portable plugin or MCP connection alone does not expose VS Code tools in another host; retain local work and continue submission in a supported host if the tool is absent.

`atlas_checkStageRunner` exposes the same read-only check as **Atlas: Check Stage Runner** (`atlasStageRunner.check`). It returns readiness and safe backend identity directly. MCP and extension connections must target the intended matching backend. SQL environment is separate from the extension connection profile. Use the supported sign-in flow; never copy tokens or credentials.

Preserve any host Stage confirmation. It does not replace content acknowledgement or separate Apply approval. Workbench has no Stage/Apply buttons in this release.

## Resume, failure and recovery

- Resume a matching task-bound checkpoint; a new turn/task does not require restaging. Content, scope or revision differences require reconciliation and the review appropriate to the changes. Never clear a conflicting draft silently.
- If Stage is uncertain, invoke the same tool with `recoverOnly:true`. It performs reads, compares the saved intended dataset counts/hashes and verifies the current fingerprint. Exact proof restores the receipt; partial/different content or missing prior intent stays uncertain. Do not retry writes or use another transport blindly.
- On server `valid=false`, recording validation preserves the failed revision/digest. Repair, validate, review and accept again; the new operation inherits the failed draft for supported restaging. Repeat server validation and obtain new Apply approval afterward.
- Unknown Apply outcomes require authoritative status inspection before retrying. A confirmed Apply can still be recorded after subsequent local edits; refresh removes only proposals matching confirmed applied records.
- Missing helpers, review surface or host capability leave local work intact. Report the missing capability without inventing a successful receipt or alternate submission path.

Governed operations use the `metadata` or `model` family: `create_*_change_set`, `get_*_change_set`, `get_*_change_set_fingerprint`, `validate_*_change_set`, and `apply_*_change_set`. Validate and Apply require `expected_draft_revision`. Stage-batch commit finalizes transport only.
