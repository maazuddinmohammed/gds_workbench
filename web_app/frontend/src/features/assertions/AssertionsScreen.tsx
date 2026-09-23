import { useState } from "react";
import { useInfiniteQuery, useQueryClient } from "@tanstack/react-query";
import type { ModelDetail } from "../models/api";
import { assertionsQueryKeys, type AssertionDocumentFilters, type AssertionsApi } from "./api";
import { AssertionDocumentsLedger } from "./AssertionLedgers";
import { AssertionEditor } from "./AssertionEditor";

export function AssertionsScreen({ api, tenantId, model, hasTenantLock }: {
  api: AssertionsApi; tenantId: number; model: ModelDetail; hasTenantLock: boolean;
}) {
  const queryClient = useQueryClient();
  const [editorOpen, setEditorOpen] = useState(false);
  const [filters, setFilters] = useState<AssertionDocumentFilters>({});
  const documents = useInfiniteQuery({
    queryKey: assertionsQueryKeys.documents(tenantId, model.model_id, filters),
    queryFn: ({ pageParam }) => api.listAssertionDocuments(tenantId, model.model_id, filters, 200, pageParam),
    initialPageParam: undefined as string | undefined,
    getNextPageParam: (page) => page.next_cursor ?? undefined,
  });
  const saved = async () => {
    setFilters({});
    await Promise.all([
      queryClient.invalidateQueries({ queryKey: ["assertion-documents", tenantId, model.model_id] }),
      queryClient.invalidateQueries({ queryKey: ["assertion-document-choices", tenantId, model.model_id] }),
      queryClient.invalidateQueries({ queryKey: ["model", tenantId, model.model_id] }),
    ]);
  };
  return <div className="assertions-page page-enter">
    <header className="workflow-commandbar assertions-commandbar">
      <h1>Assertion documents</h1>
      <div className="workflow-command-actions">
        <button className="button button-primary button-small" type="button" disabled={!hasTenantLock} title={hasTenantLock ? undefined : "Tenant Lock required"} onClick={() => setEditorOpen(true)}>Add Assertion</button>
        <button className="button button-secondary button-small" type="button" onClick={async () => {
          await Promise.all([documents.refetch(), queryClient.invalidateQueries({ queryKey: ["model", tenantId, model.model_id] }), queryClient.invalidateQueries({ queryKey: ["tenant-home", tenantId] })]);
        }}>Refresh</button>
      </div>
    </header>
    {editorOpen ? <AssertionEditor api={api} tenantId={tenantId} modelId={model.model_id} modelRevision={model.model_revision} hasTenantLock={hasTenantLock} onClose={() => setEditorOpen(false)} onSaved={saved} /> : null}
    <AssertionDocumentsLedger key={JSON.stringify(filters)} tenantId={tenantId} modelId={model.model_id} items={documents.data?.pages.flatMap((page) => page.items) ?? []} filters={filters}
      state={{ isLoading: documents.isPending, isError: documents.isError, revisionMismatch: documents.data?.pages.some((page) => page.model_revision !== model.model_revision) ?? false, hasMore: documents.hasNextPage, isLoadingMore: documents.isFetchingNextPage }}
      onApplyFilters={setFilters} onLoadMore={() => { void documents.fetchNextPage(); }} />
  </div>;
}
