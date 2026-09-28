import { ApiError } from "../../core/http";
import type { WorkflowRunEvent, WorkflowRunRecord } from "./api";

export const TENANT_WORKFLOW_CONFLICT_MESSAGE = (
  "Another Workflow Run is already active for this Tenant. "
  + "This run remains queued; retry after the active run finishes."
);

export function isTenantWorkflowConflict(error: unknown): boolean {
  return error instanceof ApiError && error.code === "tenant_workflow_conflict";
}

export function isPartialMappingRun(run: WorkflowRunRecord | undefined): boolean {
  return run?.model_workflow === "mapping"
    && (run.workflow_run_state === "completed" || run.workflow_run_state === "completed_with_repair")
    && ((run.mapping_outcome?.failed_pair_count ?? 0) > 0
      || (run.mapping_outcome?.partial_pair_count ?? 0) > 0);
}

export function RunStateBadge({ state, partial = false }: {
  state: WorkflowRunRecord["workflow_run_state"];
  partial?: boolean;
}) {
  const tone = partial ? "is-warning" : state === "completed" || state === "completed_with_repair"
    ? "is-success"
    : state === "failed"
      ? "is-danger"
      : "is-warning";
  return <span className={`status-badge ${tone}`}>{partial ? "Partial results" : runStateLabel(state)}</span>;
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

export function workflowStageLabel(stage: string): string {
  return stage
    .replaceAll("_", " ")
    .replaceAll(".", " · ")
    .replace(/^./, (character) => character.toLocaleUpperCase());
}

export function WorkflowEventProgress({ event }: { event: WorkflowRunEvent }) {
  // Pair outcomes identify frozen selection positions, not execution progress.
  if (["mapping.pair_completed", "mapping.pair_preserved", "mapping.pair_no_source",
    "mapping.pair_failed", "mapping.pair_partial", "mapping.pair_empty"].includes(event.stage)) return null;
  if (event.current === null || event.total === null || event.total < 1) return null;
  const label = workflowStageLabel(event.stage);
  return (
    <progress
      className="workflow-event-progress"
      aria-label={`${label} progress: ${event.current} of ${event.total}`}
      max={event.total}
      value={event.current}
    />
  );
}
