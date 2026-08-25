import { useEffect, useMemo, useRef } from "react";
import { useForm } from "@tanstack/react-form";
import { getCoreRowModel, useReactTable, type ColumnDef } from "@tanstack/react-table";

import { formatRequiredDateTime as formatDateTime } from "../../shared/presentation";
import type {
  ProfilingFilters,
  ProfilingObject,
  ProfilingObjectDetail,
} from "./api";
import {
  DrawerHeader,
  Fact,
  WorkflowTable,
  formatPercent,
} from "./shared";

export function ProfilingResults({
  filters,
  items,
  isLoading,
  isError,
  revisionMismatch,
  selectedObjectId,
  onApplyFilters,
  onShowDetails,
}: {
  filters: ProfilingFilters;
  items: ProfilingObject[];
  isLoading: boolean;
  isError: boolean;
  revisionMismatch: boolean;
  selectedObjectId: number | null;
  onApplyFilters: (filters: ProfilingFilters) => void;
  onShowDetails: (objectId: number) => void;
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
        <button
          id={`profiling-detail-trigger-${row.original.object_id}`}
          className="text-action"
          type="button"
          aria-label={`Show profiling details for ${row.original.object_name}`}
          aria-expanded={selectedObjectId === row.original.object_id}
          onClick={() => onShowDetails(row.original.object_id)}
        >
          Show details
        </button>
      ),
    },
  ], [onShowDetails, selectedObjectId]);
  const table = useReactTable({ data: items, columns, getCoreRowModel: getCoreRowModel() });

  return (
    <section className="workflow-surface" aria-label="Profiling result review">
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
        <WorkflowTable table={table} label="Profiling results" selectedId={selectedObjectId} />
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
      const nextFilters: ProfilingFilters = {
        sourceTenantCode: value.sourceTenantCode,
        systemCode: value.systemCode,
        objectSchema: value.objectSchema,
        objectName: value.objectName,
      };
      if (
        typeof parsedObjectId === "number"
        && Number.isSafeInteger(parsedObjectId)
        && parsedObjectId > 0
      ) {
        nextFilters.objectId = parsedObjectId;
      }
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

export function ProfilingObjectDrawer({
  detail,
  fallback,
  isLoading,
  isError,
  onClose,
}: {
  detail: ProfilingObjectDetail | undefined;
  fallback: ProfilingObject | undefined;
  isLoading: boolean;
  isError: boolean;
  onClose: () => void;
}) {
  const closeButton = useRef<HTMLButtonElement>(null);
  useEffect(() => closeButton.current?.focus(), []);

  return (
    <aside
      className="workflow-drawer"
      aria-label="Profiling Object details"
      onKeyDown={(event) => {
        if (event.key === "Escape") onClose();
      }}
    >
      <DrawerHeader
        eyebrow="Profile evidence"
        title={detail?.object_name ?? fallback?.object_name ?? "Profiled Object"}
        closeLabel="Close profiling Object details"
        closeRef={closeButton}
        onClose={onClose}
      />
      {isLoading ? (
        <div className="surface-state" aria-busy="true">Loading profile evidence…</div>
      ) : isError || !detail ? (
        <div className="surface-state is-error" role="alert">
          Profile evidence could not be loaded.
        </div>
      ) : (
        <>
          <dl className="drawer-facts">
            <Fact label="System" value={detail.system_code} />
            <Fact label="Source Tenant" value={detail.source_tenant_code} />
            <Fact label="Object" value={`${detail.object_schema}.${detail.object_name}`} />
            <Fact label="Profiles" value={String(detail.profiled_attribute_count)} />
          </dl>
          {detail.profiles_truncated ? (
            <p className="drawer-warning">
              This bounded response does not include every Attribute profile.
            </p>
          ) : null}
          <div className="drawer-table-scroll">
            <table aria-label={`Attribute profiles for ${detail.object_name}`}>
              <thead>
                <tr>
                  <th>Attribute</th>
                  <th>Rows</th>
                  <th>Populated</th>
                  <th>Null</th>
                  <th>Distinct</th>
                </tr>
              </thead>
              <tbody>
                {detail.attribute_profiles.map((profile) => (
                  <tr key={profile.attribute_id}>
                    <td>
                      <span className="profile-attribute">
                        <strong>{profile.attribute_name}</strong>
                        <span>{profile.attribute_data_type}</span>
                      </span>
                    </td>
                    <td>{profile.row_count}</td>
                    <td>{formatPercent(profile.percent_populated)}</td>
                    <td>{formatPercent(profile.percent_null)}</td>
                    <td>{formatPercent(profile.percent_distinct)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <p className="drawer-footnote">
            Last profiled {formatDateTime(detail.last_profiled_at)}
          </p>
        </>
      )}
    </aside>
  );
}
