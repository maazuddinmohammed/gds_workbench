import { useMemo, useState } from "react";
import { useForm } from "@tanstack/react-form";
import {
  flexRender,
  getCoreRowModel,
  useReactTable,
  type ColumnDef,
} from "@tanstack/react-table";

import type {
  MetadataDatasetDescription,
  MetadataFilters,
  MetadataRow,
  MetadataRowSchema,
} from "./api";
import {
  metadataFieldLabel,
  metadataPropertySchema,
  metadataValueText,
} from "./api";

export interface MetadataLedgerState {
  isLoading: boolean;
  isFetching: boolean;
  isDenied: boolean;
  isError: boolean;
  hasNext: boolean;
  hasPrevious: boolean;
}

export function MetadataLedger({
  descriptor,
  items,
  filters,
  rowSchema,
  state,
  canAdd,
  addDisabledReason,
  onApplyFilters,
  onOpenRow,
  onAdd,
  onNext,
  onPrevious,
}: {
  descriptor: MetadataDatasetDescription;
  items: MetadataRow[];
  filters: MetadataFilters;
  rowSchema: MetadataRowSchema | null;
  state: MetadataLedgerState;
  canAdd: boolean;
  addDisabledReason: string;
  onApplyFilters: (filters: MetadataFilters) => void;
  onOpenRow: (row: MetadataRow) => void;
  onAdd: () => void;
  onNext: () => void;
  onPrevious: () => void;
}) {
  const columns = useMemo<ColumnDef<MetadataRow>[]>(() => [
    ...descriptor.columns.map((field): ColumnDef<MetadataRow> => ({
      id: field,
      accessorFn: (row) => row[field],
      header: metadataFieldLabel(field),
      cell: ({ row }) => {
        const value = row.original[field];
        return (
          <span className={descriptor.natural_key.includes(field)
            ? "metadata-cell-value is-key"
            : "metadata-cell-value"}
          >
            {metadataValueText(value)}
          </span>
        );
      },
    })),
    {
      id: "actions",
      header: "",
      cell: ({ row }) => (
        <button
          className="text-action"
          type="button"
          onClick={() => onOpenRow(row.original)}
        >
          Show details
        </button>
      ),
    },
  ], [descriptor.columns, descriptor.natural_key, onOpenRow]);
  const table = useReactTable({ data: items, columns, getCoreRowModel: getCoreRowModel() });

  return (
    <section className="metadata-ledger" aria-labelledby="metadata-sheet-heading">
      <header className="metadata-ledger-heading">
        <div>
          <p className="eyebrow">Normalized sheet · {descriptor.section}</p>
          <h2 id="metadata-sheet-heading">{descriptor.label}</h2>
          <p>
            {descriptor.columns.length} canonical columns · {descriptor.filter_fields.length}{" "}
            sheet-specific filters
          </p>
        </div>
        {descriptor.section === "operational" ? (
          <button
            className="button button-secondary button-small"
            type="button"
            disabled={!canAdd}
            title={canAdd ? "Stage a complete normalized row" : addDisabledReason}
            onClick={onAdd}
          >
            Add row
          </button>
        ) : (
          <span className="metadata-readonly-badge">Read-only</span>
        )}
      </header>

      <MetadataFilterBar
        key={descriptor.dataset}
        descriptor={descriptor}
        items={items}
        rowSchema={rowSchema}
        initialFilters={filters}
        onApply={onApplyFilters}
      />

      {state.isLoading ? (
        <div className="surface-state" aria-busy="true">Loading {descriptor.label}…</div>
      ) : state.isDenied ? (
        <div className="surface-state is-error" role="alert">
          You do not have permission to view this Metadata sheet.
        </div>
      ) : state.isError ? (
        <div className="surface-state is-error" role="alert">
          This Metadata sheet could not be loaded. No row data was retained.
        </div>
      ) : items.length === 0 ? (
        <div className="empty-state compact">
          No rows match this sheet’s server filters.
        </div>
      ) : (
        <div className="metadata-table-scroll table-scroll">
          <table aria-label={`${descriptor.label} normalized Metadata`}>
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
                    <td key={cell.id}>
                      {flexRender(cell.column.columnDef.cell, cell.getContext())}
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      <footer className="metadata-pagination" aria-label="Metadata sheet pagination">
        <span>{state.isFetching && !state.isLoading ? "Refreshing page…" : `${items.length} rows on page`}</span>
        <div>
          <button
            className="button button-secondary button-small"
            type="button"
            disabled={!state.hasPrevious || state.isFetching}
            onClick={onPrevious}
          >
            Previous
          </button>
          <button
            className="button button-secondary button-small"
            type="button"
            disabled={!state.hasNext || state.isFetching}
            onClick={onNext}
          >
            Next
          </button>
        </div>
      </footer>
    </section>
  );
}

function MetadataFilterBar({
  descriptor,
  items,
  rowSchema,
  initialFilters,
  onApply,
}: {
  descriptor: MetadataDatasetDescription;
  items: MetadataRow[];
  rowSchema: MetadataRowSchema | null;
  initialFilters: MetadataFilters;
  onApply: (filters: MetadataFilters) => void;
}) {
  const [validationMessage, setValidationMessage] = useState("");
  const defaultFilters = Object.fromEntries(
    descriptor.filter_fields.map((field) => [
      field,
      initialFilters[field] === undefined ? "" : String(initialFilters[field]),
    ]),
  );
  const form = useForm({
    defaultValues: { filters: defaultFilters },
    onSubmit: ({ value }) => {
      const next: MetadataFilters = {};
      for (const field of descriptor.filter_fields) {
        const raw = value.filters[field]?.trim() ?? "";
        if (!raw) continue;
        const sample = items.find((row) => row[field] !== null)?.[field];
        const property = metadataPropertySchema(rowSchema?.properties[field] ?? {});
        const kind = property.type ?? typeof sample;
        if (kind === "boolean") {
          if (raw !== "true" && raw !== "false") {
            setValidationMessage(`${metadataFieldLabel(field)} must be Yes or No.`);
            return;
          }
          next[field] = raw === "true";
        } else if (kind === "integer" || kind === "number") {
          const parsed = Number(raw);
          if (!Number.isFinite(parsed) || (kind === "integer" && !Number.isSafeInteger(parsed))) {
            setValidationMessage(`${metadataFieldLabel(field)} must be a valid number.`);
            return;
          }
          next[field] = parsed;
        } else {
          next[field] = raw;
        }
      }
      setValidationMessage("");
      onApply(next);
    },
  });

  return (
    <form
      className="metadata-filter-band"
      aria-label={`${descriptor.label} server filters`}
      onSubmit={(event) => {
        event.preventDefault();
        event.stopPropagation();
        void form.handleSubmit();
      }}
    >
      <div className="metadata-filter-fields">
        {descriptor.filter_fields.map((field) => {
          const sample = items.find((row) => row[field] !== null)?.[field];
          const property = metadataPropertySchema(rowSchema?.properties[field] ?? {});
          const kind = property.type ?? typeof sample;
          return (
            <form.Field key={field} name={`filters.${field}`}>
              {(control) => (
                <label>
                  <span>{metadataFieldLabel(field)}</span>
                  {kind === "boolean" ? (
                    <select
                      aria-label={`${metadataFieldLabel(field)} filter`}
                      value={control.state.value}
                      onBlur={control.handleBlur}
                      onChange={(event) => control.handleChange(event.target.value)}
                    >
                      <option value="">Any</option>
                      <option value="true">Yes</option>
                      <option value="false">No</option>
                    </select>
                  ) : (
                    <input
                      aria-label={`${metadataFieldLabel(field)} filter`}
                      inputMode={kind === "integer" || kind === "number" ? "numeric" : undefined}
                      type={kind === "integer" || kind === "number" ? "number" : "text"}
                      value={control.state.value}
                      onBlur={control.handleBlur}
                      onChange={(event) => control.handleChange(event.target.value)}
                    />
                  )}
                </label>
              )}
            </form.Field>
          );
        })}
      </div>
      <div className="metadata-filter-actions">
        <span aria-live="polite">{validationMessage}</span>
        <button
          className="button button-secondary button-small"
          type="button"
          onClick={() => {
            form.reset({ filters: Object.fromEntries(
              descriptor.filter_fields.map((field) => [field, ""]),
            ) });
            setValidationMessage("");
            onApply({});
          }}
        >
          Clear filters
        </button>
        <button className="button button-primary button-small" type="submit">
          Apply sheet filters
        </button>
      </div>
    </form>
  );
}
