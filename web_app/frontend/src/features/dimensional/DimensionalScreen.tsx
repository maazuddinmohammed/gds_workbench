import { DdlExportButton } from "../project_targets/DdlExportButton";
import { WorkflowCommandCenter, WorkflowCommandTools, WorkflowMenu } from "../workflows/WorkflowCommandCenter";
import { ProjectLayerActions } from "../project_record_review/ProjectLayerActions";
import { TargetExportButton } from "../project_targets/TargetExportDialog";
import { ProjectRecordHistory } from "../project_record_review/ProjectRecordHistory";
import { ProjectRecordReview } from "../project_record_review/ProjectRecordReview";
import { useState } from "react";
import { useInfiniteQuery, useIsFetching, useQueryClient } from "@tanstack/react-query";

import { ApiError } from "../../core/http";
import type {
  DimensionalFilters,
  DimensionalRelationshipFilters,
} from "./api";
import type { ProjectDetail } from "../projects/api";
import { dimensionalQueryKeys, type DimensionalApi } from "./api";
import {
  DimensionalEntitiesLedger,
  DimensionalRelationshipsLedger,
} from "./DimensionalLedgers";
import { WorkflowRunDialog } from "../workflows/WorkflowRunDialog";
import { WorkflowRunMonitor } from "../workflows/WorkflowRunMonitor";

type DimensionalView = "entities" | "relationships" | "submodels";

export function DimensionalScreen({
  api,
  tenantId,
  project,
  hasTenantLock,
  canDelete = false,
}: {
  api: DimensionalApi;
  tenantId: number;
  project: ProjectDetail;
  hasTenantLock: boolean;
  canDelete?: boolean;
}) {
  const queryClient = useQueryClient();
  const [view, setView] = useState<DimensionalView>("entities");
  const [selectedIds, setSelectedIds] = useState<Set<number>>(new Set());
  const [runDialogOpen, setRunDialogOpen] = useState(false);
  const [recentRunId, setRecentRunId] = useState<number | null>(null);
  const [objectFilters, setObjectFilters] = useState<DimensionalFilters>({ status: "active" });
  const [relationshipFilters, setRelationshipFilters] = useState<DimensionalRelationshipFilters>({ status: "active" });
  const objectsQuery = useInfiniteQuery({
    queryKey: dimensionalQueryKeys.objects(tenantId, project.project_id, objectFilters),
    queryFn: ({ pageParam }) => api.listDimensionalObjects(
      tenantId,
      project.project_id,
      objectFilters,
      200,
      pageParam,
    ),
    initialPageParam: undefined as string | undefined,
    getNextPageParam: (lastPage) => lastPage.next_cursor ?? undefined,
    enabled: view === "entities",
  });
  const relationshipsQuery = useInfiniteQuery({
    queryKey: dimensionalQueryKeys.relationships(tenantId, project.project_id, relationshipFilters),
    queryFn: ({ pageParam }) => api.listDimensionalRelationships(
      tenantId,
      project.project_id,
      relationshipFilters,
      200,
      pageParam,
    ),
    initialPageParam: undefined as string | undefined,
    getNextPageParam: (lastPage) => lastPage.next_cursor ?? undefined,
    enabled: view === "relationships",
  });

  const activeReviewQuery = view === "entities" ? objectsQuery : relationshipsQuery;
  const submodelsFetching = useIsFetching({ queryKey: ["project-record-history", tenantId, project.project_id, "dimensional_submodel"] }) > 0;
  const refreshing = view === "submodels" ? submodelsFetching : activeReviewQuery.isFetching;
  const refresh = async () => {
    setSelectedIds(new Set());
    await Promise.all([
      view === "submodels"
        ? queryClient.invalidateQueries({ queryKey: ["project-record-history", tenantId, project.project_id, "dimensional_submodel"] })
        : view === "entities"
        ? objectsQuery.refetch()
        : relationshipsQuery.refetch(),
      queryClient.invalidateQueries({ queryKey: ["project", tenantId, project.project_id] }),
      queryClient.invalidateQueries({ queryKey: ["tenant-home", tenantId] }),
    ]);
  };
  const invalidateLedgers = async () => {
    await Promise.all([
      queryClient.invalidateQueries({
        queryKey: ["dimensional-objects", tenantId, project.project_id],
      }),
      queryClient.invalidateQueries({
        queryKey: ["dimensional-attributes", tenantId, project.project_id],
      }),
      queryClient.invalidateQueries({
        queryKey: ["dimensional-relationships", tenantId, project.project_id],
      }),
    ]);
  };

  return (
    <WorkflowCommandCenter filterCount={Object.values(view === "entities" ? objectFilters : relationshipFilters).filter(Boolean).length} className="dimensional-page page-enter">
      <header className="workflow-commandbar project-section-toolbar dimensional-commandbar">
        <h1 className="project-section-title sr-only">Dimensional</h1>
        <div className="workflow-command-context">
          <nav className="workflow-tabs" aria-label="Dimensional views">
            {([
              ["entities", "Entities", objectsQuery],
              ["relationships", "Relationships", relationshipsQuery],
              ["submodels", "Submodels", null],
            ] as const).map(([nextView, label, query]) => (
              <button
                key={nextView}
                className={view === nextView ? "is-active" : ""}
                type="button"
                aria-pressed={view === nextView}
                onClick={() => { setSelectedIds(new Set()); setView(nextView); }}
              >
                {label}
                {query?.data ? <span className="command-count" aria-hidden="true" title="Loaded records matching the filters">
                  {query.data.pages.reduce((total, page) => total + page.items.length, 0)}{query.hasNextPage ? "+" : ""}
                </span> : null}
              </button>
            ))}
          </nav>

        </div>
        <div className="workflow-command-actions">
          <WorkflowCommandTools filters={view !== "submodels"} />
          <WorkflowMenu>
          <ProjectLayerActions api={api} tenantId={tenantId} projectId={project.project_id} projectRevision={project.project_revision} hasTenantLock={hasTenantLock} canDelete={canDelete} layer="dimensional" onApplied={() => setSelectedIds(new Set())} />
          <TargetExportButton api={api} tenantId={tenantId} projectId={project.project_id} projectRevision={project.project_revision} layer="dimensional" entityIds={view === "entities" && selectedIds.size ? [...selectedIds] : undefined} />
          <DdlExportButton api={api} tenantId={tenantId} projectId={project.project_id} projectRevision={project.project_revision} layer="dimensional" entityIds={view === "entities" && selectedIds.size ? [...selectedIds] : undefined} />
          </WorkflowMenu>
          <button className="button button-secondary button-small" type="button" disabled={refreshing} onClick={() => void refresh()}>
            {refreshing ? "Refreshing…" : "Refresh"}
          </button>
          <button
            className="button button-primary button-small"
            type="button"
            disabled={!hasTenantLock}
            title={hasTenantLock ? undefined : "Tenant Lock required"}
            onClick={() => setRunDialogOpen(true)}
          >
            Run Dimensional
          </button>
        </div>
      </header>
      <WorkflowRunMonitor
        api={api}
        tenantId={tenantId}
        projectId={project.project_id}
        projectRevision={project.project_revision}
        workflow="dimensional"
        hasTenantLock={hasTenantLock}
        focusRunId={recentRunId}
        onApplied={invalidateLedgers}
      />
      {view === "submodels" ? <ProjectRecordHistory
        api={api} tenantId={tenantId} projectId={project.project_id} projectRevision={project.project_revision}
        dataset="dimensional_submodel" label="Dimensional Submodels" hasTenantLock={hasTenantLock}
        showHeader={false} actions={canDelete ? ["lock", "unlock", "deactivate", "reactivate", "delete"] : ["lock", "unlock", "deactivate", "reactivate"]}
      /> : <>
      <ProjectRecordReview
        actions={canDelete ? ["lock", "unlock", "deactivate", "reactivate", "delete"] : ["lock", "unlock", "deactivate", "reactivate"]}
        api={api} tenantId={tenantId} projectId={project.project_id} projectRevision={project.project_revision}
        dataset={view === "entities" ? "dimensional_entity" : "dimensional_relationship"}
        selectedIds={selectedIds} hasTenantLock={hasTenantLock}
        disabled={activeReviewQuery.isPending || activeReviewQuery.isError || activeReviewQuery.data?.pages.some((page) => page.project_revision !== project.project_revision) === true}
        onApplied={async () => { setSelectedIds(new Set()); await queryClient.invalidateQueries({ predicate: (query) => query.queryKey[1] === tenantId }); }}
      />
      {view === "entities" ? <DimensionalEntitiesLedger
        selectedIds={selectedIds} onSelectionChange={setSelectedIds}
        tenantId={tenantId}
        projectId={project.project_id}
        items={objectsQuery.data?.pages.flatMap((page) => page.items) ?? []}
        filters={objectFilters}
        state={queryState(objectsQuery, project.project_revision)}
        onApplyFilters={(next) => { setSelectedIds(new Set()); setObjectFilters(next); }}
        onLoadMore={() => void objectsQuery.fetchNextPage()}
      /> : <DimensionalRelationshipsLedger
        selectedIds={selectedIds} onSelectionChange={setSelectedIds}
        tenantId={tenantId}
        projectId={project.project_id}
        items={relationshipsQuery.data?.pages.flatMap((page) => page.items) ?? []}
        filters={relationshipFilters}
        state={queryState(relationshipsQuery, project.project_revision)}
        onApplyFilters={(next) => { setSelectedIds(new Set()); setRelationshipFilters(next); }}
        onLoadMore={() => void relationshipsQuery.fetchNextPage()}
      />}
      </>}
      {runDialogOpen ? (
        <WorkflowRunDialog
          api={api}
          tenantId={tenantId}
          project={project}
          kind="inference"
          workflow="dimensional"
          logicalEntitySource={api}
          executeCreated={(workflowRunId, executionMode, expectedProjectRevision) => api.executeDimensionalRun(
            tenantId,
            project.project_id,
            workflowRunId,
            executionMode,
            expectedProjectRevision,
          ).then(() => undefined)}
          onClose={() => setRunDialogOpen(false)}
          onCreated={async (workflowRunId) => {
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
) {
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
