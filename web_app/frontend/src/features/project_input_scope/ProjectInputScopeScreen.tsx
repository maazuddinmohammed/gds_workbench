import { useEffect, useMemo, useRef, useState } from "react";
import { useForm } from "@tanstack/react-form";
import { useQuery, useQueryClient, useInfiniteQuery } from "@tanstack/react-query";
import { Link } from "@tanstack/react-router";
import {
  flexRender,
  getCoreRowModel,
  useReactTable,
  type ColumnDef,
} from "@tanstack/react-table";

import { TenantWorkspace } from "../../app/TenantWorkspace";
import { zoneLabel } from "../../shared/presentation";
import { ErrorPage, LoadingPage, WorkspaceToolbar } from "../../shared/ui";
import { validTenantProjectIds } from "../projects/ProjectRouteFrame";
import { ProjectWorkspaceShell } from "../projects/ProjectWorkspaceShell";
import { WorkflowCommandCenter, WorkflowCommandTools, WorkflowFilters } from "../workflows/WorkflowCommandCenter";
import type { ProjectsApi } from "../projects/api";
import type { TenantsApi } from "../tenants/api";
import type {
  ProjectInputScopeApi,
  ProjectInputScopeDetail,
  ProjectInputScopeFilters,
  ProjectInputScopeObject,
} from "./api";
import { AddScopeDialog } from "./AddScopeDialog";
import { SourceCodeFilter, SourceFilterNotice, scopeFilterChoicesKey, useScopeFilterChoices, type ScopeFilterChoices } from "./scopeFilterChoices";

type ProjectInputScopeScreenApi = Pick<TenantsApi, "readTenantHome">
  & Pick<ProjectsApi, "readProject" | "readProjectOverview">
  & Partial<Pick<ProjectsApi, "setProjectLock">>
  & ProjectInputScopeApi;

export function ProjectInputScopeScreen({
  api,
  tenantId,
  projectId,
}: {
  api: ProjectInputScopeScreenApi;
  tenantId: number;
  projectId: number;
}) {
  const validIds = validTenantProjectIds(tenantId, projectId);
  const queryClient = useQueryClient();
  const [addOpen, setAddOpen] = useState(false);
  const [filters, setFilters] = useState<ProjectInputScopeFilters>({});
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
  const projectQuery = useQuery({
    queryKey: ["project", tenantId, projectId],
    queryFn: () => api.readProject(tenantId, projectId),
    enabled: validIds,
  });
  const sourceChoices = useScopeFilterChoices(api, tenantId, projectId, projectQuery.data?.project_revision);
  const scopeQuery = useInfiniteQuery({
    queryKey: ["project-input-scope", tenantId, projectId, filters],
    queryFn: ({ pageParam }) => api.listProjectInputScope(tenantId, projectId, filters, 200, pageParam),
    initialPageParam: undefined as string | undefined,
    getNextPageParam: (page) => page.next_cursor ?? undefined,
    enabled: validIds,
  });
  const detailQuery = useQuery({
    queryKey: ["project-input-scope-object", tenantId, projectId, detailObjectId],
    queryFn: () => api.readProjectInputScopeObject(tenantId, projectId, detailObjectId as number),
    enabled: validIds && detailObjectId !== null,
  });

  if (!validIds) return <ErrorPage />;
  if (homeQuery.isPending || projectQuery.isPending) {
    return <LoadingPage label="Loading active Project Input Scope" />;
  }
  if (homeQuery.isError || projectQuery.isError) return <ErrorPage />;

  return (
    <TenantWorkspace home={homeQuery.data} activeNav="projects" project={projectQuery.data}>
      <ProjectWorkspaceShell api={api} tenantLock={homeQuery.data.lock} project={projectQuery.data} activeStage="scope">
        <ScopeView
          tenantId={tenantId}
          projectInputScopeObjectCount={projectQuery.data.project_input_scope_object_count}
          objects={scopeQuery.data?.pages.flatMap((page) => page.items) ?? []}
          sourceChoices={sourceChoices}
          filterCount={Object.values(filters).filter(Boolean).length}
          onAdd={() => setAddOpen(true)}
          projectLocked={projectQuery.data.is_locked === true}
          onRefresh={() => void Promise.all([scopeQuery.refetch(), sourceChoices.refetch(), projectQuery.refetch(), homeQuery.refetch()])}
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
        {scopeQuery.hasNextPage ? <button className="button button-secondary" type="button" disabled={scopeQuery.isFetching} onClick={() => void scopeQuery.fetchNextPage()}>Load more Objects</button> : null}
        {addOpen ? <AddScopeDialog api={api} tenantId={tenantId} projectId={projectId} projectRevision={projectQuery.data.project_revision}
          hasTenantLock={Boolean(!projectQuery.data.is_locked && homeQuery.data.lock.is_locked && homeQuery.data.lock.owned_by_current_principal)} onClose={() => setAddOpen(false)}
          onAdded={async () => { await Promise.all([
            queryClient.invalidateQueries({ queryKey: ["project-input-scope", tenantId, projectId] }),
            queryClient.invalidateQueries({ queryKey: ["project", tenantId, projectId] }),
            queryClient.invalidateQueries({ queryKey: ["project-overview", tenantId, projectId] }),
            queryClient.invalidateQueries({ queryKey: ["scope-candidates", tenantId, projectId] }),
            queryClient.invalidateQueries({ queryKey: ["scope-search-options", tenantId, projectId] }),
            queryClient.invalidateQueries({ queryKey: scopeFilterChoicesKey(tenantId, projectId) }),
          ]); }} /> : null}
      </ProjectWorkspaceShell>
    </TenantWorkspace>
  );
}

function ScopeView({
  tenantId,
  projectInputScopeObjectCount,
  objects,
  sourceChoices,
  filterCount,
  isLoading,
  isError,
  selectedObjectId,
  detail,
  isDetailLoading,
  isDetailError,
  onShowDetails,
  onCloseDetails,
  onFiltersChange,
  onAdd,
  projectLocked,
  onRefresh,
}: {
  tenantId: number;
  projectInputScopeObjectCount: number;
  objects: ProjectInputScopeObject[];
  sourceChoices: ScopeFilterChoices;
  filterCount: number;
  isLoading: boolean;
  isError: boolean;
  selectedObjectId: number | null;
  detail: ProjectInputScopeDetail | undefined;
  isDetailLoading: boolean;
  isDetailError: boolean;
  onShowDetails: (objectId: number) => void;
  onCloseDetails: () => void;
  onFiltersChange: (filters: ProjectInputScopeFilters) => void;
  onAdd: () => void;
  projectLocked: boolean;
  onRefresh: () => void;
}) {
  const columns = useMemo<ColumnDef<ProjectInputScopeObject>[]>(() => [
    {
      accessorKey: "source_tenant_code",
      header: "Source Tenant",
      cell: ({ row }) => (
        <strong>{row.original.source_tenant_code}</strong>
      ),
    },
    {
      accessorKey: "system_code",
      header: "System",
      cell: ({ row }) => (
        <strong>{row.original.system_code}</strong>
      ),
    },
    { accessorKey: "object_schema", header: "Schema" },
    {
      accessorKey: "object_name",
      header: "Object",
      cell: ({ row }) => (
        <span className="scope-object-name">
          <strong>{row.original.object_name}</strong>
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
          Details
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
    <WorkflowCommandCenter className="scope-page page-enter" filterCount={filterCount}>
      <h1 className="project-section-title sr-only">Input Scope</h1>
      <WorkspaceToolbar actions={<>
          <WorkflowCommandTools />
          <button className="button button-secondary button-small" type="button" onClick={onRefresh}>Refresh</button>
          <button className="button button-primary button-small" type="button" disabled={projectLocked} onClick={onAdd}>Add Objects</button>
      </>}><span>{objects.length} of {projectInputScopeObjectCount} Objects</span></WorkspaceToolbar>
      <WorkflowFilters><ScopeFilterForm sourceChoices={sourceChoices} onApply={onFiltersChange} /></WorkflowFilters>
      <div className={`scope-data-layout${selectedObjectId ? " has-inspector" : ""}`}>
        <section className="scope-ledger" aria-label="Active Project Input Scope ledger">
          {isLoading ? (
            <div className="surface-state" aria-busy="true">Loading Input Scope Objects…</div>
          ) : isError ? (
            <div className="surface-state is-error" role="alert">
              Active Project Input Scope could not be loaded.
            </div>
          ) : (
            <div className="workflow-table-scroll table-scroll ledger-grid" role="region" aria-label="Input Scope table" tabIndex={0}>
              <table aria-label="Active Project Input Scope">
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
            <div className="empty-state compact">No active Project Input Scope Objects match these filters.</div>
          ) : null}
        </section>
        {selectedObjectId ? (
          <ScopeDetailDrawer
            tenantId={tenantId}
            detail={detail}
            fallback={objects.find((item) => item.object_id === selectedObjectId)}
            isLoading={isDetailLoading}
            isError={isDetailError}
            onClose={onCloseDetails}
          />
        ) : null}
      </div>
    </WorkflowCommandCenter>
  );
}

function ScopeDetailDrawer({
  tenantId,
  detail,
  fallback,
  isLoading,
  isError,
  onClose,
}: {
  tenantId: number;
  detail: ProjectInputScopeDetail | undefined;
  fallback: ProjectInputScopeObject | undefined;
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
    ["Source or Bronze input", detail.is_project_input_eligible],
  ] as const : [];

  return (
    <aside
      id="scope-object-detail"
      className="scope-object-inspector"
      aria-label="Project Input Scope Object details"
      onKeyDown={(event) => {
        if (event.key === "Escape") onClose();
      }}
    >
      <header>
        <div>
          <small>Object details</small>
          <h2>{object?.object_name ?? "Project Input Scope Object"}</h2>
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
          <Link className="text-action" to="/tenants/$tenantId/metadata/objects" params={{ tenantId: String(tenantId) }} search={{ objectId: detail.object_id }}>Review physical metadata</Link>
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
            <div className="attribute-scroll ledger-grid" role="region" aria-label="Scope attribute table" tabIndex={0}>
              <table aria-label={`Attributes for ${detail.object_name}`}>
                <thead>
                  <tr>
                    <th scope="col">Name</th>
                    <th scope="col">Storage type</th>
                    <th scope="col">Inferred type</th>
                    <th scope="col">Nullable</th>
                    <th scope="col">Natural key</th>
                    <th scope="col">Lock</th>
                  </tr>
                </thead>
                <tbody>
                  {detail.attributes.map((attribute) => (
                    <tr key={attribute.attribute_id}>
                      <td><strong>{attribute.attribute_name}</strong></td>
                      <td>{attribute.attribute_data_type}</td>
                      <td>{attribute.attribute_inferred_data_type ?? "Not inferred"}</td>
                      <td>{attribute.attribute_nullability ? "Yes" : "No"}</td>
                      <td>{attribute.is_natural_key ? "Yes" : "No"}</td>
                      <td>{attribute.is_locked ? "Locked" : "Open"}</td>
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

export function ScopeFilterForm({
  ariaLabel = "Filter active Project Input Scope",
  sourceChoices,
  onApply,
}: {
  ariaLabel?: string;
  sourceChoices: ScopeFilterChoices;
  onApply: (filters: ProjectInputScopeFilters) => void;
}) {
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
      aria-label={ariaLabel}
      onSubmit={(event) => {
        event.preventDefault();
        event.stopPropagation();
        void form.handleSubmit();
      }}
    >
      <form.Field name="sourceTenantCode">
        {(field) => (
          <SourceCodeFilter label="Source Tenant code" value={field.state.value}
            codes={sourceChoices.tenantCodes} isLoading={sourceChoices.isLoading}
            isUnavailable={sourceChoices.isUnavailable} onChange={field.handleChange} />
        )}
      </form.Field>
      <form.Field name="systemCode">
        {(field) => (
          <SourceCodeFilter label="System code" value={field.state.value}
            codes={sourceChoices.systemCodes} isLoading={sourceChoices.isLoading}
            isUnavailable={sourceChoices.isUnavailable} onChange={field.handleChange} />
        )}
      </form.Field>
      <form.Field name="objectName">
        {(field) => (
          <label>
            <span>Schema or Object name</span>
            <input
              maxLength={400}
              value={field.state.value}
              onBlur={field.handleBlur}
              onChange={(event) => field.handleChange(event.target.value)}
            />
          </label>
        )}
      </form.Field>
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
      <SourceFilterNotice unavailable={sourceChoices.isUnavailable} />
    </form>
  );
}
