import type { ReactNode } from "react";
import { useQuery } from "@tanstack/react-query";

import type { ModelDetail, ModelsApi } from "../features/models/api";
import type { TenantHomeRecord, TenantsApi } from "../features/tenants/api";
import { ErrorPage, LoadingPage } from "../shared/ui";
import { TenantWorkspace, type WorkspaceNavigation } from "./TenantWorkspace";

export type WorkspaceModelRouteApi = Pick<TenantsApi, "readTenantHome">
  & Pick<ModelsApi, "readModel">;

export interface WorkspaceModelRouteContext {
  home: TenantHomeRecord;
  model: ModelDetail;
}

export function WorkspaceModelRouteFrame({
  api,
  tenantId,
  modelId,
  activeNav,
  loadingLabel,
  children,
}: {
  api: WorkspaceModelRouteApi;
  tenantId: number;
  modelId: number;
  activeNav: WorkspaceNavigation;
  loadingLabel: string;
  children: (context: WorkspaceModelRouteContext) => ReactNode;
}) {
  const validIds = Number.isSafeInteger(tenantId)
    && tenantId > 0
    && Number.isSafeInteger(modelId)
    && modelId > 0;
  const homeQuery = useQuery({
    queryKey: ["tenant-home", tenantId],
    queryFn: () => api.readTenantHome(tenantId),
    enabled: validIds,
  });
  const modelQuery = useQuery({
    queryKey: ["model", tenantId, modelId],
    queryFn: () => api.readModel(tenantId, modelId),
    enabled: validIds,
  });

  if (!validIds) return <ErrorPage />;
  if (homeQuery.isPending || modelQuery.isPending) {
    return <LoadingPage label={loadingLabel} />;
  }
  if (homeQuery.isError || modelQuery.isError) return <ErrorPage />;

  const context = { home: homeQuery.data, model: modelQuery.data };
  return (
    <TenantWorkspace home={context.home} activeNav={activeNav} model={context.model}>
      {children(context)}
    </TenantWorkspace>
  );
}
