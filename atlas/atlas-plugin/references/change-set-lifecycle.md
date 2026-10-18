# Change Set lifecycle

Use this procedure for Metadata or Project changes. Finish related work locally, then submit one reviewed batch at a meaningful completion/dependency boundary. Read-only work stops before submission; saving generated files does not deploy or execute them.

Run `node scripts/atlas-local.js <command>` from the installed plugin directory. `--session` is the working directory containing `.atlas`; add `--owner <verified-Tenant-id>` for another registered Metadata owner. The [runtime reference](local-runtime.md) covers the PowerShell fallback; [command-contract](../contracts/local-helper.json) owns exact flags.

## Submit with `next`

Run `next --session <workspace> --area metadata|project`, do exactly its `action`, then run `next` again. Stop when it reports `no_pending_changes`. `next` only reads; every write is an action you perform.

| `action.kind` | Do |
|---|---|
| `helper` | Run `argv` exactly, as a structured argument array. |
| `mcp` | Call `tool` with `arguments` and save the exact JSON response to `save_response_to`. `requires_tenant_lock` names the Tenant whose lock you must hold: check it with `check_tenant_lock` and acquire it if free. |
| `extension` | Call the Stage Runner tool with `input`. |
| `ask_user` | Show `show` when present, ask `question` and wait for an explicit yes; then run each `after_approval` step in order. |
| `author` | Follow `instructions`, usually repairing local records. |
| `stop` | Tell the user; do not retry or work around it. |

Then follow `then`. After a failed MCP call, run `next --area <area> --error <code>` ([recovery](#resume-failure-and-recovery)). `other_work` lists other areas or owners with pending work.

| State | Meaning |
|---|---|
| `no_session`, `snapshot_missing`, `not_started`, `no_pending_changes` | Set up the workspace, install the Snapshot, or nothing to submit. |
| `needs_task`, `needs_validation`, `validation_failed`, `local_files_invalid` | Add a task, run `validate`, or repair the findings or unreadable draft files. |
| `ready_for_review` | Local changes pass validation. The user reviews them in Atlas Local Workbench and approves Stage; then check the Stage Runner, hold the Tenant Lock, create the server draft, run `accept` with `--prepare-stage true` and stage with `atlas_stageApprovedManifest`. |
| `accepted`, `draft_bound`, `stage_prepared` | An interrupted acceptance continues: create the draft, prepare the request, or stage. |
| `stage_uncertain` | The last Stage outcome is unknown; recover with `recoverOnly: true` before anything else. |
| `staged` | Validate the exact server draft and record it with the `validation` checkpoint. |
| `server_validation_failed` | Repair locally; the repaired batch restages into the same draft. |
| `server_validated` | Show the complete server action review and ask separately: “Apply these validated changes to [Tenant/Project]?” After a yes, record `apply-approval`. |
| `apply_approved` | Apply with the approved `expected_draft_revision` and `expected_candidate_digest`, then record the `apply` checkpoint. |
| `refresh_required`, `refresh_blocked` | Install a fresh Snapshot; reconcile unapplied drafts first when they exist. |
| `error_recovery` | The recovery action for the `--error` code of a failed call. |

Rules these steps enforce:

- Review and validation bind exact bytes. An edit after Stage approval invalidates it: validate and review again. Never transcribe digests from memory; helpers read them from saved results.
- Stage requires `status="staged"` and `fingerprint_verified=true`. Never paste record payloads into tools or reconstruct hashes.
- A local pass is not a server pass. Show the complete server action review, including retained server-only changes.
- An Apply approval binds one server review; a new validation needs a new approval.
- After Apply, confirm the actual outcome, release a lock acquired for this work when appropriate and refresh affected Snapshots before dependent work. Refresh retires only proposals confirmed as applied.

Several transport chunks are one logical Change Set. Stage transfers proposals to a server draft; Apply persists them. Neither is a Git commit, deployment or pipeline run.

## Exact local commands

`next` supplies these with real values; they are listed for reading its actions. Use structured argument arrays where available. Paths and UUIDs below are placeholders; use actual helper/tool results.

```text
accept --session <workspace> --area metadata|project
  --digest <digest-from-reviewed-helper-result>
  --backend-file <workspace>/.atlas/temp/check.json
  --draft-file <workspace>/.atlas/temp/draft.json
  --prepare-stage true
  --output-file <workspace>/.atlas/temp/prepared.json

operation-record --session <workspace> --area metadata|project
  --checkpoint validation --file <workspace>/.atlas/temp/validation.json

operation-record --session <workspace> --area metadata|project
  --checkpoint apply-approval --digest-from-operation true

operation-record --session <workspace> --area metadata|project
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
- Helpers normalize supported server aliases, including `metadata_change_set_id` and `project_change_set_id`, to local `change_set_id`. Never rename IDs manually or infer one from a filename.
- Durable evidence stays under `.atlas/tasks/<task>.evidence/`. Temporary operation JSON belongs under `.atlas/temp/`; retain only bounded verified evidence afterward, not credentials, arbitrary tool dumps or physical query rows.
- `accepted_digest`, server fingerprint and validation `candidate_digest` identify different representations. Do not compare them as interchangeable values. The receipt links approved local content to its Stage result.

Task progress remains flexible prose. It cannot authorize a write or replace a validation result, operation checkpoint or receipt.

## Workflow-specific bindings

Field authoring belongs in [Project Change Sets](project/change-sets.md) and the Metadata table guides; this procedure owns review and submission.

| Work | Required binding |
|---|---|
| Metadata | Owning Tenant and Metadata draft revision. No invented Tenant-wide metadata revision. |
| Project | Project identity, applied Project revision and Project draft revision. Recheck the applied revision before handoff. |
| Project-owned enrichment | Project Change Set; preserve the selected applied Input Scope and current Project revision. Reuse pending findings locally before submission. |
| Mixed Metadata/Project work | Separate drafts and Applies ordered by dependencies; no combined atomic Apply. |
| Several Metadata owners | Same workspace, [separate owner roots](workspace-contract.md#project-derived-metadata-owners), authorization, drafts and approval bindings. Resolve owner on each helper call. |

## Extension readiness

Install the matching Stage Runner VSIX for VS Code Copilot in a trusted workspace. It exposes `atlas_checkStageRunner` and `atlas_stageApprovedManifest`. The approved files must be inside the current workspace. Follow [Copilot - VS Code setup](../docs/copilot-vs-code-installation-and-setup.md). If a tool is missing, retain local work and repair setup; never paste payloads into another tool.

`atlas_checkStageRunner` exposes the same read-only check as **Atlas: Check Stage Runner** (`atlasStageRunner.check`). It returns readiness and safe backend identity directly. MCP and extension connections must target the intended matching backend. Microsoft tokens stay in VS Code. If authentication expires, ask the user to run **Atlas: Check Stage Runner** and complete sign-in. Never copy credentials or replay writes after disconnection; inspect the saved operation and server status. SQL environment is separate from the connection profile. Use the supported sign-in flow; never copy tokens or credentials.

Preserve any host Stage confirmation. It does not replace content acknowledgement or separate Apply approval. Atlas Local Workbench has no Stage/Apply buttons in this release.

## Resume, failure and recovery

- Resume a matching task-bound checkpoint; a new turn/task does not require restaging. Content, scope or revision differences require reconciliation and the review appropriate to the changes. Never clear a conflicting draft silently.
- If Stage is uncertain, invoke the same tool with `recoverOnly:true`. It performs reads, compares the saved intended dataset counts/hashes and verifies the current fingerprint. Exact proof restores the receipt; partial/different content or missing prior intent stays uncertain. Do not retry writes or use another transport blindly.
- On server `valid=false`, recording validation preserves the failed revision/digest. Repair, validate, review and accept again; the new operation inherits the failed draft for supported restaging. Repeat server validation and obtain new Apply approval afterward.
- When a governed MCP call fails, run `next --area <area> --error <code>` with the code that follows the tool name in the error text, and follow its one recovery action. It says stop for codes it does not know; never retry blindly.
- Unknown Apply outcomes require authoritative status inspection before retrying. A confirmed Apply can still be recorded after subsequent local edits; refresh removes only proposals matching confirmed applied records.
- Missing helpers, review surface or host capability leave local work intact. Report the missing capability without inventing a successful receipt or alternate submission path.

Governed operations use the `metadata` or `project` family: `create_*_change_set`, `get_*_change_set`, `get_*_change_set_fingerprint`, `validate_*_change_set`, and `apply_*_change_set`. Validate and Apply require `expected_draft_revision`; Apply also requires the approved `expected_candidate_digest`. Stage upload tools (`stage_*`, `begin_*`, `put_*`, `commit_*`) are hidden from agent connections and refused with `stage_runner_required`; only the Stage Runner uses them.
