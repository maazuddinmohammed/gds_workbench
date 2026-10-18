import { useState } from "react";
import { useInfiniteQuery, useQuery, useQueryClient } from "@tanstack/react-query";
import type { ProjectDetail } from "../projects/api";
import { contextQueryKeys, loadContextSystems, type ContextGroupFilters, type ContextApi } from "./api";
import { ContextGroupsLedger } from "./ContextLedgers";
import { ContextEditor } from "./ContextEditor";
import { WorkflowCommandCenter, WorkflowCommandTools } from "../workflows/WorkflowCommandCenter";

export function ContextScreen({ api, tenantId, project, hasTenantLock, authoringDisabledReason }: { api: ContextApi; tenantId: number; project: ProjectDetail; hasTenantLock: boolean; authoringDisabledReason?: string | undefined }) {
  const queryClient = useQueryClient();
  const [editing, setEditing] = useState(false);
  const [savedNotice, setSavedNotice] = useState(false);
  const [filters, setFilters] = useState<ContextGroupFilters>({});
  const types = useQuery({ queryKey: contextQueryKeys.types(tenantId, project.project_id), queryFn: () => api.listContextTypes(tenantId, project.project_id) });
  const systems = useQuery({ queryKey: contextQueryKeys.systems(tenantId, project.project_id), queryFn: () => loadContextSystems(api, tenantId, project.project_id) });
  const groups = useInfiniteQuery({
    queryKey: contextQueryKeys.groups(tenantId, project.project_id, filters),
    queryFn: ({ pageParam }) => api.listContextGroups(tenantId, project.project_id, filters, 200, pageParam),
    initialPageParam: undefined as string | undefined, getNextPageParam: (page) => page.next_cursor ?? undefined,
  });
  const saved = async () => {
    await Promise.all([queryClient.invalidateQueries({ queryKey: ["project", tenantId, project.project_id] }), queryClient.invalidateQueries({ predicate: ({ queryKey }) => typeof queryKey[0] === "string" && queryKey[0].startsWith("context-") && queryKey[1] === tenantId && queryKey[2] === project.project_id })]);
    setSavedNotice(true);
  };
  return <WorkflowCommandCenter className="context-page page-enter" filterCount={Object.values(filters).filter((value) => value !== undefined && value !== "").length}>
    <header className="workflow-commandbar project-section-toolbar context-commandbar">
      <h1 className="project-section-title sr-only">Context groups</h1>
      <div className="workflow-command-context"><span className={hasTenantLock ? "lock-context is-held" : "lock-context"}>{hasTenantLock ? "Tenant Lock held" : authoringDisabledReason ?? "Tenant Lock required to change Context"}</span></div>
      <div className="workflow-command-actions"><WorkflowCommandTools />
        <button className="button button-secondary button-small" type="button" onClick={async () => { await Promise.all([groups.refetch(), types.refetch(), systems.refetch(), queryClient.invalidateQueries({ queryKey: ["project", tenantId, project.project_id] }), queryClient.invalidateQueries({ queryKey: ["tenant-home", tenantId] })]); }}>Refresh</button>
        <button className="button button-primary button-small" type="button" disabled={!hasTenantLock} title={!hasTenantLock ? authoringDisabledReason ?? "Tenant Lock required" : undefined} onClick={() => { setSavedNotice(false); setEditing(true); }}>Create group</button>
      </div>
    </header>
    {savedNotice ? <p className="workspace-view-context" role="status">Group saved. Choose View records to add information to it.</p> : null}
    {editing ? <ContextEditor kind="group" api={api} tenantId={tenantId} projectId={project.project_id} projectRevision={project.project_revision} hasTenantLock={hasTenantLock} authoringDisabledReason={authoringDisabledReason} onClose={() => setEditing(false)} onSaved={saved} /> : null}
    <ContextGroupsLedger key={JSON.stringify(filters)} tenantId={tenantId} projectId={project.project_id} items={groups.data?.pages.flatMap((page) => page.items) ?? []} filters={filters} types={types.data?.items ?? []} systems={systems.data ?? []} choicesUnavailable={types.isError || systems.isError}
      state={{ isLoading: groups.isPending, isError: groups.isError, revisionMismatch: groups.data?.pages.some((page) => page.project_revision !== project.project_revision) ?? false, hasMore: groups.hasNextPage, isLoadingMore: groups.isFetchingNextPage }} onApplyFilters={setFilters} onLoadMore={() => { void groups.fetchNextPage(); }} />
  </WorkflowCommandCenter>;
}
