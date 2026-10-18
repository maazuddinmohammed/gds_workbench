import { useState } from "react";
import { Link } from "@tanstack/react-router";
import { useInfiniteQuery, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { contextQueryKeys, type ContextApi, type ContextRecordFilters } from "./api";
import { ContextEditor } from "./ContextEditor";
import { ContextRecordsLedger } from "./ContextLedgers";
import { ProjectRecordReview } from "../project_record_review/ProjectRecordReview";
import { WorkflowCommandCenter, WorkflowCommandTools, WorkflowMenu } from "../workflows/WorkflowCommandCenter";
import { Fact, WorkspaceToolbar } from "../../shared/ui";
import { formatRequiredDateTime as formatDateTime } from "../../shared/presentation";

type DetailProps = { api: ContextApi; tenantId: number; projectId: number; projectRevision: number; hasTenantLock: boolean; authoringDisabledReason?: string | undefined };
export function ContextGroupDetailPage({ api, tenantId, projectId, groupId, projectRevision, hasTenantLock, authoringDisabledReason }: DetailProps & { groupId: number }) {
  const [editor, setEditor] = useState<"group" | "record" | { recordId: string } | null>(null);
  const [selectedIds, setSelectedIds] = useState<Set<string>>(new Set());
  const [filters, setFilters] = useState<ContextRecordFilters>({});
  const queryClient = useQueryClient();
  const query = useQuery({ queryKey: contextQueryKeys.group(tenantId, projectId, groupId), queryFn: () => api.readContextGroup(tenantId, projectId, groupId) });
  const scopedFilters = { ...filters, groupId };
  const records = useInfiniteQuery({
    queryKey: contextQueryKeys.records(tenantId, projectId, scopedFilters),
    queryFn: ({ pageParam }) => api.listContextRecords(tenantId, projectId, scopedFilters, 200, pageParam),
    initialPageParam: undefined as string | undefined, getNextPageParam: (page) => page.next_cursor ?? undefined, enabled: query.isSuccess,
  });
  const editingRecordId = typeof editor === "object" ? editor?.recordId : undefined;
  // Load a fresh edit snapshot once; background reads must not replace a dirty form.
  const editingRecord = useMutation({
    mutationFn: (recordId: string) => api.readContextRecord(tenantId, projectId, recordId),
    retry: false,
  });
  const saved = async () => {
    setSelectedIds(new Set());
    await Promise.all([queryClient.invalidateQueries({ queryKey: ["project", tenantId, projectId] }), queryClient.invalidateQueries({ predicate: ({ queryKey }) => typeof queryKey[0] === "string" && queryKey[0].startsWith("context-") && queryKey[1] === tenantId && queryKey[2] === projectId })]);
  };
  if (query.isPending) return <div className="surface-state" aria-busy="true">Loading Context group…</div>;
  if (query.isError) return <div className="surface-state is-error" role="alert">Context group details could not be loaded. <button className="text-action" type="button" onClick={() => void query.refetch()}>Retry</button></div>;
  const group = query.data;
  const editBlockedReason = !hasTenantLock ? authoringDisabledReason ?? "Tenant Lock required to change Context." : group.locked_record_count > 0 ? "Unlock this group's records before changing its settings." : undefined;
  const addBlockedReason = !hasTenantLock ? authoringDisabledReason ?? "Tenant Lock required to change Context." : !group.is_active ? "Activate this group before adding records." : undefined;
  const revisionMismatch = records.data?.pages.some((page) => page.project_revision !== projectRevision) ?? false;
  return <article className="context-page page-enter"><WorkflowCommandCenter className="context-records-workspace" filterCount={Object.values(filters).filter((value) => value !== undefined && value !== "").length}>
    <WorkspaceToolbar actions={<><WorkflowCommandTools />
      <button className="button button-primary button-small" type="button" disabled={Boolean(addBlockedReason) || query.isFetching} title={addBlockedReason} onClick={() => setEditor("record")}>Add record</button>
      <WorkflowMenu><button className="button button-secondary button-small" type="button" disabled={Boolean(editBlockedReason) || query.isFetching} title={editBlockedReason} onClick={() => setEditor("group")}>Edit group</button>
      <button className="button button-secondary button-small" type="button" onClick={async () => { setSelectedIds(new Set()); await Promise.all([query.refetch(), records.refetch(), queryClient.invalidateQueries({ queryKey: ["project", tenantId, projectId] }), queryClient.invalidateQueries({ queryKey: ["tenant-home", tenantId] })]); }}>Refresh</button>
      </WorkflowMenu></>}><div className="workspace-record-heading">
      <Link className="text-action" to="/tenants/$tenantId/projects/$projectId/context" params={{ tenantId: String(tenantId), projectId: String(projectId) }}>← Context groups</Link>
      <h1>{group.context_group_name}</h1><p>{group.context_type.context_type_name} · {group.source_system?.system_code ?? "Entire Project"} · {group.is_active ? "Active" : "Inactive"}</p>
    </div></WorkspaceToolbar>
    {editBlockedReason ? <p className="workspace-view-context">{editBlockedReason}</p> : null}
    {addBlockedReason && addBlockedReason !== editBlockedReason ? <p className="workspace-view-context">{addBlockedReason}</p> : null}
    {editor === "group" ? <ContextEditor kind="group" api={api} tenantId={tenantId} projectId={projectId} projectRevision={projectRevision} hasTenantLock={hasTenantLock} authoringDisabledReason={authoringDisabledReason} group={group} onClose={() => setEditor(null)} onSaved={saved} /> : editor === "record" ? <ContextEditor kind="record" api={api} tenantId={tenantId} projectId={projectId} projectRevision={projectRevision} hasTenantLock={hasTenantLock} authoringDisabledReason={authoringDisabledReason} group={group} onClose={() => setEditor(null)} onSaved={saved} /> : null}
    {editingRecordId && editingRecord.isPending ? <p role="status">Loading record for editing…</p> : null}
    {editingRecordId && editingRecord.isError ? <p role="alert">The record could not be loaded. <button className="text-action" type="button" onClick={() => editingRecord.mutate(editingRecordId)}>Retry record</button> <button className="text-action" type="button" onClick={() => setEditor(null)}>Cancel edit</button></p> : null}
    {editingRecordId && editingRecord.isSuccess ? <ContextEditor key={editingRecordId} kind="record" api={api} tenantId={tenantId} projectId={projectId} projectRevision={projectRevision} hasTenantLock={hasTenantLock} authoringDisabledReason={authoringDisabledReason} group={editingRecord.data.group} record={editingRecord.data} onClose={() => setEditor(null)} onSaved={saved} /> : null}
    <ProjectRecordReview api={api} tenantId={tenantId} projectId={projectId} projectRevision={projectRevision} dataset="context_record" selectedIds={selectedIds} hasTenantLock={hasTenantLock} disabled={records.isFetching || records.isError || revisionMismatch} onApplied={saved} />
    <ContextRecordsLedger key={JSON.stringify(scopedFilters)} tenantId={tenantId} projectId={projectId} items={records.data?.pages.flatMap((page) => page.items) ?? []} filters={filters} selectedIds={selectedIds} onSelectionChange={setSelectedIds} onEdit={(recordId) => { setEditor({ recordId }); editingRecord.reset(); editingRecord.mutate(recordId); }} editingDisabledReason={addBlockedReason} selectionDisabled={!hasTenantLock || records.isFetching || revisionMismatch} state={{ isLoading: records.isPending, isError: records.isError, revisionMismatch, hasMore: records.hasNextPage, isLoadingMore: records.isFetchingNextPage }} onApplyFilters={(next) => { setSelectedIds(new Set()); setFilters(next); }} onLoadMore={() => { void records.fetchNextPage(); }} />
    <details className="detail-section detail-disclosure"><summary><h2>Group details</h2></summary>
      {group.context_group_description ? <dl className="workspace-detail-facts"><Fact label="Context Group Description" value={group.context_group_description} /></dl> : null}
      <dl className="detail-fact-grid"><Fact label="Type" value={group.context_type.context_type_name} /><Fact label="Source System" value={group.source_system?.system_code ?? "Entire Project"} /><Fact label="Updated" value={formatDateTime(group.updated_at)} /></dl>
    </details>
  </WorkflowCommandCenter></article>;
}
export function ContextRecordDetailPage({ api, tenantId, projectId, recordId, projectRevision, hasTenantLock, authoringDisabledReason }: DetailProps & { recordId: string }) {
  const [editing, setEditing] = useState(false);
  const queryClient = useQueryClient();
  const query = useQuery({ queryKey: contextQueryKeys.record(tenantId, projectId, recordId), queryFn: () => api.readContextRecord(tenantId, projectId, recordId) });
  const saved = async () => {
    await Promise.all([queryClient.invalidateQueries({ queryKey: ["project", tenantId, projectId] }), queryClient.invalidateQueries({ predicate: ({ queryKey }) => typeof queryKey[0] === "string" && queryKey[0].startsWith("context-") && queryKey[1] === tenantId && queryKey[2] === projectId })]);
  };
  if (query.isPending) return <div className="surface-state" aria-busy="true">Loading Context record…</div>;
  if (query.isError) return <div className="surface-state is-error" role="alert">Context record details could not be loaded. <button className="text-action" type="button" onClick={() => void query.refetch()}>Retry</button></div>;
  const record = query.data;
  const editBlockedReason = !hasTenantLock ? authoringDisabledReason ?? "Tenant Lock required to change Context." : record.is_locked ? "Unlock this record before editing." : !record.group.is_active ? "Activate this group before editing its records." : undefined;
  return <article className="workflow-detail-page context-detail-page page-enter">
    <WorkspaceToolbar actions={<>
      <button className="button button-primary button-small" type="button" disabled={Boolean(editBlockedReason) || query.isFetching} title={editBlockedReason} onClick={() => setEditing(true)}>Edit record</button>
      <ProjectRecordReview api={api} tenantId={tenantId} projectId={projectId} projectRevision={projectRevision} dataset="context_record" selectedIds={new Set([recordId])} hasTenantLock={hasTenantLock} disabled={query.isFetching} onApplied={saved}
        presentation="record" actions={[record.is_locked ? "unlock" : "lock", record.status === "active" ? "deactivate" : "reactivate"]}
        menuActions={<button className="button button-secondary button-small" type="button" disabled={query.isFetching} onClick={async () => { await Promise.all([query.refetch(), queryClient.invalidateQueries({ queryKey: ["project", tenantId, projectId] }), queryClient.invalidateQueries({ queryKey: ["tenant-home", tenantId] })]); }}>Refresh</button>} />
    </>}><div className="workspace-record-heading">
      <Link className="text-action" to="/tenants/$tenantId/projects/$projectId/context/groups/$groupId" params={{ tenantId: String(tenantId), projectId: String(projectId), groupId: String(record.group.context_group_id) }}>← {record.group.context_group_name}</Link>
      <h1>Context record</h1><p>{record.group.context_type.context_type_name}</p>
    </div></WorkspaceToolbar>
    {editBlockedReason ? <p className="workspace-view-context">{editBlockedReason}</p> : null}
    {editing ? <ContextEditor kind="record" api={api} tenantId={tenantId} projectId={projectId} projectRevision={projectRevision} hasTenantLock={hasTenantLock} authoringDisabledReason={authoringDisabledReason} group={record.group} record={record} onClose={() => setEditing(false)} onSaved={saved} /> : null}
    <div className="workspace-record-table" role="region" aria-label="Context record details" tabIndex={0}>
      <table aria-label="Context record details"><tbody>
        <tr><th scope="row">Context Record Text</th><td>{record.context_text}</td></tr>
        <tr><th scope="row">Source reference</th><td>{record.source_reference ?? "—"}</td></tr>
        <tr><th scope="row">Status</th><td>{record.status.charAt(0).toUpperCase() + record.status.slice(1)}</td></tr>
        <tr><th scope="row">Lock</th><td>{record.is_locked ? "Locked" : "Open"}</td></tr>
        <tr><th scope="row">Updated</th><td>{formatDateTime(record.updated_at)}</td></tr>
      </tbody></table>
    </div>
  </article>;
}
