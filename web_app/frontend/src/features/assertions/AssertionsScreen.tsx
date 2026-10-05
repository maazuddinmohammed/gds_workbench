import { useState } from "react";
import { useInfiniteQuery, useQuery, useQueryClient } from "@tanstack/react-query";
import type { ModelDetail } from "../models/api";
import { assertionsQueryKeys, type AssertionDocumentFilters, type AssertionsApi } from "./api";
import { AssertionDocumentsLedger } from "./AssertionLedgers";
import { AssertionEditor } from "./AssertionEditor";
import type { ModelInputScopeApi } from "../model_input_scope/api";
import { scopeFilterChoicesKey, sourceCodes, useScopeFilterChoices } from "../model_input_scope/scopeFilterChoices";
import { WorkflowCommandCenter, WorkflowCommandTools } from "../workflows/WorkflowCommandCenter";

export function AssertionsScreen({ api, tenantId, model, hasTenantLock }: {
  api: AssertionsApi & Pick<ModelInputScopeApi, "listModelInputScope">; tenantId: number; model: ModelDetail; hasTenantLock: boolean;
}) {
  const queryClient = useQueryClient();
  const [editorOpen, setEditorOpen] = useState(false);
  const [filters, setFilters] = useState<AssertionDocumentFilters>({});
  const scopeChoices = useScopeFilterChoices(api, tenantId, model.model_id, model.model_revision);
  const documentSystems = useQuery({
    queryKey: ["assertion-filter-systems", tenantId, model.model_id],
    queryFn: async () => {
      const codes: string[] = [];
      const cursors = new Set<string>();
      let cursor: string | undefined;
      let revision: number | undefined;
      for (let page = 0; page < 250; page += 1) {
        const response = await api.listAssertionDocuments(tenantId, model.model_id, {}, 200, cursor);
        revision ??= response.model_revision;
        if (response.model_revision !== revision) throw new Error("Assertion source choices changed while loading");
        for (const document of response.items) if (document.source_system) codes.push(document.source_system.system_code);
        if (!response.next_cursor) return { modelRevision: response.model_revision, codes: sourceCodes(codes) };
        if (cursors.has(response.next_cursor)) throw new Error("Assertion source cursor repeated");
        cursors.add(response.next_cursor); cursor = response.next_cursor;
      }
      throw new Error("Assertion source choices exceed the supported bounded selection");
    },
  });
  const sourceChoices = { codes: sourceCodes([...scopeChoices.systemCodes, ...(documentSystems.data?.codes ?? [])]),
    isLoading: scopeChoices.isLoading || documentSystems.isPending,
    isUnavailable: scopeChoices.isUnavailable || documentSystems.isError
      || (documentSystems.data !== undefined && documentSystems.data.modelRevision !== model.model_revision) };
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
      queryClient.invalidateQueries({ queryKey: ["assertion-filter-systems", tenantId, model.model_id] }),
      queryClient.invalidateQueries({ queryKey: scopeFilterChoicesKey(tenantId, model.model_id) }),
      queryClient.invalidateQueries({ queryKey: ["model", tenantId, model.model_id] }),
    ]);
  };
  return <WorkflowCommandCenter className="assertions-page page-enter" filterCount={Object.values(filters).filter((value) => value !== undefined && value !== "").length}>
    <header className="workflow-commandbar model-section-toolbar assertions-commandbar">
      <h1 className="model-section-title sr-only">Assertion documents</h1>
      <div className="workflow-command-context">
        <span className={hasTenantLock ? "lock-context is-held" : "lock-context"}>
          {hasTenantLock ? "Tenant Lock held" : "Tenant Lock required to add Assertions"}
        </span>
      </div>
      <div className="workflow-command-actions">
        <WorkflowCommandTools />
        <button className="button button-secondary button-small" type="button" onClick={async () => {
          await Promise.all([documents.refetch(), documentSystems.refetch(), scopeChoices.refetch(), queryClient.invalidateQueries({ queryKey: ["model", tenantId, model.model_id] }), queryClient.invalidateQueries({ queryKey: ["tenant-home", tenantId] })]);
        }}>Refresh</button>
        <button className="button button-primary button-small" type="button" disabled={!hasTenantLock} title={hasTenantLock ? undefined : "Tenant Lock required"} onClick={() => setEditorOpen(true)}>Add Assertion</button>
      </div>
    </header>
    {editorOpen ? <AssertionEditor api={api} tenantId={tenantId} modelId={model.model_id} modelRevision={model.model_revision} hasTenantLock={hasTenantLock} onClose={() => setEditorOpen(false)} onSaved={saved} /> : null}
    <AssertionDocumentsLedger sourceChoices={sourceChoices} key={JSON.stringify(filters)} tenantId={tenantId} modelId={model.model_id} items={documents.data?.pages.flatMap((page) => page.items) ?? []} filters={filters}
      state={{ isLoading: documents.isPending, isError: documents.isError, revisionMismatch: documents.data?.pages.some((page) => page.model_revision !== model.model_revision) ?? false, hasMore: documents.hasNextPage, isLoadingMore: documents.isFetchingNextPage }}
      onApplyFilters={setFilters} onLoadMore={() => { void documents.fetchNextPage(); }} />
  </WorkflowCommandCenter>;
}
