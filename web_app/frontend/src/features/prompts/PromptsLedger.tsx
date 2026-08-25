import { useMemo } from "react";
import { Link } from "@tanstack/react-router";
import {
  flexRender,
  getCoreRowModel,
  useReactTable,
  type ColumnDef,
} from "@tanstack/react-table";

import { formatRequiredDateTime as formatDateTime } from "../../shared/presentation";
import type { PromptOwnershipScope, PromptTemplateSummary } from "./api";

export type PromptVisibilityFilter = "" | PromptOwnershipScope;

export function PromptsLedger({
  tenantId,
  items,
  visibility,
  pageNumber,
  hasPreviousPage,
  hasNextPage,
  isPaging,
  onVisibilityChange,
  onPreviousPage,
  onNextPage,
}: {
  tenantId: number;
  items: PromptTemplateSummary[];
  visibility: PromptVisibilityFilter;
  pageNumber: number;
  hasPreviousPage: boolean;
  hasNextPage: boolean;
  isPaging: boolean;
  onVisibilityChange: (visibility: PromptVisibilityFilter) => void;
  onPreviousPage: () => void;
  onNextPage: () => void;
}) {
  const visibleItems = visibility
    ? items.filter((item) => item.prompt_template_ownership_scope === visibility)
    : items;
  const columns = useMemo<ColumnDef<PromptTemplateSummary>[]>(() => [
    {
      accessorKey: "prompt_template_name",
      header: "Prompt Template",
      cell: ({ row }) => (
        <span className="prompt-template-name">
          <strong>{row.original.prompt_template_name}</strong>
          <code>{row.original.prompt_template_code}</code>
        </span>
      ),
    },
    {
      accessorKey: "prompt_template_ownership_scope",
      header: "Visibility",
      cell: ({ getValue }) => {
        const value = getValue<PromptOwnershipScope>();
        return (
          <span className={`prompt-ownership is-${value}`}>
            {value === "global" ? "Global" : "This Tenant"}
          </span>
        );
      },
    },
    {
      id: "stage",
      header: "Workflow / stage",
      cell: ({ row }) => (
        <span className="prompt-stage-cell">
          <strong>{humanize(row.original.model_workflow)}</strong>
          <small>
            {modeLabel(row.original.workflow_execution_mode)} · {row.original.workflow_stage_name}
          </small>
        </span>
      ),
    },
    {
      id: "latest",
      header: "Latest version",
      cell: ({ row }) => row.original.latest_version_number === null ? (
        <span className="prompt-version-empty">No version</span>
      ) : (
        <span className="prompt-version-cell">
          <strong>v{row.original.latest_version_number}</strong>
          <VersionStatus value={row.original.latest_version_status} />
          {row.original.latest_version_digest ? (
            <code title={row.original.latest_version_digest}>
              {shortDigest(row.original.latest_version_digest)}
            </code>
          ) : null}
        </span>
      ),
    },
    {
      accessorKey: "is_active",
      header: "Template",
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
          className="button button-secondary button-small"
          aria-label={`Open ${row.original.prompt_template_name}`}
          to="/tenants/$tenantId/prompts/templates/$promptTemplateId"
          params={{
            tenantId: String(tenantId),
            promptTemplateId: String(row.original.prompt_template_id),
          }}
        >
          Open
        </Link>
      ),
    },
  ], [tenantId]);
  const table = useReactTable({
    data: visibleItems,
    columns,
    getCoreRowModel: getCoreRowModel(),
  });

  return (
    <section className="prompt-ledger" aria-labelledby="prompt-ledger-heading">
      <header className="prompt-ledger-header">
        <div>
          <p className="eyebrow">Versioned operational ledger</p>
          <h2 id="prompt-ledger-heading">Prompt Templates</h2>
        </div>
        <label className="prompt-local-filter">
          <span>Visibility on this page</span>
          <select
            aria-label="Visibility on this page"
            value={visibility}
            onChange={(event) => onVisibilityChange(event.target.value as PromptVisibilityFilter)}
          >
            <option value="">Global and Tenant</option>
            <option value="global">Global only</option>
            <option value="tenant">This Tenant only</option>
          </select>
          {visibility ? <small>Local view · no server filter available</small> : null}
        </label>
      </header>
      {visibleItems.length === 0 ? (
        <div className="empty-state compact">
          {items.length
            ? "No Prompt Templates match this page-local visibility view."
            : "No Prompt Templates match these server filters."}
        </div>
      ) : (
        <div className="table-scroll prompt-table-scroll">
          <table aria-label="Prompt Templates">
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
        </div>
      )}
      <footer className="ledger-pagination prompt-pagination">
        <span>Server page {pageNumber}</span>
        <div>
          <button
            className="button button-secondary button-small"
            type="button"
            disabled={!hasPreviousPage || isPaging}
            onClick={onPreviousPage}
          >
            Previous
          </button>
          <button
            className="button button-secondary button-small"
            type="button"
            disabled={!hasNextPage || isPaging}
            onClick={onNextPage}
          >
            {isPaging ? "Loading…" : "Next"}
          </button>
        </div>
      </footer>
    </section>
  );
}

export function VersionStatus({
  value,
}: {
  value: PromptTemplateSummary["latest_version_status"];
}) {
  const tone = value === "published"
    ? "is-success"
    : value === "draft"
      ? "is-warning"
      : "is-neutral";
  return <span className={`status-badge ${tone}`}>{value ? humanize(value) : "None"}</span>;
}

export function humanize(value: string): string {
  return value.replaceAll("_", " ").replace(/^./, (character) => character.toLocaleUpperCase());
}

export function modeLabel(value: PromptTemplateSummary["workflow_execution_mode"]): string {
  return value ? humanize(value) : "Default mode";
}

export function shortDigest(value: string): string {
  return `${value.slice(0, 12)}…${value.slice(-8)}`;
}
