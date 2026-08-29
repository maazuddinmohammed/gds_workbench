import { useMemo } from "react";
import { useForm } from "@tanstack/react-form";
import { Link } from "@tanstack/react-router";
import { getCoreRowModel, useReactTable, type ColumnDef } from "@tanstack/react-table";

import { formatRequiredDateTime as formatDateTime } from "../../shared/presentation";
import type {
  ProfilingFilters,
  ProfilingObject,
} from "./api";
import { WorkflowTable } from "./shared";

export function ProfilingResults({
  tenantId,
  modelId,
  filters,
  items,
  isLoading,
  isError,
  revisionMismatch,
  onApplyFilters,
}: {
  tenantId: number;
  modelId: number;
  filters: ProfilingFilters;
  items: ProfilingObject[];
  isLoading: boolean;
  isError: boolean;
  revisionMismatch: boolean;
  onApplyFilters: (filters: ProfilingFilters) => void;
}) {
  const columns = useMemo<ColumnDef<ProfilingObject>[]>(() => [
    {
      accessorKey: "object_name",
      header: "Object",
      cell: ({ row }) => (
        <span className="scope-object-name">
          <strong>{row.original.object_name}</strong>
          <span>{row.original.object_schema}</span>
        </span>
      ),
    },
    {
      accessorKey: "system_code",
      header: "System",
      cell: ({ row }) => (
        <span className="scope-secondary">
          <strong>{row.original.system_code}</strong>
          <span>{row.original.system_name}</span>
        </span>
      ),
    },
    {
      accessorKey: "source_tenant_code",
      header: "Source Tenant",
      cell: ({ row }) => (
        <span className="scope-secondary">
          <strong>{row.original.source_tenant_code}</strong>
          <span>{row.original.source_tenant_name}</span>
        </span>
      ),
    },
    { accessorKey: "connection_code", header: "Connection" },
    {
      accessorKey: "profiled_attribute_count",
      header: "Profiles",
      cell: ({ getValue }) => `${getValue<number>()} profiles`,
    },
    {
      accessorKey: "last_profiled_at",
      header: "Last profiled",
      cell: ({ getValue }) => formatDateTime(getValue<string>()),
    },
    {
      id: "actions",
      header: "Actions",
      cell: ({ row }) => (
        <Link
          id={`profiling-detail-trigger-${row.original.object_id}`}
          className="text-action"
          aria-label={`Open profiling details for ${row.original.object_name}`}
          to="/tenants/$tenantId/models/$modelId/profiling/$objectId"
          params={{
            tenantId: String(tenantId),
            modelId: String(modelId),
            objectId: String(row.original.object_id),
          }}
          search={{ ...filters, returnObjectId: row.original.object_id }}
        >
          Show details
        </Link>
      ),
    },
  ], [filters, modelId, tenantId]);
  const table = useReactTable({ data: items, columns, getCoreRowModel: getCoreRowModel() });

  return (
    <section
      id="profiling-results-surface"
      className="workflow-surface"
      aria-label="Profiling result review"
      tabIndex={-1}
    >
      <ProfilingFilterForm filters={filters} onApply={onApplyFilters} />
      {isLoading ? (
        <div className="surface-state" aria-busy="true">Loading profiling results…</div>
      ) : revisionMismatch ? (
        <div className="surface-state is-error" role="alert">
          The Model changed while profiling results were loading. Refresh before review.
        </div>
      ) : isError ? (
        <div className="surface-state is-error" role="alert">
          Profiling results could not be loaded.
        </div>
      ) : (
        <WorkflowTable table={table} label="Profiling results" selectedId={null} />
      )}
      {!isLoading && !isError && !revisionMismatch && !items.length ? (
        <div className="empty-state compact">No profiling results match these filters.</div>
      ) : null}
    </section>
  );
}

function ProfilingFilterForm({
  filters,
  onApply,
}: {
  filters: ProfilingFilters;
  onApply: (filters: ProfilingFilters) => void;
}) {
  const form = useForm({
    defaultValues: {
      objectId: filters.objectId ? String(filters.objectId) : "",
      sourceTenantCode: filters.sourceTenantCode ?? "",
      systemCode: filters.systemCode ?? "",
      objectSchema: filters.objectSchema ?? "",
      objectName: filters.objectName ?? "",
    },
    onSubmit: ({ value }) => {
      const parsedObjectId = value.objectId.trim() ? Number(value.objectId) : undefined;
      const nextFilters: ProfilingFilters = {};
      if (
        typeof parsedObjectId === "number"
        && Number.isSafeInteger(parsedObjectId)
        && parsedObjectId > 0
      ) {
        nextFilters.objectId = parsedObjectId;
      }
      if (value.sourceTenantCode.trim()) nextFilters.sourceTenantCode = value.sourceTenantCode;
      if (value.systemCode.trim()) nextFilters.systemCode = value.systemCode;
      if (value.objectSchema.trim()) nextFilters.objectSchema = value.objectSchema;
      if (value.objectName.trim()) nextFilters.objectName = value.objectName;
      onApply(nextFilters);
    },
  });

  return (
    <form
      className="workflow-filterbar profiling-filterbar"
      aria-label="Profiling result filters"
      onSubmit={(event) => {
        event.preventDefault();
        event.stopPropagation();
        void form.handleSubmit();
      }}
    >
      <form.Field name="objectId">
        {(field) => (
          <label>
            <span>Object ID</span>
            <input
              aria-label="Object ID"
              inputMode="numeric"
              value={field.state.value}
              onBlur={field.handleBlur}
              onChange={(event) => field.handleChange(event.target.value)}
            />
          </label>
        )}
      </form.Field>
      <form.Field name="sourceTenantCode">
        {(field) => (
          <label>
            <span>Source Tenant code</span>
            <input
              aria-label="Source Tenant code"
              value={field.state.value}
              onBlur={field.handleBlur}
              onChange={(event) => field.handleChange(event.target.value)}
            />
          </label>
        )}
      </form.Field>
      <form.Field name="systemCode">
        {(field) => (
          <label>
            <span>System code</span>
            <input
              aria-label="System code"
              value={field.state.value}
              onBlur={field.handleBlur}
              onChange={(event) => field.handleChange(event.target.value)}
            />
          </label>
        )}
      </form.Field>
      <form.Field name="objectSchema">
        {(field) => (
          <label>
            <span>Object schema</span>
            <input
              aria-label="Object schema"
              value={field.state.value}
              onBlur={field.handleBlur}
              onChange={(event) => field.handleChange(event.target.value)}
            />
          </label>
        )}
      </form.Field>
      <form.Field name="objectName">
        {(field) => (
          <label>
            <span>Object name</span>
            <input
              aria-label="Object name"
              value={field.state.value}
              onBlur={field.handleBlur}
              onChange={(event) => field.handleChange(event.target.value)}
            />
          </label>
        )}
      </form.Field>
      <div className="workflow-filter-actions">
        <button className="button button-secondary button-small" type="submit">
          Apply result filters
        </button>
        <button
          className="text-action"
          type="button"
          onClick={() => {
            form.reset();
            onApply({});
          }}
        >
          Clear
        </button>
      </div>
    </form>
  );
}
