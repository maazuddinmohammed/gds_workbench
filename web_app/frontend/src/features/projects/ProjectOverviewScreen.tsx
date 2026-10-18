import { useQuery } from "@tanstack/react-query";
import { Link } from "@tanstack/react-router";

import { TenantWorkspace } from "../../app/TenantWorkspace";
import { formatDateTime } from "../../shared/presentation";
import { ErrorPage, LoadingPage, WorkspaceToolbar } from "../../shared/ui";
import type { TenantsApi } from "../tenants/api";
import { validTenantProjectIds } from "./ProjectRouteFrame";
import { ProjectWorkspaceShell } from "./ProjectWorkspaceShell";
import type {
  ProjectDetail,
  ProjectsApi,
  ProjectWorkflowOverview,
  QualityWarningCode,
  WorkflowLedgerEntry,
} from "./api";

type ProjectOverviewApi = Pick<TenantsApi, "readTenantHome"> & ProjectsApi;

export function ProjectOverviewScreen({
  api,
  tenantId,
  projectId,
}: {
  api: ProjectOverviewApi;
  tenantId: number;
  projectId: number;
}) {
  const validIds = validTenantProjectIds(tenantId, projectId);
  const homeQuery = useQuery({
    queryKey: ["tenant-home", tenantId],
    queryFn: () => api.readTenantHome(tenantId),
    enabled: validIds,
  });
  const projectQuery = useQuery({
    queryKey: ["project", tenantId, projectId],
    queryFn: () => api.readProject(tenantId, projectId),
    enabled: validIds,
  });
  const overviewQuery = useQuery({
    queryKey: ["project-overview", tenantId, projectId],
    queryFn: () => api.readProjectOverview(tenantId, projectId),
    enabled: validIds,
  });

  if (!validIds) return <ErrorPage />;
  if (homeQuery.isPending || projectQuery.isPending || overviewQuery.isPending) {
    return <LoadingPage label="Loading Project" />;
  }
  if (homeQuery.isError || projectQuery.isError || overviewQuery.isError) return <ErrorPage />;

  return (
    <TenantWorkspace home={homeQuery.data} activeNav="projects" project={projectQuery.data}>
      <ProjectWorkspaceShell api={api} tenantLock={homeQuery.data.lock} project={projectQuery.data} activeStage="overview">
        <ProjectOverviewView
          project={projectQuery.data}
          overview={overviewQuery.data}
          tenantId={tenantId}
          refreshing={homeQuery.isFetching || projectQuery.isFetching || overviewQuery.isFetching}
          onRefresh={() => void Promise.all([homeQuery.refetch(), projectQuery.refetch(), overviewQuery.refetch()])}
        />
      </ProjectWorkspaceShell>
    </TenantWorkspace>
  );
}

function ProjectOverviewView({
  project,
  overview,
  tenantId,
  refreshing,
  onRefresh,
}: {
  project: ProjectDetail;
  overview: ProjectWorkflowOverview;
  tenantId: number;
  refreshing: boolean;
  onRefresh: () => void;
}) {
  return (
    <div className="project-overview page-enter">
      <h1 className="project-section-title sr-only">Overview</h1>
      <WorkspaceToolbar actions={<button className="button button-secondary button-small" type="button" disabled={refreshing} onClick={onRefresh}>
        {refreshing ? "Refreshing…" : "Refresh"}
      </button>}><span>Workflow coverage</span></WorkspaceToolbar>
      <header className="project-overview-header" aria-label="Project summary">
        <dl className="project-overview-schemas">
          {[
            { label: "Logical schemas", schemas: project.logical_schemas },
            { label: "Dimensional schemas", schemas: project.dimensional_schemas },
          ].map(({ label, schemas }) => (
            <div key={label}>
              <dt>{label}</dt>
              <dd>{schemas.length ? <ul aria-label={label} role="list">
                {schemas.map((schema) => <li key={schema.schema_name}>{schema.schema_name}</li>)}
              </ul> : <span className="project-schema-empty">None configured</span>}</dd>
            </div>
          ))}
        </dl>
        <dl className="project-overview-meta">
          <div><dt>Status</dt><dd>
            <span className={`status-badge ${project.is_active ? "is-success" : "is-neutral"}`}>
              {project.is_active ? "Active" : "Archived"}
            </span>
          </dd></div>
          <div><dt>Updated</dt><dd>
            <time dateTime={project.updated_at}>{formatDateTime(project.updated_at) ?? "—"}</time>
          </dd></div>
        </dl>
      </header>

      <section className="workflow-ledger" aria-labelledby="workflow-ledger-heading">
        <h2 id="workflow-ledger-heading" className="sr-only">Workflow ledger</h2>
        {overview.project_revision !== project.project_revision ? (
          <div className="surface-state is-error" role="alert">
            The Project changed while its workflow ledger was loading. Refresh to reconcile revisions.
          </div>
        ) : (
          <div className="table-scroll ledger-grid" role="region" aria-label="Workflow coverage table" tabIndex={0}>
            <table aria-label="Project workflow ledger">
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
                          to="/tenants/$tenantId/projects/$projectId/input-scope"
                          params={{ tenantId: String(tenantId), projectId: String(project.project_id) }}
                        >
                          Review Input Scope
                        </Link>
                      ) : row.workflow === "profiling" ? (
                        <Link
                          className="text-action"
                          to="/tenants/$tenantId/projects/$projectId/profiling"
                          params={{ tenantId: String(tenantId), projectId: String(project.project_id) }}
                        >
                          Review Profiling
                        </Link>
                      ) : row.workflow === "analysis" ? (
                        <Link
                          className="text-action"
                          to="/tenants/$tenantId/projects/$projectId/analysis"
                          params={{ tenantId: String(tenantId), projectId: String(project.project_id) }}
                        >
                          Review Analysis
                        </Link>
                      ) : row.workflow === "context" ? (
                        <Link
                          className="text-action"
                          to="/tenants/$tenantId/projects/$projectId/context"
                          params={{ tenantId: String(tenantId), projectId: String(project.project_id) }}
                        >
                          Review Context
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
    failed: "Failed", cancelled: "Cancelled",
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
    scope_empty: "Project Input Scope is empty",
    profiling_results_unavailable: "Profiling results unavailable",
    logical_results_unavailable: "Logical results unavailable",
  };
  return labels[warning];
}
