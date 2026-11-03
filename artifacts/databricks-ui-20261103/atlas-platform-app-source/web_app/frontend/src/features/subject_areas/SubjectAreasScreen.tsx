import { useState } from "react";
import { Link } from "@tanstack/react-router";
import { useQuery, useQueryClient } from "@tanstack/react-query";

import { ApiError } from "../../core/http";
import { formatRequiredDateTime as formatDateTime } from "../../shared/presentation";
import type { ProjectDetail } from "../projects/api";
import { ProjectLayerActions } from "../project_record_review/ProjectLayerActions";
import { ProjectRecordReview } from "../project_record_review/ProjectRecordReview";
import { WorkflowCommandCenter, WorkflowCommandTools, WorkflowFilters, WorkflowMenu } from "../workflows/WorkflowCommandCenter";
import { WorkflowRunDialog } from "../workflows/WorkflowRunDialog";
import { WorkflowRunMonitor } from "../workflows/WorkflowRunMonitor";
import { subjectAreaQueryKeys, type ScopeTable, type SubjectAreaApi, type SubjectAreaSummary } from "./api";
import { AreaChips, AssignTablesDialog, SubjectAreaEditorDialog } from "./SubjectAreaDialogs";
import "./subject-areas.css";
import { RefreshButton } from "../../shared/ui";

type View = "areas" | "unassigned";
type StatusFilter = "active" | "inactive" | "all";

export function SubjectAreasScreen({ api, tenantId, project, hasTenantLock, canDelete = false }: {
  api: SubjectAreaApi;
  tenantId: number;
  project: ProjectDetail;
  hasTenantLock: boolean;
  canDelete?: boolean;
}) {
  const queryClient = useQueryClient();
  const projectId = project.project_id;
  const [view, setView] = useState<View>("areas");
  const [status, setStatus] = useState<StatusFilter>("active");
  const [search, setSearch] = useState("");
  const [selectedAreaIds, setSelectedAreaIds] = useState<Set<number>>(new Set());
  const [selectedTableIds, setSelectedTableIds] = useState<Set<number>>(new Set());
  const [dialog, setDialog] = useState<"create" | "assign" | "run" | "run-selected" | null>(null);
  const [recentRunId, setRecentRunId] = useState<number | null>(null);
  const areasQuery = useQuery({
    queryKey: subjectAreaQueryKeys.areas(tenantId, projectId),
    queryFn: () => api.listSubjectAreas(tenantId, projectId),
  });
  const tablesQuery = useQuery({
    queryKey: subjectAreaQueryKeys.tables(tenantId, projectId),
    queryFn: () => api.listSubjectAreaScopeTables(tenantId, projectId),
    enabled: view === "unassigned" || dialog === "assign",
  });
  const page = areasQuery.data;
  const revisionMismatch = (page !== undefined && page.project_revision !== project.project_revision)
    || (tablesQuery.data !== undefined && tablesQuery.data.project_revision !== project.project_revision);
  const needle = search.trim().toLocaleLowerCase();
  const areas = (page?.items ?? []).filter((area) => (
    (status === "all" || (status === "active") === area.subject_area_is_active)
    && (!needle || area.subject_area_name.toLocaleLowerCase().includes(needle)
      || area.subject_area_definition.toLocaleLowerCase().includes(needle))
  ));
  const unassigned = (tablesQuery.data?.items ?? []).filter((table) => (
    table.areas.length === 0 && (!needle || [table.object_schema, table.object_name, table.system_code]
      .some((value) => value.toLocaleLowerCase().includes(needle)))
  ));
  const activeCount = page?.items.filter((area) => area.subject_area_is_active).length ?? 0;
  const invalidate = async () => {
    setSelectedAreaIds(new Set());
    setSelectedTableIds(new Set());
    await Promise.all([
      queryClient.invalidateQueries({ queryKey: subjectAreaQueryKeys.all(tenantId, projectId) }),
      queryClient.invalidateQueries({ queryKey: ["project", tenantId, projectId] }),
      queryClient.invalidateQueries({ queryKey: ["project-overview", tenantId, projectId] }),
      queryClient.invalidateQueries({ queryKey: ["tenant-home", tenantId] }),
    ]);
  };
  const refreshing = areasQuery.isFetching || tablesQuery.isFetching;
  const lockReason = hasTenantLock ? undefined : "Tenant Lock required";

  return (
    <WorkflowCommandCenter filterCount={(status !== "active" ? 1 : 0) + (needle ? 1 : 0)} className="subject-areas-page page-enter">
      <header className="workflow-commandbar project-section-toolbar subject-areas-commandbar">
        <h1 className="project-section-title sr-only">Subject Areas</h1>
        <div className="workflow-command-context">
          <nav className="workflow-tabs" aria-label="Subject Area views">
            <button className={view === "areas" ? "is-active" : ""} type="button" aria-pressed={view === "areas"}
              onClick={() => { setSelectedTableIds(new Set()); setView("areas"); }}>
              Areas{page ? <span className="command-count" aria-hidden="true">{activeCount}</span> : null}
            </button>
            <button className={view === "unassigned" ? "is-active" : ""} type="button" aria-pressed={view === "unassigned"}
              onClick={() => { setSelectedAreaIds(new Set()); setView("unassigned"); }}>
              Unassigned{page ? <span className="command-count" aria-hidden="true">{page.unassigned_table_count}</span> : null}
            </button>
          </nav>
        </div>
        <div className="workflow-command-actions">
          <WorkflowCommandTools />
          <WorkflowMenu>
            <ProjectLayerActions api={api} tenantId={tenantId} projectId={projectId} projectRevision={project.project_revision}
              hasTenantLock={hasTenantLock} canDelete={canDelete} layer="subject_area" onApplied={() => void invalidate()} />
          </WorkflowMenu>
          <RefreshButton refreshing={refreshing} onClick={() => void invalidate()} />
          <button className="button button-secondary button-small" type="button" disabled={!hasTenantLock || !page}
            title={lockReason} onClick={() => setDialog("create")}>New area</button>
          <button className="button button-primary button-small" type="button" disabled={!hasTenantLock}
            title={lockReason} onClick={() => setDialog("run")}>Run Subject Areas</button>
        </div>
      </header>

      <WorkflowFilters>
        <form className="workflow-filterbar subject-area-filterbar" aria-label="Filter Subject Areas"
          onSubmit={(event) => event.preventDefault()}>
          <label><span>Search</span>
            <input aria-label="Search Subject Areas and Objects" value={search} maxLength={200}
              onChange={(event) => setSearch(event.target.value)} />
          </label>
          {view === "areas" ? <label><span>Status</span>
            <select aria-label="Subject Area status" value={status}
              onChange={(event) => { setSelectedAreaIds(new Set()); setStatus(event.target.value as StatusFilter); }}>
              <option value="active">Active</option>
              <option value="inactive">Inactive</option>
              <option value="all">All statuses</option>
            </select>
          </label> : null}
          <div className="workflow-filter-actions">
            <button className="button button-secondary button-small" type="button"
              onClick={() => { setSearch(""); setStatus("active"); }}>Clear</button>
          </div>
        </form>
      </WorkflowFilters>

      <WorkflowRunMonitor api={api} tenantId={tenantId} projectId={projectId} projectRevision={project.project_revision}
        workflow="subject_area" hasTenantLock={hasTenantLock} focusRunId={recentRunId} onApplied={invalidate} />

      {page ? <p className="subject-area-overview">
        <span><strong>{page.scope_table_count - page.unassigned_table_count}</strong> of {page.scope_table_count} Bronze Input Scope Objects are in an area</span>
      </p> : null}

      {view === "areas" ? <>
        <ProjectRecordReview
          actions={canDelete ? ["lock", "unlock", "deactivate", "reactivate", "delete"] : ["lock", "unlock", "deactivate", "reactivate"]}
          api={api} tenantId={tenantId} projectId={projectId} projectRevision={project.project_revision}
          dataset="subject_area" selectedIds={selectedAreaIds} hasTenantLock={hasTenantLock}
          disabled={areasQuery.isPending || areasQuery.isError || revisionMismatch} onApplied={invalidate} />
        <AreasLedger tenantId={tenantId} projectId={projectId} areas={areas}
          query={areasQuery} revisionMismatch={revisionMismatch} filtered={(page?.items.length ?? 0) > 0}
          selectedIds={selectedAreaIds} onSelectionChange={setSelectedAreaIds}
          onCreate={hasTenantLock ? () => setDialog("create") : undefined} />
      </> : <>
        <div className="review-selectionbar" hidden={selectedTableIds.size === 0}>
          <span>{selectedTableIds.size} selected</span>
          <div className="workflow-command-actions">
            <button className="button button-secondary button-small" type="button" disabled={!hasTenantLock || revisionMismatch}
              title={lockReason} onClick={() => setDialog("assign")}>Add to area…</button>
            <button className="button button-secondary button-small" type="button" disabled={!hasTenantLock || revisionMismatch}
              title={lockReason} onClick={() => setDialog("run-selected")}>Run on selected…</button>
          </div>
        </div>
        <UnassignedLedger tables={unassigned} query={tablesQuery} revisionMismatch={revisionMismatch}
          selectedIds={selectedTableIds} onSelectionChange={setSelectedTableIds} />
      </>}

      {dialog === "create" && page ? <SubjectAreaEditorDialog api={api} tenantId={tenantId} projectId={projectId}
        projectRevision={project.project_revision} hasTenantLock={hasTenantLock}
        onClose={() => setDialog(null)} onSaved={invalidate} /> : null}
      {dialog === "assign" && page ? <AssignTablesDialog api={api} tenantId={tenantId} projectId={projectId}
        projectRevision={project.project_revision} hasTenantLock={hasTenantLock}
        areas={page.items} tables={(tablesQuery.data?.items ?? []).filter((table) => selectedTableIds.has(table.object_id))}
        onClose={() => setDialog(null)} onSaved={invalidate} /> : null}
      {dialog === "run" || dialog === "run-selected" ? <WorkflowRunDialog api={api} tenantId={tenantId} project={project}
        kind="inference" workflow="subject_area" initialSelectedIds={dialog === "run-selected" ? [...selectedTableIds] : []}
        executeCreated={(workflowRunId, executionMode, expectedProjectRevision) => api.executeSubjectAreaRun(
          tenantId, projectId, workflowRunId, executionMode, expectedProjectRevision,
        ).then(() => undefined)}
        onClose={() => setDialog(null)}
        onCreated={async (workflowRunId) => {
          setRecentRunId(workflowRunId);
          await Promise.all([
            queryClient.invalidateQueries({ queryKey: ["project", tenantId, projectId] }),
            queryClient.invalidateQueries({ queryKey: ["tenant-home", tenantId] }),
          ]);
        }} /> : null}
    </WorkflowCommandCenter>
  );
}

function ledgerState(query: { isPending: boolean; isError: boolean; error: Error | null }, revisionMismatch: boolean, labels: {
  loading: string; denied: string; error: string;
}) {
  if (query.isPending) return <div className="surface-state" aria-busy="true">{labels.loading}</div>;
  if (query.isError) {
    const denied = query.error instanceof ApiError && query.error.status === 403;
    return <div className="surface-state is-error" role="alert">{denied ? labels.denied : labels.error}</div>;
  }
  if (revisionMismatch) {
    return <div className="surface-state is-error" role="alert">The Project changed while Subject Areas were loading. Refresh to reconcile revisions.</div>;
  }
  return null;
}

function AreasLedger({ tenantId, projectId, areas, query, revisionMismatch, filtered, selectedIds, onSelectionChange, onCreate }: {
  tenantId: number; projectId: number; areas: SubjectAreaSummary[];
  query: { isPending: boolean; isError: boolean; error: Error | null }; revisionMismatch: boolean; filtered: boolean;
  selectedIds: Set<number>; onSelectionChange: (ids: Set<number>) => void; onCreate?: (() => void) | undefined;
}) {
  const state = ledgerState(query, revisionMismatch, {
    loading: "Loading Subject Areas…",
    denied: "You do not have permission to view Subject Areas.",
    error: "Subject Areas could not be loaded.",
  });
  return <section className="workflow-surface" aria-label="Subject Areas">
    {state ?? (!areas.length ? <div className="empty-state compact subject-area-empty">
      {filtered ? <p>No Subject Areas match these filters.</p> : <>
        <p><strong>No Subject Areas yet.</strong> Run Subject Areas to group the Input Scope Objects by business capability, or create one yourself.</p>
        {onCreate ? <button className="button button-secondary button-small" type="button" onClick={onCreate}>New area</button> : null}
      </>}
    </div> : <div className="workflow-table-scroll table-scroll ledger-grid subject-area-ledger" tabIndex={0} role="region" aria-label="Scrollable Subject Areas">
      <table aria-label="Subject Areas">
        <thead><tr>
          <th><input type="checkbox" aria-label="Select shown Subject Areas"
            checked={areas.every((area) => selectedIds.has(area.subject_area_id))}
            onChange={(event) => onSelectionChange(event.target.checked ? new Set(areas.map((area) => area.subject_area_id)) : new Set())} /></th>
          <th>Subject Area</th><th className="is-numeric">Objects</th><th className="is-numeric">Attributes</th><th>Status</th><th>Lock</th><th>Updated</th>
          <th><span className="sr-only">Actions</span></th>
        </tr></thead>
        <tbody>{areas.map((area) => <tr key={area.subject_area_id}>
          <td><input type="checkbox" aria-label={`Select ${area.subject_area_name}`} checked={selectedIds.has(area.subject_area_id)}
            onChange={(event) => {
              const next = new Set(selectedIds);
              if (event.target.checked) next.add(area.subject_area_id); else next.delete(area.subject_area_id);
              onSelectionChange(next);
            }} /></td>
          <th scope="row"><span className="subject-area-name-cell">
            <strong>{area.subject_area_name}</strong>
            <small>{area.subject_area_definition}</small>
          </span></th>
          <td className="is-numeric">{area.table_count}</td>
          <td className="is-numeric">{area.column_count.toLocaleString()}</td>
          <td><span className={`status-badge ${area.subject_area_is_active ? "is-success" : "is-neutral"}`}>
            {area.subject_area_is_active ? "Active" : "Inactive"}
          </span></td>
          <td>{area.subject_area_is_locked ? "Locked" : "Open"}</td>
          <td>{formatDateTime(area.updated_at)}</td>
          <td><Link className="button button-secondary button-small" aria-label={`Open ${area.subject_area_name}`}
            to="/tenants/$tenantId/projects/$projectId/subject-areas/$subjectAreaId"
            params={{ tenantId: String(tenantId), projectId: String(projectId), subjectAreaId: String(area.subject_area_id) }}>
            Open
          </Link></td>
        </tr>)}</tbody>
      </table>
    </div>)}
  </section>;
}

function UnassignedLedger({ tables, query, revisionMismatch, selectedIds, onSelectionChange }: {
  tables: ScopeTable[]; query: { isPending: boolean; isError: boolean; error: Error | null }; revisionMismatch: boolean;
  selectedIds: Set<number>; onSelectionChange: (ids: Set<number>) => void;
}) {
  const state = ledgerState(query, revisionMismatch, {
    loading: "Loading Input Scope Objects…",
    denied: "You do not have permission to view Input Scope Objects.",
    error: "Input Scope Objects could not be loaded.",
  });
  return <section className="workflow-surface" aria-label="Unassigned Objects">
    {state ?? (!tables.length ? <div className="empty-state compact subject-area-empty">
      <p><strong>Every Input Scope Object is in a Subject Area.</strong></p>
    </div> : <div className="workflow-table-scroll table-scroll ledger-grid subject-area-ledger" tabIndex={0} role="region" aria-label="Scrollable unassigned Objects">
      <table aria-label="Unassigned Objects">
        <thead><tr>
          <th><input type="checkbox" aria-label="Select shown unassigned Objects"
            checked={tables.every((table) => selectedIds.has(table.object_id))}
            onChange={(event) => onSelectionChange(event.target.checked ? new Set(tables.map((table) => table.object_id)) : new Set())} /></th>
          <th>System</th><th>Object schema</th><th>Object name</th><th className="is-numeric">Attributes</th><th>Description</th><th>Subject Areas</th>
        </tr></thead>
        <tbody>{tables.map((table) => <tr key={table.object_id}>
          <td><input type="checkbox" aria-label={`Select ${table.object_schema}.${table.object_name}`} checked={selectedIds.has(table.object_id)}
            onChange={(event) => {
              const next = new Set(selectedIds);
              if (event.target.checked) next.add(table.object_id); else next.delete(table.object_id);
              onSelectionChange(next);
            }} /></td>
          <td>{table.system_code}</td>
          <td>{table.object_schema}</td>
          <th scope="row">{table.object_name}</th>
          <td className="is-numeric">{table.column_count}</td>
          <td className="subject-area-description">{table.object_description ? <span>{table.object_description}</span> : <span className="subject-area-muted">No description</span>}</td>
          <td><AreaChips memberships={table.areas} /></td>
        </tr>)}</tbody>
      </table>
    </div>)}
  </section>;
}
