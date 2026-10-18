import { useEffect, useRef, useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { Link, useSearch } from "@tanstack/react-router";
import { WorkspaceToolbar } from "../../shared/ui";

import type { TenantHomeRecord, TenantsApi } from "../tenants/api";
import { canAuthorProjects } from "../tenants/presentation";
import type { WorkflowsApi } from "../workflows/api";
import type { CreateProjectCommand, ProjectDetail, ProjectsApi } from "./api";
import { ProjectForm } from "./ProjectForm";

export function ProjectSettingsScreen({ api, home, project }: {
  api: Pick<ProjectsApi, "readProject" | "updateProject"> & Pick<WorkflowsApi, "readAgentCapabilities"> & Pick<TenantsApi, "readTenantHome">;
  home: TenantHomeRecord;
  project: ProjectDetail;
}) {
  const client = useQueryClient();
  const heading = useRef<HTMLHeadingElement>(null);
  const [initialProject, setInitialProject] = useState(project);
  const [formVersion, setFormVersion] = useState(0);
  const [dirty, setDirty] = useState(false);
  const [confirmRefresh, setConfirmRefresh] = useState(false);
  const [refreshing, setRefreshing] = useState(false);
  const [refreshFailed, setRefreshFailed] = useState(false);
  const [needsRefresh, setNeedsRefresh] = useState(false);
  const [savedRevision, setSavedRevision] = useState<number | null>(null);
  const tenantId = project.tenant_id;
  const projectId = project.project_id;
  const hasTenantLock = home.lock.owned_by_current_principal === true;
  const stale = initialProject.project_revision !== project.project_revision;
  const disabledReason = project.is_locked ? "Project locked. Unlock it before changing settings." : !project.is_active ? "Archived Projects are read-only."
    : !canAuthorProjects(home.tenant.effective_role) ? "Architect permission required to update Project settings."
      : !hasTenantLock ? "Tenant Lock required to update Project settings."
        : stale || needsRefresh ? "The Project changed. Your edits are preserved. Refresh saved settings before retrying."
          : undefined;

  useEffect(() => { heading.current?.focus(); }, []);

  async function refresh() {
    setRefreshing(true);
    setRefreshFailed(false);
    setConfirmRefresh(false);
    try {
      const [current, currentHome] = await Promise.all([
        api.readProject(tenantId, projectId), api.readTenantHome(tenantId),
      ]);
      client.setQueryData(["project", tenantId, projectId], current);
      client.setQueryData(["tenant-home", tenantId], currentHome);
      setInitialProject(current);
      setFormVersion((version) => version + 1);
      setDirty(false);
      setNeedsRefresh(false);
      heading.current?.focus();
    } catch {
      setRefreshFailed(true);
    } finally {
      setRefreshing(false);
    }
  }

  const mutation = useMutation({
    mutationFn: (command: CreateProjectCommand) => api.updateProject(tenantId, projectId, {
      ...command, expected_project_revision: initialProject.project_revision,
    }),
    retry: false,
    onSuccess: async (result) => {
      setSavedRevision(result.project_revision);
      setNeedsRefresh(true);
      await client.invalidateQueries({ predicate: (query) => query.queryKey[1] === tenantId, refetchType: "none" });
      await refresh();
    },
  });
  const busy = mutation.isPending || refreshing;

  return <section className="project-settings-page page-enter" aria-labelledby="project-settings-heading">
    <h1 className="project-section-title sr-only" id="project-settings-heading" ref={heading} tabIndex={-1}>Definition</h1>
    <WorkspaceToolbar actions={
      <button className="button button-secondary button-small" type="button" disabled={busy} onClick={() => {
        if (dirty) setConfirmRefresh(true);
        else { mutation.reset(); void refresh(); }
      }}>{refreshing ? "Refreshing…" : "Refresh saved settings"}</button>
    }><ProjectSettingsTabs project={project} active="definition" /></WorkspaceToolbar>
    {disabledReason ? <p className="lock-context">{disabledReason}</p> : null}
    {confirmRefresh ? <div className="project-settings-refresh" role="alert">
      <p>Refreshing replaces your unsaved edits with the saved Project settings.</p>
      <button className="button button-secondary button-small" type="button" onClick={() => setConfirmRefresh(false)}>Keep editing</button>
      <button className="button button-secondary button-small" type="button" onClick={() => { mutation.reset(); void refresh(); }}>Discard edits and refresh</button>
    </div> : null}
    {refreshFailed ? <p role="alert">Saved settings could not be loaded. Your edits are preserved. Retry Refresh saved settings.</p> : null}
    {savedRevision !== null ? <p role="status">Project settings saved at revision {savedRevision}.</p> : null}
    <ProjectForm key={`${projectId}:${formVersion}`} api={api} tenantId={tenantId} initialProject={initialProject}
      systems={home.systems}
      hasTenantLock={hasTenantLock} disabledReason={disabledReason} isPending={busy} error={mutation.error}
      onDirty={() => { setDirty(true); setSavedRevision(null); }} onSubmit={(command) => mutation.mutate(command)} />
  </section>;
}

export function ProjectSettingsTabs({ project, active }: { project: ProjectDetail; active: "definition" | "prompts" }) {
  const { layer } = useSearch({ strict: false });
  const params = { tenantId: String(project.tenant_id), projectId: String(project.project_id) };
  return <nav className="workspace-tabs" aria-label="Project settings pages">
    <Link className={active === "definition" ? "is-active" : ""} to="/tenants/$tenantId/projects/$projectId/settings"
      params={params} search={layer ? { layer } : {}} aria-current={active === "definition" ? "page" : undefined}>Definition</Link>
    <Link className={active === "prompts" ? "is-active" : ""} to="/tenants/$tenantId/projects/$projectId/settings/prompts"
      params={params} search={layer ? { layer } : {}} aria-current={active === "prompts" ? "page" : undefined}>Prompts</Link>
  </nav>;
}
