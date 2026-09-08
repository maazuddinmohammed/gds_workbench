# Deterministic staging

Use after `server-handoff.md` prerequisites: validation, digest acceptance, lock/revision checks, and an active task-bound `draft-cache`.

## Preferred path

1. Run `prepare-stage-request --session <session> --area metadata|model` once.
2. The helper returns `manifest` and `accepted_digest`. Invoke `gds_stageApprovedManifest` with exactly:

   ```js
   {manifestPath: result.manifest, expectedDigest: result.accepted_digest}
   ```

   `result` is the helper result; verify its digest equals the user's accepted digest. No payload argument exists.
3. Do not open, parse, quote, or pass any payload file through the agent. Do not fetch pending rows.

One request targets one area and every dataset currently present; areas never mix.

The extension verifies containment, bindings, hashes, counts, IDs, limits, and digest. It privately reconciles affected server data, runs allowlisted Stage tools, carries revisions, and verifies the fingerprint. Present datasets fully replace pending data. Payloads/subcall responses never enter model context.

On `status=staged` and `fingerprintVerified=true`, persist only `{area, changeSetId, resultingRevision, acceptedDigest, stageFingerprint}` from the receipt to `tasks/<ID>.stage-proof.json`. This is a sanitized checkpoint, never raw tool output. `draft-cache` stores ID/revision/status but **not** the fingerprint; do not invent a flag. Cache the resulting revision, mark staged, then validate server-side.

Server normalization makes local digest and fingerprint differ. The receipt binds `acceptedDigest -> Change Set ID -> resultingRevision -> stageFingerprint`. Before resume/Apply, compare local digest, area and cached ID/revision with the checkpoint. Its filename identifies the task; session/Snapshot identify Tenant/Model scope. Compare that scope and checkpoint ID/revision/fingerprint with authoritative `get_metadata_change_set_fingerprint` or `get_model_change_set_fingerprint`. Require server `active` before validation and `validated` before Apply. Validation may change status, not the staged content. Missing checkpoint or changed revision/fingerprint stops Apply: summary reads can establish server state but cannot reconstruct proof of the earlier accepted bytes. Do not bless current server content as previously acknowledged.

Validation returns `error_count`, groups, at most 25 bounded examples, and bounded actions—not records. If invalid, cache with `draft-cache --validation-failed true`; repair, validate, re-acknowledge, and Stage. Only that task-bound failed draft may be replaced.

## Failure and authentication

- If the Stage tool is absent, have the user enable/install the packaged Stage Runner and resume; absence is not a failure receipt.
- Production may prompt for VS Code Microsoft sign-in/consent. Never handle its token.
- `stageStarted=false` plus `legacyFallbackAllowed=true` proves no Stage write. Correct the reported failure before retrying the runner; these flags do not authorize bypassing approval, authentication, or payload verification.
- If `stageStarted=true`, stop. Never use legacy fallback, blindly retry, Apply, discard, or invent cleanup. Read only the Change Set summary/fingerprint to establish the resulting revision and escalate the unresolved outcome to the user.
- Conflicts, changed/foreign state, lock/identity mismatch, malformed responses, and hash mismatch fail closed.

## Legacy helpers

`prepare-stage` remains a compatibility capability for an explicitly requested Custom/manual handoff. It does not produce the runner's verified receipt. Do not switch to it automatically or pass payload rows through context to work around a missing runner. Stop normal handoff until the runner works; a manual path must independently establish exact accepted-content verification before Apply. Never fabricate that proof from a fresh server fingerprint.

Never stage record-wise, repack, recalculate hashes, or invent revisions. Limits: Metadata 450 KiB/5,000 records; Model 1 MiB/5,000; 64 chunks.
