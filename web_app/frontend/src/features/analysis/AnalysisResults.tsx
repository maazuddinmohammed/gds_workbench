import { useMemo } from "react";
import { useForm } from "@tanstack/react-form";
import { Link } from "@tanstack/react-router";
import {
  flexRender,
  getCoreRowModel,
  useReactTable,
  type ColumnDef,
} from "@tanstack/react-table";

import type {
  AnalysisFilters,
  AnalysisFinding,
} from "./api";
import type { ModelScopeObject } from "../model_scope/api";

export function AnalysisResults({
  tenantId,
  modelId,
  items,
  endpointOptions,
  filters,
  selectedIds,
  isLoading,
  isError,
  revisionMismatch,
  hasMore,
  isLoadingMore,
  hasTenantLock,
  onApplyFilters,
  onSelectionChange,
  onLoadMore,
}: {
  tenantId: number;
  modelId: number;
  items: AnalysisFinding[];
  endpointOptions: ModelScopeObject[];
  filters: AnalysisFilters;
  selectedIds: Set<number>;
  isLoading: boolean;
  isError: boolean;
  revisionMismatch: boolean;
  hasMore: boolean;
  isLoadingMore: boolean;
  hasTenantLock: boolean;
  onApplyFilters: (filters: AnalysisFilters) => void;
  onSelectionChange: (ids: Set<number>) => void;
  onLoadMore: () => void;
}) {
  const form = useForm({
    defaultValues: {
      objectId: filters.objectId ? String(filters.objectId) : "",
      validationState: filters.validationState ?? "",
      showInactive: filters.showInactive ?? false,
    },
    onSubmit: ({ value }) => onApplyFilters({
      ...(value.objectId ? { objectId: Number(value.objectId) } : {}),
      ...(value.validationState
        ? { validationState: value.validationState as "validated" | "unvalidated" }
        : {}),
      ...(value.showInactive ? { showInactive: true } : {}),
    }),
  });
  const allSelected = items.length > 0
    && items.every((item) => selectedIds.has(item.analysis_result_id));
  const columns = useMemo<ColumnDef<AnalysisFinding>[]>(() => [
    {
      id: "selection",
      header: () => (
        <input
          type="checkbox"
          aria-label="Select all visible findings"
          checked={allSelected}
          onChange={(event) => onSelectionChange(event.target.checked
            ? new Set(items.map((item) => item.analysis_result_id))
            : new Set())}
        />
      ),
      cell: ({ row }) => (
        <input
          type="checkbox"
          aria-label={`Select finding ${row.original.analysis_result_id}`}
          checked={selectedIds.has(row.original.analysis_result_id)}
          onChange={(event) => {
            const next = new Set(selectedIds);
            if (event.target.checked) next.add(row.original.analysis_result_id);
            else next.delete(row.original.analysis_result_id);
            onSelectionChange(next);
          }}
        />
      ),
    },
    {
      id: "from",
      header: "From Object / attribute",
      cell: ({ row }) => <EndpointCell endpoint={row.original.from_endpoint} />,
    },
    {
      id: "relationship",
      header: "Relationship",
      cell: ({ row }) => relationshipLabel(row.original.relationship_kind),
    },
    {
      id: "to",
      header: "To Object / attribute",
      cell: ({ row }) => <EndpointCell endpoint={row.original.to_endpoint} />,
    },
    {
      accessorKey: "relationship_confidence",
      header: "Confidence",
      cell: ({ getValue }) => (
        <span className={`status-badge confidence-${getValue<string>()}`}>
          {getValue<string>()}
        </span>
      ),
    },
    {
      id: "validation",
      header: "Validation",
      cell: ({ row }) => (
        <span className={`status-badge ${validationTone(row.original)}`}>
          {row.original.validation_result
            ? relationshipLabel(row.original.validation_result)
            : "Pending"}
        </span>
      ),
    },
    {
      id: "lock",
      header: "Lock",
      cell: ({ row }) => row.original.is_locked ? "Locked" : "Open",
    },
    {
      id: "actions",
      header: "",
      cell: ({ row }) => (
        <Link
          className="text-action"
          aria-label={`Open finding ${row.original.analysis_result_id}`}
          to="/tenants/$tenantId/models/$modelId/analysis/$findingId"
          params={{
            tenantId: String(tenantId),
            modelId: String(modelId),
            findingId: String(row.original.analysis_result_id),
          }}
        >
          Show details
        </Link>
      ),
    },
  ], [allSelected, items, modelId, onSelectionChange, selectedIds, tenantId]);
  const table = useReactTable({ data: items, columns, getCoreRowModel: getCoreRowModel() });
  const mutationReason = hasTenantLock
    ? "Review updates are not available from the web API yet."
    : "Tenant Lock required for review updates.";

  return (
    <section className="workflow-surface" aria-label="Analysis results">
      <form
        className="workflow-filterbar analysis-filterbar"
        aria-label="Filter Analysis findings"
        onSubmit={(event) => {
          event.preventDefault();
          event.stopPropagation();
          void form.handleSubmit();
        }}
      >
        <form.Field name="objectId">
          {(field) => (
            <label>
              <span>Object endpoint</span>
              <select
                aria-label="Object endpoint"
                value={field.state.value}
                onBlur={field.handleBlur}
                onChange={(event) => field.handleChange(event.target.value)}
              >
                <option value="">All Objects</option>
                {endpointOptions.map((item) => (
                  <option key={item.object_id} value={item.object_id}>
                    {item.object_name} · {item.system_code}
                  </option>
                ))}
              </select>
            </label>
          )}
        </form.Field>
        <form.Field name="validationState">
          {(field) => (
            <label>
              <span>Validation state</span>
              <select
                aria-label="Validation state"
                value={field.state.value}
                onBlur={field.handleBlur}
                onChange={(event) => field.handleChange(event.target.value)}
              >
                <option value="">All validation states</option>
                <option value="unvalidated">Pending</option>
                <option value="validated">Validated</option>
              </select>
            </label>
          )}
        </form.Field>
        <form.Field name="showInactive">
          {(field) => (
            <label className="inline-checkbox">
              <input
                type="checkbox"
                checked={field.state.value}
                onBlur={field.handleBlur}
                onChange={(event) => field.handleChange(event.target.checked)}
              />
              <span>Show inactive</span>
            </label>
          )}
        </form.Field>
        <div className="workflow-filter-actions">
          <button
            className="button button-secondary button-small"
            type="button"
            onClick={() => {
              form.reset();
              onApplyFilters({});
            }}
          >
            Clear
          </button>
          <button className="button button-secondary button-small" type="submit">
            Apply finding filters
          </button>
        </div>
      </form>

      <div className="review-selectionbar">
        <span>{selectedIds.size ? `${selectedIds.size} selected` : "Select findings to review"}</span>
        <div>
          {(["Lock selected", "Unlock selected", "Make inactive"] as const).map((label) => (
            <button key={label} className="button button-secondary button-small" type="button" disabled>
              {label}
            </button>
          ))}
        </div>
        <small>{mutationReason}</small>
      </div>

      {isLoading ? (
        <div className="surface-state" aria-busy="true">Loading Analysis findings…</div>
      ) : isError ? (
        <div className="surface-state is-error" role="alert">
          Analysis findings could not be loaded.
        </div>
      ) : revisionMismatch ? (
        <div className="surface-state is-error" role="alert">
          The Model changed while Analysis results were loading. Refresh to reconcile revisions.
        </div>
      ) : items.length === 0 ? (
        <div className="empty-state compact">No Analysis findings match these filters.</div>
      ) : (
        <div className="workflow-table-scroll table-scroll">
          <table aria-label="Analysis findings">
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
                <tr key={row.id} className={selectedIds.has(row.original.analysis_result_id) ? "is-active" : ""}>
                  {row.getVisibleCells().map((cell) => (
                    <td key={cell.id}>{flexRender(cell.column.columnDef.cell, cell.getContext())}</td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
          {hasMore ? (
            <div className="ledger-pagination">
              <button
                className="button button-secondary button-small"
                type="button"
                disabled={isLoadingMore}
                onClick={onLoadMore}
              >
                {isLoadingMore ? "Loading…" : "Load more findings"}
              </button>
            </div>
          ) : null}
        </div>
      )}
    </section>
  );
}

function EndpointCell({ endpoint }: { endpoint: AnalysisFinding["from_endpoint"] }) {
  return (
    <span className="endpoint-cell">
      <strong>{endpoint.object_name}</strong>
      <span>{endpoint.attribute_name}</span>
    </span>
  );
}

function relationshipLabel(value: string): string {
  return value.replaceAll("_", " ").replace(/^./, (character) => character.toLocaleUpperCase());
}

function validationTone(item: AnalysisFinding): string {
  if (item.validation_result === "supported") return "is-success";
  if (item.validation_result === "unsupported") return "is-danger";
  return "is-warning";
}
