import { WorkflowCommandCenter, WorkflowCommandTools, WorkflowMenu } from "../workflows/WorkflowCommandCenter";
import { Link } from "@tanstack/react-router";
import { ProjectRecordReview } from "../project_record_review/ProjectRecordReview";
import { useRef, useState } from "react";
import { useInfiniteQuery, useQuery, useQueryClient } from "@tanstack/react-query";

import { ApiError } from "../../core/http";
import type { ProjectDetail } from "../projects/api";
import { WorkflowRunMonitor } from "../workflows/WorkflowRunMonitor";
import { loadMappingSystems, mappingQueryKeys, type MappingApi, type MappingFilters, type MappingEntityType } from "./api";
import {
  MappingObjectsLedger,
  type MappingLedgerState,
} from "./MappingLedgers";
import { MappingExportDialog } from "./MappingExportDialog";
import { MappingRunDialog } from "./MappingRunDialog";
import { RefreshButton } from "../../shared/ui";

export function MappingScreen({
  api,
  tenantId,
  project,
  hasTenantLock,
  hasAppPermission,
  layer,
  systemCode,
}: {
  api: MappingApi;
  tenantId: number;
  project: ProjectDetail;
  hasTenantLock: boolean;
  hasAppPermission: boolean;
  layer: "logical" | "dimensional";
  /** The System tab from the address; undefined shows All Systems. */
  systemCode?: string | undefined;
}) {
  const queryClient = useQueryClient();
  const commandButton = useRef<HTMLButtonElement>(null);
  const refreshButton = useRef<HTMLButtonElement>(null);
  // A selection belongs to the System tab it was made on; switching tabs clears it.
  const [selection, setSelection] = useState<{ system: string | undefined; ids: Set<number> }>({ system: systemCode, ids: new Set() });
  const selectedIds = selection.system === systemCode ? selection.ids : new Set<number>();
  const setSelectedIds = (ids: Set<number>) => setSelection({ system: systemCode, ids });
  const [runDialogOpen, setRunDialogOpen] = useState(false);
  const [exportOpen, setExportOpen] = useState(false);
  const [recentRunId, setRecentRunId] = useState<number | null>(null);
  const [filters, setFilters] = useState<MappingFilters>({});
  const entityType: MappingEntityType = layer === "logical" ? "logical_entity" : "dimensional_entity";
  const objectFilters: MappingFilters = { ...filters, entityType, ...(systemCode ? { sourceSystemCode: systemCode } : {}) };
  const systems = useQuery({
    queryKey: ["mapping-filter-systems", tenantId, project.project_id, entityType],
    queryFn: () => loadMappingSystems(api, tenantId, project.project_id, entityType),
  });
  const systemsUnavailable = systems.isError
    || (systems.data !== undefined && systems.data.projectRevision !== project.project_revision);
  const objects = useInfiniteQuery({
    queryKey: mappingQueryKeys.objects(tenantId, project.project_id, objectFilters),
    queryFn: ({ pageParam }) => api.listMappingObjects(
      tenantId,
      project.project_id,
      objectFilters,
      200,
      pageParam,
    ),
    initialPageParam: undefined as string | undefined,
    getNextPageParam: (page) => page.next_cursor ?? undefined,
  });
  const ledgerState = queryState(objects, project.project_revision);
  // The ledger already reports its own failure; a Systems error alone gets one quiet alert.
  const ledgerFailed = ledgerState.isError || ledgerState.revisionMismatch;
  const permissionLabel = project.is_locked ? "Project locked. Unlock it before making changes." : !hasAppPermission
    ? "Architect permission required to run"
    : !hasTenantLock
      ? "Tenant Lock required to run"
      : "Tenant Lock held";
  const routeParams = { tenantId: String(tenantId), projectId: String(project.project_id) };
  const isSelectedSystem = (code: string) => systemCode?.toLowerCase() === code.toLowerCase();

  const refresh = async () => {
    setSelectedIds(new Set());
    await Promise.all([
      objects.refetch(),
      systems.refetch(),
      ...["mapping-object", "mapping-attribute", "mapping-attributes"].map((prefix) =>
        queryClient.invalidateQueries({ queryKey: [prefix, tenantId, project.project_id] })),
      queryClient.invalidateQueries({ queryKey: ["project", tenantId, project.project_id] }),
      queryClient.invalidateQueries({ queryKey: ["tenant-home", tenantId] }),
    ]);
  };
  const applyFilters = (nextFilters: MappingFilters) => {
    setSelectedIds(new Set());
    setFilters(nextFilters);
  };
  const invalidateLedgers = async () => {
    await Promise.all([
      queryClient.invalidateQueries({
        queryKey: ["mapping-objects", tenantId, project.project_id],
      }),
      queryClient.invalidateQueries({
        queryKey: ["mapping-attributes", tenantId, project.project_id],
      }),
      queryClient.invalidateQueries({ queryKey: ["mapping-filter-systems", tenantId, project.project_id] }),
      queryClient.invalidateQueries({ queryKey: ["mapping-object", tenantId, project.project_id] }),
      queryClient.invalidateQueries({ queryKey: ["mapping-attribute", tenantId, project.project_id] }),
    ]);
  };

  return (
    <WorkflowCommandCenter filterCount={Object.values(filters).filter(Boolean).length} className={`mapping-workspace page-enter${selectedIds.size ? " has-selection" : ""}`}>
      <h1 className="project-section-title sr-only">Mapping</h1>
      <header className="workflow-commandbar mapping-commandbar project-section-toolbar">
        <div className="workflow-command-context mapping-command-context">
          <div className="mapping-layer-header">
            <nav className="target-layer-switch" aria-label="Mapping layer">
              {(["logical", "dimensional"] as const).map((value) => (
                <Link
                  key={value}
                  to="/tenants/$tenantId/mapping/projects/$projectId"
                  params={routeParams}
                  search={{ layer: value }}
                  className={layer === value ? "is-active" : ""}
                  aria-current={layer === value ? "page" : undefined}
                >
                  {value === "logical" ? "Logical" : "Dimensional"}
                </Link>
              ))}
            </nav>
            <span>{layer === "logical" ? "Logical Entities → Silver" : "Dimensional Entities → Gold"}</span>
          </div>

        </div>
        <div className="workflow-command-actions">
          <WorkflowCommandTools />
          <WorkflowMenu><button type="button" className="button button-secondary button-small"
            onClick={() => setExportOpen(true)}>Export</button></WorkflowMenu>
          <RefreshButton ref={refreshButton} refreshing={false} onClick={() => void refresh()} />
          <button
            ref={commandButton}
            className="button button-primary button-small"
            type="button"
            disabled={!hasTenantLock || !hasAppPermission}
            title={permissionLabel}
            onClick={() => setRunDialogOpen(true)}
          >
            Generate mappings
          </button>
        </div>
      </header>
      <WorkflowRunMonitor
        api={api}
        tenantId={tenantId}
        projectId={project.project_id}
        projectRevision={project.project_revision}
        workflow="mapping"
        hasTenantLock={hasTenantLock && hasAppPermission}
        focusRunId={recentRunId}
        onApplied={invalidateLedgers}
      />
      <div className="mapping-system-bar">
        <nav className="workspace-tabs mapping-system-tabs" aria-label="Mapping Systems" aria-busy={systems.isPending}>
          {/* explicitUndefined: a link without a System is active only when none is selected. */}
          <Link to="/tenants/$tenantId/mapping/projects/$projectId" params={routeParams}
            search={{ layer, system: undefined }} activeOptions={{ explicitUndefined: true }}
            className={systemCode ? "" : "is-active"} aria-current={systemCode ? undefined : "page"}>
            All Systems
          </Link>
          {systemsUnavailable ? null : systems.data?.systems.map((system) => (
            <Link key={system.code} to="/tenants/$tenantId/mapping/projects/$projectId" params={routeParams}
              search={{ layer, system: system.code }}
              className={isSelectedSystem(system.code) ? "is-active" : ""}
              aria-current={isSelectedSystem(system.code) ? "page" : undefined}
              aria-label={`${system.code}, ${system.mappings} ${system.mappings === 1 ? "Mapping" : "Mappings"}`}>
              {system.code}<small aria-hidden="true">{system.mappings}</small>
            </Link>
          ))}
        </nav>
        {systemsUnavailable && !ledgerFailed
          ? <p className="field-help" role="alert">Systems could not be loaded. Refresh to retry.</p> : null}
      </div>
      <ProjectRecordReview
        api={api} tenantId={tenantId} projectId={project.project_id} projectRevision={project.project_revision}
        dataset="mapping_object"
        actions={["lock", "unlock", "deactivate", "reactivate", "delete"]}
        deleteIds={new Set(objects.data?.pages.flatMap((page) => page.items)
          .filter((item) => selectedIds.has(item.mapping_object_id) && !item.is_locked)
          .map((item) => item.mapping_object_id) ?? [])}
        selectedIds={selectedIds} hasTenantLock={hasTenantLock && hasAppPermission}
        disabled={objects.isPending || objects.isError || objects.data?.pages.some((page) => page.project_revision !== project.project_revision) === true}
        onApplied={async () => {
          setSelectedIds(new Set());
          await queryClient.invalidateQueries({ predicate: (query) => query.queryKey[1] === tenantId });
          requestAnimationFrame(() => refreshButton.current?.focus());
        }}
      />
      <MappingObjectsLedger
        selectedIds={selectedIds} onSelectionChange={setSelectedIds}
        tenantId={tenantId}
        projectId={project.project_id}
        systemCode={systemCode}
        items={objects.data?.pages.flatMap((page) => page.items) ?? []}
        filters={filters}
        state={ledgerState}
        onApplyFilters={applyFilters}
        onLoadMore={() => void objects.fetchNextPage()}
      />
      {exportOpen ? <MappingExportDialog api={api} tenantId={tenantId} project={project} entityType={entityType}
        systemCodes={systems.data?.systems.map((system) => system.code) ?? []} loading={systems.isPending}
        unavailable={systemsUnavailable}
        initialSystem={systemCode} onClose={() => setExportOpen(false)} /> : null}
      {runDialogOpen ? (
        <MappingRunDialog
          entityType={entityType}
          api={api}
          tenantId={tenantId}
          project={project}
          initialSystemCode={systemCode}
          onClose={() => { setRunDialogOpen(false); commandButton.current?.focus(); }}
          onCompleted={async (workflowRunId) => {
            setRecentRunId(workflowRunId);
            await Promise.all([
              queryClient.invalidateQueries({ queryKey: ["project", tenantId, project.project_id] }),
              queryClient.invalidateQueries({ queryKey: ["tenant-home", tenantId] }),
            ]);
          }}
        />
      ) : null}
    </WorkflowCommandCenter>
  );
}

function queryState(
  query: {
    isPending: boolean;
    isError: boolean;
    error: Error | null;
    data: { pages: { project_revision: number }[] } | undefined;
    hasNextPage: boolean;
    isFetchingNextPage: boolean;
  },
  projectRevision: number,
): MappingLedgerState {
  return {
    isLoading: query.isPending,
    isError: query.isError,
    isDenied: query.error instanceof ApiError && query.error.status === 403,
    revisionMismatch: query.data !== undefined
      && query.data.pages.some((page) => page.project_revision !== projectRevision),
    hasMore: query.hasNextPage,
    isLoadingMore: query.isFetchingNextPage,
  };
}
