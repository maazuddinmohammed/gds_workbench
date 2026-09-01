---
name: gds
description: Run strict GDS Workbench workflows for metadata, models, mappings, code, QA, Snapshots, and Change Sets. Use to initialize GDS Workbench, resume work, or request governed changes.
---

# GDS router

## Start or resume

Pure explanations must answer directly; do not create a session.

1. For session work, establish directory, Tenant Code, and state through `references/session.md`.
   On resume run `status` once and continue its current/resume task.
2. Infer focus, target, mode, and scope; ask only for a blocker.
   Every mutating mode creates its target task before work and starts the first task immediately.
   For an end-to-end Automatic request, load `references/automatic-journey.md`, ask one compact
   intake, and queue the requested targets. Otherwise select one target from
   `references/workflow-targets.md`.
3. For predefined Model work, select its target; run `readiness` once for a known target without `inspect`,
   unless resume proof is reusable. Mapping/Code collect proof then run final readiness. For
   generic Metadata mutation or assertion preparation, use one `inspect` per area.
4. Before a dataset's first write, load `references/change-sets.md` and `references/local-helper.md`,
   then its compact contract. Load contracts lazily, never for future datasets.
5. Before server mutation, call `get_server_contract` once; pass its exact result to local
   `contract-check`. Incompatibility stops.
6. Load only the active-target reference. Never preload every workflow. Load platform lifecycle
   detail only for an Automatic journey, Target Registration, Code, or QA.

`Open Workbench` is local after the session folder is known.

Do not load an entire Snapshot. Use bounded reads. Local authority remains unchanged.
`Application Prompt` and `Workflow Run` surfaces are out of scope; never discover, call, or depend on them.
Session Tenant Code is never a physical Object key default. Model ownership does not own or rewrite physical Object identity.
Copy physical keys from authoritative records; never synthesize them.

## Modes

- **Quick / Ad Hoc**: bounded read/explanation; mutation creates a task.
- **Guided Build**: selected human checkpoints.
- **Automatic Build**: complete coverage, internal checkpoints without human pauses, one final local review.
- **Custom Build**: bounded exception path; all gates still apply.

Infer Custom + Selected for a specific bounded ask. Keep one Model per session.

Before live-data use, ask once for `never`, `essential`, or `as_needed`; persist `sql-policy`.
Only use `execute_databricks_sql`; combine reads and never run generated transformations. Declining
SQL never blocks Snapshot-based authoring.

## Review meanings

Task `review` is not record `needs_review`; it means local bytes await acceptance. Write supported
records `active`. Use `needs_review` only for a complete, supportable
proposal with one unresolved semantic decision; missing grain, lineage, keys, or conflicts are
blockers instead. Never blanket-mark agent-generated records `needs_review`.

## One target boundary

1. Complete all selected scope/sections. Automatic checkpoints update coverage and continue.
2. Run one final local review and validation. Show digest, actions, blockers, and `needs_review`.
3. Ask once whether to approve that digest, promote reviewed statuses, acquire an unowned Tenant Lock,
   and proceed through Stage plus server Validate. On approval call `approve-reviewed` at most once, use its
   promoted digest, then `validate` and `accept`; do not ask for the same review again. Re-ask only
   if non-status content changes.
4. Check/acquire the Tenant Lock, reconcile, and Stage. Review changed actions/content; never duplicate approval.
5. Server Validate, show authoritative `action_review`, and obtain fresh Apply approval.
6. Apply once, mark that area stale, release a lock acquired here, and stop. Show the exact next
   queued/eligible target and ask one continue question; if none, report completion. Never cross an Apply boundary automatically.

Workbench never calls MCP, Stages, Applies, archives, deploys, or executes generated code.

## References

- Lifecycle/session/targets: `references/automatic-journey.md`, `references/session.md`, `references/workflow-targets.md`
- Local records: `references/change-sets.md`, `references/local-helper.md`
- Server handoff: `references/server-handoff.md`
- Other rules: `references/focus-areas.md`, `references/workbench.md`, `references/workflows/`
