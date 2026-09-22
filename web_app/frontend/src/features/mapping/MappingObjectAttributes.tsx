import { useState } from "react";
import { useInfiniteQuery, useQueryClient } from "@tanstack/react-query";

import { ApiError } from "../../core/http";
import { ModelRecordReview } from "../model_record_review/ModelRecordReview";
import { MappingAttributesLedger } from "./MappingLedgers";
import { mappingQueryKeys, type MappingApi, type MappingFilters } from "./api";

export function MappingObjectAttributes({
  api, tenantId, modelId, mappingObjectId, modelRevision, hasTenantLock,
}: {
  api: MappingApi;
  tenantId: number;
  modelId: number;
  mappingObjectId: number;
  modelRevision: number;
  hasTenantLock: boolean;
}) {
  const client = useQueryClient();
  const [selectedIds, setSelectedIds] = useState<Set<number>>(new Set());
  const [filters, setFilters] = useState<MappingFilters>({});
  const scopedFilters = { ...filters, mappingObjectId };
  const query = useInfiniteQuery({
    queryKey: mappingQueryKeys.attributes(tenantId, modelId, scopedFilters),
    initialPageParam: undefined as string | undefined,
    queryFn: ({ pageParam }) => api.listMappingAttributes(tenantId, modelId, scopedFilters, 200, pageParam),
    getNextPageParam: (page) => page.next_cursor ?? undefined,
  });
  const revisionMismatch = query.data?.pages.some((page) => page.model_revision !== modelRevision) === true;
  return (
    <section className="detail-section mapping-object-attributes" aria-labelledby="mapping-attributes-heading">
      <header>
        <h2 id="mapping-attributes-heading">Attribute mappings</h2>
        <button className="button button-secondary button-small" type="button" disabled={query.isFetching}
          onClick={() => {
            setSelectedIds(new Set());
            void Promise.all([
              query.refetch(),
              client.invalidateQueries({ queryKey: ["model", tenantId, modelId] }),
              client.invalidateQueries({ queryKey: mappingQueryKeys.object(tenantId, modelId, mappingObjectId) }),
              client.invalidateQueries({ queryKey: ["tenant-home", tenantId] }),
            ]);
          }}>Refresh Attributes</button>
      </header>
      <ModelRecordReview api={api} tenantId={tenantId} modelId={modelId} modelRevision={modelRevision}
        dataset="mapping_attribute" selectedIds={selectedIds} hasTenantLock={hasTenantLock}
        disabled={query.isPending || query.isError || query.isFetching || revisionMismatch}
        onApplied={async () => {
          setSelectedIds(new Set());
          await client.invalidateQueries({ predicate: (cached) => cached.queryKey[1] === tenantId });
        }}
      />
      <MappingAttributesLedger tenantId={tenantId} modelId={modelId}
        selectedIds={selectedIds} onSelectionChange={setSelectedIds}
        items={query.data?.pages.flatMap((page) => page.items) ?? []}
        filters={filters}
        state={{
          isLoading: query.isPending,
          isError: query.isError,
          isDenied: query.error instanceof ApiError && query.error.status === 403,
          revisionMismatch,
          hasMore: query.hasNextPage,
          isLoadingMore: query.isFetchingNextPage,
        }}
        onApplyFilters={(next) => { setSelectedIds(new Set()); setFilters(next); }}
        onLoadMore={() => void query.fetchNextPage()}
      />
    </section>
  );
}
