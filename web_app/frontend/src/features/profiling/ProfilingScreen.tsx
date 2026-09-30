import { WorkflowActivityPanel, WorkflowCommandCenter, WorkflowCommandTools } from "../workflows/WorkflowCommandCenter";
import { useEffect, useRef, useState } from "react";
import { useInfiniteQuery, useQuery, useQueryClient } from "@tanstack/react-query";

import type { ModelDetail } from "../models/api";
import type { WorkflowRunFilterState } from "../workflows/api";
import {
  profilingQueryKeys,
  type ProfilingApi,
  type ProfilingFilters,
} from "./api";
import { ProfilingRunConfiguration } from "./ProfilingRunConfiguration";
import { ProfilingResults } from "./ProfilingResults";
import { useScopeFilterChoices } from "../model_input_scope/scopeFilterChoices";
import { ProfilingRunDrawer, ProfilingRuns } from "./ProfilingRuns";

type ProfilingView = "results" | "runs";

export function ProfilingScreen({
  api,
  tenantId,
  model,
  hasTenantLock,
  resultFilters,
  returnObjectId,
  onApplyResultFilters,
  onReturnFocusHandled,
}: {
  api: ProfilingApi;
  tenantId: number;
  model: ModelDetail;
  hasTenantLock: boolean;
  resultFilters: ProfilingFilters;
  returnObjectId?: number;
  onApplyResultFilters: (filters: ProfilingFilters) => void;
  onReturnFocusHandled: () => Promise<void>;
}) {
  const queryClient = useQueryClient();
  const [view, setView] = useState<ProfilingView>("results");
  const [runState, setRunState] = useState<WorkflowRunFilterState>("");
  const [selectedRunId, setSelectedRunId] = useState<number | null>(null);
  const [runConfigurationOpen, setRunConfigurationOpen] = useState(false);
  const runReturnId = useRef<number | null>(null);
  const handledReturnObjectId = useRef<number | null>(null);
  const sourceChoices = useScopeFilterChoices(api, tenantId, model.model_id, model.model_revision);

  const resultsQuery = useQuery({
    queryKey: profilingQueryKeys.results(tenantId, model.model_id, resultFilters),
    queryFn: () => api.listProfilingObjects(
      tenantId,
      model.model_id,
      resultFilters,
    ),
  });
  const runsQuery = useInfiniteQuery({
    queryKey: profilingQueryKeys.runs(tenantId, model.model_id, runState),
    queryFn: ({ pageParam }) => api.listWorkflowRuns(
      tenantId,
      model.model_id,
      "profiling",
      runState,
      50,
      pageParam,
    ),
    initialPageParam: undefined as string | undefined,
    getNextPageParam: (page) => page.next_cursor ?? undefined,
    enabled: view === "runs" || selectedRunId !== null,
  });

  useEffect(() => {
    const first = runsQuery.data?.pages[0]?.items[0];
    if (view === "runs" && selectedRunId === null && first && !runsQuery.isFetching) setSelectedRunId(first.workflow_run_id);
  }, [view, selectedRunId, runsQuery.data, runsQuery.isFetching]);
  useEffect(() => {
    if (selectedRunId !== null) return;
    if (runReturnId.current !== null) {
      document
        .getElementById(`profiling-run-trigger-${runReturnId.current}`)
        ?.focus();
      runReturnId.current = null;
    }
  }, [selectedRunId]);
  useEffect(() => {
    if (
      returnObjectId === undefined
      || handledReturnObjectId.current === returnObjectId
      || resultsQuery.isPending
    ) return;
    handledReturnObjectId.current = returnObjectId;
    const restoreFocus = () => {
      const origin = document.getElementById(`profiling-detail-trigger-${returnObjectId}`);
      const target = origin ?? document.getElementById("profiling-results-surface");
      if (!target) return;
      target.focus({ preventScroll: true });
      if (typeof target.scrollIntoView === "function") {
        target.scrollIntoView({ block: "center" });
      }
    };
    void onReturnFocusHandled().then(restoreFocus, restoreFocus);
  }, [onReturnFocusHandled, resultsQuery.isPending, returnObjectId]);

  const refresh = async () => {
    const requests = view === "results"
      ? [resultsQuery.refetch()]
      : [
          runsQuery.refetch(),
          selectedRunId === null
            ? Promise.resolve()
            : queryClient.invalidateQueries({
                queryKey: profilingQueryKeys.run(
                  tenantId,
                  model.model_id,
                  selectedRunId,
                ),
              }),
          selectedRunId === null
            ? Promise.resolve()
            : queryClient.invalidateQueries({
                queryKey: profilingQueryKeys.eventFamily(
                  tenantId,
                  model.model_id,
                  selectedRunId,
                ),
              }),
        ];
    await Promise.all([
      sourceChoices.refetch(),
      ...requests,
      queryClient.invalidateQueries({
        queryKey: ["model", tenantId, model.model_id],
      }),
      queryClient.invalidateQueries({ queryKey: ["tenant-home", tenantId] }),
    ]);
  };

  return (
    <WorkflowCommandCenter filterCount={Object.values(resultFilters).filter(Boolean).length} className="profiling-page page-enter">
      <header className="workflow-commandbar model-section-toolbar">
        <h1 className="model-section-title sr-only">Profiling</h1>
        <div className="workflow-command-context">
          <strong className="workflow-view-label">Results</strong>
        </div>
        <div className="workflow-command-actions">
          <WorkflowCommandTools />
          <button
            className="button button-secondary button-small"
            type="button"
            onClick={refresh}
          >
            Refresh
          </button>
          <button
            id="run-profiling-trigger"
            className="button button-primary button-small"
            type="button"
            disabled={!hasTenantLock}
            onClick={() => setRunConfigurationOpen(true)}
          >
            Run profiling
          </button>
        </div>
      </header>


        <ProfilingResults
          tenantId={tenantId}
          modelId={model.model_id}
          filters={resultFilters}
          sourceChoices={sourceChoices}
          items={resultsQuery.data?.items ?? []}
          isLoading={resultsQuery.isPending}
          isError={resultsQuery.isError}
          revisionMismatch={
            resultsQuery.data !== undefined
            && resultsQuery.data.model_revision !== model.model_revision
          }
          onApplyFilters={onApplyResultFilters}
        />
      <WorkflowActivityPanel label="Profiling" open={view === "runs"}
        onOpenChange={(open) => setView(open ? "runs" : "results")}
        actions={<button className="button button-secondary button-small" type="button"
          disabled={runsQuery.isFetching} onClick={() => void refresh()}>{runsQuery.isFetching ? "Refreshing…" : "Refresh runs"}</button>}>
        <div className="workflow-run-monitor-layout profiling-activity-layout">
          <div className="workflow-run-browser">
            <ProfilingRuns compact items={runsQuery.data?.pages.flatMap((page) => page.items) ?? []}
              state={runState} isLoading={runsQuery.isPending} isError={runsQuery.isError} selectedRunId={selectedRunId}
              onStateChange={(state) => { setSelectedRunId(null); setRunState(state); }} onShowDetails={setSelectedRunId} />
            {runsQuery.hasNextPage ? <button className="button button-secondary button-small" type="button"
              disabled={runsQuery.isFetchingNextPage} onClick={() => void runsQuery.fetchNextPage()}>Load more runs</button> : null}
          </div>
          <div className="workflow-run-monitor-detail">
            {selectedRunId !== null ? <ProfilingRunDrawer embedded api={api} tenantId={tenantId} model={model}
              hasTenantLock={hasTenantLock} runId={selectedRunId}
              onClose={() => { runReturnId.current = selectedRunId; setSelectedRunId(null); }} />
              : <p className="empty-state compact">Choose a run to see its details.</p>}
          </div>
        </div>
      </WorkflowActivityPanel>

      {runConfigurationOpen ? (
        <ProfilingRunConfiguration
          api={api}
          tenantId={tenantId}
          model={model}
          onClose={() => {
            setRunConfigurationOpen(false);
            queueMicrotask(() => {
              document.getElementById("run-profiling-trigger")?.focus();
            });
          }}
          onCreated={async (workflowRunId) => {
            setRunConfigurationOpen(false);
            setView("runs");
            setRunState("");
            runReturnId.current = null;
            setSelectedRunId(workflowRunId);
            await queryClient.invalidateQueries({
              queryKey: profilingQueryKeys.runs(tenantId, model.model_id),
            });
          }}
        />
      ) : null}
    </WorkflowCommandCenter>
  );
}
