import { useMemo, type ReactNode } from "react";
import { useForm } from "@tanstack/react-form";
import { Link } from "@tanstack/react-router";
import {
  flexRender,
  getCoreRowModel,
  useReactTable,
  type ColumnDef,
} from "@tanstack/react-table";

import type {
  MappingAttribute,
  MappingDependency,
  MappingFilters,
  MappingObject,
} from "./api";
import { formatRequiredDateTime as formatDateTime } from "../../shared/presentation";

export interface MappingLedgerState {
  isLoading: boolean;
  isError: boolean;
  isDenied: boolean;
  revisionMismatch: boolean;
  hasMore: boolean;
  isLoadingMore: boolean;
}

interface CommonLedgerProps {
  tenantId: number;
  modelId: number;
  filters: MappingFilters;
  state: MappingLedgerState;
  onApplyFilters: (filters: MappingFilters) => void;
  onLoadMore: () => void;
}

export function MappingDependenciesLedger({
  items,
  filters,
  state,
  onApplyFilters,
  onLoadMore,
}: CommonLedgerProps & { items: MappingDependency[] }) {
  const columns = useMemo<ColumnDef<MappingDependency>[]>(() => [
    {
      id: "source_system",
      header: "Source System",
      cell: ({ row }) => (
        <span className="endpoint-cell">
          <strong>{row.original.source_system.system_name}</strong>
          <span>{row.original.source_system.system_code}</span>
        </span>
      ),
    },
    { accessorKey: "entity_type", header: "Entity type", cell: ({ getValue }) => humanize(getValue<string>()) },
    { accessorKey: "dependency_order", header: "Order" },
    { accessorKey: "status", header: "Status", cell: ({ getValue }) => humanize(getValue<string>()) },
    { accessorKey: "is_locked", header: "Lock", cell: ({ getValue }) => getValue<boolean>() ? "Locked" : "Open" },
    {
      accessorKey: "workflow_run_id",
      header: "Provenance",
      cell: ({ getValue }) => {
        const value = getValue<number | null>();
        return value === null ? "No workflow provenance" : `Workflow run ${value}`;
      },
    },
    { accessorKey: "updated_at", header: "Updated", cell: ({ getValue }) => formatDateTime(getValue<string>()) },
  ], []);
  return (
    <MappingLedgerSurface
      label="Mapping Dependencies"
      items={items}
      columns={columns}
      filters={<MappingFilterBar filters={filters} onApplyFilters={onApplyFilters} />}
      state={state}
      onLoadMore={onLoadMore}
    />
  );
}

export function MappingObjectsLedger({
  tenantId,
  modelId,
  items,
  filters,
  state,
  onApplyFilters,
  onLoadMore,
}: CommonLedgerProps & { items: MappingObject[] }) {
  const columns = useMemo<ColumnDef<MappingObject>[]>(() => [
    {
      id: "target",
      header: "Target Object",
      cell: ({ row }) => (
        <span className="endpoint-cell">
          <strong>{row.original.target.object_schema}.{row.original.target.object_name}</strong>
          <span>{row.original.target.tenant_code} · {row.original.target.system_code} · {row.original.target.zone_code}</span>
        </span>
      ),
    },
    {
      id: "source",
      header: "Modeled source",
      cell: ({ row }) => (
        <span className="endpoint-cell">
          <strong>{row.original.source.entity_name}</strong>
          <span>{humanize(row.original.source.entity_type)}</span>
        </span>
      ),
    },
    { id: "source_system", header: "Source System", cell: ({ row }) => row.original.source_system.system_code },
    { accessorKey: "dependency_order", header: "Order" },
    { accessorKey: "status", header: "Status", cell: ({ getValue }) => humanize(getValue<string>()) },
    { accessorKey: "is_locked", header: "Lock", cell: ({ getValue }) => getValue<boolean>() ? "Locked" : "Open" },
    {
      id: "action",
      header: "",
      cell: ({ row }) => (
        <Link
          className="text-action"
          aria-label={`Open Object Mapping ${row.original.mapping_object_id}`}
          to="/tenants/$tenantId/mapping/models/$modelId/objects/$mappingObjectId"
          params={{
            tenantId: String(tenantId),
            modelId: String(modelId),
            mappingObjectId: String(row.original.mapping_object_id),
          }}
        >
          Show details
        </Link>
      ),
    },
  ], [modelId, tenantId]);
  return (
    <MappingLedgerSurface
      label="Object Mappings"
      items={items}
      columns={columns}
      filters={<MappingFilterBar filters={filters} onApplyFilters={onApplyFilters} />}
      state={state}
      onLoadMore={onLoadMore}
    />
  );
}

export function MappingAttributesLedger({
  tenantId,
  modelId,
  items,
  filters,
  state,
  onApplyFilters,
  onLoadMore,
}: CommonLedgerProps & { items: MappingAttribute[] }) {
  const columns = useMemo<ColumnDef<MappingAttribute>[]>(() => [
    {
      id: "target",
      header: "Target Attribute",
      cell: ({ row }) => (
        <span className="endpoint-cell">
          <strong>{row.original.target.object.object_schema}.{row.original.target.object.object_name}.{row.original.target.attribute_name}</strong>
          <span>{row.original.target.attribute_data_type} · ordinal {row.original.target.attribute_ordinal_position}</span>
        </span>
      ),
    },
    {
      id: "source",
      header: "Modeled source",
      cell: ({ row }) => (
        <span className="endpoint-cell">
          <strong>{row.original.source.entity.entity_name}.{row.original.source.attribute_name}</strong>
          <span>{humanize(row.original.source.entity.entity_type)}</span>
        </span>
      ),
    },
    { id: "source_system", header: "Source System", cell: ({ row }) => row.original.source_system.system_code },
    { accessorKey: "status", header: "Status", cell: ({ getValue }) => humanize(getValue<string>()) },
    { accessorKey: "is_locked", header: "Lock", cell: ({ getValue }) => getValue<boolean>() ? "Locked" : "Open" },
    { accessorKey: "updated_at", header: "Updated", cell: ({ getValue }) => formatDateTime(getValue<string>()) },
    {
      id: "action",
      header: "",
      cell: ({ row }) => (
        <Link
          className="text-action"
          aria-label={`Open Attribute Mapping ${row.original.mapping_attribute_id}`}
          to="/tenants/$tenantId/mapping/models/$modelId/attributes/$mappingAttributeId"
          params={{
            tenantId: String(tenantId),
            modelId: String(modelId),
            mappingAttributeId: String(row.original.mapping_attribute_id),
          }}
        >
          Show details
        </Link>
      ),
    },
  ], [modelId, tenantId]);
  return (
    <MappingLedgerSurface
      label="Attribute Mappings"
      items={items}
      columns={columns}
      filters={<MappingFilterBar filters={filters} onApplyFilters={onApplyFilters} />}
      state={state}
      onLoadMore={onLoadMore}
    />
  );
}

function MappingFilterBar({
  filters,
  onApplyFilters,
}: {
  filters: MappingFilters;
  onApplyFilters: (filters: MappingFilters) => void;
}) {
  const form = useForm({
    defaultValues: {
      entityType: filters.entityType ?? "",
      sourceSystemCode: filters.sourceSystemCode ?? "",
      status: filters.status ?? "",
      locked: filters.locked === undefined ? "" : String(filters.locked),
    },
    onSubmit: ({ value }) => onApplyFilters({
      ...(value.entityType ? { entityType: value.entityType as NonNullable<MappingFilters["entityType"]> } : {}),
      ...(value.sourceSystemCode ? { sourceSystemCode: value.sourceSystemCode } : {}),
      ...(value.status ? { status: value.status as NonNullable<MappingFilters["status"]> } : {}),
      ...(value.locked ? { locked: value.locked === "true" } : {}),
    }),
  });
  return (
    <form
      className="workflow-filterbar mapping-filterbar"
      aria-label="Filter Mapping"
      onSubmit={(event) => {
        event.preventDefault();
        event.stopPropagation();
        void form.handleSubmit();
      }}
    >
      <form.Field name="entityType">
        {(field) => (
          <label>
            <span>Entity type</span>
            <select aria-label="Entity type" value={field.state.value} onChange={(event) => field.handleChange(event.target.value)}>
              <option value="">All Entity types</option>
              <option value="logical_entity">Logical Entity</option>
              <option value="dimensional_entity">Dimensional Entity</option>
            </select>
          </label>
        )}
      </form.Field>
      <form.Field name="sourceSystemCode">
        {(field) => (
          <label>
            <span>Source System code</span>
            <input aria-label="Source System code" value={field.state.value} onChange={(event) => field.handleChange(event.target.value)} />
          </label>
        )}
      </form.Field>
      <form.Field name="status">
        {(field) => (
          <label>
            <span>Mapping status</span>
            <select aria-label="Mapping status" value={field.state.value} onChange={(event) => field.handleChange(event.target.value)}>
              <option value="">All statuses</option>
              <option value="active">Active</option>
              <option value="inactive">Inactive</option>
              <option value="deprecated">Deprecated</option>
            </select>
          </label>
        )}
      </form.Field>
      <form.Field name="locked">
        {(field) => (
          <label>
            <span>Mapping lock</span>
            <select aria-label="Mapping lock" value={field.state.value} onChange={(event) => field.handleChange(event.target.value)}>
              <option value="">All lock states</option>
              <option value="true">Locked</option>
              <option value="false">Open</option>
            </select>
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
        <button className="button button-secondary button-small" type="submit">Apply Mapping filters</button>
      </div>
    </form>
  );
}

function MappingLedgerSurface<T>({
  label,
  items,
  columns,
  filters,
  state,
  onLoadMore,
}: {
  label: string;
  items: T[];
  columns: ColumnDef<T>[];
  filters: ReactNode;
  state: MappingLedgerState;
  onLoadMore: () => void;
}) {
  const table = useReactTable({ data: items, columns, getCoreRowModel: getCoreRowModel() });
  return (
    <section className="workflow-surface mapping-surface" aria-label={label}>
      {filters}
      {state.isLoading ? (
        <div className="surface-state" aria-busy="true">Loading {label}…</div>
      ) : state.isDenied ? (
        <div className="surface-state is-error" role="alert">You do not have permission to view {label}.</div>
      ) : state.isError ? (
        <div className="surface-state is-error" role="alert">{label} could not be loaded.</div>
      ) : state.revisionMismatch ? (
        <div className="surface-state is-error" role="alert">
          The Model changed while {label} were loading. Refresh to reconcile revisions.
        </div>
      ) : items.length === 0 ? (
        <div className="empty-state compact">No {label} match these filters.</div>
      ) : (
        <div className="workflow-table-scroll mapping-table-scroll table-scroll">
          <table aria-label={label}>
            <thead>
              {table.getHeaderGroups().map((group) => (
                <tr key={group.id}>
                  {group.headers.map((header) => (
                    <th key={header.id}>
                      {header.isPlaceholder ? null : flexRender(header.column.columnDef.header, header.getContext())}
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
          {state.hasMore ? (
            <div className="ledger-pagination">
              <button
                className="button button-secondary button-small"
                type="button"
                disabled={state.isLoadingMore}
                onClick={onLoadMore}
              >
                {state.isLoadingMore ? "Loading…" : `Load more ${label}`}
              </button>
            </div>
          ) : null}
        </div>
      )}
    </section>
  );
}

function humanize(value: string): string {
  return value.replaceAll("_", " ").replace(/^./, (character) => character.toLocaleUpperCase());
}
