import { useId, useMemo, useRef, useState, type ReactNode } from "react";
import { useMutation, useQuery } from "@tanstack/react-query";

import { ApiError } from "../../core/http";
import { trapDialogFocus, useDialogFocus } from "../../shared/dialog";
import {
  subjectAreaQueryKeys,
  tableLabel,
  type SaveSubjectAreaCommand,
  type SaveSubjectAreaResult,
  type ScopeTable,
  type SubjectAreaApi,
  type SubjectAreaSummary,
} from "./api";

/** Column total against the per-area cap, in words as well as a bar. */
export function ColumnMeter({ columns, limit }: { columns: number; limit: number }) {
  const over = columns > limit;
  const near = !over && columns >= limit * 0.85;
  const percent = limit > 0 ? Math.min(100, Math.round((columns / limit) * 100)) : 100;
  return <span className={`subject-area-meter${over ? " is-over" : near ? " is-near" : ""}`}>
    <span className="subject-area-meter-track" aria-hidden="true"><span style={{ width: `${percent}%` }} /></span>
    <span className="subject-area-meter-label">
      {columns.toLocaleString()} / {limit.toLocaleString()}{over ? " · over limit" : ""}
    </span>
  </span>;
}

type PickerView = "all" | "unassigned" | "assigned";

/**
 * Search and select Bronze Input Scope tables. Tables in `fixedIds` are shown as already
 * chosen and cannot change; the caller owns the selection.
 */
export function ScopeTablePicker({ tables, selected, onChange, fixedIds, fixedLabel = "In this area", disabled = false }: {
  tables: ScopeTable[];
  selected: ReadonlySet<number>;
  onChange: (ids: Set<number>) => void;
  fixedIds?: ReadonlySet<number>;
  fixedLabel?: string;
  disabled?: boolean;
}) {
  const [search, setSearch] = useState("");
  const [view, setView] = useState<PickerView>("all");
  const [system, setSystem] = useState("");
  const searchId = useId();
  const systems = useMemo(() => [...new Set(tables.map((table) => table.system_code))].sort(), [tables]);
  const needle = search.trim().toLocaleLowerCase();
  const visible = tables.filter((table) => (
    (view === "all" || (view === "unassigned") === (table.areas.length === 0))
    && (!system || table.system_code === system)
    && (!needle || [table.object_schema, table.object_name, table.system_code, table.object_description ?? ""]
      .some((value) => value.toLocaleLowerCase().includes(needle)))
  ));
  const choosable = visible.filter((table) => !fixedIds?.has(table.object_id));
  const allChosen = choosable.length > 0 && choosable.every((table) => selected.has(table.object_id));
  const someChosen = choosable.some((table) => selected.has(table.object_id));
  return <div className="subject-area-picker">
    <div className="subject-area-picker-tools">
      <label htmlFor={searchId}>Search tables
        <input id={searchId} type="search" value={search} disabled={disabled} maxLength={200}
          placeholder="Schema, table, System or description" onChange={(event) => setSearch(event.target.value)} />
      </label>
      {systems.length > 1 ? <label>System
        <select value={system} disabled={disabled} onChange={(event) => setSystem(event.target.value)}>
          <option value="">All Systems</option>
          {systems.map((code) => <option key={code} value={code}>{code}</option>)}
        </select>
      </label> : null}
      <fieldset className="subject-area-segments" disabled={disabled}>
        <legend className="sr-only">Show tables</legend>
        {([["all", "All"], ["unassigned", "Unassigned"], ["assigned", "In an area"]] as const).map(([value, label]) => (
          <label key={value} className={view === value ? "is-active" : ""}>
            <input type="radio" name={`${searchId}-view`} checked={view === value} onChange={() => setView(value)} />{label}
          </label>
        ))}
      </fieldset>
    </div>
    <div className="workflow-table-scroll subject-area-picker-scroll" tabIndex={0} role="region" aria-label="Scrollable Input Scope tables">
      <table aria-label="Input Scope tables">
        <thead><tr>
          <th><input type="checkbox" aria-label="Select all shown tables" disabled={disabled || !choosable.length}
            checked={allChosen} ref={(element) => { if (element) element.indeterminate = someChosen && !allChosen; }}
            onChange={(event) => {
              const next = new Set(selected);
              for (const table of choosable) {
                if (event.target.checked) next.add(table.object_id); else next.delete(table.object_id);
              }
              onChange(next);
            }} /></th>
          <th>Table</th><th>System</th><th className="is-numeric">Columns</th><th>Subject areas</th>
        </tr></thead>
        <tbody>{visible.map((table) => {
          const fixed = fixedIds?.has(table.object_id) === true;
          return <tr key={table.object_id} className={fixed ? "is-fixed" : undefined}>
            <td><input type="checkbox" aria-label={`Choose ${tableLabel(table)}`} disabled={disabled || fixed}
              checked={fixed || selected.has(table.object_id)}
              onChange={(event) => {
                const next = new Set(selected);
                if (event.target.checked) next.add(table.object_id); else next.delete(table.object_id);
                onChange(next);
              }} /></td>
            <th scope="row"><span className="subject-area-table-name">
              <strong>{table.object_name}</strong><small>{table.object_schema}</small>
            </span></th>
            <td>{table.system_code}</td>
            <td className="is-numeric">{table.column_count}</td>
            <td>{fixed ? <span className="status-badge is-neutral">{fixedLabel}</span>
              : <AreaChips memberships={table.areas} />}</td>
          </tr>;
        })}</tbody>
      </table>
      {!visible.length ? <p className="empty-state compact">No tables match this search.</p> : null}
    </div>
  </div>;
}

export function AreaChips({ memberships, exceptId }: { memberships: ScopeTable["areas"]; exceptId?: number }) {
  const shown = memberships.filter((item) => item.subject_area_id !== exceptId);
  if (!shown.length) return <span className="subject-area-muted">{exceptId ? "No other area" : "Unassigned"}</span>;
  return <span className="chip-list subject-area-chips">
    {shown.map((item) => <span key={item.subject_area_id}>{item.subject_area_name}</span>)}
  </span>;
}

export function saveError(error: Error, retryable: boolean): string {
  if (retryable) return "The save was not confirmed. Retry the same save safely.";
  if (error instanceof ApiError) {
    if (error.code === "subject_area_name_conflict") {
      return "Another Subject Area, possibly inactive, already uses this name. Choose another name or reactivate that area.";
    }
    if (error.code === "subject_area_table_unavailable") {
      return "Some tables are no longer in the active Bronze Input Scope. Close, refresh and choose again.";
    }
    if (error.code === "record_locked") return "Unlock the area or its tables before changing them.";
    if (error.code === "project_revision_conflict") return "The Project changed. Close and refresh before saving.";
    if (error.code === "tenant_workflow_conflict") return "A workflow is running for this Tenant. Save again when it finishes.";
    if (error.status === 403) return "Saving requires permission and your Tenant Lock.";
    if (error.status === 404) return "This Subject Area is no longer available. Close and refresh.";
  }
  return "The Subject Area could not be saved. Nothing was changed. Try again.";
}

/** Idempotent save that keeps its key until the outcome is known. */
export function useSubjectAreaSave({ api, tenantId, projectId, onSaved }: {
  api: SubjectAreaApi; tenantId: number; projectId: number;
  onSaved: (result: SaveSubjectAreaResult) => Promise<void>;
}) {
  const attempt = useRef<{ command: SaveSubjectAreaCommand; key: string } | null>(null);
  const mutation = useMutation({
    mutationFn: (submission: NonNullable<typeof attempt.current>) => api.saveSubjectArea(
      tenantId, projectId, submission.command, submission.key,
    ),
    onSuccess: async (result) => { attempt.current = null; await onSaved(result); },
    onError: (error) => {
      if (error instanceof ApiError && error.status < 500 && error.status !== 408) attempt.current = null;
    },
  });
  const retryable = mutation.isError && attempt.current !== null;
  return {
    mutation,
    retryable,
    busy: mutation.isPending || retryable,
    error: mutation.isError ? saveError(mutation.error, retryable) : null,
    submit: (command: SaveSubjectAreaCommand) => {
      if (!attempt.current) attempt.current = { command, key: crypto.randomUUID() };
      mutation.mutate(attempt.current);
    },
  };
}

function DialogFrame({ titleId, title, eyebrow, busy, onClose, wide = false, children }: {
  titleId: string; title: string; eyebrow?: string | undefined; busy: boolean; onClose: () => void; wide?: boolean; children: ReactNode;
}) {
  const close = useRef<HTMLButtonElement>(null);
  useDialogFocus(close);
  return <div className="dialog-scrim" role="presentation">
    <section className={`run-configuration-dialog subject-area-dialog${wide ? " is-wide" : ""}`} role="dialog" aria-modal="true"
      aria-labelledby={titleId} onKeyDown={(event) => { if (event.key === "Escape" && !busy) onClose(); trapDialogFocus(event); }}>
      <header className="drawer-header">
        <div>{eyebrow ? <small>{eyebrow}</small> : null}<h2 id={titleId}>{title}</h2></div>
        <button ref={close} className="panel-close" type="button" aria-label={`Close ${title}`} disabled={busy} onClick={onClose}>×</button>
      </header>
      {children}
    </section>
  </div>;
}

function useScopeTables(api: SubjectAreaApi, tenantId: number, projectId: number) {
  return useQuery({
    queryKey: subjectAreaQueryKeys.tables(tenantId, projectId),
    queryFn: () => api.listSubjectAreaScopeTables(tenantId, projectId),
  });
}

function ScopeTablesState({ query, projectRevision }: {
  query: ReturnType<typeof useScopeTables>; projectRevision: number;
}) {
  if (query.isPending) return <p className="surface-state compact" aria-busy="true">Loading Input Scope tables…</p>;
  if (query.isError) return <p className="inline-error" role="alert">Input Scope tables could not be loaded. Close and retry.</p>;
  if (query.data.project_revision !== projectRevision) {
    return <p className="inline-error" role="alert">The Project changed. Close and refresh before choosing tables.</p>;
  }
  if (!query.data.items.length) return <p className="empty-state compact">Add Bronze tables to the Project Input Scope first.</p>;
  return null;
}

/** Create an area, optionally with tables, or edit an area's name and definition. */
export function SubjectAreaEditorDialog({ api, tenantId, projectId, projectRevision, hasTenantLock, maxColumns, area, initialObjectIds = [], onClose, onSaved }: {
  api: SubjectAreaApi; tenantId: number; projectId: number; projectRevision: number; hasTenantLock: boolean;
  maxColumns: number; area?: SubjectAreaSummary; initialObjectIds?: number[];
  onClose: () => void; onSaved: (result: SaveSubjectAreaResult, saved: { name: string }) => Promise<void>;
}) {
  const creating = area === undefined;
  const [revision] = useState(projectRevision);
  const [name, setName] = useState(area?.subject_area_name ?? "");
  const [definition, setDefinition] = useState(area?.subject_area_definition ?? "");
  const [selected, setSelected] = useState(() => new Set(initialObjectIds));
  const tables = useScopeTables(api, tenantId, projectId);
  const save = useSubjectAreaSave({ api, tenantId, projectId, onSaved: async (result) => {
    await onSaved(result, { name: name.trim() }); onClose();
  } });
  const titleId = useId();
  const nameId = useId();
  const definitionId = useId();
  const trimmedName = name.trim();
  const trimmedDefinition = definition.trim();
  const nameChanged = !creating && trimmedName !== area.subject_area_name;
  const definitionChanged = !creating && trimmedDefinition !== area.subject_area_definition;
  const selectedColumns = (tables.data?.items ?? [])
    .filter((table) => selected.has(table.object_id))
    .reduce((total, table) => total + table.column_count, 0);
  const stale = revision !== projectRevision;
  const locked = area?.subject_area_is_locked === true;
  const ready = hasTenantLock && !stale && !locked && trimmedName.length > 0 && trimmedDefinition.length > 0
    && (creating ? (tables.isSuccess || selected.size === 0) : nameChanged || definitionChanged);
  return <DialogFrame titleId={titleId} title={creating ? "New Subject Area" : "Edit Subject Area"}
    eyebrow={creating ? undefined : area.subject_area_name} busy={save.busy} onClose={onClose} wide={creating}>
    <form className="subject-area-form" onSubmit={(event) => {
      event.preventDefault();
      if (save.retryable) { save.submit({ expected_project_revision: revision }); return; }
      if (!ready || save.busy) return;
      save.submit(creating ? {
        expected_project_revision: revision,
        subject_area_name: trimmedName,
        subject_area_definition: trimmedDefinition,
        add_object_ids: [...selected].sort((left, right) => left - right),
      } : {
        expected_project_revision: revision,
        subject_area_id: area.subject_area_id,
        ...(nameChanged ? { subject_area_name: trimmedName } : {}),
        ...(definitionChanged ? { subject_area_definition: trimmedDefinition } : {}),
      });
    }}>
      <fieldset className="subject-area-fields" disabled={save.busy || locked || stale}>
        <label htmlFor={nameId}>Name
          <input id={nameId} value={name} required maxLength={255} autoComplete="off"
            onChange={(event) => { setName(event.target.value); save.mutation.reset(); }} />
        </label>
        <label htmlFor={definitionId}>Definition
          <textarea id={definitionId} value={definition} required rows={3} maxLength={4000} aria-describedby={`${definitionId}-help`}
            onChange={(event) => { setDefinition(event.target.value); save.mutation.reset(); }} />
        </label>
        <small id={`${definitionId}-help`}>One or two sentences on the business capability the area covers and where it ends.</small>
      </fieldset>
      {nameChanged ? <p className="field-help">Renaming keeps the old name as an inactive area for history and moves its active tables to the new name.</p> : null}
      {creating ? <section className="subject-area-picker-section" aria-label="Tables">
        <header><h3>Tables</h3><ColumnMeter columns={selectedColumns} limit={maxColumns} /></header>
        <ScopeTablesState query={tables} projectRevision={revision} />
        {tables.data && tables.data.project_revision === revision && tables.data.items.length
          ? <ScopeTablePicker tables={tables.data.items} selected={selected} disabled={save.busy}
            onChange={(ids) => { setSelected(ids); save.mutation.reset(); }} /> : null}
        {selectedColumns > maxColumns ? <p className="subject-area-warning" role="status">
          Over the {maxColumns}-column limit. A Logical Build may not fit one answer; consider a narrower area.</p> : null}
      </section> : null}
      {locked ? <p role="alert">Unlock this Subject Area before editing it.</p> : null}
      {stale ? <p role="alert">The Project changed. Close and refresh before saving.</p> : null}
      {!hasTenantLock ? <p role="alert">Acquire the Tenant Lock before saving.</p> : null}
      {save.error ? <p className="inline-error" role="alert">{save.error}</p> : null}
      <footer className="subject-area-dialog-actions">
        {creating ? <span>{selected.size} table{selected.size === 1 ? "" : "s"} selected</span> : <span />}
        <div className="workflow-command-actions">
          <button className="button button-secondary" type="button" disabled={save.busy} onClick={onClose}>Cancel</button>
          <button className="button button-primary" type="submit" disabled={save.mutation.isPending || (!save.retryable && !ready)}>
            {save.mutation.isPending ? "Saving…" : save.retryable ? "Retry save" : creating ? "Create area" : "Save changes"}
          </button>
        </div>
      </footer>
    </form>
  </DialogFrame>;
}

/** Add Input Scope tables to one existing area. */
export function AddTablesDialog({ api, tenantId, projectId, projectRevision, hasTenantLock, maxColumns, area, memberIds, memberColumns, onClose, onSaved }: {
  api: SubjectAreaApi; tenantId: number; projectId: number; projectRevision: number; hasTenantLock: boolean;
  maxColumns: number; area: SubjectAreaSummary; memberIds: ReadonlySet<number>; memberColumns: number;
  onClose: () => void; onSaved: (result: SaveSubjectAreaResult) => Promise<void>;
}) {
  const [revision] = useState(projectRevision);
  const [selected, setSelected] = useState(() => new Set<number>());
  const tables = useScopeTables(api, tenantId, projectId);
  const save = useSubjectAreaSave({ api, tenantId, projectId, onSaved: async (result) => { await onSaved(result); onClose(); } });
  const titleId = useId();
  const added = (tables.data?.items ?? []).filter((table) => selected.has(table.object_id));
  const total = memberColumns + added.reduce((sum, table) => sum + table.column_count, 0);
  const stale = revision !== projectRevision;
  const ready = hasTenantLock && !stale && !area.subject_area_is_locked && selected.size > 0 && selected.size <= 5000;
  return <DialogFrame titleId={titleId} title="Add tables" eyebrow={area.subject_area_name} busy={save.busy} onClose={onClose} wide>
    <form className="subject-area-form" onSubmit={(event) => {
      event.preventDefault();
      if (save.retryable) { save.submit({ expected_project_revision: revision }); return; }
      if (!ready || save.busy) return;
      save.submit({
        expected_project_revision: revision,
        subject_area_id: area.subject_area_id,
        add_object_ids: [...selected].sort((left, right) => left - right),
      });
    }}>
      <section className="subject-area-picker-section" aria-label="Tables to add">
        <header><h3>Area columns after adding</h3><ColumnMeter columns={total} limit={maxColumns} /></header>
        <ScopeTablesState query={tables} projectRevision={revision} />
        {tables.data && tables.data.project_revision === revision && tables.data.items.length
          ? <ScopeTablePicker tables={tables.data.items} selected={selected} fixedIds={memberIds} disabled={save.busy}
            onChange={(ids) => { setSelected(ids); save.mutation.reset(); }} /> : null}
        {total > maxColumns ? <p className="subject-area-warning" role="status">
          Over the {maxColumns}-column limit. A Logical Build may not fit one answer; consider another area.</p> : null}
      </section>
      {area.subject_area_status !== "active" ? <p className="field-help">Adding tables makes this inactive area active again.</p> : null}
      {area.subject_area_is_locked ? <p role="alert">Unlock this Subject Area before adding tables.</p> : null}
      {stale ? <p role="alert">The Project changed. Close and refresh before saving.</p> : null}
      {!hasTenantLock ? <p role="alert">Acquire the Tenant Lock before saving.</p> : null}
      {save.error ? <p className="inline-error" role="alert">{save.error}</p> : null}
      <footer className="subject-area-dialog-actions">
        <span>{selected.size} table{selected.size === 1 ? "" : "s"} selected</span>
        <div className="workflow-command-actions">
          <button className="button button-secondary" type="button" disabled={save.busy} onClick={onClose}>Cancel</button>
          <button className="button button-primary" type="submit" disabled={save.mutation.isPending || (!save.retryable && !ready)}>
            {save.mutation.isPending ? "Adding…" : save.retryable ? "Retry save" : "Add tables"}
          </button>
        </div>
      </footer>
    </form>
  </DialogFrame>;
}

/** Put chosen unassigned tables into an existing area or a new one. */
export function AssignTablesDialog({ api, tenantId, projectId, projectRevision, hasTenantLock, maxColumns, areas, tables, onClose, onSaved }: {
  api: SubjectAreaApi; tenantId: number; projectId: number; projectRevision: number; hasTenantLock: boolean;
  maxColumns: number; areas: SubjectAreaSummary[]; tables: ScopeTable[];
  onClose: () => void; onSaved: (result: SaveSubjectAreaResult) => Promise<void>;
}) {
  const [revision] = useState(projectRevision);
  const choices = areas.filter((area) => area.subject_area_status === "active" && !area.subject_area_is_locked);
  const [target, setTarget] = useState<number | "new">(choices[0]?.subject_area_id ?? "new");
  const [name, setName] = useState("");
  const [definition, setDefinition] = useState("");
  const save = useSubjectAreaSave({ api, tenantId, projectId, onSaved: async (result) => { await onSaved(result); onClose(); } });
  const titleId = useId();
  const areaId = useId();
  const nameId = useId();
  const definitionId = useId();
  const addedColumns = tables.reduce((total, table) => total + table.column_count, 0);
  const chosen = target === "new" ? undefined : choices.find((area) => area.subject_area_id === target);
  const total = addedColumns + (chosen?.column_count ?? 0);
  const stale = revision !== projectRevision;
  const ready = hasTenantLock && !stale && tables.length > 0
    && (target === "new" ? name.trim().length > 0 && definition.trim().length > 0 : chosen !== undefined);
  const objectIds = tables.map((table) => table.object_id).sort((left, right) => left - right);
  return <DialogFrame titleId={titleId} title="Add to Subject Area" eyebrow={`${tables.length} table${tables.length === 1 ? "" : "s"}`}
    busy={save.busy} onClose={onClose}>
    <form className="subject-area-form" onSubmit={(event) => {
      event.preventDefault();
      if (save.retryable) { save.submit({ expected_project_revision: revision }); return; }
      if (!ready || save.busy) return;
      save.submit(target === "new" ? {
        expected_project_revision: revision,
        subject_area_name: name.trim(),
        subject_area_definition: definition.trim(),
        add_object_ids: objectIds,
      } : { expected_project_revision: revision, subject_area_id: target, add_object_ids: objectIds });
    }}>
      <fieldset className="subject-area-fields" disabled={save.busy || stale}>
        <label htmlFor={areaId}>Subject Area
          <select id={areaId} value={String(target)} onChange={(event) => {
            setTarget(event.target.value === "new" ? "new" : Number(event.target.value)); save.mutation.reset();
          }}>
            {choices.map((area) => <option key={area.subject_area_id} value={area.subject_area_id}>
              {area.subject_area_name} ({area.column_count} columns)
            </option>)}
            <option value="new">New Subject Area…</option>
          </select>
        </label>
        {target === "new" ? <>
          <label htmlFor={nameId}>Name
            <input id={nameId} value={name} required maxLength={255} autoComplete="off"
              onChange={(event) => { setName(event.target.value); save.mutation.reset(); }} />
          </label>
          <label htmlFor={definitionId}>Definition
            <textarea id={definitionId} value={definition} required rows={3} maxLength={4000}
              onChange={(event) => { setDefinition(event.target.value); save.mutation.reset(); }} />
          </label>
        </> : null}
      </fieldset>
      <div className="subject-area-assign-summary">
        <span>Area columns after adding</span><ColumnMeter columns={total} limit={maxColumns} />
      </div>
      <ul className="subject-area-assign-list" aria-label="Tables to add">
        {tables.map((table) => <li key={table.object_id}><strong>{table.object_name}</strong>
          <small>{table.object_schema} · {table.system_code} · {table.column_count} columns</small></li>)}
      </ul>
      {total > maxColumns ? <p className="subject-area-warning" role="status">
        Over the {maxColumns}-column limit. A Logical Build may not fit one answer; consider another area.</p> : null}
      {stale ? <p role="alert">The Project changed. Close and refresh before saving.</p> : null}
      {!hasTenantLock ? <p role="alert">Acquire the Tenant Lock before saving.</p> : null}
      {save.error ? <p className="inline-error" role="alert">{save.error}</p> : null}
      <footer className="subject-area-dialog-actions">
        <span />
        <div className="workflow-command-actions">
          <button className="button button-secondary" type="button" disabled={save.busy} onClick={onClose}>Cancel</button>
          <button className="button button-primary" type="submit" disabled={save.mutation.isPending || (!save.retryable && !ready)}>
            {save.mutation.isPending ? "Saving…" : save.retryable ? "Retry save" : target === "new" ? "Create area" : "Add tables"}
          </button>
        </div>
      </footer>
    </form>
  </DialogFrame>;
}
