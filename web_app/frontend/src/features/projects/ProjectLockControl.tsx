import { useMutation, useQueryClient } from "@tanstack/react-query";
import { ApiError } from "../../core/http";
import type { TenantHomeRecord } from "../tenants/api";
import { canAuthorProjects } from "../tenants/presentation";
import type { ProjectDetail, ProjectsApi } from "./api";

export function ProjectLockControl({ api, home, project }: {
  api: Partial<Pick<ProjectsApi, "setProjectLock">>;
  home: TenantHomeRecord;
  project: Pick<ProjectDetail, "tenant_id" | "project_id" | "project_revision" | "is_locked" | "is_active"> | undefined;
}) {
  const client = useQueryClient();
  const mutation = useMutation({
    mutationFn: async () => {
      if (!api.setProjectLock || !project) throw new Error("Project lock unavailable");
      return api.setProjectLock(project.tenant_id, project.project_id, {
        expected_project_revision: project.project_revision, is_locked: !project.is_locked,
      });
    },
    retry: false,
    onSuccess: async (result) => {
      await client.invalidateQueries({ predicate: (query) => query.queryKey[1] === result.tenant_id });
    },
  });
  const reason = !project ? "Select a Project first." : !project.is_active ? "Archived Projects are read-only."
    : !canAuthorProjects(home.tenant.effective_role) ? "Architect permission required."
      : !home.lock.owned_by_current_principal ? "Acquire the Tenant Lock first."
        : !api.setProjectLock ? "Project lock unavailable." : undefined;
  const error = mutation.error instanceof ApiError && mutation.error.code === "project_workflow_conflict"
    ? "Finish or cancel queued and running workflows before locking the Project."
    : "Project lock could not be changed. Refresh the Project and retry.";
  return <div className="projects-lock-action">
    <button className="button button-secondary button-small" type="button" disabled={!!reason || mutation.isPending}
      title={reason ?? (project?.is_locked ? "Allow Project changes and workflows" : "Block all Project changes and workflows")}
      onClick={() => mutation.mutate()}>{mutation.isPending ? "Saving…" : project?.is_locked ? "Unlock Project" : "Lock Project"}</button>
    {mutation.isError ? <p role="alert">{error}</p> : null}
  </div>;
}
