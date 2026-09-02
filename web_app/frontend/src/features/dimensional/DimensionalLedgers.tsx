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
  DimensionalAttribute,
  DimensionalAttributeFilters,
  DimensionalFilters,
  DimensionalObject,
  DimensionalRelationship,
  DimensionalRelationshipFilters,
} from "./api";
import { formatRequiredDateTime as formatDateTime } from "../../shared/presentation";

export interface DimensionalLedgerState {
  isLoading: boolean;
  isError: boolean;
  isDenied: boolean;
  revisionMismatch: boolean;
  hasMore: boolean;
  isLoadingMore: boolean;
}

export function DimensionalObjectsLedger({
  tenantId,
  modelId,
  items,
  filters,
  state,
  onApplyFilters,
  onLoadMore,
}: {
  tenantId: number;
  modelId: number;
  items: DimensionalObject[];
  filters: DimensionalFilters;
  state: DimensionalLedgerState;
  onApplyFilters: (filters: DimensionalFilters) => void;
  onLoadMore: () => void;
}) {
  const columns = useMemo<ColumnDef<DimensionalObject>[]>(() => [
    {
      accessorKey: "dimensional_entity_name",
      header: "Dimensional Object",
      cell: ({ row }) => (
        <span className="endpoint-cell">
          <strong>{row.original.dimensional_entity_name}</strong>
          <span>{humanize(row.original.dimensional_entity_type)}</span>
        </span>
      ),
    },
    {
      accessorKey: "dimensional_fact_type",
      header: "Fact type",
      cell: ({ getValue }) => {
        const value = getValue<string | null>();
        return value ? humanize(value) : "—";
      },
    },
    { accessorKey: "dimensional_entity_dependency_order", header: "Order" },
    {
      accessorKey: "dimensional_entity_confidence",
      header: "Confidence",
      cell: ({ getValue }) => (
        <span className={`status-badge confidence-${getValue<string>()}`}>
          {humanize(getValue<string>())}
        </span>
      ),
    },
    {
      accessorKey: "dimensional_entity_status",
      header: "Status",
      cell: ({ getValue }) => humanize(getValue<string>()),
    },
    {
      accessorKey: "dimensional_entity_is_locked",
      header: "Lock",
      cell: ({ getValue }) => getValue<boolean>() ? "Locked" : "Open",
    },
    {
      accessorKey: "updated_at",
      header: "Updated",
      cell: ({ getValue }) => formatDateTime(getValue<string>()),
    },
    {
      id: "action",
      header: "",
      cell: ({ row }) => (
        <Link
          className="text-action"
          aria-label={`Open Dimensional Object ${row.original.dimensional_entity_id}`}
          to="/tenants/$tenantId/models/$modelId/dimensional/objects/$entityId"
          params={{
            tenantId: String(tenantId),
            modelId: String(modelId),
            entityId: String(row.original.dimensional_entity_id),
          }}
        >
          Show details
        </Link>
      ),
    },
  ], [modelId, tenantId]);
  const table = useReactTable({ data: items, columns, getCoreRowModel: getCoreRowModel() });

  return (
    <section className="workflow-surface" aria-label="Dimensional Objects">
      <DimensionalFilterBar filters={filters} onApplyFilters={onApplyFilters} />
      {state.isLoading ? (
        <div className="surface-state" aria-busy="true">Loading Dimensional Objects…</div>
      ) : state.isDenied ? (
        <div className="surface-state is-error" role="alert">
          You do not have permission to view Dimensional Objects.
        </div>
      ) : state.isError ? (
        <div className="surface-state is-error" role="alert">
          Dimensional Objects could not be loaded.
        </div>
      ) : state.revisionMismatch ? (
        <div className="surface-state is-error" role="alert">
          The Model changed while Dimensional Objects were loading. Refresh to reconcile revisions.
        </div>
      ) : items.length === 0 ? (
        <div className="empty-state compact">No Dimensional Objects match these filters.</div>
      ) : (
        <div className="workflow-table-scroll table-scroll">
          <table aria-label="Dimensional Objects">
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
          {state.hasMore ? (
            <div className="ledger-pagination">
              <button
                className="button button-secondary button-small"
                type="button"
                disabled={state.isLoadingMore}
                onClick={onLoadMore}
              >
                {state.isLoadingMore ? "Loading…" : "Load more Dimensional Objects"}
              </button>
            </div>
          ) : null}
        </div>
      )}
    </section>
  );
}

function DimensionalFilterBar({
  filters,
  onApplyFilters,
}: {
  filters: DimensionalFilters;
  onApplyFilters: (filters: DimensionalFilters) => void;
}) {
  const form = useForm({
    defaultValues: {
      namePrefix: filters.namePrefix ?? "",
      status: filters.status ?? "",
      locked: filters.locked === undefined ? "" : String(filters.locked),
    },
    onSubmit: ({ value }) => onApplyFilters({
      ...(value.namePrefix ? { namePrefix: value.namePrefix } : {}),
      ...(value.status ? { status: value.status as NonNullable<DimensionalFilters["status"]> } : {}),
      ...(value.locked ? { locked: value.locked === "true" } : {}),
    }),
  });
  return (
    <form
      className="workflow-filterbar dimensional-filterbar"
      aria-label="Filter Dimensional Objects"
      onSubmit={(event) => {
        event.preventDefault();
        event.stopPropagation();
        void form.handleSubmit();
      }}
    >
      <form.Field name="namePrefix">
        {(field) => (
          <label>
            <span>Object name prefix</span>
            <input
              aria-label="Object name prefix"
              value={field.state.value}
              onBlur={field.handleBlur}
              onChange={(event) => field.handleChange(event.target.value)}
            />
          </label>
        )}
      </form.Field>
      <form.Field name="status">
        {(field) => (
          <label>
            <span>Object status</span>
            <select
              aria-label="Object status"
              value={field.state.value}
              onChange={(event) => field.handleChange(event.target.value)}
            >
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
            <span>Object lock</span>
            <select
              aria-label="Object lock"
              value={field.state.value}
              onChange={(event) => field.handleChange(event.target.value)}
            >
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
        <button className="button button-secondary button-small" type="submit">
          Apply Object filters
        </button>
      </div>
    </form>
  );
}

export function DimensionalAttributesLedger({
  tenantId,
  modelId,
  items,
  filters,
  state,
  onApplyFilters,
  onLoadMore,
}: {
  tenantId: number;
  modelId: number;
  items: DimensionalAttribute[];
  filters: DimensionalAttributeFilters;
  state: DimensionalLedgerState;
  onApplyFilters: (filters: DimensionalAttributeFilters) => void;
  onLoadMore: () => void;
}) {
  const columns = useMemo<ColumnDef<DimensionalAttribute>[]>(() => [
    {
      accessorKey: "dimensional_attribute_name",
      header: "Dimensional Attribute",
      cell: ({ row }) => (
        <span className="endpoint-cell">
          <strong>{row.original.dimensional_attribute_name}</strong>
          <span>{row.original.dimensional_attribute_data_type}</span>
        </span>
      ),
    },
    { accessorKey: "dimensional_entity_name", header: "Object" },
    {
      accessorKey: "dimensional_attribute_role",
      header: "Role",
      cell: ({ getValue }) => humanize(getValue<string>()),
    },
    {
      accessorKey: "dimensional_attribute_key_role",
      header: "Key role",
      cell: ({ getValue }) => humanize(getValue<string>()),
    },
    {
      accessorKey: "dimensional_attribute_additivity",
      header: "Additivity",
      cell: ({ getValue }) => {
        const value = getValue<string | null>();
        return value ? humanize(value) : "—";
      },
    },
    {
      accessorKey: "dimensional_attribute_default_aggregation",
      header: "Aggregation",
      cell: ({ getValue }) => getValue<string | null>() ?? "—",
    },
    {
      accessorKey: "dimensional_attribute_status",
      header: "Status",
      cell: ({ getValue }) => humanize(getValue<string>()),
    },
    {
      id: "action",
      header: "",
      cell: ({ row }) => (
        <Link
          className="text-action"
          aria-label={`Open Dimensional Attribute ${row.original.dimensional_attribute_id}`}
          to="/tenants/$tenantId/models/$modelId/dimensional/attributes/$attributeId"
          params={{
            tenantId: String(tenantId),
            modelId: String(modelId),
            attributeId: String(row.original.dimensional_attribute_id),
          }}
        >
          Show details
        </Link>
      ),
    },
  ], [modelId, tenantId]);
  return (
    <DimensionalLedgerSurface
      tableLabel="Dimensional Attributes"
      items={items}
      columns={columns}
      state={state}
      onLoadMore={onLoadMore}
      filters={<DimensionalCollectionFilterBar
        kind="Attribute"
        filters={filters}
        onApplyFilters={onApplyFilters}
      />}
    />
  );
}

export function DimensionalRelationshipsLedger({
  tenantId,
  modelId,
  items,
  filters,
  state,
  onApplyFilters,
  onLoadMore,
}: {
  tenantId: number;
  modelId: number;
  items: DimensionalRelationship[];
  filters: DimensionalRelationshipFilters;
  state: DimensionalLedgerState;
  onApplyFilters: (filters: DimensionalRelationshipFilters) => void;
  onLoadMore: () => void;
}) {
  const columns = useMemo<ColumnDef<DimensionalRelationship>[]>(() => [
    { accessorKey: "dimensional_relationship_name", header: "Relationship" },
    {
      id: "from",
      header: "From",
      cell: ({ row }) => (
        <span className="endpoint-cell">
          <strong>{row.original.from_dimensional_entity_name}</strong>
          <span>{row.original.from_dimensional_attribute_name}</span>
        </span>
      ),
    },
    {
      id: "to",
      header: "To",
      cell: ({ row }) => (
        <span className="endpoint-cell">
          <strong>{row.original.to_dimensional_entity_name}</strong>
          <span>{row.original.to_dimensional_attribute_name}</span>
        </span>
      ),
    },
    {
      accessorKey: "dimensional_relationship_kind",
      header: "Kind",
      cell: ({ getValue }) => humanize(getValue<string>()),
    },
    {
      accessorKey: "dimensional_relationship_cardinality",
      header: "Cardinality",
      cell: ({ getValue }) => humanize(getValue<string>()),
    },
    {
      accessorKey: "dimensional_relationship_status",
      header: "Status",
      cell: ({ getValue }) => humanize(getValue<string>()),
    },
    {
      id: "action",
      header: "",
      cell: ({ row }) => (
        <Link
          className="text-action"
          aria-label={`Open Dimensional Relationship ${row.original.dimensional_relationship_id}`}
          to="/tenants/$tenantId/models/$modelId/dimensional/relationships/$relationshipId"
          params={{
            tenantId: String(tenantId),
            modelId: String(modelId),
            relationshipId: String(row.original.dimensional_relationship_id),
          }}
        >
          Show details
        </Link>
      ),
    },
  ], [modelId, tenantId]);
  return (
    <DimensionalLedgerSurface
      tableLabel="Dimensional Relationships"
      items={items}
      columns={columns}
      state={state}
      onLoadMore={onLoadMore}
      filters={<DimensionalCollectionFilterBar
        kind="Relationship"
        filters={filters}
        onApplyFilters={onApplyFilters}
      />}
    />
  );
}

function DimensionalCollectionFilterBar<T extends DimensionalAttributeFilters>({
  kind,
  filters,
  onApplyFilters,
}: {
  kind: "Attribute" | "Relationship";
  filters: T;
  onApplyFilters: (filters: T) => void;
}) {
  const form = useForm({
    defaultValues: {
      namePrefix: filters.namePrefix ?? "",
      dimensionalEntityId: filters.dimensionalEntityId
        ? String(filters.dimensionalEntityId)
        : "",
      status: filters.status ?? "",
      locked: filters.locked === undefined ? "" : String(filters.locked),
    },
    onSubmit: ({ value }) => onApplyFilters({
      ...(value.namePrefix ? { namePrefix: value.namePrefix } : {}),
      ...(value.dimensionalEntityId
        ? { dimensionalEntityId: Number(value.dimensionalEntityId) }
        : {}),
      ...(value.status ? { status: value.status as NonNullable<DimensionalFilters["status"]> } : {}),
      ...(value.locked ? { locked: value.locked === "true" } : {}),
    } as T),
  });
  return (
    <form
      className="workflow-filterbar dimensional-filterbar has-entity-filter"
      aria-label={`Filter Dimensional ${kind}s`}
      onSubmit={(event) => {
        event.preventDefault();
        event.stopPropagation();
        void form.handleSubmit();
      }}
    >
      <form.Field name="namePrefix">
        {(field) => (
          <label>
            <span>{kind} name prefix</span>
            <input
              aria-label={`${kind} name prefix`}
              value={field.state.value}
              onBlur={field.handleBlur}
              onChange={(event) => field.handleChange(event.target.value)}
            />
          </label>
        )}
      </form.Field>
      <form.Field name="dimensionalEntityId">
        {(field) => (
          <label>
            <span>Object ID</span>
            <input
              aria-label={`${kind} Object ID`}
              type="number"
              min="1"
              step="1"
              value={field.state.value}
              onBlur={field.handleBlur}
              onChange={(event) => field.handleChange(event.target.value)}
            />
          </label>
        )}
      </form.Field>
      <form.Field name="status">
        {(field) => (
          <label>
            <span>{kind} status</span>
            <select
              aria-label={`${kind} status`}
              value={field.state.value}
              onChange={(event) => field.handleChange(event.target.value)}
            >
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
            <span>{kind} lock</span>
            <select
              aria-label={`${kind} lock`}
              value={field.state.value}
              onChange={(event) => field.handleChange(event.target.value)}
            >
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
            onApplyFilters({} as T);
          }}
        >
          Clear
        </button>
        <button className="button button-secondary button-small" type="submit">
          Apply {kind} filters
        </button>
      </div>
    </form>
  );
}

function DimensionalLedgerSurface<T>({
  tableLabel,
  items,
  columns,
  state,
  filters,
  onLoadMore,
}: {
  tableLabel: string;
  items: T[];
  columns: ColumnDef<T>[];
  state: DimensionalLedgerState;
  filters: ReactNode;
  onLoadMore: () => void;
}) {
  const table = useReactTable({ data: items, columns, getCoreRowModel: getCoreRowModel() });
  return (
    <section className="workflow-surface" aria-label={tableLabel}>
      {filters}
      {state.isLoading ? (
        <div className="surface-state" aria-busy="true">Loading {tableLabel}…</div>
      ) : state.isDenied ? (
        <div className="surface-state is-error" role="alert">
          You do not have permission to view {tableLabel}.
        </div>
      ) : state.isError ? (
        <div className="surface-state is-error" role="alert">{tableLabel} could not be loaded.</div>
      ) : state.revisionMismatch ? (
        <div className="surface-state is-error" role="alert">
          The Model changed while {tableLabel} were loading. Refresh to reconcile revisions.
        </div>
      ) : items.length === 0 ? (
        <div className="empty-state compact">No {tableLabel} match these filters.</div>
      ) : (
        <div className="workflow-table-scroll table-scroll">
          <table aria-label={tableLabel}>
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
                {state.isLoadingMore ? "Loading…" : `Load more ${tableLabel}`}
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
