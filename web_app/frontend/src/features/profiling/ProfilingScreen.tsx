import { useEffect, useRef, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";

import type { ModelDetail } from "../models/api";
import type { WorkflowRunFilterState } from "../workflows/api";
import {
  profilingQueryKeys,
  type ProfilingApi,
  type ProfilingFilters,
} from "./api";
import { ProfilingRunConfiguration } from "./ProfilingRunConfiguration";
import { ProfilingResults } from "./ProfilingResults";
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

  const resultsQuery = useQuery({
    queryKey: profilingQueryKeys.results(tenantId, model.model_id, resultFilters),
    queryFn: () => api.listProfilingObjects(
      tenantId,
      model.model_id,
      resultFilters,
    ),
    enabled: view === "results",
  });
  const runsQuery = useQuery({
    queryKey: profilingQueryKeys.runs(tenantId, model.model_id, runState),
    queryFn: () => api.listWorkflowRuns(
      tenantId,
      model.model_id,
      "profiling",
      runState,
    ),
    enabled: view === "runs" || selectedRunId !== null,
  });

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
      ...requests,
      queryClient.invalidateQueries({
        queryKey: ["model", tenantId, model.model_id],
      }),
      queryClient.invalidateQueries({ queryKey: ["tenant-home", tenantId] }),
    ]);
  };

  return (
    <div className="profiling-page page-enter">
      <header className="workflow-commandbar">
        <div className="workflow-command-context">
          <span className={hasTenantLock ? "lock-context is-held" : "lock-context"}>
            {hasTenantLock ? "Tenant Lock held" : "Tenant Lock required to run"}
          </span>
          <nav className="workflow-tabs" aria-label="Profiling views">
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

      {view === "results" ? (
        <ProfilingResults
          tenantId={tenantId}
          modelId={model.model_id}
          filters={resultFilters}
          items={resultsQuery.data?.items ?? []}
          isLoading={resultsQuery.isPending}
          isError={resultsQuery.isError}
          revisionMismatch={
            resultsQuery.data !== undefined
            && resultsQuery.data.model_revision !== model.model_revision
          }
          onApplyFilters={onApplyResultFilters}
        />
      ) : (
        <ProfilingRuns
          items={runsQuery.data?.items ?? []}
          state={runState}
          isLoading={runsQuery.isPending}
          isError={runsQuery.isError}
          selectedRunId={selectedRunId}
          onStateChange={(state) => {
            setSelectedRunId(null);
            setRunState(state);
          }}
          onShowDetails={setSelectedRunId}
        />
      )}

      {selectedRunId !== null ? (
        <ProfilingRunDrawer
          api={api}
          tenantId={tenantId}
          model={model}
          runId={selectedRunId}
          onClose={() => {
            runReturnId.current = selectedRunId;
            setSelectedRunId(null);
          }}
        />
      ) : null}

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
    </div>
  );
}
