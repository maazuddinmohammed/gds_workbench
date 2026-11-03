import { useState, type ReactNode } from "react";
import { Link } from "@tanstack/react-router";
import type { ContextGroup, ContextGroupFilters, ContextRecord, ContextRecordFilters, ContextSourceSystem, ContextType } from "./api";
import { formatRequiredDateTime as formatDateTime } from "../../shared/presentation";
import { WorkflowFilters } from "../workflows/WorkflowCommandCenter";

export interface ContextLedgerState {
  isLoading: boolean; isError: boolean; revisionMismatch: boolean; hasMore: boolean; isLoadingMore: boolean;
}
export function ContextGroupsLedger({ tenantId, projectId, items, filters, types, systems, choicesUnavailable, state, onApplyFilters, onLoadMore }: {
  tenantId: number; projectId: number; items: ContextGroup[]; filters: ContextGroupFilters;
  types: ContextType[]; systems: ContextSourceSystem[]; choicesUnavailable: boolean;
  state: ContextLedgerState; onApplyFilters: (filters: ContextGroupFilters) => void; onLoadMore: () => void;
}) {
  const [values, setValues] = useState({ namePrefix: filters.namePrefix ?? "", contextTypeId: String(filters.contextTypeId ?? ""), sourceSystemId: String(filters.sourceSystemId ?? ""), active: filters.active === undefined ? "" : String(filters.active) });
  return <>
    <WorkflowFilters><form className="workflow-filterbar context-group-filterbar" aria-label="Filter Context groups" onSubmit={(event) => {
      event.preventDefault();
      onApplyFilters({ ...(values.namePrefix ? { namePrefix: values.namePrefix } : {}), ...(values.contextTypeId ? { contextTypeId: Number(values.contextTypeId) } : {}), ...(values.sourceSystemId ? { sourceSystemId: Number(values.sourceSystemId) } : {}), ...(values.active ? { active: values.active === "true" } : {}) });
    }}>
      <label><span>Context Group Name prefix</span><input value={values.namePrefix} onChange={(event) => setValues({ ...values, namePrefix: event.target.value })} /></label>
      <label><span>Context type</span><select value={values.contextTypeId} onChange={(event) => setValues({ ...values, contextTypeId: event.target.value })}><option value="">All types</option>{types.map((type) => <option key={type.context_type_id} value={type.context_type_id}>{type.context_type_name}</option>)}</select></label>
      <label><span>Source System</span><select value={values.sourceSystemId} onChange={(event) => setValues({ ...values, sourceSystemId: event.target.value })}><option value="">All Systems</option>{systems.map((system) => <option key={system.system_id} value={system.system_id}>{system.system_code}</option>)}</select></label>
      <label><span>Group activity</span><select value={values.active} onChange={(event) => setValues({ ...values, active: event.target.value })}><option value="">All activity states</option><option value="true">Active</option><option value="false">Inactive</option></select></label>
      {choicesUnavailable ? <p className="field-help">Some filter choices are unavailable. Refresh to reload them.</p> : null}
      <div className="workflow-filter-actions"><button className="button button-primary button-small" type="submit">Apply Group filters</button><button className="button button-secondary button-small" type="button" onClick={() => { setValues({ namePrefix: "", contextTypeId: "", sourceSystemId: "", active: "" }); onApplyFilters({}); }}>Clear filters</button></div>
    </form></WorkflowFilters>
    <ContextLedgerSurface label="Context groups" state={state} count={items.length} onLoadMore={onLoadMore} emptyMessage={Object.values(filters).some((value) => value !== undefined && value !== "") ? "No Context groups match these filters." : "No Context groups yet. Create a group to organize requirements, decisions, and other information."}>
      <table aria-label="Context groups"><thead><tr><th>Context Group Name</th><th>Type</th><th>Source System</th><th>Records</th><th>Locked</th><th>Status</th><th>Updated</th><th>Actions</th></tr></thead><tbody>
        {items.map((group) => <tr key={group.context_group_id}>
          <td>{group.context_group_name}</td><td>{group.context_type.context_type_name}</td><td>{group.source_system?.system_code ?? "Entire Project"}</td><td>{group.record_count}</td><td>{group.locked_record_count}</td><td><span className={`status-badge ${group.is_active ? "is-success" : "is-neutral"}`}>{group.is_active ? "Active" : "Inactive"}</span></td><td>{formatDateTime(group.updated_at)}</td>
          <td><Link className="text-action" aria-label={`View records in ${group.context_group_name}`} to="/tenants/$tenantId/projects/$projectId/context/groups/$groupId" params={{ tenantId: String(tenantId), projectId: String(projectId), groupId: String(group.context_group_id) }}>View records</Link></td>
        </tr>)}
      </tbody></table>
    </ContextLedgerSurface>
  </>;
}
export function ContextRecordsLedger({ tenantId, projectId, items, filters, state, selectedIds, onSelectionChange, onEdit, editingDisabledReason, selectionDisabled, onApplyFilters, onLoadMore }: {
  tenantId: number; projectId: number; items: ContextRecord[]; filters: ContextRecordFilters; state: ContextLedgerState;
  selectedIds: Set<string>; onSelectionChange: (ids: Set<string>) => void; onEdit: (recordId: string) => void;
  editingDisabledReason?: string | undefined; selectionDisabled: boolean;
  onApplyFilters: (filters: ContextRecordFilters) => void; onLoadMore: () => void;
}) {
  const [values, setValues] = useState({ textSearch: filters.textSearch ?? "", status: filters.status ?? "", locked: filters.locked === undefined ? "" : String(filters.locked) });
  return <>
    <WorkflowFilters><form className="workflow-filterbar context-record-filterbar" aria-label="Filter Context records" onSubmit={(event) => {
      event.preventDefault(); onApplyFilters({ ...(values.textSearch ? { textSearch: values.textSearch } : {}), ...(values.status ? { status: values.status as NonNullable<ContextRecordFilters["status"]> } : {}), ...(values.locked ? { locked: values.locked === "true" } : {}) });
    }}>
      <label><span>Search context</span><input value={values.textSearch} onChange={(event) => setValues({ ...values, textSearch: event.target.value })} /></label>
      <label><span>Record status</span><select value={values.status} onChange={(event) => setValues({ ...values, status: event.target.value })}><option value="">All statuses</option><option value="active">Active</option><option value="inactive">Inactive</option><option value="deprecated">Deprecated</option></select></label>
      <label><span>Record lock</span><select value={values.locked} onChange={(event) => setValues({ ...values, locked: event.target.value })}><option value="">All locks</option><option value="true">Locked</option><option value="false">Open</option></select></label>
      <div className="workflow-filter-actions"><button className="button button-primary button-small" type="submit">Apply Record filters</button><button className="button button-secondary button-small" type="button" onClick={() => { setValues({ textSearch: "", status: "", locked: "" }); onApplyFilters({}); }}>Clear filters</button></div>
    </form></WorkflowFilters>
    <ContextLedgerSurface label="Context records" state={state} count={items.length} onLoadMore={onLoadMore} emptyMessage={Object.values(filters).some((value) => value !== undefined && value !== "") ? "No Context records match these filters." : "No Context records yet. Use Add record to capture information in this group."}>
      <table className="context-records-table" aria-label="Context records"><thead><tr><th><input className="project-review-checkbox" type="checkbox" aria-label="Select loaded Context records" disabled={selectionDisabled} checked={items.length > 0 && items.every((item) => selectedIds.has(item.context_record_id))} ref={(input) => { if (input) input.indeterminate = items.some((item) => selectedIds.has(item.context_record_id)) && !items.every((item) => selectedIds.has(item.context_record_id)); }} onChange={(event) => onSelectionChange(event.target.checked ? new Set(items.map((item) => item.context_record_id)) : new Set())} /></th><th>Context Record Text</th><th>Source reference</th><th>Status</th><th>Lock</th><th>Updated</th><th>Actions</th></tr></thead><tbody>
        {items.map((record) => <tr key={record.context_record_id}>
          <td><input className="project-review-checkbox" type="checkbox" aria-label={`Select ${record.context_text_preview}`} disabled={selectionDisabled} checked={selectedIds.has(record.context_record_id)} onChange={(event) => { const next = new Set(selectedIds); if (event.target.checked) next.add(record.context_record_id); else next.delete(record.context_record_id); onSelectionChange(next); }} /></td>
          <td className="context-record-text">{record.context_text_preview}{record.text_truncated ? "…" : ""}{record.text_truncated || record.source_reference_truncated ? <Link className="text-action context-full-text" to="/tenants/$tenantId/projects/$projectId/context/records/$recordId" params={{ tenantId: String(tenantId), projectId: String(projectId), recordId: record.context_record_id }}>Read full text</Link> : null}</td>
          <td className="context-source-reference">{record.source_reference_preview ?? "—"}{record.source_reference_truncated ? "…" : ""}</td><td>{record.status.charAt(0).toUpperCase() + record.status.slice(1)}</td><td>{record.is_locked ? "Locked" : "Open"}</td><td>{formatDateTime(record.updated_at)}</td>
          <td><button className="text-action" type="button" aria-label={`Edit ${record.context_text_preview}`} disabled={Boolean(editingDisabledReason) || record.is_locked || selectionDisabled} title={editingDisabledReason ?? (record.is_locked ? "Unlock this record before editing." : undefined)} onClick={() => onEdit(record.context_record_id)}>Edit</button></td>
        </tr>)}
      </tbody></table>
    </ContextLedgerSurface>
  </>;
}
function ContextLedgerSurface({ label, state, count, onLoadMore, children, emptyMessage }: { label: string; state: ContextLedgerState; count: number; onLoadMore: () => void; children: ReactNode; emptyMessage: string }) {
  if (state.isLoading) return <div className="surface-state" aria-busy="true">Loading {label}…</div>;
  if (state.isError) return <div className="surface-state is-error" role="alert">{label} could not be loaded. Refresh to retry.</div>;
  if (state.revisionMismatch) return <div className="surface-state is-error" role="alert">The Project changed while {label} were loading. Refresh to reconcile revisions.</div>;
  if (!count) return <p className="empty-state compact">{emptyMessage}</p>;
  return <><div className="workflow-table-scroll table-scroll ledger-grid" role="region" aria-label={`${label} table`} tabIndex={0}>{children}</div>{state.hasMore ? <div className="ledger-pagination"><button className="button button-secondary button-small" type="button" disabled={state.isLoadingMore} onClick={onLoadMore}>{state.isLoadingMore ? "Loading…" : "Load more"}</button></div> : null}</>;
}
