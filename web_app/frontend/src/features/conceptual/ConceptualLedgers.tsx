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
  ConceptualFilters,
  ConceptualObject,
  ConceptualRelationship,
} from "./api";
import { formatRequiredDateTime as formatDateTime } from "../../shared/presentation";

interface LedgerState {
  isLoading: boolean;
  isError: boolean;
  isDenied: boolean;
  revisionMismatch: boolean;
  hasMore: boolean;
  isLoadingMore: boolean;
}

export function ConceptualObjectsLedger({
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
  items: ConceptualObject[];
  filters: ConceptualFilters;
  state: LedgerState;
  onApplyFilters: (filters: ConceptualFilters) => void;
  onLoadMore: () => void;
}) {
  const columns = useMemo<ColumnDef<ConceptualObject>[]>(() => [
    {
      accessorKey: "conceptual_object_name",
      header: "Conceptual Object",
      cell: ({ row }) => (
        <span className="endpoint-cell">
          <strong>{row.original.conceptual_object_name}</strong>
          <span>{humanize(row.original.conceptual_object_type)}</span>
        </span>
      ),
    },
    {
      accessorKey: "conceptual_object_confidence",
      header: "Confidence",
      cell: ({ getValue }) => <ConfidenceBadge confidence={getValue<string>()} />,
    },
    {
      accessorKey: "conceptual_object_status",
      header: "Status",
      cell: ({ getValue }) => humanize(getValue<string>()),
    },
    {
      accessorKey: "conceptual_object_is_locked",
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
          aria-label={`Open Conceptual Object ${row.original.conceptual_object_id}`}
          to="/tenants/$tenantId/models/$modelId/conceptual/objects/$objectId"
          params={{
            tenantId: String(tenantId),
            modelId: String(modelId),
            objectId: String(row.original.conceptual_object_id),
          }}
        >
          Show details
        </Link>
      ),
    },
  ], [modelId, tenantId]);
  return (
    <ConceptualLedgerSurface
      tableLabel="Conceptual Objects"
      items={items}
      columns={columns}
      state={state}
      onLoadMore={onLoadMore}
      loadingLabel="Loading Conceptual Objects…"
      deniedLabel="You do not have permission to view Conceptual Objects."
      errorLabel="Conceptual Objects could not be loaded."
      revisionLabel="The Model changed while Conceptual Objects were loading. Refresh to reconcile revisions."
      emptyLabel="No Conceptual Objects match these filters."
      filters={(
        <ConceptualFilterBar
          kind="Object"
          filters={filters}
          onApplyFilters={onApplyFilters}
        />
      )}
    />
  );
}

export function ConceptualRelationshipsLedger({
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
  items: ConceptualRelationship[];
  filters: ConceptualFilters;
  state: LedgerState;
  onApplyFilters: (filters: ConceptualFilters) => void;
  onLoadMore: () => void;
}) {
  const columns = useMemo<ColumnDef<ConceptualRelationship>[]>(() => [
    {
      accessorKey: "conceptual_relationship_name",
      header: "Relationship",
      cell: ({ row }) => (
        <span className="endpoint-cell">
          <strong>{row.original.conceptual_relationship_name}</strong>
          <span>{humanize(row.original.conceptual_relationship_type)}</span>
        </span>
      ),
    },
    { accessorKey: "from_conceptual_object_name", header: "From" },
    { accessorKey: "to_conceptual_object_name", header: "To" },
    {
      accessorKey: "conceptual_relationship_cardinality",
      header: "Cardinality",
      cell: ({ getValue }) => humanize(getValue<string>()),
    },
    {
      accessorKey: "conceptual_relationship_confidence",
      header: "Confidence",
      cell: ({ getValue }) => <ConfidenceBadge confidence={getValue<string>()} />,
    },
    {
      accessorKey: "conceptual_relationship_status",
      header: "Status",
      cell: ({ getValue }) => humanize(getValue<string>()),
    },
    {
      accessorKey: "conceptual_relationship_is_locked",
      header: "Lock",
      cell: ({ getValue }) => getValue<boolean>() ? "Locked" : "Open",
    },
    {
      id: "action",
      header: "",
      cell: ({ row }) => (
        <Link
          className="text-action"
          aria-label={`Open Conceptual Relationship ${row.original.conceptual_relationship_id}`}
          to="/tenants/$tenantId/models/$modelId/conceptual/relationships/$relationshipId"
          params={{
            tenantId: String(tenantId),
            modelId: String(modelId),
            relationshipId: String(row.original.conceptual_relationship_id),
          }}
        >
          Show details
        </Link>
      ),
    },
  ], [modelId, tenantId]);
  return (
    <ConceptualLedgerSurface
      tableLabel="Conceptual Relationships"
      items={items}
      columns={columns}
      state={state}
      onLoadMore={onLoadMore}
      loadingLabel="Loading Conceptual Relationships…"
      deniedLabel="You do not have permission to view Conceptual Relationships."
      errorLabel="Conceptual Relationships could not be loaded."
      revisionLabel="The Model changed while Conceptual Relationships were loading. Refresh to reconcile revisions."
      emptyLabel="No Conceptual Relationships match these filters."
      filters={(
        <ConceptualFilterBar
          kind="Relationship"
          filters={filters}
          onApplyFilters={onApplyFilters}
        />
      )}
    />
  );
}

function ConceptualFilterBar({
  kind,
  filters,
  onApplyFilters,
}: {
  kind: "Object" | "Relationship";
  filters: ConceptualFilters;
  onApplyFilters: (filters: ConceptualFilters) => void;
}) {
  const form = useForm({
    defaultValues: {
      namePrefix: filters.namePrefix ?? "",
      status: filters.status ?? "",
      locked: filters.locked === undefined ? "" : String(filters.locked),
    },
    onSubmit: ({ value }) => onApplyFilters({
      ...(value.namePrefix ? { namePrefix: value.namePrefix } : {}),
      ...(value.status ? { status: value.status as NonNullable<ConceptualFilters["status"]> } : {}),
      ...(value.locked ? { locked: value.locked === "true" } : {}),
    }),
  });
  return (
    <form
      className="workflow-filterbar conceptual-filterbar"
      aria-label={`Filter Conceptual ${kind}s`}
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
            onApplyFilters({});
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

function ConceptualLedgerSurface<T>({
  tableLabel,
  items,
  columns,
  state,
  filters,
  loadingLabel,
  deniedLabel,
  errorLabel,
  revisionLabel,
  emptyLabel,
  onLoadMore,
}: {
  tableLabel: string;
  items: T[];
  columns: ColumnDef<T>[];
  state: LedgerState;
  filters: ReactNode;
  loadingLabel: string;
  deniedLabel: string;
  errorLabel: string;
  revisionLabel: string;
  emptyLabel: string;
  onLoadMore: () => void;
}) {
  const table = useReactTable({ data: items, columns, getCoreRowModel: getCoreRowModel() });
  return (
    <section className="workflow-surface" aria-label={tableLabel}>
      {filters}
      {state.isLoading ? (
        <div className="surface-state" aria-busy="true">{loadingLabel}</div>
      ) : state.isDenied ? (
        <div className="surface-state is-error" role="alert">{deniedLabel}</div>
      ) : state.isError ? (
        <div className="surface-state is-error" role="alert">{errorLabel}</div>
      ) : state.revisionMismatch ? (
        <div className="surface-state is-error" role="alert">{revisionLabel}</div>
      ) : items.length === 0 ? (
        <div className="empty-state compact">{emptyLabel}</div>
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

function ConfidenceBadge({ confidence }: { confidence: string }) {
  return (
    <span className={`status-badge confidence-${confidence}`}>
      {humanize(confidence)}
    </span>
  );
}

function humanize(value: string): string {
  return value.replaceAll("_", " ").replace(/^./, (character) => character.toLocaleUpperCase());
}
