import { reviewSelectionColumn } from "../model_record_review/selection";
import { useMemo, type ReactNode } from "react";
import { useForm } from "@tanstack/react-form";
import { Link } from "@tanstack/react-router";
import {
  getCoreRowModel,
  useReactTable,
  type ColumnDef,
} from "@tanstack/react-table";

import type {
  MappingAttribute,
  MappingFilters,
  MappingObject,
  MappingApi,
} from "./api";
import "./mapping-ledger.css";
import { SourceCodeFilter, SourceFilterNotice } from "../model_input_scope/scopeFilterChoices";
import { MappingTransformationValue, useMappingAttributeDocuments } from "./MappingAttributeDocuments";
import { Fact } from "../../shared/ui";
import { formatRequiredDateTime } from "../../shared/presentation";

interface MappingSourceChoices { codes: string[]; isLoading: boolean; isUnavailable: boolean }

export interface MappingLedgerState {
  isLoading: boolean;
  isError: boolean;
  isDenied: boolean;
  revisionMismatch: boolean;
  hasMore: boolean;
  isLoadingMore: boolean;
}

interface CommonLedgerProps {
  selectedIds: Set<number>;
  onSelectionChange: (ids: Set<number>) => void;
  tenantId: number;
  modelId: number;
  filters: MappingFilters;
  state: MappingLedgerState;
  onApplyFilters: (filters: MappingFilters) => void;
  onLoadMore: () => void;
}

export function MappingObjectsLedger({
  sourceChoices,
  tenantId,
  modelId,
  selectedIds, onSelectionChange,
  items,
  filters,
  state,
  onApplyFilters,
  onLoadMore,
}: CommonLedgerProps & {
  items: MappingObject[]; sourceChoices: MappingSourceChoices;
}) {
  const columns = useMemo<ColumnDef<MappingObject>[]>(() => [
    reviewSelectionColumn(items, { selectedIds, onSelectionChange }, (item) => item.mapping_object_id, "Mapping Objects"),
    { id: "source_system", header: "System", cell: ({ row }) => row.original.source_system.system_code },
    {
      id: "schema",
      header: "Schema",
      cell: ({ row }) => row.original.target.entity_schema_name,
    },
    { id: "entity", header: "Entity name", cell: ({ row }) => <strong>{row.original.target.entity_name}</strong> },
    { accessorKey: "dependency_order", header: "Entity order" },
    { accessorKey: "status", header: "Status", cell: ({ getValue }) => humanize(getValue<string>()) },
    { accessorKey: "is_locked", header: "Lock", cell: ({ getValue }) => getValue<boolean>() ? "Locked" : "Open" },
    {
      id: "action",
      header: "Actions",
      cell: ({ row }) => (
        <Link
          className="text-action"
          aria-label={`Open Object Mapping ${row.original.mapping_object_id}`}
          to="/tenants/$tenantId/mapping/models/$modelId/objects/$mappingObjectId"
          search={{ layer: row.original.target.entity_type === "logical_entity" ? "logical" : "dimensional" }}
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
  ], [items, selectedIds, onSelectionChange, modelId, tenantId]);
  return (
    <MappingLedgerSurface
      label="Object Mappings"
      items={items}
      columns={columns}
      filters={<MappingFilterBar filters={filters} onApplyFilters={onApplyFilters} sourceChoices={sourceChoices} />}
      state={state}
      onLoadMore={onLoadMore}
    />
  );
}

export function MappingAttributesLedger({
  api,
  filtersOpen,
  filterId,
  tenantId,
  modelId,
  selectedIds, onSelectionChange,
  items,
  filters,
  state,
  onApplyFilters,
  onLoadMore,
}: CommonLedgerProps & {
  api: Pick<MappingApi, "readMappingAttribute">;
  items: MappingAttribute[];
  filtersOpen: boolean;
  filterId: string;
}) {
  const { documents, fields } = useMappingAttributeDocuments({ api, tenantId, modelId, items,
    enabled: !state.isLoading && !state.isError && !state.isDenied && !state.revisionMismatch });
  const documentColumns = fields.length ? fields.map((field) => ({
    id: `field:${field}`, header: () => <span title={field}>{humanize(field) || "Unnamed field"}</span>,
  })) : [{ id: "empty-document", header: "Transformation" }];
  const columns = useMemo<ColumnDef<MappingAttribute>[]>(() => [
    reviewSelectionColumn(items.filter((item) => item.mapping_attribute_id !== null),
      { selectedIds, onSelectionChange }, (item) => item.mapping_attribute_id!, "Mapping Attributes"),
    {
      id: "target",
      header: "Target Attribute",
      cell: ({ row }) => <span className="mapping-attribute-identity"><strong>{row.original.target.attribute_name}</strong>
        <small>{row.original.target.data_type}</small></span>,
    },
    ...documentColumns,
    { id: "status", header: "Status", cell: ({ row }) => <span className="mapping-attribute-status">
      <span className={`status-badge ${row.original.status === "active" ? "is-success" : "is-neutral"}`}>{row.original.status === null ? "Not mapped" : humanize(row.original.status)}</span>
      <small>{row.original.is_locked ? "Locked" : "Open"}</small></span> },
    { id: "record-info", header: "Record info" },
  ], [items, selectedIds, onSelectionChange, documentColumns]);
  return (
    <MappingLedgerSurface
      label="Attribute Mappings"
      items={items}
      columns={columns}
      filters={<div id={filterId} hidden={!filtersOpen}>
        <MappingFilterBar filters={filters} onApplyFilters={onApplyFilters} objectScoped />
      </div>}
      state={state}
      onLoadMore={onLoadMore}
      renderCell={(item, column) => {
        // These rows come from modeled Attributes, not persisted Mapping records.
        if (item.mapping_attribute_id === null && column !== "target" && column !== "status") return <></>;
        const isField = column.startsWith("field:") || column === "empty-document";
        if (!isField && column !== "record-info") return undefined;
        const record = item.mapping_attribute_id === null ? undefined : documents.get(item.mapping_attribute_id);
        const firstColumn = documentColumns[0]?.id;
        if (!record || record.state !== "ready" || !record.detail) {
          if (column !== firstColumn) return <span className="mapping-cell-state">—</span>;
          if (!record || record.state === "loading") return <span className="mapping-cell-state" aria-busy="true">Loading transformation…</span>;
          if (record.state === "changed") return <span className="mapping-cell-state is-error" role="alert">Mapping changed. Refresh to load the current transformation.</span>;
          return <div className="mapping-cell-state is-error" role="alert">
            <span>{record.denied ? "Transformation access denied." : "Transformation could not be loaded."}</span>
            <button type="button" className="text-action" onClick={record.retry}>Retry transformation</button>
          </div>;
        }
        const detail = record.detail;
        if (column === "record-info") return <details className="mapping-record-info">
          <summary aria-label={`Record info for ${item.target.attribute_name}`}>Record info</summary>
          <dl className="detail-fact-grid">
            <Fact label="Attribute Mapping" value={String(detail.mapping_attribute_id)} />
            <Fact label="Ordinal" value={String(detail.target.ordinal_position)} />
            <Fact label="Updated" value={formatRequiredDateTime(detail.updated_at)} />
            <Fact label="Created" value={formatRequiredDateTime(detail.created_at)} />
            <Fact label="Output template" value={detail.output_template?.output_template_name ?? "Free form"} />
            {detail.output_template ? <>
              <Fact label="Template code" value={detail.output_template.output_template_code} />
              <Fact label="Template target" value={humanize(detail.output_template.output_template_target_type)} />
              <Fact label="Template state" value={detail.output_template.is_active ? "Active" : "Inactive"} />
            </> : null}
          </dl>
          {detail.mapping_document !== null ? <details className="support-record-details"><summary>Original document</summary>
            <pre className="mapping-original-document" tabIndex={0}><code>{JSON.stringify(detail.mapping_document, null, 2)}</code></pre>
          </details> : null}
        </details>;
        const doc = detail.mapping_document;
        if (doc === null) return <></>;
        if (Object.keys(doc).length === 0 || column === "empty-document") {
          return <span className="mapping-cell-state">{column !== firstColumn ? "—"
            : Object.keys(doc).length === 0 ? "No fields" : "No additional fields"}</span>;
        }
        const field = column.slice("field:".length);
        if (!Object.hasOwn(doc, field)) return <span className="mapping-cell-state">Not provided</span>;
        const entity = item.target.entity;
        const label = `${humanize(field)} for ${entity.entity_schema_name}.${entity.entity_name}.${item.target.attribute_name} / ${item.source_system.system_code}`;
        return <MappingTransformationValue value={doc[field]!} label={label} ordered={field === "steps" || field === "transformation_steps"} />;
      }}
    />
  );
}

function MappingFilterBar({
  sourceChoices,
  filters,
  onApplyFilters,
  objectScoped = false,
}: {
  sourceChoices?: MappingSourceChoices;
  filters: MappingFilters;
  onApplyFilters: (filters: MappingFilters) => void;
  objectScoped?: boolean;
}) {
  const form = useForm({
    defaultValues: {
      sourceSystemCode: filters.sourceSystemCode ?? "",
      status: filters.status ?? "",
      locked: filters.locked === undefined ? "" : String(filters.locked),
    },
    onSubmit: ({ value }) => onApplyFilters({
      ...(value.sourceSystemCode ? { sourceSystemCode: value.sourceSystemCode } : {}),
      ...(value.status ? { status: value.status as NonNullable<MappingFilters["status"]> } : {}),
      ...(value.locked ? { locked: value.locked === "true" } : {}),
    }),
  });
  return (
    <form
      className={`workflow-filterbar mapping-filterbar${objectScoped ? " is-object-scoped" : ""}`}
      aria-label="Filter Mapping"
      onSubmit={(event) => {
        event.preventDefault();
        event.stopPropagation();
        void form.handleSubmit();
      }}
    >
      {!objectScoped ? (
        <>
          <form.Field name="sourceSystemCode">
            {(field) => (
              <SourceCodeFilter label="Source System code" value={field.state.value}
                codes={sourceChoices?.codes ?? []} isLoading={sourceChoices?.isLoading ?? false}
                isUnavailable={sourceChoices?.isUnavailable ?? false} onChange={field.handleChange} />
            )}
          </form.Field>
        </>
      ) : null}
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
      <SourceFilterNotice unavailable={sourceChoices?.isUnavailable ?? false} />
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
  renderCell,
}: {
  label: string;
  items: T[];
  columns: ColumnDef<T>[];
  filters: ReactNode;
  state: MappingLedgerState;
  onLoadMore: () => void;
  renderCell?: (item: T, column: string) => ReactNode;
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
        <div className="workflow-table-scroll mapping-table-scroll mapping-spreadsheet table-scroll" role="region" aria-label={`${label} spreadsheet`} tabIndex={0}>
          <table aria-label={label}>
            <thead>
              {table.getHeaderGroups().map((group) => (
                <tr key={group.id}>
                  {group.headers.map((header) => (
                    <th key={header.id} scope="col" className={header.column.id.startsWith("field:") || header.column.id === "empty-document"
                      ? "mapping-document-column" : `mapping-column-${header.column.id}`}>
                      {header.isPlaceholder ? null : typeof header.column.columnDef.header === "function"
                        ? header.column.columnDef.header(header.getContext()) : header.column.columnDef.header}
                    </th>
                  ))}
                </tr>
              ))}
            </thead>
            <tbody>
              {table.getRowModel().rows.map((row) => (
                <tr key={row.id}>
                  {row.getVisibleCells().map((cell) => (
                    <td key={cell.id} className={cell.column.id.startsWith("field:") || cell.column.id === "empty-document"
                      ? "mapping-document-column" : `mapping-column-${cell.column.id}`}>
                      {/* These local renderers are stateless. Direct calls keep selection
                          inputs mounted when newly loaded documents add columns. */}
                      {renderCell?.(row.original, cell.column.id) ?? (typeof cell.column.columnDef.cell === "function"
                        ? cell.column.columnDef.cell(cell.getContext()) : cell.column.columnDef.cell)}
                    </td>
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
