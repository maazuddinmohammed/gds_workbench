# Governed Model workflow

Use this reference only when the user requests a server Model Change Set, Stage,
Validate, Apply, or Archive. Inspection, proposals, and local drafts stop before this workflow.
Read [model-tools.md](model-tools.md) or [model-datasets.md](model-datasets.md) only
around an unfamiliar tool or affected dataset.

## Route intent

- Inspect: focused reads, answer, stop.
- Proposal: compact checked design/diff, no write, stop.
- Local draft: write only `GDS/model-change-set`; no MCP mutation or lock, stop.
- Server draft: lock, create/resume, Stage, and Validate only to the requested boundary.
- Apply: use the validated revision only after a fresh explicit approval.
- Archive: inspect the exact owned draft and revision, confirm, archive without a lock,
  and stop.

A lower boundary never implies a higher one. Do not re-ask the boundary when the user's
verbs make it clear.

## Read the minimum baseline

1. Use `list_tenants` only when the Tenant is ambiguous.
2. Call `get_model` when Model identity, revision, or policy is needed. No public tool
   creates a Model.
3. Preserve current naming templates and established names by default. Read or author
   `model_details` only for an explicit naming/template request.
4. Read requested records and direct dependencies only. A read dependency is not an
   affected dataset.
5. Call `describe_model_dataset` only for datasets whose records will be authored.
6. Use a broad `get_model_snapshot` or `get_model_dbml` only when the user requests it
   or several affected layers genuinely require that baseline. Never repeat, log, or
   store a temporary `download_url`.

Do not turn interviews or assumptions into fabricated profiling counts, analysis
results, Assertions, sources, or mappings. Record uncertainty and the smallest owner
or decision needed.

## Proposal and local draft

Keep the Model Snapshot immutable. Put complete, ID-free pending records only in the
local Model Change Set. Preserve existing pending records and use natural keys. A key
change inserts a new record; it is not a rename. A copied unchanged record is temporary
working state and must be edited or removed before handoff.

Do not acquire a Tenant Lock while reading, designing, drafting, or checking local
files. Do not describe local files as Staged, server-validated, Applied, or an
authoritative Snapshot.

Review only affected work: dataset/count, intended effect, canonical-key changes,
material assumptions/conflicts, and checks deferred to server validation.

## Enter the governed write window

For archive-only intent, call `get_model_change_set`, confirm the exact draft and latest
revision, then call `archive_model_change_set` without acquiring a Tenant Lock. If this
workflow already owns a lock, release it when safe. Stop. The steps below apply only to
Create, Stage, Validate, or Apply.

1. Call `check_tenant_lock`.
2. Ask before acquiring the Tenant Lock. Stop on another owner's lock; override only
   after explicit user direction, reason, and approval. Override releases the old lock
   and never acquires a new one.
3. Acquire with a bounded purpose/duration.
4. Re-read `get_model` and compare its revision with the reviewed baseline. On drift,
   release the lock, rebase, and repeat review before creating or staging anything.
5. Call `create_model_change_set`. It may resume the caller's existing draft.
6. When resumed, call `get_model_change_set` for counts and read every nonempty pending
   dataset, including unrelated pending work. Reconcile it locally so unseen work is
   never overwritten.
7. Present the exact affected Stage batch and obtain approval for that server write.
8. Call one `stage_model_change_set` with the latest `draft_revision` and approved
   affected dataset replacements. Each supplied list is the complete accumulated
   pending action list for that dataset. Omitted pending datasets remain unchanged.
   Record the returned revision immediately.

Renew an owned lock before the next write when needed. Never silently reacquire,
extend, or override it.

## Validate and repair

Call `validate_model_change_set` with the latest revision. Repair the first failed
phase, restage the complete affected pending lists, record the new revision, and
validate again. Never bypass or reinterpret server errors.

When valid, show the authoritative `action_review`, candidate digest, revision,
affected natural keys, validation warnings, and truncation. Validation and Stage
approval are not Apply approval.

## Apply after a fresh decision

Ask one explicit final question identifying the validated Model Change Set revision
and effects. Only that affirmative answer authorizes `apply_model_change_set`.

After Apply, verify with fresh focused reads and, only when useful, DBML or a fresh
Snapshot. Report the resulting Model revision and effective records, release the
Tenant Lock, and record verified outcomes rather than raw tool dumps.

For a validated-draft handoff, abandonment, or terminal pause after this workflow
acquired the lock, release it when safe and report failure. Archive an abandoned draft
instead of deleting it.

## Recovery rules

- Authentication required: pause for sign-in, then retry only the safe read.
- Authorization denied: stop; never seek a bypass.
- Revision conflict: fetch, reconcile, and rebuild from the latest revision. Never
  resend stale input.
- Ambiguous non-idempotent result: inspect current state before any retry.
- Invalid record: re-read only its `describe_model_dataset` contract; do not remove
  required nullable fields or invent properties.
- Scope/reference/lock failure: repair the proposal or ask for one decision. Never use
  individual graph mutation or direct Model Scope/lock-table mutation.
- External write, missing evidence, or missing authority: pause with the precise
  blocker. Never deploy, publish, or write to Azure/Databricks without approval.

Keep reports compact. Never expose credentials, connection values, temporary URLs,
raw prompts, raw physical rows, or unredacted tool output.
