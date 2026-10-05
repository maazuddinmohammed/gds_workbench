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
  ModelLedgerRecord,
  ModelsApi,
  ModelStatus,
} from "./api";
import { ModelLockControl } from "./ModelLockControl";
import { CreateModelDialog } from "./CreateModelDialog";
import type { WorkflowsApi } from "../workflows/api";

type ModelsLedgerApi = Pick<TenantsApi, "readTenantHome"> & ModelsApi & Pick<WorkflowsApi, "readAgentCapabilities">;

export function ModelsLedgerScreen({
  api,
  tenantId,
}: {
  api: ModelsLedgerApi;
  tenantId: number;
}) {
  const [creating, setCreating] = useState(false);
  const queryClient = useQueryClient();
  const navigate = useNavigate();
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
  const canCreate = homeQuery.data.tenant.effective_role === "super_admin"
    || homeQuery.data.tenant.effective_role === "tenant_admin";

  return (
    <TenantWorkspace home={homeQuery.data} activeNav="models">
      <main className="workspace workspace-ledger">
        <ModelLedgerTable
          models={modelsQuery.data.items}
          status={status}
          tenantId={tenantId}
          api={api}
          home={homeQuery.data}
          onStatusChange={(nextStatus) => statusForm.setFieldValue("status", nextStatus)}
          onCreate={canCreate ? () => setCreating(true) : undefined}
        />
        {creating && canCreate ? <CreateModelDialog
          api={api}
          tenantId={tenantId}
          hasTenantLock={homeQuery.data.lock.owned_by_current_principal === true}
          systems={homeQuery.data.systems}
          onClose={() => setCreating(false)}
          onCreated={(created) => {
            setCreating(false);
            void queryClient.invalidateQueries({ queryKey: ["models", tenantId] });
            void navigate({ to: "/tenants/$tenantId/models/$modelId", params: {
              tenantId: String(tenantId), modelId: String(created.model_id),
            } });
          }}
        /> : null}
      </main>
    </TenantWorkspace>
  );
}

function ModelLedgerTable({
  models,
  status,
  tenantId,
  api,
  home,
  onStatusChange,
  onCreate,
}: {
  models: ModelLedgerRecord[];
  status: ModelStatus;
  tenantId: number;
  api: ModelsLedgerApi;
  home: TenantHomeRecord;
  onStatusChange: (status: ModelStatus) => void;
  onCreate: (() => void) | undefined;
}) {
  const [selectedId, setSelectedId] = useState<number | null>(null);
  const selected = models.find((model) => model.model_id === selectedId);
  const columns = useMemo<ColumnDef<ModelLedgerRecord>[]>(() => [
    {
      id: "select",
      header: "Select",
      cell: ({ row }) => <input type="radio" name="model-lock-selection"
        aria-label={`Select ${row.original.model_name}`}
        checked={selectedId === row.original.model_id}
        onChange={() => setSelectedId(row.original.model_id)} />,
    },
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
    {
      accessorKey: "model_revision",
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
          to="/tenants/$tenantId/models/$modelId"
          params={{ tenantId: String(tenantId), modelId: String(row.original.model_id) }}
          aria-label={`Open ${row.original.model_name}`}
        >
          Open
        </Link>
      ),
    },
  ], [tenantId, selectedId]);
  const table = useReactTable({
    data: models,
    columns,
    getCoreRowModel: getCoreRowModel(),
  });

  return (
    <section className="models-page page-enter" aria-labelledby="models-heading">
      <header className="models-commandbar">
        <div>
          <h1 id="models-heading">Models</h1>
        </div>
        <div className="models-ledger-actions">
        <div className="workspace-tabs" aria-label="Model status">
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
        {onCreate ? <button className="button button-primary button-small" type="button" onClick={onCreate}>Create Model</button> : null}
        <ModelLockControl key={selectedId ?? "unselected"} api={api} home={home}
          model={selected ? { ...selected, tenant_id: tenantId, is_active: status === "active" } : undefined} />
        </div>
      </header>
      <div className="models-table-scroll table-scroll ledger-grid" role="region" aria-label="Models table" tabIndex={0}>
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
