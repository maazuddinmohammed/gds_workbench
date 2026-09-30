import { WorkflowCommandCenter, WorkflowCommandTools } from "../workflows/WorkflowCommandCenter";
import { Link } from "@tanstack/react-router";
import { ModelRecordReview } from "../model_record_review/ModelRecordReview";
import { useRef, useState } from "react";
import { useInfiniteQuery, useQuery, useQueryClient } from "@tanstack/react-query";

import { ApiError } from "../../core/http";
import type { ModelDetail } from "../models/api";
import { WorkflowRunMonitor } from "../workflows/WorkflowRunMonitor";
import { loadMappingFilterSystems, mappingQueryKeys, type MappingApi, type MappingFilters, type MappingEntityType } from "./api";
import {
  MappingObjectsLedger,
  type MappingLedgerState,
} from "./MappingLedgers";
import { MappingRunDialog } from "./MappingRunDialog";

export function MappingScreen({
  api,
  tenantId,
  model,
  hasTenantLock,
  hasAppPermission,
  layer,
}: {
  api: MappingApi;
  tenantId: number;
  model: ModelDetail;
  hasTenantLock: boolean;
  hasAppPermission: boolean;
  layer: "logical" | "dimensional";
}) {
  const queryClient = useQueryClient();
  const commandButton = useRef<HTMLButtonElement>(null);
  const refreshButton = useRef<HTMLButtonElement>(null);
  const [selectedIds, setSelectedIds] = useState<Set<number>>(new Set());
  const [runDialogOpen, setRunDialogOpen] = useState(false);
  const [recentRunId, setRecentRunId] = useState<number | null>(null);
  const [filters, setFilters] = useState<MappingFilters>({});
  const entityType: MappingEntityType = layer === "logical" ? "logical_entity" : "dimensional_entity";
  const objectFilters = { ...filters, entityType };
  const sourceChoices = useQuery({
    queryKey: ["mapping-filter-systems", tenantId, model.model_id, entityType],
    queryFn: () => loadMappingFilterSystems(api, tenantId, model.model_id, entityType),
  });
  const objects = useInfiniteQuery({
    queryKey: mappingQueryKeys.objects(tenantId, model.model_id, objectFilters),
    queryFn: ({ pageParam }) => api.listMappingObjects(
      tenantId,
      model.model_id,
      objectFilters,
      200,
      pageParam,
    ),
    initialPageParam: undefined as string | undefined,
    getNextPageParam: (page) => page.next_cursor ?? undefined,
  });
  const permissionLabel = !hasAppPermission
    ? "Architect permission required to run"
    : !hasTenantLock
      ? "Tenant Lock required to run"
      : "Tenant Lock held";

  const refresh = async () => {
    setSelectedIds(new Set());
    await Promise.all([
      objects.refetch(),
      sourceChoices.refetch(),
      ...["mapping-object", "mapping-attribute", "mapping-attributes"].map((prefix) =>
        queryClient.invalidateQueries({ queryKey: [prefix, tenantId, model.model_id] })),
      queryClient.invalidateQueries({ queryKey: ["model", tenantId, model.model_id] }),
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
        queryKey: ["mapping-objects", tenantId, model.model_id],
      }),
      queryClient.invalidateQueries({
        queryKey: ["mapping-attributes", tenantId, model.model_id],
      }),
      queryClient.invalidateQueries({ queryKey: ["mapping-filter-systems", tenantId, model.model_id] }),
      queryClient.invalidateQueries({ queryKey: ["mapping-object", tenantId, model.model_id] }),
      queryClient.invalidateQueries({ queryKey: ["mapping-attribute", tenantId, model.model_id] }),
    ]);
  };

  return (
    <WorkflowCommandCenter filterCount={Object.values(filters).filter(Boolean).length} className={`mapping-workspace page-enter${selectedIds.size ? " has-selection" : ""}`}>
      <h1 className="model-section-title sr-only">Mapping</h1>
      <header className="workflow-commandbar mapping-commandbar model-section-toolbar">
        <div className="workflow-command-context mapping-command-context">
          <div className="mapping-layer-header">
            <nav className="target-layer-switch" aria-label="Mapping layer">
              {(["logical", "dimensional"] as const).map((value) => (
                <Link
                  key={value}
                  to="/tenants/$tenantId/mapping/models/$modelId"
                  params={{ tenantId: String(tenantId), modelId: String(model.model_id) }}
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
          <button ref={refreshButton} className="button button-secondary button-small" type="button" onClick={() => void refresh()}>
            Refresh
          </button>
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
        modelId={model.model_id}
        modelRevision={model.model_revision}
        workflow="mapping"
        hasTenantLock={hasTenantLock && hasAppPermission}
        focusRunId={recentRunId}
        onApplied={invalidateLedgers}
      />
      <ModelRecordReview
        api={api} tenantId={tenantId} modelId={model.model_id} modelRevision={model.model_revision}
        dataset="mapping_object"
        selectedIds={selectedIds} hasTenantLock={hasTenantLock && hasAppPermission}
        disabled={objects.isPending || objects.isError || objects.data?.pages.some((page) => page.model_revision !== model.model_revision) === true}
        onApplied={async () => {
          setSelectedIds(new Set());
          await queryClient.invalidateQueries({ predicate: (query) => query.queryKey[1] === tenantId });
          requestAnimationFrame(() => refreshButton.current?.focus());
        }}
      />
      <MappingObjectsLedger
        sourceChoices={{ codes: sourceChoices.data?.codes ?? [], isLoading: sourceChoices.isPending,
          isUnavailable: sourceChoices.isError || (sourceChoices.data !== undefined && sourceChoices.data.modelRevision !== model.model_revision) }}
        selectedIds={selectedIds} onSelectionChange={setSelectedIds}
        tenantId={tenantId}
        modelId={model.model_id}
        items={objects.data?.pages.flatMap((page) => page.items) ?? []}
        filters={filters}
        state={queryState(objects, model.model_revision)}
        onApplyFilters={applyFilters}
        onLoadMore={() => void objects.fetchNextPage()}
      />
      {runDialogOpen ? (
        <MappingRunDialog
          entityType={entityType}
          api={api}
          tenantId={tenantId}
          model={model}
          onClose={() => { setRunDialogOpen(false); commandButton.current?.focus(); }}
          onCompleted={async (workflowRunId) => {
            setRecentRunId(workflowRunId);
            await Promise.all([
              queryClient.invalidateQueries({ queryKey: ["model", tenantId, model.model_id] }),
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
    data: { pages: { model_revision: number }[] } | undefined;
    hasNextPage: boolean;
    isFetchingNextPage: boolean;
  },
  modelRevision: number,
): MappingLedgerState {
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
