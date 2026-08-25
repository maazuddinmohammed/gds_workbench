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
import type { ModelLedgerRecord } from "../models/api";
import { codeGenerationQueryKeys, type CodeGenerationApi } from "./api";

export function CodeGenerationModels({
  api,
  tenantId,
}: {
  api: CodeGenerationApi;
  tenantId: number;
}) {
  const query = useInfiniteQuery({
    queryKey: codeGenerationQueryKeys.models(tenantId),
    queryFn: ({ pageParam }) => api.listModels(tenantId, "active", 200, pageParam),
    initialPageParam: undefined as string | undefined,
    getNextPageParam: (page) => page.next_cursor ?? undefined,
  });
  const models = query.data?.pages.flatMap((page) => page.items) ?? [];
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
      accessorKey: "model_scope_object_count",
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
          aria-label={`Open ${row.original.model_name} Code Generation`}
          to="/tenants/$tenantId/code-generation/models/$modelId"
          params={{ tenantId: String(tenantId), modelId: String(row.original.model_id) }}
        >
          Open
        </Link>
      ),
    },
  ], [tenantId]);
  const table = useReactTable({ data: models, columns, getCoreRowModel: getCoreRowModel() });

  return (
    <section className="models-page code-generation-models page-enter">
      <header className="models-commandbar">
        <div>
          <p className="eyebrow">Applied Mapping register</p>
          <h1>Code Generation</h1>
        </div>
        <div className="mapping-model-actions">
          <span className="models-context-note">Choose an active Model to review target SQL</span>
          <button
            className="button button-secondary button-small"
            type="button"
            disabled={query.isFetching}
            onClick={() => void query.refetch()}
          >
            {query.isFetching ? "Refreshing…" : "Refresh"}
          </button>
        </div>
      </header>
      {query.isPending ? (
        <div className="surface-state" aria-busy="true">Loading Models for Code Generation…</div>
      ) : query.error instanceof ApiError && query.error.status === 403 ? (
        <div className="surface-state is-error" role="alert">
          You do not have permission to view Models for Code Generation.
        </div>
      ) : query.isError ? (
        <div className="surface-state is-error" role="alert">
          Models for Code Generation could not be loaded.
        </div>
      ) : models.length === 0 ? (
        <div className="empty-state compact">No active Models are available for Code Generation.</div>
      ) : (
        <div className="models-table-scroll table-scroll">
          <table aria-label="Models for Code Generation">
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
