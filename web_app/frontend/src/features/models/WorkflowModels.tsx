import { useMemo } from "react";
import { useInfiniteQuery } from "@tanstack/react-query";
import { Link } from "@tanstack/react-router";
import {
  flexRender,
  getCoreRowModel,
  useReactTable,
  type ColumnDef,
} from "@tanstack/react-table";

import { ApiError } from "../../core/http";
import { formatRequiredDateTime as formatDateTime } from "../../shared/presentation";
import type { ModelLedgerRecord, ModelsApi } from "./api";

const workflowViews = {
  mapping: {
    title: "Mapping",
    eyebrow: "Applied model register",
    context: "Choose a Model to review its Mapping",
    className: "mapping-models-page",
    queryKey: "mapping-models",
    route: "/tenants/$tenantId/mapping/models/$modelId",
  },
  code_generation: {
    title: "Code Generation",
    eyebrow: "Applied Mapping register",
    context: "Choose an active Model to review target SQL",
    className: "code-generation-models",
    queryKey: "code-generation-models",
    route: "/tenants/$tenantId/code-generation/models/$modelId",
  },
  validation: {
    title: "Validation",
    eyebrow: "Applied validation register",
    context: "Choose an active Model to review or author Validation",
    className: "validation-models",
    queryKey: "validation-models",
    route: "/tenants/$tenantId/validation/models/$modelId",
  },
} as const;

export function WorkflowModels({
  api,
  tenantId,
  workflow,
}: {
  api: Pick<ModelsApi, "listModels">;
  tenantId: number;
  workflow: keyof typeof workflowViews;
}) {
  const view = workflowViews[workflow];
  const query = useInfiniteQuery({
    queryKey: [view.queryKey, tenantId],
    queryFn: ({ pageParam }) => api.listModels(tenantId, "active", 200, pageParam),
    initialPageParam: undefined as string | undefined,
    getNextPageParam: (page) => page.next_cursor ?? undefined,
  });
  const models = useMemo(() => query.data?.pages.flatMap((page) => page.items) ?? [], [query.data]);
  const columns = useMemo<ColumnDef<ModelLedgerRecord>[]>(() => [
    {
      accessorKey: "model_name",
      header: "Model",
      cell: ({ row }) => (
        <span className="model-name">
          <strong>{row.original.model_name}</strong>
          <span>{row.original.model_description ?? "No description provided"}</span>
        </span>
      ),
    },
    {
      accessorKey: "model_revision",
      header: "Revision",
      cell: ({ getValue }) => `r${getValue<number>()}`,
    },
    {
      accessorKey: "model_input_scope_object_count",
      header: "Active scope",
      cell: ({ getValue }) => `${getValue<number>()} Objects`,
    },
    {
      accessorKey: "latest_workflow",
      header: "Latest workflow",
      cell: ({ getValue }) => humanize(getValue<string | null>() ?? "not_started"),
    },
    {
      accessorKey: "latest_run_status",
      header: "Latest run",
      cell: ({ getValue }) => humanize(getValue<string | null>() ?? "not_started"),
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
          aria-label={`Open ${row.original.model_name} ${view.title}`}
          to={view.route}
          params={{ tenantId: String(tenantId), modelId: String(row.original.model_id) }}
          {...(workflow === "mapping" ? { search: {} } : {})}
        >
          Open
        </Link>
      ),
    },
  ], [tenantId, view, workflow]);
  const table = useReactTable({ data: models, columns, getCoreRowModel: getCoreRowModel() });

  return (
    <section className={`models-page ${view.className} page-enter`}>
      <header className="models-commandbar">
        <div>
          <p className="eyebrow">{view.eyebrow}</p>
          <h1>{view.title}</h1>
        </div>
        <div className="mapping-model-actions">
          <span className="models-context-note">{view.context}</span>
          <button
            className="button button-secondary button-small"
            type="button"
            disabled={workflow !== "mapping" && query.isFetching}
            onClick={() => void query.refetch()}
          >
            {workflow !== "mapping" && query.isFetching ? "Refreshing…" : "Refresh"}
          </button>
        </div>
      </header>
      {query.isPending ? (
        <div className="surface-state" aria-busy="true">Loading Models for {view.title}…</div>
      ) : query.error instanceof ApiError && query.error.status === 403 ? (
        <div className="surface-state is-error" role="alert">
          You do not have permission to view Models for {view.title}.
        </div>
      ) : query.isError ? (
        <div className="surface-state is-error" role="alert">
          Models for {view.title} could not be loaded.
        </div>
      ) : models.length === 0 ? (
        <div className="empty-state compact">No active Models are available for {view.title}.</div>
      ) : (
        <div className="models-table-scroll table-scroll">
          <table aria-label={`Models for ${view.title}`}>
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
          {query.hasNextPage ? (
            <div className="ledger-pagination">
              <button
                className="button button-secondary button-small"
                type="button"
                disabled={query.isFetchingNextPage}
                onClick={() => void query.fetchNextPage()}
              >
                {query.isFetchingNextPage ? "Loading…" : "Load more Models"}
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
