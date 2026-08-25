import { useMemo } from "react";
import {
  flexRender,
  getCoreRowModel,
  useReactTable,
  type ColumnDef,
} from "@tanstack/react-table";

import { formatRequiredDateTime as formatDateTime } from "../../shared/presentation";
import type { WorkflowRunFilterState, WorkflowRunRecord } from "../workflows/api";
import { RunStateBadge } from "../workflows/presentation";

export function AnalysisRuns({
  items,
  state,
  isLoading,
  isError,
  onStateChange,
}: {
  items: WorkflowRunRecord[];
  state: WorkflowRunFilterState;
  isLoading: boolean;
  isError: boolean;
  onStateChange: (state: WorkflowRunFilterState) => void;
}) {
  const columns = useMemo<ColumnDef<WorkflowRunRecord>[]>(() => [
    { accessorKey: "workflow_run_id", header: "Run", cell: ({ getValue }) => `AR-${getValue<number>()}` },
    {
      id: "kind",
      header: "Run type",
      cell: ({ row }) => row.original.workflow_execution_mode === null ? "Validation" : "Inference",
    },
    {
      id: "mode",
      header: "Mode",
      cell: ({ row }) => row.original.workflow_execution_mode?.replaceAll("_", " ") ?? "Deterministic",
    },
    { accessorKey: "selected_scope_count", header: "Objects" },
    { accessorKey: "actor_display_name", header: "Actor" },
    {
      accessorKey: "workflow_run_state",
      header: "State",
      cell: ({ row }) => <RunStateBadge state={row.original.workflow_run_state} />,
    },
    {
      accessorKey: "created_at",
      header: "Created",
      cell: ({ getValue }) => formatDateTime(getValue<string>()),
    },
  ], []);
  const table = useReactTable({ data: items, columns, getCoreRowModel: getCoreRowModel() });

  return (
    <section className="workflow-surface" aria-label="Analysis run history">
      <div className="workflow-filterbar run-filterbar">
        <label>
          <span>Run state</span>
          <select
            aria-label="Run state"
            value={state}
            onChange={(event) => onStateChange(event.target.value as WorkflowRunFilterState)}
          >
            <option value="">All states</option>
            <option value="queued">Queued</option>
            <option value="running">Running</option>
            <option value="completed">Completed</option>
            <option value="completed_with_repair">Completed with repair</option>
            <option value="failed">Failed</option>
          </select>
        </label>
        <span>{items.length} recent runs</span>
      </div>
      {isLoading ? (
        <div className="surface-state" aria-busy="true">Loading Analysis runs…</div>
      ) : isError ? (
        <div className="surface-state is-error" role="alert">Analysis runs could not be loaded.</div>
      ) : items.length === 0 ? (
        <div className="empty-state compact">No Analysis runs match this state.</div>
      ) : (
        <div className="workflow-table-scroll table-scroll">
          <table aria-label="Analysis runs">
            <thead>
              {table.getHeaderGroups().map((group) => (
                <tr key={group.id}>
                  {group.headers.map((header) => (
                    <th key={header.id}>
                      {header.isPlaceholder
                        ? null
                        : flexRender(header.column.columnDef.header, header.getContext())}
                    </th>
                  ))}
                </tr>
              ))}
            </thead>
            <tbody>
              {table.getRowModel().rows.map((row) => (
                <tr key={row.id}>
                  {row.getVisibleCells().map((cell) => (
                    <td key={cell.id}>{flexRender(cell.column.columnDef.cell, cell.getContext())}</td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </section>
  );
}
