import { useEffect, useMemo, useRef, useState } from "react";
import { useForm } from "@tanstack/react-form";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { getCoreRowModel, useReactTable, type ColumnDef } from "@tanstack/react-table";

import { formatRequiredDateTime as formatDateTime } from "../../shared/presentation";
import { Fact } from "../../shared/ui";
import type { ModelDetail } from "../models/api";
import type {
  WorkflowRunEvent,
  WorkflowRunFilterState,
  WorkflowRunRecord,
} from "../workflows/api";
import {
  isTenantWorkflowConflict,
  RunStateBadge,
  TENANT_WORKFLOW_CONFLICT_MESSAGE,
  WorkflowEventProgress,
} from "../workflows/presentation";
import { profilingQueryKeys, type ProfilingApi } from "./api";
import {
  DrawerHeader,
  WorkflowTable,
  stageLabel,
} from "./shared";
import { useProfilingRunEvents } from "./useProfilingRunEvents";
import { CancelWorkflowRun } from "../workflows/CancelWorkflowRun";
import { WorkflowTokenUsage } from "../workflows/WorkflowTokenUsage";

export function ProfilingRuns({
  compact = false,
  items,
  state,
  isLoading,
  isError,
  selectedRunId,
  onStateChange,
  onShowDetails,
}: {
  compact?: boolean;
  items: WorkflowRunRecord[];
  state: WorkflowRunFilterState;
  isLoading: boolean;
  isError: boolean;
  selectedRunId: number | null;
  onStateChange: (state: WorkflowRunFilterState) => void;
  onShowDetails: (runId: number) => void;
}) {
  const [runIdInput, setRunIdInput] = useState("");
  const runIdNumber = Number(runIdInput);
  const stateForm = useForm({ defaultValues: { state } });
  const columns = useMemo<ColumnDef<WorkflowRunRecord>[]>(() => [
    {
      accessorKey: "workflow_run_id",
      header: "Run",
      cell: ({ getValue }) => <strong>PR-{getValue<number>()}</strong>,
    },
    {
      accessorKey: "workflow_run_state",
      header: "Status",
      cell: ({ getValue }) => (
        <RunStateBadge state={getValue<WorkflowRunRecord["workflow_run_state"]>()} />
      ),
    },
    { accessorKey: "selected_scope_count", header: "Objects" },
    {
      accessorKey: "requested_batch_id",
      header: "Batch ID",
      cell: ({ getValue }) => getValue<string | null>() ?? "Not used",
    },
    { accessorKey: "actor_display_name", header: "Actor" },
    {
      accessorKey: "created_at",
      header: "Created",
      cell: ({ getValue }) => formatDateTime(getValue<string>()),
    },
    {
      id: "actions",
      header: "Actions",
      cell: ({ row }) => (
        <button
          id={`profiling-run-trigger-${row.original.workflow_run_id}`}
          className="text-action"
          type="button"
          aria-label={`Show details for profiling run PR-${row.original.workflow_run_id}`}
          aria-expanded={selectedRunId === row.original.workflow_run_id}
          onClick={() => onShowDetails(row.original.workflow_run_id)}
        >
          Show details
        </button>
      ),
    },
  ], [onShowDetails, selectedRunId]);
  const table = useReactTable({ data: items, columns, getCoreRowModel: getCoreRowModel() });

  return (
    <section className="workflow-surface" aria-label="Profiling run history">
      <div className="workflow-filterbar run-filterbar">
        <stateForm.Field name="state">
          {(field) => (
            <label>
              <span>Run state</span>
              <select
                aria-label="Run state"
                value={field.state.value}
                onChange={(event) => {
                  const next = event.target.value as WorkflowRunFilterState;
                  field.handleChange(next);
                  onStateChange(next);
                }}
              >
                <option value="">All states</option>
                <option value="queued">Queued</option>
                <option value="running">Running</option>
                <option value="completed">Completed</option>
                <option value="completed_with_repair">Completed with repair</option>
                <option value="failed">Failed</option>
                <option value="cancelled">Cancelled</option>
              </select>
            </label>
          )}
        </stateForm.Field>
        <span>{items.length} recent {items.length === 1 ? "run" : "runs"}</span>
      </div>
      {compact ? <form className="workflow-run-id-navigation" onSubmit={(event) => {
        event.preventDefault(); if (Number.isSafeInteger(runIdNumber) && runIdNumber > 0) onShowDetails(runIdNumber);
      }}>
        <label><span>Run ID</span><input aria-label="Run ID" type="number" min="1" step="1" value={runIdInput} onChange={(event) => setRunIdInput(event.target.value)} /></label>
        <button className="button button-secondary button-small" type="submit" disabled={!Number.isSafeInteger(runIdNumber) || runIdNumber <= 0}>Open run</button>
      </form> : null}
      {isLoading ? (
        <div className="surface-state" aria-busy="true">Loading profiling runs…</div>
      ) : isError ? (
        <div className="surface-state is-error" role="alert">
          Profiling runs could not be loaded.
        </div>
      ) : (
        compact ? <ol className="workflow-recent-runs" aria-label="Profiling run list">{items.map((run) => <li key={run.workflow_run_id}>
          <button type="button" id={`profiling-run-trigger-${run.workflow_run_id}`} aria-pressed={selectedRunId === run.workflow_run_id}
            className={selectedRunId === run.workflow_run_id ? "is-selected" : ""} onClick={() => onShowDetails(run.workflow_run_id)}>
            <span><strong>PR-{run.workflow_run_id}</strong><small>{formatDateTime(run.created_at)} · {run.selected_scope_count} Objects</small></span>
            <RunStateBadge state={run.workflow_run_state} />
          </button>
        </li>)}</ol> : <WorkflowTable table={table} label="Profiling runs" selectedId={selectedRunId} />
      )}
      {!isLoading && !isError && !items.length ? (
        <div className="empty-state compact">No profiling runs match this state.</div>
      ) : null}
    </section>
  );
}

export function ProfilingRunDrawer({
  embedded = false,
  hasTenantLock = true,
  api,
  tenantId,
  model,
  runId,
  onClose,
}: {
  embedded?: boolean;
  hasTenantLock?: boolean;
  api: ProfilingApi;
  tenantId: number;
  model: ModelDetail;
  runId: number;
  onClose: () => void;
}) {
  const queryClient = useQueryClient();
  const closeButton = useRef<HTMLButtonElement>(null);
  const runQuery = useQuery({
    queryKey: profilingQueryKeys.run(tenantId, model.model_id, runId),
    queryFn: () => api.readWorkflowRun(tenantId, model.model_id, runId),
  });
  const { events, query: eventsQuery } = useProfilingRunEvents({
    api,
    tenantId,
    modelId: model.model_id,
    runId,
  });
  const executeMutation = useMutation({
    mutationFn: () => api.executeProfilingRun(
      tenantId,
      model.model_id,
      runId,
      model.model_revision,
    ),
    onSuccess: async () => {
      await Promise.all([
        queryClient.invalidateQueries({
          queryKey: profilingQueryKeys.run(tenantId, model.model_id, runId),
        }),
        queryClient.invalidateQueries({
          queryKey: profilingQueryKeys.runs(tenantId, model.model_id),
        }),
      ]);
    },
  });

  useEffect(() => { if (!embedded) closeButton.current?.focus(); }, [embedded, runId]);

  const run = runQuery.data;
  return (
    <aside
      className={embedded ? "profiling-run-inline" : "workflow-drawer run-drawer"}
      aria-label="Profiling run details"
      onKeyDown={(event) => {
        if (event.key === "Escape" && !embedded) onClose();
      }}
    >
      {embedded ? <header className="workflow-run-detail-header"><strong>PR-{runId}</strong>{run ? <RunStateBadge state={run.workflow_run_state} /> : null}</header> : <DrawerHeader
        eyebrow="Run events"
        title={`PR-${runId}`}
        closeLabel="Close profiling run details"
        closeRef={closeButton}
        onClose={onClose}
        badge={run ? <RunStateBadge state={run.workflow_run_state} /> : undefined}
      />}
      {runQuery.isPending ? (
        <div className="surface-state" aria-busy="true">Loading run details…</div>
      ) : runQuery.isError || !run ? (
        <div className="surface-state is-error" role="alert">
          Run details could not be loaded.
        </div>
      ) : (
        <>
          <dl className="drawer-facts run-facts">
            <Fact label="Created" value={formatDateTime(run.created_at)} />
            <Fact label="Actor" value={run.actor_display_name} />
            <Fact label="Objects" value={String(run.selected_scope_count)} />
            <Fact label="Batch ID" value={run.requested_batch_id ?? "Not used"} />
          </dl>
          <WorkflowTokenUsage usage={run.token_usage} />
          <CancelWorkflowRun key={runId} api={api} tenantId={tenantId} modelId={model.model_id}
            run={run} hasTenantLock={hasTenantLock} onCancelled={async () => {
              await Promise.all([
                runQuery.refetch(), eventsQuery.refetch(),
                queryClient.invalidateQueries({ queryKey: profilingQueryKeys.runs(tenantId, model.model_id) }),
                queryClient.invalidateQueries({ queryKey: ["model-overview", tenantId, model.model_id] }),
                queryClient.invalidateQueries({ queryKey: ["tenant-home", tenantId] }),
              ]);
            }} />
          {run.workflow_run_state === "queued" ? (
            <div className="queued-run-action">
              <p>Creation does not execute Profiling. Start this queued run explicitly.</p>
              <button
                className="button button-primary button-small"
                type="button"
                disabled={executeMutation.isPending || !hasTenantLock}
                title={hasTenantLock ? undefined : "Tenant Lock required"}
                onClick={() => { if (hasTenantLock) executeMutation.mutate(); }}
              >
                {executeMutation.isPending ? "Starting…" : "Execute queued run"}
              </button>
            </div>
          ) : null}
          {executeMutation.isError ? (
            <p className="inline-error" role="alert">
              {isTenantWorkflowConflict(executeMutation.error)
                ? TENANT_WORKFLOW_CONFLICT_MESSAGE
                : "The queued run could not be started."}
            </p>
          ) : null}
          {run.failure_message ? (
            <div className="run-failure" role="alert">
              <strong>{run.failure_code ?? "Run failed"}</strong>
              <p>{run.failure_message}</p>
              <small>Reference {run.correlation_id}</small>
            </div>
          ) : null}
          <RunEventTimeline
            events={events}
            isLoading={eventsQuery.isPending && !events.length}
            isError={eventsQuery.isError}
          />
        </>
      )}
    </aside>
  );
}

function RunEventTimeline({
  events,
  isLoading,
  isError,
}: {
  events: WorkflowRunEvent[];
  isLoading: boolean;
  isError: boolean;
}) {
  if (isLoading) {
    return <div className="surface-state compact" aria-busy="true">Loading run events…</div>;
  }
  if (isError) {
    return (
      <div className="surface-state is-error compact" role="alert">
        Run events could not be loaded.
      </div>
    );
  }
  if (!events.length) {
    return (
      <div className="empty-state compact">
        No run events yet. Use Refresh to check again.
      </div>
    );
  }
  return (
    <ol className="run-event-timeline" aria-label="Run event timeline">
      {events.map((event) => (
        <li className={`is-${event.status}`} key={event.sequence}>
          <span className="event-marker" aria-hidden="true" />
          <div>
            <header>
              <strong>{stageLabel(event.stage)}</strong>
              <time>{formatDateTime(event.created_at)}</time>
            </header>
            <p>{event.message}</p>
            <WorkflowEventProgress event={event} />
            <small className="workflow-event-meta">
              <span>Event {event.sequence} · Attempt {event.attempt}</span>
              {event.current !== null && event.total !== null ? (
                <span>{event.current} of {event.total}</span>
              ) : null}
              {event.finding_count > 0 ? (
                <span>
                  {event.finding_count} {event.finding_count === 1 ? "finding" : "findings"}
                </span>
              ) : null}
            </small>
          </div>
        </li>
      ))}
    </ol>
  );
}
