import { WorkflowCommandCenter, WorkflowCommandTools, WorkflowFilters } from "../workflows/WorkflowCommandCenter";
import { useEffect, useRef, useState } from "react";
import { Link } from "@tanstack/react-router";
import { useQuery, useQueryClient } from "@tanstack/react-query";

import { zoneLabel } from "../../shared/presentation";
import {
  metadataColumnLabel,
  metadataValueText,
  metadataQueryKeys,
  type MetadataApi,
  type MetadataActiveState,
  type ObjectAttribute,
  type ObjectCatalogDetail,
  type ObjectCatalogFilters,
  type ObjectCatalogSummary,
} from "./api";

const OBJECT_COLUMNS = [
  "tenant_code", "system_code", "connection_code", "zone_code", "object_schema", "object_name",
  "source_tenant_code", "object_type_code", "fc_object_schema", "fc_object_name", "batch_attribute_name",
  "object_description", "object_transformation", "value", "is_active", "is_locked", "attribute_count",
] as const;
const PAGE_SIZE = 50;
const validId = (id: number) => Number.isSafeInteger(id) && id > 0;
export function PhysicalMetadataScreen({ api, tenantId, objectId, onObjectChange,
  embedded = false,
}: {
  api: Pick<MetadataApi, "listMetadataObjects" | "readMetadataObject">;
  tenantId: number;
  objectId: number | null;
  onObjectChange: (objectId: number | null) => void;
  embedded?: boolean;
}) {
  const queryClient = useQueryClient();
  const headingRef = useRef<HTMLHeadingElement>(null);
  const returnFocusRef = useRef<number | null>(null);
  const [filters, setFilters] = useState<ObjectCatalogFilters>({ activeState: "active" });
  const [cursor, setCursor] = useState<string | undefined>();
  const [cursorHistory, setCursorHistory] = useState<Array<string | undefined>>([]);
  const [attributeState, setAttributeState] = useState<MetadataActiveState>("all");
  const [attributePage, setAttributePage] = useState(0);
  const objectsQuery = useQuery({
    queryKey: metadataQueryKeys.objects(tenantId, filters, cursor),
    queryFn: async () => {
      const page = await api.listMetadataObjects(tenantId, filters, PAGE_SIZE, cursor);
      if (page.tenant_id !== tenantId || page.items.length > PAGE_SIZE
        || new Set(page.items.map((row) => row.object_id)).size !== page.items.length
        || page.items.some((row) => !validId(row.object_id) || row.source_tenant_id !== tenantId)) {
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
        || detail.attributes.length > 2000
        || detail.attribute_count !== detail.attributes.length
        || new Set(detail.attributes.map((row) => row.attribute_id)).size !== detail.attributes.length
        || detail.attributes.some((row) => !validId(row.attribute_id))) {
        throw new Error("Object response unavailable");
      }
      return detail;
    },
    enabled: objectId !== null,
  });
  const objects = objectsQuery.isError ? [] : objectsQuery.data?.items ?? [];
  const detail = detailQuery.isError ? undefined : detailQuery.data;
  useEffect(() => {
    setAttributePage(0);
    setAttributeState("all");
    if (objectId === null && returnFocusRef.current !== null) {
      const trigger = document.getElementById(`metadata-object-${returnFocusRef.current}`);
      (trigger ?? headingRef.current)?.focus();
      returnFocusRef.current = null;
    }
  }, [objectId]);

  const refresh = () => Promise.all([
    objectsQuery.refetch(),
    objectId !== null ? detailQuery.refetch() : Promise.resolve(null),
    queryClient.invalidateQueries({ queryKey: ["tenant-home", tenantId] }),
  ]);
  const filteredAttributes = detail?.attributes.filter((row) => attributeState === "all" || row.is_active === (attributeState === "active")) ?? [];
  const attributes = filteredAttributes.slice(attributePage * PAGE_SIZE, (attributePage + 1) * PAGE_SIZE);
  const Workspace = embedded ? "section" : "main";

  return (
    <Workspace className={embedded ? "metadata-object-workspace" : "workspace metadata-workspace physical-metadata-workspace page-enter"}>
      <WorkflowCommandCenter className="physical-catalog-workspace" filterCount={[filters.activeState !== "active", filters.zone, filters.systemCode, filters.sourceTenantCode].filter(Boolean).length}>
      {embedded && objectId === null ? <nav className="metadata-sheet-tabs" aria-label="Object zones">
        {["", "source", "bronze", "silver", "gold"].map((zone) => <button key={zone} type="button"
          aria-current={(filters.zone ?? "") === zone ? "page" : undefined} onClick={() => {
            setFilters(({ zone: _previousZone, ...rest }) => ({ ...rest, ...(zone ? { zone: zone as NonNullable<ObjectCatalogFilters["zone"]> } : {}) }));
            setCursor(undefined); setCursorHistory([]);
          }}>{zone ? zoneLabel(zone) : "All objects"}</button>)}
      </nav> : null}
      <header className="metadata-commandbar">
        {embedded ? <h2 className="sr-only" ref={headingRef} tabIndex={-1}>Objects and Attributes</h2> : <div><p className="eyebrow">Physical metadata</p><h1 ref={headingRef} tabIndex={-1}>Objects and Attributes</h1>
          <p>Making a record inactive does not remove its Model Scope membership.</p></div>}
        <div>{!embedded || objectId === null ? <WorkflowCommandTools /> : null}{!embedded ? <Link className="button button-secondary button-small" to="/tenants/$tenantId/metadata" params={{ tenantId: String(tenantId) }}>Metadata sheets</Link> : null}
          <button className="button button-secondary button-small" disabled={objectsQuery.isFetching || (objectId !== null && detailQuery.isFetching)} onClick={() => void refresh()}>Refresh</button></div>
      </header>
      <div hidden={embedded && objectId !== null}><WorkflowFilters><form key={filters.zone ?? "all"} className="workflow-filterbar physical-catalog-filters" onSubmit={(event) => {
        event.preventDefault();
        const values = new FormData(event.currentTarget);
        const zone = String(values.get("zone") ?? "");
        setFilters({ activeState: values.get("state") as MetadataActiveState, ...(zone ? { zone: zone as NonNullable<ObjectCatalogFilters["zone"]> } : {}), systemCode: String(values.get("system") ?? ""), sourceTenantCode: String(values.get("sourceTenant") ?? "") });
        setCursor(undefined); setCursorHistory([]);
      }}>
        <label>Object state<select name="state" defaultValue={filters.activeState}><StateOptions /></select></label>
        <label>Zone<select name="zone" defaultValue={filters.zone ?? ""}><option value="">All zones</option>{["source", "bronze", "silver", "gold"].map((zone) => <option key={zone} value={zone}>{zoneLabel(zone)}</option>)}</select></label>
        <label>System code<input name="system" defaultValue={filters.systemCode} maxLength={100} /></label>
        <label>Source Tenant code<input name="sourceTenant" defaultValue={filters.sourceTenantCode} maxLength={100} /></label>
        <button className="button button-secondary button-small">Apply filters</button>
      </form></WorkflowFilters></div>
      {!embedded || objectId === null ? <section className="physical-object-ledger" aria-label="Object catalog">
        {objectsQuery.isPending ? <div className="surface-state" aria-busy="true">Loading Objects…</div>
          : objectsQuery.isError ? <div role="alert" className="surface-state is-error">Objects could not be loaded. Refresh to try again.</div>
            : !objects.length ? <div className="empty-state compact">No Objects match these catalog filters.</div>
              : <div className="table-scroll physical-catalog-scroll ledger-grid" tabIndex={0} role="region" aria-label="Object catalog table"><table aria-label="Physical Objects"><thead><tr>
                {OBJECT_COLUMNS.map((field) => <th key={field} scope="col">{metadataColumnLabel(field)}</th>)}<th scope="col">Actions</th>
              </tr></thead><tbody>{objects.map((row) => <tr key={row.object_id} className={objectId === row.object_id ? "is-active" : ""}>
                <ObjectGridCells row={row} />
                <td className="metadata-row-actions"><button id={`metadata-object-${row.object_id}`} className="text-action" aria-label={`View attributes for ${row.object_schema}.${row.object_name}`} aria-expanded={objectId === row.object_id} onClick={() => { returnFocusRef.current = row.object_id; onObjectChange(row.object_id); }}>View attributes</button>
                </td>
              </tr>)}</tbody></table></div>}
        <div className="physical-page-controls"><span>Page {cursorHistory.length + 1} · {objects.length} Objects shown</span>
          <button className="button button-secondary button-small" disabled={objectsQuery.isFetching || !cursorHistory.length} onClick={() => { setCursor(cursorHistory.at(-1)); setCursorHistory(cursorHistory.slice(0, -1)); }}>Previous Objects</button>
          <button className="button button-secondary button-small" disabled={objectsQuery.isFetching || objectsQuery.isError || !objectsQuery.data?.next_cursor} onClick={() => { setCursorHistory([...cursorHistory, cursor]); setCursor(objectsQuery.data?.next_cursor ?? undefined); }}>Next Objects</button></div>
      </section> : null}
      {objectId !== null ? <ObjectInspector key={objectId} detail={detail} loading={detailQuery.isPending} error={detailQuery.isError}
        attributes={attributes} attributeState={attributeState} attributePage={attributePage} attributeCount={filteredAttributes.length}
        embedded={embedded} onClose={() => { returnFocusRef.current ??= objectId; onObjectChange(null); }}
        onStateChange={(state) => { setAttributeState(state); setAttributePage(0); }}
        onPageChange={(page) => { setAttributePage(page); document.getElementById("physical-attribute-heading")?.focus(); }} /> : null}
      </WorkflowCommandCenter>
    </Workspace>
  );
}

function ObjectInspector({ detail, loading, error, attributes, attributeState, attributePage, attributeCount, onClose, onStateChange, onPageChange, embedded }: {
  detail: ObjectCatalogDetail | undefined; loading: boolean; error: boolean;
  attributes: ObjectAttribute[]; attributeState: MetadataActiveState; attributePage: number; attributeCount: number;
  onClose: () => void; onStateChange: (state: MetadataActiveState) => void; onPageChange: (page: number) => void;
  embedded: boolean;
}) {
  const closeRef = useRef<HTMLButtonElement>(null);
  useEffect(() => { closeRef.current?.focus(); }, []);
  return <aside className="scope-object-inspector physical-object-inspector" aria-label="Physical Object details" onKeyDown={(event) => { if (event.key === "Escape") { event.stopPropagation(); onClose(); } }}>
    {embedded ? <button ref={closeRef} type="button" className="text-action metadata-object-back" onClick={onClose}>← Objects</button> : null}
    <header><div><small>{embedded && detail ? `${zoneLabel(detail.zone_code)} / ${detail.object_schema}` : "Physical Object"}</small><h2>{detail ? embedded ? detail.object_name : `${detail.object_schema}.${detail.object_name}` : "Object details"}</h2></div>
      {!embedded ? <button ref={closeRef} className="panel-close" aria-label="Close physical Object details" onClick={onClose}>×</button> : null}</header>
    {loading ? <div className="surface-state" aria-busy="true">Loading Object details…</div>
      : error || !detail ? <div className="surface-state is-error" role="alert">Object details are unavailable. Refresh to check access and current metadata. Catalog detail supports up to 2,000 Attributes.</div>
        : <>
          <div className="table-scroll physical-object-detail-scroll ledger-grid" role="region" aria-label="Object details table" tabIndex={0}><table aria-label={`Physical Object ${detail.object_name}`}><thead><tr>
                {OBJECT_COLUMNS.map((field) => <th key={field} scope="col">{metadataColumnLabel(field)}</th>)}
          </tr></thead><tbody><tr>
            <ObjectGridCells row={detail} />
          </tr></tbody></table></div>
          <section aria-label="Attributes"><header className="physical-attribute-heading"><h3 id="physical-attribute-heading" tabIndex={-1}>Attributes</h3><div className="metadata-object-actions"><label>Attribute state<select value={attributeState} onChange={(event) => onStateChange(event.target.value as MetadataActiveState)}><StateOptions /></select></label>
            </div></header>
            {!detail.is_active ? <p>This Object is inactive. Attribute state is independent; making an Attribute active does not activate its Object.</p> : null}
            {!attributes.length ? <div className="empty-state compact">No Attributes match this state.</div> : <div className="table-scroll physical-attribute-scroll ledger-grid" role="region" aria-label="Attribute catalog table" tabIndex={0}><table aria-label={`Physical Attributes for ${detail.object_name}`}><thead><tr>
              <th scope="col">AttributeName</th><th scope="col">AttributeOrdinalPosition</th><th scope="col">AttributeDescription</th><th scope="col">AttributeDataType</th><th scope="col">AttributeInferredDataType</th><th scope="col">AttributeNullability</th><th scope="col">IsSurrogateKey</th><th scope="col">IsNaturalKey</th><th scope="col">IsMetaData</th><th scope="col">IsMaskingRequired</th><th scope="col">IsMapped</th><th scope="col">IsPurge</th><th scope="col">FcAttributeName</th><th scope="col">AttributeCustomCode</th><th scope="col">Value</th><th scope="col">IsActive</th><th scope="col">IsLocked</th>
            </tr></thead><tbody>{attributes.map((row) => <tr key={row.attribute_id}>
              <th scope="row">{row.attribute_name}</th><td>{row.attribute_ordinal_position}</td><td className="physical-grid-description">{row.attribute_description ?? "—"}{row.description_truncated ? <small>First 2,000 characters shown</small> : null}</td><td>{row.attribute_data_type}</td><td>{row.attribute_inferred_data_type ?? "Not inferred"}</td><td>{row.attribute_nullability ? "Yes" : "No"}</td><td>{row.is_surrogate_key ? "Yes" : "No"}</td><td>{row.is_natural_key ? "Yes" : "No"}</td><td>{row.is_meta_data ? "Yes" : "No"}</td><td>{row.is_masking_required ? "Yes" : "No"}</td><td>{row.is_mapped ? "Yes" : "No"}</td><td>{row.is_purge ? "Yes" : "No"}</td><td>{row.fc_attribute_name ?? "—"}</td><td className="physical-grid-code">{row.attribute_custom_code ?? "—"}{row.custom_code_truncated ? <small>First 2,000 characters shown</small> : null}</td><td>{metadataValueText(row.value)}</td><td>{row.is_active ? "Active" : "Inactive"}</td><td>{row.is_locked ? "Locked" : "Unlocked"}</td>
            </tr>)}</tbody></table></div>}
            <div className="physical-page-controls"><span>{attributes.length} of {attributeCount} Attributes · Page {attributePage + 1}</span><button className="button button-secondary button-small" disabled={attributePage === 0} onClick={() => onPageChange(attributePage - 1)}>Previous Attributes</button><button className="button button-secondary button-small" disabled={(attributePage + 1) * PAGE_SIZE >= attributeCount} onClick={() => onPageChange(attributePage + 1)}>Next Attributes</button></div>
          </section>
        </>}
  </aside>;
}

function ObjectGridCells({ row }: { row: ObjectCatalogSummary }) {
  return OBJECT_COLUMNS.map((field) => {
    if (field === "object_name") return <th scope="row" key={field}>{row.object_name}</th>;
    const truncated = (field === "object_description" && row.description_truncated)
      || (field === "object_transformation" && row.transformation_truncated);
    const text = field === "zone_code" ? zoneLabel(row.zone_code)
      : field === "is_active" ? row.is_active ? "Active" : "Inactive"
        : field === "is_locked" ? row.is_locked ? "Locked" : "Unlocked"
          : metadataValueText(row[field]);
    return <td key={field} className={field === "object_description" ? "physical-grid-description" : field === "object_transformation" ? "physical-grid-code" : undefined}>
      {text}{truncated ? <small>First 2,000 characters shown</small> : null}
    </td>;
  });
}

function StateOptions() { return <><option value="active">Active</option><option value="inactive">Inactive</option><option value="all">All</option></>; }
