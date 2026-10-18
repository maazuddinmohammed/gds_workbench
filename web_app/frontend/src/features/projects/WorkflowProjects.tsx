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
import type { ProjectLedgerRecord, ProjectsApi } from "./api";

const workflowViews = {
  mapping: {
    title: "Mapping",
    eyebrow: "Applied project register",
    className: "mapping-projects-page",
    queryKey: "mapping-projects",
    route: "/tenants/$tenantId/mapping/projects/$projectId",
  },
  code_generation: {
    title: "Code Generation",
    eyebrow: "Applied Mapping register",
    className: "code-generation-projects",
    queryKey: "code-generation-projects",
    route: "/tenants/$tenantId/code-generation/projects/$projectId",
  },
  validation: {
    title: "Validation",
    eyebrow: "Applied validation register",
    className: "validation-projects",
    queryKey: "validation-projects",
    route: "/tenants/$tenantId/validation/projects/$projectId",
  },
} as const;

export function WorkflowProjects({
  api,
  tenantId,
  workflow,
}: {
  api: Pick<ProjectsApi, "listProjects">;
  tenantId: number;
  workflow: keyof typeof workflowViews;
}) {
  const view = workflowViews[workflow];
  const query = useInfiniteQuery({
    queryKey: [view.queryKey, tenantId],
    queryFn: ({ pageParam }) => api.listProjects(tenantId, "active", 200, pageParam),
    initialPageParam: undefined as string | undefined,
    getNextPageParam: (page) => page.next_cursor ?? undefined,
  });
  const projects = useMemo(() => query.data?.pages.flatMap((page) => page.items) ?? [], [query.data]);
  const columns = useMemo<ColumnDef<ProjectLedgerRecord>[]>(() => [
    {
      accessorKey: "project_name",
      header: "Project",
      cell: ({ row }) => (
        <span className="project-name">
          <strong>{row.original.project_name}</strong>
          <span>{row.original.project_description ?? "No description provided"}</span>
        </span>
      ),
    },
    {
      accessorKey: "project_revision",
      header: "Revision",
      cell: ({ getValue }) => `r${getValue<number>()}`,
    },
    {
      accessorKey: "project_input_scope_object_count",
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
          aria-label={`Open ${row.original.project_name} ${view.title}`}
          to={view.route}
          params={{ tenantId: String(tenantId), projectId: String(row.original.project_id) }}
          {...(workflow === "mapping" ? { search: {} } : {})}
        >
          Open
        </Link>
      ),
    },
  ], [tenantId, view, workflow]);
  const table = useReactTable({ data: projects, columns, getCoreRowModel: getCoreRowModel() });

  return (
    <section className={`projects-page ${view.className} page-enter`}>
      <header className="projects-commandbar">
        <div>
          <h1>{view.title}</h1>
        </div>
        <div className="mapping-project-actions">
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
        <div className="surface-state" aria-busy="true">Loading Projects for {view.title}…</div>
      ) : query.error instanceof ApiError && query.error.status === 403 ? (
        <div className="surface-state is-error" role="alert">
          You do not have permission to view Projects for {view.title}.
        </div>
      ) : query.isError ? (
        <div className="surface-state is-error" role="alert">
          Projects for {view.title} could not be loaded.
        </div>
      ) : projects.length === 0 ? (
        <div className="empty-state compact">No active Projects are available for {view.title}.</div>
      ) : (
        <div className="projects-table-scroll table-scroll ledger-grid" role="region" aria-label="Workflow Projects table" tabIndex={0}>
          <table aria-label={`Projects for ${view.title}`}>
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
                {query.isFetchingNextPage ? "Loading…" : "Load more Projects"}
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
