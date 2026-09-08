import { TargetExportButton } from "../model_targets/TargetExportDialog";
import { ModelRecordHistory } from "../model_record_review/ModelRecordHistory";
import { ModelRecordReview } from "../model_record_review/ModelRecordReview";
import { useState } from "react";
import { useInfiniteQuery, useQueryClient } from "@tanstack/react-query";

import { ApiError } from "../../core/http";
import type {
  DimensionalAttributeFilters,
  DimensionalFilters,
  DimensionalRelationshipFilters,
} from "./api";
import type { ModelDetail } from "../models/api";
import { dimensionalQueryKeys, type DimensionalApi } from "./api";
import {
  DimensionalAttributesLedger,
  DimensionalObjectsLedger,
  DimensionalRelationshipsLedger,
} from "./DimensionalLedgers";
import { WorkflowRunDialog } from "../workflows/WorkflowRunDialog";
import { WorkflowRunMonitor } from "../workflows/WorkflowRunMonitor";

type DimensionalView = "objects" | "attributes" | "relationships" | "submodels";

export function DimensionalScreen({
  api,
  tenantId,
  model,
  hasTenantLock,
}: {
  api: DimensionalApi;
  tenantId: number;
  model: ModelDetail;
  hasTenantLock: boolean;
}) {
  const queryClient = useQueryClient();
  const [view, setView] = useState<DimensionalView>("objects");
  const [selectedIds, setSelectedIds] = useState<Set<number>>(new Set());
  const [runDialogOpen, setRunDialogOpen] = useState(false);
  const [recentRunId, setRecentRunId] = useState<number | null>(null);
  const [objectFilters, setObjectFilters] = useState<DimensionalFilters>({});
  const [attributeFilters, setAttributeFilters] = useState<DimensionalAttributeFilters>({});
  const [relationshipFilters, setRelationshipFilters] = useState<DimensionalRelationshipFilters>({});
  const objectsQuery = useInfiniteQuery({
    queryKey: dimensionalQueryKeys.objects(tenantId, model.model_id, objectFilters),
    queryFn: ({ pageParam }) => api.listDimensionalObjects(
      tenantId,
      model.model_id,
      objectFilters,
      200,
      pageParam,
    ),
    initialPageParam: undefined as string | undefined,
    getNextPageParam: (lastPage) => lastPage.next_cursor ?? undefined,
    enabled: view === "objects",
  });
  const attributesQuery = useInfiniteQuery({
    queryKey: dimensionalQueryKeys.attributes(tenantId, model.model_id, attributeFilters),
    queryFn: ({ pageParam }) => api.listDimensionalAttributes(
      tenantId,
      model.model_id,
      attributeFilters,
      200,
      pageParam,
    ),
    initialPageParam: undefined as string | undefined,
    getNextPageParam: (lastPage) => lastPage.next_cursor ?? undefined,
    enabled: view === "attributes",
  });
  const relationshipsQuery = useInfiniteQuery({
    queryKey: dimensionalQueryKeys.relationships(tenantId, model.model_id, relationshipFilters),
    queryFn: ({ pageParam }) => api.listDimensionalRelationships(
      tenantId,
      model.model_id,
      relationshipFilters,
      200,
      pageParam,
    ),
    initialPageParam: undefined as string | undefined,
    getNextPageParam: (lastPage) => lastPage.next_cursor ?? undefined,
    enabled: view === "relationships",
  });

  const activeReviewQuery = view === "objects" ? objectsQuery : view === "attributes" ? attributesQuery : relationshipsQuery;
  const refresh = async () => {
    setSelectedIds(new Set());
    await Promise.all([
      view === "objects"
        ? objectsQuery.refetch()
        : view === "attributes"
          ? attributesQuery.refetch()
          : relationshipsQuery.refetch(),
      queryClient.invalidateQueries({ queryKey: ["model", tenantId, model.model_id] }),
      queryClient.invalidateQueries({ queryKey: ["tenant-home", tenantId] }),
    ]);
  };
  const invalidateLedgers = async () => {
    await Promise.all([
      queryClient.invalidateQueries({
        queryKey: ["dimensional-objects", tenantId, model.model_id],
      }),
      queryClient.invalidateQueries({
        queryKey: ["dimensional-attributes", tenantId, model.model_id],
      }),
      queryClient.invalidateQueries({
        queryKey: ["dimensional-relationships", tenantId, model.model_id],
      }),
    ]);
  };

  return (
    <div className="dimensional-page page-enter">
      <header className="workflow-commandbar dimensional-commandbar">
        <div className="workflow-command-context">
          <span className={hasTenantLock ? "lock-context is-held" : "lock-context"}>
            {hasTenantLock ? "Tenant Lock held" : "Tenant Lock required to run"}
          </span>
          <nav className="workflow-tabs" aria-label="Dimensional views">
            {([
              ["objects", "Objects"],
              ["attributes", "Attributes"],
              ["relationships", "Relationships"],
              ["submodels", "Submodels"],
            ] as const).map(([nextView, label]) => (
              <button
                key={nextView}
                className={view === nextView ? "is-active" : ""}
                type="button"
                aria-pressed={view === nextView}
                onClick={() => { setSelectedIds(new Set()); setView(nextView); }}
              >
                {label}
              </button>
            ))}
          </nav>
        </div>
        <div className="workflow-command-actions">
          <TargetExportButton api={api} tenantId={tenantId} modelId={model.model_id} modelRevision={model.model_revision} layer="dimensional" entityIds={view === "objects" && selectedIds.size ? [...selectedIds] : undefined} />
          <button className="button button-secondary button-small" type="button" onClick={refresh}>
            Refresh
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
        modelId={model.model_id}
        modelRevision={model.model_revision}
        workflow="dimensional"
        hasTenantLock={hasTenantLock}
        focusRunId={recentRunId}
        onApplied={invalidateLedgers}
      />
      {view === "submodels" ? <ModelRecordHistory
        api={api} tenantId={tenantId} modelId={model.model_id} modelRevision={model.model_revision}
        dataset="dimensional_submodel" label="Dimensional Submodels" hasTenantLock={hasTenantLock}
      /> : <>
      <ModelRecordReview
        api={api} tenantId={tenantId} modelId={model.model_id} modelRevision={model.model_revision}
        dataset={view === "objects" ? "dimensional_entity" : view === "attributes" ? "dimensional_attribute" : "dimensional_relationship"}
        selectedIds={selectedIds} hasTenantLock={hasTenantLock}
        disabled={activeReviewQuery.isPending || activeReviewQuery.isError || activeReviewQuery.data?.pages.some((page) => page.model_revision !== model.model_revision) === true}
        onApplied={async () => { setSelectedIds(new Set()); await queryClient.invalidateQueries({ predicate: (query) => query.queryKey[1] === tenantId }); }}
      />
      {view === "objects" ? <DimensionalObjectsLedger
        selectedIds={selectedIds} onSelectionChange={setSelectedIds}
        tenantId={tenantId}
        modelId={model.model_id}
        items={objectsQuery.data?.pages.flatMap((page) => page.items) ?? []}
        filters={objectFilters}
        state={queryState(objectsQuery, model.model_revision)}
        onApplyFilters={(next) => { setSelectedIds(new Set()); setObjectFilters(next); }}
        onLoadMore={() => void objectsQuery.fetchNextPage()}
      /> : view === "attributes" ? <DimensionalAttributesLedger
        selectedIds={selectedIds} onSelectionChange={setSelectedIds}
        tenantId={tenantId}
        modelId={model.model_id}
        items={attributesQuery.data?.pages.flatMap((page) => page.items) ?? []}
        filters={attributeFilters}
        state={queryState(attributesQuery, model.model_revision)}
        onApplyFilters={(next) => { setSelectedIds(new Set()); setAttributeFilters(next); }}
        onLoadMore={() => void attributesQuery.fetchNextPage()}
      /> : <DimensionalRelationshipsLedger
        selectedIds={selectedIds} onSelectionChange={setSelectedIds}
        tenantId={tenantId}
        modelId={model.model_id}
        items={relationshipsQuery.data?.pages.flatMap((page) => page.items) ?? []}
        filters={relationshipFilters}
        state={queryState(relationshipsQuery, model.model_revision)}
        onApplyFilters={(next) => { setSelectedIds(new Set()); setRelationshipFilters(next); }}
        onLoadMore={() => void relationshipsQuery.fetchNextPage()}
      />}
      </>}
      {runDialogOpen ? (
        <WorkflowRunDialog
          api={api}
          tenantId={tenantId}
          model={model}
          kind="inference"
          workflow="dimensional"
          executeCreated={(workflowRunId, executionMode) => api.executeDimensionalRun(
            tenantId,
            model.model_id,
            workflowRunId,
            executionMode,
            model.model_revision,
          ).then(() => undefined)}
          onClose={() => setRunDialogOpen(false)}
          onCreated={async (workflowRunId) => {
            setRecentRunId(workflowRunId);
            await Promise.all([
              queryClient.invalidateQueries({ queryKey: ["model", tenantId, model.model_id] }),
              queryClient.invalidateQueries({ queryKey: ["tenant-home", tenantId] }),
            ]);
          }}
        />
      ) : null}
    </div>
  );
}

function queryState(
  query: {
    isPending: boolean;
    isError: boolean;
    error: Error | null;
    data: { pages: { model_revision: number }[] } | undefined;
    hasNextPage: boolean;
    isFetchingNextPage: boolean;
  },
  modelRevision: number,
) {
  return {
    isLoading: query.isPending,
    isError: query.isError,
    isDenied: query.error instanceof ApiError && query.error.status === 403,
    revisionMismatch: query.data !== undefined
      && query.data.pages.some((page) => page.model_revision !== modelRevision),
    hasMore: query.hasNextPage,
    isLoadingMore: query.isFetchingNextPage,
  };
}
