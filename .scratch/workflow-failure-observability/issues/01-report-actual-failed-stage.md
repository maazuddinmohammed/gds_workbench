# Report the actual failed workflow stage

Status: needs-triage

## Problem

The run failure panel labels the most recent failed/blocked event as **Last stage**.
A later terminal `workflow_run` event can replace the useful agent-stage event.
Its attempt is the highest persisted progress attempt, which may differ from the
attempt executing when the failure occurred.

Verified in the current source on 2026-09-28:

- `web_app/frontend/src/features/workflows/WorkflowRunMonitor.tsx:491` reverses
  events and takes the first failed/blocked event. Lines 526–531 display its stage
  and attempt without distinguishing terminal summaries.
- `application.fail_workflow_run` in `database/13_application_workflow_runs.sql`
  appends a terminal `workflow_run` event. The existing failure code/message remain
  useful; this issue concerns stage/attempt precision.

## Suggested acceptance

- With a specific stage failure followed by a terminal run failure, show the
  specific stage and its evidenced attempt.
- When only the terminal event exists, display an honest summary/unknown state;
  do not infer an exact failing stage or attempt.
- Preserve safe public error codes/messages, correlation reference, and event
  history. Never add provider bodies, prompts, credentials, or raw SDK errors.
- Add a focused regression with ordered stage and terminal events. If exact
  attribution needs backend changes, define the stored contract before changing
  the label.

## Comments

Preserved from the completed September 21 failure audit during cleanup. No fix
was implemented in this cleanup. General verification limits are retained in
[verification-limits.md](../verification-limits.md).
