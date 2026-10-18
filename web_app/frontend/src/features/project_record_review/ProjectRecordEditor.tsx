import { useNavigate } from "@tanstack/react-router";
import { useRef, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ApiError } from "../../core/http";
import { trapDialogFocus, useDialogFocus } from "../../shared/dialog";
import type { EditableDataset, ProjectRecordEditorApi, ProjectRecordEditor as Editor, ProjectRecordEditorRequest, ProjectReviewCommand } from "./api";
import { ReviewDialog } from "./ProjectRecordReview";
import { WorkflowMenu } from "../workflows/WorkflowCommandCenter";

export function ProjectRecordTools({ api, tenantId, projectId, projectRevision, hasTenantLock, canDelete = false, dataset, recordId }: {
  api: ProjectRecordEditorApi; tenantId: number; projectId: number; projectRevision: number;
  hasTenantLock: boolean; canDelete?: boolean; dataset: EditableDataset; recordId: number;
}) {
  const [editing, setEditing] = useState(false);
  const [review, setReview] = useState<ProjectReviewCommand | null>(null);
  const client = useQueryClient();
  const navigate = useNavigate();
  const refresh = async () => { await client.invalidateQueries({ predicate: (query) => query.queryKey[1] === tenantId }); };
  return <div className="project-detail-tools">
    <div className="workflow-command-actions">
      <button className="button button-secondary button-small" type="button" disabled={!hasTenantLock}
        title={hasTenantLock ? undefined : "Tenant Lock required"} onClick={() => setEditing(true)}>Edit definition</button>
      <WorkflowMenu>{((canDelete ? ["lock", "unlock", "deactivate", "reactivate", "delete"] : ["lock", "unlock", "deactivate", "reactivate"]) as ProjectReviewCommand["action"][]).map((action) => <button key={action} className={`button button-secondary button-small${action === "delete" ? " project-delete-action" : ""}`} type="button"
        disabled={!hasTenantLock} title={hasTenantLock ? undefined : "Tenant Lock required"}
        onClick={() => setReview({ dataset, record_ids: [recordId], action, expected_project_revision: projectRevision })}>
        {action === "delete" ? "Delete" : action === "deactivate" ? "Deactivate" : action === "reactivate" ? "Activate" : action === "lock" ? "Lock" : "Unlock"}
      </button>)}</WorkflowMenu>
    </div>
    {editing ? <ProjectRecordEditor api={api} tenantId={tenantId} projectId={projectId} projectRevision={projectRevision}
      hasTenantLock={hasTenantLock} command={{ dataset, record_id: recordId, expected_project_revision: projectRevision }}
      onClose={() => setEditing(false)} onSaved={refresh} /> : null}
    {review ? <ReviewDialog key={`${review.dataset}:${review.action}:${review.record_ids.join()}`}
      api={api} tenantId={tenantId} projectId={projectId} command={review} projectRevision={projectRevision}
      hasTenantLock={hasTenantLock} onReview={setReview} onClose={() => setReview(null)}
      onApplied={async () => {
        setReview(null);
        if (review.action === "delete") await navigate({
          to: dataset.startsWith("conceptual_") ? "/tenants/$tenantId/projects/$projectId/conceptual"
            : dataset.startsWith("logical_") ? "/tenants/$tenantId/projects/$projectId/logical"
              : "/tenants/$tenantId/projects/$projectId/dimensional",
          params: { tenantId: String(tenantId), projectId: String(projectId) },
        });
        await refresh();
      }} /> : null}
  </div>;
}

export function ProjectRecordEditor({ api, tenantId, projectId, projectRevision, hasTenantLock, command, onClose, onSaved }: {
  api: ProjectRecordEditorApi; tenantId: number; projectId: number; projectRevision: number; hasTenantLock: boolean;
  command: ProjectRecordEditorRequest; onClose: () => void; onSaved: () => Promise<void>;
}) {
  const [initialCommand] = useState(command);
  const [changes, setChanges] = useState<Record<string, unknown>>({});
  const close = useRef<HTMLButtonElement>(null);
  const request = useRef<{ command: ProjectRecordEditorRequest & { changes: Record<string, unknown> }; key: string } | null>(null);
  const query = useQuery({ queryKey: ["project-record-editor", tenantId, projectId, initialCommand],
    queryFn: () => api.readProjectRecordEditor(tenantId, projectId, initialCommand), retry: false, staleTime: Infinity });
  const mutation = useMutation({
    mutationFn: (attempt: NonNullable<typeof request.current>) => api.saveProjectRecord(tenantId, projectId, attempt.command, attempt.key),
    onSuccess: async () => { request.current = null; await onSaved(); onClose(); },
    onError: (error) => { if (error instanceof ApiError && error.status < 500 && error.status !== 408) request.current = null; },
  });
  const retryable = mutation.isError && request.current !== null;
  const busy = mutation.isPending || retryable;
  const stale = initialCommand.expected_project_revision !== projectRevision;
  useDialogFocus(close);
  return <div className="dialog-scrim" role="presentation"><section className="run-configuration-dialog project-record-review-dialog"
    role="dialog" aria-modal="true" aria-labelledby="project-record-editor-heading" onKeyDown={(event) => {
      if (event.key === "Escape" && !busy) onClose(); trapDialogFocus(event);
    }}>
    <header className="drawer-header"><div><small>{initialCommand.dataset.replaceAll("_", " ")}</small><h2 id="project-record-editor-heading">Edit definition</h2></div>
      <button ref={close} className="panel-close" type="button" aria-label="Close editor" disabled={busy} onClick={onClose}>×</button>
    </header>
    <form className="project-record-review-body project-record-editor" onSubmit={(event) => {
      event.preventDefault();
      if (busy || stale || !hasTenantLock || query.data?.is_locked || !Object.keys(changes).length) return;
      request.current = { command: { ...initialCommand, changes: Object.fromEntries(Object.entries(changes).map(([name, value]) => [name, Array.isArray(value) ? value.map((item: string) => item.trim()).filter(Boolean) : value])) }, key: crypto.randomUUID() };
      mutation.mutate(request.current);
    }}>
      {query.isPending ? <p aria-busy="true">Loading definition…</p> : null}
      {query.isError ? <p role="alert">{editError(query.error)}</p> : null}
      {query.data ? <>
        <strong>{query.data.label}</strong>
        <p className="field-help">Identity and relationship endpoints stay fixed. Evidence and lifecycle are preserved. Review downstream mapping, code, and validations after editing.</p>
        {query.data.is_locked ? <p role="alert">Unlock this record before editing it.</p> : null}
        <fieldset disabled={busy || stale || !hasTenantLock || query.data.is_locked}>
          {query.data.fields.map((field) => <EditorControl key={field.name} field={field}
            value={field.name in changes ? changes[field.name] : field.value}
            onChange={(value) => { setChanges((previous) => ({ ...previous, [field.name]: value })); mutation.reset(); }} />)}
        </fieldset>
      </> : null}
      {stale ? <p role="alert">The Project changed. Close and reopen this editor before saving.</p> : null}
      {!hasTenantLock ? <p role="alert">Tenant Lock required to save.</p> : null}
      {mutation.isError ? <p role="alert">{retryable ? "The save result could not be confirmed. Retry the same save safely." : editError(mutation.error)}</p> : null}
      <footer className="workflow-command-actions">
        <button className="button button-secondary" type="button" disabled={busy} onClick={onClose}>Cancel</button>
        {retryable ? <button className="button button-primary" type="button" disabled={mutation.isPending || !hasTenantLock}
          onClick={() => { if (request.current) mutation.mutate(request.current); }}>Retry save</button>
          : <button className="button button-primary" type="submit" disabled={busy || stale || !hasTenantLock || !query.data || query.data.is_locked || !Object.keys(changes).length}>
            {mutation.isPending ? "Saving…" : "Save changes"}</button>}
      </footer>
    </form>
  </section></div>;
}

function EditorControl({ field, value, onChange }: { field: Editor["fields"][number]; value: unknown; onChange: (value: unknown) => void }) {
  const id = `edit-${field.name}`;
  if (field.kind === "boolean") return <label htmlFor={id} className="project-editor-checkbox"><input id={id} type="checkbox" checked={value === true} onChange={(event) => onChange(event.target.checked)} />{field.label}</label>;
  const text = Array.isArray(value) ? value.join("\n") : String(value ?? "");
  return <label htmlFor={id}>{field.label}{!field.required ? " (optional)" : ""}
    {field.kind === "choice" ? <select id={id} value={text} required={field.required} onChange={(event) => onChange(event.target.value || null)}>
      {!field.required ? <option value="">Not specified</option> : null}
      {field.options.map((option) => <option key={option} value={option}>{field.name === "dimensional_attribute_key_role" && option === "business" ? "Natural key" : option.replaceAll("_", " ")}</option>)}
    </select> : field.kind === "multiline" || field.kind === "lines" ? <textarea id={id} rows={3} value={text}
      required={field.required && field.kind !== "lines"} maxLength={field.maximum_length ?? undefined}
      onChange={(event) => onChange(field.kind === "lines" ? event.target.value.split("\n") : event.target.value || null)} />
      : <input id={id} type={field.kind === "number" ? "number" : "text"} value={text} required={field.required}
        min={field.minimum ?? undefined} maxLength={field.maximum_length ?? undefined}
        onChange={(event) => onChange(field.kind === "number" ? event.target.value === "" ? null : Number(event.target.value) : event.target.value || null)} />}
    {field.kind === "lines" ? <small>One alias per line.</small> : null}
  </label>;
}
function editError(error: Error): string {
  if (error instanceof ApiError) {
    if (error.code === "record_locked") return "Unlock this record before editing it.";
    if (error.status === 403) return "Editing requires permission and your Tenant Lock.";
    if (error.status === 409) return "The Project changed or has an active workflow. Close and refresh before editing again.";
    if (error.status === 422 || error.code === "invalid_request") return "Check the required fields and type-specific modeling rules. No changes were saved.";
  }
  return "The definition could not be loaded or saved. Try again.";
}
