import { useQuery } from "@tanstack/react-query";
import {
  flexRender,
  getCoreRowModel,
  useReactTable,
  type ColumnDef,
} from "@tanstack/react-table";

import { TenantWorkspace } from "../../app/TenantWorkspace";
import { formatDateTime } from "../../shared/presentation";
import { ErrorPage, LoadingPage } from "../../shared/ui";
import { TenantLockFocus } from "../tenant_locks/TenantLockFocus";
import { tenantHomeQueryKey, type TenantLockApi } from "../tenant_locks/api";
import type { SystemRecord, TenantsApi } from "./api";

type TenantHomeApi = Pick<TenantsApi, "readTenantHome"> & TenantLockApi;

export function TenantHomeScreen({ api, tenantId }: { api: TenantHomeApi; tenantId: number }) {
  const isValidTenantId = Number.isSafeInteger(tenantId) && tenantId > 0;
  const homeQuery = useQuery({
    queryKey: tenantHomeQueryKey(tenantId),
    queryFn: () => api.readTenantHome(tenantId),
    enabled: isValidTenantId,
  });

  if (!isValidTenantId) return <ErrorPage />;
  if (homeQuery.isPending) return <LoadingPage label="Loading Tenant workspace" />;
  if (homeQuery.isError) return <ErrorPage />;

  const home = homeQuery.data;
  return (
    <TenantWorkspace home={home} activeNav="home">
      <main className="workspace">
        <div className="tenant-home-page">
          <TenantLockFocus
            actions={home.lock_actions}
            api={api}
            lock={home.lock}
            tenantId={home.tenant.tenant_id}
            tenantName={home.tenant.tenant_name}
          />
          <SystemsTable systems={home.systems} />
        </div>
      </main>
    </TenantWorkspace>
  );
}

const systemColumns: ColumnDef<SystemRecord>[] = [
  {
    accessorKey: "system_name",
    header: "System",
    cell: ({ row }) => (
      <span className="system-name">
        <strong>{row.original.system_name}</strong>
        <span>{row.original.system_code}</span>
      </span>
    ),
  },
  { accessorKey: "system_type_name", header: "Type" },
  { accessorKey: "connection_count", header: "Connections" },
  { accessorKey: "registered_object_count", header: "Registered objects" },
  { accessorKey: "active_model_count", header: "Used by Models" },
  {
    accessorKey: "last_metadata_update_time",
    header: "Last metadata update",
    cell: ({ getValue }) => formatDateTime(getValue<string | null>()) ?? "—",
  },
];

function SystemsTable({ systems }: { systems: SystemRecord[] }) {
  const table = useReactTable({
    data: systems,
    columns: systemColumns,
    getCoreRowModel: getCoreRowModel(),
  });

  return (
    <section className="systems-section" aria-labelledby="systems-heading">
      <header>
        <div>
          <p className="eyebrow">Registered metadata</p>
          <h2 id="systems-heading">Systems</h2>
        </div>
      </header>
      <div className="table-scroll">
        <table aria-label="Registered Systems">
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
                    {cell.column.columnDef.cell
                      ? flexRender(cell.column.columnDef.cell, cell.getContext())
                      : String(cell.getValue() ?? "")}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {!systems.length ? <div className="empty-state compact">No registered Systems.</div> : null}
    </section>
  );
}
