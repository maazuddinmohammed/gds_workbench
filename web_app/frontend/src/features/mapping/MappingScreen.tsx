import { ModelRecordReview } from "../model_record_review/ModelRecordReview";
import { useRef, useState } from "react";
import { useInfiniteQuery, useQueryClient } from "@tanstack/react-query";
import { Link } from "@tanstack/react-router";

import { ApiError } from "../../core/http";
import type { ModelDetail } from "../models/api";
import { WorkflowRunMonitor } from "../workflows/WorkflowRunMonitor";
import { mappingQueryKeys, type MappingApi, type MappingFilters, type MappingDependency, type MappingEntityType } from "./api";
import {
  MappingDependenciesLedger,
  MappingObjectsLedger,
  type MappingLedgerState,
} from "./MappingLedgers";
import { MappingDependencyDialog } from "./MappingDependencyDialog";
import { MappingRunDialog } from "./MappingRunDialog";

type MappingView = "dependencies" | "objects";

export function MappingScreen({
  api,
  tenantId,
  model,
  hasTenantLock,
  hasAppPermission,
  initialView,
  layer,
}: {
  api: MappingApi;
  tenantId: number;
  model: ModelDetail;
  hasTenantLock: boolean;
  hasAppPermission: boolean;
  initialView?: MappingView;
  layer: "logical" | "dimensional";
}) {
  const queryClient = useQueryClient();
  const commandButton = useRef<HTMLButtonElement>(null);
  const [view, setView] = useState<MappingView>(initialView ?? "dependencies");
  const [selectedIds, setSelectedIds] = useState<Set<number>>(new Set());
  const [dependencyEditor, setDependencyEditor] = useState<MappingDependency | null | undefined>(undefined);
  const [runDialogOpen, setRunDialogOpen] = useState(false);
  const [recentRunId, setRecentRunId] = useState<number | null>(null);
  const [filters, setFilters] = useState<Record<MappingView, MappingFilters>>({
    dependencies: {},
    objects: {},
  });
  const entityType: MappingEntityType = layer === "logical" ? "logical_entity" : "dimensional_entity";
  const dependencyFilters = { ...filters.dependencies, entityType };
  const objectFilters = { ...filters.objects, entityType };
  const dependencies = useInfiniteQuery({
    queryKey: mappingQueryKeys.dependencies(tenantId, model.model_id, dependencyFilters),
    queryFn: ({ pageParam }) => api.listMappingDependencies(
      tenantId,
      model.model_id,
      dependencyFilters,
      200,
      pageParam,
    ),
    initialPageParam: undefined as string | undefined,
    getNextPageParam: (page) => page.next_cursor ?? undefined,
    enabled: view === "dependencies",
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
    enabled: view === "objects",
  });
  const activeQuery = view === "dependencies" ? dependencies : objects;
  const permissionLabel = !hasAppPermission
    ? "Architect permission required to run"
    : !hasTenantLock
      ? "Tenant Lock required to run"
      : "Tenant Lock held";

  const refresh = async () => {
    setSelectedIds(new Set());
    await Promise.all([
      activeQuery.refetch(),
      queryClient.invalidateQueries({ queryKey: ["model", tenantId, model.model_id] }),
      queryClient.invalidateQueries({ queryKey: ["tenant-home", tenantId] }),
    ]);
  };
  const setViewFilters = (nextFilters: MappingFilters) => {
    setSelectedIds(new Set());
    setFilters((current) => ({ ...current, [view]: nextFilters }));
  };
  const invalidateLedgers = async () => {
    await Promise.all([
      queryClient.invalidateQueries({
        queryKey: ["mapping-dependencies", tenantId, model.model_id],
      }),
      queryClient.invalidateQueries({
        queryKey: ["mapping-objects", tenantId, model.model_id],
      }),
      queryClient.invalidateQueries({
        queryKey: ["mapping-attributes", tenantId, model.model_id],
      }),
    ]);
  };

  return (
    <main className="workspace mapping-workspace page-enter">
      <header className="mapping-layer-header">
        <h1>Mapping</h1>
        <nav className="target-layer-switch" aria-label="Mapping layer">
          {(["logical", "dimensional"] as const).map((value) => (
            <Link
              key={value}
              to="/tenants/$tenantId/mapping/models/$modelId"
              params={{ tenantId: String(tenantId), modelId: String(model.model_id) }}
              search={{ layer: value, view }}
              className={layer === value ? "is-active" : ""}
              aria-current={layer === value ? "page" : undefined}
            >
              {value === "logical" ? "Logical" : "Dimensional"}
            </Link>
          ))}
        </nav>
        <span>{layer === "logical" ? "Logical Entities → Silver" : "Dimensional Entities → Gold"}</span>
      </header>
      <header className="workflow-commandbar mapping-commandbar">
        <div className="workflow-command-context mapping-command-context">
          <Link
            className="text-action"
            aria-label="Back to Mapping Models"
            to="/tenants/$tenantId/mapping"
            params={{ tenantId: String(tenantId) }}
          >
            ← Back to Models
          </Link>
          <span className={hasTenantLock && hasAppPermission ? "lock-context is-held" : "lock-context"}>
            {permissionLabel}
          </span>
          <nav className="workflow-tabs" aria-label="Mapping views">
            {([
              ["dependencies", "Dependencies"],
              ["objects", "Object mappings"],
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
          <button className="button button-secondary button-small" type="button" onClick={() => void refresh()}>
            Refresh
          </button>
          <button
            ref={commandButton}
            className="button button-primary button-small"
            type="button"
            disabled={!hasTenantLock || !hasAppPermission}
            title={permissionLabel}
            onClick={() => view === "dependencies" ? setDependencyEditor(null) : setRunDialogOpen(true)}
          >
            {view === "dependencies" ? "Add System dependency" : "Generate mappings"}
          </button>
        </div>
      </header>
      <div className="workflow-context-line mapping-context-line">
        <strong>{model.model_name} · r{model.model_revision}</strong>
        <Link className="text-action" to="/tenants/$tenantId/models/$modelId/targets" params={{ tenantId: String(tenantId), modelId: String(model.model_id) }} search={{ layer }}>Review target bindings</Link>
      </div>
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
        dataset={view === "dependencies" ? "mapping_dependency" : "mapping_object"}
        selectedIds={selectedIds} hasTenantLock={hasTenantLock && hasAppPermission}
        disabled={activeQuery.isPending || activeQuery.isError || activeQuery.data?.pages.some((page) => page.model_revision !== model.model_revision) === true}
        onApplied={async () => { setSelectedIds(new Set()); await queryClient.invalidateQueries({ predicate: (query) => query.queryKey[1] === tenantId }); }}
      />
      {view === "dependencies" ? (
        <MappingDependenciesLedger
          onEdit={setDependencyEditor} canEdit={hasTenantLock && hasAppPermission}
          selectedIds={selectedIds} onSelectionChange={setSelectedIds}
          tenantId={tenantId}
          modelId={model.model_id}
          items={dependencies.data?.pages.flatMap((page) => page.items) ?? []}
          filters={filters.dependencies}
          state={queryState(dependencies, model.model_revision)}
          onApplyFilters={setViewFilters}
          onLoadMore={() => void dependencies.fetchNextPage()}
        />
      ) : (
        <MappingObjectsLedger
          selectedIds={selectedIds} onSelectionChange={setSelectedIds}
          tenantId={tenantId}
          modelId={model.model_id}
          items={objects.data?.pages.flatMap((page) => page.items) ?? []}
          filters={filters.objects}
          state={queryState(objects, model.model_revision)}
          onApplyFilters={setViewFilters}
          onLoadMore={() => void objects.fetchNextPage()}
        />
      )}
      {dependencyEditor !== undefined ? <MappingDependencyDialog api={api} tenantId={tenantId} modelId={model.model_id} modelRevision={model.model_revision}
        entityType={entityType} dependency={dependencyEditor} onClose={() => { setDependencyEditor(undefined); commandButton.current?.focus(); }} onSaved={async () => { await refresh(); await invalidateLedgers(); }} /> : null}
      {runDialogOpen ? (
        <MappingRunDialog
          entityType={entityType}
          api={api}
          tenantId={tenantId}
          model={model}
          onClose={() => setRunDialogOpen(false)}
          onCompleted={async (workflowRunId) => {
            setRecentRunId(workflowRunId);
            await Promise.all([
              queryClient.invalidateQueries({ queryKey: ["model", tenantId, model.model_id] }),
              queryClient.invalidateQueries({ queryKey: ["tenant-home", tenantId] }),
            ]);
          }}
        />
      ) : null}
    </main>
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
