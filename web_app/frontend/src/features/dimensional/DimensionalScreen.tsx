import { DdlExportButton } from "../project_targets/DdlExportButton";
import { WorkflowCommandCenter, WorkflowCommandTools, WorkflowMenu } from "../workflows/WorkflowCommandCenter";
import { ProjectLayerActions } from "../project_record_review/ProjectLayerActions";
import { TargetExportButton } from "../project_targets/TargetExportDialog";
import { ProjectRecordReview } from "../project_record_review/ProjectRecordReview";
import { subjectAreaQueryKeys } from "../subject_areas/api";
import { useState } from "react";
import { useInfiniteQuery, useQuery, useQueryClient } from "@tanstack/react-query";

import { ApiError } from "../../core/http";
import type {
  DimensionalObjectFilters,
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
import { RefreshButton } from "../../shared/ui";
import { ModelSubjectAreasLedger } from "../projects/ModelSubjectAreas";

type DimensionalView = "subject_areas" | "entities" | "relationships";

export function DimensionalScreen({
  api,
  tenantId,
  project,
  hasTenantLock,
  canDelete = false,
  initialView,
}: {
  api: DimensionalApi;
  tenantId: number;
  project: ProjectDetail;
  hasTenantLock: boolean;
  canDelete?: boolean;
  initialView?: DimensionalView | undefined;
}) {
  const queryClient = useQueryClient();
  const [view, setView] = useState<DimensionalView>(initialView ?? "entities");
  const [selectedIds, setSelectedIds] = useState<Set<number>>(new Set());
  const [runOperation, setRunOperation] = useState<"build" | "optimize" | null>(null);
  const [recentRunId, setRecentRunId] = useState<number | null>(null);
  const [objectFilters, setObjectFilters] = useState<DimensionalObjectFilters>({ active: true });
  const [relationshipFilters, setRelationshipFilters] = useState<DimensionalRelationshipFilters>({ active: true });
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
  // Same cache entry as the Subject Areas screen, so changes there refresh this filter.
  const subjectAreasQuery = useQuery({
    queryKey: subjectAreaQueryKeys.areas(tenantId, project.project_id),
    queryFn: () => api.listSubjectAreas(tenantId, project.project_id),
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
  // The Subject Areas tab: each active area with this layer's Entities from it.
  const modelAreasQuery = useQuery({
    queryKey: dimensionalQueryKeys.subjectAreas(tenantId, project.project_id),
    queryFn: () => api.listDimensionalSubjectAreas(tenantId, project.project_id),
    enabled: view === "subject_areas",
  });

  const activeReviewQuery = view === "entities" ? objectsQuery : relationshipsQuery;
  const activeFilters = view === "entities" ? objectFilters : view === "relationships" ? relationshipFilters : {};
  const refresh = async () => {
    setSelectedIds(new Set());
    await Promise.all([
      view === "subject_areas" ? modelAreasQuery.refetch()
        : view === "entities" ? objectsQuery.refetch() : relationshipsQuery.refetch(),
      view === "entities" ? subjectAreasQuery.refetch() : Promise.resolve(),
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
    <WorkflowCommandCenter filterCount={Object.values(activeFilters).filter((value) => value !== undefined).length} className="dimensional-page page-enter">
      <header className="workflow-commandbar project-section-toolbar dimensional-commandbar">
        <h1 className="project-section-title sr-only">Dimensional</h1>
        <div className="workflow-command-context">
          <nav className="workflow-tabs" aria-label="Dimensional views">
            {([
              ["subject_areas", "Subject Areas", modelAreasQuery.data ? String(modelAreasQuery.data.items.length) : null],
              ["entities", "Entities", loadedCount(objectsQuery)],
              ["relationships", "Relationships", loadedCount(relationshipsQuery)],
            ] as const).map(([nextView, label, count]) => (
              <button
                key={nextView}
                className={view === nextView ? "is-active" : ""}
                type="button"
                aria-pressed={view === nextView}
                onClick={() => { setSelectedIds(new Set()); setView(nextView); }}
              >
                {label}
                {count !== null ? <span className="command-count" aria-hidden="true" title="Loaded records matching the filters">
                  {count}
                </span> : null}
              </button>
            ))}
          </nav>

        </div>
        <div className="workflow-command-actions">
          <WorkflowCommandTools />
          <WorkflowMenu>
          <ProjectLayerActions api={api} tenantId={tenantId} projectId={project.project_id} projectRevision={project.project_revision} hasTenantLock={hasTenantLock} canDelete={canDelete} layer="dimensional" onApplied={() => setSelectedIds(new Set())} />
          <TargetExportButton api={api} tenantId={tenantId} projectId={project.project_id} projectRevision={project.project_revision} layer="dimensional" entityIds={view === "entities" && selectedIds.size ? [...selectedIds] : undefined} />
          <DdlExportButton api={api} tenantId={tenantId} projectId={project.project_id} projectRevision={project.project_revision} layer="dimensional" entityIds={view === "entities" && selectedIds.size ? [...selectedIds] : undefined} />
          </WorkflowMenu>
          <RefreshButton refreshing={view === "subject_areas" ? modelAreasQuery.isFetching : activeReviewQuery.isFetching}
            onClick={() => void refresh()} />
          <WorkflowMenu label="Run Dimensional" primary>
            <button
              className="button button-secondary button-small"
              type="button"
              disabled={!hasTenantLock}
              title={hasTenantLock ? "Model the chosen Subject Areas, one after another" : "Tenant Lock required"}
              onClick={() => setRunOperation("build")}
            >
              Build
            </button>
            <button
              className="button button-secondary button-small"
              type="button"
              disabled={!hasTenantLock}
              title={hasTenantLock ? "Review the whole model across Subject Areas" : "Tenant Lock required"}
              onClick={() => setRunOperation("optimize")}
            >
              Optimize
            </button>
          </WorkflowMenu>
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
      {view !== "subject_areas" ? <ProjectRecordReview
          actions={canDelete ? ["lock", "unlock", "deactivate", "reactivate", "delete"] : ["lock", "unlock", "deactivate", "reactivate"]}
          api={api} tenantId={tenantId} projectId={project.project_id} projectRevision={project.project_revision}
          dataset={view === "entities" ? "dimensional_entity" : "dimensional_relationship"}
          selectedIds={selectedIds} hasTenantLock={hasTenantLock}
          disabled={activeReviewQuery.isPending || activeReviewQuery.isError || activeReviewQuery.data?.pages.some((page) => page.project_revision !== project.project_revision) === true}
          onApplied={async () => { setSelectedIds(new Set()); await queryClient.invalidateQueries({ predicate: (query) => query.queryKey[1] === tenantId }); }}
        /> : null}
      {view === "subject_areas" ? <ModelSubjectAreasLedger layer="dimensional" tenantId={tenantId}
        projectId={project.project_id} areas={modelAreasQuery.data?.items ?? []}
        state={{
          isLoading: modelAreasQuery.isPending,
          isError: modelAreasQuery.isError,
          revisionMismatch: modelAreasQuery.data !== undefined
            && modelAreasQuery.data.project_revision !== project.project_revision,
        }} /> : view === "entities" ? <DimensionalEntitiesLedger
        selectedIds={selectedIds} onSelectionChange={setSelectedIds}
        tenantId={tenantId}
        projectId={project.project_id}
        items={objectsQuery.data?.pages.flatMap((page) => page.items) ?? []}
        filters={objectFilters}
        subjectAreas={subjectAreasQuery.data?.items ?? []}
        subjectAreasState={subjectAreasQuery.isPending
          ? "loading"
          : subjectAreasQuery.isError
            ? "error"
            : subjectAreasQuery.data.project_revision !== project.project_revision
              ? "revision_mismatch"
              : "ready"}
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
      {runOperation ? (
        <WorkflowRunDialog
          api={api}
          tenantId={tenantId}
          project={project}
          kind="inference"
          workflow="dimensional"
          workflowOperation={runOperation}
          subjectAreaSource={api}
          executeCreated={(workflowRunId, executionMode, expectedProjectRevision) => api.executeDimensionalRun(
            tenantId,
            project.project_id,
            workflowRunId,
            executionMode,
            expectedProjectRevision,
          ).then(() => undefined)}
          onClose={() => setRunOperation(null)}
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

function loadedCount(query: {
  data: { pages: { items: unknown[] }[] } | undefined;
  hasNextPage: boolean;
}): string | null {
  if (!query.data) return null;
  const total = query.data.pages.reduce((sum, page) => sum + page.items.length, 0);
  return `${total}${query.hasNextPage ? "+" : ""}`;
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
