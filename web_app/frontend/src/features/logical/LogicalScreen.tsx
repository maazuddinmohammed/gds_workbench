import { DdlExportButton } from "../project_targets/DdlExportButton";
import { WorkflowCommandCenter, WorkflowCommandTools, WorkflowMenu } from "../workflows/WorkflowCommandCenter";
import { ProjectLayerActions } from "../project_record_review/ProjectLayerActions";
import { TargetExportButton } from "../project_targets/TargetExportDialog";
import { ProjectRecordReview } from "../project_record_review/ProjectRecordReview";
import { useState } from "react";
import { useInfiniteQuery, useQuery, useQueryClient } from "@tanstack/react-query";

import type {
  LogicalEntityFilters,
  LogicalFilters,
  LogicalRelationshipFilters,
} from "./api";
import type { ProjectDetail } from "../projects/api";
import { loadAllLogicalSubmodels, logicalQueryKeys, type LogicalApi } from "./api";
import {
  LogicalEntitiesLedger,
  LogicalRelationshipsLedger,
  LogicalSubmodelsLedger,
} from "./LogicalLedgers";
import { WorkflowRunDialog } from "../workflows/WorkflowRunDialog";
import { WorkflowRunMonitor } from "../workflows/WorkflowRunMonitor";

type LogicalView = "entities" | "relationships" | "submodels";

export function LogicalScreen({
  api,
  tenantId,
  project,
  hasTenantLock,
  canDelete = false,
}: {
  api: LogicalApi;
  tenantId: number;
  project: ProjectDetail;
  hasTenantLock: boolean;
  canDelete?: boolean;
}) {
  const queryClient = useQueryClient();
  const [view, setView] = useState<LogicalView>("entities");
  const [selectedIds, setSelectedIds] = useState<Set<number>>(new Set());
  const [runDialogOpen, setRunDialogOpen] = useState(false);
  const [recentRunId, setRecentRunId] = useState<number | null>(null);
  const [entityFilters, setEntityFilters] = useState<LogicalEntityFilters>({ status: "active" });
  const [relationshipFilters, setRelationshipFilters] = useState<LogicalRelationshipFilters>({ status: "active" });
  const [submodelFilters, setSubmodelFilters] = useState<LogicalFilters>({ status: "active" });
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
  const entitySubmodelsQuery = useQuery({
    queryKey: logicalQueryKeys.submodelOptions(tenantId, project.project_id),
    queryFn: () => loadAllLogicalSubmodels(api, tenantId, project.project_id),
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
  const submodelsQuery = useInfiniteQuery({
    queryKey: logicalQueryKeys.submodels(tenantId, project.project_id, submodelFilters),
    queryFn: ({ pageParam }) => api.listLogicalSubmodels(
      tenantId,
      project.project_id,
      submodelFilters,
      200,
      pageParam,
    ),
    initialPageParam: undefined as string | undefined,
    getNextPageParam: (lastPage) => lastPage.next_cursor ?? undefined,
    enabled: view === "submodels",
  });

  const activeReviewQuery = view === "entities" ? entitiesQuery : view === "relationships" ? relationshipsQuery : submodelsQuery;
  const refresh = async () => {
    setSelectedIds(new Set());
    await Promise.all([
      view === "entities"
        ? entitiesQuery.refetch()
        : view === "relationships"
            ? relationshipsQuery.refetch()
            : submodelsQuery.refetch(),
      view === "entities" ? entitySubmodelsQuery.refetch() : Promise.resolve(),
      queryClient.invalidateQueries({ queryKey: ["project", tenantId, project.project_id] }),
      queryClient.invalidateQueries({ queryKey: ["tenant-home", tenantId] }),
    ]);
  };
  const invalidateLedgers = async () => {
    await Promise.all([
      queryClient.invalidateQueries({ queryKey: ["logical-entities", tenantId, project.project_id] }),
      queryClient.invalidateQueries({ queryKey: ["logical-attributes", tenantId, project.project_id] }),
      queryClient.invalidateQueries({ queryKey: ["logical-relationships", tenantId, project.project_id] }),
      queryClient.invalidateQueries({ queryKey: ["logical-submodels", tenantId, project.project_id] }),
      queryClient.invalidateQueries({
        queryKey: logicalQueryKeys.submodelOptions(tenantId, project.project_id),
      }),
    ]);
  };

  return (
    <WorkflowCommandCenter filterCount={Object.values(view === "entities" ? entityFilters : view === "relationships" ? relationshipFilters : submodelFilters).filter(Boolean).length} className="logical-page page-enter">
      <header className="workflow-commandbar project-section-toolbar logical-commandbar">
        <h1 className="project-section-title sr-only">Logical</h1>
        <div className="workflow-command-context">
          <nav className="workflow-tabs" aria-label="Logical views">
            {([
              ["entities", "Entities", entitiesQuery],
              ["relationships", "Relationships", relationshipsQuery],
              ["submodels", "Submodels", submodelsQuery],
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
          <WorkflowCommandTools />
          <WorkflowMenu>
          <ProjectLayerActions api={api} tenantId={tenantId} projectId={project.project_id} projectRevision={project.project_revision} hasTenantLock={hasTenantLock} canDelete={canDelete} layer="logical" onApplied={() => setSelectedIds(new Set())} />
          <TargetExportButton api={api} tenantId={tenantId} projectId={project.project_id} projectRevision={project.project_revision} layer="logical" entityIds={view === "entities" && selectedIds.size ? [...selectedIds] : undefined} />
          <DdlExportButton api={api} tenantId={tenantId} projectId={project.project_id} projectRevision={project.project_revision} layer="logical" entityIds={view === "entities" && selectedIds.size ? [...selectedIds] : undefined} />
          </WorkflowMenu>
          <button className="button button-secondary button-small" type="button" disabled={activeReviewQuery.isFetching} onClick={() => void refresh()}>
            {activeReviewQuery.isFetching ? "Refreshing…" : "Refresh"}
          </button>
          <button
            className="button button-primary button-small"
            type="button"
            disabled={!hasTenantLock}
            title={hasTenantLock ? undefined : "Tenant Lock required"}
            onClick={() => setRunDialogOpen(true)}
          >
            Run Logical
          </button>
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
      <ProjectRecordReview
        actions={canDelete ? ["lock", "unlock", "deactivate", "reactivate", "delete"] : ["lock", "unlock", "deactivate", "reactivate"]}
        api={api} tenantId={tenantId} projectId={project.project_id} projectRevision={project.project_revision}
        dataset={view === "entities" ? "logical_entity" : view === "relationships" ? "logical_relationship" : "logical_submodel"} selectedIds={selectedIds} hasTenantLock={hasTenantLock}
        disabled={activeReviewQuery.isPending || activeReviewQuery.isError || activeReviewQuery.data?.pages.some((page) => page.project_revision !== project.project_revision) === true}
        onApplied={async () => {
          setSelectedIds(new Set());
          await queryClient.invalidateQueries({ predicate: (query) => query.queryKey[1] === tenantId });
        }}
      />
      {view === "entities" ? (
        <LogicalEntitiesLedger
          selectedIds={selectedIds} onSelectionChange={setSelectedIds}
          tenantId={tenantId}
          projectId={project.project_id}
          items={entitiesQuery.data?.pages.flatMap((page) => page.items) ?? []}
          filters={entityFilters}
          submodels={entitySubmodelsQuery.data?.items ?? []}
          submodelsState={entitySubmodelsQuery.isPending
            ? "loading"
            : entitySubmodelsQuery.isError
              ? "error"
              : entitySubmodelsQuery.data.projectRevision !== project.project_revision
                ? "revision_mismatch"
                : "ready"}
          state={queryState(entitiesQuery, project.project_revision)}
          onApplyFilters={(next) => { setSelectedIds(new Set()); setEntityFilters(next); }}
          onLoadMore={() => void entitiesQuery.fetchNextPage()}
        />
      ) : view === "relationships" ? (
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
      ) : (
        <LogicalSubmodelsLedger
          selectedIds={selectedIds} onSelectionChange={setSelectedIds}
          tenantId={tenantId}
          projectId={project.project_id}
          items={submodelsQuery.data?.pages.flatMap((page) => page.items) ?? []}
          filters={submodelFilters}
          state={queryState(submodelsQuery, project.project_revision)}
          onApplyFilters={(next) => { setSelectedIds(new Set()); setSubmodelFilters(next); }}
          onLoadMore={() => void submodelsQuery.fetchNextPage()}
        />
      )}
      {runDialogOpen ? (
        <WorkflowRunDialog
          api={api}
          tenantId={tenantId}
          project={project}
          kind="inference"
          workflow="logical"
          executeCreated={(workflowRunId, executionMode, expectedProjectRevision) => api.executeLogicalRun(
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
