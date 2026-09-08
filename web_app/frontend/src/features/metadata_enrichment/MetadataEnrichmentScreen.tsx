import { Fragment, useEffect, useRef, useState } from "react";
import { useInfiniteQuery, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { ApiError } from "../../core/http";
import { formatRequiredDateTime, zoneLabel } from "../../shared/presentation";
import type { ModelDetail } from "../models/api";
import type { ModelInputScopeApi, ModelInputScopeObject } from "../model_input_scope/api";
import type { MetadataApi, ObjectAttribute, ReviewMetadataRecordsCommand } from "../metadata/api";
import { WorkflowRunDialog } from "../workflows/WorkflowRunDialog";
import { WorkflowTokenUsage } from "../workflows/WorkflowTokenUsage";
import { RunStateBadge } from "../workflows/presentation";
import { workflowRunQueryKeys, type WorkflowCreationApi, type WorkflowRunMonitorApi } from "../workflows/api";
import type { MetadataEnrichmentTransport } from "./api";

type EnrichmentApi = WorkflowCreationApi & WorkflowRunMonitorApi & MetadataEnrichmentTransport
  & Pick<ModelInputScopeApi, "listModelInputScope" | "readModelInputScopeObject">
  & Pick<MetadataApi, "reviewMetadataRecords">;
type DescriptionRecord = { type: "object" | "attribute"; id: number; objectId: number; name: string; description: string | null; revision: string; truncated: boolean };
type ReviewRequest = { command: ReviewMetadataRecordsCommand; key: string };

export function MetadataEnrichmentScreen({ api, tenantId, model, hasTenantLock }: {
  api: EnrichmentApi; tenantId: number; model: ModelDetail; hasTenantLock: boolean;
}) {
  const client = useQueryClient();
  const [runDialog, setRunDialog] = useState<"object" | "attribute" | null>(null);
  const [selectedIds, setSelectedIds] = useState<Set<number>>(new Set());
  const [recentRunId, setRecentRunId] = useState<number | null>(null);
  const [objectId, setObjectId] = useState<number | null>(null);
  const [attributePage, setAttributePage] = useState(0);
  const [editor, setEditor] = useState<DescriptionRecord | null>(null);
  const [search, setSearch] = useState("");
  const [objectFilter, setObjectFilter] = useState("");
  const [notice, setNotice] = useState("");
  const [refreshRequired, setRefreshRequired] = useState(false);
  const pendingReview = useRef<ReviewRequest | null>(null);
  const heading = useRef<HTMLHeadingElement>(null);
  const editTrigger = useRef<HTMLElement | null>(null);
  const returnObject = useRef<number | null>(null);
  const objects = useInfiniteQuery({
    queryKey: ["model-input-scope", tenantId, model.model_id, { objectName: objectFilter }],
    queryFn: ({ pageParam }) => api.listModelInputScope(tenantId, model.model_id, { objectName: objectFilter }, 200, pageParam),
    initialPageParam: undefined as string | undefined,
    getNextPageParam: (page) => page.next_cursor ?? undefined,
  });
  const detail = useQuery({
    queryKey: ["model-input-scope-object", tenantId, model.model_id, objectId],
    queryFn: () => api.readModelInputScopeObject(tenantId, model.model_id, objectId!), enabled: objectId !== null,
  });
  const refreshMetadata = async () => {
    await Promise.all(["model-input-scope", "model-input-scope-object", "metadata-object", "metadata-objects", "metadata-rows", "workflow-run-enrichment-scope"]
      .map((prefix) => client.invalidateQueries({ queryKey: [prefix, tenantId] })));
  };
  const review = useMutation({
    mutationFn: async (request: ReviewRequest) => {
      const receipt = await api.reviewMetadataRecords(tenantId, request.command, request.key);
      const expected = new Set(request.command.records.map((item) => item.record_id));
      if (receipt.records.length !== expected.size || new Set(receipt.records.map((item) => item.record_id)).size !== expected.size
        || receipt.records.some((item) => !expected.has(item.record_id) || !/^[0-9a-f]{64}$/.test(item.review_revision))) throw new Error("Outcome unconfirmed");
      return receipt;
    },
    onSuccess: async () => {
      pendingReview.current = null; setEditor(null); setSelectedIds(new Set()); setNotice("Metadata saved.");
      await refreshMetadata();
    },
    onError: (error) => {
      if (error instanceof ApiError && error.status < 500 && error.status !== 408) {
        pendingReview.current = null; setRefreshRequired(true);
      }
    },
  });
  const uncertain = review.isError && pendingReview.current !== null;
  const busy = review.isPending || uncertain;
  const changed = objects.data?.pages.some((page) => page.model_revision !== model.model_revision) ?? false;
  const current = !detail.isError && detail.data?.object_id === objectId ? detail.data : undefined;
  const rows = objects.isError || changed ? [] : objects.data?.pages.flatMap((page) => page.items) ?? [];
  const submitReview = (command: ReviewMetadataRecordsCommand) => {
    if (busy || !hasTenantLock || refreshRequired) return;
    setNotice(""); pendingReview.current = { command, key: crypto.randomUUID() }; review.mutate(pendingReview.current);
  };
  const refresh = async () => {
    if (busy) return;
    await refreshMetadata(); setSelectedIds(new Set()); review.reset(); setRefreshRequired(false); setNotice("");
  };
  useEffect(() => {
    setAttributePage(0); setSelectedIds(new Set());
    if (objectId !== null) heading.current?.focus();
    else if (returnObject.current !== null) document.getElementById(`enrichment-object-${returnObject.current}`)?.focus();
  }, [objectId]);
  useEffect(() => {
    if (!editor && !review.isPending && !objects.isFetching && !detail.isFetching && editTrigger.current) {
      editTrigger.current.focus(); editTrigger.current = null;
    }
  }, [editor, review.isPending, objects.isFetching, detail.isFetching]);
  const recordActions = (object: ModelInputScopeObject, attribute?: ObjectAttribute) => {
    const record: DescriptionRecord = { type: attribute ? "attribute" : "object", id: attribute?.attribute_id ?? object.object_id,
      objectId: object.object_id, name: attribute?.attribute_name ?? object.object_name,
      description: attribute ? attribute.attribute_description : object.object_description ?? null,
      revision: (attribute ? attribute.review_revision : object.review_revision) ?? "",
      truncated: (attribute ? attribute.description_truncated : object.description_truncated) ?? false };
    const locked = attribute?.is_locked ?? object.is_locked ?? false;
    const unavailable = busy || refreshRequired || changed || !hasTenantLock || object.source_tenant_id !== tenantId
      || !/^[0-9a-f]{64}$/.test(record.revision) || objects.isFetching || objects.isError
      || (attribute !== undefined && (detail.isFetching || detail.isError || !attribute.is_active || object.is_locked === true));
    const reason = object.source_tenant_id !== tenantId ? "Manage this metadata in its owning Tenant" : !hasTenantLock ? "Owned Tenant Lock required"
      : attribute && object.is_locked ? "Unlock the parent Object first" : locked ? "Locked in Metadata" : undefined;
    return <div className="enrichment-record-actions" aria-label={`Actions for ${record.name}`}>
      <button type="button" className="text-action" disabled={unavailable || locked} title={reason} onClick={(event) => { editTrigger.current = event.currentTarget; review.reset(); setEditor(record); }}>Edit</button>
    </div>;
  };
  const selectable = objectId === null
    ? rows.filter((item) => item.source_tenant_id === tenantId && /^[0-9a-f]{64}$/.test(item.review_revision ?? ""))
      .map((item) => ({ id: item.object_id, revision: item.review_revision!, locked: item.is_locked ?? false }))
    : !current || current.is_locked || current.source_tenant_id !== tenantId ? [] : current.attributes.slice(attributePage * 50, (attributePage + 1) * 50)
      .filter((item) => item.is_active && /^[0-9a-f]{64}$/.test(item.review_revision ?? ""))
      .map((item) => ({ id: item.attribute_id, revision: item.review_revision!, locked: item.is_locked }));
  const selected = selectable.filter((item) => selectedIds.has(item.id));
  const selectionBusy = busy || refreshRequired || changed || !hasTenantLock || objects.isFetching || detail.isFetching;
  const checkbox = (id?: number) => <input type="checkbox" aria-label={id === undefined ? "Select all visible records" : `Select ${objectId === null ? "Object" : "Attribute"} ${id}`}
    disabled={selectionBusy || (id === undefined ? !selectable.length : !selectable.some((item) => item.id === id))}
    checked={id === undefined ? selectable.length > 0 && selectable.every((item) => selectedIds.has(item.id)) : selectedIds.has(id)}
    onChange={(event) => setSelectedIds((old) => { const next = new Set(old); for (const key of id === undefined ? selectable.map((item) => item.id) : [id]) { if (event.target.checked) next.add(key); else next.delete(key); } return next; })} />;
  const lockControls = <div className="enrichment-bulk-actions"><span>{selected.length ? `${selected.length} selected` : ""}</span>{(["lock", "unlock"] as const).map((action) => {
    const records = selected.filter((item) => item.locked === (action === "unlock"));
    return <button key={action} type="button" className="button button-secondary button-small" disabled={selectionBusy || !records.length || records.length > 200} title={records.length > 200 ? "Select up to 200 records" : undefined}
      onClick={() => submitReview({ record_type: objectId === null ? "object" : "attribute", action, records: records.map((item) => ({ record_id: item.id, expected_revision: item.revision })) })}>{action === "lock" ? "Lock" : "Unlock"}</button>;
  })}</div>;
  const error = uncertain ? "Save was not confirmed. Retry the same request before making another change."
    : review.error instanceof ApiError && review.error.code === "metadata_revision_conflict" ? "This metadata changed. Refresh and review its current value."
    : review.error instanceof ApiError && review.error.code === "tenant_workflow_conflict" ? "A workflow is active. Wait for it to finish, then refresh."
    : "Could not save. Check the record lock and your Tenant Lock, then refresh.";

  return <div className="metadata-enrichment-screen page-enter">
    <header className="workflow-commandbar">
      <h1>Enrichment</h1>
      <div className="target-review-actions">
        <button className="button button-secondary button-small" type="button" disabled={busy || objects.isFetching || detail.isFetching} onClick={() => void refresh()}>Refresh</button>
        {objectId === null ? <button className="button button-primary button-small" type="button" disabled={!hasTenantLock || busy || refreshRequired || changed} title={hasTenantLock ? undefined : "Owned Tenant Lock required"} onClick={() => setRunDialog("object")}>Run object enrichment</button> : null}
        <button className={`button button-${objectId === null ? "secondary" : "primary"} button-small`} type="button" disabled={!hasTenantLock || busy || refreshRequired || changed || (objectId !== null && (!current || current.is_locked || current.source_tenant_id !== tenantId))} title={hasTenantLock ? undefined : "Owned Tenant Lock required"} onClick={() => setRunDialog("attribute")}>Run attribute enrichment</button>
      </div>
    </header>
    <EnrichmentHistory api={api} tenantId={tenantId} modelId={model.model_id} focusRunId={recentRunId} onRefresh={refresh} controls={lockControls} disabled={busy} />
    {!editor && review.isError ? <div role="alert"><p>{error}</p>{uncertain ? <button type="button" className="button button-secondary button-small" onClick={() => { if (pendingReview.current) review.mutate(pendingReview.current); }}>Retry same save</button> : null}</div> : null}
    {notice ? <p role="status">{notice}</p> : null}
    {objectId === null ? <section className="workflow-surface" aria-label="Current metadata">
      <form className="enrichment-search" onSubmit={(event) => { event.preventDefault(); if (!busy) { setSelectedIds(new Set()); setObjectFilter(search.trim()); } }}>
        <label htmlFor="enrichment-object-search">Objects</label><input id="enrichment-object-search" type="search" placeholder="Find an Object" value={search} disabled={busy} onChange={(event) => setSearch(event.target.value)} />
        <button type="submit" className="button button-secondary button-small" disabled={busy}>Search</button>
      </form>
      {objects.isPending ? <p className="surface-state" aria-busy="true">Loading metadata…</p> : objects.isError || changed ? <p className="surface-state" role="alert">Metadata is unavailable or the Model changed. Refresh to retry.</p> : <>
        <div className="workflow-table-scroll table-scroll"><table className="enrichment-metadata-table" aria-label="Object metadata"><thead><tr><th className="selection-cell">{checkbox()}</th><th>Schema</th><th>Object</th><th>Description</th><th>Zone</th><th>Attributes</th><th>Actions</th><th><span className="sr-only">Details</span></th></tr></thead>
          <tbody>{rows.map((object) => <tr key={object.object_id}><td className="selection-cell">{checkbox(object.object_id)}</td><td>{object.object_schema}</td><td><strong>{object.object_name}</strong>{object.is_locked ? <span className="metadata-lock-label">Locked</span> : null}</td><td className="enrichment-description">{object.object_description || <span className="field-help">No description</span>}</td><td>{zoneLabel(object.zone_code)}</td><td>{object.attribute_count}</td><td>{recordActions(object)}</td><td><button type="button" className="text-action" id={`enrichment-object-${object.object_id}`} disabled={busy} aria-label={`Show details for ${object.object_name}`} onClick={() => { returnObject.current = object.object_id; setObjectId(object.object_id); }}>Show details</button></td></tr>)}</tbody>
        </table></div>
        {!rows.length ? <p className="empty-state compact">No Objects match this Scope.</p> : null}
        {objects.hasNextPage ? <button type="button" className="button button-secondary button-small" disabled={busy || objects.isFetching} onClick={() => void objects.fetchNextPage()}>Load more Objects</button> : null}
      </>}
    </section> : <section className="workflow-surface enrichment-object-detail" aria-label="Object metadata details">
      <button type="button" className="text-action" disabled={busy} onClick={() => setObjectId(null)}>← Back to Objects</button>
      <header className="enrichment-detail-header"><div><small>{current?.object_schema}</small><h2 tabIndex={-1} ref={heading}>{current?.object_name ?? "Object details"}</h2></div>{current ? recordActions(current) : null}</header>
      {detail.isPending ? <p aria-busy="true">Loading Attributes…</p> : !current ? <p role="alert">Object details unavailable. Refresh to retry.</p> : <>
        <p className="enrichment-object-description">{current.object_description || "No description"}</p>
        {current.is_locked ? <p className="lock-context">Object locked in Metadata. Unlock it to edit descriptions.</p> : null}
        <div className="workflow-table-scroll table-scroll"><table className="enrichment-metadata-table" aria-label={`Attributes for ${current.object_name}`}><thead><tr><th className="selection-cell">{checkbox()}</th><th>Attribute</th><th>Inferred type</th><th>Description</th><th>Actions</th></tr></thead><tbody>
          {current.attributes.slice(attributePage * 50, (attributePage + 1) * 50).map((attribute) => <tr key={attribute.attribute_id}><td className="selection-cell">{checkbox(attribute.attribute_id)}</td><td><strong>{attribute.attribute_name}</strong>{attribute.is_locked || !attribute.is_active ? <span className="metadata-lock-label">{!attribute.is_active ? "Inactive" : "Locked"}</span> : null}</td><td>{attribute.attribute_inferred_data_type ?? <span className="field-help">Not inferred</span>}</td><td className="enrichment-description">{attribute.attribute_description || <span className="field-help">No description</span>}</td><td>{recordActions(current, attribute)}</td></tr>)}
        </tbody></table></div>
        {!current.attributes.length ? <p className="empty-state compact">No Attributes.</p> : null}
        {current.attributes.length > 50 ? <div className="enrichment-pagination"><span>{attributePage * 50 + 1}–{Math.min((attributePage + 1) * 50, current.attributes.length)} of {current.attributes.length}</span><button type="button" className="button button-secondary button-small" disabled={busy || attributePage === 0} onClick={() => { setSelectedIds(new Set()); setAttributePage((page) => page - 1); }}>Previous</button><button type="button" className="button button-secondary button-small" disabled={busy || (attributePage + 1) * 50 >= current.attributes.length} onClick={() => { setSelectedIds(new Set()); setAttributePage((page) => page + 1); }}>Next</button></div> : null}
      </>}
    </section>}
    {editor ? <DescriptionEditor record={editor} busy={busy} uncertain={uncertain} canSave={hasTenantLock && !refreshRequired} error={review.isError ? error : null}
      onClose={() => setEditor(null)} onRetry={() => { if (pendingReview.current) review.mutate(pendingReview.current); }}
      onSave={(description) => submitReview({ record_type: editor.type, action: "describe", records: [{ record_id: editor.id, expected_revision: editor.revision, description }] })} /> : null}
    {runDialog ? <WorkflowRunDialog api={api} tenantId={tenantId} model={model} kind="inference" workflow="metadata_enrichment" enrichmentTarget={runDialog} readEnrichmentObject={api.readModelInputScopeObject} {...(current && runDialog === "attribute" ? { enrichmentObject: current } : {})} initialSelectedIds={[...selectedIds]}
      executeCreated={async (runId) => { await api.executeMetadataEnrichmentRun(tenantId, model.model_id, runId, model.model_revision); }}
      onClose={() => setRunDialog(null)} onCreated={async (runId) => { setRecentRunId(runId); await client.invalidateQueries({ queryKey: workflowRunQueryKeys.recent(tenantId, model.model_id, "metadata_enrichment") }); }} /> : null}
  </div>;
}

function DescriptionEditor({ record, busy, uncertain, canSave, error, onClose, onSave, onRetry }: {
  record: DescriptionRecord; busy: boolean; uncertain: boolean; canSave: boolean; error: string | null;
  onClose: () => void; onSave: (description: string | null) => void; onRetry: () => void;
}) {
  const [value, setValue] = useState(record.description ?? "");
  const dialog = useRef<HTMLElement>(null);
  const textarea = useRef<HTMLTextAreaElement>(null);
  useEffect(() => {
    const previous = document.activeElement as HTMLElement | null; textarea.current?.focus();
    return () => previous?.focus();
  }, []);
  const bytes = new TextEncoder().encode(value).length;
  return <div className="dialog-scrim" role="presentation"><section ref={dialog} className="run-configuration-dialog" role="dialog" aria-modal="true" aria-labelledby="description-editor-title" onKeyDown={(event) => {
    if (event.key === "Escape" && !busy) { event.stopPropagation(); onClose(); }
    if (event.key === "Tab") {
      const elements = Array.from(dialog.current?.querySelectorAll<HTMLElement>('button:not(:disabled), textarea:not(:disabled)') ?? []);
      const first = elements[0], last = elements.at(-1);
      if (event.shiftKey && document.activeElement === first) { event.preventDefault(); last?.focus(); }
      else if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first?.focus(); }
    }
  }}><header className="drawer-header"><h2 id="description-editor-title">Edit description</h2><button className="panel-close" type="button" aria-label="Close description editor" disabled={busy} onClick={onClose}>×</button></header>
    <form className="description-editor-form" onSubmit={(event) => { event.preventDefault(); if (canSave && !busy && bytes <= 2000 && value !== (record.description ?? "")) onSave(value.trim() || null); }}>
      <label htmlFor="metadata-description">{record.name}</label><textarea ref={textarea} id="metadata-description" value={value} disabled={busy} rows={7} onChange={(event) => setValue(event.target.value)} />
      {record.truncated ? <p role="note">This is a shortened preview. Saving replaces the full existing description.</p> : null}
      {bytes > 2000 ? <p role="alert">Description exceeds 2,000 UTF-8 bytes.</p> : null}
      {error ? <p role="alert">{error}</p> : null}
      <footer className="target-review-actions"><button className="button button-secondary" type="button" disabled={busy} onClick={onClose}>Cancel</button>
        {uncertain ? <button type="button" className="button button-primary" onClick={onRetry}>Retry same save</button> : <button className="button button-primary" type="submit" disabled={busy || !canSave || bytes > 2000 || value === (record.description ?? "")}>{busy ? "Saving…" : "Save description"}</button>}
      </footer>
    </form>
  </section></div>;
}

function EnrichmentHistory({ api, tenantId, modelId, focusRunId, onRefresh, controls, disabled }: {
  api: WorkflowRunMonitorApi; tenantId: number; modelId: number; focusRunId: number | null; onRefresh: () => Promise<void>; controls: React.ReactNode; disabled: boolean;
}) {
  const [expanded, setExpanded] = useState(false);
  const [runId, setRunId] = useState<number | null>(null);
  const recent = useInfiniteQuery({ queryKey: workflowRunQueryKeys.recent(tenantId, modelId, "metadata_enrichment"),
    queryFn: ({ pageParam }) => api.listWorkflowRuns(tenantId, modelId, "metadata_enrichment", "", 5, pageParam),
    initialPageParam: undefined as string | undefined, getNextPageParam: (page) => page.next_cursor ?? undefined });
  const detail = useQuery({ queryKey: workflowRunQueryKeys.detail(tenantId, modelId, runId ?? 0),
    queryFn: () => api.readWorkflowRun(tenantId, modelId, runId!), enabled: runId !== null });
  useEffect(() => { if (focusRunId !== null) setExpanded(true); }, [focusRunId]);
  const rows = recent.data?.pages.flatMap((page) => page.items) ?? [];
  return <section className="enrichment-history" aria-label="Workflow history"><header className="workflow-run-monitor-header"><div><h2>Workflow history</h2>{!expanded && rows[0] ? <RunStateBadge state={rows[0].workflow_run_state} /> : null}</div><div className="workflow-run-monitor-actions">{controls}
    <button className="button button-secondary button-small" type="button" disabled={disabled || recent.isFetching || detail.isFetching} onClick={() => void Promise.all([recent.refetch(), ...(runId ? [detail.refetch()] : []), onRefresh()])}>Refresh runs</button>
    <button className="button button-secondary button-small" type="button" aria-expanded={expanded} aria-controls="enrichment-run-history" onClick={() => setExpanded((value) => !value)}>{expanded ? "Hide activity" : "Show activity"}</button>
  </div></header><div id="enrichment-run-history" hidden={!expanded}>
    {recent.isPending ? <p aria-busy="true">Loading runs…</p> : recent.isError ? <p role="alert">Workflow history unavailable. Refresh to retry.</p> : !rows.length ? <p className="empty-state compact">No enrichment runs yet.</p> : <div className="workflow-table-scroll table-scroll"><table aria-label="Enrichment runs"><thead><tr><th>Run</th><th>Status</th><th>Objects</th><th>Started</th><th>Details</th></tr></thead><tbody>
      {rows.map((run) => <Fragment key={run.workflow_run_id}><tr><td>Run {run.workflow_run_id}</td><td><RunStateBadge state={run.workflow_run_state} /></td><td>{run.selected_scope_count}</td><td>{formatRequiredDateTime(run.created_at)}</td><td><button className="text-action" type="button" aria-label={`Show run ${run.workflow_run_id} details`} aria-expanded={runId === run.workflow_run_id} onClick={() => setRunId(runId === run.workflow_run_id ? null : run.workflow_run_id)}>{runId === run.workflow_run_id ? "Hide details" : "Show details"}</button></td></tr>
        {runId === run.workflow_run_id ? <tr><td colSpan={5}>{detail.isPending ? <p aria-busy="true">Loading run…</p> : detail.isError || detail.data?.model_workflow !== "metadata_enrichment" ? <p role="alert">Run details unavailable.</p> : <div className="enrichment-run-detail">{detail.data.failure_message ? <p role="alert">{detail.data.failure_message}</p> : null}<WorkflowTokenUsage usage={detail.data.token_usage} /></div>}</td></tr> : null}
      </Fragment>)}
    </tbody></table></div>}
    {recent.hasNextPage ? <button className="button button-secondary button-small" type="button" disabled={recent.isFetching} onClick={() => void recent.fetchNextPage()}>Load more runs</button> : null}
  </div></section>;
}
