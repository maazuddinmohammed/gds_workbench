# Report the actual failed workflow stage

Status: needs-triage

`WorkflowRunMonitor.tsx` reverses failed/blocked events and displays the newest
event as **Last stage**. A terminal `workflow_run` event from
`application.fail_workflow_run` can hide a more specific stage failure. Rechecked
against current source during cleanup on 2026-09-30; unresolved.

Acceptance:

- Prefer the evidenced stage failure when followed by a terminal run summary.
- If only a terminal event exists, show an honest summary or unknown stage/attempt.
- Preserve safe error codes, correlation reference and event history.
- Cover ordered stage/terminal events without exposing provider bodies or secrets.

Sources: `web_app/frontend/src/features/workflows/WorkflowRunMonitor.tsx` and
`database/13_application_workflow_runs.sql`.
