import { useMemo } from "react";
import { useForm, useStore } from "@tanstack/react-form";
import { useQuery } from "@tanstack/react-query";
import { Link } from "@tanstack/react-router";
import {
  flexRender,
  getCoreRowModel,
  useReactTable,
  type ColumnDef,
} from "@tanstack/react-table";

import { TenantWorkspace } from "../../app/TenantWorkspace";
import { formatDateTime } from "../../shared/presentation";
import { ErrorPage, LoadingPage, StatusBadge } from "../../shared/ui";
import type { TenantsApi } from "../tenants/api";
import type {
  ModelLedgerRecord,
  ModelsApi,
  ModelStatus,
} from "./api";
import { workflowLabel } from "./presentation";

type ModelsLedgerApi = Pick<TenantsApi, "readTenantHome"> & ModelsApi;

export function ModelsLedgerScreen({
  api,
  tenantId,
}: {
  api: ModelsLedgerApi;
  tenantId: number;
}) {
  const isValidTenantId = Number.isSafeInteger(tenantId) && tenantId > 0;
  const statusForm = useForm({
    defaultValues: { status: "active" as ModelStatus },
  });
  const status = useStore(statusForm.store, (state) => state.values.status);
  const homeQuery = useQuery({
    queryKey: ["tenant-home", tenantId],
    queryFn: () => api.readTenantHome(tenantId),
    enabled: isValidTenantId,
  });
  const modelsQuery = useQuery({
    queryKey: ["models", tenantId, status],
    queryFn: () => api.listModels(tenantId, status),
    enabled: isValidTenantId,
  });

  if (!isValidTenantId) return <ErrorPage />;
  if (homeQuery.isPending || modelsQuery.isPending) {
    return <LoadingPage label="Loading Models" />;
  }
  if (homeQuery.isError || modelsQuery.isError) return <ErrorPage />;

  return (
    <TenantWorkspace home={homeQuery.data} activeNav="models">
      <main className="workspace workspace-ledger">
        <ModelLedgerTable
          models={modelsQuery.data.items}
          status={status}
          tenantId={tenantId}
          tenantName={homeQuery.data.tenant.tenant_name}
          onStatusChange={(nextStatus) => statusForm.setFieldValue("status", nextStatus)}
        />
      </main>
    </TenantWorkspace>
  );
}

function ModelLedgerTable({
  models,
  status,
  tenantId,
  tenantName,
  onStatusChange,
}: {
  models: ModelLedgerRecord[];
  status: ModelStatus;
  tenantId: number;
  tenantName: string;
  onStatusChange: (status: ModelStatus) => void;
}) {
  const columns = useMemo<ColumnDef<ModelLedgerRecord>[]>(() => [
    {
      accessorKey: "model_name",
      header: "Model",
      cell: ({ row }) => (
        <span className="model-name">
          <strong>{row.original.model_name}</strong>
          <span>{row.original.model_description ?? "No description"}</span>
        </span>
      ),
    },
    { id: "owner_tenant", header: "Owner Tenant", cell: () => tenantName },
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
      cell: ({ getValue }) => workflowLabel(getValue<ModelLedgerRecord["latest_workflow"]>()),
    },
    {
      accessorKey: "latest_run_status",
      header: "Latest run",
      cell: ({ getValue }) => <StatusBadge value={getValue<string | null>()} />,
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
          to="/tenants/$tenantId/models/$modelId"
          params={{ tenantId: String(tenantId), modelId: String(row.original.model_id) }}
          aria-label={`Open ${row.original.model_name}`}
        >
          Open
        </Link>
      ),
    },
  ], [tenantId, tenantName]);
  const table = useReactTable({
    data: models,
    columns,
    getCoreRowModel: getCoreRowModel(),
  });

  return (
    <section className="models-page page-enter" aria-labelledby="models-heading">
      <header className="models-commandbar">
        <div>
          <p className="eyebrow">Governed model register</p>
          <h1 id="models-heading">Models</h1>
        </div>
        <div className="models-mode-tabs" aria-label="Model status">
          {(["active", "archived"] as const).map((option) => (
            <button
              className={status === option ? "is-active" : ""}
              type="button"
              aria-pressed={status === option}
              key={option}
              onClick={() => onStatusChange(option)}
            >
              {option === "active" ? "Active" : "Archived"}
            </button>
          ))}
        </div>
      </header>
      <div className="models-table-scroll table-scroll">
        <table aria-label={`${status === "active" ? "Active" : "Archived"} Models`}>
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
      {!models.length ? (
        <div className="empty-state compact">No {status} Models.</div>
      ) : null}
    </section>
  );
}
