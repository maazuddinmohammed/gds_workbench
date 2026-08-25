import type { ReactNode } from "react";
import { useQuery } from "@tanstack/react-query";

import type { ModelDetail } from "../features/models/api";
import type { TenantHomeRecord, TenantsApi } from "../features/tenants/api";
import { ErrorPage, LoadingPage } from "../shared/ui";
import { TenantWorkspace, type WorkspaceNavigation } from "./TenantWorkspace";

export interface TenantRouteContext {
  home: TenantHomeRecord;
}

export function TenantRouteFrame({
  api,
  tenantId,
  activeNav,
  loadingLabel,
  model,
  children,
}: {
  api: Pick<TenantsApi, "readTenantHome">;
  tenantId: number;
  activeNav: WorkspaceNavigation;
  loadingLabel: string;
  model?: ModelDetail;
  children: (context: TenantRouteContext) => ReactNode;
}) {
  const validTenantId = Number.isSafeInteger(tenantId) && tenantId > 0;
  const homeQuery = useQuery({
    queryKey: ["tenant-home", tenantId],
    queryFn: () => api.readTenantHome(tenantId),
    enabled: validTenantId,
  });

  if (!validTenantId) return <ErrorPage />;
  if (homeQuery.isPending) return <LoadingPage label={loadingLabel} />;
  if (homeQuery.isError) return <ErrorPage />;

  const context = { home: homeQuery.data };
  return (
    <TenantWorkspace
      home={context.home}
      activeNav={activeNav}
      {...(model ? { model } : {})}
    >
      {children(context)}
    </TenantWorkspace>
  );
}
