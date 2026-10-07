import { ApiError } from "../../core/http";
import { formatDateTime } from "../../shared/presentation";
import type { WorkflowRunEvent, WorkflowRunRecord } from "./api";

export function workflowRunDuration(run: WorkflowRunRecord): string {
  if (!run.started_at) return "Not started";
  if (isActiveRun(run)) return "In progress";
  const elapsed = Date.parse(run.completed_at ?? "") - Date.parse(run.started_at);
  if (!Number.isFinite(elapsed) || elapsed < 0) return "Not recorded";
  if (elapsed > 0 && elapsed < 1000) return "<1s";
  const seconds = Math.floor(elapsed / 1000);
  const hours = Math.floor(seconds / 3600);
  const minutes = Math.floor((seconds % 3600) / 60);
  return [hours ? `${hours}h` : "", hours || minutes ? `${minutes}m` : "", `${seconds % 60}s`]
    .filter(Boolean).join(" ");
}

export function WorkflowRunTiming({ run }: { run: WorkflowRunRecord }) {
  const timestamp = (value: string | null, fallback: string) => {
    const formatted = formatDateTime(value, { year: "numeric", second: "2-digit", timeZoneName: "short" });
    return formatted && value ? <time dateTime={value}>{formatted}</time> : fallback;
  };
  return <dl className="workflow-run-timing" aria-label="Run timing">
    <div><dt>Started</dt><dd>{timestamp(run.started_at, "Not started")}</dd></div>
    <div><dt>Ended</dt><dd>{timestamp(run.completed_at, isActiveRun(run) ? "—" : "Not recorded")}</dd></div>
    <div><dt>Duration</dt><dd>{workflowRunDuration(run)}</dd></div>
  </dl>;
}

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
    : state === "cancelled"
      ? "is-neutral"
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
    cancelled: "Cancelled",
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
