---
name: gds
description: Run the strict GDS Workbench workflow for metadata, model, mapping, Databricks code, validation, snapshots, and Change Sets. Use when the user says initialize GDS, start GDS, initialize GDS Workbench, start GDS Workbench, GDS Workbench, asks to resume GDS work, or requests governed GDS changes.
---

# GDS router

Be concise. Plan before mutation.

## Start or resume

Pure explanations must answer directly; do not create or resume a session.

1. For local work, establish directory, Tenant Code, and session via `references/session.md`.
2. Ask for one or more focus areas: Metadata, Model, Code, Validation, or Ad Hoc.
3. Infer obvious areas; ask only for missing decisions.
4. For predefined Model work, select exactly one workflow target from `references/workflow-targets.md`. Assertion preparation is the one pre-process, non-target Model exception.
5. Unless resume proof is reusable, run `readiness` once for a known target and never precede it with `inspect`. For generic Metadata mutation or assertion preparation, run one `inspect` per required area. Record inputs in the plan.
6. Load only the reference for the active target. Do not preload every workflow.

`Open Workbench` is local after the session folder is known.

## Choose the path

- **Quick / Ad Hoc**: explanations bypass setup. Local inspection needs a session, not a task. Mark stale Snapshot results unverified. Create a task if work becomes mutation.
- **Guided Build**: predefined workflow with a human review checkpoint.
- **Automatic Build**: predefined complete coverage, compact batches, and review after each selected section.
- **Custom Build**: fallback outside predefined paths; every gate still applies.

Infer Custom + Selected for a specific bounded ask unless the user requests another mode/scope.

Mutation requires a task/plan. Requests may add tasks. Keep one Model per session.

## Context rule

Do not load an entire Snapshot into model context. Use the local helper for its catalog and selected compact records. Snapshots are immutable; write only complete pending records to the matching local Change Set.

First mutation of an area needs a newly downloaded, unzipped Snapshot. Reuse it until Apply marks that area stale. Never infer freshness from file times.

Local authority remains unchanged. `Application Prompt` and `Workflow Run` surfaces are out of scope; never discover, call, or depend on them.

## Mandatory gates

For mutating work follow:

1. One target `readiness`, or one `inspect` per area for non-target mutation.
2. Build/update the ordered plan from discussion and compact evidence.
3. Edit the local Change Set.
4. Human review in conversation or Workbench.
5. Local validation. An explicit local override is digest-bound and never overrides server validation.
6. Stage or resume the one governed server draft.
7. Server Validate.
8. Apply.
9. Mark only the applied area stale, update the task, stop, and show eligible targets.

Never Stage, Apply, archive, deploy, execute generated code, or mutate a server from Workbench. Never cross an Apply boundary automatically.

## References

- Session, queue, freshness: `references/session.md`
- Focus-area behavior: `references/focus-areas.md`
- Local Change Sets and reconciliation: `references/change-sets.md`
- Local helper commands: `references/local-helper.md`
- Governed handoff, loaded only at accepted Stage or an upstream archive boundary: `references/server-handoff.md`
- Workflow target router: `references/workflow-targets.md`
- Workbench behavior: `references/workbench.md`
- Target-specific rules: `references/workflows/`
