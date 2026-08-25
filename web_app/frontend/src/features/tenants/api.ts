import type { HttpRequest } from "../../core/http";
import type {
  TenantLockActions,
  TenantLockState,
} from "../tenant_locks/api";

export type TenantRole =
  | "viewer"
  | "developer"
  | "architect"
  | "tenant_admin"
  | "super_admin";

export interface SessionRecord {
  display_name: string;
  actor_kind: string;
  is_super_admin: boolean;
  last_tenant_id: number | null;
}

export interface TenantRecord {
  tenant_id: number;
  tenant_code: string;
  tenant_name: string;
  tenant_description: string | null;
  tenant_visibility: "global" | "private";
  effective_role: TenantRole;
}

export interface TenantCollection {
  items: TenantRecord[];
  next_cursor: string | null;
}

export interface SystemRecord {
  system_id: number;
  system_code: string;
  system_name: string;
  system_type_name: string;
  connection_count: number;
  registered_object_count: number;
  active_model_count: number;
  last_metadata_update_time: string | null;
}

export interface TenantHomeRecord {
  tenant: TenantRecord;
  lock: TenantLockState;
  lock_actions: TenantLockActions;
  systems: SystemRecord[];
}

export interface TenantsApi {
  readSession: () => Promise<SessionRecord>;
  listTenants: () => Promise<TenantCollection>;
  selectTenant: (tenantId: number) => Promise<{ tenant_id: number }>;
  readTenantHome: (tenantId: number) => Promise<TenantHomeRecord>;
}

export function createTenantsApi(request: HttpRequest): TenantsApi {
  return {
    readSession: () => request<SessionRecord>("/api/v1/session"),
    listTenants: () => request<TenantCollection>("/api/v1/tenants?page_size=200"),
    selectTenant: (tenantId) =>
      request<{ tenant_id: number }>(`/api/v1/tenants/${tenantId}/select`, {
        method: "POST",
      }),
    readTenantHome: (tenantId) =>
      request<TenantHomeRecord>(`/api/v1/tenants/${tenantId}/home`),
  };
}
