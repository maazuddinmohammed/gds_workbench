import type { HttpRequest } from "../../core/http";
import type { ObjectAttribute } from "../metadata/api";
export type { ObjectAttribute } from "../metadata/api";

export type ZoneCode = "source" | "bronze";

export interface ModelInputScopeFilters {
  zone?: string;
  systemCode?: string;
  sourceTenantCode?: string;
  objectName?: string;
}

export interface ModelInputScopeObject {
  model_input_scope_id: number;
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
  is_model_input_eligible: boolean;
  is_dimensional_source_eligible: boolean;
  is_logical_mapping_target_eligible: boolean;
  is_dimensional_mapping_target_eligible: boolean;
  created_at: string;
  updated_at: string;
}

export interface ModelInputScopePage {
  model_id: number;
  model_revision: number;
  items: ModelInputScopeObject[];
  next_cursor: string | null;
}

export interface ModelInputScopeDetail extends ModelInputScopeObject {
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
  tenantId: number; systemCode: string; zone: ZoneCode; objectName: string;
}
export interface AddScopeCommand { object_ids: number[]; expected_model_revision: number }

export interface ModelInputScopeApi {
  readScopeSearchOptions: (tenantId: number, modelId: number) => Promise<{ model_revision: number; locations: ScopeLocation[] }>;
  listScopeCandidates: (tenantId: number, modelId: number, filters: ScopeCandidateFilters, cursor?: string) => Promise<{ model_revision: number; items: ScopeCandidate[]; next_cursor: string | null }>;
  addScopeObjects: (tenantId: number, modelId: number, command: AddScopeCommand, key: string) => Promise<{ model_revision: number; action_count: number }>;
  listModelInputScope: (
    tenantId: number,
    modelId: number,
    filters?: ModelInputScopeFilters,
    pageSize?: number,
    cursor?: string,
  ) => Promise<ModelInputScopePage>;
  readModelInputScopeObject: (
    tenantId: number,
    modelId: number,
    objectId: number,
  ) => Promise<ModelInputScopeDetail>;
}

export function createModelInputScopeApi(request: HttpRequest): ModelInputScopeApi {
  return {
    readScopeSearchOptions: (tenantId, modelId) => request(`/api/v1/tenants/${tenantId}/models/${modelId}/input-scope/options`),
    listScopeCandidates: (tenantId, modelId, filters, cursor) => {
      const query = new URLSearchParams({ placement_tenant_id: String(filters.tenantId), system_code: filters.systemCode, zone: filters.zone, page_size: "50" });
      if (filters.objectName.trim()) query.set("object_name", filters.objectName.trim());
      if (cursor) query.set("cursor", cursor);
      return request(`/api/v1/tenants/${tenantId}/models/${modelId}/input-scope/candidates?${query}`);
    },
    addScopeObjects: (tenantId, modelId, command, key) => request(`/api/v1/tenants/${tenantId}/models/${modelId}/change-sets/input-scope/add`, {
      method: "POST", headers: { "content-type": "application/json", "Idempotency-Key": key }, body: JSON.stringify(command),
    }),
    listModelInputScope: (tenantId, modelId, filters = {}, pageSize = 200, cursor) => {
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
      return request<ModelInputScopePage>(
        `/api/v1/tenants/${tenantId}/models/${modelId}/input-scope?${query}`,
      );
    },
    readModelInputScopeObject: (tenantId, modelId, objectId) =>
      request<ModelInputScopeDetail>(
        `/api/v1/tenants/${tenantId}/models/${modelId}/input-scope/${objectId}`,
      ),
  };
}

function normalizeNaturalKeyFilter(value: string | undefined): string {
  return value?.replace(/^ +| +$/g, "").toLowerCase() ?? "";
}
