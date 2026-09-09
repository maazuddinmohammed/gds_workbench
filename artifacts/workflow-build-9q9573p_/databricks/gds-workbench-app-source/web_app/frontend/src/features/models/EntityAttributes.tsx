import { useState } from "react";
import { ModelRecordReview } from "../model_record_review/ModelRecordReview";
import type { ModelRecordReviewApi } from "../model_record_review/api";
import type { ReviewStatus } from "../../shared/contracts";
import { useInfiniteQuery, useQueryClient } from "@tanstack/react-query";
import { Link } from "@tanstack/react-router";
import type { LogicalTransport } from "../logical/api";
import type { DimensionalTransport } from "../dimensional/api";

type Props = { tenantId: number; modelId: number; entityId: number; modelRevision: number; hasTenantLock: boolean } & (
  { layer: "logical"; api: ModelRecordReviewApi & Pick<LogicalTransport, "listLogicalAttributes"> } |
  { layer: "dimensional"; api: ModelRecordReviewApi & Pick<DimensionalTransport, "listDimensionalAttributes"> }
);

export function EntityAttributes(props: Props) {
  const { tenantId, modelId, entityId, layer, modelRevision, hasTenantLock } = props;
  const client = useQueryClient();
  const [selectedIds, setSelectedIds] = useState<Set<number>>(new Set());
  const [status, setStatus] = useState<ReviewStatus | "">("active");
  const query = useInfiniteQuery({
    queryKey: ["entity-detail-attributes", tenantId, modelId, layer, entityId, status],
    initialPageParam: undefined as string | undefined,
    queryFn: async ({ pageParam }) => {
      if (props.layer === "logical") {
        const page = await props.api.listLogicalAttributes(tenantId, modelId, { logicalEntityId: entityId, ...(status ? { status } : {}) }, 200, pageParam);
        return { revision: page.model_revision, next: page.next_cursor, items: page.items.map((item) => ({
          id: item.logical_attribute_id, name: item.logical_attribute_name, type: item.logical_attribute_data_type,
          nullable: item.logical_attribute_is_nullable, status: item.logical_attribute_status, locked: item.logical_attribute_is_locked,
          role: [item.logical_attribute_is_primary_key && "Primary key", item.logical_attribute_is_natural_key && "Natural key", item.logical_attribute_is_surrogate_key && "Surrogate key", item.logical_attribute_is_audit_column && "Audit"].filter(Boolean).join(" · ") || "—",
        })) };
      }
      const page = await props.api.listDimensionalAttributes(tenantId, modelId, { dimensionalEntityId: entityId, ...(status ? { status } : {}) }, 200, pageParam);
      return { revision: page.model_revision, next: page.next_cursor, items: page.items.map((item) => ({
        id: item.dimensional_attribute_id, name: item.dimensional_attribute_name, type: item.dimensional_attribute_data_type,
        nullable: item.dimensional_attribute_is_nullable, status: item.dimensional_attribute_status, locked: item.dimensional_attribute_is_locked,
        role: [item.dimensional_attribute_key_role !== "none" ? `${item.dimensional_attribute_key_role} key` : item.dimensional_attribute_role, item.dimensional_attribute_is_grain_component && "Grain"].filter(Boolean).join(" · ").replaceAll("_", " "),
      })) };
    },
    getNextPageParam: (page) => page.next ?? undefined,
  });
  const stale = query.data?.pages.some((page) => page.revision !== modelRevision);
  return <section className="detail-section" aria-label="Entity Attributes">
    <header><h2>Attributes</h2><div className="target-review-actions"><label className="field-help">Status <select aria-label="Attribute status" value={status} onChange={(event) => { setSelectedIds(new Set()); setStatus(event.target.value as ReviewStatus | ""); }}><option value="active">Active</option><option value="inactive">Inactive</option><option value="">All</option></select></label><button type="button" className="text-action" disabled={query.isFetching} onClick={() => { setSelectedIds(new Set()); void Promise.all([query.refetch(), client.invalidateQueries({ queryKey: ["model", tenantId, modelId] })]); }}>Refresh Attributes</button></div></header>
    {selectedIds.size > 0 ? <ModelRecordReview api={props.api} tenantId={tenantId} modelId={modelId} modelRevision={modelRevision} hasTenantLock={hasTenantLock} dataset={layer === "logical" ? "logical_attribute" : "dimensional_attribute"} selectedIds={selectedIds} disabled={query.isPending || query.isError || query.isFetching || stale === true} onApplied={async () => { setSelectedIds(new Set()); await client.invalidateQueries({ predicate: (cached) => cached.queryKey[1] === tenantId }); }} /> : null}
    {query.isPending ? <p aria-busy="true">Loading Attributes…</p> : query.isError || stale ? <p role="alert">Attributes could not be loaded consistently. <button className="text-action" type="button" onClick={() => void query.refetch()}>Retry</button></p> : <>
      <div className="workflow-table-scroll table-scroll"><table className="entity-detail-attributes" aria-label="Entity Attributes">
        <thead><tr><th className="selection-column"><span className="sr-only">Select</span></th><th>Attribute</th><th>Data type</th><th>Nullable</th><th>Role</th><th>Status</th><th>Lock</th><th>Actions</th></tr></thead>
        <tbody>{query.data.pages.flatMap((page) => page.items).map((item) => <tr key={item.id}>
          <td className="selection-column"><input type="checkbox" aria-label={`Select ${layer === "logical" ? "Logical" : "Dimensional"} Attribute ${item.id}`} disabled={!hasTenantLock || stale || query.isFetching} checked={selectedIds.has(item.id)} onChange={(event) => setSelectedIds((current) => { const next = new Set(current); if (event.target.checked) next.add(item.id); else next.delete(item.id); return next; })} /></td>
          <td><strong>{item.name}</strong></td><td>{item.type}</td><td>{item.nullable ? "Yes" : "No"}</td><td>{item.role}</td><td>{item.status}</td><td>{item.locked ? "Locked" : "Open"}</td>
          <td><Link className="text-action" aria-label={`Open ${layer === "logical" ? "Logical" : "Dimensional"} Attribute ${item.id}`} to={layer === "logical" ? "/tenants/$tenantId/models/$modelId/logical/attributes/$attributeId" : "/tenants/$tenantId/models/$modelId/dimensional/attributes/$attributeId"}
            params={{ tenantId: String(tenantId), modelId: String(modelId), attributeId: String(item.id) }}>Show details</Link></td>
        </tr>)}</tbody>
      </table></div>
      {!query.data.pages[0]?.items.length ? <p className="detail-empty">No matching Attributes.</p> : null}
      {query.hasNextPage ? <button className="button button-secondary button-small" type="button" disabled={query.isFetching} onClick={() => void query.fetchNextPage()}>Load more Attributes</button> : null}
    </>}
  </section>;
}
