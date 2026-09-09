import { useState } from "react";
import { useInfiniteQuery, useQueryClient } from "@tanstack/react-query";
import { Link } from "@tanstack/react-router";

import type { ModelRecordHistoryApi, ModelReviewDataset } from "./api";
import { ModelRecordReview } from "./ModelRecordReview";

export function ModelRecordHistory({ api, tenantId, modelId, modelRevision, dataset, label, hasTenantLock }: {
  api: ModelRecordHistoryApi; tenantId: number; modelId: number; modelRevision: number;
  dataset: ModelReviewDataset; label: string; hasTenantLock: boolean;
}) {
  const client = useQueryClient();
  const [selectedIds, setSelectedIds] = useState<Set<number>>(new Set());
  const query = useInfiniteQuery({
    queryKey: ["model-record-history", tenantId, modelId, dataset, modelRevision],
    queryFn: ({ pageParam }) => api.listModelReviewRecords(tenantId, modelId, dataset, modelRevision, pageParam),
    initialPageParam: 1,
    getNextPageParam: (page) => page.next_page ?? undefined,
  });
  const items = query.data?.pages.flatMap((page) => page.items) ?? [];
  const stale = query.data?.pages.some((page) => page.model_revision !== modelRevision) === true;
  return <section className="workflow-surface" aria-label={label}>
    <header className="workflow-commandbar"><h2>{label}</h2>
      <button className="button button-secondary button-small" type="button" disabled={query.isFetching}
        onClick={() => { setSelectedIds(new Set()); void query.refetch(); }}>Refresh records</button>
    </header>
    <p className="field-help">Includes inactive records. Review shows required dependencies before Apply.</p>
    <ModelRecordReview api={api} tenantId={tenantId} modelId={modelId} modelRevision={modelRevision}
      dataset={dataset} selectedIds={selectedIds} hasTenantLock={hasTenantLock}
      disabled={query.isPending || query.isError || stale}
      onApplied={async () => { setSelectedIds(new Set()); await client.invalidateQueries({ predicate: (q) => q.queryKey[1] === tenantId }); }} />
    {query.isPending ? <p aria-busy="true">Loading records…</p>
      : query.isError || stale ? <p role="alert">Records could not be loaded at this Model revision. Refresh the Model and try again.</p>
      : items.length === 0 ? <p className="empty-state compact">No records yet.</p>
      : <div className="workflow-table-scroll table-scroll" tabIndex={0} aria-label={label}>
        <table aria-label={label}>
          <thead><tr>
            <th><input className="model-review-checkbox" type="checkbox" aria-label={`Select loaded ${label}`}
              checked={items.length > 0 && items.every((item) => selectedIds.has(item.record_id))}
              onChange={(event) => setSelectedIds(event.target.checked ? new Set(items.map((item) => item.record_id)) : new Set())} /></th>
            <th>Record</th><th>Status</th><th>Lock</th>{dataset === "generated_code" ? <th>SQL</th> : null}
          </tr></thead>
          <tbody>{items.map((item) => <tr key={item.record_id}>
            <td><input className="model-review-checkbox" type="checkbox" aria-label={`Select ${label} ${item.record_id}`} checked={selectedIds.has(item.record_id)}
              onChange={(event) => { const ids = new Set(selectedIds); if (event.target.checked) ids.add(item.record_id); else ids.delete(item.record_id); setSelectedIds(ids); }} /></td>
            <td>{item.label}</td><td>{item.status}</td><td>{item.is_locked ? "Locked" : "Open"}</td>
            {dataset === "generated_code" ? <td><Link className="text-action"
              to="/tenants/$tenantId/code-generation/models/$modelId/artifacts/$artifactId"
              params={{ tenantId: String(tenantId), modelId: String(modelId), artifactId: String(item.record_id) }}
            >Show SQL details</Link></td> : null}
          </tr>)}</tbody>
        </table>
      </div>}
    {query.hasNextPage ? <button className="button button-secondary button-small" type="button" disabled={query.isFetching}
      onClick={() => void query.fetchNextPage()}>Load more records</button> : null}
  </section>;
}
