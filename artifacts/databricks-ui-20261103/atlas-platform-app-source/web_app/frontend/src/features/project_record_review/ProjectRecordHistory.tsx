import { useState } from "react";
import { useInfiniteQuery, useQueryClient } from "@tanstack/react-query";
import { Link } from "@tanstack/react-router";

import type { ProjectRecordHistoryApi, ProjectReviewCommand, ProjectReviewDataset } from "./api";
import { ProjectRecordReview } from "./ProjectRecordReview";

export function ProjectRecordHistory({ api, tenantId, projectId, projectRevision, dataset, label, hasTenantLock, entityType, actions, showHeader = true }: {
  api: ProjectRecordHistoryApi; tenantId: number; projectId: number; projectRevision: number;
  showHeader?: boolean; actions?: readonly ProjectReviewCommand["action"][];
  entityType?: "logical_entity" | "dimensional_entity";
  dataset: ProjectReviewDataset; label: string; hasTenantLock: boolean;
}) {
  const client = useQueryClient();
  const [selectedIds, setSelectedIds] = useState<Set<number | string>>(new Set());
  const query = useInfiniteQuery({
    queryKey: ["project-record-history", tenantId, projectId, dataset, projectRevision, entityType],
    queryFn: ({ pageParam }) => api.listProjectReviewRecords(tenantId, projectId, dataset, projectRevision, pageParam, entityType),
    initialPageParam: 1,
    getNextPageParam: (page) => page.next_page ?? undefined,
  });
  const items = query.data?.pages.flatMap((page) => page.items) ?? [];
  const stale = query.data?.pages.some((page) => page.project_revision !== projectRevision) === true;
  return <section className="workflow-surface" aria-label={label}>
    {showHeader ? <header className="workflow-commandbar"><h2>{label}</h2>
      <button className="button button-secondary button-small" type="button" disabled={query.isFetching}
        onClick={() => { setSelectedIds(new Set()); void query.refetch(); }}>Refresh records</button>
    </header> : null}
    {dataset !== "generated_code" ? <p className="field-help">Includes inactive records.</p> : null}
    <ProjectRecordReview api={api} tenantId={tenantId} projectId={projectId} projectRevision={projectRevision}
      {...(actions ? { actions } : {})} dataset={dataset} selectedIds={selectedIds} hasTenantLock={hasTenantLock}
      disabled={query.isPending || query.isError || stale}
      onApplied={async () => { setSelectedIds(new Set()); await client.invalidateQueries({ predicate: (q) => q.queryKey[1] === tenantId }); }} />
    {query.isPending ? <p aria-busy="true">Loading records…</p>
      : query.isError || stale ? <p role="alert">Records could not be loaded at this Project revision. Refresh the Project and try again.</p>
      : items.length === 0 ? <p className="empty-state compact">No records yet.</p>
      : <div className="workflow-table-scroll table-scroll ledger-grid" role="region" tabIndex={0} aria-label={label}>
        <table aria-label={label}>
          <thead><tr>
            <th><input className="project-review-checkbox" type="checkbox" aria-label={`Select loaded ${label}`}
              checked={items.length > 0 && items.every((item) => selectedIds.has(item.record_id))}
              onChange={(event) => setSelectedIds(event.target.checked ? new Set(items.map((item) => item.record_id)) : new Set())} /></th>
            <th>Record</th><th>Status</th><th>Lock</th>{dataset === "generated_code" ? <th>SQL</th> : null}
          </tr></thead>
          <tbody>{items.map((item) => <tr key={item.record_id}>
            <td><input className="project-review-checkbox" type="checkbox" aria-label={`Select ${label} ${item.record_id}`} checked={selectedIds.has(item.record_id)}
              onChange={(event) => { const ids = new Set(selectedIds); if (event.target.checked) ids.add(item.record_id); else ids.delete(item.record_id); setSelectedIds(ids); }} /></td>
            <td>{item.label}</td><td>{item.status}</td><td>{item.is_locked ? "Locked" : "Open"}</td>
            {dataset === "generated_code" ? <td><Link className="text-action"
              to="/tenants/$tenantId/code-generation/projects/$projectId/artifacts/$artifactId"
              search={{ layer: entityType === "dimensional_entity" ? "dimensional" : "logical" }}
              params={{ tenantId: String(tenantId), projectId: String(projectId), artifactId: String(item.record_id) }}
            >Show SQL details</Link></td> : null}
          </tr>)}</tbody>
        </table>
      </div>}
    {query.hasNextPage ? <button className="button button-secondary button-small" type="button" disabled={query.isFetching}
      onClick={() => void query.fetchNextPage()}>Load more records</button> : null}
  </section>;
}
