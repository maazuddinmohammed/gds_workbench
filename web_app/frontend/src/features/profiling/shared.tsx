import type { ReactNode, RefObject } from "react";
import { flexRender, type Table } from "@tanstack/react-table";

import type {
  AttributeProfile,
  ProfilingObject,
} from "./api";
import type { WorkflowRunRecord } from "../workflows/api";

export function WorkflowTable<T extends ProfilingObject | WorkflowRunRecord>({
  table,
  label,
  selectedId,
}: {
  table: Table<T>;
  label: string;
  selectedId: number | null;
}) {
  return (
    <div className="workflow-table-scroll table-scroll">
      <table aria-label={label}>
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
          {table.getRowModel().rows.map((row) => {
            const record = row.original;
            const rowId = "object_id" in record ? record.object_id : record.workflow_run_id;
            return (
              <tr className={selectedId === rowId ? "is-active" : ""} key={row.id}>
                {row.getVisibleCells().map((cell) => (
                  <td key={cell.id}>
                    {flexRender(cell.column.columnDef.cell, cell.getContext())}
                  </td>
                ))}
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}

export function DrawerHeader({
  eyebrow,
  title,
  titleId,
  closeLabel,
  closeRef,
  onClose,
  badge,
}: {
  eyebrow: string;
  title: string;
  titleId?: string;
  closeLabel: string;
  closeRef: RefObject<HTMLButtonElement | null>;
  onClose: () => void;
  badge?: ReactNode;
}) {
  return (
    <header className="drawer-header">
      <div>
        <small>{eyebrow}</small>
        <h2 id={titleId}>{title}</h2>
      </div>
      <div className="drawer-header-actions">
        {badge}
        <button
          ref={closeRef}
          className="panel-close"
          type="button"
          aria-label={closeLabel}
          onClick={onClose}
        >
          <span aria-hidden="true">×</span>
        </button>
      </div>
    </header>
  );
}

export function Fact({ label, value }: { label: string; value: string }) {
  return <div><dt>{label}</dt><dd>{value}</dd></div>;
}

export function stageLabel(stage: string): string {
  return stage
    .replaceAll("_", " ")
    .replaceAll(".", " · ")
    .replace(/^./, (character) => character.toLocaleUpperCase());
}

export function formatPercent(value: AttributeProfile["percent_populated"]): string {
  if (value === null) return "—";
  const parsed = Number(value);
  return Number.isFinite(parsed)
    ? `${new Intl.NumberFormat(undefined, { maximumFractionDigits: 2 }).format(parsed)}%`
    : "—";
}
