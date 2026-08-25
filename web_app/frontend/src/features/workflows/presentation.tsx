import type { WorkflowRunRecord } from "./api";

export function RunStateBadge({ state }: { state: WorkflowRunRecord["workflow_run_state"] }) {
  const tone = state === "completed" || state === "completed_with_repair"
    ? "is-success"
    : state === "failed"
      ? "is-danger"
      : "is-warning";
  return <span className={`status-badge ${tone}`}>{runStateLabel(state)}</span>;
}

function runStateLabel(state: WorkflowRunRecord["workflow_run_state"]): string {
  const labels: Record<WorkflowRunRecord["workflow_run_state"], string> = {
    queued: "Queued",
    running: "Running",
    completed: "Completed",
    completed_with_repair: "Completed with repair",
    failed: "Failed",
  };
  return labels[state];
}

export function isActiveRun(run: WorkflowRunRecord): boolean {
  return run.workflow_run_state === "queued" || run.workflow_run_state === "running";
}
