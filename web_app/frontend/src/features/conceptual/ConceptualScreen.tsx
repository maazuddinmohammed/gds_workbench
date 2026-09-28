import { ModelLayerActions } from "../model_record_review/ModelLayerActions";
import { useState } from "react";
import { useInfiniteQuery, useQueryClient } from "@tanstack/react-query";

import { ApiError } from "../../core/http";
import type { ModelDetail } from "../models/api";
import { conceptualQueryKeys, type ConceptualApi, type ConceptualFilters } from "./api";
import { ConceptualObjectsLedger, ConceptualRelationshipsLedger } from "./ConceptualLedgers";
import { ModelRecordReview } from "../model_record_review/ModelRecordReview";
import { WorkflowRunDialog } from "../workflows/WorkflowRunDialog";
import { WorkflowRunMonitor } from "../workflows/WorkflowRunMonitor";

type ConceptualView = "objects" | "relationships";

export function ConceptualScreen({
  api,
  tenantId,
  model,
  hasTenantLock,
  canDelete = false,
}: {
  api: ConceptualApi;
  tenantId: number;
  model: ModelDetail;
  hasTenantLock: boolean;
  canDelete?: boolean;
}) {
  const queryClient = useQueryClient();
  const [selectedIds, setSelectedIds] = useState<Set<number>>(new Set());
  const [view, setView] = useState<ConceptualView>("objects");
  const [runDialogOpen, setRunDialogOpen] = useState(false);
  const [recentRunId, setRecentRunId] = useState<number | null>(null);
  const [objectFilters, setObjectFilters] = useState<ConceptualFilters>({ status: "active" });
  const [relationshipFilters, setRelationshipFilters] = useState<ConceptualFilters>({ status: "active" });
  const objectsQuery = useInfiniteQuery({
    queryKey: conceptualQueryKeys.objects(tenantId, model.model_id, objectFilters),
    queryFn: ({ pageParam }) => api.listConceptualObjects(
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
  const relationshipsQuery = useInfiniteQuery({
    queryKey: conceptualQueryKeys.relationships(
      tenantId,
      model.model_id,
      relationshipFilters,
    ),
    queryFn: ({ pageParam }) => api.listConceptualRelationships(
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

  const activeReviewQuery = view === "objects" ? objectsQuery : relationshipsQuery;
  const refresh = async () => {
    setSelectedIds(new Set());
    await Promise.all([
      view === "objects" ? objectsQuery.refetch() : relationshipsQuery.refetch(),
      queryClient.invalidateQueries({ queryKey: ["model", tenantId, model.model_id] }),
      queryClient.invalidateQueries({ queryKey: ["tenant-home", tenantId] }),
    ]);
  };
  const invalidateLedgers = async () => {
    await Promise.all([
      queryClient.invalidateQueries({
        queryKey: ["conceptual-objects", tenantId, model.model_id],
      }),
      queryClient.invalidateQueries({
        queryKey: ["conceptual-relationships", tenantId, model.model_id],
      }),
    ]);
  };

  return (
    <div className="conceptual-page page-enter">
      <header className="workflow-commandbar model-section-toolbar conceptual-commandbar">
        <h1 className="model-section-title sr-only">Conceptual</h1>
        <div className="workflow-command-context">
          <nav className="workflow-tabs" aria-label="Conceptual views">
            <button
              className={view === "objects" ? "is-active" : ""}
              type="button"
              aria-pressed={view === "objects"}
              onClick={() => { setSelectedIds(new Set()); setView("objects"); }}
            >
              Objects
            </button>
            <button
              className={view === "relationships" ? "is-active" : ""}
              type="button"
              aria-pressed={view === "relationships"}
              onClick={() => { setSelectedIds(new Set()); setView("relationships"); }}
            >
              Relationships
            </button>
          </nav>
          <span className={hasTenantLock ? "lock-context is-held" : "lock-context"}>
            {hasTenantLock ? "Tenant Lock held" : "Tenant Lock required to run"}
          </span>
        </div>
        <div className="workflow-command-actions">
          <ModelLayerActions api={api} tenantId={tenantId} modelId={model.model_id} modelRevision={model.model_revision} hasTenantLock={hasTenantLock} canDelete={canDelete} layer="conceptual" onApplied={() => setSelectedIds(new Set())} />
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
            Run Conceptual
          </button>
        </div>
      </header>

      <WorkflowRunMonitor
        api={api}
        tenantId={tenantId}
        modelId={model.model_id}
        modelRevision={model.model_revision}
        workflow="conceptual"
        hasTenantLock={hasTenantLock}
        focusRunId={recentRunId}
        onApplied={invalidateLedgers}
      />

      <ModelRecordReview
        actions={canDelete ? ["lock", "unlock", "deactivate", "reactivate", "delete"] : ["lock", "unlock", "deactivate", "reactivate"]}
        api={api} tenantId={tenantId} modelId={model.model_id} modelRevision={model.model_revision}
        dataset={view === "objects" ? "conceptual_object" : "conceptual_relationship"}
        selectedIds={selectedIds} hasTenantLock={hasTenantLock}
        disabled={(view === "objects" ? objectsQuery : relationshipsQuery).isPending
          || (view === "objects" ? objectsQuery : relationshipsQuery).isError
          || (view === "objects" ? objectsQuery : relationshipsQuery).data?.pages.some(
            (page) => page.model_revision !== model.model_revision,
          ) === true}
        onApplied={async () => {
          setSelectedIds(new Set());
          await Promise.all([
            invalidateLedgers(),
            ...["conceptual-object", "conceptual-relationship", "model", "model-overview"].map(
              (key) => queryClient.invalidateQueries({ queryKey: [key, tenantId, model.model_id] }),
            ),
            queryClient.invalidateQueries({ queryKey: ["tenant-home", tenantId] }),
          ]);
        }}
      />

      {view === "objects" ? (
        <ConceptualObjectsLedger
          tenantId={tenantId}
          modelId={model.model_id}
          items={objectsQuery.data?.pages.flatMap((page) => page.items) ?? []}
          filters={objectFilters}
          state={{
            isLoading: objectsQuery.isPending,
            isError: objectsQuery.isError,
            isDenied: objectsQuery.error instanceof ApiError && objectsQuery.error.status === 403,
            revisionMismatch: objectsQuery.data !== undefined
              && objectsQuery.data.pages.some((page) => page.model_revision !== model.model_revision),
            hasMore: objectsQuery.hasNextPage,
            isLoadingMore: objectsQuery.isFetchingNextPage,
          }}
          selectedIds={selectedIds}
          onSelectionChange={setSelectedIds}
          onApplyFilters={(filters) => { setSelectedIds(new Set()); setObjectFilters(filters); }}
          onLoadMore={() => void objectsQuery.fetchNextPage()}
        />
      ) : (
        <ConceptualRelationshipsLedger
          tenantId={tenantId}
          modelId={model.model_id}
          items={relationshipsQuery.data?.pages.flatMap((page) => page.items) ?? []}
          filters={relationshipFilters}
          state={{
            isLoading: relationshipsQuery.isPending,
            isError: relationshipsQuery.isError,
            isDenied: relationshipsQuery.error instanceof ApiError
              && relationshipsQuery.error.status === 403,
            revisionMismatch: relationshipsQuery.data !== undefined
              && relationshipsQuery.data.pages.some(
                (page) => page.model_revision !== model.model_revision,
              ),
            hasMore: relationshipsQuery.hasNextPage,
            isLoadingMore: relationshipsQuery.isFetchingNextPage,
          }}
          selectedIds={selectedIds}
          onSelectionChange={setSelectedIds}
          onApplyFilters={(filters) => { setSelectedIds(new Set()); setRelationshipFilters(filters); }}
          onLoadMore={() => void relationshipsQuery.fetchNextPage()}
        />
      )}
      {runDialogOpen ? (
        <WorkflowRunDialog
          api={api}
          tenantId={tenantId}
          model={model}
          kind="inference"
          workflow="conceptual"
          executeCreated={(workflowRunId, executionMode, expectedModelRevision) => api.executeConceptualRun(
            tenantId,
            model.model_id,
            workflowRunId,
            executionMode,
            expectedModelRevision,
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
