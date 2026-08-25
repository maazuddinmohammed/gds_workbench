import { useState } from "react";
import { useInfiniteQuery, useQuery, useQueryClient } from "@tanstack/react-query";

import type { ModelDetail } from "../models/api";
import type { WorkflowRunFilterState } from "../workflows/api";
import { loadAllBronzeScope, workflowCreationQueryKeys } from "../workflows/api";
import { WorkflowRunDialog } from "../workflows/WorkflowRunDialog";
import { isActiveRun } from "../workflows/presentation";
import {
  analysisQueryKeys,
  type AnalysisApi,
  type AnalysisFilters,
} from "./api";
import { AnalysisResults } from "./AnalysisResults";
import { AnalysisRuns } from "./AnalysisRuns";

type AnalysisView = "results" | "runs";
type RunDialogKind = "inference" | "validation" | null;

export function AnalysisScreen({
  api,
  tenantId,
  model,
  hasTenantLock,
}: {
  api: AnalysisApi;
  tenantId: number;
  model: ModelDetail;
  hasTenantLock: boolean;
}) {
  const queryClient = useQueryClient();
  const [view, setView] = useState<AnalysisView>("results");
  const [filters, setFilters] = useState<AnalysisFilters>({});
  const [selectedIds, setSelectedIds] = useState<Set<number>>(new Set());
  const [runState, setRunState] = useState<WorkflowRunFilterState>("");
  const [runDialog, setRunDialog] = useState<RunDialogKind>(null);
  const findingsQuery = useInfiniteQuery({
    queryKey: analysisQueryKeys.findings(tenantId, model.model_id, filters),
    queryFn: ({ pageParam }) => api.listAnalysisFindings(
      tenantId,
      model.model_id,
      filters,
      200,
      pageParam,
    ),
    initialPageParam: undefined as string | undefined,
    getNextPageParam: (lastPage) => lastPage.next_cursor ?? undefined,
    enabled: view === "results",
  });
  const endpointOptionsQuery = useQuery({
    queryKey: workflowCreationQueryKeys.bronzeScope(tenantId, model.model_id),
    queryFn: () => loadAllBronzeScope(api, tenantId, model.model_id),
  });
  const runsQuery = useQuery({
    queryKey: analysisQueryKeys.runs(tenantId, model.model_id, runState),
    queryFn: () => api.listWorkflowRuns(
      tenantId,
      model.model_id,
      "analysis",
      runState,
    ),
    enabled: view === "runs",
    refetchInterval: (query) => (
      query.state.data?.items.some(isActiveRun) ? 2_000 : false
    ),
  });

  const refresh = async () => {
    await Promise.all([
      view === "results" ? findingsQuery.refetch() : runsQuery.refetch(),
      endpointOptionsQuery.refetch(),
      queryClient.invalidateQueries({ queryKey: ["model", tenantId, model.model_id] }),
      queryClient.invalidateQueries({ queryKey: ["tenant-home", tenantId] }),
    ]);
  };

  return (
    <div className="analysis-page page-enter">
      <header className="workflow-commandbar">
        <div className="workflow-command-context">
          <span className={hasTenantLock ? "lock-context is-held" : "lock-context"}>
            {hasTenantLock ? "Tenant Lock held" : "Tenant Lock required to run"}
          </span>
          <nav className="workflow-tabs" aria-label="Analysis views">
            <button
              className={view === "results" ? "is-active" : ""}
              type="button"
              aria-pressed={view === "results"}
              onClick={() => setView("results")}
            >
              Results
            </button>
            <button
              className={view === "runs" ? "is-active" : ""}
              type="button"
              aria-pressed={view === "runs"}
              onClick={() => setView("runs")}
            >
              Runs
            </button>
          </nav>
        </div>
        <div className="workflow-command-actions">
          <button className="button button-secondary button-small" type="button" onClick={refresh}>
            Refresh
          </button>
          <button
            className="button button-secondary button-small"
            type="button"
            disabled={!hasTenantLock}
            title={hasTenantLock ? undefined : "Tenant Lock required"}
            onClick={() => setRunDialog("inference")}
          >
            Run inference
          </button>
          <button
            className="button button-primary button-small"
            type="button"
            disabled={!hasTenantLock}
            title={hasTenantLock ? undefined : "Tenant Lock required"}
            onClick={() => setRunDialog("validation")}
          >
            Validate pending
          </button>
        </div>
      </header>

      {view === "results" ? (
        <AnalysisResults
          tenantId={tenantId}
          modelId={model.model_id}
          items={findingsQuery.data?.pages.flatMap((page) => page.items) ?? []}
          endpointOptions={endpointOptionsQuery.data?.items ?? []}
          filters={filters}
          selectedIds={selectedIds}
          isLoading={findingsQuery.isPending}
          isError={findingsQuery.isError}
          revisionMismatch={
            findingsQuery.data !== undefined
            && findingsQuery.data.pages.some(
              (page) => page.model_revision !== model.model_revision,
            )
          }
          hasMore={findingsQuery.hasNextPage}
          isLoadingMore={findingsQuery.isFetchingNextPage}
          hasTenantLock={hasTenantLock}
          onApplyFilters={(nextFilters) => {
            setSelectedIds(new Set());
            setFilters(nextFilters);
          }}
          onSelectionChange={setSelectedIds}
          onLoadMore={() => {
            void findingsQuery.fetchNextPage();
          }}
        />
      ) : (
        <AnalysisRuns
          items={runsQuery.data?.items ?? []}
          state={runState}
          isLoading={runsQuery.isPending}
          isError={runsQuery.isError}
          onStateChange={setRunState}
        />
      )}

      {runDialog ? (
        <WorkflowRunDialog
          api={api}
          tenantId={tenantId}
          model={model}
          kind={runDialog}
          onClose={() => setRunDialog(null)}
          onCreated={async () => {
            setView("runs");
            await queryClient.invalidateQueries({
              queryKey: analysisQueryKeys.runs(tenantId, model.model_id, runState),
            });
          }}
        />
      ) : null}
    </div>
  );
}
