---
name: gds
description: Run the strict GDS Workbench workflow for metadata, model, mapping, Databricks code, validation, snapshots, and Change Sets. Use when the user says initialize GDS, start GDS, initialize GDS Workbench, start GDS Workbench, GDS Workbench, asks to resume GDS work, or requests governed GDS changes.
---

# GDS router

Plan mutations.

## Start or resume

Pure explanations must answer directly; do not create or resume a session.

1. For session work, load `references/platform-lifecycle.md`, then establish directory, Tenant Code,
   and session via `references/session.md`.
2. Ask for one or more focus areas: Metadata, Model, Code, QA, Validation, or Ad Hoc.
3. Infer obvious areas; ask only when blocked.
4. For predefined Model work, select exactly one workflow target from `references/workflow-targets.md`. Assertion preparation is the one pre-process, non-target Model exception.
5. Unless resume proof is reusable, run `readiness` once for a known target, without `inspect`. For
   generic Metadata mutation or assertion preparation, run one `inspect` per area. Record plan inputs.
6. Before first write, load `references/change-sets.md` and `references/local-helper.md`.
7. Before first server mutation, call `get_server_contract`, pass its exact result to local
   `contract-check`, and stop on incompatibility. Run once per resumed work period.
8. Load only the active-target reference. Never preload every workflow.

`Open Workbench` is local after the session folder is known.

## Choose the path

- **Quick / Ad Hoc**: explanations bypass setup. Local inspection needs a session, not a task. Mark stale Snapshot results unverified. Create a task if work becomes mutation.
- **Guided Build**: predefined workflow with a human review checkpoint.
- **Automatic Build**: predefined complete coverage, compact batches, and review after each selected section.
- **Custom Build**: fallback outside predefined paths; every gate still applies.

Infer Custom + Selected for a specific bounded ask unless the user requests another mode/scope.

Mutation requires a task/plan; keep one Model per session.

Before live-data use, if `status.sql_policy` is absent, ask and persist via `sql-policy`: `never`,
`essential`, or `as_needed`. Reuse until changed. `never` uses Snapshots; `essential` queries
only blocking gaps; `as_needed` permits bounded useful evidence. Use only
`execute_databricks_sql`, combine reads, and never run generated transformations. QA may be
sample-verified; Apply never executes queries.

## Context rule

Do not load an entire Snapshot. Use compact contracts, the local catalog, and selected records.
Snapshots are immutable; write only complete pending records to the matching local Change Set.

First area mutation needs a newly downloaded, unzipped Snapshot. Reuse until Apply marks it stale.
Never infer freshness from file times.

Local authority remains unchanged. `Application Prompt` and `Workflow Run` surfaces are out of scope; never discover, call, or depend on them.

## Mandatory gates

For mutating work follow:

1. One target `readiness`, or one `inspect` per area for non-target mutation.
2. Build/update the ordered plan from discussion and compact evidence.
3. Edit the local Change Set.
4. Human review in conversation or Workbench. After explicit approval, run `approve-reviewed` for pending Model statuses; never infer approval.
5. Local validation. A local override is digest-bound and never overrides server validation.
6. Stage or resume the one governed server draft.
7. Server Validate.
8. Apply.
9. Mark only the applied area stale, update the task, stop, and show eligible targets.

Never Stage, Apply, archive, deploy, execute generated code, or mutate a server from Workbench. Never cross an Apply boundary automatically.

## References

- Session, queue, freshness: `references/session.md`
- Platform lifecycle and default orchestration: `references/platform-lifecycle.md`
- Focus-area behavior: `references/focus-areas.md`
- Local Change Sets and reconciliation: `references/change-sets.md`
- Local helper commands: `references/local-helper.md`
- Governed handoff, loaded only at accepted Stage or an upstream archive boundary: `references/server-handoff.md`
- Workflow target router: `references/workflow-targets.md`
- Workbench behavior: `references/workbench.md`
- Target-specific rules: `references/workflows/`
