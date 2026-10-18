import { useId, useRef, useState } from "react";
import { useInfiniteQuery, useQueryClient } from "@tanstack/react-query";

import { ApiError } from "../../core/http";
import { ProjectRecordReview } from "../project_record_review/ProjectRecordReview";
import { MappingAttributesLedger } from "./MappingLedgers";
import { mappingQueryKeys, type MappingApi, type MappingFilters } from "./api";

export function MappingObjectAttributes({
  api, tenantId, projectId, mappingObjectId, projectRevision, hasTenantLock,
}: {
  api: MappingApi;
  tenantId: number;
  projectId: number;
  mappingObjectId: number;
  projectRevision: number;
  hasTenantLock: boolean;
}) {
  const client = useQueryClient();
  const headingId = useId();
  const refreshButton = useRef<HTMLButtonElement>(null);
  const [selectedIds, setSelectedIds] = useState<Set<number>>(new Set());
  const [filters, setFilters] = useState<MappingFilters>({});
  const [filtersOpen, setFiltersOpen] = useState(false);
  const filterId = `${headingId}-filters`;
  const filterCount = Number(Boolean(filters.status)) + Number(filters.locked !== undefined);
  const scopedFilters = { ...filters, mappingObjectId };
  const query = useInfiniteQuery({
    queryKey: mappingQueryKeys.attributes(tenantId, projectId, scopedFilters),
    initialPageParam: undefined as string | undefined,
    queryFn: ({ pageParam }) => api.listMappingAttributes(tenantId, projectId, scopedFilters, 200, pageParam),
    getNextPageParam: (page) => page.next_cursor ?? undefined,
  });
  const revisionMismatch = query.data?.pages.some((page) => page.project_revision !== projectRevision) === true;
  return (
    <section className={`detail-section mapping-object-attributes${selectedIds.size ? " has-selection" : ""}`} aria-labelledby={headingId}>
      <header>
        <h2 id={headingId}>Attribute transformations</h2>
        <div className="workflow-command-actions">
        <button className="button button-secondary button-small" type="button" aria-expanded={filtersOpen}
          aria-controls={filterId} onClick={() => setFiltersOpen(!filtersOpen)}>
          Filters{filterCount ? ` · ${filterCount}` : ""}
        </button>
        <button ref={refreshButton} className="button button-secondary button-small" type="button" disabled={query.isFetching}
          onClick={() => {
            setSelectedIds(new Set());
            void Promise.all([
              query.refetch(),
              client.invalidateQueries({ queryKey: ["mapping-attribute", tenantId, projectId] }),
              client.invalidateQueries({ queryKey: ["mapping-objects", tenantId, projectId] }),
              client.invalidateQueries({ queryKey: ["project", tenantId, projectId] }),
              client.invalidateQueries({ queryKey: mappingQueryKeys.object(tenantId, projectId, mappingObjectId) }),
              client.invalidateQueries({ queryKey: ["tenant-home", tenantId] }),
            ]);
          }}>Refresh Attributes</button>
        </div>
      </header>
      <ProjectRecordReview api={api} tenantId={tenantId} projectId={projectId} projectRevision={projectRevision}
        dataset="mapping_attribute" selectedIds={selectedIds} hasTenantLock={hasTenantLock}
        disabled={query.isPending || query.isError || query.isFetching || revisionMismatch}
        onApplied={async () => {
          setSelectedIds(new Set());
          await client.invalidateQueries({ predicate: (cached) => cached.queryKey[1] === tenantId });
          requestAnimationFrame(() => refreshButton.current?.focus());
        }}
      />
      <MappingAttributesLedger api={api} tenantId={tenantId} projectId={projectId}
        filtersOpen={filtersOpen} filterId={filterId}
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
