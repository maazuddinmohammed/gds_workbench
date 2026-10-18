import type { HttpRequest } from "../../core/http";
import type { ObjectAttribute as PhysicalAttribute } from "../metadata/api";
export interface ObjectAttribute extends PhysicalAttribute { review_revision?: string | null; }

export type ZoneCode = "source" | "bronze";

export interface ProjectInputScopeFilters {
  zone?: string;
  systemCode?: string;
  sourceTenantCode?: string;
  objectName?: string;
}

export interface ProjectInputScopeObject {
  project_input_scope_id: number;
  object_id: number;
  connection_id: number;
  system_id: number;
  system_code: string;
  system_name: string;
  source_tenant_id: number;
  source_tenant_code: string;
  source_tenant_name: string;
  object_schema: string;
  object_name: string;
  zone_code: ZoneCode;
  object_description?: string | null;
  description_truncated?: boolean;
  is_locked?: boolean;
  review_revision?: string | null;
  batch_attribute_name: string | null;
  attribute_count: number;
  is_project_input_eligible: boolean;
  created_at: string;
  updated_at: string;
}

export interface ProjectInputScopePage {
  project_id: number;
  project_revision: number;
  items: ProjectInputScopeObject[];
  next_cursor: string | null;
}

export interface ProjectInputScopeDetail extends ProjectInputScopeObject {
  total_attribute_count?: number;
  attributes: ObjectAttribute[];
}

export interface ScopeLocation {
  tenant_id: number; tenant_code: string; tenant_name: string;
  system_code: string; system_name: string; zone_code: ZoneCode;
}
export interface ScopeCandidate {
  object_id: number; object_schema: string; object_name: string;
  system_code: string; source_tenant_code: string; zone_code: ZoneCode;
  attribute_count: number; is_in_active_scope: boolean;
}
export interface ScopeCandidateFilters {
  sourceTenantCode: string; systemCode: string; zone: ZoneCode; objectName: string;
}
export interface AddScopeCommand { object_ids: number[]; expected_project_revision: number }

export interface ProjectInputScopeApi {
  readScopeSearchOptions: (tenantId: number, projectId: number) => Promise<{ project_revision: number; locations: ScopeLocation[] }>;
  listScopeCandidates: (tenantId: number, projectId: number, filters: ScopeCandidateFilters, cursor?: string) => Promise<{ project_revision: number; items: ScopeCandidate[]; next_cursor: string | null }>;
  addScopeObjects: (tenantId: number, projectId: number, command: AddScopeCommand, key: string) => Promise<{ project_revision: number; action_count: number }>;
  listProjectInputScope: (
    tenantId: number,
    projectId: number,
    filters?: ProjectInputScopeFilters,
    pageSize?: number,
    cursor?: string,
  ) => Promise<ProjectInputScopePage>;
  readProjectInputScopeObject: (
    tenantId: number,
    projectId: number,
    objectId: number,
  ) => Promise<ProjectInputScopeDetail>;
}

export function createProjectInputScopeApi(request: HttpRequest): ProjectInputScopeApi {
  return {
    readScopeSearchOptions: (tenantId, projectId) => request(`/api/v1/tenants/${tenantId}/projects/${projectId}/input-scope/options`),
    listScopeCandidates: (tenantId, projectId, filters, cursor) => {
      const query = new URLSearchParams({ source_tenant_code: filters.sourceTenantCode, system_code: filters.systemCode, zone: filters.zone, page_size: "200" });
      if (filters.objectName.trim()) query.set("object_name", filters.objectName.trim());
      if (cursor) query.set("cursor", cursor);
      return request(`/api/v1/tenants/${tenantId}/projects/${projectId}/input-scope/candidates?${query}`);
    },
    addScopeObjects: (tenantId, projectId, command, key) => request(`/api/v1/tenants/${tenantId}/projects/${projectId}/change-sets/input-scope/add`, {
      method: "POST", headers: { "content-type": "application/json", "Idempotency-Key": key }, body: JSON.stringify(command),
    }),
    listProjectInputScope: (tenantId, projectId, filters = {}, pageSize = 200, cursor) => {
      const query = new URLSearchParams();
      const normalizedFilters = {
        zone: normalizeNaturalKeyFilter(filters.zone),
        system_code: normalizeNaturalKeyFilter(filters.systemCode),
        source_tenant_code: normalizeNaturalKeyFilter(filters.sourceTenantCode),
        object_name: normalizeNaturalKeyFilter(filters.objectName),
      };
      for (const [key, value] of Object.entries(normalizedFilters)) {
        if (value) query.set(key, value);
      }
      query.set("page_size", String(pageSize));
      if (cursor) query.set("cursor", cursor);
      return request<ProjectInputScopePage>(
        `/api/v1/tenants/${tenantId}/projects/${projectId}/input-scope?${query}`,
      );
    },
    readProjectInputScopeObject: (tenantId, projectId, objectId) =>
      request<ProjectInputScopeDetail>(
        `/api/v1/tenants/${tenantId}/projects/${projectId}/input-scope/${objectId}`,
      ),
  };
}

function normalizeNaturalKeyFilter(value: string | undefined): string {
  return value?.replace(/^ +| +$/g, "").toLowerCase() ?? "";
}
