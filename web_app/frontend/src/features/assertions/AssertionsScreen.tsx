import { useState } from "react";
import { useInfiniteQuery, useQueryClient } from "@tanstack/react-query";

import type { ModelDetail } from "../models/api";
import {
  assertionsQueryKeys,
  type AssertionDocumentFilters,
  type AssertionRecordFilters,
  type AssertionsApi,
} from "./api";
import { AssertionDocumentsLedger, AssertionRecordsLedger } from "./AssertionLedgers";

type AssertionsView = "documents" | "records";

export function AssertionsScreen({
  api,
  tenantId,
  model,
}: {
  api: AssertionsApi;
  tenantId: number;
  model: ModelDetail;
}) {
  const queryClient = useQueryClient();
  const [view, setView] = useState<AssertionsView>("documents");
  const [documentFilters, setDocumentFilters] = useState<AssertionDocumentFilters>({});
  const [recordFilters, setRecordFilters] = useState<AssertionRecordFilters>({});
  const documentsQuery = useInfiniteQuery({
    queryKey: assertionsQueryKeys.documents(tenantId, model.model_id, documentFilters),
    queryFn: ({ pageParam }) => api.listAssertionDocuments(
      tenantId,
      model.model_id,
      documentFilters,
      200,
      pageParam,
    ),
    initialPageParam: undefined as string | undefined,
    getNextPageParam: (lastPage) => lastPage.next_cursor ?? undefined,
    enabled: view === "documents",
  });
  const recordsQuery = useInfiniteQuery({
    queryKey: assertionsQueryKeys.records(tenantId, model.model_id, recordFilters),
    queryFn: ({ pageParam }) => api.listAssertionRecords(
      tenantId,
      model.model_id,
      recordFilters,
      200,
      pageParam,
    ),
    initialPageParam: undefined as string | undefined,
    getNextPageParam: (lastPage) => lastPage.next_cursor ?? undefined,
    enabled: view === "records",
  });

  const refresh = async () => {
    await Promise.all([
      view === "documents" ? documentsQuery.refetch() : recordsQuery.refetch(),
      queryClient.invalidateQueries({ queryKey: ["model", tenantId, model.model_id] }),
      queryClient.invalidateQueries({ queryKey: ["tenant-home", tenantId] }),
    ]);
  };

  return (
    <div className="assertions-page page-enter">
      <header className="workflow-commandbar assertions-commandbar">
        <nav className="workflow-tabs" aria-label="Assertion views">
          <button
            className={view === "documents" ? "is-active" : ""}
            type="button"
            aria-pressed={view === "documents"}
            onClick={() => setView("documents")}
          >
            Documents
          </button>
          <button
            className={view === "records" ? "is-active" : ""}
            type="button"
            aria-pressed={view === "records"}
            onClick={() => setView("records")}
          >
            Records
          </button>
        </nav>
        <div className="workflow-command-actions">
          <span className="read-only-context">Review only · governed imports are not exposed here</span>
          <button className="button button-secondary button-small" type="button" onClick={refresh}>
            Refresh
          </button>
        </div>
      </header>

      {view === "documents" ? (
        <AssertionDocumentsLedger
          tenantId={tenantId}
          modelId={model.model_id}
          items={documentsQuery.data?.pages.flatMap((page) => page.items) ?? []}
          filters={documentFilters}
          state={{
            isLoading: documentsQuery.isPending,
            isError: documentsQuery.isError,
            revisionMismatch: documentsQuery.data !== undefined
              && documentsQuery.data.pages.some(
                (page) => page.model_revision !== model.model_revision,
              ),
            hasMore: documentsQuery.hasNextPage,
            isLoadingMore: documentsQuery.isFetchingNextPage,
          }}
          onApplyFilters={setDocumentFilters}
          onLoadMore={() => {
            void documentsQuery.fetchNextPage();
          }}
        />
      ) : (
        <AssertionRecordsLedger
          tenantId={tenantId}
          modelId={model.model_id}
          items={recordsQuery.data?.pages.flatMap((page) => page.items) ?? []}
          filters={recordFilters}
          state={{
            isLoading: recordsQuery.isPending,
            isError: recordsQuery.isError,
            revisionMismatch: recordsQuery.data !== undefined
              && recordsQuery.data.pages.some(
                (page) => page.model_revision !== model.model_revision,
              ),
            hasMore: recordsQuery.hasNextPage,
            isLoadingMore: recordsQuery.isFetchingNextPage,
          }}
          onApplyFilters={setRecordFilters}
          onLoadMore={() => {
            void recordsQuery.fetchNextPage();
          }}
        />
      )}
    </div>
  );
}
