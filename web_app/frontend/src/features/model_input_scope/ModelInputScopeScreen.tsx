import { useEffect, useMemo, useRef, useState } from "react";
import { useForm } from "@tanstack/react-form";
import { useQuery } from "@tanstack/react-query";
import {
  flexRender,
  getCoreRowModel,
  useReactTable,
  type ColumnDef,
} from "@tanstack/react-table";

import { TenantWorkspace } from "../../app/TenantWorkspace";
import { zoneLabel } from "../../shared/presentation";
import { ErrorPage, LoadingPage } from "../../shared/ui";
import { ModelWorkspaceShell } from "../models/ModelWorkspaceShell";
import type { ModelsApi } from "../models/api";
import type { TenantsApi } from "../tenants/api";
import type {
  ModelInputScopeApi,
  ModelInputScopeDetail,
  ModelInputScopeFilters,
  ModelInputScopeObject,
} from "./api";

type ModelInputScopeScreenApi = Pick<TenantsApi, "readTenantHome">
  & Pick<ModelsApi, "readModel">
  & ModelInputScopeApi;

export function ModelInputScopeScreen({
  api,
  tenantId,
  modelId,
}: {
  api: ModelInputScopeScreenApi;
  tenantId: number;
  modelId: number;
}) {
  const validIds = validTenantModelIds(tenantId, modelId);
  const [filters, setFilters] = useState<ModelInputScopeFilters>({});
  const [detailObjectId, setDetailObjectId] = useState<number | null>(null);
  const focusReturnObjectIdRef = useRef<number | null>(null);
  useEffect(() => {
    if (detailObjectId !== null || focusReturnObjectIdRef.current === null) return;
    document.getElementById(
      `scope-detail-trigger-${focusReturnObjectIdRef.current}`,
    )?.focus();
    focusReturnObjectIdRef.current = null;
  }, [detailObjectId]);
  const homeQuery = useQuery({
    queryKey: ["tenant-home", tenantId],
    queryFn: () => api.readTenantHome(tenantId),
    enabled: validIds,
  });
  const modelQuery = useQuery({
    queryKey: ["model", tenantId, modelId],
    queryFn: () => api.readModel(tenantId, modelId),
    enabled: validIds,
  });
  const scopeQuery = useQuery({
    queryKey: ["model-input-scope", tenantId, modelId, filters],
    queryFn: () => api.listModelInputScope(tenantId, modelId, filters),
    enabled: validIds,
  });
  const detailQuery = useQuery({
    queryKey: ["model-input-scope-object", tenantId, modelId, detailObjectId],
    queryFn: () => api.readModelInputScopeObject(tenantId, modelId, detailObjectId as number),
    enabled: validIds && detailObjectId !== null,
  });

  if (!validIds) return <ErrorPage />;
  if (homeQuery.isPending || modelQuery.isPending) {
    return <LoadingPage label="Loading active Model Input Scope" />;
  }
  if (homeQuery.isError || modelQuery.isError) return <ErrorPage />;

  return (
    <TenantWorkspace home={homeQuery.data} activeNav="models" model={modelQuery.data}>
      <ModelWorkspaceShell model={modelQuery.data} activeStage="scope">
        <ScopeView
          modelInputScopeObjectCount={modelQuery.data.model_input_scope_object_count}
          objects={scopeQuery.data?.items ?? []}
          isLoading={scopeQuery.isPending}
          isError={scopeQuery.isError}
          selectedObjectId={detailObjectId}
          detail={detailQuery.data}
          isDetailLoading={detailQuery.isPending && detailObjectId !== null}
          isDetailError={detailQuery.isError}
          onShowDetails={setDetailObjectId}
          onCloseDetails={() => {
            focusReturnObjectIdRef.current = detailObjectId;
            setDetailObjectId(null);
          }}
          onFiltersChange={(nextFilters) => {
            setDetailObjectId(null);
            setFilters(nextFilters);
          }}
        />
      </ModelWorkspaceShell>
    </TenantWorkspace>
  );
}

function validTenantModelIds(tenantId: number, modelId: number): boolean {
  return Number.isSafeInteger(tenantId)
    && tenantId > 0
    && Number.isSafeInteger(modelId)
    && modelId > 0;
}

function ScopeView({
  modelInputScopeObjectCount,
  objects,
  isLoading,
  isError,
  selectedObjectId,
  detail,
  isDetailLoading,
  isDetailError,
  onShowDetails,
  onCloseDetails,
  onFiltersChange,
}: {
  modelInputScopeObjectCount: number;
  objects: ModelInputScopeObject[];
  isLoading: boolean;
  isError: boolean;
  selectedObjectId: number | null;
  detail: ModelInputScopeDetail | undefined;
  isDetailLoading: boolean;
  isDetailError: boolean;
  onShowDetails: (objectId: number) => void;
  onCloseDetails: () => void;
  onFiltersChange: (filters: ModelInputScopeFilters) => void;
}) {
  const columns = useMemo<ColumnDef<ModelInputScopeObject>[]>(() => [
    {
      accessorKey: "object_name",
      header: "Object",
      cell: ({ row }) => (
        <span className="scope-object-name">
          <strong>{row.original.object_name}</strong>
          <span>{row.original.object_schema}</span>
        </span>
      ),
    },
    {
      accessorKey: "system_code",
      header: "System",
      cell: ({ row }) => (
        <span className="scope-secondary">
          <strong>{row.original.system_code}</strong>
          <span>{row.original.system_name}</span>
        </span>
      ),
    },
    {
      accessorKey: "source_tenant_code",
      header: "Source Tenant",
      cell: ({ row }) => (
        <span className="scope-secondary">
          <strong>{row.original.source_tenant_code}</strong>
          <span>{row.original.source_tenant_name}</span>
        </span>
      ),
    },
    {
      accessorKey: "zone_code",
      header: "Zone",
      cell: ({ getValue }) => <span className="zone-badge">{zoneLabel(getValue<string>())}</span>,
    },
    { accessorKey: "attribute_count", header: "Attributes" },
    {
      accessorKey: "batch_attribute_name",
      header: "Batch attribute",
      cell: ({ getValue }) => getValue<string | null>() ?? "—",
    },
    {
      id: "actions",
      header: "Actions",
      cell: ({ row }) => (
        <button
          id={`scope-detail-trigger-${row.original.object_id}`}
          className="text-action"
          type="button"
          aria-label={`Show details for ${row.original.object_name}`}
          aria-expanded={selectedObjectId === row.original.object_id}
          aria-controls={selectedObjectId === row.original.object_id ? "scope-object-detail" : undefined}
          onClick={() => onShowDetails(row.original.object_id)}
        >
          Show details
        </button>
      ),
    },
  ], [onShowDetails, selectedObjectId]);
  const table = useReactTable({
    data: objects,
    columns,
    getCoreRowModel: getCoreRowModel(),
  });

  return (
    <div className="scope-page page-enter">
      <header className="section-bar">
        <div>
          <p className="eyebrow">Model Input Scope</p>
          <h1>Active Model Input Scope</h1>
        </div>
        <span>{objects.length} of {modelInputScopeObjectCount} Objects shown</span>
      </header>
      <ScopeFilterForm onApply={onFiltersChange} />
      <div className={`scope-data-layout${selectedObjectId ? " has-inspector" : ""}`}>
        <section className="scope-ledger" aria-label="Active Model Input Scope ledger">
          {isLoading ? (
            <div className="surface-state" aria-busy="true">Loading Input Scope Objects…</div>
          ) : isError ? (
            <div className="surface-state is-error" role="alert">
              Active Model Input Scope could not be loaded.
            </div>
          ) : (
            <div className="table-scroll">
              <table aria-label="Active Model Input Scope">
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
                    <tr
                      className={selectedObjectId === row.original.object_id ? "is-active" : ""}
                      key={row.id}
                    >
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
          )}
          {!isLoading && !isError && !objects.length ? (
            <div className="empty-state compact">No active Model Input Scope Objects match these filters.</div>
          ) : null}
        </section>
        {selectedObjectId ? (
          <ScopeDetailDrawer
            detail={detail}
            fallback={objects.find((item) => item.object_id === selectedObjectId)}
            isLoading={isDetailLoading}
            isError={isDetailError}
            onClose={onCloseDetails}
          />
        ) : null}
      </div>
    </div>
  );
}

function ScopeDetailDrawer({
  detail,
  fallback,
  isLoading,
  isError,
  onClose,
}: {
  detail: ModelInputScopeDetail | undefined;
  fallback: ModelInputScopeObject | undefined;
  isLoading: boolean;
  isError: boolean;
  onClose: () => void;
}) {
  const closeButtonRef = useRef<HTMLButtonElement>(null);
  useEffect(() => {
    closeButtonRef.current?.focus();
  }, []);
  const object = detail ?? fallback;
  const eligibility = detail ? [
    ["Source or Bronze input", detail.is_model_input_eligible],
    ["Dimensional source", detail.is_dimensional_source_eligible],
    ["Logical mapping target", detail.is_logical_mapping_target_eligible],
    ["Dimensional mapping target", detail.is_dimensional_mapping_target_eligible],
  ] as const : [];

  return (
    <aside
      id="scope-object-detail"
      className="scope-object-inspector"
      aria-label="Model Input Scope Object details"
      onKeyDown={(event) => {
        if (event.key === "Escape") onClose();
      }}
    >
      <header>
        <div>
          <small>Object details</small>
          <h2>{object?.object_name ?? "Model Input Scope Object"}</h2>
        </div>
        <div className="inspector-header-actions">
          {object ? <span className="zone-badge">{zoneLabel(object.zone_code)}</span> : null}
          <button
            ref={closeButtonRef}
            className="panel-close"
            type="button"
            aria-label="Close object details"
            onClick={onClose}
          >
            <span aria-hidden="true">×</span>
          </button>
        </div>
      </header>

      {isLoading ? (
        <div className="surface-state" aria-busy="true">Loading Object details…</div>
      ) : isError || !detail ? (
        <div className="surface-state is-error" role="alert">
          Object details could not be loaded.
        </div>
      ) : (
        <>
          <p>{detail.object_schema}.{detail.object_name}</p>
          <dl className="object-facts">
            <div><dt>System</dt><dd>{detail.system_code}</dd></div>
            <div><dt>Source Tenant</dt><dd>{detail.source_tenant_code}</dd></div>
            <div><dt>Attributes</dt><dd>{detail.attribute_count}</dd></div>
            <div><dt>Batch attribute</dt><dd>{detail.batch_attribute_name ?? "None"}</dd></div>
          </dl>
          <section className="eligibility-section" aria-labelledby="eligibility-heading">
            <h3 id="eligibility-heading">Server-evaluated eligibility</h3>
            <ul>
              {eligibility.map(([label, eligible]) => (
                <li key={label}>
                  <span>{label}</span>
                  <strong className={eligible ? "is-eligible" : "is-ineligible"}>
                    {eligible ? "Eligible" : "Not eligible"}
                  </strong>
                </li>
              ))}
            </ul>
          </section>
          <section className="attribute-section" aria-labelledby="attributes-heading">
            <header>
              <strong id="attributes-heading">Attributes</strong>
              <span>{detail.attributes.length}</span>
            </header>
            <div className="attribute-scroll">
              <table aria-label={`Attributes for ${detail.object_name}`}>
                <thead>
                  <tr><th>Name</th><th>Type</th><th>Nullable</th><th>Natural key</th></tr>
                </thead>
                <tbody>
                  {detail.attributes.map((attribute) => (
                    <tr key={attribute.attribute_id}>
                      <td><strong>{attribute.attribute_name}</strong></td>
                      <td>{attribute.attribute_data_type}</td>
                      <td>{attribute.attribute_nullability ? "Yes" : "No"}</td>
                      <td>{attribute.is_natural_key ? "Yes" : "No"}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </section>
        </>
      )}
    </aside>
  );
}

function ScopeFilterForm({ onApply }: { onApply: (filters: ModelInputScopeFilters) => void }) {
  const form = useForm({
    defaultValues: {
      zone: "",
      systemCode: "",
      sourceTenantCode: "",
      objectName: "",
    },
    onSubmit: ({ value }) => onApply(value),
  });

  return (
    <form
      className="scope-filterbar"
      aria-label="Filter active Model Input Scope"
      onSubmit={(event) => {
        event.preventDefault();
        event.stopPropagation();
        void form.handleSubmit();
      }}
    >
      <form.Field name="zone">
        {(field) => (
          <label>
            <span>Zone</span>
            <select
              value={field.state.value}
              onBlur={field.handleBlur}
              onChange={(event) => field.handleChange(event.target.value)}
            >
              <option value="">All Zones</option>
              <option value="source">Source</option>
              <option value="bronze">Bronze</option>
            </select>
          </label>
        )}
      </form.Field>
      <form.Field name="systemCode">
        {(field) => (
          <label>
            <span>System code</span>
            <input
              maxLength={100}
              value={field.state.value}
              onBlur={field.handleBlur}
              onChange={(event) => field.handleChange(event.target.value)}
            />
          </label>
        )}
      </form.Field>
      <form.Field name="sourceTenantCode">
        {(field) => (
          <label>
            <span>Source Tenant code</span>
            <input
              maxLength={100}
              value={field.state.value}
              onBlur={field.handleBlur}
              onChange={(event) => field.handleChange(event.target.value)}
            />
          </label>
        )}
      </form.Field>
      <form.Field name="objectName">
        {(field) => (
          <label>
            <span>Object name</span>
            <input
              maxLength={400}
              value={field.state.value}
              onBlur={field.handleBlur}
              onChange={(event) => field.handleChange(event.target.value)}
            />
          </label>
        )}
      </form.Field>
      <div className="scope-filter-actions">
        <button
          className="button button-secondary"
          type="button"
          onClick={() => {
            form.reset();
            onApply({});
          }}
        >
          Clear
        </button>
        <button className="button button-primary" type="submit">Apply filters</button>
      </div>
    </form>
  );
}
