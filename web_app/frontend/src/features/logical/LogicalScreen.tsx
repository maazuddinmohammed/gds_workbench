import { useState } from "react";
import { useInfiniteQuery, useQuery, useQueryClient } from "@tanstack/react-query";

import type {
  LogicalAttributeFilters,
  LogicalEntityFilters,
  LogicalFilters,
  LogicalRelationshipFilters,
} from "./api";
import type { ModelDetail } from "../models/api";
import { loadAllLogicalSubmodels, logicalQueryKeys, type LogicalApi } from "./api";
import {
  LogicalAttributesLedger,
  LogicalEntitiesLedger,
  LogicalRelationshipsLedger,
  LogicalSubmodelsLedger,
} from "./LogicalLedgers";
import { WorkflowRunDialog } from "../workflows/WorkflowRunDialog";
import { WorkflowRunMonitor } from "../workflows/WorkflowRunMonitor";

type LogicalView = "entities" | "attributes" | "relationships" | "submodels";

export function LogicalScreen({
  api,
  tenantId,
  model,
  hasTenantLock,
}: {
  api: LogicalApi;
  tenantId: number;
  model: ModelDetail;
  hasTenantLock: boolean;
}) {
  const queryClient = useQueryClient();
  const [view, setView] = useState<LogicalView>("entities");
  const [runDialogOpen, setRunDialogOpen] = useState(false);
  const [recentRunId, setRecentRunId] = useState<number | null>(null);
  const [entityFilters, setEntityFilters] = useState<LogicalEntityFilters>({});
  const [attributeFilters, setAttributeFilters] = useState<LogicalAttributeFilters>({});
  const [relationshipFilters, setRelationshipFilters] = useState<LogicalRelationshipFilters>({});
  const [submodelFilters, setSubmodelFilters] = useState<LogicalFilters>({});
  const entitiesQuery = useInfiniteQuery({
    queryKey: logicalQueryKeys.entities(tenantId, model.model_id, entityFilters),
    queryFn: ({ pageParam }) => api.listLogicalEntities(
      tenantId,
      model.model_id,
      entityFilters,
      200,
      pageParam,
    ),
    initialPageParam: undefined as string | undefined,
    getNextPageParam: (lastPage) => lastPage.next_cursor ?? undefined,
    enabled: view === "entities",
  });
  const entitySubmodelsQuery = useQuery({
    queryKey: logicalQueryKeys.submodelOptions(tenantId, model.model_id),
    queryFn: () => loadAllLogicalSubmodels(api, tenantId, model.model_id),
    enabled: view === "entities",
  });
  const attributesQuery = useInfiniteQuery({
    queryKey: logicalQueryKeys.attributes(tenantId, model.model_id, attributeFilters),
    queryFn: ({ pageParam }) => api.listLogicalAttributes(
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
    queryKey: logicalQueryKeys.relationships(tenantId, model.model_id, relationshipFilters),
    queryFn: ({ pageParam }) => api.listLogicalRelationships(
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
  const submodelsQuery = useInfiniteQuery({
    queryKey: logicalQueryKeys.submodels(tenantId, model.model_id, submodelFilters),
    queryFn: ({ pageParam }) => api.listLogicalSubmodels(
      tenantId,
      model.model_id,
      submodelFilters,
      200,
      pageParam,
    ),
    initialPageParam: undefined as string | undefined,
    getNextPageParam: (lastPage) => lastPage.next_cursor ?? undefined,
    enabled: view === "submodels",
  });

  const refresh = async () => {
    await Promise.all([
      view === "entities"
        ? entitiesQuery.refetch()
        : view === "attributes"
          ? attributesQuery.refetch()
          : view === "relationships"
            ? relationshipsQuery.refetch()
            : submodelsQuery.refetch(),
      view === "entities" ? entitySubmodelsQuery.refetch() : Promise.resolve(),
      queryClient.invalidateQueries({ queryKey: ["model", tenantId, model.model_id] }),
      queryClient.invalidateQueries({ queryKey: ["tenant-home", tenantId] }),
    ]);
  };
  const invalidateLedgers = async () => {
    await Promise.all([
      queryClient.invalidateQueries({ queryKey: ["logical-entities", tenantId, model.model_id] }),
      queryClient.invalidateQueries({ queryKey: ["logical-attributes", tenantId, model.model_id] }),
      queryClient.invalidateQueries({ queryKey: ["logical-relationships", tenantId, model.model_id] }),
      queryClient.invalidateQueries({ queryKey: ["logical-submodels", tenantId, model.model_id] }),
      queryClient.invalidateQueries({
        queryKey: logicalQueryKeys.submodelOptions(tenantId, model.model_id),
      }),
    ]);
  };

  return (
    <div className="logical-page page-enter">
      <header className="workflow-commandbar logical-commandbar">
        <div className="workflow-command-context">
          <span className={hasTenantLock ? "lock-context is-held" : "lock-context"}>
            {hasTenantLock ? "Tenant Lock held" : "Tenant Lock required to run"}
          </span>
          <nav className="workflow-tabs" aria-label="Logical views">
            {([
              ["entities", "Entities"],
              ["attributes", "Attributes"],
              ["relationships", "Relationships"],
              ["submodels", "Submodels"],
            ] as const).map(([nextView, label]) => (
              <button
                key={nextView}
                className={view === nextView ? "is-active" : ""}
                type="button"
                aria-pressed={view === nextView}
                onClick={() => setView(nextView)}
              >
                {label}
              </button>
            ))}
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
            Run Logical
          </button>
        </div>
      </header>
      <WorkflowRunMonitor
        api={api}
        tenantId={tenantId}
        modelId={model.model_id}
        modelRevision={model.model_revision}
        workflow="logical"
        hasTenantLock={hasTenantLock}
        focusRunId={recentRunId}
        onApplied={invalidateLedgers}
      />
      {view === "entities" ? (
        <LogicalEntitiesLedger
          tenantId={tenantId}
          modelId={model.model_id}
          items={entitiesQuery.data?.pages.flatMap((page) => page.items) ?? []}
          filters={entityFilters}
          submodels={entitySubmodelsQuery.data?.items ?? []}
          submodelsState={entitySubmodelsQuery.isPending
            ? "loading"
            : entitySubmodelsQuery.isError
              ? "error"
              : entitySubmodelsQuery.data.modelRevision !== model.model_revision
                ? "revision_mismatch"
                : "ready"}
          state={queryState(entitiesQuery, model.model_revision)}
          onApplyFilters={setEntityFilters}
          onLoadMore={() => void entitiesQuery.fetchNextPage()}
        />
      ) : view === "attributes" ? (
        <LogicalAttributesLedger
          tenantId={tenantId}
          modelId={model.model_id}
          items={attributesQuery.data?.pages.flatMap((page) => page.items) ?? []}
          filters={attributeFilters}
          state={queryState(attributesQuery, model.model_revision)}
          onApplyFilters={setAttributeFilters}
          onLoadMore={() => void attributesQuery.fetchNextPage()}
        />
      ) : view === "relationships" ? (
        <LogicalRelationshipsLedger
          tenantId={tenantId}
          modelId={model.model_id}
          items={relationshipsQuery.data?.pages.flatMap((page) => page.items) ?? []}
          filters={relationshipFilters}
          state={queryState(relationshipsQuery, model.model_revision)}
          onApplyFilters={setRelationshipFilters}
          onLoadMore={() => void relationshipsQuery.fetchNextPage()}
        />
      ) : (
        <LogicalSubmodelsLedger
          tenantId={tenantId}
          modelId={model.model_id}
          items={submodelsQuery.data?.pages.flatMap((page) => page.items) ?? []}
          filters={submodelFilters}
          state={queryState(submodelsQuery, model.model_revision)}
          onApplyFilters={setSubmodelFilters}
          onLoadMore={() => void submodelsQuery.fetchNextPage()}
        />
      )}
      {runDialogOpen ? (
        <WorkflowRunDialog
          api={api}
          tenantId={tenantId}
          model={model}
          kind="inference"
          workflow="logical"
          executeCreated={(workflowRunId, executionMode) => api.executeLogicalRun(
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
    data: { pages: { model_revision: number }[] } | undefined;
    hasNextPage: boolean;
    isFetchingNextPage: boolean;
  },
  modelRevision: number,
) {
  return {
    isLoading: query.isPending,
    isError: query.isError,
    revisionMismatch: query.data !== undefined
      && query.data.pages.some((page) => page.model_revision !== modelRevision),
    hasMore: query.hasNextPage,
    isLoadingMore: query.isFetchingNextPage,
  };
}
