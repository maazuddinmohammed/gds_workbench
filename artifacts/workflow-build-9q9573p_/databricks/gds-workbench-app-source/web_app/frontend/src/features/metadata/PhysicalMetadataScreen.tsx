import { useEffect, useRef, useState } from "react";
import { Link } from "@tanstack/react-router";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { ApiError } from "../../core/http";
import { zoneLabel } from "../../shared/presentation";
import type { TenantLockState } from "../tenant_locks/api";
import {
  metadataQueryKeys,
  type MetadataApi,
  type MetadataActiveState,
  type MetadataReviewAction,
  type ObjectAttribute,
  type ObjectCatalogDetail,
  type ObjectCatalogFilters,
  type ReviewMetadataRecordsCommand,
} from "./api";

const ACTIONS: Array<[MetadataReviewAction, string]> = [
  ["lock", "Lock"], ["unlock", "Unlock"], ["deactivate", "Make inactive"], ["reactivate", "Make active"],
];
const PAGE_SIZE = 50;
const validId = (id: number) => Number.isSafeInteger(id) && id > 0;
const validRevision = (revision: string) => /^[0-9a-f]{64}$/.test(revision);
type ReviewRequest = { command: ReviewMetadataRecordsCommand; idempotencyKey: string };

export function PhysicalMetadataScreen({ api, tenantId, tenantLock, canWriteMetadata, objectId, onObjectChange }: {
  api: Pick<MetadataApi, "listMetadataObjects" | "readMetadataObject" | "reviewMetadataRecords">;
  tenantId: number;
  tenantLock: TenantLockState;
  canWriteMetadata: boolean;
  objectId: number | null;
  onObjectChange: (objectId: number | null) => void;
}) {
  const queryClient = useQueryClient();
  const headingRef = useRef<HTMLHeadingElement>(null);
  const returnFocusRef = useRef<number | null>(null);
  const reviewRequest = useRef<ReviewRequest | null>(null);
  const [filters, setFilters] = useState<ObjectCatalogFilters>({ activeState: "active" });
  const [cursor, setCursor] = useState<string | undefined>();
  const [cursorHistory, setCursorHistory] = useState<Array<string | undefined>>([]);
  const [objectSelection, setObjectSelection] = useState<Set<number>>(new Set());
  const [attributeSelection, setAttributeSelection] = useState<Set<number>>(new Set());
  const [attributeState, setAttributeState] = useState<MetadataActiveState>("all");
  const [attributePage, setAttributePage] = useState(0);
  const [notice, setNotice] = useState("");
  const [refreshRequired, setRefreshRequired] = useState(false);

  const objectsQuery = useQuery({
    queryKey: metadataQueryKeys.objects(tenantId, filters, cursor),
    queryFn: async () => {
      const page = await api.listMetadataObjects(tenantId, filters, PAGE_SIZE, cursor);
      if (page.tenant_id !== tenantId || page.items.length > PAGE_SIZE
        || new Set(page.items.map((row) => row.object_id)).size !== page.items.length
        || page.items.some((row) => !validId(row.object_id) || row.source_tenant_id !== tenantId || !validRevision(row.review_revision))) {
        throw new Error("Catalog response unavailable");
      }
      return page;
    },
  });
  const detailQuery = useQuery({
    queryKey: metadataQueryKeys.object(tenantId, objectId),
    queryFn: async () => {
      const detail = await api.readMetadataObject(tenantId, objectId!);
      if (detail.object_id !== objectId || detail.source_tenant_id !== tenantId
        || !validRevision(detail.review_revision) || detail.attributes.length > 2000
        || detail.attribute_count !== detail.attributes.length
        || new Set(detail.attributes.map((row) => row.attribute_id)).size !== detail.attributes.length
        || detail.attributes.some((row) => !validId(row.attribute_id) || !validRevision(row.review_revision))) {
        throw new Error("Object response unavailable");
      }
      return detail;
    },
    enabled: objectId !== null,
  });
  const objects = objectsQuery.isError ? [] : objectsQuery.data?.items ?? [];
  const detail = detailQuery.isError ? undefined : detailQuery.data;
  const hasTenantLock = () => tenantLock.is_locked && tenantLock.owned_by_current_principal === true
    && tenantLock.expires_at !== null && Date.parse(tenantLock.expires_at) > Date.now();
  const accessReason = !canWriteMetadata ? "Developer permission or higher is required."
    : !hasTenantLock() ? "Own an unexpired Tenant Lock to review metadata."
      : refreshRequired ? "Refresh and review the current records before another action." : "";

  const mutation = useMutation({
    mutationFn: async (request: ReviewRequest) => {
      const result = await api.reviewMetadataRecords(tenantId, request.command, request.idempotencyKey);
      const expectedIds = request.command.records.map((row) => row.record_id);
      if (result.records.length !== expectedIds.length
        || result.records.some((row, index) => row.record_id !== expectedIds[index] || !validRevision(row.review_revision))
        || !Number.isInteger(result.action_count) || result.action_count < 0 || result.action_count > expectedIds.length) {
        throw new Error("Review outcome unavailable");
      }
      return result;
    },
    onSuccess: async (result) => {
      reviewRequest.current = null;
      setObjectSelection(new Set());
      setAttributeSelection(new Set());
      setCursor(undefined);
      setCursorHistory([]);
      setAttributePage(0);
      setNotice(`${result.records.length} record${result.records.length === 1 ? "" : "s"} reviewed; ${result.action_count} changed.`);
      await Promise.all([
        "metadata-objects", "metadata-object", "metadata-rows", "tenant-home",
        "model-input-scope", "model-input-scope-object", "workflow-run-bronze-scope",
        "workflow-run-enrichment-scope", "workflow-run-dimensional-scope",
        "mapping-run-targets", "mapping-run-systems", "code-generation-targets",
      ].map((prefix) => queryClient.invalidateQueries({ queryKey: [prefix, tenantId] })));
    },
    onError: (error) => {
      if (error instanceof ApiError && error.status < 500 && error.status !== 408) {
        reviewRequest.current = null;
        setObjectSelection(new Set());
        setAttributeSelection(new Set());
        setRefreshRequired(true);
      }
    },
  });
  const retryable = mutation.isError && reviewRequest.current !== null;
  const busy = mutation.isPending || retryable;
  const selectionDisabled = busy || Boolean(accessReason);
  const clearAttributes = () => { setAttributeSelection(new Set()); setAttributePage(0); };

  useEffect(() => {
    setAttributeSelection(new Set());
    setAttributePage(0);
    setAttributeState("all");
    if (objectId === null && returnFocusRef.current !== null) {
      const trigger = document.getElementById(`metadata-object-${returnFocusRef.current}`);
      (trigger ?? headingRef.current)?.focus();
      returnFocusRef.current = null;
    }
  }, [objectId]);

  const review = (recordType: "object" | "attribute", action: MetadataReviewAction, rows: Array<{ id: number; revision: string; locked: boolean }>) => {
    if (busy || !canWriteMetadata || !hasTenantLock() || refreshRequired || rows.length === 0 || rows.length > 200
      || rows.some((row) => !validId(row.id) || !validRevision(row.revision))
      || ((action === "deactivate" || action === "reactivate") && rows.some((row) => row.locked))
      || (recordType === "attribute" && (!detail || detail.is_locked || detailQuery.isFetching))) return;
    setNotice("");
    reviewRequest.current = {
      command: { record_type: recordType, action, records: rows.map((row) => ({ record_id: row.id, expected_revision: row.revision })).sort((a, b) => a.record_id - b.record_id) },
      idempotencyKey: globalThis.crypto.randomUUID(),
    };
    mutation.mutate(reviewRequest.current);
  };
  const refresh = async () => {
    if (busy) return;
    setObjectSelection(new Set());
    clearAttributes();
    setNotice("");
    mutation.reset();
    const results = await Promise.all([
      objectsQuery.refetch(),
      objectId !== null ? detailQuery.refetch() : Promise.resolve(null),
      queryClient.invalidateQueries({ queryKey: ["tenant-home", tenantId] }),
    ]);
    if (!results[0]?.isError && !results[1]?.isError) setRefreshRequired(false);
  };
  const selectedObjects = objects.filter((row) => objectSelection.has(row.object_id));
  const filteredAttributes = detail?.attributes.filter((row) => attributeState === "all" || row.is_active === (attributeState === "active")) ?? [];
  const attributes = filteredAttributes.slice(attributePage * PAGE_SIZE, (attributePage + 1) * PAGE_SIZE);
  const selectedAttributes = attributes.filter((row) => attributeSelection.has(row.attribute_id));

  return (
    <main className="workspace metadata-workspace physical-metadata-workspace page-enter">
      <header className="metadata-commandbar">
        <div><p className="eyebrow">Physical metadata</p><h1 ref={headingRef} tabIndex={-1}>Objects and Attributes</h1>
          <p>Review shared records across Models. Making a record inactive does not remove its Model Scope membership.</p></div>
        <div><Link className="button button-secondary button-small" to="/tenants/$tenantId/metadata" params={{ tenantId: String(tenantId) }}>Metadata sheets</Link>
          <button className="button button-secondary button-small" disabled={busy || objectsQuery.isFetching || (objectId !== null && detailQuery.isFetching)} onClick={() => void refresh()}>Refresh</button></div>
      </header>
      <p className="physical-review-access">{accessReason || "Tenant Lock owned. Locking preserves a record; unlock it before changing its active state."}</p>
      {notice ? <p role="status" className="physical-review-notice">{notice}</p> : null}
      {mutation.isError ? <div className="surface-state is-error" role="alert"><p>{reviewError(mutation.error, retryable)}</p>
        {retryable ? <button className="button button-secondary button-small" onClick={() => { if (reviewRequest.current) mutation.mutate(reviewRequest.current); }}>Retry review</button> : null}</div> : null}
      {mutation.isPending ? <p role="status">Reviewing selected metadata…</p> : null}
      <form className="workflow-filterbar physical-catalog-filters" onSubmit={(event) => {
        event.preventDefault();
        if (busy) return;
        const values = new FormData(event.currentTarget);
        const zone = String(values.get("zone") ?? "");
        setFilters({ activeState: values.get("state") as MetadataActiveState, ...(zone ? { zone: zone as NonNullable<ObjectCatalogFilters["zone"]> } : {}), systemCode: String(values.get("system") ?? ""), sourceTenantCode: String(values.get("sourceTenant") ?? "") });
        setCursor(undefined); setCursorHistory([]); setObjectSelection(new Set());
      }}>
        <label>Object state<select name="state" defaultValue="active" disabled={busy}><StateOptions /></select></label>
        <label>Zone<select name="zone" defaultValue="" disabled={busy}><option value="">All zones</option>{["source", "bronze", "silver", "gold"].map((zone) => <option key={zone} value={zone}>{zoneLabel(zone)}</option>)}</select></label>
        <label>System code<input name="system" maxLength={100} disabled={busy} /></label>
        <label>Source Tenant code<input name="sourceTenant" maxLength={100} disabled={busy} /></label>
        <button className="button button-secondary button-small" disabled={busy}>Apply filters</button>
      </form>
      <section className="physical-object-ledger" aria-label="Object catalog">
        <ReviewActions label="selected Objects" count={selectedObjects.length} disabled={selectionDisabled || objectsQuery.isFetching || objectsQuery.isError} locked={selectedObjects.some((row) => row.is_locked)} onReview={(action) => review("object", action, selectedObjects.map((row) => ({ id: row.object_id, revision: row.review_revision, locked: row.is_locked })))} />
        {objectsQuery.isPending ? <div className="surface-state" aria-busy="true">Loading Objects…</div>
          : objectsQuery.isError ? <div role="alert" className="surface-state is-error">Objects could not be loaded. Refresh to try again.</div>
            : !objects.length ? <div className="empty-state compact">No Objects match these catalog filters.</div>
              : <div className="table-scroll physical-catalog-scroll" tabIndex={0} role="region" aria-label="Object catalog table"><table aria-label="Physical Objects"><thead><tr>
                <th><input type="checkbox" aria-label="Select Object page" checked={objects.length > 0 && objects.every((row) => objectSelection.has(row.object_id))} disabled={selectionDisabled || objectsQuery.isFetching} onChange={(event) => setObjectSelection(event.target.checked ? new Set(objects.map((row) => row.object_id)) : new Set())} /></th>
                <th scope="col">Object</th><th scope="col">Zone</th><th scope="col">System</th><th scope="col">Source Tenant</th><th scope="col">State</th><th scope="col">Lock</th><th scope="col">Attributes</th><th scope="col">Details</th>
              </tr></thead><tbody>{objects.map((row) => <tr key={row.object_id} className={objectId === row.object_id ? "is-active" : ""}>
                <td><input type="checkbox" aria-label={`Select Object ${row.object_schema}.${row.object_name}`} checked={objectSelection.has(row.object_id)} disabled={selectionDisabled || objectsQuery.isFetching} onChange={(event) => setObjectSelection(toggleSelection(objectSelection, row.object_id, event.target.checked))} /></td>
                <th scope="row">{row.object_schema}.{row.object_name}</th><td>{zoneLabel(row.zone_code)}</td><td>{row.system_code}</td><td>{row.source_tenant_code}</td><td>{row.is_active ? "Active" : "Inactive"}</td><td>{row.is_locked ? "Locked" : "Unlocked"}</td><td>{row.attribute_count}</td>
                <td><button id={`metadata-object-${row.object_id}`} className="text-action" disabled={busy} aria-label={`Show details for ${row.object_schema}.${row.object_name}`} aria-expanded={objectId === row.object_id} onClick={() => { returnFocusRef.current = row.object_id; onObjectChange(row.object_id); }}>Show details</button></td>
              </tr>)}</tbody></table></div>}
        <div className="physical-page-controls"><span>Page {cursorHistory.length + 1} · {objects.length} Objects shown</span>
          <button className="button button-secondary button-small" disabled={busy || objectsQuery.isFetching || !cursorHistory.length} onClick={() => { setCursor(cursorHistory.at(-1)); setCursorHistory(cursorHistory.slice(0, -1)); setObjectSelection(new Set()); }}>Previous Objects</button>
          <button className="button button-secondary button-small" disabled={busy || objectsQuery.isFetching || objectsQuery.isError || !objectsQuery.data?.next_cursor} onClick={() => { setCursorHistory([...cursorHistory, cursor]); setCursor(objectsQuery.data?.next_cursor ?? undefined); setObjectSelection(new Set()); }}>Next Objects</button></div>
      </section>
      {objectId !== null ? <ObjectInspector key={objectId} detail={detail} loading={detailQuery.isPending} error={detailQuery.isError} busy={busy} disabled={selectionDisabled || detailQuery.isFetching} attributes={attributes} attributeState={attributeState} attributePage={attributePage} attributeCount={filteredAttributes.length} selected={attributeSelection}
        onClose={() => { if (!busy) { returnFocusRef.current ??= objectId; onObjectChange(null); } }}
        onStateChange={(state) => { setAttributeState(state); clearAttributes(); }}
        onPageChange={(page) => { setAttributePage(page); setAttributeSelection(new Set()); document.getElementById("physical-attribute-heading")?.focus(); }}
        onSelectionChange={setAttributeSelection}
        onObjectReview={(action) => { if (detail && !detailQuery.isFetching) review("object", action, [{ id: detail.object_id, revision: detail.review_revision, locked: detail.is_locked }]); }}
        onAttributeReview={(action) => review("attribute", action, selectedAttributes.map((row) => ({ id: row.attribute_id, revision: row.review_revision, locked: row.is_locked })))} /> : null}
    </main>
  );
}

function ObjectInspector({ detail, loading, error, busy, disabled, attributes, attributeState, attributePage, attributeCount, selected, onClose, onStateChange, onPageChange, onSelectionChange, onObjectReview, onAttributeReview }: {
  detail: ObjectCatalogDetail | undefined; loading: boolean; error: boolean; busy: boolean; disabled: boolean;
  attributes: ObjectAttribute[]; attributeState: MetadataActiveState; attributePage: number; attributeCount: number; selected: Set<number>;
  onClose: () => void; onStateChange: (state: MetadataActiveState) => void; onPageChange: (page: number) => void; onSelectionChange: (selected: Set<number>) => void;
  onObjectReview: (action: MetadataReviewAction) => void; onAttributeReview: (action: MetadataReviewAction) => void;
}) {
  const closeRef = useRef<HTMLButtonElement>(null);
  useEffect(() => { closeRef.current?.focus(); }, []);
  const attributesDisabled = disabled || !detail || detail.is_locked;
  return <aside className="scope-object-inspector physical-object-inspector" aria-label="Physical Object details" onKeyDown={(event) => { if (event.key === "Escape" && !busy) { event.stopPropagation(); onClose(); } }}>
    <header><div><small>Physical Object</small><h2>{detail ? `${detail.object_schema}.${detail.object_name}` : "Object details"}</h2></div><button ref={closeRef} className="panel-close" disabled={busy} aria-label="Close physical Object details" onClick={onClose}>×</button></header>
    {loading ? <div className="surface-state" aria-busy="true">Loading Object details…</div>
      : error || !detail ? <div className="surface-state is-error" role="alert">Object details are unavailable. Refresh to check access and current metadata. Catalog detail supports up to 2,000 Attributes.</div>
        : <>
          <p>{zoneLabel(detail.zone_code)} · {detail.system_code} · {detail.is_active ? "Active" : "Inactive"} · {detail.is_locked ? "Locked" : "Unlocked"}</p>
          <p className="physical-description">{detail.object_description ?? "No Object description recorded."}</p>
          <ReviewActions label="Object" count={1} disabled={disabled} locked={detail.is_locked} onReview={onObjectReview} />
          <section aria-label="Attribute review"><header className="physical-attribute-heading"><h3 id="physical-attribute-heading" tabIndex={-1}>Attributes</h3><label>Attribute state<select value={attributeState} disabled={busy} onChange={(event) => onStateChange(event.target.value as MetadataActiveState)}><StateOptions /></select></label></header>
            {detail.is_locked ? <p>Unlock the Object first to review its Attributes.</p> : null}
            {!detail.is_active ? <p>This Object is inactive. Attribute state is independent; making an Attribute active does not activate its Object.</p> : null}
            <ReviewActions label="selected Attributes" count={selected.size} disabled={attributesDisabled} locked={attributes.some((row) => selected.has(row.attribute_id) && row.is_locked)} onReview={onAttributeReview} />
            {!attributes.length ? <div className="empty-state compact">No Attributes match this state.</div> : <div className="table-scroll physical-attribute-scroll" role="region" aria-label="Attribute catalog table" tabIndex={0}><table aria-label={`Physical Attributes for ${detail.object_name}`}><thead><tr>
              <th><input type="checkbox" aria-label="Select Attribute page" checked={attributes.every((row) => selected.has(row.attribute_id))} disabled={attributesDisabled} onChange={(event) => onSelectionChange(event.target.checked ? new Set(attributes.map((row) => row.attribute_id)) : new Set())} /></th>
              <th scope="col">Attribute</th><th scope="col">Storage type</th><th scope="col">Inferred type</th><th scope="col">State</th><th scope="col">Lock</th><th scope="col">Description and properties</th>
            </tr></thead><tbody>{attributes.map((row) => <tr key={row.attribute_id}>
              <td><input type="checkbox" aria-label={`Select Attribute ${row.attribute_name}`} checked={selected.has(row.attribute_id)} disabled={attributesDisabled} onChange={(event) => onSelectionChange(toggleSelection(selected, row.attribute_id, event.target.checked))} /></td>
              <th scope="row">{row.attribute_name}</th><td>{row.attribute_data_type}</td><td>{row.attribute_inferred_data_type ?? "Not inferred"}</td><td>{row.is_active ? "Active" : "Inactive"}</td><td>{row.is_locked ? "Locked" : "Unlocked"}</td>
              <td><details><summary>Details for {row.attribute_name}</summary><p className="physical-description">{row.attribute_description ?? "No Attribute description recorded."}</p><dl className="object-facts">
                <div><dt>Nullable</dt><dd>{row.attribute_nullability ? "Yes" : "No"}</dd></div><div><dt>Ordinal</dt><dd>{row.attribute_ordinal_position}</dd></div>
                <div><dt>Key roles</dt><dd>{[row.is_surrogate_key ? "Surrogate" : "", row.is_natural_key ? "Natural" : ""].filter(Boolean).join(", ") || "None"}</dd></div>
                <div><dt>Masking required</dt><dd>{row.is_masking_required ? "Yes" : "No"}</dd></div><div><dt>Metadata</dt><dd>{row.is_meta_data ? "Yes" : "No"}</dd></div><div><dt>Mapped</dt><dd>{row.is_mapped ? "Yes" : "No"}</dd></div><div><dt>Purge</dt><dd>{row.is_purge ? "Yes" : "No"}</dd></div>
              </dl></details></td>
            </tr>)}</tbody></table></div>}
            <div className="physical-page-controls"><span>{attributes.length} of {attributeCount} Attributes · Page {attributePage + 1}</span><button className="button button-secondary button-small" disabled={busy || attributePage === 0} onClick={() => onPageChange(attributePage - 1)}>Previous Attributes</button><button className="button button-secondary button-small" disabled={busy || (attributePage + 1) * PAGE_SIZE >= attributeCount} onClick={() => onPageChange(attributePage + 1)}>Next Attributes</button></div>
          </section>
        </>}
  </aside>;
}

function ReviewActions({ label, count, disabled, locked, onReview }: { label: string; count: number; disabled: boolean; locked: boolean; onReview: (action: MetadataReviewAction) => void }) {
  return <div className="physical-review-actions" role="group" aria-label={`Review ${label}`}>
    <span>{label === "Object" ? "This Object" : `${count} ${label}`}</span>
    {ACTIONS.map(([action, title]) => <button key={action} className="button button-secondary button-small" disabled={disabled || !count || count > 200 || (locked && (action === "deactivate" || action === "reactivate"))} title={locked && (action === "deactivate" || action === "reactivate") ? "Unlock selected records before changing their active state." : undefined} aria-label={`${title} ${label}`} onClick={() => onReview(action)}>{title}</button>)}
  </div>;
}
function StateOptions() { return <><option value="active">Active</option><option value="inactive">Inactive</option><option value="all">All</option></>; }
function toggleSelection(selected: Set<number>, id: number, checked: boolean): Set<number> {
  const next = new Set(selected);
  if (checked && next.size < 200) next.add(id); else if (!checked) next.delete(id);
  return next;
}
function reviewError(error: Error, ambiguous: boolean): string {
  if (ambiguous) return "The review outcome is not confirmed. Retry the same review to retrieve its outcome before making another change.";
  if (!(error instanceof ApiError)) return "The review could not be completed. Refresh and try again.";
  if (error.code === "object_locked") return "The Object is locked. Refresh, unlock the Object, then review again.";
  if (error.code === "attribute_locked") return "Selected Attributes are locked. Refresh, unlock them, then change their active state.";
  if (error.code === "tenant_workflow_conflict") return "A Workflow Run is active. Wait for it to finish, then refresh before reviewing metadata.";
  if (error.code === "metadata_revision_conflict") return "Selected metadata changed after it was read. Refresh and select the current records.";
  if (error.code === "metadata_selection_conflict" || error.status === 404) return "Some selected records are no longer available. Refresh and select again.";
  if (error.code === "metadata_review_conflict") return "This request key belongs to another review. Refresh before starting a new action.";
  if (error.status === 403) return "Review was not authorized. Check your permission and owned Tenant Lock, then refresh.";
  return "The review was rejected. Refresh and check the selected records before retrying.";
}
