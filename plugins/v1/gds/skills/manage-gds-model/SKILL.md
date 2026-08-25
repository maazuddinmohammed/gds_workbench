---
name: manage-gds-model
description: "Inspect or govern an existing GDS Model and its complete Model Change Set. Use for current Model Scope/evidence/layers, Model Snapshot/DBML, or create/resume/handoff/stage/validate/apply/archive lifecycle work. Route new Profiling, Analysis, Assertion extraction, and layer design to their dedicated skills."
---

# Manage GDS Model

Use governed `gds-workbench` tools only. There is no public Model-create tool or
individual graph mutation. Never expose temporary URLs, credentials, raw physical
rows, prompts, or raw tool output.

## Choose the smallest path

- **Inspect:** use the smallest focused read, answer, and stop.
- **Broad review:** use `get_model_snapshot` or `get_model_dbml` only when several
  layers or a requested export require it; answer and stop.
- **Local draft:** use `$open-gds-metadata-workbench` to edit only
  `GDS/model-change-set`. Keep the Snapshot immutable; do not lock, create a server
  draft, Stage, Validate, or Apply.
- **Server draft:** inspect an existing draft with `get_model_change_set` and stop.
  Enter the governed write window only for explicit create/resume, Stage, Validate,
  Apply, or server handoff intent. Archive-only work needs no lock.
- **Apply:** show the authoritative review and obtain fresh approval immediately before
  `apply_model_change_set`.

Do not re-ask a clear boundary or advance beyond it. Ask only for a missing choice that
changes records or the stopping boundary.

## Route reads and authored datasets

- Use `list_tenants` only when the Tenant needed for Model discovery is ambiguous.
- Use `get_model` for identity, revision, `model_details`, and naming templates.
- Use `get_model_scope` for current `model_scope` Objects. For a requested scope
  addition, use `list_objects` and then `get_objects` to resolve the exact physical
  candidate before authoring it.
- Use `get_model_profiling` to inspect existing `profiling_profile` records. Route new
  physical table profiling or new Profile evidence to `$profile-gds-data`. Use
  `get_model_analysis` for existing `analysis_result`; route new relationship evidence
  to `$analyze-gds-relationships`.
- Use `get_modeling_assertion_documents` and `get_modeling_assertion_records` for
  existing `modeling_assertion_document` and `modeling_assertion_record`; route new
  document/text extraction to `$capture-modeling-assertions`.
- Use the Conceptual, Logical, Dimensional, or Mapping builder for those layers. Their
  focused read tools are listed in [model tools](../../references/model-tools.md).

Call `describe_model_dataset` only for a dataset being authored; its live result is
the record contract. Read only its direct dependencies. Preserve current templates
and established names unless the user explicitly requests a change.
Follow a returned `next_cursor` unchanged only until the requested scope is complete.

## Govern a server Change Set

Read [governed workflow](../../references/governed-model-workflow.md).
For a saved `GDS/model-change-set`, also use
[local handoff](references/local-handoff.md) to bind, seal the Stage review, and
record returned revisions without losing resumed work.

Then:

1. For read-only server draft inspection, call `get_model_change_set`, answer, and stop
   without acquiring a lock.
2. For archive-only intent, inspect the latest draft revision, confirm the exact draft,
   call `archive_model_change_set` without acquiring a lock, and stop. Release a lock
   already owned by this workflow when safe.
3. Before Create, Stage, Validate, or Apply, call `check_tenant_lock`; ask before
   `acquire_tenant_lock`.
4. Call `create_model_change_set` only for explicit create/resume or when the requested
   Stage operation has no draft. It may resume the caller's draft.
5. If resumed, call `get_model_change_set` for counts and every nonempty pending
   dataset before replacing anything.
6. Show the exact Stage batch and ask before staging. Use `stage_model_change_set` for
   normal-size input. When one dataset exceeds the request limit, prepare chunks with
   `prepare-stage-batch.js`, then call `begin_model_stage_batch`, ordered
   `put_model_stage_chunk`, and `commit_model_stage_batch` at the original revision.
7. Call `validate_model_change_set` at the returned revision. Repair only the first
   failed phase and restage complete affected lists.
8. Show the authoritative `action_review`, warnings, truncation, digest, and revision.
   Validation and Stage approval are not Apply approval.
9. After fresh approval, call `apply_model_change_set` once, verify with focused reads,
   and call `release_tenant_lock`.
10. For abandonment, confirm and call `archive_model_change_set`, then release an owned
   lock when safe. Release a lock this workflow acquired at any requested stopping
   boundary when no immediate governed write follows.

Never retry an ambiguous non-idempotent result. Inspect current state first. Never
overwrite unseen resumed work, fabricate evidence, or use direct SQL for Model writes.

## Report

Normally use at most three bullets and 120 words: outcome, affected datasets/counts,
and blocker or next boundary. Approval reviews and material conflicts may be longer.
