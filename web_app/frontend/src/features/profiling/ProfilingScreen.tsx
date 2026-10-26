import { WorkflowActivityPanel, WorkflowCommandCenter, WorkflowCommandTools } from "../workflows/WorkflowCommandCenter";
import { useEffect, useRef, useState } from "react";
import { useInfiniteQuery, useQuery, useQueryClient } from "@tanstack/react-query";

import type { ProjectDetail } from "../projects/api";
import type { WorkflowRunFilterState } from "../workflows/api";
import {
  profilingQueryKeys,
  type ProfilingApi,
  type ProfilingFilters,
} from "./api";
import { ProfilingRunConfiguration } from "./ProfilingRunConfiguration";
import { ProfilingResults } from "./ProfilingResults";
import { useScopeFilterChoices } from "../project_input_scope/scopeFilterChoices";
import { ProfilingRunDrawer, ProfilingRuns } from "./ProfilingRuns";
import { RefreshButton } from "../../shared/ui";

type ProfilingView = "results" | "runs";

export function ProfilingScreen({
  api,
  tenantId,
  project,
  hasTenantLock,
  resultFilters,
  returnObjectId,
  onApplyResultFilters,
  onReturnFocusHandled,
}: {
  api: ProfilingApi;
  tenantId: number;
  project: ProjectDetail;
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
  const sourceChoices = useScopeFilterChoices(api, tenantId, project.project_id, project.project_revision);

  const resultsQuery = useQuery({
    queryKey: profilingQueryKeys.results(tenantId, project.project_id, resultFilters),
    queryFn: () => api.listProfilingObjects(
      tenantId,
      project.project_id,
      resultFilters,
    ),
  });
  const runsQuery = useInfiniteQuery({
    queryKey: profilingQueryKeys.runs(tenantId, project.project_id, runState),
    queryFn: ({ pageParam }) => api.listWorkflowRuns(
      tenantId,
      project.project_id,
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
                  project.project_id,
                  selectedRunId,
                ),
              }),
          selectedRunId === null
            ? Promise.resolve()
            : queryClient.invalidateQueries({
                queryKey: profilingQueryKeys.eventFamily(
                  tenantId,
                  project.project_id,
                  selectedRunId,
                ),
              }),
        ];
    await Promise.all([
      sourceChoices.refetch(),
      ...requests,
      queryClient.invalidateQueries({
        queryKey: ["project", tenantId, project.project_id],
      }),
      queryClient.invalidateQueries({ queryKey: ["tenant-home", tenantId] }),
    ]);
  };

  return (
    <WorkflowCommandCenter filterCount={Object.values(resultFilters).filter(Boolean).length} className="profiling-page page-enter">
      <header className="workflow-commandbar project-section-toolbar">
        <h1 className="project-section-title sr-only">Profiling</h1>
        <div className="workflow-command-context">
          <strong className="workflow-view-label">Results</strong>
        </div>
        <div className="workflow-command-actions">
          <WorkflowCommandTools />
          <RefreshButton refreshing={false} onClick={refresh} />
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
          projectId={project.project_id}
          filters={resultFilters}
          sourceChoices={sourceChoices}
          items={resultsQuery.data?.items ?? []}
          isLoading={resultsQuery.isPending}
          isError={resultsQuery.isError}
          revisionMismatch={
            resultsQuery.data !== undefined
            && resultsQuery.data.project_revision !== project.project_revision
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
            {selectedRunId !== null ? <ProfilingRunDrawer embedded api={api} tenantId={tenantId} project={project}
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
          project={project}
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
              queryKey: profilingQueryKeys.runs(tenantId, project.project_id),
            });
          }}
        />
      ) : null}
    </WorkflowCommandCenter>
  );
}
