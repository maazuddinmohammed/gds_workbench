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
  LogicalAttribute,
  LogicalAttributeFilters,
  LogicalEntity,
  LogicalEntityFilters,
  LogicalFilters,
  LogicalRelationship,
  LogicalRelationshipFilters,
  LogicalSubmodel,
} from "./api";
import { formatRequiredDateTime as formatDateTime } from "../../shared/presentation";

interface LedgerState {
  isLoading: boolean;
  isError: boolean;
  revisionMismatch: boolean;
  hasMore: boolean;
  isLoadingMore: boolean;
}

export function LogicalEntitiesLedger({
  tenantId,
  modelId,
  items,
  filters,
  submodels,
  submodelsState,
  state,
  onApplyFilters,
  onLoadMore,
}: {
  tenantId: number;
  modelId: number;
  items: LogicalEntity[];
  filters: LogicalEntityFilters;
  submodels: LogicalSubmodel[];
  submodelsState: "loading" | "error" | "revision_mismatch" | "ready";
  state: LedgerState;
  onApplyFilters: (filters: LogicalEntityFilters) => void;
  onLoadMore: () => void;
}) {
  const columns = useMemo<ColumnDef<LogicalEntity>[]>(() => [
    {
      accessorKey: "logical_entity_name",
      header: "Logical Entity",
      cell: ({ row }) => (
        <span className="endpoint-cell">
          <strong>{row.original.logical_entity_name}</strong>
          <span>{humanize(row.original.logical_entity_type)}</span>
        </span>
      ),
    },
    { accessorKey: "logical_entity_dependency_order", header: "Order" },
    {
      accessorKey: "logical_entity_confidence",
      header: "Confidence",
      cell: ({ getValue }) => (
        <span className={`status-badge confidence-${getValue<string>()}`}>
          {humanize(getValue<string>())}
        </span>
      ),
    },
    {
      accessorKey: "logical_entity_status",
      header: "Status",
      cell: ({ getValue }) => humanize(getValue<string>()),
    },
    {
      accessorKey: "logical_entity_is_locked",
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
          aria-label={`Open Logical Entity ${row.original.logical_entity_id}`}
          to="/tenants/$tenantId/models/$modelId/logical/entities/$entityId"
          params={{
            tenantId: String(tenantId),
            modelId: String(modelId),
            entityId: String(row.original.logical_entity_id),
          }}
        >
          Show details
        </Link>
      ),
    },
  ], [modelId, tenantId]);
  const table = useReactTable({ data: items, columns, getCoreRowModel: getCoreRowModel() });

  return (
    <section className="workflow-surface" aria-label="Logical Entities">
      <LogicalEntityFilterBar
        filters={filters}
        submodels={submodels}
        submodelsState={submodelsState}
        onApplyFilters={onApplyFilters}
      />
      {state.isLoading ? (
        <div className="surface-state" aria-busy="true">Loading Logical Entities…</div>
      ) : state.isError ? (
        <div className="surface-state is-error" role="alert">
          Logical Entities could not be loaded.
        </div>
      ) : state.revisionMismatch ? (
        <div className="surface-state is-error" role="alert">
          The Model changed while Logical Entities were loading. Refresh to reconcile revisions.
        </div>
      ) : items.length === 0 ? (
        <div className="empty-state compact">No Logical Entities match these filters.</div>
      ) : (
        <div className="workflow-table-scroll table-scroll">
          <table aria-label="Logical Entities">
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
                {state.isLoadingMore ? "Loading…" : "Load more Logical Entities"}
              </button>
            </div>
          ) : null}
        </div>
      )}
    </section>
  );
}

function LogicalEntityFilterBar({
  filters,
  submodels,
  submodelsState,
  onApplyFilters,
}: {
  filters: LogicalEntityFilters;
  submodels: LogicalSubmodel[];
  submodelsState: "loading" | "error" | "revision_mismatch" | "ready";
  onApplyFilters: (filters: LogicalEntityFilters) => void;
}) {
  const form = useForm({
    defaultValues: {
      namePrefix: filters.namePrefix ?? "",
      logicalSubmodelId: filters.logicalSubmodelId
        ? String(filters.logicalSubmodelId)
        : "",
      status: filters.status ?? "",
      locked: filters.locked === undefined ? "" : String(filters.locked),
    },
    onSubmit: ({ value }) => onApplyFilters({
      ...(value.namePrefix ? { namePrefix: value.namePrefix } : {}),
      ...(value.logicalSubmodelId
        ? { logicalSubmodelId: Number(value.logicalSubmodelId) }
        : {}),
      ...(value.status ? { status: value.status as NonNullable<LogicalFilters["status"]> } : {}),
      ...(value.locked ? { locked: value.locked === "true" } : {}),
    }),
  });
  return (
    <form
      className="workflow-filterbar logical-filterbar logical-entity-filterbar"
      aria-label="Filter Logical Entities"
      onSubmit={(event) => {
        event.preventDefault();
        event.stopPropagation();
        void form.handleSubmit();
      }}
    >
      <form.Field name="namePrefix">
        {(field) => (
          <label>
            <span>Entity name prefix</span>
            <input
              aria-label="Entity name prefix"
              value={field.state.value}
              onBlur={field.handleBlur}
              onChange={(event) => field.handleChange(event.target.value)}
            />
          </label>
        )}
      </form.Field>
      <form.Field name="logicalSubmodelId">
        {(field) => (
          <label>
            <span>Entity Submodel</span>
            <select
              aria-label="Entity Submodel"
              value={field.state.value}
              disabled={submodelsState !== "ready"}
              onChange={(event) => field.handleChange(event.target.value)}
            >
              <option value="">
                {submodelsState === "loading"
                  ? "Loading Submodels…"
                  : submodelsState === "error"
                    ? "Submodels unavailable"
                    : submodelsState === "revision_mismatch"
                      ? "Refresh Submodels"
                      : "All Submodels"}
              </option>
              {submodels.map((submodel) => (
                <option
                  key={submodel.logical_submodel_id}
                  value={String(submodel.logical_submodel_id)}
                >
                  {submodel.logical_submodel_name}
                </option>
              ))}
            </select>
          </label>
        )}
      </form.Field>
      <form.Field name="status">
        {(field) => (
          <label>
            <span>Entity status</span>
            <select
              aria-label="Entity status"
              value={field.state.value}
              onChange={(event) => field.handleChange(event.target.value)}
            >
              <option value="">All statuses</option>
              <option value="active">Active</option>
              <option value="needs_review">Needs review</option>
              <option value="inactive">Inactive</option>
              <option value="deprecated">Deprecated</option>
            </select>
          </label>
        )}
      </form.Field>
      <form.Field name="locked">
        {(field) => (
          <label>
            <span>Entity lock</span>
            <select
              aria-label="Entity lock"
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
          Apply Entity filters
        </button>
      </div>
    </form>
  );
}

export function LogicalAttributesLedger({
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
  items: LogicalAttribute[];
  filters: LogicalAttributeFilters;
  state: LedgerState;
  onApplyFilters: (filters: LogicalAttributeFilters) => void;
  onLoadMore: () => void;
}) {
  const columns = useMemo<ColumnDef<LogicalAttribute>[]>(() => [
    {
      accessorKey: "logical_attribute_name",
      header: "Logical Attribute",
      cell: ({ row }) => (
        <span className="endpoint-cell">
          <strong>{row.original.logical_attribute_name}</strong>
          <span>{row.original.logical_attribute_data_type}</span>
        </span>
      ),
    },
    { accessorKey: "logical_entity_name", header: "Entity" },
    { accessorKey: "logical_attribute_ordinal_position", header: "Ordinal" },
    {
      id: "keys",
      header: "Key role",
      cell: ({ row }) => row.original.logical_attribute_is_primary_key
        ? "Primary"
        : row.original.logical_attribute_is_natural_key
          ? "Natural"
          : row.original.logical_attribute_is_surrogate_key
            ? "Surrogate"
            : "—",
    },
    {
      accessorKey: "logical_attribute_is_nullable",
      header: "Nullable",
      cell: ({ getValue }) => getValue<boolean>() ? "Yes" : "No",
    },
    {
      accessorKey: "logical_attribute_status",
      header: "Status",
      cell: ({ getValue }) => humanize(getValue<string>()),
    },
    {
      accessorKey: "logical_attribute_is_locked",
      header: "Lock",
      cell: ({ getValue }) => getValue<boolean>() ? "Locked" : "Open",
    },
    {
      id: "action",
      header: "",
      cell: ({ row }) => (
        <Link
          className="text-action"
          aria-label={`Open Logical Attribute ${row.original.logical_attribute_id}`}
          to="/tenants/$tenantId/models/$modelId/logical/attributes/$attributeId"
          params={{
            tenantId: String(tenantId),
            modelId: String(modelId),
            attributeId: String(row.original.logical_attribute_id),
          }}
        >
          Show details
        </Link>
      ),
    },
  ], [modelId, tenantId]);
  return (
    <LogicalLedgerSurface
      tableLabel="Logical Attributes"
      items={items}
      columns={columns}
      state={state}
      onLoadMore={onLoadMore}
      filters={(
        <LogicalCollectionFilterBar
          kind="Attribute"
          filters={filters}
          includeEntity
          onApplyFilters={onApplyFilters}
        />
      )}
    />
  );
}

export function LogicalRelationshipsLedger({
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
  items: LogicalRelationship[];
  filters: LogicalRelationshipFilters;
  state: LedgerState;
  onApplyFilters: (filters: LogicalRelationshipFilters) => void;
  onLoadMore: () => void;
}) {
  const columns = useMemo<ColumnDef<LogicalRelationship>[]>(() => [
    { accessorKey: "logical_relationship_name", header: "Relationship" },
    {
      id: "from",
      header: "From",
      cell: ({ row }) => (
        <span className="endpoint-cell">
          <strong>{row.original.from_logical_entity_name}</strong>
          <span>{row.original.from_logical_attribute_name}</span>
        </span>
      ),
    },
    {
      id: "to",
      header: "To",
      cell: ({ row }) => (
        <span className="endpoint-cell">
          <strong>{row.original.to_logical_entity_name}</strong>
          <span>{row.original.to_logical_attribute_name}</span>
        </span>
      ),
    },
    {
      accessorKey: "logical_relationship_cardinality",
      header: "Cardinality",
      cell: ({ getValue }) => humanize(getValue<string>()),
    },
    {
      accessorKey: "logical_relationship_confidence",
      header: "Confidence",
      cell: ({ getValue }) => (
        <span className={`status-badge confidence-${getValue<string>()}`}>
          {humanize(getValue<string>())}
        </span>
      ),
    },
    {
      accessorKey: "logical_relationship_status",
      header: "Status",
      cell: ({ getValue }) => humanize(getValue<string>()),
    },
    {
      id: "action",
      header: "",
      cell: ({ row }) => (
        <Link
          className="text-action"
          aria-label={`Open Logical Relationship ${row.original.logical_relationship_id}`}
          to="/tenants/$tenantId/models/$modelId/logical/relationships/$relationshipId"
          params={{
            tenantId: String(tenantId),
            modelId: String(modelId),
            relationshipId: String(row.original.logical_relationship_id),
          }}
        >
          Show details
        </Link>
      ),
    },
  ], [modelId, tenantId]);
  return (
    <LogicalLedgerSurface
      tableLabel="Logical Relationships"
      items={items}
      columns={columns}
      state={state}
      onLoadMore={onLoadMore}
      filters={(
        <LogicalCollectionFilterBar
          kind="Relationship"
          filters={filters}
          includeEntity
          onApplyFilters={onApplyFilters}
        />
      )}
    />
  );
}

export function LogicalSubmodelsLedger({
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
  items: LogicalSubmodel[];
  filters: LogicalFilters;
  state: LedgerState;
  onApplyFilters: (filters: LogicalFilters) => void;
  onLoadMore: () => void;
}) {
  const columns = useMemo<ColumnDef<LogicalSubmodel>[]>(() => [
    { accessorKey: "logical_submodel_name", header: "Logical Submodel" },
    { accessorKey: "entity_count", header: "Entities" },
    {
      accessorKey: "logical_submodel_status",
      header: "Status",
      cell: ({ getValue }) => humanize(getValue<string>()),
    },
    {
      accessorKey: "logical_submodel_is_locked",
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
          aria-label={`Open Logical Submodel ${row.original.logical_submodel_id}`}
          to="/tenants/$tenantId/models/$modelId/logical/submodels/$submodelId"
          params={{
            tenantId: String(tenantId),
            modelId: String(modelId),
            submodelId: String(row.original.logical_submodel_id),
          }}
        >
          Show details
        </Link>
      ),
    },
  ], [modelId, tenantId]);
  return (
    <LogicalLedgerSurface
      tableLabel="Logical Submodels"
      items={items}
      columns={columns}
      state={state}
      onLoadMore={onLoadMore}
      filters={(
        <LogicalCollectionFilterBar
          kind="Submodel"
          filters={filters}
          onApplyFilters={onApplyFilters}
        />
      )}
    />
  );
}

function LogicalCollectionFilterBar<T extends LogicalFilters>({
  kind,
  filters,
  includeEntity = false,
  onApplyFilters,
}: {
  kind: "Attribute" | "Relationship" | "Submodel";
  filters: T;
  includeEntity?: boolean;
  onApplyFilters: (filters: T) => void;
}) {
  const filterWithEntity = filters as LogicalAttributeFilters;
  const form = useForm({
    defaultValues: {
      namePrefix: filters.namePrefix ?? "",
      status: filters.status ?? "",
      locked: filters.locked === undefined ? "" : String(filters.locked),
      logicalEntityId: filterWithEntity.logicalEntityId
        ? String(filterWithEntity.logicalEntityId)
        : "",
    },
    onSubmit: ({ value }) => onApplyFilters({
      ...(value.namePrefix ? { namePrefix: value.namePrefix } : {}),
      ...(value.status ? { status: value.status as NonNullable<LogicalFilters["status"]> } : {}),
      ...(value.locked ? { locked: value.locked === "true" } : {}),
      ...(includeEntity && value.logicalEntityId
        ? { logicalEntityId: Number(value.logicalEntityId) }
        : {}),
    } as T),
  });
  return (
    <form
      className={`workflow-filterbar logical-filterbar${includeEntity ? " has-entity-filter" : ""}`}
      aria-label={`Filter Logical ${kind}s`}
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
      {includeEntity ? (
        <form.Field name="logicalEntityId">
          {(field) => (
            <label>
              <span>Entity ID</span>
              <input
                aria-label={`${kind} Entity ID`}
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
      ) : null}
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
              <option value="needs_review">Needs review</option>
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

function LogicalLedgerSurface<T>({
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
  state: LedgerState;
  filters: ReactNode;
  onLoadMore: () => void;
}) {
  const table = useReactTable({ data: items, columns, getCoreRowModel: getCoreRowModel() });
  return (
    <section className="workflow-surface" aria-label={tableLabel}>
      {filters}
      {state.isLoading ? (
        <div className="surface-state" aria-busy="true">Loading {tableLabel}…</div>
      ) : state.isError ? (
        <div className="surface-state is-error" role="alert">
          {tableLabel} could not be loaded.
        </div>
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
