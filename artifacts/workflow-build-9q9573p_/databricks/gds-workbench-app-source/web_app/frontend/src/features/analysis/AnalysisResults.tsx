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
  AnalysisReviewAction,
} from "./api";
import type { ModelInputScopeObject } from "../model_input_scope/api";

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
  reviewPending,
  reviewRetryable,
  reviewError,
  reviewNotice,
  onReview,
  onRetryReview,
  onApplyFilters,
  onSelectionChange,
  onLoadMore,
}: {
  tenantId: number;
  modelId: number;
  items: AnalysisFinding[];
  endpointOptions: ModelInputScopeObject[];
  filters: AnalysisFilters;
  selectedIds: Set<number>;
  isLoading: boolean;
  isError: boolean;
  revisionMismatch: boolean;
  hasMore: boolean;
  isLoadingMore: boolean;
  hasTenantLock: boolean;
  reviewPending: boolean;
  reviewRetryable: boolean;
  reviewError: string | null;
  reviewNotice: string;
  onReview: (action: AnalysisReviewAction) => void;
  onRetryReview: () => void;
  onApplyFilters: (filters: AnalysisFilters) => void;
  onSelectionChange: (ids: Set<number>) => void;
  onLoadMore: () => void;
}) {
  const reviewBusy = reviewPending || reviewRetryable;
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
          disabled={reviewBusy}
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
          disabled={reviewBusy}
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
      id: "from_object", header: "From Object",
      cell: ({ row }) => row.original.from_endpoint.object_name,
    },
    { id: "from_attribute", header: "From Attribute", cell: ({ row }) => row.original.from_endpoint.attribute_name },
    { id: "to_object", header: "To Object", cell: ({ row }) => row.original.to_endpoint.object_name },
    { id: "to_attribute", header: "To Attribute", cell: ({ row }) => row.original.to_endpoint.attribute_name },
    { id: "relationship", header: "Relationship", cell: ({ row }) => relationshipLabel(row.original.relationship_kind) },
    { id: "cardinality", header: () => <span title="Observed endpoint uniqueness from recorded validation counts">Cardinality</span>, cell: ({ row }) => row.original.observed_cardinality ? relationshipLabel(row.original.observed_cardinality) : row.original.validation_result ? "Unavailable" : "Not validated" },
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
      accessorKey: "status",
      header: "Status",
      cell: ({ getValue }) => relationshipLabel(getValue<string>()),
    },
    {
      id: "lock",
      header: "Lock",
      cell: ({ row }) => row.original.is_locked ? "Locked" : "Open",
    },
    { id: "actions", header: "Actions", cell: ({ row }) => <Link className="text-action" aria-label={`Open finding ${row.original.analysis_result_id}`}
        to="/tenants/$tenantId/models/$modelId/analysis/$findingId"
        params={{ tenantId: String(tenantId), modelId: String(modelId), findingId: String(row.original.analysis_result_id) }}>Show details</Link> },
  ], [allSelected, items, modelId, onSelectionChange, reviewBusy, selectedIds, tenantId]);
  const table = useReactTable({ data: items, columns, getCoreRowModel: getCoreRowModel() });
  const mutationReason = !hasTenantLock
    ? "Tenant Lock required for review updates."
    : reviewPending
      ? "Applying selected review…"
      : reviewRetryable
        ? "Retry the pending review before changing your selection."
        : revisionMismatch
          ? "Refresh before reviewing findings from a different Model revision."
          : selectedIds.size > 200
            ? "Select at most 200 findings per review."
            : "";
  const canReview = hasTenantLock && selectedIds.size > 0 && selectedIds.size <= 200
    && !reviewBusy && !revisionMismatch && !isLoading && !isError;

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
                disabled={reviewBusy}
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
                disabled={reviewBusy}
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
                disabled={reviewBusy}
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
            disabled={reviewBusy}
            onClick={() => {
              form.reset();
              onApplyFilters({});
            }}
          >
            Clear
          </button>
          <button className="button button-secondary button-small" type="submit" disabled={reviewBusy}>
            Apply finding filters
          </button>
        </div>
      </form>

      <div className="review-selectionbar" aria-busy={reviewPending}>
        <span>{selectedIds.size ? `${selectedIds.size} selected` : ""}</span>
        <div>
          {([
            ["lock", "Lock selected"],
            ["unlock", "Unlock selected"],
            ["deactivate", "Make inactive"],
            ["reactivate", "Make active"],
          ] as const).map(([action, label]) => (
            <button
              key={action}
              className="button button-secondary button-small"
              type="button"
              disabled={!canReview}
              title={canReview ? undefined : mutationReason}
              onClick={() => onReview(action)}
            >
              {label}
            </button>
          ))}
        </div>
        <small>{mutationReason}</small>
      </div>
      {reviewError ? (
        <div className="surface-state is-error" role="alert">
          <p>{reviewError}</p>
          {reviewRetryable ? (
            <button
              className="button button-secondary button-small"
              type="button"
              disabled={!hasTenantLock || reviewPending}
              title={hasTenantLock ? undefined : "Tenant Lock required for review updates"}
              onClick={onRetryReview}
            >
              Retry review
            </button>
          ) : null}
        </div>
      ) : reviewNotice ? <p role="status">{reviewNotice}</p> : null}

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

function relationshipLabel(value: string): string {
  return value.replaceAll("_", " ").replace(/^./, (character) => character.toLocaleUpperCase());
}

function validationTone(item: AnalysisFinding): string {
  if (item.validation_result === "supported") return "is-success";
  if (item.validation_result === "unsupported") return "is-danger";
  return "is-warning";
}
