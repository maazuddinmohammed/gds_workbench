import { useState } from "react";
import { useInfiniteQuery, useQueryClient } from "@tanstack/react-query";
import { Link } from "@tanstack/react-router";

import { ApiError } from "../../core/http";
import type { ModelDetail } from "../models/api";
import { mappingQueryKeys, type MappingApi, type MappingFilters } from "./api";
import {
  MappingAttributesLedger,
  MappingDependenciesLedger,
  MappingObjectsLedger,
  type MappingLedgerState,
} from "./MappingLedgers";
import { MappingRunDialog } from "./MappingRunDialog";

type MappingView = "dependencies" | "objects" | "attributes";

export function MappingScreen({
  api,
  tenantId,
  model,
  hasTenantLock,
  hasAppPermission,
  initialView,
}: {
  api: MappingApi;
  tenantId: number;
  model: ModelDetail;
  hasTenantLock: boolean;
  hasAppPermission: boolean;
  initialView?: MappingView;
}) {
  const queryClient = useQueryClient();
  const [view, setView] = useState<MappingView>(initialView ?? "dependencies");
  const [runDialogOpen, setRunDialogOpen] = useState(false);
  const [filters, setFilters] = useState<Record<MappingView, MappingFilters>>({
    dependencies: {},
    objects: {},
    attributes: {},
  });
  const dependencies = useInfiniteQuery({
    queryKey: mappingQueryKeys.dependencies(tenantId, model.model_id, filters.dependencies),
    queryFn: ({ pageParam }) => api.listMappingDependencies(
      tenantId,
      model.model_id,
      filters.dependencies,
      200,
      pageParam,
    ),
    initialPageParam: undefined as string | undefined,
    getNextPageParam: (page) => page.next_cursor ?? undefined,
    enabled: view === "dependencies",
  });
  const objects = useInfiniteQuery({
    queryKey: mappingQueryKeys.objects(tenantId, model.model_id, filters.objects),
    queryFn: ({ pageParam }) => api.listMappingObjects(
      tenantId,
      model.model_id,
      filters.objects,
      200,
      pageParam,
    ),
    initialPageParam: undefined as string | undefined,
    getNextPageParam: (page) => page.next_cursor ?? undefined,
    enabled: view === "objects",
  });
  const attributes = useInfiniteQuery({
    queryKey: mappingQueryKeys.attributes(tenantId, model.model_id, filters.attributes),
    queryFn: ({ pageParam }) => api.listMappingAttributes(
      tenantId,
      model.model_id,
      filters.attributes,
      200,
      pageParam,
    ),
    initialPageParam: undefined as string | undefined,
    getNextPageParam: (page) => page.next_cursor ?? undefined,
    enabled: view === "attributes",
  });
  const activeQuery = view === "dependencies" ? dependencies : view === "objects" ? objects : attributes;
  const permissionLabel = !hasAppPermission
    ? "Architect permission required to run"
    : !hasTenantLock
      ? "Tenant Lock required to run"
      : "Tenant Lock held";

  const refresh = async () => {
    await Promise.all([
      activeQuery.refetch(),
      queryClient.invalidateQueries({ queryKey: ["model", tenantId, model.model_id] }),
      queryClient.invalidateQueries({ queryKey: ["tenant-home", tenantId] }),
    ]);
  };
  const setViewFilters = (nextFilters: MappingFilters) => {
    setFilters((current) => ({ ...current, [view]: nextFilters }));
  };

  return (
    <main className="workspace mapping-workspace page-enter">
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
              ["attributes", "Attribute mappings"],
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
          <button className="button button-secondary button-small" type="button" onClick={() => void refresh()}>
            Refresh
          </button>
          <button
            className="button button-primary button-small"
            type="button"
            disabled={!hasTenantLock || !hasAppPermission}
            title={permissionLabel}
            onClick={() => setRunDialogOpen(true)}
          >
            Run Mapping
          </button>
        </div>
      </header>
      <div className="workflow-context-line mapping-context-line">
        <strong>{model.model_name} · r{model.model_revision}</strong>
        <span>Logical mappings target eligible Silver Objects. Dimensional mappings target eligible Gold Objects.</span>
      </div>
      {view === "dependencies" ? (
        <MappingDependenciesLedger
          tenantId={tenantId}
          modelId={model.model_id}
          items={dependencies.data?.pages.flatMap((page) => page.items) ?? []}
          filters={filters.dependencies}
          state={queryState(dependencies, model.model_revision)}
          onApplyFilters={setViewFilters}
          onLoadMore={() => void dependencies.fetchNextPage()}
        />
      ) : view === "objects" ? (
        <MappingObjectsLedger
          tenantId={tenantId}
          modelId={model.model_id}
          items={objects.data?.pages.flatMap((page) => page.items) ?? []}
          filters={filters.objects}
          state={queryState(objects, model.model_revision)}
          onApplyFilters={setViewFilters}
          onLoadMore={() => void objects.fetchNextPage()}
        />
      ) : (
        <MappingAttributesLedger
          tenantId={tenantId}
          modelId={model.model_id}
          items={attributes.data?.pages.flatMap((page) => page.items) ?? []}
          filters={filters.attributes}
          state={queryState(attributes, model.model_revision)}
          onApplyFilters={setViewFilters}
          onLoadMore={() => void attributes.fetchNextPage()}
        />
      )}
      {runDialogOpen ? (
        <MappingRunDialog
          api={api}
          tenantId={tenantId}
          model={model}
          onClose={() => setRunDialogOpen(false)}
          onCompleted={async () => {
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
