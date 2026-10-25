import { useEffect, useRef, useState } from "react";
import { Link, useNavigate } from "@tanstack/react-router";
import { useQuery, useQueryClient } from "@tanstack/react-query";

import { ApiError } from "../../core/http";
import { formatRequiredDateTime as formatDateTime } from "../../shared/presentation";
import { DetailState } from "../../shared/ui";
import type { ProjectDetail } from "../projects/api";
import { ProjectRecordReview } from "../project_record_review/ProjectRecordReview";
import { subjectAreaQueryKeys, tableLabel, type SubjectAreaApi, type SubjectAreaDetail } from "./api";
import { AddTablesDialog, AreaChips, ColumnMeter, SubjectAreaEditorDialog, useSubjectAreaSave } from "./SubjectAreaDialogs";
import "./subject-areas.css";

export function SubjectAreaDetailPage({ api, tenantId, project, subjectAreaId, hasTenantLock, canDelete = false }: {
  api: SubjectAreaApi; tenantId: number; project: ProjectDetail; subjectAreaId: number;
  hasTenantLock: boolean; canDelete?: boolean;
}) {
  const query = useQuery({
    queryKey: subjectAreaQueryKeys.area(tenantId, project.project_id, subjectAreaId),
    queryFn: () => api.readSubjectArea(tenantId, project.project_id, subjectAreaId),
  });
  if (query.isPending) return <DetailState label="Loading Subject Area…" />;
  if (query.isError) {
    return <DetailState error label={query.error instanceof ApiError && query.error.status === 404
      ? "This Subject Area is unavailable. Return to Subject Areas and refresh."
      : query.error instanceof ApiError && query.error.status === 403
        ? "You do not have permission to view this Subject Area."
        : "The Subject Area could not be loaded. Refresh to try again."} />;
  }
  return <SubjectAreaView api={api} tenantId={tenantId} project={project} area={query.data}
    hasTenantLock={hasTenantLock} canDelete={canDelete} />;
}

function SubjectAreaView({ api, tenantId, project, area, hasTenantLock, canDelete }: {
  api: SubjectAreaApi; tenantId: number; project: ProjectDetail; area: SubjectAreaDetail;
  hasTenantLock: boolean; canDelete: boolean;
}) {
  const projectId = project.project_id;
  const queryClient = useQueryClient();
  const navigate = useNavigate();
  const heading = useRef<HTMLHeadingElement>(null);
  const [dialog, setDialog] = useState<"edit" | "add" | null>(null);
  const [selected, setSelected] = useState<Set<number>>(new Set());
  const [notice, setNotice] = useState("");
  useEffect(() => heading.current?.focus(), []);
  const stale = area.project_revision !== project.project_revision;
  const locked = area.subject_area_is_locked;
  const memberIds = new Set(area.tables.map((table) => table.object_id));
  const membershipId = (objectId: number) => area.tables.find((table) => table.object_id === objectId)?.areas
    .find((item) => item.subject_area_id === area.subject_area_id);
  const removable = [...selected].filter((objectId) => membershipId(objectId)?.subject_area_table_is_locked === false);
  const invalidate = async () => {
    setSelected(new Set());
    await Promise.all([
      queryClient.invalidateQueries({ queryKey: subjectAreaQueryKeys.all(tenantId, projectId) }),
      queryClient.invalidateQueries({ queryKey: ["project", tenantId, projectId] }),
      queryClient.invalidateQueries({ queryKey: ["project-overview", tenantId, projectId] }),
      queryClient.invalidateQueries({ queryKey: ["tenant-home", tenantId] }),
    ]);
  };
  const removal = useSubjectAreaSave({ api, tenantId, projectId, onSaved: async () => {
    setNotice("Tables removed from this area. They stay in the Input Scope and any other area.");
    await invalidate();
  } });
  const blocked = !hasTenantLock ? "Tenant Lock required" : stale ? "Refresh before changing this area"
    : locked ? "Unlock this area first" : undefined;
  const statusLabel = area.subject_area_status === "active" ? "Active"
    : area.subject_area_status === "inactive" ? "Inactive" : "Deprecated";

  return <article className="workflow-detail-page modeled-detail-page subject-area-detail-page page-enter">
    <header className="workflow-detail-header">
      <div className="workspace-record-heading">
        <Link className="text-action" to="/tenants/$tenantId/projects/$projectId/subject-areas"
          params={{ tenantId: String(tenantId), projectId: String(projectId) }}>← Back to Subject Areas</Link>
        <div className="subject-area-detail-title">
          <h1 ref={heading} tabIndex={-1}>{area.subject_area_name}</h1>
          <div className="detail-badge-stack">
            <span className={`status-badge ${area.subject_area_status === "active" ? "is-success" : "is-warning"}`}>{statusLabel}</span>
            <span className="status-badge is-neutral">{locked ? "Locked" : "Open"}</span>
          </div>
        </div>
      </div>
      <div className="workflow-command-actions">
        <button className="button button-secondary button-small" type="button" disabled={Boolean(blocked)} title={blocked}
          onClick={() => setDialog("edit")}>Edit</button>
        <button className="button button-primary button-small" type="button" disabled={Boolean(blocked)} title={blocked}
          onClick={() => setDialog("add")}>Add tables</button>
        <ProjectRecordReview presentation="record" api={api} tenantId={tenantId} projectId={projectId}
          projectRevision={project.project_revision} dataset="subject_area" selectedIds={new Set([area.subject_area_id])}
          hasTenantLock={hasTenantLock} disabled={stale}
          actions={canDelete ? ["lock", "unlock", "deactivate", "reactivate", "delete"] : ["lock", "unlock", "deactivate", "reactivate"]}
          onApplied={async () => {
            await invalidate();
            if (!(await queryClient.fetchQuery({
              queryKey: subjectAreaQueryKeys.areas(tenantId, projectId),
              queryFn: () => api.listSubjectAreas(tenantId, projectId),
            })).items.some((item) => item.subject_area_id === area.subject_area_id)) {
              await navigate({ to: "/tenants/$tenantId/projects/$projectId/subject-areas",
                params: { tenantId: String(tenantId), projectId: String(projectId) } });
            }
          }} />
      </div>
    </header>

    {stale ? <p className="inline-error" role="alert">The Project changed. Refresh to see the current Subject Area.</p> : null}
    <section className="detail-section detail-primary" aria-label="Subject Area definition">
      <dl className="modeled-detail-fields">
        <div className="is-definition"><dt>Definition</dt><dd>{area.subject_area_definition}</dd></div>
        <div><dt>Tables</dt><dd>{area.table_count}</dd></div>
        <div><dt>Columns</dt><dd><ColumnMeter columns={area.column_count} limit={area.max_subject_area_columns} /></dd></div>
        <div><dt>Updated</dt><dd>{formatDateTime(area.updated_at)}</dd></div>
      </dl>
      {area.column_count > area.max_subject_area_columns ? <p className="subject-area-warning" role="status">
        This area is over the {area.max_subject_area_columns}-column limit. Split it so each Logical Build fits one answer.</p> : null}
    </section>

    <section className="detail-section subject-area-members" aria-labelledby="subject-area-tables-heading">
      <header><h2 id="subject-area-tables-heading">Tables</h2></header>
      <div className="review-selectionbar" hidden={selected.size === 0}>
        <span>{selected.size} selected</span>
        <div className="workflow-command-actions">
          <button className="button button-secondary button-small" type="button"
            disabled={Boolean(blocked) || removal.busy || removable.length === 0}
            title={blocked ?? (removable.length === 0 ? "Locked tables stay in the area" : undefined)}
            onClick={() => {
              setNotice("");
              removal.submit({
                expected_project_revision: project.project_revision,
                subject_area_id: area.subject_area_id,
                remove_object_ids: removable.sort((left, right) => left - right),
              });
            }}>{removal.mutation.isPending ? "Removing…" : removal.retryable ? "Retry removal" : "Remove from area"}</button>
          <ProjectRecordReview presentation="record" api={api} tenantId={tenantId} projectId={projectId}
            projectRevision={project.project_revision} dataset="subject_area_table" hasTenantLock={hasTenantLock}
            disabled={stale} actions={["lock", "unlock"]}
            selectedIds={new Set([...selected].flatMap((objectId) => {
              const membership = membershipId(objectId);
              return membership ? [membership.subject_area_table_id] : [];
            }))}
            onApplied={invalidate} />
        </div>
      </div>
      {notice ? <p role="status">{notice}</p> : null}
      {removal.error ? <p className="inline-error" role="alert">{removal.error}</p> : null}
      {!area.tables.length ? <div className="empty-state compact subject-area-empty">
        <p>No tables yet. Add Bronze Input Scope tables to define what this area covers.</p>
      </div> : <div className="workflow-table-scroll table-scroll ledger-grid subject-area-ledger" tabIndex={0} role="region" aria-label="Scrollable Subject Area tables">
        <table aria-label="Subject Area tables">
          <thead><tr>
            <th><input type="checkbox" aria-label="Select all tables in this area"
              checked={area.tables.every((table) => selected.has(table.object_id))}
              onChange={(event) => setSelected(event.target.checked ? new Set(area.tables.map((table) => table.object_id)) : new Set())} /></th>
            <th>Table</th><th>System</th><th className="is-numeric">Columns</th><th>Description</th><th>Also in</th><th>Lock</th>
          </tr></thead>
          <tbody>{area.tables.map((table) => {
            const membership = membershipId(table.object_id);
            return <tr key={table.object_id}>
              <td><input type="checkbox" aria-label={`Select ${tableLabel(table)}`} checked={selected.has(table.object_id)}
                onChange={(event) => {
                  const next = new Set(selected);
                  if (event.target.checked) next.add(table.object_id); else next.delete(table.object_id);
                  setSelected(next);
                }} /></td>
              <th scope="row"><span className="subject-area-table-name"><strong>{table.object_name}</strong><small>{table.object_schema}</small></span></th>
              <td>{table.system_code}</td>
              <td className="is-numeric">{table.column_count}</td>
              <td className="subject-area-description">{table.object_description ?? <span className="subject-area-muted">No description</span>}</td>
              <td><AreaChips memberships={table.areas} exceptId={area.subject_area_id} /></td>
              <td>{membership?.subject_area_table_is_locked ? "Locked" : "Open"}</td>
            </tr>;
          })}</tbody>
        </table>
      </div>}
    </section>

    {dialog === "edit" ? <SubjectAreaEditorDialog api={api} tenantId={tenantId} projectId={projectId}
      projectRevision={project.project_revision} hasTenantLock={hasTenantLock} maxColumns={area.max_subject_area_columns}
      area={area} onClose={() => setDialog(null)} onSaved={async (_result, saved) => {
        await invalidate();
        if (saved.name.toLocaleLowerCase() === area.subject_area_name.toLocaleLowerCase()) return;
        // A rename saves the area under its new name and keeps the old one inactive.
        const page = await queryClient.fetchQuery({
          queryKey: subjectAreaQueryKeys.areas(tenantId, projectId),
          queryFn: () => api.listSubjectAreas(tenantId, projectId),
        });
        const renamed = page.items.find((item) => item.subject_area_status === "active"
          && item.subject_area_name.toLocaleLowerCase() === saved.name.toLocaleLowerCase());
        await navigate(renamed ? {
          to: "/tenants/$tenantId/projects/$projectId/subject-areas/$subjectAreaId",
          params: { tenantId: String(tenantId), projectId: String(projectId), subjectAreaId: String(renamed.subject_area_id) },
        } : {
          to: "/tenants/$tenantId/projects/$projectId/subject-areas",
          params: { tenantId: String(tenantId), projectId: String(projectId) },
        });
      }} /> : null}
    {dialog === "add" ? <AddTablesDialog api={api} tenantId={tenantId} projectId={projectId}
      projectRevision={project.project_revision} hasTenantLock={hasTenantLock} maxColumns={area.max_subject_area_columns}
      area={area} memberIds={memberIds} memberColumns={area.column_count}
      onClose={() => setDialog(null)} onSaved={invalidate} /> : null}
  </article>;
}
