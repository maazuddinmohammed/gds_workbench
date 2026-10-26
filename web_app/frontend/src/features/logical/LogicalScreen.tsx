import { DdlExportButton } from "../project_targets/DdlExportButton";
import { WorkflowCommandCenter, WorkflowCommandTools, WorkflowMenu } from "../workflows/WorkflowCommandCenter";
import { ProjectLayerActions } from "../project_record_review/ProjectLayerActions";
import { TargetExportButton } from "../project_targets/TargetExportDialog";
import { ProjectRecordReview } from "../project_record_review/ProjectRecordReview";
import { subjectAreaQueryKeys } from "../subject_areas/api";
import { useState } from "react";
import { useInfiniteQuery, useQuery, useQueryClient } from "@tanstack/react-query";

import type {
  LogicalEntityFilters,
  LogicalRelationshipFilters,
} from "./api";
import type { ProjectDetail } from "../projects/api";
import { logicalQueryKeys, type LogicalApi } from "./api";
import {
  LogicalEntitiesLedger,
  LogicalRelationshipsLedger,
} from "./LogicalLedgers";
import { WorkflowRunDialog } from "../workflows/WorkflowRunDialog";
import { WorkflowRunMonitor } from "../workflows/WorkflowRunMonitor";
import { RefreshButton } from "../../shared/ui";
import { ModelSubjectAreasLedger } from "../projects/ModelSubjectAreas";

type LogicalView = "subject_areas" | "entities" | "relationships";

export function LogicalScreen({
  api,
  tenantId,
  project,
  hasTenantLock,
  canDelete = false,
  initialView,
}: {
  api: LogicalApi;
  tenantId: number;
  project: ProjectDetail;
  hasTenantLock: boolean;
  canDelete?: boolean;
  initialView?: LogicalView | undefined;
}) {
  const queryClient = useQueryClient();
  const [view, setView] = useState<LogicalView>(initialView ?? "entities");
  const [selectedIds, setSelectedIds] = useState<Set<number>>(new Set());
  const [runOperation, setRunOperation] = useState<"build" | "optimize" | null>(null);
  const [recentRunId, setRecentRunId] = useState<number | null>(null);
  const [entityFilters, setEntityFilters] = useState<LogicalEntityFilters>({ active: true });
  const [relationshipFilters, setRelationshipFilters] = useState<LogicalRelationshipFilters>({ active: true });
  const entitiesQuery = useInfiniteQuery({
    queryKey: logicalQueryKeys.entities(tenantId, project.project_id, entityFilters),
    queryFn: ({ pageParam }) => api.listLogicalEntities(
      tenantId,
      project.project_id,
      entityFilters,
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
    queryKey: logicalQueryKeys.relationships(tenantId, project.project_id, relationshipFilters),
    queryFn: ({ pageParam }) => api.listLogicalRelationships(
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
    queryKey: logicalQueryKeys.subjectAreas(tenantId, project.project_id),
    queryFn: () => api.listLogicalSubjectAreas(tenantId, project.project_id),
    enabled: view === "subject_areas",
  });

  const activeReviewQuery = view === "entities" ? entitiesQuery : relationshipsQuery;
  const activeFilters = view === "entities" ? entityFilters : view === "relationships" ? relationshipFilters : {};
  const refresh = async () => {
    setSelectedIds(new Set());
    await Promise.all([
      view === "subject_areas" ? modelAreasQuery.refetch()
        : view === "entities" ? entitiesQuery.refetch() : relationshipsQuery.refetch(),
      view === "entities" ? subjectAreasQuery.refetch() : Promise.resolve(),
      queryClient.invalidateQueries({ queryKey: ["project", tenantId, project.project_id] }),
      queryClient.invalidateQueries({ queryKey: ["tenant-home", tenantId] }),
    ]);
  };
  const invalidateLedgers = async () => {
    await Promise.all([
      queryClient.invalidateQueries({ queryKey: ["logical-entities", tenantId, project.project_id] }),
      queryClient.invalidateQueries({ queryKey: ["logical-attributes", tenantId, project.project_id] }),
      queryClient.invalidateQueries({ queryKey: ["logical-relationships", tenantId, project.project_id] }),
    ]);
  };

  return (
    <WorkflowCommandCenter filterCount={Object.values(activeFilters).filter((value) => value !== undefined).length} className="logical-page page-enter">
      <header className="workflow-commandbar project-section-toolbar logical-commandbar">
        <h1 className="project-section-title sr-only">Logical</h1>
        <div className="workflow-command-context">
          <nav className="workflow-tabs" aria-label="Logical views">
            {([
              ["subject_areas", "Subject Areas", modelAreasQuery.data ? String(modelAreasQuery.data.items.length) : null],
              ["entities", "Entities", loadedCount(entitiesQuery)],
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
          <ProjectLayerActions api={api} tenantId={tenantId} projectId={project.project_id} projectRevision={project.project_revision} hasTenantLock={hasTenantLock} canDelete={canDelete} layer="logical" onApplied={() => setSelectedIds(new Set())} />
          <TargetExportButton api={api} tenantId={tenantId} projectId={project.project_id} projectRevision={project.project_revision} layer="logical" entityIds={view === "entities" && selectedIds.size ? [...selectedIds] : undefined} />
          <DdlExportButton api={api} tenantId={tenantId} projectId={project.project_id} projectRevision={project.project_revision} layer="logical" entityIds={view === "entities" && selectedIds.size ? [...selectedIds] : undefined} />
          </WorkflowMenu>
          <RefreshButton refreshing={view === "subject_areas" ? modelAreasQuery.isFetching : activeReviewQuery.isFetching}
            onClick={() => void refresh()} />
          <WorkflowMenu label="Run Logical" primary>
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
        workflow="logical"
        hasTenantLock={hasTenantLock}
        focusRunId={recentRunId}
        onApplied={invalidateLedgers}
      />
      {view !== "subject_areas" ? <ProjectRecordReview
          actions={canDelete ? ["lock", "unlock", "deactivate", "reactivate", "delete"] : ["lock", "unlock", "deactivate", "reactivate"]}
          api={api} tenantId={tenantId} projectId={project.project_id} projectRevision={project.project_revision}
          dataset={view === "entities" ? "logical_entity" : "logical_relationship"} selectedIds={selectedIds} hasTenantLock={hasTenantLock}
          disabled={activeReviewQuery.isPending || activeReviewQuery.isError || activeReviewQuery.data?.pages.some((page) => page.project_revision !== project.project_revision) === true}
          onApplied={async () => {
            setSelectedIds(new Set());
            await queryClient.invalidateQueries({ predicate: (query) => query.queryKey[1] === tenantId });
          }}
        /> : null}
      {view === "subject_areas" ? (
        <ModelSubjectAreasLedger layer="logical" tenantId={tenantId} projectId={project.project_id}
          areas={modelAreasQuery.data?.items ?? []}
          state={{
            isLoading: modelAreasQuery.isPending,
            isError: modelAreasQuery.isError,
            revisionMismatch: modelAreasQuery.data !== undefined
              && modelAreasQuery.data.project_revision !== project.project_revision,
          }} />
      ) : view === "entities" ? (
        <LogicalEntitiesLedger
          selectedIds={selectedIds} onSelectionChange={setSelectedIds}
          tenantId={tenantId}
          projectId={project.project_id}
          items={entitiesQuery.data?.pages.flatMap((page) => page.items) ?? []}
          filters={entityFilters}
          subjectAreas={subjectAreasQuery.data?.items ?? []}
          subjectAreasState={subjectAreasQuery.isPending
            ? "loading"
            : subjectAreasQuery.isError
              ? "error"
              : subjectAreasQuery.data.project_revision !== project.project_revision
                ? "revision_mismatch"
                : "ready"}
          state={queryState(entitiesQuery, project.project_revision)}
          onApplyFilters={(next) => { setSelectedIds(new Set()); setEntityFilters(next); }}
          onLoadMore={() => void entitiesQuery.fetchNextPage()}
        />
      ) : (
        <LogicalRelationshipsLedger
          selectedIds={selectedIds} onSelectionChange={setSelectedIds}
          tenantId={tenantId}
          projectId={project.project_id}
          items={relationshipsQuery.data?.pages.flatMap((page) => page.items) ?? []}
          filters={relationshipFilters}
          state={queryState(relationshipsQuery, project.project_revision)}
          onApplyFilters={(next) => { setSelectedIds(new Set()); setRelationshipFilters(next); }}
          onLoadMore={() => void relationshipsQuery.fetchNextPage()}
        />
      )}
      {runOperation ? (
        <WorkflowRunDialog
          api={api}
          tenantId={tenantId}
          project={project}
          kind="inference"
          workflow="logical"
          workflowOperation={runOperation}
          subjectAreaSource={api}
          executeCreated={(workflowRunId, executionMode, expectedProjectRevision) => api.executeLogicalRun(
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
    data: { pages: { project_revision: number }[] } | undefined;
    hasNextPage: boolean;
    isFetchingNextPage: boolean;
  },
  projectRevision: number,
) {
  return {
    isLoading: query.isPending,
    isError: query.isError,
    revisionMismatch: query.data !== undefined
      && query.data.pages.some((page) => page.project_revision !== projectRevision),
    hasMore: query.hasNextPage,
    isLoadingMore: query.isFetchingNextPage,
  };
}
