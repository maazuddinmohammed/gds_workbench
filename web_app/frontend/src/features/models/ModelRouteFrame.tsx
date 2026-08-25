import type { ReactNode } from "react";
import { useQuery } from "@tanstack/react-query";

import { TenantWorkspace } from "../../app/TenantWorkspace";
import { ErrorPage, LoadingPage } from "../../shared/ui";
import type { TenantHomeRecord, TenantsApi } from "../tenants/api";
import { ModelWorkspaceShell, type ModelStage } from "./ModelWorkspaceShell";
import type { ModelDetail, ModelsApi } from "./api";

export type ModelRouteApi = Pick<TenantsApi, "readTenantHome"> & Pick<ModelsApi, "readModel">;

export interface ModelRouteContext {
  home: TenantHomeRecord;
  model: ModelDetail;
}

export function ModelRouteFrame({
  api,
  tenantId,
  modelId,
  activeStage,
  loadingLabel,
  children,
}: {
  api: ModelRouteApi;
  tenantId: number;
  modelId: number;
  activeStage: ModelStage;
  loadingLabel: string;
  children: (context: ModelRouteContext) => ReactNode;
}) {
  const validIds = validTenantModelIds(tenantId, modelId);
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
    <TenantWorkspace home={context.home} activeNav="models" model={context.model}>
      <ModelWorkspaceShell model={context.model} activeStage={activeStage}>
        {children(context)}
      </ModelWorkspaceShell>
    </TenantWorkspace>
  );
}

export function validTenantModelIds(tenantId: number, modelId: number): boolean {
  return Number.isSafeInteger(tenantId)
    && tenantId > 0
    && Number.isSafeInteger(modelId)
    && modelId > 0;
}
