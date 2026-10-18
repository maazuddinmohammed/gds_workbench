import { useMemo, useState } from "react";
import { useForm, useStore } from "@tanstack/react-form";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Link, useNavigate } from "@tanstack/react-router";
import {
  flexRender,
  getCoreRowModel,
  useReactTable,
  type ColumnDef,
} from "@tanstack/react-table";

import { TenantWorkspace } from "../../app/TenantWorkspace";
import { formatDateTime } from "../../shared/presentation";
import { ErrorPage, LoadingPage, StatusBadge } from "../../shared/ui";
import type { TenantHomeRecord, TenantsApi } from "../tenants/api";
import type {
  ProjectLedgerRecord,
  ProjectsApi,
  ProjectStatus,
} from "./api";
import { ProjectLockControl } from "./ProjectLockControl";
import { CreateProjectDialog } from "./CreateProjectDialog";
import type { WorkflowsApi } from "../workflows/api";

type ProjectsLedgerApi = Pick<TenantsApi, "readTenantHome"> & ProjectsApi & Pick<WorkflowsApi, "readAgentCapabilities">;

export function ProjectsLedgerScreen({
  api,
  tenantId,
}: {
  api: ProjectsLedgerApi;
  tenantId: number;
}) {
  const [creating, setCreating] = useState(false);
  const queryClient = useQueryClient();
  const navigate = useNavigate();
  const isValidTenantId = Number.isSafeInteger(tenantId) && tenantId > 0;
  const statusForm = useForm({
    defaultValues: { status: "active" as ProjectStatus },
  });
  const status = useStore(statusForm.store, (state) => state.values.status);
  const homeQuery = useQuery({
    queryKey: ["tenant-home", tenantId],
    queryFn: () => api.readTenantHome(tenantId),
    enabled: isValidTenantId,
  });
  const projectsQuery = useQuery({
    queryKey: ["projects", tenantId, status],
    queryFn: () => api.listProjects(tenantId, status),
    enabled: isValidTenantId,
  });

  if (!isValidTenantId) return <ErrorPage />;
  if (homeQuery.isPending || projectsQuery.isPending) {
    return <LoadingPage label="Loading Projects" />;
  }
  if (homeQuery.isError || projectsQuery.isError) return <ErrorPage />;
  const canCreate = homeQuery.data.tenant.effective_role === "super_admin"
    || homeQuery.data.tenant.effective_role === "tenant_admin";

  return (
    <TenantWorkspace home={homeQuery.data} activeNav="projects">
      <main className="workspace workspace-ledger">
        <ProjectLedgerTable
          projects={projectsQuery.data.items}
          status={status}
          tenantId={tenantId}
          api={api}
          home={homeQuery.data}
          onStatusChange={(nextStatus) => statusForm.setFieldValue("status", nextStatus)}
          onCreate={canCreate ? () => setCreating(true) : undefined}
        />
        {creating && canCreate ? <CreateProjectDialog
          api={api}
          tenantId={tenantId}
          hasTenantLock={homeQuery.data.lock.owned_by_current_principal === true}
          systems={homeQuery.data.systems}
          onClose={() => setCreating(false)}
          onCreated={(created) => {
            setCreating(false);
            void queryClient.invalidateQueries({ queryKey: ["projects", tenantId] });
            void navigate({ to: "/tenants/$tenantId/projects/$projectId", params: {
              tenantId: String(tenantId), projectId: String(created.project_id),
            } });
          }}
        /> : null}
      </main>
    </TenantWorkspace>
  );
}

function ProjectLedgerTable({
  projects,
  status,
  tenantId,
  api,
  home,
  onStatusChange,
  onCreate,
}: {
  projects: ProjectLedgerRecord[];
  status: ProjectStatus;
  tenantId: number;
  api: ProjectsLedgerApi;
  home: TenantHomeRecord;
  onStatusChange: (status: ProjectStatus) => void;
  onCreate: (() => void) | undefined;
}) {
  const [selectedId, setSelectedId] = useState<number | null>(null);
  const selected = projects.find((project) => project.project_id === selectedId);
  const columns = useMemo<ColumnDef<ProjectLedgerRecord>[]>(() => [
    {
      id: "select",
      header: "Select",
      cell: ({ row }) => <input type="radio" name="project-lock-selection"
        aria-label={`Select ${row.original.project_name}`}
        checked={selectedId === row.original.project_id}
        onChange={() => setSelectedId(row.original.project_id)} />,
    },
    {
      accessorKey: "project_name",
      header: "Project",
      cell: ({ row }) => (
        <span className="project-name">
          <strong>{row.original.project_name}</strong>
          <span>{row.original.project_description ?? "No description"}</span>
        </span>
      ),
    },
    {
      accessorKey: "project_revision",
      header: "Revision",
      cell: ({ getValue }) => `r${getValue<number>()}`,
    },
    {
      accessorKey: "is_locked",
      header: "Lock status",
      cell: ({ getValue }) => <StatusBadge value={getValue<boolean>() ? "Locked" : "Unlocked"} />,
    },
    {
      accessorKey: "updated_at",
      header: "Updated",
      cell: ({ getValue }) => formatDateTime(getValue<string>()) ?? "—",
    },
    {
      id: "actions",
      header: "Actions",
      cell: ({ row }) => (
        <Link
          className="button button-secondary button-small"
          to="/tenants/$tenantId/projects/$projectId"
          params={{ tenantId: String(tenantId), projectId: String(row.original.project_id) }}
          aria-label={`Open ${row.original.project_name}`}
        >
          Open
        </Link>
      ),
    },
  ], [tenantId, selectedId]);
  const table = useReactTable({
    data: projects,
    columns,
    getCoreRowModel: getCoreRowModel(),
  });

  return (
    <section className="projects-page page-enter" aria-labelledby="projects-heading">
      <header className="projects-commandbar">
        <div>
          <h1 id="projects-heading">Projects</h1>
        </div>
        <div className="projects-ledger-actions">
        <div className="workspace-tabs" aria-label="Project status">
          {(["active", "archived"] as const).map((option) => (
            <button
              className={status === option ? "is-active" : ""}
              type="button"
              aria-pressed={status === option}
              key={option}
              onClick={() => { setSelectedId(null); onStatusChange(option); }}
            >
              {option === "active" ? "Active" : "Archived"}
            </button>
          ))}
        </div>
        {onCreate ? <button className="button button-primary button-small" type="button" onClick={onCreate}>Create Project</button> : null}
        <ProjectLockControl key={selectedId ?? "unselected"} api={api} home={home}
          project={selected ? { ...selected, tenant_id: tenantId, is_active: status === "active" } : undefined} />
        </div>
      </header>
      <div className="projects-table-scroll table-scroll ledger-grid" role="region" aria-label="Projects table" tabIndex={0}>
        <table aria-label={`${status === "active" ? "Active" : "Archived"} Projects`}>
          <thead>
            {table.getHeaderGroups().map((headerGroup) => (
              <tr key={headerGroup.id}>
                {headerGroup.headers.map((header) => (
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
      {!projects.length ? (
        <div className="empty-state compact">No {status} Projects.</div>
      ) : null}
    </section>
  );
}
