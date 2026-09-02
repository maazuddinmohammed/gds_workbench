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
  AssertionDocument,
  AssertionDocumentFilters,
  AssertionRecord,
  AssertionRecordFilters,
} from "./api";
import { formatRequiredDateTime as formatDateTime } from "../../shared/presentation";

interface LedgerState {
  isLoading: boolean;
  isError: boolean;
  revisionMismatch: boolean;
  hasMore: boolean;
  isLoadingMore: boolean;
}

export function AssertionDocumentsLedger({
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
  items: AssertionDocument[];
  filters: AssertionDocumentFilters;
  state: LedgerState;
  onApplyFilters: (filters: AssertionDocumentFilters) => void;
  onLoadMore: () => void;
}) {
  const form = useForm({
    defaultValues: {
      sourceSystemId: filters.sourceSystemId ? String(filters.sourceSystemId) : "",
      sourceSystemCode: filters.sourceSystemCode ?? "",
      active: filters.active === undefined ? "" : String(filters.active),
      namePrefix: filters.namePrefix ?? "",
    },
    onSubmit: ({ value }) => onApplyFilters({
      ...(value.sourceSystemId ? { sourceSystemId: Number(value.sourceSystemId) } : {}),
      ...(value.sourceSystemCode ? { sourceSystemCode: value.sourceSystemCode } : {}),
      ...(value.active ? { active: value.active === "true" } : {}),
      ...(value.namePrefix ? { namePrefix: value.namePrefix } : {}),
    }),
  });
  const columns = useMemo<ColumnDef<AssertionDocument>[]>(() => [
    {
      accessorKey: "modeling_assertion_document_name",
      header: "Document",
      cell: ({ row }) => (
        <span className="endpoint-cell">
          <strong>{row.original.modeling_assertion_document_name}</strong>
          <span>{row.original.modeling_assertion_document_type ?? "Unclassified"}</span>
        </span>
      ),
    },
    {
      id: "system",
      header: "Source System",
      cell: ({ row }) => row.original.source_system?.system_code ?? "Not assigned",
    },
    {
      id: "tenant",
      header: "Source Tenant",
      cell: ({ row }) => row.original.source_tenant?.tenant_code ?? "Not assigned",
    },
    { accessorKey: "record_count", header: "Records" },
    { accessorKey: "locked_record_count", header: "Locked" },
    {
      accessorKey: "is_active",
      header: "State",
      cell: ({ getValue }) => (
        <span className={`status-badge ${getValue<boolean>() ? "is-success" : "is-neutral"}`}>
          {getValue<boolean>() ? "Active" : "Inactive"}
        </span>
      ),
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
          aria-label={`Open Assertion Document ${row.original.modeling_assertion_document_id}`}
          to="/tenants/$tenantId/models/$modelId/assertions/documents/$documentId"
          params={{
            tenantId: String(tenantId),
            modelId: String(modelId),
            documentId: String(row.original.modeling_assertion_document_id),
          }}
        >
          Show details
        </Link>
      ),
    },
  ], [modelId, tenantId]);
  return (
    <AssertionLedgerSurface
      tableLabel="Assertion Documents"
      items={items}
      columns={columns}
      state={state}
      onLoadMore={onLoadMore}
      loadingLabel="Loading Assertion Documents…"
      errorLabel="Assertion Documents could not be loaded."
      revisionLabel="The Model changed while Assertion Documents were loading. Refresh to reconcile revisions."
      emptyLabel="No Assertion Documents match these filters."
      filters={(
        <form
          className="workflow-filterbar assertion-document-filterbar"
          aria-label="Filter Assertion Documents"
          onSubmit={(event) => {
            event.preventDefault();
            event.stopPropagation();
            void form.handleSubmit();
          }}
        >
          <form.Field name="namePrefix">
            {(field) => <TextFilter label="Document name prefix" field={field} />}
          </form.Field>
          <form.Field name="sourceSystemId">
            {(field) => <NumberFilter label="Source System ID" field={field} />}
          </form.Field>
          <form.Field name="sourceSystemCode">
            {(field) => <TextFilter label="Source System code" field={field} />}
          </form.Field>
          <form.Field name="active">
            {(field) => (
              <label>
                <span>Document activity</span>
                <select
                  aria-label="Document activity"
                  value={field.state.value}
                  onBlur={field.handleBlur}
                  onChange={(event) => field.handleChange(event.target.value)}
                >
                  <option value="">All activity states</option>
                  <option value="true">Active</option>
                  <option value="false">Inactive</option>
                </select>
              </label>
            )}
          </form.Field>
          <FilterActions
            applyLabel="Apply Document filters"
            onClear={() => {
              form.reset();
              onApplyFilters({});
            }}
          />
        </form>
      )}
    />
  );
}

export function AssertionRecordsLedger({
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
  items: AssertionRecord[];
  filters: AssertionRecordFilters;
  state: LedgerState;
  onApplyFilters: (filters: AssertionRecordFilters) => void;
  onLoadMore: () => void;
}) {
  const form = useForm({
    defaultValues: {
      documentId: filters.documentId ? String(filters.documentId) : "",
      documentName: filters.documentName ?? "",
      sourceSystemId: filters.sourceSystemId ? String(filters.sourceSystemId) : "",
      sourceSystemCode: filters.sourceSystemCode ?? "",
      status: filters.status ?? "",
      locked: filters.locked === undefined ? "" : String(filters.locked),
      applicableLayer: filters.applicableLayer ?? "",
      keyPrefix: filters.keyPrefix ?? "",
    },
    onSubmit: ({ value }) => onApplyFilters({
      ...(value.documentId ? { documentId: Number(value.documentId) } : {}),
      ...(value.documentName ? { documentName: value.documentName } : {}),
      ...(value.sourceSystemId ? { sourceSystemId: Number(value.sourceSystemId) } : {}),
      ...(value.sourceSystemCode ? { sourceSystemCode: value.sourceSystemCode } : {}),
      ...(value.status ? { status: value.status as NonNullable<AssertionRecordFilters["status"]> } : {}),
      ...(value.locked ? { locked: value.locked === "true" } : {}),
      ...(value.applicableLayer
        ? { applicableLayer: value.applicableLayer as NonNullable<AssertionRecordFilters["applicableLayer"]> }
        : {}),
      ...(value.keyPrefix ? { keyPrefix: value.keyPrefix } : {}),
    }),
  });
  const columns = useMemo<ColumnDef<AssertionRecord>[]>(() => [
    {
      accessorKey: "modeling_assertion_record_key",
      header: "Assertion key",
      cell: ({ row }) => (
        <span className="endpoint-cell">
          <strong>{row.original.modeling_assertion_record_key}</strong>
          <span>{humanize(row.original.modeling_assertion_record_type)}</span>
        </span>
      ),
    },
    {
      id: "document",
      header: "Document",
      cell: ({ row }) => row.original.document.modeling_assertion_document_name,
    },
    {
      id: "layers",
      header: "Applicable layers",
      cell: ({ row }) => (
        <span className="chip-list">
          {row.original.modeling_assertion_applicable_layers.map((layer) => (
            <span key={layer}>{humanize(layer)}</span>
          ))}
        </span>
      ),
    },
    {
      accessorKey: "modeling_assertion_confidence",
      header: "Confidence",
      cell: ({ getValue }) => getValue<string | null>() ?? "Not set",
    },
    {
      accessorKey: "modeling_assertion_record_status",
      header: "Status",
      cell: ({ getValue }) => humanize(getValue<string>()),
    },
    {
      accessorKey: "modeling_assertion_record_is_locked",
      header: "Lock",
      cell: ({ getValue }) => getValue<boolean>() ? "Locked" : "Open",
    },
    {
      id: "action",
      header: "",
      cell: ({ row }) => (
        <Link
          className="text-action"
          aria-label={`Open Assertion Record ${row.original.modeling_assertion_record_id}`}
          to="/tenants/$tenantId/models/$modelId/assertions/records/$recordId"
          params={{
            tenantId: String(tenantId),
            modelId: String(modelId),
            recordId: String(row.original.modeling_assertion_record_id),
          }}
        >
          Show details
        </Link>
      ),
    },
  ], [modelId, tenantId]);
  return (
    <AssertionLedgerSurface
      tableLabel="Assertion Records"
      items={items}
      columns={columns}
      state={state}
      onLoadMore={onLoadMore}
      loadingLabel="Loading Assertion Records…"
      errorLabel="Assertion Records could not be loaded."
      revisionLabel="The Model changed while Assertion Records were loading. Refresh to reconcile revisions."
      emptyLabel="No Assertion Records match these filters."
      filters={(
        <form
          className="workflow-filterbar assertion-record-filterbar"
          aria-label="Filter Assertion Records"
          onSubmit={(event) => {
            event.preventDefault();
            event.stopPropagation();
            void form.handleSubmit();
          }}
        >
          <form.Field name="keyPrefix">
            {(field) => <TextFilter label="Record key prefix" field={field} />}
          </form.Field>
          <form.Field name="documentId">
            {(field) => <NumberFilter label="Document ID" field={field} />}
          </form.Field>
          <form.Field name="documentName">
            {(field) => <TextFilter label="Document name" field={field} />}
          </form.Field>
          <form.Field name="sourceSystemId">
            {(field) => <NumberFilter label="Source System ID" field={field} />}
          </form.Field>
          <form.Field name="sourceSystemCode">
            {(field) => <TextFilter label="Source System code" field={field} />}
          </form.Field>
          <form.Field name="status">
            {(field) => (
              <label>
                <span>Record status</span>
                <select aria-label="Record status" value={field.state.value} onChange={(event) => field.handleChange(event.target.value)}>
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
                <span>Record lock</span>
                <select aria-label="Record lock" value={field.state.value} onChange={(event) => field.handleChange(event.target.value)}>
                  <option value="">All lock states</option>
                  <option value="true">Locked</option>
                  <option value="false">Open</option>
                </select>
              </label>
            )}
          </form.Field>
          <form.Field name="applicableLayer">
            {(field) => (
              <label>
                <span>Applicable layer</span>
                <select aria-label="Applicable layer" value={field.state.value} onChange={(event) => field.handleChange(event.target.value)}>
                  <option value="">All layers</option>
                  <option value="analysis">Analysis</option>
                  <option value="conceptual">Conceptual</option>
                  <option value="logical">Logical</option>
                  <option value="dimensional">Dimensional</option>
                  <option value="mapping">Mapping</option>
                </select>
              </label>
            )}
          </form.Field>
          <FilterActions
            applyLabel="Apply Record filters"
            onClear={() => {
              form.reset();
              onApplyFilters({});
            }}
          />
        </form>
      )}
    />
  );
}

function AssertionLedgerSurface<T>({
  tableLabel,
  items,
  columns,
  state,
  filters,
  loadingLabel,
  errorLabel,
  revisionLabel,
  emptyLabel,
  onLoadMore,
}: {
  tableLabel: string;
  items: T[];
  columns: ColumnDef<T>[];
  state: LedgerState;
  filters: React.ReactNode;
  loadingLabel: string;
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

function TextFilter({ label, field }: { label: string; field: TextField }) {
  return (
    <label>
      <span>{label}</span>
      <input
        aria-label={label}
        value={field.state.value}
        onBlur={field.handleBlur}
        onChange={(event) => field.handleChange(event.target.value)}
      />
    </label>
  );
}

function NumberFilter({ label, field }: { label: string; field: TextField }) {
  return (
    <label>
      <span>{label}</span>
      <input
        aria-label={label}
        inputMode="numeric"
        pattern="[0-9]*"
        value={field.state.value}
        onBlur={field.handleBlur}
        onChange={(event) => field.handleChange(event.target.value.replace(/[^0-9]/g, ""))}
      />
    </label>
  );
}

interface TextField {
  state: { value: string };
  handleBlur: () => void;
  handleChange: (value: string) => void;
}

function FilterActions({ applyLabel, onClear }: { applyLabel: string; onClear: () => void }) {
  return (
    <div className="workflow-filter-actions">
      <button className="button button-secondary button-small" type="button" onClick={onClear}>Clear</button>
      <button className="button button-secondary button-small" type="submit">{applyLabel}</button>
    </div>
  );
}

function humanize(value: string): string {
  return value.replaceAll("_", " ").replace(/^./, (character) => character.toLocaleUpperCase());
}
