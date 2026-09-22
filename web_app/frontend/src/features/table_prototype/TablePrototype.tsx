/*
 * PROTOTYPE — delete or absorb after review.
 * Question: Which tablecn-style layout best fits GDS Workbench data ledgers?
 * Visual thesis: calm, dense governance UI with terracotta actions and visible evidence.
 * Content plan: workspace context, filters, comparable records, selection/detail state.
 * Interaction thesis: immediate sorting/filtering, persistent selection, smooth inspector reveal.
 */
import { useEffect, useMemo, useState, type ReactNode } from "react";
import {
  flexRender,
  getCoreRowModel,
  getFilteredRowModel,
  getPaginationRowModel,
  getSortedRowModel,
  useReactTable,
  type ColumnDef,
  type Row,
  type SortingState,
  type Table,
  type VisibilityState,
} from "@tanstack/react-table";

import { Fact } from "../../shared/ui";
import "../../styles/table-prototype.css";

type Variant = "A" | "B" | "C";

interface ModelRow {
  id: number;
  model: string;
  description: string;
  domain: string;
  owner: string;
  revision: number;
  scope: number;
  workflow: string;
  state: "completed" | "running" | "attention";
  updated: string;
  findings: number;
}

const rows: ModelRow[] = [
  { id: 1042, model: "Customer 360", description: "Unified customer identity and lifecycle", domain: "Customer", owner: "Data Products", revision: 18, scope: 42, workflow: "Validation", state: "completed", updated: "12 min ago", findings: 0 },
  { id: 1077, model: "Commercial Lending", description: "Loan origination and servicing model", domain: "Lending", owner: "Risk Engineering", revision: 9, scope: 28, workflow: "Code generation", state: "running", updated: "28 min ago", findings: 2 },
  { id: 1014, model: "Treasury Positions", description: "Daily positions, cash flow, and exposure", domain: "Treasury", owner: "Finance Data", revision: 31, scope: 67, workflow: "Mapping", state: "attention", updated: "1 hr ago", findings: 4 },
  { id: 1091, model: "Digital Engagement", description: "Web and mobile interaction journeys", domain: "Digital", owner: "Growth Analytics", revision: 7, scope: 19, workflow: "Analysis", state: "completed", updated: "3 hr ago", findings: 0 },
  { id: 1038, model: "Regulatory Capital", description: "Capital adequacy and risk-weighted assets", domain: "Risk", owner: "Risk Engineering", revision: 24, scope: 53, workflow: "Validation", state: "completed", updated: "Yesterday", findings: 1 },
  { id: 1056, model: "Merchant Settlement", description: "Settlement events and merchant balances", domain: "Payments", owner: "Payments Data", revision: 12, scope: 36, workflow: "Dimensional", state: "running", updated: "Yesterday", findings: 0 },
  { id: 1023, model: "Workforce Planning", description: "Headcount, capacity, and cost forecasts", domain: "People", owner: "Enterprise Data", revision: 5, scope: 14, workflow: "Logical", state: "completed", updated: "Sep 18", findings: 0 },
  { id: 1069, model: "Card Authorization", description: "Authorization decisions and outcomes", domain: "Payments", owner: "Payments Data", revision: 16, scope: 48, workflow: "Profiling", state: "attention", updated: "Sep 17", findings: 3 },
];

const variantNames: Record<Variant, string> = {
  A: "Balanced ledger",
  B: "Table + inspector",
  C: "Operations grid",
};

function StateBadge({ state }: { state: ModelRow["state"] }) {
  const label = state === "attention" ? "Needs attention" : state;
  return <span className={`prototype-status is-${state}`}><i aria-hidden="true" />{label}</span>;
}

function SortLabel({ children, column }: { children: ReactNode; column: { getIsSorted: () => false | "asc" | "desc"; toggleSorting: (descending?: boolean) => void } }) {
  const direction = column.getIsSorted();
  return (
    <button className="prototype-sort" type="button" onClick={() => column.toggleSorting(direction === "asc")}>
      {children}<span aria-hidden="true">{direction === "asc" ? "↑" : direction === "desc" ? "↓" : "↕"}</span>
    </button>
  );
}

export function TablePrototype({ variant, onVariantChange }: { variant: Variant; onVariantChange: (variant: Variant) => void }) {
  const [globalFilter, setGlobalFilter] = useState("");
  const [sorting, setSorting] = useState<SortingState>([{ id: "updated", desc: false }]);
  const [rowSelection, setRowSelection] = useState<Record<string, boolean>>({});
  const [columnVisibility, setColumnVisibility] = useState<VisibilityState>({});
  const [focusedId, setFocusedId] = useState(rows[0]!.id);

  const columns = useMemo<ColumnDef<ModelRow>[]>(() => [
    {
      id: "select",
      enableSorting: false,
      header: ({ table }) => <input type="checkbox" aria-label="Select all visible Models" checked={table.getIsAllPageRowsSelected()} onChange={table.getToggleAllPageRowsSelectedHandler()} />,
      cell: ({ row }) => <input type="checkbox" aria-label={`Select ${row.original.model}`} checked={row.getIsSelected()} onChange={row.getToggleSelectedHandler()} />,
    },
    {
      accessorKey: "model",
      header: ({ column }) => <SortLabel column={column}>Model</SortLabel>,
      cell: ({ row }) => <span className="prototype-model"><strong>{row.original.model}</strong><small>{row.original.description}</small></span>,
    },
    { accessorKey: "domain", header: ({ column }) => <SortLabel column={column}>Domain</SortLabel> },
    { accessorKey: "owner", header: "Owner" },
    { accessorKey: "revision", header: ({ column }) => <SortLabel column={column}>Revision</SortLabel>, cell: ({ getValue }) => `r${getValue<number>()}` },
    { accessorKey: "scope", header: ({ column }) => <SortLabel column={column}>Scope</SortLabel>, cell: ({ getValue }) => `${getValue<number>()} Objects` },
    { accessorKey: "workflow", header: "Latest workflow" },
    { accessorKey: "state", header: "Run state", cell: ({ getValue }) => <StateBadge state={getValue<ModelRow["state"]>()} /> },
    { accessorKey: "updated", header: ({ column }) => <SortLabel column={column}>Updated</SortLabel> },
    { accessorKey: "findings", header: "Findings", cell: ({ getValue }) => <span className={getValue<number>() ? "prototype-finding-count" : ""}>{getValue<number>()}</span> },
    { id: "actions", enableSorting: false, header: "", cell: ({ row }) => <button className="text-action" type="button" onClick={() => setFocusedId(row.original.id)}>Show details</button> },
  ], []);

  const table = useReactTable({
    data: rows,
    columns,
    state: { globalFilter, sorting, rowSelection, columnVisibility },
    onGlobalFilterChange: setGlobalFilter,
    onSortingChange: setSorting,
    onRowSelectionChange: setRowSelection,
    onColumnVisibilityChange: setColumnVisibility,
    getRowId: (row) => String(row.id),
    getCoreRowModel: getCoreRowModel(),
    getFilteredRowModel: getFilteredRowModel(),
    getSortedRowModel: getSortedRowModel(),
    getPaginationRowModel: getPaginationRowModel(),
    initialState: { pagination: { pageSize: 5 } },
  });

  const focused = rows.find((row) => row.id === focusedId) ?? rows[0]!;
  const shared = { table, search: globalFilter, onSearch: setGlobalFilter, focused, onFocus: (row: ModelRow) => setFocusedId(row.id) };

  return (
    <div className={`table-prototype variant-${variant.toLowerCase()}`}>
      {variant === "A" ? <VariantA {...shared} /> : variant === "B" ? <VariantB {...shared} /> : <VariantC {...shared} />}
      {import.meta.env.DEV ? <PrototypeSwitcher current={variant} onChange={onVariantChange} /> : null}
    </div>
  );
}

interface VariantProps {
  table: Table<ModelRow>;
  search: string;
  onSearch: (value: string) => void;
  focused: ModelRow;
  onFocus: (row: ModelRow) => void;
}

function VariantA({ table, search, onSearch, onFocus }: VariantProps) {
  return (
    <PrototypeShell active="Models">
      <main className="prototype-workspace">
        <header className="prototype-titlebar"><div><p className="eyebrow">Governed model register</p><h1>Models</h1><p>Compare ownership, scope, and the latest governed workflow state.</p></div><button className="button button-primary" type="button">Create Model</button></header>
        <div className="prototype-toolbar">
          <label className="prototype-search"><span className="sr-only">Search Models</span><Magnifier /><input type="search" placeholder="Search Models…" value={search} onChange={(event) => onSearch(event.target.value)} /></label>
          <div className="prototype-filter-set"><button className="prototype-filter is-active" type="button">Active <b>8</b></button><button className="prototype-filter" type="button">Archived <b>3</b></button></div>
          <ColumnMenu table={table} />
        </div>
        <DataTable table={table} onFocus={onFocus} />
        <TableFooter table={table} />
      </main>
    </PrototypeShell>
  );
}

function VariantB({ table, search, onSearch, focused, onFocus }: VariantProps) {
  return (
    <PrototypeShell active="Models" compact>
      <main className="prototype-workspace split-workspace">
        <section className="prototype-list-pane">
          <header className="prototype-titlebar compact"><div><p className="eyebrow">Governed models</p><h1>Model register</h1></div><span className="prototype-count">8 active</span></header>
          <div className="prototype-toolbar"><label className="prototype-search"><Magnifier /><input aria-label="Search Models" type="search" placeholder="Find a Model…" value={search} onChange={(event) => onSearch(event.target.value)} /></label><ColumnMenu table={table} /></div>
          <DataTable table={table} onFocus={onFocus} focusedId={focused.id} compact />
          <TableFooter table={table} />
        </section>
        <aside className="prototype-inspector" aria-label={`${focused.model} details`}>
          <header><p className="eyebrow">Model MR-{focused.id}</p><h2>{focused.model}</h2><StateBadge state={focused.state} /></header>
          <p>{focused.description}</p>
          <dl><Fact label="Owner" value={focused.owner} /><Fact label="Domain" value={focused.domain} /><Fact label="Revision" value={`r${focused.revision}`} /><Fact label="Active scope" value={`${focused.scope} Objects`} /></dl>
          <div className="prototype-inspector-section"><span>Latest governed workflow</span><strong>{focused.workflow}</strong><small>{focused.updated} · {focused.findings} findings</small></div>
          <button className="button button-primary" type="button">Open Model</button>
        </aside>
      </main>
    </PrototypeShell>
  );
}

function VariantC({ table, search, onSearch, onFocus }: VariantProps) {
  return (
    <div className="prototype-grid-shell">
      <header className="prototype-grid-topbar"><span className="prototype-mark">GDS</span><strong>Workbench / Model operations</strong><div><span className="prototype-live-dot" /> Acme Financial · Architect</div></header>
      <main>
        <header className="prototype-grid-heading"><div><p className="eyebrow">Operational model inventory</p><h1>8 active Models</h1></div><div className="prototype-grid-metrics"><span><small>Running</small><b>2</b></span><span><small>Attention</small><b>2</b></span><span><small>In scope</small><b>307</b></span></div></header>
        <div className="prototype-grid-controls"><label className="prototype-search"><Magnifier /><input aria-label="Search Models" type="search" placeholder="Search all columns…" value={search} onChange={(event) => onSearch(event.target.value)} /></label><button className="prototype-filter" type="button">Domain: All</button><button className="prototype-filter" type="button">Run state: All</button><ColumnMenu table={table} /><button className="button button-primary" type="button">Create Model</button></div>
        <DataTable table={table} onFocus={onFocus} grid />
        <TableFooter table={table} />
      </main>
    </div>
  );
}

function PrototypeShell({ children, active, compact = false }: { children: ReactNode; active: string; compact?: boolean }) {
  return (
    <div className={`prototype-shell${compact ? " is-compact" : ""}`}>
      <header className="prototype-topbar"><span className="prototype-brand">GDS <b>Workbench</b></span><div><small>Tenant</small><strong>Acme Financial</strong><span className="prototype-tenant-code">ACME</span></div><aside>Architect <button type="button">Switch Tenant</button></aside></header>
      <nav className="prototype-sidebar" aria-label="Prototype navigation"><button type="button">‹ <span>Hide</span></button>{["Home", "Metadata", "Models", "Mapping", "Code Generation", "Validation", "Prompts"].map((item) => <span key={item} className={item === active ? "is-active" : ""}><i>{item.slice(0, 1)}</i>{item}</span>)}</nav>
      {children}
    </div>
  );
}

function DataTable({ table, onFocus, focusedId, compact = false, grid = false }: { table: Table<ModelRow>; onFocus: (row: ModelRow) => void; focusedId?: number; compact?: boolean; grid?: boolean }) {
  const hidden = compact ? new Set(["select", "owner", "scope", "workflow", "findings", "actions"]) : new Set<string>();
  const visibleCells = (row: Row<ModelRow>) => row.getVisibleCells().filter((cell) => !hidden.has(cell.column.id));
  return (
    <div className={`prototype-table-scroll${compact ? " is-compact" : ""}${grid ? " is-grid" : ""}`} role="region" aria-label="Models table" tabIndex={0}>
      <table>
        <thead>{table.getHeaderGroups().map((group) => <tr key={group.id}>{group.headers.filter((header) => !hidden.has(header.column.id)).map((header) => <th key={header.id}>{header.isPlaceholder ? null : flexRender(header.column.columnDef.header, header.getContext())}</th>)}</tr>)}</thead>
        <tbody>{table.getRowModel().rows.map((row) => <tr key={row.id} className={`${row.getIsSelected() ? "is-selected" : ""}${focusedId === row.original.id ? " is-focused" : ""}`} onClick={() => onFocus(row.original)}>{visibleCells(row).map((cell) => <td key={cell.id}>{flexRender(cell.column.columnDef.cell, cell.getContext())}</td>)}</tr>)}</tbody>
      </table>
      {!table.getRowModel().rows.length ? <div className="prototype-empty">No Models match this search.</div> : null}
      {table.getFilteredSelectedRowModel().rows.length ? <div className="prototype-actionbar"><strong>{table.getFilteredSelectedRowModel().rows.length} selected</strong><button type="button">Compare</button><button type="button">Run Validation</button><button type="button" onClick={() => table.resetRowSelection()}>Clear</button></div> : null}
    </div>
  );
}

function TableFooter({ table }: { table: Table<ModelRow> }) {
  return <footer className="prototype-table-footer"><span>{table.getFilteredRowModel().rows.length} Models</span><div><button type="button" disabled={!table.getCanPreviousPage()} onClick={() => table.previousPage()}>Previous</button><b>Page {table.getState().pagination.pageIndex + 1} of {Math.max(1, table.getPageCount())}</b><button type="button" disabled={!table.getCanNextPage()} onClick={() => table.nextPage()}>Next</button></div></footer>;
}

function ColumnMenu({ table }: { table: Table<ModelRow> }) {
  return <details className="prototype-columns"><summary>Columns</summary><div>{table.getAllLeafColumns().filter((column) => !["select", "actions"].includes(column.id)).map((column) => <label key={column.id}><input type="checkbox" checked={column.getIsVisible()} onChange={column.getToggleVisibilityHandler()} />{column.id.replace(/^./, (value) => value.toUpperCase())}</label>)}</div></details>;
}

function PrototypeSwitcher({ current, onChange }: { current: Variant; onChange: (variant: Variant) => void }) {
  const variants: Variant[] = ["A", "B", "C"];
  const cycle = (offset: number) => onChange(variants[(variants.indexOf(current) + offset + variants.length) % variants.length]!);
  useEffect(() => {
    const onKeyDown = (event: KeyboardEvent) => {
      const target = event.target as HTMLElement | null;
      if (target?.matches("input, textarea, select, [contenteditable='true']")) return;
      if (event.key === "ArrowLeft") cycle(-1);
      if (event.key === "ArrowRight") cycle(1);
    };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  });
  return <div className="prototype-switcher" aria-label="Prototype variants"><button type="button" aria-label="Previous variant" onClick={() => cycle(-1)}>←</button><span><small>Prototype</small><strong>{current} — {variantNames[current]}</strong></span><button type="button" aria-label="Next variant" onClick={() => cycle(1)}>→</button></div>;
}

function Magnifier() { return <svg aria-hidden="true" viewBox="0 0 24 24"><circle cx="10.5" cy="10.5" r="6.5" /><path d="m16 16 4 4" /></svg>; }
