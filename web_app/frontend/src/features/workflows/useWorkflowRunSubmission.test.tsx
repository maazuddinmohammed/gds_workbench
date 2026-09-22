import type { ReactNode } from "react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, renderHook, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { ApiError } from "../../core/http";
import type { CreateWorkflowRunCommand, WorkflowRunCommandResult, WorkflowsApi } from "./api";
import { useWorkflowRunSubmission } from "./useWorkflowRunSubmission";

const command: CreateWorkflowRunCommand = {
  expected_model_revision: 18,
  model_workflow: "mapping",
  workflow_execution_mode: "tool_assisted",
  selected_object_ids: [701],
  requested_batch_id: null,
  agent: null,
  prompt_overrides: {},
};
const created: WorkflowRunCommandResult = {
  created: true,
  workflow_run_id: 1150,
  workflow_run_state: "queued",
  correlation_id: "fixture-correlation",
  prompt_snapshot_count: 1,
  created_at: "2026-09-21T12:00:00Z",
};

describe("Workflow Run submission", () => {
  it("reuses the key after ambiguous create failures and changes it for an edited command", async () => {
    const createWorkflowRun = vi.fn<WorkflowsApi["createWorkflowRun"]>()
      .mockRejectedValueOnce(new TypeError("Network unavailable"))
      .mockRejectedValueOnce(new ApiError(503, "dependency_unavailable", null))
      .mockResolvedValue(created);
    const execute = vi.fn(async () => undefined);
    const onSuccess = vi.fn(async () => undefined);
    const { result } = mount({ api: { createWorkflowRun }, tenantId: 7, modelId: 18, execute, onSuccess });

    for (let attempt = 0; attempt < 2; attempt += 1) {
      await act(async () => {
        await expect(result.current.mutation.mutateAsync(structuredClone(command))).rejects.toThrow();
      });
    }
    expect(createWorkflowRun.mock.calls[1]).toEqual(createWorkflowRun.mock.calls[0]);
    expect(execute).not.toHaveBeenCalled();
    expect(onSuccess).not.toHaveBeenCalled();
    expect(result.current.pendingRunId).toBeNull();

    const edited = { ...command, workflow_execution_mode: "one_shot" as const };
    await act(async () => { await result.current.mutation.mutateAsync(edited); });
    expect(createWorkflowRun.mock.calls[2]?.slice(0, 3)).toEqual([7, 18, edited]);
    expect(createWorkflowRun.mock.calls[2]?.[3]).not.toBe(createWorkflowRun.mock.calls[0]?.[3]);
    expect(execute).toHaveBeenCalledExactlyOnceWith(1150, edited);
    expect(onSuccess).toHaveBeenCalledExactlyOnceWith(1150);
  });

  it("retries only start using the original command, mode, and revision after a rerender", async () => {
    const createWorkflowRun = vi.fn<WorkflowsApi["createWorkflowRun"]>().mockResolvedValue(created);
    const execute = vi.fn(async (_id: number, _command: CreateWorkflowRunCommand) => undefined)
      .mockRejectedValueOnce(new ApiError(409, "tenant_workflow_conflict", null));
    const options = { api: { createWorkflowRun }, tenantId: 7, modelId: 18, execute, onSuccess: vi.fn(async () => undefined) };
    const { result, rerender } = mount(options);
    const original = structuredClone(command);
    await act(async () => {
      await expect(result.current.mutation.mutateAsync(original)).rejects.toThrow();
    });
    expect(result.current.pendingRunId).toBe(1150);
    expect(options.onSuccess).not.toHaveBeenCalled();

    original.workflow_execution_mode = "one_shot";
    original.expected_model_revision = 19;
    original.selected_object_ids.push(702);
    const nextExecute = vi.fn(async () => undefined);
    rerender({ ...options, execute: nextExecute });
    await act(async () => { await result.current.mutation.mutateAsync(undefined); });
    expect(createWorkflowRun).toHaveBeenCalledTimes(1);
    expect(createWorkflowRun.mock.calls[0]?.[2]).toEqual(command);
    expect(nextExecute).toHaveBeenCalledExactlyOnceWith(1150, command);
    expect(options.onSuccess).toHaveBeenCalledExactlyOnceWith(1150);
  });

  it("stays pending through create, start, and the awaited success callback before closing", async () => {
    let resolveCreate!: (result: WorkflowRunCommandResult) => void;
    let resolveStart!: () => void;
    let resolveSuccess!: () => void;
    const createGate = new Promise<WorkflowRunCommandResult>((resolve) => { resolveCreate = resolve; });
    const startGate = new Promise<void>((resolve) => { resolveStart = resolve; });
    const successGate = new Promise<void>((resolve) => { resolveSuccess = resolve; });
    const createWorkflowRun = vi.fn<WorkflowsApi["createWorkflowRun"]>().mockReturnValue(createGate);
    const execute = vi.fn(() => startGate);
    const onCreated = vi.fn((_workflowRunId: number) => successGate);
    const close = vi.fn();
    const { result } = mount({
      api: { createWorkflowRun }, tenantId: 7, modelId: 18, execute,
      onSuccess: async (id) => { await onCreated(id); close(); },
    });
    act(() => result.current.mutation.mutate(command));
    await waitFor(() => expect(result.current.mutation.isPending).toBe(true));
    expect(result.current.pendingRunId).toBeNull();
    expect(execute).not.toHaveBeenCalled();

    await act(async () => resolveCreate(created));
    await waitFor(() => expect(result.current.pendingRunId).toBe(1150));
    expect(result.current.mutation.isPending).toBe(true);
    expect(onCreated).not.toHaveBeenCalled();
    await act(async () => resolveStart());
    await waitFor(() => expect(onCreated).toHaveBeenCalledExactlyOnceWith(1150));
    expect(result.current.mutation.isPending).toBe(true);
    expect(close).not.toHaveBeenCalled();
    await act(async () => resolveSuccess());
    await waitFor(() => expect(result.current.mutation.isSuccess).toBe(true));
    expect(close).toHaveBeenCalledOnce();
  });

  it("preserves create-only callers without reporting a pending start", async () => {
    const createWorkflowRun = vi.fn<WorkflowsApi["createWorkflowRun"]>().mockResolvedValue(created);
    const onSuccess = vi.fn(async () => undefined);
    const { result } = mount({ api: { createWorkflowRun }, tenantId: 7, modelId: 18, onSuccess });
    await act(async () => { await result.current.mutation.mutateAsync(command); });
    expect(createWorkflowRun).toHaveBeenCalledOnce();
    expect(result.current.pendingRunId).toBeNull();
    expect(onSuccess).toHaveBeenCalledExactlyOnceWith(1150);
  });
});

function mount(options: Parameters<typeof useWorkflowRunSubmission>[0]) {
  const client = new QueryClient({ defaultOptions: { mutations: { retry: false } } });
  return renderHook(useWorkflowRunSubmission, {
    initialProps: options,
    wrapper: ({ children }: { children: ReactNode }) => (
      <QueryClientProvider client={client}>{children}</QueryClientProvider>
    ),
  });
}
