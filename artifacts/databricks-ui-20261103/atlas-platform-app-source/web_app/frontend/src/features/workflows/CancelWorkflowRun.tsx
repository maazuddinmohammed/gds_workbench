import { useMutation } from "@tanstack/react-query";

import { ApiError } from "../../core/http";
import type { WorkflowRunRecord, WorkflowsApi } from "./api";
import { isActiveRun } from "./presentation";

export function CancelWorkflowRun({ api, tenantId, projectId, run, hasTenantLock, onCancelled }: {
  api: Pick<WorkflowsApi, "cancelWorkflowRun">;
  tenantId: number;
  projectId: number;
  run: WorkflowRunRecord;
  hasTenantLock: boolean;
  onCancelled: () => Promise<unknown>;
}) {
  const cancellation = useMutation({
    mutationFn: () => api.cancelWorkflowRun(tenantId, projectId, run.workflow_run_id),
    onSuccess: onCancelled,
  });
  if (!isActiveRun(run)) return null;
  const errorCode = cancellation.error instanceof ApiError ? cancellation.error.code : null;
  return <div className="workflow-cancel-action">
    <button className="button button-secondary button-small" type="button"
      disabled={!hasTenantLock || cancellation.isPending || cancellation.isSuccess}
      title={hasTenantLock ? undefined : "Tenant Lock required"}
      onClick={() => { if (hasTenantLock) cancellation.mutate(); }}>
      {cancellation.isPending ? "Cancelling…" : cancellation.isSuccess ? "Cancelled" : "Cancel run"}
    </button>
    {cancellation.isError ? <p className="inline-error" role="alert">
      {errorCode === "workflow_run_cancellation_conflict"
        ? "This run has already finished or saved its result. Refresh to see its outcome."
        : errorCode === "authorization_denied"
          ? "Only the run owner can cancel this run."
          : errorCode === "tenant_lock_required" || errorCode === "tenant_locked"
            ? "Acquire the Tenant Lock before cancelling."
            : "Cancellation could not be confirmed. Refresh or retry."}
    </p> : null}
  </div>;
}
