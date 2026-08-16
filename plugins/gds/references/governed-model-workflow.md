# Governed Model workflow

Use this sequence for the full governed Model Change Set: Model details/scope,
profiling, analysis, Modeling Assertions, Conceptual, Logical, Dimensional, and Model
Mapping changes.
Read [model-tools.md](model-tools.md) and [model-datasets.md](model-datasets.md)
before the first write.

## 1. Establish scope without writing

1. Use `list_tenants` only when the Tenant is not already unambiguous.
2. Call `get_model(tenant_id)`. Select an existing Model; no public tool creates one.
3. Record the selected Tenant, Model ID/name/revision, objective, requested layers,
   owner, sources, assumptions, exclusions, and acceptance checks.
4. Read current naming templates. Ask whether to preserve them, adopt them for this
   work, or stage a full replacement. Preview sample names before recording a choice.
5. Read `get_model_scope` and only the focused model, catalog, profiling, analysis,
   assertion, and mapping records needed. Page until complete or report truncation.
6. For a broad baseline, obtain one fresh `get_model_snapshot`. Keep its temporary
   URL out of logs and copied chat. Use `get_model_dbml` when a diagram review helps.
7. Call `describe_model_dataset` for every dataset that may be staged. Draft only
   exact, complete, ID-free records. Preserve source evidence and decision links.

Classify all eight sections as current, proposed, not needed, or blocked. Supporting
records are governed data, not filler:

- change `model_details` only from an explicit naming/template decision;
- stage `model_scope` only through the governed Change Set when the exact visible
  physical Object boundary is authorized; never use direct scope mutation;
- create `profiling_profile` only from measured, attributable statistics whose counts
  and percentages satisfy the live contract;
- create `analysis_result` only from an attributable relationship evaluation with its
  real policy version, result, counts, confidence, basis, and lock state;
- pair each `modeling_assertion_record` with its document/provenance, stable key, exact
  applicable layers, and confidence; track its evidence/decision owner only in the
  authorized decision or progress log because Assertion records have no owner field;
  and
- keep layer records and mappings traceable to those physical or Assertion sources.

Never turn an interview answer into fabricated profiling counts or a supposedly
executed analysis result. Mark the dataset blocked with an owner when evidence is not
available.

Do not acquire a lock while eliciting requirements, reading, drafting, previewing,
or running local checks.

## 2. Review the proposal

Show the user:

- model type, business scope, and explicit grain where applicable;
- current versus proposed names and templates;
- affected datasets and complete pending record counts;
- source lineage, unresolved assumptions, and decisions;
- local schema, duplicate, and available per-record semantic warnings;
- expected insert/update/deactivate/reactivate effects; and
- which checks only the server can perform, including future-graph scope, locks, and
  cross-dataset references.

Resolve `no_change` proposals and unintended key changes. A canonical-key change is
an insert, not a rename. Do not claim a proposed local JSON file is applied or an
authoritative Snapshot.

## 3. Enter the governed write window

1. Call `check_tenant_lock`.
2. Ask the user before acquiring the Tenant Lock. If another Principal owns it, stop;
   do not override unless the user explicitly requests and approves that separate
   governed operation.
3. Acquire the lock with a bounded purpose and duration.
4. Re-read `get_model` after lock acquisition and compare its Model revision with the
   reviewed local Snapshot/baseline. If it changed, release the lock, refresh/rebase
   the proposal, and repeat review; do not create or Stage from the stale baseline.
5. Call `create_model_change_set(model_id)`. A successful call may resume an existing
   draft.
6. If resumed, call `get_model_change_set` for counts and then every nonempty pending
   dataset. Reconcile those records with the local proposal before staging. Never
   overwrite unseen pending work.
7. Present the exact Stage batch and obtain approval for this server write.
8. Call one `stage_model_change_set` with the latest `draft_revision` and all approved
   dataset replacements. Each list contains every intended pending action for that
   dataset, not every applied record; omitted applied records remain. Keep each
   accumulated pending dataset complete and record the returned revision immediately.

If the lock may expire during review, renew it before the next write. Do not silently
reacquire or extend locks.

## 4. Validate and repair

Call `validate_model_change_set` with the latest revision. Repair the first failed
phase, restage the complete affected pending datasets, record the new revision, and
validate again. Do not bypass or reinterpret server errors.

When valid, present the authoritative `action_review`, candidate digest, exact draft
revision, affected natural keys, and any truncation. Validation is not approval.

## 5. Apply only after a fresh decision

Ask one explicit final question identifying the validated Model Change Set and its
effects. Only an affirmative answer to that question authorizes
`apply_model_change_set`. Never treat earlier design, lock, create, Stage, or Validate
approval as Apply approval.

After Apply:

1. Verify with fresh focused reads and, when useful, a fresh Snapshot/DBML artifact.
2. Confirm the returned Model revision and effective records.
3. Release the Tenant Lock.
4. Update the decision/progress record with verified outcomes, not raw tool dumps.

For an abandoned draft, confirm intent and call `archive_model_change_set`; this
retains history and does not delete applied model records. Release an owned lock.
When stopping at a validated draft, or pausing/abandoning after this workflow acquired
the lock, release the caller-owned lock when safe and report any release failure.

## Recovery rules

- Authentication required: pause for client sign-in, then retry only the safe read.
- Authorization denied: stop; never seek a bypass.
- Revision conflict: read the Change Set, reconcile, and rebuild from the latest
  revision. Never resend stale input.
- Ambiguous non-idempotent result: inspect current state before deciding whether any
  retry is safe.
- Invalid record: re-read `describe_model_dataset`; do not remove required nullable
  fields or add guessed fields.
- Scope/reference/lock failure: repair the underlying proposal or ask the user for a
  decision. Do not mutate Model Scope or locked records through any direct tool.
- Required external write, missing business decision, or unavailable evidence: pause
  with the precise blocker and the smallest question needed to continue.

Keep reports compact: current checkpoint, verified evidence, remaining checks, and
blocker status. Never include credentials, temporary URLs, raw prompts, raw physical
rows, or unredacted tool dumps.
