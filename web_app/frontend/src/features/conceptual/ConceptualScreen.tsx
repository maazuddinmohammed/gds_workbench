import { useState } from "react";
import { useInfiniteQuery, useQueryClient } from "@tanstack/react-query";

import { ApiError } from "../../core/http";
import type { ModelDetail } from "../models/api";
import { conceptualQueryKeys, type ConceptualApi, type ConceptualFilters } from "./api";
import { ConceptualObjectsLedger, ConceptualRelationshipsLedger } from "./ConceptualLedgers";
import { WorkflowRunDialog } from "../workflows/WorkflowRunDialog";

type ConceptualView = "objects" | "relationships";

export function ConceptualScreen({
  api,
  tenantId,
  model,
  hasTenantLock,
}: {
  api: ConceptualApi;
  tenantId: number;
  model: ModelDetail;
  hasTenantLock: boolean;
}) {
  const queryClient = useQueryClient();
  const [view, setView] = useState<ConceptualView>("objects");
  const [runDialogOpen, setRunDialogOpen] = useState(false);
  const [objectFilters, setObjectFilters] = useState<ConceptualFilters>({});
  const [relationshipFilters, setRelationshipFilters] = useState<ConceptualFilters>({});
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

  const refresh = async () => {
    await Promise.all([
      view === "objects" ? objectsQuery.refetch() : relationshipsQuery.refetch(),
      queryClient.invalidateQueries({ queryKey: ["model", tenantId, model.model_id] }),
      queryClient.invalidateQueries({ queryKey: ["tenant-home", tenantId] }),
    ]);
  };

  return (
    <div className="conceptual-page page-enter">
      <header className="workflow-commandbar conceptual-commandbar">
        <div className="workflow-command-context">
          <span className={hasTenantLock ? "lock-context is-held" : "lock-context"}>
            {hasTenantLock ? "Tenant Lock held" : "Tenant Lock required to run"}
          </span>
          <nav className="workflow-tabs" aria-label="Conceptual views">
            <button
              className={view === "objects" ? "is-active" : ""}
              type="button"
              aria-pressed={view === "objects"}
              onClick={() => setView("objects")}
            >
              Objects
            </button>
            <button
              className={view === "relationships" ? "is-active" : ""}
              type="button"
              aria-pressed={view === "relationships"}
              onClick={() => setView("relationships")}
            >
              Relationships
            </button>
          </nav>
        </div>
        <div className="workflow-command-actions">
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
            Run Conceptual
          </button>
        </div>
      </header>

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
          onApplyFilters={setObjectFilters}
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
          onApplyFilters={setRelationshipFilters}
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
          executeCreated={(workflowRunId, executionMode) => api.executeConceptualRun(
            tenantId,
            model.model_id,
            workflowRunId,
            executionMode,
            model.model_revision,
          ).then(() => undefined)}
          onClose={() => setRunDialogOpen(false)}
          onCreated={async () => {
            await Promise.all([
              queryClient.invalidateQueries({
                queryKey: ["conceptual-objects", tenantId, model.model_id],
              }),
              queryClient.invalidateQueries({
                queryKey: ["conceptual-relationships", tenantId, model.model_id],
              }),
              queryClient.invalidateQueries({ queryKey: ["model", tenantId, model.model_id] }),
              queryClient.invalidateQueries({ queryKey: ["tenant-home", tenantId] }),
            ]);
          }}
        />
      ) : null}
    </div>
  );
}
