import { useQuery } from "@tanstack/react-query";
import { Link } from "@tanstack/react-router";

import { TenantWorkspace } from "../../app/TenantWorkspace";
import { formatDateTime } from "../../shared/presentation";
import { ErrorPage, LoadingPage } from "../../shared/ui";
import type { TenantsApi } from "../tenants/api";
import { ModelWorkspaceShell } from "./ModelWorkspaceShell";
import type {
  ModelDetail,
  ModelsApi,
  ModelWorkflowOverview,
  QualityWarningCode,
  WorkflowLedgerEntry,
} from "./api";

type ModelOverviewApi = Pick<TenantsApi, "readTenantHome"> & ModelsApi;

export function ModelOverviewScreen({
  api,
  tenantId,
  modelId,
}: {
  api: ModelOverviewApi;
  tenantId: number;
  modelId: number;
}) {
  const validIds = validTenantModelIds(tenantId, modelId);
  const homeQuery = useQuery({
    queryKey: ["tenant-home", tenantId],
    queryFn: () => api.readTenantHome(tenantId),
    enabled: validIds,
  });
  const modelQuery = useQuery({
    queryKey: ["model", tenantId, modelId],
    queryFn: () => api.readModel(tenantId, modelId),
    enabled: validIds,
  });
  const overviewQuery = useQuery({
    queryKey: ["model-overview", tenantId, modelId],
    queryFn: () => api.readModelOverview(tenantId, modelId),
    enabled: validIds,
  });

  if (!validIds) return <ErrorPage />;
  if (homeQuery.isPending || modelQuery.isPending || overviewQuery.isPending) {
    return <LoadingPage label="Loading Model" />;
  }
  if (homeQuery.isError || modelQuery.isError || overviewQuery.isError) return <ErrorPage />;

  return (
    <TenantWorkspace home={homeQuery.data} activeNav="models" model={modelQuery.data}>
      <ModelWorkspaceShell model={modelQuery.data} activeStage="overview">
        <ModelOverviewView
          model={modelQuery.data}
          overview={overviewQuery.data}
          tenantId={tenantId}
        />
      </ModelWorkspaceShell>
    </TenantWorkspace>
  );
}

function validTenantModelIds(tenantId: number, modelId: number): boolean {
  return Number.isSafeInteger(tenantId)
    && tenantId > 0
    && Number.isSafeInteger(modelId)
    && modelId > 0;
}

function ModelOverviewView({
  model,
  overview,
  tenantId,
}: {
  model: ModelDetail;
  overview: ModelWorkflowOverview;
  tenantId: number;
}) {
  return (
    <div className="model-overview page-enter">
      <header className="model-overview-header">
        <div>
          <p className="eyebrow">Model overview</p>
          <h1>{model.model_name}</h1>
          <p>{model.model_description ?? "No description provided."}</p>
        </div>
        <div className="model-overview-facts" aria-label="Model facts">
          <DetailFact label="Revision" value={`r${model.model_revision}`} />
          <DetailFact label="Status" value={model.is_active ? "Active" : "Archived"} />
          <DetailFact label="Updated" value={formatDateTime(model.updated_at) ?? "—"} />
        </div>
      </header>

      <section className="workflow-ledger" aria-labelledby="workflow-ledger-heading">
        <header>
          <div>
            <p className="eyebrow">Current model journey</p>
            <h2 id="workflow-ledger-heading">Workflow ledger</h2>
          </div>
          <span>Server-backed · quality warnings never block</span>
        </header>
        {overview.model_revision !== model.model_revision ? (
          <div className="surface-state is-error" role="alert">
            The Model changed while its workflow ledger was loading. Refresh to reconcile revisions.
          </div>
        ) : (
          <div className="table-scroll">
            <table aria-label="Model workflow ledger">
              <thead>
                <tr>
                  <th>Workflow</th>
                  <th>Coverage</th>
                  <th>State / latest run</th>
                  <th>Quality / action</th>
                </tr>
              </thead>
              <tbody>
                {overview.items.map((row) => (
                  <tr key={row.workflow}>
                    <td><strong>{ledgerWorkflowLabel(row.workflow)}</strong></td>
                    <td><WorkflowCoverage row={row} /></td>
                    <td>
                      <span className="workflow-state-cell">
                        <WorkflowStateBadge state={row.state} />
                        {row.latest_run_id ? (
                          <small>
                            Run {row.latest_run_id}
                            {formatDateTime(row.latest_run_created_at)
                              ? ` · ${formatDateTime(row.latest_run_created_at)}`
                              : ""}
                          </small>
                        ) : null}
                      </span>
                    </td>
                    <td>
                      {row.workflow === "scope" ? (
                        <Link
                          className="text-action"
                          to="/tenants/$tenantId/models/$modelId/input-scope"
                          params={{ tenantId: String(tenantId), modelId: String(model.model_id) }}
                        >
                          Review Input Scope
                        </Link>
                      ) : row.workflow === "profiling" ? (
                        <Link
                          className="text-action"
                          to="/tenants/$tenantId/models/$modelId/profiling"
                          params={{ tenantId: String(tenantId), modelId: String(model.model_id) }}
                        >
                          Review Profiling
                        </Link>
                      ) : row.workflow === "analysis" ? (
                        <Link
                          className="text-action"
                          to="/tenants/$tenantId/models/$modelId/analysis"
                          params={{ tenantId: String(tenantId), modelId: String(model.model_id) }}
                        >
                          Review Analysis
                        </Link>
                      ) : row.workflow === "assertions" ? (
                        <Link
                          className="text-action"
                          to="/tenants/$tenantId/models/$modelId/assertions"
                          params={{ tenantId: String(tenantId), modelId: String(model.model_id) }}
                        >
                          Review Assertions
                        </Link>
                      ) : row.quality_warning_codes.length ? (
                        <span className="workflow-warnings">
                          {row.quality_warning_codes.map((warning) => (
                            <span key={warning}>{qualityWarningLabel(warning)}</span>
                          ))}
                        </span>
                      ) : (
                        <span className="unavailable-action">No quality warning</span>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>
    </div>
  );
}

function WorkflowCoverage({ row }: { row: WorkflowLedgerEntry }) {
  return (
    <span className="workflow-coverage">
      <strong>
        {row.result_count} {row.workflow === "scope" ? "Objects" : "results"}
      </strong>
      {row.locked_count ? <small>{row.locked_count} locked</small> : null}
    </span>
  );
}

function WorkflowStateBadge({ state }: { state: WorkflowLedgerEntry["state"] }) {
  const labels: Record<WorkflowLedgerEntry["state"], string> = {
    empty: "Empty",
    ready: "Ready",
    not_started: "Not started",
    queued: "Queued",
    running: "Running",
    results_available: "Results available",
    completed_no_results: "Completed · no results",
    failed: "Failed",
  };
  const tone = state === "ready" || state === "results_available"
    ? "is-success"
    : state === "queued" || state === "running"
      ? "is-warning"
      : state === "failed"
        ? "is-danger"
        : "is-neutral";
  return <span className={`status-badge ${tone}`}>{labels[state]}</span>;
}

function ledgerWorkflowLabel(workflow: WorkflowLedgerEntry["workflow"]): string {
  return workflow[0]?.toLocaleUpperCase() + workflow.slice(1);
}

function qualityWarningLabel(warning: QualityWarningCode): string {
  const labels: Record<QualityWarningCode, string> = {
    scope_empty: "Model Input Scope is empty",
    profiling_results_unavailable: "Profiling results unavailable",
    conceptual_results_unavailable: "Conceptual results unavailable",
    logical_results_unavailable: "Logical results unavailable",
  };
  return labels[warning];
}

function DetailFact({ label, value }: { label: string; value: string }) {
  return (
    <span>
      <small>{label}</small>
      <strong>{value}</strong>
    </span>
  );
}
