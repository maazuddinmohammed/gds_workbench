import type { ReactNode } from "react";
import { useQuery } from "@tanstack/react-query";

import { TenantWorkspace } from "../../app/TenantWorkspace";
import { ErrorPage, LoadingPage } from "../../shared/ui";
import type { TenantHomeRecord, TenantsApi } from "../tenants/api";
import { ProjectWorkspaceShell, type ProjectStage } from "./ProjectWorkspaceShell";
import type { ProjectDetail, ProjectsApi } from "./api";
import type { TenantLockApi } from "../tenant_locks/api";
import { TenantLockControl } from "../tenant_locks/TenantLockControl";

export type ProjectRouteApi = Pick<TenantsApi, "readTenantHome"> & Pick<ProjectsApi, "readProject" | "readProjectOverview"> & Partial<Pick<ProjectsApi, "setProjectLock">>;

export interface ProjectRouteContext {
  home: TenantHomeRecord;
  project: ProjectDetail;
}

export function ProjectRouteFrame({
  api,
  tenantLockApi,
  tenantId,
  projectId,
  activeStage,
  loadingLabel,
  children,
}: {
  api: ProjectRouteApi;
  tenantLockApi?: TenantLockApi;
  tenantId: number;
  projectId: number;
  activeStage: ProjectStage;
  loadingLabel: string;
  children: (context: ProjectRouteContext) => ReactNode;
}) {
  const validIds = validTenantProjectIds(tenantId, projectId);
  const homeQuery = useQuery({
    queryKey: ["tenant-home", tenantId],
    queryFn: () => api.readTenantHome(tenantId),
    enabled: validIds,
  });
  const projectQuery = useQuery({
    queryKey: ["project", tenantId, projectId],
    queryFn: () => api.readProject(tenantId, projectId),
    enabled: validIds,
  });

  if (!validIds) return <ErrorPage />;
  if (homeQuery.isPending || projectQuery.isPending) {
    return <LoadingPage label={loadingLabel} />;
  }
  if (homeQuery.isError || projectQuery.isError) return <ErrorPage />;

  const context = { home: homeQuery.data, project: projectQuery.data };
  return (
    <TenantWorkspace home={context.home} activeNav="projects" project={context.project}>
      <ProjectWorkspaceShell api={api} tenantLock={context.home.lock} project={context.project} activeStage={activeStage}
        lockControl={tenantLockApi ? <TenantLockControl api={tenantLockApi} home={context.home} /> : undefined}>
        {children(context)}
      </ProjectWorkspaceShell>
    </TenantWorkspace>
  );
}

export function validTenantProjectIds(tenantId: number, projectId: number): boolean {
  return Number.isSafeInteger(tenantId)
    && tenantId > 0
    && Number.isSafeInteger(projectId)
    && projectId > 0;
}
