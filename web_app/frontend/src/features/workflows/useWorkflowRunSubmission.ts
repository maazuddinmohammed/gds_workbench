import { useRef, useState } from "react";
import { useMutation } from "@tanstack/react-query";

import type { CreateWorkflowRunCommand, WorkflowsApi } from "./api";

export function useWorkflowRunSubmission({
  api,
  tenantId,
  modelId,
  execute,
  onSuccess,
}: {
  api: Pick<WorkflowsApi, "createWorkflowRun">;
  tenantId: number;
  modelId: number;
  execute?: ((workflowRunId: number, command: CreateWorkflowRunCommand) => Promise<unknown>) | undefined;
  onSuccess: (workflowRunId: number) => Promise<void>;
}) {
  const attemptRef = useRef<{
    fingerprint: string;
    key: string;
    command: CreateWorkflowRunCommand;
    workflowRunId: number | null;
  } | null>(null);
  const [pendingRunId, setPendingRunId] = useState<number | null>(null);
  const mutation = useMutation({
    mutationFn: async (command: CreateWorkflowRunCommand | undefined) => {
      let attempt = attemptRef.current;
      if (!attempt || attempt.workflowRunId === null) {
        if (!command) throw new Error("A Workflow Run command is required before retrying.");
        const fingerprint = JSON.stringify(command);
        if (!attempt || attempt.fingerprint !== fingerprint) {
          attempt = {
            fingerprint,
            key: globalThis.crypto.randomUUID(),
            command: structuredClone(command),
            workflowRunId: null,
          };
          attemptRef.current = attempt;
        }
        const result = await api.createWorkflowRun(tenantId, modelId, attempt.command, attempt.key);
        attempt.workflowRunId = result.workflow_run_id;
        if (execute) setPendingRunId(result.workflow_run_id);
      }
      await execute?.(attempt.workflowRunId, attempt.command);
      return attempt.workflowRunId;
    },
    onSuccess: (workflowRunId) => onSuccess(workflowRunId),
  });

  return { mutation, pendingRunId };
}
